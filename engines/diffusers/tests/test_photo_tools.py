# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Photo tools (photo_tools.py) with tiny ONNX models (tests/fixtures/onnx, made by make_onnx_fixtures.py)."""
import json
import os

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("onnxruntime")
import photo_tools  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "onnx")


@pytest.fixture
def helpers(tmp_path, monkeypatch):
    monkeypatch.setenv("VK_HELPERS_DIR", str(tmp_path / "helpers"))
    return tmp_path


def photo(tmp_path, size=(100, 70), name="in.png"):
    rng = np.random.default_rng(0)
    path = str(tmp_path / name)
    Image.fromarray(rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)).save(path)
    return path


def test_the_catalog_is_pinned_and_licensed_for_commercial_use():
    for t in photo_tools.catalog():
        assert all(len(h) == 64 for h in t["files"].values()), t["id"]
        if "repo" in t:
            assert len(t["revision"]) == 40, t["id"]
        else:  # a GitHub release: every file has an https URL and a checksum
            assert set(t["urls"]) == set(t["files"]) and all(u.startswith("https://") for u in t["urls"].values()), t["id"]
        assert t["model"] in t["files"] and t["licence"] in ("MIT", "Apache-2.0", "BSD-3-Clause"), t["id"]
        assert t["kind"] in ("image", "mask", "segment")
        # the GPU tools are image tools from their original weights; the mask and selection tools are ONNX
        if t.get("runtime") == "torch":
            assert t["kind"] == "image" and t["model"].endswith(".pth") and t["range"] == "0-1", t["id"]
        else:
            assert t["model"].endswith(".onnx"), t["id"]
        for v in (t.get("variants") or {}).values():  # other weights: pinned, and their own licence when it differs
            assert v["url"].startswith("https://") and len(v["sha256"]) == 64, t["id"]
            assert v.get("licence", t["licence"]) in ("MIT", "Apache-2.0", "BSD-3-Clause", "CC-BY-4.0"), t["id"]
    assert sum(t.get("runtime") == "torch" for t in photo_tools.catalog()) == 3


def test_a_file_from_a_url_is_checked_and_a_wrong_one_removed(tmp_path, monkeypatch):
    import hashlib
    import io
    import urllib.request
    import pinned
    good = b"weights " * 1000
    served = {"a.pth": good, "b.pth": b"tampered"}

    class Answer(io.BytesIO):
        headers = {"Content-Length": str(len(good))}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: Answer(served[req.full_url.rsplit("/", 1)[1]]))
    digest = hashlib.sha256(good).hexdigest()
    folder = str(tmp_path / "t")
    seen = []
    pinned.fetch_urls({"a.pth": "https://example.org/r/a.pth"}, {"a.pth": digest}, folder, report=seen.append)
    assert open(os.path.join(folder, "a.pth"), "rb").read() == good and seen[-1] == 100.0
    assert not os.path.exists(os.path.join(folder, "a.pth.part"))
    # the second call reads nothing (the mark says it is complete)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("fetched again"))
    pinned.fetch_urls({"a.pth": "https://example.org/r/a.pth"}, {"a.pth": digest}, folder)
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: Answer(served["b.pth"]))
    with pytest.raises(RuntimeError, match="checksum"):
        pinned.fetch_urls({"b.pth": "https://example.org/r/b.pth"}, {"b.pth": digest}, str(tmp_path / "u"))
    assert not os.listdir(tmp_path / "u")
    with pytest.raises(ValueError, match="https"):
        pinned.fetch_urls({"c.pth": "http://example.org/c.pth"}, {"c.pth": digest}, str(tmp_path / "v"))


@pytest.fixture
def tiny_torch_model(tmp_path):
    """A tiny ESRGAN ×2 made from spandrel's own class, so the loader recognises it (about 0.8 MB)."""
    torch = pytest.importorskip("torch")
    spandrel = pytest.importorskip("spandrel")
    from spandrel.architectures.ESRGAN import ESRGAN
    torch.manual_seed(0)
    net = ESRGAN(in_nc=3, out_nc=3, num_filters=4, num_blocks=1, scale=2)
    path = str(tmp_path / "tiny_x2.pth")
    torch.save(net.state_dict(), path)
    assert spandrel.ModelLoader().load_from_file(path).scale == 2
    return path


def test_pytorch_weights_are_recognised_imported_and_run_on_the_gpu(helpers, tmp_path, tiny_torch_model):
    draft = photo_tools.inspect(tiny_torch_model)
    assert (draft["kind"], draft["runtime"], draft["scale"], draft["arch"]) == ("image", "torch", 2, "ESRGAN")
    folder, m = photo_tools.import_file(tiny_torch_model, "Tiny")
    assert os.listdir(folder) == sorted(["tiny_x2.pth", "tool.json"]) or set(os.listdir(folder)) == {"tiny_x2.pth", "tool.json"}
    m["tile"] = 32  # several tiles on a small picture
    pic = photo(tmp_path, (70, 50))
    path = photo_tools.apply({"photo_tool": {"folder": folder, "strength": 1.0}, "input_image": pic}, tmp_path)
    assert Image.open(path).size == (140, 100)
    # a safetensors file of the same weights is taken too
    from safetensors.torch import save_file
    import torch
    st = str(tmp_path / "tiny.safetensors")
    save_file(torch.load(tiny_torch_model), st)
    assert photo_tools.inspect(st)["scale"] == 2


def test_the_tile_of_a_gpu_tool_follows_the_room_left_in_metal(monkeypatch):
    pytest.importorskip("torch")
    monkeypatch.setattr(photo_tools, "_device", lambda: "mps")
    m = {"tile": 512, "tile_metal_gb": {"256": 2.3, "384": 4.5, "512": 7.1}}
    # a 24 GB Mac (budget 17.8 GB) with nothing loaded: the largest; with FLUX (12 GB) loaded: 384; a 16 GB Mac
    # (budget 11.8 GB) with SDXL (7 GB) loaded: 256; no room at all: still the smallest
    assert photo_tools.metal_tile(m, budget_gb=17.8, used_gb=0.3) == 512
    assert photo_tools.metal_tile(m, budget_gb=17.8, used_gb=12.0) == 384
    assert photo_tools.metal_tile(m, budget_gb=11.8, used_gb=7.0) == 256
    assert photo_tools.metal_tile(m, budget_gb=11.8, used_gb=11.0) == 256
    assert photo_tools.metal_tile({"tile": 768}, budget_gb=1, used_gb=0) == 768
    monkeypatch.setattr(photo_tools, "_device", lambda: "cpu")
    assert photo_tools.metal_tile(m, budget_gb=1, used_gb=0) == 512


def test_a_variant_is_fetched_on_first_use_into_its_own_folder(helpers, tmp_path, tiny_torch_model, monkeypatch):
    import hashlib
    import pinned
    folder, m = photo_tools.import_file(tiny_torch_model, "Tiny")
    data = open(tiny_torch_model, "rb").read()
    m["variants"] = {"sharp": {"label": "Sharp", "description": "", "file": "sharp.pth", "url": "https://example.org/sharp.pth",
                               "sha256": hashlib.sha256(data).hexdigest(), "size_mb": 1, "tile_metal_gb": {"128": 0.1}}}
    json.dump(m, open(os.path.join(folder, "tool.json"), "w"))
    fetched = []

    def fake_fetch(urls, files, dest, report=None):
        fetched.append(dest)
        os.makedirs(dest, exist_ok=True)
        open(os.path.join(dest, "sharp.pth"), "wb").write(data)
        return dest

    monkeypatch.setattr(pinned, "fetch_urls", fake_fetch)
    tables = []
    tile = photo_tools.metal_tile
    monkeypatch.setattr(photo_tools, "metal_tile", lambda m: tables.append(m.get("tile_metal_gb")) or tile(m))
    path = photo_tools.apply({"photo_tool": {"folder": folder, "variant": "sharp"}, "input_image": photo(tmp_path, (40, 30))}, tmp_path)
    assert Image.open(path).size == (80, 60)
    assert fetched == [os.path.join(folder, "variants", "sharp")]
    photo_tools.apply({"photo_tool": {"folder": folder}, "input_image": photo(tmp_path, (40, 30))}, tmp_path)
    assert tables == [{"128": 0.1}, None]  # the variant's own tile table, the tool's own (none) without it
    with pytest.raises(ValueError, match="no variant"):
        photo_tools.apply({"photo_tool": {"folder": folder, "variant": "gone"}, "input_image": photo(tmp_path, (40, 30))}, tmp_path)


def test_the_catalog_offers_scunet_sharp_and_the_jpeg_quality(monkeypatch):
    tools = {t["id"]: t for t in photo_tools.catalog()}
    sharp = tools["scunet-real"]["variants"]["sharp"]
    assert sharp["url"].startswith("https://github.com/cszn/KAIR/") and len(sharp["sha256"]) == 64
    assert tools["fbcnn-color"].get("quality") is True
    natural = tools["swinir-real-x4"]["variants"]["natural"]
    monkeypatch.setattr(photo_tools, "_device", lambda: "mps")
    assert natural["url"].startswith("https://github.com/Phhofm/models/") and natural["licence"] == "CC-BY-4.0"
    # 16 GB Mac (Metal budget 12.7 GB): 512 alone (11.5 GB, run in the test app at 12.3 GB, no swap), 384 beside 1 GB
    assert photo_tools.metal_tile(natural, budget_gb=12.7, used_gb=0.0) == 512
    assert photo_tools.metal_tile(natural, budget_gb=12.7, used_gb=1.0) == 384


def test_a_file_that_is_no_photo_model_is_refused(tmp_path):
    pytest.importorskip("spandrel")
    import torch
    bad = str(tmp_path / "other.pth")
    torch.save({"layer.weight": torch.zeros(3, 3)}, bad)
    with pytest.raises(ValueError, match="spandrel does not know"):
        photo_tools.inspect(bad)
    with pytest.raises(ValueError, match="onnx, .pth or .safetensors"):
        photo_tools.inspect(str(tmp_path / "x.gguf"))


def test_the_importer_takes_model_files_chosen_on_the_enhance_page(helpers, monkeypatch, tiny_torch_model):
    import importer
    seen = []
    monkeypatch.setattr(importer, "emit", lambda tag, payload: seen.append((tag, payload)))
    info = importer.run_import("toolfile", tiny_torch_model, None, dry_run=True)
    assert info["type"] == "photo_tool" and "2×" in info["label"] and "ESRGAN, GPU" in info["label"]
    importer.run_import("toolfile", tiny_torch_model, None)
    assert seen[-1][0] == "__import_done__" and seen[-1][1]["manifest"]["runtime"] == "torch"
    assert [m["name"] for _, m in photo_tools.installed()] == ["tiny_x2"]


def test_an_image_model_is_recognised_with_its_scale_and_range():
    d = photo_tools.inspect(os.path.join(FIX, "brighten.onnx"))
    assert (d["kind"], d["scale"], d["range"]) == ("image", 1, "0-1")
    d = photo_tools.inspect(os.path.join(FIX, "enlarge2.onnx"))
    assert (d["kind"], d["scale"]) == ("image", 2)
    d = photo_tools.inspect(os.path.join(FIX, "mask64.onnx"))
    assert (d["kind"], d["size"]) == ("mask", 64)


def test_a_model_that_is_not_a_photo_tool_is_refused(tmp_path):
    with pytest.raises(ValueError, match="2 inputs"):
        photo_tools.inspect(os.path.join(FIX, "two_inputs.onnx"))
    bad = tmp_path / "broken.onnx"
    bad.write_bytes(b"not a model")
    with pytest.raises(ValueError, match="can not load"):
        photo_tools.inspect(str(bad))
    with pytest.raises(ValueError, match=".onnx"):
        photo_tools.inspect(str(tmp_path / "x.safetensors"))


def test_an_imported_tool_runs_in_tiles_without_seams(helpers):
    folder, m = photo_tools.import_file(os.path.join(FIX, "brighten.onnx"), "Brighter")
    assert json.load(open(os.path.join(folder, "tool.json")))["name"] == "Brighter"
    m["tile"] = 48  # many tiles on a small picture
    rgb = np.asarray(Image.open(photo(helpers, (130, 90))).convert("RGB"))
    out = photo_tools.run_image(m, folder, rgb)
    expected = np.clip(rgb.astype(np.float32) * 0.8 + 0.2 * 255, 0, 255)
    assert out.shape == rgb.shape and np.abs(out.astype(np.float32) - expected).max() <= 1.0
    with pytest.raises(FileExistsError):
        photo_tools.import_file(os.path.join(FIX, "brighten.onnx"), "Brighter")


def test_an_enlarging_tool_and_the_strength(helpers, tmp_path):
    folder, _ = photo_tools.import_file(os.path.join(FIX, "enlarge2.onnx"))
    pic = photo(tmp_path)
    path = photo_tools.apply({"photo_tool": {"folder": folder, "strength": 0.5}, "input_image": pic}, tmp_path)
    assert Image.open(path).size == (200, 140)


def test_a_picture_over_the_limit_is_made_smaller_first_and_said_so(helpers, tmp_path):
    folder, m = photo_tools.import_file(os.path.join(FIX, "enlarge2.onnx"))
    m["max_side"] = 64
    json.dump(m, open(os.path.join(folder, "tool.json"), "w"))
    notes = []
    path = photo_tools.apply({"photo_tool": {"folder": folder}, "input_image": photo(tmp_path, (100, 70))}, tmp_path,
                             note=notes.append)
    # 100 × 70 -> 64 × 45, then twice the size
    assert Image.open(path).size == (128, 90)
    assert notes and "100 × 70" in notes[0] and "64 × 45" in notes[0]


def test_an_enlarging_tool_brings_its_result_to_the_factor_asked_for(helpers, tmp_path):
    folder, m = photo_tools.import_file(os.path.join(FIX, "enlarge2.onnx"))
    pic = photo(tmp_path, (100, 70))
    path = photo_tools.apply({"photo_tool": {"folder": folder, "factor": 1.5}, "input_image": pic}, tmp_path)
    assert Image.open(path).size == (150, 105)
    # more than the tool can: its own scale
    path = photo_tools.apply({"photo_tool": {"folder": folder, "factor": 4}, "input_image": pic}, tmp_path)
    assert Image.open(path).size == (200, 140)
    # measured on the picture given, also when it was made smaller first: 100 × 70 -> 64 × 45 -> 128 × 90, and
    # × 1.2 of 100 × 70 is 120 × 84
    m["max_side"] = 64
    json.dump(m, open(os.path.join(folder, "tool.json"), "w"))
    path = photo_tools.apply({"photo_tool": {"folder": folder, "factor": 1.2}, "input_image": pic}, tmp_path)
    assert Image.open(path).size == (120, 84)


def test_a_mask_tool_cuts_out_or_gives_the_mask(helpers, tmp_path):
    folder, _ = photo_tools.import_file(os.path.join(FIX, "mask64.onnx"))
    rgb = np.zeros((80, 120, 3), np.uint8)
    rgb[:, :60, 0] = 255  # the left half is red: "the subject"
    pic = str(tmp_path / "red.png")
    Image.fromarray(rgb).save(pic)
    cut = Image.open(photo_tools.apply({"photo_tool": {"folder": folder}, "input_image": pic}, tmp_path))
    alpha = np.asarray(cut)[..., 3]
    assert cut.mode == "RGBA" and alpha[:, :50].mean() > 200 and alpha[:, 70:].mean() < 50
    mask = Image.open(photo_tools.apply({"photo_tool": {"folder": folder, "output": "mask"}, "input_image": pic}, tmp_path))
    assert mask.mode == "RGB" and np.asarray(mask)[:, :50].mean() > 200


def test_a_tool_outside_the_tools_folder_or_a_file_outside_its_folder_is_refused(helpers, tmp_path):
    with pytest.raises(ValueError, match="not installed"):
        photo_tools.apply({"photo_tool": {"folder": str(tmp_path)}, "input_image": photo(tmp_path)}, tmp_path)
    folder, m = photo_tools.import_file(os.path.join(FIX, "brighten.onnx"))
    m["model"] = "../../evil.onnx"
    json.dump(m, open(os.path.join(folder, "tool.json"), "w"))
    with pytest.raises(ValueError, match="outside its folder"):
        photo_tools.apply({"photo_tool": {"folder": folder}, "input_image": photo(tmp_path)}, tmp_path)


def test_the_importer_takes_onnx_files_as_photo_tools(helpers, monkeypatch):
    import importer
    seen = []
    monkeypatch.setattr(importer, "emit", lambda tag, payload: seen.append((tag, payload)))
    info = importer.run_import("file", os.path.join(FIX, "enlarge2.onnx"), None, dry_run=True)
    assert info["type"] == "photo_tool" and "2×" in info["label"]
    importer.run_import("file", os.path.join(FIX, "enlarge2.onnx"), "Twice")
    tag, done = seen[-1]
    assert tag == "__import_done__" and done["manifest"]["name"] == "Twice"
    assert [m["name"] for _, m in photo_tools.installed()] == ["Twice"]


class _Session:
    """An ONNX session stand-in: fixed outputs, the inputs it got kept."""

    def __init__(self, names, outputs):
        self.names, self.outputs, self.got = names, outputs, None

    def get_inputs(self):
        return [type("I", (), {"name": n})() for n in self.names]

    def get_outputs(self):
        return [type("O", (), {"name": n})() for n in self.outputs]

    def run(self, _names, feeds):
        self.got = feeds
        return [self.outputs[n] for n in self.outputs]


def test_a_selection_is_made_on_the_upright_picture_of_a_rotated_jpeg(tmp_path):
    # upright 100×60, red on the left; stored on its side with EXIF orientation 6 (as a phone saves a portrait)
    upright = np.zeros((60, 100, 3), np.uint8)
    upright[:, :50, 0] = 255
    path = str(tmp_path / "rotated.jpg")
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.fromarray(upright).transpose(Image.Transpose.ROTATE_90).save(path, exif=exif, quality=95)
    assert Image.open(path).size == (60, 100)

    seg = object.__new__(photo_tools.Segmenter)
    seg.m, seg.image, seg.embeddings = {"size": 32}, None, None
    seg.encoder = _Session(["pixel_values"], {"image_embeddings": np.zeros((1, 4, 2, 2), np.float32)})
    low = np.full((1, 1, 1, 8, 8), -1.0, np.float32)
    low[..., :, :4] = 1.0  # the left half selected
    seg.decoder = _Session(["input_points", "input_labels", "image_embeddings"],
                           {"iou_scores": np.ones((1, 1, 1), np.float32), "pred_masks": low})
    out = str(tmp_path / "mask.png")
    seg.select(path, [[25, 30, 1]], out)

    x = seg.encoder.got["pixel_values"][0]  # 3×32×32, the picture as the model saw it
    assert x[0, :, :14].mean() > x[0, :, 18:].mean() + 1  # red on the left: upright, not on its side
    mask = np.asarray(Image.open(out))
    assert mask.shape[:2] == (60, 100)
    assert mask[:, :45].min() == 255 and mask[:, 55:].max() == 0
    # the click in the upright picture's pixels, scaled to the model's side
    assert np.allclose(seg.decoder.got["input_points"][0, 0, 0], [25 * 32 / 100, 30 * 32 / 60])


def test_a_selection_picks_its_candidate_by_size_largest_first(tmp_path):
    # three candidates as SAM gives them: a detail (rated best), the whole thing, a part
    path = str(tmp_path / "p.png")
    Image.new("RGB", (16, 16)).save(path)
    low = np.full((1, 1, 3, 16, 16), -1.0, np.float32)
    low[0, 0, 0, :2, :2] = 1.0   # 4 pixels
    low[0, 0, 1, :, :] = 1.0     # 256
    low[0, 0, 2, :8, :8] = 1.0   # 64
    seg = object.__new__(photo_tools.Segmenter)
    seg.m, seg.image, seg.embeddings = {"size": 16}, None, None
    seg.encoder = _Session(["pixel_values"], {"image_embeddings": np.zeros((1, 4, 2, 2), np.float32)})
    seg.decoder = _Session(["input_points", "input_labels", "image_embeddings"],
                           {"iou_scores": np.array([[[0.9, 0.5, 0.7]]], np.float32), "pred_masks": low})
    out = str(tmp_path / "m.png")

    def area(pick):
        seg.select(path, [[1, 1, 1]], out, pick)
        return int((np.asarray(Image.open(out)) > 0).sum())

    # 0 = the whole thing, then ever smaller, and round again
    assert [area(p) for p in (0, 1, 2, 3)] == [256, 64, 4, 256]
    ans = seg.select(path, [[1, 1, 1]], out, 1)
    assert (ans["pick"], ans["candidates"], round(ans["score"], 2)) == (1, 3, 0.7)
    # no pick: the one SAM rates best, with its place by size
    ans = seg.select(path, [[1, 1, 1], [9, 9, 0]], out)
    assert (ans["pick"], round(ans["score"], 2)) == (2, 0.9)
    assert int((np.asarray(Image.open(out)) > 0).sum()) == 4


def test_a_selection_leaves_out_candidates_the_same_as_another(tmp_path):
    # SAM gives the whole thing twice and a part: two candidates, so the next pick always changes the mask
    path = str(tmp_path / "p.png")
    Image.new("RGB", (16, 16)).save(path)
    low = np.full((1, 1, 3, 16, 16), -1.0, np.float32)
    low[0, 0, 0, :, :] = 1.0
    low[0, 0, 1, :, :] = 2.0     # the same shape, other values
    low[0, 0, 2, :8, :8] = 1.0
    seg = object.__new__(photo_tools.Segmenter)
    seg.m, seg.image, seg.embeddings = {"size": 16}, None, None
    seg.encoder = _Session(["pixel_values"], {"image_embeddings": np.zeros((1, 4, 2, 2), np.float32)})
    seg.decoder = _Session(["input_points", "input_labels", "image_embeddings"],
                           {"iou_scores": np.array([[[0.5, 0.9, 0.7]]], np.float32), "pred_masks": low})
    out = str(tmp_path / "m.png")
    ans = seg.select(path, [[1, 1, 1]], out)
    # the best rated one is the duplicate: it takes the place of the shape kept
    assert (ans["pick"], ans["candidates"]) == (0, 2)
    areas = []
    for p in (0, 1, 2):
        seg.select(path, [[1, 1, 1]], out, p)
        areas.append(int((np.asarray(Image.open(out)) > 0).sum()))
    assert areas == [256, 64, 256]


def test_a_tool_works_on_the_upright_picture_of_a_rotated_jpeg(helpers, tmp_path):
    # a phone portrait stored on its side (EXIF orientation 6): the result and a selection's mask are upright
    folder, _ = photo_tools.import_file(os.path.join(FIX, "enlarge2.onnx"))
    path = str(tmp_path / "rotated.jpg")
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", (70, 40)).save(path, exif=exif)
    out = photo_tools.apply({"photo_tool": {"folder": folder}, "input_image": path}, tmp_path)
    assert Image.open(out).size == (80, 140)


def test_a_click_selection_is_one_piece_without_dots_or_holes():
    # SAM unsure on a glass bottle: a pattern of dots (hand test); and a second thing apart from the click
    low = np.full((32, 32), -1.0, np.float32)
    low[4:28, 4:14] = 1.0
    low[4:28, 4:14][(np.add.outer(np.arange(24), np.arange(10)) % 2) == 1] = -1.0  # every other pixel
    low[10:12, 8:10] = -1.0  # a hole
    low[4:10, 20:30] = 1.0   # something else
    out = photo_tools.whole(low, [(8, 16)])
    # the bottle whole (the outermost corner pixels of the pattern aside)
    assert (out[5:27, 5:13] > 0).all() and (out[4:28, 4:14] > 0).mean() > 0.99
    assert (out[4:10, 20:30] <= 0).all()          # the other thing left out
    assert (out[:, 15:19] <= 0).all() and (out[0] <= 0).all()
    # no click on any part: all parts stay
    assert (photo_tools.whole(low, [(17, 30)])[4:10, 20:30] > 0).all()


def test_a_hole_with_a_not_this_click_stays_open_and_a_click_beside_the_picture_counts_at_its_edge():
    ring = np.full((20, 20), -1.0, np.float32)
    ring[2:18, 2:18] = 1.0
    ring[7:13, 7:13] = -1.0  # the gap in a mug's handle
    assert (photo_tools.whole(ring, [(3, 3)])[7:13, 7:13] > 0).all()
    assert (photo_tools.whole(ring, [(3, 3)], [(10, 10)])[7:13, 7:13] <= 0).all()
    # x = -1 would have wrapped round to the other side (nothing there): the part at the left edge is taken
    edge = np.full((20, 20), -1.0, np.float32)
    edge[:, :5] = 1.0
    edge[:, 15:] = 1.0
    out = photo_tools.whole(edge, [(-1, 10)])
    assert (out[:, :5] > 0).all() and (out[:, 15:] <= 0).all()
