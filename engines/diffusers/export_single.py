# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
#
# The key maps follow diffusers' scripts convert_diffusers_to_original_stable_diffusion.py and
# convert_diffusers_to_original_sdxl.py, Copyright The HuggingFace Team, Apache License 2.0.
"""A model in diffusers' folder layout (a baked model, an imported repository) written as one .safetensors file in the
original layout of Stable Diffusion 1.x and SDXL, which other apps (ComfyUI, Automatic1111, Forge) load as a
checkpoint: UNet, VAE and text encoders, 16 bit.

    python main.py export_single <model folder> <out.safetensors>
prints __progress__ lines and one __exported__ {"file": …, "gb": …} or __error__ {"error": …}.
"""
import json
import os
import re
import sys

import compat

def _unet_layer_map(sdxl):
    """(original prefix, diffusers prefix) pairs of the UNet's blocks."""
    out = []
    blocks = 3 if sdxl else 4
    for i in range(blocks):
        for j in range(2):
            out.append((f"input_blocks.{3 * i + j + 1}.0.", f"down_blocks.{i}.resnets.{j}."))
            if (i > 0) if sdxl else (i < 3):
                out.append((f"input_blocks.{3 * i + j + 1}.1.", f"down_blocks.{i}.attentions.{j}."))
        for j in range(4 if sdxl else 3):
            out.append((f"output_blocks.{3 * i + j}.0.", f"up_blocks.{i}.resnets.{j}."))
            if (i < 2) if sdxl else (i > 0):
                out.append((f"output_blocks.{3 * i + j}.1.", f"up_blocks.{i}.attentions.{j}."))
        if i < 3:
            out.append((f"input_blocks.{3 * (i + 1)}.0.op.", f"down_blocks.{i}.downsamplers.0.conv."))
            out.append((f"output_blocks.{3 * i + 2}.{1 if i == 0 else 2}.", f"up_blocks.{i}.upsamplers.0."))
    if sdxl:
        out.append(("output_blocks.2.2.conv.", "output_blocks.2.1.conv."))
    out.append(("middle_block.1.", "mid_block.attentions.0."))
    for j in range(2):
        out.append((f"middle_block.{2 * j}.", f"mid_block.resnets.{j}."))
    return out


UNET_MAP = [
    ("time_embed.0.weight", "time_embedding.linear_1.weight"), ("time_embed.0.bias", "time_embedding.linear_1.bias"),
    ("time_embed.2.weight", "time_embedding.linear_2.weight"), ("time_embed.2.bias", "time_embedding.linear_2.bias"),
    ("input_blocks.0.0.weight", "conv_in.weight"), ("input_blocks.0.0.bias", "conv_in.bias"),
    ("out.0.weight", "conv_norm_out.weight"), ("out.0.bias", "conv_norm_out.bias"),
    ("out.2.weight", "conv_out.weight"), ("out.2.bias", "conv_out.bias"),
    ("label_emb.0.0.weight", "add_embedding.linear_1.weight"), ("label_emb.0.0.bias", "add_embedding.linear_1.bias"),
    ("label_emb.0.2.weight", "add_embedding.linear_2.weight"), ("label_emb.0.2.bias", "add_embedding.linear_2.bias"),
]
UNET_RESNET_MAP = [("in_layers.0", "norm1"), ("in_layers.2", "conv1"), ("out_layers.0", "norm2"),
                   ("out_layers.3", "conv2"), ("emb_layers.1", "time_emb_proj"), ("skip_connection", "conv_shortcut")]


def convert_unet(sd, sdxl):
    mapping = {k: k for k in sd}
    for orig, hf in UNET_MAP:
        if hf in mapping:
            mapping[hf] = orig
    for k, v in mapping.items():
        if "resnets" in k:
            for orig, hf in UNET_RESNET_MAP:
                v = v.replace(hf, orig)
            mapping[k] = v
    layers = _unet_layer_map(sdxl)
    for k, v in mapping.items():
        for orig, hf in layers:
            v = v.replace(hf, orig)
        mapping[k] = v
    return {"model.diffusion_model." + new: sd[old] for old, new in mapping.items()}


def _vae_map():
    out = [("nin_shortcut", "conv_shortcut"), ("norm_out", "conv_norm_out"), ("mid.attn_1.", "mid_block.attentions.0.")]
    for i in range(4):
        for j in range(2):
            out.append((f"encoder.down.{i}.block.{j}.", f"encoder.down_blocks.{i}.resnets.{j}."))
        if i < 3:
            out.append((f"down.{i}.downsample.", f"down_blocks.{i}.downsamplers.0."))
            out.append((f"up.{3 - i}.upsample.", f"up_blocks.{i}.upsamplers.0."))
        for j in range(3):
            out.append((f"decoder.up.{3 - i}.block.{j}.", f"decoder.up_blocks.{i}.resnets.{j}."))
    for i in range(2):
        out.append((f"mid.block_{i + 1}.", f"mid_block.resnets.{i}."))
    return out


VAE_ATTN_MAP = [("norm.", "group_norm."), ("q.", "to_q."), ("k.", "to_k."), ("v.", "to_v."), ("proj_out.", "to_out.0."),
                # older diffusers names
                ("q.", "query."), ("k.", "key."), ("v.", "value."), ("proj_out.", "proj_attn.")]


def convert_vae(sd):
    vae_map = _vae_map()
    mapping = {}
    for k in sd:
        v = k
        for orig, hf in vae_map:
            v = v.replace(hf, orig)
        if "attentions" in k:
            for orig, hf in VAE_ATTN_MAP:
                v = v.replace(hf, orig)
        mapping[k] = v
    out = {}
    for old, new in mapping.items():
        t = sd[old]
        if re.search(r"mid\.attn_1\.(q|k|v|proj_out)\.weight$", new) and t.ndim == 2:
            t = t.reshape(*t.shape, 1, 1)  # linear in diffusers, 1×1 conv in the original
        out["first_stage_model." + new] = t
    return out


OPENCLIP_MAP = [("transformer.resblocks.", "text_model.encoder.layers."), ("ln_1", "layer_norm1"), ("ln_2", "layer_norm2"),
                (".c_fc.", ".fc1."), (".c_proj.", ".fc2."), (".attn", ".self_attn"), ("ln_final.", "text_model.final_layer_norm."),
                ("token_embedding.weight", "text_model.embeddings.token_embedding.weight"),
                ("positional_embedding", "text_model.embeddings.position_embedding.weight")]


def convert_openclip(sd):
    """SDXL's second text encoder (CLIPTextModelWithProjection) in OpenCLIP's layout: q, k, v joined."""
    import torch
    protected = {re.escape(hf): orig for orig, hf in OPENCLIP_MAP}
    pattern = re.compile("|".join(protected.keys()))
    rename = lambda k: pattern.sub(lambda m: protected[re.escape(m.group(0))], k)  # noqa: E731
    out, qkv_w, qkv_b = {}, {}, {}
    for k, v in sd.items():
        m = re.match(r"(.*)\.self_attn\.([qkv])_proj\.(weight|bias)$", k)
        if m:
            (qkv_w if m.group(3) == "weight" else qkv_b).setdefault(m.group(1) + ".self_attn", {})[m.group(2)] = v
            continue
        out[rename(k)] = v
    for store, suffix in ((qkv_w, ".in_proj_weight"), (qkv_b, ".in_proj_bias")):
        for pre, parts in store.items():
            if set(parts) != {"q", "k", "v"}:
                raise ValueError("The second text encoder misses q, k or v of %s" % pre)
            out[rename(pre) + suffix] = torch.cat([parts["q"], parts["k"], parts["v"]])
    if "text_projection.weight" in out:
        out["text_projection"] = out.pop("text_projection.weight").T.contiguous()
    return {"conditioner.embedders.1.model." + k: v for k, v in out.items()}


def clip_keys(sd):
    """A CLIP text encoder's keys with "text_model." in front, as the original layout has them: transformers 5 saves
    CLIPTextModel without it (CLIPTextModelWithProjection keeps it)."""
    if any(k.startswith("text_model.") for k in sd):
        return sd
    return {(k if k.startswith("text_projection") else "text_model." + k): v for k, v in sd.items()}


def _load(folder):
    """The tensors of one component folder (safetensors or .bin, also sharded)."""
    import torch
    from safetensors.torch import load_file
    files = sorted(f for f in os.listdir(folder) if not f.startswith("._"))
    st = [f for f in files if f.endswith(".safetensors")]
    out = {}
    if st:
        for f in st:
            out.update(load_file(os.path.join(folder, f), device="cpu"))
        return out
    for f in (x for x in files if x.endswith(".bin")):
        compat.refuse_pickle(f)
        out.update(torch.load(os.path.join(folder, f), map_location="cpu", weights_only=True))
    if not out:
        raise ValueError("No weights in %s" % folder)
    return out


def export(model_folder, out_path, report=None):
    """Writes the model (diffusers layout) as one original-layout .safetensors file. Returns its size in GB."""
    from safetensors.torch import save_file
    with open(os.path.join(model_folder, "model.json")) as f:
        m = json.load(f)
    arch = m.get("arch", "")
    if m.get("family") not in ("sd1", "sdxl") or m.get("layout") not in ("repo", "folder"):
        raise ValueError("Only Stable Diffusion 1.x and SDXL models in folder layout can be exported as one file "
                         "(this one is %s, %s)." % (m.get("label", arch), m.get("layout")))
    sdxl = m["family"] == "sdxl"
    weights = os.path.join(model_folder, m.get("weights_dir") or m.get("base_dir") or "weights")
    say = report or (lambda *_: None)
    say("Reading the UNet", 10)
    state = convert_unet(_load(os.path.join(weights, "unet")), sdxl)
    say("Reading the VAE", 40)
    state.update(convert_vae(_load(os.path.join(weights, "vae"))))
    say("Reading the text encoders", 55)
    te = clip_keys(_load(os.path.join(weights, "text_encoder")))
    prefix = "conditioner.embedders.0.transformer." if sdxl else "cond_stage_model.transformer."
    state.update({prefix + k: v for k, v in te.items()})
    if sdxl:
        state.update(convert_openclip(clip_keys(_load(os.path.join(weights, "text_encoder_2")))))
    state = {k: (v.half() if v.is_floating_point() else v).contiguous() for k, v in state.items()}
    say("Writing the file", 80)
    tmp = out_path + ".part"
    try:
        save_file(state, tmp, metadata={"format": "pt", "exported_by": "VulKara", "base": m.get("label", "")})
        os.replace(tmp, out_path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return os.path.getsize(out_path) / 1e9


def main(argv):
    def report(stage, pct):
        print("__progress__ " + json.dumps({"stage": stage, "progress": pct}), flush=True)

    try:
        gb = export(argv[0], argv[1], report)
        print("__exported__ " + json.dumps({"file": argv[1], "gb": round(gb, 2)}), flush=True)
        return 0
    except Exception as e:
        print("__error__ " + json.dumps({"error": str(e)}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
