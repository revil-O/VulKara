# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
import profiles


def row(ram, model_id, bf16_native=True):
    return [r for r in profiles.recommendations(ram, bf16_native) if r["id"] == model_id][0]


def test_24gb_mac_runs_flux2_klein_9b_without_streaming():
    r = row(24, "flux2_klein_9b")
    # its text encoder in 4 bit lets the 8 bit model stay in memory (memory.fitting_plan) instead of streaming
    assert not r["diffusers"].get("streamed") and r["diffusers"]["mode"] == "model 8 bit, text encoder 4 bit"
    assert r["mlx"]["fits"] and r["mlx"]["mode"] == "model 4 bit" and r["mlx"]["side"] == 1024
    assert r["why"].startswith("both fit")
    assert not row(24, "flux2_dev")["diffusers"]["fits"]  # the text encoder alone is too big


def test_more_ram_means_less_quantization():
    assert row(16, "sdxl")["diffusers"]["mode"] == "model 16 bit"
    assert row(16, "flux1")["diffusers"].get("streamed")  # only as the SSD emergency mode
    assert row(32, "flux1")["mlx"]["mode"] == "model 8 bit"
    assert row(64, "flux1")["mlx"]["mode"] == "model 16 bit"
    assert row(24, "krea2")["mlx"]["mode"] == "model 4 bit"  # text encoder quantized too
    assert row(32, "krea2")["mlx"]["mode"] == "model 4 bit, text encoder 16 bit"
    assert not row(32, "flux2_dev")["mlx"]["fits"] and row(48, "flux2_dev")["mlx"]["fits"]


def test_float16_only_where_bfloat16_is_missing():
    assert row(24, "flux1", bf16_native=False)["diffusers"]["float16"]
    assert row(24, "flux2_klein_9b", bf16_native=False)["mlx"]["float16"]
    assert not row(24, "flux1", bf16_native=True)["diffusers"]["float16"]
    assert not row(24, "sdxl", bf16_native=False)["diffusers"]["float16"]


def test_tier_table_has_a_row_per_model():
    table = profiles.tiers_markdown((16, 24))
    assert table.count("\n") == len(profiles.MODELS) + 1
    # 16 GB (Mac mini M4): Krea 2 fits with its text encoder freed after the prompt
    assert "| Krea 2 | MLX: 4 bit, TE only for new prompts, 768 px | MLX: 4 bit, 1024 px |" in table
