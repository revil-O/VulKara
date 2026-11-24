# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""SD 1.x / 2.x on the diffusers engine: detection, LoRA family, .ckpt, memory."""
import json

import pytest

import importer
import memory
import registry


def _header(shapes):
    return {k: list(v) for k, v in shapes.items()}


def test_single_files_sd1_sd2_inpaint():
    sd1 = {"cond_stage_model.transformer.text_model.x": [1], "model.diffusion_model.input_blocks.0.0.weight": [320, 4, 3, 3]}
    assert registry.detect_from_single_file(_header(sd1), "dreamshaper.safetensors")[:2] == ("sd15", "single_full")
    inpaint = dict(sd1, **{"model.diffusion_model.input_blocks.0.0.weight": [320, 9, 3, 3]})
    assert registry.detect_from_single_file(_header(inpaint), "x.safetensors")[0] == "sd15_inpaint"
    sd2 = {"cond_stage_model.model.ln_final.weight": [1024], "model.diffusion_model.input_blocks.0.0.weight": [320, 4, 3, 3]}
    assert registry.detect_from_single_file(_header(sd2), "v2-1_768-ema.safetensors")[0] == "sd21"
    assert registry.detect_from_single_file(_header(sd2), "v2-1_512-base.safetensors")[0] == "sd21_base"


def test_repos_sd1_sd2_inpaint():
    idx = {"_class_name": "StableDiffusionPipeline"}
    assert registry.detect_from_model_index(idx, {"cross_attention_dim": 768})[0] == "sd15"
    assert registry.detect_from_model_index(idx, {"cross_attention_dim": 1024, "sample_size": 96})[0] == "sd21"
    assert registry.detect_from_model_index(idx, {"cross_attention_dim": 1024, "sample_size": 64})[0] == "sd21_base"
    assert registry.detect_from_model_index({"_class_name": "StableDiffusionInpaintPipeline"})[0] == "sd15_inpaint"


def test_lora_family_from_the_cross_attention_width():
    def shapes(ctx):
        return {"lora_unet_down_blocks_0_attentions_0_transformer_blocks_0_attn2_to_k.lora_down.weight": [8, ctx],
                "lora_unet_down_blocks_0_attentions_0_transformer_blocks_0_attn2_to_k.lora_up.weight": [320, 8]}
    assert registry._unet_lora_family(shapes(768)) == "sd1"
    assert registry._unet_lora_family(shapes(1024)) == "sd2"
    assert registry._unet_lora_family(shapes(2048)) == "sdxl"
    assert registry._unet_lora_family({"lora_te_text_model_x.lora_down.weight": [8, 768]}) == "sd1"


def test_ckpt_is_read_without_running_code(tmp_path):
    torch = pytest.importorskip("torch")
    good = tmp_path / "m.ckpt"
    torch.save({"state_dict": {"a.weight": torch.ones(2, 2)}, "epoch": 3}, good)
    out = tmp_path / "m.safetensors"
    importer.ckpt_to_safetensors(str(good), str(out))
    assert registry.read_safetensors_header(str(out)) == {"a.weight": [2, 2]}

    class Evil:
        def __reduce__(self):
            return (print, ("this must not run",))
    bad = tmp_path / "bad.ckpt"
    torch.save({"state_dict": {"a": torch.ones(1)}, "x": Evil()}, bad)
    with pytest.raises(registry.UnsupportedModel):
        importer.ckpt_to_safetensors(str(bad), str(tmp_path / "bad.safetensors"))


def test_sd15_fits_8_gb_and_downloads_without_safety_checker():
    spec = registry.ARCHS["sd15"]
    assert memory.plan(dict(spec["fallback_params"]), "unet", "sd1", 8)["fits"]
    files = ["model_index.json", "safety_checker/model.fp16.safetensors", "safety_checker/config.json",
             "unet/diffusion_pytorch_model.fp16.safetensors", "unet/diffusion_pytorch_model.safetensors",
             "unet/diffusion_pytorch_model.non_ema.safetensors", "unet/config.json",
             "text_encoder/model.fp16.safetensors", "text_encoder/model.safetensors",
             "vae/diffusion_pytorch_model.fp16.safetensors", "vae/diffusion_pytorch_model.safetensors"]
    index = {"_class_name": "StableDiffusionPipeline", "safety_checker": ["stable_diffusion", "StableDiffusionSafetyChecker"],
             "unet": ["diffusers", "UNet2DConditionModel"], "text_encoder": ["transformers", "CLIPTextModel"],
             "vae": ["diffusers", "AutoencoderKL"]}
    wanted, variant = importer._repo_plan_files(files, index)
    assert variant == "fp16"
    assert not any(f.startswith("safety_checker/") for f in wanted)
    assert not any("non_ema" in f for f in wanted)
    assert [f for f in wanted if f.endswith(".safetensors")] == [
        "text_encoder/model.fp16.safetensors", "unet/diffusion_pytorch_model.fp16.safetensors",
        "vae/diffusion_pytorch_model.fp16.safetensors"]


def test_controlnets_for_sd15():
    import controlnet
    assert controlnet.types_for("sd15", "sd1") == ["BodyPose", "Depth", "Canny", "LineArt", "Scribble", "Illusion"]
    assert controlnet.types_for("sd15_inpaint", "sd1") == []
    spec = controlnet.resolve("sd15", "sd1", "Depth")
    assert spec["pipeline"] == "StableDiffusionControlNetPipeline" and spec["control_arg"] == "image"
    # the 16 bit file, stored under the name diffusers loads
    assert spec["remote_files"]["diffusion_pytorch_model.fp16.safetensors"] == "diffusion_pytorch_model.safetensors"
    assert controlnet.resolve("sd15", "sd1", "Illusion")["repo"] == "monster-labs/control_v1p_sd15_qrcode_monster"
    with pytest.raises(ValueError):
        controlnet.resolve("sd15", "sd1", "Tile")




def test_sd21_plan_matches_its_measured_peak():
    # MEASUREMENTS 7cr: SD 2.1 at 768², 5.8 GB in every picture on a Mac mini M4
    p = memory.plan({"text_encoder": 0.34, "unet": 0.866, "vae": 0.084}, "unet", "sd2", 16)
    assert p["activations_side"] == 768 and 5.6 <= p["est_peak_gb"] <= 6.0
