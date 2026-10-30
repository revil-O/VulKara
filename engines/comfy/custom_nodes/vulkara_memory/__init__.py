# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""VulKara's switch for ComfyUI's memory mode. On the Mac ComfyUI always keeps whole models in memory (SHARED;
--lowvram is ignored there, ComfyUI PR #15998). In LOW_VRAM it keeps only what fits and copies the other layers in
for their turn: a GGUF file is mapped, not read, so those layers come from the file through the macOS file cache
(docs/MEASUREMENTS.md 7h). The engine sets the mode per picture (engines/comfy/main.py); the request goes through
vulkara_guard's key check like every other one.

It also sets up attention for the Mac (docs/MEASUREMENTS.md 7o): ComfyUI starts with --use-pytorch-cross-attention, and
here a head size below 64 the fused MPS kernel does not take (SD 1.5's 40) is padded with zeros to 64 (same result);
unpadded such heads hold the whole attention matrix. The VAE keeps its split attention: an MPS allocation that does not
fit ends the process instead of raising, so ComfyUI's fallback to slices would never run.

An FP8 model stays in 16 bit: ComfyUI keeps one in FP8 where 16 bit would not fit, but MPS cannot cast FP8 ("Undefined
type Float8_e4m3fn" at the first step), so a Mac short of memory swaps instead of stopping the job. And a model that
may run in float16 does so instead of bfloat16: MPS computes bfloat16 at half the speed (MEASUREMENTS 7ab). Of the
models VulKara runs here that is Anima alone (Lumina 2 allows only bfloat16, AuraFlow and Wan pick float16 already).
"""
import asyncio
import comfy.model_management as mm
import torch
import torch.nn.functional as F
from aiohttp import web
from server import PromptServer

FUSED_HEAD_DIMS = (32, 64)


def pad_attention():
    sdpa = F.scaled_dot_product_attention
    if getattr(sdpa, "vk_padded", False):
        return

    def padded(query, key, value, *args, scale=None, **kwargs):
        d = query.shape[-1]
        if query.device.type != "mps" or d >= 64 or d in FUSED_HEAD_DIMS or key.shape[-1] != d or value.shape[-1] != d:
            return sdpa(query, key, value, *args, scale=scale, **kwargs)
        pad = lambda t: F.pad(t, (0, 64 - d))
        return sdpa(pad(query), pad(key), pad(value), *args, scale=d ** -0.5 if scale is None else scale, **kwargs)[..., :d]
    padded.vk_padded = True
    F.scaled_dot_product_attention = padded


def mac_weights():
    unet_dtype = mm.unet_dtype

    def dtype(*args, **kwargs):
        dt = unet_dtype(*args, **kwargs)
        if mm.get_torch_device().type != "mps":
            return dt
        if dt in mm.FLOAT8_TYPES:
            dt = unet_dtype(*args, **dict(kwargs, weight_dtype=None))
        if dt == torch.bfloat16 and torch.float16 in (kwargs.get("supported_dtypes") or ()):
            dt = torch.float16
        return dt
    mm.unet_dtype = dtype


pad_attention()
mac_weights()
mm.pytorch_attention_enabled_vae = lambda: False

MODES = {"SHARED": mm.VRAMState.SHARED, "LOW_VRAM": mm.VRAMState.LOW_VRAM}


@PromptServer.instance.routes.post("/vulkara/memory")
async def set_memory_mode(request):
    mode = MODES.get((await request.json()).get("mode"))
    if mode is None:
        return web.Response(status=400, text="unknown mode")
    # the engine sent /free just before: ComfyUI's worker unloads only once it has read that flag, and a prompt queued
    # before would run first with the old mode's models; so wait until it was read (unloading here races the worker)
    queue = PromptServer.instance.prompt_queue
    for _ in range(600):
        if not queue.get_flags(reset=False):
            break
        await asyncio.sleep(0.05)
    mm.vram_state = mode
    return web.json_response({"mode": mm.vram_state.name})


NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
