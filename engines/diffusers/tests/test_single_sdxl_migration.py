# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
import json
import os
import sys
import types

import importer

PARTS = ("unet", "vae", "text_encoder", "text_encoder_2")


def _model(tmp_path, file_at=None):
    d = tmp_path / "Model"
    (d / "base" / "unet").mkdir(parents=True)
    (d / "base" / "unet" / "config.json").write_text("{}")
    src = d / "model.safetensors"
    if file_at:
        file_at.write_bytes(b"w" * 10)
        os.symlink(file_at, src)
    else:
        src.write_bytes(b"w" * 10)
    m = {"layout": "single_full", "file": "model.safetensors", "file_format": "safetensors", "base_dir": "base",
         "sha256": "abc", "arch": "sdxl", "denoiser": "unet", "quant_request": "auto",
         "components": {"unet": 2.57, "text_encoder": 0.12, "text_encoder_2": 0.69, "vae": 0.08}}
    (d / "model.json").write_text(json.dumps(m))
    return d


def _fake_diffusers(monkeypatch, fail=False):
    calls = []

    class Pipe:
        @classmethod
        def from_single_file(cls, src, config, dtype, **kw):
            calls.append((src, config))
            return cls()

        def save_pretrained(self, out, safe_serialization):
            if fail:
                raise OSError("disk full")
            for c in PARTS:
                os.makedirs(os.path.join(out, c))
                open(os.path.join(out, c, "diffusion_pytorch_model.safetensors"), "wb").close()
            open(os.path.join(out, "model_index.json"), "w").write("{}")

    monkeypatch.setitem(sys.modules, "diffusers", types.SimpleNamespace(StableDiffusionXLPipeline=Pipe,
                                                                         StableDiffusionPipeline=Pipe))
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(float16="float16"))
    monkeypatch.setattr(importer, "free_bytes", lambda folder: 1024 ** 4)  # room, whatever the test disk has
    return calls


def test_an_sdxl_file_becomes_a_folder_and_the_file_goes(tmp_path, monkeypatch):
    d = _model(tmp_path)
    calls = _fake_diffusers(monkeypatch)
    seen = []
    assert importer.migrate_single_file(str(d), status=seen.append)
    m = json.loads((d / "model.json").read_text())
    assert (m["layout"], m["weights_dir"], m["variant"], m["sha256"]) == ("repo", "weights", None, "abc")
    assert "file" not in m and "base_dir" not in m and m["plan"]["min_ram_gb"] == m["min_ram_gb"]
    assert not (d / "model.safetensors").exists() and not (d / "base").exists()
    assert (d / "weights" / "unet" / "diffusion_pytorch_model.safetensors").is_file()
    assert calls == [(str(d / "model.safetensors"), str(d / "base"))]
    assert seen == ["Converting the model file to a folder (one-time)"]
    assert not importer.migrate_single_file(str(d))  # once


def test_a_failed_conversion_leaves_the_model_as_it_was(tmp_path, monkeypatch):
    d = _model(tmp_path)
    _fake_diffusers(monkeypatch, fail=True)
    before = (d / "model.json").read_text()
    assert not importer.migrate_single_file(str(d))
    assert (d / "model.json").read_text() == before and (d / "model.safetensors").is_file()
    assert not (d / "weights.partial").exists() and not (d / "weights").exists()


def test_a_conversion_stopped_before_the_manifest_is_done_again(tmp_path, monkeypatch):
    # the process ended after the folder was renamed but before model.json named it: the folder is redone
    d = _model(tmp_path)
    (d / "weights" / "unet").mkdir(parents=True)
    (d / "weights" / "unet" / "stale.bin").write_bytes(b"old")
    _fake_diffusers(monkeypatch)
    assert importer.migrate_single_file(str(d))
    assert not (d / "weights" / "unet" / "stale.bin").exists()
    assert (d / "weights" / "unet" / "diffusion_pytorch_model.safetensors").is_file()


def test_the_conversion_keeps_the_import_margin(tmp_path, monkeypatch):
    d = _model(tmp_path)
    _fake_diffusers(monkeypatch)
    size = (d / "model.safetensors").stat().st_size
    monkeypatch.setattr(importer, "free_bytes", lambda folder: size + 3 * 1024 ** 3)  # 3 GB over the file: too little
    assert not importer.migrate_single_file(str(d))
    assert json.loads((d / "model.json").read_text())["layout"] == "single_full"


def test_a_link_to_the_users_file_goes_but_the_file_stays(tmp_path, monkeypatch):
    own = tmp_path / "users_checkpoint.safetensors"
    d = _model(tmp_path, file_at=own)
    _fake_diffusers(monkeypatch)
    assert importer.migrate_single_file(str(d))
    assert not os.path.lexists(d / "model.safetensors") and own.is_file()


def test_other_models_are_not_touched(tmp_path, monkeypatch):
    d = _model(tmp_path)
    m = json.loads((d / "model.json").read_text())
    (d / "model.json").write_text(json.dumps({**m, "arch": "sd15"}))
    calls = _fake_diffusers(monkeypatch)
    assert not importer.migrate_single_file(str(d)) and calls == []


def _weights(path, dtype):
    import numpy as np
    from safetensors.numpy import save_file
    save_file({"w": np.ones((4, 4), dtype), "position_ids": np.arange(4, dtype=np.int64)}, str(path))


def test_a_32_bit_sd1_file_becomes_a_folder_a_16_bit_one_stays(tmp_path, monkeypatch):
    import numpy as np
    d = _model(tmp_path)
    m = json.loads((d / "model.json").read_text())
    m.update(arch="sd15", components={"unet": 0.86, "text_encoder": 0.12, "vae": 0.08})
    (d / "model.json").write_text(json.dumps(m))
    _weights(d / "model.safetensors", np.float16)
    calls = _fake_diffusers(monkeypatch)
    assert not importer.migrate_single_file(str(d)) and calls == []
    _weights(d / "model.safetensors", np.float32)
    assert importer.migrate_single_file(str(d)) and len(calls) == 1
    assert json.loads((d / "model.json").read_text())["layout"] == "repo"


def _folder(tmp_path, weights_dir="weights"):
    import numpy as np
    d = tmp_path / "RV"
    for c in ("unet", "text_encoder"):
        (d / "weights" / c).mkdir(parents=True)
        _weights(d / "weights" / c / "model.safetensors", np.float32)
    (d / "model.json").write_text(json.dumps({"layout": "repo", "weights_dir": weights_dir, "arch": "sd15"}))
    return d


def test_a_32_bit_sd1_folder_is_saved_in_16_bit_once(tmp_path):
    import registry
    d = _folder(tmp_path)
    seen = []
    assert importer.migrate_fp32(str(d), status=seen.append)
    for c in ("unet", "text_encoder"):
        h = registry.read_safetensors_json(str(d / "weights" / c / "model.safetensors"))
        assert (h["w"]["dtype"], h["position_ids"]["dtype"]) == ("F16", "I64")  # integers stay
    assert seen == ["Saving the model in 16 bit (one-time)"]
    assert not importer.migrate_fp32(str(d))  # once
    assert not list(d.rglob("*.partial"))


def test_the_users_own_folder_and_other_models_stay_in_32_bit(tmp_path):
    import registry
    own = _folder(tmp_path)
    d = tmp_path / "Taken-over"
    d.mkdir()
    (d / "model.json").write_text(json.dumps({"layout": "repo", "weights_dir": str(own / "weights"), "arch": "sd15"}))
    assert not importer.migrate_fp32(str(d))
    m = json.loads((own / "model.json").read_text())
    (own / "model.json").write_text(json.dumps({**m, "arch": "sdxl"}))
    assert not importer.migrate_fp32(str(own))
    assert registry.read_safetensors_json(str(own / "weights" / "unet" / "model.safetensors"))["w"]["dtype"] == "F32"
