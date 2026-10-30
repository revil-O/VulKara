# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
import memory
import registry


def plan(arch, ram, **kw):
    spec = registry.ARCHS[arch]
    return memory.plan(spec["fallback_params"], spec["denoiser"], spec["family"], ram, **kw)


def test_sdxl_fits_everywhere_unquantized():
    for ram in (16, 24, 64):
        p = plan("sdxl", ram)
        assert p["fits"] and p["quant"]["unet"] == "none" and not p["staged_text_encoder"]


def test_flux1_on_24gb_is_quantized_and_fits():
    p = plan("flux1_schnell", 24)
    assert p["fits"]
    assert p["quant"]["transformer"] in ("q8", "q4")
    assert p["est_peak_gb"] <= memory.budget_gb(24)


def test_flux1_on_64gb_full_precision():
    p = plan("flux1_dev", 64)
    assert p["fits"] and p["quant"]["transformer"] == "none"


def test_flux2_dev_rejected_on_24gb():
    p = plan("flux2_dev", 24)
    assert not p["fits"] and p["min_ram_gb"] > 24
    assert plan("flux2_dev", 64, quant="q4")["fits"]  # 4 bit must be chosen explicitly
    assert plan("flux2_dev", 96)["fits"]


def test_flux2_klein_fits_16gb():
    assert plan("flux2_klein", 16)["fits"]


def test_gguf_denoiser_size_is_fixed():
    spec = registry.ARCHS["flux1_schnell"]
    p = memory.plan(spec["fallback_params"], "transformer", "flux1", 24, denoiser_fixed_gb=6.8)
    assert p["fits"] and p["quant"]["transformer"] == "gguf"


def test_forced_quant():
    p = plan("sdxl", 64, quant="q8")
    assert p["quant"]["unet"] == "q8"


def test_flux1_gguf_q8_fits_24gb_with_quantized_t5():
    spec = registry.ARCHS["flux1_dev"]
    p = memory.plan(spec["fallback_params"], "transformer", "flux1", 24, denoiser_fixed_gb=12.7)
    assert p["fits"] and p["quant"]["text_encoder_2"] in ("q8", "q4")


def test_budget_reserve():
    assert memory.budget_gb(16) == 12
    assert abs(memory.budget_gb(64) - 51.2) < 1e-6
    assert memory.budget_gb(memory.ram_needed_gb(20)) >= 20 - 1e-9


def test_auto_never_picks_quanto_4bit():
    for arch in registry.ARCHS:
        spec = registry.ARCHS[arch]
        for ram in (8, 16, 24, 48, 96):
            p = memory.plan(spec["fallback_params"], spec["denoiser"], spec["family"], ram)
            assert "q4" not in p["quant"].values(), (arch, ram, p)


def test_sdxl_vae_stays_in_bfloat16_when_it_encodes_a_picture():
    # img2img / inpaint would move it to float32 and back for every picture (force_upcast); bfloat16 has the range
    import torch
    from diffusers import AutoencoderKL

    import engine
    vae = AutoencoderKL(block_out_channels=(8,), norm_num_groups=8, latent_channels=4, force_upcast=True)
    vae.to(torch.float16)
    engine._bf16_vae(vae)
    assert vae.dtype == torch.bfloat16 and not vae.config.force_upcast
    latents = vae.encode(torch.zeros(1, 3, 16, 16, dtype=torch.float16)).latent_dist.mode()
    assert latents.dtype == torch.bfloat16 and vae.dtype == torch.bfloat16
    engine._bf16_vae(vae)  # a second time changes nothing
    assert vae.encode(torch.zeros(1, 3, 16, 16, dtype=torch.float16)).latent_dist.mode().dtype == torch.bfloat16


def test_benchmarks_learn_the_bit_size_of_a_weights_file(tmp_path):
    import json as _json
    import struct

    def safetensors(name, dtypes):
        header = {"w%d" % i: {"dtype": d, "shape": [1], "data_offsets": [0, 1]} for i, d in enumerate(dtypes)}
        data = _json.dumps(header).encode()
        (tmp_path / name).write_bytes(struct.pack("<Q", len(data)) + data + b"\0")
        return str(tmp_path / name)

    assert registry.file_precision(safetensors("fp8.safetensors", ["F8_E4M3", "F32"])) == "8 bit (FP8)"
    assert registry.file_precision(safetensors("bf16.safetensors", ["BF16", "F32"])) == "16 bit"
    assert registry.file_precision(str(tmp_path / "missing.gguf")) == "?"
    import protocol
    sent = []
    protocol.event, old = (lambda name, **f: sent.append((name, f))), protocol.event
    try:
        protocol.precision([("transformer", "8 bit"), ("text_encoder_2", "16 bit")])
    finally:
        protocol.event = old
    assert sent == [("precision", {"message": "transformer 8 bit, text encoder 2 16 bit"})]


def test_benchmarks_get_the_plans_peak_at_the_pictures_size():
    p = memory.plan({"transformer": 6.0, "text_encoder": 4.0, "vae": 0.08}, "transformer", "z_image", 48)
    assert memory.peak_at(p, 1024, 1024) == p["est_peak_gb"]
    # a quarter of the pixels: a quarter of the activations; smaller still counts as a quarter
    assert abs(memory.peak_at(p, 512, 512) - (p["denoise_peak_gb"] - 0.75 * p["activations_gb"])) < 1e-9
    assert memory.peak_at(p, 256, 256) == memory.peak_at(p, 512, 512)
    # staged (the text encoder only for encoding): encoding both may be the peak, whatever the size
    staged = memory.plan({"transformer": 6.0, "text_encoder": 4.0, "vae": 0.08}, "transformer", "z_image", 24)
    assert staged["est_peak_gb"] > staged["denoise_peak_gb"] and memory.peak_at(staged, 512, 512) == staged["est_peak_gb"]


def test_the_engines_measure_their_own_footprint_over_a_job():
    import mmap
    import protocol
    sent = []
    protocol.event, old = (lambda name, **f: sent.append((name, f))), protocol.event
    try:
        fp = protocol.Footprint()
        fp.start()
        protocol.planned(3.456)
        m = mmap.mmap(-1, 300 * 1024 * 1024)
        for i in range(0, len(m), 16384):
            m[i] = 1
        fp.report()
        m.close()
    finally:
        protocol.event = old
    name, f = sent[0]
    assert name == "footprint" and f["peak_gb"] >= 0.29 and f["plan_gb"] == 3.46 and f["read_gb"] >= 0


def test_attention_with_a_head_size_mps_does_not_fuse_is_padded_to_the_same_result():
    import pytest
    torch = pytest.importorskip("torch")
    if not torch.backends.mps.is_available():
        pytest.skip("needs MPS")
    import torch.nn.functional as F
    import engine
    q, k, v = (torch.randn(2, 8, 1024, 40, device="mps", dtype=torch.float16) for _ in range(3))
    plain = F.scaled_dot_product_attention(q, k, v)
    engine.fused_attention()
    padded = F.scaled_dot_product_attention(q, k, v)
    assert getattr(F.scaled_dot_product_attention, "vk_padded", False) and padded.shape == plain.shape
    assert (padded - plain).abs().max().item() < 1e-3


def test_qwen_image21_runs_in_stages_on_16gb_instead_of_streaming():
    comps = {"text_encoder": 8.77, "transformer": 7.12, "vae": 0.34}  # Qwen-Image 2.1
    assert not memory.plan(comps, "transformer", "qwen_image21", 16)["fits"]  # the engine streamed it before (7s, 7w)
    p = memory.fitting_plan(comps, "transformer", "qwen_image21", 16)
    assert p["fits"] and p["releases_denoiser"] and p["staged_text_encoder"]
    assert p["quant"] == {"transformer": "q8", "text_encoder": "q8"}
    # bigger Macs keep the denoiser while encoding; a plan that fits as it is stays as it is
    assert not memory.fitting_plan(comps, "transformer", "qwen_image21", 24).get("releases_denoiser")
    sdxl = {"unet": 2.6, "text_encoder": 0.8, "vae": 0.1}
    assert memory.fitting_plan(sdxl, "unet", "sdxl", 16) == memory.plan(sdxl, "unet", "sdxl", 16)


def test_staging_that_frees_the_denoiser_still_counts_a_second_one():
    # Ideogram 4: encoding frees the transformer, its unconditional twin (4 B, 8 bit) stays loaded beside the encoder
    comps = {"transformer": 4.0, "unconditional_transformer": 4.0, "text_encoder": 12.0, "vae": 0.1}
    p = memory.plan(comps, "transformer", "ideogram4", 24, quant="q8", staging_frees_denoiser=True)
    assert p["staged_text_encoder"] and p["est_peak_gb"] >= p["text_gb"] + 4.0
