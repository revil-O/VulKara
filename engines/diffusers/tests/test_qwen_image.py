# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Qwen-Image (20B MMDiT) and Qwen-Image 2.1 (7B): detection, GGUF headers, RAM plans, the import of single
files from a Hugging Face repo and the prompt encoding. No network: the Hub is replaced by fakes."""
import hashlib
import shutil
import types

import numpy as np
import pytest

import engine
import importer
import memory
import registry
import samplers

# tensor names as in city96/Qwen-Image-gguf and abenzerps/Qwen-Image-2.1-Uncensored-GGUF (header read with a
# range request), shapes in GGUF order
QWEN_IMAGE = {"img_in.weight": [64, 3072], "txt_in.weight": [3584, 3072], "txt_norm.weight": [3584],
              "time_text_embed.timestep_embedder.linear_1.weight": [256, 3072],
              "transformer_blocks.0.img_mod.1.weight": [3072, 18432], "transformer_blocks.0.txt_mod.1.weight": [3072, 18432],
              "transformer_blocks.0.img_mlp.net.0.proj.weight": [3072, 12288],
              "transformer_blocks.0.txt_mlp.net.0.proj.weight": [3072, 12288],
              "transformer_blocks.0.attn.add_q_proj.weight": [3072, 3072],
              "norm_out.linear.weight": [3072, 6144], "proj_out.weight": [3072, 64]}
QWEN_IMAGE_21 = {"img_in.weight": [64, 4096], "txt_in.in_layer.weight": [4096, 4096], "txt_in.text_norm.weight": [4096],
                 "txt_in.out_layer.weight": [4096, 4096],
                 "time_text_embed.timestep_embedder.linear_1.weight": [256, 4096],
                 "transformer_blocks.0.attn.to_q.weight": [4096, 4096],
                 "transformer_blocks.0.img_mlp.gate_layer.weight": [4096, 12288],
                 "transformer_blocks.0.img_mlp.proj.weight": [4096, 12288],
                 "norm_out.linear.weight": [4096, 4096], "proj_out.weight": [4096, 64]}


def test_single_files_are_recognised_by_their_tensor_names():
    arch, layout, overrides, params = registry.detect_from_single_file(QWEN_IMAGE, "city96/Qwen-Image-gguf/qwen-image-Q4_K_S.gguf")
    assert (arch, layout, overrides) == ("qwen_image", "single_denoiser", {}) and params > 0
    arch, layout, _, _ = registry.detect_from_single_file(QWEN_IMAGE_21, "x/qwen-image-2.1-UC-Q4_K_M.gguf")
    assert (arch, layout) == ("qwen_image21", "single_denoiser")
    # ComfyUI checkpoints carry the prefix of the diffusion model
    comfy = {"model.diffusion_model." + k: v for k, v in QWEN_IMAGE_21.items()}
    assert registry.detect_from_single_file(comfy, "qwen_image_2.1_bf16.safetensors")[0] == "qwen_image21"


def test_edit_models_and_other_pipelines_are_refused():
    with pytest.raises(registry.UnsupportedModel, match="Edit"):
        registry.detect_from_single_file(QWEN_IMAGE, "QuantStack/Qwen-Image-Edit-GGUF/Qwen_Image_Edit-Q4_K_M.gguf")
    with pytest.raises(registry.UnsupportedModel, match="Qwen-Image"):
        registry.detect_from_model_index({"_class_name": "QwenImageEditPlusPipeline"})
    # "credit" is no edit model
    assert registry.detect_from_single_file(QWEN_IMAGE, "x/credit-qwen-image-Q4.gguf")[0] == "qwen_image"


def test_diffusers_repos_and_distilled_defaults():
    assert registry.detect_from_model_index({"_class_name": "QwenImagePipeline"}, {}, "Qwen/Qwen-Image-2512") \
        == ("qwen_image", {})
    assert registry.detect_from_model_index({"_class_name": "QwenImage21Pipeline"}, {}, "Qwen/Qwen-Image-2.1")[0] \
        == "qwen_image21"
    # few-step distillations: no guidance is true_cfg_scale 1 for these pipelines, not 0
    _, overrides = registry.detect_from_model_index({"_class_name": "QwenImagePipeline"}, {}, "x/Qwen-Image-Lightning")
    assert overrides == {"num_steps": 4, "guidance_scale": 1.0}


def test_specs_follow_the_pipelines():
    qi, q21 = registry.ARCHS["qwen_image"], registry.ARCHS["qwen_image21"]
    assert qi["base_repo"] == "Qwen/Qwen-Image" and not qi.get("gated")
    assert qi["defaults"]["width"] == 1328 and 1328 in qi["resolutions"] and 928 in qi["resolutions"]
    assert all(r % qi["size_multiple"] == 0 for r in qi["resolutions"])
    assert all(r % q21["size_multiple"] == 0 for r in q21["resolutions"])
    assert qi["guidance_param"] == q21["guidance_param"] == "true_cfg_scale"
    assert q21["img2img"] and q21["image_reference"] and not q21.get("inpaint_pipeline")
    assert "flow_heun" not in samplers.for_family("qwen_image") and "flow_euler" in samplers.for_family("qwen_image21")


def _write_gguf(path, names):
    import gguf
    w = gguf.GGUFWriter(str(path), "qwen_image")
    for name in names:
        w.add_tensor(name, np.zeros((2, 32), np.float32))
    w.write_header_to_file()
    w.write_kv_data_to_file()
    w.write_tensors_to_file()
    w.close()


def test_gguf_header_from_the_first_bytes(tmp_path):
    path = tmp_path / "m.gguf"
    _write_gguf(path, list(QWEN_IMAGE_21))
    data = path.read_bytes()
    assert registry.parse_gguf_header(data) == registry.read_gguf_header(str(path))
    with pytest.raises(registry.IncompleteHeader):
        registry.parse_gguf_header(data[:200])
    with pytest.raises(registry.UnsupportedModel):
        registry.parse_gguf_header(b"PK\x03\x04" + data[4:])


def _lora(tmp_path, names):
    from safetensors.numpy import save_file
    path = str(tmp_path / "lora.safetensors")
    save_file({n: np.zeros((4, 4), np.float16) for n in names}, path)
    return path


def test_lora_families(tmp_path):
    qi = _lora(tmp_path, ["transformer.transformer_blocks.0.img_mod.1.lora_A.weight",
                          "transformer.transformer_blocks.0.img_mod.1.lora_B.weight"])
    assert registry.inspect_lora(qi)["family"] == "qwen_image"
    kohya = _lora(tmp_path, ["lora_unet_transformer_blocks_0_txt_mlp_net_2.lora_down.weight",
                             "lora_unet_transformer_blocks_0_txt_mlp_net_2.lora_up.weight"])
    assert registry.inspect_lora(kohya)["family"] == "qwen_image"
    q21 = _lora(tmp_path, ["transformer.transformer_blocks.0.img_mlp.gate_layer.lora_A.weight",
                           "transformer.transformer_blocks.0.img_mlp.gate_layer.lora_B.weight"])
    assert registry.inspect_lora(q21)["family"] == "qwen_image21"
    # FLUX in its original names has an img_mlp too, in double blocks
    flux = _lora(tmp_path, ["diffusion_model.double_blocks.0.img_mlp.0.lora_A.weight",
                            "diffusion_model.double_blocks.0.img_mlp.0.lora_B.weight"])
    assert registry.inspect_lora(flux)["family"].startswith("flux")


def _gguf_plan(arch, gguf_gb, ram):
    spec = registry.ARCHS[arch]
    return memory.plan(spec["fallback_params"], "transformer", spec["family"], ram, denoiser_fixed_gb=gguf_gb)


def test_memory_plans_of_the_gguf_files():
    q4 = _gguf_plan("qwen_image21", 4.29, 24)  # Qwen-Image 2.1 Q4_K_M: text encoder 8 bit, both resident
    assert q4["fits"] and q4["quant"] == {"transformer": "gguf", "text_encoder": "q8"} and not q4["staged_text_encoder"]
    q8 = _gguf_plan("qwen_image21", 7.07, 24)  # Q8_0: the text encoder is loaded per prompt
    assert q8["fits"] and q8["staged_text_encoder"]
    assert not _gguf_plan("qwen_image21", 4.29, 16)["fits"]
    # Qwen-Image's 20B transformer in 4 bit (11.3 GB) needs a 32 GB Mac
    assert not _gguf_plan("qwen_image", 11.31, 24)["fits"] and _gguf_plan("qwen_image", 11.31, 32)["fits"]


def test_gguf_files_stream_too():
    info = {"layout": "single_denoiser", "denoiser_fixed_gb": 11.3}
    assert importer._streamable(info)


# ------------------------------------------------------------ import from a repo without diffusers layout

REPO = {"README.md": 9000, "qwen-image-2.1-UC-Q8_0.gguf": 7_590_000_000, "qwen-image-2.1-UC-Q4_K_M.gguf": 4_600_000_000,
        "qwen-image-2.1-UC-fp8.safetensors": 7_120_000_000, "qwen-image-2.1-UC-MLX-4bit.safetensors": 4_000_000_000,
        "qwen-image-2.1-uncensored-lora.safetensors": 30_000_000,
        "text_encoders/qwen3vl_8b_bf16.safetensors": 17_530_000_000, "vae/qwen_image_2.1_vae_bf16.safetensors": 676_000_000}


def test_candidates_leave_out_encoders_vaes_loras_and_other_formats():
    assert importer.model_file_candidates(REPO) == ["qwen-image-2.1-UC-Q4_K_M.gguf", "qwen-image-2.1-UC-Q8_0.gguf",
                                                    "qwen-image-2.1-UC-fp8.safetensors"]


def test_a_repo_without_model_index_names_its_model_files(monkeypatch):
    from huggingface_hub.utils import EntryNotFoundError

    def no_index(repo, filename, token):
        raise EntryNotFoundError("404")

    monkeypatch.setattr(importer, "_hf_json", no_index)
    monkeypatch.setattr(importer, "_hf_repo_info", lambda repo, token: (None, REPO))
    with pytest.raises(registry.UnsupportedModel) as e:
        importer.inspect("hf", "abenzerps/Qwen-Image-2.1-Uncensored-GGUF")
    msg = str(e.value)
    assert msg.startswith(importer.NO_LAYOUT) and importer.PICK_FILE in msg
    assert "qwen-image-2.1-UC-Q4_K_M.gguf (4.3 GB), qwen-image-2.1-UC-Q8_0.gguf (7.1 GB)" in msg
    assert "text_encoders" not in msg and "lora" not in msg and "MLX" not in msg

    many = {"q%02d.gguf" % i: (i + 1) * 1024 ** 3 for i in range(15)}
    monkeypatch.setattr(importer, "_hf_repo_info", lambda repo, token: (None, many))
    with pytest.raises(registry.UnsupportedModel, match="and 3 more$"):
        importer.inspect("hf", "x/many")


BASE_INDEX = {"_class_name": "QwenImage21Pipeline", "processor": ["transformers", "Qwen3VLProcessor"],
              "scheduler": ["diffusers", "FlowMatchEulerDiscreteScheduler"],
              "text_encoder": ["transformers", "Qwen3VLForConditionalGeneration"],
              "transformer": ["diffusers", "QwenImage21Transformer2DModel"], "vae": ["diffusers", "AutoencoderKLQwenImage21"]}
BASE_FILES = {"model_index.json": 1, "processor/tokenizer.json": 1, "scheduler/scheduler_config.json": 1,
              "text_encoder/config.json": 1, "text_encoder/model-00001-of-00002.safetensors": 9 * 1024 ** 3,
              "text_encoder/model-00002-of-00002.safetensors": 8 * 1024 ** 3,
              "text_encoder/model.safetensors.index.json": 1, "transformer/config.json": 1,
              "transformer/diffusion_pytorch_model.safetensors": 14 * 1024 ** 3,
              "vae/config.json": 1, "vae/diffusion_pytorch_model.safetensors": 1024 ** 3}


def test_a_gguf_file_from_the_hub_is_planned_from_its_header(monkeypatch):
    import huggingface_hub
    file = "qwen-image-2.1-UC-Q4_K_M.gguf"

    class Api:
        def __init__(self, token=None):
            pass

        def model_info(self, repo, files_metadata=False):
            return types.SimpleNamespace(siblings=[types.SimpleNamespace(rfilename=f, size=n) for f, n in REPO.items()])

    monkeypatch.setattr(huggingface_hub, "HfApi", Api)
    monkeypatch.setattr(importer, "_hf_gguf_shapes", lambda repo, f, token: QWEN_IMAGE_21 if f == file else None)
    monkeypatch.setattr(importer, "_hf_repo_info", lambda repo, token: (None, BASE_FILES))
    monkeypatch.setattr(importer, "_hf_json", lambda repo, f, token: BASE_INDEX)
    monkeypatch.setattr(importer, "_params_from_hf", lambda api, repo, files: {"text_encoder": 8.77, "vae": 0.34})
    info = importer.inspect("hf", "abenzerps/Qwen-Image-2.1-Uncensored-GGUF", file=file)
    assert (info["arch"], info["layout"], info["base_repo"]) == ("qwen_image21", "single_denoiser", "Qwen/Qwen-Image-2.1")
    assert set(info["components"]) == {"text_encoder", "transformer", "vae"}  # the processor has no weights
    assert info["gguf"] and abs(info["denoiser_fixed_gb"] - 4.6e9 / 1024 ** 3) < 1e-6
    # the base repo's transformer is not downloaded, the GGUF file replaces it
    assert abs(info["download_bytes"] - (18 * 1024 ** 3 + 4_600_000_000)) < 100  # + configs
    plan = importer.make_plan(info, ram_gb=24)
    assert plan["fits"] and plan["quant"]["transformer"] == "gguf" and not plan.get("streamed")

    # without a readable header the file name tells (the header is checked after the download)
    monkeypatch.setattr(importer, "_hf_gguf_shapes", lambda repo, f, token: None)
    assert importer.inspect("hf", "abenzerps/Qwen-Image-2.1-Uncensored-GGUF", file=file)["arch"] == "qwen_image21"


def test_names_of_gguf_files():
    assert importer._guess_from_name("city96/Qwen-Image-gguf/qwen-image-Q4_K_S.gguf")[0] == "qwen_image"
    assert importer._guess_from_name("x/qwen-image-2.1-Q8_0.gguf")[0] == "qwen_image21"
    assert importer._guess_from_name("x/Qwen_Image_2_1-Q4.gguf")[0] == "qwen_image21"


def test_an_old_runtime_is_named_before_the_download(monkeypatch):
    import importlib.metadata as md
    versions = {"diffusers": "0.40.0", "torchvision": "0.29.1"}

    def version(name):
        if name not in versions:
            raise md.PackageNotFoundError(name)
        return versions[name]

    monkeypatch.setattr(md, "version", version)
    assert "diffusers 0.41 or newer" in registry.runtime_too_old("qwen_image21")
    assert registry.runtime_too_old("qwen_image") is None
    versions["diffusers"] = "0.41.0"
    assert registry.runtime_too_old("qwen_image21") is None
    del versions["torchvision"]
    assert "torchvision" in registry.runtime_too_old("qwen_image21")


# ------------------------------------------------------------ prompt encoding (staged text encoder)

class FakeTextPipe:
    def __init__(self, extra=()):
        self.prompts, self.extra = [], tuple(extra)

    def encode_prompt(self, prompt, device=None):
        import torch
        self.prompts.append(prompt)
        return (torch.ones(1, 3, 8), None if prompt == " " else torch.ones(1, 3, dtype=torch.long)) + self.extra


@pytest.mark.parametrize("arch, extra", [("qwen_image", ()), ("qwen_image21", ("image_pad_mask",))])
def test_staged_encoding_guides_with_an_empty_negative_prompt(arch, extra):
    spec = registry.ARCHS[arch]
    pipe = FakeTextPipe(extra)
    out = engine._encode(pipe, spec, "a lighthouse", "", 4.0, "cpu")
    assert pipe.prompts == ["a lighthouse", " "]
    assert set(out) == {"prompt_embeds", "prompt_embeds_mask", "negative_prompt_embeds", "negative_prompt_embeds_mask"}
    pipe = FakeTextPipe(extra)
    out = engine._encode(pipe, spec, "a lighthouse", "fog", 1.0, "cpu")
    assert pipe.prompts == ["a lighthouse"] and set(out) == {"prompt_embeds", "prompt_embeds_mask"}


def test_encoded_masks_keep_their_type():
    import torch
    lm = engine.LoadedModel.__new__(engine.LoadedModel)
    lm.embed_cache, lm.text_pipe, lm.staged, lm.dtype = None, FakeTextPipe(), False, torch.bfloat16
    lm.spec, lm.device = registry.ARCHS["qwen_image"], "cpu"
    out = lm.encode("a lighthouse", "", 4.0)
    assert out["prompt_embeds"].dtype == torch.bfloat16 and out["prompt_embeds_mask"].dtype == torch.long
    assert "negative_prompt_embeds_mask" not in out  # no padding: the pipeline takes no mask


def test_staged_encoding_lets_go_of_the_text_encoder(monkeypatch):
    # staged (16 GB): the text encoder is loaded for a new prompt and dropped after; the pipeline kept it before (18.7 GB)
    import torch
    lm = engine.LoadedModel.__new__(engine.LoadedModel)
    lm.embed_cache, lm.text_pipe, lm.staged, lm.dtype = None, FakeTextPipe(), True, torch.bfloat16
    lm.spec, lm.device = registry.ARCHS["qwen_image"], "cpu"
    monkeypatch.setattr(engine.prompt_cache, "limit_gb", lambda: 0)
    lm.encode("a lighthouse", "", 4.0)
    assert lm.text_pipe is None


def test_gguf_weights_outside_linear_layers_are_unpacked_once():
    """A BF16 norm weight stays raw bytes after a GGUF load (twice its length); the norm must get real values."""
    torch = pytest.importorskip("torch")
    gguf = pytest.importorskip("gguf")
    from diffusers.quantizers.gguf.utils import GGUFLinear, GGUFParameter

    values = torch.arange(8, dtype=torch.bfloat16)
    norm = torch.nn.Module()
    norm.weight = GGUFParameter(values.view(torch.uint8), quant_type=gguf.GGMLQuantizationType.BF16)
    linear = GGUFLinear(4, 4, bias=False, compute_dtype=torch.float32)
    linear.weight = GGUFParameter(torch.zeros(4, 4, dtype=torch.bfloat16).view(torch.uint8), quant_type=gguf.GGMLQuantizationType.BF16)
    model = torch.nn.Sequential(norm, linear)
    assert norm.weight.shape[-1] == 16  # bytes
    engine._dequantize_gguf_outside_linear(model, torch.float32)
    assert norm.weight.shape == (8,) and not hasattr(norm.weight, "quant_type")
    assert torch.equal(norm.weight, values.float())
    assert hasattr(linear.weight, "quant_type")  # the linear layer unpacks its own weight while computing
    # a buffer too (SD 3.5's pos_embed from a GGUF copy, MEASUREMENTS 7bk)
    table = torch.nn.Module()
    table.register_buffer("pos_embed", GGUFParameter(values.view(torch.uint8), quant_type=gguf.GGMLQuantizationType.BF16))
    engine._dequantize_gguf_outside_linear(torch.nn.Sequential(table), torch.float32)
    assert table.pos_embed.shape == (8,) and torch.equal(table.pos_embed, values.float())


def test_an_import_without_a_name_is_named_after_its_file_unless_the_file_name_says_nothing():
    assert importer.default_name("hf", "Limbicnation/pixel-art-lora", "pytorch_lora_weights.safetensors") == "pixel-art-lora"
    assert importer.default_name("hf", "abenzerps/Qwen-Image-2.1-Uncensored-GGUF", "qwen-image-2.1-UC-Q4_K_M.gguf") \
        == "qwen-image-2.1-UC-Q4_K_M"
    assert importer.default_name("hf", "black-forest-labs/FLUX.2-klein-4B") == "FLUX.2-klein-4B"
    assert importer.default_name("file", "/x/model.safetensors") == "model"


def test_a_repo_import_takes_files_another_model_already_has(tmp_path, monkeypatch):
    """The official repo after a GGUF import of the same model: its text encoder is copied, not downloaded again."""
    monkeypatch.setattr(importer, "progress", lambda *a, **k: None)
    other = tmp_path / "qwen-gguf" / "base" / "text_encoder"
    other.mkdir(parents=True)
    (other / "model-00001-of-00002.safetensors").write_bytes(b"x" * 10)
    (other / "model-00002-of-00002.safetensors").write_bytes(b"y" * 7)
    # FLUX.1's VAE: the same path and size as SD 3.5's, another content
    vae = tmp_path / "FLUX.1-dev" / "weights" / "vae"
    vae.mkdir(parents=True)
    (vae / "diffusion_pytorch_model.safetensors").write_bytes(b"f" * 5)
    target = tmp_path / "Qwen-Image-2.1"
    target.mkdir()
    sha = lambda b: hashlib.sha256(b).hexdigest()
    info = {"files": ["text_encoder/model-00001-of-00002.safetensors", "text_encoder/model-00002-of-00002.safetensors",
                      "transformer/diffusion_pytorch_model.safetensors", "vae/diffusion_pytorch_model.safetensors",
                      "model_index.json"],
            "file_sizes": {"text_encoder/model-00001-of-00002.safetensors": 10,
                           "text_encoder/model-00002-of-00002.safetensors": 8,  # another size: not the same file
                           "transformer/diffusion_pytorch_model.safetensors": 99,
                           "vae/diffusion_pytorch_model.safetensors": 5, "model_index.json": 1},
            "file_sha256": {"text_encoder/model-00001-of-00002.safetensors": sha(b"x" * 10).upper(),
                            "vae/diffusion_pytorch_model.safetensors": sha(b"s" * 5)}}
    left = importer._reuse_repo_files(info, target)
    assert (target / "weights" / "text_encoder" / "model-00001-of-00002.safetensors").read_bytes() == b"x" * 10
    assert left == ["text_encoder/model-00002-of-00002.safetensors", "transformer/diffusion_pytorch_model.safetensors",
                    "vae/diffusion_pytorch_model.safetensors", "model_index.json"]
    # without the Hub's checksum nothing is taken over
    del info["file_sha256"]
    shutil.rmtree(target / "weights")
    assert len(importer._reuse_repo_files(info, target)) == 5



def test_an_empty_model_keeps_what_it_computes_itself():
    """Qwen-Image 2.1's rotary frequencies are a plain list made in __init__: a model built for the quantized cache
    must keep them real ("Cannot copy out of meta tensor" at the first step otherwise)."""
    torch = pytest.importorskip("torch")
    rope = pytest.importorskip("diffusers.models.transformers.transformer_qwenimage21").QwenImage21Rope

    with engine._meta_weights():
        model = torch.nn.Sequential(torch.nn.Linear(4, 4), rope(10000, [16, 56, 56]))
    assert model[0].weight.device.type == "meta"
    assert all(f.device.type == "cpu" for f in model[1].freqs)
