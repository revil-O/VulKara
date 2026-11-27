# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Scans (scans.py): the photos on a flatbed scan found, straightened and cut out, with drawn test scans."""
import json
import io

import cv2
import numpy as np
import pytest

from PIL import Image, ImageCms

import scans

W, H = 2480, 3508  # A4 at 300 dpi


def photo(w, h, seed=1, top_bright=False):
    """A photo: smooth colours with texture, as a print has."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w]
    img = np.stack([80 + 60 * np.sin(x / 37.0), 90 + 50 * np.cos(y / 53.0), 120 + 40 * np.sin((x + y) / 71.0)], -1)
    img += rng.normal(0, 12, img.shape)
    if top_bright:
        img[: h // 2] = 235 + rng.normal(0, 3, (h // 2, w, 3))
    return np.clip(img, 0, 255).astype(np.uint8)


def scan(places, seed=0):
    """A white scanner background with the photos pasted in: places = [(photo, cx, cy, angle)]."""
    rng = np.random.default_rng(seed)
    out = np.clip(250 + rng.normal(0, 2, (H, W, 3)), 0, 255).astype(np.uint8)
    for img, cx, cy, angle in places:
        h, w = img.shape[:2]
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        m[0, 2] += cx - w / 2
        m[1, 2] += cy - h / 2
        mask = cv2.warpAffine(np.full((h, w), 255, np.uint8), m, (W, H))
        pasted = cv2.warpAffine(img, m, (W, H), flags=cv2.INTER_LINEAR)
        out[mask > 127] = pasted[mask > 127]
    return out


def close(a, b, tol):
    return abs(a - b) <= tol


def test_one_straight_photo():
    found = scans.find_photos(scan([(photo(1200, 900), 1000, 1200, 0)]))
    assert len(found) == 1
    p = found[0]
    assert close(p["cx"], 1000, W * 0.01) and close(p["cy"], 1200, H * 0.01)
    assert close(max(p["w"], p["h"]), 1200, 1200 * 0.02) and close(min(p["w"], p["h"]), 900, 900 * 0.02)
    assert abs(p["angle"]) <= 0.3 and p["turn"] == 0


def test_tilted_photo_reports_small_angle():
    p = scans.find_photos(scan([(photo(1200, 900), 1240, 1500, 3)]))[0]
    assert close(abs(p["angle"]), 3, 0.3) and abs(p["angle"]) <= 45


def test_three_photos_in_reading_order():
    found = scans.find_photos(scan([(photo(900, 700, 3), 700, 2600, 0), (photo(900, 700, 2), 1800, 700, 1),
                                    (photo(900, 700, 1), 640, 760, -1)]))
    assert [(round(p["cx"] / 100), round(p["cy"] / 100)) for p in found] == [(6, 8), (18, 7), (7, 26)]


def test_close_photos_stay_apart():
    # 7 px on the scan are 3 px at the 1500 px working size
    found = scans.find_photos(scan([(photo(1000, 800, 1), 700, 1000, 0), (photo(1000, 800, 2), 700 + 1000 + 7, 1000, 0)]))
    assert len(found) == 2


def test_bright_sky_edge_is_kept():
    found = scans.find_photos(scan([(photo(1200, 900, top_bright=True), 1240, 1500, 0)]))
    assert len(found) == 1
    assert close(min(found[0]["w"], found[0]["h"]), 900, 900 * 0.02)


def bordered(w, h, border, seed=1):
    """A print with a white paper border around the picture."""
    inner = photo(w - 2 * border, h - 2 * border, seed)
    return cv2.copyMakeBorder(inner, border, border, border, border, cv2.BORDER_CONSTANT, value=(239, 240, 241))


def test_white_print_border_is_cut_off():
    p = scans.find_photos(scan([(bordered(1200, 900, 40), 1240, 1500, 2)]))[0]
    assert close(max(p["w"], p["h"]), 1120, 1120 * 0.015) and close(min(p["w"], p["h"]), 820, 820 * 0.015)


def test_a_wide_bright_band_is_not_cut_off():
    img = photo(1200, 900)
    img[:200] = 240  # a pale sky over a fifth of the photo: more than a paper border can be
    p = scans.find_photos(scan([(img, 1240, 1500, 0)]))[0]
    assert close(min(p["w"], p["h"]), 900, 900 * 0.02)


def test_empty_scan_finds_nothing():
    assert scans.find_photos(scan([])) == []


def test_sixteen_bit_and_gray_inputs():
    eight = scan([(photo(1200, 900), 1000, 1200, 2)])
    want = scans.find_photos(eight)[0]
    for img in (eight.astype(np.uint16) * 257, cv2.cvtColor(eight, cv2.COLOR_BGR2GRAY)):
        got = scans.find_photos(img)[0]
        assert close(got["cx"], want["cx"], 3) and close(got["w"], want["w"], 3) and close(got["angle"], want["angle"], 0.2)


def test_main_prints_one_line(tmp_path, capsys):
    path = tmp_path / "s.png"
    cv2.imwrite(str(path), scan([(photo(1200, 900), 1000, 1200, 0)]))
    assert scans.find_main([str(path)]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and lines[0].startswith("__photos__ ")
    data = json.loads(lines[0].split(" ", 1)[1])
    assert data["size"] == [W, H] and len(data["photos"]) == 1
    assert scans.find_main([str(tmp_path / "missing.png")]) == 1
    assert capsys.readouterr().out.startswith("__error__ ")



# ------------------------------------------------------------------ cutting out and saving


def rect(cx, cy, w, h, angle=0.0, turn=0):
    return {"cx": cx, "cy": cy, "w": w, "h": h, "angle": angle, "turn": turn}


def saved(tmp_path, img, name="Album3_Seite12.png", **info):
    path = tmp_path / name
    if info:
        Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).save(path, **info)
    else:
        cv2.imwrite(str(path), img)
    return str(path)


def test_cut_names_and_order(tmp_path):
    src = saved(tmp_path, scan([(photo(900, 700, 1), 640, 760, 0), (photo(900, 700, 2), 1800, 700, 0)]))
    files = scans.cut_photos(src, [rect(640, 760, 880, 680), rect(1800, 700, 880, 680)], str(tmp_path / "out"), "Foto")
    assert [f.rsplit("/", 1)[1] for f in files] == ["Album3_Seite12 – Foto 1.png", "Album3_Seite12 – Foto 2.png"]


def test_never_overwrites(tmp_path):
    src = saved(tmp_path, scan([(photo(900, 700), 640, 760, 0)]))
    out = tmp_path / "out"
    out.mkdir()
    old = out / "Album3_Seite12 – Photo 1.png"
    old.write_bytes(b"mine")
    files = scans.cut_photos(src, [rect(640, 760, 880, 680)], str(out), "Photo")
    assert files[0].endswith("Album3_Seite12 – Photo 1 (2).png") and old.read_bytes() == b"mine"


def test_sixteen_bit_stays_sixteen(tmp_path):
    src = saved(tmp_path, scan([(photo(900, 700), 640, 760, 0)]).astype(np.uint16) * 257)
    out = cv2.imread(scans.cut_photos(src, [rect(640, 760, 880, 680)], str(tmp_path), "Photo")[0], cv2.IMREAD_UNCHANGED)
    assert out.dtype == np.uint16 and out.ndim == 3 and out.shape[2] == 3


def test_jpeg_becomes_eight_bit_png(tmp_path):
    src = saved(tmp_path, scan([(photo(900, 700), 640, 760, 0)]), "s.jpg")
    out = scans.cut_photos(src, [rect(640, 760, 880, 680)], str(tmp_path), "Photo")[0]
    assert out.endswith(".png") and cv2.imread(out, cv2.IMREAD_UNCHANGED).dtype == np.uint8


@pytest.mark.parametrize("sixteen", [False, True])
def test_dpi_and_icc_are_kept(tmp_path, sixteen):
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    src = saved(tmp_path, scan([(photo(900, 700), 640, 760, 0)]), dpi=(600, 600), icc_profile=icc)
    if sixteen:  # a 16-bit scan with the same DPI and profile: written by the module's own PNG writer
        img = cv2.imread(src, cv2.IMREAD_UNCHANGED).astype(np.uint16) * 257
        src = str(tmp_path / "Album3_Seite12_16.png")
        scans.write_png(src, img, (600, 600), icc)
    out = Image.open(scans.cut_photos(src, [rect(640, 760, 880, 680)], str(tmp_path / "o"), "Photo")[0])
    assert round(out.info["dpi"][0]) == 600 and out.info["icc_profile"] == icc


def test_straightened_has_no_white_border(tmp_path):
    src = saved(tmp_path, scan([(photo(1200, 900), 1240, 1500, 3)]))
    p = scans.find_photos(cv2.imread(src))[0]
    out = cv2.imread(scans.cut_photos(src, [p], str(tmp_path / "o"), "Photo")[0])
    rim = np.concatenate([out[:2].reshape(-1, 3), out[-2:].reshape(-1, 3), out[:, :2].reshape(-1, 3), out[:, -2:].reshape(-1, 3)])
    assert (rim.min(axis=1) > 240).mean() < 0.05


def test_turn_rotates_losslessly(tmp_path):
    src = saved(tmp_path, scan([(photo(900, 700), 640, 760, 0)]))
    upright = cv2.imread(scans.cut_photos(src, [rect(640, 760, 880, 680)], str(tmp_path / "a"), "Photo")[0])
    turned = cv2.imread(scans.cut_photos(src, [rect(640, 760, 880, 680, turn=90)], str(tmp_path / "b"), "Photo")[0])
    assert turned.shape[:2] == upright.shape[1::-1] and np.array_equal(turned, np.rot90(upright, -1))  # clockwise


def test_frame_outside_is_clipped(tmp_path):
    src = saved(tmp_path, scan([(photo(900, 700), 640, 760, 0)]))
    out = cv2.imread(scans.cut_photos(src, [rect(100, 760, 880, 680)], str(tmp_path / "o"), "Photo")[0])
    assert out.shape[1] == pytest.approx(540, abs=2)  # from x = 0 to 540, not 880 wide with smeared edges


def test_missing_out_dir_is_created(tmp_path):
    src = saved(tmp_path, scan([(photo(900, 700), 640, 760, 0)]))
    files = scans.cut_photos(src, [rect(640, 760, 880, 680)], str(tmp_path / "new" / "folder"), "Photo")
    assert (tmp_path / "new" / "folder").is_dir() and len(files) == 1


def test_cut_main_reports_files_and_errors(tmp_path, capsys):
    src = saved(tmp_path, scan([(photo(900, 700), 640, 760, 0)]))
    job = tmp_path / "job.json"
    job.write_text(json.dumps({"scan": src, "photos": [rect(640, 760, 880, 680)], "out": str(tmp_path / "o"), "word": "Photo"}))
    assert scans.cut_main([str(job)]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].startswith("__progress__ ") and lines[-1].startswith("__cut__ ")
    assert len(json.loads(lines[-1].split(" ", 1)[1])["files"]) == 1
    job.write_text(json.dumps({"scan": str(tmp_path / "gone.png"), "photos": [], "out": str(tmp_path), "word": "Photo"}))
    assert scans.cut_main([str(job)]) == 1 and capsys.readouterr().out.strip().splitlines()[-1].startswith("__error__ ")


# ------------------------------------------------------------------ after the review


def test_dark_scanner_edge_is_not_a_photo():
    img = scan([(photo(1200, 900), 1240, 1500, 2)])
    img[:15], img[-15:], img[:, :15], img[:, -15:] = 40, 40, 40, 40  # the dark strip some scanners leave all round
    found = scans.find_photos(img)
    assert len(found) == 1 and close(found[0]["cx"], 1240, 25) and close(max(found[0]["w"], found[0]["h"]), 1200, 1200 * 0.02)


def test_dark_strip_at_one_edge_is_not_a_photo():
    img = scan([(photo(1200, 900), 1240, 1500, 0)])
    img[:, :20] = 35
    assert len(scans.find_photos(img)) == 1


def test_bright_band_at_one_edge_of_a_photo_is_kept():
    img = photo(1200, 900)
    img[:40] = 240  # a pale sky along the top only: a paper border runs all round
    p = scans.find_photos(scan([(img, 1240, 1500, 0)]))[0]
    assert close(min(p["w"], p["h"]), 900, 900 * 0.02)


def test_cut_refuses_a_frame_outside_or_larger_than_the_scan(tmp_path):
    src = saved(tmp_path, scan([(photo(900, 700), 640, 760, 0)]))
    with pytest.raises(ValueError):
        scans.cut_photos(src, [rect(9999, 760, 880, 680)], str(tmp_path / "o"), "Photo")
    with pytest.raises(ValueError):
        scans.cut_photos(src, [rect(640, 760, 1e5, 1e5)], str(tmp_path / "o"), "Photo")


def test_write_png_never_replaces_a_file(tmp_path):
    path = tmp_path / "x.png"
    path.write_bytes(b"mine")
    with pytest.raises(FileExistsError):
        scans.write_png(str(path), np.zeros((4, 4, 3), np.uint8))
    assert path.read_bytes() == b"mine"


def test_grey_scan_gets_no_colour_profile_of_rgb(tmp_path):
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    grey = cv2.cvtColor(scan([(photo(900, 700), 640, 760, 0)]), cv2.COLOR_BGR2GRAY)
    src = str(tmp_path / "g.png")
    Image.fromarray(grey).save(src, dpi=(300, 300), icc_profile=icc)
    out = Image.open(scans.cut_photos(src, [rect(640, 760, 880, 680)], str(tmp_path / "o"), "Photo")[0])
    assert "icc_profile" not in out.info and round(out.info["dpi"][0]) == 300


def test_unreadable_metadata_does_not_stop_the_cut(tmp_path, monkeypatch):
    src = saved(tmp_path, scan([(photo(900, 700), 640, 760, 0)]))
    monkeypatch.setattr(Image, "open", lambda *a, **k: (_ for _ in ()).throw(Image.DecompressionBombError("too big")))
    assert len(scans.cut_photos(src, [rect(640, 760, 880, 680)], str(tmp_path / "o"), "Photo")) == 1


def test_dpi_follows_a_turned_jpeg(tmp_path):
    img = Image.fromarray(cv2.cvtColor(scan([(photo(900, 700), 640, 760, 0)]), cv2.COLOR_BGR2RGB))
    exif = Image.Exif()
    exif[274] = 6  # shown turned a quarter clockwise
    src = str(tmp_path / "t.jpg")
    img.save(src, dpi=(300, 600), exif=exif)
    assert scans._scan_info(src)[0] == (600, 300)


def test_a_slight_tilt_of_a_wide_photo_is_straightened():
    # the far edge moves 0.26 px on a 300 px photo, 2.1 px on a 2400 px one
    assert scans.straight({"w": 300, "h": 200, "angle": 0.05}) and not scans.straight({"w": 2400, "h": 1800, "angle": 0.05})
