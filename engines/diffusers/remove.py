# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Removing a painted object (Inpainting → Remove): its place filled from the surroundings, without a prompt or a
picture model.

The painted mask is grown first: a mask exactly on the object left a ghost of its outline with both fillers. Small
areas are filled by LaMa (restore.fill, on the CPU, about a second); large ones by RORem, an SDXL inpainting model
trained to remove objects, at 512 px around the mask with its maker's settings. ObjectClear (objectclear.py), only
when asked for, works on the whole picture and takes the object's shadow and a darker reflection with it: of the
area it marks beyond the painted mask only what it makes lighter joins (a removed shadow; a light reflection must be
painted), never a face of another person that the face detector (when downloaded) finds nor a person Apple Vision
finds that is not painted (up to four). The
filled area gets the colours around it (RORem left a lighter patch) and is blended in softly; outside the grown mask
the picture stays to the pixel. Measured in docs/MEASUREMENTS.md, 7by, 7ca and 7cc.
"""
import os

import cv2
import numpy as np
from PIL import Image

# RORem (Apache-2.0; its base, SDXL inpainting 0.1, under CreativeML OpenRAIL++-M), downloaded as a helper model
HELPER = "rorem"
REPO = "LetsThink/RORem"
PIN = ("22d02de974c8dc92c717cd3431f8b0fe0eeecc3b", {
    "model_index.json": "6bbb51e728849016e28b3b9426bf34dcadb089d7d758ea04406fe240a284133f",
    "scheduler/scheduler_config.json": "7c3996754c270ade2a9674636f63eb5a5e4133319eca3596fe728c1fd22525de",
    "text_encoder/config.json": "79afdab1d0562fbfe88050b9ae5c754ce218a28e9f1dd2464934ffd8412ace69",
    "text_encoder/model.safetensors": "660c6f5b1abae9dc498ac2d21e1347d2abdb0cf6c0c0c8576cd796491d9a6cdd",
    "text_encoder_2/config.json": "fd4532a8004620304d0f53d50f0aea5ed2d47cdbf0ae7a32ccd3f01ad49b6ba0",
    "text_encoder_2/model.safetensors": "ec310df2af79c318e24d20511b601a591ca8cd4f1fce1d8dff822a356bcdb1f4",
    "tokenizer/merges.txt": "9fd691f7c8039210e0fced15865466c65820d09b63988b0174bfe25de299051a",
    "tokenizer/special_tokens_map.json": "c4864a9376a8401918425bed71fc14fc0e81f9b59ec45c1cf96cccb2df508eac",
    "tokenizer/tokenizer_config.json": "7eb36a76a02551ce8583dbee08d062e672997a5fe1db82ebc642d88c7e79cc96",
    "tokenizer/vocab.json": "e089ad92ba36837a0d31433e555c8f45fe601ab5c221d4f607ded32d9f7a4349",
    "tokenizer_2/merges.txt": "9fd691f7c8039210e0fced15865466c65820d09b63988b0174bfe25de299051a",
    "tokenizer_2/special_tokens_map.json": "f118ab3a983206e4f32583448de6bd6aae4ee21869135cef1f5848a753cdaab6",
    "tokenizer_2/tokenizer_config.json": "516314ccab66918d7cb647480ac27abd3520d14e1e5825aac99f50c851c16071",
    "tokenizer_2/vocab.json": "e089ad92ba36837a0d31433e555c8f45fe601ab5c221d4f607ded32d9f7a4349",
    "unet/config.json": "5af962909637ac683e1aadf88ae70c7015905446a759a068c9a09687f3be58f9",
    "unet/diffusion_pytorch_model.safetensors": "ed10552914ce17189e9544071b2b3d1cbd467834e0e5a7b79469dc32800b8b4e",
    "vae/config.json": "f88842ae29663e47f34161fb520f081a355a1511af7810c3e5fb1d6c282c8bb6",
    "vae/diffusion_pytorch_model.safetensors": "6353737672c94b96174cb590f711eac6edf2fcce5b6e91aa9d73c5adc589ee48",
})
# the maker's settings; 1024 px took 14.1 GB on the 16 GB Mac mini, 512 px 8.8 GB, 20 steps 10 s (7by)
SIZE, STEPS, GUIDANCE, STRENGTH = 512, 20, 1.0, 0.99
# the mask grows by this share of the picture's longer side
GROW = 0.015
# from this share of the picture (grown mask) Auto takes RORem: LaMa smeared large areas
LARGE = 0.15
# ObjectClear's effects beyond the painted mask count where it lightens the picture by this much (Lab L, 0..100,
# smoothed over SMOOTH × the growth): its effects area also spilled onto a neighbour's face, arm and papers (7cc)
LIGHTER, SMOOTH = 3.0, 0.5
# ... at this longer side at most (ObjectClear works at a shorter side of 512, a longer one of at most 1024)
WORK = 1024
# a face found beside the painted mask is protected with this margin (share of its size) all round
FACE_MARGIN = 0.1
# a person Vision finds is the removed one when this share of it is painted; the others keep ObjectClear's effects
# off (a dark jacket before a light window passed as a shadow and was smeared)
OWN_PERSON = 0.1
# ObjectClear kept the object when the edges inside the painted mask follow the original's this closely (correlation
# of the grey gradients): kept or redrawn 0.46-0.63, removed at most 0.21 over 131 results (MEASUREMENTS 7ci)
KEPT = 0.35


def widen(m, px):
    """The mask m (0/1) grown by px pixels all round."""
    return cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * px + 1, 2 * px + 1)))


def grow(mask, size):
    """The painted mask (0/1 at the picture's size), the grown one and by how many pixels it grew."""
    painted = (np.asarray(mask.convert("L").resize(size, Image.NEAREST)) > 127).astype(np.uint8)
    px = max(1, int(round(GROW * max(size))))
    return painted, widen(painted, px), px


def methods(method, rorem_ready, objectclear_ready, allowed):
    """The methods a job runs, one picture each: Compare takes every one on this Mac (ObjectClear only where allowed,
    not in a build with commercially usable models only), as each makes things up now and then."""
    if method != "compare":
        return [method]
    return [m for m, ok in (("lama", True), ("rorem", rorem_ready), ("objectclear", objectclear_ready and allowed)) if ok]


def choose(method, share, rorem_ready, objectclear_ready=False, auto_objectclear=False):
    """The filler that runs ("lama", "rorem" or "objectclear") and a note when Auto wanted RORem but it is not
    downloaded. Auto takes ObjectClear whenever it is there and allowed (auto_objectclear: not in a build with
    commercially usable models only): on 28 pictures with architecture LaMa and RORem left the dark shadow under
    vehicles even at 4 % of the picture (MEASUREMENTS 7cb)."""
    if method == "auto" and auto_objectclear and objectclear_ready:
        return "objectclear", ""
    if method == "objectclear":
        if objectclear_ready:
            return "objectclear", ""
        raise ValueError("Download ObjectClear first (Models → Helper models)")
    if method == "lama" or (method == "auto" and share < LARGE):
        return "lama", ""
    if rorem_ready:
        return "rorem", ""
    if method == "rorem":
        raise ValueError("Download RORem first (Models → Helper models)")
    return "lama", "RORem is not downloaded: LaMa filled the large area (Models → Helper models)"


def kept_object(original, filled, painted):
    """Did the filler leave the object (or paint it again) in the painted mask (0/1)? ObjectClear sometimes paints a
    bottle into a bottle-shaped hole, mostly with a loosely painted mask (hand test 2026-11-14). Compared at most WORK
    px on the longer side, only around the mask."""
    ys, xs = np.flatnonzero(painted.any(1)), np.flatnonzero(painted.any(0))
    if not len(ys):
        return False
    y0, y1, x0, x1 = ys[0], ys[-1] + 1, xs[0], xs[-1] + 1
    k = max(1.0, max(y1 - y0, x1 - x0) / WORK)
    size = (max(1, round((x1 - x0) / k)), max(1, round((y1 - y0) / k)))
    inside = cv2.resize(np.ascontiguousarray(painted[y0:y1, x0:x1]), size, interpolation=cv2.INTER_NEAREST) > 0
    # a gradient needs two pixels each way (a thin wire across a panorama shrinks to one row)
    if min(size) < 2 or inside.sum() < 50:
        return False

    def edges(a):
        grey = cv2.resize(np.ascontiguousarray(a[y0:y1, x0:x1]), size, interpolation=cv2.INTER_AREA).astype(np.float32).mean(2)
        return np.hypot(*np.gradient(grey))[inside]
    a, b = edges(filled), edges(original)
    if a.std() == 0 or b.std() == 0:
        return False
    return float(np.corrcoef(a, b)[0, 1]) > KEPT


def box(m, margin):
    """One square area around the whole mask m plus margin, within the picture (RORem sees its surroundings)."""
    import restore
    ys, xs = np.nonzero(m)
    x0, y0 = max(0, xs.min() - margin), max(0, ys.min() - margin)
    x1, y1 = min(m.shape[1], xs.max() + 1 + margin), min(m.shape[0], ys.max() + 1 + margin)
    return restore.square(x0, y0, x1 - x0, y1 - y0, m.shape[1], m.shape[0])


def square_crop(rgb, m, area):
    """The area (x0, y0, x1, y1) of rgb and of the mask m as SIZE×SIZE pictures for RORem, padded to a square by
    mirroring (a wide area stretched to a square squashed what RORem saw), and the square's side."""
    x0, y0, x1, y1 = area
    w, h = x1 - x0, y1 - y0
    side = max(w, h)
    pic = cv2.copyMakeBorder(np.ascontiguousarray(rgb[y0:y1, x0:x1]), 0, side - h, 0, side - w, cv2.BORDER_REFLECT_101)
    hole = cv2.copyMakeBorder(np.ascontiguousarray(m[y0:y1, x0:x1]).astype(np.float32), 0, side - h, 0, side - w, cv2.BORDER_CONSTANT, value=0)
    pic = cv2.resize(pic, (SIZE, SIZE), interpolation=cv2.INTER_AREA if side > SIZE else cv2.INTER_LANCZOS4)
    # area, not nearest: a thin stroke must not vanish when the mask is made smaller
    hole = (cv2.resize(hole, (SIZE, SIZE), interpolation=cv2.INTER_AREA) > 0).astype(np.uint8) * 255
    return Image.fromarray(pic), Image.fromarray(hole), side


def match_colours(original, filled, grown, px, skip=None):
    """filled shifted, inside the grown mask, by how far its colours stray from the original on a ring just outside it,
    measured there and carried smoothly inwards. Local, not one mean for the whole area: around an object between
    sky and trees one mean lifted the tree line into a bright ghost (7by). LaMa keeps the ring as it was, so it is
    left alone; RORem's crop comes back a little lighter, which is taken out. skip (bool): not measured there (a
    protected face or person, where ObjectClear's fill is a different face or lighter clothes)."""
    ring = cv2.dilate(grown, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * px + 1, 2 * px + 1))) - grown
    if skip is not None:
        ring[skip] = 0
    if not ring.any():
        return filled
    sigma = max(3.0, 4.0 * px)
    # only the area around the mask: blurring a 19 MP frame with this sigma took many seconds
    ys, xs = np.nonzero(ring)
    reach = int(3 * sigma)
    y0, y1 = max(0, ys.min() - reach), min(grown.shape[0], ys.max() + 1 + reach)
    x0, x1 = max(0, xs.min() - reach), min(grown.shape[1], xs.max() + 1 + reach)
    o, f = original[y0:y1, x0:x1], filled[y0:y1, x0:x1]
    r, g = ring[y0:y1, x0:x1], grown[y0:y1, x0:x1]
    diff = (o.astype(np.float32) - f.astype(np.float32)) * r[..., None]
    # the offset is smooth: computed at a fraction of the size, so a large sigma stays cheap
    k = max(1, int(sigma // 8))
    small = (max(1, diff.shape[1] // k), max(1, diff.shape[0] // k))
    w_s = cv2.GaussianBlur(cv2.resize(r.astype(np.float32), small, interpolation=cv2.INTER_AREA), (0, 0), sigma / k)
    d_s = cv2.GaussianBlur(cv2.resize(diff, small, interpolation=cv2.INTER_AREA), (0, 0), sigma / k)
    size = (diff.shape[1], diff.shape[0])
    weight = cv2.resize(w_s, size, interpolation=cv2.INTER_LINEAR)
    offset = cv2.resize(d_s, size, interpolation=cv2.INTER_LINEAR) / np.maximum(weight, 1e-4)[..., None]
    # far from any ring pixel the weight is tiny and the offset noise: fade it out there
    offset *= np.clip(weight / max(float(weight[g > 0].max()), 1e-4), 0, 1)[..., None] ** 0.5
    part = np.clip(f.astype(np.float32) + offset + 0.5, 0, 255).astype(np.uint8)
    out = filled.copy()
    out[y0:y1, x0:x1] = np.where(g[..., None] > 0, part, f)
    return out


def blend(original, filled, painted, grown, px):
    """filled on the painted mask and the inner half of the grown part, fading to the original over its outer half;
    outside the grown mask the original. Fading from the painted edge on let the object's soft outline show again."""
    half = px / 2
    alpha = 1 - (cv2.distanceTransform(1 - painted, cv2.DIST_L2, 3) - half) / (half + 1)
    alpha = np.clip(alpha, 0, 1) * grown
    out = original * (1 - alpha[..., None]) + filled * alpha[..., None]
    return np.where(alpha[..., None] > 0, np.clip(out + 0.5, 0, 255).astype(np.uint8), original)


def other_faces(rgb, painted):
    """Boxes (x0, y0, x1, y1), a little enlarged and not clipped to the picture (a face at its edge keeps its centre),
    of the faces in rgb whose eyes, nose and mouth all lie outside the painted mask (other people; the box may still
    reach into the mask); none when the face detector (YuNet, from the face restoration helper) is not downloaded.
    A broken detector file raises (cv2.error)."""
    import restore
    detector = os.path.join(restore.helper_folder(restore.FACE_HELPER), restore.FACE_DETECTOR)
    if not os.path.isfile(detector):
        return []
    h, w = painted.shape
    boxes = []
    for pts in restore.find_faces(rgb, detector):
        xs, ys = np.clip(np.round(pts[:, 0]).astype(int), 0, w - 1), np.clip(np.round(pts[:, 1]).astype(int), 0, h - 1)
        if painted[ys, xs].any():
            continue
        sq = restore.face_square(pts)
        if sq is None:
            continue
        x, y, bw, bh = sq
        mx, my = bw * FACE_MARGIN, bh * FACE_MARGIN
        boxes.append((int(np.floor(x - mx)), int(np.floor(y - my)),
                      int(np.ceil(x + bw + mx)), int(np.ceil(y + bh + my))))
    return boxes


def face_area(faces, shape):
    """The ellipses inside the face boxes (unclipped; cv2 clips the drawing) as one mask (bool): the box corners are
    background or the removed object, a straight edge there showed as a seam (7cc)."""
    area = np.zeros(shape, np.uint8)
    for x0, y0, x1, y1 in faces:
        cv2.ellipse(area, (((x0 + x1) / 2, (y0 + y1) / 2), (x1 - x0, y1 - y0), 0), 1, -1)
    return area > 0


def other_persons(labels, painted, px):
    """The people in labels (a map, 1..n per person, 0 = none; None: not known) of whom less than OWN_PERSON is
    painted, grown by px all round (their soft outline), as one mask (bool) and how many."""
    if labels is None:
        return np.zeros(painted.shape, bool), 0
    area = np.zeros(painted.shape, np.uint8)
    n = 0
    for k in np.unique(labels[labels > 0]):
        person = labels == k
        if painted[person].mean() < OWN_PERSON:
            area |= person.view(np.uint8)
            n += 1
    return widen(area, px) > 0, n


def shadows(original, filled, effects, painted, grown, px, protect):
    """Of ObjectClear's effects (0/1) the part beyond the painted mask it may replace: where its fill is lighter than
    the original (a removed shadow; a changed face, arm or paper is as often darker), outside protect (faces, bool),
    and only the parts touching the grown mask. In the grown mask's soft edge the rest fades in as without effects."""
    extra = (effects > 0) & (painted == 0) & ~protect
    if not extra.any():
        return np.zeros_like(grown)
    # at most WORK px on the longer side, only around the effects: ObjectClear's fill has no more detail (shorter side
    # 512), and Lab, blur and labels of a 24 MP frame at full size cost seconds and hundreds of MB
    h, w = grown.shape
    k = max(1.0, max(h, w) / WORK)
    sigma = max(1.0, SMOOTH * px)
    reach = int(3 * sigma) + 1
    ys, xs = np.flatnonzero(extra.any(1)), np.flatnonzero(extra.any(0))  # not np.nonzero: 16 bytes per pixel
    y0, y1 = max(0, ys[0] - reach), min(h, ys[-1] + 1 + reach)
    x0, x1 = max(0, xs[0] - reach), min(w, xs[-1] + 1 + reach)
    size = (max(1, round((x1 - x0) / k)), max(1, round((y1 - y0) / k)))

    def small(a, how=cv2.INTER_AREA):
        return cv2.resize(np.ascontiguousarray(a[y0:y1, x0:x1]), size, interpolation=how)

    light = [cv2.cvtColor(small(a).astype(np.float32) / 255, cv2.COLOR_RGB2LAB)[..., 0].copy()
             for a in (filled, original)]
    lighter = cv2.GaussianBlur(light[0] - light[1], (0, 0), sigma / k) > LIGHTER
    ext = small(extra.view(np.uint8)) > 0
    near = small(grown) > 0
    keep = (lighter & ext).astype(np.uint8)
    _, labels = cv2.connectedComponents(keep | near.view(np.uint8))
    keep = (np.isin(labels, np.unique(labels[near])) & (keep > 0)).astype(np.uint8)
    out = np.zeros_like(grown)
    out[y0:y1, x0:x1] = cv2.resize(keep, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST)
    return out & extra


def ready(folder):
    """RORem is there: pinned.py marked this revision complete (a hand-deleted file or a new pin is not)."""
    import pinned
    return pinned._checked(folder).get("revision") == PIN[0] and all(os.path.isfile(os.path.join(folder, f)) for f in PIN[1])


def remove(img, mask, method, lama, rorem, rorem_ready, state=None, note=None, objectclear=None,
           objectclear_ready=False, auto_objectclear=False, log=None, persons=None, check=True):
    """The picture without the painted object. lama, rorem: fill(img, grown) -> the picture with the grown mask
    (0/1) filled; objectclear: fill(img, grown) -> that picture and the object's effects (0/1 at img's size), which
    are then replaced like the painted mask where shadows() allows it; method: "auto", "lama", "rorem" or
    "objectclear"; log: a line for the engine's log; persons: () -> the people's map at img's size (see
    other_persons) or None, asked only when ObjectClear ran; check: when ObjectClear kept the object (kept_object),
    fill again as Auto without it (not when comparing the methods). Returns the picture, the filler that ran and the
    grown share."""
    state = state or (lambda s: None)
    painted, grown, px = grow(mask, img.size)
    if not painted.any():
        raise ValueError("Paint over the object to remove first")
    share = float(grown.mean())
    used, why = choose(method, share, rorem_ready, objectclear_ready, auto_objectclear)
    if why and note:
        note(why)
    state("Removing the object")
    filled = {"lama": lama, "rorem": rorem, "objectclear": objectclear}[used](img, grown)
    effects = protect = skip = None
    if used == "objectclear":
        filled, effects = filled
    filled = np.asarray(filled.convert("RGB").resize(img.size))
    original = np.asarray(img.convert("RGB"))
    if effects is not None and check and kept_object(original, filled, painted):
        # filled again as Auto does without ObjectClear (its shadows are then not removed)
        used, why = choose("auto", share, rorem_ready)
        if note:
            note("ObjectClear kept the object: filled again without it")
            if why:
                note(why)
        if log:
            log("[remove] ObjectClear kept the object, filled by %s" % used)
        filled = np.asarray({"lama": lama, "rorem": rorem}[used](img, grown).convert("RGB").resize(img.size))
        effects = None
    if effects is not None:
        beyond = float(((effects > 0) & (painted == 0)).mean())
        # always: a neighbour's face in the grown soft edge is protected too
        try:
            faces = other_faces(original, painted)
        except Exception as e:  # a broken detector file must not cost the minute ObjectClear just ran
            faces = []
            if log:
                log("[remove] face detection failed: %s" % e)
            if note:
                note("Face detection failed: faces were not protected")
        protect = face_area(faces, grown.shape)
        try:
            people, kept = other_persons(persons() if persons else None, painted, px)
        except Exception as e:  # as with faces: a broken people map must not cost ObjectClear's minute
            people, kept = np.zeros(painted.shape, bool), 0
            if log:
                log("[remove] person map failed: %s" % e)
            if note:
                note("Person detection failed: people were not protected")
        extra = shadows(original, filled, effects, painted, grown, px, protect | people)
        if log:
            h, w = grown.shape
            boxes = [(max(0, a), max(0, b), min(w, c), min(h, d)) for a, b, c, d in faces]
            log("[remove] ObjectClear marked %.2f %% of the picture beyond the mask, %.2f %% kept (lighter); faces "
                "protected: %s; persons protected: %d" % (100 * beyond, 100 * float(extra.mean()), boxes or "none", kept))
        painted = np.maximum(painted, extra)
        grown = widen(painted, px)
        # on another person's face only the painted mask itself is replaced, no soft edge (7cc: it changed the chin)
        grown = np.where(protect, painted, grown)
        # where ObjectClear's fill differs on purpose the colours are not measured
        skip = protect | people
    state("Matching the colours")
    filled = match_colours(original, filled, grown, px, skip)
    return Image.fromarray(blend(original, filled, painted, grown, px)), used, share
