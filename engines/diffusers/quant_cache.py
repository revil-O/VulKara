# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Keeps components quantized with optimum-quanto on disk, so they are quantized only once: text encoders and
ControlNets; denoisers are GGUF copies (gguf_cache.py).

Quantizing runs on the CPU and is slow, and staged text encoders would pay for it on every new
prompt. The cache holds the quantized weights (safetensors), quanto's quantization map and every
buffer (non-persistent ones such as rotary tables are not in a state dict).

Layout: <model_dir>/qcache/<component>-<level>/{model.safetensors, cache.json}
A cache is used only if the source files and the library versions still match.
"""
import json
import os
import shutil
import time

import protocol

FORMAT = 1
BUFFER_PREFIX = "__buffer__."
MIN_FREE_GB = 5.0  # leave the disk some room


def enabled():
    return os.environ.get("VK_QUANT_CACHE", "1") != "0"


def _versions():
    import importlib.metadata as md
    return {p: md.version(p) for p in ("torch", "optimum-quanto", "transformers", "diffusers")}


def _source_signature(folder, comp):
    """Size and mtime of the component's weight files (a re-import changes them)."""
    d = os.path.join(folder, comp) if comp else folder
    sig = []
    if os.path.isfile(d):
        paths = [d]
    else:
        paths = sorted(os.path.join(d, f) for f in os.listdir(d)
                       if f.endswith((".safetensors", ".bin", ".gguf", ".json")) and not f.startswith("._"))
    for p in paths:
        st = os.stat(p)
        sig.append([os.path.basename(p), st.st_size, int(st.st_mtime)])
    return sig


def cache_dir(model_dir, comp, level):
    return os.path.join(model_dir, "qcache", "%s-%s" % (comp or "denoiser", level))


def _key(folder, comp, level, dtype):
    key = {"format": FORMAT, "component": comp, "level": level, "dtype": str(dtype),
           "source": _source_signature(folder, comp), "versions": _versions()}
    if comp and _kept_in_fp32(folder, comp):
        key["kept_fp32"] = "q8"  # caches made before left them 16 bit and are made again once
    return key


def _kept_in_fp32(folder, comp):
    """The layers a transformers class keeps in float32 (T5's wo), [] when none or not a transformers class."""
    try:
        with open(os.path.join(folder, "model_index.json")) as f:
            lib, name = json.load(f)[comp]
    except (OSError, ValueError, KeyError, TypeError):
        return []
    if lib != "transformers":
        return []
    import transformers
    return list(getattr(getattr(transformers, name, None), "_keep_in_fp32_modules", None) or [])


def quantize_kept_fp32(model, dtype):
    """The layers the model keeps in float32 in 8 bit: transformers' quanto quantizer leaves them out, so 1.0B of
    T5-XXL's 4.76B parameters (its wo layers) stayed 16 bit, its "4 bit" took 5.2 GB next to the denoiser against 3.1
    planned (FLUX.1 Fill on the Mac mini, MEASUREMENTS 7bf). In 4 bit one test prompt's embedding went off (cosine
    0.91 against 0.97); float32 only guards against float16 overflow, so only when the text encoder computes in
    bfloat16."""
    import torch
    from optimum.quanto import QModuleMixin, freeze, qint8, quantize
    kept = set(getattr(model, "_keep_in_fp32_modules", None) or [])
    if not kept or dtype != torch.bfloat16:
        return model
    names = [name for name, module in model.named_modules() if name.rpartition(".")[2] in kept
             and isinstance(module, torch.nn.Linear) and not isinstance(module, QModuleMixin)]
    if names:
        quantize(model, weights=qint8, include=names)
        freeze(model)
    return model


def load(model_dir, folder, comp, level, dtype, make_empty):
    """Returns the cached model or None. make_empty() builds the model on the meta device."""
    if not enabled():
        return None
    d = cache_dir(model_dir, comp, level)
    try:
        with open(os.path.join(d, "cache.json")) as f:
            info = json.load(f)
    except (OSError, ValueError):
        return None
    if info.get("key") != _key(folder, comp, level, dtype):
        protocol.log("[diffusers] quantized cache of %s is outdated, rebuilding" % comp)
        shutil.rmtree(d, ignore_errors=True)
        return None
    try:
        return _restore(d, info, dtype, make_empty)
    except Exception as e:  # a broken cache must never block generation
        if _stopped(e):
            raise
        protocol.log("[diffusers] quantized cache of %s unusable (%s), rebuilding" % (comp, e))
        shutil.rmtree(d, ignore_errors=True)
        return None


def _stopped(e):
    """A Stop raised into the loading thread (protocol.interruptible, engine.StopRequested): the cache is fine and
    stays; it went on as "unusable, rebuilding" and was deleted before."""
    return type(e).__name__ == "StopRequested"


def _restore(d, info, dtype, make_empty):
    import torch
    from optimum.quanto import requantize
    from safetensors.torch import load_file

    import quanto_mps
    quanto_mps.patch()  # unpacking must not need quanto's compiled kernels
    sd = load_file(os.path.join(d, "model.safetensors"))
    buffers = {k[len(BUFFER_PREFIX):]: sd.pop(k) for k in list(sd) if k.startswith(BUFFER_PREFIX)}
    for alias, src in info["aliases"].items():
        sd[alias] = sd[src]
    model = make_empty().to(dtype)
    requantize(model, sd, info["qmap"], device=torch.device("cpu"))

    # tensors that are not quantized keep the dtype they were saved with (some stay float32)
    for name, t in list(model.named_parameters()) + list(model.named_buffers()):
        src = sd.get(name, buffers.get(name))
        if src is not None and src.dtype != t.dtype:
            _set_tensor(model, name, src, isinstance(t, torch.nn.Parameter))
    for name, t in buffers.items():
        _set_tensor(model, name, t, False)
    if hasattr(model, "tie_weights"):
        model.tie_weights()
    left = [n for n, t in list(model.named_parameters()) + list(model.named_buffers()) if t.device.type == "meta"]
    if left:
        raise ValueError("not restored: %s" % ", ".join(left[:3]))
    return model.eval()


def _set_tensor(model, name, value, is_param):
    import torch
    mod_name, _, attr = name.rpartition(".")
    mod = model.get_submodule(mod_name) if mod_name else model
    if is_param:
        setattr(mod, attr, torch.nn.Parameter(value, requires_grad=False))
    else:
        mod._buffers[attr] = value


def save(model_dir, folder, comp, level, dtype, model):
    """Stores a freshly quantized component; failures only cost the next start time."""
    if not enabled():
        return
    d = cache_dir(model_dir, comp, level)
    try:
        need_gb = sum(t.numel() * t.element_size() for t in model.state_dict().values()) / 1024 ** 3
        free_gb = shutil.disk_usage(model_dir).free / 1024 ** 3
        if free_gb - need_gb < MIN_FREE_GB:
            protocol.log("[diffusers] not caching quantized %s: only %.0f GB free" % (comp, free_gb))
            return
        _write(d, folder, comp, level, dtype, model)
    except Exception as e:
        shutil.rmtree(d, ignore_errors=True)  # written half: gone (also when stopped)
        if _stopped(e):
            raise
        protocol.log("[diffusers] could not cache quantized %s: %s" % (comp, e))


def _write(d, folder, comp, level, dtype, model):
    from optimum.quanto import quantization_map
    from safetensors.torch import save_file

    t0 = time.time()
    tmp = d + ".tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    tensors, aliases, seen = {}, {}, {}
    for k, v in model.state_dict().items():
        key = (v.data_ptr(), v.dtype, tuple(v.shape), tuple(v.stride()))
        if key in seen:
            aliases[k] = seen[key]  # tied weights (e.g. T5 shared / embed_tokens) are stored once
        else:
            seen[key] = k
            tensors[k] = v.contiguous()
    persistent = set(model.state_dict())
    for k, v in model.named_buffers():
        if k not in persistent:
            tensors[BUFFER_PREFIX + k] = v.contiguous()
    save_file(tensors, os.path.join(tmp, "model.safetensors"))
    with open(os.path.join(tmp, "cache.json"), "w") as f:
        json.dump({"key": _key(folder, comp, level, dtype), "qmap": quantization_map(model), "aliases": aliases}, f)
    shutil.rmtree(d, ignore_errors=True)
    os.replace(tmp, d)
    protocol.log("[diffusers] cached quantized %s in %.1fs" % (comp, time.time() - t0))
