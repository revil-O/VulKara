# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""LoRAs baked into a new model (merge.py), with a tiny SD 1.5 pipeline of random weights and a tiny LoRA."""
import json
import os

import pytest

torch = pytest.importorskip("torch")
diffusers = pytest.importorskip("diffusers")
pytest.importorskip("peft")
import importer  # noqa: E402
import merge  # noqa: E402


def _tiny_model(folder):
    """A diffusers folder of a tiny SD 1.5 pipeline (no text encoder: the LoRA only changes the UNet)."""
    from diffusers import AutoencoderKL, PNDMScheduler, StableDiffusionPipeline, UNet2DConditionModel
    torch.manual_seed(0)
    unet = UNet2DConditionModel(block_out_channels=(32, 64), layers_per_block=1, sample_size=8, in_channels=4,
                                out_channels=4, down_block_types=("DownBlock2D", "CrossAttnDownBlock2D"),
                                up_block_types=("CrossAttnUpBlock2D", "UpBlock2D"), cross_attention_dim=32)
    vae = AutoencoderKL(block_out_channels=(32,), in_channels=3, out_channels=3, latent_channels=4,
                        down_block_types=("DownEncoderBlock2D",), up_block_types=("UpDecoderBlock2D",))
    pipe = StableDiffusionPipeline(vae=vae, text_encoder=None, tokenizer=None, unet=unet, scheduler=PNDMScheduler(),
                                   safety_checker=None, feature_extractor=None, requires_safety_checker=False)
    pipe.save_pretrained(str(folder / "weights"))
    (folder / "model.json").write_text(json.dumps({
        "layout": "repo", "weights_dir": "weights", "variant": None, "name": folder.name, "arch": "sd15",
        "family": "sd1", "label": "Stable Diffusion 1.5", "denoiser": "unet", "components": {"unet": 0.01, "vae": 0.01},
        "img2img": True, "defaults": {"num_steps": 25}}))
    return unet


def _tiny_lora(folder, unet):
    """A LoRA on the UNet's attention with non-zero factors, written as the trainer writes LoRAs."""
    from diffusers import StableDiffusionPipeline
    from peft import LoraConfig
    from peft.utils import get_peft_model_state_dict
    unet = unet.__class__.from_config(unet.config)
    unet.add_adapter(LoraConfig(r=4, lora_alpha=4, target_modules=["to_q", "to_k", "to_v", "to_out.0"]))
    torch.manual_seed(1)
    with torch.no_grad():
        for n, p in unet.named_parameters():
            if "lora_" in n:
                p.normal_(0, 0.2)
    folder.mkdir(parents=True)
    StableDiffusionPipeline.save_lora_weights(str(folder), unet_lora_layers=get_peft_model_state_dict(unet))
    (folder / "lora.json").write_text(json.dumps({"type": "lora", "name": "tiny", "file": "pytorch_lora_weights.safetensors",
                                                  "family": "sd1", "trigger_words": ["tinystyle"]}))


def test_loras_are_baked_into_a_new_model_that_needs_no_lora(tmp_path, monkeypatch):
    models = tmp_path / "models"
    base = models / "Tiny"
    base.mkdir(parents=True)
    unet = _tiny_model(base)
    _tiny_lora(tmp_path / "loras" / "tiny", unet)
    # the tiny model's sizes are not a real SD 1.5: the inspection of the new folder is taken as it is
    monkeypatch.setattr(importer, "inspect", lambda source, ref, **k: {
        "arch": "sd15", "denoiser": "unet", "components": {"unet": 0.01, "vae": 0.01}, "layout": "folder"})
    monkeypatch.setattr(importer, "make_plan", lambda info, quant="auto", ram_gb=None: {"fits": True, "min_ram_gb": 1, "quant": {}})
    done = []
    monkeypatch.setattr(importer, "emit", lambda tag, payload: done.append((tag, payload)))
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps({"model": str(base), "name": "Tiny baked",
                                "loras": [{"path": str(tmp_path / "loras" / "tiny"), "scale": 0.8}]}))
    m = merge.merge(str(spec), str(models))

    target = models / "Tiny_baked"
    assert done[-1][0] == "__import_done__" and done[-1][1]["model_path"] == str(target)
    assert m["layout"] == "repo" and m["source"]["type"] == "merge" and m["source"]["loras"][0]["scale"] == 0.8
    assert m["trigger_words"] == ["tinystyle"]
    assert m["imported_on"] == importer.imported_on()  # made on this Mac
    assert json.loads((target / "model.json").read_text())["name"] == "Tiny_baked"
    assert not list(models.glob(".baking_*"))  # built in a hidden folder, renamed at the end

    # the baked UNet gives what the base gives with the LoRA at 0.8
    from diffusers import StableDiffusionPipeline, UNet2DConditionModel
    ref = StableDiffusionPipeline.from_pretrained(str(base / "weights"), text_encoder=None, tokenizer=None, dtype=torch.float16)
    ref.load_lora_weights(str(tmp_path / "loras" / "tiny"), adapter_name="t")
    ref.set_adapters(["t"], adapter_weights=[0.8])
    baked = UNet2DConditionModel.from_pretrained(str(target / "weights"), subfolder="unet", dtype=torch.float16)
    plain = UNet2DConditionModel.from_pretrained(str(base / "weights"), subfolder="unet", dtype=torch.float16)
    torch.manual_seed(2)
    x, t, c = torch.randn(1, 4, 8, 8), torch.tensor([10]), torch.randn(1, 4, 32)
    with torch.no_grad():
        want = ref.unet.float()(x, t, c).sample
        got = baked.float()(x, t, c).sample
        before = plain.float()(x, t, c).sample
    assert (got - want).abs().max() < 0.05 * want.abs().max()
    assert (before - want).abs().max() > 5 * (got - want).abs().max()  # the LoRA changed something, and it is in
    # no LoRA adapter left in the new model's files
    from safetensors import safe_open
    with safe_open(str(target / "weights" / "unet" / "diffusion_pytorch_model.safetensors"), "pt") as f:
        assert not any("lora" in k for k in f.keys())


def test_macos_companion_files_on_exfat_drives_are_no_weights(tmp_path):
    """On exFAT / FAT drives macOS writes "._name" next to every file; they are no safetensors."""
    from safetensors.torch import save_file
    comp = tmp_path / "unet"
    comp.mkdir()
    save_file({"w": torch.zeros(2, 3)}, str(comp / "diffusion_pytorch_model.safetensors"))
    (comp / "._diffusion_pytorch_model.safetensors").write_bytes(b"\x00\x05\x16\x07" + b"\x00" * 60)
    assert importer._params_from_folder(str(tmp_path), ["unet"]) == {"unet": 6 / 1e9}


def test_compressed_or_comfyui_models_are_refused_with_the_reason(tmp_path):
    gguf = {"arch": "flux1_dev", "layout": "single_denoiser", "file": "model.gguf", "name": "flux1-dev-Q4"}
    assert "stored compressed" in merge.mergeable(gguf, str(tmp_path))
    comfy = {"arch": "anima", "layout": "comfy_files", "name": "Anima"}
    assert "ComfyUI" in merge.mergeable(comfy, str(tmp_path))
    assert merge.mergeable({"arch": "sdxl", "layout": "single_full", "file": "model.safetensors"}, str(tmp_path)) is None
    with pytest.raises(ValueError, match="at least one LoRA"):
        base = tmp_path / "m"
        base.mkdir()
        (base / "model.json").write_text(json.dumps({"arch": "sd15", "layout": "repo", "weights_dir": "weights", "name": "m"}))
        spec = tmp_path / "s.json"
        spec.write_text(json.dumps({"model": str(base), "loras": []}))
        merge.merge(str(spec), str(tmp_path / "models"))
    assert os.path.isdir(tmp_path) and not (tmp_path / "models" / "m").exists()


def test_the_memory_needed_counts_two_bytes_per_parameter():
    m = {"components": {"transformer": 12.0, "text_encoder": 0.1, "text_encoder_2": 4.7, "vae": 0.1}}
    assert abs(merge._need_gb(m, "", False) - 24.2) < 1e-6
    assert abs(merge._need_gb(m, "", True) - 33.8) < 1e-6


def test_linked_text_encoders_of_an_fp16_base_get_the_plain_names(tmp_path):
    src, dst = tmp_path / "te", tmp_path / "out"
    src.mkdir()
    (src / "config.json").write_text("{}")
    (src / "model.fp16.safetensors").write_bytes(b"w")
    (src / "big.fp16-00001-of-00002.safetensors").write_bytes(b"a")
    (src / "big.safetensors.index.fp16.json").write_text(json.dumps({"weight_map": {"x": "big.fp16-00001-of-00002.safetensors"}}))
    (src / "both.fp16.bin").write_bytes(b"h")
    (src / "both.bin").write_bytes(b"f")
    merge._link_or_copy(str(src), str(dst), "fp16")
    names = sorted(p.name for p in dst.iterdir())
    assert names == ["big-00001-of-00002.safetensors", "big.safetensors.index.json", "both.bin", "config.json",
                     "model.safetensors"]
    assert json.loads((dst / "big.safetensors.index.json").read_text())["weight_map"]["x"] == "big-00001-of-00002.safetensors"
    assert (dst / "both.bin").read_bytes() == b"f"
