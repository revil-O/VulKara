# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Converging verticals straightened (upright.py), with drawn façades seen from below."""
import math

import cv2
import numpy as np
import pytest
from PIL import Image

import photo_tools
import upright

W, H = 1200, 900


def facade(seed=3):
    """A building front: window columns and storeys on a textured wall, with sky above."""
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), (150, 170, 190), np.uint8)
    img[:120] = (220, 200, 170)
    img += rng.integers(0, 12, img.shape, dtype=np.uint8)
    for x in range(120, W - 100, 140):
        cv2.line(img, (x, 130), (x, H - 20), (40, 40, 50), 6)
        for y in range(180, H - 60, 120):
            cv2.rectangle(img, (x + 25, y), (x + 95, y + 70), (70, 90, 120), -1)
    for y in range(130, H, 120):
        cv2.line(img, (100, y), (W - 100, y), (60, 60, 70), 3)
    return img


def seen_from_below(img, pull=0.18):
    """The verticals converge towards the top, as with a camera tilted upwards."""
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    dst = np.float32([[W * pull, 0], [W * (1 - pull), 0], [W, H], [0, H]])
    return cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (W, H), borderMode=cv2.BORDER_REPLICATE)


def vertical_tilts(img):
    """How far (degrees) the long, nearly vertical lines of a picture lean."""
    edges = cv2.Canny(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 80, minLineLength=img.shape[0] // 4, maxLineGap=10)
    out = []
    for x1, y1, x2, y2 in (lines.reshape(-1, 4) if lines is not None else []):
        a = math.degrees(math.atan2(x2 - x1, y2 - y1))
        a = (a + 90) % 180 - 90
        if abs(a) < 30:
            out.append(abs(a))
    return out


def test_converging_verticals_come_out_upright():
    tilted = seen_from_below(facade())
    assert np.median(vertical_tilts(tilted)) > 3  # the test picture really leans
    out, found = upright.straighten(tilted, 1.0)
    assert found
    tilts = vertical_tilts(out)
    assert len(tilts) >= 4 and np.median(tilts) < 0.5


def test_half_strength_corrects_about_half():
    tilted = seen_from_below(facade())
    full = np.median(vertical_tilts(tilted))
    half = np.median(vertical_tilts(upright.straighten(tilted, 0.5)[0]))
    assert 0.3 * full < half < 0.7 * full


def test_strength_zero_leaves_the_photo_as_it_is():
    tilted = seen_from_below(facade())
    out, _ = upright.straighten(tilted, 0.0)
    assert np.array_equal(out, tilted)


def test_a_photo_without_straight_lines_stays_as_it_is():
    rng = np.random.default_rng(1)
    noise = cv2.GaussianBlur(rng.integers(0, 255, (H, W, 3), dtype=np.uint8), (0, 0), 6)
    out, found = upright.straighten(noise, 1.0)
    assert not found and np.array_equal(out, noise)


def test_the_result_has_no_empty_corners():
    out, _ = upright.straighten(seen_from_below(facade()), 1.0)
    corners = [out[0, 0], out[0, -1], out[-1, 0], out[-1, -1]]
    assert all(int(c.max()) > 30 for c in corners)  # the façade never has black, only the empty border would
    assert out.shape[0] > H * 0.6 and out.shape[1] > W * 0.5


def test_an_upright_photo_is_left_alone():
    img = facade()
    out, found = upright.straighten(img, 1.0)
    assert found and out.shape == img.shape and np.abs(out.astype(int) - img.astype(int)).mean() < 1


def test_the_tool_runs_through_the_photo_tools(tmp_path):
    src = tmp_path / "house.png"
    Image.fromarray(seen_from_below(facade())).save(src)
    notes = []
    path = photo_tools.apply({"photo_tool": {"folder": upright.TOOL_ID, "strength": 1.0}, "input_image": str(src)},
                             str(tmp_path), note=notes.append)
    assert path and path.endswith(".png") and "upright" in path and Image.open(path).size[0] > W * 0.5


def test_the_tool_says_so_when_it_finds_no_lines(tmp_path):
    rng = np.random.default_rng(2)
    src = tmp_path / "fog.png"
    Image.fromarray(cv2.GaussianBlur(rng.integers(0, 255, (H, W, 3), dtype=np.uint8), (0, 0), 6)).save(src)
    notes = []
    photo_tools.apply({"photo_tool": {"folder": upright.TOOL_ID}, "input_image": str(src)}, str(tmp_path), note=notes.append)
    assert notes and "verticals" in notes[0]


def test_another_folder_name_still_has_to_be_an_installed_tool(tmp_path):
    with pytest.raises(ValueError):
        photo_tools.apply({"photo_tool": {"folder": "builtin:other"}, "input_image": str(tmp_path / "x.png")}, str(tmp_path))


def fan(apex_y):
    """Stems or rays that meet at one point inside or near the picture (a bunch of flowers, a sunburst): no building."""
    rng = np.random.default_rng(5)
    img = cv2.GaussianBlur(rng.integers(90, 160, (H, W, 3), dtype=np.uint8), (0, 0), 3)
    apex = (W // 2, apex_y)
    for dx in range(-260, 261, 65):
        cv2.line(img, apex, (W // 2 + dx, H - 10), (30, 90, 40), 7)
    return img


# inside the picture, and just above it (0.6 picture heights from its middle)
@pytest.mark.parametrize("apex_y", [H // 3, -H // 10])
def test_lines_meeting_near_the_picture_are_not_converging_verticals(apex_y):
    img = fan(apex_y)
    out, found = upright.straighten(img, 1.0)
    assert not found and np.array_equal(out, img)


def test_the_result_is_never_empty_or_much_smaller():
    for img in (fan(H // 3), seen_from_below(facade(), 0.3), seen_from_below(facade(), 0.45)):
        out, _ = upright.straighten(img, 1.0)
        assert out.size and out.shape[0] * out.shape[1] >= 0.5 * H * W


def test_no_full_size_canvas_is_made_for_the_correction(monkeypatch):
    # only the cut-out part is warped at full size: no picture larger than the photo is ever made
    tilted = seen_from_below(facade(), 0.25)
    sizes = []
    real = cv2.warpPerspective

    def watch(src, m, size, *a, **k):
        sizes.append(size[0] * size[1])
        return real(src, m, size, *a, **k)
    monkeypatch.setattr(cv2, "warpPerspective", watch)
    out, found = upright.straighten(tilted, 1.0)
    assert found and out.shape[0] * out.shape[1] >= 0.5 * H * W
    assert max(sizes) <= 1.05 * H * W


def test_a_busy_photo_is_handled_quickly():
    import time
    rng = np.random.default_rng(9)
    img = seen_from_below(facade(), 0.18)
    for _ in range(1500):  # branches, grass, rain: many short near-vertical strokes
        x, y = int(rng.integers(0, W)), int(rng.integers(0, H - 80))
        cv2.line(img, (x, y), (x + int(rng.integers(-8, 9)), y + 70), (int(rng.integers(0, 255)),) * 3, 2)
    started = time.perf_counter()
    upright.straighten(img, 1.0)
    assert time.perf_counter() - started < 2.0


def test_stop_ends_the_tool_without_a_result(tmp_path):
    src = tmp_path / "house.png"
    Image.fromarray(seen_from_below(facade())).save(src)
    assert photo_tools.apply({"photo_tool": {"folder": upright.TOOL_ID}, "input_image": str(src)}, str(tmp_path),
                             stop=lambda: True) is None
