# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""The one-time quantization of a component in a short-lived process of its own.

Quantizing loads the 16 bit weights first; the engine that did it in its own process kept that memory afterwards (macOS
did not get it back): Qwen-Image 2.1 on a 16 GB Mac mini stayed at 18-19 GB with 11-12 GB in the swap until the app
restarted, against 9.9 GB from the cache (MEASUREMENTS 7bd). Here the process writes the cache and ends, and the engine
loads the quantized component from the cache.

python quantize_once.py '<json>' with {"kind": "component", "folder", "comp", "variant"} (a text encoder, Transformers'
Quanto), {"kind": "gguf", "source", "comp", "variant"} (the denoiser written as GGUF, gguf_cache.py) or
{"kind": "controlnet", "folder", "cls"} (8 bit with optimum-quanto itself), and "model_dir", "level" (q8/q4), "dtype".
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(job, stop=None):
    """Quantizes in a child process; True when it wrote the cache. stop() true ends the child (the job was cancelled)."""
    import time
    proc = subprocess.Popen([sys.executable, os.path.join(HERE, "quantize_once.py"), json.dumps(job)],
                            stdout=sys.stderr, stderr=sys.stderr)
    try:
        while proc.poll() is None:
            if stop is not None and stop():
                return False
            time.sleep(0.5)
    finally:
        # also when a stop is raised in this thread while it waits (the engine loads models interruptibly)
        if proc.poll() is None:
            proc.terminate()
            proc.wait()
    return proc.returncode == 0


def main(job):
    sys.path.insert(0, HERE)
    import torch
    import diffusers
    import transformers
    import engine
    import quant_cache
    dtype = getattr(torch, job["dtype"])
    level = job["level"]
    if job["kind"] == "gguf":
        import gguf_cache
        gguf_cache.write(job["model_dir"], job["source"], job.get("comp"), level, job.get("variant"),
                         progress=lambda pct: print("progress %d" % pct, file=sys.stderr, flush=True))
    elif job["kind"] == "controlnet":
        # Diffusers' Quanto backend goes with version 1.0, and these ControlNets do not load as a single file (GGUF):
        # optimum-quanto quantizes the 16 bit weights itself (1.2-2.2B parameters, on the CPU)
        from optimum.quanto import freeze, qint8, quantize
        folder = job["folder"]
        model = getattr(diffusers, job["cls"]).from_pretrained(folder, dtype=dtype)
        # the linear layers only, as Diffusers' backend did
        quantize(model, weights=qint8, include=[n for n, mod in model.named_modules() if isinstance(mod, torch.nn.Linear)])
        freeze(model)
        quant_cache.save(folder, folder, None, level, dtype, model)
    else:
        folder, comp = job["folder"], job["comp"]
        with open(os.path.join(folder, "model_index.json")) as f:
            lib, name = json.load(f)[comp]
        cls = getattr(transformers, name)
        config = engine._quanto_configs({comp: level})[comp]
        extra = {"variant": job["variant"]} if job.get("variant") else {}
        model = cls.from_pretrained(folder, subfolder=comp, dtype=dtype, quantization_config=config, **extra)
        quant_cache.quantize_kept_fp32(model, dtype)
        quant_cache.save(job["model_dir"], folder, comp, level, dtype, model)


if __name__ == "__main__":
    main(json.loads(sys.argv[1]))
