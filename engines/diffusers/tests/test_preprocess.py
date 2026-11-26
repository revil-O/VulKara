# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
import numpy as np
import pytest

pytest.importorskip("cv2")
import preprocess  # noqa: E402


def _wholebody():
    """133 COCO-WholeBody keypoints: point i at (i, 2 i), all confident."""
    pts = np.array([[i, 2 * i] for i in range(133)], np.float32)
    return pts, np.ones(133, np.float32)


def test_coco_wholebody_to_openpose():
    pts, score = _wholebody()
    p = preprocess._to_openpose(pts, score)
    assert len(p["body"]) == 18 and len(p["face"]) == 70
    assert len(p["lhand"]) == 21 and len(p["rhand"]) == 21
    assert p["body"][0] == [0, 0]                    # nose
    assert p["body"][1] == [5.5, 11.0]               # neck = middle of the shoulders (5, 6)
    assert p["body"][2] == [6, 12]                   # right shoulder = COCO 6
    assert p["body"][14] == [2, 4]                   # right eye = COCO 2
    assert p["face"][0] == [23, 46]
    assert p["lhand"][0] == [91, 182] and p["rhand"][0] == [112, 224]
    assert p["face"][68] is not None                 # pupils are added


def test_low_scores_are_left_out():
    pts, score = _wholebody()
    score[91:112] = 0.1   # left hand not visible
    score[6] = 0.1        # right shoulder not visible → no neck
    p = preprocess._to_openpose(pts, score)
    assert p["lhand"] is None
    assert p["body"][1] is None and p["body"][2] is None


def test_draw_pose_scales_to_the_requested_size():
    pts, score = _wholebody()
    pose = {"width": 200, "height": 400, "people": [preprocess._to_openpose(pts * 0.5, score)]}
    img = preprocess.draw_pose(pose, 100, 200)
    assert img.size == (100, 200)
    assert np.asarray(img).max() > 0


def test_edge_images():
    from PIL import Image
    img = Image.new("RGB", (64, 64), "black")
    img.paste((255, 255, 255), (16, 16, 48, 48))
    for kind in ("Canny", "LineArt", "Scribble"):
        out = np.asarray(preprocess.control_image(kind, img))
        assert out.shape == (64, 64, 3) and out.max() == 255


def test_the_depth_control_picture_takes_the_chosen_model(monkeypatch):
    seen = []
    monkeypatch.setattr(preprocess, "depth", lambda image, report=None, model="depth": seen.append(model) or image)
    from PIL import Image
    img = Image.new("RGB", (8, 8))
    preprocess.control_image("Depth", img)
    preprocess.control_image("Depth", img, depth_model="depth_base")
    assert seen == ["depth", "depth_base"]
    assert preprocess.MODELS["depth_base"]["repo"] == "depth-anything/Depth-Anything-V2-Base-hf"
