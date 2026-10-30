# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Emergency mode for models that do not fit into RAM: the denoiser's blocks are streamed from the SSD.

Each block (transformer block / UNet stage) is written once to <cache>/<name>.safetensors in the
compute format. While denoising, a block is loaded onto the GPU right before it runs and dropped
right after. Blocks are loaded straight onto the GPU, which is much faster on MPS than diffusers'
group offloading.

Reading is the slow part (a step reads every streamed block), so:
  - as many blocks as the memory plan allows stay on the GPU for good (`resident_share`), spread evenly
    over the model, so the SSD keeps reading while the kept blocks compute;
  - the next blocks are read ahead (`PREFETCH` blocks, `READERS` reads at a time: a fast internal SSD
    delivers more with two reads at once, an external one is not slower for it).
"""
import collections
import json
import os
import time

import torch

FORMAT = 1
PREFETCH = 2  # blocks read ahead
READERS = 2   # reads at a time
# streamed blocks whose computing may still be queued on the GPU when the next one is loaded: MPS runs asynchronously,
# and on a busy GPU Python ran far ahead, every queued block holding its weights (FLUX.2 [klein] 9B: 18.6 GB instead
# of 13, MEASUREMENTS 7ac)
QUEUED = 2
PROFILE = os.environ.get("VK_STREAM_PROFILE") == "1"
# VK_STREAM_PROFILE=1: where the time of a streamed generation goes (waiting for the SSD, copying to the GPU,
# computing), how much was read and how often the denoiser ran (two passes per step with true guidance)
STATS = {"wait": 0.0, "copy": 0.0, "forward": 0.0, "read_gb": 0.0, "blocks": 0, "passes": 0, "peak_gb": 0.0, "skipped": 0}


def reset():
    for k in STATS:
        STATS[k] = 0 if isinstance(STATS[k], int) else 0.0


def report():
    """The profile since the last report, as one line; resets it."""
    s = dict(STATS)
    reset()
    total = s["wait"] + s["copy"] + s["forward"]
    return ("passes %d, blocks %d (%d skipped by step caching), read %.1f GB | waiting for the SSD %.1fs, to the GPU %.1fs, computing %.1fs "
            "(%.0f%% waiting) | %.2f GB/s while waiting | GPU memory peak %.1f GB" % (
                s["passes"], s["blocks"], s["skipped"], s["read_gb"], s["wait"], s["copy"], s["forward"],
                100 * s["wait"] / total if total else 0, s["read_gb"] / s["wait"] if s["wait"] else 0, s["peak_gb"]))


def _block_lists(model):
    """The ModuleLists that hold the repeated blocks (FLUX: transformer_blocks and
    single_transformer_blocks, SD 3: transformer_blocks, UNet: down/up blocks)."""
    out = []
    for name, child in model.named_children():
        if isinstance(child, torch.nn.ModuleList) and len(child) >= 2:
            out.append((name, child))
    return out


def _signature(model, dtype):
    n = sum(p.numel() for p in model.parameters())
    return {"format": FORMAT, "class": type(model).__name__, "params": n, "dtype": str(dtype)}


def _read_signature(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def resident_blocks(sizes, share):
    """Which blocks stay on the GPU: about `share` of all bytes, spread evenly over the model (every
    second, third, ... block), so that reading the others overlaps with computing these."""
    total = sum(sizes)
    budget = share * total
    if budget <= 0 or not sizes:
        return set()
    keep, used, acc = set(), 0, 0.0
    step = min(1.0, budget / total)
    for i, size in enumerate(sizes):
        acc += step
        if acc >= 1.0 - 1e-9 and used + size <= budget:
            keep.add(i)
            used += size
            acc -= 1.0
    return keep


def enable(model, device, dtype, cache_dir, report=None, resident_share=0.0):
    """Streams the blocks of `model` (loaded on the CPU, e.g. memory-mapped) from `cache_dir`; about
    `resident_share` of the blocks' bytes stays on the GPU instead. Returns (streamed, kept) block counts."""
    from safetensors.torch import save_file

    os.makedirs(cache_dir, exist_ok=True)
    sig_path = os.path.join(cache_dir, "stream.json")
    sig = _signature(model, dtype)
    valid = _read_signature(sig_path) == sig
    lists = _block_lists(model)
    blocks = [("%s.%d" % (name, i), block) for name, lst in lists for i, block in enumerate(lst)]
    if not blocks:
        raise ValueError("This model has no blocks to stream")

    from concurrent.futures import ThreadPoolExecutor
    from safetensors.torch import load as load_bytes
    pool = ThreadPoolExecutor(max_workers=READERS)
    pending = {}

    def read(path):
        # one sequential read (memory-mapped page faults are several times slower on a busy Mac)
        with open(path, "rb") as fh:
            data = fh.read()
        STATS["read_gb"] += len(data) / 1024 ** 3  # also without the profile: benchmarks report it
        return load_bytes(data)

    order = []  # the streamed blocks in the order they run
    queued = collections.deque()  # an MPS event after each streamed block's computing, oldest first
    on_mps = torch.device(device).type == "mps"

    def prefetch(q):
        """Reads the streamed block at place q of the order (and wraps to the next pass)."""
        i = order[q % len(order)]
        if i not in pending:
            pending[i] = pool.submit(read, blocks[i][1]._stream_path)

    paths = []
    for n, (key, block) in enumerate(blocks):
        path = os.path.join(cache_dir, key + ".safetensors")
        if not valid or not os.path.isfile(path):
            if any(p.device.type == "meta" for p in block.parameters()):
                raise ValueError("The SSD streaming cache of this model is incomplete: remove %s and try again" % cache_dir)
            if report:
                report(n, len(blocks))
            state = {k: v.detach().to(dtype).contiguous() for k, v in block.state_dict().items()}
            save_file(state, path)
            del state
        paths.append(path)
    keep = resident_blocks([os.path.getsize(p) for p in paths], resident_share)
    model._stream_kept = [(blocks[n][1], paths[n]) for n in sorted(keep)]
    model._stream_device = device
    model._stream_read = read
    for n, (key, block) in enumerate(blocks):
        path = paths[n]
        if n in keep:
            # stays on the GPU: loaded once from its cache file, no hooks
            block.load_state_dict({k: v.to(device) for k, v in read(path).items()}, assign=True, strict=True)
            continue
        block.to("meta")  # frees the CPU copy; the weights come back per forward
        block._stream_path = path
        block._stream_index = n
        block._stream_place = len(order)
        block._stream_key = key
        order.append(n)

        def load(module, args, kwargs=None):
            i, q = module._stream_index, module._stream_place
            # step caching (step_cache.py) decided after the first block that this run reuses the others: not read
            needed = getattr(model, "_stream_needed", None)
            if needed is not None and getattr(module, "_step_cache_skippable", False) and not needed():
                if PROFILE:
                    STATS["skipped"] += 1
                return
            while len(queued) >= QUEUED:
                queued.popleft().synchronize()
            t0 = time.time()
            prefetch(q)
            state = pending.pop(i).result()
            for ahead in range(1, PREFETCH + 1):  # the next blocks load while this one computes
                prefetch(q + ahead)
            t1 = time.time()
            STATS["wait"] += t1 - t0  # what the steps waited for the SSD (benchmarks), measured without syncing
            if PROFILE:
                STATS["blocks"] += 1
                STATS["passes"] += q == 0
            state = {k: v.to(device, non_blocking=True) for k, v in state.items()}
            for pname, A, B, s in model._stream_loras.get(module._stream_key, ()):
                w = state[pname]
                state[pname] = (w.to(torch.float32) + _delta(A, B, s, w.shape, device)).to(w.dtype)
            module.load_state_dict(state, assign=True, strict=True)
            del state
            if PROFILE:
                torch.mps.synchronize()
                STATS["copy"] += time.time() - t1
                STATS["t_fwd"] = time.time()

        def drop(module, args, output):
            if PROFILE:
                torch.mps.synchronize()
                STATS["forward"] += time.time() - STATS["t_fwd"]
                STATS["peak_gb"] = max(STATS["peak_gb"], torch.mps.driver_allocated_memory() / 1024 ** 3)
            module.to("meta")
            if on_mps:
                queued.append(torch.mps.Event())
                queued[-1].record()
            return output

        block.register_forward_pre_hook(load)
        block.register_forward_hook(drop)
    STATS["read_gb"] = 0.0  # the kept blocks' first read is not part of a step
    model._stream_blocks = {key: block for n, (key, block) in enumerate(blocks) if n not in keep}
    model._stream_loras = {}
    model._stream_resident = []
    if not valid:
        with open(sig_path, "w") as f:
            json.dump(sig, f)
    # the rest (embedders, norms, output layer) stays on the GPU
    for _, child in model.named_children():
        if not any(child is lst for _, lst in lists):
            child.to(device=device, dtype=dtype)
    for name, p in model.named_parameters(recurse=False):
        p.data = p.data.to(device=device, dtype=dtype)
    return len(order), len(keep)


def unpack_gguf(load, empty, cache_dir, dtype, source_id, report=None):
    """A GGUF denoiser made streamable: its blocks unpacked once into the stream cache in the compute format (block by
    block, each freed right after), the other weights (embedders, norms, output layer) into rest.safetensors. Later
    loads read only those, never the GGUF file again (diffusers copies a whole GGUF file into RAM).
    load() gives the GGUF model, empty() the same model on the meta device; source_id names the file (its SHA-256).
    Returns the empty model with the other weights in place, for enable()."""
    from safetensors.torch import load_file, save_file
    model = empty()
    marker = os.path.join(cache_dir, "unpacked.json")
    rest_path = os.path.join(cache_dir, "rest.safetensors")
    want = {"format": FORMAT, "source": source_id, "dtype": str(dtype)}
    if _read_signature(marker) != want or not os.path.isfile(rest_path):
        from diffusers.quantizers.gguf.utils import dequantize_gguf_tensor

        def plain(v):
            return (dequantize_gguf_tensor(v) if hasattr(v, "quant_type") else v).detach().to(dtype).contiguous()

        os.makedirs(cache_dir, exist_ok=True)
        packed = load()
        lists = _block_lists(packed)
        blocks = [("%s.%d" % (name, i), block) for name, lst in lists for i, block in enumerate(lst)]
        for n, (key, block) in enumerate(blocks):
            if report:
                report(n, len(blocks))
            save_file({k: plain(v) for k, v in block.state_dict().items()}, os.path.join(cache_dir, key + ".safetensors"))
            block.to("meta")
        names = {name for name, _ in lists}
        save_file({k: plain(v) for k, v in packed.state_dict().items() if k.split(".")[0] not in names}, rest_path)
        del packed
        with open(os.path.join(cache_dir, "stream.json"), "w") as f:
            json.dump(_signature(model, dtype), f)
        with open(marker, "w") as f:
            json.dump(want, f)
    model.load_state_dict(load_file(rest_path), strict=False, assign=True)
    return model


def kept_gb(model):
    """GB of blocks kept on the GPU."""
    return sum(os.path.getsize(p) for _, p in getattr(model, "_stream_kept", ())) / 1024 ** 3


def release_kept(model):
    """Frees the kept blocks (while a text encoder needs their memory, e.g. for a new prompt on a 16 GB Mac); their
    LoRAs come off first and come back with restore_kept."""
    if not getattr(model, "_stream_kept", None) or getattr(model, "_stream_released", None) is not None:
        return
    entries = getattr(model, "_stream_entries", [])
    set_loras(model, [])
    for block, _ in model._stream_kept:
        block.to("meta")
    model._stream_released = entries


def restore_kept(model):
    """Reads the kept blocks back onto the GPU (once per new prompt, instead of every step) with their LoRAs."""
    entries = getattr(model, "_stream_released", None)
    if entries is None:
        return
    for block, path in model._stream_kept:
        block.load_state_dict({k: v.to(model._stream_device) for k, v in model._stream_read(path).items()},
                              assign=True, strict=True)
    model._stream_released = None
    set_loras(model, entries)


def _delta(A, B, s, shape, device):
    """s * (B @ A) in the weight's shape (linear and conv LoRAs), computed in float32"""
    a = A.to(device, torch.float32).reshape(A.shape[0], -1)
    b = B.to(device, torch.float32).reshape(B.shape[0], -1)
    return (s * (b @ a)).reshape(shape)


def _fits(A, B, shape):
    """Whether B @ A has the weight's shape (linear and conv LoRAs)."""
    if A.dim() < 2 or B.dim() < 2 or not shape:
        return False
    rank, n_in = A.shape[0], A[0].numel()
    n_out = B.shape[0]
    return B[0].numel() == rank and n_out == shape[0] and n_out * n_in == torch.Size(shape).numel()


def _place(model, name):
    """Where a LoRA layer (module name relative to the denoiser) lands: (block key, parameter name, shape)
    for a streamed block's layer, (None, parameter name, shape) for a resident one, None when the model
    has no such layer. The streamed blocks keep their parameters' shapes on the meta device."""
    blocks = model._stream_blocks
    key = next((k for k in blocks if name == k or name.startswith(k + ".")), None)
    if key is not None:
        pname = "weight" if name == key else name[len(key) + 1:] + ".weight"
        p = dict(blocks[key].named_parameters()).get(pname)
        return (key, pname, tuple(p.shape)) if p is not None else None
    p = dict(model.named_parameters()).get(name + ".weight")
    if p is None or p.device.type == "meta":
        return None
    return None, name + ".weight", tuple(p.shape)


def fitting(model, entries):
    """How many LoRA entries [(module name, A, B, scale)] find a layer of their name and size."""
    n = 0
    for name, A, B, _ in entries:
        place = _place(model, name)
        if place is not None and _fits(A, B, place[2]):
            n += 1
    return n


def set_loras(model, entries):
    """LoRAs for a streamed model: entries [(module name, A, B, scale)] (module names relative to the
    denoiser, e.g. "transformer_blocks.3.attn.to_q"). Block layers get the LoRA merged into their
    weights while a block is loaded; resident layers get it added once (and taken out again on the
    next call). Entries without a layer of their name and size are left out (fitting() tells how many
    fit, before). Returns how many entries were placed."""
    for p, delta in getattr(model, "_stream_resident", []):
        p.data -= delta
    model._stream_resident = []
    model._stream_entries = list(entries)
    params = dict(model.named_parameters())
    per_block, matched = {}, 0
    for name, A, B, s in entries:
        place = _place(model, name)
        if place is None or not _fits(A, B, place[2]):
            continue
        key, pname, shape = place
        if key is not None:
            per_block.setdefault(key, []).append((pname, A, B, s))
        else:
            p = params[pname]
            delta = _delta(A, B, s, p.shape, p.device).to(p.dtype)
            p.data += delta
            model._stream_resident.append((p, delta))
        matched += 1
    model._stream_loras = per_block
    return matched


def cache_gb(cache_dir):
    if not os.path.isdir(cache_dir):
        return 0.0
    return sum(os.path.getsize(os.path.join(cache_dir, f)) for f in os.listdir(cache_dir)) / 1024 ** 3
