# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Z-Image (Turbo and Base): recognising its checkpoints and repos, the import of single files from the Turbo / Base
repo, the memory plans of both runtimes, the staged prompt encoding, guidance, its LoRAs in every naming and the
installed LoRAs' labels. No network: the fixture holds the tensor names, dtypes and shapes of real checkpoints (their
headers, no weights), the Hub is replaced by fakes."""
import gzip
import importlib.util
import json
import os
import types

import pytest
import torch

import civitai
import engine
import importer
import lora_convert
import memory
import recheck
import registry
import samplers

HERE = os.path.dirname(__file__)
with gzip.open(os.path.join(HERE, "fixtures", "z_image_turbo_headers.json.gz"), "rt") as f:
    FIXTURE = json.load(f)
COMFY = {k: v[1] for k, v in FIXTURE["comfy_bf16"].items()}           # Comfy-Org/z_image_turbo, original names
GGUF = FIXTURE["gguf_q4_k_m"]                                           # unsloth/Z-Image-Turbo-GGUF, GGUF order
DIFFUSERS = {k: v[1] for k, v in FIXTURE["diffusers_shard1"].items()}  # Tongyi-MAI/Z-Image-Turbo, first shard
with gzip.open(os.path.join(HERE, "fixtures", "lora_headers.json.gz"), "rt") as f:
    LORAS = json.load(f)

# Tongyi-MAI/Z-Image-Turbo's transformer config and its files as Hugging Face lists them (bytes)
TURBO_CONFIG = {"_class_name": "ZImageTransformer2DModel", "all_f_patch_size": [1], "all_patch_size": [2],
                "axes_dims": [32, 48, 48], "axes_lens": [1536, 512, 512], "cap_feat_dim": 2560, "dim": 3840,
                "in_channels": 16, "n_heads": 30, "n_kv_heads": 30, "n_layers": 30, "n_refiner_layers": 2,
                "norm_eps": 1e-05, "qk_norm": True, "rope_theta": 256.0, "t_scale": 1000.0}
MODEL_INDEX = {"_class_name": "ZImagePipeline", "scheduler": ["diffusers", "FlowMatchEulerDiscreteScheduler"],
               "text_encoder": ["transformers", "Qwen3Model"], "tokenizer": ["transformers", "Qwen2Tokenizer"],
               "transformer": ["diffusers", "ZImageTransformer2DModel"], "vae": ["diffusers", "AutoencoderKL"]}
TURBO_FILES = {
    "model_index.json": 467, "scheduler/scheduler_config.json": 173, "text_encoder/config.json": 726,
    "text_encoder/generation_config.json": 239, "text_encoder/model-00001-of-00003.safetensors": 3_957_900_840,
    "text_encoder/model-00002-of-00003.safetensors": 3_987_450_520,
    "text_encoder/model-00003-of-00003.safetensors": 99_630_640, "text_encoder/model.safetensors.index.json": 32_819,
    "tokenizer/merges.txt": 1_671_853, "tokenizer/tokenizer.json": 11_422_654, "tokenizer/tokenizer_config.json": 9_732,
    "tokenizer/vocab.json": 2_776_833, "transformer/config.json": 473,
    "transformer/diffusion_pytorch_model-00001-of-00003.safetensors": 9_973_693_184,
    "transformer/diffusion_pytorch_model-00002-of-00003.safetensors": 9_973_714_824,
    "transformer/diffusion_pytorch_model-00003-of-00003.safetensors": 4_672_282_880,
    "transformer/diffusion_pytorch_model.safetensors.index.json": 48_969,
    "vae/config.json": 805, "vae/diffusion_pytorch_model.safetensors": 167_666_902,
}
TEXT_ENCODER_BYTES = 3_957_900_840 + 3_987_450_520 + 99_630_640
# what the headers of the base repo's text encoder and VAE count (billions)
BASE_PARAMS = {"text_encoder": 4.022, "vae": 0.084}


def _mlx_main():
    spec = importlib.util.spec_from_file_location("mlx_main", os.path.join(HERE, "..", "..", "mlx", "main.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------ recognising

def test_the_checkpoints_are_z_image_in_every_naming():
    assert registry.is_z_image(COMFY) and registry.is_z_image(GGUF) and registry.is_z_image(DIFFUSERS)
    arch, layout, overrides, params = registry.detect_from_single_file(COMFY, "Comfy-Org/z_image_turbo/z_image_turbo_bf16.safetensors")
    assert (arch, layout, overrides) == ("z_image", "single_denoiser", {})  # Turbo: the architecture's defaults
    assert abs(params - 6.15) < 0.01
    # GGUF lists the dimensions the other way round; ComfyUI files carry a prefix; diffusers' own names
    assert registry.detect_from_single_file(GGUF, "unsloth/Z-Image-Turbo-GGUF/z-image-turbo-Q4_K_M.gguf")[0] == "z_image"
    prefixed = {"model.diffusion_model." + k: v for k, v in COMFY.items()}
    assert registry.detect_from_single_file(prefixed, "x/moodyProMix_bf16.safetensors")[0] == "z_image"
    assert registry.detect_from_single_file(DIFFUSERS, "x/z-image-turbo-diffusers.safetensors")[0] == "z_image"


def test_turbo_and_base_by_name():
    detect = registry.detect_from_single_file
    base = {"num_steps": 30, "guidance_scale": 4.0}
    assert detect(COMFY, "Comfy-Org/z_image/z_image_bf16.safetensors")[2] == {}  # no word: Turbo, as most are
    assert detect(COMFY, "x/zImageBase_base.safetensors")[2] == base
    assert detect(COMFY, "x/luciddreamerZ_v083BKawaii_bf16.safetensors ZImageBase")[2] == base  # Civitai's base model
    assert detect(COMFY, "x/zImageTurbo_turbo.safetensors ZImageTurbo")[2] == {}
    # distilled fine-tunes of the base run like Turbo; the generic "turbo" rule (4 steps) does not apply
    assert detect(COMFY, "x/redcraft_zibDistilled.safetensors ZImageBase")[2] == {}
    assert detect(COMFY, "x/unstableRevolution ZIT v3.safetensors")[2] == {}
    assert registry.ARCHS["z_image"]["defaults"]["num_steps"] == 9


def test_lumina_is_its_own_model_omni_and_incomplete_files_are_refused():
    lumina = {k: [2304 if d == 3840 else d for d in v] for k, v in COMFY.items()}
    assert registry.detect_from_single_file(lumina, "lumina2.safetensors")[:2] == ("lumina2", "comfy_files")
    other = {k: [2560 if d == 3840 else d for d in v] for k, v in COMFY.items()}
    with pytest.raises(registry.UnsupportedModel, match="Lumina 2 and Z-Image"):
        registry.detect_from_single_file(other, "nextdit.safetensors")
    with pytest.raises(registry.UnsupportedModel, match="Omni"):
        registry.detect_from_single_file(dict(COMFY, **{"siglip_embedder.1.weight": [3840, 1152]}), "z_image_omni.safetensors")
    with pytest.raises(registry.UnsupportedModel, match="Incomplete Z-Image"):
        registry.detect_from_single_file({k: v for k, v in COMFY.items() if not k.startswith("x_embedder.")})


def test_diffusers_repos_turbo_base_and_omni():
    detect = registry.detect_from_model_index
    assert detect(MODEL_INDEX, TURBO_CONFIG, "Tongyi-MAI/Z-Image-Turbo", {"shift": 3.0}) == ("z_image", {})
    assert detect(MODEL_INDEX, TURBO_CONFIG, "Tongyi-MAI/Z-Image", {"shift": 6.0})[1]["guidance_scale"] == 4.0
    # a folder whose name says nothing: Base shifts by 6
    assert detect(MODEL_INDEX, TURBO_CONFIG, "/Volumes/x/my-merge", {"shift": 6.0})[1]["num_steps"] == 30
    assert detect(MODEL_INDEX, TURBO_CONFIG, "/Volumes/x/my-merge", None) == ("z_image", {})
    with pytest.raises(registry.UnsupportedModel, match="Omni"):
        detect(MODEL_INDEX, dict(TURBO_CONFIG, siglip_feat_dim=1152), "x/Z-Image-Omni")
    with pytest.raises(registry.UnsupportedModel, match="Z-Image"):
        detect({"_class_name": "ZImageOmniPipeline"}, {}, "x")


def test_the_spec_follows_diffusers():
    import diffusers
    from diffusers.loaders.single_file_model import SINGLE_FILE_LOADABLE_CLASSES
    spec = registry.ARCHS["z_image"]
    for key in ("pipeline", "img2img_pipeline", "inpaint_pipeline", "denoiser_class"):
        assert hasattr(diffusers, spec[key]), spec[key]
    assert spec["denoiser_class"] in SINGLE_FILE_LOADABLE_CLASSES
    assert spec["negative_prompt"] and spec["torch_dtype"] == "bfloat16" and not spec.get("fp16_compute")
    assert all(r % spec["size_multiple"] == 0 for r in spec["resolutions"]) and 2048 in spec["resolutions"]
    with torch.device("meta"):
        model = diffusers.ZImageTransformer2DModel.from_config(TURBO_CONFIG)
    # the fused qkv of the original names holds what to_q / to_k / to_v hold; ComfyUI leaves out no weight
    assert abs(sum(p.numel() for p in model.parameters()) / 1e9 - registry._n_params(COMFY) / 1e9) < 0.01
    assert abs(spec["fallback_params"]["transformer"] - registry._n_params(COMFY) / 1e9) < 0.01


def test_civitai_and_hugging_face_bases():
    assert civitai.arch_of("ZImageTurbo") == "z_image" and civitai.arch_of("ZImageBase") == "z_image"
    assert civitai.lora_hint("ZImageBase")["family"] == "z_image"
    assert registry.family_of_repo("Tongyi-MAI/Z-Image-Turbo") == ("z_image", None)
    assert registry.family_label("z_image") == "Z-Image" and "z_image" not in registry.FOREIGN_FAMILIES
    assert importer._guess_from_name("unsloth/Z-Image-GGUF/z-image-Q8_0.gguf")[0] == "z_image"


# ------------------------------------------------------------ import and memory

@pytest.fixture
def hub(monkeypatch):
    asked = []

    def repo_info(repo, token):
        asked.append(repo)
        return None, TURBO_FILES

    monkeypatch.setattr(importer, "_hf_repo_info", repo_info)
    monkeypatch.setattr(importer, "_hf_json", lambda repo, f, token: MODEL_INDEX)
    monkeypatch.setattr(importer, "_params_from_hf", lambda api, repo, files: dict(BASE_PARAMS))
    return asked


def test_a_single_file_is_completed_from_the_turbo_or_base_repo(tmp_path, monkeypatch, hub):
    path = tmp_path / "zImageTurbo_turbo.safetensors"
    path.write_bytes(b"x")
    monkeypatch.setattr(registry, "read_single_file_header", lambda p: COMFY)
    info = importer.inspect("file", str(path))
    assert (info["arch"], info["layout"], info["base_repo"]) == ("z_image", "single_denoiser", "Tongyi-MAI/Z-Image-Turbo")
    assert set(info["components"]) == {"text_encoder", "transformer", "vae"}
    assert abs(info["components"]["transformer"] - 6.15) < 0.01
    # the base repo's 24.6 GB transformer is not downloaded: the Qwen3 encoder, VAE, tokenizer and configs are
    assert TEXT_ENCODER_BYTES < info["download_bytes"] < TEXT_ENCODER_BYTES + 200_000_000
    base = tmp_path / "zImageBase_base.safetensors"
    base.write_bytes(b"x")
    info = importer.inspect("file", str(base))
    assert info["base_repo"] == "Tongyi-MAI/Z-Image" and info["overrides"]["guidance_scale"] == 4.0
    # Civitai's base model decides for a file whose name says nothing
    plain = tmp_path / "moodyWildMix_v40.safetensors"
    plain.write_bytes(b"x")
    assert importer.inspect("file", str(plain), name_hint="ZImageBase")["base_repo"] == "Tongyi-MAI/Z-Image"
    assert importer.inspect("file", str(plain), name_hint="ZImageTurbo")["base_repo"] == "Tongyi-MAI/Z-Image-Turbo"


def test_the_official_repos(monkeypatch, hub):
    shifts = {"Tongyi-MAI/Z-Image-Turbo": 3.0, "Tongyi-MAI/Z-Image": 6.0}

    def hf_json(repo, f, token):
        return {"model_index.json": MODEL_INDEX, "transformer/config.json": TURBO_CONFIG,
                "scheduler/scheduler_config.json": {"shift": shifts[repo]}}[f]

    monkeypatch.setattr(importer, "_hf_json", hf_json)
    monkeypatch.setattr(importer, "_params_from_hf", lambda api, repo, files: dict(BASE_PARAMS, transformer=6.155))
    info = importer.inspect("hf", "Tongyi-MAI/Z-Image-Turbo")
    assert (info["arch"], info["layout"], info["overrides"], info["variant"]) == ("z_image", "repo", {}, None)
    assert round(info["download_bytes"] / 1e9, 1) == 32.8  # the transformer is stored in 32 bit
    assert importer.inspect("hf", "Tongyi-MAI/Z-Image")["overrides"] == {"num_steps": 30, "guidance_scale": 4.0}


COMPONENTS = {"text_encoder": 4.022, "transformer": 6.155, "vae": 0.084}


def test_memory_plans_with_diffusers():
    # 24 GB: 16 bit would leave 1.8 GB under the budget (staged), less than the margin: the transformer in 8 bit
    plan = memory.plan(COMPONENTS, "transformer", "z_image", 24)
    assert plan["fits"] and plan["quant"]["transformer"] == "q8"
    # 26 GB: the transformer in 16 bit, the Qwen3 encoder in 8 bit and only loaded for a new prompt
    plan = memory.plan(COMPONENTS, "transformer", "z_image", 26)
    assert plan["fits"] and plan["quant"] == {"transformer": "none", "text_encoder": "q8"} and plan["staged_text_encoder"]
    # 16 GB: both in 8 bit
    plan = memory.plan(COMPONENTS, "transformer", "z_image", 16)
    assert plan["fits"] and plan["quant"] == {"transformer": "q8", "text_encoder": "q8"} and plan["min_ram_gb"] == 16
    # an 8 bit GGUF keeps the encoder resident on 24 GB
    plan = memory.plan(COMPONENTS, "transformer", "z_image", 24, denoiser_fixed_gb=7_224_707_136 / 1024 ** 3)
    assert plan["fits"] and not plan["staged_text_encoder"]


def test_memory_plans_with_mlx():
    mlx_main = _mlx_main()
    m = {"arch": "z_image", "denoiser": "transformer", "components": COMPONENTS}
    assert mlx_main.choose_quant(m, ram_gb=24)[0] == 8
    # 16 GB: 8 bit with the text encoder dropped after encoding (measured on the M2 with the 16 GB plan: 7.5-8 GB for
    # the steps; before, 4 bit with the encoder kept peaked at 12.9 GB and swapped on the Mac mini)
    bits, plan, quantize_te = mlx_main.choose_quant(m, ram_gb=16)
    assert bits == 8 and plan["fits"] and plan["staged_text_encoder"] and not quantize_te
    assert mlx_main.choose_quant(m, ram_gb=48)[0] is None
    assert not mlx_main.z_image_guided({"defaults": {"guidance_scale": 0.0}})
    assert mlx_main.z_image_guided({"defaults": {"guidance_scale": 4.0}})


def test_mlx_keeps_the_encoded_prompts_while_the_text_encoder_is_dropped(monkeypatch):
    # staged: the text encoder is freed after the first prompt; the same prompt again needs no text encoder
    import sys
    monkeypatch.setitem(sys.modules, "mlx", types.ModuleType("mlx"))
    monkeypatch.setitem(sys.modules, "mlx.core", types.SimpleNamespace(eval=lambda arrays: None))
    calls = []

    class Model:
        def _encode_prompts(self, *, prompt, negative_prompt, guidance):
            calls.append((prompt, negative_prompt))
            return ("enc " + prompt, "neg " + negative_prompt if guidance > 1.0 else None)

    model = Model()
    _mlx_main().cache_prompt_encodings(model, keep=2)
    assert model._encode_prompts(prompt="a", negative_prompt="x", guidance=0.0) == ("enc a", None)
    assert model._encode_prompts(prompt="a", negative_prompt="y", guidance=0.0) == ("enc a", None)  # no guidance: no negative
    assert model._encode_prompts(prompt="a", negative_prompt="x", guidance=4.0) == ("enc a", "neg x")
    model._encode_prompts(prompt="b", negative_prompt="", guidance=0.0)
    assert calls == [("a", "x"), ("a", "x"), ("b", "")]
    model._encode_prompts(prompt="a", negative_prompt="z", guidance=0.0)  # the oldest went (keep=2)
    assert len(calls) == 4


def test_small_macs_decode_in_tiles_where_the_vae_allows_it(monkeypatch):
    import sys
    tiling = types.SimpleNamespace(TilingConfig=type("TilingConfig", (), {
        "may_tile_implicitly": staticmethod(lambda m: getattr(m.vae, "supports_implicit_tiling", True))}))
    monkeypatch.setitem(sys.modules, "mflux.models.common.vae.tiling_config", tiling)
    mlx_main = _mlx_main()
    z, flux2 = types.SimpleNamespace(vae=object(), tiling_config=None), types.SimpleNamespace(vae=types.SimpleNamespace(supports_implicit_tiling=False), tiling_config=None)
    mlx_main.low_ram(z)
    mlx_main.low_ram(flux2)
    assert z.tiling_config is not None and flux2.tiling_config is None


def test_a_mac_short_of_free_memory_decodes_in_tiles_and_the_job_says_so(monkeypatch):
    import sys
    import protocol
    tiling = types.SimpleNamespace(TilingConfig=type("TilingConfig", (), {"may_tile_implicitly": staticmethod(lambda m: True)}))
    monkeypatch.setitem(sys.modules, "mflux.models.common.vae.tiling_config", tiling)
    mlx_main = _mlx_main()
    sent = []
    monkeypatch.setattr(protocol, "event", lambda name, **f: sent.append((name, f)))
    monkeypatch.setattr(protocol, "footprint_gb", lambda: 8.0)
    plan = memory.plan({"transformer": 6.0, "text_encoder": 4.0, "vae": 0.08}, "transformer", "z_image", 24)
    eng = mlx_main.MlxEngine.__new__(mlx_main.MlxEngine)
    eng.plan, eng.model = plan, types.SimpleNamespace(vae=object(), tiling_config=None)
    peak = memory.peak_at(plan, 1024, 1024)
    # enough free: in one piece, the decode counted in the plan
    monkeypatch.setattr(memory, "free_gb", lambda held=0.0: 40.0)
    eng._plan_job("z_image", 1024, 1024)
    assert eng.model.tiling_config is None and protocol.PLANNED["gb"] == round(peak + mlx_main.DECODE_GB["z_image"], 2)
    assert sent == [("planned", {"gb": protocol.PLANNED["gb"]})]
    # too little for the one-piece decode, enough without it: tiles, and a note
    sent.clear()
    monkeypatch.setattr(memory, "free_gb", lambda held=0.0: peak + 1.0)
    eng._plan_job("z_image", 1024, 1024)
    assert eng.model.tiling_config is not None and protocol.PLANNED["gb"] == round(peak, 2)
    assert [f["message"] for n, f in sent if n == "note"] == ["Not enough memory free to decode the picture in one piece: decoded in tiles (no visible difference)"]
    # short even so: the job tells how much is free
    sent.clear()
    monkeypatch.setattr(memory, "free_gb", lambda held=0.0: peak - 3.0)
    eng._plan_job("z_image", 1024, 1024)
    assert [f["message"] for n, f in sent if n == "note"][0].startswith("Only %.1f GB of memory free" % (peak - 3.0))


def test_flow_samplers_and_guidance_off():
    assert "flow_euler" in samplers.for_family("z_image") and "flow_heun" not in samplers.for_family("z_image")
    spec = registry.ARCHS["z_image"]
    # diffusers' Z-Image guides with anything above 0: up to 1 is "off" as in mflux and for the other models
    assert engine.pipeline_guidance(spec, 1.0) == 0.0 and engine.pipeline_guidance(spec, 0.5) == 0.0
    assert engine.pipeline_guidance(spec, 4.0) == 4.0
    assert engine.pipeline_guidance(registry.ARCHS["flux1_dev"], 1.0) == 1.0  # others as they are


# ------------------------------------------------------------ prompt encoding (staged text encoder)

class FakeZImagePipe:
    def __init__(self):
        self.calls = []

    def encode_prompt(self, prompt, device=None, do_classifier_free_guidance=True, negative_prompt=None,
                      max_sequence_length=512):
        self.calls.append((prompt, negative_prompt, do_classifier_free_guidance))
        # one tensor per prompt, as long as its tokens (no padding)
        neg = [torch.zeros(3, 8)] if do_classifier_free_guidance else []
        return [torch.ones(5, 8)], neg


def test_staged_encoding_returns_lists_and_guides_only_above_1():
    spec = registry.ARCHS["z_image"]
    pipe = FakeZImagePipe()
    out = engine._encode(pipe, spec, "a lighthouse", "", 0.0, "cpu")
    assert pipe.calls == [("a lighthouse", "", False)] and set(out) == {"prompt_embeds"}
    pipe = FakeZImagePipe()
    out = engine._encode(pipe, spec, "a lighthouse", "fog", 4.0, "cpu")
    assert pipe.calls == [("a lighthouse", "fog", True)] and set(out) == {"prompt_embeds", "negative_prompt_embeds"}
    lm = engine.LoadedModel.__new__(engine.LoadedModel)
    lm.embed_cache, lm.text_pipe, lm.staged, lm.dtype = None, FakeZImagePipe(), False, torch.bfloat16
    lm.spec, lm.device = spec, "cpu"
    out = lm.encode("a lighthouse", "fog", 4.0)
    assert isinstance(out["prompt_embeds"], list) and out["prompt_embeds"][0].dtype == torch.bfloat16
    assert out["negative_prompt_embeds"][0].shape == (3, 8)


# ------------------------------------------------------------ LoRAs

_model = []


def tensors(name):
    """The fixture's LoRA as zeros, rank 1 (the rank does not matter here)."""
    out = {}
    for k, s in LORAS[name]["shapes"].items():
        if k.endswith(".alpha") or not s:
            out[k] = torch.tensor(1.0)
        else:
            small = s.index(min(s[:2]))
            out[k] = torch.zeros(*[1 if i == small else d for i, d in enumerate(s)], dtype=torch.float16)
    return out


def placed(sd):
    """(share of the layers diffusers' Z-Image reader names that exist in the model with the LoRA's widths, layers)."""
    import diffusers
    if not _model:
        with torch.device("meta"):
            _model.append(diffusers.ZImageTransformer2DModel.from_config(TURBO_CONFIG))
    mods = dict(_model[0].named_modules())
    res = diffusers.ZImagePipeline.lora_state_dict(dict(sd))
    out = res[0] if isinstance(res, tuple) else res
    layers = [k[len("transformer."):-len(".lora_A.weight")] for k in out
              if k.startswith("transformer.") and k.endswith(".lora_A.weight")]
    ok = 0
    for n in layers:
        w = getattr(mods.get(n), "weight", None)
        a, b = out["transformer.%s.lora_A.weight" % n], out["transformer.%s.lora_B.weight" % n]
        ok += w is not None and w.shape[1] == a.shape[1] and w.shape[0] == b.shape[0]
    return (ok / len(layers) if layers else 0.0), len(layers)


class ZImagePipelineStandIn:
    """Only its name matters to lora_convert."""


def test_ai_toolkit_loras_load_as_they_are():
    sd = tensors("zimage_aitoolkit")
    assert not lora_convert._needs(lora_convert._kind(ZImagePipelineStandIn()), list(sd))
    assert lora_convert.prepare(ZImagePipelineStandIn(), sd) is sd
    assert placed(sd) == (1.0, 240)


def test_comfyui_loras_with_the_fused_qkv_are_converted():
    sd = tensors("zimage_comfy_nometa")
    pipe = ZImagePipelineStandIn()
    assert lora_convert._needs(lora_convert._kind(pipe), list(sd)) == ["zimage"]
    # qkv becomes to_q / to_k / to_v: 202 layers -> 270
    assert placed(lora_convert.prepare(pipe, sd)) == (1.0, 270)
    assert placed(sd)[0] < engine.LoadedModel.MIN_APPLIED  # without the conversion it did not fit


def test_kohya_names_with_the_fused_qkv_and_alphas():
    q = torch.full((3, 1), 1.0)
    sd = {"lora_unet_layers_0_attention_qkv.lora_down.weight": torch.ones(1, 3840),
          "lora_unet_layers_0_attention_qkv.lora_up.weight": torch.cat([q, 2 * q, 3 * q]).repeat(1280, 1)[:11520],
          "lora_unet_layers_0_attention_qkv.alpha": torch.tensor(1.0),
          "lora_unet_layers_0_attention_out.lora_down.weight": torch.ones(1, 3840),
          "lora_unet_layers_0_attention_out.lora_up.weight": torch.ones(3840, 1),
          "lora_unet_noise_refiner_1_feed_forward_w2.lora_down.weight": torch.ones(1, 10240),
          "lora_unet_noise_refiner_1_feed_forward_w2.lora_up.weight": torch.ones(3840, 1),
          "lora_unet_layers_3_adaLN_modulation_0.lora_down.weight": torch.ones(1, 256),
          "lora_unet_layers_3_adaLN_modulation_0.lora_up.weight": torch.ones(15360, 1),
          "lora_unet_final_layer_linear.lora_down.weight": torch.ones(1, 3840),
          "lora_unet_final_layer_linear.lora_up.weight": torch.ones(64, 1),
          "lora_unet_layers_0_attention_out.dora_scale": torch.ones(1, 3840)}
    out = lora_convert.z_image_to_diffusers(sd)
    assert set(out) >= {"diffusion_model.layers.0.attention.to_q.lora_A.weight",
                        "diffusion_model.layers.0.attention.to_v.alpha",
                        "diffusion_model.layers.0.attention.to_out.0.lora_B.weight",
                        "diffusion_model.noise_refiner.1.feed_forward.w2.lora_A.weight",
                        "diffusion_model.layers.3.adaLN_modulation.0.lora_B.weight",
                        "diffusion_model.all_final_layer.2-1.linear.lora_A.weight"}
    assert not [k for k in out if "dora_scale" in k or "qkv" in k]
    assert placed(lora_convert.prepare(ZImagePipelineStandIn(), sd)) == (1.0, 7)


def test_the_fused_qkv_is_cut_in_rows_q_k_v():
    up = torch.cat([torch.full((3840, 2), float(i)) for i in range(3)])
    out = lora_convert.z_image_to_diffusers({"diffusion_model.layers.5.attention.qkv.lora_B.weight": up,
                                             "diffusion_model.layers.5.attention.qkv.lora_A.weight": torch.ones(2, 3840)})
    for i, x in enumerate("qkv"):
        assert torch.equal(out["diffusion_model.layers.5.attention.to_%s.lora_B.weight" % x], torch.full((3840, 2), float(i)))
        assert out["diffusion_model.layers.5.attention.to_%s.lora_A.weight" % x].shape == (2, 3840)
    # next to the split layers (some trainers write both) the fused one is left out
    both = {"diffusion_model.layers.0.attention.qkv.lora_A.weight": torch.ones(2, 3840),
            "diffusion_model.layers.0.attention.to_q.lora_A.weight": torch.zeros(2, 3840)}
    assert torch.equal(lora_convert.z_image_to_diffusers(both)["diffusion_model.layers.0.attention.to_q.lora_A.weight"],
                       torch.zeros(2, 3840))


def test_peft_dumps_without_a_prefix_get_one():
    sd = {"base_model.model.layers.0.attention.to_q.lora_A.default.weight": torch.ones(1, 3840),
          "base_model.model.layers.0.attention.to_q.lora_B.default.weight": torch.ones(3840, 1)}
    assert lora_convert.z_image_needs(list(sd))
    assert placed(lora_convert.prepare(ZImagePipelineStandIn(), sd)) == (1.0, 1)


def test_z_image_loras_fit_z_image_models_only():
    zimage = registry.lora_identity(LORAS["zimage_comfy_nometa"]["shapes"], LORAS["zimage_comfy_nometa"]["meta"])
    model = {"arch": "z_image", "family": "z_image", "label": "Z-Image"}
    assert registry.lora_mismatch(dict(zimage, name="z"), model) is None
    flux = registry.lora_identity(LORAS["flux1_kohya_meta"]["shapes"], LORAS["flux1_kohya_meta"]["meta"])
    assert "FLUX.1" in registry.lora_mismatch(dict(flux, name="f"), model)
    assert "Z-Image" in registry.lora_mismatch(dict(zimage, name="z"), {"arch": "chroma", "family": "chroma"})


def test_mlx_takes_the_converted_names_and_counts_what_finds_its_place():
    """mflux's Z-Image mapping lists per layer the keys it reads ("{block}" a block number): a stand-in with the
    patterns of its diffusers / peft names."""
    mlx_main = _mlx_main()
    targets = []
    for kind in ("layers", "noise_refiner", "context_refiner"):
        for layer in ("attention.to_q", "attention.to_k", "attention.to_v", "attention.to_out.0", "feed_forward.w1",
                      "feed_forward.w2", "feed_forward.w3", "adaLN_modulation.0"):
            targets.append(types.SimpleNamespace(possible_down_patterns=[
                "diffusion_model.%s.{block}.%s.lora_A.weight" % (kind, layer),
                "transformer.%s.{block}.%s.lora_A.weight" % (kind, layer)]))
    converted = lora_convert.z_image_to_diffusers(tensors("zimage_comfy_nometa"))
    assert mlx_main.lora_coverage(list(converted), targets) == (270, 270)
    assert mlx_main.lora_coverage(list(tensors("zimage_aitoolkit")), targets) == (240, 240)
    placed_before, total = mlx_main.lora_coverage(list(tensors("zimage_comfy_nometa")), targets)
    assert placed_before < total * mlx_main.MIN_APPLIED  # the fused qkv has no place in mflux


# ------------------------------------------------------------ installed LoRAs

def test_recheck_takes_the_no_runtime_note_off_installed_z_image_loras(tmp_path):
    from safetensors.torch import save_file
    folder = tmp_path / "loras" / "skin"
    folder.mkdir(parents=True)
    save_file({k: v.contiguous() for k, v in tensors("zimage_aitoolkit").items()}, str(folder / "lora.safetensors"))
    label = "LoRA for Z-Image" + registry.NO_RUNTIME_LABEL
    (folder / "lora.json").write_text(json.dumps({"type": "lora", "name": "skin", "file": "lora.safetensors",
                                                  "family": "z_image", "variant": None, "label": label}))
    report = recheck.recheck(str(tmp_path / "models"), str(tmp_path / "loras"), apply=True)
    assert report[0]["changes"] == {"label": [label, "LoRA for Z-Image"]}
    assert json.loads((folder / "lora.json").read_text())["label"] == "LoRA for Z-Image"
    assert recheck.recheck(str(tmp_path / "models"), str(tmp_path / "loras")) == []


def test_mlx_runs_z_image_on_its_own_fixed_shift(tmp_path):
    # mflux shifts by the resolution (about 3.16 at 1024 px for Turbo); the model's config asks for a fixed 3 (Base 6)
    mlx_main = _mlx_main()
    turbo, base = {"defaults": {"guidance_scale": 0.0}}, {"defaults": {"guidance_scale": 4.0}}
    assert mlx_main.z_image_shift(turbo, str(tmp_path)) == 3.0 and mlx_main.z_image_shift(base, str(tmp_path)) == 6.0
    (tmp_path / "weights" / "scheduler").mkdir(parents=True)
    (tmp_path / "weights" / "scheduler" / "scheduler_config.json").write_text('{"shift": 4.5}')
    assert mlx_main.z_image_shift(dict(turbo, weights_dir="weights"), str(tmp_path)) == 4.5
    # the reference: diffusers' FlowMatchEulerDiscreteScheduler with Z-Image-Turbo's config, 9 steps
    s = torch.linspace(1.0, 1 / 9, 9)
    ref = (3 * s / (1 + 2 * s)).tolist()
    from diffusers import FlowMatchEulerDiscreteScheduler
    d = FlowMatchEulerDiscreteScheduler(shift=3.0, use_dynamic_shifting=False)
    d.set_timesteps(sigmas=s.tolist())
    assert torch.allclose(d.sigmas[:-1], torch.tensor(ref), atol=1e-6)


def test_mlx_loads_the_parts_one_after_another_the_denoiser_first(monkeypatch):
    # mflux leaves the weights lazy; all of them at once in the first step peaked at 29.3 GB on a 16 GB Mac mini
    import sys
    order = []
    monkeypatch.setitem(sys.modules, "mlx", types.ModuleType("mlx"))
    monkeypatch.setitem(sys.modules, "mlx.core", types.SimpleNamespace(eval=lambda p: order.append(p), clear_cache=lambda: None))
    mlx_main = _mlx_main()

    class Part:
        def __init__(self, name):
            self.name = name

        def parameters(self):
            return self.name

    model = types.SimpleNamespace(text_encoder=Part("te"), vae=Part("vae"), transformer=Part("tr"), steps=9)
    assert mlx_main.materialize(model) == ["transformer", "vae", "text_encoder"] and order == ["tr", "vae", "te"]
    order.clear()
    assert mlx_main.materialize(model, text_encoders=False) == ["transformer", "vae"] and order == ["tr", "vae"]
    # an mlx Module (mflux's models) is a dict whose parts are its items
    order.clear()
    as_module = {"text_encoder": Part("te"), "transformer": Part("tr"), "config": "x"}
    assert mlx_main.materialize(as_module) == ["transformer", "text_encoder"] and order == ["tr", "te"]


def test_mlx_progress_is_sent_after_the_step_is_evaluated(monkeypatch):
    # mflux calls the in-loop callback before it evaluates the step: the value of a step must wait for it
    import sys
    calls = []
    monkeypatch.setitem(sys.modules, "mlx", types.ModuleType("mlx"))
    monkeypatch.setitem(sys.modules, "mlx.core", types.SimpleNamespace(eval=lambda x: calls.append(("eval", x))))
    mlx_main = _mlx_main()
    monkeypatch.setattr(mlx_main.protocol, "progress", lambda v: calls.append(("progress", v)))
    mlx_main.Progress(None, 8).call_in_loop(0, 1, "p", "latents", None, None)
    assert calls == [("eval", "latents"), ("progress", 12.5)]
