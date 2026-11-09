# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Installed LoRAs and models checked again with the current detection (registry.lora_identity, model_variant,
is_chroma): a LoRA filed under the wrong family (a kohya FLUX.1 LoRA taken for SDXL, a Qwen-Image 2.1 LoRA for
Qwen-Image …), a missing sub-base (FLUX.2 [klein] 4B / 9B), a Chroma checkpoint filed as FLUX.1 [schnell] or marked
as not runnable before Chroma was supported (it becomes a Chroma model; its base takes FLUX.1's T5 and VAE over), the
label of a LoRA whose family became runnable (Z-Image) that still says no model can use it.

    python main.py recheck_loras            prints what would change (one JSON line each)
    python main.py recheck_loras --apply    changes it; each changed manifest is kept as <manifest>.bak

The app runs it once with --apply (src/main/migrate.ts). Works offline: the hint is the source's base model
the manifest already holds (Civitai), nothing is looked up.
"""
import argparse
import json
import os
import shutil
import sys

import paths
import registry

LORA_MANIFEST = "lora.json"
MODEL_MANIFEST = "model.json"


def _read(path):
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _hint(lm):
    """What the LoRA's source said it is for, as the manifest kept it (Civitai's base model)."""
    import civitai
    base = (lm.get("source") or {}).get("base_model") or (lm.get("civitai") or {}).get("base_model")
    return civitai.lora_hint(base) if base else None


def lora_changes(folder, lm):
    """{field: (old, new)} for a LoRA, or {"error": text} when its file can not be read or placed."""
    file = os.path.normpath(os.path.join(folder, lm.get("file") or "lora.safetensors"))
    if os.path.dirname(file) != os.path.normpath(folder):
        return {"error": "names a file outside its folder"}
    try:
        info = registry.inspect_lora(file, _hint(lm) or False)
    except (registry.UnsupportedModel, OSError, ValueError) as e:
        return {"error": str(e)}
    out = {}
    if lm.get("family") != info["family"]:
        out["family"] = (lm.get("family"), info["family"])
    if (lm.get("variant") or None) != (info.get("variant") or None) and (info.get("variant") or "family" in out):
        out["variant"] = (lm.get("variant"), info.get("variant"))
    label = lm.get("label")
    if isinstance(label, str) and label.endswith(registry.NO_RUNTIME_LABEL) and info["family"] not in registry.FOREIGN_FAMILIES:
        out["label"] = (label, label[:-len(registry.NO_RUNTIME_LABEL)])  # its family runs now (Z-Image)
    return out


def _single_file_shapes(path):
    if path.lower().endswith(".gguf"):
        with open(path, "rb") as f:
            data = f.read(64 * 1024 * 1024)
        try:
            return registry.parse_gguf_header(data)
        except registry.IncompleteHeader:
            return registry.read_gguf_header(path)
    return registry.read_safetensors_header(path)


def _is_chroma_file(folder, m):
    path = os.path.join(folder, m["file"])
    try:
        return os.path.isfile(path) and registry.is_chroma(_single_file_shapes(path))
    except (registry.UnsupportedModel, OSError, ValueError):
        return False


def chroma_manifest(folder, m, ram_gb=None):
    """The manifest fields of a Chroma checkpoint that was imported as FLUX.1 (or marked as not runnable before Chroma
    was supported), as an import of it would write them: arch, defaults (the file's name tells Flash), parts (T5
    only: FLUX.1's CLIP encoder is not used), memory plan."""
    import importer
    spec = registry.ARCHS["chroma"]
    src = m.get("source") or {}
    names = " ".join(str(x) for x in (src.get("file"), src.get("ref"), m.get("name")) if x)
    comps = dict(m.get("components") or {})
    # FLUX.1's T5 (text_encoder_2) is Chroma's text_encoder
    comps = {"text_encoder": comps.get("text_encoder_2") or spec["fallback_params"]["text_encoder"],
             "transformer": comps.get("transformer") or spec["fallback_params"]["transformer"],
             "vae": comps.get("vae") or spec["fallback_params"]["vae"]}
    gguf = str(m.get("file") or "").lower().endswith(".gguf")
    info = {"arch": "chroma", "components": comps, "denoiser": spec["denoiser"], "layout": m.get("layout"),
            "denoiser_fixed_gb": os.path.getsize(os.path.join(folder, m["file"])) / 1024 ** 3 if gguf else None}
    plan = importer.make_plan(info, m.get("quant_request") or "auto", ram_gb)
    return {"arch": "chroma", "family": "chroma", "label": spec["label"], "unsupported": None,
            "base_repo": importer._base_repo("chroma", comps["transformer"], names),
            "components": comps, "plan": plan, "min_ram_gb": plan["min_ram_gb"],
            "defaults": {**spec["defaults"], **registry.chroma_overrides(names)},
            "resolutions": spec["resolutions"], "negative_prompt": spec["negative_prompt"],
            "img2img": True, "inpaint": True, "inpaint_only": False, "runtime": "diffusers", "kind": "image"}


def model_changes(folder, m, ram_gb=None):
    """{field: (old, new)} for a model."""
    out = {}
    arch = m.get("arch")
    single = m.get("layout") == "single_denoiser" and m.get("file")
    # a Chroma checkpoint imported as FLUX.1, or marked as not runnable when Chroma was not supported yet
    if single and ((arch in ("flux1_schnell", "flux1_dev") and _is_chroma_file(folder, m))
                   or (arch == "chroma" and m.get("unsupported"))):
        for field, new in chroma_manifest(folder, m, ram_gb).items():
            if m.get(field) != new and not (new is None and field not in m):
                out[field] = (m.get(field), new)
        old_ram = (m.get("plan") or {}).get("ram_gb")
        if "plan" in out and not m.get("imported_on") and isinstance(old_ram, (int, float)):
            # the new plan is for this Mac; the Mac it was imported on stays known (src/main/foreign_mac.ts)
            out["imported_on"] = (None, {"ram_gb": int(old_ram + 0.5)})
        return out
    if arch in registry.ARCHS:
        variant = registry.model_variant(dict(m, variant=None, sub_base=None))
        if variant and m.get("sub_base") != variant:
            out["sub_base"] = (m.get("sub_base"), variant)
        # a sub-base written into "variant" (the file variant diffusers loads) goes back to what was there before
        if m.get("variant") in registry.SUB_BASES:
            out["variant"] = (m["variant"], _original_file_variant(folder))
        # an architecture that learned to repaint masks (FLUX.2 [klein] with its inpainting pipeline)
        if registry.ARCHS[arch].get("inpaint_pipeline") and m.get("inpaint") is False:
            out["inpaint"] = (False, True)
        if registry.ARCHS[arch].get("user_loras") is False and m.get("user_loras") is not False:
            out["user_loras"] = (m.get("user_loras"), False)
    return out


def _original_file_variant(folder):
    """The file variant of a model before a recheck wrote a sub-base over it: from its first backup, else none."""
    try:
        with open(os.path.join(folder, MODEL_MANIFEST + ".bak")) as f:
            return registry.file_variant(json.load(f))
    except (OSError, ValueError):
        return None


def _apply(path, data, changes):
    backup = path + ".bak"
    if not os.path.exists(backup):  # the first backup is the original
        shutil.copy2(path, backup)
    for field, (_, new) in changes.items():
        if new is None:
            data.pop(field, None)
        else:
            data[field] = new
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, path)


def _chroma_base(folder, data, apply):
    """What happens to the base parts of a model that becomes Chroma (importer.chroma_base_from_flux1): FLUX.1's T5
    and VAE are taken over without a download; parts that are missing are downloaded when it is first used."""
    import importer
    base = importer._base_folder(folder, data)
    try:
        cls = importer._load_json(base / "model_index.json").get("_class_name")
    except (OSError, ValueError):
        cls = None
    if cls == "ChromaPipeline":
        return None
    src = data.get("source") or {}
    flash = registry.is_chroma_flash(" ".join(str(x) for x in (src.get("file"), src.get("ref"), data.get("name")) if x))
    if apply and importer.chroma_base_from_flux1(base, flash=flash):
        return "FLUX.1's T5 text encoder and VAE taken over (FLUX.1's CLIP parts kept in %s)" % importer.FLUX1_LEFTOVERS
    if not apply and cls == "FluxPipeline" and (base / "text_encoder_2").is_dir():
        return "FLUX.1's T5 text encoder and VAE would be taken over (no download)"
    return "missing parts are downloaded from %s when it is first used" % importer._base_repo(
        "chroma", None, " ".join(str(x) for x in (src.get("file"), data.get("name")) if x))


def recheck(models_dir, loras_dir, apply=False, ram_gb=None):
    """[{"type", "folder", "name", "changes": {field: [old, new]}} or {…, "error"}] for every manifest that
    would change (or could not be checked); with apply=True the changes are written. ram_gb: the memory the plans
    of changed models are made for (default: this Mac's)."""
    report = []
    for kind, root, manifest, check in (("lora", loras_dir, LORA_MANIFEST, lora_changes),
                                        ("model", models_dir, MODEL_MANIFEST,
                                         lambda folder, m: model_changes(folder, m, ram_gb))):
        if not root or not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            folder = os.path.join(root, entry)
            path = os.path.join(folder, manifest)
            if entry.startswith(".") or not os.path.isfile(path):
                continue
            data = _read(path)
            if data is None:
                continue
            changes = check(folder, data)
            if not changes:
                continue
            item = {"type": kind, "folder": folder, "name": data.get("name") or entry}
            if "error" in changes:
                item["error"] = changes["error"]
            else:
                item["changes"] = {k: list(v) for k, v in changes.items()}
                if kind == "model" and (changes.get("arch", (None, None))[1] == "chroma" or "unsupported" in changes):
                    try:
                        base = _chroma_base(folder, data, apply)  # before the manifest: it names Chroma's parts
                    except OSError as e:
                        base = "not changed (%s): missing parts are downloaded when it is first used" % e
                    if base:
                        item["base"] = base
                if apply:
                    _apply(path, data, changes)
            report.append(item)
    return report


def main(argv):
    p = argparse.ArgumentParser(prog="recheck_loras")
    p.add_argument("--apply", action="store_true", help="write the changes (each manifest kept as .bak)")
    p.add_argument("--models", default=None, help="models folder (default: the app's)")
    p.add_argument("--loras", default=None, help="LoRA folder (default: the app's)")
    a = p.parse_args(argv)
    models = a.models or str(paths.models_dir())
    loras = a.loras or str(paths.loras_dir())
    report = recheck(models, loras, apply=a.apply)
    for item in report:
        print(json.dumps(item, ensure_ascii=False))
    changed = sum(1 for i in report if "changes" in i)
    print("%s %d manifest(s), %d could not be checked" % ("changed" if a.apply else "would change", changed,
                                                         len(report) - changed), file=sys.stderr)
    return 0
