# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Recomputes the memory figures of the recommended models (src/shared/data/curated_models.json) with the current
memory planner: min_ram_gb (Diffusers, in memory), min_ram_gb_mlx (MLX, 4 bit) and min_ram_gb_streamed (Diffusers with
the 16 bit denoiser streamed from the SSD, where that needs less). Shows the changes; writes them with --write.
Entries it has no architecture for keep their values.

    .venv/bin/python tools/update_curated_ram.py [--write]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import memory  # noqa: E402
import registry  # noqa: E402

MLX_ARCHS = ("flux1_schnell", "flux1_dev", "flux2_klein", "z_image")
CURATED = os.path.join(HERE, "..", "..", "..", "src", "shared", "data", "curated_models.json")

# id -> (arch, parameter overrides in billions, size of a pre-quantized GGUF transformer in GB)
ENTRIES = {
    "FLUX.2-klein-4B": ("flux2_klein", {"transformer": 3.9, "text_encoder": 4.0}, None),
    "FLUX.2-klein-9B": ("flux2_klein", {"transformer": 9.1, "text_encoder": 8.2}, None),
    "FLUX.1-schnell-Q4": ("flux1_schnell", None, 6.3),
    "FLUX.1-schnell-Q8": ("flux1_schnell", None, 11.8),
    "FLUX.1-dev": ("flux1_dev", None, None),
    "FLUX.1-dev-Q4": ("flux1_dev", None, 6.3),
    "Chroma1-HD": ("chroma", None, None),
    "Chroma1-Flash": ("chroma", None, None),
    "GonzaLomo-Chroma": ("chroma", None, None),
    "Z-Image-Turbo": ("z_image", None, None),
    "SD3.5-Medium": ("sd35_medium", None, None),
    "SD3.5-Large": ("sd35_large", None, None),
    "SDXL-Base-1.0": ("sdxl", None, None),
    "SDXL-Turbo": ("sdxl", None, None),
}


def figures(arch, params, fixed):
    spec = registry.ARCHS[arch]
    comps = dict(spec["fallback_params"], **(params or {}))
    den = spec["denoiser"]
    out = {"min_ram_gb": memory.plan(comps, den, spec["family"], 256, denoiser_fixed_gb=fixed)["min_ram_gb"]}
    if arch in MLX_ARCHS and fixed is None:
        # the MLX runtime quantizes everything to 4 bit quickly and keeps it loaded
        out["min_ram_gb_mlx"] = memory.plan(comps, den, spec["family"], 256, quant="q4", allow_staging=False)["min_ram_gb"]
    # the denoiser streams from the SSD in 16 bit blocks (a GGUF one unpacked into the stream cache once), with a
    # big text encoder in 4 bit as the last resort (engine.py)
    streamed = dict(comps)
    streamed[den] *= memory.stream_resident_share(spec["family"])
    need = memory.plan(streamed, den, spec["family"], 256, text_quant_opts=memory.QUANT_ORDER)["min_ram_gb"]
    if need < out["min_ram_gb"]:
        out["min_ram_gb_streamed"] = need
    return out


def main():
    with open(CURATED) as f:
        entries = json.load(f)
    changed = 0
    for e in entries:
        if e["id"] not in ENTRIES:
            continue
        new = figures(*ENTRIES[e["id"]])
        old = {k: e.get(k) for k in ("min_ram_gb", "min_ram_gb_mlx", "min_ram_gb_streamed")}
        for k in ("min_ram_gb_mlx", "min_ram_gb_streamed"):
            e.pop(k, None)
        e.update(new)
        if {k: v for k, v in old.items() if v is not None} != new:
            changed += 1
            print("%-20s %s -> %s" % (e["id"], {k: v for k, v in old.items() if v is not None}, new))
    print("%d entries changed" % changed)
    if "--write" in sys.argv and changed:
        with open(CURATED, "w") as f:
            f.write("[\n" + ",\n".join("    " + json.dumps(e, ensure_ascii=False) for e in entries) + "\n]\n")


if __name__ == "__main__":
    main()
