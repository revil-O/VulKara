# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""The helper models (content filter, Restore, pose and depth detection, ControlNets, upscaling) as the Models page
shows them: helpers.json lists them with their folder under the helpers folder. They are downloaded when first
needed anyway; install() fetches one ahead (Models → Installed → Helper models → Download), always at its pinned
commit and checked (pinned.py)."""
import json
import os

import paths

CATALOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "helpers.json")


def catalog():
    with open(CATALOG_FILE) as f:
        return json.load(f)["helpers"]


def folder_of(h):
    first, _, rest = h["folder"].partition("/")
    return os.path.join(str(paths.helpers_dir(first)), rest) if rest else str(paths.helpers_dir(first))


def install(helper_id, report=None, token=None):
    """Downloads one helper; returns its folder."""
    import pinned
    h = next((x for x in catalog() if x["id"] == helper_id), None)
    if h is None:
        raise ValueError("Unknown helper model: %s" % helper_id)
    folder = folder_of(h)
    token = token or os.environ.get("HF_TOKEN") or None
    say = report or (lambda message: None)
    say("Downloading %s (%d MB, one-time)" % (h["name"], h["size_mb"]))
    kind = h["kind"]
    if kind == "content":
        import content_check
        revision, digest = content_check.PINNED[h["repo"]]
        pinned.fetch(h["repo"], revision, {"config.json": None, "preprocessor_config.json": None, "model.safetensors": digest},
                     folder, report=say)
    elif kind == "lama":
        import restore
        pinned.fetch(h["repo"], restore.LAMA_PIN[0], {restore.LAMA_FILE: restore.LAMA_PIN[1]}, folder, report=say)
    elif kind == "ddcolor":
        import restore
        pinned.fetch(h["repo"], restore.COLOR_PIN[0], {restore.COLOR_FILE: restore.COLOR_PIN[1]}, folder, report=say)
    elif kind == "faces":
        import restore
        pinned.fetch_urls({f: u for f, (u, _) in restore.FACE_FILES.items()},
                          {f: d for f, (_, d) in restore.FACE_FILES.items()}, folder)
    elif kind == "preprocess":
        import preprocess
        preprocess.ensure_model(h["name_in_engine"])
    elif kind == "controlnet":
        import controlnet
        spec = next((s for s in _controlnet_specs() if s["id"] == h["id"]), None)
        if spec is None:
            raise ValueError("Unknown ControlNet: %s" % h["id"])
        controlnet.ensure_downloaded(spec, token=token)
    elif kind == "upscaler":
        pinned.fetch_pinned(h["repo"], folder, token=token, report=say)
    elif kind in ("pup", "lora"):
        pinned.fetch_pinned(h["repo"], folder, token=token, report=say)
    else:
        raise ValueError("Unknown kind of helper: %s" % kind)
    return folder


def _controlnet_specs():
    import controlnet
    specs = []
    for e in list(controlnet.MODELS.values()) + [x for fam in controlnet.EXTRA.values() for x in fam.values()]:
        specs += list(e["per_type"].values()) if "per_type" in e else [e]
    return specs
