# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""SeedVR2-3B (ByteDance Seed, Apache-2.0) as the Upscale tool's "Detailed" variant, run by mflux on MLX. Its two files
are downloaded into the tool's variants folder at their pinned checksums on first use. 8 bit with mflux's memory saver
(1 GB cache, the transformer freed before decoding, the VAE tiled): 11.3 GB at most on a 16 GB Mac, the same picture as
without it (MEASUREMENTS 7cl)."""
import os
import tempfile
import uuid

import numpy as np

BITS = 8
SEED = 42  # one step from noise: a fixed seed makes the same photo come out the same


def target(given, factor, scale, cap):
    """The result's size: given (w, h) times factor (at most the tool's scale), made smaller to cap on the longer side
    (as the Enhance page shows it)."""
    k = min(float(factor or scale), float(scale))
    w, h = max(1, round(given[0] * k)), max(1, round(given[1] * k))
    if cap and max(w, h) > cap:
        c = cap / max(w, h)
        w, h = max(1, round(w * c)), max(1, round(h * c))
    return w, h


def weights(folder, variant_id, v, report=None, state=None, stop=None):
    """The variant's folder with its files, downloaded and checked on first use (pinned.fetch_urls)."""
    import pinned
    files = v.get("files") or {}
    if not files:
        raise ValueError("%s names no files" % v.get("label", variant_id))
    where = os.path.join(folder, "variants", variant_id)
    if state and not all(os.path.isfile(os.path.join(where, n)) for n in files):
        state("Downloading SeedVR2 (%.1f GB, one-time)" % (v.get("size_mb", 0) * 1024 ** 2 / 1e9))
    numbers = (lambda x: report(x) if isinstance(x, (int, float)) else None) if report else None
    pinned.fetch_urls({n: f["url"] for n, f in files.items()}, {n: f["sha256"] for n, f in files.items()}, where,
                      report=numbers, stop=stop)
    return where


class Stopped(Exception):
    pass


class _Watch:
    """mflux's callbacks around its one step: the job's phases, and a stop asked for between them."""

    def __init__(self, stop, state, progress):
        self.stop, self.state, self.progress = stop, state, progress

    def _check(self):
        if self.stop and self.stop():
            raise Stopped()

    def call_before_loop(self, *args, **kwargs):
        self._check()
        self.state("Upscaling (SeedVR2)")
        self.progress(-1)

    def call_in_loop(self, *args, **kwargs):
        self._check()

    def call_after_loop(self, *args, **kwargs):
        self._check()
        self.state("Decoding (SeedVR2)")
        self.progress(-1)


def run(job, images_dir, stop=None, state=None, progress=None, note=None, log=None):
    """A photo tool job with the "detailed" variant: the enlarged picture saved as PNG; returns its path, or None when
    stopped. stop: () -> bool, asked between the phases (mflux runs its one step without a break)."""
    import colour
    import photo_tools
    from PIL import Image
    state = state or (lambda s: None)
    progress = progress or (lambda p: None)
    opts = job["photo_tool"]
    folder = os.path.realpath(opts["folder"])
    if not folder.startswith(os.path.realpath(photo_tools.root()) + os.sep):
        raise ValueError("This photo tool is not installed")
    m = photo_tools.load_manifest(folder)
    variant_id = opts.get("variant")
    v = photo_tools.variants(m).get(variant_id)
    if not v or v.get("engine") != "mlx":
        raise ValueError("%s has no MLX variant %s" % (m.get("name", "This tool"), variant_id))
    if not job.get("input_image"):
        raise ValueError("Choose a picture")
    with Image.open(job["input_image"]) as head:  # the size from the header, before the pixels are read
        if head.width * head.height > photo_tools.MAX_PIXELS:
            raise ValueError("The picture is too large (at most %d megapixels)" % (photo_tools.MAX_PIXELS // 1_000_000))
    import pinned
    try:
        where = weights(folder, variant_id, v, report=progress, state=state, stop=stop)
    except pinned.Stopped:
        return None  # the downloaded part stays: the next job goes on from it
    if stop and stop():
        return None
    # upright as the app shows it, in sRGB whatever profile it carries; mflux reads a file
    rgb = np.asarray(colour.open_rgb(job["input_image"]))
    given = (rgb.shape[1], rgb.shape[0])
    w, h = target(given, opts.get("factor"), int(m.get("scale", 4)), v.get("max_output"))
    if note and (w, h) != target(given, opts.get("factor"), int(m.get("scale", 4)), None):
        note("The result is %d × %d: SeedVR2 makes at most %d pixels on the longer side" % (w, h, v["max_output"]))
    import mlx.core as mx
    from mflux.callbacks.instances.memory_saver import MemorySaver
    from mflux.models.common.config import ModelConfig
    from mflux.models.seedvr2 import SeedVR2
    state("Loading SeedVR2 (MLX, %d bit)" % BITS)
    progress(-1)
    model = None
    try:
        with tempfile.TemporaryDirectory() as work:
            src = os.path.join(work, "input.png")
            Image.fromarray(rgb).save(src)
            model = SeedVR2(quantize=BITS, model_path=where, model_config=ModelConfig.seedvr2_3b())
            model.callbacks.register(MemorySaver(model=model, keep_transformer=False))
            model.callbacks.register(_Watch(stop, state, progress))
            # mflux's resolution is the result's shorter side
            out = model.generate_image(seed=SEED, image_path=src, resolution=min(w, h), softness=0.0).image
    except Stopped:
        return None
    finally:
        del model
        import gc
        gc.collect()
        mx.clear_cache()
    out = out.convert("RGB")
    if out.size != (w, h):
        out = out.resize((w, h), Image.LANCZOS)
    picture = Image.fromarray(photo_tools.blend(rgb, np.asarray(out), float(opts.get("strength", 1.0))))
    stem = "".join(filter(str.isalnum, os.path.splitext(os.path.basename(job["input_image"]))[0][:30])) or "photo"
    path = os.path.join(str(images_dir), "%s_%s_%s.png" % (stem, m.get("task") or "upscale", uuid.uuid4().hex[:12]))
    picture.save(path)
    if log:
        log("[seedvr2] %d × %d -> %d × %d" % (given[0], given[1], w, h))
    return path
