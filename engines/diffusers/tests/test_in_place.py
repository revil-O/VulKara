# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""A model folder registered in place: refused when its model.json was written on another Mac (the app would refuse
to run it after a "done")."""
import json

import pytest

import importer
import registry


def folder(tmp_path, **extra):
    m = {"engine": "diffusers", "arch": "sd15", "components": {"unet": 0.86}, **extra}
    (tmp_path / "model.json").write_text(json.dumps(m))
    return str(tmp_path)


def test_a_folder_from_another_mac_is_refused_with_a_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("VK_MACHINE_ID", "here")
    monkeypatch.setattr(importer.memory, "total_ram_gb", lambda: 16.0)
    monkeypatch.setattr(importer, "emit", lambda *a: None)
    for made in ({"imported_on": {"machine": "other", "ram_gb": 24}}, {"plan": {"ram_gb": 24.0}}):
        with pytest.raises(registry.UnsupportedModel, match="another Mac"):
            importer.register_in_place(folder(tmp_path, **made), dry_run=True)
    # its own: taken as it is
    assert importer.register_in_place(folder(tmp_path, imported_on={"machine": "here", "ram_gb": 16}))["arch"] == "sd15"
    assert importer.register_in_place(folder(tmp_path, plan={"ram_gb": 16.0}))["arch"] == "sd15"
