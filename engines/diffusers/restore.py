# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Restoring old photos: colour cast and contrast, repairing by an AI under guard rails, rebuilding soft detail,
restoring faces, colouring, sharpening.

The repairing AI (an image editing model) is told what it may do, and its result is held to it afterwards:
  - outside the painted damage the original stays (when that lock is on),
  - the picture may change only so much outside the damage, and no face may appear, vanish or move.
A result that breaks a rule is refused, not delivered. Colouring is done by DDColor, a model made for it: it only adds
colour to the brightness of the photo, so it can not change a shape or a detail.

Soft detail of the whole photo is rebuilt by Real-ESRGAN (the photo made as much smaller as it is soft, then four times
larger again); faces, which it can not rebuild, by CodeFormer, taken from the photo before Real-ESRGAN (its texture
would turn into wrinkles) and blended in by a strength. Measured in docs/MEASUREMENTS.md.
"""
import os

import cv2
import numpy as np
from PIL import Image

# the rules every AI restoration gets; the user adds own ones in the app
BASE_RULES = [
    "Only restore the photo: remove scratches, dust, spots, stains, creases, tears and holes.",
    "Keep the composition, framing and perspective exactly as they are.",
    "Keep every person, face, facial expression, pose, hair and body exactly as it is; do not beautify or rejuvenate.",
    "Keep clothing, objects, buildings, background and any writing exactly as they are.",
    "Do not add, remove or invent anything.",
]
GRAY_RULE = "Keep the colors of the photo as they are; do not colorize it."

# DDColor (Apache 2.0): the ModelScope weights, the most natural colours of its versions
COLOR_REPO, COLOR_FILE = "piddnad/ddcolor_modelscope", "pytorch_model.bin"
COLOR_PIN = ("060f67494e31883a4b13cb27f889f3154847ada4", "d81711971ec59200da26d5e8a1afae8dd3778d495ea8ad7a7dadc769f403f7e7")
COLOR_SIZE = 512
# LaMa (Apache 2.0) as ONNX: it fills holes and scratches from their surroundings; ONNX holds no code that runs on loading
LAMA_REPO, LAMA_FILE = "edgetools/lama", "lama_fp32.onnx"
LAMA_PIN = ("d3f22ee032d32d9a68ac06dd3da40aba1f831f1d", "1faef5301d78db7dda502fe59966957ec4b79dd64e16f03ed96913c7a4eb68d6")
LAMA_SIZE = 512
# Real-ESRGAN x4plus (BSD-3-Clause), the Upscale helper: rebuilds edges and textures of the whole photo
DETAIL_HELPER = "realesrgan"
DETAIL_TOOL = {"runtime": "torch", "model": "RealESRGAN_x4plus.safetensors", "scale": 4, "range": "0-1", "multiple": 4,
               "half": True, "tile": 384, "tile_metal_gb": {"256": 1.3, "384": 2.4, "512": 3.0}}
# lrzjason's consistency LoRA for FLUX.2 [klein] 4B (Apache-2.0): the repair stays closer to the photo, scratches go
# more thoroughly; made for 4B only. It adds 1.1-2.2 GB while denoising (11.7 GB on the Mac mini, MEASUREMENTS 7bh)
CONSISTENCY_HELPER = "klein4b_consistency"
CONSISTENCY_FILE = "f2k_4B_consist_20260314.safetensors"
CONSISTENCY_VARIANT = "klein4b"
CONSISTENCY_GB = 1.7
# image to image: at full strength the LoRA held the edit back, at half it kept the picture and made the edit (7bi)
KEEP_PICTURE_SCALE = 0.5
# CodeFormer (S-Lab License 1.0, non-commercial) restores faces; YuNet (MIT, OpenCV Zoo) finds them with 5 landmarks
FACE_HELPER = "codeformer"
FACE_MODEL, FACE_DETECTOR = "codeformer.pth", "face_detection_yunet_2023mar.onnx"
FACE_FILES = {
    FACE_MODEL: ("https://github.com/sczhou/CodeFormer/releases/download/v0.1.0/codeformer.pth",
                 "1009e537e0c2a07d4cabce6355f53cb66767cd4b4297ec7a4a64ca4b8a5684b7"),
    FACE_DETECTOR: ("https://github.com/opencv/opencv_zoo/raw/f12e12798e8314f7c074a6656816c048dcc95b7a/models/"
                    "face_detection_yunet/face_detection_yunet_2023mar.onnx",
                    "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
}
# where the eyes, nose and mouth corners of a face sit in CodeFormer's 512 px square (the FFHQ alignment)
FACE_TEMPLATE = np.array([[192.98138, 239.94708], [318.90277, 240.1936], [256.63416, 314.01935],
                          [201.26117, 371.41043], [313.08905, 371.15118]], np.float32)
# a face smaller than this (eye to mouth corners, in pixels) is left alone: CodeFormer would invent it
FACE_MIN = 14

# a black-and-white photo has one hue at most (grey, or toned like sepia): its colour varies this little (LAB a/b)
MONOCHROME_SPREAD = 6.0
# a face may move by this share of the picture's diagonal
FACE_SHIFT = 0.05


def to_array(img):
    return np.asarray(img.convert("RGB"))


def _unit(x):
    """x as a float within 0..1."""
    return min(1.0, max(0.0, float(x)))


def helper_folder(helper_id):
    """The folder of a helper model of helpers.json (whether it is downloaded or not)."""
    import helpers
    return helpers.folder_of(next(x for x in helpers.catalog() if x["id"] == helper_id))


def is_grayscale(img):
    """A black-and-white photo, also a toned one (sepia): its colour hardly varies over the picture."""
    lab = cv2.cvtColor(to_array(img.resize((256, 256))), cv2.COLOR_RGB2LAB).astype(np.float32)
    return float(max(lab[..., 1].std(), lab[..., 2].std())) < MONOCHROME_SPREAD


def correct(img, neutral=None, strength=1.0):
    """Colour cast, faded tones and flat contrast: grey-world white balance, levels, local contrast.
    neutral: make a toned black-and-white photo neutral grey (None: when the photo is one). Light tones are compressed
    towards white instead of clipped, so a white dress keeps its folds. strength 0..1 blends with the photo."""
    orig = to_array(img).astype(np.float32)
    a = orig.copy()
    if neutral is None:
        neutral = is_grayscale(img)
    if neutral:
        a = np.repeat(cv2.cvtColor(a.astype(np.uint8), cv2.COLOR_RGB2GRAY)[..., None], 3, axis=2).astype(np.float32)
    else:
        # grey world: the average colour of a photo is neutral; a red or yellow cast shifts it
        means = a.reshape(-1, 3).mean(0)
        a *= means.mean() / np.maximum(means, 1)
    # levels over all channels together (per channel would bring a cast back): the darkest 0.5 % become black, the
    # brightest 0.2 % white; above 80 % a soft shoulder compresses instead of clipping
    lo, hi = np.percentile(a, [0.5, 99.8])
    x = np.clip((a - lo) / np.maximum(hi - lo, 1), 0, None)
    knee = 0.8
    over = x > knee
    x[over] = knee + (1 - knee) * (1 - np.exp(-(x[over] - knee) / (1 - knee)))
    a = (np.clip(x, 0, 1) * 255).astype(np.uint8)
    # local contrast on the brightness only, so colours do not shift
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB)
    lab[..., 0] = cv2.createCLAHE(clipLimit=1.2, tileGridSize=(8, 8)).apply(lab[..., 0])
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB).astype(np.float32)
    return Image.fromarray((orig + (out - orig) * _unit(strength)).clip(0, 255).round().astype(np.uint8))


def guard_prompt(user_rules, note=""):
    """The instruction for the editing model: the fixed rules, the user's own rules and an optional note."""
    rules = BASE_RULES + [GRAY_RULE]
    rules += [r.strip() for r in user_rules or [] if r and r.strip()]
    text = " ".join(rules)
    return (note.strip() + " " + text).strip() if note and note.strip() else text


def _mask(mask, size):
    """The painted damage as weights 0..1, grown a little and with soft edges."""
    if mask is None:
        return None
    m = np.asarray(mask.convert("L").resize(size, Image.BILINEAR)).astype(np.float32) / 255
    if m.max() <= 0:
        return None
    grow = max(3, int(round(min(size) * 0.006)))
    m = cv2.dilate(m, np.ones((grow * 2 + 1, grow * 2 + 1), np.uint8))
    m = np.clip(cv2.GaussianBlur(m, (0, 0), grow), 0, 1)
    m[m < 0.004] = 0  # the soft edge ends: beyond it the original stays untouched
    return m


def _damage(img, mask):
    """The painted damage as 0/1 at the photo's size, grown a little over the edge of each mark."""
    m = (np.asarray(mask.convert("L").resize(img.size, Image.NEAREST)) > 127).astype(np.uint8)
    return cv2.dilate(m, np.ones((5, 5), np.uint8)) if m.any() else None


def prefill(img, mask, report=None):
    """The painted damage filled from its surroundings before the AI sees the photo: an editing model keeps what it is
    shown, also a white hole; filled, it only has to refine the place. LaMa fills; without it OpenCV does, more simply."""
    if mask is None:
        return img
    m = _damage(img, mask)
    if m is None:
        return img
    try:
        return fill(img, m, report)
    except Exception as e:  # no network for the first download, for instance: the simple filling still helps
        if report:
            report("LaMa not available (%s), filling simply" % str(e).splitlines()[0][:80])
        return Image.fromarray(cv2.inpaint(to_array(img), m, max(3, int(min(img.size) * 0.008)), cv2.INPAINT_TELEA))


_lama = None


def _lama_session(report=None):
    global _lama
    if _lama is None:
        import onnxruntime
        import pinned
        import preprocess
        if report:
            report("Loading the filling model (0.2 GB, downloaded once)")
        folder = pinned.fetch(LAMA_REPO, LAMA_PIN[0], {LAMA_FILE: LAMA_PIN[1]}, str(preprocess.root() / "inpaint" / LAMA_REPO.replace("/", "--")))
        path = os.path.join(folder, LAMA_FILE)
        _lama = onnxruntime.InferenceSession(path, providers=["CPUExecutionProvider"])
    return _lama


def _boxes(m, margin):
    """Square areas around the damage: marks close to each other share one, so LaMa sees their surroundings."""
    grown = cv2.dilate(m, np.ones((margin * 2 + 1, margin * 2 + 1), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(grown, connectivity=8)
    h, w = m.shape
    return [square(x, y, bw, bh, w, h) for x, y, bw, bh, _area in stats[1:count]]


def square(x, y, bw, bh, w, h):
    """The square around the box x, y, bw, bh with the same centre, moved into a w x h picture."""
    side = min(max(bw, bh), max(w, h))
    cx, cy = x + bw / 2, y + bh / 2
    x0 = int(min(max(0, cx - side / 2), max(0, w - side)))
    y0 = int(min(max(0, cy - side / 2), max(0, h - side)))
    return (x0, y0, min(w, x0 + side), min(h, y0 + side))


def fill(img, m, report=None):
    """Fills the damage m (0/1 at the photo's size) with LaMa, area by area; outside the damage nothing changes."""
    session = _lama_session(report)
    names = [i.name for i in session.get_inputs()]
    out = to_array(img).copy()
    for x0, y0, x1, y1 in _boxes(m, max(24, int(min(m.shape) * 0.06))):
        crop, cm = out[y0:y1, x0:x1], m[y0:y1, x0:x1]
        if not cm.any():
            continue
        size = (crop.shape[1], crop.shape[0])
        image = cv2.resize(crop, (LAMA_SIZE, LAMA_SIZE), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
        hole = (cv2.resize(cm, (LAMA_SIZE, LAMA_SIZE), interpolation=cv2.INTER_NEAREST) > 0).astype(np.float32)
        result = session.run(None, {names[0]: image.transpose(2, 0, 1)[None], names[1]: hole[None, None]})[0][0]
        result = result.transpose(1, 2, 0)
        if result.max() <= 1.5:  # some exports give 0..1, others 0..255
            result = result * 255
        filled = cv2.resize(np.clip(result, 0, 255).astype(np.uint8), size, interpolation=cv2.INTER_CUBIC)
        out[y0:y1, x0:x1] = np.where(cm[..., None] > 0, filled, crop)
    return Image.fromarray(out)


def structure_change(a, b, outside=None):
    """How much the shapes differ (0..1): the mean difference of the blurred brightness, at a small size, so
    grain, dust and colour do not count. outside: weights of the area that counts (1 = counts)."""
    def small(x):
        g = cv2.cvtColor(x, cv2.COLOR_RGB2GRAY).astype(np.float32)
        h, w = g.shape
        s = 384 / max(h, w)
        g = cv2.resize(g, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
        return cv2.GaussianBlur(g, (0, 0), 2)
    da, db = small(a), small(b)
    diff = np.abs(da - db) / 255
    if outside is None:
        return float(diff.mean())
    weight = cv2.resize(outside.astype(np.float32), (diff.shape[1], diff.shape[0]), interpolation=cv2.INTER_AREA)
    return float((diff * weight).sum() / max(weight.sum(), 1e-6))


def compose(original, ai, mask=None, repair=True, colorize=False, lock=True):
    """The repaired picture from the original (after correction) and the AI result.
    repair: shapes may come from the AI (only inside the damage when lock and a mask are given);
    colorize: the colours come from the AI everywhere, the brightness never outside the damage."""
    o = to_array(original)
    a = to_array(ai.resize(original.size, Image.LANCZOS))
    m = _mask(mask, original.size)
    ol, al = cv2.cvtColor(o, cv2.COLOR_RGB2LAB), cv2.cvtColor(a, cv2.COLOR_RGB2LAB)
    out = ol.astype(np.float32)
    if repair:
        weight = m if (lock and m is not None) else np.ones(o.shape[:2], np.float32)
        out = out * (1 - weight[..., None]) + al.astype(np.float32) * weight[..., None]
    if colorize:
        out[..., 1:] = al[..., 1:]
    rgb = cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    if not colorize:
        # where nothing changes the original stays to the pixel (LAB and back would round it)
        weight = (m if (lock and m is not None) else np.ones(o.shape[:2], np.float32)) if repair else np.zeros(o.shape[:2], np.float32)
        rgb = np.where(weight[..., None] > 0, rgb, o)
    return Image.fromarray(rgb), m


def faces(img, detect):
    """Centres of the faces found (normalised to 0..1)."""
    pose = detect(img)
    w, h = pose["width"], pose["height"]
    out = []
    for p in pose["people"]:
        pts = [q for q in (p.get("face") or []) if q]
        if len(pts) >= 10:
            out.append((sum(q[0] for q in pts) / len(pts) / w, sum(q[1] for q in pts) / len(pts) / h))
    return out


def faces_kept(before, after):
    """Every face is still there, near where it was, and none was added."""
    if len(before) != len(after):
        return False
    left = list(after)
    for fx, fy in before:
        near = [f for f in left if ((f[0] - fx) ** 2 + (f[1] - fy) ** 2) ** 0.5 <= FACE_SHIFT * 2 ** 0.5]
        if not near:
            return False
        left.remove(near[0])
    return True


def check(original, result, mask_weights, max_change, detect=None):
    """The guard rails on the delivered picture. Returns (ok, message)."""
    o, r = to_array(original), to_array(result)
    outside = None if mask_weights is None else 1 - mask_weights
    change = structure_change(o, r, outside)
    where = "outside the painted damage" if mask_weights is not None else "in the picture"
    if change > max_change:
        return False, ("The AI changed %.0f %% of the shapes %s (allowed: %.0f %%). Paint the damaged parts, "
                       "or allow more change." % (change * 100, where, max_change * 100))
    if detect is not None:
        before, after = faces(original, detect), faces(result, detect)
        if not faces_kept(before, after):
            return False, ("The AI changed the faces: %d before, %d after, or one moved. The result was not kept."
                           % (len(before), len(after)))
    return True, "Guard rails kept: %.1f %% change %s (allowed %.0f %%)." % (change * 100, where, max_change * 100)


_colorizer = None


def _ddcolor(device, report=None):
    """The colouring model, downloaded on first use into the helper models' folder and kept loaded."""
    global _colorizer
    if _colorizer is None:
        import torch
        import ddcolor
        import pinned
        import preprocess
        if report:
            report("Loading the colouring model (0.9 GB, downloaded once)")
        folder = pinned.fetch(COLOR_REPO, COLOR_PIN[0], {COLOR_FILE: COLOR_PIN[1]}, str(preprocess.root() / "colorize" / COLOR_REPO.replace("/", "--")))
        path = os.path.join(folder, COLOR_FILE)
        state = torch.load(path, map_location="cpu", weights_only=True)
        state = state.get("params", state)
        model = ddcolor.DDColor(encoder_name="convnext-l", decoder_name="MultiScaleColorDecoder", input_size=[COLOR_SIZE, COLOR_SIZE],
                                num_output_channels=2, last_norm="Spectral", do_normalize=False, num_queries=100, num_scales=3, dec_layers=9)
        missing, unexpected = model.load_state_dict(state, strict=False)
        if missing:
            raise RuntimeError("The colouring model does not fit its weights (%d missing)" % len(missing))
        _colorizer = model.to(device).eval()
    return _colorizer


def colorize(img, strength=1.0, device="cpu", report=None):
    """Colours a black-and-white photo with DDColor. Only the colour comes from the model: the brightness, with all
    shapes and details, stays the photo's own at full size. strength scales the colours (1 = as the model sees them)."""
    import torch
    import torch.nn.functional as F
    model = _ddcolor(device, report)
    rgb = to_array(img).astype(np.float32) / 255
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    small = cv2.resize(rgb, (COLOR_SIZE, COLOR_SIZE), interpolation=cv2.INTER_AREA)
    light = cv2.cvtColor(small, cv2.COLOR_RGB2LAB)[..., :1]
    gray = cv2.cvtColor(np.concatenate([light, np.zeros_like(light), np.zeros_like(light)], -1), cv2.COLOR_LAB2RGB)
    tensor = torch.from_numpy(gray.transpose(2, 0, 1)).float().unsqueeze(0).to(device)
    with torch.inference_mode():
        ab = model(tensor).float().cpu()
    ab = F.interpolate(ab, size=rgb.shape[:2], mode="bilinear", align_corners=False)[0].numpy().transpose(1, 2, 0)
    out = cv2.cvtColor(np.concatenate([lab[..., :1], ab * float(strength)], -1), cv2.COLOR_LAB2RGB)
    return Image.fromarray((np.clip(out, 0, 1) * 255).round().astype(np.uint8))


def sharpen(img, amount=0.5):
    """Less grain and crisper details: the brightness is denoised and then sharpened, the colour only smoothed a little
    (grain in the colour is noise, not detail). amount 0..1."""
    amount = min(1.0, max(0.0, float(amount)))
    lab = cv2.cvtColor(to_array(img), cv2.COLOR_RGB2LAB)
    light = cv2.fastNlMeansDenoising(lab[..., 0], None, h=4 + 10 * amount, templateWindowSize=7, searchWindowSize=21)
    # sharpen edges only: small differences are left grain, raising them would bring the grain back
    detail = light.astype(np.float32) - cv2.GaussianBlur(light, (0, 0), 1.3).astype(np.float32)
    detail[np.abs(detail) < 2 + 2 * amount] = 0
    lab[..., 0] = np.clip(light + 1.4 * amount * detail, 0, 255).astype(np.uint8)
    for c in (1, 2):
        lab[..., c] = cv2.GaussianBlur(lab[..., c], (0, 0), 1.0)
    return Image.fromarray(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))


def _keep_tone(result, photo):
    """A black-and-white or toned photo keeps its own colour: only the brightness comes from the model's result."""
    if not is_grayscale(photo):
        return result
    res = cv2.cvtColor(to_array(result), cv2.COLOR_RGB2LAB)
    own = cv2.cvtColor(to_array(photo.resize(result.size, Image.LANCZOS)), cv2.COLOR_RGB2LAB)
    res[..., 1:] = own[..., 1:]
    return Image.fromarray(cv2.cvtColor(res, cv2.COLOR_LAB2RGB))


def details(img, level=2.0, strength=1.0, scale=1, report=None, stop=None):
    """Soft detail of the whole photo rebuilt by Real-ESRGAN: the photo is made `level` times smaller (as soft as it
    is), four times larger by the model, and brought to `scale` (1 or 2) times its own size. strength 0..1 blends with
    the photo. Returns None when stopped."""
    import helpers
    import photo_tools
    folder = helper_folder(DETAIL_HELPER)
    if not os.path.isfile(os.path.join(folder, DETAIL_TOOL["model"])):
        helpers.install(DETAIL_HELPER, report=report if callable(report) else None)
    level = min(4.0, max(1.0, float(level)))
    scale = 2 if int(scale) == 2 else 1
    w, h = img.size
    small = img.resize((max(16, round(w / level)), max(16, round(h / level))), Image.LANCZOS) if level > 1 else img
    numbers = (lambda x: report(x) if isinstance(x, (int, float)) else None) if report else None
    out = photo_tools.run_image(DETAIL_TOOL, folder, to_array(small), report=numbers, stop=stop)
    if out is None:
        return None
    target = (w * scale, h * scale)
    rebuilt = _keep_tone(Image.fromarray(out).resize(target, Image.LANCZOS), img)
    strength = _unit(strength)
    if strength >= 1:
        return rebuilt
    base = img.resize(target, Image.LANCZOS) if scale != 1 else img
    return Image.blend(base, rebuilt, strength)


_face_net = None


def detector_path():
    """The face detector alone (0.2 MB), for showing the faces before anything is restored."""
    import pinned
    folder = helper_folder(FACE_HELPER)
    path = os.path.join(folder, FACE_DETECTOR)
    if not os.path.isfile(path):
        url, digest = FACE_FILES[FACE_DETECTOR]
        pinned.fetch_urls({FACE_DETECTOR: url}, {FACE_DETECTOR: digest}, folder)
    return path


def face_square(points):
    """The part of the picture a face's restoration covers (left, top, width, height), from its 5 landmarks: the
    inner square of CodeFormer's 512 px crop, mapped back."""
    m, _ = cv2.estimateAffinePartial2D(np.asarray(points, np.float32), FACE_TEMPLATE, method=cv2.LMEDS)
    if m is None:
        return None
    inv = cv2.invertAffineTransform(m)
    corners = np.array([[40, 40, 1], [472, 40, 1], [472, 472, 1], [40, 472, 1]], np.float32) @ inv.T
    x0, y0 = corners.min(0)
    x1, y1 = corners.max(0)
    return [float(x0), float(y0), float(x1 - x0), float(y1 - y0)]


def faces_main(argv):
    """main.py find_faces <image>: the faces of a photo for the Restore page, as one line
    __faces__ {"size": [w, h], "faces": [{"points": [[x, y] × 5], "box": [x, y, w, h]}]}."""
    import json
    import colour
    try:
        img = colour.open_rgb(argv[0])
        found = find_faces(to_array(img), detector_path())
        faces = [{"points": [[float(a), float(b)] for a, b in p], "box": face_square(p)} for p in found]
        print("__faces__ " + json.dumps({"size": list(img.size), "faces": [f for f in faces if f["box"]]}), flush=True)
        return 0
    except Exception as e:
        print("__error__ " + json.dumps({"error": str(e)}), flush=True)
        return 1


def consistency_lora(scale=1.0, report=None):
    """The consistency LoRA as the generation takes a resolved LoRA (downloaded on first use)."""
    import helpers
    file = os.path.join(helper_folder(CONSISTENCY_HELPER), CONSISTENCY_FILE)
    if not os.path.isfile(file):
        helpers.install(CONSISTENCY_HELPER, report=report)
    return {"file": file, "scale": scale, "name": "Consistency LoRA", "trigger_words": [], "plan_gb": CONSISTENCY_GB}


def _face_files(report=None):
    import helpers
    folder = helper_folder(FACE_HELPER)
    if not all(os.path.isfile(os.path.join(folder, f)) for f in FACE_FILES):
        helpers.install(FACE_HELPER, report=report)
    return folder


def _codeformer(device, report=None):
    """CodeFormer through spandrel (its architecture comes with spandrel_extra_arches), kept loaded."""
    global _face_net
    if _face_net is None:
        try:
            import spandrel
            import spandrel_extra_arches
        except ImportError:
            raise RuntimeError("Restoring faces needs a runtime update: Settings → Runtimes → Diffusers → Update.")
        spandrel_extra_arches.install()
        folder = _face_files(report)
        if report:
            report("Loading the face model")
        desc = spandrel.ModelLoader().load_from_file(os.path.join(folder, FACE_MODEL))
        _face_net = desc.model.to(device).eval()
    return _face_net


def find_faces(rgb, detector, min_spread=FACE_MIN):
    """The 5 landmarks (eyes, nose tip, mouth corners) of each face, largest first; faces whose landmarks spread less
    than min_spread pixels are left out (CodeFormer can not restore them; the face detailer wants them)."""
    h, w = rgb.shape[:2]
    k = min(1.0, 1280 / max(h, w))
    small = cv2.resize(rgb, (round(w * k), round(h * k)), interpolation=cv2.INTER_AREA) if k < 1 else rgb
    det = cv2.FaceDetectorYN.create(detector, "", (small.shape[1], small.shape[0]), 0.7)
    _, found = det.detect(cv2.cvtColor(small, cv2.COLOR_RGB2BGR))
    faces = [f[4:14].reshape(5, 2).astype(np.float32) / k for f in (found if found is not None else [])]
    faces = [p for p in faces if max(np.ptp(p[:, 0]), np.ptp(p[:, 1])) >= min_spread]
    return sorted(faces, key=lambda p: -np.ptp(p[:, 0]))


def _restore_face(net, face, fidelity, device):
    import torch
    t = torch.from_numpy(face.astype(np.float32) / 127.5 - 1).permute(2, 0, 1)[None].to(device)
    with torch.inference_mode():
        out = net(t, weight=float(fidelity))
        out = out[0] if isinstance(out, (tuple, list)) else out
    out = ((out.clamp(-1, 1) + 1) * 127.5)[0].permute(1, 2, 0).float().cpu().numpy()
    return out.round().astype(np.uint8)


def restore_faces(img, source=None, fidelity=0.9, strength=0.6, device="cpu", report=None, points=None):
    """Faces restored by CodeFormer and blended into img. source: the picture the faces are taken from (the photo
    before Real-ESRGAN, at img's size or smaller); fidelity 0.5..1: higher keeps more of the face as it is; strength
    0..1; points: the faces' landmarks in img's pixels as the user placed them (None: found here). Returns (picture,
    number of faces)."""
    net = _codeformer(device, report)
    folder = _face_files(report)
    if source is None:
        source = img
    base = to_array(img).astype(np.float32)
    h, w = base.shape[:2]
    src = to_array(source.resize((w, h), Image.LANCZOS) if source.size != (w, h) else source)
    found = find_faces(src, os.path.join(folder, FACE_DETECTOR)) if points is None else \
        [np.asarray(p, np.float32).reshape(5, 2) for p in points]
    gray = is_grayscale(source)
    fade = _face_fade(strength)
    for i, pts in enumerate(found):
        if report:
            report("Restoring face %d of %d" % (i + 1, len(found)))
        m, _ = cv2.estimateAffinePartial2D(pts, FACE_TEMPLATE, method=cv2.LMEDS)
        if m is None:
            continue
        fixed = _restore_face(net, cv2.warpAffine(src, m, (512, 512), borderMode=cv2.BORDER_REFLECT_101),
                              _unit(fidelity), device)
        if gray:
            fixed = np.repeat(cv2.cvtColor(fixed, cv2.COLOR_RGB2GRAY)[..., None], 3, axis=2)
        base = _paste_face(base, fixed, m, fade)
    out = Image.fromarray(base.clip(0, 255).round().astype(np.uint8))
    return (_keep_tone(out, source) if gray else out), len(found)


def _face_fade(strength):
    """The weight of a restored face over its 512 square: full in the middle, fading out towards the edge."""
    fade = np.zeros((512, 512), np.float32)
    cv2.rectangle(fade, (40, 40), (472, 472), 1.0, -1)
    return cv2.GaussianBlur(fade, (0, 0), 22) * _unit(strength)


def _paste_face(base, fixed, m, fade):
    """The restored 512 square fixed put back where m took it from, blended into base (float, H x W x 3) by fade."""
    h, w = base.shape[:2]
    inv = cv2.invertAffineTransform(m)
    back = cv2.warpAffine(fixed, inv, (w, h), flags=cv2.INTER_LANCZOS4).astype(np.float32)
    weight = cv2.warpAffine(fade, inv, (w, h))[..., None]
    return base * (1 - weight) + back * weight


def find_specks(img, sensitivity=0.5, faces=()):
    """Dust and scratches of a scan as a 0/1 mask: small dark or bright spots and thin lines that stand out much more
    than their surroundings do (a speck on a calm sky or dress, not a blossom among leaves). sensitivity 0..1; the eyes
    and the mouth of the faces (their 5 landmarks) are left alone, so catchlights and pupils stay."""
    g = cv2.cvtColor(to_array(img), cv2.COLOR_RGB2GRAY).astype(np.float32)
    k = max(5, int(min(g.shape) * 0.008) | 1)  # the largest speck, in pixels
    keep = _speck_shapes(_standing_out(g, k, _unit(sensitivity)), k)
    for pts in faces:
        pts = np.asarray(pts, np.float32).reshape(5, 2)
        span = max(np.ptp(pts[:, 0]), np.ptp(pts[:, 1]))
        for px, py in (pts[0], pts[1], (pts[3] + pts[4]) / 2):
            cv2.circle(keep, (int(px), int(py)), int(span * 0.28), 0, -1)
    return cv2.dilate(keep, np.ones((3, 3), np.uint8))


def _standing_out(g, k, sensitivity):
    """The pixels of gray picture g that are much darker or brighter than their k-sized neighbourhood, above the
    picture's grain and far above what is usual around them, as a 0/1 mask."""
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    resp = np.maximum(cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, se), cv2.morphologyEx(g, cv2.MORPH_TOPHAT, se))
    noise = float(np.median(np.abs(g - cv2.medianBlur(g.astype(np.uint8), 3).astype(np.float32)))) * 1.4826 + 1
    floor = (7.0 - 4.5 * sensitivity) * noise + 10
    # a speck stands 7-16 times above its surroundings' average response, leaves and fabric 3-5 times (MEASUREMENTS.md)
    busy = cv2.GaussianBlur(resp, (0, 0), k * 2.0)
    return ((resp > floor) & (resp > (9.0 - 5.0 * sensitivity) * (busy + 1))).astype(np.uint8)


def _speck_shapes(cand, k, max_line=0.5):
    """Of the candidate areas, the specks (at most about k x k) and the scratches (thin lines at least 3 k and at most
    max_line of the shorter side long), as a 0/1 mask."""
    n, lab, st, _ = cv2.connectedComponentsWithStats(cand, connectivity=8)
    bw, bh, area = st[:, cv2.CC_STAT_WIDTH], st[:, cv2.CC_STAT_HEIGHT], st[:, cv2.CC_STAT_AREA]
    longest = np.maximum(bw, bh)
    speck = area <= k * k * 1.2
    scratch = (longest >= 3 * k) & (area <= 3.0 * np.maximum(1, longest)) & (longest <= max_line * min(cand.shape))
    ok = speck | scratch
    ok[0] = False  # the background
    return ok[lab].astype(np.uint8)


def remove_specks(img, sensitivity=0.5, faces=(), report=None):
    """Dust and scratches filled from their surroundings (LaMa, or OpenCV without it). Returns (picture, share masked)."""
    m = find_specks(img, sensitivity, faces)
    if not m.any():
        return img, 0.0
    try:
        out = fill(img, m, report)
    except Exception as e:
        if report:
            report("LaMa not available (%s), filling simply" % str(e).splitlines()[0][:80])
        out = Image.fromarray(cv2.inpaint(to_array(img), m, 3, cv2.INPAINT_TELEA))
    return out, float(m.mean())
