# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Models trained to fill a mask (SDXL inpainting, FLUX.1 Fill) and FLUX.2 [klein]'s inpainting pipeline
(MEASUREMENTS 7bf): detection, and existing klein manifests learn that they can inpaint."""
import importer
import recheck
import registry


def test_sdxl_inpainting_by_its_nine_channel_unet():
    sdxl = {"conditioner.embedders.1.model.ln_final.weight": [1280],
            "model.diffusion_model.input_blocks.0.0.weight": [320, 4, 3, 3]}
    assert registry.detect_from_single_file(sdxl, "juggernaut.safetensors")[:2] == ("sdxl", "single_full")
    inpaint = dict(sdxl, **{"model.diffusion_model.input_blocks.0.0.weight": [320, 9, 3, 3]})
    assert registry.detect_from_single_file(inpaint, "realvisxl-inpainting.safetensors")[:2] == ("sdxl_inpaint", "single_full")
    assert registry.detect_from_model_index({"_class_name": "StableDiffusionXLInpaintPipeline"})[0] == "sdxl_inpaint"
    assert registry.detect_from_model_index({"_class_name": "StableDiffusionXLPipeline"}, {"in_channels": 9})[0] == "sdxl_inpaint"
    assert registry.detect_from_model_index({"_class_name": "StableDiffusionXLPipeline"}, {"in_channels": 4})[0] == "sdxl"
    assert registry.ARCHS["sdxl_inpaint"]["max_strength"] == 0.99  # its card: degraded at 1


def test_flux1_fill_by_its_input_layer():
    def flux(in_dim, gguf=False):
        return {"double_blocks.0.img_attn.qkv.weight": [9216, 3072], "single_blocks.0.linear1.weight": [21504, 3072],
                "guidance_in.in_layer.weight": [3072, 256], "img_in.weight": [in_dim, 3072] if gguf else [3072, in_dim]}
    assert registry.detect_from_single_file(flux(64), "flux1-dev.safetensors")[0] == "flux1_dev"
    assert registry.detect_from_single_file(flux(384), "flux1-fill-dev.safetensors")[0] == "flux1_fill"
    assert registry.detect_from_single_file(flux(384, gguf=True), "flux1-fill-dev-Q8_0.gguf")[0] == "flux1_fill"
    assert registry.detect_from_model_index({"_class_name": "FluxFillPipeline"})[0] == "flux1_fill"
    assert importer._guess_from_name("FLUX.1-Fill-dev-Q4_K_S.gguf")[0] == "flux1_fill"
    spec = registry.ARCHS["flux1_fill"]
    assert spec["inpaint_only"] and spec["defaults"]["guidance_scale"] == 30.0
    assert not spec.get("fp16_compute")  # NaN in float16 at 1024 px


def test_flux1_fill_makes_room_for_a_new_prompt_on_16_gb():
    # a new prompt took 11.9-12.6 GB against a plan of 10.6 with the transformer resident (Mac mini, 7bf)
    import memory
    spec = registry.ARCHS["flux1_fill"]
    p = memory.fitting_plan(spec["fallback_params"], "transformer", "flux1", 16, denoiser_fixed_gb=6.8,
                            encode_extra_gb=spec["encode_extra_gb"])
    assert p["fits"] and p["releases_denoiser"]
    assert not memory.fitting_plan(spec["fallback_params"], "transformer", "flux1", 16,
                                   denoiser_fixed_gb=6.8).get("releases_denoiser")


def test_klein_manifests_learn_that_they_inpaint():
    m = {"arch": "flux2_klein", "layout": "repo", "inpaint": False, "sub_base": "klein4b"}
    assert recheck.model_changes("/nowhere", m)["inpaint"] == (False, True)
    assert "inpaint" not in recheck.model_changes("/nowhere", dict(m, inpaint=True))
    assert "inpaint" not in recheck.model_changes("/nowhere", dict(m, arch="flux2_dev"))


def test_klein_inpainting_counts_the_reference_tokens():
    # the picture goes along as reference tokens: one more set of activations (12.2-13.7 GB against 9.8, 7bf)
    import memory
    assert registry.ARCHS["flux2_klein"]["inpaint_reference"]
    plan = {"denoise_peak_gb": 8.2, "est_peak_gb": 9.5, "activations_gb": 3.0}
    extra = memory.activations_at(plan, 1024, 1024)[1]
    assert memory.peak_at(plan, 1024, 1024, extra) == 8.2 + 3.0


def test_every_flux2_edit_with_a_picture_counts_the_reference_tokens():
    # Restore's repair hands klein the photo without a mask: 12.5-13.0 GB against a plan of 9.8 (7bh)
    import engine
    plan = {"denoise_peak_gb": 8.2, "est_peak_gb": 9.5, "activations_gb": 3.0}
    klein, sdxl = registry.ARCHS["flux2_klein"], registry.ARCHS["sdxl"]
    assert engine.reference_gb(klein, plan, 1024, 1024, picture=True, masked=False) == 3.0
    assert engine.reference_gb(klein, plan, 1024, 1024, picture=True, masked=True) == 3.0
    assert engine.reference_gb(registry.ARCHS["flux2_dev"], plan, 1024, 1024, picture=True, masked=False) == 3.0
    assert engine.reference_gb(klein, plan, 1024, 1024, picture=False, masked=False) == 0.0
    assert engine.reference_gb(sdxl, plan, 1024, 1024, picture=True, masked=False) == 0.0  # img2img: no tokens


def test_a_gated_base_without_a_token_asks_for_the_token(monkeypatch):
    # FLUX.1 Fill's licence was accepted, the app had no token: the message asked to accept the licence (2026-11-04)
    import huggingface_hub
    import pytest
    from huggingface_hub.utils import GatedRepoError

    def gated(repo, token=None):
        e = GatedRepoError.__new__(GatedRepoError)
        Exception.__init__(e, "gated")
        raise e
    monkeypatch.setattr(huggingface_hub, "auth_check", gated)
    with pytest.raises(PermissionError, match="needs an access token"):
        importer._check_base_access("black-forest-labs/FLUX.1-Fill-dev", None)
    with pytest.raises(PermissionError, match="Accept its licence"):
        importer._check_base_access("black-forest-labs/FLUX.1-Fill-dev", "hf_x")
