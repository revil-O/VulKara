# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""This Mac and what the engines do on it: chip, GPU, RAM, number format, and per model family the
mode (quantization, text encoder staging, runtime) and resolution the memory plan picks.

    python main.py hardware              JSON for the Settings page
    python main.py hardware --tiers      Markdown table for the RAM tiers 16/24/32/48/64/128 GB
"""
import json
import re
import subprocess
import sys

import memory

# model families as the app offers them (sizes in billion parameters, as in registry.ARCHS)
MODELS = [
    {"id": "sdxl", "title": "SDXL", "family": "sdxl", "denoiser": "unet",
     "components": {"unet": 2.57, "text_encoder": 0.12, "text_encoder_2": 0.69, "vae": 0.08}},
    {"id": "sd35_medium", "title": "SD 3.5 Medium", "family": "sd3", "denoiser": "transformer",
     "components": {"transformer": 2.47, "text_encoder": 0.12, "text_encoder_2": 0.69, "text_encoder_3": 4.76, "vae": 0.08}},
    {"id": "sd35_large", "title": "SD 3.5 Large", "family": "sd3", "denoiser": "transformer",
     "components": {"transformer": 8.06, "text_encoder": 0.12, "text_encoder_2": 0.69, "text_encoder_3": 4.76, "vae": 0.08}},
    {"id": "flux1", "title": "FLUX.1 [dev] / [schnell]", "family": "flux1", "denoiser": "transformer", "mlx": True,
     "components": {"transformer": 11.9, "text_encoder": 0.12, "text_encoder_2": 4.76, "vae": 0.08}},
    {"id": "flux2_klein_4b", "title": "FLUX.2 [klein] 4B", "family": "flux2", "denoiser": "transformer", "mlx": True,
     "components": {"transformer": 4.0, "text_encoder": 4.0, "vae": 0.08}},
    {"id": "flux2_klein_9b", "title": "FLUX.2 [klein] 9B", "family": "flux2", "denoiser": "transformer", "mlx": True,
     "components": {"transformer": 9.1, "text_encoder": 8.2, "vae": 0.08}},
    {"id": "z_image", "title": "Z-Image", "family": "z_image", "denoiser": "transformer", "mlx": True,
     "components": {"transformer": 6.15, "text_encoder": 4.02, "vae": 0.08}},
    {"id": "flux2_dev", "title": "FLUX.2 [dev]", "family": "flux2", "denoiser": "transformer", "mlx": True,
     "components": {"transformer": 32.2, "text_encoder": 24.0, "vae": 0.08}},
    {"id": "krea2", "title": "Krea 2", "family": "krea2", "denoiser": "transformer", "mlx": True, "mlx_only": True,
     "mlx_staged": True, "components": {"transformer": 13.1, "text_encoder": 4.4, "vae": 0.13}},
    {"id": "ideogram4", "title": "Ideogram 4", "family": "ideogram4", "denoiser": "transformer", "mlx": True,
     "mlx_only": True, "mlx_staged": True,
     "components": {"transformer": 9.28, "unconditional_transformer": 9.28, "text_encoder": 8.2, "vae": 0.08}},
]
SIDES = [1024, 768, 512]
QUANT_TEXT = {"none": "16 bit", "q8": "8 bit", "q4": "4 bit", "gguf": "GGUF"}


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def hardware():
    chip = _run(["sysctl", "-n", "machdep.cpu.brand_string"]) or "unknown"
    m = re.search(r"\bM(\d+)", chip)
    gen = int(m.group(1)) if m else None
    cores = re.search(r'"gpu-core-count" = (\d+)', _run(["ioreg", "-rc", "AGXAccelerator"]))
    perf = _run(["sysctl", "-n", "hw.perflevel0.physicalcpu"])
    eff = _run(["sysctl", "-n", "hw.perflevel1.physicalcpu"])
    return {
        "chip": chip, "generation": gen,
        "gpu_cores": int(cores.group(1)) if cores else None,
        "cpu_cores": "%s performance + %s efficiency" % (perf, eff) if perf and eff else None,
        "ram_gb": round(memory.total_ram_gb()),
        # M1/M2 have no bfloat16 in hardware: the engines compute in float16 where it is safe
        "bf16_native": gen is not None and gen >= 3,
        # M5: matrix units in the GPU cores (used once PyTorch / MLX support them)
        "neural_accelerators": gen is not None and gen >= 5,
    }


def _describe(p):
    parts = []
    quants = p["quant"]
    den = [q for c, q in quants.items() if not c.startswith("text_encoder")]
    tes = [q for c, q in quants.items() if c.startswith("text_encoder")]
    parts.append("model " + QUANT_TEXT.get(den[0], den[0]) if den else "model 16 bit")
    if tes:
        parts.append("text encoder " + QUANT_TEXT.get(tes[0], tes[0]))
    if p.get("releases_denoiser"):
        parts.append("text encoder and model one after the other for each new prompt")
    elif p.get("staged_text_encoder"):
        parts.append("text encoder loaded per prompt")
    return ", ".join(parts)


def _best_side(model, ram_gb, planner):
    """largest square size whose activations fit next to the weights"""
    act = memory.ACTIVATIONS_GB.get(model["family"], 2.5)
    for side in SIDES:
        p = planner(act * (side / 1024) ** 2)
        if p["fits"]:
            return side, p
    return None, planner(act * (SIDES[-1] / 1024) ** 2)


def _mlx_plan(model, ram_gb, act):
    """as the MLX engine picks it (engines/mlx/main.py, choose_quant): least quantization
    that fits, everything resident except for staged models (Krea 2, Ideogram 4: the text encoder is freed after
    encoding); Krea 2 first tries its text encoder in 16 bit"""
    if model["family"] == "krea2":
        for bits, level in ((None, "none"), (8, "q8"), (4, "q4")):
            scaled = {c: (v * memory.BYTES_PER_PARAM["none"] / memory.BYTES_PER_PARAM[level] if c.startswith("text_encoder") else v)
                      for c, v in model["components"].items()}
            p = memory.plan(scaled, model["denoiser"], model["family"], ram_gb, quant=level,
                            allow_staging=False, activations_gb=act)
            if p["fits"]:
                p["bits"], p["te_bits"] = bits, None
                return p
    for bits, level in ((None, "none"), (8, "q8"), (4, "q4")):
        p = memory.plan(model["components"], model["denoiser"], model["family"], ram_gb, quant=level,
                        allow_staging=bool(model.get("mlx_staged")), activations_gb=act)
        if p["fits"]:
            p["bits"], p["te_bits"] = bits, bits
            return p
    p["bits"], p["te_bits"] = 4, 4
    return p


def _mlx_mode(p):
    bits = lambda b: "16 bit" if b is None else "%d bit" % b  # noqa: E731
    mode = "model " + bits(p["bits"])
    if p.get("te_bits") != p["bits"]:
        mode += ", text encoder " + bits(p.get("te_bits"))
    if p.get("staged_text_encoder"):
        mode += ", text encoder only for new prompts"
    return mode


def recommendations(ram_gb, bf16_native=True):
    out = []
    for model in MODELS:
        row = {"id": model["id"], "title": model["title"]}
        if not model.get("mlx_only"):
            side, p = _best_side(model, ram_gb, lambda act: memory.fitting_plan(
                model["components"], model["denoiser"], model["family"], ram_gb, activations_gb=act))
            row["diffusers"] = {"fits": side is not None, "side": side, "mode": _describe(p),
                                "min_ram_gb": p["min_ram_gb"],
                                "float16": model["family"] == "flux1" and not bf16_native}
            if side is None:
                # emergency mode of the engine: the denoiser's blocks come from the SSD (engine.py)
                comps = dict(model["components"])
                comps[model["denoiser"]] *= memory.stream_resident_share(model["family"])
                sp = memory.plan(comps, model["denoiser"], model["family"], ram_gb)
                if not sp["fits"]:
                    # as the engine: a big text encoder in 4 bit as the last resort
                    sp = memory.plan(comps, model["denoiser"], model["family"], ram_gb, text_quant_opts=memory.QUANT_ORDER)
                if sp["fits"]:
                    tes = [q for c, q in sp["quant"].items() if c.startswith("text_encoder")]
                    mode = "model 16 bit streamed from the SSD (slow)"
                    if tes:
                        mode += ", text encoder " + QUANT_TEXT.get(tes[0], tes[0])
                    row["diffusers"].update({"fits": True, "side": 1024, "mode": mode, "streamed": True})
        if model.get("mlx"):
            side, p = _best_side(model, ram_gb, lambda act: _mlx_plan(model, ram_gb, act))
            row["mlx"] = {"fits": side is not None, "side": side,
                          "mode": _mlx_mode(p),
                          "min_ram_gb": p["min_ram_gb"],
                          "float16": model["family"] == "flux2" and not bf16_native}
        row["why"] = _why(row, model)
        out.append(row)
    return out


def _why(row, model):
    d, x = row.get("diffusers"), row.get("mlx")
    if model.get("mlx_only"):
        return "MLX only" if x["fits"] else "needs about %d GB RAM" % x["min_ram_gb"]
    if d["fits"] and d.get("streamed"):
        return ("MLX fits; Diffusers only streamed from the SSD" if x and x["fits"] else
                "too big for memory: Diffusers streams it block by block from the SSD (slow)")
    if d["fits"] and x and x["fits"] and "per prompt" in d["mode"]:
        return "MLX keeps the text encoder loaded (Diffusers reloads it per new prompt)"
    if d["fits"] and x and x["fits"]:
        return "both fit; MLX for folder models, Diffusers for single files, Img2Img and ControlNet"
    if x and x["fits"]:
        return "only MLX fits (4/8 bit quantized while loading)"
    if d["fits"]:
        return "fits with Diffusers"
    return "needs about %d GB RAM" % min(v["min_ram_gb"] for v in (d, x) if v)


def profile():
    hw = hardware()
    return {"hardware": hw, "models": recommendations(hw["ram_gb"], hw["bf16_native"]),
            "reserve_gb": round(hw["ram_gb"] - memory.budget_gb(hw["ram_gb"]), 1)}


def tiers_markdown(tiers=(16, 24, 32, 48, 64, 128)):
    """What the planner picks per RAM tier (bfloat16 chip; M1/M2 compute FLUX in float16)."""
    lines = ["| Model | " + " | ".join("%d GB" % t for t in tiers) + " |",
             "|---|" + "---|" * len(tiers)]
    for model in MODELS:
        cells = []
        for t in tiers:
            row = [r for r in recommendations(t) if r["id"] == model["id"]][0]
            parts = []
            for name, key in (("Diffusers", "diffusers"), ("MLX", "mlx")):
                v = row.get(key)
                if v and v["fits"]:
                    parts.append("%s: %s, %d px" % (name, v["mode"].replace("model ", "").replace("text encoder", "TE"), v["side"]))
            cells.append("<br>".join(parts) or "–")
        lines.append("| %s | %s |" % (model["title"], " | ".join(cells)))
    return "\n".join(lines)


def main(argv):
    if "--tiers" in argv:
        print(tiers_markdown())
    else:
        print("__profile__ " + json.dumps(profile()), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
