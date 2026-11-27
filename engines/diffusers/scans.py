# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Scans page: the photos on a flatbed scan, found and cut out.

The scanner's background is taken from a strip along the scan's edge; whatever differs from it in colour is a
photo. Each connected area becomes the smallest turned rectangle around it (no line search). A rectangle is
{cx, cy, w, h, angle, turn} in pixels of the scan: angle in degrees (|angle| <= 45, positive turns clockwise on
screen), turn the user's quarter turns (0, 90, 180, 270, clockwise) applied after straightening.

    python main.py find_photos <scan>    __photos__ {"size": [w, h], "photos": [...]}
    python main.py cut_photos <job.json> __cut__ {"files": [...]}; job: {"scan", "photos", "out", "word"}

Cut-out photos keep the scan's bit depth (16 bit stays 16 bit), DPI and colour profile; they are written as PNG
"<scan> – <word> <n>.png" and never over an existing file.
"""
import json
import math
import os
import struct
import zlib

import cv2
import numpy as np

WORK_SIZE = 1500  # long side of the copy the photos are found on
EDGE_STRIP = 0.02  # share of each side the background is measured on
MIN_AREA = 0.02  # areas below this share of the scan are dust or marks
INSET = 0.004  # the rectangle is drawn in by this share of the photo's short side, so no background seam is left
PAPER_BORDER = 0.08  # a white print border is cut off when it is at most this share of the side
MIN_FILL = 0.35  # a photo fills its rectangle (less only by bright holes); a strip along the scan's edge does not


def load(path):
    """The scan as it is stored (8 or 16 bit, grey stays 2D, alpha dropped)."""
    # any depth and colour as stored, the EXIF orientation applied (as the page shows the scan); alpha is dropped
    img = cv2.imread(path, cv2.IMREAD_ANYDEPTH | cv2.IMREAD_ANYCOLOR)
    if img is None:
        raise FileNotFoundError(f"could not read the scan {path}")
    if img.ndim == 3 and img.shape[2] == 4:
        img = img[:, :, :3]
    return img


def _eight_bit_colour(img):
    if img.dtype == np.uint16:
        img = (img >> 8).astype(np.uint8)
    elif img.dtype != np.uint8:
        img = np.clip(img, 0, 255).astype(np.uint8)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img


def _strip(a, b):
    return np.concatenate([a[:b].reshape(-1, *a.shape[2:]), a[-b:].reshape(-1, *a.shape[2:]),
                           a[:, :b].reshape(-1, *a.shape[2:]), a[:, -b:].reshape(-1, *a.shape[2:])])


def _photo_mask(small):
    """Pixels that differ in colour from the scanner's background (bright parts of a photo still differ by more than
    the scanner's noise; the rectangle around the area covers bites at its edge)."""
    b = max(2, int(min(small.shape[:2]) * EDGE_STRIP))
    smooth = cv2.medianBlur(small, 3).astype(np.int16)
    edge = _strip(smooth, b)
    background = np.median(edge, axis=0)
    dist = np.abs(smooth - background).max(axis=2)
    noise = np.median(np.abs(edge - background).max(axis=1))
    mask = dist > max(8.0, 6.0 * noise)
    mask = cv2.morphologyEx(mask.astype(np.uint8) * 255, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    return mask


def _rectangle(points, scale):
    """The smallest turned rectangle around the points, in the scan's pixels and this module's convention."""
    box = cv2.boxPoints(cv2.minAreaRect(points)) / scale
    e1, e2 = box[1] - box[0], box[2] - box[1]
    # the edge nearer to horizontal gives width and angle
    across, down = (e1, e2) if abs(e1[0]) >= abs(e1[1]) else (e2, e1)
    if across[0] < 0:
        across = -across
    angle = math.degrees(math.atan2(across[1], across[0]))
    w, h = float(np.hypot(*across)), float(np.hypot(*down))
    cx, cy = box.mean(axis=0)
    inset = INSET * min(w, h)
    return {"cx": float(cx), "cy": float(cy), "w": w - 2 * inset, "h": h - 2 * inset, "angle": angle, "turn": 0}


def _extent(p):
    """Top and bottom of the turned rectangle on screen."""
    a = math.radians(p["angle"])
    half = (abs(math.sin(a)) * p["w"] + abs(math.cos(a)) * p["h"]) / 2
    return p["cy"] - half, p["cy"] + half


def reading_order(photos):
    """Row by row from the top (same row when the heights overlap by more than half the smaller one), then left to right."""
    rows = []
    for p in sorted(photos, key=lambda q: _extent(q)[0]):
        top, bottom = _extent(p)
        for row in rows:
            rt, rb = row[0]
            overlap = min(bottom, rb) - max(top, rt)
            if overlap > 0.5 * min(bottom - top, rb - rt):
                row[1].append(p)
                break
        else:
            rows.append([(top, bottom), [p]])
    return [p for _, ps in rows for p in sorted(ps, key=lambda q: q["cx"])]


def _paper_lines(lines):
    """How many lines from the start are white paper: bright, even and without colour."""
    n = 0
    for line in lines:
        means = line.reshape(-1, 3).mean(axis=0)
        if means.mean() < 215 or line.std() > 6 or means.max() - means.min() > 12:
            break
        n += 1
    return n


def without_paper_border(img, p):
    """The rectangle drawn in to the picture where the photo has a white paper border (old prints); a bright band wider
    than a border can be (sky, snow) stays."""
    a = _eight_bit_colour(cut(img, {**p, "turn": 0})).astype(np.float32)
    h, w = a.shape[:2]
    cuts = []
    for lines, length in ((a, h), (a[::-1], h), (a.transpose(1, 0, 2), w), (a.transpose(1, 0, 2)[::-1], w)):
        n = _paper_lines(lines[: int(length * PAPER_BORDER) + 2])
        cuts.append(n + 1 if 0 < n <= length * PAPER_BORDER else 0)
    top, bottom, left, right = cuts
    # old prints have their border all round: a bright band at one or two edges is sky, snow or a wall
    if sum(1 for c in cuts if c) < 3:
        return p
    a_ = math.radians(p["angle"])
    du, dv = (left - right) / 2, (top - bottom) / 2
    return {**p, "w": p["w"] - left - right, "h": p["h"] - top - bottom,
            "cx": p["cx"] + du * math.cos(a_) - dv * math.sin(a_), "cy": p["cy"] + du * math.sin(a_) + dv * math.cos(a_)}


def find_photos(img):
    """The photos on the scan as turned rectangles in reading order; [] when there is none."""
    colour = _eight_bit_colour(img)
    h, w = colour.shape[:2]
    scale = min(1.0, WORK_SIZE / max(h, w))
    small = cv2.resize(colour, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else colour
    mask = _photo_mask(small)
    # outer edges and their holes: an area inside the hole of another (a photo inside a dark strip round the scan)
    # is an area of its own; what an area covers is its outline less its holes
    contours, tree = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    least = MIN_AREA * small.shape[0] * small.shape[1]
    found = []
    for i, c in enumerate(contours):
        if tree[0][i][3] != -1:  # a hole
            continue
        covered = cv2.contourArea(c) - sum(cv2.contourArea(contours[j]) for j in range(len(contours)) if tree[0][j][3] == i)
        (_, _), (rw, rh), _ = cv2.minAreaRect(c)
        if covered >= least and covered >= MIN_FILL * rw * rh:
            found.append(_rectangle(c, scale))
    return reading_order([without_paper_border(img, p) for p in found])


def find_main(argv):
    """main.py find_photos <scan>: one line __photos__ {"size": [w, h], "photos": [...]} or __error__."""
    try:
        img = load(argv[0])
        photos = [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in p.items()} for p in find_photos(img)]
        print("__photos__ " + json.dumps({"size": [img.shape[1], img.shape[0]], "photos": photos}), flush=True)
        return 0
    except Exception as e:
        print("__error__ " + json.dumps({"error": str(e)}), flush=True)
        return 1


def _corners(p):
    """Top left, top right and bottom left of the turned rectangle in the scan's pixels."""
    a = math.radians(p["angle"])
    c, s = math.cos(a), math.sin(a)
    at = lambda dx, dy: (p["cx"] + dx * c - dy * s, p["cy"] + dx * s + dy * c)  # noqa: E731
    w, h = p["w"] / 2, p["h"] / 2
    return np.float32([at(-w, -h), at(w, -h), at(-w, h)])


def straight(p):
    """Whether the frame's tilt moves its far edge by less than half a pixel: then it is cut out without turning."""
    return abs(math.sin(math.radians(p["angle"]))) * max(p["w"], p["h"]) < 0.5


def check_frame(img, p):
    """A frame must have its middle on the scan and be no larger than the scan's diagonal."""
    h, w = img.shape[:2]
    if not (0 <= p["cx"] <= w and 0 <= p["cy"] <= h):
        raise ValueError("a frame lies outside the scan")
    if not (0 < p["w"] <= math.hypot(w, h) and 0 < p["h"] <= math.hypot(w, h)):
        raise ValueError("a frame is larger than the scan")


def cut(img, p):
    """One photo straightened and cut out of the scan, clipped to the scan where the rectangle reaches past it."""
    check_frame(img, p)
    w, h = max(1, round(p["w"])), max(1, round(p["h"]))
    m = cv2.getAffineTransform(_corners(p), np.float32([[0, 0], [w, 0], [0, h]]))
    if straight(p):  # straight already: no interpolation, only the pixels
        m = np.float64([[1, 0, round(m[0, 2])], [0, 1, round(m[1, 2])]])
    out = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    inside = cv2.warpAffine(np.full(img.shape[:2], 255, np.uint8), m, (w, h), flags=cv2.INTER_NEAREST)
    inside = inside > 0
    # the columns inside the scan where most of the frame is, then the rows inside those columns
    cols = np.flatnonzero(inside.mean(axis=0) > 0.5 * inside.mean(axis=0).max()) if inside.any() else []
    rows = np.flatnonzero(inside[:, cols[0]:cols[-1] + 1].mean(axis=1) > 0.99) if len(cols) else []
    if len(rows):
        cols = np.flatnonzero(inside[rows[0]:rows[-1] + 1].mean(axis=0) > 0.99)
    if not len(rows) or not len(cols):
        raise ValueError("the frame lies outside the scan")
    out = out[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    return np.ascontiguousarray(np.rot90(out, -(p.get("turn", 0) // 90)))


def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def write_png(path, img, dpi=None, icc=None):
    """img as PNG (8 or 16 bit as it is) with DPI (pHYs) and colour profile (iCCP) put in after the header."""
    ok, data = cv2.imencode(".png", img)
    if not ok:
        raise ValueError(f"could not write {path}")
    data = data.tobytes()
    extra = b""
    # a grey PNG may only carry a grey profile
    if icc and (img.ndim == 3 or icc[16:20] == b"GRAY"):
        extra += _chunk(b"iCCP", b"ICC Profile\0\0" + zlib.compress(icc))
    if dpi and dpi[0] and dpi[1]:
        extra += _chunk(b"pHYs", struct.pack(">IIB", round(dpi[0] / 0.0254), round(dpi[1] / 0.0254), 1))
    end_of_header = 8 + 25  # signature, IHDR chunk
    with open(path, "xb") as f:  # never over a file, also when two exports run at once
        f.write(data[:end_of_header] + extra + data[end_of_header:])


def unique_path(folder, stem):
    """folder/stem.png, or stem (2).png, (3) … when that name is taken."""
    path, n = os.path.join(folder, stem + ".png"), 1
    while os.path.exists(path):
        n += 1
        path = os.path.join(folder, f"{stem} ({n}).png")
    return path


def _scan_info(path):
    """DPI (as the scan is shown: swapped for a quarter-turned JPEG) and colour profile; (None, None) when they can
    not be read (the photos are cut out all the same)."""
    from PIL import Image
    try:
        with Image.open(path) as im:
            dpi, icc = im.info.get("dpi"), im.info.get("icc_profile")
            if dpi and im.getexif().get(274) in (5, 6, 7, 8):
                dpi = (dpi[1], dpi[0])
            return (tuple(round(d) for d in dpi) if dpi else None), icc
    except Exception:
        return None, None


def cut_photos(scan, photos, out_dir, word, report=None):
    """Every photo of the scan cut out into out_dir as "<scan> – <word> <n>.png"; the files written."""
    img = load(scan)
    dpi, icc = _scan_info(scan)
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(scan))[0]
    files = []
    for i, p in enumerate(photos, 1):
        photo = cut(img, p)
        while True:
            path = unique_path(out_dir, f"{stem} \u2013 {word} {i}")
            try:
                write_png(path, photo, dpi, icc)
                break
            except FileExistsError:  # taken in the meantime by another export
                continue
        files.append(path)
        if report:
            report(i / len(photos))
    return files


def cut_main(argv):
    """main.py cut_photos <job.json>: __progress__ lines, then __cut__ {"files": [...]} or __error__."""
    try:
        with open(argv[0], encoding="utf-8") as f:
            job = json.load(f)
        progress = lambda v: print("__progress__ " + json.dumps({"stage": "cut", "progress": round(v * 100)}), flush=True)  # noqa: E731
        progress(0)
        files = cut_photos(job["scan"], job["photos"], job["out"], job.get("word") or "Photo", progress)
        print("__cut__ " + json.dumps({"files": files}), flush=True)
        return 0
    except Exception as e:
        print("__error__ " + json.dumps({"error": str(e)}), flush=True)
        return 1
