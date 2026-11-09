# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Prompt from a picture (Image to image): Qwen3-VL 2B Instruct describes the picture as one English paragraph an
image model can take as its prompt. 16 bit on the GPU: 8-12 s a picture and a 5.3 GB peak on a 16 GB Mac mini; 8 bit
(optimum-quanto) was 5-6 times slower and saved nothing at the peak (MEASUREMENTS 7br).

    python main.py caption_image <image>   __progress__ lines, then __caption__ {"text": ...} or __error__ {"error": ...}
"""
import json
import os
import re

HELPER = "qwen3_vl"
# every text of 7br ended on its own within 156-212 tokens; 200 cut them mid-sentence (7bn)
MAX_TOKENS = 300
# the pictures of 7br were about 1 megapixel; a larger one is made smaller first (fewer picture tokens, same text)
MAX_SIDE = 1024
ASK = ("Write one paragraph that an image generator can use as its prompt to make this picture again: the subject, "
       "the setting, the light, the colours, the style and the camera. Only the paragraph.")


def messages(image):
    return [{"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text": ASK}]}]


def whole_sentences(text, ended):
    """The text, cut back to its last full sentence when it ran into the token limit."""
    text = text.strip()
    if ended:
        return text
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", text)]
    return text[:ends[-1]] if ends else text


def folder(report=None):
    import helpers
    import pinned
    import restore
    path = restore.helper_folder(HELPER)
    # complete only with the download's mark, written after its last file: stopped after the weights, the processor
    # files were missing and every later try failed
    repo = next(h["repo"] for h in helpers.catalog() if h["id"] == HELPER)
    if pinned._checked(path).get("revision") != pinned.pins(repo)[0]:
        helpers.install(HELPER, report=report)
    return path


def describe(path, report=lambda stage, pct: None):
    import colour
    import torch
    from transformers import AutoProcessor, Qwen3VLForConditionalGeneration
    where = folder(lambda message: report(message, -1))
    image = colour.open_rgb(path)
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    report("Loading Qwen3-VL 2B", -1)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = Qwen3VLForConditionalGeneration.from_pretrained(where, dtype=torch.bfloat16).to(device).eval()
    processor = AutoProcessor.from_pretrained(where)
    report("Describing the picture", -1)
    inputs = processor.apply_chat_template(messages(image), tokenize=True, add_generation_prompt=True,
                                           return_dict=True, return_tensors="pt").to(device)
    with torch.inference_mode():
        out = model.generate(**inputs, max_new_tokens=MAX_TOKENS, do_sample=False)
    new = out[0, inputs["input_ids"].shape[1]:]
    return whole_sentences(processor.decode(new, skip_special_tokens=True), len(new) < MAX_TOKENS)


def main(argv):
    def report(stage, pct):
        print("__progress__ " + json.dumps({"stage": stage, "progress": pct}), flush=True)

    try:
        text = describe(argv[0], report)
        if not text:
            raise RuntimeError("Qwen3-VL wrote nothing")
        print("__caption__ " + json.dumps({"text": text}), flush=True)
        return 0
    except Exception as e:
        print("__error__ " + json.dumps({"error": str(e)}), flush=True)
        return 1
