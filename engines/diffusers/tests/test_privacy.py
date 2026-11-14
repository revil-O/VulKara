# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""What leaves the Mac: pinned helper models, links without API keys, checksum lookups only when allowed."""
import hashlib
import json

import pytest

import civitai
import importer
import pinned
import previews


def test_public_ref_drops_the_api_key():
    assert civitai.public_ref("https://civitai.com/api/download/models/123?token=SECRET&type=Model") == \
        "https://civitai.com/api/download/models/123"
    assert civitai.public_ref("https://civitai.com/models/5/x?modelVersionId=9&token=S") == \
        "https://civitai.com/models/5/x?modelVersionId=9"
    assert civitai.parse_ref("https://civitai.com/models/5/x?modelVersionId=9&token=S") == (5, 9)
    with pytest.raises(civitai.CivitaiError) as e:
        civitai.parse_ref("https://example.com/a?token=SECRET")
    assert "SECRET" not in str(e.value)


def test_no_checksum_lookup_unless_allowed(monkeypatch):
    asked = []
    monkeypatch.setattr(civitai, "lookup_hash", lambda sha, token=None: asked.append(sha))
    monkeypatch.delenv("VK_HASH_LOOKUPS", raising=False)
    importer._HASH_LOOKUPS.clear()
    assert importer._civitai_lookup("a" * 64) is None and asked == []
    monkeypatch.setenv("VK_HASH_LOOKUPS", "1")
    importer._civitai_lookup("b" * 64)
    assert asked == ["b" * 64]


def test_safe_mode_takes_no_explicit_civitai_preview(monkeypatch):
    images = [{"url": "https://image.civitai.com/x/width=1024/a.jpg", "nsfw_level": 8}]
    monkeypatch.setenv("VK_SAFE_MODE", "1")
    assert previews.civitai_image(images) is None
    monkeypatch.delenv("VK_SAFE_MODE")
    assert previews.civitai_image(images).endswith("a.jpg")


def test_pinned_files_are_checked_and_then_used_without_the_network(tmp_path, monkeypatch):
    data = b"weights"
    digest = hashlib.sha256(data).hexdigest()
    calls = []

    def download(repo, name, revision=None, local_dir=None, **kw):
        calls.append(revision)
        (tmp_path / name).write_bytes(data)
        return str(tmp_path / name)
    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    pinned.fetch("a/b", "c0ffee", {"model.safetensors": digest}, str(tmp_path))
    pinned.fetch("a/b", "c0ffee", {"model.safetensors": digest}, str(tmp_path))
    assert calls == ["c0ffee"]


def test_a_pinned_file_with_another_checksum_is_refused(tmp_path, monkeypatch):
    def download(repo, name, revision=None, local_dir=None, **kw):
        (tmp_path / name).write_bytes(b"something else")
        return str(tmp_path / name)
    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    with pytest.raises(RuntimeError):
        pinned.fetch("a/b", "c0ffee", {"model.safetensors": "0" * 64}, str(tmp_path))
    assert not (tmp_path / "model.safetensors").exists()


def test_every_helper_the_engines_download_is_pinned():
    import controlnet
    import preprocess
    with open(pinned.PINS_FILE) as f:
        all_pins = json.load(f)
    specs = []
    for e in list(controlnet.MODELS.values()) + [x for fam in controlnet.EXTRA.values() for x in fam.values()]:
        specs += list(e["per_type"].values()) if "per_type" in e else [e]
    for s in specs:
        _, files = pinned.pins(s["repo"])
        assert set(s.get("remote_files") or s["files"]) <= set(files), s["repo"]
    for m in preprocess.MODELS.values():
        assert m["repo"] in all_pins
    assert "Comfy-Org/Real-ESRGAN_repackaged" in all_pins
    for repo, entry in all_pins.items():
        assert len(entry["revision"]) == 40, repo
        assert any(entry["files"].values()), repo  # at least the weights are checked by their checksum


def test_a_pinned_file_can_get_another_name_and_is_then_ready(tmp_path, monkeypatch):
    data = b"weights"
    digest = hashlib.sha256(data).hexdigest()

    def download(repo, name, revision=None, local_dir=None, **kw):
        (tmp_path / name).write_bytes(data)
        return str(tmp_path / name)
    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    monkeypatch.setattr(pinned, "pins", lambda repo: ("c0ffee", {"model_promax.safetensors": digest}))
    rename = {"model_promax.safetensors": "model.safetensors"}
    assert not pinned.ready("a/b", str(tmp_path), rename)
    pinned.fetch_pinned("a/b", str(tmp_path), rename=rename)
    assert (tmp_path / "model.safetensors").read_bytes() == data and not (tmp_path / "model_promax.safetensors").exists()
    assert pinned.ready("a/b", str(tmp_path), rename)


def test_the_helper_catalog_matches_what_the_engines_download():
    import helpers
    import preprocess
    cat = helpers.catalog()
    ids = [h["id"] for h in cat]
    assert len(ids) == len(set(ids))
    for s in helpers._controlnet_specs():
        h = next(x for x in cat if x["id"] == s["id"])
        assert h["repo"] == s["repo"] and h["folder"] == "controlnets/" + s["id"]
    for name, m in preprocess.MODELS.items():
        assert any(h.get("name_in_engine") == name and h["repo"] == m["repo"] for h in cat)
    with open(pinned.PINS_FILE) as f:
        all_pins = json.load(f)
    for h in cat:
        assert h["kind"] in ("content", "lama", "ddcolor", "preprocess", "controlnet", "upscaler", "faces", "pup", "lora", "rorem",
                             "objectclear"), h["id"]
        if h["kind"] in ("preprocess", "controlnet", "upscaler", "pup", "lora"):
            assert h["repo"] in all_pins, h["id"]
        if h["kind"] == "faces":  # GitHub releases: every file with an https URL and its SHA-256
            import restore
            assert all(u.startswith("https://github.com/") and len(d) == 64 for u, d in restore.FACE_FILES.values())
        if h["kind"] == "rorem":  # pinned in remove.py, every file by its SHA-256
            import remove
            assert h["repo"] == remove.REPO and len(remove.PIN[0]) == 40
            assert all(len(d) == 64 for d in remove.PIN[1].values())
        if h["kind"] == "objectclear":  # pinned in objectclear.py, every file by its SHA-256
            import objectclear
            assert h["repo"] == objectclear.REPO and len(objectclear.PIN[0]) == 40
            assert all(len(d) == 64 for d in objectclear.PIN[1].values())
