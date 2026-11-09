# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""The bfloat16 check is measured once per Mac and kept: on the M4 its timing flipped, and each flip wrote the stream
cache again (MEASUREMENTS 7bp)."""
import json

import pytest

import engine

torch = pytest.importorskip("torch")


def test_the_bf16_check_is_measured_once_per_chip(monkeypatch, tmp_path):
    runs = []
    monkeypatch.setattr(engine, "BF16_FILE", tmp_path / "bf16_check.json")
    monkeypatch.setattr(engine, "_chip", lambda: "Apple M4")
    monkeypatch.setattr(engine, "_bf16_timing", lambda device: runs.append(device) or True)
    monkeypatch.setattr(engine, "_BF16_SLOW", None)
    assert engine.bf16_is_slow("mps") and runs == ["mps"]
    assert json.loads((tmp_path / "bf16_check.json").read_text()) == {"chip": "Apple M4", "torch": torch.__version__, "slow": True}
    # a new engine process reads it back, whatever a timing would say now
    monkeypatch.setattr(engine, "_BF16_SLOW", None)
    monkeypatch.setattr(engine, "_bf16_timing", lambda device: runs.append(device) or False)
    assert engine.bf16_is_slow("mps") and runs == ["mps"]
    # another chip (a profile moved to another Mac) measures again
    monkeypatch.setattr(engine, "_BF16_SLOW", None)
    monkeypatch.setattr(engine, "_chip", lambda: "Apple M2")
    assert not engine.bf16_is_slow("mps") and runs == ["mps", "mps"]
    assert not engine.bf16_is_slow("cpu")
    # another torch measures again; a chip that could not be read is measured, never kept
    monkeypatch.setattr(engine, "_BF16_SLOW", None)
    monkeypatch.setattr(torch, "__version__", "9.9.9")
    assert not engine.bf16_is_slow("mps") and runs == ["mps", "mps", "mps"]
    monkeypatch.setattr(engine, "_BF16_SLOW", None)
    monkeypatch.setattr(engine, "_chip", lambda: "")
    (tmp_path / "bf16_check.json").unlink()
    assert not engine.bf16_is_slow("mps") and not (tmp_path / "bf16_check.json").exists()
