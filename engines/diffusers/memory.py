# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Chooses per-component quantization so a model fits into the machine's RAM.

Apple Silicon has unified memory, so "fits" means: the weights that are resident
at the same time plus activations stay below a share of total RAM. When the text
encoders are "staged" they are only loaded to encode a new prompt and freed before
denoising. The denoiser stays loaded meanwhile (reloading it per prompt would cost far
more time), so during encoding both are resident, just without the activations.
"""
# macOS and the app itself need a reserve; on small Macs it is a fixed amount, on big ones a share
RESERVE_FRACTION = 0.2
MIN_RESERVE_GB = 4.0
RUNTIME_OVERHEAD_GB = 1.0  # python + torch + app
# SD 1.5 at 1024 px measured 1.9 GB over its weights with fused attention (docs/MEASUREMENTS.md 7n)
ACTIVATIONS_GB = {"sd1": 1.9, "sd2": 1.0, "sdxl": 1.5, "sd3": 2.0, "flux1": 2.5, "flux2": 3.0, "flux3": 2.5, "krea2": 3.0, "ideogram4": 2.5,
                  "chroma": 2.5,  # FLUX.1's blocks; the guided and the unguided pass run one after the other
                  # Z-Image at 1024 px (4096 image + up to 512 caption tokens, 3840 wide); with guidance (Base)
                  # both passes run as one batch
                  "z_image": 3.0,
                  "wan": 4.0,  # wan (video): decoding all frames dominates
                  # Qwen-Image at its native 1328 px (6900 image tokens); 2.1 at 1024 px with its text cache
                  # 2.1: 10.5 GB with its transformer in 8 bit in stages (7z), 12.1 GB streamed (7w)
                  "qwen_image": 3.5, "qwen_image21": 2.8}
# families made for a smaller picture: whether they fit is judged at their own size, not at 1024²
NATIVE_SIDE = {"sd1": 512, "sd2": 768}
# further denoisers that run next to the main one and get its precision (Ideogram 4 denoises with a
# conditional and an unconditional transformer)
SECOND_DENOISERS = ("unconditional_transformer",)
# share of a streamed denoiser counted as resident while denoising: the rest of the model and the blocks in flight (on
# the GPU up to three, streaming.QUEUED waiting and the one loading, and two read ahead). 15 % holds for models of many
# small blocks (Qwen-Image 2.1, MEASUREMENTS 7w); a FLUX.2 double block is 4.8 % of the model, five of them in flight
# 27 % (klein 9B: 14.3 GB with 15 %, planned 12 GB, 7ac)
STREAM_RESIDENT_SHARE = {"flux2": 0.27}


def stream_resident_share(family):
    return STREAM_RESIDENT_SHARE.get(family, 0.15)

BYTES_PER_PARAM = {"none": 2.0, "q8": 1.05, "q4": 0.6}
QUANT_ORDER = ["none", "q8", "q4"]  # best quality first
# what "auto" may pick for on-the-fly quantization (optimum-quanto): packing 4 bit weights runs
# on the CPU and takes 10+ minutes for an 8B model, so 4 bit comes from GGUF files or MLX instead
AUTO_ORDER = ["none", "q8"]

# components smaller than this stay in 16 bit, quantizing them saves nothing
MIN_QUANT_PARAMS_B = 1.0


def total_ram_gb():
    import psutil
    return psutil.virtual_memory().total / 1024 ** 3


def _reserve_override():
    import os
    try:
        return float(os.environ.get("VK_MEMORY_RESERVE_GB") or 0)
    except ValueError:
        return 0.0


def budget_gb(ram_gb):
    reserve = _reserve_override() or max(MIN_RESERVE_GB, ram_gb * RESERVE_FRACTION)
    return ram_gb - reserve


def ram_needed_gb(peak_gb):
    """Inverse of budget_gb: the smallest RAM whose budget holds peak_gb."""
    if _reserve_override():
        return peak_gb + _reserve_override()
    return max(peak_gb + MIN_RESERVE_GB, peak_gb / (1 - RESERVE_FRACTION))


def _scale(side_or_pixels):
    return max(0.25, side_or_pixels / (1024 * 1024))


def activations_at(plan, width, height):
    """(the activations a plan counts, those at a picture size): they grow and shrink with the pixels, not below a
    quarter of 1024²'s; a plan's are for its activations_side (1024 in older plans)."""
    act = plan.get("activations_gb", 2.5)
    side = plan.get("activations_side", 1024)
    return act, act / _scale(side * side) * _scale(width * height)


def peak_at(plan, width, height):
    """A plan's peak for a picture size; a staged plan's encoding peak does not change with the size."""
    act, at = activations_at(plan, width, height)
    denoise = plan["denoise_peak_gb"] - act + at
    encoding = plan["est_peak_gb"] if plan["est_peak_gb"] > plan["denoise_peak_gb"] else 0
    return max(encoding, denoise)


def free_gb(held_gb=0.0):
    """What a job can use now: what macOS has available, plus what the engine itself already holds (held_gb)."""
    import psutil
    return psutil.virtual_memory().available / 1024 ** 3 + held_gb


def short_of(need_gb, held_gb, total_gb=None):
    """None when a job's planned peak fits into the memory free now, else a note for the job: other programs (or
    another engine) hold what is missing, and the picture will swap."""
    free = free_gb(held_gb)
    if need_gb <= free:
        return None
    others = (total_gb or total_ram_gb()) - free
    return ("Only %.1f GB of memory free for the planned %.1f GB (other programs or engines hold %.1f GB): this picture may be "
            "slow, macOS moves memory to the swap" % (free, need_gb, others))


def _is_text_encoder(name):
    return name.startswith("text_encoder")


def _gb(params_b, quant):
    return params_b * BYTES_PER_PARAM[quant]


def plan(components, denoiser, family, ram_gb, quant="auto", denoiser_fixed_gb=None, allow_staging=True,
         activations_gb=None, text_quant_opts=None, staging_frees_denoiser=False):
    """
    components:  {component_name: params_in_billion}
    denoiser:    name of the denoiser component ("unet" / "transformer")
    denoiser_fixed_gb: size of a pre-quantized denoiser (GGUF), its quant is not ours to choose
    quant:       "auto" or a forced level for all quantizable components
    activations_gb: activations at another resolution than 1024² (default: the family's value)
    text_quant_opts: what "auto" may pick for big text encoders (default AUTO_ORDER; SSD streaming's last resort
                     also allows 4 bit)
    staging_frees_denoiser: staged, the prompt is encoded while the denoiser is not loaded (FLUX 3 on MLX), so the
                     text encoder and the denoiser are never in memory together

    Returns a dict with quant per component, staged flag, peak estimate, fit and min RAM.
    """
    budget = budget_gb(ram_gb)
    side = NATIVE_SIDE.get(family, 1024) if activations_gb is None else 1024
    act = ACTIVATIONS_GB.get(family, 2.5) * _scale(side * side) if activations_gb is None else activations_gb
    extra = RUNTIME_OVERHEAD_GB + act

    big_te = [n for n, p in components.items() if _is_text_encoder(n) and p >= MIN_QUANT_PARAMS_B]
    seconds = [n for n in components if n in SECOND_DENOISERS and n != denoiser]
    small = {n: p for n, p in components.items() if n != denoiser and n not in big_te and n not in seconds}
    small_te_gb = sum(_gb(p, "none") for n, p in small.items() if _is_text_encoder(n))
    other_gb = sum(_gb(p, "none") for n, p in small.items() if not _is_text_encoder(n))  # vae etc.

    if denoiser_fixed_gb is not None:
        denoiser_opts = ["gguf"]
    elif quant == "auto":
        denoiser_opts = AUTO_ORDER
    else:
        denoiser_opts = [quant]
    te_opts = (text_quant_opts or AUTO_ORDER) if quant == "auto" else [quant]

    def seconds_gb(dq):
        return sum(_gb(components[n], "q8" if dq == "gguf" else dq) for n in seconds)

    def denoiser_gb(dq):
        main = denoiser_fixed_gb if dq == "gguf" else _gb(components[denoiser], dq)
        return main + seconds_gb(dq)

    def denoise_peak(dq, tq, staged):
        den_gb = denoiser_gb(dq)
        te_gb = 0 if staged else small_te_gb + sum(_gb(components[n], tq) for n in big_te)
        return te_gb + den_gb + other_gb + extra

    def evaluate(dq, tq, staged):
        den_gb = denoiser_gb(dq)
        te_gb = small_te_gb + sum(_gb(components[n], tq) for n in big_te)
        if staged:
            # freeing the denoiser leaves a second one (Ideogram 4's unconditional transformer) loaded
            encoding = te_gb + seconds_gb(dq) + other_gb + RUNTIME_OVERHEAD_GB if staging_frees_denoiser else \
                te_gb + den_gb + other_gb + RUNTIME_OVERHEAD_GB
            return max(encoding, denoise_peak(dq, tq, staged))
        return denoise_peak(dq, tq, staged)

    candidates = []
    # the denoiser's precision matters most for image quality; an 8 bit text encoder is
    # nearly lossless, staging costs a few seconds per new prompt, 4 bit text encoders hurt most
    for di, dq in enumerate(denoiser_opts):
        for ti, tq in enumerate(te_opts if big_te else ["none"]):
            for staged in ((False, True) if allow_staging else (False,)):
                candidates.append((di, ti, staged, dq, tq))
    te_cost = {"none": 0, "q8": 1, "q4": 3}
    candidates.sort(key=lambda c: c[0] * 10 + te_cost[c[4]] + (2 if c[2] else 0))

    best = None
    for _, _, staged, dq, tq in candidates:
        peak = evaluate(dq, tq, staged)
        if peak <= budget:
            best = (dq, tq, staged, peak)
            break

    smallest = min(evaluate(dq, tq, staged) for _, _, staged, dq, tq in candidates)
    min_ram_gb = int(ram_needed_gb(smallest) + 0.999)

    if best is None:
        dq, tq, staged = denoiser_opts[-1], (te_opts[-1] if big_te else "none"), True
        fits, peak = False, smallest
    else:
        dq, tq, staged, peak = best
        fits = True

    quant_map = {denoiser: dq}
    for n in seconds:
        quant_map[n] = dq
    for n in big_te:
        quant_map[n] = tq
    return {
        "fits": fits,
        "quant": quant_map,
        "staged_text_encoder": staged and bool(big_te or small_te_gb),
        "est_peak_gb": round(peak, 1),
        # while denoising (what an extra model such as a ControlNet adds to)
        "denoise_peak_gb": round(denoise_peak(dq, tq, staged and bool(big_te or small_te_gb)), 1),
        # text encoders as planned (resident unless staged)
        "text_gb": round(small_te_gb + sum(_gb(components[n], tq) for n in big_te), 1),
        "activations_gb": act,
        "activations_side": side,
        "budget_gb": round(budget, 1),
        "min_ram_gb": min_ram_gb,
        "ram_gb": round(ram_gb, 1),
    }


def fitting_plan(components, denoiser, family, ram_gb, quant="auto", denoiser_fixed_gb=None, activations_gb=None):
    """The plan without SSD streaming: plan(), and where that does not fit, a big text encoder may go to 4 bit, then
    the denoiser may make room while a new prompt is encoded ("releases_denoiser": it is loaded again afterwards, a
    prompt from the prompt cache needs neither). Streaming the denoiser is the engine's last resort."""
    p = plan(components, denoiser, family, ram_gb, quant=quant, denoiser_fixed_gb=denoiser_fixed_gb,
             activations_gb=activations_gb)
    if p["fits"]:
        return p
    for frees in (False, True):
        q = plan(components, denoiser, family, ram_gb, quant=quant, denoiser_fixed_gb=denoiser_fixed_gb,
                 activations_gb=activations_gb, text_quant_opts=QUANT_ORDER, staging_frees_denoiser=frees)
        if q["fits"]:
            q["releases_denoiser"] = frees and q["staged_text_encoder"]
            return q
    return p
