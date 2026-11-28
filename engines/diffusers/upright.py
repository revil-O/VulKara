# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Converging verticals straightened (Enhance: the built-in tool "Upright"), without a model.

The nearly vertical line segments of the photo are found (Canny, probabilistic Hough), their common vanishing point is
estimated robustly (random pairs of segments, the point most of them pass close to, then least squares over those),
and one perspective transform maps two lines through that point onto verticals, anchored at the middle row so the
photo keeps its size there. The strength moves the target points part of the way; the empty corners are cut off.
"""
import math

import cv2
import numpy as np

TOOL_ID = "builtin:upright"
MANIFEST = {"name": "Upright", "task": "upright", "kind": "image"}

WORK_SIZE = 1500  # long side of the copy the lines are found on
MAX_LEAN = 30  # degrees from vertical a segment may lean to count
MIN_LINES = 4  # fewer agreeing segments: the photo has no clear verticals
INLIER_DEG = 1.5  # a segment agrees with a vanishing point when it points at it within this angle
MAX_CORRECTION = 25  # degrees: the outer guide lines are never turned further (strong corrections stretch people)
STRAIGHT = 0.2  # degrees: verticals leaning less are left alone
# a building's verticals meet far outside the picture; lines meeting closer than this many picture heights from its
# middle are something else (stems in a vase, rays, a fan)
MIN_DISTANCE = 0.8
MIN_SPREAD = 0.25  # the agreeing segments must spread over at least this share of the width
MIN_KEPT = 0.5  # a result keeping less of the photo's area is not given
MAX_SEGMENTS = 300  # the longest segments carry the estimate; more only cost time on busy photos (trees, grass)


def _segments(rgb):
    """Nearly vertical line segments [(x1, y1, x2, y2)] in the photo's pixels, longest first."""
    h, w = rgb.shape[:2]
    scale = min(1.0, WORK_SIZE / max(h, w))
    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if scale < 1:
        grey = cv2.resize(grey, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    edges = cv2.Canny(grey, 50, 150)
    found = cv2.HoughLinesP(edges, 1, np.pi / 180, 40, minLineLength=max(20, int(min(grey.shape) * 0.05)), maxLineGap=8)
    out = []
    for x1, y1, x2, y2 in (found.reshape(-1, 4) if found is not None else []):  # (N, 1, 4) in OpenCV 4, (N, 4) in 5
        lean = (math.degrees(math.atan2(x2 - x1, y2 - y1)) + 90) % 180 - 90
        if abs(lean) <= MAX_LEAN:
            out.append(np.array([x1, y1, x2, y2], np.float64) / scale)
    return sorted(out, key=lambda s: -math.hypot(s[2] - s[0], s[3] - s[1]))[:MAX_SEGMENTS]


def _line(s):
    """The segment's line as homogeneous coordinates, normalised (a·x + b·y + c = 0 with a² + b² = 1)."""
    l = np.cross([s[0], s[1], 1.0], [s[2], s[3], 1.0])
    return l / math.hypot(l[0], l[1])


def _agrees(s, v):
    """Whether the segment points at the vanishing point v (homogeneous; v[2] = 0: a direction)."""
    mid = np.array([(s[0] + s[2]) / 2, (s[1] + s[3]) / 2])
    to_v = v[:2] - mid * v[2]
    d = np.array([s[2] - s[0], s[3] - s[1]])
    cos = abs(d @ to_v) / (np.linalg.norm(d) * np.linalg.norm(to_v) + 1e-12)
    return cos >= math.cos(math.radians(INLIER_DEG))


def vanishing_point(segments, tries=400, seed=0):
    """The vertical vanishing point (homogeneous, unit length) most segments agree with, and the agreeing segments."""
    if len(segments) < 2:
        return None, []
    rng = np.random.default_rng(seed)
    lines = [_line(s) for s in segments]
    weights = np.array([math.hypot(s[2] - s[0], s[3] - s[1]) for s in segments])
    best, best_score = None, 0.0
    for _ in range(tries):
        i, j = rng.choice(len(segments), 2, replace=False)
        v = np.cross(lines[i], lines[j])
        if not np.any(v):
            continue
        v = v / np.linalg.norm(v)
        score = sum(weights[k] for k, s in enumerate(segments) if _agrees(s, v))
        if score > best_score:
            best, best_score = v, score
    if best is None:
        return None, []
    inliers = [k for k, s in enumerate(segments) if _agrees(s, best)]
    if len(inliers) < 2:
        return None, []
    # least squares: the point nearest to all agreeing lines, weighted by their length
    a = np.array([lines[k] * weights[k] for k in inliers])
    v = np.linalg.svd(a)[2][-1]
    return v / np.linalg.norm(v), [segments[k] for k in inliers]


def _through(v, x, y, at_y):
    """Where the line from (x, y) towards the vanishing point v crosses the row at_y."""
    dx, dy = v[0] - x * v[2], v[1] - y * v[2]
    if abs(dy) < 1e-12:
        return x
    return x + dx * (at_y - y) / dy


def _inner_box(valid):
    """The largest upright rectangle (x0, y0, x1, y1) inside the valid area, searched on a coarse grid."""
    h, w = valid.shape
    k = max(1, max(h, w) // 300)
    small = valid[::k, ::k]
    rows = []
    for r in small:
        xs = np.flatnonzero(r)
        rows.append((xs[0], xs[-1]) if len(xs) and xs[-1] - xs[0] + 1 == len(xs) else (None, None))
    best, box = 0, (0, 0, w, h)
    n = len(rows)
    for top in range(n):
        if rows[top][0] is None:
            continue
        left, right = rows[top]
        for bottom in range(top, n):
            if rows[bottom][0] is None:
                break
            left, right = max(left, rows[bottom][0]), min(right, rows[bottom][1])
            if right <= left:
                break
            area = (right - left + 1) * (bottom - top + 1)
            if area > best:
                best, box = area, (left * k, top * k, (right + 1) * k, (bottom + 1) * k)
    # one pixel in from each side: the edge rows of the grid may still touch the empty corner
    x0, y0, x1, y1 = box
    return x0 + k, y0 + k, min(w, x1) - k, min(h, y1) - k


def straighten(rgb, strength=1.0, stop=None):
    """The photo with its verticals straightened by the strength (0..1); and whether clear verticals were found. Without
    them, or at strength 0, the photo comes back as it is. (None, False) when stop() asks to end."""
    strength = max(0.0, min(1.0, float(strength)))
    segments = _segments(rgb)
    v, agreeing = vanishing_point(segments)
    if v is None or len(agreeing) < MIN_LINES:
        return rgb, False
    h, w = rgb.shape[:2]
    mids = [(sg[0] + sg[2]) / 2 for sg in agreeing]
    if max(mids) - min(mids) < MIN_SPREAD * w:
        return rgb, False
    if abs(v[2]) > 1e-12 and math.hypot(v[0] / v[2] - w / 2, v[1] / v[2] - h / 2) < MIN_DISTANCE * h:
        return rgb, False
    mid = h / 2
    xs = (0.25 * w, 0.75 * w)
    tops = [_through(v, x, mid, 0) for x in xs]
    bottoms = [_through(v, x, mid, h) for x in xs]
    lean = max(abs(math.degrees(math.atan2(t - x, mid))) for t, x in zip(tops, xs))
    if lean < STRAIGHT or strength == 0:
        return rgb, True
    # never turn the guide lines by more than MAX_CORRECTION degrees
    strength *= min(1.0, MAX_CORRECTION / lean)
    src = np.float32([[tops[0], 0], [tops[1], 0], [bottoms[1], h], [bottoms[0], h]])
    target = np.float32([[xs[0], 0], [xs[1], 0], [xs[1], h], [xs[0], h]])
    dst = src + strength * (target - src)
    m = cv2.getPerspectiveTransform(src, dst)
    if stop and stop():
        return None, False
    corners = cv2.perspectiveTransform(np.float32([[[0, 0]], [[w, 0]], [[w, h]], [[0, h]]]), m)[:, 0]
    x_min, y_min = np.floor(corners.min(axis=0))
    x_max, y_max = np.ceil(corners.max(axis=0))
    shift = np.array([[1, 0, -x_min], [0, 1, -y_min], [0, 0, 1]], np.float64)
    size = (int(x_max - x_min), int(y_max - y_min))
    if size[0] * size[1] > 4 * w * h:
        return rgb, True  # a degenerate estimate: leave the photo as it is rather than distort it
    # where the corrected photo has no empty corners, found on a coarse copy (a few hundred pixels across) ...
    k = max(1.0, max(size) / 400)
    coarse = np.diag([1 / k, 1 / k, 1.0])
    small_src = (max(1, round(w / k)), max(1, round(h / k)))
    valid = cv2.warpPerspective(np.full(small_src[::-1], 255, np.uint8), coarse @ shift @ m @ np.linalg.inv(coarse),
                                (max(1, math.ceil(size[0] / k)), max(1, math.ceil(size[1] / k))), flags=cv2.INTER_NEAREST) > 0
    bx0, by0, bx1, by1 = _inner_box(valid)
    x0, y0 = math.ceil(bx0 * k), math.ceil(by0 * k)
    x1, y1 = min(size[0], math.floor(bx1 * k)), min(size[1], math.floor(by1 * k))
    if x1 <= x0 or y1 <= y0 or (x1 - x0) * (y1 - y0) < MIN_KEPT * w * h:
        return rgb, False
    # ... then only that part is made at full size: no canvas larger than the photo
    crop = np.array([[1, 0, -x0], [0, 1, -y0], [0, 0, 1]], np.float64)
    out = cv2.warpPerspective(rgb, crop @ shift @ m, (x1 - x0, y1 - y0), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return np.ascontiguousarray(out), True
