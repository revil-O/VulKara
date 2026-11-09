# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""The denoiser in 8 or 4 bit as a GGUF file written once (Q8_0, Q4_0), loaded like an imported GGUF model.

It replaces Diffusers' Quanto backend for the denoiser, which "is deprecated and will be removed in version 1.0.0":
written once tensor by tensor, 0.4-1.3 GB less than Quanto, loaded in seconds, as fast per step at 8 bit and 3-4 %
slower at 4 bit (MEASUREMENTS 7bk). The text encoders stay with Transformers' Quanto (quant_cache).

Layout: <model_dir>/qcache/<component>-<level>.gguf and .json (the source files it was written from).
"""
import json
import os
import shutil

import protocol
import quant_cache

FORMAT = 1
GGML = {"q8": "Q8_0", "q4": "Q4_0"}
SIZE = {"q8": 34 / 32 / 2, "q4": 18 / 32 / 2}  # bytes of the file per byte of 16 bit weights (Q8_0, Q4_0 blocks)


def path(model_dir, comp, level):
    return os.path.join(model_dir, "qcache", "%s-%s.gguf" % (comp or "denoiser", level))


def sources(src, variant=None):
    """The weight files of a component folder (the shards of its index, the variant's if one is used) or the file."""
    if os.path.isfile(src):
        return [src]
    stem = "diffusion_pytorch_model"
    index = os.path.join(src, "%s.safetensors.index%s.json" % (stem, "." + variant if variant else ""))
    if os.path.isfile(index):
        with open(index) as f:
            return sorted({os.path.join(src, n) for n in json.load(f)["weight_map"].values()})
    single = os.path.join(src, "%s%s.safetensors" % (stem, "." + variant if variant else ""))
    if os.path.isfile(single):
        return [single]
    raise FileNotFoundError("No weights of %s in %s" % (stem, src))


def _key(src, level):
    return {"format": FORMAT, "level": level, "source": quant_cache._source_signature(src, None)}


def ready(model_dir, src, comp, level):
    """The GGUF file when it was written from these source files, else None (an outdated one is removed)."""
    p = path(model_dir, comp, level)
    try:
        with open(p[:-5] + ".json") as f:
            key = json.load(f)
    except (OSError, ValueError):
        return None
    if key == _key(src, level) and os.path.isfile(p):
        return p
    protocol.log("[diffusers] the %s bit copy of %s is outdated, written again" % (level[1:], comp))
    remove(model_dir, comp, level)
    return None


def remove(model_dir, comp, level):
    p = path(model_dir, comp, level)
    for f in (p, p[:-5] + ".json", p + ".tmp"):
        if os.path.exists(f):
            os.remove(f)


def short_of_room(model_dir, src, comp, level, variant=None):
    """The message when the disk has no room for the copy (its size plus the room kept free), else None."""
    need_gb = sum(os.path.getsize(f) for f in sources(src, variant)) * SIZE[level] / 1024 ** 3
    free_gb = shutil.disk_usage(model_dir).free / 1024 ** 3
    if free_gb - need_gb >= quant_cache.MIN_FREE_GB:
        return None
    return ("The %s bit copy of %s needs %.1f GB on the models disk, plus %.0f GB kept free; %.1f GB are free. Make "
            "room there and start the job again." % (level[1:], comp, need_gb, quant_cache.MIN_FREE_GB, free_gb))


def write(model_dir, src, comp, level, variant=None, progress=None):
    """Writes the GGUF file (in the quantize_once process); the Quanto caches of the component go afterwards."""
    import convert_gguf
    files = sources(src, variant)
    os.makedirs(os.path.dirname(path(model_dir, comp, level)), exist_ok=True)
    short = short_of_room(model_dir, src, comp, level, variant)
    if short:
        raise OSError(short)
    p = path(model_dir, comp, level)
    convert_gguf.convert(files, p + ".tmp", GGML[level], progress=progress)
    os.replace(p + ".tmp", p)
    with open(p[:-5] + ".json", "w") as f:
        json.dump(_key(src, level), f)
    # the component's Quanto copies (VulKara before the GGUF copies), of either bit size, are not used any more
    for old in ("q8", "q4"):
        shutil.rmtree(quant_cache.cache_dir(model_dir, comp, old), ignore_errors=True)
    return p
