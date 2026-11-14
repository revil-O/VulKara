# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""LoRA files in the namings diffusers' own readers do not take, brought into one they do, before loading.

engine.py hands every LoRA through prepare() (loading, the coverage check and the SSD streaming path read the same
converted dict). What is converted, per pipeline:

- every pipeline: peft dumps (".lora_A.default.weight", with or without "base_model.model."), the component prefix
  ("transformer." / "unet.") added when a file has none; a file naming some layers ".lora.down/up" and the others
  ".lora_A/B" in one naming (diffusers' reader takes one per file and drops the rest: lrzjason's FLUX.2 [klein]
  consistency LoRAs, 20 of 100 layers)
- FLUX.1 / Chroma: the original (BFL) block names with peft factors (lora_A / lora_B), as ComfyUI and ai-toolkit
  write them, into kohya's names, which diffusers' FLUX reader maps (it splits the fused qkv layers); Chroma's
  distilled guidance layers are left out (diffusers maps none of them)
- Qwen-Image 2.1: ComfyUI's fused SwiGLU layer img_mlp.gate_up (ai-toolkit "qwen_image_2" LoRAs) split into
  diffusers' img_mlp.gate_layer (the first half of the rows) and img_mlp.proj (the second half)
- Z-Image: every naming other than diffusers' with peft factors (ComfyUI's original names with the fused
  attention.qkv, kohya's, peft dumps) into diffusers' names (z_image_to_diffusers); the MLX engine uses the same
- SD / SDXL: ai-toolkit's "lora_transformer_" names and stray "diffusion_model_" keys as kohya's "lora_unet_"
  (diffusers converts a kohya file only when every key is kohya's)

- Fibo 2.0: diffusers' layout (to_q / to_k / to_v, w1 / w3, to_out.0) fused for ComfyUI's repacked files (attention.qkv,
  feed_forward.w13 with the hidden width padded to a multiple of 256, attention.out, cross and perceiver attention
  to_kv), the rank stacked (fibo2_to_comfy); and ComfyUI's fused layout split back into diffusers' for mflux
  (fibo2_to_diffusers). Neither runtime reads the other's layout.

LyCORIS LoKr / LoHa have no reader in diffusers: they are refused with a clear message (check_format).
"""
import os
import re

import registry


class UnsupportedLoraFormat(ValueError):
    pass


_LYCORIS = re.compile(r"\.(lokr_w[12](_[ab])?|lokr_t[12]|hada_w[12]_[ab]|hada_t[12])$")

# a LoRA layer in the original (BFL) block names with peft factors, as ai-toolkit writes FLUX.1 / Chroma LoRAs for ComfyUI
_BFL_PEFT = re.compile(r"^(?:model\.diffusion_model\.|diffusion_model\.|transformer\.)?"
                       r"((?:double_blocks|single_blocks)\.\d+\..+?|img_in|txt_in|final_layer\..+?)"
                       r"\.(lora_A|lora_B|alpha)(?:\.default)?(?:\.weight)?$")

# the fused SwiGLU layer of Qwen-Image 2.1 in ComfyUI's names: dotted (ai-toolkit) or kohya's underscores
_GATE_UP = re.compile(r"^(.*img_mlp)([._])gate_up(\.(?:lora_A|lora_B|lora_down|lora_up)\.weight|\.alpha)$")

_COMPONENT_PREFIXES = ("transformer.", "unet.", "text_encoder.", "text_encoder_2.", "text_encoder_3.", "lora_unet_",
                       "lora_te", "lora_transformer_", "diffusion_model.", "model.diffusion_model.", "diffusion_model_",
                       "lycoris_")


def check_format(keys, name="This LoRA"):
    """Refuses formats no diffusers reader takes (LyCORIS LoKr / LoHa) with a message that says so."""
    for k in keys:
        if _LYCORIS.search(k):
            kind = "LoKr" if "lokr" in k else "LoHa"
            raise UnsupportedLoraFormat("%s is a LyCORIS %s file: LoKr/LoHa LoRAs are not supported yet (only LoRA, "
                                        "LoCon and DoRA files load)" % (name, kind))


def bfl_lora_to_kohya(sd):
    """A LoRA in the original block names with peft factors in kohya's names; without an alpha a layer keeps
    scale 1. Layers of Chroma's distilled guidance network are left out."""
    out = {}
    for k, v in sd.items():
        if "distilled_guidance_layer" in k:
            continue
        m = _BFL_PEFT.match(k)
        if not m:
            out[k] = v
            continue
        suffix = {"lora_A": ".lora_down.weight", "lora_B": ".lora_up.weight", "alpha": ".alpha"}[m.group(2)]
        out["lora_unet_" + m.group(1).replace(".", "_") + suffix] = v
    return out


def split_gate_up(sd):
    """Qwen-Image 2.1's fused gate_up layer as diffusers' gate_layer (first half of the rows) and proj (second):
    the down factor (lora_A) and alpha go to both, the up factor (lora_B) is cut in two."""
    out = {}
    for k, v in sd.items():
        m = _GATE_UP.match(k)
        if not m:
            out[k] = v
            continue
        head, sep, tail = m.groups()
        gate, proj = head + sep + "gate_layer" + tail, head + sep + "proj" + tail
        if tail.startswith((".lora_B", ".lora_up")):
            out[gate], out[proj] = (x.contiguous() for x in v.chunk(2, dim=0))
        else:
            out[gate], out[proj] = v, v.clone() if hasattr(v, "clone") else v
    return out


# ---------------------------------------------------------------- Z-Image

# the layers of Z-Image's transformer in diffusers' names (which mflux takes as well)
_Z_LAYER = r"(?:layers|noise_refiner|context_refiner)\.\d+\."
_Z_CANONICAL = re.compile(r"^(?:" + _Z_LAYER + r"(?:attention\.(?:to_q|to_k|to_v|to_out\.0)|feed_forward\.w[123]|"
                          r"adaLN_modulation\.0)|cap_embedder\.\d+|t_embedder\.mlp\.\d+|all_x_embedder\.2-1|"
                          r"all_final_layer\.2-1\.(?:linear|adaLN_modulation\.1))$")
_Z_PREFIXES = ("base_model.model.", "model.diffusion_model.", "diffusion_model.", "transformer.", "lora_unet_",
               "lycoris_")
_Z_FACTOR = re.compile(r"\.(?:(lora_a|lora_down|lora\.down)|(lora_b|lora_up|lora\.up))(?:\.default)?(?:\.weight)?$|"
                       r"\.(alpha)$", re.I)
# kohya's names (every "." an "_") of the layers, lower case
_Z_KOHYA = [
    (re.compile(r"^(layers|noise_refiner|context_refiner)_(\d+)_attention_(qkv|out)$"), r"\1.\2.attention.\3"),
    (re.compile(r"^(layers|noise_refiner|context_refiner)_(\d+)_attention_to_(q|k|v)$"), r"\1.\2.attention.to_\3"),
    (re.compile(r"^(layers|noise_refiner|context_refiner)_(\d+)_attention_to_out_0$"), r"\1.\2.attention.to_out.0"),
    (re.compile(r"^(layers|noise_refiner|context_refiner)_(\d+)_feed_forward_(w[123])$"), r"\1.\2.feed_forward.\3"),
    (re.compile(r"^(layers|noise_refiner|context_refiner)_(\d+)_adaln_modulation_0$"), r"\1.\2.adaLN_modulation.0"),
    (re.compile(r"^cap_embedder_(\d+)$"), r"cap_embedder.\1"),
    (re.compile(r"^t_embedder_mlp_(\d+)$"), r"t_embedder.mlp.\1"),
    (re.compile(r"^(?:all_)?x_embedder(?:_2-1)?$"), "x_embedder"),
    (re.compile(r"^(?:all_)?final_layer(?:_2-1)?_linear$"), "final_layer.linear"),
    (re.compile(r"^(?:all_)?final_layer(?:_2-1)?_adaln_modulation_1$"), "final_layer.adaLN_modulation.1"),
]


def _z_parts(key):
    """(module, factor) of a Z-Image LoRA key: factor "A" (down), "B" (up) or "alpha"; None for other entries
    (DoRA scales, full weight differences)."""
    k = key
    for p in _Z_PREFIXES:
        if k.startswith(p):
            k = k[len(p):]
            break
    m = _Z_FACTOR.search(k)
    if not m:
        return None
    factor = "A" if m.group(1) else "B" if m.group(2) else "alpha"
    module = k[:m.start()]
    if "." not in module:  # kohya
        low = module.lower()
        for pattern, repl in _Z_KOHYA:
            if pattern.match(low):
                module = pattern.sub(repl, low)
                break
    module = re.sub(r"\.to\.([qkv])$", r".to_\1", module)  # "to.q" of some trainers
    module = re.sub(r"\.attention\.out$", ".attention.to_out.0", module)
    module = re.sub(r"^(?:all_)?x_embedder(?:\.2-1)?$", "all_x_embedder.2-1", module)
    module = re.sub(r"^(?:all_)?final_layer(?:\.2-1)?\.", "all_final_layer.2-1.", module)
    return module, factor


def z_image_needs(keys):
    """Whether a Z-Image LoRA is in names other than diffusers' (with peft factors lora_A / lora_B): ComfyUI's original
    names (fused attention.qkv, attention.out, final_layer, x_embedder), kohya's, peft dumps."""
    for k in keys:
        if not k.startswith(("diffusion_model.", "transformer.")) or ".default." in k:
            return True  # kohya, peft dumps, ComfyUI's model.diffusion_model., no prefix at all
        parts = _z_parts(k)
        if parts is None:
            continue
        module, factor = parts
        if module.endswith(".attention.qkv") or not _Z_CANONICAL.match(module):
            return True
        if factor != "alpha" and not re.search(r"\.lora_[AB]\.weight$", k):
            return True
    return False


def z_image_to_diffusers(sd):
    """A Z-Image LoRA in diffusers' names with peft factors ("diffusion_model.<layer>.lora_A.weight", ".lora_B.weight",
    ".alpha"), which both runtimes read. The fused qkv layer of the original names becomes to_q / to_k / to_v: the
    down factor and alpha go to all three, the up factor is cut in three (rows q, k, v). Where a file has both the fused
    and the split layer (or "out" and "to_out.0"), the split one counts. Works on torch and MLX arrays alike."""
    out, fused = {}, {}
    for k, v in sd.items():
        parts = _z_parts(k)
        if parts is None:
            continue
        module, factor = parts
        name = {"A": "lora_A.weight", "B": "lora_B.weight", "alpha": "alpha"}[factor]
        if module.endswith(".attention.qkv"):
            fused[(module[:-len(".qkv")], name)] = v
        else:
            out["diffusion_model.%s.%s" % (module, name)] = v
    for (attention, name), v in fused.items():
        targets = ["diffusion_model.%s.to_%s.%s" % (attention, x, name) for x in "qkv"]
        if any(t in out for t in targets):
            continue
        if name == "lora_B.weight":
            n = v.shape[0] // 3
            for i, t in enumerate(targets):
                out[t] = v[i * n:(i + 1) * n]
        else:
            for t in targets:
                out[t] = v
    return out


# ---------------------------------------------------------------- AuraFlow

# AuraFlow / Pony V7 LoRAs made for ComfyUI name the original layers (dotted, or kohya's underscores); diffusers' reader
# takes only its own names with peft factors. The map is diffusers' own for the single file (convert_auraflow_...)
_AURA_DOUBLE = {"attn.w2q": "attn.to_q", "attn.w2k": "attn.to_k", "attn.w2v": "attn.to_v", "attn.w2o": "attn.to_out.0",
                "attn.w1q": "attn.add_q_proj", "attn.w1k": "attn.add_k_proj", "attn.w1v": "attn.add_v_proj",
                "attn.w1o": "attn.to_add_out", "mlpX.c_fc1": "ff.linear_1", "mlpX.c_fc2": "ff.linear_2",
                "mlpX.c_proj": "ff.out_projection", "mlpC.c_fc1": "ff_context.linear_1",
                "mlpC.c_fc2": "ff_context.linear_2", "mlpC.c_proj": "ff_context.out_projection",
                "modX.1": "norm1.linear", "modC.1": "norm1_context.linear"}
_AURA_SINGLE = {"attn.w1q": "attn.to_q", "attn.w1k": "attn.to_k", "attn.w1v": "attn.to_v", "attn.w1o": "attn.to_out.0",
                "mlp.c_fc1": "ff.linear_1", "mlp.c_fc2": "ff.linear_2", "mlp.c_proj": "ff.out_projection",
                "modCX.1": "norm1.linear"}
# kohya writes "_" for every "." (and "c_fc1" keeps its own): compared with both as "."
_AURA_LAYERS = {kind: {k.replace("_", ".").lower(): v for k, v in m.items()}
                for kind, m in (("double", _AURA_DOUBLE), ("single", _AURA_SINGLE))}
_AURA_KEY = re.compile(r"^(?:lora_unet_|lora_transformer_|(?:model[._])?diffusion_model[._])?(double|single)_layers[._](\d+)"
                       r"[._](.+?)\.(lora_down\.weight|lora_up\.weight|lora_A\.weight|lora_B\.weight|alpha)$")


def auraflow_needs(keys):
    return any(_AURA_KEY.match(k) for k in keys)


def auraflow_to_diffusers(sd):
    """An AuraFlow LoRA in diffusers' names with peft factors ("transformer.<layer>.lora_A.weight", ".lora_B.weight"),
    alpha / rank folded into the up factor (this reader takes no alphas). Layers it does not map are left out."""
    layers = {}
    for k, v in sd.items():
        m = _AURA_KEY.match(k)
        if m:
            layers.setdefault((m[1], m[2], m[3].replace("_", ".").lower()), {})[m[4]] = v
    out = {}
    for (kind, i, layer), f in layers.items():
        target = _AURA_LAYERS[kind].get(layer)
        down = f.get("lora_down.weight", f.get("lora_A.weight"))
        up = f.get("lora_up.weight", f.get("lora_B.weight"))
        if target is None or down is None or up is None:
            continue
        if "alpha" in f:
            up = up * (float(f["alpha"]) / down.shape[0])
        name = "transformer.%s_transformer_blocks.%s.%s" % ("joint" if kind == "double" else "single", i, target)
        out[name + ".lora_A.weight"], out[name + ".lora_B.weight"] = down, up
    return out


def _peft_dump(sd, component):
    """peft's own dump: ".default." taken out, "base_model.model." too, and the component prefix put in front
    of keys that have none."""
    out = {}
    for k, v in sd.items():
        k = k.replace(".default.", ".")
        if k.startswith("base_model.model."):
            k = k[len("base_model.model."):]
        if component and not k.startswith(_COMPONENT_PREFIXES):
            k = component + "." + k
        out[k] = v
    return out


_OLD_FACTORS = (".lora.down.weight", ".lora.up.weight")


def _peft_factor(key):
    """diffusers' older factor names (".lora.down/up") as peft's (".lora_A/B")."""
    if key.endswith(".lora.down.weight"):
        return key[:-len(".lora.down.weight")] + ".lora_A.weight"
    if key.endswith(".lora.up.weight"):
        return key[:-len(".lora.up.weight")] + ".lora_B.weight"
    return key


def _kohya_unet(sd):
    """SD / SDXL: every UNet key in kohya's "lora_unet_" names (diffusers converts kohya files only as a whole)."""
    out = {}
    for k, v in sd.items():
        for p in ("lora_transformer_", "diffusion_model_"):
            if k.startswith(p):
                k = "lora_unet_" + k[len(p):]
                break
        out[k] = v
    return out


def _kind(pipe):
    name = type(pipe).__name__
    if name.startswith("Chroma"):
        return "chroma"
    if name.startswith("Flux2"):
        return "flux2"
    if name.startswith("Flux"):
        return "flux1"
    if name.startswith("QwenImage21"):
        return "qwen_image21"
    if name.startswith("ZImage"):
        return "z_image"
    if name.startswith("AuraFlow"):
        return "auraflow"
    if name.startswith("StableDiffusion") and not name.startswith("StableDiffusion3"):
        return "unet"
    return "other"


def _needs(kind, keys):
    """Which conversions a file in these key names needs for that kind of pipeline."""
    steps = []
    if kind == "z_image":
        # one conversion for every naming (diffusers' own reader of 0.40 drops kohya's fused qkv layers)
        return ["zimage"] if z_image_needs(keys) else []
    if kind == "auraflow" and auraflow_needs(keys):
        return ["auraflow"]
    if kind == "flux2" and any(k.startswith("base_model.model.") for k in keys) and not any(".default." in k for k in keys):
        return []  # diffusers' FLUX.2 reader takes peft's prefix itself (as ComfyUI's "diffusion_model.", any naming)
    if any(k.endswith(_OLD_FACTORS) for k in keys) and any(".lora_A." in k for k in keys):
        steps.append("one_naming")
    if any(".default." in k or k.startswith("base_model.model.") for k in keys):
        steps.append("peft")
    elif kind not in ("unet",) and keys and not any(k.startswith(_COMPONENT_PREFIXES) for k in keys):
        steps.append("peft")  # diffusers names without the component prefix
    if kind in ("flux1", "chroma") and any("distilled_guidance_layer" in k or (_BFL_PEFT.match(k) and ".lora_" in k)
                                           for k in keys):
        steps.append("bfl")
    if kind == "qwen_image21" and any(_GATE_UP.match(k) for k in keys):
        steps.append("gate_up")
    if kind == "unet" and any(k.startswith(("lora_transformer_", "diffusion_model_")) for k in keys):
        steps.append("kohya_unet")
    return steps


def convert(pipe, sd):
    """The state dict in a naming the pipeline's reader takes (see the module's docstring)."""
    kind = _kind(pipe)
    steps = _needs(kind, list(sd))
    if "zimage" in steps:
        return z_image_to_diffusers(sd)
    if "auraflow" in steps:
        return auraflow_to_diffusers(sd)
    if "one_naming" in steps:
        sd = {_peft_factor(k): v for k, v in sd.items()}
    if "peft" in steps:
        sd = _peft_dump(sd, "unet" if kind == "unet" else "transformer")
    if "bfl" in steps:
        sd = bfl_lora_to_kohya(sd)
    if "gate_up" in steps:
        sd = split_gate_up(sd)
    if "kohya_unet" in steps:
        sd = _kohya_unet(sd)
    return sd


def prepare(pipe, source, name="This LoRA"):
    """A LoRA file (path) or state dict as the pipeline's reader takes it: refused when it is LoKr / LoHa,
    converted when it needs it (then a state dict), else as it was."""
    if isinstance(source, str):
        if not (source.lower().endswith(".safetensors") and os.path.isfile(source)):
            return source  # the reader says what is wrong with it
        keys = list(registry.read_safetensors_header(source))
        check_format(keys, name)
        if not _needs(_kind(pipe), keys):
            return source
        from safetensors.torch import load_file
        source = load_file(source)
    else:
        check_format(source, name)
    return convert(pipe, source) if _needs(_kind(pipe), list(source)) else source


# ------------------------------------------------------------------ Fibo 2.0: diffusers' layout <-> ComfyUI's fused files

_FIBO_PREFIXES = ("base_model.model.", "transformer.", "diffusion_model.")
_FIBO_FACTOR = re.compile(r"\.(lora_A|lora_B|lora_down|lora_up)(\.default)?\.weight$|\.alpha$")
# diffusers' layer -> (ComfyUI's fused layer, its place in it, parts of the fusion); the feed-forward's hidden width is
# padded to a multiple of 256 in the fused files
_FIBO_FUSED = {"attention.to_q": ("attention.qkv", 0, 3), "attention.to_k": ("attention.qkv", 1, 3),
               "attention.to_v": ("attention.qkv", 2, 3), "feed_forward.w1": ("feed_forward.w13", 0, 2),
               "feed_forward.w3": ("feed_forward.w13", 1, 2), "ffn.w1": ("ffn.w13", 0, 2), "ffn.w3": ("ffn.w13", 1, 2),
               "cross_attention.to_k": ("cross_attention.to_kv", 0, 2), "cross_attention.to_v": ("cross_attention.to_kv", 1, 2),
               "self_attention.to_k": ("self_attention.to_kv", 0, 2), "self_attention.to_v": ("self_attention.to_kv", 1, 2)}
# diffusers' output projections -> ComfyUI's (mflux names the cross and perceiver ones to_out.0 as diffusers does)
_FIBO_RENAMED = {"attention.to_out.0": "attention.out", "cross_attention.to_out.0": "cross_attention.to_out",
                 "self_attention.to_out.0": "self_attention.to_out"}
_FIBO_PAD = 256


def _fibo_layers(sd):
    """{layer (without prefix): {"A": down, "B": up, "alpha": alpha or None}} of a Fibo 2.0 LoRA, and the prefix seen."""
    layers, prefix = {}, ""
    for k, v in sd.items():
        m = _FIBO_FACTOR.search(k)
        if not m:
            continue
        name = k[:m.start()]
        for p in _FIBO_PREFIXES:
            if name.startswith(p):
                name, prefix = name[len(p):], p
                break
        d = layers.setdefault(name, {"A": None, "B": None, "alpha": None})
        kind = m.group(1) or "alpha"
        d["A" if kind in ("lora_A", "lora_down") else "B" if kind in ("lora_B", "lora_up") else "alpha"] = v
    return layers, prefix


def _match(name, table):
    """The entry of table (layer tails) the layer name ends with, or None."""
    return next((k for k in sorted(table, key=len, reverse=True) if name == k or name.endswith("." + k)), None)


def _padded(width):
    return -(-width // _FIBO_PAD) * _FIBO_PAD


def fibo2_needs_comfy(keys):
    """Whether a Fibo 2.0 LoRA is in diffusers' layout (separate q / k / v, w1 / w3), which ComfyUI's fused files skip."""
    return any(any(k.endswith("." + d + s) for d in _FIBO_FUSED for s in (".lora_A.weight", ".lora_down.weight")) for k in keys)


def fibo2_needs_diffusers(keys):
    """Whether a Fibo 2.0 LoRA is in ComfyUI's fused layout, which mflux does not map."""
    fused = {f for f, _, _ in _FIBO_FUSED.values()} | set(_FIBO_RENAMED.values())
    return any(any(k.endswith("." + f + s) for f in fused for s in (".lora_A.weight", ".lora_down.weight")) for k in keys)


def fibo2_to_comfy(sd):
    """Diffusers' layout fused for ComfyUI's files: the parts of a fused layer stacked along the rank (their down
    factors one under the other, the up factors block-diagonal, the feed-forward rows padded as in the files), the
    alpha times the parts so the scale alpha / rank stays. Keys as ComfyUI reads them (diffusion_model.…)."""
    import torch
    layers, _ = _fibo_layers(sd)
    out, groups = {}, {}
    for name, d in layers.items():
        tail = _match(name, _FIBO_FUSED)
        renamed = _match(name, _FIBO_RENAMED)
        if tail:
            fused, place, parts = _FIBO_FUSED[tail]
            groups.setdefault(name[:-len(tail)] + fused, [None] * parts)[place] = d
        elif renamed:
            out[name[:-len(renamed)] + _FIBO_RENAMED[renamed]] = d
        else:
            out[name] = d
    for key, parts in groups.items():
        if any(p is None for p in parts):
            raise UnsupportedLoraFormat("The LoRA lacks a part of %s" % key)
        pad = _padded(parts[0]["B"].shape[0]) if key.endswith(("w13",)) else parts[0]["B"].shape[0]
        A = torch.cat([p["A"] for p in parts], 0)
        rank = sum(p["A"].shape[0] for p in parts)
        B = torch.zeros(pad * len(parts), rank, dtype=parts[0]["B"].dtype)
        r0 = 0
        for i, p in enumerate(parts):
            B[i * pad:i * pad + p["B"].shape[0], r0:r0 + p["A"].shape[0]] = p["B"]
            r0 += p["A"].shape[0]
        alpha = parts[0]["alpha"]
        out[key] = {"A": A, "B": B, "alpha": None if alpha is None else alpha * len(parts)}
    for name, d in list(out.items()):
        if name.endswith("feed_forward.w2") or name.endswith("ffn.w2"):  # its input is the padded hidden width
            A = d["A"]
            pad = _padded(A.shape[1])
            if pad != A.shape[1]:
                d["A"] = torch.cat([A, torch.zeros(A.shape[0], pad - A.shape[1], dtype=A.dtype)], 1)
    result = {}
    for name, d in out.items():
        result["diffusion_model.%s.lora_A.weight" % name] = d["A"]
        result["diffusion_model.%s.lora_B.weight" % name] = d["B"]
        if d["alpha"] is not None:
            result["diffusion_model.%s.alpha" % name] = d["alpha"]
    return result


def fibo2_to_diffusers(sd):
    """ComfyUI's fused layout split into diffusers' (as mflux maps it): every part keeps the whole down factor and its
    rows of the up factor, the feed-forward padding cut off. Keys with the transformer. prefix."""
    layers, _ = _fibo_layers(sd)
    split = {}
    for tail, (fused, place, parts) in _FIBO_FUSED.items():
        split.setdefault(fused, []).append((place, parts, tail))
    out = {}
    inv = {v: k for k, v in _FIBO_RENAMED.items()}
    for name, d in layers.items():
        tail = _match(name, split)
        renamed = _match(name, inv)
        if tail:
            rows = d["B"].shape[0] // split[tail][0][1]
            for place, parts, part in split[tail]:
                B = d["B"][place * rows:(place + 1) * rows]
                if tail.endswith("w13"):  # the padding rows carry nothing
                    B = B[:_unpadded(B)]
                out[name[:-len(tail)] + part] = {"A": d["A"], "B": B, "alpha": d["alpha"]}
        elif renamed:
            out[name[:-len(renamed)] + inv[renamed]] = d
        elif name.endswith(("feed_forward.w2", "ffn.w2")) and d["A"].shape[1] % _FIBO_PAD == 0:
            out[name] = {"A": d["A"][:, :_unpadded_cols(d["A"])], "B": d["B"], "alpha": d["alpha"]}
        else:
            out[name] = d
    result = {}
    for name, d in out.items():
        result["transformer.%s.lora_A.weight" % name] = d["A"]
        result["transformer.%s.lora_B.weight" % name] = d["B"]
        if d["alpha"] is not None:
            result["transformer.%s.alpha" % name] = d["alpha"]
    return result


def _unpadded(B):
    """Rows of an up factor before the zero padding (the fused files pad the hidden width to a multiple of 256)."""
    n = B.shape[0]
    while n > 0 and not _any(B[n - 1]):
        n -= 1
    return n


def _unpadded_cols(A):
    n = A.shape[1]
    while n > 0 and not _any(A[:, n - 1]):
        n -= 1
    return n


def _any(t):
    """Whether a row holds anything (torch and mlx tensors alike)."""
    try:
        return bool(t.abs().max() > 0)
    except AttributeError:
        import mlx.core as mx
        return bool(mx.abs(t).max() > 0)
