# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
import io
import json
import os

import pytest

import previews


def test_civitai_picks_the_most_harmless_image_small():
    images = [{"url": "https://image.civitai.com/x/abc/width=1024/1.jpeg", "nsfw_level": 8},
              {"url": "https://image.civitai.com/x/def/width=832/2.jpeg", "nsfw_level": 1}]
    assert previews.civitai_image(images) == "https://image.civitai.com/x/def/width=512/2.jpeg"
    assert previews.civitai_image([]) is None


def test_hf_prefers_example_pictures(monkeypatch):
    class Api:
        def __init__(self, token=None):
            pass

        def list_repo_files(self, repo):
            return ["README.md", "assets/logo.png", "samples/a.webp", "dev_grid.jpg", "model.safetensors"]
    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "HfApi", Api)
    assert previews.hf_image("org/model") == "dev_grid.jpg"


def test_save_makes_a_square_thumbnail(tmp_path):
    PIL = pytest.importorskip("PIL.Image")
    buf = io.BytesIO()
    PIL.new("RGB", (1200, 800), "red").save(buf, "PNG")
    path = previews._save(buf.getvalue(), str(tmp_path))
    assert PIL.open(path).size == (previews.SIZE, previews.SIZE)


def test_missing_lists_models_without_preview(tmp_path):
    for name, files in (("a", ["model.json"]), ("b", ["model.json", "preview.jpg"]), ("c", []),
                        ("l", ["lora.json"])):
        os.makedirs(tmp_path / name)
        for f in files:
            (tmp_path / name / f).write_text(json.dumps({}))
    assert [os.path.basename(p) for p in previews.missing([str(tmp_path)])] == ["a", "l"]


def _lora(tmp_path, name, tag_frequency=None, trigger_words=()):
    folder = tmp_path / name
    folder.mkdir()
    meta = {"ss_tag_frequency": json.dumps({"img": tag_frequency})} if tag_frequency else {}
    header = json.dumps({"__metadata__": meta}).encode()
    (folder / "lora.safetensors").write_bytes(len(header).to_bytes(8, "little") + header)
    (folder / "lora.json").write_text(json.dumps({"name": name, "file": "lora.safetensors",
                                                     "trigger_words": list(trigger_words)}))
    return str(folder)


def test_lora_picture_uses_a_whole_training_caption(tmp_path):
    folder = _lora(tmp_path, "t4tt00-tattoo", {
        "t4tt00 black and white drawing tattoo of a cheshire cat": 1,
        "t4tt00 black and white drawing tattoo of a rose with thorns": 1,
        "wearing a top hat and holding a pocket clock": 1,  # a fragment after a comma
        "set against a white background.": 2})
    assert previews.lora_prompt(folder).startswith("t4tt00 black and white drawing tattoo of")


def test_lora_picture_uses_training_tags_or_name_and_triggers(tmp_path):
    tags = _lora(tmp_path, "styled", {"monochrome": 9, "solo": 8, "tattoo_style": 7, "flower": 5, "skull": 3})
    assert previews.lora_prompt(tags).startswith("monochrome, tattoo_style, flower")
    named = _lora(tmp_path, "fantasy-digital-painting", trigger_words=["zaat style"])
    assert previews.lora_prompt(named).startswith("zaat style, fantasy a digital painting of")


CARD = """---
license: apache-2.0
---
# A model
[![badge](https://img.shields.io/badge/x-y-blue)](https://example.org)
<img src="https://evil.example.com/a.png">
![grid](https://cdn-uploads.huggingface.co/production/uploads/abc/grid.png "the grid")
![later](samples/b.png)
"""


def _card(monkeypatch, text):
    import huggingface_hub

    def download(repo, filename, token=None):
        assert filename == "README.md"
        p = os.path.join(os.environ.get("TMPDIR", "/tmp"), "vk_card_%d.md" % os.getpid())
        with open(p, "w") as f:
            f.write(text)
        return p
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)


def test_the_model_card_gives_its_pictures_on_hugging_face_in_order(monkeypatch):
    _card(monkeypatch, CARD)
    assert previews.hf_card_images("org/model") == [
        "https://cdn-uploads.huggingface.co/production/uploads/abc/grid.png",
        "https://huggingface.co/org/model/resolve/main/samples/b.png"]


def test_card_links_are_read_like_a_browser_would(monkeypatch):
    _card(monkeypatch, "\n".join([
        "![a](data:image/png;base64,AAAA)",                       # inline data: not a link to fetch
        "![b](mailto:me@example.org)",
        "![c](https://huggingface.co/org/model/blob/main/c.png)",  # a page about the file -> the file itself
        "![d](//cdn-uploads.huggingface.co/u/d.png)",              # protocol-relative
        "![e](http://huggingface.co/org/model/resolve/main/e.png)",  # http to Hugging Face -> https
        "![f](/other/repo/resolve/main/f.png)",                     # from the site root
        "![g](.hidden/g.png)",
        "![h](https://evil.example.com/h.png)",
        "![i](logo.svg)",
    ]))
    assert previews.hf_card_images("org/model") == [
        "https://huggingface.co/org/model/resolve/main/c.png",
        "https://cdn-uploads.huggingface.co/u/d.png",
        "https://huggingface.co/org/model/resolve/main/e.png",
        "https://huggingface.co/other/repo/resolve/main/f.png",
        "https://huggingface.co/org/model/resolve/main/.hidden/g.png",
    ]


def _png():
    from PIL import Image
    import io
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 100, 50)).save(b, "PNG")
    return b.getvalue()


def _hf_model(tmp_path):
    folder = tmp_path / "m"
    folder.mkdir()
    (folder / "model.json").write_text(json.dumps({"source": {"type": "hf", "ref": "org/model"}}))
    return str(folder)


def _card_fetch(monkeypatch, urls, pages):
    """The card offers urls; pages maps url -> bytes, or an exception to raise."""
    monkeypatch.setattr(previews, "hf_image", lambda repo, token=None: None)
    monkeypatch.setattr(previews, "hf_card_images", lambda repo, token=None: list(urls))

    def get(url):
        v = pages[url]
        if isinstance(v, Exception):
            raise v
        return v
    monkeypatch.setattr(previews, "_get", get)


def _http_error(code):
    import urllib.error
    return urllib.error.HTTPError("https://huggingface.co/x", code, "x", {}, None)


def test_fetch_falls_back_to_the_card_picture(tmp_path, monkeypatch):
    folder = _hf_model(tmp_path)
    _card_fetch(monkeypatch, ["https://cdn-uploads.huggingface.co/x.png"], {"https://cdn-uploads.huggingface.co/x.png": _png()})
    monkeypatch.setattr(previews, "_refused", lambda data, safe: None)
    assert previews.fetch_for(folder) == os.path.join(folder, previews.FILE)


def test_a_card_picture_that_is_gone_or_no_picture_gives_way_to_the_next(tmp_path, monkeypatch):
    folder = _hf_model(tmp_path)
    a, b, c = ("https://huggingface.co/org/model/resolve/main/%s.png" % n for n in "abc")
    _card_fetch(monkeypatch, [a, b, c], {a: _http_error(404), b: b"<html>not a picture</html>", c: _png()})
    monkeypatch.setattr(previews, "_refused", lambda data, safe: None)
    assert previews.fetch_for(folder) == os.path.join(folder, previews.FILE)


def test_a_network_failure_is_tried_again_later(tmp_path, monkeypatch):
    import urllib.error
    folder = _hf_model(tmp_path)
    a = "https://cdn-uploads.huggingface.co/a.png"
    _card_fetch(monkeypatch, [a], {a: urllib.error.URLError("no route")})
    with pytest.raises(Exception):
        previews.fetch_for(folder)


def test_the_filter_checks_card_pictures_also_outside_safe_mode(tmp_path, monkeypatch):
    folder = _hf_model(tmp_path)
    a = "https://cdn-uploads.huggingface.co/a.png"
    _card_fetch(monkeypatch, [a], {a: _png()})
    seen = []
    monkeypatch.setattr(previews, "_refused", lambda data, safe: seen.append(safe) or "a likely minor")
    monkeypatch.delenv("VK_SAFE_MODE", raising=False)
    previews.main([str(tmp_path)])
    assert seen == [False] and not os.path.exists(os.path.join(folder, previews.FILE))
    assert json.load(open(os.path.join(folder, "model.json")))["preview_missing"] == "refused"
    assert list(previews.missing([str(tmp_path)])) == []


def test_safe_mode_refusals_are_tried_again_once_it_is_off(tmp_path, monkeypatch):
    folder = _hf_model(tmp_path)
    a = "https://cdn-uploads.huggingface.co/a.png"
    _card_fetch(monkeypatch, [a], {a: _png()})
    monkeypatch.setattr(previews, "_refused", lambda data, safe: "nudity" if safe else None)
    monkeypatch.setenv("VK_SAFE_MODE", "1")
    previews.main([str(tmp_path)])
    assert json.load(open(os.path.join(folder, "model.json")))["preview_missing"] == "safe"
    assert list(previews.missing([str(tmp_path)])) == []
    monkeypatch.delenv("VK_SAFE_MODE")
    assert list(previews.missing([str(tmp_path)])) == [folder]


def test_a_filter_that_does_not_work_leaves_the_folder_for_a_later_start(tmp_path, monkeypatch):
    folder = _hf_model(tmp_path)
    a = "https://cdn-uploads.huggingface.co/a.png"
    _card_fetch(monkeypatch, [a], {a: _png()})

    def broken(data, safe):
        raise RuntimeError("the filter weights are not there yet")
    monkeypatch.setattr(previews, "_refused", broken)
    previews.main([str(tmp_path)])
    assert "preview_missing" not in json.load(open(os.path.join(folder, "model.json")))
    assert list(previews.missing([str(tmp_path)])) == [folder]


def test_civitai_samples_all_too_explicit_for_safe_mode_count_as_a_safe_refusal(tmp_path, monkeypatch):
    folder = tmp_path / "c"
    folder.mkdir()
    (folder / "model.json").write_text(json.dumps({"source": {"type": "civitai", "images": [{"url": "https://image.civitai.com/x/width=450/a.jpeg", "nsfw_level": 8}]}}))
    monkeypatch.setenv("VK_SAFE_MODE", "1")
    previews.main([str(tmp_path)])
    assert json.load(open(folder / "model.json"))["preview_missing"] == "safe"


def test_a_folder_without_any_picture_is_not_tried_at_every_start(tmp_path, monkeypatch):
    folder = _hf_model(tmp_path)
    monkeypatch.setattr(previews, "fetch_for", lambda f, token=None: None)
    previews.main([str(tmp_path)])
    assert json.load(open(os.path.join(folder, "model.json"))).get("preview_missing") is True
    assert list(previews.missing([str(tmp_path)])) == []
