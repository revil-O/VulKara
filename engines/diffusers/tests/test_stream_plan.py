# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""The import plan counts SSD streaming as the engine does: a model too large for the memory still fits when its
denoiser can stream (a GGUF one in 16 bit, unpacked once)."""
import importer

FLUX1 = {"arch": "flux1_dev", "layout": "repo", "denoiser": "transformer",
         "components": {"transformer": 11.9, "text_encoder": 0.12, "text_encoder_2": 4.76, "vae": 0.08}}


def test_a_16_bit_model_too_large_for_16_gb_fits_streamed(monkeypatch):
    monkeypatch.delenv("VK_SSD_STREAMING", raising=False)
    plan = importer.make_plan(FLUX1, ram_gb=16)
    assert plan["fits"] and plan["streamed"] and plan["quant"]["transformer"] == "none"


def test_a_gguf_file_too_large_for_16_gb_fits_streamed_and_nothing_streams_when_it_is_off(monkeypatch):
    monkeypatch.delenv("VK_SSD_STREAMING", raising=False)
    gguf = dict(FLUX1, layout="single_denoiser", denoiser_fixed_gb=12.7)  # an 8 bit FLUX.1 [dev] fine-tune (from FP8)
    plan = importer.make_plan(gguf, ram_gb=16)
    assert plan["fits"] and plan["streamed"] and plan["quant"]["transformer"] == "none"
    monkeypatch.setenv("VK_SSD_STREAMING", "off")
    assert not importer.make_plan(FLUX1, ram_gb=16)["fits"]
    assert not importer.make_plan(gguf, ram_gb=16)["fits"]


def test_a_model_that_fits_is_not_streamed(monkeypatch):
    monkeypatch.delenv("VK_SSD_STREAMING", raising=False)
    plan = importer.make_plan(FLUX1, ram_gb=24)
    assert plan["fits"] and not plan.get("streamed")


def test_a_civitai_16_bit_file_that_does_not_fit_is_streamed(monkeypatch):
    # FLUX.1 [dev] fine-tune as one 16 bit file on a 16 GB Mac: the import check counts on SSD streaming, as the engine
    # does
    import importer
    import registry
    spec = registry.ARCHS["flux1_dev"]
    info = {"arch": "flux1_dev", "components": spec["fallback_params"], "denoiser": spec["denoiser"],
            "layout": "single_denoiser", "denoiser_fixed_gb": None}
    plan = importer.make_plan(info, ram_gb=16)
    assert plan["fits"] and plan.get("streamed")
    assert importer.make_plan(dict(info, denoiser_fixed_gb=11.8), ram_gb=16).get("streamed")  # its GGUF file too



def test_a_streamed_model_keeps_what_the_memory_plan_allows():
    import engine
    import memory
    comps = {"text_encoder": 0.1, "text_encoder_2": 4.8, "transformer": 11.9, "vae": 0.1}  # FLUX.1 [dev]
    full_gb = memory._gb(11.9, "none")
    resident = memory.stream_resident_share("flux")
    for ram, low, high in ((16, 0.05, 0.35), (24, 0.3, 0.8)):
        streamed = dict(comps, transformer=comps["transformer"] * resident)
        plan = memory.plan(streamed, "transformer", "flux", ram)
        keep, kept_plan, release = engine.keep_plan(comps, "transformer", "flux", ram, plan)
        assert low <= keep <= high, (ram, keep)
        assert kept_plan["fits"] and kept_plan["quant"]["transformer"] == "none"
        assert kept_plan["quant"]["text_encoder_2"] in ("none", "q8")  # never 4 bit for it
        share = keep + resident + engine.STREAM_KEEP_MARGIN
        if release:  # 16 GB: the text encoder is staged and gets the kept blocks' room; denoising fits with them
            assert ram == 16 and kept_plan["staged_text_encoder"]
            assert plan["denoise_peak_gb"] + full_gb * (share - resident) <= plan["budget_gb"]
            # and the plan the job reports counts them while denoising
            assert kept_plan["denoise_peak_gb"] == round(plan["denoise_peak_gb"] + full_gb * (share - resident), 1)
            assert kept_plan["est_peak_gb"] >= kept_plan["denoise_peak_gb"] > plan["denoise_peak_gb"]
        else:  # with the margin given back it still fits: kept + in flight + margin <= what the plan allowed
            assert memory.plan(comps, "transformer", "flux", ram, denoiser_fixed_gb=full_gb * share)["fits"]


def test_flux2_counts_its_large_double_blocks_in_flight():
    import memory
    # klein 9B streamed on 16 GB: five 0.87 GB double blocks in flight (MEASUREMENTS 7ac), more than the usual 15 %
    assert memory.stream_resident_share("flux2") * memory._gb(9.08, "none") >= 4.3
    assert memory.stream_resident_share("qwen_image") == 0.15
