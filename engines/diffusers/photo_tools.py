# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Photo tools: small models that take a photo and give back a photo or a mask (sharpen, denoise, upscale, remove JPEG
artefacts, remove the background, select objects). No diffusion model is involved. Two runtimes:
  - "torch": the original PyTorch weights (.pth, .safetensors) loaded through spandrel and run on the GPU (MPS);
    the recommended image tools (NAFNet, SCUNet, SwinIR, FBCNN) work this way;
  - "onnx" (the default of older manifests): ONNX files with onnxruntime on the CPU; the mask and selection tools
    (BiRefNet, SAM 2.1) and imported ONNX files.

Installed tools live in <helpers>/photo_tools/<name>/ with a tool.json:
  {"type": "photo_tool", "format": 1, "name", "task", "kind": "image" | "mask" | "segment", "runtime", "model": file,
   "range": "0-1" | "0-255" | "imagenet", "scale": n (image), "multiple": n, "min_side": n, "tile": n,
   "tile_metal_gb": {tile: peak GB} (GPU tools: the tile is chosen by the room left in Metal's budget),
   "size": n (fixed input), "source": {...}, "licence", ...}
The recommended ones come from photo_tools.json (pinned by commit or URL and SHA-256, pinned.py); any other file the
user imports is checked here first (inspect): one picture in, one picture or mask out, nothing else.
"""
import json
import os
import shutil
import time

import numpy as np

import paths

MANIFEST = "tool.json"
CATALOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "photo_tools.json")
FORMAT = 1
IMAGENET = (np.array([0.485, 0.456, 0.406], np.float32), np.array([0.229, 0.224, 0.225], np.float32))
MAX_PIXELS = 50_000_000  # the largest photo a tool takes (about 8K × 6K)
TORCH_FILES = (".pth", ".pt", ".safetensors")
SCALES = (1, 2, 3, 4, 8)


def root():
    return paths.helpers_dir("photo_tools")


def catalog():
    with open(CATALOG_FILE) as f:
        return json.load(f)["tools"]


def installed():
    """[(folder, manifest)] of the installed tools."""
    out = []
    base = root()
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        folder = os.path.join(base, name)
        try:
            with open(os.path.join(folder, MANIFEST)) as f:
                m = json.load(f)
        except (OSError, ValueError):
            continue
        if m.get("type") == "photo_tool":
            out.append((folder, m))
    return out


def load_manifest(folder):
    with open(os.path.join(folder, MANIFEST)) as f:
        m = json.load(f)
    if m.get("type") != "photo_tool":
        raise ValueError("Not a photo tool: %s" % folder)
    return m


def _inside(folder, name):
    """A file of the tool, which must lie in its folder (a manifest can not point elsewhere)."""
    folder = os.path.realpath(folder)
    path = os.path.realpath(os.path.join(folder, name))
    if not path.startswith(folder + os.sep):
        raise ValueError("The tool names a file outside its folder: %s" % name)
    return path


def _session(path):
    """An onnxruntime session on the CPU; custom operators of a file are not loaded (no shared libraries)."""
    import onnxruntime as ort
    opts = ort.SessionOptions()
    opts.log_severity_level = 3
    opts.intra_op_num_threads = max(1, (os.cpu_count() or 4) - 1)
    return ort.InferenceSession(path, sess_options=opts, providers=["CPUExecutionProvider"])


def _device():
    import torch
    return "mps" if torch.backends.mps.is_available() else "cpu"


def _torch_model(path):
    """The spandrel descriptor of a weights file (on the CPU), or a ValueError saying why it is not a photo tool.
    spandrel reads .pth files with a restricted unpickler: only tensors, no code."""
    try:
        import spandrel
    except ImportError:
        raise RuntimeError("This tool runs with PyTorch (spandrel), which this Diffusers runtime does not have yet: "
                           "update it in Settings → Runtimes")
    try:
        desc = spandrel.ModelLoader().load_from_file(path)
    except Exception as e:
        raise ValueError("spandrel does not know this model (%s)" % str(e)[:200])
    if not isinstance(desc, spandrel.ImageModelDescriptor):
        raise ValueError("The model takes a mask too (%s); a photo tool takes one picture" % desc.architecture.name)
    if desc.input_channels != 3 or desc.output_channels != 3:
        raise ValueError("The model takes %d channels and gives %d; a photo tool takes and gives a colour picture"
                         % (desc.input_channels, desc.output_channels))
    if desc.scale not in SCALES:
        raise ValueError("The model enlarges %d times; photo tools enlarge 1, 2, 3, 4 or 8 times" % desc.scale)
    return desc


def inspect_torch(path):
    """What a PyTorch weights file is, as a manifest draft (kind image; spandrel tells the scale and the sizes)."""
    desc = _torch_model(path)
    req = desc.size_requirements
    return {"type": "photo_tool", "format": FORMAT, "kind": "image", "runtime": "torch", "model": os.path.basename(path),
            "arch": desc.architecture.name, "scale": int(desc.scale), "range": "0-1",
            "multiple": max(1, int(req.multiple_of)), "min_side": int(req.minimum),
            "tile": 512 if desc.scale == 1 else 256}


# ---------------------------------------------------------------------------------------------------- installing

def install_recommended(tool_id, report=None):
    """Downloads a recommended tool at its pinned commit (pinned.py checks every file) and writes its manifest."""
    import pinned
    spec = next((t for t in catalog() if t["id"] == tool_id), None)
    if spec is None:
        raise ValueError("Unknown photo tool: %s" % tool_id)
    folder = os.path.join(root(), tool_id)
    if report:
        report("Downloading %s (%d MB)" % (spec["name"], spec["size_mb"]))
    if spec.get("repo"):
        pinned.fetch(spec["repo"], spec["revision"], spec["files"], folder)
        source = {"type": "hf", "repo": spec["repo"], "revision": spec["revision"]}
    else:
        pinned.fetch_urls(spec["urls"], spec["files"], folder, report=report)
        source = {"type": "url", "urls": spec["urls"]}
    manifest = {k: v for k, v in spec.items() if k not in ("files", "revision", "repo", "urls", "size_mb")}
    manifest.update({"type": "photo_tool", "format": FORMAT, "recommended": tool_id, "imported_at": int(time.time()),
                     "source": source})
    if manifest["kind"] == "image" and manifest.get("runtime") == "torch":
        manifest.setdefault("scale", inspect_torch(_inside(folder, spec["model"]))["scale"])
    elif manifest["kind"] == "image":
        manifest.setdefault("scale", _probe(_session(_inside(folder, spec["model"])), manifest)["scale"])
    with open(os.path.join(folder, MANIFEST), "w") as f:
        json.dump(manifest, f, indent=1)
    return folder, manifest


def _shape(arg):
    return [d if isinstance(d, int) else None for d in arg.shape]


def inspect(path):
    """What a model file is, or a ValueError saying why it is not a photo tool. Returns a manifest draft."""
    if not os.path.isfile(path) or not path.lower().endswith((".onnx",) + TORCH_FILES):
        raise ValueError("Choose an .onnx, .pth or .safetensors file")
    if path.lower().endswith(TORCH_FILES):
        return inspect_torch(path)
    try:
        sess = _session(path)
    except Exception as e:
        raise ValueError("onnxruntime can not load this file (%s); custom operators are not supported" % str(e)[:200])
    ins, outs = sess.get_inputs(), sess.get_outputs()
    if len(ins) != 1:
        raise ValueError("The model takes %d inputs; a photo tool takes one picture" % len(ins))
    shape = _shape(ins[0])
    if len(shape) != 4 or shape[1] not in (3, None) or "float" not in ins[0].type:
        raise ValueError("The model's input is %s %s, not a picture (1 × 3 × height × width, float)" % (ins[0].type, shape))
    out = _shape(outs[0])
    if len(out) != 4 or out[1] not in (1, 3, None):
        raise ValueError("The model's output is %s, not a picture or a mask" % out)
    fixed = shape[2] if shape[2] == shape[3] and shape[2] is not None else None
    draft = {"type": "photo_tool", "format": FORMAT, "kind": "mask" if out[1] == 1 else "image",
             "model": os.path.basename(path)}
    if fixed:
        draft["size" if draft["kind"] == "mask" else "tile"] = fixed
    probe = _probe(sess, draft)
    draft.update(probe)
    return draft


def _probe(sess, m):
    """Runs a small grey picture through the model: the scale of the output and the value range it works in."""
    side = m.get("size") or m.get("tile") or 64
    side = min(side, 128) if not (m.get("size") or m.get("tile")) else side
    name = sess.get_inputs()[0].name
    found = {}
    for rng, value in (("0-1", 0.5), ("0-255", 127.5)):
        x = np.full((1, 3, side, side), value, np.float32)
        y = np.asarray(sess.run(None, {name: x})[0], np.float32)
        if y.ndim != 4 or y.shape[2] % side or y.shape[3] % side:
            raise ValueError("The model's output (%s) is not a multiple of its input (%d × %d)" % (y.shape, side, side))
        scale = y.shape[2] // side
        if m.get("kind") == "mask":
            return {"scale": 1, "range": m.get("range", "imagenet")}
        mean = float(np.nanmean(y))
        if rng == "0-1" and 0.15 < mean < 0.85:
            found = {"scale": scale, "range": "0-1"}
            break
        if rng == "0-255" and 40 < mean < 215:
            found = {"scale": scale, "range": "0-255"}
            break
    if not found:
        raise ValueError("The value range of this model could not be found out (neither 0–1 nor 0–255)")
    if found["scale"] not in SCALES:
        raise ValueError("The model enlarges %d times; photo tools enlarge 1, 2, 3, 4 or 8 times" % found["scale"])
    return found


def import_file(path, name=None, report=None):
    """Copies a checked model file (an ONNX file with its external weight files next to it, or PyTorch weights) into
    a tool folder."""
    draft = inspect(path)
    import importer
    name = importer.safe_name(name or os.path.splitext(os.path.basename(path))[0])
    folder = os.path.join(root(), name)
    if os.path.exists(folder):
        raise FileExistsError("A photo tool named %s already exists" % name)
    os.makedirs(folder)
    try:
        if report:
            report("Copying %s" % os.path.basename(path))
        shutil.copy2(path, os.path.join(folder, os.path.basename(path)))
        # weights kept outside the graph (model.onnx.data / model.onnx_data) travel along
        base = os.path.basename(path)
        for extra in os.listdir(os.path.dirname(os.path.abspath(path))) if draft.get("runtime") != "torch" else ():
            if extra != base and extra.startswith(base) and extra.endswith(("data", "_data", ".bin")):
                shutil.copy2(os.path.join(os.path.dirname(os.path.abspath(path)), extra), os.path.join(folder, extra))
        draft.update({"name": name, "task": "custom", "imported_at": int(time.time()),
                      "source": {"type": "file", "file": os.path.basename(path)},
                      "description": "Imported from %s" % os.path.basename(path)})
        with open(os.path.join(folder, MANIFEST), "w") as f:
            json.dump(draft, f, indent=1)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return folder, draft


# ---------------------------------------------------------------------------------------------------- running

def _to_input(rgb, rng):
    """HWC uint8 RGB -> 1×3×H×W float32 in the model's range."""
    x = rgb.astype(np.float32)
    if rng == "0-1":
        x /= 255.0
    elif rng == "imagenet":
        x = (x / 255.0 - IMAGENET[0]) / IMAGENET[1]
    return np.ascontiguousarray(x.transpose(2, 0, 1)[None])


def _from_output(y, rng):
    """1×3×H×W float -> HWC float32 0..255."""
    y = np.asarray(y, np.float32)[0].transpose(1, 2, 0)
    if rng in ("0-1", "imagenet"):
        y = y * 255.0
    return np.clip(y, 0, 255)


def _weights(h, w, overlap):
    """Blending weights of a tile: 1 inside, falling off linearly over the overlap at the edges."""
    ramp_h = np.minimum(np.arange(h) + 1, np.arange(h)[::-1] + 1).astype(np.float32)
    ramp_w = np.minimum(np.arange(w) + 1, np.arange(w)[::-1] + 1).astype(np.float32)
    return (np.minimum(1.0, ramp_h / max(1, overlap))[:, None] * np.minimum(1.0, ramp_w / max(1, overlap))[None, :])


def _onnx_runner(m, folder):
    """(infer, fixed side) of an ONNX image tool: infer takes a padded HWC uint8 tile, gives HWC float 0..255."""
    sess = _session(_inside(folder, m["model"]))
    name = sess.get_inputs()[0].name
    rng = m.get("range", "0-1")
    fixed = _shape(sess.get_inputs()[0])[2]
    return (lambda padded: _from_output(sess.run(None, {name: _to_input(padded, rng)})[0], rng)), fixed, None


def metal_tile(m, budget_gb=None, used_gb=None):
    """The tile a GPU tool can afford here: the largest of the manifest's "tile_metal_gb" (tile -> peak Metal GB,
    measured in MEASUREMENTS.md) that fits in what is left of Metal's budget (0.74 × RAM, as the Hardware page
    shows it) beside what the engine holds already, with 1 GB headroom. Without the table: the manifest's tile."""
    table = m.get("tile_metal_gb")
    if not table or _device() != "mps":
        return int(m.get("tile") or 512)
    import torch
    if budget_gb is None:
        import psutil
        budget_gb = psutil.virtual_memory().total / 1e9 * 0.74
    if used_gb is None:
        used_gb = torch.mps.driver_allocated_memory() / 1e9
    room = budget_gb - used_gb - 1.0
    fits = [int(t) for t, gb in table.items() if float(gb) <= room]
    return max(fits) if fits else min(int(t) for t in table)


def _torch_runner(m, folder, model=None, quality=None):
    """(infer, None, release) of a PyTorch image tool on the GPU; release frees the model and Metal's cache.
    model: another weights file of the tool (a variant, relative to its folder); quality: FBCNN's JPEG quality 1..100
    instead of the one it estimates (lower removes more artefacts and more detail)."""
    import torch
    desc = _torch_model(_inside(folder, model or m["model"])).eval().to(_device())
    device = desc.device
    # half precision where the manifest asks for it and the architecture bears it (measured per tool, MEASUREMENTS.md)
    dtype = torch.float16 if m.get("half") and desc.supports_half and device.type == "mps" else torch.float32
    if dtype == torch.float16:
        desc = desc.half()

    qf = None
    if quality is not None and desc.architecture.name == "FBCNN":
        # FBCNN's embedding takes 1 - quality/100 (as in its own test code): low quality = strong cleanup
        qf = torch.tensor([[1.0 - min(100.0, max(1.0, float(quality))) / 100.0]], device=device, dtype=dtype)

    def infer(padded):
        x = torch.from_numpy(np.ascontiguousarray(padded)).to(device).permute(2, 0, 1)[None].to(dtype) / 255.0
        with torch.inference_mode():
            # FBCNN with a quality given: its own model call (the descriptor passes only the picture)
            y = desc.model(x, qf_input=qf)[0] if qf is not None else desc(x)
            y = y[0].float().clamp(0, 1).mul(255.0).permute(1, 2, 0).cpu()
        return y.numpy()

    def release():
        desc.to("cpu")
        if device.type == "mps":
            torch.mps.empty_cache()

    return infer, None, release


def run_image(m, folder, rgb, report=None, stop=None, model=None, quality=None):
    """An image tool on an RGB picture (HWC uint8), in overlapping tiles. Returns HWC uint8 (scaled)."""
    torch_tool = m.get("runtime") == "torch"
    tile = metal_tile(m) if torch_tool else None
    if torch_tool:
        infer, fixed, release = _torch_runner(m, folder, model=model, quality=quality)
    else:
        infer, fixed, release = _onnx_runner(m, folder)
    try:
        return _tiled(m, rgb, infer, fixed, report, stop, tile=tile)
    finally:
        if release:
            release()


def _tiled(m, rgb, infer, fixed, report=None, stop=None, tile=None):
    scale = int(m.get("scale", 1))
    mult = int(m.get("multiple", 8))
    least = int(m.get("min_side") or 0)
    h, w = rgb.shape[:2]
    tile = int(fixed or tile or m.get("tile") or 512)
    overlap = 32 if tile >= 128 else 8
    step = tile - 2 * overlap
    out = np.zeros((h * scale, w * scale, 3), np.float32)
    acc = np.zeros((h * scale, w * scale, 1), np.float32)
    ys = list(range(0, max(1, h - 2 * overlap), step)) or [0]
    xs = list(range(0, max(1, w - 2 * overlap), step)) or [0]
    total, done = len(ys) * len(xs), 0
    for y0 in ys:
        for x0 in xs:
            if stop and stop():
                return None
            y1, x1 = min(h, y0 + tile), min(w, x0 + tile)
            y0c, x0c = max(0, y1 - tile), max(0, x1 - tile)
            crop = rgb[y0c:y1, x0c:x1]
            ch, cw = crop.shape[:2]
            # padded to the model's multiple (reflected, so the edges look like the picture)
            th = fixed or max(least, -(-ch // mult) * mult)
            tw = fixed or max(least, -(-cw // mult) * mult)
            reflect = th - ch < ch and tw - cw < cw
            padded = np.pad(crop, ((0, th - ch), (0, tw - cw), (0, 0)), mode="reflect" if reflect else "edge")
            res = infer(padded)[:ch * scale, :cw * scale]
            wgt = _weights(ch * scale, cw * scale, overlap * scale)[..., None]
            out[y0c * scale:y1 * scale, x0c * scale:x1 * scale] += res * wgt
            acc[y0c * scale:y1 * scale, x0c * scale:x1 * scale] += wgt
            done += 1
            if report:
                report(100.0 * done / total)
    return np.clip(out / np.maximum(acc, 1e-6), 0, 255).round().astype(np.uint8)


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def run_mask(m, folder, rgb):
    """A mask tool (background removal): the whole picture at the model's size; returns a mask HW float 0..1."""
    from PIL import Image
    sess = _session(_inside(folder, m["model"]))
    name = sess.get_inputs()[0].name
    side = int(m.get("size") or 1024)
    small = np.asarray(Image.fromarray(rgb).resize((side, side), Image.BILINEAR))
    y = np.asarray(sess.run(None, {name: _to_input(small, m.get("range", "imagenet"))})[0], np.float32)[0, 0]
    if y.min() < 0 or y.max() > 1:
        y = _sigmoid(y)  # logits
    mask = Image.fromarray((y * 255).round().astype(np.uint8)).resize((rgb.shape[1], rgb.shape[0]), Image.BILINEAR)
    return np.asarray(mask, np.float32) / 255.0


def blend(original, result, strength):
    """The tool's result mixed with the original (enlarged the plain way where the tool enlarges)."""
    if strength >= 0.999:
        return result
    from PIL import Image
    if original.shape[:2] != result.shape[:2]:
        original = np.asarray(Image.fromarray(original).resize((result.shape[1], result.shape[0]), Image.LANCZOS))
    mixed = original.astype(np.float32) * (1 - strength) + result.astype(np.float32) * strength
    return np.clip(mixed, 0, 255).round().astype(np.uint8)


def apply(job, images_dir, report=None, stop=None, note=None):
    """A photo tool job: {"photo_tool": {"folder", "strength", "output": "cutout" | "mask", "mask": path}, "input_image"}.
    Returns the saved PNG's path, or None when stopped."""
    import uuid
    from PIL import Image
    opts = job["photo_tool"]
    folder = os.path.realpath(opts["folder"])
    if not folder.startswith(os.path.realpath(root()) + os.sep):
        raise ValueError("This photo tool is not installed")
    m = load_manifest(folder)
    if not job.get("input_image"):
        raise ValueError("Choose a picture")
    with Image.open(job["input_image"]) as head:  # the size from the header, before the pixels are read
        if head.width * head.height > MAX_PIXELS:
            raise ValueError("The picture is too large (at most %d megapixels)" % (MAX_PIXELS // 1_000_000))
    import colour
    # upright as the app shows it (a selection's mask is too), in sRGB whatever profile it carries (Display P3, HDR)
    rgb = np.asarray(colour.open_rgb(job["input_image"]))
    given = (rgb.shape[1], rgb.shape[0])  # the picture's own size, before it may be made smaller
    stem = "".join(filter(str.isalnum, os.path.splitext(os.path.basename(job["input_image"]))[0][:30])) or "photo"
    max_side = m.get("max_side")
    if max_side and max(rgb.shape[:2]) > max_side:
        if m["kind"] != "image":
            raise ValueError("%s takes pictures up to %d pixels on the longer side" % (m.get("name", "This tool"), max_side))
        # larger pictures are made smaller first (a 4× tool would otherwise give more than 8192 pixels)
        h, w = rgb.shape[:2]
        k = max_side / max(h, w)
        small = (max(1, round(w * k)), max(1, round(h * k)))
        rgb = np.asarray(Image.fromarray(rgb).resize(small, Image.LANCZOS))
        if note:
            note("The picture (%d × %d) was made smaller to %d × %d first: %s takes up to %d pixels on the longer side."
                 % (w, h, small[0], small[1], m.get("name", "this tool"), max_side))
    if m["kind"] == "image":
        model = _variant_model(m, folder, opts.get("variant"), report)
        quality = opts.get("quality") if m.get("task") == "dejpeg" else None
        # a variant with another architecture brings its own measured tile table (DAT2 needs more Metal than SwinIR)
        own = (variants(m).get(opts.get("variant")) or {}) if model else {}
        if own.get("tile_metal_gb"):
            m = dict(m, tile_metal_gb=own["tile_metal_gb"])
        out = run_image(m, folder, rgb, report, stop, model=model, quality=quality)
        if out is None:
            return None
        picture = Image.fromarray(blend(rgb, out, float(opts.get("strength", 1.0))))
        # an enlarging tool's result brought to the factor asked for, measured on the picture given
        factor = opts.get("factor")
        if factor and int(m.get("scale", 1)) > 1:
            k = min(float(factor), int(m["scale"]))
            target = (max(1, round(given[0] * k)), max(1, round(given[1] * k)))
            if target[0] < picture.width:
                picture = picture.resize(target, Image.LANCZOS)
        suffix = m.get("task") or "enhanced"
    elif m["kind"] == "mask":
        mask = run_mask(m, folder, rgb)
        picture, suffix = _cutout_or_mask(rgb, mask, opts.get("output", "cutout"))
    elif m["kind"] == "segment":
        # the mask was chosen interactively (segment_serve); the job only cuts out with it
        mask_path = opts.get("mask")
        if not mask_path or not os.path.isfile(mask_path):
            raise ValueError("Select something in the picture first")
        mask = np.asarray(Image.open(mask_path).convert("L").resize((rgb.shape[1], rgb.shape[0])), np.float32) / 255.0
        picture, suffix = _cutout_or_mask(rgb, mask, opts.get("output", "cutout"))
    else:
        raise ValueError("Unknown kind of photo tool: %s" % m["kind"])
    path = os.path.join(str(images_dir), "%s_%s_%s.png" % (stem, suffix, uuid.uuid4().hex[:12]))
    picture.save(path)
    return path


def variants(m):
    """The other weights a tool offers ({id: {"label", "description", "file", "url", "sha256", "size_mb"}}): from its
    manifest, or for a tool installed before the catalog had them, from the catalog."""
    if m.get("variants"):
        return m["variants"]
    spec = next((t for t in catalog() if t["id"] == m.get("recommended")), None)
    return (spec or {}).get("variants") or {}


def _variant_model(m, folder, variant, report=None):
    """The weights file of a variant (relative to the tool's folder), downloaded on first use at its pinned checksum;
    None for the tool's own weights."""
    if not variant or variant == "default":
        return None
    v = variants(m).get(variant)
    if not v:
        raise ValueError("%s has no variant %s" % (m.get("name", "This tool"), variant))
    import pinned
    rel = os.path.join("variants", variant)
    numbers = (lambda x: report(x) if isinstance(x, (int, float)) else None) if report else None
    pinned.fetch_urls({v["file"]: v["url"]}, {v["file"]: v["sha256"]}, os.path.join(folder, rel), report=numbers)
    return os.path.join(rel, v["file"])


def _cutout_or_mask(rgb, mask, output):
    from PIL import Image
    alpha = (np.clip(mask, 0, 1) * 255).round().astype(np.uint8)
    if output == "mask":
        return Image.fromarray(alpha, "L").convert("RGB"), "mask"
    return Image.fromarray(np.dstack([rgb, alpha]), "RGBA"), "cutout"


# ---------------------------------------------------------------------------------------------------- selecting (SAM 2)

class Segmenter:
    """SAM 2.1: the picture is encoded once, every set of clicks is a quick decoder run."""

    def __init__(self, folder):
        self.folder = folder
        self.m = load_manifest(folder)
        if self.m["kind"] != "segment":
            raise ValueError("Not a selection tool")
        self.encoder = _session(_inside(folder, self.m["model"]))
        self.decoder = _session(_inside(folder, self.m["decoder"]))
        self.image = None
        self.embeddings = None

    def _encode(self, path):
        from PIL import Image, ImageOps
        if self.image == path:
            return
        # upright as the app shows it: the clicks and the mask are in the upright picture's pixels
        src = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        self.size = src.size
        side = int(self.m.get("size") or 1024)
        x = _to_input(np.asarray(src.resize((side, side), Image.BILINEAR)), "imagenet")
        names = [o.name for o in self.encoder.get_outputs()]
        self.embeddings = dict(zip(names, self.encoder.run(None, {self.encoder.get_inputs()[0].name: x})))
        self.image = path

    def select(self, path, points, out_path, pick=None):
        """points: [[x, y, 1 | 0]] in picture pixels (1 = this belongs to it, 0 = not). SAM gives a few candidates
        (whole thing, part, detail); pick chooses one of them sorted by size, largest first, None the one SAM rates
        best. Saves the mask as PNG; returns {"mask": out_path, "score": iou, "pick": its place by size,
        "candidates": how many}."""
        from PIL import Image
        if not points:
            raise ValueError("Click on what to select")
        self._encode(path)
        side = int(self.m.get("size") or 1024)
        w, h = self.size
        coords = np.array([[[[p[0] * side / w, p[1] * side / h] for p in points]]], np.float32)
        labels = np.array([[[int(p[2]) for p in points]]], np.int64)
        feeds = {}
        for inp in self.decoder.get_inputs():
            if inp.name == "input_points":
                feeds[inp.name] = coords
            elif inp.name == "input_labels":
                feeds[inp.name] = labels
            elif inp.name == "input_boxes":
                feeds[inp.name] = np.zeros((1, 0, 4), np.float32)
            else:
                match = next((k for k in self.embeddings if k == inp.name or k.split(".")[-1] == inp.name.split(".")[-1]), None)
                if match is None:
                    raise ValueError("The selection model expects %s" % inp.name)
                feeds[inp.name] = self.embeddings[match]
        outs = dict(zip([o.name for o in self.decoder.get_outputs()], self.decoder.run(None, feeds)))
        scores = np.asarray(outs["iou_scores"], np.float32)[0, 0]
        masks = np.asarray(outs["pred_masks"], np.float32)[0, 0]
        # largest first; equal sizes keep the model's order. A candidate the same as a larger one is left out, so the
        # next pick always changes the selection
        shapes = [masks[i] > 0 for i in range(len(scores))]
        order = []
        for i in sorted(range(len(scores)), key=lambda i: -int(shapes[i].sum())):
            if not any(np.array_equal(shapes[i], shapes[j]) for j in order):
                order.append(i)
        top = int(np.argmax(scores))
        place = next(k for k, j in enumerate(order) if np.array_equal(shapes[j], shapes[top])) if pick is None else int(pick) % len(order)
        best = order[place]
        low = [(p[0] * masks.shape[2] / w, p[1] * masks.shape[1] / h, p[2]) for p in points]
        logits = whole(masks[best], [p[:2] for p in low if p[2]], [p[:2] for p in low if not p[2]])
        # the model's own values made big, then cut: a cut low mask made big came out dotted on glass (hand test)
        big = Image.fromarray(logits.astype(np.float32), "F").resize((w, h), Image.BILINEAR)
        Image.fromarray(((np.asarray(big) > 0) * 255).astype(np.uint8)).save(out_path)
        return {"mask": out_path, "score": float(scores[best]), "pick": place, "candidates": len(order)}


def whole(logits, clicks, out=()):
    """SAM's low mask (logits, > 0 = selected) as one piece: only the parts at a click (x, y in its pixels; all
    parts when no click lies on one) with their holes filled, except a hole with a "not this" click (out) in it, such
    as the gap in a mug's handle. On a glass bottle SAM was unsure and its mask a pattern of dots that left most of
    the bottle."""
    import cv2
    # one-pixel gaps closed first: the dots also lay along the outline, where filling holes does not reach
    on = cv2.morphologyEx((logits > 0).astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    _, parts = cv2.connectedComponents(on, connectivity=8)
    def at(labels, x, y):  # a click just beside the picture counts at its edge
        return int(labels[min(on.shape[0] - 1, max(0, int(y))), min(on.shape[1] - 1, max(0, int(x)))])
    hit = {at(parts, x, y) for x, y in clicks} - {0}
    keep = np.isin(parts, list(hit)) if hit else on > 0
    # holes: the parts of the rest that do not touch the border
    _, rest = cv2.connectedComponents((~keep).astype(np.uint8), connectivity=4)
    border = np.unique(np.concatenate([rest[0], rest[-1], rest[:, 0], rest[:, -1], [at(rest, x, y) for x, y in out]]))
    keep |= ~np.isin(rest, border)
    # inside: at least a little above the cut; outside: below it
    return np.where(keep, np.maximum(logits, 0.5), np.minimum(logits, -0.5))


def segment_serve(stream=None):
    """The selection process of the app (photo_tools segment): JSON lines {"id", "tool", "image", "points", "pick"}
    in, {"id", "mask", "score", "pick", "candidates"} or {"id", "error"} out. The tool stays loaded, the picture's encoding is
    kept."""
    import sys
    import tempfile
    import uuid
    src = stream or sys.stdin
    seg = None
    # in the app's data folder (with the other input pictures), so a selection survives a restart of the Mac
    data = os.environ.get("VK_DATA_DIR")
    work = os.path.join(data, "inputs", "selections") if data else tempfile.mkdtemp(prefix="vk-select-")
    os.makedirs(work, exist_ok=True)
    for line in src:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        rid = req.get("id")
        try:
            folder = os.path.realpath(req["tool"])
            if not folder.startswith(os.path.realpath(root()) + os.sep):
                raise ValueError("This photo tool is not installed")
            if seg is None or seg.folder != folder:
                seg = Segmenter(folder)
            out = os.path.join(work, "mask_%s.png" % uuid.uuid4().hex[:16])
            pick = req.get("pick")
            ans = dict(seg.select(req["image"], req.get("points") or [], out, pick if isinstance(pick, int) else None), id=rid)
        except Exception as e:
            ans = {"id": rid, "error": str(e)[:300]}
        sys.stdout.write(json.dumps(ans) + "\n")
        sys.stdout.flush()
