# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Chroma: recognising its checkpoints, the import plan, the memory plan, staged prompt encoding, its LoRAs, and
Chroma checkpoints once imported as FLUX.1 (or marked as not runnable) made runnable. No network: the fixture holds
the tensor names, dtypes and shapes of lodestones/Chroma1-HD's single-file checkpoint (its header, no weights)."""
import gzip
import json
import os

import pytest
import torch

import engine
import importer
import memory
import recheck
import registry
import samplers

HERE = os.path.dirname(__file__)
with gzip.open(os.path.join(HERE, "fixtures", "chroma1_hd_header.json.gz"), "rt") as f:
    SHAPES = {k: v[1] for k, v in json.load(f)["tensors"].items()}
with gzip.open(os.path.join(HERE, "fixtures", "lora_headers.json.gz"), "rt") as f:
    LORAS = json.load(f)

# lodestones/Chroma1-HD as Hugging Face lists it (bytes), and its model_index.json
HD_FILES = {
    "Chroma1-HD.safetensors": 17_800_038_288, "model_index.json": 600, "scheduler/scheduler_config.json": 500,
    "text_encoder/config.json": 741, "text_encoder/model-00001-of-00002.safetensors": 4_994_582_224,
    "text_encoder/model-00002-of-00002.safetensors": 4_530_066_360, "text_encoder/model.safetensors.index.json": 19_921,
    "tokenizer/added_tokens.json": 2_593, "tokenizer/special_tokens_map.json": 2_543, "tokenizer/spiece.model": 791_656,
    "tokenizer/tokenizer_config.json": 20_847, "transformer/config.json": 490,
    "transformer/diffusion_pytorch_model-00001-of-00002.safetensors": 9_946_193_392,
    "transformer/diffusion_pytorch_model-00002-of-00002.safetensors": 7_853_894_360,
    "transformer/diffusion_pytorch_model.safetensors.index.json": 106_695,
    "vae/config.json": 819, "vae/diffusion_pytorch_model.safetensors": 167_666_902,
}
HD_INDEX = dict(importer.CHROMA_MODEL_INDEX, tokenizer=["transformers", "T5Tokenizer"])
BASE_BYTES = 4_994_582_224 + 4_530_066_360 + 167_666_902


# ------------------------------------------------------------ recognising

def test_the_checkpoint_is_chroma():
    assert registry.is_chroma(SHAPES)
    arch, layout, overrides, params = registry.detect_from_single_file(SHAPES, "lodestones/Chroma1-HD/Chroma1-HD.safetensors")
    assert (arch, layout, overrides) == ("chroma", "single_denoiser", {})
    assert abs(params - 8.9) < 0.01
    # GGUF lists the dimensions the other way round; ComfyUI files carry a prefix
    gguf = {"model.diffusion_model." + k: list(reversed(v)) for k, v in SHAPES.items()}
    assert registry.detect_from_single_file(gguf, "x/gonzalomoChroma_v20.gguf")[0] == "chroma"
    # in diffusers' names
    named = {"distilled_guidance_layer.in_proj.weight": [5120, 64], "transformer_blocks.0.attn.to_q.weight": [3072, 3072],
             "single_transformer_blocks.0.attn.to_q.weight": [3072, 3072], "x_embedder.weight": [3072, 64]}
    assert registry.detect_from_single_file(named)[0] == "chroma"


def test_radiance_and_incomplete_files_are_refused():
    radiance = {k: v for k, v in SHAPES.items() if not k.startswith("img_in.")}
    radiance.update({"nerf_blocks.0.norm.scale": [64], "img_in_patch.weight": [3072, 3, 16, 16]})
    assert not registry.is_chroma(radiance)
    with pytest.raises(registry.UnsupportedModel, match="Radiance"):
        registry.detect_from_single_file(radiance, "Chroma1-Radiance.safetensors")
    with pytest.raises(registry.UnsupportedModel, match="Incomplete Chroma"):
        registry.detect_from_single_file({k: v for k, v in SHAPES.items() if not k.startswith("img_in.")})


def test_distilled_versions_run_without_guidance():
    assert registry.detect_from_single_file(SHAPES, "Chroma1-HD-Flash.safetensors")[2] == \
        {"num_steps": 12, "guidance_scale": 1.0, "negative_prompt": ""}
    assert registry.chroma_overrides("chroma-hyper-8step.safetensors")["guidance_scale"] == 1.0
    assert registry.detect_from_model_index({"_class_name": "ChromaPipeline"}, {}, "lodestones/Chroma1-HD") == ("chroma", {})
    assert registry.detect_from_model_index({"_class_name": "ChromaPipeline"}, {}, "lodestones/Chroma1-Flash")[1]["num_steps"] == 12
    with pytest.raises(registry.UnsupportedModel, match="Radiance"):
        registry.detect_from_model_index({"_class_name": "ChromaRadiancePipeline"})


def test_the_spec_follows_diffusers():
    import diffusers
    from diffusers.loaders.single_file_model import SINGLE_FILE_LOADABLE_CLASSES
    spec = registry.ARCHS["chroma"]
    for key in ("pipeline", "img2img_pipeline", "inpaint_pipeline", "denoiser_class"):
        assert hasattr(diffusers, spec[key]), spec[key]
    assert spec["denoiser_class"] in SINGLE_FILE_LOADABLE_CLASSES
    # bfloat16, computed in float16 where bfloat16 is emulated: on an M2 the same picture, 39 % faster
    assert spec["negative_prompt"] and spec["torch_dtype"] == "bfloat16" and spec.get("fp16_compute")
    assert all(r % spec["size_multiple"] == 0 for r in spec["resolutions"])
    with torch.device("meta"):
        model = diffusers.ChromaTransformer2DModel.from_config(importer.CHROMA_TRANSFORMER_CONFIG)
    assert abs(sum(p.numel() for p in model.parameters()) / 1e9 - registry._n_params(SHAPES) / 1e9) < 0.01


# ------------------------------------------------------------ import and memory

@pytest.fixture
def hub(monkeypatch):
    monkeypatch.setattr(importer, "_hf_repo_info", lambda repo, token: (None, HD_FILES))
    monkeypatch.setattr(importer, "_hf_json", lambda repo, f, token: HD_INDEX)
    monkeypatch.setattr(importer, "_params_from_hf", lambda api, repo, files: {"text_encoder": 4.76, "vae": 0.084})


def test_a_single_file_is_completed_from_chroma1_hd(tmp_path, monkeypatch, hub):
    path = tmp_path / "gonzalomoChroma_v20.safetensors"
    path.write_bytes(b"x")
    monkeypatch.setattr(registry, "read_single_file_header", lambda p: SHAPES)
    info = importer.inspect("file", str(path))
    assert (info["arch"], info["layout"], info["base_repo"]) == ("chroma", "single_denoiser", "lodestones/Chroma1-HD")
    assert set(info["components"]) == {"text_encoder", "transformer", "vae"}  # T5 only, no CLIP
    # the base repo's transformer (and its single file) are not downloaded: T5, VAE, tokenizer and configs are
    assert BASE_BYTES < info["download_bytes"] < BASE_BYTES + 1_000_000
    plan = importer.make_plan(info, ram_gb=24)
    assert plan["fits"] and plan["quant"] == {"transformer": "q8", "text_encoder": "q8"} and not plan.get("streamed")
    # 16 GB: the transformer in 4 bit in memory (before streaming 16 bit from the SSD, MEASUREMENTS 7be)
    assert importer.make_plan(info, ram_gb=16)["quant"]["transformer"] == "q4" and not importer.make_plan(info, ram_gb=16).get("streamed")
    flash = tmp_path / "Chroma1-HD-Flash.safetensors"
    flash.write_bytes(b"x")
    assert importer.inspect("file", str(flash))["base_repo"] == "lodestones/Chroma1-Flash"


def test_gguf_names_and_civitai():
    import civitai
    assert importer._guess_from_name("silveroxides/Chroma-GGUF/chroma-unlocked-v38-Q8_0.gguf")[0] == "chroma"
    with pytest.raises(registry.UnsupportedModel, match="Radiance"):
        importer._guess_from_name("x/chroma-radiance-Q8_0.gguf")
    assert civitai.arch_of("Chroma") == "chroma"


def test_the_8_bit_gguf_fits_24_gb_with_its_text_encoder_resident():
    comps = {"text_encoder": 4.76, "transformer": 8.9, "vae": 0.084}
    plan = memory.plan(comps, "transformer", "chroma", 24, denoiser_fixed_gb=9_462_431_904 / 1024 ** 3)
    assert plan["fits"] and plan["quant"] == {"transformer": "gguf", "text_encoder": "q8"}
    assert not plan["staged_text_encoder"] and plan["est_peak_gb"] == 17.5 and plan["min_ram_gb"] == 19


def test_flow_samplers_with_chroma_shift():
    assert "flow_euler" in samplers.for_family("chroma") and "flow_heun" not in samplers.for_family("chroma")
    s = samplers.make("flow_unipc", "karras", importer.chroma_scheduler_config(), "chroma")
    assert type(s).__name__ == "UniPCMultistepScheduler" and s.config.flow_shift == 3.0


# ------------------------------------------------------------ prompt encoding

class FakeChromaPipe:
    def __init__(self):
        self.calls = []

    def encode_prompt(self, prompt, negative_prompt=None, device=None, do_classifier_free_guidance=True,
                      max_sequence_length=512):
        self.calls.append((prompt, negative_prompt, do_classifier_free_guidance, max_sequence_length))
        mask = torch.ones(1, 4)
        neg = (torch.zeros(1, 4, 8), torch.zeros(4, 3), torch.ones(1, 4)) if do_classifier_free_guidance else (None,) * 3
        return (torch.ones(1, 4, 8), torch.zeros(4, 3), mask) + neg


def test_staged_encoding_with_masks_and_real_guidance():
    spec = registry.ARCHS["chroma"]
    pipe = FakeChromaPipe()
    out = engine._encode(pipe, spec, "a lighthouse", "", 4.0, "cpu")
    assert pipe.calls == [("a lighthouse", "", True, 512)]
    assert set(out) == {"prompt_embeds", "prompt_attention_mask", "negative_prompt_embeds", "negative_prompt_attention_mask"}
    pipe = FakeChromaPipe()
    out = engine._encode(pipe, spec, "a lighthouse", "fog", 1.0, "cpu")
    assert pipe.calls == [("a lighthouse", "fog", False, 512)] and set(out) == {"prompt_embeds", "prompt_attention_mask"}
    lm = engine.LoadedModel.__new__(engine.LoadedModel)
    lm.embed_cache, lm.text_pipe, lm.staged, lm.dtype = None, FakeChromaPipe(), False, torch.float16
    lm.spec, lm.device = spec, "cpu"
    out = lm.encode("a lighthouse", "blurry", 4.0)
    assert out["prompt_attention_mask"].dtype == torch.float16 and out["negative_prompt_embeds"].dtype == torch.float16


def test_the_pipelines_hand_the_transformer_a_boolean_mask():
    """diffusers 0.41 makes a 0/1 float mask, which scaled_dot_product_attention adds instead of applying (issue
    12116); the helper that extends it over the image tokens returns booleans once a Chroma model loads."""
    import diffusers
    engine._chroma_bool_masks()
    engine._chroma_bool_masks()  # idempotent
    for name in ("ChromaPipeline", "ChromaImg2ImgPipeline", "ChromaInpaintPipeline"):
        cls = getattr(diffusers, name)
        m = cls._prepare_attention_mask(object(), batch_size=1, sequence_length=2, dtype=torch.float16,
                                        attention_mask=torch.tensor([[1.0, 1.0, 0.0]], dtype=torch.float16))
        assert m.dtype == torch.bool and m.tolist() == [[True, True, False, True, True]]
        assert cls._prepare_attention_mask(object(), 1, 2, torch.float16, None) is None


# ------------------------------------------------------------ LoRAs

class ChromaPipelineStandIn:
    """Only its name matters to engine._lora_source."""


def _state_dict(name):
    """The fixture's LoRA as zeros of rank 1 (the rank, the smaller side of each matrix, does not matter here)."""
    out = {}
    for k, s in LORAS[name]["shapes"].items():
        if k.endswith(".alpha") or not s:
            out[k] = torch.tensor(1.0)
        else:
            small = s.index(min(s))
            out[k] = torch.zeros(*[1 if i == small else d for i, d in enumerate(s)], dtype=torch.float16)
    return out


def _placed(sd):
    """Share of the LoRA's transformer layers diffusers' reader maps onto Chroma's transformer."""
    import diffusers
    with torch.device("meta"):
        model = diffusers.ChromaTransformer2DModel.from_config(importer.CHROMA_TRANSFORMER_CONFIG)
    names = {n for n, _ in model.named_modules()}
    res = diffusers.ChromaPipeline.lora_state_dict(sd)
    out = res[0] if isinstance(res, tuple) else res
    layers = [k[len("transformer."):-len(".lora_A.weight")] for k in out
              if k.startswith("transformer.") and k.endswith(".lora_A.weight")]
    return (sum(1 for n in layers if n in names) / len(layers)) if layers else 0.0, len(layers)


# the fused qkv / linear1 layers of the original names become several of diffusers' (228 -> 418)
@pytest.mark.parametrize("name, layers", [("chroma_kohya_meta", 418), ("chroma_aitoolkit_comfy", 418)])
def test_chroma_loras_find_all_their_layers(name, layers):
    pipe = ChromaPipelineStandIn()
    assert _placed(engine._lora_source(pipe, _state_dict(name))) == (1.0, layers)
    if name == "chroma_aitoolkit_comfy":
        # in the original block names with peft factors: without the conversion diffusers places none
        assert _placed(_state_dict(name))[1] == 0


def test_flux1_loras_do_not_fit_chroma():
    share, _ = _placed(engine._lora_source(ChromaPipelineStandIn(), _state_dict("flux1_kohya_meta")))
    assert share < engine.LoadedModel.MIN_APPLIED  # its modulation layers have no place in Chroma
    lora = registry.lora_identity(LORAS["flux1_kohya_meta"]["shapes"], LORAS["flux1_kohya_meta"]["meta"])
    assert registry.lora_mismatch(dict(lora, name="f"), {"arch": "chroma", "family": "chroma"})
    lora = registry.lora_identity(LORAS["chroma_kohya_meta"]["shapes"], LORAS["chroma_kohya_meta"]["meta"])
    assert lora["family"] == "chroma" and registry.lora_mismatch(dict(lora, name="c"), {"arch": "chroma"}) is None


def test_original_names_are_converted_and_the_guidance_network_left_out():
    a = torch.zeros(2, 3072)
    sd = {"diffusion_model.double_blocks.0.img_attn.qkv.lora_A.weight": a,
          "diffusion_model.single_blocks.3.linear1.lora_B.weight": a, "diffusion_model.final_layer.linear.alpha": a,
          "diffusion_model.distilled_guidance_layer.in_proj.lora_A.weight": a, "lora_te_text_model.x.alpha": a}
    assert set(engine.bfl_lora_to_kohya(sd)) == {
        "lora_unet_double_blocks_0_img_attn_qkv.lora_down.weight", "lora_unet_single_blocks_3_linear1.lora_up.weight",
        "lora_unet_final_layer_linear.alpha", "lora_te_text_model.x.alpha"}
    assert engine._lora_source(object(), sd) is sd  # other pipelines read LoRAs as they are


# ------------------------------------------------------------ a Chroma checkpoint once imported as FLUX.1

def _flux1_base(base):
    """The base parts a single-file FLUX.1 [schnell] import downloaded (weights as tiny stand-ins)."""
    files = {
        "model_index.json": json.dumps({"_class_name": "FluxPipeline", "scheduler": ["diffusers", "FlowMatchEulerDiscreteScheduler"],
                                        "text_encoder": ["transformers", "CLIPTextModel"], "text_encoder_2": ["transformers", "T5EncoderModel"],
                                        "tokenizer": ["transformers", "CLIPTokenizer"], "tokenizer_2": ["transformers", "T5TokenizerFast"],
                                        "transformer": ["diffusers", "FluxTransformer2DModel"], "vae": ["diffusers", "AutoencoderKL"]}),
        "scheduler/scheduler_config.json": json.dumps({"_class_name": "FlowMatchEulerDiscreteScheduler", "shift": 1.0}),
        "text_encoder/config.json": json.dumps({"model_type": "clip_text_model"}), "text_encoder/model.safetensors": "c",
        "text_encoder_2/config.json": json.dumps({"model_type": "t5"}), "text_encoder_2/model-00001-of-00002.safetensors": "t",
        "text_encoder_2/model-00002-of-00002.safetensors": "t", "text_encoder_2/model.safetensors.index.json": "{}",
        "tokenizer/vocab.json": "{}", "tokenizer_2/spiece.model": "s", "tokenizer_2/tokenizer.json": "{}",
        "transformer/config.json": json.dumps({"_class_name": "FluxTransformer2DModel"}),
        "transformer/diffusion_pytorch_model.safetensors.index.json": "{}",
        "vae/config.json": "{}", "vae/diffusion_pytorch_model.safetensors": "v",
    }
    for rel, text in files.items():
        (base / rel).parent.mkdir(parents=True, exist_ok=True)
        (base / rel).write_text(text)


def _no_network(*a, **k):
    raise AssertionError("no download expected")


def _marked_model(tmp_path):
    """GonzaLomo_Chroma as the first check left it: FLUX.1 [schnell]'s manifest, marked as not runnable."""
    m = tmp_path / "models" / "GonzaLomo_Chroma"
    _flux1_base(m / "base")
    with open(m / "model.gguf", "wb") as f:
        f.truncate(9_462_431_904)  # the size of the real 8 bit file (sparse: takes no disk space)
    manifest = {"layout": "single_denoiser", "file": "model.gguf", "file_format": "gguf", "base_dir": "base",
                "base_repo": "black-forest-labs/FLUX.1-schnell", "engine": "diffusers", "name": "GonzaLomo_Chroma",
                "arch": "chroma", "family": "chroma", "label": "Chroma", "denoiser": "transformer",
                "components": {"text_encoder": 0.123, "text_encoder_2": 4.762, "transformer": 8.9, "vae": 0.084},
                "quant_request": "auto", "defaults": {"num_steps": 4, "guidance_scale": 0.0, "width": 1024, "height": 1024},
                "negative_prompt": False, "img2img": True, "preview": "preview.jpg",
                "source": {"type": "civitai", "base_model": "Chroma", "file": "gonzalomoChroma_v20.safetensors"},
                "unsupported": "Chroma models can not run in VulKara yet"}
    (m / "model.json").write_text(json.dumps(manifest))
    (m / "model.json.bak").write_text(json.dumps(dict(manifest, arch="flux1_schnell")))
    return m


def test_recheck_makes_a_marked_chroma_checkpoint_runnable(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "_hf_repo_info", _no_network)
    m = _marked_model(tmp_path)
    before = (m / "model.json").read_text()
    report = recheck.recheck(str(tmp_path / "models"), str(tmp_path / "loras"), ram_gb=24)
    assert len(report) == 1 and "would be taken over" in report[0]["base"]
    assert (m / "model.json").read_text() == before and (m / "base" / "text_encoder_2").is_dir()  # a dry run

    report = recheck.recheck(str(tmp_path / "models"), str(tmp_path / "loras"), apply=True, ram_gb=24)
    assert "taken over" in report[0]["base"]
    data = json.loads((m / "model.json").read_text())
    assert "unsupported" not in data and (data["arch"], data["family"], data["base_repo"]) == \
        ("chroma", "chroma", "lodestones/Chroma1-HD")
    assert data["components"] == {"text_encoder": 4.762, "transformer": 8.9, "vae": 0.084}
    assert data["defaults"]["num_steps"] == 30 and data["defaults"]["guidance_scale"] == 4.0
    assert data["negative_prompt"] and data["inpaint"] and data["preview"] == "preview.jpg"
    assert data["plan"]["fits"] and data["plan"]["quant"] == {"transformer": "gguf", "text_encoder": "q8"}
    assert json.loads((m / "model.json.bak").read_text())["arch"] == "flux1_schnell"  # the first backup stays
    base = m / "base"
    assert json.loads((base / "model_index.json").read_text())["_class_name"] == "ChromaPipeline"
    assert json.loads((base / "text_encoder" / "config.json").read_text())["model_type"] == "t5"
    assert (base / "tokenizer" / "spiece.model").exists() and not (base / "text_encoder_2").exists()
    assert json.loads((base / "scheduler" / "scheduler_config.json").read_text())["shift"] == 3.0
    assert json.loads((base / "transformer" / "config.json").read_text())["_class_name"] == "ChromaTransformer2DModel"
    unused = base / importer.FLUX1_LEFTOVERS
    assert (unused / "text_encoder" / "model.safetensors").exists() and (unused / "tokenizer" / "vocab.json").exists()
    assert json.loads((unused / "model_index.json").read_text())["_class_name"] == "FluxPipeline"
    assert importer.base_problem(str(m), data) is None
    assert recheck.recheck(str(tmp_path / "models"), str(tmp_path / "loras"), ram_gb=24) == []  # once is enough
    assert importer.ensure_base(str(m), data) is False


def test_an_interrupted_takeover_goes_on(tmp_path):
    base = tmp_path / "base"
    _flux1_base(base)
    (base / importer.FLUX1_LEFTOVERS).mkdir()
    os.rename(base / "text_encoder", base / importer.FLUX1_LEFTOVERS / "text_encoder")
    os.rename(base / "text_encoder_2", base / "text_encoder")  # stopped here
    assert importer.chroma_base_from_flux1(base)
    assert json.loads((base / "text_encoder" / "config.json").read_text())["model_type"] == "t5"
    assert not (base / "tokenizer_2").exists() and (base / importer.FLUX1_LEFTOVERS / "tokenizer").is_dir()
    # not a FLUX.1 base with T5: left alone
    other = tmp_path / "other"
    other.mkdir()
    (other / "model_index.json").write_text(json.dumps({"_class_name": "StableDiffusion3Pipeline"}))
    assert not importer.chroma_base_from_flux1(other)


def test_the_engine_takes_flux1_parts_over_on_first_use(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "_hf_repo_info", _no_network)
    m = _marked_model(tmp_path)
    data = json.loads((m / "model.json").read_text())
    data.pop("unsupported")
    assert "FluxPipeline" in importer.base_problem(str(m), data)
    assert importer.ensure_base(str(m), data) is True and importer.base_problem(str(m), data) is None


def test_missing_base_parts_are_downloaded(tmp_path, monkeypatch, hub):
    import huggingface_hub
    m = tmp_path / "models" / "Chroma"
    base = m / "base"
    base.mkdir(parents=True)
    (base / "model_index.json").write_text(json.dumps(HD_INDEX))
    data = {"layout": "single_denoiser", "file": "model.gguf", "base_dir": "base", "base_repo": "lodestones/Chroma1-HD",
            "arch": "chroma", "denoiser": "transformer", "name": "Chroma"}
    assert importer.base_problem(str(m), data) == "its scheduler is missing"
    asked = []

    def download(repo, local_dir, allow_patterns, token=None):
        asked.extend(allow_patterns)
        for f in allow_patterns:
            os.makedirs(os.path.dirname(os.path.join(local_dir, f)), exist_ok=True)
            with open(os.path.join(local_dir, f), "w") as out:
                out.write(json.dumps(HD_INDEX) if f == "model_index.json" else "")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", download)
    monkeypatch.setattr(importer, "ensure_space", lambda *a: None)
    stages = []
    assert importer.ensure_base(str(m), data, report=lambda stage, pct: stages.append(stage))
    assert "vae/diffusion_pytorch_model.safetensors" in asked and "text_encoder/model-00001-of-00002.safetensors" in asked
    assert not [f for f in asked if f.startswith("transformer/") and f.endswith(".safetensors")]  # the model's own
    assert "Chroma1-HD.safetensors" not in asked and stages
    assert importer.base_problem(str(m), data) is None

    # offline: the message says what to do
    (base / "vae" / "diffusion_pytorch_model.safetensors").unlink()
    monkeypatch.setattr(importer, "_hf_repo_info", lambda repo, token: (_ for _ in ()).throw(OSError("offline")))
    with pytest.raises(registry.UnsupportedModel, match="Models → Installed"):
        importer.ensure_base(str(m), data)
