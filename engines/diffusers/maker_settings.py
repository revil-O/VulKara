# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""The settings a model's maker recommends, read from its model card (Hugging Face README, Civitai description).

Makers write them in many forms ("Sampling Steps: 5", "Steps: 4 (min) 6 (recommended)", "CFG Scale: 1.0-2.0",
"Sampler: DPM++ SDE Karras", "Recommended Negative Prompt: ..."). What is found becomes the model's defaults on
import: the maker knows best what the model was made for, and VulKara's own rules (turbo: 4 steps, no guidance) only
fill in what the card does not say. Nothing is guessed: a value that can not be read clearly is left out.
"""

import html
import json
import re

# the app's sampler names (src/shared/samplers.ts) and how makers write them; the longest first
SAMPLERS = [
    ("dpm++ 2m sde", "DPM++ 2M SDE"), ("dpm++2m sde", "DPM++ 2M SDE"), ("dpmpp2msde", "DPM++ 2M SDE"),
    ("dpm++ sde", "DPM++ SDE"), ("dpm++sde", "DPM++ SDE"), ("dpmppsde", "DPM++ SDE"),
    ("dpm++ 2m", "DPM++ 2M"), ("dpm++2m", "DPM++ 2M"), ("dpmpp2m", "DPM++ 2M"),
    ("euler a", "Euler a"), ("eulera", "Euler a"), ("euler ancestral", "Euler a"),
    ("euler", "Euler"), ("unipc", "UniPC"), ("heun", "Heun"), ("ddim", "DDIM"), ("lcm", "LCM"), ("tcd", "TCD"),
    ("deis", "DEIS"), ("lms", "LMS"),
]
SCHEDULES = [("karras", "Karras"), ("exponential", "Exponential"), ("beta", "Beta")]
# their diffusers schedulers take no other sigma schedule (samplers.py)
NO_SCHEDULE = {"Euler a", "DDIM", "LCM", "TCD"}

NUM = r"(\d{1,9}(?:[.,]\d{1,3})?)"  # bounded: a longer run of digits is not a number a card means


def _plain(text):
    """The card as plain lines: HTML tags and Markdown emphasis out, <br> and </p> as line breaks."""
    t = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</div>", "\n", text or "")
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"[*_`]+", "", t)
    return re.sub(r"[ \t]+", " ", t)


def _number(s):
    return float(s.replace(",", "."))


# what the maker marks as their own choice among several ("Euler A (my go-to)", "25-30 (I use 30 normally)")
PREFERRED = r"go-?to|recommended|favou?rite|best|i use|i like"


def _steps_ok(v):
    return v if 1 <= v <= 150 else None


def _steps(t):
    # "Steps: 25-30 (I use 30 normally)" -> the one the maker uses
    m = re.search(r"(?i)\bsteps?\b[^\n]{0,30}?\(\s*i use\s*" + NUM, t)
    if m and _steps_ok(int(_number(m.group(1)))):
        return int(_number(m.group(1)))
    # "minimum at 20 steps, the sweet spot is between 25-50" -> the sweet spot
    m = re.search(r"(?i)sweet spot[^\n\d]{0,20}" + NUM + r"(?:\s*(?:-|–|to|and)\s*" + NUM + r")?", t)
    if m:
        lo = _number(m.group(1))
        hi = _number(m.group(2)) if m.group(2) else lo
        if _steps_ok(int(-(-(lo + hi) // 2))):
            return int(-(-(lo + hi) // 2))
    # "Steps: 4 (min) 6 (recommended)" -> the recommended one
    m = re.search(r"(?i)\bsteps?\b[^\n\d]{0,30}" + NUM + r"[^\n]{0,30}?" + NUM + r"\s*\(?\s*recommended", t)
    if m and _steps_ok(int(_number(m.group(2)))):
        return int(_number(m.group(2)))
    # "Sampling Steps: 5" / "Steps: 4-6" (the middle, rounded up) / "4 to 8 steps"
    m = re.search(r"(?i)\b(?:sampling )?steps?\b\s*[:=]?\s*" + NUM + r"(?:\s*(?:-|–|to)\s*" + NUM + r")?", t)
    if not m:
        m = re.search(r"(?i)" + NUM + r"(?:\s*(?:-|–|to)\s*" + NUM + r")?\s+(?:sampling )?steps\b", t)
    if not m:
        return None
    lo = _number(m.group(1))
    hi = _number(m.group(2)) if m.group(2) else lo
    return _steps_ok(int(-(-(lo + hi) // 2)))


def _cfg(t):
    m = re.search(r"(?i)\b(?:cfg(?: scale)?|guidance(?: scale)?)\b[^\n]{0,30}?\(\s*i use\s*" + NUM, t)
    if m and 0 <= _number(m.group(1)) <= 30:
        return _number(m.group(1))
    m = re.search(r"(?i)\b(?:cfg(?: scale)?|guidance(?: scale)?)\b\s*[:=]?\s*" + NUM + r"(?:\s*(?:-|–|to)\s*" + NUM + r")?", t)
    if not m:
        return None
    lo = _number(m.group(1))
    hi = _number(m.group(2)) if m.group(2) else lo
    v = round((lo + hi) / 2, 2)
    return v if 0 <= v <= 30 else None


def _find(text, names):
    return next((name for key, name in names if key in text), None)


def _sampler(t):
    m = re.search(r"(?i)\b(?:sampler|sampling method|sampling(?! steps))\b\s*[:=]?\s*([^\n]{2,80})", t)
    if not m:
        return None, None, []
    line = m.group(1).lower()
    # several named ("Euler a / DPM++ 2M + Karras"): the one the maker marks as theirs, else the first
    parts = [p for p in re.split(r"\s*(?:/|\||,|\bor\b)\s*", line) if _find(p, SAMPLERS)]
    if not parts:
        return None, None, []
    part = next((p for p in parts if re.search(PREFERRED, p)), parts[0])
    sampler = _find(part, SAMPLERS)
    schedule = _find(part, SCHEDULES)
    # the samplers the maker names, without repeats: the picker is held to these (the preferred one is the default)
    allowed = list(dict.fromkeys(_find(p, SAMPLERS) for p in parts))
    if not schedule and len(parts) == 1:
        # a line of its own: "Scheduler: karras, exponential or beta" -> the first it names
        s = re.search(r"(?i)\bschedul(?:er|e)\b\s*[:=]?\s*([^\n]{2,60})", t)
        if s:
            first = re.split(r"\s*(?:/|\||,|\bor\b)\s*", s.group(1).lower())[0]
            schedule = _find(first, SCHEDULES)
    return sampler, (None if sampler in NO_SCHEDULE else schedule), allowed


# advice, not a prompt: "Start with no negative, and add afterwards the Stuff you don't wanna see" (Juggernaut XL).
# Whole phrases only: a real negative prompt may hold "you", "dont" or "start with" and must stay
ADVICE = re.compile(r"(?i)^\s*(?:none|n/?a|-)\s*\.?\s*$|\bno negative|\bstart with(?:out| no)\b|\bnot needed\b"
                    r"|\bleave (?:it )?empty\b|\bdon[\u2019\u00b4'`]t (?:wan(?:na|t)|need|use)\b")


def is_advice(text):
    return bool(ADVICE.search(text or ""))


def _negative(t):
    m = re.search(r"(?i)negative(?: prompt)?\s*[:=]\s*\n?\s*([^\n]{3,600})", t)
    if not m:
        return None
    neg = m.group(1).strip().strip('"\u201c\u201d\'')
    if is_advice(neg):
        return None
    # A1111 weights "(word:1.3)" and brackets mean nothing to the engines: the words stay
    neg = re.sub(r"\(([^():]+):\s*\d+(?:\.\d+)?\)", r"\1", neg)
    neg = re.sub(r"[()\[\]]", "", neg)
    neg = re.sub(r"\s*,\s*", ", ", neg).strip(" ,")
    return neg or None


def _code(text):
    """The values of the maker's code example (diffusers: num_inference_steps=28, guidance_scale=3.5)."""
    out = {}
    m = re.search(r"num_inference_steps\s*=\s*(\d+)\b", text or "")
    if m and 1 <= int(m.group(1)) <= 150:
        out["num_steps"] = int(m.group(1))
    m = re.search(r"\bguidance_scale\s*=\s*(\d+(?:\.\d+)?)\b", text or "")
    if m and float(m.group(1)) <= 30:
        out["guidance_scale"] = float(m.group(1))
    return out


def parse(text):
    """{num_steps, guidance_scale, sampler, sigma_schedule, negative_prompt}: only what the card says clearly; the
    card's prose first, its code example where the prose says nothing."""
    text = (text or "")[:200_000]  # a card is prose; a longer file is something else
    code = _code(text)
    t = _plain(text)
    # the generation part of the card when it has one (not the hires fix, whose steps are others)
    gen = re.split(r"(?im)^\s*#*\s*(?:hires|upscal)", t)[0]
    out = {}
    steps = _steps(gen)
    if steps:
        out["num_steps"] = steps
    cfg = _cfg(gen)
    if cfg is not None:
        out["guidance_scale"] = cfg
    sampler, schedule, allowed = _sampler(gen)
    if sampler:
        out["sampler"] = sampler
    if schedule:
        out["sigma_schedule"] = schedule
    if len(allowed) >= 1:
        out["samplers"] = allowed
    neg = _negative(t)
    if neg:
        out["negative_prompt"] = neg
    for k, v in code.items():
        out.setdefault(k, v)
    return out


def apply(manifest, settings, source):
    """The maker's settings into a model's manifest: kept as they were read, and over the guessed defaults."""
    if not settings:
        return manifest
    scalar = {k: v for k, v in settings.items() if k != "samplers"}
    manifest["maker"] = {**scalar, "source": source}
    manifest["defaults"] = {**(manifest.get("defaults") or {}), **scalar}
    if settings.get("samplers"):
        manifest["samplers"] = settings["samplers"]
    return manifest


def from_hf(repo, revision=None, token=None):
    """The settings of a Hugging Face model card; {} when there is no card or nothing clear in it."""
    try:
        from huggingface_hub import hf_hub_download
        path = hf_hub_download(repo, "README.md", revision=revision, token=token)
        with open(path, encoding="utf-8", errors="replace") as f:
            return parse(f.read())
    except Exception:
        return {}


def from_civitai(source, token=None):
    """The settings of a Civitai model by the ids its manifest keeps; {} when Civitai can not be asked."""
    try:
        import civitai
        ref = source.get("ref") or ""
        c = civitai.resolve(ref, token)
        return parse(c.get("card") or "")
    except Exception:
        return {}


def _civitai_by_hash(sha256, token=None):
    """The Civitai settings of a file imported from disk, found by its SHA256; {} when it is not on Civitai, or when
    the user did not allow telling Civitai which files are on this Mac (Settings -> Privacy: VK_HASH_LOOKUPS)."""
    import os
    if os.environ.get("VK_HASH_LOOKUPS") != "1":
        return {}
    try:
        import civitai
        v = civitai.lookup_hash(sha256, token)
        if not v or not v.get("model_id"):
            return {}
        return from_civitai({"ref": "https://civitai.com/models/%s?modelVersionId=%s" % (v["model_id"], v["version_id"])}, token)
    except Exception:
        return {}


def read(manifest, token=None, civitai_token=None):
    """(settings, source label) of an installed model by what its manifest names: the Hugging Face repo, the
    Civitai page, or for a file from disk its SHA256 on Civitai."""
    src = manifest.get("source") or {}
    if src.get("type") == "hf" and src.get("ref"):
        return from_hf(src["ref"], token=token), "hf model card"
    if src.get("type") == "civitai" and src.get("ref"):
        return from_civitai(src, civitai_token), "civitai description"
    if manifest.get("sha256"):
        return _civitai_by_hash(manifest["sha256"], civitai_token), "civitai description (found by the file's SHA256)"
    return {}, ""


def refresh(folder, token=None, civitai_token=None, dry=False):
    """Reads the maker's settings of an installed model again and writes them into its manifest (not with dry).
    Returns what was found."""
    import os
    path = os.path.join(folder, "model.json")
    with open(path) as f:
        manifest = json.load(f)
    settings, label = read(manifest, token, civitai_token)
    if settings and not dry:
        apply(manifest, settings, label)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(manifest, f, indent=1)
        os.replace(tmp, path)
    return settings


def main(argv):
    import os
    dry = "--dry" in argv
    for folder in [a for a in argv if a != "--dry"]:
        found = refresh(folder, token=os.environ.get("HF_TOKEN") or None, civitai_token=os.environ.get("CIVITAI_TOKEN") or None, dry=dry)
        print(json.dumps({"folder": folder, "maker": found}))
    return 0
