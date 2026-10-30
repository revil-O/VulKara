# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""SSD streaming setting (VK_SSD_STREAMING = auto | always | off): when LoadedModel streams."""
import json

import pytest

import engine


def _model(tmp_path, transformer_gb):
    manifest = {
        "layout": "repo", "weights_dir": "weights", "engine": "diffusers", "arch": "flux2_klein",
        "denoiser": "transformer",
        "components": {"text_encoder": 3.0, "transformer": transformer_gb, "vae": 0.2},
        "quant_request": "auto",
    }
    (tmp_path / "model.json").write_text(json.dumps(manifest))
    return str(tmp_path)


@pytest.mark.parametrize("value, mode", [
    (None, "auto"), ("auto", "auto"), ("always", "always"), ("off", "off"),
    ("0", "off"), ("1", "always"), (" Always ", "always"), ("nonsense", "auto"),
])
def test_stream_mode_from_environment(monkeypatch, value, mode):
    if value is None:
        monkeypatch.delenv("VK_SSD_STREAMING", raising=False)
    else:
        monkeypatch.setenv("VK_SSD_STREAMING", value)
    assert engine.stream_mode() == mode


@pytest.mark.parametrize("mode, transformer_gb, streamed", [
    ("auto", 4, False),      # fits: loaded normally
    ("auto", 30, True),      # too large: emergency streaming
    ("always", 4, True),     # fits, streamed anyway
    ("always", 30, True),
])
def test_when_the_model_is_streamed(tmp_path, monkeypatch, mode, transformer_gb, streamed):
    monkeypatch.setenv("VK_SSD_STREAMING", mode)
    monkeypatch.setattr(engine.LoadedModel, "_check_stream_disk", lambda self: None)
    m = engine.LoadedModel(_model(tmp_path, transformer_gb), "cpu", ram_gb=24)
    assert m.stream is streamed
    assert m.plan["fits"]


def test_off_refuses_a_model_that_does_not_fit(tmp_path, monkeypatch):
    monkeypatch.setenv("VK_SSD_STREAMING", "off")
    with pytest.raises(MemoryError):
        engine.LoadedModel(_model(tmp_path, 60), "cpu", ram_gb=24)


def test_a_big_text_encoder_goes_to_4_bit_when_only_that_lets_the_model_stream(tmp_path, monkeypatch):
    # Qwen-Image 2.1 on a 16 GB Mac (Mac mini M4), streaming forced: its 8.8B text encoder in 8 bit leaves no room even
    # when the transformer streams; in 4 bit it fits
    monkeypatch.setenv("VK_SSD_STREAMING", "always")
    monkeypatch.setattr(engine.LoadedModel, "_check_stream_disk", lambda self: None)
    monkeypatch.setattr(engine.registry, "runtime_too_old", lambda arch: None)
    manifest = {
        "layout": "repo", "weights_dir": "weights", "engine": "diffusers", "arch": "qwen_image21",
        "denoiser": "transformer", "components": {"text_encoder": 8.767, "transformer": 7.115, "vae": 0.338},
        "quant_request": "auto",
    }
    (tmp_path / "model.json").write_text(json.dumps(manifest))
    m = engine.LoadedModel(str(tmp_path), "cpu", ram_gb=16)
    assert m.stream and m.plan["fits"] and not m.release_denoiser
    assert m.plan["quant"]["text_encoder"] == "q4"
    # left to the plan it runs in stages instead (7z): text encoder in 8 bit alone, then the transformer in 8 bit
    monkeypatch.setenv("VK_SSD_STREAMING", "auto")
    m = engine.LoadedModel(str(tmp_path), "cpu", ram_gb=16)
    assert not m.stream and m.release_denoiser and m.plan["fits"]
    assert m.plan["quant"] == {"transformer": "q8", "text_encoder": "q8"}
    # with enough memory the text encoder stays in 8 bit
    m = engine.LoadedModel(str(tmp_path), "cpu", ram_gb=24)
    assert m.plan["quant"]["text_encoder"] == "q8"


def test_a_stop_ends_the_one_time_streaming_preparation_at_the_next_block(tmp_path, monkeypatch):
    monkeypatch.setattr(engine.protocol, "status", lambda message: None)
    m = engine.LoadedModel(_model(tmp_path, 8), "cpu", ram_gb=24)
    report = m._stoppable("Preparing SSD streaming (one-time) %d%%")
    report(0, 10)  # no reader: runs to the end
    stopped = []
    m.stop = lambda: bool(stopped)
    report(1, 10)
    stopped.append(True)
    with pytest.raises(engine.StopRequested):
        report(2, 10)
