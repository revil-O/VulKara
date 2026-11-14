# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""The face detailer (K4, plans/K4_GESICHTS_DETAILER.md): masks around the largest faces, each painted again in its
crop and put back, a face filling much of the picture left as it is."""
import types

import pytest

Image = pytest.importorskip("PIL.Image")
np = pytest.importorskip("numpy")

import engine  # noqa: E402
import restore  # noqa: E402


def faces_at(monkeypatch, boxes):
    """restore's face finder returning faces with these squares (x, y, w, h), as many as given."""
    def find(rgb, detector, min_spread=restore.FACE_MIN):
        assert min_spread == engine.FACE_DETAIL_MIN  # small faces are what the detailer is for
        return [np.full((5, 2), i, np.float32) for i in range(len(boxes))]
    monkeypatch.setattr(restore, "find_faces", find)
    monkeypatch.setattr(restore, "face_square", lambda pts: list(boxes[int(pts[0, 0])]))


def test_the_four_largest_faces_get_an_ellipse_a_little_larger_than_the_face(monkeypatch):
    faces_at(monkeypatch, [(100, 100, 100, 100)] * 6)
    masks = engine.face_masks(Image.new("RGB", (1024, 1024)), "yunet.onnx")
    assert len(masks) == 4
    box = masks[0].getbbox()
    assert abs((box[2] - box[0]) - 118) <= 2 and abs((box[0] + box[2]) / 2 - 150) <= 1
    faces_at(monkeypatch, [])
    assert engine.face_masks(Image.new("RGB", (64, 64)), "yunet.onnx") == []


def test_small_faces_are_painted_again_in_their_crop_a_large_one_stays(monkeypatch):
    faces_at(monkeypatch, [(700, 100, 60, 60), (100, 100, 800, 800)])
    monkeypatch.setattr(restore, "detector_path", lambda: "yunet.onnx")
    calls = []

    class Pipe:
        def __call__(self, prompt=None, image=None, mask_image=None, width=None, height=None, strength=None,
                     num_inference_steps=None, guidance_scale=None):
            pass

    monkeypatch.setattr(engine, "_derive_pipeline", lambda cls, base, **extra: Pipe())
    eng = object.__new__(engine.DiffusersEngine)
    eng.reader = None

    def run(pipe, call, seed, steps, model=None, quiet=False):
        calls.append(dict(call, _steps=steps))
        return Image.new("RGB", (call["width"], call["height"]), (255, 0, 0))

    eng._run = run
    model = types.SimpleNamespace(pipe=None)
    spec = {"inpaint_pipeline": "StableDiffusionXLInpaintPipeline"}
    first = {"prompt": "a crowd", "num_inference_steps": 30, "guidance_scale": 6, "width": 1024, "height": 1024,
             "image": "first pass input", "strength": 0.7, "controlnet_conditioning_scale": 1.0}
    picture = Image.new("RGB", (1024, 1024), (0, 0, 255))
    out, n = eng._face_detail(picture, model, spec, first, 7, 30, 0.9)
    assert n == 1 and len(calls) == 1
    c = calls[0]
    # the prompt and sampling of the picture, its own crop and mask, the strength kept in 0.2..0.6
    assert c["prompt"] == "a crowd" and c["strength"] == 0.6 and c["image"] != "first pass input"
    assert "controlnet_conditioning_scale" not in c and (c["width"], c["height"]) == (1024, 1024)
    px = np.asarray(out)
    assert tuple(px[130, 730]) == (255, 0, 0)  # the face's middle comes from the new picture
    assert tuple(px[600, 300]) == (0, 0, 255)  # away from it the picture is untouched
    # a few-step model: the pipelines run steps × strength steps and refuse fewer than one (4 × 0.2)
    calls.clear()
    eng._face_detail(picture, model, spec, dict(first, num_inference_steps=4), 7, 4, 0.2)
    assert calls[0]["strength"] == 0.2 and calls[0]["num_inference_steps"] * 0.2 >= 1 and calls[0]["_steps"] == 5


def test_a_failing_face_finder_keeps_the_finished_picture(monkeypatch):
    import protocol
    notes = []
    monkeypatch.setattr(protocol, "note", notes.append)
    monkeypatch.setattr(protocol, "log", lambda line: None)
    eng = engine.DiffusersEngine.__new__(engine.DiffusersEngine)

    def offline(*a, **k):
        raise OSError("no network")
    monkeypatch.setattr(eng, "_face_detail", offline)
    img = Image.new("RGB", (64, 64), (1, 2, 3))
    assert eng._faces_refined(img, None, {}, {}, 1, 4, "0.4") is img
    assert notes == ["Faces not refined: no network"]

    def stopped(*a, **k):
        raise engine.StopRequested()
    monkeypatch.setattr(eng, "_face_detail", stopped)
    with pytest.raises(engine.StopRequested):
        eng._faces_refined(img, None, {}, {}, 1, 4, 0.4)
