# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""ObjectClear: a painted object removed together with its shadow and reflection (of what it changes beyond the painted
mask VulKara keeps only what gets lighter, and no other person's face: remove.py, MEASUREMENTS 7cc).

ObjectClear (Zhao, Wang, Yang, Zhou: "Precise Object and Effect Removal with Adaptive Target-Aware Attention",
arXiv 2505.22636) is an SDXL inpainting model trained to take an object's effects away with it. Its weights
(jixin0101/ObjectClear) are under the S-Lab License 1.0 (non-commercial); their base, SDXL inpainting 0.1, under
CreativeML Open RAIL++-M. This is VulKara's own implementation of its inference, written from the paper and the
layout of the published weights; none of ObjectClear's code is used. Around diffusers' standard
StableDiffusionXLInpaintPipeline it adds:

- the object embedding: the object alone (picture times mask) through the image half of CLIP ViT-L/14, mapped by a
  small trained module ("postfuse") onto the word "object" of a fixed prompt;
- the whole picture, not the masked one, as the UNet's picture condition;
- after the first step the noised original put back outside the mask (SVDS in the paper);
- in the last step the cross-attention paid to the object token in one early layer, kept as a map: it marks the
  object and its effects and guides the fusion with the original (AGF, fuse()).

The numbers (token, layer, threshold, kernel sizes, wavelet levels, sizing) are those the model was published with:
results only match the maker's with them (plans/OBJECTCLEAR_NACHBAU.md, steps 1-3).
"""
import contextlib
import gc
import os

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from torch import nn

HELPER = "objectclear"
REPO = "jixin0101/ObjectClear"
# the fp16 weights only (the fp32 copies beside them are not loaded); checksums from the Hub, small files checked
# against a fresh download (plans/OBJECTCLEAR_NACHBAU.md 4.8)
PIN = ("c73af80888dbd519819d0a521b5c8d0f3cda6859", {
    "model_index.json": "eb5879ebaa9438feb542b8c3a23d96a6948f9f62344454de727348eb44957713",
    "scheduler/scheduler_config.json": "a8e9a8517e8739938ea85819012bad195d41ccb3e11e2501cf196da64099b1f6",
    "text_encoder/config.json": "fcb477b961c7233eff97a02375bee975c4925075b80720793933fec5602878f9",
    "text_encoder/model.fp16.safetensors": "fc83cf401d930147807e7c44021c164bcc5508c9d4cc0ff35f4e354685ca9cd0",
    "text_encoder_2/config.json": "927bbd612346a9da1de0bc10d79f24ec7d64756cc8bb0ca1257604f163c83f4a",
    "text_encoder_2/model.fp16.safetensors": "a8622bd41f8d359df484fdf9de091edb9337a2fd747f0a5c9c320a62e24d1fd3",
    "tokenizer/merges.txt": "9fd691f7c8039210e0fced15865466c65820d09b63988b0174bfe25de299051a",
    "tokenizer/special_tokens_map.json": "c4864a9376a8401918425bed71fc14fc0e81f9b59ec45c1cf96cccb2df508eac",
    "tokenizer/tokenizer_config.json": "19d7b034cb0cc3ce9766c2231373ab8aa8991fc72e2c8f76558bfaae3de0d563",
    "tokenizer/vocab.json": "e089ad92ba36837a0d31433e555c8f45fe601ab5c221d4f607ded32d9f7a4349",
    "tokenizer_2/merges.txt": "9fd691f7c8039210e0fced15865466c65820d09b63988b0174bfe25de299051a",
    "tokenizer_2/special_tokens_map.json": "f118ab3a983206e4f32583448de6bd6aae4ee21869135cef1f5848a753cdaab6",
    "tokenizer_2/tokenizer_config.json": "c9d23941f76a41cbd50eda9290f57be7828f0a7a677939e9ef181f7e12bd1bdf",
    "tokenizer_2/vocab.json": "e089ad92ba36837a0d31433e555c8f45fe601ab5c221d4f607ded32d9f7a4349",
    "unet/config.json": "d0b7bf0c11f5811883d6bd6afc99c9779286e58b62fe7ad4acbfda5f9d2aef5d",
    "unet/diffusion_pytorch_model.fp16.safetensors": "fb0c35b0be8bba4ecd61dfca4e716a0a9878639c5fc271a05a780b4dc2366c31",
    "vae/config.json": "d51651b33b00f1c4a1f4aeb9e6a7efe56b0ff8c0c822f5a902c028a5161cfc10",
    "vae/diffusion_pytorch_model.fp16.safetensors": "4ad62825e5c8b31eefb77355ba6693785619bf7d669d9b1a6fd9f19dec6d65b3",
    "image_prompt_encoder/config.json": "96eaadaeeb52b21b9d0856cd0e6ff9d8b9231f48a2c3720dcaf857d6a48b0e6b",
    "image_prompt_encoder/model.fp16.safetensors": "0ebf6aa2b0f8db475ca7bd1148fcc2dc131f989cb452a45103ff23e3ece825c8",
    "postfuse_module/config.json": "e77d22f7c0ea6ce33cd63bd05fa7370014fb735570b37efa16d86246a472c970",
    "postfuse_module/model.fp16.safetensors": "3e3f1dca78cfe25f36ff8b9a8b16ab52cfd0982c81afd04864cace1e4c2afaaf",
})

PROMPT = "remove the instance of object"
# the word "object" in PROMPT: 0 is the start token
TOKEN = 5
# first cross-attention at half the latent size; its map on TOKEN outlines object and shadow
LAYER = "down_blocks.1.attentions.0.transformer_blocks.0.attn2"
# trained at 512×512; the maker's steps and guidance
SHORT, STEPS, GUIDANCE = 512, 20, 2.5
# longer side at most: memory grows with the area (a 3:1 panorama at short side 512 would be 1536 px wide); up to
# 2:1 the short side stays 512, wider pictures get a smaller one (MEASUREMENTS 7ca)
LONG = 1024
# CLIP's input statistics (for pictures in 0..1, though the model was trained feeding it -1..1)
CLIP_SIZE = 224
CLIP_MEAN = (0.48145466, 0.4578275, 0.40821073)
CLIP_STD = (0.26862954, 0.26130258, 0.27577711)
# fusion: map threshold (of 255), widening ellipse, its soft edge, wavelet levels of the colour fix
THRESHOLD, WIDEN, BLUR, SIGMA, LEVELS = 128, 21, 9, 2, 5


def working_size(w, h, short=SHORT, long=LONG):
    """The size the model works at: shorter side `short` (smaller pictures keep theirs), the longer one at most
    `long`, both sides rounded up to a multiple of 16."""
    if min(w, h) >= short:
        w, h = (short, int(h * short / w)) if w < h else (int(w * short / h), short)
    if max(w, h) > long:
        w, h = (long, int(h * long / w)) if w > h else (int(w * long / h), long)
    return -(-w // 16) * 16, -(-h // 16) * 16


def ready(folder):
    """ObjectClear is there: pinned.py marked this revision complete (a hand-deleted file or a new pin is not)."""
    import pinned
    return pinned._checked(folder).get("revision") == PIN[0] and all(os.path.isfile(os.path.join(folder, f)) for f in PIN[1])


def prepare(image, mask):
    """image and mask at working_size: bicubic for the picture, nearest for the mask so it stays sharp."""
    size = working_size(*image.size)
    return image.convert("RGB").resize(size, Image.BICUBIC), mask.convert("L").resize(size, Image.NEAREST)


class _MLP(nn.Module):
    """LayerNorm, Linear, GELU, Linear; adds its input back when it keeps the width."""

    def __init__(self, dim_in, dim):
        super().__init__()
        self.layernorm = nn.LayerNorm(dim_in)
        self.fc1 = nn.Linear(dim_in, dim)
        self.fc2 = nn.Linear(dim, dim)

    def forward(self, x):
        y = self.fc2(F.gelu(self.fc1(self.layernorm(x))))
        return y + x if y.shape == x.shape else y


class Postfuse(nn.Module):
    """The object's CLIP image embedding mapped into the text encoders' space (attribute names = the weight keys)."""

    def __init__(self, text_dim=2048, image_dim=768):
        super().__init__()
        self.mlp1 = _MLP(image_dim, text_dim)
        self.mlp2 = _MLP(text_dim, text_dim)
        self.layer_norm = nn.LayerNorm(text_dim)

    def forward(self, image_embed):
        return self.layer_norm(self.mlp2(self.mlp1(image_embed)))


def put_object(prompt_embeds, object_embed, index=TOKEN):
    """prompt_embeds [b, tokens, d] with the token at index replaced by object_embed [b, 1, d] (a copy)."""
    out = prompt_embeds.clone()
    out[:, index] = object_embed[:, 0]
    return out


def clip_pixels(pixels, binary):
    """The object alone (pixels in -1..1 kept where binary > 0.5, else 0) at CLIP's size and statistics."""
    obj = pixels * (binary > 0.5)
    obj = F.interpolate(obj, (CLIP_SIZE, CLIP_SIZE), mode="bilinear", antialias=True)
    mean = torch.as_tensor(CLIP_MEAN, dtype=obj.dtype, device=obj.device)[:, None, None]
    std = torch.as_tensor(CLIP_STD, dtype=obj.dtype, device=obj.device)[:, None, None]
    return (obj - mean) / std


def object_embedding(vision, postfuse, pixels, binary):
    """The object's CLIP embedding [1, 1, 768] and the prompt token made from it [1, 1, 2048]."""
    with torch.no_grad():
        clip = vision(pixel_values=clip_pixels(pixels, binary)).image_embeds[:, None]
        return clip, postfuse(clip)


class _KeepToken:
    """Diffusers' plain attention (scores computed explicitly, unlike SDPA), keeping the share every picture position
    gives one text token. Set on one layer for one step only: SDPA is faster and is what the other steps used."""

    def __init__(self, token):
        from diffusers.models.attention_processor import AttnProcessor
        self.token, self.probs, self._plain = token, None, AttnProcessor()

    def __call__(self, attn, hidden_states, encoder_hidden_states=None, attention_mask=None, temb=None, *args, **kw):
        scores = attn.get_attention_scores

        def keep(query, key, mask=None):
            probs = scores(query, key, mask)
            self.probs = probs[:, :, self.token:self.token + 1]
            return probs

        attn.get_attention_scores = keep
        try:
            return self._plain(attn, hidden_states, encoder_hidden_states, attention_mask, temb)
        finally:
            del attn.get_attention_scores


def attention_map(probs, heads, height, width):
    """Kept attention [batch*heads, (height/2)*(width/2), 1] as maps [batch, height, width] in 0..1: mean of the
    heads, bilinear to the latent size, stretched to the full range per map."""
    m = probs.view(-1, heads, height // 2, width // 2).mean(dim=1, keepdim=True)
    m = F.interpolate(m, size=(height, width), mode="bilinear", align_corners=False)
    lo, hi = m.amin(dim=(2, 3), keepdim=True), m.amax(dim=(2, 3), keepdim=True)
    return ((m - lo) / (hi - lo + 1e-8))[:, 0]


def _embeds_file(folder):
    """Where the fixed prompt's embeddings are kept, named after the text encoders' checksums (other encoders never
    get them)."""
    te, te2 = (PIN[1]["text_encoder%s/model.fp16.safetensors" % n][:12] for n in ("", "_2"))
    return os.path.join(folder, "prompt-embeds-%s-%s.safetensors" % (te, te2))


def prompt_embeds(folder, device, dtype=torch.float16, loading=contextlib.nullcontext):
    """PROMPT's embeddings and the empty negative prompt's (zeros) as encode_prompt gives them. The prompt is fixed:
    both text encoders (1.6 GB) run once, the result is kept beside the weights (0.6 MB) and read from then on, the
    same numbers."""
    from safetensors.torch import load_file, save_file
    path = _embeds_file(folder)
    if os.path.isfile(path):
        e = load_file(path, device=str(device))
        return e["pe"], e["npe"], e["ppe"], e["nppe"]
    from diffusers import StableDiffusionXLInpaintPipeline
    with loading():
        enc = StableDiffusionXLInpaintPipeline.from_pretrained(folder, unet=None, vae=None, variant="fp16",
                                                               dtype=dtype, use_safetensors=True).to(device)
    with torch.no_grad():
        pe, npe, ppe, nppe = enc.encode_prompt(PROMPT, device=device, num_images_per_prompt=1,
                                               do_classifier_free_guidance=True)
    del enc
    _free(device)
    try:
        save_file(dict(pe=pe, npe=npe, ppe=ppe, nppe=nppe), path + ".part")
        os.replace(path + ".part", path)
    except OSError:  # a read-only helpers folder: the encoders run again next time
        pass
    return pe, npe, ppe, nppe


def _free(device):
    gc.collect()
    if device == "mps":
        torch.mps.empty_cache()


def _encode(vae, x, generator):
    """x (-1..1) as scaled latents, a sample of the encoder's distribution (it draws from generator)."""
    return vae.encode(x).latent_dist.sample(generator).to(x.dtype) * vae.config.scaling_factor


def run(folder, image, mask, seed=1, steps=STEPS, guidance=GUIDANCE, svds=True, on_step=None, device="mps",
        dtype=torch.float16, loading=contextlib.nullcontext):
    """image without the masked object and its effects, at image's size (a multiple of 16, see prepare()), and the
    attention map (uint8, latent size) for fuse() or effects(). The pinned fp16 weights are read from folder for this
    call, part by part, so that only the UNet and the VAE are in memory together: the object embedding and both
    picture encodings first, then CLIP's image half freed, then the UNet. on_step(i, latents) sees the latents after
    each step (it may raise to stop); loading: a context around each read of weights (to break it off)."""
    from diffusers import AutoencoderKL, EulerDiscreteScheduler, StableDiffusionXLInpaintPipeline, UNet2DConditionModel
    from diffusers.utils.torch_utils import randn_tensor
    from safetensors.torch import load_file
    from transformers import CLIPVisionModelWithProjection
    pe, npe, ppe, nppe = prompt_embeds(folder, device, dtype, loading)
    with loading():
        vae = AutoencoderKL.from_pretrained(folder, subfolder="vae", variant="fp16", dtype=dtype, use_safetensors=True).to(device)
        # only CLIP's image half: the text half of this checkpoint is left unread (transformers warns about it)
        vision = CLIPVisionModelWithProjection.from_pretrained(os.path.join(folder, "image_prompt_encoder"),
                                                               variant="fp16", dtype=dtype, use_safetensors=True).to(device).eval()
        postfuse = Postfuse()
        postfuse.load_state_dict(load_file(os.path.join(folder, "postfuse_module", "model.fp16.safetensors")))
        postfuse = postfuse.to(device, dtype).eval()
    scheduler = EulerDiscreteScheduler.from_pretrained(folder, subfolder="scheduler")
    pipe = StableDiffusionXLInpaintPipeline(vae=vae, text_encoder=None, text_encoder_2=None, tokenizer=None,
                                            tokenizer_2=None, unet=None, scheduler=scheduler)
    pipe.set_progress_bar_config(disable=True)
    w, h = image.size
    pixels = pipe.image_processor.preprocess(image, height=h, width=w).to(torch.float32)
    binary = pipe.mask_processor.preprocess(mask, height=h, width=w)
    _, token = object_embedding(vision, postfuse, pixels.to(device), binary.to(device))
    del vision, postfuse
    with torch.no_grad():
        pe = put_object(pe, token)
        # draws in the maker's order: start latents, noise, condition latents (the same picture encoded twice)
        g = torch.Generator("cpu").manual_seed(seed)
        x = pixels.to(device, pe.dtype)
        start = _encode(vae, x, g)
        noise = randn_tensor(start.shape, generator=g, device=torch.device(device), dtype=pe.dtype)
        cond = _encode(vae, x, g)
    _free(device)
    with loading():
        pipe.register_modules(unet=UNet2DConditionModel.from_pretrained(folder, subfolder="unet", variant="fp16",
                                                                        dtype=dtype, use_safetensors=True).to(device))
    layer = pipe.unet.get_submodule(LAYER)
    keep = _KeepToken(TOKEN)

    def step_end(p, i, t, kw):
        lat = kw["latents"]
        if svds and i == 0 and steps > 1:
            m = kw["mask"][:1]
            lat = (1 - m) * p.scheduler.add_noise(start, noise, p.scheduler.timesteps[1:2]) + m * lat
        if i == steps - 2:
            layer.set_processor(keep)
        if on_step:
            on_step(i, lat)
        return {"latents": lat}

    if steps == 1:
        layer.set_processor(keep)
    with torch.no_grad():
        out = pipe(prompt_embeds=pe, negative_prompt_embeds=npe, pooled_prompt_embeds=ppe,
                   negative_pooled_prompt_embeds=nppe, image=image, mask_image=mask, masked_image_latents=cond,
                   latents=noise, height=h, width=w, strength=1.0, num_inference_steps=steps,
                   guidance_scale=guidance, generator=g, callback_on_step_end=step_end,
                   callback_on_step_end_tensor_inputs=["latents", "mask"]).images[0]
    cond_map = attention_map(keep.probs, layer.heads, h // 8, w // 8)[-1]
    # numpy keeps float16 here (as the maker's run did): the truncation to uint8 must round alike
    return out, (cond_map.cpu().numpy() * 255.0).astype(np.uint8)


def effects(attention, grown):
    """Where the attention map (uint8, latent size) marks the object and its effects, as 0/1 at the size of grown (the
    grown mask at the picture's size): thresholded and widened as fuse() does it at the working size, and only the
    parts that touch the grown mask (another object's shadow stays)."""
    ah, aw = attention.shape
    work = (aw * 8, ah * 8)
    core = cv2.resize((attention > THRESHOLD).astype(np.uint8), work, interpolation=cv2.INTER_NEAREST)
    wide = cv2.dilate(core, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (WIDEN, WIDEN)))
    # area, not nearest: a thin stroke must not vanish when the mask is made smaller
    near = cv2.resize(grown.astype(np.float32), work, interpolation=cv2.INTER_AREA) > 0
    _, labels = cv2.connectedComponents((wide.astype(bool) | near).astype(np.uint8))
    keep = np.isin(labels, np.unique(labels[near])) & (wide > 0)
    h, w = grown.shape
    return (cv2.resize(keep.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR) >= 0.5).astype(np.uint8)


def _blur(x, radius):
    """One wavelet level per channel of x [c, h, w]: a 3×3 binomial blur, at radius > 1 also down and up by radius."""
    from scipy.ndimage import convolve, zoom
    k = np.outer((0.25, 0.5, 0.25), (0.25, 0.5, 0.25)).astype(np.float32)
    out = np.empty_like(x)
    for c in range(x.shape[0]):
        b = convolve(x[c], k, mode="nearest")
        out[c] = zoom(zoom(b, 1 / radius, order=1), radius, order=1) if radius > 1 else b
    return out


def _bands(x, levels=LEVELS):
    """x [c, h, w] split into its detail (sum of all levels) and what is left after the coarsest blur."""
    detail = np.zeros_like(x)
    for i in range(levels):
        low = _blur(x, 2 ** i)
        detail += x - low
        x = low
    return detail, x


def colour_fix(detail_from, colour_from):
    """The detail of one picture over the coarse colours of another (uint8 or float 0..255, h×w×3; sides a multiple
    of 2**(LEVELS-1): the down and up scaling must land on the same size)."""
    a = np.moveaxis(detail_from.astype(np.float32) / 255.0, 2, 0)
    b = np.moveaxis(colour_from.astype(np.float32) / 255.0, 2, 0)
    out = _bands(a)[0] + _bands(b)[1]
    return np.clip(np.moveaxis(out, 0, 2) * 255.0, 0, 255).astype(np.uint8)


def fuse(original, removed, attention):
    """The model's result put into the original (both uint8 h×w×3 at the working size) where the attention map
    (uint8, any size) marks object and effects, with a soft widened edge; elsewhere the original's detail over the
    result's coarse colours (the result is a little off in colour everywhere)."""
    h, w = original.shape[:2]
    core = cv2.resize((attention > THRESHOLD).astype(np.float32), (w, h), interpolation=cv2.INTER_NEAREST)
    wide = cv2.dilate(core, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (WIDEN, WIDEN)))
    soft = np.clip(np.maximum(core, cv2.GaussianBlur(wide, (BLUR, BLUR), SIGMA)), 0, 1)[..., None]
    outside = 1 - core[..., None]
    # mirrored to a multiple of the coarsest level, as the wavelet steps need; cropped back after
    step = 2 ** (LEVELS - 1)
    pad = ((0, -h % step), (0, -w % step), (0, 0))
    base = colour_fix(np.pad(original * outside, pad, mode="reflect"),
                      np.pad(removed * outside, pad, mode="reflect"))[:h, :w]
    return (base * (1 - soft) + removed * soft).astype(np.uint8)
