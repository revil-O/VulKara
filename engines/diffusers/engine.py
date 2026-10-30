# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Runs imported diffusers models (SDXL, SD 3.5, FLUX.1, Chroma, FLUX.2, Qwen-Image, Z-Image) on MPS."""
import gc
import inspect
import json
import os
import random
import time
import types
import uuid
from pathlib import Path

import colour
import controlnet
import lora_convert
import memory
import paths
import prompt_cache
import protocol
import quant_cache
import registry
import samplers
import step_cache
import streaming
from importer import MANIFEST

def stream_mode():
    """SSD streaming of the denoiser (Settings → Engine and memory, env VK_SSD_STREAMING):
    auto = only when the model does not fit into memory otherwise, always = also when it fits
    (keeps memory free, slow), off = never (too large models are refused)."""
    v = os.environ.get("VK_SSD_STREAMING", "auto").strip().lower()
    return {"0": "off", "1": "always"}.get(v, v if v in ("auto", "always", "off") else "auto")


# what the memory plan leaves free beyond that may keep blocks of a streamed model on the GPU, less this margin
STREAM_KEEP_MARGIN = 0.05
SLICE_ABOVE_PIXELS = 1536 * 1536
IMAGES_DIR = paths.images_dir()


# Restore's previews (a part of the photo, restored quickly) are kept apart from the results, not in the history
PREVIEWS = ".previews"


def _face_points(given, box, scale):
    """The faces the user placed (landmarks in the photo's pixels) for the picture being restored: moved into the
    preview's part and scaled to the result's size; those outside the part are left out. None: find them."""
    if given is None:
        return None
    ox, oy = (box[0], box[1]) if box else (0, 0)
    out = []
    for face in given:
        pts = [[(float(x) - ox) * scale, (float(y) - oy) * scale] for x, y in face][:5]
        if len(pts) != 5:
            continue
        if box:
            cx, cy = sum(p[0] for p in pts) / 5 / scale, sum(p[1] for p in pts) / 5 / scale
            if not (0 <= cx < box[2] - box[0] and 0 <= cy < box[3] - box[1]):
                continue
        out.append(pts)
    return out


def _preview_box(box, size, photo=None):
    """The preview's part of the photo as (left, top, right, bottom), clamped into it; None for the whole photo.
    box "auto" (w, h only): around the largest face when the face model is there, else the middle of the photo."""
    if not box:
        return None
    w, h = size
    if box.get("auto"):
        bw, bh = min(w, int(box.get("w", 768))), min(h, int(box.get("h", 768)))
        cx, cy = w / 2, h / 2
        if photo is not None:
            try:
                import restore as rs
                detector = os.path.join(rs.helper_folder(rs.FACE_HELPER), rs.FACE_DETECTOR)
                found = rs.find_faces(rs.to_array(photo), detector) if os.path.isfile(detector) else []
                if found:
                    cx, cy = float(found[0][:, 0].mean()), float(found[0][:, 1].mean())
            except Exception:
                pass
        box = {"x": cx - bw / 2, "y": cy - bh / 2, "w": bw, "h": bh}
    x, y, bw, bh = (int(round(float(v))) for v in (box.get("x", 0), box.get("y", 0), box.get("w", 0), box.get("h", 0)))
    bw, bh = max(64, min(w, bw)), max(64, min(h, bh))
    x, y = max(0, min(w - bw, x)), max(0, min(h - bh, y))
    return (x, y, x + bw, y + bh)


class StopRequested(Exception):
    pass


def _meta_weights():
    """A model built inside this has its weights on the meta device, to be filled from a cache. Only the weights: tensors
    a module computes itself in __init__ stay real, as nothing fills them later (Qwen-Image 2.1 keeps its rotary
    frequencies in a plain list; on the meta device they failed with "Cannot copy out of meta tensor")."""
    from accelerate import init_empty_weights
    return init_empty_weights(include_buffers=False)


def _device():
    import torch
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _torch_dtype(name, device):
    import torch
    if device == "cpu":
        return torch.float32
    return {"float16": torch.float16, "bfloat16": torch.bfloat16}[name]


_BF16_SLOW = None


def bf16_is_slow(device):
    """True on GPUs without bfloat16 hardware (M1/M2): there float16 matmuls run twice as fast."""
    global _BF16_SLOW
    if device != "mps":
        return False
    if _BF16_SLOW is None:
        import torch
        timings = {}
        for dt in (torch.bfloat16, torch.float16):
            a = torch.randn(1024, 2048, device=device, dtype=dt)
            b = torch.randn(2048, 2048, device=device, dtype=dt)
            a @ b
            torch.mps.synchronize()
            t0 = time.time()
            for _ in range(10):
                a @ b
            torch.mps.synchronize()
            timings[dt] = time.time() - t0
        _BF16_SLOW = timings[torch.bfloat16] > 1.3 * timings[torch.float16]
        protocol.log("[diffusers] bfloat16 %s on this GPU" % ("slow, computing in float16 where safe" if _BF16_SLOW else "fast"))
    return _BF16_SLOW


def load_manifest(model_dir):
    with open(os.path.join(model_dir, MANIFEST)) as f:
        return json.load(f)


def _snap(v, multiple):
    return max(multiple, int(round(v / multiple)) * multiple)


def _quanto_configs(quant_map, denoiser):
    """quant_map {component: none|q8|q4|gguf} -> PipelineQuantizationConfig mapping."""
    import diffusers
    import transformers
    import quanto_mps
    levels = {"q8": "int8", "q4": "int4"}
    mapping = {}
    if any(q in levels for q in quant_map.values()):
        quanto_mps.patch()
    for comp, q in quant_map.items():
        if q not in levels:
            continue
        if comp == denoiser:
            mapping[comp] = diffusers.QuantoConfig(weights_dtype=levels[q])
        else:
            mapping[comp] = transformers.QuantoConfig(weights=levels[q])
    return mapping


def applied_layers(module, adapter):
    """How many layers of a module carry the peft adapter of that name (lora_A holds one entry per adapter)."""
    n = 0
    for sub in module.modules():
        a = getattr(sub, "lora_A", None)
        if a is not None and hasattr(a, "keys") and adapter in a.keys():
            n += 1
    return n


def place_adapters(module, device):
    """Brings every weight of a module that is not on the device there (a LoRA weight peft left on the CPU), and
    returns the names it found. A quantized model already on the device is not touched by the move."""
    strays = [n for n, p in list(module.named_parameters()) + list(module.named_buffers())
              if p.device.type not in (str(device).split(":")[0], "meta")]
    if strays:
        module.to(device)
    return strays


class LoadedModel:
    """One imported model with the pipelines needed for the current RAM plan."""
    stop = None  # whether the job was stopped (the engine's reader), for long one-time preparations


    def __init__(self, model_dir, device, ram_gb=None):
        self.model_dir = model_dir
        self.m = load_manifest(model_dir)
        self.spec = registry.ARCHS[self.m["arch"]]
        if self.spec.get("runtime") == "mlx":
            raise ValueError("%s runs with the MLX runtime only: install it in Settings → Runtimes → MLX"
                             % self.spec["label"])
        too_old = registry.runtime_too_old(self.m["arch"])
        if too_old:
            raise ValueError(too_old)
        self.device = device
        self.dtype = _torch_dtype(self.spec["torch_dtype"], device)
        self.text_dtype = self.dtype
        # denoiser + VAE in float16 where the model tolerates it and bfloat16 is emulated; the text
        # encoders keep bfloat16 (T5 overflows in float16), their embeddings are cast
        if self.spec.get("fp16_compute") and self.dtype != _torch_dtype("float16", device) and bf16_is_slow(device):
            self.dtype = _torch_dtype("float16", device)
        fixed_gb = None
        if self.m.get("file_format") == "gguf":
            fixed_gb = os.path.getsize(self._path(self.m["file"])) / 1024 ** 3
        ram = ram_gb if ram_gb is not None else memory.total_ram_gb()
        # a whole checkpoint file loads in one piece: no 4 bit text encoder, no stages (memory.plan alone)
        planner = memory.plan if self.m["layout"] == "single_full" else memory.fitting_plan
        self.plan = planner(self.m["components"], self.m["denoiser"], self.spec["family"], ram,
                            quant=self.m.get("quant_request", "auto"), denoiser_fixed_gb=fixed_gb)
        self.stream = False
        self.stream_keep = 0.0  # share of a streamed denoiser kept on the GPU
        self.stream_release = False  # the kept blocks make room while a new prompt is encoded
        self.stream_model = None
        mode = stream_mode()
        if self._can_stream() and (mode == "always" or (mode == "auto" and not self.plan["fits"])):
            # the denoiser's blocks come from the SSD one at a time (streaming.py); "auto" only as an
            # emergency mode for models that do not fit otherwise
            comps = dict(self.m["components"])
            comps[self.m["denoiser"]] = comps[self.m["denoiser"]] * memory.stream_resident_share(self.spec["family"])
            plan = memory.plan(comps, self.m["denoiser"], self.spec["family"], ram, quant="auto")
            te_opts = None
            if not plan["fits"]:
                # last resort: a big text encoder (Qwen-Image 2.1: 8.8B) in 4 bit, quantized once and cached
                te_opts = memory.QUANT_ORDER
                plan = memory.plan(comps, self.m["denoiser"], self.spec["family"], ram, quant="auto",
                                   text_quant_opts=te_opts)
            if plan["fits"]:
                self.stream_keep, plan, self.stream_release = keep_plan(
                    self.m["components"], self.m["denoiser"], self.spec["family"], ram, plan, te_opts)
                plan["quant"][self.m["denoiser"]] = "none"
                plan["streamed"] = True
                self.plan, self.stream = plan, True
                self._check_stream_disk()
        if not self.plan["fits"]:
            hint = ""
            if self.m["arch"] in ("flux1_schnell", "flux1_dev", "flux2_klein", "z_image") and self.m["layout"] == "repo":
                hint = " It fits with the MLX runtime (4 bit): Settings → Runtimes → MLX."
            raise MemoryError("%s needs about %d GB RAM with the Diffusers runtime, this Mac has %d GB.%s"
                              % (self.spec["label"], self.plan["min_ram_gb"], round(self.plan["ram_gb"]), hint))
        self.staged = self.plan["staged_text_encoder"] and self.m["layout"] != "single_full"
        # stages: the denoiser makes room while a new prompt is encoded (memory.fitting_plan, MEASUREMENTS 7z)
        self.release_denoiser = self.staged and bool(self.plan.get("releases_denoiser")) and not self.stream
        # text encoders in their own pipeline: loaded per new prompt (staged) or kept (mixed dtypes)
        self.separate_text = self.staged or (self.text_dtype != self.dtype and self.m["layout"] != "single_full")
        self.text_pipe = None     # resident text encoder pipeline (separate_text without staging)
        self.pipe = None          # denoiser pipeline (holds everything when not separate_text)
        self.embed_cache = None   # (key, kwargs)
        self.lora_key = ()        # LoRAs currently loaded into the pipeline
        self.controlnet = None    # (id, model) of the loaded ControlNet

    def precision(self):
        """The bit size of each part as the plan loads it (benchmarks): a GGUF denoiser keeps its type, a streamed
        one is unpacked to 16 bit on the SSD."""
        names = {"none": "16 bit", "q8": "8 bit", "q4": "4 bit"}
        parts = []
        for c, q in self.plan["quant"].items():
            label = names.get(q, q)
            if c == self.m["denoiser"] and self.stream:
                label = "16 bit, streamed from the SSD"
            elif c == self.m["denoiser"] and self.m.get("file_format") == "gguf":
                label = registry.file_precision(self._path(self.m["file"]))
            parts.append((c, label))
        return parts

    def _path(self, p):
        return p if os.path.isabs(p) else os.path.join(self.model_dir, p)

    def _can_stream(self):
        """Denoisers in the diffusers layout or as one file (a GGUF file is unpacked into the stream cache once);
        VK_SSD_STREAMING=off turns streaming off (stream_mode)."""
        if stream_mode() == "off":
            return False
        return self.m["layout"] in ("repo", "single_denoiser")

    @property
    def stream_dir(self):
        # Settings → Folders → SSD streaming cache: one folder per model there, else next to the model
        shared = os.environ.get("VK_STREAM_CACHE_DIR")
        if shared:
            return os.path.join(shared, os.path.basename(os.path.normpath(self.model_dir)))
        return os.path.join(self.model_dir, "stream_cache")

    def _check_stream_disk(self):
        import shutil
        need_gb = self.m["components"][self.m["denoiser"]] * 2 - streaming.cache_gb(self.stream_dir)
        # the disk the blocks go to: the streaming cache folder's, else the model's
        where = os.environ.get("VK_STREAM_CACHE_DIR") or self.model_dir
        while not os.path.exists(where) and os.path.dirname(where) != where:  # a cache folder not made yet
            where = os.path.dirname(where)
        free_gb = shutil.disk_usage(where).free / 1024 ** 3
        if need_gb > 0 and free_gb < need_gb + 5:
            raise MemoryError("%s does not fit into this Mac's memory; streaming it from the SSD needs %d GB free "
                              "disk space (%d GB free)" % (self.spec["label"], need_gb + 5, free_gb))

    def _stoppable(self, status):
        """A report for a long one-time preparation (status with the percent): a stop ends it at the next block, the
        blocks written so far are written again next time."""
        def report(i, total):
            protocol.status(status % (100 * i // total))
            if self.stop is not None and self.stop():
                raise StopRequested()
        return report

    def _load_streamed_denoiser(self):
        """The denoiser memory-mapped on the CPU, its blocks moved to the SSD cache."""
        import diffusers
        m = self.m
        protocol.status("Streaming the model from the SSD (slow)" if stream_mode() == "always"
                      else "Model larger than memory: streaming it from the SSD (slow)")
        if m["layout"] == "repo":
            folder = self._path(m["weights_dir"])
            cls = self._component_class(folder, m["denoiser"])
            extra = {"variant": registry.file_variant(m)} if registry.file_variant(m) else {}
            model = cls.from_pretrained(folder, subfolder=m["denoiser"], dtype=self.dtype, **extra)
        elif m.get("file_format") == "gguf":
            model = self._unpacked_gguf_denoiser()
        else:
            cls = getattr(diffusers, self.spec["denoiser_class"])
            model = cls.from_single_file(self._path(m["file"]), config=self._path(m["base_dir"]),
                                         subfolder=m["denoiser"], dtype=self.dtype)
        n, kept = streaming.enable(model, self.device, self.dtype, self.stream_dir, resident_share=self.stream_keep,
                                   report=self._stoppable("Preparing SSD streaming (one-time) %d%%"))
        protocol.log("[diffusers] streaming %d blocks of %s from %s, %d blocks (%.1f GB) kept in memory%s"
                     % (n, m["denoiser"], self.stream_dir, kept, streaming.kept_gb(model),
                        ", making room for each new prompt" if self.stream_release else ""))
        self.stream_model = model
        return model

    def _unpacked_gguf_denoiser(self):
        """A GGUF denoiser for streaming: unpacked into the stream cache on its first use (it is read into RAM once
        for that), later only the small rest of it is read from there."""
        import diffusers
        m = self.m
        cls = getattr(diffusers, self.spec["denoiser_class"])

        def load():
            protocol.status("Unpacking the GGUF file for SSD streaming (one-time)")
            return cls.from_single_file(self._path(m["file"]), config=self._path(m["base_dir"]), subfolder=m["denoiser"],
                                        dtype=self.dtype,
                                        quantization_config=diffusers.GGUFQuantizationConfig(compute_dtype=self.dtype))

        def empty():
            with _meta_weights():
                return cls.from_config(cls.load_config(self._path(m["base_dir"]), subfolder=m["denoiser"]))

        return streaming.unpack_gguf(load, empty, self.stream_dir, self.dtype, m.get("sha256") or m["file"],
                                     report=self._stoppable("Unpacking the GGUF file for SSD streaming (one-time) %d%%"))

    @property
    def text_components(self):
        return [c for c in self.m["components"] if c.startswith("text_encoder")]

    def _pipeline_class(self, img2img=False):
        import diffusers
        name = self.spec["img2img_pipeline"] if img2img else self.spec["pipeline"]
        return getattr(diffusers, name)

    def _from_pretrained(self, skip=(), with_denoiser=None, dtype=None):
        """Loads the pipeline, leaving the components in `skip` out.

        Quantized components are loaded one by one, so the UI can show which one is being prepared."""
        m = self.m
        dtype = dtype or self.dtype
        folder = self._path(m["weights_dir"] if m["layout"] == "repo" else m["base_dir"])
        kwargs = {c: None for c in skip}
        kwargs.update(self.spec.get("pipeline_kwargs", {}))  # e.g. SD 1.x without its safety checker
        if with_denoiser is not None:
            kwargs[m["denoiser"]] = with_denoiser
        quant = {c: q for c, q in self.plan["quant"].items() if c not in skip and c not in kwargs}
        variant = registry.file_variant(m)
        for comp, cfg in _quanto_configs(quant, m["denoiser"]).items():
            kwargs[comp] = self._load_component(folder, comp, cfg, quant[comp], variant, dtype)
        if variant:
            kwargs["variant"] = variant
        pipe = self._pipeline_class().from_pretrained(folder, dtype=dtype, **kwargs)
        pipe.set_progress_bar_config(disable=True)
        if self.stream:
            # the streamed denoiser places its own weights (its blocks are "meta" between uses)
            import torch
            for name, comp in pipe.components.items():
                if isinstance(comp, torch.nn.Module) and name != m["denoiser"]:
                    comp.to(self.device)
            return pipe
        return pipe.to(self.device)

    def _component_class(self, folder, comp):
        import diffusers
        import transformers
        with open(os.path.join(folder, "model_index.json")) as f:
            lib, cls = json.load(f)[comp]
        return getattr(diffusers if lib == "diffusers" else transformers, cls)

    def _load_component(self, folder, comp, quant_config, level, variant=None, dtype=None):
        cls = self._component_class(folder, comp)
        dtype = dtype or self.dtype

        def make_empty():
            with _meta_weights():
                if hasattr(cls, "config_class") and hasattr(cls, "_from_config"):  # transformers
                    return cls._from_config(cls.config_class.from_pretrained(folder, subfolder=comp), dtype=dtype)
                return cls.from_config(cls.load_config(folder, subfolder=comp))

        protocol.status("Loading %s" % comp)
        model = quant_cache.load(self.model_dir, folder, comp, level, dtype, make_empty)
        if model is not None:
            return model
        # quantizing layer by layer on the CPU keeps the peak low (loading onto the GPU first
        # materializes the full 16 bit weights there)
        protocol.status("Quantizing %s (one-time)" % comp)
        extra = {"variant": variant} if variant else {}
        model = cls.from_pretrained(folder, subfolder=comp, dtype=dtype, quantization_config=quant_config, **extra)
        quant_cache.save(self.model_dir, folder, comp, level, dtype, model)
        return model

    def _load_denoiser_single_file(self):
        import diffusers
        m = self.m
        cls = getattr(diffusers, self.spec["denoiser_class"])
        kwargs = {}
        q = self.plan["quant"].get(m["denoiser"])
        cached = q in ("q8", "q4") and m["file_format"] != "gguf"
        if m["file_format"] == "gguf":
            kwargs["quantization_config"] = diffusers.GGUFQuantizationConfig(compute_dtype=self.dtype)
        elif cached:
            kwargs["quantization_config"] = _quanto_configs({m["denoiser"]: q}, m["denoiser"])[m["denoiser"]]

            def make_empty():
                with _meta_weights():
                    return cls.from_config(cls.load_config(self._path(m["base_dir"]), subfolder=m["denoiser"]))

            model = quant_cache.load(self.model_dir, self._path(m["file"]), None, q, self.dtype, make_empty)
            if model is not None:
                return model
            protocol.status("Quantizing %s (one-time)" % m["denoiser"])
        model = cls.from_single_file(self._path(m["file"]), config=self._path(m["base_dir"]),
                                     subfolder=m["denoiser"], dtype=self.dtype, **kwargs)
        if m["file_format"] == "gguf":
            _dequantize_gguf_outside_linear(model, self.dtype)
        if cached:
            quant_cache.save(self.model_dir, self._path(m["file"]), None, q, self.dtype, model)
        return model

    def load(self):
        m = self.m
        skip = self.text_components if self.separate_text else []
        if self.release_denoiser:
            # loaded once the prompt is encoded (ensure_denoiser)
            self.pipe = self._from_pretrained(skip=skip + [m["denoiser"]])
            self.default_scheduler = samplers.own_default(self.pipe.scheduler, self.spec["family"])
            self.pipe.scheduler = self.default_scheduler
            self._setup_vae()
            return
        if m["layout"] == "single_full":
            pipe = self._pipeline_class().from_single_file(self._path(m["file"]), config=self._path(m["base_dir"]),
                                                           dtype=self.dtype, **self.spec.get("pipeline_kwargs", {}))
            pipe.set_progress_bar_config(disable=True)
            self.pipe = pipe.to(self.device)
        elif self.stream:
            self.pipe = self._from_pretrained(skip=skip, with_denoiser=self._load_streamed_denoiser())
        elif m["layout"] == "single_denoiser":
            self.pipe = self._from_pretrained(skip=skip, with_denoiser=self._load_denoiser_single_file())
        else:
            self.pipe = self._from_pretrained(skip=skip)
        self.default_scheduler = samplers.own_default(self.pipe.scheduler, self.spec["family"])
        self.pipe.scheduler = self.default_scheduler
        self._setup_vae()
        denoiser = getattr(self.pipe, self.m["denoiser"], None)
        level = step_cache.threshold()
        if denoiser is not None and level is not None:
            if step_cache.attach(denoiser, level):
                protocol.log("[diffusers] step caching on (threshold %.2f)" % level)
            else:
                protocol.log("[diffusers] step caching: not available for %s" % type(denoiser).__name__)

    def ensure_denoiser(self):
        """A plan in stages: the denoiser back in the pipeline after a new prompt was encoded without it."""
        m = self.m
        if not self.release_denoiser or getattr(self.pipe, m["denoiser"], None) is not None:
            return
        if m["layout"] == "single_denoiser":
            model = self._load_denoiser_single_file()
        else:
            folder = self._path(m["weights_dir"])
            q = self.plan["quant"].get(m["denoiser"], "none")
            cfg = _quanto_configs({m["denoiser"]: q}, m["denoiser"]).get(m["denoiser"])
            if cfg is not None:
                model = self._load_component(folder, m["denoiser"], cfg, q, registry.file_variant(m))
            else:
                protocol.status("Loading %s" % m["denoiser"])
                model = self._component_class(folder, m["denoiser"]).from_pretrained(
                    folder, subfolder=m["denoiser"], dtype=self.dtype, variant=registry.file_variant(m))
        self.pipe.register_modules(**{m["denoiser"]: model.to(self.device)})
        self.lora_key = ()  # the LoRAs go onto the new denoiser
        level = step_cache.threshold()
        if level is not None:
            step_cache.attach(model, level)

    def set_sampler(self, sampler, sigmas):
        """Scheduler for the next job (the model's own for "default")."""
        s = samplers.make(sampler, sigmas, dict(self.default_scheduler.config), self.spec["family"])
        self.pipe.scheduler = s or self.default_scheduler

    def _setup_vae(self):
        """Decode large images tile by tile, so the VAE does not need GBs of extra memory."""
        vae = getattr(self.pipe, "vae", None)
        if vae is None or not hasattr(vae, "enable_tiling"):
            return
        if self.decode_self:
            _bf16_vae(vae)
        try:
            if type(vae).__name__.startswith("AutoencoderKLQwenImage"):
                # Qwen-Image's VAEs tile at 256 px blended over 64 px: the seams show as streaks in plain
                # areas. Blended over 128 px they are half as strong; 512 px tiles (2 GB more) a quarter, where the
                # plan leaves the room (not when streaming, which fills the memory with kept blocks), MEASUREMENTS 7v
                size = 512 if not self.stream and self.plan["budget_gb"] - self.plan["denoise_peak_gb"] >= 2.5 else 256
                vae.enable_tiling(tile_sample_min_height=size, tile_sample_min_width=size,
                                  tile_sample_stride_height=size - 128, tile_sample_stride_width=size - 128)
                vae.blend_v = types.MethodType(_blend_v, vae)
                vae.blend_h = types.MethodType(_blend_h, vae)
            else:
                vae.enable_tiling()
            if getattr(vae, "tile_sample_min_size", 0) > 512:
                vae.tile_sample_min_size = 512
                vae.tile_latent_min_size = 512 // (2 ** (len(vae.config.block_out_channels) - 1))
        except Exception as e:  # some VAEs have no tiling
            protocol.log("[diffusers] no VAE tiling: %s" % e)

    @property
    def decode_self(self):
        # the SDXL pipeline decodes in float32 on MPS (+10 GB at 1024 px); bfloat16 has the same
        # range without the memory cost, but the pipeline would cast it back to float16
        return self.spec["family"] == "sdxl" and self.device == "mps"

    def decode_sdxl_latents(self, latents):
        import torch
        vae = self.pipe.vae
        if vae.dtype != torch.bfloat16:
            vae.to(torch.bfloat16)
        cfg = vae.config
        latents = latents.to(torch.bfloat16)
        if getattr(cfg, "latents_mean", None) is not None and getattr(cfg, "latents_std", None) is not None:
            mean = torch.tensor(cfg.latents_mean).view(1, -1, 1, 1).to(latents.device, latents.dtype)
            std = torch.tensor(cfg.latents_std).view(1, -1, 1, 1).to(latents.device, latents.dtype)
            latents = latents * std / cfg.scaling_factor + mean
        else:
            latents = latents / cfg.scaling_factor
        with torch.no_grad():
            image = vae.decode(latents, return_dict=False)[0]
        return self.pipe.image_processor.postprocess(image.float(), output_type="pil")[0]

    def apply_loras(self, loras):
        """loras: [{"file", "scale", "name"}]; reloads adapters only when the selection changes."""
        key = tuple((l["file"], float(l["scale"])) for l in loras)
        if key == self.lora_key:
            return
        if self.stream:
            # the blocks are dropped after each use: the LoRA is merged into them as they load
            self._stream_loras(loras)
            self.lora_key = key
            return
        pipe = self.pipe
        if self.lora_key:
            pipe.unload_lora_weights()
            self.lora_key = ()
        if loras:
            names = []
            try:
                for i, l in enumerate(loras):
                    name = "lora%d" % i
                    _check_lora_format(l)  # LoKr / LoHa: refused with what it is, not a loader error
                    try:
                        self._load_lora(pipe, l["file"], name, drop_text_encoder=self.separate_text)
                    except Exception as first_error:
                        # some LoRAs carry text encoder parts diffusers can not map: use the rest
                        try:
                            try:
                                pipe.delete_adapters([name])
                            except Exception:
                                pass
                            self._load_lora(pipe, l["file"], name, drop_text_encoder=True)
                            protocol.log("[diffusers] LoRA %s: loaded without its text encoder part, which did "
                                         "not load (%s)" % (l["name"], str(first_error)[:300]))
                        except Exception as e:
                            raise ValueError("The LoRA %s does not fit this %s model: %s"
                                             % (l["name"], self.spec["label"], str(e)[:200]))
                    self._check_applied(pipe, l, name)
                    names.append(name)
                try:
                    pipe.set_adapters(names, adapter_weights=[float(l["scale"]) for l in loras])
                except Exception as e:
                    # "Adapter name(s) … not in the list of present adapters" and the like
                    raise ValueError("The LoRAs could not be switched on for this %s model: %s"
                                     % (self.spec["label"], str(e)[:200]))
                # a LoRA weight peft left on the CPU would stop the first step ("tensors on two devices", seen once
                # with two LoRAs on a FLUX model): every weight onto the device before anything runs
                import torch
                for comp_name, comp in pipe.components.items():
                    if isinstance(comp, torch.nn.Module):
                        strays = place_adapters(comp, self.device)
                        if strays:
                            protocol.log("[diffusers] %d LoRA weights of %s were not on the GPU, moved there (%s)"
                                         % (len(strays), comp_name, ", ".join(strays[:3])))
            except Exception as e:
                pipe.unload_lora_weights()
                if isinstance(e, ValueError):
                    raise
                raise ValueError("The LoRA could not be loaded into this %s model: %s" % (self.spec["label"], str(e)[:200]))
        self.lora_key = key

    MIN_APPLIED = 0.9  # a LoRA of which fewer of its layers find their place does not fit the model

    @staticmethod
    def _lora_state_dict(pipe, file):
        """diffusers' reading of a LoRA file (kohya / peft / older diffusers names in one naming), as
        (state dict, alphas). SD / SDXL: with the UNet's config, which maps kohya's SDXL block names
        (input_blocks_4_1 …) to the UNet's; without it no UNet layer of such a file is found."""
        unet = getattr(pipe, "unet", None)
        file = _lora_source(pipe, file)
        res = pipe.lora_state_dict(file, unet_config=unet.config) if unet is not None else pipe.lora_state_dict(file)
        sd, alphas = (res[0], res[1] if len(res) > 1 else None) if isinstance(res, tuple) else (res, None)
        return sd, (alphas if isinstance(alphas, dict) else {})

    def _check_applied(self, pipe, lora, name):
        """How many of the LoRA's denoiser layers got the adapter: below MIN_APPLIED it does not fit (peft
        loads what matches and only warns about the rest)."""
        sd, _ = self._lora_state_dict(pipe, lora["file"])
        comp = self.m["denoiser"]
        expected = sum(1 for k in sd if k.startswith(comp + ".") and k.endswith(self.LORA_A))
        applied = applied_layers(getattr(pipe, comp), name)
        if expected == 0:
            # a text encoder LoRA: it has to have arrived there
            encoders = [getattr(pipe, n) for n in ("text_encoder", "text_encoder_2", "text_encoder_3")
                        if getattr(pipe, n, None) is not None]
            if any(applied_layers(e, name) for e in encoders):
                return
            raise ValueError("The LoRA %s does not fit this %s model: none of its layers belongs to it (made for "
                             "another kind of model, or in a format the runtime can not read)"
                             % (lora["name"], self.spec["label"]))
        share = applied / expected
        if share < self.MIN_APPLIED:
            raise ValueError("The LoRA %s does not fit this %s model: only %d%% of its layers (%d of %d) found their "
                             "place" % (lora["name"], self.spec["label"], int(share * 100), applied, expected))
        if applied < expected:
            protocol.log("[diffusers] LoRA %s: %d of %d layers applied" % (lora["name"], applied, expected))

    LORA_A = (".lora_A.weight", ".lora.down.weight", ".lora_down.weight")
    LORA_B = (".lora_B.weight", ".lora.up.weight", ".lora_up.weight")

    def _stream_loras(self, loras):
        """LoRA factors for the streamed denoiser (streaming.set_loras), from diffusers' reader, which
        brings kohya / peft / older diffusers files into one naming; text encoder parts are skipped."""
        denoiser = getattr(self.pipe, self.m["denoiser"])
        prefix = self.m["denoiser"] + "."
        entries = []
        for l in loras:
            _check_lora_format(l)
            sd, alphas = self._lora_state_dict(self.pipe, l["file"])
            mine = []
            for k, a in sd.items():
                suffix = next((x for x in self.LORA_A if k.endswith(x)), None)
                if suffix is None or not k.startswith(prefix):
                    continue
                base = k[:-len(suffix)]
                b = next((sd[base + x] for x in self.LORA_B if base + x in sd), None)
                if b is None:
                    continue
                alpha = sd.get(base + ".alpha", alphas.get(base + ".alpha", alphas.get(base)))
                scale = float(l["scale"]) * (float(alpha) / a.shape[0] if alpha is not None else 1.0)
                mine.append((base[len(prefix):], a, b, scale))
            # checked before anything is generated: each layer by name and size against the streamed blocks
            fit = streaming.fitting(denoiser, mine)
            if not mine or fit < len(mine) * self.MIN_APPLIED:
                raise ValueError("The LoRA %s does not fit this %s model: only %d%% of its layers (%d of %d) found "
                                 "their place" % (l["name"], self.spec["label"], int(100 * fit / max(1, len(mine))),
                                                  fit, len(mine)))
            entries += mine
        matched = streaming.set_loras(denoiser, entries)
        if loras:
            protocol.log("[diffusers] %d LoRA layers merged into the streamed blocks" % matched)

    TEXT_ENCODER_LORA_PREFIXES = ("lora_te", "text_encoder", "te_", "te1", "te2", "lora_te1", "lora_te2")

    @classmethod
    def _load_lora(cls, pipe, file, name, drop_text_encoder=False):
        if not drop_text_encoder:
            if getattr(pipe, "unet", None) is not None and cls._load_unet_lora(pipe, file, name):
                return
            with _plain_weight_names(getattr(pipe, "transformer", None)):
                pipe.load_lora_weights(_lora_source(pipe, file), adapter_name=name)
            return
        from safetensors.torch import load_file
        sd = {k: v for k, v in load_file(file).items() if not k.startswith(cls.TEXT_ENCODER_LORA_PREFIXES)}
        with _plain_weight_names(getattr(pipe, "transformer", None)):
            pipe.load_lora_weights(_lora_source(pipe, sd), adapter_name=name)

    @staticmethod
    def _load_unet_lora(pipe, file, name):
        """SD 1.x / 2.x / SDXL LoRAs with text encoder parts in the old key format, which diffusers
        can not map to transformers 5 layer names: converts them to peft (alpha folded into lora_B)
        and loads them next to the UNet part. Returns False for files without a text encoder part."""
        from diffusers.utils import convert_state_dict_to_peft
        sd, alphas = LoadedModel._lora_state_dict(pipe, file)
        encoders = [n for n in ("text_encoder", "text_encoder_2") if getattr(pipe, n, None) is not None
                    and any(k.startswith(n + ".") for k in sd)]
        if not encoders:
            return False
        unet = {k: v for k, v in sd.items() if k.startswith("unet.")}
        pipe.load_lora_into_unet(unet, network_alphas={k: v for k, v in alphas.items() if k.startswith("unet.")} or None,
                                 unet=pipe.unet, adapter_name=name)
        for enc in encoders:
            module = getattr(pipe, enc)
            part = {k[len(enc) + 1:]: v for k, v in sd.items() if k.startswith(enc + ".")}
            converted = convert_state_dict_to_peft(dict(part))
            renamed = dict(zip(part, converted))  # the conversion keeps the order of the keys
            has_text_model = any(n.startswith("text_model.") for n, _ in module.named_modules())
            out = {}
            for old_key, new_key in renamed.items():
                v = converted[new_key]
                if new_key.endswith("lora_B.weight"):
                    old_down = old_key[:-len("up.weight")] + "down.weight"
                    alpha = alphas.get(enc + "." + old_down + ".alpha")
                    if alpha is not None and old_down in part:
                        v = v * (float(alpha) / part[old_down].shape[0])
                if not has_text_model and new_key.startswith("text_model."):
                    new_key = new_key[len("text_model."):]
                out[enc + "." + new_key] = v
            pipe.load_lora_into_text_encoder(out, network_alphas=None, text_encoder=module, prefix=enc,
                                             adapter_name=name)
        return True

    def controlnet_room(self, width=1024, height=1024):
        """GB left for the ControlNet's weights next to this model at a picture size (activations as memory.peak_at
        counts them); the ControlNet runs a copy of the first blocks at every step: about twice the activations on top."""
        planned, act = memory.activations_at(self.plan, width, height)
        denoise = self.plan["denoise_peak_gb"] - planned + act
        return self.plan["budget_gb"] - denoise - 2 * act

    def ensure_controlnet(self, cn_spec, width=1024, height=1024):
        """Loads the family's ControlNet (downloading it once); in 8 bit if 16 bit does not fit."""
        import diffusers
        if self.controlnet and self.controlnet[0] == cn_spec["id"]:
            return self.controlnet[1]
        self.release_controlnet()
        folder = controlnet.ensure_downloaded(cn_spec, report=lambda stage, pct: (
            protocol.status("%s %d%%" % (stage, pct) if pct >= 0 else stage)))
        free = self.controlnet_room(width, height)
        if cn_spec["params_b"] * memory.BYTES_PER_PARAM["none"] > free and not self.separate_text:
            # make room: text encoders are then only loaded to encode a new prompt
            free += self.drop_text_encoders()
        cls = getattr(diffusers, cn_spec["class"])
        if cn_spec["params_b"] * memory.BYTES_PER_PARAM["none"] <= free:
            protocol.status("Loading ControlNet")
            model = cls.from_pretrained(str(folder), dtype=self.dtype)
        elif cn_spec["params_b"] * memory.BYTES_PER_PARAM["q8"] <= free:
            def make_empty():
                with _meta_weights():
                    return cls.from_config(cls.load_config(str(folder)))

            model = quant_cache.load(str(folder), str(folder), None, "q8", self.dtype, make_empty)
            if model is None:
                protocol.status("Quantizing ControlNet (one-time)")
                model = cls.from_pretrained(str(folder), dtype=self.dtype, quantization_config=_quanto_configs(
                    {"controlnet": "q8"}, "controlnet")["controlnet"])
                quant_cache.save(str(folder), str(folder), None, "q8", self.dtype, model)
        else:
            raise MemoryError("Not enough RAM for the ControlNet (%.1f GB, %.1f GB in 8 bit) next to %s at %d × %d: "
                              "a smaller picture leaves more room." % (cn_spec["size_gb"], cn_spec["size_gb"] / 2,
                                                                      self.spec["label"], width, height))
        model = model.to(self.device)
        self.controlnet = (cn_spec["id"], model)
        return model

    def drop_text_encoders(self):
        """Switches a model with resident text encoders to staged encoding; returns the GB freed."""
        if self.separate_text or self.m["layout"] == "single_full" or not self.text_components:
            return 0.0
        self.pipe.register_modules(**{c: None for c in self.text_components})
        self.staged = self.separate_text = True
        self.embed_cache = None
        _free_memory()
        protocol.log("[diffusers] text encoders unloaded to make room (loaded per new prompt now)")
        return self.plan.get("text_gb", 0.0)

    def release_controlnet(self):
        if self.controlnet:
            self.controlnet = None
            _free_memory()

    def destroy(self):
        self.pipe = None
        self.text_pipe = None
        self.embed_cache = None
        self.controlnet = None
        _free_memory()

    # -------------------------------------------------------- prompt encoding

    def encode(self, prompt, negative, guidance):
        """Encodes with the text encoder pipeline (temporary when staged); returns kwargs for __call__."""
        key = (prompt, negative, guidance > 1)
        if self.embed_cache and self.embed_cache[0] == key:
            return self.embed_cache[1]
        disk_key = self._prompt_key(prompt, negative, guidance) if prompt_cache.limit_gb() > 0 else None
        kwargs = prompt_cache.load(disk_key, self.device)
        if kwargs is not None:
            protocol.log("[diffusers] prompt embeddings from the prompt cache")
            self.embed_cache = (key, kwargs)
            return kwargs
        if getattr(self, "release_denoiser", False) and getattr(self.pipe, self.m["denoiser"], None) is not None:
            # stages: the denoiser makes room for the text encoder and is loaded again after (ensure_denoiser)
            self.pipe.register_modules(**{self.m["denoiser"]: None})
            _free_memory()
        # the kept blocks of a streamed model make room for the text encoder (16 GB Macs), and come back after
        release = getattr(self, "stream_release", False) and getattr(self, "stream_model", None) is not None
        if release:
            streaming.release_kept(self.stream_model)
            _free_memory()
        try:
            text_pipe = self.text_pipe or self._from_pretrained(skip=[self.m["denoiser"], "vae"], dtype=self.text_dtype)
            try:
                kwargs = _encode(text_pipe, self.spec, prompt, negative, guidance, self.device)
            finally:
                if self.staged:
                    del text_pipe
                    _free_memory()
                else:
                    self.text_pipe = text_pipe
        finally:
            if release:
                protocol.status("Loading the kept part of the model")
                streaming.restore_kept(self.stream_model)
        # embeddings in the denoiser's dtype (float16 when the text encoders run in bfloat16); attention
        # masks (Qwen-Image) stay integers, a mask the encoder left out (no padding) stays out; Z-Image's
        # embeddings are a list (one tensor per prompt, as long as its tokens)
        def cast(v):
            if isinstance(v, (list, tuple)):
                return [cast(x) for x in v]
            return v.to(self.dtype) if v.is_floating_point() else v
        kwargs = {k: cast(v) for k, v in kwargs.items() if v is not None}
        prompt_cache.save(disk_key, kwargs)
        self.embed_cache = (key, kwargs)
        return kwargs

    def _prompt_key(self, prompt, negative, guidance):
        """What the embeddings depend on (prompt_cache): LoRAs do not, they leave separate text encoders out."""
        m = self.m
        folder = self._path(m["weights_dir"] if m["layout"] == "repo" else m["base_dir"])
        text = {}
        for c in self.text_components:
            try:
                sig = quant_cache._source_signature(folder, c)
            except OSError:
                sig = None
            text[c] = [sig, self.plan["quant"].get(c, "none")]
        return prompt_cache.key({
            "folder": os.path.abspath(folder), "text": text, "text_dtype": str(self.text_dtype), "dtype": str(self.dtype),
            "family": self.spec["family"], "pipeline": self.spec["pipeline"], "call": self.spec.get("call_kwargs", {}),
            "empty_negative": self.spec.get("empty_negative", ""), "prompt": prompt, "negative": negative,
            "guided": guidance > 1})


# LoRA files in namings diffusers' readers do not take are converted in one place (lora_convert.py)
bfl_lora_to_kohya = lora_convert.bfl_lora_to_kohya


class _plain_weight_names:
    """While a LoRA loads: the transformer's state dict also names quantized weights plainly (`x.weight`).

    quanto keeps them as `x.weight._data` / `x.weight._scale`; the FLUX/Chroma loader looks each layer up as `x.weight`
    to see whether it must widen the LoRA, and fails with a KeyError on a quantized transformer."""

    def __init__(self, transformer):
        self.transformer = transformer

    def __enter__(self):
        t = self.transformer
        if t is None or "state_dict" in vars(t):
            self.transformer = None
            return self
        original = type(t).state_dict

        def state_dict(*args, **kwargs):
            sd = original(t, *args, **kwargs)
            if args or kwargs:
                return sd
            for mod_name, module in t.named_modules():
                w = getattr(module, "weight", None)
                key = mod_name + ".weight"
                if w is not None and key not in sd and key + "._data" in sd:
                    sd[key] = w
            return sd

        t.state_dict = state_dict
        return self

    def __exit__(self, *exc):
        if self.transformer is not None:
            del self.transformer.state_dict
        return False


_lora_source = lora_convert.prepare


def _check_lora_format(lora):
    """A LoRA in a format no reader of this runtime takes (LyCORIS LoKr / LoHa) is refused by name."""
    if str(lora.get("file", "")).lower().endswith(".safetensors") and os.path.isfile(lora["file"]):
        lora_convert.check_format(registry.read_safetensors_header(lora["file"]), "The LoRA %s" % lora.get("name", "?"))


def _dequantize_gguf_outside_linear(model, dtype):
    """GGUF weights stay packed as raw bytes; diffusers unpacks them only inside its linear layers. A layer that reads
    its weight itself (the RMSNorm of Qwen-Image 2.1, whose BF16 weight looks twice as long as bytes) gets it unpacked
    once here, which costs little: these are norms and small embeddings."""
    import torch
    from diffusers.quantizers.gguf.utils import GGUFLinear, dequantize_gguf_tensor
    for module in model.modules():
        if isinstance(module, GGUFLinear):
            continue
        for name, param in list(module.named_parameters(recurse=False)):
            if hasattr(param, "quant_type"):
                setattr(module, name, torch.nn.Parameter(dequantize_gguf_tensor(param).to(dtype), requires_grad=False))


def _encode(pipe, spec, prompt, negative, guidance, device):
    import torch
    family = spec["family"]
    with torch.no_grad():
        if family == "flux1":
            pe, ppe, _ = pipe.encode_prompt(prompt=prompt, prompt_2=prompt, device=device,
                                            max_sequence_length=spec.get("call_kwargs", {}).get("max_sequence_length", 512))
            return {"prompt_embeds": pe, "pooled_prompt_embeds": ppe}
        if family == "chroma":
            # T5 only, with attention masks (Chroma masks the padding); real CFG takes the negative prompt's as well
            pe, _, mask, npe, _, nmask = pipe.encode_prompt(prompt=prompt, negative_prompt=negative or "", device=device,
                                                            do_classifier_free_guidance=guidance > 1,
                                                            max_sequence_length=spec["call_kwargs"]["max_sequence_length"])
            out = {"prompt_embeds": pe, "prompt_attention_mask": mask}
            if guidance > 1:
                out.update(negative_prompt_embeds=npe, negative_prompt_attention_mask=nmask)
            return out
        if family == "sd3":
            pe, npe, ppe, nppe = pipe.encode_prompt(prompt=prompt, prompt_2=prompt, prompt_3=prompt, device=device,
                                                    do_classifier_free_guidance=guidance > 1,
                                                    negative_prompt=negative, negative_prompt_2=negative,
                                                    negative_prompt_3=negative)
            out = {"prompt_embeds": pe, "pooled_prompt_embeds": ppe}
            if guidance > 1:
                out.update(negative_prompt_embeds=npe, negative_pooled_prompt_embeds=nppe)
            return out
        if family == "flux2":
            pe, _ = pipe.encode_prompt(prompt=prompt, device=device)
            out = {"prompt_embeds": pe}
            if spec["pipeline"] == "Flux2KleinPipeline" and guidance > 1:
                npe, _ = pipe.encode_prompt(prompt=negative or "", device=device)
                out["negative_prompt_embeds"] = npe
            return out
        if family == "z_image":
            # Qwen3 hidden states, one tensor per prompt without the padding; guidance only above 1 (guidance_off_at)
            pe, npe = pipe.encode_prompt(prompt=prompt, device=device, do_classifier_free_guidance=guidance > 1,
                                         negative_prompt=negative or "")
            out = {"prompt_embeds": pe}
            if guidance > 1:
                out["negative_prompt_embeds"] = npe
            return out
        if family in ("qwen_image", "qwen_image21"):
            # Qwen-Image 2.1 returns a third value (where condition images sit), unused without an image
            pe, mask = pipe.encode_prompt(prompt=prompt, device=device)[:2]
            out = {"prompt_embeds": pe, "prompt_embeds_mask": mask}
            if guidance > 1:  # true CFG: the pipelines only guide with negative embeddings
                npe, nmask = pipe.encode_prompt(prompt=negative or spec.get("empty_negative", ""), device=device)[:2]
                out.update(negative_prompt_embeds=npe, negative_prompt_embeds_mask=nmask)
            return out
        if family == "auraflow":
            pe, mask, npe, nmask = pipe.encode_prompt(prompt=prompt, negative_prompt=negative or "", device=device,
                                                      do_classifier_free_guidance=guidance > 1,
                                                      max_sequence_length=spec["call_kwargs"]["max_sequence_length"])
            out = {"prompt_embeds": pe, "prompt_attention_mask": mask}
            if guidance > 1:
                out.update(negative_prompt_embeds=npe, negative_prompt_attention_mask=nmask)
            return out
    raise ValueError("Staged encoding is not supported for %s" % family)


_TE_RANK = {"none": 0, "q8": 1, "q4": 2}


class _nothing:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


def keep_plan(components, denoiser, family, ram_gb, streamed_plan, text_quant_opts=None):
    """How much of a streamed denoiser may stay on the GPU for good, and the memory plan with it: the largest share
    of its 16 bit weights that fits, less STREAM_KEEP_MARGIN. Every kept block is a block less to read from the SSD
    in every step, which is worth more than a 16 bit text encoder: the text encoders may go to 8 bit (nearly lossless)
    or be loaded per new prompt, but never below what streaming needed anyway.

    Where the text encoder is loaded per new prompt anyway (staged, 16 GB Macs), the kept blocks can make room for it
    while a new prompt is encoded and are read back after (once per prompt, not per step): then only the denoising
    has to fit. Returns (share, plan, release), release: free the kept blocks while encoding."""
    full_gb = memory._gb(components[denoiser], "none")
    resident = memory.stream_resident_share(family)
    worst = max([1] + [_TE_RANK.get(q, 0) for n, q in streamed_plan["quant"].items() if n != denoiser])
    for twentieths in range(20, 3, -1):
        share = twentieths / 20
        keep = round(share - resident - STREAM_KEEP_MARGIN, 2)
        if keep <= 0:
            break
        # the denoiser at its real size (16 bit), only the text encoders' precision and staging are for the plan to pick
        p = memory.plan(components, denoiser, family, ram_gb, quant="auto", denoiser_fixed_gb=full_gb * share,
                        text_quant_opts=text_quant_opts)
        te_ok = all(_TE_RANK.get(q, 0) <= worst for n, q in p["quant"].items() if n != denoiser)
        if p["fits"] and te_ok:
            p["quant"][denoiser] = "none"
            return min(keep, 1.0 - resident), p, False
        # the streamed plan's encoding (blocks in flight only) stays as it is; denoising holds the kept blocks
        denoising = streamed_plan["denoise_peak_gb"] + full_gb * (share - resident)
        if streamed_plan["staged_text_encoder"] and denoising <= streamed_plan["budget_gb"]:
            # the kept blocks count while denoising (the job's planned peak, the room for a ControlNet), not while
            # encoding, when they are released
            p = dict(streamed_plan, denoise_peak_gb=round(denoising, 1),
                     est_peak_gb=round(max(streamed_plan["est_peak_gb"], denoising), 1))
            return min(keep, 1.0 - resident), p, True
    return 0.0, streamed_plan, False


def pipeline_guidance(spec, guidance):
    """The guidance value the pipeline gets: Z-Image guides with any value above 0, the app (and mflux) take values up
    to 1 as "off" (guidance_off_at), as for the other models with real guidance."""
    off = spec.get("guidance_off_at")
    return 0.0 if off is not None and guidance <= off else guidance


def _derive_pipeline(cls, base, **extra):
    """Another pipeline class on the loaded components (img2img, ControlNet).

    Like DiffusionPipeline.from_pipe, but without its final cast of all shared modules (to
    float32 by default, which doubles the memory, and which quantized modules refuse)."""
    params = inspect.signature(cls.__init__).parameters
    kwargs = {k: v for k, v in base.components.items() if k in params}
    kwargs.update(extra)
    for k, p in params.items():
        if k == "self" or k in kwargs or p.kind not in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY):
            continue
        if k in base.config and not k.startswith("_"):
            kwargs[k] = base.config[k]      # settings such as force_zeros_for_empty_prompt
        elif p.default is inspect.Parameter.empty:
            kwargs[k] = None                # optional component the base pipeline does not have
    if "requires_safety_checker" in params:
        kwargs["requires_safety_checker"] = False  # results are checked by content_check.py, for every model
    pipe = cls(**kwargs)
    pipe.set_progress_bar_config(disable=True)
    return pipe


def _prefill(image, mask):
    """Fills the masked (empty) part with the colours of the rest: every empty pixel takes the
    colour of the nearest picture pixel, then that is blurred strongly, so the model continues the
    light and colours at the edge instead of starting from grey."""
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    img = np.asarray(image.convert("RGB"), dtype=np.float32)
    empty = np.asarray(mask.convert("L")) >= 128
    if not empty.any() or empty.all():
        return image.convert("RGB")
    idx = ndimage.distance_transform_edt(empty, return_distances=False, return_indices=True)
    stretched = img[idx[0], idx[1]]
    sigma = max(4, min(empty.shape) / 16)
    blurred = np.stack([ndimage.gaussian_filter(stretched[..., c], sigma) for c in range(3)], -1)
    out = np.where(empty[..., None], blurred, img)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def _mask_crop(mask, width, height):
    """For a mask that covers less than a third of the picture: the region around it (margin a
    quarter of the mask, at least 1/10 of the picture) in the picture's aspect ratio, and
    the size to paint it at (the picture's size). None for big masks."""
    box = mask.getbbox()
    if not box:
        return None
    mw, mh = box[2] - box[0], box[3] - box[1]
    if mw * mh > width * height / 3:
        return None
    pad = max(min(width, height) // 10, max(mw, mh) // 4)
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    side_w = mw + 2 * pad
    side_h = mh + 2 * pad
    # the crop keeps the picture's aspect ratio, so it scales up without distortion
    scale = max(side_w / width, side_h / height)
    cw_, ch_ = min(width, round(width * scale)), min(height, round(height * scale))
    x0 = int(min(max(0, cx - cw_ / 2), width - cw_))
    y0 = int(min(max(0, cy - ch_ / 2), height - ch_))
    if cw_ >= width * 0.8:
        return None
    return (x0, y0, x0 + cw_, y0 + ch_), (width // 8 * 8, height // 8 * 8)


def _grow_mask(mask, fraction=16):
    """The model also repaints a strip of the existing picture along the mask's edge (1/fraction
    of the size), so new and old parts blend instead of meeting at a seam."""
    from PIL import ImageFilter
    r = max(4, min(mask.size) // fraction)
    return mask.filter(ImageFilter.GaussianBlur(r)).point(lambda v: 255 if v > 8 else 0)


def _blend_into(original, painted, mask):
    """Only the masked area comes from the new picture (soft edge); the rest stays pixel-exact
    (the VAE round trip of the pipeline would change it slightly)."""
    from PIL import Image, ImageFilter
    painted = painted.convert("RGB").resize(original.size)
    # the soft edge spans the grown strip: the old picture fades into the new one
    soft = mask.convert("L").filter(ImageFilter.GaussianBlur(max(2, min(original.size) // 24)))
    return Image.composite(painted, original.convert("RGB"), soft)


def _bf16_vae(vae):
    """SDXL's VAE on MPS in bfloat16 for good, encoding too: the img2img and inpaint pipelines would otherwise move it
    to float32 for every input picture and back (force_upcast), and the weights moved in the middle of a job land
    between the job's buffers, where the Metal cache can not give them back afterwards (1.8 GB after an img2img job
    at 1024 px, measured 2026-10-26). bfloat16 has float32's range, so nothing overflows."""
    import torch
    if vae.dtype != torch.bfloat16:
        vae.to(torch.bfloat16)
    if vae.config.get("force_upcast"):
        vae.register_to_config(force_upcast=False)
        encode = vae.encode
        vae.encode = lambda x, *a, **k: encode(x.to(torch.bfloat16), *a, **k)


def _blend_weights(n, like):
    """The next tile's share over an overlap of n: 0 to 1, reached 16 px before the end (the outermost pixels of a tile
    differ most from its neighbour's)."""
    import torch
    return torch.clamp(torch.arange(n, device=like.device, dtype=torch.float32) / max(1, n - 16), 0, 1).to(like.dtype)


def _blend_v(self, a, b, extent):
    extent = min(a.shape[-2], b.shape[-2], extent)
    w = _blend_weights(extent, b).view(1, 1, 1, extent, 1)
    b[:, :, :, :extent, :] = a[:, :, :, -extent:, :] * (1 - w) + b[:, :, :, :extent, :] * w
    return b


def _blend_h(self, a, b, extent):
    extent = min(a.shape[-1], b.shape[-1], extent)
    w = _blend_weights(extent, b).view(1, 1, 1, 1, extent)
    b[:, :, :, :, :extent] = a[:, :, :, :, -extent:] * (1 - w) + b[:, :, :, :, :extent] * w
    return b


def _free_memory():
    import torch
    gc.collect()
    if torch.backends.mps.is_available():
        torch.mps.empty_cache()
    elif torch.cuda.is_available():
        torch.cuda.empty_cache()


# head sizes the fused attention kernel of MPS takes (torch 2.14); others run a slow path that holds the whole attention
# matrix: SD 1.5's 40 (8 heads at 64x64 latents) took 3.5 GB more and 6 times as long
FUSED_HEAD_DIMS = (32, 64)


def fused_attention():
    """On MPS, attention with a head size below 64 the fused kernel does not take is padded with zeros to 64 (same
    result: the zeros add nothing to the scores, the padded output is cut off again)."""
    import torch.nn.functional as F
    sdpa = F.scaled_dot_product_attention
    if getattr(sdpa, "vk_padded", False):
        return

    def padded(query, key, value, *args, scale=None, **kwargs):
        d = query.shape[-1]
        if query.device.type != "mps" or d >= 64 or d in FUSED_HEAD_DIMS or key.shape[-1] != d or value.shape[-1] != d:
            return sdpa(query, key, value, *args, scale=scale, **kwargs)
        pad = lambda t: F.pad(t, (0, 64 - d))
        return sdpa(pad(query), pad(key), pad(value), *args, scale=d ** -0.5 if scale is None else scale, **kwargs)[..., :d]
    padded.vk_padded = True
    F.scaled_dot_product_attention = padded


class DiffusersEngine:
    def __init__(self, reader=None, images_dir=IMAGES_DIR, ram_gb=None):
        self.reader = reader
        self.images_dir = Path(images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.ram_gb = ram_gb
        self.model = None
        self.device = _device()
        if self.device == "mps":
            fused_attention()

    def unload(self):
        if self.model is not None:
            self.model.destroy()
            self.model = None
            _free_memory()  # what only the model object still held (its transformer, a streamed model)

    def _state(self, state):
        protocol.progress(-1)
        protocol.status(state)
        if self.reader is not None and self.reader.stop_requested():
            raise StopRequested()

    def _ensure_model(self, model_dir):
        model_dir = os.path.abspath(model_dir)
        if self.model is not None and self.model.model_dir == model_dir:
            return self.model
        self.unload()
        # imports made before FP8 support: convert once to GGUF (the GPU can not use FP8)
        from importer import migrate_fp8
        migrate_fp8(model_dir, progress_cb=lambda p: protocol.status("Converting FP8 model to GGUF (one-time) %d%%" % p))
        # base parts a single-file model lacks (e.g. a Chroma checkpoint once imported as FLUX.1): taken from what
        # is there, else downloaded once
        from importer import ensure_base
        if ensure_base(model_dir, load_manifest(model_dir), token=os.environ.get("HF_TOKEN") or None,
                       report=lambda stage, pct: protocol.status("%s %d%%" % (stage, pct) if pct >= 0 else stage)):
            protocol.log("[diffusers] base parts of %s completed" % os.path.basename(model_dir))
        self._state("Loading model")
        model = LoadedModel(model_dir, self.device, self.ram_gb)
        model.stop = self.reader.stop_requested if self.reader is not None else None
        model.load()
        self.model = model
        return model

    def generate(self, d):
        """d is the job dict sent by the frontend. Returns the list of saved image paths."""
        if d.get("restore"):
            return self.restore(d)
        if d.get("photo_tool"):
            return self.photo_tool(d)
        model_dir = d.get("model_dir")
        if not model_dir or not os.path.isfile(os.path.join(model_dir, MANIFEST)):
            raise ValueError("Model not found, please re-import it")
        manifest = load_manifest(model_dir)
        if manifest.get("unsupported") or manifest.get("arch") not in registry.ARCHS:
            # installed, but no runtime of the app can run its kind yet
            raise ValueError(manifest.get("unsupported") or "%s models can not run in VulKara yet"
                             % (manifest.get("label") or manifest.get("arch") or "These"))
        model = self._ensure_model(model_dir)
        protocol.precision(model.precision())
        spec, m = model.spec, model.m
        defaults = m.get("defaults", spec["defaults"])

        prompt = d.get("prompt") or ""
        negative = (d.get("negative_prompt") or "") if spec["negative_prompt"] else ""
        steps = int(d.get("num_steps") or defaults["num_steps"])
        guidance = float(d["guidance_scale"]) if d.get("guidance_scale") is not None else defaults["guidance_scale"]
        seed = d.get("seed")
        seed = int(seed) if seed not in (None, "") and int(seed) >= 0 else random.randint(0, 2 ** 31 - 1)
        n_imgs = int(d.get("count") or 1)

        init_image = None
        if d.get("input_image"):
            init_image = colour.open_rgb(d["input_image"])  # in sRGB, whatever profile it carries
        width, height = self._size(d, spec, defaults, init_image)
        need = memory.peak_at(model.plan, width, height)
        protocol.planned(need)
        short = memory.short_of(need, protocol.footprint_gb())
        if short:
            protocol.note(short)

        call = {"num_inference_steps": steps, "guidance_scale": pipeline_guidance(spec, guidance), "width": width,
                "height": height}
        call.update(spec.get("call_kwargs", {}))
        if spec.get("guidance_param"):
            # Qwen-Image: true classifier-free guidance (its guidance_scale is for guidance-distilled models)
            call[spec["guidance_param"]] = call.pop("guidance_scale")
            if guidance > 1 and not negative and spec.get("empty_negative"):
                negative = spec["empty_negative"]  # these pipelines only guide with a negative prompt
        loras = self._resolve_loras(d.get("loras") or [], spec, m)
        # a model with LoRAs baked in (merge.py) takes their trigger words as the LoRAs would have brought them
        baked = (m.get("trigger_words") or []) if (m.get("source") or {}).get("type") == "merge" else []
        for words in [l["trigger_words"] for l in loras] + [baked]:
            for w in words:
                if w and w.lower() not in prompt.lower():
                    prompt = w + ", " + prompt
        if model.release_denoiser:
            # stages: a new prompt is encoded while the denoiser is out, then the denoiser comes (back); the encoding
            # below finds the prompt in the model's cache
            self._state("Encoding prompt")
            model.encode(prompt, negative, guidance)
            model.ensure_denoiser()
        if loras:
            self._state("Loading LoRA")
        model.apply_loras(loras)
        # no sampler chosen: the one the model's maker recommends (maker_settings.py), else the model's own
        if d.get("sampler") and str(d["sampler"]).lower() != "default":
            model.set_sampler(d.get("sampler"), d.get("sigma_schedule"))
        else:
            # a card naming a schedule the sampler, or a sampler the family can not take: what of it works
            for sampler, sigmas in ((defaults.get("sampler"), defaults.get("sigma_schedule")), (defaults.get("sampler"), None), (None, None)):
                try:
                    model.set_sampler(sampler, sigmas)
                    break
                except ValueError:
                    pass
        pipe = model.pipe
        pipe_class = None  # another pipeline built on the loaded components
        pipe_extra = {}
        cn_type = d.get("controlnet_model")
        if cn_type and cn_type != "None" and d.get("controlnet_image"):
            cn_spec = controlnet.resolve(m["arch"], spec["family"], cn_type)
            if init_image is not None and not cn_spec["img2img_pipeline"]:
                raise ValueError("%s models can not combine ControlNet with an input image (Image to image)"
                                 % spec["label"])
            control_image = colour.open_rgb(d["controlnet_image"])
            if d.get("controlnet_preprocess") in (True, "Yes", "true", 1):
                import preprocess
                self._state("Preparing %s control image" % cn_type)
                control_image = preprocess.control_image(cn_type, control_image, report=lambda stage, pct: (
                    protocol.status("%s %d%%" % (stage, pct) if pct >= 0 else stage)))
            control_image = control_image.resize((width, height))
            pipe_extra["controlnet"] = model.ensure_controlnet(cn_spec, width, height)
            call.update(controlnet.call_kwargs(cn_spec, cn_type, d.get("controlnet_weight") or 1.0,
                                               control_image, spec["family"], img2img=init_image is not None))
            pipe_class = cn_spec["img2img_pipeline" if init_image is not None else "pipeline"]
        else:
            model.release_controlnet()

        mask, crop = None, None
        if spec.get("inpaint_only") and not (init_image is not None and d.get("mask_image")):
            raise ValueError("%s only repaints masked parts of a picture (Inpainting, AI Canvas)" % spec["label"])
        if init_image is not None and d.get("mask_image"):
            # inpainting / outpainting (AI Canvas): white in the mask is painted anew
            if not spec.get("inpaint_pipeline"):
                raise ValueError("%s can not paint into a mask; use an SDXL, SD 3.5, FLUX.1, Chroma or Z-Image model" % spec["label"])
            if pipe_class:
                raise ValueError("ControlNet and a mask can not be combined")
            from PIL import Image
            init_image = init_image.resize((width, height))
            raw_mask = Image.open(d["mask_image"]).convert("L").resize((width, height))
            # extending needs a wide transition (smooth skies), repainting a part a narrow one
            mask = _grow_mask(raw_mask, 16 if d.get("prefill") else 48)
            if d.get("prefill"):
                # outpainting: the empty part starts from the colours along the picture's edge
                init_image = _prefill(init_image, raw_mask)
            full_image, full_mask = init_image, mask
            crop = None if d.get("prefill") else _mask_crop(mask, width, height)
            if crop:
                # a small mask: the model paints the area around it at full size, so what the
                # prompt asks for lands in the mask (in the whole picture it would go elsewhere)
                box, (cw, ch) = crop
                init_image = full_image.crop(box).resize((cw, ch), Image.LANCZOS)
                mask = full_mask.crop(box).resize((cw, ch))
                call["width"], call["height"] = cw, ch
            call["image"], call["mask_image"] = init_image, mask
            call["strength"] = min(1.0, max(0.05, float(d.get("inpaint_strength", 1.0))))
            pipe_class = spec["inpaint_pipeline"]
        elif init_image is not None:
            init_image = init_image.resize((width, height))
            if spec["family"] == "flux2" or spec.get("image_reference"):
                # FLUX.2 and Qwen-Image 2.1 use the image as a reference (editing)
                if spec.get("image_reference") and model.separate_text:
                    # Qwen-Image 2.1 reads the picture with its text encoder: encoded apart (staged), the
                    # pipeline can not take it
                    raise ValueError("%s edits pictures only when its text encoder stays loaded: this Mac's memory "
                                     "plan loads it per prompt. Use a smaller (more compressed) model file, or "
                                     "generate without an input picture" % spec["label"])
                call["image"] = [init_image]
            else:
                # how much of the picture changes (0 = nothing, 1 = everything)
                call["strength"] = min(1.0, max(0.05, float(d.get("strength", 0.6))))
                call["image"] = init_image
                pipe_class = pipe_class or spec["img2img_pipeline"]

        if pipe_class:
            import diffusers
            pipe = _derive_pipeline(getattr(diffusers, pipe_class), pipe, **pipe_extra)
            accepted = inspect.signature(pipe.__call__).parameters
            for k in ("width", "height"):
                if k not in accepted:  # SDXL img2img takes the size from the image
                    call.pop(k)

        if model.separate_text:
            self._state("Encoding prompt")
            call.update(model.encode(prompt, negative, guidance))
        else:
            call["prompt"] = prompt
            if negative and spec["negative_prompt"]:
                call["negative_prompt"] = negative

        # above ~1536² the UNet's attention maps alone take GBs: compute them in slices; SD 1.5 / 2 (whose first
        # attention runs at a quarter of the latent's width) already above 512² (768² took 16 GB and swapped, 2026-10-14).
        # On MPS the fused kernel (fused_attention) never holds the maps, slices would only be slower
        if hasattr(pipe, "enable_attention_slicing") and spec["family"] in ("sdxl", "sd1", "sd2"):
            if self.device != "mps" and width * height > (SLICE_ABOVE_PIXELS if spec["family"] == "sdxl" else 512 * 512):
                pipe.enable_attention_slicing()
            else:
                pipe.disable_attention_slicing()

        paths = []
        for i in range(n_imgs):
            self._state("Generating")
            img = self._run(pipe, call, seed + i, steps, model, quiet=d.get("_quiet", False))
            if mask is not None and crop:
                box = crop[0]
                patch = img.convert("RGB").resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
                img = full_image.copy()
                img.paste(patch, box[:2])
                img = _blend_into(full_image, img, full_mask)
            elif mask is not None:
                img = _blend_into(init_image, img, mask)
            path = self._save(img, prompt)
            paths.append(path)
            if not d.get("_quiet") and not d.get("_hold"):
                protocol.result(path)
        return paths

    def photo_tool(self, d):
        """A photo tool (photo_tools.py, ONNX on the CPU): sharpen, denoise, enlarge, cut out. No diffusion model is
        needed, so the loaded one stays."""
        import photo_tools
        protocol.status("Working on the picture")
        protocol.progress(-1)
        t0 = time.time()
        stop = (lambda: self.reader.stop_requested()) if self.reader is not None else None
        path = photo_tools.apply(d, self.images_dir, report=lambda p: protocol.progress(round(p, 1)), stop=stop,
                                 note=protocol.note)
        if path is None:
            raise StopRequested()
        protocol.log("[photo tool] done in %.1fs" % (time.time() - t0))
        if not d.get("_quiet"):
            protocol.result(path)
        return [path]

    def restore(self, d):
        """An old photo restored (restore.py): corrected, repaired by FLUX.2 under guard rails, its soft detail rebuilt
        by Real-ESRGAN, faces by CodeFormer, coloured by DDColor, sharpened. A repair that breaks a guard rail is
        refused with the reason. With "preview" (x, y, w, h in the photo's pixels) only that part is restored, quickly,
        into the previews folder."""
        import restore as rs
        from PIL import Image
        opts = d["restore"]
        original = colour.open_rgb(d["input_image"])  # in sRGB, whatever profile it carries (also HDR)
        full_size = original.size
        box = _preview_box(opts.get("preview"), original.size, original)
        mask = Image.open(d["mask_image"]) if d.get("mask_image") else None
        if box:
            original = original.crop(box)
            if mask is not None:
                mask = mask.convert("L").resize(full_size).crop(box)
        if opts.get("correct"):
            self._state("Correcting colours and contrast")
            work = rs.correct(original, strength=float(opts.get("correct_strength", 0.8)))
        else:
            work = original
        if opts.get("dust"):
            self._state("Removing dust and scratches")
            faces = []
            try:
                faces = rs.find_faces(rs.to_array(work), rs.detector_path())
            except Exception:  # without the detector the eyes are not protected, the rest still works
                pass
            work, share = rs.remove_specks(work, float(opts.get("dust_sensitivity", 0.5)), faces, report=self._state)
            protocol.log("[restore] dust and scratches: %.2f %% of the photo filled" % (share * 100))
        repair, colorize = bool(opts.get("repair")), bool(opts.get("colorize"))
        out = work
        if repair:
            with open(os.path.join(d.get("model_dir") or "", MANIFEST)) as f:
                family = json.load(f).get("family")
            if family != "flux2":
                raise ValueError("The AI restoration needs a FLUX.2 model (it edits the photo, it does not paint anew)")
            source = self.images_dir / (".restore_%d.png" % random.randint(0, 100000000))
            if mask is not None:
                self._state("Filling the damage")
            rs.prefill(work, mask, report=self._state).save(source)
            try:
                job = {k: v for k, v in d.items() if k not in ("restore", "mask_image")}
                job.update(input_image=str(source), count=1, _hold=True,
                           prompt=rs.guard_prompt(opts.get("rules"), d.get("prompt") or ""))
                ai_path = self.generate(job)[0]
            finally:
                source.unlink(missing_ok=True)
            ai = Image.open(ai_path).convert("RGB")
            os.remove(ai_path)
            lock = opts.get("lock", True)
            out, weights = rs.compose(work, ai, mask, repair=True, lock=lock)
            self._state("Checking the guard rails")
            detect = None
            if opts.get("check_faces", True):
                import preprocess
                detect = preprocess.detect_pose
            ok, message = rs.check(work, out, weights if lock else None, float(opts.get("max_change", 0.06)), detect)
            if not ok:
                raise ValueError(message)
            protocol.log("[restore] " + message)
        # faces are taken from the photo before any AI step: the repair repaints faces into other people, and Real-ESRGAN's
        # texture turns into wrinkles
        out = self._details_and_faces(out, work, opts, box)
        if colorize:
            self._state("Colouring")
            out = rs.colorize(out, float(opts.get("color_strength", 1.0)), self.device, report=self._state)
        if opts.get("sharpen"):
            self._state("Sharpening")
            out = rs.sharpen(out, float(opts.get("sharpness", 0.5)))
        if box:
            path = self._save_preview(out, box)
        else:
            path = self._save(out, "restored photo")
        protocol.result(path)
        return [path]

    def _details_and_faces(self, out, face_source, opts, box):
        """Restore's AI steps on a soft photo: its detail rebuilt by Real-ESRGAN (or the photo only enlarged), its faces
        restored by CodeFormer from face_source, the photo before any AI step."""
        import restore as rs
        from PIL import Image
        scale = 2 if int(opts.get("scale", 1) or 1) == 2 else 1
        if opts.get("details"):
            self._state("Rebuilding details")
            say = lambda x: protocol.progress(round(x, 1)) if isinstance(x, (int, float)) else self._state(x)  # noqa: E731
            stop = (lambda: self.reader.stop_requested()) if self.reader is not None else None
            rebuilt = rs.details(out, float(opts.get("detail_level", 2.0)), float(opts.get("detail_strength", 1.0)),
                                 scale, report=say, stop=stop)
            protocol.progress(-1)
            if rebuilt is None:
                raise StopRequested()
            out = rebuilt
        elif scale == 2:
            out = out.resize((out.width * 2, out.height * 2), Image.LANCZOS)
        if opts.get("faces"):
            self._state("Finding faces")
            points = _face_points(opts.get("face_points"), box, out.width / face_source.width)
            out, count = rs.restore_faces(out, face_source, float(opts.get("face_fidelity", 0.9)),
                                          float(opts.get("face_strength", 0.6)), self.device, report=self._state,
                                          points=points)
            protocol.log("[restore] %d face(s) restored" % count)
            if not count and not box:
                protocol.note("No face was found that is large enough to restore (at least %d pixels from the eyes "
                              "to the mouth)." % rs.FACE_MIN)
        return out

    def _save_preview(self, img, box):
        """A preview of Restore: into the previews folder of the pictures folder; the oldest beyond 12 are removed.
        Its name tells the part of the photo (preview_x…_y…_w…_h…_id.png), so the page can show the same part of the
        original next to it."""
        folder = self.images_dir / PREVIEWS
        folder.mkdir(parents=True, exist_ok=True)
        old = sorted(folder.glob("preview_*.png"), key=lambda p: p.stat().st_mtime)
        for p in old[:-11]:
            p.unlink(missing_ok=True)
        x0, y0, x1, y1 = box
        path = folder / ("preview_x%d_y%d_w%d_h%d_%s.png" % (x0, y0, x1 - x0, y1 - y0, uuid.uuid4().hex[:12]))
        img.save(path)
        return str(path)

    def make_preview(self, job):
        """A model paints a preview picture: of itself, or of a LoRA it is used with (see previews.paint)."""
        import previews
        return previews.paint(self.generate, job)

    @staticmethod
    def _resolve_loras(entries, spec, m=None):
        from importer import LORA_MANIFEST
        out = []
        model = dict(m or {}, family=spec["family"], label=(m or {}).get("label") or spec["label"])
        for e in entries:
            if not e or not e.get("path"):
                continue
            with open(os.path.join(e["path"], LORA_MANIFEST)) as f:
                lm = json.load(f)
            problem = registry.lora_mismatch(lm, model)
            if problem:
                raise ValueError(problem)
            folder = os.path.abspath(e["path"])
            file = os.path.normpath(os.path.join(folder, lm["file"]))
            if os.path.dirname(file) != folder:
                raise ValueError("The LoRA %s names a file outside its folder" % lm["name"])
            out.append({"file": file, "scale": e.get("scale", 1.0),
                        "name": lm["name"], "trigger_words": lm.get("trigger_words", []) if e.get("use_trigger", True) else []})
        return out

    def _size(self, d, spec, defaults, init_image):
        mult = spec["size_multiple"]
        if d.get("width") and d.get("height") and (init_image is None or d.get("exact_size")):
            w, h = int(d["width"]), int(d["height"])
        elif init_image is not None:
            w, h = init_image.size
            # keep the aspect ratio, but work at the model's native pixel count
            target = defaults["width"] * defaults["height"]
            scale = (target / float(w * h)) ** 0.5
            w, h = w * scale, h * scale
        else:
            w, h = defaults["width"], defaults["height"]
        return _snap(w, mult), _snap(h, mult)

    def _run(self, pipe, call, seed, steps, model=None, quiet=False):
        import torch
        reader = self.reader

        sync = torch.mps.synchronize if self.device == "mps" else (lambda: None)

        def on_step(p, i, t, kwargs):
            sync()  # MPS runs asynchronously: report a step once it is really done
            total = getattr(p, "_num_timesteps", None) or steps
            if not quiet:
                protocol.progress(round(100.0 * (i + 1) / total, 1))
            if reader is not None and reader.stop_requested():
                p._interrupt = True
            return kwargs

        generator = torch.Generator("cpu").manual_seed(seed)
        t0 = time.time()
        decode_self = model is not None and model.decode_self
        denoiser = getattr(pipe, model.m["denoiser"], None) if model is not None else None
        with step_cache.run(denoiser) if denoiser is not None else _nothing() as cache:
            out = pipe(generator=generator, callback_on_step_end=on_step,
                       **dict(call, output_type="latent") if decode_self else call)
        if reader is not None and reader.stop_requested():
            raise StopRequested()
        cached = step_cache.note(cache)
        if cached and not quiet:
            protocol.note(cached)
        if cache is not None:
            protocol.log("[diffusers] step caching: %d of %d runs reused" % (cache.reused, cache.runs))
        if decode_self:
            protocol.status("Decoding")
            img = model.decode_sdxl_latents(out.images)
        else:
            img = out.images[0]
        del out
        _free_memory()  # give cached GPU memory back between images
        protocol.log("[diffusers] image done in %.1fs" % (time.time() - t0))
        if model is not None and model.stream:
            protocol.waited("ssd_stream", streaming.STATS["wait"], streaming.STATS["read_gb"])
            if streaming.PROFILE:
                protocol.log("[diffusers] stream profile: " + streaming.report())
            else:
                streaming.reset()
        return img

    def _save(self, img, prompt):
        stem = "".join(filter(str.isalnum, prompt[:30])) or "image"
        path = self.images_dir / ("%s_%s.png" % (stem, uuid.uuid4().hex[:12]))
        img.save(path)
        return str(path)
