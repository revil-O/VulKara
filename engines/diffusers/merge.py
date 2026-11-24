# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""LoRAs baked into a model: a new model of its own (a diffusers folder under the models folder) that needs no LoRA
any more. The base must hold its weights unquantized (a checkpoint, or a diffusers folder); GGUF, FP8 and NF4 files
can not take the LoRA's change without losing it. Everything runs on the CPU in 16 bit; the text encoders are only
loaded when a LoRA changes them, else their folders are linked (or copied) from the base. The LoRAs are read and
checked as the engine does it (engine.LoadedModel), so a file that would not fit there is refused here too.

The import queue runs it: import_model --source=merge --ref=<spec.json>, spec {"model": folder, "loras": [{"path":
LoRA folder, "scale"}], "name"} (LoRAs named by their folders, as jobs do).
"""
import json
import os
import shutil
import time
from pathlib import Path

import compat
import paths
import protocol
import registry

MANIFEST = "model.json"
QUANTIZED = (".gguf",)
TEXT_KINDS = ("text_encoder", "tokenizer")


def _emit(tag, payload):
    import importer
    importer.emit(tag, payload)


def _progress(message):
    import importer
    importer.progress(message)


def _read(path):
    with open(path) as f:
        return json.load(f)


def _folder_bytes(folder):
    total = 0
    for root, _, files in os.walk(folder):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def mergeable(m, folder):
    """None when the model can take LoRAs baked in, else why not (a sentence for the user)."""
    spec = registry.ARCHS.get(m.get("arch"))
    if not spec:
        return "This kind of model is not known to the app."
    if m.get("unsupported"):
        return m["unsupported"]
    if spec.get("runtime") == "comfyui" or m.get("layout") == "comfy_files":
        return "%s models run in ComfyUI; LoRAs can not be baked into them here." % spec["label"]
    if spec.get("user_loras") is False or m.get("user_loras") is False:
        return "%s takes no LoRAs." % spec["label"]
    if m.get("layout") == "single_denoiser":
        f = str(m.get("file") or "").lower()
        if f.endswith(QUANTIZED) or any(t in f for t in ("fp8", "nf4", "q4", "q8")):
            return ("%s is stored compressed (%s): baking a LoRA in needs the full weights. Import the model "
                    "unquantized (its original safetensors or diffusers folder) and bake into that."
                    % (m.get("name", "This model"), os.path.basename(f)))
    if m.get("layout") not in ("repo", "single_full", "single_denoiser"):
        return "This model's layout (%s) can not take LoRAs baked in." % m.get("layout")
    return None


def _text_parts(lora_files):
    """Whether any of the LoRAs changes a text encoder (then the encoders are loaded and saved anew)."""
    import engine
    for f in lora_files:
        keys = registry.read_safetensors_header(f).keys()
        if any(k.startswith(engine.LoadedModel.TEXT_ENCODER_LORA_PREFIXES) or "text_encoder" in k for k in keys):
            return True
    return False


def _need_gb(m, folder, with_text):
    """The weights the merge holds in memory at 16 bit, in GB (from the manifest's components, else the files)."""
    comps = m.get("components") or {}
    if comps:  # parameters in billions, 2 bytes each at 16 bit
        import memory
        return memory.BYTES_PER_PARAM["none"] * sum(v for k, v in comps.items()
                                                    if with_text or not k.startswith("text_encoder"))
    if m.get("file"):
        return os.path.getsize(os.path.join(folder, m["file"])) / 1e9
    return _folder_bytes(folder) / 1e9


def _check_memory(need_gb):
    import psutil
    free = psutil.virtual_memory().available / 1e9
    # the weights, the LoRAs' layers and one copy of the largest tensors while fusing
    if need_gb * 1.3 > free:
        raise MemoryError("Baking needs about %.0f GB of free memory, %.0f GB are free now. Close other apps or "
                          "unload the model in use, then try again." % (need_gb * 1.3, free))


def _plain_name(f, variant):
    """model.fp16.safetensors -> model.safetensors, model.fp16-00001-of-00002.safetensors -> model-00001-of-00002...,
    model.safetensors.index.fp16.json -> model.safetensors.index.json"""
    if not variant:
        return f
    return f.replace(".%s." % variant, ".").replace(".%s-" % variant, "-")


def _link_or_copy(src, dst, variant=None):
    """A folder of the base taken over unchanged: hard links where the disk allows them (no space), else a copy.
    Files of the base's variant (fp16) get the plain names, as the new model is read without a variant."""
    for root, _, files in os.walk(src):
        rel = os.path.relpath(root, src)
        os.makedirs(os.path.join(dst, rel), exist_ok=True)
        for f in files:
            if f.startswith("._"):  # macOS' companions on exFAT drives
                continue
            name = _plain_name(f, variant)
            if name != f and name in files:  # the plain file is there too and taken itself
                continue
            a, b = os.path.join(root, f), os.path.join(dst, rel, name)
            if name != f and f.endswith(".json"):  # a shard index names its shards
                with open(a) as fh:
                    text = fh.read()
                with open(b, "w") as fh:
                    fh.write(text.replace(".%s-" % variant, "-").replace(".%s." % variant, "."))
                continue
            try:
                os.link(a, b)
            except OSError:
                shutil.copy2(a, b)


def _load_pipeline(m, folder, spec, dtype, with_text):
    """The base on the CPU at 16 bit; without its text encoders when no LoRA changes them (repo layout)."""
    import diffusers
    cls = getattr(diffusers, spec["pipeline"])
    kw = dict(spec.get("pipeline_kwargs", {}))
    if m["layout"] == "single_full":
        return cls.from_single_file(os.path.join(folder, m["file"]), config=os.path.join(folder, m["base_dir"]),
                                    dtype=dtype, **kw), None
    weights = os.path.join(folder, m["weights_dir"] if m["layout"] == "repo" else m["base_dir"])
    index = _read(os.path.join(weights, "model_index.json"))
    skipped = []
    if not with_text:
        for comp in index:
            if comp.startswith(TEXT_KINDS):
                kw[comp] = None
                skipped.append(comp)
    variant = registry.file_variant(m)
    if variant:
        kw["variant"] = variant
    if m["layout"] == "single_denoiser":
        den = m["denoiser"]
        den_cls = getattr(diffusers, spec["denoiser_class"])
        kw[den] = den_cls.from_single_file(os.path.join(folder, m["file"]), config=weights, subfolder=den, dtype=dtype)
    return cls.from_pretrained(weights, dtype=dtype, **kw), (weights, skipped)


def merge(spec_path, models_dir=None):
    """Bakes the LoRAs of a spec into a new model; emits __import_done__ like an import. Returns the manifest."""
    import torch
    import engine
    import importer
    job = _read(spec_path)
    base_dir = os.path.realpath(job["model"])
    m = _read(os.path.join(base_dir, MANIFEST))
    why = mergeable(m, base_dir)
    if why:
        raise ValueError(why)
    spec = registry.ARCHS[m["arch"]]
    # the engine's own reading: the file inside each LoRA's folder, refused when it does not fit the model
    chosen = [l for l in job.get("loras") or [] if l.get("path") and float(l.get("scale", 1)) != 0]
    loras = engine.DiffusersEngine._resolve_loras(chosen, spec, m)
    if not loras:
        raise ValueError("Choose at least one LoRA to bake in")
    name = importer.safe_name(job.get("name") or "%s_%s" % (m.get("name", "model"), "_".join(l.get("name", "lora") for l in loras)))
    root = Path(models_dir or importer.models_root())
    target = root / name
    if target.exists():
        raise FileExistsError("A model named %s already exists" % name)
    with_text = _text_parts([l["file"] for l in loras])
    need = _need_gb(m, base_dir, with_text)
    _check_memory(need)
    importer.ensure_space(str(root), int(need * 1e9), spec["label"])
    dtype = torch.float16 if spec["family"] in ("sd1", "sd2", "sdxl") else torch.bfloat16

    _progress("Loading %s" % m.get("name", "the model"))
    pipe, kept = _load_pipeline(m, base_dir, spec, dtype, with_text)
    shim = object.__new__(engine.LoadedModel)  # the engine's LoRA reading and checks, without loading a model
    shim.m, shim.spec = m, spec
    names = []
    for i, l in enumerate(loras):
        _progress("Reading LoRA %s" % l.get("name", i + 1))
        n = "bake%d" % i
        engine._check_lora_format(l)
        engine.LoadedModel._load_lora(pipe, l["file"], n, drop_text_encoder=not with_text)
        shim._check_applied(pipe, l, n)
        names.append(n)
    _progress("Baking in")
    pipe.set_adapters(names, adapter_weights=[float(l.get("scale", 1)) for l in loras])
    pipe.fuse_lora(adapter_names=names, lora_scale=1.0)
    pipe.unload_lora_weights()

    for old in root.glob(".baking_*"):  # left by a bake that was stopped hard (imports run one at a time)
        shutil.rmtree(old, ignore_errors=True)
    work = root / (".baking_" + name)
    work.mkdir(parents=True)
    _stop_on_sigterm()
    try:
        weights = work / "weights"
        _progress("Saving the new model")
        if kept and kept[1]:
            # the text encoders were not loaded: saved without them, then their folders taken over from the base
            src, skipped = kept
            compat.drop_chat_templates(pipe)
            pipe.save_pretrained(str(weights), safe_serialization=True)
            index = _read(os.path.join(src, "model_index.json"))
            for comp in skipped:
                if os.path.isdir(os.path.join(src, comp)):
                    _link_or_copy(os.path.join(src, comp), str(weights / comp), registry.file_variant(m))
            with open(weights / "model_index.json", "w") as f:
                json.dump(index, f, indent=2)
        else:
            compat.drop_chat_templates(pipe)
            pipe.save_pretrained(str(weights), safe_serialization=True)
        del pipe
        manifest = _manifest(m, base_dir, work, loras, importer, name)
        with open(work / MANIFEST, "w") as f:
            json.dump(manifest, f, indent=1)
        os.rename(work, target)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    _emit("__import_done__", {"model_path": str(target), "manifest": manifest})
    return manifest


def _stop_on_sigterm():
    """Cancelling an import sends SIGTERM; raised as SystemExit, so the half-written model is removed."""
    import signal
    import sys
    try:
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    except ValueError:  # not the main thread (tests)
        pass


def _manifest(m, base_dir, target, loras, importer, name=None):
    """The new model's model.json: what the importer writes for a diffusers folder, with where it came from.
    target: the folder being written; name: the model's name (the folder it is renamed to)."""
    info = importer.inspect("dir", str(target / "weights"))
    plan = importer.make_plan(info, "auto")
    spec = registry.ARCHS[info["arch"]]
    manifest = {
        "layout": "repo", "weights_dir": "weights", "variant": None,
        "engine": "diffusers", "format_version": importer.FORMAT_VERSION, "name": name or target.name,
        "arch": info["arch"], "family": spec["family"], "label": spec["label"],
        "denoiser": info["denoiser"], "components": info["components"],
        "quant_request": "auto", "plan": plan, "min_ram_gb": plan["min_ram_gb"],
        "defaults": {**spec["defaults"], **(m.get("defaults") or {})},
        "resolutions": m.get("resolutions") or spec["resolutions"], "negative_prompt": spec["negative_prompt"],
        "img2img": m.get("img2img", True), "runtime": spec.get("runtime") or "diffusers",
        "inpaint": m.get("inpaint", False), "inpaint_only": False,
        "content_filtered": bool(m.get("content_filtered")), "kind": m.get("kind") or "image",
        "source": {"type": "merge", "base": m.get("name"), "base_folder": base_dir,
                   "loras": [{"name": l.get("name"), "file": os.path.basename(l["file"]), "scale": float(l.get("scale", 1))} for l in loras]},
        "imported_at": int(time.time()), "imported_on": importer.imported_on(),
    }
    sub = registry.model_variant(m)
    if sub:
        manifest["sub_base"] = sub
    words = []
    for l in loras:
        words += [w for w in l.get("trigger_words") or [] if w not in words]
    if words:
        manifest["trigger_words"] = words
    # the base's picture, until the new model has one of its own
    if m.get("preview") and os.path.isfile(os.path.join(base_dir, m["preview"])):
        shutil.copy2(os.path.join(base_dir, m["preview"]), target / m["preview"])
        manifest["preview"] = m["preview"]
    return manifest


def main(spec_path):
    try:
        merge(spec_path)
    except Exception as e:
        _emit("__import_error__", {"code": type(e).__name__, "message": str(e)})
        return 1
    finally:
        try:  # the spec the app wrote for this bake (<data>/merges) is used once
            os.remove(spec_path)
        except OSError:
            pass
    return 0


if __name__ == "__main__":  # pragma: no cover
    import sys
    sys.exit(main(sys.argv[1]))
