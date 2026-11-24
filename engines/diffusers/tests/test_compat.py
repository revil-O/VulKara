# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""The Intel build's older packages (compat.py): no quanto plans, no pickles of the user's below PyTorch 2.6, and the
dtype= the engine writes reaching diffusers."""
import importlib.metadata as md

import pytest

import compat
import memory
import registry


def test_without_quanto_every_plan_is_16_bit(monkeypatch):
    monkeypatch.setattr(compat, "QUANTO", False)
    for arch, spec in registry.ARCHS.items():
        for ram in (8, 16, 64):
            for quant in ("auto", "q8", "q4"):
                p = memory.plan(spec["fallback_params"], spec["denoiser"], spec["family"], ram, quant=quant)
                assert set(p["quant"].values()) <= {"none", "gguf"}, (arch, ram, quant, p)


@pytest.mark.parametrize("torch_version, safe", [("2.2.2", False), ("2.5.1", False), ("2.6.0", True), ("2.14.1+cpu", True)])
def test_pickles_only_from_pytorch_2_6(monkeypatch, torch_version, safe):
    real = md.version
    monkeypatch.setattr(md, "version", lambda p: torch_version if p == "torch" else real(p))
    assert compat.pickle_safe() is safe
    if safe:
        compat.refuse_pickle("/x/model.ckpt")
    else:
        with pytest.raises(ValueError, match="model.ckpt.*safetensors"):
            compat.refuse_pickle("/x/model.ckpt")


def test_the_engine_dtype_reaches_diffusers():
    import torch
    from diffusers import UNet2DConditionModel
    unet = UNet2DConditionModel(block_out_channels=(32, 64), layers_per_block=1, sample_size=8, cross_attention_dim=32,
                                down_block_types=("CrossAttnDownBlock2D", "DownBlock2D"),
                                up_block_types=("UpBlock2D", "CrossAttnUpBlock2D"), attention_head_dim=4)
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        unet.save_pretrained(d)
        assert UNet2DConditionModel.from_pretrained(d, dtype=torch.float16).dtype == torch.float16


def test_on_the_cpu_the_reserve_is_1_gb_so_sd15_fits_8_gb_unstreamed(monkeypatch):
    # an Intel Mac with 8 GB: SD 1.5 ran 2.6 times as fast held in memory as streamed (plans/INTEL_MACHBARKEIT.md)
    monkeypatch.setattr(compat, "cpu_only", lambda: True)
    monkeypatch.delenv("VK_MEMORY_RESERVE_GB", raising=False)
    assert memory.budget_gb(8) == pytest.approx(6.4)
    monkeypatch.setattr(compat, "cpu_only", lambda: False)
    assert memory.budget_gb(8) == pytest.approx(4.0)


@pytest.mark.parametrize("torch_version", ["2.2.2", "2.14.1"])
def test_on_pytorch_2_2_only_sd_and_sdxl_are_imported(monkeypatch, torch_version):
    # FLUX and newer need torch.nn.RMSNorm: refused before the download, not at the first picture
    real = md.version
    monkeypatch.setattr(md, "version", lambda p: torch_version if p == "torch" else real(p))
    old = torch_version.startswith("2.2")
    for arch, spec in registry.ARCHS.items():
        if spec.get("packages"):
            continue  # their own minimums (Qwen-Image 2.1)
        message = registry.runtime_too_old(arch)
        if old and spec["family"] not in ("sd1", "sd2", "sdxl"):
            assert message and "PyTorch 2.4" in message, arch
        else:
            assert message is None, (arch, message)


@pytest.mark.parametrize("transformers_version, dropped", [("4.57.6", True), ("5.10.0", False)])
def test_chat_templates_are_dropped_before_saving_on_old_transformers(monkeypatch, transformers_version, dropped):
    import types
    real = md.version
    monkeypatch.setattr(md, "version", lambda p: transformers_version if p == "transformers" else real(p))
    tok = types.SimpleNamespace(chat_template={"../../escape": "x"})
    pipe = types.SimpleNamespace(components={"tokenizer": tok, "unet": object(), "scheduler": None})
    compat.drop_chat_templates(pipe)
    assert (tok.chat_template is None) == dropped


@pytest.mark.parametrize("diffusers_version, refused", [("0.35.2", True), ("0.38.0", False)])
def test_a_folder_with_python_files_is_refused_on_old_diffusers(monkeypatch, tmp_path, diffusers_version, refused):
    real = md.version
    monkeypatch.setattr(md, "version", lambda p: diffusers_version if p == "diffusers" else real(p))
    (tmp_path / "unet").mkdir()
    (tmp_path / "unet" / "config.json").write_text("{}")
    compat.refuse_code(str(tmp_path))  # no Python file: fine on every version
    (tmp_path / "None.py").write_text("print('owned')")
    if refused:
        with pytest.raises(ValueError, match="Python files"):
            compat.refuse_code(str(tmp_path))
    else:
        compat.refuse_code(str(tmp_path))


def test_the_intel_build_is_told_by_the_cpu_not_by_installed_packages():
    """The MLX and ComfyUI runtimes have no optimum-quanto: on Apple chips they keep their 8/4-bit plans."""
    import platform
    intel = platform.machine() == "x86_64"
    assert compat.QUANTO is not intel and compat.cpu_only() is intel


def test_the_reserve_check_does_not_load_pytorch():
    """The MLX engine imports memory.py and has no use for PyTorch."""
    import os
    import subprocess
    import sys
    code = "import sys, memory; memory._min_reserve(); print('torch' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


def test_python_files_in_any_case_and_behind_links_are_found(monkeypatch, tmp_path):
    real = md.version
    monkeypatch.setattr(md, "version", lambda p: "0.35.2" if p == "diffusers" else real(p))
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "loop").symlink_to(tmp_path)  # a link loop must end
    compat.refuse_code(str(tmp_path))
    (tmp_path / "x" / "evil.PY").write_text("print('owned')")
    model = tmp_path / "model"
    model.mkdir()
    (model / "unet").symlink_to(tmp_path / "x")
    with pytest.raises(ValueError, match="Python files"):
        compat.refuse_code(str(model))


@pytest.mark.skipif(compat._version("diffusers") >= (0, 36), reason="install() wraps the loaders on the Intel set only")
def test_the_intel_build_loads_no_pickle_weights_and_no_folder_with_code(monkeypatch, tmp_path):
    from diffusers import UNet2DConditionModel
    unet = UNet2DConditionModel(block_out_channels=(32, 64), layers_per_block=1, sample_size=8, cross_attention_dim=32,
                                down_block_types=("CrossAttnDownBlock2D", "DownBlock2D"),
                                up_block_types=("UpBlock2D", "CrossAttnUpBlock2D"), attention_head_dim=4)
    unet.save_pretrained(tmp_path, safe_serialization=False)  # diffusion_pytorch_model.bin only
    monkeypatch.setattr(compat, "pickle_safe", lambda: False)
    with pytest.raises(OSError):
        UNet2DConditionModel.from_pretrained(str(tmp_path))
    unet.save_pretrained(tmp_path)
    UNet2DConditionModel.from_pretrained(str(tmp_path))  # safetensors load
    (tmp_path / "helper.py").write_text("print('owned')")
    with pytest.raises(ValueError, match="Python files"):
        UNet2DConditionModel.from_pretrained(str(tmp_path))
