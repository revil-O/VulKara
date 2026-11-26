# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""ControlNet preprocessing: control images from photos, and poses for the pose editor.

    pose      DWPose (YOLOX person detector + RTMPose whole body, ONNX): body, hands, face,
              drawn in the OpenPose "full" style of controlnet_aux
    depth     Depth Anything V2 Small
    canny / lineart / scribble   OpenCV edge images
    tile      the photo itself

Models are downloaded on first use into <models folder>/../annotators/.

    python main.py detect_pose <image>   prints {"width", "height", "people": [...]} (pose editor)
"""
import json
import math
import sys

import numpy as np

import paths

MODELS = {
    "dwpose": {"repo": "yzd-v/DWPose", "files": ["yolox_l.onnx", "dw-ll_ucoco_384.onnx"], "size_gb": 0.35},
    "depth": {"repo": "depth-anything/Depth-Anything-V2-Small-hf",
              "files": ["config.json", "model.safetensors", "preprocessor_config.json"], "size_gb": 0.1},
    # finer edges (hair, plants, thin poles) at 0.2 s and 1.5 GB on an M4 (MEASUREMENTS 7cx); CC BY-NC 4.0
    "depth_base": {"repo": "depth-anything/Depth-Anything-V2-Base-hf",
                   "files": ["config.json", "model.safetensors", "preprocessor_config.json"], "size_gb": 0.39},
}


def root():
    return paths.helpers_dir("annotators")


def ensure_model(name, report=None):
    """The detector's folder, fetched once at its pinned commit and checked (pinned.py)."""
    import pinned
    from importer import _ProgressWatcher
    spec = MODELS[name]
    d = root() / name
    if pinned.ready(spec["repo"], str(d)):
        return d
    d.mkdir(parents=True, exist_ok=True)
    stage = "Downloading %s preprocessor (%.2f GB, one-time)" % (name, spec["size_gb"])
    with _ProgressWatcher(str(d), int(spec["size_gb"] * 1024 ** 3), stage, report=report):
        pinned.fetch_pinned(spec["repo"], str(d))
    return d


# ---------------------------------------------------------------- DWPose

_sessions = {}


def _session(path):
    import onnxruntime as ort
    if path not in _sessions:
        _sessions[path] = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    return _sessions[path]


def _nms(boxes, scores, thr):
    x1, y1, x2, y2 = boxes.T
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size:
        i = order[0]
        keep.append(i)
        xx1, yy1 = np.maximum(x1[i], x1[order[1:]]), np.maximum(y1[i], y1[order[1:]])
        xx2, yy2 = np.minimum(x2[i], x2[order[1:]]), np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0, xx2 - xx1 + 1) * np.maximum(0, yy2 - yy1 + 1)
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[1:][iou <= thr]
    return keep


def _detect_people(session, img):
    """YOLOX-L: person boxes (x0, y0, x1, y1) in image pixels."""
    import cv2
    size = 640
    r = min(size / img.shape[0], size / img.shape[1])
    padded = np.full((size, size, 3), 114, np.uint8)
    resized = cv2.resize(img, (int(img.shape[1] * r), int(img.shape[0] * r)), interpolation=cv2.INTER_LINEAR)
    padded[:resized.shape[0], :resized.shape[1]] = resized
    x = np.ascontiguousarray(padded.transpose(2, 0, 1), dtype=np.float32)[None]
    out = session.run(None, {session.get_inputs()[0].name: x})[0][0]
    grids, strides = [], []
    for s in (8, 16, 32):
        n = size // s
        xv, yv = np.meshgrid(np.arange(n), np.arange(n))
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        strides.append(np.full((n * n, 1), s))
    grids, strides = np.concatenate(grids), np.concatenate(strides)
    out[:, :2] = (out[:, :2] + grids) * strides
    out[:, 2:4] = np.exp(out[:, 2:4]) * strides
    cx, cy, w, h = out[:, 0], out[:, 1], out[:, 2], out[:, 3]
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], 1) / r
    scores = out[:, 4] * out[:, 5]  # objectness × "person" (class 0)
    mask = scores > 0.3
    boxes, scores = boxes[mask], scores[mask]
    if not len(boxes):
        return []
    return [boxes[i] for i in _nms(boxes, scores, 0.45)]


def _estimate(session, img, box):
    """RTMPose whole body on one person box: 133 keypoints + scores."""
    import cv2
    w, h = 288, 384
    center = (box[:2] + box[2:]) / 2
    bw, bh = (box[2:] - box[:2]) * 1.25
    if bw > bh * w / h:
        bh = bw * h / w
    else:
        bw = bh * w / h
    # maps the (padded) box onto the model input
    m = np.array([[w / bw, 0, w / 2 - center[0] * w / bw], [0, h / bh, h / 2 - center[1] * h / bh]], np.float32)
    crop = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR)
    x = (crop - np.array([123.675, 116.28, 103.53])) / np.array([58.395, 57.12, 57.375])
    x = np.ascontiguousarray(x.transpose(2, 0, 1), dtype=np.float32)[None]
    simcc_x, simcc_y = session.run(None, {session.get_inputs()[0].name: x})
    kx, ky = simcc_x[0].argmax(1) / 2.0, simcc_y[0].argmax(1) / 2.0
    score = np.minimum(simcc_x[0].max(1), simcc_y[0].max(1))
    pts = np.stack([kx / w * bw + center[0] - bw / 2, ky / h * bh + center[1] - bh / 2], 1)
    return pts, score


# COCO-WholeBody body order → OpenPose COCO-18 (neck = middle of the shoulders)
_COCO_TO_OPENPOSE = [0, None, 6, 8, 10, 5, 7, 9, 12, 14, 16, 11, 13, 15, 2, 1, 4, 3]


def _to_openpose(pts, score, thr=0.3):
    def pt(i):
        return [float(pts[i][0]), float(pts[i][1])] if score[i] > thr else None

    body = []
    for i in _COCO_TO_OPENPOSE:
        if i is None:
            ok = score[5] > thr and score[6] > thr
            body.append([float((pts[5][0] + pts[6][0]) / 2), float((pts[5][1] + pts[6][1]) / 2)] if ok else None)
        else:
            body.append(pt(i))
    face = [pt(i) for i in range(23, 91)]
    # pupils: DWPose has none, the editor's format has two (middle of each eye)
    for eye in (range(36, 42), range(42, 48)):
        e = [face[i] for i in eye if face[i]]
        face.append([sum(p[0] for p in e) / len(e), sum(p[1] for p in e) / len(e)] if len(e) == 6 else None)
    lhand = [pt(i) for i in range(91, 112)]
    rhand = [pt(i) for i in range(112, 133)]
    part = lambda p: p if sum(1 for k in p if k) >= 4 else None  # noqa: E731
    return {"body": body, "lhand": part(lhand), "rhand": part(rhand), "face": part(face)}


def detect_pose(image, report=None):
    """PIL image → {"width", "height", "people": [{body, rhand, lhand, face}]} in image pixels."""
    d = ensure_model("dwpose", report)
    img = np.asarray(image.convert("RGB"))
    det, pose = _session(d / "yolox_l.onnx"), _session(d / "dw-ll_ucoco_384.onnx")
    boxes = _detect_people(det, img)
    if not boxes:
        boxes = [np.array([0, 0, img.shape[1], img.shape[0]], np.float32)]
    people = []
    for box in boxes:
        pts, score = _estimate(pose, img, np.asarray(box, np.float32))
        p = _to_openpose(pts, score)
        if sum(1 for k in p["body"] if k) >= 3:
            people.append(p)
    return {"width": img.shape[1], "height": img.shape[0], "people": people}


# ---------------------------------------------------------------- drawing (like controlnet_aux)

LIMBS = [[1, 2], [1, 5], [2, 3], [3, 4], [5, 6], [6, 7], [1, 8], [8, 9], [9, 10], [1, 11], [11, 12], [12, 13],
         [1, 0], [0, 14], [14, 16], [0, 15], [15, 17]]
BODY_COLORS = [[255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0], [170, 255, 0], [85, 255, 0], [0, 255, 0],
               [0, 255, 85], [0, 255, 170], [0, 255, 255], [0, 170, 255], [0, 85, 255], [0, 0, 255], [85, 0, 255],
               [170, 0, 255], [255, 0, 255], [255, 0, 170], [255, 0, 85]]
HAND_EDGES = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [0, 9], [9, 10], [10, 11], [11, 12],
              [0, 13], [13, 14], [14, 15], [15, 16], [0, 17], [17, 18], [18, 19], [19, 20]]


def _hand_color(i):
    import colorsys
    return [int(c * 255) for c in colorsys.hsv_to_rgb(i / len(HAND_EDGES), 1.0, 1.0)]


def _extent(pts):
    pts = [p for p in pts or [] if p]
    if len(pts) < 2:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return max(max(xs) - min(xs), max(ys) - min(ys))


def draw_pose(pose, width=None, height=None):
    """Renders the pose editor's format (see detect_pose) as an OpenPose control image."""
    import cv2
    from PIL import Image
    w, h = int(width or pose["width"]), int(height or pose["height"])
    sx, sy = w / pose["width"], h / pose["height"]
    scale = lambda pts: pts and [p and (p[0] * sx, p[1] * sy) for p in pts]  # noqa: E731
    s = max(w, h) / 512
    stick, joint = max(3, 4 * s), max(3, 4 * s)
    canvas = np.zeros((h, w, 3), np.uint8)
    people = [{k: scale(v) for k, v in p.items()} for p in pose["people"]]
    for p in people:
        b = p["body"]
        for i, (a, c) in enumerate(LIMBS):
            if not b[a] or not b[c]:
                continue
            (x1, y1), (x2, y2) = b[a], b[c]
            poly = cv2.ellipse2Poly((int((x1 + x2) / 2), int((y1 + y2) / 2)),
                                    (int(math.hypot(x2 - x1, y2 - y1) / 2), int(stick)),
                                    int(math.degrees(math.atan2(y2 - y1, x2 - x1))), 0, 360, 1)
            layer = canvas.copy()
            cv2.fillConvexPoly(layer, poly, BODY_COLORS[i])
            canvas = cv2.addWeighted(canvas, 0.4, layer, 0.6, 0)
        for i, k in enumerate(b):
            if k:
                cv2.circle(canvas, (int(k[0]), int(k[1])), int(joint), BODY_COLORS[i], -1)
    for p in people:
        for side in ("rhand", "lhand"):
            hand = p.get(side)
            if not hand:
                continue
            ext = _extent(hand) or 1
            line = int(max(1, min(2 * s, ext / 28)))
            r = int(max(1, min(4 * s, ext / 14)))
            for i, (a, c) in enumerate(HAND_EDGES):
                if hand[a] and hand[c]:
                    cv2.line(canvas, tuple(int(v) for v in hand[a]), tuple(int(v) for v in hand[c]), _hand_color(i), line)
            for k in hand:
                if k:
                    cv2.circle(canvas, (int(k[0]), int(k[1])), r, (0, 0, 255), -1)
    for p in people:
        face = p.get("face")
        if face:
            # larger dots are copied into the picture (e.g. as dots on a visor)
            r = int(max(1, min(3 * s, (_extent(face) or 1) / 70)))
            for k in face:
                if k:
                    cv2.circle(canvas, (int(k[0]), int(k[1])), r, (255, 255, 255), -1)
    return Image.fromarray(canvas)


# ---------------------------------------------------------------- other control types

_depth_pipes = {}


def depth(image, report=None, model="depth"):
    """A depth map (near light, far dark) by Depth Anything V2: model "depth" (Small) or "depth_base"."""
    from PIL import Image
    if model not in _depth_pipes:
        import torch
        from transformers import pipeline
        d = ensure_model(model, report)
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        _depth_pipes[model] = pipeline("depth-estimation", model=str(d), device=device)
    out = _depth_pipes[model](image.convert("RGB"))["depth"]
    return Image.merge("RGB", [out.convert("L")] * 3).resize(image.size)


def _edges(image, low, high, blur=0, thicken=0):
    import cv2
    from PIL import Image
    gray = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    if blur:
        gray = cv2.GaussianBlur(gray, (blur, blur), 0)
    e = cv2.Canny(gray, low, high)
    if thicken:
        e = cv2.dilate(e, np.ones((3, 3), np.uint8), iterations=thicken)
    return Image.fromarray(np.stack([e] * 3, -1))


def control_image(kind, image, report=None, depth_model="depth"):
    """Control image of the given ControlNet type from a photo (PIL); depth_model: "depth" (Small) or "depth_base"."""
    if kind == "BodyPose":
        return draw_pose(detect_pose(image, report))
    if kind == "Depth":
        return depth(image, report, depth_model)
    if kind == "Canny":
        return _edges(image, 100, 200)
    if kind == "LineArt":
        return _edges(image, 50, 130, blur=3)
    if kind == "Scribble":
        return _edges(image, 60, 160, blur=5, thicken=2)
    if kind == "Tile":
        return image.convert("RGB")
    raise ValueError("No preprocessing for ControlNet type %s" % kind)


def main(argv):
    from PIL import Image
    if len(argv) < 2 or argv[0] != "detect_pose":
        print("usage: main.py detect_pose <image>", file=sys.stderr)
        return 2

    def report(stage, pct):
        print("__progress__ " + json.dumps({"stage": stage, "progress": pct}), flush=True)

    try:
        result = detect_pose(Image.open(argv[1]), report)
        print("__pose__ " + json.dumps(result), flush=True)
        return 0
    except Exception as e:
        print("__error__ " + json.dumps({"error": str(e)}), flush=True)
        return 1
