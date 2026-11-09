# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""The denoiser's GGUF copy instead of Diffusers' Quanto backend (gguf_cache.py, MEASUREMENTS 7bk)."""
import json
import os
import sys
import types

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine  # noqa: E402
import gguf_cache  # noqa: E402
import quant_cache  # noqa: E402
import quantize_once  # noqa: E402


def _shards(folder):
    import torch
    from safetensors.torch import save_file
    os.makedirs(folder, exist_ok=True)
    torch.manual_seed(0)
    a = {"blocks.0.attn.to_q.weight": torch.randn(64, 64, dtype=torch.bfloat16), "blocks.0.norm.weight": torch.ones(64)}
    b = {"blocks.1.ff.weight": torch.randn(128, 64, dtype=torch.bfloat16)}
    save_file(a, os.path.join(folder, "diffusion_pytorch_model-00001-of-00002.safetensors"))
    save_file(b, os.path.join(folder, "diffusion_pytorch_model-00002-of-00002.safetensors"))
    index = {"weight_map": {**{k: "diffusion_pytorch_model-00001-of-00002.safetensors" for k in a},
                            **{k: "diffusion_pytorch_model-00002-of-00002.safetensors" for k in b}}}
    with open(os.path.join(folder, "diffusion_pytorch_model.safetensors.index.json"), "w") as f:
        json.dump(index, f)
    return {**a, **b}


def test_the_shards_of_a_denoiser_become_one_gguf_with_its_names_and_values(tmp_path):
    pytest.importorskip("gguf")
    from gguf import GGUFReader, quants
    src = str(tmp_path / "weights" / "transformer")
    tensors = _shards(src)
    model_dir = str(tmp_path)
    old = quant_cache.cache_dir(model_dir, "transformer", "q8")
    os.makedirs(old)  # the Quanto copy of VulKara before
    p = gguf_cache.write(model_dir, src, "transformer", "q8")
    assert p == gguf_cache.path(model_dir, "transformer", "q8") and not os.path.exists(old)
    read = {t.name: t for t in GGUFReader(p).tensors}
    assert set(read) == set(tensors)
    assert read["blocks.0.norm.weight"].tensor_type.name == "F32"  # 1-D stays whole
    q = read["blocks.1.ff.weight"]
    assert q.tensor_type.name == "Q8_0"
    back = quants.dequantize(q.data, q.tensor_type).reshape(128, 64)
    want = tensors["blocks.1.ff.weight"].float().numpy()
    assert np.abs(back - want).max() < 0.05
    assert gguf_cache.ready(model_dir, src, "transformer", "q8") == p


def test_a_copy_of_other_source_files_is_written_again(tmp_path):
    pytest.importorskip("gguf")
    src = str(tmp_path / "weights" / "transformer")
    _shards(src)
    gguf_cache.write(str(tmp_path), src, "transformer", "q4")
    shard = os.path.join(src, "diffusion_pytorch_model-00002-of-00002.safetensors")
    os.utime(shard, (1, 1))  # a re-import changes the files
    assert gguf_cache.ready(str(tmp_path), src, "transformer", "q4") is None
    assert not os.path.exists(gguf_cache.path(str(tmp_path), "transformer", "q4"))


def test_the_weights_of_a_variant_or_a_single_file_are_found(tmp_path):
    d = tmp_path / "transformer"
    d.mkdir()
    (d / "diffusion_pytorch_model.fp16.safetensors").write_bytes(b"x")
    (d / "diffusion_pytorch_model.safetensors").write_bytes(b"x")
    assert gguf_cache.sources(str(d), "fp16") == [str(d / "diffusion_pytorch_model.fp16.safetensors")]
    assert gguf_cache.sources(str(d)) == [str(d / "diffusion_pytorch_model.safetensors")]
    assert gguf_cache.sources(str(d / "diffusion_pytorch_model.safetensors")) == [str(d / "diffusion_pytorch_model.safetensors")]
    with pytest.raises(FileNotFoundError):
        gguf_cache.sources(str(d), "bf16")


def test_the_denoiser_is_written_once_in_its_own_process_and_loaded_as_gguf(monkeypatch, tmp_path):
    import diffusers
    jobs, loaded = [], {}
    readies = iter([None, "/m/qcache/transformer-q8.gguf"])
    monkeypatch.setattr(gguf_cache, "ready", lambda *a: next(readies))
    monkeypatch.setattr(quantize_once, "run", lambda job, stop: jobs.append(job) or True)
    monkeypatch.setattr(gguf_cache, "short_of_room", lambda *a: None)
    monkeypatch.setattr(engine.protocol, "status", lambda s: None)
    monkeypatch.setattr(engine, "_dequantize_gguf_outside_linear", lambda model, dtype: None)
    from diffusers.models import model_loading_utils as mlu
    # the GGUF read as views of the mapped file while it loads (diffusers' own reader copies every tensor)
    cls = types.SimpleNamespace(from_single_file=lambda f, **k: loaded.update(
        file=f, reader=mlu.load_gguf_checkpoint.__name__, **k) or "model")
    model = types.SimpleNamespace(model_dir="/m", stop=None, dtype="bf16", _component_class=lambda folder, comp: cls)
    src = str(tmp_path)  # a folder: the component of a repo
    out = engine.LoadedModel._quantized_denoiser(model, src, "/m/weights", "transformer", "q8", "fp16")
    assert out == "model" and jobs[0]["kind"] == "gguf" and jobs[0]["variant"] == "fp16" and jobs[0]["comp"] == "transformer"
    assert loaded["file"] == "/m/qcache/transformer-q8.gguf" and loaded["subfolder"] == "transformer"
    assert loaded["reader"] == "mapped" and mlu.load_gguf_checkpoint.__name__ == "load_gguf_checkpoint"
    assert isinstance(loaded["quantization_config"], diffusers.GGUFQuantizationConfig)
    # not written (no room, broken file): said, not loaded in 16 bit behind the plan's back
    monkeypatch.setattr(gguf_cache, "ready", lambda *a: None)
    monkeypatch.setattr(quantize_once, "run", lambda job, stop: False)
    with pytest.raises(RuntimeError, match="8 bit copy of transformer"):
        engine.LoadedModel._quantized_denoiser(model, src, "/m/weights", "transformer", "q8")


def test_quanto_configs_are_only_made_for_text_encoders():
    pytest.importorskip("optimum.quanto")
    cfg = engine._quanto_configs({"text_encoder": "q8", "text_encoder_2": "q4", "vae": "none"})
    assert set(cfg) == {"text_encoder", "text_encoder_2"}
    assert all(type(c).__module__.startswith("transformers") for c in cfg.values())


def test_a_controlnet_is_quantized_by_optimum_quanto_itself_and_restored_from_the_cache(tmp_path):
    pytest.importorskip("optimum.quanto")
    import torch
    import diffusers
    from optimum.quanto import QModuleMixin
    tiny = diffusers.UNet2DConditionModel(block_out_channels=(32, 64), layers_per_block=1, sample_size=8,
                                          cross_attention_dim=16, down_block_types=("DownBlock2D", "CrossAttnDownBlock2D"),
                                          up_block_types=("CrossAttnUpBlock2D", "UpBlock2D"))
    folder = str(tmp_path / "cn")
    tiny.save_pretrained(folder)
    quantize_once.main({"kind": "controlnet", "folder": folder, "cls": "UNet2DConditionModel", "model_dir": folder,
                        "level": "q8", "dtype": "float32"})

    def make_empty():
        with engine._meta_weights():
            return diffusers.UNet2DConditionModel.from_config(diffusers.UNet2DConditionModel.load_config(folder))
    restored = quant_cache.load(folder, folder, None, "q8", torch.float32, make_empty)
    kinds = {type(m) for m in restored.modules() if isinstance(m, (torch.nn.Linear, torch.nn.Conv2d))}
    assert any(issubclass(k, QModuleMixin) for k in kinds)
    convs = [m for m in restored.modules() if isinstance(m, torch.nn.Conv2d)]
    assert convs and not any(isinstance(m, QModuleMixin) for m in convs)  # the linear layers only, as before


def test_a_disk_without_room_for_the_copy_says_how_much_is_missing(monkeypatch, tmp_path):
    import collections
    import shutil
    d = tmp_path / "transformer"
    d.mkdir()
    (d / "diffusion_pytorch_model.safetensors").write_bytes(b"x" * 2 * 1024 * 1024)
    usage = collections.namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda p: usage(0, 0, 3 * 1024 ** 3))
    msg = gguf_cache.short_of_room(str(tmp_path), str(d), "transformer", "q8")
    assert msg.startswith("The 8 bit copy of transformer needs") and "3.0 GB are free" in msg
    monkeypatch.setattr(shutil, "disk_usage", lambda p: usage(0, 0, 500 * 1024 ** 3))
    assert gguf_cache.short_of_room(str(tmp_path), str(d), "transformer", "q8") is None
    # the old Quanto copies of either bit size go once the GGUF copy is written
    for old in ("q8", "q4"):
        os.makedirs(quant_cache.cache_dir(str(tmp_path), "transformer", old))
    import convert_gguf
    monkeypatch.setattr(convert_gguf, "convert", lambda files, out, kind, progress=None: open(out, "wb").close())
    gguf_cache.write(str(tmp_path), str(d), "transformer", "q8")
    assert not any(os.path.exists(quant_cache.cache_dir(str(tmp_path), "transformer", old)) for old in ("q8", "q4"))


def test_unpacking_reads_the_gguf_file_mapped_not_copied(tmp_path, monkeypatch):
    # Diffusers copies every tensor of a GGUF file into memory; the unpacking for SSD streaming reads them mapped
    # (the same values, MEASUREMENTS 7bp)
    pytest.importorskip("gguf")
    import gguf
    import torch
    from diffusers.models import model_loading_utils as mlu
    import streaming
    src = str(tmp_path / "weights" / "transformer")
    _shards(src)
    p = gguf_cache.write(str(tmp_path), src, "transformer", "q8")
    copied = mlu.load_gguf_checkpoint(p)
    readers = []
    reader = gguf.GGUFReader
    monkeypatch.setattr(gguf, "GGUFReader", lambda path, mode="r": readers.append(reader(path, mode)) or readers[-1])
    original = mlu.load_gguf_checkpoint
    with streaming._gguf_mapped():
        assert mlu.load_gguf_checkpoint is not original
        mapped = mlu.load_gguf_checkpoint(p)
    assert mlu.load_gguf_checkpoint is original
    assert set(mapped) == set(copied)
    for k, v in copied.items():
        assert torch.equal(mapped[k].as_subclass(torch.Tensor), v.as_subclass(torch.Tensor))
        assert getattr(mapped[k], "quant_type", None) == getattr(v, "quant_type", None)
    file = readers[0].data  # the mapped file: every tensor points into its pages
    assert file.mode == "c"  # copy on write: a tensor written in place gets its own page instead of a crash
    lo, hi = file.ctypes.data, file.ctypes.data + file.nbytes
    assert all(lo <= t.as_subclass(torch.Tensor).data_ptr() < hi for t in mapped.values())
