# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""LoRA files in namings diffusers' readers do not take (lora_convert.py): converted before loading, so that their
layers land on the model's. Checked with the headers of real LoRAs (tests/fixtures/lora_headers.json.gz, shapes only):
diffusers' own reader reads the converted dict, and each layer it names must exist in the model (built on the meta
device from the real config, no weights) with the LoRA's input width."""
import gzip
import json
import os

import pytest
import torch

import diffusers
import engine
import lora_convert

with gzip.open(os.path.join(os.path.dirname(__file__), "fixtures", "lora_headers.json.gz"), "rt") as f:
    LORAS = json.load(f)

FLUX1 = {"attention_head_dim": 128, "guidance_embeds": True, "in_channels": 64, "joint_attention_dim": 4096,
         "num_attention_heads": 24, "num_layers": 19, "num_single_layers": 38, "patch_size": 1, "pooled_projection_dim": 768}
KLEIN9 = {"attention_head_dim": 128, "axes_dims_rope": [32, 32, 32, 32], "eps": 1e-06, "guidance_embeds": False,
          "in_channels": 128, "joint_attention_dim": 12288, "mlp_ratio": 3.0, "num_attention_heads": 32, "num_layers": 8,
          "num_single_layers": 24, "out_channels": None, "patch_size": 1, "rope_theta": 2000, "timestep_guidance_channels": 256}
KLEIN4 = dict(KLEIN9, joint_attention_dim=7680, num_attention_heads=24, num_layers=5, num_single_layers=20)
QWEN21 = {"attention_head_dim": 128, "axes_dims_rope": [16, 56, 56], "context_in_dim": 4096, "in_channels": 64,
          "num_attention_heads": 32, "num_layers": 32, "out_channels": 64, "patch_size": 1, "mlp_ratio": 3, "eps": 1e-06,
          "causal_condition": True}
SDXL = {"addition_embed_type": "text_time", "addition_time_embed_dim": 256, "attention_head_dim": [5, 10, 20],
        "block_out_channels": [320, 640, 1280], "cross_attention_dim": 2048,
        "down_block_types": ["DownBlock2D", "CrossAttnDownBlock2D", "CrossAttnDownBlock2D"], "in_channels": 4,
        "layers_per_block": 2, "out_channels": 4, "projection_class_embeddings_input_dim": 2816, "sample_size": 128,
        "transformer_layers_per_block": [1, 2, 10], "up_block_types": ["CrossAttnUpBlock2D", "CrossAttnUpBlock2D", "UpBlock2D"],
        "use_linear_projection": True}

# pipeline -> (its denoiser's class, config, component)
TARGETS = {
    "FluxPipeline": ("FluxTransformer2DModel", FLUX1, "transformer"),
    "Flux2KleinPipeline": ("Flux2Transformer2DModel", KLEIN9, "transformer"),
    "Flux2KleinPipeline/4B": ("Flux2Transformer2DModel", KLEIN4, "transformer"),
    "QwenImage21Pipeline": ("QwenImage21Transformer2DModel", QWEN21, "transformer"),
    "StableDiffusionXLPipeline": ("UNet2DConditionModel", SDXL, "unet"),
}
_models = {}


def stand_in(pipeline):
    """Only the class name matters to lora_convert ("/4B" names the model size only the tests need)."""
    return type(pipeline.split("/")[0], (), {})()


def tensors(name):
    """The fixture's LoRA as zeros, rank 1 (the smaller side of each matrix: the rank does not matter here)."""
    out = {}
    for k, s in LORAS[name]["shapes"].items():
        if k.endswith(".alpha") or not s:
            out[k] = torch.tensor(1.0)
        elif len(s) >= 2:
            small = s.index(min(s[:2]))
            out[k] = torch.zeros(*[1 if i == small else d for i, d in enumerate(s)], dtype=torch.float16)
        else:
            out[k] = torch.zeros(*s, dtype=torch.float16)
    return out


def coverage(pipeline, sd):
    """(share of the layers diffusers' reader names that exist with the LoRA's input width, number of layers)."""
    cls, config, comp = TARGETS[pipeline]
    pipeline = pipeline.split("/")[0]
    if not hasattr(diffusers, cls) or not hasattr(diffusers, pipeline):
        pytest.skip("this diffusers has no %s" % cls)
    if id(config) not in _models:
        with torch.device("meta"):
            _models[id(config)] = getattr(diffusers, cls).from_config(config)
    model = _models[id(config)]
    kw = {"unet_config": model.config} if comp == "unet" else {}
    res = getattr(diffusers, pipeline).lora_state_dict(dict(sd), **kw)
    out = res[0] if isinstance(res, tuple) else res
    mods = dict(model.named_modules())
    layers = [(k[len(comp) + 1:].replace(".lora.down.weight", ".lora_A.weight")[:-len(".lora_A.weight")], v)
              for k, v in out.items() if k.startswith(comp + ".") and k.endswith((".lora_A.weight", ".lora.down.weight"))]
    ok = sum(1 for n, v in layers if n in mods and getattr(mods[n], "weight", None) is not None
             and mods[n].weight.shape[1] == v.shape[1])
    return (ok / len(layers) if layers else 0.0), len(layers)


# fixture, pipeline, layers diffusers reads after the conversion (all of them land on the model)
CASES = [
    ("chroma_aitoolkit_comfy", "FluxPipeline", 418),     # FLUX.1 names of ComfyUI / ai-toolkit (BFL, peft factors)
    ("klein9_peft_dump", "Flux2KleinPipeline", 140),     # peft dump: ".default.", no prefix
    ("qwen21_aitoolkit", "QwenImage21Pipeline", 224),    # fused img_mlp.gate_up split in two
    ("sdxl_aitoolkit_lora_transformer", "StableDiffusionXLPipeline", 162),  # ai-toolkit's lora_transformer_
    ("sdxl_dora_mixed_prefixes", "StableDiffusionXLPipeline", 66),          # lora_unet_ and diffusion_model_ mixed
]


@pytest.mark.parametrize("name, pipeline, layers", CASES)
def test_converted_loras_land_on_the_model(name, pipeline, layers):
    sd = tensors(name)
    pipe = stand_in(pipeline)
    assert lora_convert._needs(lora_convert._kind(pipe), list(sd))  # this file is one of the converted kinds
    assert coverage(pipeline, lora_convert.convert(pipe, sd)) == (1.0, layers)
    before, _ = coverage(pipeline, sd)
    assert before < engine.LoadedModel.MIN_APPLIED  # without the conversion it did not fit (0 % or 83 %)


@pytest.mark.parametrize("name, pipeline", [("flux1_kohya_meta", "FluxPipeline"), ("flux1_aitoolkit_meta", "FluxPipeline"),
                                            ("klein9_aitoolkit", "Flux2KleinPipeline"), ("sdxl_kohya_te", "StableDiffusionXLPipeline"),
                                            ("klein4_peft_bfl", "Flux2KleinPipeline/4B"),  # fal's outpaint LoRA
                                            ("illustrious_stabilizer_diffusers_names", "StableDiffusionXLPipeline")])
def test_files_diffusers_reads_as_they_are_stay_as_they_are(name, pipeline):
    sd = tensors(name)
    assert not lora_convert._needs(lora_convert._kind(stand_in(pipeline)), list(sd))
    assert lora_convert.prepare(stand_in(pipeline), sd) is sd
    assert coverage(pipeline, sd)[0] == 1.0


def test_a_file_mixing_both_factor_namings_gets_one():
    """lrzjason's FLUX.2 [klein] consistency LoRAs name 32 of 144 layers ".lora.down/up", the rest ".lora_A/B":
    diffusers' reader keeps both, peft then loads only the lora_A/B layers (112 of 144 in the app, refused)."""
    sd = tensors("klein9_lcs_mixed_factor_names")
    pipe = stand_in("Flux2KleinPipeline")
    assert sum(k.endswith(".lora.down.weight") for k in sd) == 32
    out = lora_convert.convert(pipe, sd)
    assert not [k for k in out if ".lora.down." in k or ".lora.up." in k]
    assert sum(k.endswith(".lora_A.weight") for k in out) == 144
    assert coverage("Flux2KleinPipeline", out) == (1.0, 144)


def test_qwen_image_21_gate_up_is_split_gate_rows_first():
    """ComfyUI fuses the SwiGLU gate and up projections, gate rows first; diffusers 0.41 names them
    img_mlp.gate_layer and img_mlp.proj (12288 x 4096 each)."""
    b = torch.arange(24.0).reshape(24, 1)
    a = torch.ones(1, 8)
    sd = {"diffusion_model.transformer_blocks.0.img_mlp.gate_up.lora_A.weight": a,
          "diffusion_model.transformer_blocks.0.img_mlp.gate_up.lora_B.weight": b,
          "diffusion_model.transformer_blocks.0.attn.to_q.lora_A.weight": a,
          "lora_unet_transformer_blocks_1_img_mlp_gate_up.lora_up.weight": b,
          "lora_unet_transformer_blocks_1_img_mlp_gate_up.alpha": torch.tensor(8.0)}
    out = lora_convert.split_gate_up(sd)
    gate = out["diffusion_model.transformer_blocks.0.img_mlp.gate_layer.lora_B.weight"]
    proj = out["diffusion_model.transformer_blocks.0.img_mlp.proj.lora_B.weight"]
    assert gate.flatten().tolist() == list(range(12)) and proj.flatten().tolist() == list(range(12, 24))
    assert torch.equal(out["diffusion_model.transformer_blocks.0.img_mlp.proj.lora_A.weight"], a)
    assert out["lora_unet_transformer_blocks_1_img_mlp_gate_layer.lora_up.weight"].shape == (12, 1)
    assert float(out["lora_unet_transformer_blocks_1_img_mlp_proj.alpha"]) == 8.0
    assert "diffusion_model.transformer_blocks.0.attn.to_q.lora_A.weight" in out
    assert not [k for k in out if "gate_up" in k]


def test_qwen_image_21_names_of_the_split_are_the_runtimes():
    if not hasattr(diffusers, "QwenImage21Transformer2DModel"):
        pytest.skip("this diffusers has no Qwen-Image 2.1")
    with torch.device("meta"):
        model = diffusers.QwenImage21Transformer2DModel.from_config(QWEN21)
    mlp = model.transformer_blocks[0].img_mlp
    assert tuple(mlp.gate_layer.weight.shape) == tuple(mlp.proj.weight.shape) == (12288, 4096)


def test_peft_dumps_get_their_prefix():
    a = torch.zeros(1, 4)
    sd = {"base_model.model.transformer_blocks.0.attn.to_q.lora_A.default.weight": a,
          "single_transformer_blocks.0.attn.to_out.lora_B.default.weight": a}
    out = lora_convert.convert(stand_in("Flux2KleinPipeline"), sd)
    assert set(out) == {"transformer.transformer_blocks.0.attn.to_q.lora_A.weight",
                        "transformer.single_transformer_blocks.0.attn.to_out.lora_B.weight"}


def test_auraflow_loras_for_comfyui_land_on_diffusers_layers_with_alpha_folded_in():
    down, up = torch.ones(16, 3072), torch.ones(3072, 16)
    sd = {"diffusion_model.double_layers.0.attn.w2q.lora_down.weight": down,
          "diffusion_model.double_layers.0.attn.w2q.lora_up.weight": up,
          "diffusion_model.double_layers.0.attn.w2q.alpha": torch.tensor(8.0),
          "lora_unet_single_layers_3_mlp_c_fc1.lora_down.weight": down,  # kohya's underscores
          "lora_unet_single_layers_3_mlp_c_fc1.lora_up.weight": up}
    out = lora_convert.convert(stand_in("AuraFlowPipeline"), sd)
    assert set(out) == {"transformer.joint_transformer_blocks.0.attn.to_q.lora_A.weight",
                        "transformer.joint_transformer_blocks.0.attn.to_q.lora_B.weight",
                        "transformer.single_transformer_blocks.3.ff.linear_1.lora_A.weight",
                        "transformer.single_transformer_blocks.3.ff.linear_1.lora_B.weight"}
    assert float(out["transformer.joint_transformer_blocks.0.attn.to_q.lora_B.weight"][0, 0]) == 0.5  # 8 / 16
    peft = {"transformer.joint_transformer_blocks.0.attn.to_q.lora_A.weight": down}  # SimpleTuner: as it is
    assert lora_convert.convert(stand_in("AuraFlowPipeline"), peft) == peft


@pytest.mark.parametrize("key, kind", [("lora_unet_input_blocks_4_1_proj_in.lokr_w1", "LoKr"),
                                       ("lora_unet_input_blocks_4_1_proj_in.hada_w1_a", "LoHa")])
def test_lokr_and_loha_are_refused_by_name(tmp_path, key, kind):
    from safetensors.torch import save_file
    path = str(tmp_path / "lyco.safetensors")
    save_file({key: torch.zeros(2, 2)}, path)
    with pytest.raises(lora_convert.UnsupportedLoraFormat, match="LoKr/LoHa LoRAs are not supported yet") as e:
        engine._check_lora_format({"file": path, "name": "Hands"})
    assert "The LoRA Hands is a LyCORIS %s file" % kind in str(e.value)
    with pytest.raises(lora_convert.UnsupportedLoraFormat):
        lora_convert.prepare(stand_in("StableDiffusionXLPipeline"), path)
    # the real SDXL LoKr file
    with pytest.raises(lora_convert.UnsupportedLoraFormat, match="LoKr"):
        lora_convert.check_format(LORAS["lokr_sdxl"]["shapes"], "x")


def test_a_lokr_lora_stops_before_loading():
    m = engine.LoadedModel.__new__(engine.LoadedModel)
    m.m, m.spec, m.stream, m.lora_key, m.separate_text = {"denoiser": "unet"}, {"label": "SDXL"}, False, (), False

    class Pipe:
        unloaded = False

        def unload_lora_weights(self):
            Pipe.unloaded = True

        def load_lora_weights(self, *a, **k):
            raise AssertionError("must not load")
    import tempfile
    from safetensors.torch import save_file
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "l.safetensors")
        save_file({"lora_unet_x.lokr_w1": torch.zeros(2, 2)}, path)
        m.pipe = Pipe()
        with pytest.raises(ValueError, match="The LoRA Hands is a LyCORIS LoKr file"):
            m.apply_loras([{"file": path, "scale": 1.0, "name": "Hands"}])
    assert Pipe.unloaded


class _QuantoLike(torch.nn.Module):
    """A transformer whose state dict names its weights the way quanto does (`x.weight._data`, `x.weight._scale`)."""

    def __init__(self):
        super().__init__()
        self.proj = torch.nn.Linear(8, 4)

    def state_dict(self, *args, **kwargs):
        sd = super().state_dict(*args, **kwargs)
        w = sd.pop("proj.weight")
        sd["proj.weight._data"], sd["proj.weight._scale"] = w, torch.ones(1)
        return sd


def test_quantized_weights_get_plain_names_while_a_lora_loads():
    # the FLUX/Chroma loader looks up `x.weight` and failed with a KeyError on a quantized Chroma
    t = _QuantoLike()
    with engine._plain_weight_names(t):
        assert tuple(t.state_dict()["proj.weight"].shape) == (4, 8)
    assert "proj.weight" not in t.state_dict()
    assert "state_dict" not in vars(t)
    with engine._plain_weight_names(None):
        pass


def _fibo_diffusers(rank=4, dim=16, hidden=24, alpha=True):
    """A Fibo 2.0 LoRA in diffusers' layout: one block's attention and feed-forward, random factors."""
    torch.manual_seed(1)
    sd = {}
    for name, out_w, in_w in [("attention.to_q", dim, dim), ("attention.to_k", dim, dim), ("attention.to_v", dim, dim),
                              ("attention.to_out.0", dim, dim), ("feed_forward.w1", hidden, dim), ("feed_forward.w3", hidden, dim),
                              ("feed_forward.w2", dim, hidden), ("cross_attention.to_q", dim, dim), ("cross_attention.to_k", dim, 2 * dim),
                              ("cross_attention.to_v", dim, 2 * dim), ("cross_attention.to_out.0", dim, dim)]:
        sd["transformer.layers.0.%s.lora_A.weight" % name] = torch.randn(rank, in_w)
        sd["transformer.layers.0.%s.lora_B.weight" % name] = torch.randn(out_w, rank)
        if alpha:
            sd["transformer.layers.0.%s.alpha" % name] = torch.tensor(float(rank))
    return sd


def _delta(sd, prefix, name):
    A, B = sd["%s.%s.lora_A.weight" % (prefix, name)], sd["%s.%s.lora_B.weight" % (prefix, name)]
    scale = sd.get("%s.%s.alpha" % (prefix, name))
    scale = float(scale) / A.shape[0] if scale is not None else 1.0
    return B @ A * scale


def test_fibo2_diffusers_layout_is_fused_for_comfyui_and_split_back():
    sd = _fibo_diffusers()
    assert lora_convert.fibo2_needs_comfy(sd) and not lora_convert.fibo2_needs_diffusers(sd)
    fused = lora_convert.fibo2_to_comfy(sd)
    assert lora_convert.fibo2_needs_diffusers(fused) and not lora_convert.fibo2_needs_comfy(fused)
    qkv, w13 = "diffusion_model.layers.0.attention.qkv", "diffusion_model.layers.0.feed_forward.w13"
    assert fused[qkv + ".lora_A.weight"].shape == (12, 16) and fused[qkv + ".lora_B.weight"].shape == (48, 12)
    assert fused[w13 + ".lora_B.weight"].shape == (512, 8)  # the hidden width padded to 256
    assert fused["diffusion_model.layers.0.feed_forward.w2.lora_A.weight"].shape == (4, 256)
    assert float(fused[qkv + ".alpha"]) == 12.0  # alpha / rank unchanged: 4 / 4 = 12 / 12
    # the fused layer's change is the parts' changes one under the other
    d = _delta(fused, "diffusion_model", "layers.0.attention.qkv")
    for i, part in enumerate(("to_q", "to_k", "to_v")):
        assert torch.allclose(d[i * 16:(i + 1) * 16], _delta(sd, "transformer", "layers.0.attention." + part), atol=1e-5)
    d = _delta(fused, "diffusion_model", "layers.0.feed_forward.w13")
    assert torch.allclose(d[:24], _delta(sd, "transformer", "layers.0.feed_forward.w1"), atol=1e-5)
    assert torch.allclose(d[256:280], _delta(sd, "transformer", "layers.0.feed_forward.w3"), atol=1e-5)
    assert torch.allclose(d[24:256], torch.zeros(232, 16))
    assert torch.allclose(_delta(fused, "diffusion_model", "layers.0.attention.out"), _delta(sd, "transformer", "layers.0.attention.to_out.0"))
    # the injection layers' cross attention: k and v fused, the output projection without diffusers' ".0"
    d = _delta(fused, "diffusion_model", "layers.0.cross_attention.to_kv")
    assert torch.allclose(d[16:32], _delta(sd, "transformer", "layers.0.cross_attention.to_v"), atol=1e-5)
    assert torch.allclose(_delta(fused, "diffusion_model", "layers.0.cross_attention.to_out"), _delta(sd, "transformer", "layers.0.cross_attention.to_out.0"))
    # split back for mflux: the same changes, diffusers' names, the padding gone
    back = lora_convert.fibo2_to_diffusers(fused)
    assert set(back) == set(sd)
    for name in ("attention.to_q", "attention.to_v", "attention.to_out.0", "feed_forward.w1", "feed_forward.w3", "feed_forward.w2",
                 "cross_attention.to_k", "cross_attention.to_out.0"):
        assert torch.allclose(_delta(back, "transformer", "layers.0." + name), _delta(sd, "transformer", "layers.0." + name), atol=1e-5)
    assert back["transformer.layers.0.feed_forward.w2.lora_A.weight"].shape == (4, 24)


def test_fibo2_without_alpha_keeps_the_scale_of_one():
    sd = _fibo_diffusers(alpha=False)
    fused = lora_convert.fibo2_to_comfy(sd)
    assert not any(k.endswith(".alpha") for k in fused)
    d = _delta(fused, "diffusion_model", "layers.0.attention.qkv")
    assert torch.allclose(d[16:32], _delta(sd, "transformer", "layers.0.attention.to_k"), atol=1e-5)


class _Quanto4Like(_QuantoLike):
    """quanto's 4 bit names: `x.weight._data._data`, `._scale`, `._shift`."""

    def state_dict(self, *args, **kwargs):
        sd = torch.nn.Module.state_dict(self, *args, **kwargs)
        w = sd.pop("proj.weight")
        sd["proj.weight._data._data"], sd["proj.weight._scale"], sd["proj.weight._shift"] = w, torch.ones(1), torch.zeros(1)
        return sd


def test_4_bit_quantized_weights_get_plain_names_too():
    # FLUX.1 dev kept in 4 bit on 16 GB: the Turbo-Alpha LoRA failed with KeyError 'context_embedder.weight'
    t = _Quanto4Like()
    with engine._plain_weight_names(t):
        assert tuple(t.state_dict()["proj.weight"].shape) == (4, 8)
