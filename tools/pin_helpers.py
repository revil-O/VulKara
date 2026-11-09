# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Pins of the helper models the engines download on first use (ControlNets, pose and depth detection, the upscaling
model): the repository's current commit and the SHA-256 of every weight file, written to
engines/diffusers/helper_pins.json. Run it when a helper is added or deliberately updated, then review the change:

    python3 tools/pin_helpers.py
"""
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engines", "diffusers"))
OUT = os.path.join(ROOT, "engines", "diffusers", "helper_pins.json")


def wanted():
    """{repo: [remote file names]} from the engines' own lists."""
    import controlnet
    import preprocess
    out = {}
    specs = []
    for e in list(controlnet.MODELS.values()) + [x for fam in controlnet.EXTRA.values() for x in fam.values()]:
        specs += list(e["per_type"].values()) if "per_type" in e else [e]
    for s in specs:
        out.setdefault(s["repo"], []).extend(s.get("remote_files") or s["files"])
    for m in preprocess.MODELS.values():
        out.setdefault(m["repo"], []).extend(m["files"])
    out["Comfy-Org/Real-ESRGAN_repackaged"] = ["RealESRGAN_x4plus.safetensors"]
    out["lrzjason/Consistance_Edit_Lora"] = ["f2k_4B_consist_20260314.safetensors"]
    return out


def info(repo):
    req = urllib.request.Request("https://huggingface.co/api/models/%s?blobs=true" % repo, headers={"User-Agent": "vulkara-pins"})
    token = os.environ.get("HF_TOKEN")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def main():
    pins = {}
    for repo, files in sorted(wanted().items()):
        d = info(repo)
        sib = {s["rfilename"]: s for s in d.get("siblings", [])}
        entry = {"revision": d["sha"], "files": {}}
        for f in sorted(set(files)):
            if f not in sib:
                raise SystemExit("%s has no %s" % (repo, f))
            # weight files are checked by their SHA-256; small text files are fixed by the commit
            entry["files"][f] = (sib[f].get("lfs") or {}).get("sha256")
        pins[repo] = entry
        print(repo, d["sha"][:12], len(entry["files"]))
    with open(OUT, "w") as fh:
        json.dump(pins, fh, indent=1, sort_keys=True)
        fh.write("\n")


if __name__ == "__main__":
    main()
