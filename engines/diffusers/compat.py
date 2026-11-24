# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""What the Intel-Mac build's older packages (engines/diffusers/requirements-x64.txt: PyTorch 2.2, diffusers 0.35,
no optimum-quanto) need so the same engine code runs on them. On the Apple-chip set every check here is a no-op."""
import functools
import importlib.metadata as md
import os
import platform


def _version(package):
    try:
        return tuple(int(p) for p in md.version(package).split("+")[0].split(".")[:2])
    except (md.PackageNotFoundError, ValueError):
        return (0, 0)


# The Intel build is the only x86_64 Python (also under Rosetta). Decided by the CPU, not by installed packages: the
# MLX and ComfyUI runtimes import memory.py too and have no optimum-quanto, and MLX should not load PyTorch for it.
INTEL = platform.machine() == "x86_64"
# optimum-quanto needs PyTorch 2.6, which the Intel build lacks: 8 and 4 bit on the fly are not offered there
QUANTO = not INTEL


def cpu_only():
    """No GPU for PyTorch (the Intel build): everything runs in plain RAM."""
    return INTEL


def old_torch():
    """PyTorch before 2.4 (the Intel build): FLUX and newer models need torch.nn.RMSNorm, which came with 2.4."""
    return (0, 0) < _version("torch") < (2, 4)


def pickle_safe():
    """Can torch.load(weights_only=True) be trusted with a file of the user's? Only from PyTorch 2.6 on: before, a
    crafted pickle runs code despite it (CVE-2025-32434). The Intel build has 2.2, so it takes no pickles."""
    return _version("torch") >= (2, 6)


def refuse_pickle(path):
    if not pickle_safe():
        raise ValueError("%s is a PyTorch pickle file, which this build cannot read safely (its PyTorch is older than "
                         "2.6); use a .safetensors version of the model" % path.rsplit("/", 1)[-1])


def drop_chat_templates(pipe):
    """Before save_pretrained on transformers before 5.10: a tokenizer's chat_template keys become file names there
    (CVE-2026-9856, a crafted tokenizer_config.json writes outside the folder). Stable Diffusion tokenizers use none."""
    if (0, 0) < _version("transformers") < (5, 10):
        for part in (getattr(pipe, "components", None) or {}).values():
            if getattr(part, "chat_template", None):
                part.chat_template = None


def refuse_code(folder):
    """A model folder with Python files on diffusers before 0.38: it may run them despite trust_remote_code
    (CVE-2026-44513, -44827, -45804). Downloads never fetch .py files; install() runs this before every load."""
    if (0, 0) < _version("diffusers") < (0, 38):
        seen = set()
        # links are followed (diffusers follows them too), each real folder once so a link loop ends
        for root, dirs, names in os.walk(folder, followlinks=True):
            real = os.path.realpath(root)
            if real in seen:
                dirs[:] = []
                continue
            seen.add(real)
            if any(n.lower().endswith(".py") for n in names):  # APFS and exFAT ignore case: evil.PY loads as .py
                raise ValueError("This folder holds Python files, which this build's diffusers could run: remove them "
                                 "or import the model from Hugging Face")


def _local_dir(value):
    return isinstance(value, (str, os.PathLike)) and os.path.isdir(value)


def install():
    """diffusers before 0.36 knows the dtype as torch_dtype only; the engine writes dtype= (as 0.36 on does). There,
    every load also refuses folders with Python files (refuse_code) and, before PyTorch 2.6, pickle weights: diffusers
    falls back to a .bin file when a component has no .safetensors, and torch.load is not safe there."""
    if _version("diffusers") >= (0, 36):
        return
    import diffusers
    from diffusers.loaders.single_file import FromSingleFileMixin
    from diffusers.loaders.single_file_model import FromOriginalModelMixin

    for cls, name in ((diffusers.ModelMixin, "from_pretrained"), (diffusers.DiffusionPipeline, "from_pretrained"),
                      (FromSingleFileMixin, "from_single_file"), (FromOriginalModelMixin, "from_single_file")):
        func = getattr(cls, name).__func__

        def call(klass, *args, _func=func, _pretrained=name == "from_pretrained", **kwargs):
            if "dtype" in kwargs and "torch_dtype" not in kwargs:
                kwargs["torch_dtype"] = kwargs.pop("dtype")
            for value in args[:1] + (kwargs.get("config"), kwargs.get("pretrained_model_name_or_path")):
                if _local_dir(value):
                    refuse_code(value)
            if _pretrained and not pickle_safe():
                kwargs["use_safetensors"] = True
            return _func(klass, *args, **kwargs)

        setattr(cls, name, classmethod(functools.wraps(func)(call)))
