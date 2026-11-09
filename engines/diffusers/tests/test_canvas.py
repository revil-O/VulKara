# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
import pytest

Image = pytest.importorskip("PIL.Image")
ImageDraw = pytest.importorskip("PIL.ImageDraw")
np = pytest.importorskip("numpy")

import engine  # noqa: E402


def rect_mask(size, box):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rectangle(box, fill=255)
    return m


def test_small_masks_are_painted_in_a_crop_big_ones_in_the_whole_picture():
    box, size = engine._mask_crop(rect_mask((1024, 1024), [100, 740, 458, 900]), 1024, 1024)
    assert size == (1024, 1024)
    x0, y0, x1, y1 = box
    assert x0 <= 100 and y0 <= 740 and x1 >= 458 and y1 >= 900  # the mask is inside
    assert x1 - x0 == y1 - y0 < 1024 * 0.8  # same aspect ratio as the picture, scaled up
    assert engine._mask_crop(rect_mask((1024, 1024), [0, 0, 800, 800]), 1024, 1024) is None
    assert engine._mask_crop(Image.new("L", (64, 64), 0), 64, 64) is None


def test_prefill_continues_the_colours_of_the_edge():
    img = Image.new("RGB", (256, 256), (128, 128, 128))
    ImageDraw.Draw(img).rectangle([0, 0, 127, 255], fill=(200, 60, 20))
    mask = rect_mask((256, 256), [128, 0, 255, 255])  # right half empty
    out = np.asarray(engine._prefill(img, mask), dtype=float)
    assert np.abs(out[:, 200] - [200, 60, 20]).max() < 2  # the orange continues, no grey
    assert (np.asarray(engine._prefill(img, Image.new("L", (256, 256), 0))) == np.asarray(img)).all()


def test_blend_keeps_everything_outside_the_mask():
    original = Image.new("RGB", (256, 256), (10, 20, 30))
    painted = Image.new("RGB", (256, 256), (250, 250, 250))
    mask = engine._grow_mask(rect_mask((256, 256), [96, 96, 160, 160]), 16)
    out = np.asarray(engine._blend_into(original, painted, mask))
    assert (out[0, 0] == [10, 20, 30]).all() and (out[128, 128] == [250, 250, 250]).all()
    assert engine._grow_mask(rect_mask((256, 256), [96, 96, 160, 160]), 16).getbbox()[0] < 96  # grown


def test_nothing_of_the_old_picture_shows_inside_the_mask():
    # the removed house showed through at 15-40 % (MEASUREMENTS 7bf)
    original = Image.new("RGB", (1024, 1024), (0, 0, 0))
    painted = Image.new("RGB", (1024, 1024), (255, 255, 255))
    raw = rect_mask((1024, 1024), [330, 425, 462, 542])
    out = np.asarray(engine._blend_into(original, painted, engine._grow_mask(raw, 48), raw, 48))
    assert out[np.asarray(raw) > 127].min() == 255
    assert (out[100, 100] == 0).all()


def test_the_step_at_the_grown_mask_edge_is_hidden():
    # pipelines not trained for masks keep the old picture outside the mask and shift the tone inside: a lighter disc
    # around an added seagull (MEASUREMENTS 7bf); the offset along the edge is taken out, what was drawn stays
    raw = rect_mask((1024, 1024), [400, 400, 600, 600])
    grown = engine._grow_mask(raw, 48)
    original = Image.new("RGB", (1024, 1024), (100, 100, 100))
    painted = Image.composite(Image.new("RGB", (1024, 1024), (125, 125, 125)), original, grown)  # the step
    ImageDraw.Draw(painted).rectangle([450, 450, 550, 550], fill=(250, 250, 250))  # the seagull
    out = np.asarray(engine._blend_into(original, painted, grown, raw, 48), dtype=float)[:, :, 0]
    assert np.abs(out[500, 300:450] - 100).max() <= 1  # no disc
    assert out[500, 460:540].min() >= 220
