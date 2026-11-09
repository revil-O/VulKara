# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""ERNIE-Image's prompt enhancer (PE): the Ministral 3 3B model in pe/ of baidu/ERNIE-Image-Turbo (Apache-2.0), run
with mlx_lm as diffusers' ErnieImagePipeline runs it (_enhance_prompt_with_pe): the user message is JSON with the
prompt and the picture size, sampled at temperature 0.6 and top-p 0.95. Baidu's chat template carries the instruction
in Chinese (expand the short description into a rich visual one, output only the description) and the model then
writes Chinese; the same instruction in English makes it write English (the description is shown to the user as the
picture's note, and ERNIE reads both), so the prompt is built here with the template's markers instead of the
template. Loaded for one prompt and freed again; a 16 GB Mac has the image model unloaded first (main.py)."""
import gc
import json
import os

MAX_TOKENS = 1024
TEMPERATURE, TOP_P = 0.6, 0.95
# Baidu's system prompt (pe/chat_template.jinja) in English: the model answers in the language it is instructed in
SYSTEM = ("You are a professional prompt enhancer for text-to-image models. You receive the user's short picture "
          "description and the target resolution; expand it into a rich, detailed visual description in English that "
          "helps a text-to-image model paint a high-quality picture. Output only the enhanced description, without any "
          "explanation or prefix.")


def messages(prompt, width, height):
    return [{"role": "user", "content": json.dumps({"prompt": prompt, "width": width, "height": height}, ensure_ascii=False)}]


def prompt_text(bos_token, prompt, width, height):
    """The whole prompt as the chat template lays it out (bos, [SYSTEM_PROMPT], [INST]), with the English instruction."""
    [m] = messages(prompt, width, height)
    return (bos_token or "") + "[SYSTEM_PROMPT]" + SYSTEM + "[/SYSTEM_PROMPT][INST]" + m["content"] + "[/INST]"


def enhancer_gb(folder):
    """What the enhancer holds in memory: its weights as on disk (16 bit)."""
    return sum(os.path.getsize(os.path.join(folder, f)) for f in os.listdir(folder) if f.endswith(".safetensors")) / 1024 ** 3


def enhance(folder, prompt, width, height, seed, stop=None):
    """The prompt rewritten; stop: called after each token, it raises to end the writing (Stop on the job)."""
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.sample_utils import make_sampler
    model, tokenizer = load(folder)
    try:
        text = prompt_text(tokenizer.bos_token, prompt, width, height)
        mx.random.seed(seed)  # the same prompt and seed give the same description
        parts = []
        for response in stream_generate(model, tokenizer, text, max_tokens=MAX_TOKENS,
                                        sampler=make_sampler(temp=TEMPERATURE, top_p=TOP_P)):
            parts.append(response.text)
            if stop is not None:
                stop()
    finally:
        del model
        gc.collect()
        mx.clear_cache()
    caption = "".join(parts).strip()
    if not caption:
        raise RuntimeError("The prompt enhancer wrote nothing")
    return caption
