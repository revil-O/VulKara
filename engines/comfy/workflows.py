# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""ComfyUI workflows (API format) for the jobs of the app: pictures (build) and videos (build_video).

A job of the app (prompt, size, steps, seed, input image, LoRAs) becomes a graph of ComfyUI nodes.
Models whose parts are separate files (diffusion model, text encoder, VAE: Anima and most new
architectures) use UNETLoader / CLIPLoader / VAELoader, exactly like the reference workflows of their
authors. Only standard ComfyUI nodes are used, and VulKara's VulKaraEncodeAndFree (custom_nodes/vulkara_memory), which
frees the text encoder before the sampler on a Mac short of memory.
"""

# the app's sampler names (utils/samplers.js) -> ComfyUI (sampler_name, scheduler)
SAMPLERS = {
    "Default": None,
    "Euler": ("euler", None), "Euler a": ("euler_ancestral", None), "Heun": ("heun", None),
    "DPM++ 2M": ("dpmpp_2m", None), "DPM++ 2M SDE": ("dpmpp_2m_sde", None), "DPM++ SDE": ("dpmpp_sde", None),
    "DDIM": ("ddim", None), "UniPC": ("uni_pc", None), "LMS": ("lms", None), "ER SDE": ("er_sde", None),
}
SCHEDULES = {"Default": None, "Karras": "karras", "Exponential": "exponential", "Beta": "beta"}


def _sampler_names(job, comfy):
    sampler, scheduler = comfy.get("sampler", "euler"), comfy.get("scheduler", "simple")
    picked = SAMPLERS.get(job.get("sampler") or "Default")
    if picked:
        sampler = picked[0]
    sched = SCHEDULES.get(job.get("sigma_schedule") or "Default")
    if sched:
        scheduler = sched
    return sampler, scheduler


def _loaders(files, comfy, loras):
    g = {
        "unet": _unet_loader(files["diffusion_model"]),
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": files["text_encoder"],
                                                        "type": comfy.get("clip_type", "stable_diffusion"), "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": files["vae"]}},
    }
    model, clip = ["unet", 0], ["clip", 0]
    if comfy.get("t5_min_padding"):  # AuraFlow / Pony V7: prompts padded as in the model's own workflow
        n = int(comfy["t5_min_padding"])
        g["t5"] = {"class_type": "T5TokenizerOptions", "inputs": {"clip": clip, "min_padding": n, "min_length": n}}
        clip = ["t5", 0]
    for i, (name, strength) in enumerate(loras):
        node = "lora%d" % i
        g[node] = {"class_type": "LoraLoader", "inputs": {"lora_name": name, "strength_model": float(strength),
                                                          "strength_clip": float(strength), "model": model, "clip": clip}}
        model, clip = [node, 0], [node, 1]
    return g, model, clip


def video_frames(seconds, fps):
    """Frame count for a clip length: Wan models take 4n + 1 frames."""
    n = max(1, round(float(seconds) * float(fps)))
    return (n - 1) // 4 * 4 + 1


def _unet_loader(name):
    if name.lower().endswith(".gguf"):  # ComfyUI-GGUF; LoRA patches on the GPU, not the CPU (its default)
        return {"class_type": "UnetLoaderGGUFAdvanced", "inputs": {"unet_name": name, "dequant_dtype": "target",
                                                                   "patch_dtype": "target", "patch_on_device": True}}
    return {"class_type": "UNETLoader", "inputs": {"unet_name": name, "weight_dtype": "default"}}


def _video_out(g, samples, fps):
    g["decode"] = {"class_type": "VAEDecode", "inputs": {"samples": samples, "vae": ["vae", 0]}}
    g["video"] = {"class_type": "CreateVideo", "inputs": {"images": ["decode", 0], "fps": float(fps)}}
    g["save"] = {"class_type": "SaveVideo", "inputs": {"video": ["video", 0], "filename_prefix": "vulkara",
                                                       "format": "mp4", "codec": "auto"}}
    return g


def build_video_two_stage(job, files, comfy, input_image=None):
    """Wan 2.2 I2V 14B: a high-noise model for the first steps, a low-noise model for the rest, each with
    its distillation LoRA (lightx2v: 4 steps, CFG 1), like ComfyUI's reference workflow.
    files: diffusion_model / diffusion_model_low, lora_high / lora_low, text_encoder, vae."""
    g = {
        "clip": {"class_type": "CLIPLoader", "inputs": {"clip_name": files["text_encoder"], "type": comfy.get("clip_type", "wan"),
                                                        "device": "default"}},
        "vae": {"class_type": "VAELoader", "inputs": {"vae_name": files["vae"]}},
    }
    for stage, part in (("high", "diffusion_model"), ("low", "diffusion_model_low")):
        g["unet_" + stage] = _unet_loader(files[part])
        model = ["unet_" + stage, 0]
        if files.get("lora_" + stage):
            g["lora_" + stage] = {"class_type": "LoraLoaderModelOnly", "inputs": {
                "model": model, "lora_name": files["lora_" + stage], "strength_model": 1.0}}
            model = ["lora_" + stage, 0]
        g["shift_" + stage] = {"class_type": "ModelSamplingSD3", "inputs": {"model": model, "shift": float(comfy.get("shift", 5.0))}}
    g["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"text": job.get("prompt") or "", "clip": ["clip", 0]}}
    g["neg"] = {"class_type": "CLIPTextEncode", "inputs": {"text": job.get("negative_prompt") or "", "clip": ["clip", 0]}}
    i2v = {"positive": ["pos", 0], "negative": ["neg", 0], "vae": ["vae", 0], "width": int(job["width"]),
           "height": int(job["height"]), "length": int(job["frames"]), "batch_size": 1}
    if input_image:
        g["image"] = {"class_type": "LoadImage", "inputs": {"image": input_image}}
        i2v["start_image"] = ["image", 0]
    g["i2v"] = {"class_type": "WanImageToVideo", "inputs": i2v}
    steps = max(2, int(job["steps"]))
    switch = steps // 2
    sampler, scheduler = _sampler_names(job, comfy)
    common = {"noise_seed": int(job["seed"]), "steps": steps, "cfg": float(job["cfg"]), "sampler_name": sampler,
              "scheduler": scheduler, "positive": ["i2v", 0], "negative": ["i2v", 1]}
    g["sample_high"] = {"class_type": "KSamplerAdvanced", "inputs": dict(common, model=["shift_high", 0], add_noise="enable",
                        latent_image=["i2v", 2], start_at_step=0, end_at_step=switch, return_with_leftover_noise="enable")}
    g["sample_low"] = {"class_type": "KSamplerAdvanced", "inputs": dict(common, model=["shift_low", 0], add_noise="disable",
                       latent_image=["sample_high", 0], start_at_step=switch, end_at_step=10000,
                       return_with_leftover_noise="disable")}
    return _video_out(g, ["sample_low", 0], job["fps"])


def build_video(job, files, comfy, loras=(), input_image=None):
    """Video from a start picture (Wan 2.2 TI2V). job as in build, plus frames and fps; input_image is
    the start picture in ComfyUI's input folder (without one the video starts from noise).
    Returns the API-format graph; the node "save" holds the video."""
    if files.get("diffusion_model_low"):
        return build_video_two_stage(job, files, comfy, input_image)
    sampler, scheduler = _sampler_names(job, comfy)
    g, model, clip = _loaders(files, comfy, loras)
    if comfy.get("shift"):
        g["shift"] = {"class_type": "ModelSamplingSD3", "inputs": {"model": model, "shift": float(comfy["shift"])}}
        model = ["shift", 0]
    g["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"text": job.get("prompt") or "", "clip": clip}}
    g["neg"] = {"class_type": "CLIPTextEncode", "inputs": {"text": job.get("negative_prompt") or "", "clip": clip}}
    latent = {"vae": ["vae", 0], "width": int(job["width"]), "height": int(job["height"]),
              "length": int(job["frames"]), "batch_size": 1}
    if input_image:
        g["image"] = {"class_type": "LoadImage", "inputs": {"image": input_image}}
        latent["start_image"] = ["image", 0]
    g["latent"] = {"class_type": "Wan22ImageToVideoLatent", "inputs": latent}
    g["sample"] = {"class_type": "KSampler", "inputs": {
        "seed": int(job["seed"]), "steps": int(job["steps"]), "cfg": float(job["cfg"]), "sampler_name": sampler,
        "scheduler": scheduler, "denoise": 1.0, "model": model, "positive": ["pos", 0], "negative": ["neg", 0],
        "latent_image": ["latent", 0]}}
    return _video_out(g, ["sample", 0], job["fps"])


def build(job, files, comfy, loras=(), input_image=None, references=(), free_text_encoder=False):
    """job: {prompt, negative_prompt, width, height, steps, cfg, seed, strength, sampler, sigma_schedule}
    files: {"diffusion_model", "text_encoder", "vae"}: file names as ComfyUI sees them
    comfy: the model type's ComfyUI settings (registry "comfy": clip_type, sampler, scheduler)
    loras: [(file name, strength)]; input_image: file name in ComfyUI's input folder (image to image); references:
    further pictures there that Fibo 2.0 edits with it (<image_2> ...); free_text_encoder: encode with
    VulKaraEncodeAndFree, so the text encoder is gone before the model loads (not with LoRAs, prompt padding or Fibo).
    Returns the API-format graph; the node "save" holds the result."""
    sampler, scheduler = _sampler_names(job, comfy)
    g, model, clip = _loaders(files, comfy, loras)
    if comfy.get("skip_layers"):  # MOSS-Image: the negative branch skips these layers (its maker's guidance)
        g["slg"] = {"class_type": "SkipLayerGuidanceDiTSimple", "inputs": {
            "model": model, "double_layers": "", "single_layers": comfy["skip_layers"], "start_percent": 0.0, "end_percent": 1.0}}
        model = ["slg", 0]

    fibo = comfy.get("encode") == "fibo2"
    free = free_text_encoder and not fibo and not loras and not comfy.get("t5_min_padding")
    if free:
        del g["clip"]
        g["enc"] = {"class_type": "VulKaraEncodeAndFree", "inputs": {
            "clip_name": files["text_encoder"], "type": comfy.get("clip_type", "stable_diffusion"),
            "text": job.get("prompt") or "", "negative": job.get("negative_prompt") or ""}}
    elif not fibo:
        g["pos"] = {"class_type": "CLIPTextEncode", "inputs": {"text": job.get("prompt") or "", "clip": clip}}
        g["neg"] = {"class_type": "CLIPTextEncode", "inputs": {"text": job.get("negative_prompt") or "", "clip": clip}}

    denoise = 1.0
    positive, negative, latent = ["pos", 0], ["neg", 0], ["latent", 0]
    if free:
        positive, negative = ["enc", 0], ["enc", 1]
    if fibo:
        # Fibo 2.0: one node encodes the prompt with the picture to edit (Qwen3-VL sees it, the VAE makes it the
        # reference latent) and gives the empty latent of the result; the picture itself is not noised (denoise 1)
        enc = {"clip": clip, "prompt": job.get("prompt") or "", "negative_prompt": job.get("negative_prompt") or "",
               "vae": ["vae", 0], "width": int(job["width"]), "height": int(job["height"]), "batch_size": 1}
        for i, name in enumerate([input_image, *references] if input_image else []):
            node = "image" if i == 0 else "image%d" % (i + 1)
            g[node] = {"class_type": "LoadImage", "inputs": {"image": name}}
            enc["images.image_%d" % (i + 1)] = [node, 0]
        g["enc"] = {"class_type": "TextEncodeFibo2", "inputs": enc}
        positive, negative, latent = ["enc", 0], ["enc", 1], ["enc", 2]
    elif input_image:
        g["image"] = {"class_type": "LoadImage", "inputs": {"image": input_image}}
        g["scaled"] = {"class_type": "ImageScale", "inputs": {"image": ["image", 0], "upscale_method": "lanczos",
                                                              "width": int(job["width"]), "height": int(job["height"]),
                                                              "crop": "center"}}
        g["latent"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["scaled", 0], "vae": ["vae", 0]}}
        denoise = min(1.0, max(0.05, float(job.get("strength", 0.5))))
    else:
        # FLUX.2's VAE (MOSS-Image): 128 channels at 1/16 of the size
        empty = "EmptyFlux2LatentImage" if comfy.get("latent") == "flux2" else "EmptyLatentImage"
        g["latent"] = {"class_type": empty, "inputs": {"width": int(job["width"]), "height": int(job["height"]),
                                                       "batch_size": 1}}
    g["sample"] = {"class_type": "KSampler", "inputs": {
        "seed": int(job["seed"]), "steps": int(job["steps"]), "cfg": float(job["cfg"]), "sampler_name": sampler,
        "scheduler": scheduler, "denoise": denoise, "model": model, "positive": positive, "negative": negative,
        "latent_image": latent}}
    g["decode"] = {"class_type": "VAEDecode", "inputs": {"samples": ["sample", 0], "vae": ["vae", 0]}}
    g["save"] = {"class_type": "SaveImage", "inputs": {"filename_prefix": "vulkara", "images": ["decode", 0]}}
    return g


def upscale_plan(size, factor, max_side=2048):
    """(size the model gets, size of the result) for a picture of size (w, h) enlarged factor times: a picture over
    max_side is made smaller first; the result is factor times the picture given (exactly, rounded per side), but
    at most four times what the model gets."""
    w, h = size
    k = min(1.0, max_side / max(w, h))
    small = (max(1, round(w * k)), max(1, round(h * k)))
    target = (min(round(w * factor), small[0] * 4), min(round(h * factor), small[1] * 4))
    return small, target


def build_upscale(input_image, model_name, factor=4, size=None):
    """Enlarges a picture with an upscaling model (4x); a smaller factor (1.1 to 4) scales the result down to it,
    size (w, h) to exactly that size instead. input_image: file name in ComfyUI's input folder; model_name: file in
    models/upscale_models. Returns the API-format graph; the node "save" holds the result."""
    g = {
        "image": {"class_type": "LoadImage", "inputs": {"image": input_image}},
        "model": {"class_type": "UpscaleModelLoader", "inputs": {"model_name": model_name}},
        "up": {"class_type": "ImageUpscaleWithModel", "inputs": {"upscale_model": ["model", 0], "image": ["image", 0]}},
    }
    out = ["up", 0]
    if size:
        g["scaled"] = {"class_type": "ImageScale", "inputs": {"image": out, "upscale_method": "lanczos",
                                                              "width": int(size[0]), "height": int(size[1]), "crop": "disabled"}}
        out = ["scaled", 0]
    elif abs(float(factor) - 4.0) > 1e-6:
        g["scaled"] = {"class_type": "ImageScaleBy", "inputs": {"image": out, "upscale_method": "lanczos",
                                                                "scale_by": float(factor) / 4.0}}
        out = ["scaled", 0]
    g["save"] = {"class_type": "SaveImage", "inputs": {"images": out, "filename_prefix": "vulkara"}}
    return g
