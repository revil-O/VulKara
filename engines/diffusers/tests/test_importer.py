# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
import importer

INDEX = {"text_encoder": ["transformers", "CLIPTextModel"], "text_encoder_3": ["transformers", "T5EncoderModel"],
         "transformer": ["diffusers", "SD3Transformer2DModel"], "scheduler": ["diffusers", "Sched"]}


def test_variant_names():
    assert importer._variant_of("te/model.fp16.safetensors") == "fp16"
    assert importer._variant_of("te/model.fp16-00001-of-00002.safetensors") == "fp16"
    assert importer._variant_of("te/model.safetensors.index.fp16.json") == "fp16"
    assert importer._variant_of("te/model-00001-of-00002.safetensors") is None
    assert importer._variant_of("te/model.safetensors.index.json") is None
    assert importer._variant_of("fp16_models/model.safetensors") is None


def test_sharded_fp16_variant_is_not_downloaded_twice():
    """SD 3.5 Medium: plain and fp16 shards side by side (the fp16 names use "-" after fp16)."""
    files = ["model_index.json", "scheduler/scheduler_config.json",
             "text_encoder/config.json", "text_encoder/model.safetensors", "text_encoder/model.fp16.safetensors",
             "text_encoder_3/config.json",
             "text_encoder_3/model-00001-of-00002.safetensors", "text_encoder_3/model-00002-of-00002.safetensors",
             "text_encoder_3/model.fp16-00001-of-00002.safetensors",
             "text_encoder_3/model.fp16-00002-of-00002.safetensors",
             "text_encoder_3/model.safetensors.index.json", "text_encoder_3/model.safetensors.index.fp16.json",
             "transformer/config.json", "transformer/diffusion_pytorch_model.safetensors"]
    wanted, variant = importer._repo_plan_files(files, INDEX)
    assert variant is None
    te3 = [f for f in wanted if f.startswith("text_encoder_3/")]
    assert te3 == ["text_encoder_3/config.json", "text_encoder_3/model-00001-of-00002.safetensors",
                   "text_encoder_3/model-00002-of-00002.safetensors", "text_encoder_3/model.safetensors.index.json"]
    assert "text_encoder/model.fp16.safetensors" not in wanted


def test_fp16_only_repo_uses_the_variant():
    files = ["model_index.json", "text_encoder/config.json", "text_encoder/model.fp16.safetensors",
             "text_encoder_3/config.json", "text_encoder_3/model.fp16-00001-of-00002.safetensors",
             "text_encoder_3/model.fp16-00002-of-00002.safetensors", "text_encoder_3/model.safetensors.index.fp16.json",
             "transformer/config.json", "transformer/diffusion_pytorch_model.fp16.safetensors"]
    wanted, variant = importer._repo_plan_files(files, INDEX)
    assert variant == "fp16"
    assert "text_encoder_3/model.safetensors.index.fp16.json" in wanted


def test_civitai_api_key_is_not_sent_to_the_storage_redirect():
    import urllib.request
    import civitai
    h = civitai._DropAuthOnRedirect()
    req = civitai._request("https://civitai.com/api/download/models/1", token="secret")
    storage = h.redirect_request(req, None, 307, "Temporary Redirect", {}, "https://b2.civitai.com/file?X-Amz-Signature=1")
    assert not storage.has_header("Authorization")
    same_host = h.redirect_request(req, None, 307, "Temporary Redirect", {}, "https://civitai.com/api/download/models/2")
    assert same_host.get_header("Authorization") == "Bearer secret"
    assert isinstance(h, urllib.request.HTTPRedirectHandler)


def test_civitai_trigger_words_are_cleaned():
    import civitai
    assert civitai.clean_trigger_words(["t4tt00", "simple ", "a, b", "T4TT00", ""]) == ["t4tt00", "simple", "a", "b"]


def test_files_from_disk_get_the_authors_trigger_words_from_civitai(monkeypatch):
    import civitai
    monkeypatch.setattr(importer, "progress", lambda *a, **k: None)
    monkeypatch.setenv("VK_HASH_LOOKUPS", "1")  # allowed in Settings → Privacy
    found = {"model_id": 1, "version_id": 2, "name": "Tattoo design", "base_model": "SDXL 1.0",
             "trigger_words": ["Tattoo_gen"], "images": []}
    monkeypatch.setattr(civitai, "lookup_hash", lambda sha, token=None: found if sha == "abc" else None)
    m = {"sha256": "abc", "trigger_words": ["from_metadata"], "source": {"type": "file"}}
    importer._civitai_by_hash(m, None)
    assert m["trigger_words"] == ["Tattoo_gen"] and m["civitai"]["version_id"] == 2
    offline = {"sha256": "other", "trigger_words": ["from_metadata"], "source": {"type": "file"}}
    importer._civitai_by_hash(offline, None)
    assert offline["trigger_words"] == ["from_metadata"] and "civitai" not in offline


def _fake_import(tmp_path, monkeypatch):
    """run_import of a local file as far as the manifest, without reading weights."""
    import memory
    import registry
    src = tmp_path / "x.gguf"
    src.write_bytes(b"0")
    monkeypatch.setattr(importer, "progress", lambda *a, **k: None)
    monkeypatch.setattr(importer, "emit", lambda *a, **k: None)
    monkeypatch.setattr(importer, "_single_file_is_lora", lambda *a, **k: False)
    monkeypatch.setattr(importer, "inspect", lambda source, ref, **k: {
        "arch": "sd15", "denoiser": "unet", "components": {"unet": 0.9, "vae": 0.1}, "layout": "single_denoiser",
        "source": source, "ref": ref})
    monkeypatch.setattr(importer, "_materialize", lambda info, target, token: {"layout": "single_denoiser"})
    monkeypatch.setattr(importer, "_add_preview", lambda *a, **k: None)
    monkeypatch.setattr(registry, "runtime_too_old", lambda arch: None)
    monkeypatch.setattr(memory, "total_ram_gb", lambda: 15.9999)
    return str(src)


def test_an_import_says_which_mac_it_was_made_on(tmp_path, monkeypatch):
    """imported_on: the app's id of the Mac (a hash it passes in VK_MACHINE_ID) and its memory in whole GB, so that a
    folder copied to another Mac is told apart there (src/main/foreign_mac.ts)."""
    import json
    src = _fake_import(tmp_path, monkeypatch)
    monkeypatch.setenv("VK_MACHINE_ID", "0123456789abcdef")
    importer.run_import("file", src, "Here", root=str(tmp_path / "models"))
    m = json.loads((tmp_path / "models" / "Here" / "model.json").read_text())
    assert m["imported_on"] == {"machine": "0123456789abcdef", "ram_gb": 16}
    assert round(m["plan"]["ram_gb"]) == m["imported_on"]["ram_gb"]

    # run without the app (no id): the memory is still told
    monkeypatch.delenv("VK_MACHINE_ID")
    importer.run_import("file", src, "Elsewhere", root=str(tmp_path / "models"))
    m = json.loads((tmp_path / "models" / "Elsewhere" / "model.json").read_text())
    assert m["imported_on"] == {"ram_gb": 16}




def test_installs_need_50_gb_free_on_the_models_disk(tmp_path, monkeypatch):
    import collections
    import shutil
    import pytest
    import importer
    monkeypatch.setattr(importer, "MIN_INSTALL_FREE_GB", 50.0)
    usage = collections.namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda p: usage(0, 0, 49 * 1024 ** 3))
    with pytest.raises(importer.NotEnoughSpace, match="Only 49 GB free"):
        importer.run_import("hf", "a/b", "b", dry_run=True, root=str(tmp_path / "not-made-yet"))
    # 50 GB free is enough
    monkeypatch.setattr(shutil, "disk_usage", lambda p: usage(0, 0, 50 * 1024 ** 3))
    importer.ensure_install_room(str(tmp_path))


def test_an_mflux_repository_downloads_only_what_mflux_reads():
    import importer
    names = ["model_index.json", "transformer/0.safetensors", "text_encoder/config.json", "text_encoder/LICENSE",
             "tokenizer/tokenizer.json", "tokenizer/chat_template.jinja", "fonts/DejaVuSans.ttf",
             "fonts/Aileron-Regular.otf", "fonts/LICENSE-DejaVu.txt", "LICENSE.md", "NOTICE.md", "preview.jpg",
             "README.md", "gallery/a.png", "pytorch_model.bin", "handler.py", ".gitattributes"]
    assert importer.mflux_files(names) == sorted(
        ["model_index.json", "transformer/0.safetensors", "text_encoder/config.json", "text_encoder/LICENSE",
         "tokenizer/tokenizer.json", "tokenizer/chat_template.jinja", "fonts/DejaVuSans.ttf",
         "fonts/Aileron-Regular.otf", "fonts/LICENSE-DejaVu.txt", "LICENSE.md", "NOTICE.md"])
