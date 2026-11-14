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


K4 = {"arch": "flux2_klein", "family": "flux2", "components": {"transformer": 3.9}}
K9 = {"arch": "flux2_klein", "family": "flux2", "components": {"transformer": 8.1}}


def test_extending_with_klein_4b_takes_the_outpaint_lora_downloaded_once(monkeypatch, tmp_path):
    import helpers
    import restore
    monkeypatch.setattr(restore, "helper_folder", lambda helper_id: str(tmp_path))
    installs = []
    monkeypatch.setattr(helpers, "install", lambda helper_id, report=None: (
        installs.append(helper_id), (tmp_path / engine.OUTPAINT_FILE).write_bytes(b"")))
    extend = {"prefill": True, "mask_image": "m.png"}
    for _ in range(2):
        (lora,) = engine.outpaint_loras(extend, K4, picture=True)
    assert installs == [engine.OUTPAINT_HELPER]
    assert lora["file"] == str(tmp_path / engine.OUTPAINT_FILE) and lora["scale"] == 1.1 and lora["plan_gb"] > 0
    # only extending (not repainting a part, not a new picture) and only klein 4B: the LoRA is made for its width
    assert engine.outpaint_loras({"mask_image": "m.png"}, K4, picture=True) == []
    assert engine.outpaint_loras(extend, K4, picture=False) == []
    assert engine.outpaint_loras(extend, K9, picture=True) == []


def test_the_empty_part_turns_pure_green_the_picture_stays():
    img = Image.new("RGB", (64, 32), (90, 120, 150))
    out = np.asarray(engine.green_border(img, rect_mask((64, 32), [0, 0, 9, 31])))
    assert (out[:, :10] == (0, 255, 0)).all() and (out[:, 10:] == (90, 120, 150)).all()


def test_extending_with_klein_9b_takes_a_klein_4b_installed_beside_it(tmp_path):
    import json
    k4 = dict(K4, defaults={"num_steps": 4})
    for name, mf in (("FLUX.2-klein-9B", K9), ("FLUX.2-klein-4B", k4), ("SDXL", {"arch": "sdxl", "family": "sdxl"})):
        (tmp_path / name).mkdir()
        (tmp_path / name / engine.MANIFEST).write_text(json.dumps(mf))
    (tmp_path / "half-imported").mkdir()  # no model.json
    nine = str(tmp_path / "FLUX.2-klein-9B")
    extend = {"prefill": True, "input_image": "a.png", "mask_image": "m.png", "model_dir": nine}
    assert engine.outpaint_stand_in(extend, K9) == str(tmp_path / "FLUX.2-klein-4B")
    # repainting a part, or the 4B itself: as chosen
    assert engine.outpaint_stand_in(dict(extend, prefill=False), K9) is None
    assert engine.outpaint_stand_in(extend, K4) is None
    # LoRAs chosen for 9B do not fit 4B: the job stays as chosen
    assert engine.outpaint_stand_in(dict(extend, loras=[{"path": "x"}]), K9) is None
    # not the 4B base (50 steps, the job keeps 9B's 4), not a 4B imported on another Mac (its memory plan)
    four = tmp_path / "FLUX.2-klein-4B" / engine.MANIFEST
    four.write_text(json.dumps(dict(K4, defaults={"num_steps": 50})))
    assert engine.outpaint_stand_in(extend, K9) is None
    four.write_text(json.dumps(dict(k4, imported_on={"ram_gb": 999})))
    assert engine.outpaint_stand_in(extend, K9) is None
    four.unlink()
    assert engine.outpaint_stand_in(extend, K9) is None


def test_extending_with_klein_blanks_the_masked_part_of_the_reference():
    torch = pytest.importorskip("torch")
    latents = torch.ones(1, 128, 4, 6)
    mask = rect_mask((96, 64), [80, 0, 95, 63])  # the right sixth of the picture is painted anew
    mask.putpixel((10, 10), 255)  # one masked pixel blanks its whole cell
    out = engine.blank_reference(latents, mask)
    assert out.shape == latents.shape
    assert (out[..., 5] == 0).all()  # the new border
    assert out[0, 0, 0, 0] == 0
    assert out[0, :, 1:, :5].eq(1).all() and out[0, :, 0, 1:5].eq(1).all()  # the rest of the picture as it was


def test_the_outpaint_lora_says_when_it_can_not_be_downloaded(monkeypatch, tmp_path):
    import helpers
    import restore
    monkeypatch.setattr(restore, "helper_folder", lambda helper_id: str(tmp_path))

    def offline(helper_id, report=None):
        raise OSError("no network")
    monkeypatch.setattr(helpers, "install", offline)
    with pytest.raises(OSError):  # the engine then lets 9B extend itself instead of its 4B stand-in
        engine.outpaint_file()
    (tmp_path / engine.OUTPAINT_FILE).write_bytes(b"")
    assert engine.outpaint_file() == str(tmp_path / engine.OUTPAINT_FILE)  # there: no download asked
