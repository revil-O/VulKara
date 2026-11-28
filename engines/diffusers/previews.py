# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Preview pictures of imported models and LoRAs (<folder>/preview.jpg).

    from the source   Civitai: a sample image of the version (the most harmless one first);
                      Hugging Face: an image file of the repo (grid / example / preview …)
    generated         the model itself paints a random scene (engine request "preview")

    python main.py previews [<models folder> …]   fetches missing previews from the sources
"""
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

import paths

SIZE = 384
FILE = "preview.jpg"
MAX_DOWNLOAD = 50 * 1024 * 1024  # a sample picture, not a file of any size
# models paint a random scene of these (with a random seed), so the pictures differ
SCENES = [
    "a lighthouse on a rocky coast during a storm, crashing waves",
    "a busy night market in a rainy asian city, neon signs, reflections",
    "an astronaut exploring an alien jungle with glowing plants",
    "a portrait of an old fisherman with a weathered face, soft window light",
    "a steampunk airship above the clouds at sunset",
    "a red fox in a snowy forest, morning light",
    "a cozy library with tall bookshelves and a reading cat",
    "a futuristic city skyline with flying cars at dusk",
    "a medieval castle on a cliff above a misty valley",
    "a bowl of ramen on a wooden table, steam, close-up food photo",
    "a coral reef with colorful fish and sun rays under water",
    "a vintage red sports car on a coastal road",
    "a dragon perched on a mountain peak, epic fantasy",
    "a ballet dancer bowing on a stage, spotlight",
    "a field of sunflowers under a dramatic summer sky",
    "a samurai standing in a bamboo forest, falling leaves",
    "a cup of coffee and a croissant in a parisian cafe",
    "a desert oasis with palm trees and a caravan of camels",
    "an owl in a moonlit forest, detailed feathers",
    "a colorful hot air balloon festival over a valley",
    "a robot gardener tending flowers in a greenhouse",
    "a waterfall in a lush tropical rainforest",
]


def random_scene():
    import random
    return random.choice(SCENES) + ", highly detailed"


# tags of the training data that say nothing about what a LoRA does
_GENERIC_TAGS = {"solo", "looking at viewer", "1girl", "1boy", "simple background", "white background",
                 "no humans", "highres", "absurdres", "masterpiece", "best quality", ""}
# words in a LoRA's name -> how its picture is painted ({} is a random scene)
_NAME_HINTS = [
    (r"tatt?oo|t4tt00", "a black and white tattoo design of {}, ink line art on white paper"),
    (r"pixel", "pixel art of {}"),
    (r"anime|manga", "an anime illustration of {}"),
    (r"paint", "a digital painting of {}"),
    (r"sketch|drawing|lineart", "a pencil drawing of {}"),
    (r"watercolou?r", "a watercolor painting of {}"),
    (r"photo", "a photograph of {}"),
]
_SUBJECTS = ["a wolf howling at the moon", "a rose with thorns", "a koi fish", "an owl", "a lion's head",
             "a dragon", "a ship in a storm", "a snake around a dagger", "a phoenix", "a skull with flowers"]


def _training_captions(lora_file):
    """(captions, tags) of the LoRA's training data from the kohya metadata (ss_tag_frequency)."""
    import registry
    try:
        meta = registry.read_safetensors_metadata(lora_file)
        counts = {}
        for d in json.loads(meta.get("ss_tag_frequency") or "{}").values():
            for t, c in d.items():
                counts[t.strip()] = counts.get(t.strip(), 0) + c
    except Exception:
        return [], []
    ranked = [t for t, _ in sorted(counts.items(), key=lambda x: -x[1])]
    # kohya splits captions at commas: whole captions start like most of them do ("t4tt00 …", "a …")
    captions = [t for t in ranked if len(t.split()) >= 6]
    firsts = [c.split()[0].lower() for c in captions]
    usual = max(set(firsts), key=firsts.count) if firsts else None
    captions = [c for c in captions if c.split()[0].lower() == usual]
    # single tags that are used more than once (not caption fragments)
    tags = [t for t in ranked if t.lower() not in _GENERIC_TAGS and (counts[t] > 1 or len(counts) < 4)
            and len(t.split()) <= 3]
    return captions, tags


def lora_prompt(lora_dir):
    """A prompt that shows what the LoRA does: one of its training captions, else its main training
    tags, else hints from its name; always with its trigger words."""
    import random
    with open(os.path.join(lora_dir, "lora.json")) as f:
        m = json.load(f)
    captions, tags = _training_captions(os.path.join(lora_dir, m.get("file") or "lora.safetensors"))
    triggers = [t for t in m.get("trigger_words") or [] if t]
    name = (m.get("name") or os.path.basename(lora_dir)).lower()
    if captions:
        # objects and scenes first: the picture stands in the model list (captions of people undressed)
        plain = [c for c in captions if not re.search(r"\b(woman|man|girl|boy|person|body|back|chest|breast|arm)\b", c, re.I)]
        caption = random.choice((plain or captions)[:20])
        short = tags[:3]
        style = ["tattoo design"] if re.search(r"tatt?oo", name) and "tattoo" not in " ".join([caption] + short) else []
        prompt = ", ".join([caption] + short + style)
    elif len(tags) >= 4:
        prompt = ", ".join(tags[:12])
    else:
        hint = next((h for pat, h in _NAME_HINTS if re.search(pat, name)), "{}")
        subject = random.choice(_SUBJECTS) if "tattoo" in hint else random.choice(SCENES)
        prompt = ("fantasy " if "fantasy" in name else "") + hint.format(subject) + ", highly detailed"
        triggers += [t for t in tags if t not in triggers][:2]  # a lone tag is the trigger word
    missing = [t for t in triggers if t.lower() not in prompt.lower()]
    return ", ".join(missing + [prompt])


def paint(generate, job):
    """The model of job["model_dir"] paints a random scene with generate(d) -> [paths].

    job["loras"] (optional) puts LoRAs on the model; the picture then belongs to job["target"]
    (the LoRA's folder, painted with a prompt that shows what the LoRA does), else to the model.
    Returns the saved preview path."""
    model_dir = job["model_dir"]
    target = job.get("target") or model_dir
    with open(os.path.join(model_dir, "model.json")) as f:
        defaults = json.load(f).get("defaults") or {}
    side = min(768, defaults.get("width", 1024))
    is_lora = os.path.abspath(target) != os.path.abspath(model_dir) and os.path.isfile(os.path.join(target, "lora.json"))
    if not is_lora and not os.path.isfile(os.path.join(target, "model.json")):
        # the picture is only ever written into a model's or a LoRA's own folder
        raise ValueError("Not a model or LoRA folder: %s" % target)
    paths = generate({"prompt": lora_prompt(target) if is_lora else random_scene(),
                      "negative_prompt": "blurry, low quality, watermark, nude, nudity, nsfw, deformed, bad anatomy, "
                                         "extra limbs, extra legs, extra arms, extra fingers" + ("" if is_lora else ", text"),
                      "model_dir": model_dir, "width": side, "height": side, "seed": -1,
                      "num_steps": min(20, defaults.get("num_steps", 20)), "loras": job.get("loras") or [],
                      "_quiet": True})
    with open(paths[0], "rb") as f:
        out = _save(f.read(), target)
    os.remove(paths[0])
    _mark(target, "generated")
    return out


def _save(data, folder, name=FILE):
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGB")
    s = SIZE / min(im.size)
    im = im.resize((max(SIZE, round(im.width * s)), max(SIZE, round(im.height * s))), Image.LANCZOS)
    left, top = (im.width - SIZE) // 2, (im.height - SIZE) // 2
    os.makedirs(folder, exist_ok=True)
    im.crop((left, top, left + SIZE, top + SIZE)).save(os.path.join(folder, name), quality=85, optimize=True)
    return os.path.join(folder, name)


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    """A redirect may not leave https."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme != "https":
            raise ValueError("The picture moved to a plain http address")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _get(url):
    """A picture from the web; https only (the URLs come from Civitai's answers)."""
    if urllib.parse.urlparse(url or "").scheme != "https":
        raise ValueError("Not an https address: %s" % str(url)[:100])
    opener = urllib.request.build_opener(_HttpsOnly)
    with opener.open(urllib.request.Request(url, headers={"User-Agent": "VulKara"}), timeout=30) as r:
        data = r.read(MAX_DOWNLOAD + 1)
    if len(data) > MAX_DOWNLOAD:
        raise ValueError("The picture is larger than %d MB" % (MAX_DOWNLOAD // 1024 ** 2))
    return data


def civitai_image(images):
    """URL of the most harmless sample image, as a small version (Civitai resizes on the fly)."""
    if os.environ.get("VK_SAFE_MODE") == "1":
        # Civitai's levels: 1 PG, 2 PG-13, 4 R, 8 X, 16 XXX; in safe mode no preview rather than an explicit one
        images = [i for i in images or [] if (i.get("nsfw_level") or 0) <= 2]
    if not images:
        return None
    best = sorted(images, key=lambda i: i.get("nsfw_level") or 0)[0]["url"]
    return re.sub(r"/width=\d+/", "/width=512/", best) if "/width=" in best else best


_HF_NAMES = ("grid", "preview", "example", "sample", "showcase", "demo", "cover", "thumbnail", "banner")


def hf_image(repo, token=None):
    """Path of a picture in a Hugging Face repo, preferring names like grid / example / preview."""
    from huggingface_hub import HfApi
    files = [f for f in HfApi(token=token).list_repo_files(repo) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
    if not files:
        return None
    def score(f):
        name = f.lower()
        return (not any(k in name for k in _HF_NAMES), f.count("/"), len(f))
    return sorted(files, key=score)[0]


# pictures of a model card are taken only from Hugging Face itself, never from another server the card links to
_CARD_HOSTS = ("huggingface.co", "cdn-uploads.huggingface.co")
_CARD_PICTURE = re.compile(r'!\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+"[^"]*")?\s*\)|<img\b[^>]*?\bsrc\s*=\s*["\']([^"\']+)["\']', re.I)


def _card_url(repo, raw):
    """A picture link of a model card as a browser would follow it, if it lies on Hugging Face; else None."""
    base = "https://huggingface.co/%s/resolve/main/" % repo
    u = urllib.parse.urlparse(raw)
    if not u.scheme:
        u = urllib.parse.urlparse(urllib.parse.urljoin(base, raw))  # relative, from the site root, or //host/…
    if u.hostname not in _CARD_HOSTS or u.scheme not in ("https", "http"):
        return None  # data:, mailto:, another server
    path = u.path
    if u.hostname == "huggingface.co":
        path = path.replace("/blob/", "/resolve/", 1)  # the page about a file -> the file itself
    if path.lower().endswith(".svg"):
        return None
    return urllib.parse.urlunparse(("https", u.netloc, path, "", u.query, ""))


def hf_card_images(repo, token=None):
    """The pictures of a Hugging Face model card (README) that lie on Hugging Face, in their order, for repos without a
    picture file of their own."""
    from huggingface_hub import hf_hub_download
    with open(hf_hub_download(repo, "README.md", token=token), encoding="utf-8", errors="replace") as f:
        card = f.read()
    out = []
    for m in _CARD_PICTURE.finditer(card):
        url = _card_url(repo, (m.group(1) or m.group(2) or "").strip())
        if url and url not in out:
            out.append(url)
    return out


class Refused(Exception):
    """Every picture the source offers was refused by the content filter."""


_checker = None


def _refused(data, safe):
    """Why the content filter keeps a picture out (nudity in safe mode; nudity with a likely minor always), or None.
    Raises when the filter can not run: the picture is then tried again at a later start, never shown unchecked."""
    global _checker
    from PIL import Image
    import content_check
    _checker = _checker or content_check.Checker()
    return _checker.check_picture(Image.open(io.BytesIO(data)).convert("RGB"), safe)


def _decodes(data):
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        return True
    except Exception:
        return False


def source_of(manifest):
    """Where the picture of fetch_for comes from: the model's source, or Civitai for files found
    there by their hash (importer._civitai_by_hash)."""
    src = (manifest.get("source") or {}).get("type")
    return src if src in ("civitai", "hf") or not manifest.get("civitai") else "civitai"


def fetch_for(folder, token=None):
    """Fetches the preview of an imported model / LoRA from its source; returns the path or None."""
    manifest = None
    for name in ("model.json", "lora.json"):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            with open(p) as f:
                manifest = json.load(f)
            break
    if not manifest:
        return None
    src = manifest.get("source") or {}
    if src.get("type") not in ("civitai", "hf") and (manifest.get("civitai") or {}).get("images"):
        # a file from disk that is on Civitai (found by its hash)
        url = civitai_image(manifest["civitai"]["images"])
        if not url and manifest["civitai"]["images"]:
            raise Refused("safe")
        return _save(_get(url), folder) if url else None
    if src.get("type") == "civitai":
        images = src.get("images")
        if images is None and src.get("version_id"):
            import civitai
            v = civitai._get_json("%s/model-versions/%d" % (civitai.API, int(src["version_id"])),
                                  os.environ.get("CIVITAI_TOKEN"))
            images = civitai.sample_images(v)
        url = civitai_image(images)
        if not url and images:
            raise Refused("safe")  # all of them above what safe mode shows
        return _save(_get(url), folder) if url else None
    if src.get("type") == "hf" and src.get("ref") and "/" in src["ref"] and not os.path.exists(src["ref"]):
        token = token or os.environ.get("HF_TOKEN")
        path = hf_image(src["ref"], token)
        if path:
            from huggingface_hub import hf_hub_download
            with open(hf_hub_download(src["ref"], path, token=token), "rb") as f:
                return _save(f.read(), folder)
        safe = os.environ.get("VK_SAFE_MODE") == "1"
        refused = None
        for url in hf_card_images(src["ref"], token):
            try:
                data = _get(url)
            except urllib.error.HTTPError as e:
                if 400 <= e.code < 500:
                    continue  # gone or not public: the next picture of the card
                raise
            if not _decodes(data):
                continue  # a page, not a picture
            reason = _refused(data, safe)
            if reason:
                # a refusal that only safe mode makes is tried again once it is off
                refused = refused if refused == "refused" else ("safe" if safe and not _refused(data, False) else "refused")
                continue
            return _save(data, folder)
        if refused:
            raise Refused(refused)
    return None


def _mark(folder, source=None):
    """Notes the preview (and where it came from) in the manifest."""
    for name in ("model.json", "lora.json"):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            with open(p) as f:
                m = json.load(f)
            m["preview"] = FILE
            m["preview_source"] = source or source_of(m)
            with open(p + ".tmp", "w") as f:
                json.dump(m, f, indent=1)
            os.replace(p + ".tmp", p)


def _manifest(folder):
    for name in ("model.json", "lora.json"):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            try:
                with open(p) as f:
                    return p, json.load(f)
            except (OSError, ValueError):
                return p, {}
    return None, None


def missing(roots):
    """Imported models and LoRAs without a preview, except those whose source was found to have none."""
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            folder = os.path.join(root, name)
            if not os.path.isdir(folder) or name.startswith(".") or os.path.isfile(os.path.join(folder, FILE)):
                continue
            path, m = _manifest(folder)
            if not path or not isinstance(m, dict):
                continue
            mark = m.get("preview_missing")
            # "safe": refused only because of safe mode, so asked again once it is off
            if not mark or (mark == "safe" and os.environ.get("VK_SAFE_MODE") != "1"):
                yield folder


def _mark_missing(folder, why=True):
    """Notes that the source has no picture (True) or only refused ones ("safe", "refused"), so the app does not ask
    again at every start."""
    path, m = _manifest(folder)
    if path and isinstance(m, dict):
        m["preview_missing"] = why
        with open(path + ".tmp", "w") as f:
            json.dump(m, f, indent=1)
        os.replace(path + ".tmp", path)


def main(argv):
    roots = argv or [str(paths.models_dir()), str(paths.loras_dir())]
    for folder in missing(roots):
        try:
            try:
                path = fetch_for(folder)
            except Refused as r:
                _mark_missing(folder, str(r))
                print("__preview__ " + json.dumps({"folder": folder, "preview": None, "refused": str(r)}), flush=True)
                continue
            if path:
                _mark(folder)
            else:
                _mark_missing(folder)
            print("__preview__ " + json.dumps({"folder": folder, "preview": path}), flush=True)
        except Exception as e:
            print("__preview__ " + json.dumps({"folder": folder, "error": str(e)[:200]}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
