# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Removing a painted object (remove.py), with stand-ins for LaMa and RORem: no model, no network."""
import os
import sys

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import remove as rm  # noqa: E402


def photo(size=(400, 300)):
    """A test picture: stripes on a blue ground with a red 'object'."""
    img = Image.new("RGB", size, (90, 120, 160))
    d = ImageDraw.Draw(img)
    for i in range(0, size[0], 16):
        d.line([(i, 0), (i, size[1])], fill=(40 + i // 3, 90, 60), width=3)
    d.ellipse([150, 100, 210, 160], fill=(220, 30, 30))
    return img


def mask(box, size=(400, 300)):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rectangle(box, fill=255)
    return m


def flat(colour):
    """A filler that paints the grown mask in one colour, and counts its calls."""
    def fill(img, grown):
        fill.calls += 1
        a = np.asarray(img).copy()
        a[grown > 0] = colour
        return Image.fromarray(a)
    fill.calls = 0
    return fill


def test_outside_the_grown_mask_the_picture_stays_to_the_pixel():
    img = photo()
    out, used, _ = rm.remove(img, mask([150, 100, 210, 160]), "auto", flat((0, 255, 0)), flat((0, 0, 255)), True)
    _, grown, _ = rm.grow(mask([150, 100, 210, 160]), img.size)
    o, r = np.asarray(img), np.asarray(out)
    assert used == "lama"
    assert np.array_equal(o[grown == 0], r[grown == 0])
    assert not np.array_equal(o[180 - 50, 180], r[180 - 50, 180])  # the object's place changed


def test_the_mask_grows_by_a_share_of_the_longer_side():
    painted, grown, px = rm.grow(mask([200, 150, 200, 150]), (400, 300))
    assert px == round(400 * rm.GROW) == 6
    assert painted.sum() == 1
    assert grown[150].sum() == 2 * px + 1 and grown[:, 200].sum() == 2 * px + 1


def test_small_areas_go_to_lama_large_ones_to_rorem_unless_forced():
    small, large = mask([150, 100, 210, 160]), mask([20, 20, 380, 280])
    for m, method, expected in ((small, "auto", "lama"), (large, "auto", "rorem"), (small, "rorem", "rorem"),
                                (large, "lama", "lama")):
        lama, rorem = flat((0, 255, 0)), flat((0, 0, 255))
        _, used, share = rm.remove(photo(), m, method, lama, rorem, True)
        assert used == expected, (method, share)
        assert (lama.calls, rorem.calls) == ((1, 0) if expected == "lama" else (0, 1))
    assert rm.grow(small, (400, 300))[1].mean() < rm.LARGE <= rm.grow(large, (400, 300))[1].mean()


def test_auto_fills_with_lama_and_says_so_when_rorem_is_missing():
    notes = []
    lama, rorem = flat((0, 255, 0)), flat((0, 0, 255))
    _, used, _ = rm.remove(photo(), mask([20, 20, 380, 280]), "auto", lama, rorem, False, note=notes.append)
    assert used == "lama" and rorem.calls == 0 and "not downloaded" in notes[0]
    with pytest.raises(ValueError, match="Download RORem"):
        rm.remove(photo(), mask([20, 20, 380, 280]), "rorem", lama, rorem, False)


def test_compare_runs_every_method_on_this_mac_and_objectclear_only_where_allowed():
    assert rm.methods("compare", True, True, True) == ["lama", "rorem", "objectclear"]
    assert rm.methods("compare", False, True, False) == ["lama"]
    assert rm.methods("compare", True, False, True) == ["lama", "rorem"]
    assert rm.methods("auto", True, True, True) == ["auto"]


def test_an_empty_mask_is_refused():
    with pytest.raises(ValueError):
        rm.remove(photo(), Image.new("L", (400, 300), 0), "auto", flat((0, 0, 0)), flat((0, 0, 0)), True)


def test_the_colours_of_the_fill_move_toward_the_ring_around_it():
    original = np.full((100, 100, 3), (90, 120, 160), np.uint8)
    filled = original.copy()
    painted = np.zeros((100, 100), np.uint8)
    painted[40:60, 40:60] = 1
    grown = painted.copy()
    filled[30:70, 30:70] = (130, 160, 200)  # RORem's crop a little lighter, its ring too
    out = rm.match_colours(original, filled, grown, 4)
    before = np.abs(filled[grown > 0].astype(int) - (90, 120, 160)).mean()
    after = np.abs(out[grown > 0].astype(int) - (90, 120, 160)).mean()
    assert after < before / 4
    assert np.array_equal(out[grown == 0], filled[grown == 0])


def test_a_fill_that_kept_the_ring_is_left_as_it_is_also_between_light_and_dark():
    # sky above, trees below: one mean of the ring would lift the trees into a light ghost
    original = np.zeros((100, 100, 3), np.uint8)
    original[:50] = (200, 220, 250)
    original[50:] = (30, 60, 30)
    filled = original.copy()
    painted = np.zeros((100, 100), np.uint8)
    painted[35:65, 35:65] = 1
    out = rm.match_colours(original, filled, painted, 4)
    assert np.array_equal(out, filled)


def test_the_fill_is_whole_on_the_painted_mask_and_fades_out_in_the_grown_part():
    img = photo()
    m = mask([150, 100, 210, 160])
    painted, grown, px = rm.grow(m, img.size)
    original = np.asarray(img)
    filled = np.full_like(original, 255)
    out = rm.blend(original, filled, painted, grown, px)
    assert (out[painted > 0] == 255).all()
    edge = (grown > 0) & (painted == 0)
    assert (out[edge] <= 255).all() and not (out[edge] == 255).all()
    assert np.array_equal(out[grown == 0], original[grown == 0])


def test_the_square_for_rorem_covers_the_whole_mask_and_stays_in_the_picture():
    m = np.zeros((300, 400), np.uint8)
    m[10:40, 20:60] = 1
    m[200:260, 300:390] = 1
    x0, y0, x1, y1 = rm.box(m, 24)
    assert x0 <= 20 and y0 <= 10 and x1 >= 390 and y1 >= 260
    assert 0 <= x0 and 0 <= y0 and x1 <= 400 and y1 <= 300


def test_the_object_s_soft_outline_is_covered_fully_just_outside_the_painted_mask():
    original = np.zeros((200, 200, 3), np.uint8)
    painted = np.zeros((200, 200), np.uint8)
    painted[80:120, 80:120] = 1
    px = 8
    grown = (cv2.distanceTransform(1 - painted, cv2.DIST_L2, 3) <= px).astype(np.uint8)
    out = rm.blend(original, np.full_like(original, 255), painted, grown, px)
    assert (out[100, 120:123] == 255).all()  # the halo right at the painted edge is filled, not shining through
    assert out[100, 127].max() < 255  # the outer half fades


def test_a_wide_area_is_padded_to_a_square_and_a_thin_stroke_survives_making_it_smaller():
    rgb = np.random.default_rng(1).integers(0, 255, (1000, 3000, 3), np.uint8)
    m = np.zeros((1000, 3000), np.uint8)
    m[500, 100:2900] = 1  # one pixel high
    crop, hole, side = rm.square_crop(rgb, m, (0, 400, 3000, 600))
    assert side == 3000 and crop.size == (rm.SIZE, rm.SIZE) and hole.size == (rm.SIZE, rm.SIZE)
    assert np.asarray(hole).max() == 255


def test_the_colour_match_works_on_the_area_around_the_mask_only():
    import time
    original = np.full((4000, 6000, 3), 120, np.uint8)  # 24 MP
    filled = original.copy()
    painted = np.zeros((4000, 6000), np.uint8)
    painted[1900:2100, 2900:3100] = 1
    filled[1800:2200, 2800:3200] = 160
    t = time.time()
    out = rm.match_colours(original, filled, painted, 90)
    assert time.time() - t < 5
    assert abs(int(out[2000, 3000, 0]) - 120) < 10
    assert np.array_equal(out[:1000], filled[:1000])


def test_rorem_counts_as_there_only_with_the_mark_of_its_pinned_revision(tmp_path):
    import json
    assert not rm.ready(str(tmp_path))
    (tmp_path / ".vk-checked.json").write_text(json.dumps({"repo": rm.REPO, "revision": "older"}))
    assert not rm.ready(str(tmp_path))
    (tmp_path / ".vk-checked.json").write_text(json.dumps({"repo": rm.REPO, "revision": rm.PIN[0]}))
    assert not rm.ready(str(tmp_path))  # the mark, but the files are gone
    for f in rm.PIN[1]:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_bytes(b"")
    assert rm.ready(str(tmp_path))
    (tmp_path / sorted(rm.PIN[1])[-1]).unlink()
    assert not rm.ready(str(tmp_path))


def with_effects(colour, effects_box):
    """A stand-in for ObjectClear: fills the grown mask and marks a 'shadow' (effects_box, at the picture's size)."""
    paint = flat(colour)

    def fill(img, grown):
        fill.calls += 1
        e = np.zeros_like(grown)
        x0, y0, x1, y1 = effects_box
        e[y0:y1, x0:x1] = 1
        a = np.asarray(paint(img, grown)).copy()
        a[e > 0] = colour
        return Image.fromarray(a), e
    fill.calls = 0
    return fill


def test_objectclear_runs_only_when_asked_and_needs_its_download():
    small, large = mask([150, 100, 210, 160]), mask([20, 20, 380, 280])
    for m, method, expected in ((small, "auto", "lama"), (large, "auto", "rorem"), (large, "rorem", "rorem"),
                                (small, "objectclear", "objectclear"), (large, "objectclear", "objectclear")):
        oc = with_effects((0, 0, 255), (0, 0, 1, 1))
        _, used, _ = rm.remove(photo(), m, method, flat((0, 255, 0)), flat((0, 0, 255)), True, objectclear=oc,
                               objectclear_ready=True)
        assert used == expected and oc.calls == (expected == "objectclear")
    oc = with_effects((0, 0, 255), (0, 0, 1, 1))
    with pytest.raises(ValueError, match=r"Download ObjectClear first \(Models → Helper models\)"):
        rm.remove(photo(), small, "objectclear", flat((0, 0, 0)), flat((0, 0, 0)), True, objectclear=oc)
    assert oc.calls == 0


def test_objectclear_replaces_the_shadow_too_and_leaves_the_rest_to_the_pixel():
    img, m = photo(), mask([150, 100, 210, 160])
    shadow = (205, 140, 290, 175)  # right of the object, beyond the grown mask
    out, used, _ = rm.remove(img, m, "objectclear", flat((0, 0, 0)), flat((0, 0, 0)), True,
                             objectclear=with_effects((0, 255, 0), shadow), objectclear_ready=True)
    painted, _, px = rm.grow(m, img.size)
    painted[shadow[1]:shadow[3], shadow[0]:shadow[2]] = 1
    area = rm.widen(painted, px)
    o, r = np.asarray(img), np.asarray(out)
    assert used == "objectclear"
    assert np.array_equal(o[area == 0], r[area == 0])
    assert tuple(r[160, 270]) != tuple(o[160, 270])  # in the shadow, far from the painted mask: replaced
    assert r[160, 270, 1] > 200 and r[160, 270, 0] < 60


def test_auto_takes_objectclear_when_it_is_there_and_allowed():
    # small or large: the shadow under a vehicle stays with LaMa and RORem (MEASUREMENTS 7cb)
    assert rm.choose("auto", 0.04, True, objectclear_ready=True, auto_objectclear=True) == ("objectclear", "")
    assert rm.choose("auto", 0.4, True, objectclear_ready=True, auto_objectclear=True) == ("objectclear", "")
    # not downloaded, or a build with commercially usable models only: as before
    assert rm.choose("auto", 0.04, True, objectclear_ready=False, auto_objectclear=True) == ("lama", "")
    assert rm.choose("auto", 0.4, True, objectclear_ready=True, auto_objectclear=False) == ("rorem", "")
    # Fast and Thorough stay what they say
    assert rm.choose("lama", 0.4, True, objectclear_ready=True, auto_objectclear=True) == ("lama", "")
    assert rm.choose("rorem", 0.04, True, objectclear_ready=True, auto_objectclear=True) == ("rorem", "")


def shaded():
    """A grey ground with an 'object' (150..210 × 100..160), its dark shadow on the right and a mid-grey thing (a
    neighbour) on the left; and a stand-in for ObjectClear that clears object and shadow but also changes the
    neighbour, darker, marking all three as effects."""
    a = np.full((300, 400, 3), 160, np.uint8)
    a[100:160, 150:210] = (220, 30, 30)
    a[110:170, 215:300] = 60  # the shadow
    a[110:170, 40:140] = 140  # the neighbour
    img = Image.fromarray(a)

    def fill(image, grown):
        fill.calls += 1
        out = np.asarray(image).copy()
        out[grown > 0] = 160
        out[110:170, 215:300] = 160
        out[110:170, 40:140] = 90
        e = np.zeros_like(grown)
        e[105:175, 30:305] = 1
        return Image.fromarray(out), e
    fill.calls = 0
    return img, fill


def test_objectclear_beyond_the_mask_only_lightens_a_shadow_and_leaves_a_darker_change(monkeypatch):
    monkeypatch.setattr(rm, "other_faces", lambda rgb, painted: [])
    img, oc = shaded()
    lines = []
    out, used, _ = rm.remove(img, mask([150, 100, 210, 160]), "objectclear", flat((0, 0, 0)), flat((0, 0, 0)), True,
                             objectclear=oc, objectclear_ready=True, log=lines.append)
    o, r = np.asarray(img), np.asarray(out)
    assert used == "objectclear" and lines and "faces protected: none" in lines[0]
    assert abs(int(r[140, 270, 0]) - 160) < 8  # the shadow, far from the painted mask: gone
    assert np.array_equal(o[105:175, 30:125], r[105:175, 30:125])  # the neighbour, made darker: untouched


def test_objectclear_never_changes_a_face_beside_the_mask(monkeypatch):
    face = (240, 115, 280, 165)  # inside the shadow, away from the painted mask
    monkeypatch.setattr(rm, "other_faces", lambda rgb, painted: [face])
    img, oc = shaded()
    lines = []
    out, _, _ = rm.remove(img, mask([150, 100, 210, 160]), "objectclear", flat((0, 0, 0)), flat((0, 0, 0)), True,
                          objectclear=oc, objectclear_ready=True, log=lines.append)
    o, r = np.asarray(img), np.asarray(out)
    inside = rm.face_area([face], o.shape[:2])
    assert inside[140, 260] and not inside[116, 241] and np.array_equal(o[inside], r[inside])
    assert abs(int(r[140, 230, 0]) - 160) < 8  # the rest of the shadow still goes
    assert str(face) in lines[0]


def test_objectclear_leaves_an_unpainted_person_whose_dark_clothes_it_lightened(monkeypatch):
    # a dark jacket before a light window passed as a shadow (hand test); Vision's people map protects it
    monkeypatch.setattr(rm, "other_faces", lambda rgb, painted: [])
    img, oc = shaded()
    people = np.zeros((300, 400), np.uint8)
    people[100:160, 150:210] = 1  # the painted one: removed as before
    people[110:170, 250:300] = 2  # in the "shadow": someone else
    lines = []
    out, _, _ = rm.remove(img, mask([150, 100, 210, 160]), "objectclear", flat((0, 0, 0)), flat((0, 0, 0)), True,
                          objectclear=oc, objectclear_ready=True, log=lines.append, persons=lambda: people)
    o, r = np.asarray(img), np.asarray(out)
    assert np.array_equal(o[110:170, 252:300], r[110:170, 252:300])  # the other person, with a margin: untouched
    assert abs(int(r[140, 228, 0]) - 160) < 8  # the shadow beside it still goes
    assert abs(int(r[130, 180, 0]) - 160) < 8  # the painted person goes
    assert "persons protected: 1" in lines[0]


def test_a_broken_people_map_keeps_the_objectclear_result_and_says_so(monkeypatch):
    monkeypatch.setattr(rm, "other_faces", lambda rgb, painted: [])
    img, oc = shaded()

    def broken():
        raise OSError("truncated PNG")
    notes, lines = [], []
    out, used, _ = rm.remove(img, mask([150, 100, 210, 160]), "objectclear", flat((0, 0, 0)), flat((0, 0, 0)), True,
                             objectclear=oc, objectclear_ready=True, log=lines.append, note=notes.append,
                             persons=broken)
    assert used == "objectclear" and out.size == img.size
    assert notes == ["Person detection failed: people were not protected"] and "truncated PNG" in lines[0]


def test_a_person_counts_as_painted_from_a_tenth_painted():
    people = np.zeros((100, 100), np.uint8)
    people[0:50, 0:20] = 1
    people[0:50, 60:80] = 2
    painted = np.zeros((100, 100), np.uint8)
    painted[0:50, 0:20] = 1  # all of person 1
    painted[0:4, 60:80] = 1  # 8 % of person 2
    area, n = rm.other_persons(people, painted, 2)
    assert n == 1 and area[25, 70] and area[25, 58] and not area[25, 10]
    assert rm.other_persons(None, painted, 2)[1] == 0


def test_without_the_face_detector_no_face_is_looked_for(monkeypatch, tmp_path):
    import restore
    monkeypatch.setattr(restore, "helper_folder", lambda helper: str(tmp_path))
    monkeypatch.setattr(restore, "find_faces", lambda rgb, path: pytest.fail("no detector, no search"))
    assert rm.other_faces(np.zeros((50, 50, 3), np.uint8), np.zeros((50, 50), np.uint8)) == []


def test_only_faces_with_eyes_nose_and_mouth_outside_the_painted_mask_are_protected(monkeypatch, tmp_path):
    import restore
    (tmp_path / restore.FACE_DETECTOR).write_bytes(b"")
    monkeypatch.setattr(restore, "helper_folder", lambda helper: str(tmp_path))
    mine = np.array([[15, 15], [25, 15], [20, 20], [16, 25], [24, 25]], np.float32)  # the mouth is painted
    other = mine + (45, 0)  # its square reaches into the painted mask, its features do not
    monkeypatch.setattr(restore, "find_faces", lambda rgb, path: [mine, other])
    monkeypatch.setattr(restore, "face_square", lambda p: [p[0, 0] - 5, 10, 20, 20])
    painted = np.zeros((100, 100), np.uint8)
    painted[24:30, 15:56] = 1
    assert rm.other_faces(np.zeros((100, 100, 3), np.uint8), painted) == [(53, 8, 77, 32)]


def test_a_face_at_the_picture_edge_keeps_its_whole_ellipse(monkeypatch, tmp_path):
    import restore
    (tmp_path / restore.FACE_DETECTOR).write_bytes(b"")
    monkeypatch.setattr(restore, "helper_folder", lambda helper: str(tmp_path))
    pts = np.array([[2, 15], [8, 15], [5, 20], [3, 25], [7, 25]], np.float32)
    monkeypatch.setattr(restore, "find_faces", lambda rgb, path: [pts])
    monkeypatch.setattr(restore, "face_square", lambda p: [-10, 10, 20, 20])
    assert rm.other_faces(np.zeros((100, 100, 3), np.uint8), np.zeros((100, 100), np.uint8)) == [(-12, 8, 12, 32)]
    inside = rm.face_area([(-20, 100, 40, 160)], (300, 400))
    assert inside[105, 5] and inside[130, 38] and not inside[130, 41]  # centred at x = 10, not squeezed into 0..40


def test_a_broken_face_detector_keeps_the_result_and_says_so(monkeypatch, tmp_path):
    import restore
    (tmp_path / restore.FACE_DETECTOR).write_bytes(b"")  # 0 bytes: YuNet can not be read
    monkeypatch.setattr(restore, "helper_folder", lambda helper: str(tmp_path))
    img, oc = shaded()
    notes, lines = [], []
    out, used, _ = rm.remove(img, mask([150, 100, 210, 160]), "objectclear", flat((0, 0, 0)), flat((0, 0, 0)), True,
                             objectclear=oc, objectclear_ready=True, note=notes.append, log=lines.append)
    assert used == "objectclear" and notes == ["Face detection failed: faces were not protected"]
    assert any("face detection failed" in x for x in lines)
    assert abs(int(np.asarray(out)[140, 270, 0]) - 160) < 8  # the shadow went all the same


def test_a_face_in_the_soft_edge_is_protected_without_effects_beyond_the_mask(monkeypatch):
    face = (205, 115, 235, 155)  # reaches into the grown edge (210..216) of the painted mask
    looked = []
    monkeypatch.setattr(rm, "other_faces", lambda rgb, painted: looked.append(1) or [face])
    img, _ = shaded()

    def fill(image, grown):
        out = np.asarray(image).copy()
        out[grown > 0] = 160
        return Image.fromarray(out), np.zeros_like(grown)  # no effects at all
    out, _, _ = rm.remove(img, mask([150, 100, 210, 160]), "objectclear", flat((0, 0, 0)), flat((0, 0, 0)), True,
                          objectclear=fill, objectclear_ready=True)
    o, r = np.asarray(img), np.asarray(out)
    inside = rm.face_area([face], o.shape[:2])
    painted, _, _ = rm.grow(mask([150, 100, 210, 160]), img.size)
    assert looked and inside[135, 213] and not painted[135, 213]
    assert np.array_equal(o[inside & (painted == 0)], r[inside & (painted == 0)])


def test_objectclear_keeping_the_object_is_filled_again_without_it():
    img, m = photo(), mask([140, 90, 220, 170])

    def keeps(image, grown):  # paints the object again where it was (hand test 2026-11-14)
        keeps.calls += 1
        return image.copy(), np.zeros_like(grown)
    keeps.calls = 0
    notes, lama = [], flat((0, 255, 0))
    out, used, _ = rm.remove(img, m, "auto", lama, flat((0, 0, 255)), True, objectclear=keeps, objectclear_ready=True,
                             auto_objectclear=True, note=notes.append)
    assert (used, keeps.calls, lama.calls) == ("lama", 1, 1)
    assert notes == ["ObjectClear kept the object: filled again without it"]
    assert np.asarray(out)[130, 180, 1] > 200  # LaMa's fill, not the red object
    # comparing the methods shows ObjectClear's own picture
    _, used, _ = rm.remove(img, m, "objectclear", flat((0, 255, 0)), flat((0, 0, 255)), True, objectclear=keeps,
                           objectclear_ready=True, check=False)
    assert used == "objectclear"


def test_a_kept_object_is_told_from_a_removed_one_by_its_edges():
    o = np.asarray(photo())
    painted = np.asarray(mask([140, 90, 220, 170])) // 255
    assert rm.kept_object(o, o, painted)
    assert not rm.kept_object(o, np.asarray(flat((0, 255, 0))(photo(), painted)), painted)
    assert not rm.kept_object(o, o, np.zeros_like(painted))


def test_a_thin_mask_across_a_wide_picture_is_not_checked():
    o = np.zeros((40, 4000, 3), np.uint8)
    o[:, ::7] = 255
    painted = np.zeros((40, 4000), np.uint8)
    painted[20, 100:3900] = 1  # shrinks to one row at WORK px
    assert not rm.kept_object(o, o, painted)
