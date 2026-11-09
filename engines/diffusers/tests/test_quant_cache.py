# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Round trip of the quantized-weights cache with tiny, locally created text encoders."""
import os

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
pytest.importorskip("optimum.quanto")

import quant_cache  # noqa: E402

MODELS = {
    # tied embeddings, "wo" kept in float32 by transformers
    "t5": lambda: transformers.T5EncoderModel(transformers.T5Config(
        vocab_size=128, d_model=64, d_kv=16, d_ff=128, num_layers=2, num_heads=4)),
    # rotary tables are non-persistent buffers, missing from any state dict
    "qwen3": lambda: transformers.Qwen3Model(transformers.Qwen3Config(
        vocab_size=128, hidden_size=64, intermediate_size=128, num_hidden_layers=2, num_attention_heads=4,
        num_key_value_heads=2, head_dim=16)),
}


@pytest.mark.parametrize("level", ["q8", "q4"])
@pytest.mark.parametrize("kind", sorted(MODELS))
def test_round_trip(tmp_path, kind, level):
    torch.manual_seed(0)
    folder = str(tmp_path / "src")
    comp = "text_encoder"
    MODELS[kind]().save_pretrained(os.path.join(folder, comp))
    cls = type(MODELS[kind]())
    dtype = torch.bfloat16
    quantized = cls.from_pretrained(folder, subfolder=comp, dtype=dtype,
                                    quantization_config=transformers.QuantoConfig(weights={"q8": "int8", "q4": "int4"}[level]))
    ids = torch.randint(0, 128, (1, 12))
    with torch.no_grad():
        ref = quantized(ids)[0].float()

    model_dir = str(tmp_path / "model")
    os.makedirs(model_dir)
    quant_cache.save(model_dir, folder, comp, level, dtype, quantized)
    assert os.path.isfile(os.path.join(quant_cache.cache_dir(model_dir, comp, level), "model.safetensors"))

    def make_empty():
        with torch.device("meta"):
            return cls._from_config(cls.config_class.from_pretrained(folder, subfolder=comp), dtype=dtype)

    restored = quant_cache.load(model_dir, folder, comp, level, dtype, make_empty)
    assert restored is not None
    with torch.no_grad():
        got = restored(ids)[0].float()
    assert torch.equal(ref, got)
    # int4 unpacks without quanto's C++ kernel (it is compiled on first use and fails in paths with a space)
    from optimum.quanto.library.extensions import get_extension
    assert get_extension("quanto_cpp")._lib is None
    if kind == "t5":
        assert restored.shared.weight is restored.encoder.embed_tokens.weight


def test_outdated_cache_is_dropped(tmp_path):
    folder = str(tmp_path / "src")
    comp = "text_encoder"
    MODELS["t5"]().save_pretrained(os.path.join(folder, comp))
    model = transformers.T5EncoderModel.from_pretrained(folder, subfolder=comp, dtype=torch.bfloat16,
                                                        quantization_config=transformers.QuantoConfig(weights="int8"))
    model_dir = str(tmp_path / "model")
    os.makedirs(model_dir)
    quant_cache.save(model_dir, folder, comp, "q8", torch.bfloat16, model)
    # the source changes (re-import): the cache must not be used
    weights = os.path.join(folder, comp, "model.safetensors")
    os.utime(weights, (1, 1))
    assert quant_cache.load(model_dir, folder, comp, "q8", torch.bfloat16, lambda: None) is None
    assert not os.path.exists(quant_cache.cache_dir(model_dir, comp, "q8"))


def test_a_stop_while_it_loads_keeps_the_cache(tmp_path, monkeypatch):
    folder = str(tmp_path / "src")
    comp = "text_encoder"
    MODELS["t5"]().save_pretrained(os.path.join(folder, comp))
    model = transformers.T5EncoderModel.from_pretrained(folder, subfolder=comp, dtype=torch.bfloat16,
                                                        quantization_config=transformers.QuantoConfig(weights="int8"))
    model_dir = str(tmp_path / "model")
    os.makedirs(model_dir)
    quant_cache.save(model_dir, folder, comp, "q8", torch.bfloat16, model)

    class StopRequested(Exception):  # as engine.StopRequested, raised into the loading thread by a Stop
        pass

    def stopped(*a):
        raise StopRequested()
    monkeypatch.setattr(quant_cache, "_restore", stopped)
    with pytest.raises(StopRequested):
        quant_cache.load(model_dir, folder, comp, "q8", torch.bfloat16, lambda: None)
    assert os.path.isdir(quant_cache.cache_dir(model_dir, comp, "q8"))  # kept for the next job


@pytest.mark.skipif(not torch.backends.mps.is_available(), reason="the plain packing is kept for MPS")
def test_int4_on_the_cpu_keeps_the_plain_packing():
    """TinyGemm's CPU layout is repacked layer by layer on the way to the GPU (20 s each, MEASUREMENTS 7t)."""
    import quanto_mps
    from optimum.quanto import freeze, qint4, quantize
    from optimum.quanto.tensor.weights.qbits import WeightQBitsTensor
    quanto_mps.patch()
    lin = torch.nn.Sequential(torch.nn.Linear(256, 128)).to(torch.bfloat16)
    quantize(lin, weights=qint4)
    freeze(lin)
    assert type(lin[0].weight) is WeightQBitsTensor


def test_t5s_float32_layers_are_quantized_too(tmp_path):
    # transformers' quanto quantizer left T5's wo layers 16 bit: 5.2 GB instead of 3.1 for FLUX.1's "4 bit" T5 (7bf)
    import json
    from optimum.quanto import QModuleMixin, qint8
    import quanto_mps
    quanto_mps.patch()  # int4 without quanto's compiled kernels, as the engine quantizes
    torch.manual_seed(0)
    folder, comp, dtype = str(tmp_path / "src"), "text_encoder_2", torch.bfloat16
    MODELS["t5"]().save_pretrained(os.path.join(folder, comp))
    with open(os.path.join(folder, "model_index.json"), "w") as f:
        json.dump({comp: ["transformers", "T5EncoderModel"]}, f)
    cls = transformers.T5EncoderModel
    config = transformers.QuantoConfig(weights="int4")
    quantized = cls.from_pretrained(folder, subfolder=comp, dtype=dtype, quantization_config=config)
    wo = lambda m: m.encoder.block[0].layer[1].DenseReluDense.wo  # noqa: E731
    assert not isinstance(wo(quantized), QModuleMixin)
    quant_cache.quantize_kept_fp32(quantized, dtype)
    assert isinstance(wo(quantized), QModuleMixin) and wo(quantized).weight_qtype == qint8  # 4 bit: one prompt went off
    ids = torch.randint(0, 128, (1, 12))
    with torch.no_grad():
        ref = quantized(ids)[0].float()

    model_dir = str(tmp_path / "model")
    os.makedirs(model_dir)
    quant_cache.save(model_dir, folder, comp, "q4", dtype, quantized)
    with open(os.path.join(quant_cache.cache_dir(model_dir, comp, "q4"), "cache.json")) as f:
        assert json.load(f)["key"]["kept_fp32"] == "q8"  # caches made before are made again

    def make_empty():
        with torch.device("meta"):
            return cls._from_config(cls.config_class.from_pretrained(folder, subfolder=comp), dtype=dtype)

    restored = quant_cache.load(model_dir, folder, comp, "q4", dtype, make_empty)
    assert isinstance(wo(restored), QModuleMixin)
    with torch.no_grad():
        assert torch.equal(ref, restored(ids)[0].float())
    # float16 needs them in float32 (overflow): left as they are
    other = cls.from_pretrained(folder, subfolder=comp, dtype=torch.float16, quantization_config=config)
    assert not isinstance(wo(quant_cache.quantize_kept_fp32(other, torch.float16)), QModuleMixin)
