# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Imports a model from Hugging Face, a local file or a local diffusers folder.

The result is a folder in the models folder (<models>/<name>/) with a
model.json manifest. Weights stay in their original precision on disk;
quantization is applied when the model is loaded, based on the RAM plan, so the
same import keeps working if the machine (or the plan) changes.

Progress / results are reported on stdout as
    __import_progress__ {"stage": ..., "progress": 0-100}
    __import_info__     {...}      (dry run)
    __import_done__     {...}      (the manifest)
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")  # progress is reported by _ProgressWatcher

import convert_gguf  # noqa: E402
import memory  # noqa: E402
import paths  # noqa: E402
import registry  # noqa: E402

MANIFEST = "model.json"
FORMAT_VERSION = 1


def imported_on():
    """The Mac a model is imported on, for model.json: the app's id of it (VK_MACHINE_ID, a hash, never the Mac's own
    UUID) and its memory in whole GB. A folder copied to another Mac is told by it (src/main/foreign_mac.ts)."""
    stamp = {}
    machine = os.environ.get("VK_MACHINE_ID", "").strip()
    if machine:
        stamp["machine"] = machine
    stamp["ram_gb"] = int(memory.total_ram_gb() + 0.5)  # as the app rounds it (Math.round)
    return stamp

WEIGHT_EXTS = (".safetensors", ".bin", ".ckpt", ".pt", ".pth", ".onnx", ".msgpack", ".h5", ".gguf", ".onnx_data")
# code in a repo is never fetched: the pipelines and models come from diffusers / transformers
CODE_EXTS = (".py", ".pyc", ".so", ".dylib")
# parts of a repository no engine loads: not downloaded (ERNIE-Image's prompt enhancer is a 7 GB language model)
OPTIONAL_COMPONENTS = ("safety_checker", "pe", "pe_tokenizer")
SKIP_COMPONENTS = ("scheduler", "tokenizer", "tokenizer_2", "tokenizer_3", "feature_extractor", "image_encoder",
                   "safety_checker", "processor")


def emit(tag, payload):
    print("%s %s" % (tag, json.dumps(payload)), flush=True)


def progress(stage, pct=-1):
    emit("__import_progress__", {"stage": stage, "progress": pct})


def models_root():
    root = paths.models_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root


# file names that say nothing about the model: the repository's name is taken instead
GENERIC_STEMS = {"pytorch_lora_weights", "adapter_model", "model", "lora", "diffusion_pytorch_model", "weights"}


def default_name(source, ref, file=None):
    """The name of an import without one: the file's (it often tells the variant, e.g. Q4_K_M), unless that is a
    generic one like pytorch_lora_weights; then the Hugging Face repository's."""
    base = os.path.basename((file or ref).rstrip("/"))
    # a repository or folder keeps its dots ("FLUX.2-klein-4B"), a file loses its extension
    stem = os.path.splitext(base)[0] if file or source == "file" else base
    if source == "hf" and file and stem.lower() in GENERIC_STEMS:
        return ref.rstrip("/").split("/")[-1]
    return stem


def safe_name(name):
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not name:
        raise ValueError("Invalid model name")
    return name


def is_diffusers_model_dir(path):
    return os.path.isfile(os.path.join(path, MANIFEST))


# ------------------------------------------------------------ repo inspection

def _component_names(model_index):
    return [k for k, v in model_index.items()
            if isinstance(v, list) and len(v) == 2 and v[0] in ("diffusers", "transformers")
            and v[1] is not None and k not in SKIP_COMPONENTS]


def _denoiser_name(model_index):
    return "unet" if "unet" in model_index else "transformer"


def _variant_of(filename):
    """fp16 / bf16 / fp32 for variant files ("model.fp16.safetensors", sharded
    "model.fp16-00001-of-00002.safetensors", "model.safetensors.index.fp16.json"), else None."""
    m = re.search(r"\.(fp16|fp32|bf16)[.-]", os.path.basename(filename))
    return m.group(1) if m else None


def _pick_weight_files(files, component, prefer_fp16=False):
    """From all repo files of a component folder pick one set of safetensors weights.
    Takes the plain files (what diffusers loads without a variant), else the fp16 variant;
    prefer_fp16: the fp16 variant first (half the download for models computed in 16 bit).
    Copies of the training weights (non_ema / ema) are left out. Returns (files, variant)."""
    weights = [f for f in files if f.startswith(component + "/") and f.endswith(".safetensors")
               and not re.search(r"\.(non_ema|ema)\b", os.path.basename(f))]
    fp16 = [f for f in weights if _variant_of(f) == "fp16"]
    plain = [f for f in weights if _variant_of(f) is None]
    if fp16 and (prefer_fp16 or not plain):
        return fp16, "fp16"
    if plain:
        return plain, None
    return weights, None


def _repo_plan_files(files, model_index):
    """Exact file list to download for a diffusers repo and the variant to load."""
    comps = [k for k, v in model_index.items() if isinstance(v, list) and len(v) == 2 and v[1] is not None
             and k not in OPTIONAL_COMPONENTS]
    wanted = ["model_index.json"]
    variants = set()
    # diffusers loads one variant for all components: fp16 only when every component has it
    with_weights = [c for c in _component_names(model_index)
                    if any(f.startswith(c + "/") and f.endswith(".safetensors") for f in files)]
    all_fp16 = bool(with_weights) and all(
        any(f.startswith(c + "/") and _variant_of(f) == "fp16" and f.endswith(".safetensors") for f in files)
        for c in with_weights)
    for c in comps:
        in_folder = [f for f in files if f.startswith(c + "/")]
        wanted += [f for f in in_folder if not f.endswith(WEIGHT_EXTS + CODE_EXTS) and ".safetensors.index" not in f]
        chosen, variant = _pick_weight_files(files, c, prefer_fp16=all_fp16)
        if not chosen and c in _component_names(model_index) and any(f.endswith(WEIGHT_EXTS) for f in in_folder):
            raise registry.UnsupportedModel(
                "Component '%s' has no .safetensors weights (pickle formats are not loaded for safety)" % c)
        wanted += chosen
        variants.add(variant)
        # sharded weights need their index (named after the variant)
        for f in in_folder:
            if ".safetensors.index" in f and f.endswith(".json") and _variant_of(f) == variant:
                wanted.append(f)
    variants.discard(None)
    # diffusers loads a variant for all components or none; mixed repos use the plain files
    variant = "fp16" if variants == {"fp16"} and all(
        any(_variant_of(f) == "fp16" for f in files if f.startswith(c + "/") and f.endswith(".safetensors"))
        for c in _component_names(model_index)) else None
    return sorted(set(wanted)), variant


# (repo, file) -> SHA-256 the Hub lists for a large file, from _hf_repo_info: a file of another model is only taken
# over when its content is the same (a path and a size can match by chance: FLUX.1's and SD 3.5's VAE)
_LFS_SHA256 = {}


def _hf_repo_info(repo, token):
    from huggingface_hub import HfApi
    api = HfApi(token=token)
    info = api.model_info(repo, files_metadata=True)
    sizes = {s.rfilename: (s.size or 0) for s in info.siblings}
    for s in info.siblings:
        if getattr(s, "lfs", None):
            _LFS_SHA256[(repo, s.rfilename)] = s.lfs.sha256
    return api, sizes


def _hashes(repo, files):
    return {f: _LFS_SHA256[(repo, f)] for f in files if (repo, f) in _LFS_SHA256}


NO_LAYOUT = "This repo has no diffusers layout (model_index.json)."
PICK_FILE = "Pick one of its model files:"
MAX_LISTED = 12
# folders and names of the parts that come with a model file (for ComfyUI), not models themselves
NOT_MODELS = re.compile(r"(^|[/_.-])(text_encoders?|vae|loras?|clip|t5|tokenizers?|controlnets?|upscalers?)([/_.-]|$)", re.I)
# quantized formats of other runtimes (MLX, NVIDIA FP4, ComfyUI's int8 rotation) this engine can not read
OTHER_FORMATS = re.compile(r"mlx|nvfp4|convrot", re.I)
MIN_MODEL_BYTES = 300 * 1024 ** 2


def model_file_candidates(sizes):
    """The single model files of a repo without diffusers layout, from {file: bytes}: .gguf first, then
    .safetensors, each smallest first; text encoders, VAEs, LoRAs, other runtimes' formats and small
    files left out."""
    files = [f for f, n in sizes.items() if f.lower().endswith((".gguf", ".safetensors"))
             and not NOT_MODELS.search(f) and not OTHER_FORMATS.search(os.path.basename(f))
             and (n or MIN_MODEL_BYTES) >= MIN_MODEL_BYTES]
    return sorted(files, key=lambda f: (not f.lower().endswith(".gguf"), sizes[f] or 0, f))


def _no_layout_message(repo, token):
    """The error for a repo without model_index.json, naming the files that can be imported from it."""
    try:
        sizes = _hf_repo_info(repo, token)[1]
        files = model_file_candidates(sizes)
    except Exception:
        return NO_LAYOUT + " Pick a single .safetensors/.gguf file from it."
    if not files:
        return NO_LAYOUT + " It has no .safetensors or .gguf model file either."
    listed = ["%s (%.1f GB)" % (f, sizes[f] / 1024 ** 3) if sizes.get(f) else f for f in files[:MAX_LISTED]]
    more = " and %d more" % (len(files) - MAX_LISTED) if len(files) > MAX_LISTED else ""
    return "%s %s %s%s" % (NO_LAYOUT, PICK_FILE, ", ".join(listed), more)


def _params_from_hf(api, repo, files):
    """{component: params_billion} from the safetensors headers (range requests, no weights)."""
    out = {}
    for fname in files:
        if "/" not in fname or not fname.endswith(".safetensors"):
            continue
        try:
            meta = api.parse_safetensors_file_metadata(repo, fname)
        except Exception:
            continue
        comp = fname.split("/")[0]
        out[comp] = out.get(comp, 0) + sum(meta.parameter_count.values()) / 1e9
    return out


def _params_from_folder(folder, components):
    out = {}
    for c in components:
        cdir = Path(folder) / c
        if not cdir.is_dir():
            continue
        # "._name" files are the AppleDouble companions macOS writes on exFAT / FAT drives, no weights
        files = [str(p) for p in cdir.glob("*.safetensors") if not p.name.startswith("._")]
        chosen, _ = _pick_weight_files([c + "/" + os.path.basename(f) for f in files], c)
        total = 0
        for f in chosen:
            total += registry._n_params(registry.read_safetensors_header(str(cdir / f.split("/", 1)[1])))
        out[c] = total / 1e9
    return out


def _load_json(path):
    with open(path) as f:
        return json.load(f)


def _hf_json(repo, filename, token):
    from huggingface_hub import hf_hub_download
    return _load_json(hf_hub_download(repo, filename, token=token))


def _fill_params(params, arch, components):
    fallback = registry.ARCHS[arch]["fallback_params"]
    return {c: (params.get(c) or fallback.get(c, 0.1)) for c in components}


# ------------------------------------------------------------ FLUX 3 Image Klein

# what flux3-mlx reads of Black Forest Labs' repo: its own transformer and autoencoder files and the text encoder (the
# diffusers copies in transformer/ and vae/ and the FP8 / NVFP4 variants are left out: about 22 GB less)
FLUX3_BFL_FILES = ("model.safetensors", "ae.safetensors", "config.json", "manifest.json", "LICENSE.md", "NOTICE.md")
FLUX3_SKIP = re.compile(r"^(gallery|assets|variants)/|\.(jpe?g|png|webp|gif|md)$|^\.gitattributes$", re.I)


def flux3_files(files, config):
    """The files of a FLUX 3 repo to download: an MLX repo for flux3-mlx whole (without its gallery), Black Forest
    Labs' repo only what flux3-mlx reads."""
    if config.get("format") == "flux3-mlx":
        return sorted(f for f in files if not FLUX3_SKIP.search(f) or f in ("LICENSE.md", "NOTICE.md"))
    wanted = [f for f in files if f in FLUX3_BFL_FILES or (f.startswith("text_encoder/") and not FLUX3_SKIP.search(f))]
    if "model.safetensors" not in wanted:
        raise registry.UnsupportedModel("This FLUX 3 repo has no model.safetensors (Black Forest Labs' transformer "
                                        "file), which the MLX runtime reads")
    return sorted(wanted)


def _flux3_components(sizes, files):
    """{component: billions of 16 bit parameters as large as the files}: flux3-mlx holds the weights as they lie on
    disk, so the plan (in 16 bit) comes out at their size."""
    def gb(pred):
        return sum(sizes.get(f, 0) for f in files if pred(f) and f.endswith(".safetensors")) / 1e9 / 2
    # Black Forest Labs' own files where they are (a full clone also holds diffusers' copies in transformer/ and vae/),
    # the same preference as the engine (flux3.components)
    transformer = gb(lambda f: f == "model.safetensors") or gb(lambda f: f.startswith("transformer/"))
    vae = gb(lambda f: f == "ae.safetensors") or gb(lambda f: f.startswith("vae/"))
    return {"transformer": transformer or 5.6, "text_encoder": gb(lambda f: f.startswith("text_encoder/")) or 4.4,
            "vae": vae or 0.08}


def inspect_flux3(source, ref, token=None):
    """inspect() for a FLUX 3 Image Klein repo or folder (no model_index.json), else None."""
    if source == "hf":
        try:
            config = _hf_json(ref, "config.json", token)
        except Exception:
            return None
        try:
            modular = _hf_json(ref, "modular_model_index.json", token)
        except Exception:
            modular = None
    else:
        config_path = os.path.join(ref, "config.json")
        if not os.path.isfile(config_path):
            return None
        config = _load_json(config_path)
        mpath = os.path.join(ref, "modular_model_index.json")
        modular = _load_json(mpath) if os.path.isfile(mpath) else None
    found = registry.detect_flux3(config, modular)
    if not found:
        return None
    arch, overrides = found
    info = {"source": source, "ref": ref, "file": None, "arch": arch, "overrides": overrides, "denoiser": "transformer",
            "variant": None}
    if source == "hf":
        sizes = _hf_repo_info(ref, token)[1]
        files = flux3_files(list(sizes), config)
        info.update(layout="repo", files=files, file_sizes={f: sizes.get(f, 0) for f in files},
                    file_sha256=_hashes(ref, files),
                    download_bytes=sum(sizes.get(f, 0) for f in files), components=_flux3_components(sizes, files))
    else:
        files = [str(p.relative_to(ref)) for p in Path(ref).rglob("*") if p.is_file() and not p.name.startswith("._")]
        sizes = {f: os.path.getsize(os.path.join(ref, f)) for f in files}
        info.update(layout="folder", download_bytes=0, components=_flux3_components(sizes, files))
    return info


# ------------------------------------------------------------ inspection

def _scheduler_config(model_index, read):
    """The scheduler's config where it tells a model's version (Z-Image: Base shifts by 6, Turbo by 3), else None."""
    if not str(model_index.get("_class_name", "")).startswith("ZImage"):
        return None
    try:
        return read("scheduler/scheduler_config.json")
    except Exception:
        return None


def inspect(source, ref, file=None, token=None, name_hint=""):
    """Works out architecture, layout and sizes without downloading weights. name_hint: what the source calls the
    model's base (Civitai's base model), read with the file's name where the name tells a version."""
    info = {"source": source, "ref": ref, "file": file}

    if source == "hf" and not file:
        from huggingface_hub.utils import EntryNotFoundError
        try:
            model_index = _hf_json(ref, "model_index.json", token)
        except EntryNotFoundError:
            flux3 = inspect_flux3(source, ref, token)
            if flux3:
                return flux3
            raise registry.UnsupportedModel(_no_layout_message(ref, token))
        den = _denoiser_name(model_index)
        try:
            den_cfg = _hf_json(ref, den + "/config.json", token)
        except Exception:
            den_cfg = {}
        arch, overrides = registry.detect_from_model_index(
            model_index, den_cfg, ref, _scheduler_config(model_index, lambda f: _hf_json(ref, f, token)))
        api, sizes = _hf_repo_info(ref, token)
        files, variant = _repo_plan_files(list(sizes), model_index)
        comps = _component_names(model_index)
        params = _fill_params(_params_from_hf(api, ref, files), arch, comps)
        info.update(layout="repo", arch=arch, overrides=overrides, components=params, denoiser=den,
                    variant=variant, files=files, file_sizes={f: sizes.get(f, 0) for f in files},
                    file_sha256=_hashes(ref, files), download_bytes=sum(sizes.get(f, 0) for f in files))
        return info

    if source == "dir":
        if not os.path.isfile(os.path.join(ref, "model_index.json")):
            flux3 = inspect_flux3(source, ref)
            if flux3:
                return flux3
        model_index = _load_json(os.path.join(ref, "model_index.json"))
        den = _denoiser_name(model_index)
        den_cfg_path = os.path.join(ref, den, "config.json")
        den_cfg = _load_json(den_cfg_path) if os.path.isfile(den_cfg_path) else {}
        arch, overrides = registry.detect_from_model_index(
            model_index, den_cfg, ref, _scheduler_config(model_index, lambda f: _load_json(os.path.join(ref, f))))
        comps = _component_names(model_index)
        params = _fill_params(_params_from_folder(ref, comps), arch, comps)
        info.update(layout="folder", arch=arch, overrides=overrides, components=params, denoiser=den,
                    variant=None, download_bytes=0)
        return info

    # single file: local path, or a file inside an HF repo
    if source == "hf":
        from huggingface_hub import HfApi
        api = HfApi(token=token)
        size = {s.rfilename: s.size for s in api.model_info(ref, files_metadata=True).siblings}.get(file)
        if size is None:
            raise ValueError("File %s not found in %s" % (file, ref))
        if file.endswith(".safetensors"):
            meta = api.parse_safetensors_file_metadata(ref, file)
            shapes = {k: t.shape for k, t in meta.tensors.items()}
        else:
            # the GGUF header from the file's first megabytes; from the file name when that fails (the
            # header is checked again after the download)
            shapes = _hf_gguf_shapes(ref, file, token)
        file_bytes = size
    else:
        shapes = registry.read_single_file_header(ref)
        file_bytes = os.path.getsize(ref)

    names = ref + "/" + (file or "") + (" " + name_hint if name_hint else "")
    if shapes is None:
        arch, layout, overrides, den_params = _guess_from_name(names)
    else:
        arch, layout, overrides, den_params = registry.detect_from_single_file(shapes, names)

    spec = registry.ARCHS[arch]
    if layout == "comfy_files":
        base_files = (spec.get("comfy") or {}).get("base_files") or {}
        repo_sizes, base_sizes, base_sha256 = {}, {}, {}
        for part, value in base_files.items():
            repo, repo_file = base_file_source(spec["base_repo"], value)
            try:
                if repo not in repo_sizes:
                    repo_sizes[repo] = _hf_repo_info(repo, token)[1]
                base_sizes[part] = repo_sizes[repo].get(repo_file, 0)
                if (repo, repo_file) in _LFS_SHA256:
                    base_sha256[part] = _LFS_SHA256[(repo, repo_file)]
            except Exception as e:
                info["base_warning"] = str(e)
        params = dict(spec["fallback_params"])
        if den_params and not spec.get("fixed_params"):
            params[spec["denoiser"]] = den_params
        if (file or ref).lower().endswith(".gguf") and file_bytes:
            # a GGUF file stays as it is in memory: counted by its size, in 16 bit equivalents
            params[spec["denoiser"]] = file_bytes / 2e9
        info.update(layout=layout, arch=arch, overrides=overrides, components=params, denoiser=spec["denoiser"],
                    base_repo=spec["base_repo"], variant=None, base_files=base_files, base_sizes=base_sizes,
                    base_sha256=base_sha256,
                    download_bytes=sum(base_sizes.values()) + (file_bytes if source == "hf" else 0))
        return info
    native_files = spec.get("native_files")
    if native_files:
        if source == "hf":
            raise registry.UnsupportedModel("%s: import the repo %s, or both transformer files from disk"
                                            % (spec["label"], spec["base_repo"]))
        info["native_sources"] = _ideogram_sources(ref)
        file_bytes = sum(os.path.getsize(p) for p in info["native_sources"].values())
    base = _base_repo(arch, den_params, names)
    den = spec["denoiser"]
    comps = list(spec["fallback_params"])
    base_params = {}
    base_bytes = 0
    try:
        api, sizes = _hf_repo_info(base, token)
        model_index = _hf_json(base, "model_index.json", token)
        files, _ = _repo_plan_files(list(sizes), model_index)
        if layout == "single_denoiser":
            files = [f for f in files if not _is_replaced(f, list(native_files or [den]))]
        else:
            files = [f for f in files if not f.endswith(".safetensors")]
        comps = _component_names(model_index)
        base_params = _params_from_hf(api, base, files)
        base_bytes = sum(sizes.get(f, 0) for f in files)
    except Exception as e:
        info["base_warning"] = str(e)
    params = _fill_params(base_params, arch, comps)
    if den_params:
        for c in (native_files or [den]):
            params[c] = den_params  # Ideogram 4: both transformers have the same size

    is_gguf = (file or ref).lower().endswith(".gguf")
    info.update(layout=layout, arch=arch, overrides=overrides, components=params, denoiser=den,
                base_repo=base, variant=None, gguf=is_gguf,
                denoiser_fixed_gb=(file_bytes / 1024 ** 3 if is_gguf else None),
                download_bytes=base_bytes + (file_bytes if source == "hf" else 0))
    return info


GGUF_HEADER_BYTES = (4 * 1024 ** 2, 64 * 1024 ** 2)  # first request, largest request


def _hf_gguf_shapes(repo, file, token):
    """Tensor shapes of a GGUF file in a Hugging Face repo from range requests (no weights), or None."""
    from huggingface_hub import hf_hub_url
    from huggingface_hub.utils import build_hf_headers, get_session
    n = GGUF_HEADER_BYTES[0]
    try:
        while n <= GGUF_HEADER_BYTES[1]:
            headers = dict(build_hf_headers(token=token), Range="bytes=0-%d" % (n - 1))
            data = bytearray()
            with get_session().stream("GET", hf_hub_url(repo, file), headers=headers, follow_redirects=True,
                                      timeout=60) as r:
                r.raise_for_status()
                for chunk in r.iter_bytes():  # stops at n bytes, also if the server ignores the range
                    data.extend(chunk)
                    if len(data) >= n:
                        break
            try:
                return registry.parse_gguf_header(bytes(data[:n]))
            except registry.IncompleteHeader:
                n *= 4
    except Exception as e:
        print("GGUF header of %s not read: %s" % (file, e), file=sys.stderr)
    return None


def _ideogram_role(path, header=None):
    """"transformer" (conditional) or "unconditional_transformer" for an Ideogram 4 transformer file."""
    header = header if header is not None else registry.read_safetensors_json(path)
    kind = (header.get("__metadata__") or {}).get("model_type", "")
    if kind.endswith("_uncond") or (not kind and "uncond" in os.path.basename(path).lower()):
        return "unconditional_transformer"
    return "transformer"


def _ideogram_sources(path):
    """Ideogram 4 denoises with two transformers of the same shape (conditional and unconditional).
    The file that was picked is one of them; the other one has to lie in the same folder."""
    path = os.path.abspath(path)
    header = registry.read_safetensors_json(path)
    role = _ideogram_role(path, header)
    keys = set(header) - {"__metadata__"}
    folder = os.path.dirname(path)
    for name in sorted(os.listdir(folder)):
        other = os.path.join(folder, name)
        if other == path or not name.lower().endswith(".safetensors") or name.startswith("._"):
            continue
        try:
            other_header = registry.read_safetensors_json(other)
        except Exception:
            continue
        other_role = _ideogram_role(other, other_header)
        if set(other_header) - {"__metadata__"} == keys and other_role != role:
            return {role: path, other_role: other}
    missing = "unconditional" if role == "transformer" else "conditional"
    raise registry.UnsupportedModel(
        "Ideogram 4 needs both of its transformer files: the %s one (e.g. ideogram4_%sfp8_scaled.safetensors) "
        "was not found next to %s. Put both files into the same folder and import again."
        % (missing, "unconditional_" if missing == "unconditional" else "", os.path.basename(path)))


def _guess_from_name(name):
    n = name.lower()
    if "chroma" in n:
        if "radiance" in n:
            raise registry.UnsupportedModel(registry.CHROMA_OTHERS % "Chroma Radiance")
        return "chroma", "single_denoiser", registry.chroma_overrides(n), None
    if re.search(r"pony[-_ ]?v[-_ ]?7|auraflow|aura[-_ ]flow", n):
        return "auraflow", "comfy_files", {}, None
    if re.search(r"lumina|neta[-_ ]?(yume|lumina)", n):
        return "lumina2", "comfy_files", registry.lumina_overrides(n), None
    if re.search(r"z[-_ ]?image", n):
        return "z_image", "single_denoiser", registry.z_image_overrides(n), None
    if re.search(r"qwen[-_ ]?image", n):
        arch = "qwen_image21" if re.search(r"image[-_ ]?2[._]1", n) else "qwen_image"
        return arch, "single_denoiser", registry._qwen_overrides(n, registry.name_overrides(n)), None
    if "flux" in n and "2" in n.split("flux")[-1][:3]:
        return ("flux2_dev" if "dev" in n else "flux2_klein"), "single_denoiser", {}, None
    if "flux" in n:
        return ("flux1_schnell" if "schnell" in n else "flux1_dev"), "single_denoiser", registry.name_overrides(n), None
    if "sd3" in n or "3.5" in n or "3_5" in n:
        return ("sd35_large" if "large" in n else "sd35_medium"), "single_denoiser", registry.name_overrides(n), None
    if "wan" in n and "i2v" in n and "14b" in n and ("2.2" in n or "2_2" in n):
        if "low" in n.rsplit("/", 1)[-1] and "high" not in n.rsplit("/", 1)[-1]:
            raise registry.UnsupportedModel("This is the low-noise half of Wan 2.2 I2V 14B: import the high-noise "
                                            "file, the low-noise one is added automatically")
        return "wan22_i2v_14b", "comfy_files", {}, None
    raise registry.UnsupportedModel("Can not tell the architecture of %s before download" % name)


def _is_replaced(f, components):
    """Weights (and their shard index) of components that come from the imported file(s)."""
    return any(f.startswith(c + "/") and (f.endswith(WEIGHT_EXTS) or f.endswith(".index.json")) for c in components)


def _base_repo(arch, den_params, ref=""):
    if arch == "flux2_klein" and den_params and den_params > 6:
        return "black-forest-labs/FLUX.2-klein-9B"
    if arch == "chroma" and registry.is_chroma_flash(ref):
        return registry.ARCHS[arch]["flash_base_repo"]  # the same parts; its scheduler has Flash's shift
    if arch == "z_image" and registry.is_z_image_base(ref):
        return registry.ARCHS[arch]["undistilled_base_repo"]  # the same parts; its scheduler has Base's shift
    return registry.ARCHS[arch]["base_repo"]


def make_plan(info, quant="auto", ram_gb=None):
    spec = registry.ARCHS[info["arch"]]
    if spec.get("runtime") == "comfyui":
        # ComfyUI keeps the weights as they are and frees the text encoder when the denoiser needs room
        ram = ram_gb if ram_gb is not None else memory.total_ram_gb()
        plan = memory.plan(info["components"], info["denoiser"], spec["family"], ram, quant="none", allow_staging=True,
                           denoiser_fixed_gb=info.get("denoiser_fixed_gb"))
        if plan["fits"] or not _comfy_streamable(info):
            return plan
        # too large: ComfyUI's LOW_VRAM mode copies the layers in from the mapped GGUF file (engines/comfy/main.py)
        comps = dict(info["components"])
        comps[info["denoiser"]] *= STREAM_RESIDENT_SHARE
        fixed = info.get("denoiser_fixed_gb")
        streamed = memory.plan(comps, info["denoiser"], spec["family"], ram, quant="none", allow_staging=True,
                               denoiser_fixed_gb=fixed * STREAM_RESIDENT_SHARE if fixed else None)
        if streamed["fits"]:
            streamed["streamed"] = True
            return streamed
        return plan
    if spec.get("plan_on_disk"):
        # FLUX 3 (flux3-mlx): the weights in memory as on disk, the text encoder only for encoding when both do not fit
        return memory.plan(info["components"], info["denoiser"], spec["family"],
                           ram_gb if ram_gb is not None else memory.total_ram_gb(), quant="none", allow_staging=True,
                           staging_frees_denoiser=True)
    if spec.get("runtime") == "mlx":
        # MLX-only models: mflux quantizes all weights (4 bit on small Macs, text encoder included),
        # the checkpoint's own precision (FP8) does not matter
        return memory.plan(info["components"], info["denoiser"], spec["family"],
                           ram_gb if ram_gb is not None else memory.total_ram_gb(),
                           quant="q4" if quant == "auto" else quant, allow_staging=bool(spec.get("mlx_staged")))
    ram = ram_gb if ram_gb is not None else memory.total_ram_gb()
    # a whole checkpoint file loads in one piece (engine.py): no 4 bit text encoder, no stages
    planner = memory.plan if info.get("layout") == "single_full" else memory.fitting_plan
    plan = planner(info["components"], info["denoiser"], spec["family"], ram,
                   quant=quant, denoiser_fixed_gb=info.get("denoiser_fixed_gb"))
    if plan["fits"] or not _streamable(info):
        return plan
    # too large for the memory: the engine then streams the denoiser block by block from the SSD, in 16 bit (a GGUF
    # file is unpacked for that once)
    # (engine.py); the model fits if that does
    comps = dict(info["components"])
    comps[info["denoiser"]] *= memory.stream_resident_share(spec["family"])
    streamed = memory.plan(comps, info["denoiser"], spec["family"], ram, quant=quant)
    if not streamed["fits"] and quant == "auto":
        # as the engine: a big text encoder in 4 bit as the last resort
        streamed = memory.plan(comps, info["denoiser"], spec["family"], ram, quant=quant,
                               text_quant_opts=memory.QUANT_ORDER)
    if streamed["fits"]:
        streamed["quant"][info["denoiser"]] = "none"
        streamed["streamed"] = True
        return streamed
    return plan


# share of a GGUF denoiser ComfyUI keeps resident in LOW_VRAM (the Diffusers engine's: memory.stream_resident_share)
STREAM_RESIDENT_SHARE = 0.15


def _comfy_streamable(info):
    """A ComfyUI model streams only from a GGUF file (safetensors are read into memory), and not when Settings →
    ComfyUI streaming is off."""
    if os.environ.get("VK_COMFY_STREAMING", "on").strip().lower() in ("off", "0"):
        return False
    return str(info.get("file") or info.get("ref") or "").lower().endswith(".gguf")


def _streamable(info):
    """As engine.py decides: denoisers in the diffusers layout or as a file (GGUF too), streaming not off."""
    if os.environ.get("VK_SSD_STREAMING", "auto").strip().lower() in ("off", "0"):
        return False
    return info.get("layout") in ("repo", "single_denoiser")


# ------------------------------------------------------------ download / copy

class _ProgressWatcher:
    """Reports download progress by watching bytes on disk (incl. partial files)."""

    def __init__(self, folder, total, stage, report=None, count_existing=True):
        self.folder, self.total, self.stage = folder, max(total, 1), stage
        self.report = report or progress
        self.count_existing = count_existing  # False: only bytes added from now on count
        self.start = 0
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _size(self):
        n = 0
        for root, _, files in os.walk(self.folder):
            for f in files:
                try:
                    n += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return n

    def _run(self):
        while not self.done.wait(1.0):
            self.report(self.stage, min(99, int(100 * max(0, self._size() - self.start) / self.total)))

    def __enter__(self):
        if not self.count_existing:
            self.start = self._size()
        self.thread.start()
        return self

    def __exit__(self, *a):
        self.done.set()
        self.thread.join()


def _download(repo, files, local_dir, token, total_bytes, stage):
    from huggingface_hub import snapshot_download
    os.makedirs(local_dir, exist_ok=True)
    with _ProgressWatcher(local_dir, total_bytes, stage):
        snapshot_download(repo, local_dir=local_dir, allow_patterns=files, token=token)
    progress(stage, 100)


def _sha256(path):
    h = hashlib.sha256()
    total = os.path.getsize(path) or 1
    done, last = 0, time.time()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(16 * 1024 * 1024), b""):
            h.update(chunk)
            done += len(chunk)
            if time.time() - last > 1:
                progress("Verifying", int(100 * done / total))
                last = time.time()
    return h.hexdigest()


MIN_FREE_GB = 5.0
# no model or LoRA is installed with less free on the models disk: the downloads, the caches and the Mac need room
MIN_INSTALL_FREE_GB = 50.0


class NotEnoughSpace(OSError):
    pass


def ensure_install_room(folder):
    """Refuses an install (dry runs as well, so the finders show it) while the models disk has less than
    MIN_INSTALL_FREE_GB free."""
    import shutil
    at = Path(folder)
    while not at.exists() and at.parent != at:
        at = at.parent
    free_gb = shutil.disk_usage(str(at)).free / 1024 ** 3
    if free_gb < MIN_INSTALL_FREE_GB:
        # rounded down: 49.6 GB free must not read "50 GB"
        raise NotEnoughSpace("Only %d GB free on the models disk: models are installed with %d GB free or more"
                             % (int(free_gb), MIN_INSTALL_FREE_GB))


def ensure_space(folder, need_bytes, what="this import"):
    """Refuses an import that would leave less than MIN_FREE_GB on the disk of the models folder
    (a full disk breaks downloads, caches and other apps)."""
    import shutil
    os.makedirs(folder, exist_ok=True)
    free = shutil.disk_usage(folder).free
    if free - need_bytes < MIN_FREE_GB * 1024 ** 3:
        raise OSError("Not enough disk space for %s: needs about %.1f GB, %.1f GB free on the models disk "
                      "(%s). Free some space or choose another models folder in Settings."
                      % (what, need_bytes / 1024 ** 3, free / 1024 ** 3, folder))


def _link_or_copy(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _link_or_symlink(src, dst):
    """Hard link, else a symbolic link to the file where it is (other disk, or exFAT without
    hard links): multi-GB checkpoints are not duplicated. Returns True for a symbolic link."""
    try:
        os.link(src, dst)
        return False
    except OSError:
        os.symlink(os.path.abspath(src), dst)
        return True


# ------------------------------------------------------------ import

LORA_MANIFEST = "lora.json"


def loras_root(models_dir=None):
    root = Path(models_dir).parent / "loras" if models_dir else paths.loras_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _single_file_is_lora(source, ref, file, token):
    if source == "file" and ref.lower().endswith(".safetensors"):
        return registry.is_lora(registry._strip(registry.read_safetensors_header(ref).keys()))
    if source == "hf" and file and file.lower().endswith(".safetensors"):
        from huggingface_hub import HfApi
        meta = HfApi(token=token).parse_safetensors_file_metadata(ref, file)
        return registry.is_lora(registry._strip(meta.tensors.keys()))
    return False


_HASH_LOOKUPS = {}


def _civitai_lookup(sha256):
    """Civitai's version of a file by its SHA256 (civitai.lookup_hash), asked once per file and import."""
    if os.environ.get("VK_HASH_LOOKUPS") != "1":
        return None  # the user did not allow telling Civitai which files are on this Mac (Settings -> Privacy)
    if sha256 not in _HASH_LOOKUPS:
        import civitai
        progress("Looking up the file on Civitai")
        _HASH_LOOKUPS[sha256] = civitai.lookup_hash(sha256, os.environ.get("CIVITAI_TOKEN") or None)
    return _HASH_LOOKUPS[sha256]


def _hf_lora_hint(repo, token):
    """The base model a Hugging Face LoRA repository names (its card's base_model), as a hint for
    registry.inspect_lora; None when it names none the app knows, or Hugging Face can not be reached."""
    try:
        from huggingface_hub import HfApi
        card = HfApi(token=token).model_info(repo).card_data
        bases = card.get("base_model") if card else None
    except Exception:
        return None
    for base in [bases] if isinstance(bases, str) else list(bases or []):
        family, variant = registry.family_of_repo(base)
        if family:
            return {"family": family, "variant": variant, "source": "huggingface", "base": base}
    return None


def _lora_hint(source, ref, local, token):
    """What the source says a LoRA file is for: the Hugging Face repository's base model, else the
    base model of the same file on Civitai (looked up by its hash). None when neither tells."""
    hint = _hf_lora_hint(ref, token) if source == "hf" else None
    if hint is None and source in ("file", "hf"):
        import civitai
        try:
            found = _civitai_lookup(_sha256(str(local)))
        except Exception:
            found = None
        if found:
            hint = civitai.lora_hint(found.get("base_model"))
    return hint


def _civitai_by_hash(manifest, path):
    """Files from disk or Hugging Face that are also on Civitai: the author's trigger words (more
    reliable than the training metadata) and sample images for the preview. Optional (offline)."""
    if (manifest.get("source") or {}).get("type") == "civitai":
        return
    found = _civitai_lookup(manifest.get("sha256") or _sha256(str(path)))
    if not found:
        return
    if found["trigger_words"]:
        manifest["trigger_words"] = found["trigger_words"]
    manifest["civitai"] = {k: found[k] for k in ("model_id", "version_id", "name", "base_model", "images")}


def _add_preview(target, manifest_name, manifest, token):
    """The source's preview picture (Civitai sample image, image of the HF repo); optional."""
    try:
        import previews
        progress("Fetching preview picture")
        if previews.fetch_for(str(target), token):
            manifest["preview"] = previews.FILE
            manifest["preview_source"] = previews.source_of(manifest)
            with open(target / manifest_name, "w") as f:
                json.dump(manifest, f, indent=1)
    except Exception as e:
        print("no preview picture: %s" % e, file=sys.stderr)


def import_lora(source, ref, name, file=None, dry_run=False, token=None, root=None, meta_override=None,
                family_hint=None):
    """LoRA adapters are stored in the LoRA folder (<loras>/<name>/) with a lora.json."""
    local = ref
    tmp_dir = None
    if source == "hf":
        from huggingface_hub import hf_hub_download
        tmp_dir = loras_root(root) / (".download_" + safe_name(name))
        progress("Downloading LoRA")
        local = hf_hub_download(ref, file, local_dir=str(tmp_dir), token=token)
    try:
        if family_hint is None:
            family_hint = _lora_hint(source, ref, local, token)
        info = registry.inspect_lora(local, family_hint)
        label = "LoRA for " + registry.family_label(info["family"], info.get("variant"))
        if info.get("hint_mismatch"):
            # the file wins; the source's word is kept and shown
            said = info["hint"]
            note = "%s names %s, the file's layers are %s" % (
                {"civitai": "Civitai", "huggingface": "Hugging Face"}.get(said.get("source"), "The source"),
                said.get("base") or registry.family_label(said["family"], said.get("variant")),
                registry.family_label(info["family"], info.get("variant")))
            label += " (%s)" % note
            print("LoRA %s: %s" % (name, note), file=sys.stderr)
        if info["family"] in registry.FOREIGN_FAMILIES:
            label += registry.NO_RUNTIME_LABEL
        summary = {"type": "lora", "label": label, **info}
        if dry_run:
            emit("__import_info__", summary)
            return summary
        target = loras_root(root) / safe_name(name)
        if target.exists():
            raise FileExistsError("A LoRA named %s already exists" % target.name)
        target.mkdir(parents=True)
        try:
            dst = target / "lora.safetensors"
            if tmp_dir:
                os.replace(local, dst)
            else:
                _link_or_copy(local, dst)
            manifest = {"type": "lora", "format_version": FORMAT_VERSION, "name": target.name, "file": dst.name,
                        "sha256": _sha256(str(dst)), "source": {"type": source, "ref": ref, "file": file},
                        "imported_at": int(time.time()), **info, **(meta_override or {})}
            _civitai_by_hash(manifest, dst)
            with open(target / LORA_MANIFEST, "w") as f:
                json.dump(manifest, f, indent=1)
        except BaseException:
            # a half-made folder would block the next attempt ("already exists")
            shutil.rmtree(target, ignore_errors=True)
            raise
        _add_preview(target, LORA_MANIFEST, manifest, token)
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
    emit("__import_done__", {"model_path": str(target), "manifest": manifest})
    return manifest


def _check_base_access(repo, token):
    if not repo:
        return
    from huggingface_hub import auth_check
    from huggingface_hub.utils import GatedRepoError
    try:
        auth_check(repo, token=token)
    except GatedRepoError:
        raise PermissionError("This model needs the base components of %s, which is gated on Hugging Face. "
                              "Accept its licence at https://huggingface.co/%s (with the account of your "
                              "Hugging Face token) and import again." % (repo, repo))


def import_civitai(ref, name, quant="auto", dry_run=False, force=False, token=None, root=None):
    import civitai
    civ_token = os.environ.get("CIVITAI_TOKEN") or None
    progress("Asking Civitai")
    c = civitai.resolve(ref, civ_token)
    name = name or c["name"]
    is_lora = c["type"].lower() in ("lora", "locon", "dora", "lycoris")
    if dry_run:
        summary = {"type": "lora" if is_lora else "checkpoint", "source": "civitai",
                   "label": "%s · %s (%s)" % (c["name"], c["version_name"], c["base_model"]),
                   "arch": c["arch"], "download_gb": round(c["size_bytes"] / 1024 ** 3, 1),
                   "file": c["file_name"], "trigger_words": c["trigger_words"], "note": c.get("note") or ""}
        if not is_lora and c["arch"] in registry.ARCHS:
            spec = registry.ARCHS[c["arch"]]
            # a single file: GGUF and FP8 (stored as 8 bit GGUF) take the size of the file; where it does not fit,
            # the denoiser streams from the SSD
            fixed = (c["file_name"] or "").lower().endswith(".gguf") or str(c.get("precision") or "").startswith("fp8")
            summary["plan"] = make_plan({"arch": c["arch"], "components": spec["fallback_params"], "file": c["file_name"],
                                         "denoiser": spec["denoiser"], "layout": "single_denoiser",
                                         "denoiser_fixed_gb": c["size_bytes"] / 1024 ** 3 if fixed else None}, quant)
            summary["label"] = "%s · %s" % (summary["label"], spec["label"])
        emit("__import_info__", summary)
        return summary

    if not is_lora and c["arch"] in registry.ARCHS:
        # single files need the base components of a (possibly gated) repo: check that before
        # downloading gigabytes from Civitai
        _check_base_access(registry.ARCHS[c["arch"]].get("base_repo"), token)
    if c.get("note"):
        progress("Version %s · %s" % (c["version_name"], c["note"][:200]))
    downloads = Path(root or models_root()) / ".downloads"
    ensure_space(str(downloads.parent), c["size_bytes"] * 2, c["file_name"])
    companions = {}
    for extra in c.get("extras") or []:
        companions[extra["part"]] = civitai.download(extra, str(downloads), civ_token,
                                                     progress=lambda p, e=extra: progress("Downloading %s" % e["file_name"], p))
    local = civitai.download(c, str(downloads), civ_token,
                             progress=lambda p: progress("Downloading from Civitai", p))
    source_meta = {"source": {"type": "civitai", "ref": ref, "model_id": c["model_id"], "version_id": c["version_id"],
                              "base_model": c["base_model"], "file": c["file_name"], "images": c["images"][:8]}}
    try:
        if is_lora or _single_file_is_lora("file", local, None, None):
            extra = dict(source_meta)
            if c["trigger_words"]:
                extra["trigger_words"] = c["trigger_words"]
            result = import_lora("file", local, name, root=root, meta_override=extra,
                                 family_hint=civitai.lora_hint(c["base_model"]) or False)
        else:
            if c["trigger_words"]:
                source_meta["trigger_words"] = c["trigger_words"]  # shown with the model in the picker
            import maker_settings
            source_meta["maker_settings"] = {"settings": maker_settings.parse(c.get("card") or ""), "source": "civitai description"}
            result = run_import("file", local, name, quant=quant, force=force, token=token, root=root,
                                meta_override=source_meta, companions=companions)
    except registry.UnsupportedModel as e:
        # the downloads stay in .downloads: the next attempt (after an update) skips them
        raise registry.UnsupportedModel("%s. The downloaded files are kept in %s" % (e, downloads))
    for path in [local] + list(companions.values()):
        if path and os.path.exists(path):
            os.remove(path)  # imported (hard link or copy)
    return result


def register_in_place(model_dir, dry_run=False):
    """A folder that already is an imported model (it has a model.json, e.g. imported on another
    disk or by another copy of the app) is used where it is: nothing is copied or downloaded."""
    with open(os.path.join(model_dir, MANIFEST)) as f:
        manifest = json.load(f)
    if manifest.get("engine") != "diffusers" or manifest.get("arch") not in registry.ARCHS:
        raise registry.UnsupportedModel("This folder's model.json is not a model this app can use")
    spec = registry.ARCHS[manifest["arch"]]
    if dry_run:
        summary = {"arch": manifest["arch"], "label": spec["label"], "layout": "in place",
                   "plan": manifest.get("plan"), "download_gb": 0, "gated": False,
                   "components": manifest.get("components"), "in_place": True}
        emit("__import_info__", summary)
        return summary
    emit("__import_done__", {"model_path": os.path.abspath(model_dir), "manifest": manifest})
    return manifest


def import_photo_tool(source, ref, name, dry_run=False):
    """A photo tool (photo_tools.py): a recommended one by its id, or a model file from disk (ONNX, or PyTorch
    weights spandrel knows), checked first."""
    import photo_tools
    if dry_run:
        if source == "tool":
            spec = next((t for t in photo_tools.catalog() if t["id"] == ref), None)
            if spec is None:
                raise ValueError("Unknown photo tool: %s" % ref)
            summary = {"type": "photo_tool", "label": spec["name"], "download_gb": round(spec["size_mb"] / 1024, 2)}
        else:
            draft = photo_tools.inspect(ref)
            label = {"image": "Photo tool, %d×" % draft.get("scale", 1), "mask": "Photo tool (mask)"}.get(draft["kind"], "Photo tool")
            if draft.get("arch"):
                label += " (%s, GPU)" % draft["arch"]
            summary = {"type": "photo_tool", "label": label, "download_gb": 0}
        emit("__import_info__", summary)
        return summary
    if source == "tool":
        folder, manifest = photo_tools.install_recommended(ref, report=lambda m: progress(m))
    else:
        folder, manifest = photo_tools.import_file(ref, name, report=lambda m: progress(m))
    emit("__import_done__", {"model_path": folder, "manifest": manifest})
    return manifest


def run_import(source, ref, name, file=None, quant="auto", dry_run=False, force=False, token=None, root=None,
               meta_override=None, companions=None):
    token = token or os.environ.get("HF_TOKEN") or None
    if source == "merge":
        # LoRAs baked into a new model (merge.py); ref is the spec file the app wrote
        import merge
        if dry_run:
            summary = {"type": "merge", "label": "New model with LoRAs baked in", "download_gb": 0}
            emit("__import_info__", summary)
            return summary
        return merge.merge(ref, root)
    # toolfile: a model file chosen on the Enhance page (.pth and .safetensors would be checkpoints otherwise)
    if source in ("tool", "toolfile") or (source == "file" and ref.lower().endswith(".onnx")):
        return import_photo_tool(source, ref, name, dry_run=dry_run)
    if source in ("hf", "civitai", "file", "dir"):
        ensure_install_room(root or paths.models_dir())
    if source == "helper":
        import helpers
        if dry_run:
            h = next((x for x in helpers.catalog() if x["id"] == ref), None)
            if h is None:
                raise ValueError("Unknown helper model: %s" % ref)
            summary = {"type": "helper", "label": h["name"], "download_gb": round(h["size_mb"] / 1024, 2)}
            emit("__import_info__", summary)
            return summary
        folder = helpers.install(ref, report=lambda m: progress(m), token=token)
        emit("__import_done__", {"model_path": folder, "manifest": {"type": "helper", "id": ref}})
        return {"type": "helper"}
    if source == "civitai":
        return import_civitai(ref, name, quant=quant, dry_run=dry_run, force=force, token=token, root=root)
    if source == "file" and ref.lower().endswith((".ckpt", ".pt", ".pth")):
        return import_ckpt(ref, name, quant=quant, dry_run=dry_run, force=force, token=token, root=root,
                           meta_override=meta_override)
    if source == "hf" and file and file.lower().endswith(".ckpt"):
        # a .ckpt in a repo: downloaded, then read as plain weights like a local one
        from huggingface_hub import HfApi, hf_hub_download
        size = {s.rfilename: s.size for s in HfApi(token=token).model_info(ref, files_metadata=True).siblings}.get(file) or 0
        if dry_run:
            summary = {"type": "checkpoint", "label": "%s (%s, read after download)" % (file, ref),
                       "download_gb": round(size / 1024 ** 3, 1), "gated": False}
            emit("__import_info__", summary)
            return summary
        work = Path(root or models_root()) / ".downloads"
        ensure_space(str(work.parent), size * 2, file)
        with _ProgressWatcher(str(work), size, "Downloading model file"):
            local = hf_hub_download(ref, file, local_dir=str(work / safe_name(name or file)), token=token)
        try:
            meta = {"source": {"type": "hf", "ref": ref, "file": file}}
            meta.update(meta_override or {})
            return import_ckpt(local, name, quant=quant, force=force, token=token, root=root, meta_override=meta)
        finally:
            shutil.rmtree(work / safe_name(name or file), ignore_errors=True)
    if source == "dir" and is_diffusers_model_dir(ref):
        return register_in_place(ref, dry_run=dry_run)
    progress("Inspecting")
    if _single_file_is_lora(source, ref, file, token):
        return import_lora(source, ref, name, file=file, dry_run=dry_run, token=token, root=root)
    base_hint = ((meta_override or {}).get("source") or {}).get("base_model") or ""
    info = inspect(source, ref, file=file, token=token, name_hint=base_hint)
    if companions and info.get("layout") == "comfy_files":
        # files that came with the model replace the base repo's (no download for them)
        info["companions"] = {k: v for k, v in companions.items() if v and os.path.isfile(v)}
        info["base_files"] = {k: v for k, v in info["base_files"].items() if k not in info["companions"]}
    too_old = registry.runtime_too_old(info["arch"])
    if too_old:
        # before downloading gigabytes the installed runtime could not run
        raise registry.UnsupportedModel(too_old)
    plan = make_plan(info, quant)
    spec = registry.ARCHS[info["arch"]]
    summary = {"arch": info["arch"], "label": spec["label"], "layout": info["layout"], "plan": plan,
               "download_gb": round(info.get("download_bytes", 0) / 1024 ** 3, 1),
               "gated": bool(spec.get("gated")), "components": info["components"]}
    if dry_run:
        emit("__import_info__", summary)
        return summary
    if not plan["fits"] and not force:
        raise MemoryError("%s needs about %d GB RAM, this Mac has %d GB"
                          % (spec["label"], plan["min_ram_gb"], round(plan["ram_gb"])))
    if spec.get("gated") and info["layout"] != "repo":
        # the rest of the model comes from a gated repo: check access before copying gigabytes
        _check_base_access(info.get("base_repo"), token)

    target = Path(root or models_root()) / safe_name(name)
    if target.exists():
        raise FileExistsError("A model named %s already exists" % target.name)
    need = info.get("download_bytes", 0)
    if info["source"] == "file" and info["layout"] != "folder" and not registry.ARCHS[info["arch"]].get("native_files"):
        need += os.path.getsize(info["ref"])  # copied (hard links need no space, but may not be possible)
    ensure_space(str(target.parent), need, spec["label"])
    target.mkdir(parents=True)
    try:
        manifest = _materialize(info, target, token)
        manifest.update({
            "engine": "diffusers", "format_version": FORMAT_VERSION, "name": target.name,
            "arch": info["arch"], "family": spec["family"], "label": spec["label"],
            "denoiser": info["denoiser"], "components": info["components"],
            "quant_request": quant, "plan": plan, "min_ram_gb": plan["min_ram_gb"],
            "defaults": {**spec["defaults"], **info.get("overrides", {})},
            "resolutions": spec["resolutions"], "negative_prompt": spec["negative_prompt"],
            "img2img": bool(spec.get("img2img_pipeline")) or spec["family"] == "flux2" or bool(spec.get("img2img")),
            "runtime": spec.get("runtime") or "diffusers",
            "inpaint": bool(spec.get("inpaint_pipeline")), "inpaint_only": bool(spec.get("inpaint_only")),
            "content_filtered": bool(spec.get("content_filtered")),
            "kind": spec.get("kind") or "image",
            "source": {"type": source, "ref": ref, "file": file},
            "imported_at": int(time.time()), "imported_on": imported_on(),
        })
        manifest.update(meta_override or {})
        # the maker's recommended settings (model card, Civitai description) over the guessed defaults
        import maker_settings
        given = manifest.pop("maker_settings", None)
        if given is None and source == "hf":
            given = {"settings": maker_settings.from_hf(ref, token=token), "source": "hf model card"}
        elif given is None and manifest.get("sha256"):
            # a file from disk: its Civitai page, when the user allows the lookup (_civitai_lookup)
            v = _civitai_lookup(manifest["sha256"])
            if v and v.get("model_id"):
                ref_c = "https://civitai.com/models/%s?modelVersionId=%s" % (v["model_id"], v["version_id"])
                given = {"settings": maker_settings.from_civitai({"ref": ref_c}, os.environ.get("CIVITAI_TOKEN") or None),
                         "source": "civitai description (found by the file's SHA256)"}
        if given:
            maker_settings.apply(manifest, given.get("settings") or {}, given.get("source") or "")
        variant = registry.model_variant(manifest)
        if variant:
            manifest["sub_base"] = variant  # the sub-base its LoRAs must match (FLUX.2 [klein] 4B / 9B / [dev], Wan)
        if spec.get("user_loras") is False:
            manifest["user_loras"] = False
        if source == "file" and os.path.isfile(ref) and ref.lower().endswith(".safetensors"):
            _civitai_by_hash(manifest, ref)
        with open(target / MANIFEST, "w") as f:
            json.dump(manifest, f, indent=1)
        _add_preview(target, MANIFEST, manifest, token)
    except BaseException:
        shutil.rmtree(target, ignore_errors=True)
        raise
    emit("__import_done__", {"model_path": str(target), "manifest": manifest})
    return manifest


def ckpt_to_safetensors(src, dst):
    """A PyTorch .ckpt (pickle) as .safetensors. Read with weights_only=True: plain tensors and
    containers only, a file that wants to run code is refused instead of being executed."""
    import torch
    from safetensors.torch import save_file
    try:
        obj = torch.load(src, map_location="cpu", weights_only=True, mmap=True)
    except Exception as e:
        raise registry.UnsupportedModel("This .ckpt holds more than model weights (%s); use a .safetensors "
                                        "version of the model" % str(e).split("\n")[0][:120])
    state = obj.get("state_dict", obj) if isinstance(obj, dict) else None
    if not isinstance(state, dict):
        raise registry.UnsupportedModel("No model weights found in this .ckpt")
    tensors = {k: v.contiguous().clone() for k, v in state.items() if isinstance(v, torch.Tensor)}
    if not tensors:
        raise registry.UnsupportedModel("No model weights found in this .ckpt")
    save_file(tensors, dst, metadata={"format": "pt", "converted_from": "ckpt"})


def import_ckpt(path, name, quant="auto", dry_run=False, force=False, token=None, root=None, meta_override=None):
    work = Path(root or models_root()) / ".converting"
    work.mkdir(parents=True, exist_ok=True)
    tmp = work / (safe_name(name or os.path.basename(path)) + ".safetensors")
    try:
        ensure_space(str(work), os.path.getsize(path), "converting " + os.path.basename(path))
        progress("Reading the .ckpt file")
        ckpt_to_safetensors(path, str(tmp))
        meta = {"source": {"type": "file", "ref": path, "file": None}, "converted_from": "ckpt"}
        meta.update(meta_override or {})
        return run_import("file", str(tmp), name, quant=quant, dry_run=dry_run, force=force, token=token,
                          root=root, meta_override=meta)
    finally:
        if tmp.exists():
            tmp.unlink()  # the import holds a hard link (or copy)


def base_file_source(base_repo, value):
    """A comfy base file: "path" in the model's base repo, or "owner/repo::path" in another repo."""
    repo, _, path = value.rpartition("::")
    return (repo or base_repo), path


def _existing_base_file(target, repo_file, size, sha256, folders=("base",)):
    """The same file already downloaded for another imported model (e.g. a shared text encoder): the same path in
    the repo, the same size and the same content (SHA-256 as the Hub lists it; without one nothing is taken over)."""
    if not size or not sha256:
        return None
    for other in Path(target).parent.iterdir():
        if other == Path(target) or not other.is_dir():
            continue
        for folder in folders:
            p = other / folder / repo_file
            if p.is_file() and p.stat().st_size == size and _sha256(str(p)) == sha256.lower():
                return p
    return None


def _reuse_repo_files(info, target):
    """Copies (or links) the files of a repo import that another model already has, e.g. the text encoder a
    single-file import of the same model downloaded as its base; returns the files still to download."""
    sizes = info.get("file_sizes") or {}
    hashes = info.get("file_sha256") or {}
    if not sizes:
        return info["files"]
    left = []
    for f in info["files"]:
        found = _existing_base_file(target, f, sizes.get(f), hashes.get(f), folders=("base", "weights"))
        if found and f.endswith((".safetensors", ".bin")):
            dst = target / "weights" / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            progress("Taking %s from %s" % (os.path.basename(f), found.parent.parent.name), -1)
            _link_or_copy(str(found), str(dst))
        else:
            left.append(f)
    return left


def _download_single_file(info, target, token):
    """The model file of an import from a Hugging Face repo, into <target>/file/. A GGUF file was
    recognised by its name only: its header must name the same architecture."""
    from huggingface_hub import hf_hub_download
    with _ProgressWatcher(str(target), info.get("download_bytes", 0), "Downloading model file"):
        path = hf_hub_download(info["ref"], info["file"], local_dir=str(target / "file"), token=token)
    if path.lower().endswith(".gguf"):
        arch = registry.detect_from_single_file(registry.read_gguf_header(path), info["file"])[0]
        if arch != info["arch"]:
            raise registry.UnsupportedModel("File content (%s) does not match its name (%s)" % (arch, info["arch"]))
    return path


def _materialize_comfy(info, target, token):
    """Diffusion model, text encoder and VAE as files ComfyUI loads as they are: the model (linked or
    copied), the text encoder / VAE that came with it, else the base files (downloaded once, or linked
    when another imported model already has the same file)."""
    from huggingface_hub import hf_hub_download
    ext = os.path.splitext(info.get("file") or info["ref"])[1].lower() or ".safetensors"  # .gguf stays .gguf
    dst = target / ("diffusion_model" + ext)
    if info["source"] == "hf":
        os.replace(_download_single_file(info, target, token), dst)
        shutil.rmtree(target / "file", ignore_errors=True)
    else:
        progress("Copying")
        _link_or_copy(info["ref"], dst)
    files = {"diffusion_model": dst.name}
    for part, path in (info.get("companions") or {}).items():
        _link_or_copy(path, target / (part + ".safetensors"))
        files[part] = part + ".safetensors"
    base = info.get("base_files") or {}
    sizes = info.get("base_sizes") or {}
    for part, value in base.items():
        repo, repo_file = base_file_source(info["base_repo"], value)
        local = target / "base" / repo_file
        found = _existing_base_file(target, repo_file, sizes.get(part), (info.get("base_sha256") or {}).get(part))
        if found:
            local.parent.mkdir(parents=True, exist_ok=True)
            _link_or_copy(str(found), local)
        else:
            progress("Downloading %s" % os.path.basename(repo_file), -1)
            local = hf_hub_download(repo, repo_file, local_dir=str(target / "base"), token=token)
        # both resolved: the download returns a real path, the models folder may be a symlink
        files[part] = os.path.relpath(os.path.realpath(local), os.path.realpath(target))
    return {"layout": "comfy_files", "files": files, "file": files["diffusion_model"], "file_format": "safetensors",
            "sha256": _sha256(str(dst)), "base_repo": info["base_repo"]}


def _name_variant_indexes(weights_dir, variant):
    """fal's AuraFlow repos name their fp16 index "x.safetensors.fp16.index.json", diffusers looks for
    "x.safetensors.index.fp16.json": a copy under that name."""
    if not variant:
        return
    wrong = ".safetensors.%s.index.json" % variant
    for p in Path(weights_dir).glob("*/*" + wrong):
        right = p.with_name(p.name.replace(wrong, ".safetensors.index.%s.json" % variant))
        if not p.name.startswith("._") and not right.exists():
            shutil.copyfile(p, right)


def _materialize(info, target, token):
    layout = info["layout"]
    if layout == "comfy_files":
        return _materialize_comfy(info, target, token)
    if layout == "repo":
        left = _reuse_repo_files(info, target)
        sizes = info.get("file_sizes") or {}
        if left:  # an empty allow list would download the whole repo
            _download(info["ref"], left, str(target / "weights"), token,
                      sum(sizes.get(f, 0) for f in left) if sizes else info["download_bytes"], "Downloading")
        _name_variant_indexes(target / "weights", info["variant"])
        return {"layout": "repo", "weights_dir": "weights", "variant": info["variant"]}

    if layout == "folder":
        # large folders are used in place instead of duplicating tens of GB
        return {"layout": "repo", "weights_dir": os.path.abspath(info["ref"]), "variant": None}

    # single file layouts
    src = _download_single_file(info, target, token) if info["source"] == "hf" else info["ref"]
    ext = os.path.splitext(src)[1].lower()
    native_file = registry.ARCHS[info["arch"]].get("native_file")
    native_files = registry.ARCHS[info["arch"]].get("native_files")
    if native_files:
        # Ideogram 4: both transformer files stay as they are (FP8, mflux reads them), each in the
        # folder where mflux looks for it: hard links on the same disk, else links to where they are
        # (2 x 9.3 GB are not copied; the model needs them there)
        linked = {}
        for comp, rel in native_files.items():
            dst = target / "base" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if _link_or_symlink(info["native_sources"][comp], dst):
                linked[rel] = info["native_sources"][comp]
        dst = target / "base" / native_files[info["denoiser"]]
    elif native_file:
        # models run by mflux (Krea 2): the checkpoint stays as it is (FP8 included, MLX decodes it)
        # and goes where mflux looks for it, next to the base components
        (target / "base").mkdir(parents=True, exist_ok=True)
        dst = target / "base" / native_file
        if info["source"] == "hf":
            os.replace(src, dst)
            shutil.rmtree(target / "file", ignore_errors=True)
        else:
            progress("Copying")
            _link_or_copy(src, dst)
    elif ext == ".safetensors" and convert_gguf.needs_conversion(src):
        # the Apple GPU can not compute in FP8: store it as 8 bit GGUF instead (converted one tensor at a time; half
        # the size of 16 bit, and it still streams from the SSD on a Mac too small for it)
        if info["layout"] != "single_denoiser":
            raise registry.UnsupportedModel("FP8 checkpoints are only supported for FLUX, Chroma, Z-Image and SD 3.5 transformers")
        ext = ".gguf"
        dst = target / "model.gguf"
        progress("Converting FP8 to GGUF", 0)
        convert_gguf.convert(src, str(dst), "Q8_0", progress=lambda p: progress("Converting FP8 to GGUF", p))
        if info["source"] == "hf":
            shutil.rmtree(target / "file", ignore_errors=True)
    else:
        dst = target / ("model" + ext)
        if info["source"] == "hf":
            os.replace(src, dst)
            shutil.rmtree(target / "file", ignore_errors=True)
        else:
            progress("Copying")
            _link_or_copy(src, dst)
    sha = _sha256(str(dst))

    base_dir = target / "base"
    api, sizes = _hf_repo_info(info["base_repo"], token)
    model_index = _hf_json(info["base_repo"], "model_index.json", token)
    files, variant = _repo_plan_files(list(sizes), model_index)
    den = info["denoiser"]
    if info["layout"] == "single_full":
        files = [f for f in files if not f.endswith(WEIGHT_EXTS)]  # configs + tokenizers only
        variant = None
    else:
        files = [f for f in files if not _is_replaced(f, list(native_files or [den]))]
    _download(info["base_repo"], files, str(base_dir), token, sum(sizes.get(f, 0) for f in files),
              "Downloading base components")
    out = {"layout": info["layout"], "file": str(dst.relative_to(target)), "file_format": ext.lstrip("."), "sha256": sha,
           "base_dir": "base", "base_repo": info["base_repo"], "variant": variant}
    if native_files and linked:
        out["linked_files"] = linked  # symbolic links to the user's files (checked when loading)
    return out


# ------------------------------------------------------------ base components of single-file models

# Chroma's base as lodestones/Chroma1-HD lays it out. Its T5 encoder, T5 tokenizer and VAE are the very files of
# FLUX.1's text_encoder_2, tokenizer_2 and vae (the same SHA256 on Hugging Face), so the base of a Chroma checkpoint
# imported as FLUX.1 becomes Chroma's without a download (chroma_base_from_flux1)
CHROMA_MODEL_INDEX = {
    "_class_name": "ChromaPipeline", "_diffusers_version": "0.35.1",
    "feature_extractor": [None, None], "image_encoder": [None, None],
    "scheduler": ["diffusers", "FlowMatchEulerDiscreteScheduler"],
    "text_encoder": ["transformers", "T5EncoderModel"], "tokenizer": ["transformers", "T5TokenizerFast"],
    "transformer": ["diffusers", "ChromaTransformer2DModel"], "vae": ["diffusers", "AutoencoderKL"],
}
CHROMA_TRANSFORMER_CONFIG = {
    "_class_name": "ChromaTransformer2DModel", "_diffusers_version": "0.35.1",
    "approximator_hidden_dim": 5120, "approximator_layers": 5, "approximator_num_channels": 64,
    "attention_head_dim": 128, "axes_dims_rope": [16, 56, 56], "in_channels": 64, "joint_attention_dim": 4096,
    "num_attention_heads": 24, "num_layers": 19, "num_single_layers": 38, "out_channels": None, "patch_size": 1,
}


def chroma_scheduler_config(flash=False):
    """Chroma1-HD's scheduler (shift 3); Chroma1-Flash's has shift 1."""
    return {
        "_class_name": "FlowMatchEulerDiscreteScheduler", "_diffusers_version": "0.35.1",
        "base_image_seq_len": 256, "base_shift": 0.5, "invert_sigmas": False, "max_image_seq_len": 4096,
        "max_shift": 1.15, "num_train_timesteps": 1000, "shift": 1.0 if flash else 3.0, "shift_terminal": None,
        "stochastic_sampling": False, "time_shift_type": "exponential", "use_beta_sigmas": False,
        "use_dynamic_shifting": False, "use_exponential_sigmas": False, "use_karras_sigmas": False,
    }


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _has_weights(folder):
    return folder.is_dir() and any(p.suffix == ".safetensors" and not p.name.startswith("._") for p in folder.iterdir())


FLUX1_LEFTOVERS = "flux1_unused"


def chroma_base_from_flux1(base_dir, flash=False):
    """The base folder of a Chroma checkpoint that was imported as FLUX.1 (FLUX.1 [schnell]'s parts) made Chroma's,
    without a download: text_encoder_2 / tokenizer_2 (T5) become text_encoder / tokenizer, Chroma's configs are
    written, and what Chroma does not use (FLUX.1's CLIP encoder and configs) goes to flux1_unused/ - nothing is
    deleted. Each step can run again after an interruption. Returns True when the folder is Chroma's afterwards."""
    base = Path(base_dir)
    try:
        cls = _load_json(base / "model_index.json").get("_class_name")
    except (OSError, ValueError):
        return False
    if cls == "ChromaPipeline":
        return True
    if cls != "FluxPipeline":
        return False
    t5 = base / ("text_encoder_2" if (base / "text_encoder_2").is_dir() else "text_encoder")
    tok = base / ("tokenizer_2" if (base / "tokenizer_2").is_dir() else "tokenizer")
    try:
        is_t5 = _load_json(t5 / "config.json").get("model_type") == "t5"
    except (OSError, ValueError):
        is_t5 = False
    if not (is_t5 and _has_weights(t5) and tok.is_dir() and _has_weights(base / "vae")):
        return False
    unused = base / FLUX1_LEFTOVERS
    unused.mkdir(exist_ok=True)
    for own, flux_name in (("text_encoder", "text_encoder_2"), ("tokenizer", "tokenizer_2")):
        if (base / flux_name).is_dir():
            if (base / own).exists():
                if (unused / own).exists():
                    return False  # not a state these steps leave behind: left as it is
                os.rename(base / own, unused / own)  # FLUX.1's CLIP encoder / tokenizer
            os.rename(base / flux_name, base / own)
    index = base / "transformer" / "diffusion_pytorch_model.safetensors.index.json"
    if index.exists():  # FLUX.1's shard list; the transformer is the model's own file
        (unused / "transformer").mkdir(exist_ok=True)
        os.replace(index, unused / "transformer" / index.name)
    for rel in ("transformer/config.json", "scheduler/scheduler_config.json", "model_index.json"):
        if (base / rel).exists() and not (unused / rel).exists():
            (unused / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(base / rel, unused / rel)
    _write_json(base / "transformer" / "config.json", CHROMA_TRANSFORMER_CONFIG)
    _write_json(base / "scheduler" / "scheduler_config.json", chroma_scheduler_config(flash))
    _write_json(base / "model_index.json", CHROMA_MODEL_INDEX)  # last: until here a new run starts over
    return True


def _base_folder(model_dir, m):
    p = m.get("base_dir") or "base"
    return Path(p if os.path.isabs(p) else os.path.join(model_dir, p))


def base_problem(model_dir, m):
    """What is missing from the base parts (text encoders, tokenizers, VAE, configs) of a single-file model, or None
    when nothing is. Checked offline: the base's model_index.json names the model's pipeline, and every part it
    lists has its folder, with weights for the encoders and the VAE (the denoiser is the model's own file)."""
    spec = registry.ARCHS.get(m.get("arch")) or {}
    if m.get("layout") != "single_denoiser" or not spec.get("pipeline") or spec.get("runtime"):
        return None
    base = _base_folder(model_dir, m)
    try:
        model_index = _load_json(base / "model_index.json")
    except (OSError, ValueError):
        return "its base parts are missing"
    cls = model_index.get("_class_name")
    if cls not in (spec["pipeline"], spec.get("img2img_pipeline"), spec.get("inpaint_pipeline")):
        return "its base parts are those of %s, not %s" % (cls, spec["label"])
    den = m.get("denoiser") or spec["denoiser"]
    for comp in [k for k, v in model_index.items() if isinstance(v, list) and len(v) == 2 and v[1]]:
        folder = base / comp
        if not folder.is_dir():
            return "its %s is missing" % comp
        if comp in _component_names(model_index) and comp != den and not _has_weights(folder):
            return "the weights of its %s are missing" % comp
    return None


def ensure_base(model_dir, m, token=None, report=None):
    """Completes the base parts of an installed single-file model (base_problem): a Chroma checkpoint imported as
    FLUX.1 takes FLUX.1's T5 and VAE (chroma_base_from_flux1), else what is missing is downloaded from its base
    repository; a base made for another pipeline is kept aside as <base>_<pipeline>. Returns True when something
    changed. report(stage, percent) shows the progress."""
    problem = base_problem(model_dir, m)
    if problem is None:
        return False
    spec = registry.ARCHS[m["arch"]]
    base = _base_folder(model_dir, m)
    src = m.get("source") or {}
    names = " ".join(str(x) for x in (m.get("name"), src.get("ref"), src.get("file")) if x)
    if m["arch"] == "chroma" and chroma_base_from_flux1(base, flash=registry.is_chroma_flash(names)) \
            and base_problem(model_dir, m) is None:
        return True
    try:
        cls = _load_json(base / "model_index.json").get("_class_name")
    except (OSError, ValueError):
        cls = None
    if cls and cls not in (spec["pipeline"], spec.get("img2img_pipeline"), spec.get("inpaint_pipeline")):
        aside = base.with_name("%s_%s" % (base.name, cls))
        if aside.exists():
            raise registry.UnsupportedModel("The base parts of %s are those of %s, and %s is taken" % (
                m.get("name"), cls, aside))
        os.rename(base, aside)
    repo = m.get("base_repo") or _base_repo(m["arch"], (m.get("components") or {}).get(spec["denoiser"]), names)
    if report:
        report("Completing the base parts (%s)" % problem, -1)
    def failed(e):
        if "401" in str(e) or "403" in str(e) or type(e).__name__ in ("GatedRepoError", "RepositoryNotFoundError"):
            return registry.UnsupportedModel(
                "%s: %s, and %s needs an access token: accept its licence on Hugging Face and enter the token in "
                "Settings → Access tokens" % (m.get("name") or spec["label"], problem, repo))
        return registry.UnsupportedModel(
            "%s: %s, and they could not be downloaded from %s (%s). Connect to the internet and generate again, or "
            "import it again (Models → Installed: move it to the Trash; Models → Recommended or Add: import it)"
            % (m.get("name") or spec["label"], problem, repo, str(e)[:200]))

    try:
        sizes = _hf_repo_info(repo, token)[1]
        model_index = _hf_json(repo, "model_index.json", token)
    except Exception as e:
        raise failed(e)
    files, _ = _repo_plan_files(list(sizes), model_index)
    files = [f for f in files if not _is_replaced(f, [m.get("denoiser") or spec["denoiser"]])]
    missing = [f for f in files
               if not ((base / f).is_file() and (not sizes.get(f) or (base / f).stat().st_size == sizes[f]))]
    total = sum(sizes.get(f, 0) for f in missing)
    ensure_space(str(base.parent), total, "the base parts of %s" % spec["label"])
    if missing:
        from huggingface_hub import snapshot_download
        base.mkdir(parents=True, exist_ok=True)
        try:
            with _ProgressWatcher(str(base), total, "Downloading base parts", report=report, count_existing=False):
                snapshot_download(repo, local_dir=str(base), allow_patterns=missing, token=token)
        except Exception as e:
            raise failed(e)
    problem = base_problem(model_dir, m)
    if problem:
        raise registry.UnsupportedModel("%s: %s after downloading them from %s"
                                        % (m.get("name") or spec["label"], problem, repo))
    return True


def migrate_fp8(model_dir, progress_cb=None):
    """Converts an FP8 single-file import (made before FP8 was handled) to GGUF, once.
    Returns True when the manifest changed."""
    path = os.path.join(model_dir, MANIFEST)
    with open(path) as f:
        m = json.load(f)
    if m.get("layout") != "single_denoiser" or m.get("file_format") != "safetensors" \
            or registry.ARCHS.get(m.get("arch"), {}).get("native_file"):  # mflux decodes FP8 itself
        return False
    src = m["file"] if os.path.isabs(m["file"]) else os.path.join(model_dir, m["file"])
    if not convert_gguf.needs_conversion(src):
        return False
    dst = os.path.join(model_dir, "model.gguf")
    tmp = dst + ".partial"
    convert_gguf.convert(src, tmp, "Q8_0", progress=progress_cb)
    os.replace(tmp, dst)
    # converted on this Mac (the app only runs models imported on it)
    m.update(file="model.gguf", file_format="gguf", sha256=_sha256(dst), converted_from="fp8 safetensors",
             imported_on=imported_on())
    with open(path + ".tmp", "w") as f:
        json.dump(m, f, indent=1)
    os.replace(path + ".tmp", path)
    # drop our FP8 copy only if the user's original still exists; otherwise it is the only copy
    original = (m.get("source") or {}).get("ref")
    if src.startswith(model_dir) and original and os.path.isfile(original) \
            and not os.path.samefile(original, src):
        os.remove(src)
    return True


def main(argv):
    p = argparse.ArgumentParser(prog="import_model")
    p.add_argument("--source", choices=["hf", "file", "dir", "civitai", "tool", "toolfile", "helper", "merge"], required=True)
    p.add_argument("--ref", required=True, help="HF repo id, file path or folder path")
    p.add_argument("--file", default=None, help="file inside the HF repo (single-file import)")
    p.add_argument("--name", default=None)
    p.add_argument("--quant", choices=["auto", "none", "q8", "q4"], default="auto")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="import even if the RAM plan does not fit")
    p.add_argument("--root", default=None, help="target folder (default: the models folder)")
    a = p.parse_args(argv)
    if a.source == "civitai":
        import civitai
        a.ref = civitai.public_ref(a.ref)  # a copied download link may carry the API key

    if a.name:
        name = a.name
    elif a.source in ("civitai", "tool", "toolfile", "helper", "merge"):
        name = None  # taken from the Civitai model name / the tool's id / the file's name
    else:
        name = default_name(a.source, a.ref, a.file)
    try:
        run_import(a.source, a.ref, name, file=a.file, quant=a.quant, dry_run=a.dry_run, force=a.force,
                   root=a.root)
    except registry.LoraFile as e:
        emit("__import_error__", {"code": "lora", "message": str(e)})
        sys.exit(4)
    except Exception as e:
        emit("__import_error__", {"code": type(e).__name__, "message": str(e)})
        raise
