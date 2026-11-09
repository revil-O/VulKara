# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""ERNIE-Image: recognised from its repository, run by MLX; the prompt enhancer is a helper model of its own."""
import os
import sys

import importer
import registry

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "mlx"))

INDEX = {"_class_name": "ErnieImagePipeline", "scheduler": ["diffusers", "FlowMatchEulerDiscreteScheduler"],
         "pe": ["transformers", "Ministral3ForCausalLM"], "pe_tokenizer": ["transformers", "TokenizersBackend"],
         "text_encoder": ["transformers", "Mistral3Model"], "tokenizer": ["transformers", "TokenizersBackend"],
         "transformer": ["diffusers", "ErnieImageTransformer2DModel"], "vae": ["diffusers", "AutoencoderKLFlux2"]}


def test_turbo_and_the_sft_model_are_recognised():
    assert registry.detect_from_model_index(INDEX, {}, "baidu/ERNIE-Image-Turbo") == ("ernie_image", {})
    arch, overrides = registry.detect_from_model_index(INDEX, {}, "baidu/ERNIE-Image")
    assert arch == "ernie_image" and overrides == {"num_steps": 50, "guidance_scale": 4.0}
    spec = registry.ARCHS["ernie_image"]
    assert spec["runtime"] == "mlx" and spec["defaults"]["guidance_scale"] == 1.0 and spec["defaults"]["num_steps"] == 8
    assert registry.family_label("ernie") == "ERNIE-Image" and "ernie" not in registry.FOREIGN_FAMILIES


def test_the_prompt_enhancer_is_not_downloaded():
    files = ["model_index.json", "pe/config.json", "pe/model.safetensors", "pe_tokenizer/tokenizer.json",
             "text_encoder/config.json", "text_encoder/model.safetensors", "tokenizer/tokenizer.json",
             "transformer/config.json", "transformer/diffusion_pytorch_model.safetensors",
             "vae/config.json", "vae/diffusion_pytorch_model.safetensors", "scheduler/scheduler_config.json"]
    wanted, _ = importer._repo_plan_files(files, INDEX)
    assert not [f for f in wanted if f.startswith(("pe/", "pe_tokenizer/"))]
    assert "transformer/diffusion_pytorch_model.safetensors" in wanted and "tokenizer/tokenizer.json" in wanted


def test_fits_16_gb_with_mlx():
    info = {"arch": "ernie_image", "components": dict(registry.ARCHS["ernie_image"]["fallback_params"]),
            "denoiser": "transformer"}
    assert importer.make_plan(info, ram_gb=16)["fits"]


def test_the_prompt_enhancer_is_a_pinned_helper_with_the_pipelines_message():
    import ernie_pe
    import helpers
    import pinned
    h = next(x for x in helpers.catalog() if x["id"] == "ernie_pe")
    revision, files = pinned.pins(h["repo"])
    assert h["kind"] == "pup" and len(revision) == 40 and files["pe/model.safetensors"] and "pe/chat_template.jinja" in files
    # the user message as diffusers' ErnieImagePipeline builds it: the prompt and the size as JSON
    [m] = ernie_pe.messages("a red fox", 1024, 768)
    assert m["role"] == "user" and m["content"] == '{"prompt": "a red fox", "width": 1024, "height": 768}'
    # laid out as Baidu's chat template does, with the instruction in English so the description comes in English
    text = ernie_pe.prompt_text("<s>", "a red fox", 1024, 768)
    assert text.startswith("<s>[SYSTEM_PROMPT]") and "in English" in text
    assert text.endswith('[/SYSTEM_PROMPT][INST]{"prompt": "a red fox", "width": 1024, "height": 768}[/INST]')
