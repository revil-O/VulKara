# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""src/shared/data/curated_models.json: the tested models the app installs with one click."""
import json
import os
import re

PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src", "shared", "data", "curated_models.json")
FAMILIES = {"SD 1.x", "SD 2.x", "SDXL", "SD 3.5", "FLUX.1", "Chroma", "Z-Image", "FLUX.2", "FLUX 3", "Anima", "Wan", "Lumina 2", "ERNIE-Image", "MOSS-Image", "Fibo 2.0"}


def load():
    with open(PATH) as f:
        return json.load(f)


def test_entries_are_complete_and_unique():
    models = load()
    ids = [m["id"] for m in models]
    assert len(ids) == len(set(ids))
    for m in models:
        assert re.fullmatch(r"[A-Za-z0-9._-]+", m["id"]), m["id"]  # the id is the model's folder name
        for key in ("title", "description", "source", "ref", "family", "min_ram_gb", "download_gb", "group"):
            assert m.get(key) not in (None, ""), (m["id"], key)
        assert m["family"] in FAMILIES, m["id"]
        assert m["group"] in ("base", "community", "nsfw"), m["id"]
        assert m["nsfw"] == (m["group"] == "nsfw"), m["id"]
        if m["source"] == "civitai":
            assert re.fullmatch(r"https://civitai\.com/models/\d+\?modelVersionId=\d+", m["ref"]), m["id"]
            assert m["needs_token"] == "civitai"
        else:
            assert m["source"] == "hf" and "/" in m["ref"], m["id"]
            assert m["needs_token"] in (None, "hf")


def test_two_defaults_for_the_first_start_without_token():
    defaults = [m for m in load() if m.get("default")]
    assert [m["id"] for m in defaults] == ["SD-1.5", "FLUX.2-klein-4B"]
    assert all(m["needs_token"] is None and not m["nsfw"] for m in defaults)
    assert min(m["min_ram_gb"] for m in defaults) <= 8  # something for every Mac


def test_no_ideogram_or_krea_in_the_list():
    assert not [m for m in load() if re.search(r"ideogram|krea", m["id"], re.I)]
