# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""MLX engine: runs FLUX.1, FLUX.2 [klein] and Z-Image models (diffusers folder layout), Krea 2, Ideogram 4, ERNIE-Image
and Fibo 2.0 (mflux's saved files) with mflux, and FLUX 3 Image Klein with flux3-mlx (flux3.py).

Speaks the same stdin/stdout protocol as the diffusers engine (see ../diffusers/protocol.py)
and reads the same model.json manifests, so the app can route a job to either engine.
"""
import hashlib
import inspect
import json
import os
import random
import re
import sys
import tempfile
import time
import uuid
import traceback
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
# protocol, memory planning and manifests are shared with the diffusers engine (stdlib only)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "diffusers"))

import memory  # noqa: E402
import protocol  # noqa: E402
import paths  # noqa: E402
import prompt_cache  # noqa: E402
import quant_cache  # noqa: E402

MANIFEST = "model.json"
LORA_MANIFEST = "lora.json"
IMAGES_DIR = paths.images_dir()

# mflux's quantization bits and the matching level of the memory plan, least quantized first
MLX_QUANT = [(None, "none"), (8, "q8"), (4, "q4")]


class StopRequested(Exception):
    pass


def model_class_and_config(m):
    from mflux.models.common.config import ModelConfig
    arch = m["arch"]
    if arch in ("flux1_schnell", "flux1_dev"):
        from mflux.models.flux.variants.txt2img.flux import Flux1
        return Flux1, (ModelConfig.schnell() if arch == "flux1_schnell" else ModelConfig.dev())
    if arch == "flux2_klein":
        from mflux.models.flux2.variants import Flux2Klein
        big = m.get("components", {}).get("transformer", 4) > 6
        distilled = m.get("defaults", {}).get("num_steps", 4) <= 8
        name = "flux2_klein_%s%s" % ("" if distilled else "base_", "9b" if big else "4b")
        return Flux2Klein, getattr(ModelConfig, name)()
    if arch == "z_image":
        from mflux.models.z_image import ZImage
        return ZImage, (ModelConfig.z_image() if z_image_guided(m) else ModelConfig.z_image_turbo())
    if arch == "krea2":
        from mflux.models.krea2.variants.txt2img.krea2 import Krea2
        return Krea2, ModelConfig.krea2()
    if arch == "ideogram4":
        from mflux.models.ideogram4 import Ideogram4
        return Ideogram4, ModelConfig.ideogram4_fp8()
    if arch == "ernie_image":
        from mflux.models.ernie_image import ErnieImage
        return ErnieImage, (ModelConfig.ernie_image() if ernie_guided(m) else ModelConfig.ernie_image_turbo())
    raise ValueError("The MLX runtime does not support %s models" % m.get("label", arch))


FAMILIES = {"flux1_schnell": "flux1", "flux1_dev": "flux1", "flux2_klein": "flux2", "krea2": "krea2",
            "ideogram4": "ideogram4", "z_image": "z_image", "flux3_klein": "flux3", "ernie_image": "ernie",
            "fibo2_mlx": "fibo2"}


def ernie_guided(m):
    """ERNIE-Image (SFT) runs with guidance, Turbo without (mflux refuses any other guidance than 1 for Turbo); the
    defaults the import chose tell which."""
    return float((m.get("defaults") or {}).get("guidance_scale", 1.0)) > 1.0


def z_image_guided(m):
    """Z-Image (Base) and its fine-tunes run with guidance (mflux's z_image config: CFG, Euler with shift); Turbo
    and distilled ones without (z_image_turbo: guidance forced to 0). The defaults the import chose tell which."""
    return float((m.get("defaults") or {}).get("guidance_scale", 0) or 0) > 1


def z_image_shift(m, model_dir):
    """The fixed shift of Z-Image's schedule: from a repository's scheduler config, else the maker's (Turbo 3, Base 6)."""
    weights = m.get("weights_dir") or ""
    path = os.path.join(weights if os.path.isabs(weights) else os.path.join(model_dir, weights), "scheduler",
                        "scheduler_config.json")
    try:
        with open(path) as f:
            cfg = json.load(f)
        if not cfg.get("use_dynamic_shifting") and cfg.get("shift"):
            return float(cfg["shift"])
    except (OSError, ValueError):
        pass
    return 6.0 if z_image_guided(m) else 3.0


# a LoRA of which fewer of its layers find their place in mflux's mapping does not fit the model (as in the
# diffusers engine: mflux applies what matches and only prints the rest)
MIN_APPLIED = 0.9
_DOWN = re.compile(r"\.(lora_A|lora_down|lora\.down)(\.default)?\.weight$")


def lora_coverage(keys, mapping):
    """(layers of the LoRA mflux's mapping places, layers of the LoRA): its down factors against the mapping's
    patterns ("{block}" a block number)."""
    patterns = [re.compile("^" + re.escape(p).replace(re.escape("{block}"), r"\d+") + "$")
                for t in mapping for p in t.possible_down_patterns]
    downs = [k for k in keys if _DOWN.search(k)]
    return sum(1 for k in downs if any(p.match(k) for p in patterns)), len(downs)


def fibo2_lora(path, name):
    """A Fibo 2.0 LoRA as mflux takes it: ComfyUI's fused layout split once into diffusers' (lora_convert
    .fibo2_to_diffusers) into a cached copy; a LoRA whose layers mostly have no place is refused. Returns the file."""
    import lora_convert
    import registry
    keys = list(registry.read_safetensors_header(path))
    if lora_convert.fibo2_needs_diffusers(keys):
        st = os.stat(path)
        tag = hashlib.sha1(("%s|%d|%d" % (os.path.abspath(path), st.st_size, int(st.st_mtime))).encode()).hexdigest()[:16]
        folder = os.path.join(tempfile.gettempdir(), "vulkara_mlx_loras")
        out = os.path.join(folder, "fibo2_%s.safetensors" % tag)
        if not os.path.isfile(out):
            import mlx.core as mx
            os.makedirs(folder, exist_ok=True)
            converted = lora_convert.fibo2_to_diffusers(dict(mx.load(path)))
            mx.save_safetensors(out + ".tmp.safetensors", converted)
            os.replace(out + ".tmp.safetensors", out)
            protocol.log("[mlx] LoRA %s split into diffusers' names" % name)
        path = out
        keys = list(registry.read_safetensors_header(path))
    from mflux.models.fibo2.weights.fibo2_lora_mapping import Fibo2LoRAMapping
    placed, total = lora_coverage(keys, Fibo2LoRAMapping.get_mapping())
    if not total or placed < total * MIN_APPLIED:
        raise ValueError("The LoRA %s does not fit this Fibo 2.0 model: only %d%% of its layers (%d of %d) found their "
                         "place" % (name, int(100 * placed / max(1, total)), placed, total))
    return path


def z_image_lora(path, name):
    """A Z-Image LoRA as mflux takes it: files in other names than diffusers' (ComfyUI's fused qkv, kohya's) are
    converted once into a cached copy (lora_convert.z_image_to_diffusers, the same as the diffusers engine's); a LoRA
    whose layers mostly have no place in the model is refused. Returns the file to load."""
    import lora_convert
    import registry
    keys = list(registry.read_safetensors_header(path))
    if lora_convert.z_image_needs(keys):
        st = os.stat(path)
        tag = hashlib.sha1(("%s|%d|%d" % (os.path.abspath(path), st.st_size, int(st.st_mtime))).encode()).hexdigest()[:16]
        folder = os.path.join(tempfile.gettempdir(), "vulkara_mlx_loras")
        out = os.path.join(folder, "z_image_%s.safetensors" % tag)
        if not os.path.isfile(out):
            import mlx.core as mx
            os.makedirs(folder, exist_ok=True)
            converted = lora_convert.z_image_to_diffusers(dict(mx.load(path)))
            mx.save_safetensors(out + ".tmp.safetensors", converted)
            os.replace(out + ".tmp.safetensors", out)
            protocol.log("[mlx] LoRA %s converted to diffusers' names" % name)
        path = out
        keys = list(registry.read_safetensors_header(path))
    from mflux.models.z_image.weights.z_image_lora_mapping import ZImageLoRAMapping
    placed, total = lora_coverage(keys, ZImageLoRAMapping.get_mapping())
    if not total or placed < total * MIN_APPLIED:
        raise ValueError("The LoRA %s does not fit this Z-Image model: only %d%% of its layers (%d of %d) found their "
                         "place" % (name, int(100 * placed / max(1, total)), placed, total))
    return path


# models whose checkpoint mflux reads in its own (FP8) format from base/, next to the base components
NATIVE_ARCHS = {"krea2", "ideogram4"}
# may drop the text encoder after encoding a prompt (a new prompt reloads the model): Ideogram 4, Krea 2 and Z-Image on
# small Macs, where the transformer(s) and the Qwen text encoder do not fit next to each other
STAGED_ARCHS = {"ideogram4", "krea2", "z_image"}
# Macs this small decode in tiles (low_ram)
LOW_RAM_GB = 16
# what decoding the picture in one piece adds to the plan at 1024 px (footprints measured on an M2 24 GB, MEASUREMENTS 7m);
# in tiles it is gone, so a Mac that has not that much free decodes in tiles
DECODE_GB = {"z_image": 2.5, "flux2": 1.0, "krea2": 2.0, "ernie": 2.5, "flux1": 4.5}
# the most freed buffers MLX keeps for reuse (mflux's low-RAM value): without a limit they grew to 9.9 GB per picture
CACHE_LIMIT_BYTES = 1000 ** 3
# quantized once and saved in mflux's format (<model>/mlx_q<bits>): later loads read it directly
# instead of decoding and quantizing the FP8 checkpoints again (Ideogram 4: 27 GB FP8 -> 14 GB; Krea 2, whose text
# encoder is freed after each prompt on a 16 GB Mac, then reloads quickly for a new prompt); Z-Image, ERNIE and
# FLUX.2 [klein] read their 16 bit repository at every load otherwise (Z-Image Turbo 30 GB, 46 s, MEASUREMENTS 7bs)
CACHED_ARCHS = {"ideogram4", "krea2", "z_image", "ernie_image", "flux2_klein"}
CACHE_MIN_FREE_GB = 5.0
# mflux samplers of Ideogram 4 by step count (steps + guidance schedule + noise schedule)
IDEOGRAM_PRESETS = {12: "V4_TURBO_12", 20: "V4_DEFAULT_20", 48: "V4_QUALITY_48"}
# mflux leaves these text encoders in 16 bit ("quantizing the TE degrades conditioning")
TEXT_ENCODER_16BIT = {"krea2"}


def choose_quant(m, ram_gb=None):
    """mflux quantizes all weights alike: pick the least quantization whose plan fits.

    Returns (bits, plan, quantize_text_encoder)."""
    family = FAMILIES[m["arch"]]
    ram = ram_gb or memory.total_ram_gb()
    comps = m["components"]
    if m["arch"] in TEXT_ENCODER_16BIT:
        # first try with the text encoder in 16 bit as mflux keeps it: count it at 16 bit size
        for bits, level in MLX_QUANT:
            scaled = {c: (p * memory.BYTES_PER_PARAM["none"] / memory.BYTES_PER_PARAM[level]
                          if c.startswith("text_encoder") else p) for c, p in comps.items()}
            p = memory.plan(scaled, m["denoiser"], family, ram, quant=level, allow_staging=False)
            if p["fits"]:
                return bits, p, False
    for bits, level in MLX_QUANT:
        # mflux keeps text encoders loaded, so nothing is staged (except for STAGED_ARCHS)
        p = memory.plan(comps, m["denoiser"], family, ram, quant=level, allow_staging=m["arch"] in STAGED_ARCHS)
        if p["fits"]:
            return bits, p, m["arch"] in TEXT_ENCODER_16BIT
    return 4, p, m["arch"] in TEXT_ENCODER_16BIT


# families whose transformer and VAE compute correctly in float16 (text encoders stay bfloat16,
# in float16 they overflow)
FP16_FAMILIES = {"flux2"}
_BF16_SLOW = None
_TE_HOOKED = False


def bf16_is_slow():
    """True on GPUs without bfloat16 hardware (M1/M2), measured once with a matmul."""
    global _BF16_SLOW
    if _BF16_SLOW is None:
        import mlx.core as mx
        timings = {}
        for dt in (mx.bfloat16, mx.float16):
            a = mx.random.normal((1024, 2048)).astype(dt)
            b = mx.random.normal((2048, 2048)).astype(dt)
            mx.eval(a @ b)
            t0 = time.time()
            for _ in range(10):
                mx.eval(a @ b)
            timings[dt] = time.time() - t0
        _BF16_SLOW = timings[mx.bfloat16] > 1.3 * timings[mx.float16]
    return _BF16_SLOW


def compute_dtype(family):
    """float16 where bfloat16 has no hardware and the family is known to work in float16;
    VK_MLX_PRECISION=bf16|fp16 overrides (auto by default)."""
    import mlx.core as mx
    choice = os.environ.get("VK_MLX_PRECISION", "auto").lower()
    if choice == "fp16" or (choice == "auto" and family in FP16_FAMILIES and bf16_is_slow()):
        return mx.float16
    return mx.bfloat16


def _set_precision(dtype):
    """mflux reads one global precision; text encoders are kept in bfloat16 whatever it is."""
    global _TE_HOOKED
    import mlx.core as mx
    from mflux.models.common.config import ModelConfig
    from mflux.models.common.weights.loading.weight_definition import ComponentDefinition
    ModelConfig.precision = dtype
    if not _TE_HOOKED:
        orig_init = ComponentDefinition.__init__

        def init(self, *args, **kwargs):
            orig_init(self, *args, **kwargs)
            if str(getattr(self, "name", "")).startswith("text_encoder") and self.precision is not None \
                    and self.precision == mx.float16:
                self.precision = mx.bfloat16
        ComponentDefinition.__init__ = init
        _TE_HOOKED = True


_FP8_PATCHED = False


def comfy_scaled_fp8(weights):
    """Checkpoints saved by ComfyUI as "scaled FP8" (e.g. Krea 2 fine-tunes on Civitai) carry a
    factor per weight ("<name>.weight_scale", the weight is fp8 x factor), "comfy_quant" entries
    describing the format and the prefix "model.diffusion_model.". Applies the factors to the already
    decoded weights and leaves the checkpoint as mflux expects it."""
    prefix = "model.diffusion_model."
    if any(k.startswith(prefix) for k in weights):
        weights = {(k[len(prefix):] if k.startswith(prefix) else k): v for k, v in weights.items()}
    for k in [k for k in weights if k.endswith(".weight_scale")]:
        w = k[:-len("_scale")]
        scale = weights.pop(k)
        if w in weights:
            weights[w] = weights[w] * scale.astype(weights[w].dtype)
    for k in [k for k in weights if k.endswith((".comfy_quant", ".input_scale", ".scale_input"))]:
        del weights[k]
    return weights


def _patch_fp8_loading():
    """mflux reads FP8 tensors of native checkpoints (e.g. Civitai's Krea 2 FP8) as raw bytes;
    decode them to the compute precision (lazily, so mflux still quantizes layer by layer)."""
    global _FP8_PATCHED
    if _FP8_PATCHED:
        return
    import struct

    import mlx.core as mx
    from mflux.models.common.config import ModelConfig
    from mflux.models.common.weights.loading.weight_loader import WeightLoader
    original = WeightLoader._load_mlx_native

    def load(path, weight_files=None):
        weights = original(path, weight_files)
        files = [Path(path) / f for f in weight_files] if weight_files else \
            sorted(f for f in Path(path).glob("*.safetensors") if not f.name.startswith("._"))
        for f in files:
            with open(f, "rb") as fh:
                header = json.loads(fh.read(struct.unpack("<Q", fh.read(8))[0]))
            for k, v in header.items():
                if isinstance(v, dict) and v.get("dtype") == "F8_E4M3" and k in weights:
                    # in the compute precision (bfloat16, or float16 on GPUs without bfloat16)
                    weights[k] = mx.from_fp8(weights[k], dtype=ModelConfig.precision)
        return comfy_scaled_fp8(weights)

    WeightLoader._load_mlx_native = staticmethod(load)
    _FP8_PATCHED = True


_SCALES_PATCHED = False


def _patch_ideogram_scalar_scales():
    """Ideogram 4 FP8 files from ComfyUI ("fp8_scaled") carry one scale per tensor, Ideogram's own
    files one per output row, which is all mflux's Fp8Linear handles: spread a single scale over
    the rows before the layer is used or quantized."""
    global _SCALES_PATCHED
    if _SCALES_PATCHED:
        return
    import mlx.core as mx
    from mflux.models.ideogram4.model.ideogram4_transformer.fp8_linear import Fp8Linear

    def spread(layer):
        scale = layer.weight_scale
        if scale.size == 1 and layer.out_features != 1:
            layer.weight_scale = mx.broadcast_to(scale.reshape(()).astype(mx.float32), (layer.out_features,))

    call, to_quantized = Fp8Linear.__call__, Fp8Linear.to_quantized

    def patched_call(self, x):
        spread(self)
        return call(self, x)

    def patched_to_quantized(self, *args, **kwargs):
        if self.weight.shape == (self.out_features, self.in_features):
            spread(self)
        return to_quantized(self, *args, **kwargs)

    Fp8Linear.__call__ = patched_call
    Fp8Linear.to_quantized = patched_to_quantized
    _SCALES_PATCHED = True


_QUANTIZE_TE = False
_TE_QUANT_PATCHED = False


def _quantize_krea2_text_encoder(on):
    """On small Macs the Krea 2 text encoder (Qwen3-VL, 8.8 GB in 16 bit) is quantized as well."""
    global _QUANTIZE_TE, _TE_QUANT_PATCHED
    _QUANTIZE_TE = on
    if _TE_QUANT_PATCHED or not on:
        return
    from mflux.models.krea2.weights.krea2_weight_definition import Krea2WeightDefinition
    original = Krea2WeightDefinition.get_components

    def components():
        out = original()
        for c in out:
            if c.name == "text_encoder" and _QUANTIZE_TE:
                c.skip_quantization = False
        return out

    Krea2WeightDefinition.get_components = staticmethod(components)
    _TE_QUANT_PATCHED = True


class Progress:
    """mflux callback: reports steps and turns a stop request into mflux's own interruption."""

    def __init__(self, reader, steps, quiet=False):
        self.reader = reader
        self.steps = steps
        self.quiet = quiet  # preview pictures do not move the progress bar of a job

    def call_in_loop(self, t, seed, prompt, latents, config, time_steps):
        # mflux calls this before it evaluates the step (MLX is lazy): evaluated here, the value is sent when the step
        # is done, not one step early (the run time's loading part came out a step short, Krea 2 at 0 s)
        import mlx.core as mx
        mx.eval(latents)
        if not self.quiet:
            protocol.progress(round(100.0 * (t + 1) / self.steps, 1))
        if self.reader is not None and self.reader.stop_requested():
            raise KeyboardInterrupt()


def ideogram_caption(prompt):
    """Ideogram 4 is trained on structured JSON captions; with a bare description it often paints
    its "blocked by safety filter" card. A plain prompt becomes a full caption: the description,
    the scene as background and main element, and quoted or UPPERCASE words as lettering."""
    import re
    text = [t.strip() for t in re.findall(r'"([^"]{1,80})"|\u201c([^\u201d]{1,80})\u201d', prompt) for t in t if t.strip()]
    if not text:
        text = [t.strip() for t in re.findall(r"\b[A-Z0-9][A-Z0-9'&!?.,\- ]{2,60}[A-Z0-9!?]\b", prompt)
                if sum(c.isalpha() for c in t) >= 3]
    elements = [{"type": "obj", "bbox": [120, 80, 920, 920], "desc": prompt}]
    for i, t in enumerate(text[:3]):
        top = 60 + i * 110
        elements.append({"type": "text", "bbox": [top, 100, top + 90, 900], "text": t,
                         "desc": "Clearly legible lettering reading \"%s\"." % t})
    style = {"aesthetics": "high quality, detailed, coherent composition", "lighting": "natural, well balanced lighting"}
    if re.search(r"poster|illustrat|drawing|drawn|painting|painted|sketch|cartoon|comic|anime|logo|label|"
                 r"typograph|graphic|vector|icon|watercolou?r|pixel art|3d render|render", prompt, re.I):
        style.update(medium="graphic_design" if re.search(r"poster|logo|label|typograph|graphic|icon", prompt, re.I)
                     else "illustration", art_style="as described in the prompt")
    else:
        style.update(photo="natural photograph, sharp focus", medium="photograph")
    return {
        "high_level_description": prompt,
        "style_description": style,
        "compositional_deconstruction": {"background": "The setting of the scene: " + prompt, "elements": elements},
    }


def _mflux_version():
    try:
        import importlib.metadata
        return importlib.metadata.version("mflux")
    except Exception:
        return "?"


def free_buffers(after="image"):
    """MLX keeps freed buffers for reuse, by default without a limit: after one picture of FLUX.2 [klein] 4B at 512 px
    9.9 GB of them beside 7.5 GB in use (footprint 17.9 GB), which pushed a 24 GB Mac into swap. They are limited to
    1 GB and go back after loading and after each picture; the line in the log tells what the engine holds."""
    import gc
    import mlx.core as mx
    mx.set_cache_limit(CACHE_LIMIT_BYTES)
    gc.collect()
    cached = mx.get_cache_memory()
    mx.clear_cache()
    protocol.log("[mlx] after %s: %.1f GB in use, %.1f GB of freed buffers given back, peak %.1f GB"
                 % (after, mx.get_active_memory() / 1e9, cached / 1e9, mx.get_peak_memory() / 1e9))
    mx.reset_peak_memory()


def materialize(model, text_encoders=True, denoiser=True):
    """Reads and quantizes the weights part by part right after loading, the denoiser first. mflux leaves them lazy, and
    the first step then loaded and quantized all parts at once: Z-Image Turbo on a 16 GB Mac mini peaked at 29.3 GB and
    took 84 s per step, part by part 12.3 GB and 21 s (MEASUREMENTS 7bc). text_encoders=False leaves the text encoders
    for the encoding (a plan that frees the denoiser while it encodes: both are never loaded together); denoiser=False
    leaves the transformer until the text encoder is dropped (DropTextEncoder reads it then)."""
    import mlx.core as mx
    # an mlx Module is a dict: its parts are its items, not attributes
    members = list(model.items()) if isinstance(model, dict) else list(vars(model).items())
    parts = [(n, v) for n, v in members if callable(getattr(v, "parameters", None))]
    parts.sort(key=lambda p: 0 if "transformer" in p[0] else 2 if p[0].startswith("text_encoder") else 1)
    done = []
    for name, part in parts:
        if (name.startswith("text_encoder") and not text_encoders) or ("transformer" in name and not denoiser):
            continue
        mx.eval(part.parameters())
        mx.clear_cache()  # the 16 bit originals of this part
        done.append(name)
    return done


# Krea 2's Qwen VAE in mflux's 512 px tiles still added 6.6 GB to the 7.7 GB model on a 16 GB Mac mini (14.3 GB at
# 768 and 1024 px); 256 px tiles 3.6 GB (11.3 GB), the picture 44.8 dB from the 512 px tiles, no seam (MEASUREMENTS 7bd)
DECODE_TILE = {"krea2": 256}


def low_ram(model, arch=None):
    """As mflux's own low-RAM mode (its MemorySaver) on small Macs: the VAE decodes in tiles where that costs nothing
    visually (the decode was the peak: Z-Image at 1024 px 13.8 GB against 7.5 GB for the steps)."""
    from mflux.models.common.vae.tiling_config import TilingConfig
    if getattr(model, "tiling_config", None) is None and TilingConfig.may_tile_implicitly(model):
        model.tiling_config = TilingConfig(vae_decode_tile_size=DECODE_TILE[arch]) if arch in DECODE_TILE else TilingConfig()


def cache_prompt_encodings(model, keep=8):
    """Z-Image in mflux encodes the prompt for every picture; with the text encoder dropped (staged) the encodings of
    the prompts it has seen are kept instead, like the prompt caches of mflux's other models."""
    import mlx.core as mx
    encode, cache = model._encode_prompts, {}

    def cached(*, prompt, negative_prompt, guidance):
        k = (prompt, negative_prompt if guidance > 1.0 else None)
        if k not in cache:
            out = encode(prompt=prompt, negative_prompt=negative_prompt, guidance=guidance)
            mx.eval([o for o in out if o is not None])
            if len(cache) >= keep:
                cache.pop(next(iter(cache)))
            cache[k] = out
        return cache[k]
    model._encode_prompts = cached
    model.prompt_cache = cache  # as mflux's other models: kept on disk by the engine


def _eager_fibo2_pictures():
    """mflux leaves an edit's encoded picture lazy: computed only at the first step, beside the transformer. Evaluated
    at once it is done while the text encoder is still there and the transformer not yet (DropTextEncoder)."""
    from mflux.models.fibo2.latent_creator.fibo2_latent_creator import Fibo2LatentCreator
    encode = Fibo2LatentCreator.encode_image
    if getattr(encode, "vk_eager", False):
        return

    def eager(*args, **kwargs):
        import mlx.core as mx
        out = encode(*args, **kwargs)
        mx.eval(out)
        return out
    eager.vk_eager = True
    Fibo2LatentCreator.encode_image = staticmethod(eager)


class DropTextEncoder:
    """mflux callback for staged models: once the prompt is encoded (and in mflux's prompt cache),
    the text encoder is freed before denoising; a new prompt loads the model again."""

    def __init__(self, engine):
        self.engine = engine

    def call_before_loop(self, seed, prompt, latents, config, **kwargs):
        model = self.engine.model
        if getattr(model, "text_encoder", None) is not None:
            self.engine.keep_encodings()
            model.text_encoder = None
            self.engine.encoded.add(self.engine.encode_key)
            import gc
            import mlx.core as mx
            gc.collect()
            mx.clear_cache()
            protocol.log("[mlx] text encoder freed for denoising")
        # a transformer left lazy (Fibo 2.0) is read only now, after the text encoder and the picture to edit
        if self.engine.lazy_denoiser:
            materialize(model)
            self.engine.lazy_denoiser = False


class MlxEngine:
    def __init__(self, reader=None):
        self.reader = reader
        self.model = None
        self.key = None
        self.staged = False
        self.encoded = set()  # prompts in mflux's prompt cache while the text encoder is dropped
        self.encode_key = None
        self.lazy_denoiser = False  # Fibo 2.0 staged: the transformer is read in DropTextEncoder
        self.disk_parts = None  # what a loaded model's prompt encodings depend on (prompt cache on disk)
        self.cache_before = set()  # mflux's prompt cache before this job's prompt was encoded
        self.bit_sizes = []  # (part, "8 bit") of the loaded model, reported with each job
        self.plan = None  # the memory plan of the loaded model (choose_quant)
        self.flux3_peak = None
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    def unload(self):
        self.model = None
        self.lazy_denoiser = False
        self.key = None
        self.disk_parts = None
        self.staged = False
        self.encoded = set()
        import gc
        import mlx.core as mx
        gc.collect()
        mx.clear_cache()

    def _state(self, state):
        protocol.progress(-1)
        protocol.status(state)
        if self.reader is not None and self.reader.stop_requested():
            raise StopRequested()

    def _ensure(self, model_dir, m, loras, prompt=None):
        native = m.get("layout") == "single_denoiser" and m.get("arch") in NATIVE_ARCHS
        if m.get("layout") != "repo" and not native:
            raise ValueError("The MLX runtime needs models in diffusers folder layout")
        key = (model_dir, tuple((l["file"], l["scale"]) for l in loras))
        if key == self.key and (not self.staged or getattr(self.model, "text_encoder", None) is not None
                                or prompt in self.encoded or self._cached_encodings(prompt)):
            return
        self.unload()
        dtype = compute_dtype(FAMILIES.get(m["arch"]))
        _set_precision(dtype)  # before the model class reads it
        if "float16" in str(dtype) and "bfloat16" not in str(dtype):
            protocol.log("[mlx] computing in float16 (no bfloat16 hardware on this GPU), text encoder in bfloat16")
        cls, config = model_class_and_config(m)
        bits, plan, quantize_te = choose_quant(m)
        self.plan = plan
        if not plan["fits"]:
            raise MemoryError("%s needs about %d GB RAM" % (m.get("label", m["arch"]), plan["min_ram_gb"]))
        folder = m["base_dir"] if native else m["weights_dir"]  # native: checkpoint sits in base/
        weights = folder if os.path.isabs(folder) else os.path.join(model_dir, folder)
        cache = os.path.join(model_dir, "mlx_q%s" % bits) if m["arch"] in CACHED_ARCHS and bits else None
        cached = bool(cache) and os.path.isfile(os.path.join(cache, "complete"))
        source = weights  # what the encodings on disk go by, also once the saved copy loads instead
        if cached:
            weights = cache  # the linked checkpoints are not needed any more
        else:
            for rel, src in (m.get("linked_files") or {}).items():
                if not os.path.isfile(os.path.join(model_dir, m["base_dir"], rel)):
                    raise FileNotFoundError("%s uses the file %s where it was imported from; it is no longer "
                                            "there (moved, deleted, or its disk is not connected)" % (m.get("name"), src))
        _patch_fp8_loading()
        if m["arch"] == "ideogram4":
            _patch_ideogram_scalar_scales()
        _quantize_krea2_text_encoder(quantize_te)
        if quantize_te:
            protocol.log("[mlx] text encoder quantized too (%d bit) to fit into RAM" % bits)
        self._state("Loading model (MLX%s)" % (", %d bit" % bits if bits else ""))
        # bake_lora=False applies LoRAs next to the quantized weights; baking them in needs the
        # full 16 bit weights in memory first
        self.model = cls(quantize=bits, model_path=weights, model_config=config,
                         lora_paths=[l["file"] for l in loras] or None,
                         lora_scales=[float(l["scale"]) for l in loras] or None,
                         bake_lora=not loras)
        self.staged = bool(plan.get("staged_text_encoder")) and m["arch"] in STAGED_ARCHS
        if self.staged and m["arch"] == "z_image":
            cache_prompt_encodings(self.model)
        # the text encoder's files, its bit size and the LoRAs: what the encodings on disk depend on
        te = os.path.join(source, "text_encoder")
        self.disk_parts = {"engine": "mlx", "arch": m["arch"], "weights": quant_cache._source_signature(source, None),
                           "text_encoder": quant_cache._source_signature(te, None) if os.path.isdir(te) else None,
                           "bits": bits, "quantize_te": quantize_te,
                           "loras": [(f, s, os.path.getmtime(f)) for f, s in key[1]]} if self.staged else None
        self.encoded = set()
        save = cache and not cached and not loras
        # this prompt encoded before: its text encoder is never read (the weights stay lazy until materialize); loaded
        # with it Z-Image Turbo held 11.0 GB and swapped 2.7 GB on a 16 GB Mac mini (MEASUREMENTS 7bt)
        skip_te = not save and self._cached_encodings(prompt)
        if skip_te:
            self.model.text_encoder = None
        materialize(self.model, text_encoders=not skip_te)  # before saving the cache, which would evaluate all at once
        if save:
            self._save_cache(m, cache)
        free_buffers("loaded")
        # mflux quantizes every part alike, except text encoders it keeps in 16 bit
        own = "%d bit" % bits if bits else "16 bit"
        self.bit_sizes = [(m["denoiser"], own), ("text_encoder", own if quantize_te or m["arch"] not in TEXT_ENCODER_16BIT
                                                   or not bits else "16 bit")]
        self.key = key
        if memory.total_ram_gb() <= LOW_RAM_GB:
            low_ram(self.model, m["arch"])
        protocol.log("[mlx] loaded %s, quantize=%s%s" % (m["name"], bits, ", text encoder not read (prompt encoded before)"
                                                          if skip_te else ", text encoder only for new prompts"
                                                          if self.staged else ""))
        if not skip_te:
            self._cached_encodings(prompt)
        return

    def _disk_key(self, prompt):
        if self.disk_parts is None or prompt is None:
            return None
        import importlib.metadata as md
        try:
            versions = {p: md.version(p) for p in ("mlx", "mflux")}
        except Exception:
            return None  # no versions to key by: encoded as before, not kept
        return prompt_cache.key(dict(self.disk_parts, prompt=list(prompt)), versions=versions)

    def _cached_encodings(self, prompt):
        """A staged model's prompt encoded before (also before a restart): its encodings from the disk into mflux's
        prompt cache, so the text encoder is not needed (with it dropped, the model is not loaded again)."""
        entries = prompt_cache.load_mlx(self._disk_key(prompt))
        if not entries or getattr(self.model, "prompt_cache", None) is None:
            return False
        self.model.prompt_cache.update(entries)
        self.encoded.add(prompt)
        protocol.log("[mlx] prompt encodings from the prompt cache")
        return True

    def keep_encodings(self):
        """After a staged model encoded this job's prompt: the new entries of mflux's prompt cache onto the disk."""
        cache = getattr(self.model, "prompt_cache", None) or {}
        prompt_cache.save_mlx(self._disk_key(self.encode_key),
                              {k: v for k, v in cache.items() if k not in self.cache_before})

    def _save_cache(self, m, cache):
        """Writes the freshly quantized model in mflux's format (once, if the disk has room)."""
        import shutil
        need_gb = sum(m.get("components", {}).values()) * memory.BYTES_PER_PARAM["q4"]
        free_gb = shutil.disk_usage(os.path.dirname(cache)).free / 1024 ** 3
        if free_gb - need_gb < CACHE_MIN_FREE_GB:
            protocol.log("[mlx] not caching the quantized model: %.0f GB free" % free_gb)
            return
        self._state("Saving the quantized model for faster loading (one-time)")
        t0 = time.time()
        shutil.rmtree(cache, ignore_errors=True)
        try:
            self.model.save_model(cache)
            with open(os.path.join(cache, "complete"), "w") as f:
                f.write("mflux %s\n" % _mflux_version())
            protocol.log("[mlx] cached the quantized model in %s (%.0fs)" % (cache, time.time() - t0))
        except Exception as e:
            shutil.rmtree(cache, ignore_errors=True)
            protocol.log("[mlx] could not cache the quantized model: %s" % e)

    @staticmethod
    def _resolve_loras(entries, m):
        """The job's LoRAs; refused when one does not fit the model (m: its model.json), e.g. a
        FLUX.2 [klein] 9B LoRA for the 4B model."""
        import registry
        out = []
        for e in entries or []:
            if not e or not e.get("path"):
                continue
            with open(os.path.join(e["path"], LORA_MANIFEST)) as f:
                lm = json.load(f)
            problem = registry.lora_mismatch(lm, m)
            if problem:
                raise ValueError(problem)
            folder = os.path.abspath(e["path"])
            file = os.path.normpath(os.path.join(folder, lm["file"]))
            if os.path.dirname(file) != folder:
                raise ValueError("The LoRA %s names a file outside its folder" % lm.get("name", "?"))
            if m.get("arch") == "z_image":
                file = z_image_lora(file, lm.get("name") or "?")
            if m.get("arch") == "fibo2_mlx":
                file = fibo2_lora(file, lm.get("name") or "?")
            out.append({"file": file, "scale": e.get("scale", 1.0), "name": lm.get("name") or os.path.basename(folder),
                        "trigger_words": lm.get("trigger_words", [])})
        return out

    def _ernie_enhance(self, d, prompt, width, height):
        """ERNIE-Image's prompt enhancer (ernie_pe.py) on request: the description it writes is the prompt of the
        picture and goes to the job's note. Run before the model loads; a loaded model goes when memory is short."""
        import ernie_pe
        import helpers
        import pinned
        h = next(x for x in helpers.catalog() if x["id"] == "ernie_pe")
        folder = helpers.folder_of(h)
        if not pinned.ready(h["repo"], folder):
            # the MLX engine never downloads (it runs without network): the page or Models does that
            raise ValueError("The ERNIE prompt enhancer is not downloaded yet: download it next to the option on Text to "
                             "image or on the Models page (Helper models), or switch the option off")
        pe = os.path.join(folder, "pe")
        if self.model is not None and memory.free_gb() < ernie_pe.enhancer_gb(pe) + 1.0:
            self.unload()
            protocol.log("[mlx] model unloaded for the prompt enhancer")
        seed = d.get("seed")
        seed = int(seed) if seed not in (None, "") and int(seed) >= 0 else random.randint(0, 2 ** 31 - 1)
        d["seed"] = seed  # the picture takes the same seed: prompt and seed give the same description again
        self._state("Writing the full caption (prompt upsampler)")
        t0 = time.time()

        def stop():
            if self.reader is not None and self.reader.stop_requested():
                raise StopRequested()
        caption = ernie_pe.enhance(pe, prompt, width, height, seed, stop=stop)
        # the description retells the prompt: it goes to the job's note, never into the log (a shared report)
        protocol.log("[mlx] prompt enhanced in %.0fs (%d characters)" % (time.time() - t0, len(caption)))
        protocol.note("Prompt written by the enhancer: " + caption)
        return caption

    def generate(self, d):
        model_dir = d.get("model_dir")
        if not model_dir or not os.path.isfile(os.path.join(model_dir, MANIFEST)):
            raise ValueError("Model not found, please re-import it")
        with open(os.path.join(model_dir, MANIFEST)) as f:
            m = json.load(f)
        loras = self._resolve_loras(d.get("loras"), m)
        defaults = m.get("defaults", {})

        prompt = d.get("prompt") or ""
        for l in loras:
            for w in l["trigger_words"]:
                if w and w.lower() not in prompt.lower():
                    prompt = w + ", " + prompt
        width = int(d.get("width") or defaults.get("width", 1024)) // 16 * 16
        height = int(d.get("height") or defaults.get("height", 1024)) // 16 * 16
        if m.get("arch") == "ernie_image" and d.get("upsample") and not d.get("input_image"):
            prompt = self._ernie_enhance(d, prompt, width, height)
        if m.get("arch") == "flux3_klein":
            return self._generate_flux3(d, m, model_dir, loras, prompt, width, height)
        if m.get("arch") == "fibo2_mlx":
            return self._generate_fibo2(d, m, model_dir, prompt, width, height, loras)
        steps = int(d.get("num_steps") or defaults.get("num_steps", 4))
        guidance = float(d["guidance_scale"]) if d.get("guidance_scale") is not None else defaults.get("guidance_scale", 1.0)
        if m["arch"] == "flux2_klein" and steps <= 8:
            guidance = 1.0  # distilled klein models run without guidance
        if m["arch"] == "ernie_image" and not ernie_guided(m):
            guidance = 1.0
        # what the encodings in mflux's prompt caches go by: Z-Image the negative prompt with guidance, Krea 2 negative
        # prompt and guidance, Ideogram 4 the size
        neg = d.get("negative_prompt") or None
        encode_key = {"z_image": (prompt, neg if guidance > 1.0 else None), "krea2": (prompt, neg, guidance),
                      "ideogram4": (prompt, width, height)}.get(m["arch"], (prompt,))
        self._ensure(model_dir, m, loras, encode_key)
        protocol.precision(self.bit_sizes)
        self._plan_job(FAMILIES[m["arch"]], width, height)
        model_prompt = prompt
        if m["arch"] == "ideogram4" and not prompt.strip().startswith("{"):
            model_prompt = ideogram_caption(prompt)  # JSON captions are passed on as they are
        seed = d.get("seed")
        seed = int(seed) if seed not in (None, "") and int(seed) >= 0 else random.randint(0, 2 ** 31 - 1)

        self.model.callbacks.in_loop = [cb for cb in self.model.callbacks.in_loop if not isinstance(cb, Progress)]
        self.model.callbacks.register(Progress(self.reader, steps, quiet=d.get("_quiet", False)))
        if self.staged and not any(isinstance(cb, DropTextEncoder) for cb in self.model.callbacks.before_loop):
            self.model.callbacks.register(DropTextEncoder(self))
        self.encode_key = encode_key
        self.cache_before = set(getattr(self.model, "prompt_cache", None) or {})

        if m["arch"] == "ideogram4" and steps in IDEOGRAM_PRESETS:
            # the preset brings its own guidance and noise schedules
            args = {"preset": IDEOGRAM_PRESETS[steps], "warn_on_caption_issues": False}
        elif m["arch"] == "ideogram4":
            args = {"num_inference_steps": steps, "guidance": guidance, "warn_on_caption_issues": False}
        else:
            args = {"num_inference_steps": steps, "guidance": guidance}
            if m["arch"] == "z_image":
                import mlx_schedulers
                args["scheduler"] = mlx_schedulers.static_shift(z_image_shift(m, model_dir))
            if d.get("negative_prompt") and "negative_prompt" in inspect.signature(self.model.generate_image).parameters:
                args["negative_prompt"] = d["negative_prompt"]

        saved = []
        for i in range(int(d.get("count") or 1)):
            self._state("Generating")
            t0 = time.time()
            try:
                result = self.model.generate_image(seed=seed + i, prompt=model_prompt, width=width, height=height, **args)
            except Exception as e:
                if type(e).__name__ == "StopImageGenerationException":
                    raise StopRequested()
                raise
            stem = "".join(filter(str.isalnum, prompt[:30])) or "image"
            path = IMAGES_DIR / ("%s_%s.png" % (stem, uuid.uuid4().hex[:12]))
            result.image.save(path)
            protocol.log("[mlx] image done in %.1fs" % (time.time() - t0))
            free_buffers()
            if not d.get("_quiet"):
                protocol.result(str(path))
            saved.append(str(path))
        return saved


    def _plan_job(self, family, width, height):
        """Reports the planned peak; decodes in tiles when the one-piece decode would not fit into the memory free now,
        and notes when even that is short."""
        need, held = memory.peak_at(self.plan, width, height), protocol.footprint_gb()
        decode = DECODE_GB.get(family, 0) * max(0.25, width * height / (1024 * 1024))
        if decode and getattr(self.model, "tiling_config", None) is None:
            if need + decode > memory.free_gb(held):
                low_ram(self.model, family)
                if getattr(self.model, "tiling_config", None) is not None:
                    protocol.note("Not enough memory free to decode the picture in one piece: decoded in tiles "
                                  "(no visible difference)")
            if getattr(self.model, "tiling_config", None) is None:
                need += decode
        protocol.planned(need)
        short = memory.short_of(need, held)
        if short:
            protocol.note(short)

    def _generate_flux3(self, d, m, model_dir, loras, prompt, width, height):
        """FLUX 3 Image Klein (flux3.py): an input picture is its reference; the prompt upsampler on request."""
        import flux3
        weights = m["weights_dir"] if os.path.isabs(m["weights_dir"]) else os.path.join(model_dir, m["weights_dir"])
        key = ("flux3", weights, tuple((l["file"], l["scale"]) for l in loras))
        if key != self.key:
            self.unload()
            low_memory, peak = flux3.plan(weights)
            self.flux3_peak = peak
            self._state("Loading model (MLX)")
            self.model = flux3.Flux3Model(weights, loras, low_memory, peak)
            free_buffers("loaded")
            self.bit_sizes = flux3.precision(weights)
            self.key = key
            protocol.log("[mlx] loaded %s with flux3-mlx (peak about %.0f GB%s)"
                         % (m["name"], peak, ", text encoder only for encoding" if low_memory else ""))
        protocol.precision(self.bit_sizes)
        protocol.planned(self.flux3_peak)
        short = memory.short_of(self.flux3_peak, protocol.footprint_gb())
        if short:
            protocol.note(short)
        images = []
        if d.get("input_image"):
            import colour
            images.append(colour.open_rgb(d["input_image"]))  # in sRGB, whatever profile it carries
            if not d.get("exact_size"):
                width = height = None  # the reference sets the size (flux3-mlx crops back to its shape)

        caption = prompt
        if d.get("upsample") and not flux3.finished_caption(prompt):
            if images:
                protocol.log("[mlx] the prompt upsampler is for text to image here: the edit uses the prompt as written")
            else:
                import helpers
                import pinned
                pup = next(h for h in helpers.catalog() if h["id"] == "flux3_pup")
                folder = helpers.folder_of(pup)
                if not pinned.ready(pup["repo"], folder):
                    # the MLX engine never downloads (it runs without network): the page or Models does that
                    raise ValueError("The FLUX 3 prompt upsampler is not downloaded yet: download it next to the option "
                                     "on Text to image or on the Models page (Helper models), or switch the option off")
                if self.model.make_room(flux3.upsampler_gb(folder)):
                    protocol.log("[mlx] model parts freed for the prompt upsampler")
                self._state("Writing the full caption (prompt upsampler)")
                t0 = time.time()
                def stop():
                    if self.reader is not None and self.reader.stop_requested():
                        raise StopRequested()
                caption = flux3.Upsampler(folder)(prompt, stop=stop)
                # the caption retells the prompt: it goes to the job's note, never into the log (a shared report)
                protocol.log("[mlx] prompt upsampled in %.0fs (%d characters)" % (time.time() - t0, len(caption)))
                protocol.note("Prompt written by the upsampler: " + caption)

        defaults = m.get("defaults", {})
        # the distilled checkpoint (16 steps) samples without guidance; Base with it (registry.detect_flux3)
        distilled = float(defaults.get("guidance_scale") or 1.0) <= 1.0
        steps = int(d.get("num_steps") or defaults.get("num_steps") or (flux3.DISTILLED_STEPS if distilled else flux3.BASE_STEPS))
        # the distilled model samples without guidance; Base with classifier-free guidance
        guidance = None if distilled else float(d.get("guidance_scale") or defaults.get("guidance_scale") or flux3.BASE_GUIDANCE)
        seed = d.get("seed")
        seed = int(seed) if seed not in (None, "") and int(seed) >= 0 else random.randint(0, 2 ** 31 - 1)
        quiet = d.get("_quiet", False)

        def step(done, total):
            if not quiet:
                protocol.progress(round(100.0 * done / total, 1))
            if self.reader is not None and self.reader.stop_requested():
                raise StopRequested()

        saved = []
        for i in range(int(d.get("count") or 1)):
            self._state("Generating")
            t0 = time.time()
            image = self.model.generate(caption, images, width, height, steps, guidance, seed + i, step, distilled)
            stem = "".join(filter(str.isalnum, prompt[:30])) or "image"
            path = IMAGES_DIR / ("%s_%s.png" % (stem, uuid.uuid4().hex[:12]))
            image.save(path)
            protocol.log("[mlx] image done in %.1fs" % (time.time() - t0))
            free_buffers()
            if not quiet:
                protocol.result(str(path))
            saved.append(str(path))
        return saved

    def _generate_fibo2(self, d, m, model_dir, prompt, width, height, loras=()):
        """Fibo 2.0 from mflux's saved files: text to image, an edit of the input picture as the prompt says, or only
        inside a mask (greyed out as in training, then blended back, the rest pixel for pixel). The weights load
        lazily: staged, the text encoder is dropped before the transformer's come in, and a new prompt loads again."""
        import registry
        from mflux.models.common.config import ModelConfig
        from mflux.models.fibo2.variants import Fibo2, Fibo2Edit
        weights = m["weights_dir"] if os.path.isabs(m["weights_dir"]) else os.path.join(model_dir, m["weights_dir"])
        defaults = m.get("defaults", {})
        dev = float(defaults.get("guidance_scale") or 1.0) > 1.0
        plan = memory.plan(m["components"], "transformer", "fibo2", memory.total_ram_gb(), quant="none",
                           allow_staging=True, staging_frees_denoiser=True,
                           activations_gb=registry.ARCHS["fibo2_mlx"]["activations_gb"])
        if not plan["fits"]:
            raise MemoryError("%s needs about %d GB RAM" % (m.get("label", "Fibo 2.0"), plan["min_ram_gb"]))
        staged = plan["staged_text_encoder"]
        key = ("fibo2", weights, tuple((l["file"], float(l["scale"])) for l in loras))
        if key != self.key or getattr(self.model, "text_encoder", None) is None:
            self.unload()
            self._state("Loading model (MLX)")
            self.model = Fibo2Edit(model_path=weights, model_config=ModelConfig.fibo2() if dev
                                   else ModelConfig.fibo2_edit_turbo(),
                                   lora_paths=[l["file"] for l in loras] or None,
                                   lora_scales=[float(l["scale"]) for l in loras] or None, bake_lora=not loras)
            if memory.total_ram_gb() <= LOW_RAM_GB:
                low_ram(self.model)
            # staged, the transformer is read after the prompt and the picture to edit: loaded with them it took
            # 14.3-14.6 GB on a 16 GB Mac mini before the first step (MEASUREMENTS 7bq)
            materialize(self.model, text_encoders=not staged, denoiser=not staged)
            self.lazy_denoiser = staged
            free_buffers("loaded")
            bits = getattr(self.model, "bits", None)
            self.bit_sizes = [("transformer", "%d bit" % bits if bits else "16 bit"),
                              ("text_encoder", "%d bit" % bits if bits else "16 bit")]
            self.key, self.plan, self.staged, self.encoded = key, plan, staged, set()
            protocol.log("[mlx] loaded %s, %s%s" % (m["name"], self.bit_sizes[0][1],
                                                    ", text encoder only for the prompt" if staged else ""))
        protocol.precision(self.bit_sizes)
        if staged:
            _eager_fibo2_pictures()
        # further pictures it edits with the input picture, each about 1 megapixel whatever its size
        refs = len(d.get("reference_images") or []) if d.get("input_image") and not d.get("mask_image") else 0
        spec = registry.ARCHS["fibo2_mlx"]
        need = memory.peak_at(plan, width, height, refs * spec["reference_gb"] + (spec["edit_gb"] if d.get("input_image") else 0))
        protocol.planned(need)
        short = memory.short_of(need, protocol.footprint_gb())
        if short:
            protocol.note(short)

        steps = int(d.get("num_steps") or defaults.get("num_steps", 4))
        guidance = float(d["guidance_scale"]) if dev and d.get("guidance_scale") is not None else (5.0 if dev else 1.0)
        seed = d.get("seed")
        seed = int(seed) if seed not in (None, "") and int(seed) >= 0 else random.randint(0, 2 ** 31 - 1)
        self.model.callbacks.in_loop = [cb for cb in self.model.callbacks.in_loop if not isinstance(cb, Progress)]
        self.model.callbacks.register(Progress(self.reader, steps, quiet=d.get("_quiet", False)))
        if staged and not any(isinstance(cb, DropTextEncoder) for cb in self.model.callbacks.before_loop):
            self.model.callbacks.register(DropTextEncoder(self))
        self.encode_key = (prompt,)

        work = tempfile.mkdtemp(prefix="vk_fibo2_")
        original = mask = None
        args = {"num_inference_steps": steps, "guidance": guidance}
        if d.get("input_image"):
            import colour
            import masks
            from PIL import Image
            original = colour.open_rgb(d["input_image"])  # in sRGB, whatever profile it carries
            image_path = os.path.join(work, "image.png")
            original.save(image_path)
            args["image_paths"] = [image_path]
            for i, ref in enumerate((d.get("reference_images") or []) if not d.get("mask_image") else []):
                # further pictures it edits with the input picture (<image_2> ...); a mask is for one picture
                args["image_paths"].append(os.path.join(work, "image%d.png" % (i + 2)))
                colour.open_rgb(ref).save(args["image_paths"][-1])
            if d.get("mask_image"):
                # the model repaints what it sees grey, a strip along the mask's edge included, so old and new blend
                painted_part = Image.open(d["mask_image"]).convert("L").resize(original.size)
                mask = masks.grow_mask(painted_part, 48)
                args["mask_path"] = os.path.join(work, "mask.png")
                mask.save(args["mask_path"])
            if not d.get("exact_size"):
                # the picture's proportions at the model's pixel count: the edit lines up with the picture
                pixels = defaults.get("width", 1024) * defaults.get("height", 1024)
                k = (pixels / float(original.width * original.height)) ** 0.5
                width, height = (max(16, round(v * k / 16) * 16) for v in original.size)
        saved = []
        try:
            for i in range(int(d.get("count") or 1)):
                self._state("Generating")
                t0 = time.time()
                try:
                    if original is None:
                        result = Fibo2.generate_image(self.model, seed=seed + i, prompt=prompt, width=width,
                                                      height=height, **args)
                    else:
                        result = self.model.generate_image(seed=seed + i, prompt=prompt, width=width, height=height,
                                                           **args)
                except Exception as e:
                    if type(e).__name__ == "StopImageGenerationException":
                        raise StopRequested()
                    raise
                image = result.image
                if mask is not None:
                    image = masks.blend_into(original, image, mask, painted_part)  # outside the mask the picture stays as it was
                stem = "".join(filter(str.isalnum, prompt[:30])) or "image"
                path = IMAGES_DIR / ("%s_%s.png" % (stem, uuid.uuid4().hex[:12]))
                image.save(path)
                protocol.log("[mlx] image done in %.1fs" % (time.time() - t0))
                free_buffers()
                if not d.get("_quiet"):
                    protocol.result(str(path))
                saved.append(str(path))
        finally:
            import shutil
            shutil.rmtree(work, ignore_errors=True)
        return saved


def serve(stream=None):
    reader = protocol.CommandReader(stream).start()
    engine = MlxEngine(reader)
    footprint = protocol.Footprint()  # per job, for benchmarks
    protocol.state("loaded")
    if os.environ.get("VK_ANNOUNCE_READY") == "1":
        protocol.state("idle")
    while True:
        item = reader.next_command()
        if item is None:
            break
        op, job = item
        if op in ("generate", "preview"):
            protocol.state("busy")
            footprint.start()
            # preview: a picture painted by a model (of itself or of a LoRA), see previews.paint
            target = job.get("target") or job.get("model_dir")
            try:
                if op == "preview":
                    import previews
                    protocol.preview({"model": target, "preview": previews.paint(engine.generate, job)})
                else:
                    engine.generate(job)
            except StopRequested:
                protocol.log("[mlx] stopped")
                if op == "preview":
                    protocol.preview({"model": target, "error": "stopped"})
            except Exception as e:
                traceback.print_exc()
                if op == "preview":
                    protocol.preview({"model": target, "error": str(e)[:300]})
                else:
                    protocol.error(protocol.describe(e))
            footprint.report()
            protocol.state("idle")
        elif op == "unload":
            try:
                engine.unload()
            except Exception:
                traceback.print_exc()
        elif op == "ping":
            protocol.event("pong")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "train":
        # LoRA training (train.py), started by the app's Training page
        import train
        try:
            train.main(sys.argv[2])
        except Exception as e:
            traceback.print_exc()
            train.emit({"error": str(e)[:400]})
            sys.exit(1)
    else:
        serve()
