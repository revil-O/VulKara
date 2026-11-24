# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
import json
import os
import sys

import pytest

import trainutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "mlx"))
import train as mlx_train  # noqa: E402


def test_captions_start_with_the_trigger_word():
    assert trainutil.caption_for({"caption": "on a sofa"}, "zqx_dog") == "zqx_dog, on a sofa"
    assert trainutil.caption_for({"caption": "a ZQX_DOG on a sofa"}, "zqx_dog") == "a ZQX_DOG on a sofa"
    assert trainutil.caption_for({"caption": ""}, "zqx_dog") == "zqx_dog"
    assert trainutil.caption_for({}, "") == "a photo"


def test_prepare_images_writes_pictures_and_captions(tmp_path):
    PIL = pytest.importorskip("PIL.Image")
    src = tmp_path / "big.jpg"
    PIL.new("RGB", (3000, 2000), "red").save(src)
    job = {"trigger": "zqx", "images": [{"path": str(src), "caption": "red"}, {"path": str(tmp_path / "gone.png")}]}
    n = trainutil.prepare_images(job, tmp_path / "data", 512)
    assert n == 1
    assert PIL.open(tmp_path / "data" / "img000.png").size == (768, 512)  # at most 1.5 x the training size
    assert (tmp_path / "data" / "img000.txt").read_text() == "zqx, red"
    with pytest.raises(ValueError):
        trainutil.prepare_images({"images": []}, tmp_path / "empty", 512)


def test_result_is_stored_like_an_imported_lora(tmp_path):
    header = json.dumps({"a.lora_A.weight": {"dtype": "F32", "shape": [4, 8], "data_offsets": [0, 128]}}).encode()
    adapter = tmp_path / "adapter.safetensors"
    adapter.write_bytes(len(header).to_bytes(8, "little") + header + b"\0" * 128)
    job = {"name": "my dog", "trigger": "zqx_dog", "images": [], "loras_dir": str(tmp_path / "loras")}
    first = trainutil.write_lora_folder(job, adapter, family="sdxl", base="x", training={"steps": 3})
    second = trainutil.write_lora_folder(job, adapter, family="sdxl", base="x", training={"steps": 3})
    assert os.path.basename(first) == "my_dog" and os.path.basename(second) == "my_dog_2"
    m = json.load(open(os.path.join(first, "lora.json")))
    assert m["family"] == "sdxl" and m["trigger_words"] == ["zqx_dog"] and m["source"]["type"] == "trained"
    assert m["training"]["steps"] == 3 and os.path.isfile(os.path.join(first, "lora.safetensors"))


def test_mlx_training_targets_and_model_names(tmp_path):
    (tmp_path / "transformer").mkdir()
    (tmp_path / "transformer" / "config.json").write_text(json.dumps({"num_layers": 8, "num_single_layers": 24}))
    klein = {"arch": "flux2_klein", "components": {"transformer": 9.1, "text_encoder": 8.2}}
    targets = mlx_train.lora_targets(klein, str(tmp_path), 16)
    assert {"module_path": "transformer_blocks.{block}.attn.to_q", "blocks": {"start": 0, "end": 8}, "rank": 16} in targets
    assert any(t["module_path"].startswith("single_transformer_blocks") and t["blocks"]["end"] == 24 for t in targets)
    assert mlx_train.model_name(klein) == "flux2-klein-9b"
    assert mlx_train.model_name({"arch": "flux2_klein", "components": {"transformer": 4.0}}) == "flux2-klein-4b"
    krea = {"arch": "krea2"}
    assert mlx_train.model_name(krea) == "krea-2"
    assert all(t["blocks"]["end"] == 28 for t in mlx_train.lora_targets(krea, str(tmp_path), 8))


def test_training_quantizes_more_on_small_macs():
    klein9 = {"arch": "flux2_klein", "denoiser": "transformer",
              "components": {"transformer": 9.1, "text_encoder": 8.2, "vae": 0.08}}
    assert mlx_train.choose_bits(klein9, 24) == 4
    assert mlx_train.choose_bits(klein9, 64) == 8


def test_training_bounds_mlx_buffer_cache_on_small_macs():
    assert mlx_train.cache_limit(16) == 2.0 and mlx_train.cache_limit(24) == 2.0
    assert mlx_train.cache_limit(64) is None


def test_z_image_trains_turbo_or_base_with_its_targets_and_fitting_bits(tmp_path):
    (tmp_path / "transformer").mkdir()
    (tmp_path / "transformer" / "config.json").write_text(json.dumps({"n_layers": 30}))
    turbo = {"arch": "z_image", "denoiser": "transformer", "defaults": {"guidance_scale": 0.0},
             "components": {"text_encoder": 4.02, "transformer": 6.15, "vae": 0.08}}
    assert mlx_train.model_name(turbo) == "z-image-turbo"
    assert mlx_train.model_name(dict(turbo, defaults={"guidance_scale": 4.0})) == "z-image"
    targets = mlx_train.lora_targets(turbo, str(tmp_path), 16)
    assert len(targets) == 7 and all(t["blocks"] == {"start": 0, "end": 30} for t in targets)
    assert {"module_path": "layers.{block}.attention.to_q", "blocks": {"start": 0, "end": 30}, "rank": 16} in targets
    # measured: 4 bit fits 16 GB (10.2 GB), 8 bit (13.2 GB) only from 24 GB (MEASUREMENTS 7cn)
    assert mlx_train.choose_bits(turbo, 16) == 4
    assert mlx_train.choose_bits(turbo, 24) == 8


def test_the_turbo_adapter_comes_pinned_and_checked(tmp_path, monkeypatch):
    import pinned
    seen = {}
    monkeypatch.setenv("VK_HELPERS_DIR", str(tmp_path))
    monkeypatch.setattr(pinned, "fetch_urls", lambda urls, files, folder, report=None: seen.update(urls=urls, files=files, folder=folder))
    path = mlx_train.turbo_adapter()
    name = "zimage_turbo_training_adapter_v2.safetensors"
    assert path == str(tmp_path / "train_adapters" / name)
    assert seen["urls"][name].startswith("https://huggingface.co/ostris/zimage_turbo_training_adapter/resolve/654cd1bf")
    assert len(seen["files"][name]) == 64


def test_ernie_trains_turbo_or_base_with_its_targets_and_fitting_bits(tmp_path):
    (tmp_path / "transformer").mkdir()
    (tmp_path / "transformer" / "config.json").write_text(json.dumps({"num_layers": 36}))
    turbo = {"arch": "ernie_image", "denoiser": "transformer", "defaults": {"guidance_scale": 1.0},
             "components": {"pe": 0.1, "pe_tokenizer": 0.1, "text_encoder": 3.85, "transformer": 8.03, "vae": 0.08}}
    assert mlx_train.model_name(turbo) == "ernie-image-turbo"
    assert mlx_train.model_name(dict(turbo, defaults={"guidance_scale": 4.0})) == "ernie-image"
    targets = mlx_train.lora_targets(turbo, str(tmp_path), 16)
    assert len(targets) == 8 and {"module_path": "text_proj", "rank": 16} in targets
    assert all(t["blocks"] == {"start": 0, "end": 36} for t in targets[:7])
    # measured: 4 bit fits 16 GB (10.9 GB), 8 bit (14.3 GB) from 24 GB (MEASUREMENTS 7cn)
    assert mlx_train.choose_bits(turbo, 16) == 4
    assert mlx_train.choose_bits(turbo, 24) == 8
    assert mlx_train.FAMILIES["ernie_image"] == "ernie"

