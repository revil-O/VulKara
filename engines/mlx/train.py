# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""LoRA training with mflux (FLUX.2 [klein], Krea 2, Z-Image, ERNIE-Image) on the user's pictures.

    python main.py train <job.json>

job: {"name", "trigger", "base_model": imported model folder, "images": [{"path", "caption"}],
      "resolution", "steps", "rank", "learning_rate", "work_dir", "loras_dir"}
Progress is printed as "__train__ {json}" lines (phase, step, total, loss, eta); at the end the LoRA
is stored in <loras_dir>/<name>/ like an imported one ("__train__ {"done": …}").
"""
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "diffusers"))

import memory  # noqa: E402
import registry  # noqa: E402
from trainutil import emit, prepare_images, write_lora_folder  # noqa: E402

# mflux model names and LoRA targets per architecture (module paths of the mflux transformers)
MODELS = {"flux2_klein": {"4b": "flux2-klein-4b", "9b": "flux2-klein-9b"}, "krea2": "krea-2",
          "z_image": {"turbo": "z-image-turbo", "base": "z-image"},
          "ernie_image": {"turbo": "ernie-image-turbo", "base": "ernie-image"}}
TRAINABLE = ("flux2_klein", "krea2", "z_image", "ernie_image")
# the LoRA families of the trained architectures (lora.json "family", as the LoRA library knows them)
FAMILIES = {"krea2": "krea2", "z_image": "z_image", "ernie_image": "ernie"}
# measured over the base model while training (MEASUREMENTS 7cn: Z-Image Turbo 13.2 GB in 8 bit, 10.2 in 4; ERNIE-Image
# Turbo 14.3 and 10.9); the others: twice the activations of generating plus the LoRA's gradients and optimizer state
TRAIN_ACTIVATIONS_GB = {"z_image": 3.0, "ernie": 2.5}
# mflux trains Z-Image Turbo with ostris' assistant adapter (Apache-2.0) so the step distillation holds for a short
# run; fetched here, pinned and checked, instead of into mflux's cache
ZIMAGE_ADAPTER = {
    "name": "zimage_turbo_training_adapter_v2.safetensors",
    "url": "https://huggingface.co/ostris/zimage_turbo_training_adapter/resolve/"
           "654cd1bf8b3589d9442cb1c5e35221879e1af4f3/zimage_turbo_training_adapter_v2.safetensors",
    "sha256": "20a541d3e016ab8de0da076321b48b6cd9b3ffd072d9df830a068220ab2265f6",
}


def lora_targets(m, weights_dir, rank):
    if m["arch"] == "ernie_image":
        # mflux's example targets (training/_example/train_ernie_image_turbo.json)
        with open(os.path.join(weights_dir, "transformer", "config.json")) as f:
            layers = json.load(f).get("num_layers", 36)
        return [{"module_path": "layers.{block}.%s" % p, "blocks": {"start": 0, "end": layers}, "rank": rank}
                for p in ("self_attention.to_q", "self_attention.to_k", "self_attention.to_v", "self_attention.to_out.0",
                          "mlp.gate_proj", "mlp.up_proj", "mlp.linear_fc2")] + [{"module_path": "text_proj", "rank": rank}]
    if m["arch"] == "z_image":
        # mflux's example targets (training/_example/train.json): attention and feed forward of every layer
        with open(os.path.join(weights_dir, "transformer", "config.json")) as f:
            layers = json.load(f).get("n_layers", 30)
        return [{"module_path": "layers.{block}.%s" % p, "blocks": {"start": 0, "end": layers}, "rank": rank}
                for p in ("attention.to_q", "attention.to_k", "attention.to_v", "attention.to_out.0",
                          "feed_forward.w1", "feed_forward.w2", "feed_forward.w3")]
    if m["arch"] == "krea2":
        return [{"module_path": "blocks.{block}.%s" % p, "blocks": {"start": 0, "end": 28}, "rank": rank}
                for p in ("attn.wq", "attn.wk", "attn.wv", "attn.wo", "mlp.gate", "mlp.up", "mlp.down")]
    with open(os.path.join(weights_dir, "transformer", "config.json")) as f:
        cfg = json.load(f)
    double, single = cfg.get("num_layers", 5), cfg.get("num_single_layers", 20)
    out = [{"module_path": "transformer_blocks.{block}.%s" % p, "blocks": {"start": 0, "end": double}, "rank": rank}
           for p in ("attn.to_q", "attn.to_k", "attn.to_v", "attn.to_out", "attn.add_q_proj", "attn.add_k_proj",
                     "attn.add_v_proj", "attn.to_add_out")]
    out += [{"module_path": "single_transformer_blocks.{block}.%s" % p, "blocks": {"start": 0, "end": single}, "rank": rank}
            for p in ("attn.to_qkv_mlp_proj", "attn.to_out")]
    return out


def model_name(m):
    if m["arch"] in ("z_image", "ernie_image"):
        # the rule of main.z_image_guided (not imported: "main" is also the diffusers engine's module): Base runs guided
        guided = float((m.get("defaults") or {}).get("guidance_scale", 0) or 0) > 1
        return MODELS[m["arch"]]["base" if guided else "turbo"]
    if m["arch"] == "krea2":
        return MODELS["krea2"]
    big = m.get("components", {}).get("transformer", 4) > 6
    return MODELS["flux2_klein"]["9b" if big else "4b"]


def choose_bits(m, ram_gb):
    """The base model is quantized (QLoRA); training needs about twice the activations of
    generating, plus the LoRA's gradients and optimizer state."""
    family = FAMILIES.get(m["arch"], "flux2")
    act = TRAIN_ACTIVATIONS_GB.get(family, memory.ACTIVATIONS_GB.get(family, 3.0) * 2 + 2)
    for bits, level in ((8, "q8"), (4, "q4")):
        p = memory.plan(m["components"], m["denoiser"], family, ram_gb, quant=level, allow_staging=False, activations_gb=act)
        if p["fits"]:
            return bits
    return 4


def turbo_adapter(report=None):
    """The local path of Z-Image Turbo's training adapter, downloaded once (pinned.fetch_urls: checksum, resumed)."""
    import paths
    import pinned
    folder = str(paths.helpers_dir("train_adapters"))
    pinned.fetch_urls({ZIMAGE_ADAPTER["name"]: ZIMAGE_ADAPTER["url"]}, {ZIMAGE_ADAPTER["name"]: ZIMAGE_ADAPTER["sha256"]},
                      folder, report=report)
    return os.path.join(folder, ZIMAGE_ADAPTER["name"])


def cache_limit(ram_gb):
    """MLX's buffer cache grows to the largest transient allocations; bounded on small Macs it gives freed buffers back
    at the same speed (klein 4B on 16 GB: peak 11.5 -> 8.5 GB, no swap, MEASUREMENTS 7cn). None: MLX's default."""
    return 2.0 if ram_gb < 32 else None


class Progress:
    """Stands in for tqdm in mflux's training loop: reports every step to the app."""

    last_loss = None

    def __init__(self, iterable, total=None, initial=0, **kw):
        self.iterable, self.total, self.n = iterable, total, initial

    def __iter__(self):
        t0 = time.time()
        start = self.n
        for item in self.iterable:
            yield item
            self.n += 1
            done = self.n - start
            eta = (time.time() - t0) / done * (self.total - self.n) if done else None
            emit({"phase": "training", "step": self.n, "total": self.total, "loss": Progress.last_loss,
                  "eta_s": round(eta) if eta is not None else None})


def main(job_path):
    with open(job_path) as f:
        job = json.load(f)
    base = job["base_model"]
    with open(os.path.join(base, "model.json")) as f:
        m = json.load(f)
    if m["arch"] not in TRAINABLE:
        raise ValueError("MLX training supports FLUX.2 [klein], Krea 2, Z-Image and ERNIE-Image")
    native = m.get("layout") == "single_denoiser"
    weights_dir = os.path.join(base, m["base_dir"] if native else m["weights_dir"])

    work = Path(job["work_dir"])
    shutil.rmtree(work / "data", ignore_errors=True)
    n = prepare_images(job, work / "data", int(job.get("resolution", 512)))
    steps = int(job.get("steps", 500))
    ram = memory.total_ram_gb()
    bits = choose_bits(m, ram)
    emit({"phase": "preparing", "message": "Base model in %d bit, %d pictures" % (bits, n)})
    name = model_name(m)
    adapter = None
    if name == MODELS["z_image"]["turbo"]:
        what = "Downloading the Z-Image Turbo training adapter (0.3 GB, one-time)"
        emit({"phase": "preparing", "message": what})
        adapter = turbo_adapter(report=lambda x: emit({"phase": "preparing", "message": "%s %d%%" % (what, x)})
                                if isinstance(x, (int, float)) else None)
    given = float(m.get("defaults", {}).get("guidance_scale", 0) or 0)
    guidance = {"krea2": 0.0, "z_image": given, "ernie_image": given or 1.0}
    loop = {"num_epochs": max(1, math.ceil(steps / n)), "batch_size": 1}
    if adapter:
        loop.update(timestep_low=4, timestep_high=9)  # mflux's example for Turbo (training/_example/train.json)
    elif name == MODELS["ernie_image"]["turbo"]:
        loop.update(timestep_low=1, timestep_high=8)  # mflux's example (training/_example/train_ernie_image_turbo.json)
    elif name == MODELS["ernie_image"]["base"]:
        loop.update(timestep_low=5, timestep_high=45)  # mflux's example (training/_example/train_ernie_image.json)
    config = {
        "model": name, "model_path": weights_dir, "data": str(work / "data"), "seed": 42,
        "steps": int(m.get("defaults", {}).get("num_steps", 4)), "guidance": guidance.get(m["arch"], 1.0),
        "quantize": bits, "max_resolution": int(job.get("resolution", 512)),
        "gradient_checkpointing": True, "cache_limit_gb": cache_limit(ram),
        "training_loop": loop,
        "optimizer": {"name": "AdamW", "learning_rate": float(job.get("learning_rate", 1e-4))},
        "checkpoint": {"save_frequency": max(50, steps // 4), "output_path": str(work / "output")},
        "lora_layers": {"targets": lora_targets(m, weights_dir, int(job.get("rank", 16)))},
    }
    shutil.rmtree(work / "output", ignore_errors=True)
    cfg_path = work / "train.json"
    with open(cfg_path, "w") as f:
        json.dump(config, f, indent=1)

    import mflux.models.common.training.trainer as trainer_mod
    from mflux.models.common.training.runner import TrainingRunner
    trainer_mod.tqdm = Progress
    if adapter:
        TrainingRunner.ZIMAGE_TURBO_TRAINING_ADAPTER = adapter
    finite = trainer_mod.TrainingTrainer._step_is_finite

    def step_is_finite(loss):
        ok = finite(loss)
        if ok:
            Progress.last_loss = round(float(loss), 4)
        return ok
    trainer_mod.TrainingTrainer._step_is_finite = staticmethod(step_is_finite)

    emit({"phase": "loading", "message": "Loading %s and encoding the pictures" % m.get("label", m["arch"])})
    TrainingRunner.train(config_path=str(cfg_path), resume_path=None)

    ckpts = sorted((work / "output").rglob("*_checkpoint.zip"))
    if not ckpts:
        raise RuntimeError("Training produced no checkpoint")
    import zipfile
    with zipfile.ZipFile(ckpts[-1]) as z:
        adapter = [n for n in z.namelist() if n.endswith("_adapter.safetensors")][0]
        z.extract(adapter, work)
    family = FAMILIES.get(m["arch"], "flux2")
    # the sub-base too (FLUX.2 [klein] 4B or 9B): a LoRA of one size does not fit the other
    folder = write_lora_folder(job, work / adapter, family=family, base=model_name(m), variant=registry.model_variant(m),
                               training={"steps": steps, "images": n, "resolution": int(job.get("resolution", 512)),
                                         "rank": int(job.get("rank", 16)), "base_model": m.get("name"),
                                         "runtime": "mlx", "quantize": bits})
    emit({"done": folder})
