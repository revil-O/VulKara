# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Model / LoRA downloads from civitai.com.

Accepts a model page URL (optionally with ?modelVersionId=…), "<model id>" or "<model id>@<version id>".
Only SafeTensor files are downloaded; the result goes through the normal file import
(architecture detection, LoRA handling, FP8 conversion).
"""
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request

API = "https://civitai.com/api/v1"

# civitai "baseModel" -> (our architecture or None, the family its LoRAs belong to, the sub-base). The first
# match counts; the file's own keys decide inpainting / SD 2.x size later. Families without an architecture
# (HiDream, Lumina …) are known so that their LoRAs are not taken for another model's.
BASE_MODELS = [
    (r"krea ?2", "krea2", "krea2", None),
    (r"^anima\b", "anima", "anima", None),
    (r"^ideogram 4(\.0)?$", "ideogram4", "ideogram4", None),
    (r"flux\.?2.*klein.*9b", "flux2_klein", "flux2", "klein9b"),
    (r"flux\.?2.*klein.*4b", "flux2_klein", "flux2", "klein4b"),
    (r"flux\.?2.*klein", "flux2_klein", "flux2", None),
    (r"flux\.?2", "flux2_dev", "flux2", "dev"),
    # FLUX 3 Image Klein: its LoRAs are known; checkpoints come as repositories (Hugging Face), not as single files
    (r"flux\.?3|flux 3", None, "flux3", None),
    (r"flux\.?1 ?s\b", "flux1_schnell", "flux1", None),
    (r"flux\.?1", "flux1_dev", "flux1", None),
    (r"^chroma\b", "chroma", "chroma", None),
    (r"^qwen ?2\.1\b", "qwen_image21", "qwen_image21", None),
    (r"^qwen$", "qwen_image", "qwen_image", None),
    (r"sd ?3\.5.*large", "sd35_large", "sd3", None),
    (r"sd ?3", "sd35_medium", "sd3", None),
    (r"pony ?v ?7|aura ?flow", "auraflow", "auraflow", None),  # Pony V7 is an AuraFlow model, not SDXL
    (r"sdxl|^pony\b|illustrious|noobai|playground", "sdxl", "sdxl", None),
    (r"sd ?2.*768", "sd21", "sd2", None),
    (r"sd ?2", "sd21_base", "sd2", None),
    (r"sd ?1", "sd15", "sd1", None),
    (r"^wan video 2\.2 ti2v-5b", "wan22_ti2v", "wan", "5b"),
    (r"^wan video 2\.2 i2v-a14b", "wan22_i2v_14b", "wan", "14b"),
    (r"^wan video (2\.2 t2v-a14b|14b)", None, "wan", "14b"),
    (r"^wan video 1\.3b", None, "wan", "1.3b"),
    (r"^wan video$", None, "wan", None),
    (r"^z[-_ ]?image", "z_image", "z_image", None),  # "ZImageTurbo", "ZImageBase" (the file's name decides the defaults)
    (r"^hidream-o1", None, "hidream_o1", None),
    (r"^hidream", None, "hidream", None),
    (r"^hunyuan video", None, "hunyuan_video", None),
    (r"^hunyuan 1", None, "hunyuan_dit", None),
    (r"^lumina", "lumina2", "lumina", None),
    (r"^ernie", None, "ernie", None),
    (r"^moss", "moss_image", "moss_image", None),
    (r"^fibo[- ]?2", "fibo2", "fibo2", None),
]


class CivitaiError(ValueError):
    pass


def public_ref(ref):
    """The link without what must not be kept or shown: copied download links carry the user's API key
    (?token=...). Only modelVersionId stays of the query."""
    ref = (ref or "").strip()
    u = urllib.parse.urlparse(ref)
    if u.scheme not in ("http", "https"):
        return ref
    keep = [(k, v) for k, v in urllib.parse.parse_qsl(u.query) if k == "modelVersionId"]
    return urllib.parse.urlunparse((u.scheme, u.hostname or "", u.path, "", urllib.parse.urlencode(keep), ""))


def parse_ref(ref):
    """-> (model_id, version_id or None)"""
    ref = public_ref(ref)
    m = re.match(r"^(\d+)(?:@(\d+))?$", ref)
    if m:
        return int(m.group(1)), (int(m.group(2)) if m.group(2) else None)
    u = urllib.parse.urlparse(ref)
    host = (u.hostname or "").lower()
    if host != "civitai.com" and not host.endswith(".civitai.com"):
        raise CivitaiError("Not a civitai.com link: " + ref)
    m = re.search(r"/models/(\d+)", u.path)
    version = urllib.parse.parse_qs(u.query).get("modelVersionId", [None])[0]
    if not m:
        m2 = re.search(r"/model-versions/(\d+)", u.path) or re.search(r"/api/download/models/(\d+)", u.path)
        if m2:
            return None, int(m2.group(1))
        raise CivitaiError("Could not find a model id in " + ref)
    return int(m.group(1)), (int(version) if version else None)


def is_civitai_url(url):
    """https on civitai.com or one of its subdomains: the only place the API key goes."""
    u = urllib.parse.urlparse(url or "")
    host = (u.hostname or "").lower()
    return u.scheme == "https" and (host == "civitai.com" or host.endswith(".civitai.com"))


def _request(url, token=None):
    if not is_civitai_url(url):
        raise CivitaiError("Not a Civitai address: %s" % urllib.parse.urlparse(url or "").netloc)
    headers = {"User-Agent": "VulKara"}
    if token:
        headers["Authorization"] = "Bearer " + token
    return urllib.request.Request(url, headers=headers)


class _DropAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """Downloads redirect to a signed storage URL; sending the API key there as well makes the
    storage answer HTTP 400 (two authentication methods). urllib keeps headers on redirects.
    Redirects to plain http are refused."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlparse(newurl).scheme != "https":
            raise CivitaiError("Civitai redirected the download to an insecure address")
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlparse(newurl).hostname != urllib.parse.urlparse(req.full_url).hostname:
            new.remove_header("Authorization")
        return new


_opener = urllib.request.build_opener(_DropAuthOnRedirect)


def _get_json(url, token=None):
    try:
        with _opener.open(_request(url, token), timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise CivitaiError("Civitai refused the request (HTTP %d). Save a Civitai API key in the settings." % e.code)
        if e.code == 404:
            raise CivitaiError("Model not found on Civitai")
        raise


def clean_trigger_words(words):
    """Civitai's trained words: trimmed, split at commas ("a, b" in one entry), without duplicates."""
    out = []
    for w in words or []:
        for part in str(w).split(","):
            part = part.strip()
            if part and part.lower() not in [o.lower() for o in out]:
                out.append(part)
    return out


def sample_images(version):
    """The version's sample pictures (no videos) as [{"url", "nsfw_level"}]."""
    return [{"url": i.get("url"), "nsfw_level": i.get("nsfwLevel") or 0}
            for i in version.get("images") or [] if i.get("url") and i.get("type", "image") == "image"]


def lookup_hash(sha256, token=None):
    """The Civitai version of a file (by its SHA256), for files imported from disk: official trigger
    words and sample images. None when the file is not on Civitai or Civitai cannot be reached."""
    if not sha256:
        return None
    try:
        v = _get_json("%s/model-versions/by-hash/%s" % (API, sha256), token)
    except Exception:
        return None
    return {"model_id": v.get("modelId"), "version_id": v.get("id"), "name": (v.get("model") or {}).get("name"),
            "base_model": v.get("baseModel") or "", "trigger_words": clean_trigger_words(v.get("trainedWords")),
            "images": sample_images(v)[:8]}


# precisions of Civitai files the Mac can compute (MPS / MLX); int8 / int4 / nvfp4 are ComfyUI / NVIDIA
# formats (scaled integer, Blackwell FP4) neither diffusers on MPS nor mflux reads
USABLE_FP = {None, "", "fp16", "bf16", "fp32", "fp8", "fp8_mixed"}
FP_ORDER = {"bf16": 0, "fp16": 0, "fp8": 1, "fp8_mixed": 1, "fp32": 2, None: 3, "": 3}


def _base(base_model):
    for pattern, arch, family, variant in BASE_MODELS:
        if re.search(pattern, (base_model or "").strip(), re.I):
            return arch, family, variant
    return None, None, None


def arch_of(base_model):
    """Our architecture for Civitai's "baseModel", or "unknown"."""
    return _base(base_model)[0] or "unknown"


def family_of(base_model):
    """(family, sub-base) of LoRAs for Civitai's "baseModel", (None, None) when the app does not know it."""
    return _base(base_model)[1:]


def lora_hint(base_model):
    """What Civitai's "baseModel" tells about a LoRA, as registry.inspect_lora takes it; None if nothing."""
    family, variant = family_of(base_model)
    return {"family": family, "variant": variant, "source": "civitai", "base": base_model} if family else None


def _is_gguf(f):
    # Civitai files GGUF as "GGUF" or as "Other"; the name tells
    return (f.get("metadata") or {}).get("format") == "GGUF" or (f.get("name") or "").lower().endswith(".gguf")


def _model_files(version):
    """SafeTensor and GGUF files of the model itself (both are plain tensors; pickle formats are not loaded)."""
    return [f for f in version.get("files", []) if ((f.get("metadata") or {}).get("format") == "SafeTensor" or _is_gguf(f))
            and f.get("type") in ("Model", "Diffusion Model", None)]


def pick_file(version):
    """The file to download: the primary one when the Mac can compute it, else the best usable
    precision (16 bit before FP8 before 32 bit), pruned before full. None if no file fits."""
    files = [f for f in _model_files(version) if (f.get("metadata") or {}).get("fp") in USABLE_FP]
    if not files:
        return None

    def score(f):
        meta = f.get("metadata") or {}
        return (not f.get("primary"), _is_gguf(f), FP_ORDER.get(meta.get("fp"), 3), meta.get("size") != "pruned")
    return sorted(files, key=score)[0]


def _unusable_reason(version):
    files = _model_files(version)
    if not files:
        formats = sorted({(f.get("metadata") or {}).get("format", "?") for f in version.get("files", [])})
        return "no .safetensors or .gguf file (only %s; pickle formats are not loaded for safety)" % ", ".join(formats)
    fps = sorted({str((f.get("metadata") or {}).get("fp")) for f in files})
    return "only %s files (ComfyUI / NVIDIA formats the Mac can not compute)" % ", ".join(fps)


def resolve(ref, token=None):
    """Picks the model version and its SafeTensor file. Returns a description dict.

    Without a version in the link: the newest version this app can run (a known model type with a
    usable file); "note" says when newer versions were left out and why."""
    model_id, version_id = parse_ref(ref)
    model = _get_json("%s/models/%d" % (API, model_id), token) if model_id else None
    note = ""
    if version_id:
        version = _get_json("%s/model-versions/%d" % (API, version_id), token)
        if not _model_files(version) or pick_file(version) is None:
            raise CivitaiError("Version %s can not be used: %s" % (version.get("name"), _unusable_reason(version)))
    else:
        versions = (model or {}).get("modelVersions") or []
        if not versions:
            raise CivitaiError("This model has no downloadable versions")
        model_type = ((model or {}).get("type") or "").lower()
        is_lora = model_type in ("lora", "locon", "dora", "lycoris")
        skipped = []
        version = None
        for v in versions:  # newest first
            if not is_lora and arch_of(v.get("baseModel")) == "unknown" and not re.search(r"sd ?1|sd ?2", v.get("baseModel") or "", re.I):
                skipped.append("%s (%s: model type not supported)" % (v.get("name"), v.get("baseModel")))
                continue
            if pick_file(v) is None:
                skipped.append("%s (%s)" % (v.get("name"), _unusable_reason(v)))
                continue
            version = v
            break
        if version is None:
            raise CivitaiError("No version of this model can run on this Mac: " + "; ".join(skipped[:6]))
        if skipped:
            note = "Newer versions left out: " + "; ".join(skipped[:4])
    model_type = (model or {}).get("type") or (version.get("model") or {}).get("type") or ""
    f = pick_file(version)
    base = version.get("baseModel") or ""
    # a version's own text encoder / VAE (models in separate files, e.g. Anima): downloaded with it
    extras = []
    for x in version.get("files", []):
        part = {"Text Encoder": "text_encoder", "VAE": "vae"}.get(x.get("type"))
        if part and (x.get("metadata") or {}).get("format") == "SafeTensor" and part not in [e["part"] for e in extras]:
            extras.append({"part": part, "file_name": x.get("name"), "download_url": x.get("downloadUrl"),
                           "size_bytes": int(float(x.get("sizeKB") or 0) * 1024),
                           "sha256": ((x.get("hashes") or {}).get("SHA256") or "").lower()})
    return {
        "model_id": model_id, "version_id": version.get("id"), "name": (model or {}).get("name") or version.get("name"),
        "version_name": version.get("name"), "type": model_type, "base_model": base, "arch": arch_of(base),
        "file_name": f.get("name"), "size_bytes": int(float(f.get("sizeKB") or 0) * 1024),
        "sha256": ((f.get("hashes") or {}).get("SHA256") or "").lower(), "download_url": f.get("downloadUrl"),
        "precision": (f.get("metadata") or {}).get("fp"), "note": note, "extras": extras,
        "trigger_words": clean_trigger_words(version.get("trainedWords")),
        "images": sample_images(version),  # for the model's preview picture
        # the maker's texts, where the recommended settings are written (maker_settings.py)
        "card": "%s\n%s" % (version.get("description") or "", (model or {}).get("description") or ""),
    }


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(info, dest_dir, token=None, progress=None):
    """Downloads the file into dest_dir, verifies SHA256, returns the local path."""
    os.makedirs(dest_dir, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", info["file_name"] or "").lstrip(".") or "model.safetensors"
    path = os.path.join(dest_dir, safe)
    part = path + ".partial"
    h = hashlib.sha256()
    done = 0
    if info["sha256"] and os.path.isfile(path) and _sha256_file(path) == info["sha256"]:
        return path  # kept from an import that failed after downloading
    try:
        with _opener.open(_request(info["download_url"], token), timeout=60) as r, open(part, "wb") as out:
            total = int(r.headers.get("Content-Length") or info["size_bytes"] or 0)
            last = -1
            while True:
                chunk = r.read(8 * 1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                done += len(chunk)
                pct = int(100 * done / total) if total else -1
                if progress and pct != last:
                    progress(pct)
                    last = pct
        if info["sha256"] and h.hexdigest() != info["sha256"]:
            raise CivitaiError("Checksum mismatch, the download is damaged")
    except BaseException as e:
        if os.path.exists(part):
            os.remove(part)
        if not isinstance(e, urllib.error.HTTPError):
            raise
        if e.code in (401, 403):
            raise CivitaiError("Civitai needs an API key for this download. Save one in the settings.")
        try:
            detail = e.read(300).decode("utf-8", "replace").strip()
        except Exception:
            detail = ""
        raise CivitaiError("Civitai download failed: HTTP %d %s" % (e.code, detail or e.reason))
    os.replace(part, path)
    return path
