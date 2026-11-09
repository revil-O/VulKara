# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Restore's colour handling and AI steps: pictures read as sRGB (also HDR), a correction that does not clip white,
soft detail rebuilt (Real-ESRGAN) and faces restored (CodeFormer) - the models replaced by stand-ins here."""
import io
import os
import re
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import colour  # noqa: E402
import restore as rs  # noqa: E402


def test_a_picture_without_a_profile_or_in_srgb_is_read_as_it_is(tmp_path):
    from PIL import ImageCms
    a = (np.random.default_rng(1).random((20, 30, 3)) * 255).astype(np.uint8)
    plain = tmp_path / "plain.png"
    Image.fromarray(a).save(plain)
    assert np.array_equal(np.asarray(colour.open_rgb(plain)), a)
    tagged = tmp_path / "srgb.png"
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    Image.fromarray(a).save(tagged, icc_profile=srgb)
    assert np.abs(np.asarray(colour.open_rgb(tagged)).astype(int) - a).max() <= 1


def test_a_photo_with_an_exif_orientation_is_read_upright_as_the_app_shows_it(tmp_path):
    a = np.zeros((20, 40, 3), np.uint8)
    a[:, :10] = 255  # white on the left
    exif = Image.Exif()
    exif[0x0112] = 6  # turned 90° clockwise for viewing
    p = str(tmp_path / "phone.jpg")
    Image.fromarray(a).save(p, exif=exif.tobytes(), quality=95)
    up = np.asarray(colour.open_rgb(p))
    assert up.shape[:2] == (40, 20)
    assert up[:10].mean() > 200 and up[-10:].mean() < 50  # the left edge is now at the top


def test_hdr_profiles_are_recognised_and_pq_paper_white_becomes_white():
    assert colour._hdr_kind("Rec. 2020 PQ") == "pq"
    assert colour._hdr_kind("ITU-R BT.2100 HLG") == "hlg"
    assert colour._hdr_kind("Display P3") is None and colour._hdr_kind("sRGB IEC61966-2.1") is None
    # 203 cd/m² (paper white) is PQ code 0.58: it becomes linear 1, then sRGB white, not the grey 148 it reads as
    lin = colour._pq_to_linear(np.array([0.58]))
    assert abs(lin[0] - 1) < 0.03
    out = colour._to_srgb8(np.array([[[1.0, 1.0, 1.0]], [[0.0, 0.0, 0.0]], [[4.0, 4.0, 4.0]]]))
    assert out[0, 0, 0] >= 245 and out[1, 0, 0] == 0 and out[2, 0, 0] == 255  # brighter than white: compressed to it
    assert colour._hlg_to_linear(np.array([0.75]))[0] > 0.98


def test_the_correction_keeps_the_folds_of_a_white_dress_and_its_strength_blends():
    # a dull photo with a light area of fine folds (as a wedding dress), shown at 60 % of white
    rng = np.random.default_rng(2)
    a = np.full((200, 200), 60.0)
    a[60:140, 60:140] = 140 + 12 * np.sin(np.arange(80) / 3.0)[None, :]
    a += rng.normal(0, 2, a.shape)
    img = Image.fromarray(np.repeat(a.clip(0, 255).astype(np.uint8)[..., None], 3, 2))
    out = np.asarray(rs.correct(img).convert("L")).astype(int)
    folds = out[70:130, 70:130]
    assert (out >= 254).mean() < 0.003  # hardly anything clipped
    assert folds.std() > 6  # the folds are still there
    assert folds.mean() > 170  # and the area is light now
    same = rs.correct(img, strength=0)
    assert np.array_equal(np.asarray(same), np.asarray(img))


def _fake_upscaler(monkeypatch, tmp_path):
    import helpers
    import photo_tools
    (tmp_path / rs.DETAIL_TOOL["model"]).write_bytes(b"w")
    monkeypatch.setattr(helpers, "folder_of", lambda h: str(tmp_path))
    calls = []

    def run_image(m, folder, rgb, report=None, stop=None, **k):
        calls.append(rgb.shape)
        if stop and stop():
            return None
        return np.repeat(np.repeat(rgb, 4, 0), 4, 1)  # four times larger, nearest

    monkeypatch.setattr(photo_tools, "run_image", run_image)
    return calls


def test_details_make_the_photo_as_small_as_it_is_soft_and_bring_it_to_its_size(monkeypatch, tmp_path):
    calls = _fake_upscaler(monkeypatch, tmp_path)
    img = Image.fromarray((np.random.default_rng(3).random((300, 200, 3)) * 255).astype(np.uint8))
    out = rs.details(img, level=2.0)
    assert out.size == (200, 300) and calls[-1][:2] == (150, 100)
    big = rs.details(img, level=2.0, scale=2)
    assert big.size == (400, 600)
    assert rs.details(img, level=2.0, stop=lambda: True) is None  # stopped
    half = np.asarray(rs.details(img, level=2.0, strength=0.5)).astype(int)
    full = np.asarray(out).astype(int)
    assert np.abs(half - np.asarray(img).astype(int)).mean() < np.abs(full - np.asarray(img).astype(int)).mean()


def test_details_keep_the_tone_of_a_black_and_white_photo(monkeypatch, tmp_path):
    _fake_upscaler(monkeypatch, tmp_path)
    import photo_tools
    # a model that tints: the photo must stay grey
    monkeypatch.setattr(photo_tools, "run_image", lambda m, f, rgb, **k: np.clip(np.repeat(np.repeat(rgb, 4, 0), 4, 1).astype(int) + [30, 0, -30], 0, 255).astype(np.uint8))
    g = (np.random.default_rng(4).random((80, 80)) * 200 + 20).astype(np.uint8)
    img = Image.fromarray(np.repeat(g[..., None], 3, 2))
    out = np.asarray(rs.details(img, level=2.0)).astype(int)
    assert np.abs(out[..., 0] - out[..., 2]).max() <= 3


def test_faces_are_restored_only_where_they_are_and_by_the_strength(monkeypatch, tmp_path):
    import torch

    class Net:  # a face model that paints its square white
        def __call__(self, t, weight=0.5):
            return torch.ones_like(t)

    monkeypatch.setattr(rs, "_codeformer", lambda device, report=None: Net())
    monkeypatch.setattr(rs, "_face_files", lambda report=None: str(tmp_path))
    # one face: eyes, nose, mouth corners about 60 px apart around (150, 150)
    pts = np.array([[130, 135], [170, 135], [150, 155], [135, 175], [165, 175]], np.float32)
    monkeypatch.setattr(rs, "find_faces", lambda rgb, path: [pts])
    img = Image.fromarray(np.full((400, 400, 3), 60, np.uint8))
    out, n = rs.restore_faces(img, fidelity=0.8, strength=1.0)
    a = np.asarray(out).astype(int)
    assert n == 1 and a[150, 150, 0] > 200 and a[10, 10, 0] == 60 and a[390, 390, 0] == 60
    weak, _ = rs.restore_faces(img, strength=0.5)
    assert 100 < np.asarray(weak)[150, 150, 0] < 200


def test_small_faces_are_left_alone():
    assert rs.FACE_MIN >= 10


def test_the_preview_part_is_clamped_into_the_photo_and_auto_takes_the_middle():
    import engine
    assert engine._preview_box(None, (1000, 800)) is None
    assert engine._preview_box({"x": -50, "y": 700, "w": 300, "h": 300}, (1000, 800)) == (0, 500, 300, 800)
    assert engine._preview_box({"x": 10, "y": 10, "w": 5000, "h": 20}, (1000, 800)) == (0, 10, 1000, 74)
    assert engine._preview_box({"auto": True, "w": 768, "h": 768}, (1000, 800)) == (116, 16, 884, 784)


def test_the_preview_file_name_tells_its_part(tmp_path):
    import engine
    e = object.__new__(engine.DiffusersEngine)
    e.images_dir = tmp_path
    path = e._save_preview(Image.new("RGB", (64, 64)), (10, 20, 74, 84))
    assert re.search(r"preview_x10_y20_w64_h64_[0-9a-f]+\.png$", path) and os.path.dirname(path).endswith(engine.PREVIEWS)
    for i in range(14):
        e._save_preview(Image.new("RGB", (64, 64)), (0, 0, 64, 64))
    assert len(os.listdir(tmp_path / engine.PREVIEWS)) <= 12


def test_the_restored_square_of_a_face_surrounds_its_landmarks():
    pts = [[130, 135], [170, 135], [150, 155], [135, 175], [165, 175]]
    x, y, w, h = rs.face_square(pts)
    assert x < 130 and y < 135 and x + w > 170 and y + h > 175
    assert 0.9 < w / h < 1.1 and 60 < w < 200


def test_faces_placed_by_the_user_are_used_and_follow_the_preview_part_and_the_scale(monkeypatch, tmp_path):
    import engine
    pts = [[130, 135], [170, 135], [150, 155], [135, 175], [165, 175]]
    assert engine._face_points(None, None, 1) is None
    assert engine._face_points([], None, 1) == []
    assert engine._face_points([pts], None, 2)[0][0] == [260, 270]
    # in a preview of the part (100, 100)-(300, 300) the face moves by the part's corner; one outside is left out
    far = [[q[0] + 500, q[1]] for q in pts]
    inside = engine._face_points([pts, far], (100, 100, 300, 300), 1)
    assert len(inside) == 1 and inside[0][0] == [30, 35]
    # the restoration takes the given landmarks, it does not look for faces itself
    import torch

    class Net:
        def __call__(self, t, weight=0.5):
            return torch.ones_like(t)

    def searched(rgb, path):
        raise AssertionError("searched")

    monkeypatch.setattr(rs, "_codeformer", lambda device, report=None: Net())
    monkeypatch.setattr(rs, "_face_files", lambda report=None: str(tmp_path))
    monkeypatch.setattr(rs, "find_faces", searched)
    img = Image.fromarray(np.full((400, 400, 3), 60, np.uint8))
    out, n = rs.restore_faces(img, strength=1.0, points=[pts])
    assert n == 1 and np.asarray(out)[150, 150, 0] > 200
    out, n = rs.restore_faces(img, points=[])
    assert n == 0 and np.array_equal(np.asarray(out), np.asarray(img))


def test_finding_faces_prints_one_line_for_the_app(monkeypatch, tmp_path, capsys):
    import json
    path = tmp_path / "photo.png"
    Image.new("RGB", (300, 200), (90, 90, 90)).save(path)
    pts = np.array([[130, 135], [170, 135], [150, 155], [135, 175], [165, 175]], np.float32)
    monkeypatch.setattr(rs, "detector_path", lambda: "x")
    monkeypatch.setattr(rs, "find_faces", lambda rgb, path: [pts])
    assert rs.faces_main([str(path)]) == 0
    line = capsys.readouterr().out.strip()
    assert line.startswith("__faces__ ")
    d = json.loads(line[len("__faces__ "):])
    assert d["size"] == [300, 200] and len(d["faces"]) == 1
    assert len(d["faces"][0]["points"]) == 5 and len(d["faces"][0]["box"]) == 4


def _dusty():
    """A calm grey photo with dust and a scratch on the left, busy texture (leaves) on the right."""
    import cv2
    rng = np.random.default_rng(3)
    g = np.full((600, 800), 120.0)
    g[:, 400:] += cv2.GaussianBlur(rng.normal(0, 40, (600, 400)), (0, 0), 2.0) * 3  # leaves
    g += rng.normal(0, 2, g.shape)
    specks = [(60, 80), (200, 150), (330, 300), (500, 90)]
    for y, x in specks:
        cv2.circle(g, (x, y), 2, 15.0, -1)
    cv2.line(g, (300, 40), (330, 260), 235.0, 1)
    img = Image.fromarray(np.repeat(np.clip(g, 0, 255).astype(np.uint8)[..., None], 3, 2))
    return img, specks


def test_dust_and_a_scratch_on_calm_ground_are_found_and_texture_is_left():
    img, specks = _dusty()
    m = rs.find_specks(img, 0.5)
    assert all(m[y, x] for y, x in specks)
    assert m[150, 314] or m[149, 314] or m[151, 315]  # on the scratch
    assert m[:, 400:].mean() < 0.002  # hardly anything among the leaves
    assert m.mean() < 0.01


def test_eyes_and_mouth_are_not_taken_for_dust():
    img, _ = _dusty()
    # a face whose left eye sits on the first speck
    face = [[80, 60], [120, 60], [100, 80], [85, 100], [115, 100]]
    m = rs.find_specks(img, 0.5, [face])
    assert not m[60, 80]


def test_removing_dust_fills_the_specks(monkeypatch):
    img, specks = _dusty()
    monkeypatch.setattr(rs, "fill", lambda im, m, report=None: (_ for _ in ()).throw(RuntimeError("no LaMa here")))
    out, share = rs.remove_specks(img, 0.5)
    a = np.asarray(out.convert("L")).astype(int)
    assert 0 < share < 0.01
    assert all(a[y, x] > 80 for y, x in specks)  # the dark specks are gone (OpenCV filled them)


def test_the_consistency_lora_is_a_pinned_helper_for_klein_4b(monkeypatch, tmp_path):
    import helpers
    import pinned
    h = next(x for x in helpers.catalog() if x["id"] == rs.CONSISTENCY_HELPER)
    revision, files = pinned.pins(h["repo"])
    assert files[rs.CONSISTENCY_FILE] and len(revision) == 40
    fetched = []
    monkeypatch.setattr(rs, "helper_folder", lambda helper_id: str(tmp_path))
    monkeypatch.setattr(helpers, "install", lambda helper_id, report=None: fetched.append(helper_id))
    lora = rs.consistency_lora()
    assert fetched == [rs.CONSISTENCY_HELPER]  # downloaded on first use
    assert lora["file"] == os.path.join(str(tmp_path), rs.CONSISTENCY_FILE) and lora["scale"] == 1.0
    assert lora["plan_gb"] >= 1.1  # it adds 1.1-2.2 GB while denoising (7bh)


def test_keep_the_picture_adds_the_consistency_lora_at_half_strength_for_klein_4b(monkeypatch):
    # image to image: at 1.0 the LoRA held the edit back, at 0.5 it kept the picture and made the edit (7bi)
    import engine
    import protocol
    notes = []
    monkeypatch.setattr(protocol, "note", notes.append)
    monkeypatch.setattr(rs, "consistency_lora", lambda scale=1.0, report=None: {"scale": scale})
    k4 = {"arch": "flux2_klein", "family": "flux2", "components": {"transformer": 3.9}}
    k9 = {"arch": "flux2_klein", "family": "flux2", "components": {"transformer": 8.1}}
    on = {"keep_picture": True}
    assert engine.keep_picture_loras(on, k4, picture=True) == [{"scale": rs.KEEP_PICTURE_SCALE}]
    assert rs.KEEP_PICTURE_SCALE == 0.5
    assert engine.keep_picture_loras({}, k4, picture=True) == []
    assert engine.keep_picture_loras(on, k4, picture=False) == []  # text to image
    assert engine.keep_picture_loras({**on, "mask_image": "m.png"}, k4, picture=True) == []  # inpainting
    assert engine.keep_picture_loras(on, k9, picture=True) == [] and "made for FLUX.2 [klein] 4B" in notes[0]
