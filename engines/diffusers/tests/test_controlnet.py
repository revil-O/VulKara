# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
import pytest

import controlnet
import memory


def test_types_per_model():
    assert "BodyPose" in controlnet.types_for("sdxl", "sdxl")
    assert "Tile" in controlnet.types_for("sdxl", "sdxl")
    assert "Tile" not in controlnet.types_for("flux1_dev", "flux1")
    assert controlnet.types_for("flux2_klein", "flux2") == []
    assert controlnet.types_for("sd35_medium", "sd3") == ["Depth", "Canny"]
    assert controlnet.types_for("sd35_large", "sd3") == ["Depth", "Canny", "Tile"]


def test_the_room_for_a_controlnet_follows_the_picture_size():
    """FLUX.1 [schnell] Q8 on 24 GB (its plan): at 1024² the ControlNet's activations (half the model's, MEASUREMENTS
    7as) leave 2.45 GB, enough for the ControlNet in 8 bit (2.15 GB); at 512 × 768 the activations are 3/8 of that."""
    import types
    engine = pytest.importorskip("engine")
    m = types.SimpleNamespace(plan={"budget_gb": 19.2, "denoise_peak_gb": 15.5, "est_peak_gb": 15.5, "activations_gb": 2.5}, controlnet=None)
    room = engine.LoadedModel.controlnet_room
    assert room(m, 1024, 1024) == pytest.approx(19.2 - 15.5 - 1.25)
    assert room(m, 512, 768) == pytest.approx(19.2 - (15.5 - 2.5 + 0.9375) - 0.46875)
    assert room(m, 512, 768) > room(m, 1024, 1024) > 2.15
    # never below a quarter of the activations
    assert room(m, 64, 64) == pytest.approx(room(m, 512, 512))
    # in stages the ControlNet stays loaded while the prompt is encoded: the room is next to that peak too
    m.plan["est_peak_gb"] = 18.0
    assert room(m, 512, 512) == pytest.approx(19.2 - 18.0)
    # what a loaded ControlNet adds to the job's peak: its weights and its activations
    assert engine.LoadedModel.controlnet_gb(m, 1024, 1024) == 0.0
    m.controlnet = ("id", None, 2.15)
    assert engine.LoadedModel.controlnet_gb(m, 1024, 1024) == pytest.approx(2.15 + 1.25)


def test_union_models_are_shared_per_family():
    a = controlnet.resolve("flux1_dev", "flux1", "BodyPose")
    b = controlnet.resolve("flux1_schnell", "flux1", "Depth")
    assert a["id"] == b["id"]


def test_sd3_has_a_model_per_type():
    depth = controlnet.resolve("sd35_medium", "sd3", "Depth")
    canny = controlnet.resolve("sd35_medium", "sd3", "Canny")
    assert depth["id"] != canny["id"]
    assert depth["class"] == "SD3ControlNetModel" and depth["img2img_pipeline"] is None
    kw = controlnet.call_kwargs(depth, "Depth", 0.7, "img", "sd3")
    assert kw == {"controlnet_conditioning_scale": 0.7, "control_guidance_end": 1.0, "control_image": "img"}


def test_sdxl_union_kwargs():
    spec = controlnet.resolve("sdxl", "sdxl", "BodyPose")
    kw = controlnet.call_kwargs(spec, "BodyPose", 0.8, "img", "sdxl")
    assert kw["control_image"] == ["img"]
    assert kw["control_mode"] == [0]
    assert kw["controlnet_conditioning_scale"] == pytest.approx(0.8)
    assert controlnet.call_kwargs(spec, "Canny", 1, "img", "sdxl")["control_mode"] == [3]


def test_flux_kwargs_use_recommended_tuning():
    spec = controlnet.resolve("flux1_dev", "flux1", "BodyPose")
    kw = controlnet.call_kwargs(spec, "BodyPose", 1.0, "img", "flux1")
    assert kw["control_image"] == "img"
    assert "control_mode" not in kw
    assert kw["controlnet_conditioning_scale"] == pytest.approx(0.9)
    assert kw["control_guidance_end"] == pytest.approx(0.65)


def test_unknown_type_is_rejected():
    with pytest.raises(ValueError, match="Available"):
        controlnet.resolve("flux1_dev", "flux1", "Tile")
    with pytest.raises(ValueError, match="Available: Depth, Canny"):
        controlnet.resolve("sd35_medium", "sd3", "BodyPose")
    with pytest.raises(ValueError, match="not available"):
        controlnet.resolve("flux2_klein", "flux2", "Depth")


def test_plan_reports_denoise_peak():
    p = memory.plan({"transformer": 12.0, "text_encoder": 0.12, "text_encoder_2": 4.7, "vae": 0.08},
                    "transformer", "flux1", 24, denoiser_fixed_gb=12.7)
    assert p["fits"]
    assert p["staged_text_encoder"]
    # staged: the text encoders are not resident while denoising
    assert p["denoise_peak_gb"] < p["est_peak_gb"]
    assert p["budget_gb"] == pytest.approx(memory.budget_gb(24), abs=0.1)
