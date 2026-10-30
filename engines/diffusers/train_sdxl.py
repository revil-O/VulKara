# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""LoRA training for SDXL models with diffusers + peft on MPS.

    python main.py train <job.json>     (job format: see mlx/train.py)

The model is loaded as the engine loads it; the pictures are encoded once (VAE latents, prompt
embeddings), then the text encoders and the VAE are freed and only the UNet's LoRA layers train
(attention projections, epsilon objective, AdamW, gradient checkpointing). The result is saved in
the diffusers LoRA format, which both the import and the engine read.
"""
import json
import math
import os
import random
import shutil
import sys
import time
from pathlib import Path

from trainutil import emit, prepare_images, write_lora_folder


def _crop_to(im, side):
    """largest centred square, scaled to the training size"""
    from PIL import Image
    s = side / min(im.size)
    im = im.resize((max(side, round(im.width * s)), max(side, round(im.height * s))), Image.LANCZOS)
    left, top = (im.width - side) // 2, (im.height - side) // 2
    return im.crop((left, top, left + side, top + side))


def main(job_path):
    import torch
    from engine import LoadedModel, _device, _free_memory

    with open(job_path) as f:
        job = json.load(f)
    work = Path(job["work_dir"])
    shutil.rmtree(work / "data", ignore_errors=True)
    side = int(job.get("resolution", 768)) // 64 * 64
    n = prepare_images(job, work / "data", side)
    steps = int(job.get("steps", 500))
    rank = int(job.get("rank", 16))
    device = _device()

    emit({"phase": "loading", "message": "Loading the model"})
    model = LoadedModel(job["base_model"], device)
    if model.spec["family"] != "sdxl":
        raise ValueError("Diffusers training supports SDXL models; FLUX.2 [klein] and Krea 2 train with MLX")
    model.load()
    model.ensure_denoiser()  # a plan in stages loads the pipeline without its UNet
    pipe = model.pipe

    # pictures and captions are encoded once
    from PIL import Image
    emit({"phase": "preparing", "message": "Encoding %d pictures" % n})
    vae = pipe.vae
    vae.to(torch.float32)  # the SDXL VAE overflows in float16
    items = []
    for img_path in sorted((work / "data").glob("*.png")):
        caption = img_path.with_suffix(".txt").read_text(encoding="utf-8")
        im = _crop_to(Image.open(img_path).convert("RGB"), side)
        pixels = pipe.image_processor.preprocess(im).to(device, torch.float32)
        with torch.no_grad():
            latents = vae.encode(pixels).latent_dist.sample() * vae.config.scaling_factor
            prompt_embeds, _, pooled, _ = pipe.encode_prompt(caption, device=device, num_images_per_prompt=1,
                                                             do_classifier_free_guidance=False)
        items.append({"latents": latents.to(model.dtype), "embeds": prompt_embeds.to(model.dtype),
                      "pooled": pooled.to(model.dtype)})
    time_ids = torch.tensor([[side, side, 0, 0, side, side]], device=device, dtype=model.dtype)

    # training needs neither the VAE nor the text encoders
    unet, scheduler = pipe.unet, pipe.scheduler
    for name in ("vae", "text_encoder", "text_encoder_2"):
        if getattr(pipe, name, None) is not None:
            setattr(pipe, name, None)
    del vae
    _free_memory()

    # LoRA layers on the UNet's attention
    from peft import LoraConfig
    from peft.utils import get_peft_model_state_dict
    unet.requires_grad_(False)
    unet.add_adapter(LoraConfig(r=rank, lora_alpha=rank, init_lora_weights="gaussian",
                                target_modules=["to_k", "to_q", "to_v", "to_out.0"]))
    params = [p for p in unet.parameters() if p.requires_grad]
    for p in params:
        p.data = p.data.to(torch.float32)  # LoRA weights train in float32, the base stays 16 bit
    unet.enable_gradient_checkpointing()
    unet.train()
    optimizer = torch.optim.AdamW(params, lr=float(job.get("learning_rate", 1e-4)), weight_decay=1e-2)
    # noise as in training: DDPM-normalised (the sampler of the pipeline, e.g. Euler, scales differently)
    from diffusers import DDPMScheduler
    scheduler = DDPMScheduler.from_config(scheduler.config)
    prediction = scheduler.config.get("prediction_type", "epsilon")
    n_train = scheduler.config.num_train_timesteps

    emit({"phase": "training", "step": 0, "total": steps, "loss": None, "eta_s": None})
    rng = random.Random(42)
    t0, losses = time.time(), []
    for step in range(1, steps + 1):
        item = items[rng.randrange(len(items))]
        latents = item["latents"]
        noise = torch.randn_like(latents)
        t = torch.randint(0, n_train, (1,), device=device).long()
        noisy = scheduler.add_noise(latents, noise, t)
        with torch.autocast(device_type=device, dtype=model.dtype, enabled=device == "mps"):
            pred = unet(noisy, t, encoder_hidden_states=item["embeds"],
                        added_cond_kwargs={"text_embeds": item["pooled"], "time_ids": time_ids}).sample
        target = noise if prediction == "epsilon" else scheduler.get_velocity(latents, noise, t)
        loss = torch.nn.functional.mse_loss(pred.float(), target.float())
        loss.backward()
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        losses.append(float(loss.detach()))
        if not math.isfinite(losses[-1]):
            raise RuntimeError("Training diverged (loss is not finite); try a lower learning rate")
        eta = (time.time() - t0) / step * (steps - step)
        emit({"phase": "training", "step": step, "total": steps,
              "loss": round(sum(losses[-10:]) / len(losses[-10:]), 4), "eta_s": round(eta)})

    # saved in the diffusers LoRA format
    from diffusers import StableDiffusionXLPipeline
    from diffusers.utils import convert_state_dict_to_diffusers
    out = work / "output"
    shutil.rmtree(out, ignore_errors=True)
    layers = convert_state_dict_to_diffusers(get_peft_model_state_dict(unet))
    StableDiffusionXLPipeline.save_lora_weights(str(out), unet_lora_layers=layers)
    folder = write_lora_folder(job, out / "pytorch_lora_weights.safetensors", family="sdxl",
                               base=model.m.get("name"),
                               training={"steps": steps, "images": n, "resolution": side, "rank": rank,
                                         "base_model": model.m.get("name"), "runtime": "diffusers"})
    emit({"done": folder})


def run(argv):
    try:
        main(argv[0])
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        emit({"error": str(e)[:400]})
        return 1


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(run(sys.argv[1:]))
