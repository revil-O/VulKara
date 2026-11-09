# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
import os

import registry


def test_krea2_native_checkpoint():
    shapes = {"blocks.0.mod.lin": [36864], "blocks.0.attn.wq.weight": [6144, 6144],
              "txtfusion.projector.weight": [1, 12], "first.weight": [6144, 64], "last.linear.weight": [64, 6144]}
    arch, layout, overrides, _ = registry.detect_from_single_file(shapes, "krea2TurboFP8_krea2TURBO.safetensors")
    assert (arch, layout) == ("krea2", "single_denoiser")
    assert overrides == {}  # not the generic "turbo" defaults (4 steps, no guidance)
    assert registry.ARCHS["krea2"]["runtime"] == "mlx"
    assert registry.detect_from_model_index({"_class_name": "Krea2Pipeline"}, {}, "krea/Krea-2-Turbo")[0] == "krea2"


def test_krea2_mlx_plan_quantizes_the_text_encoder_on_24gb():
    import importlib.util
    # load the MLX engine module by path (the diffusers engine has a main.py as well)
    spec = importlib.util.spec_from_file_location("mlx_main", os.path.join(os.path.dirname(__file__), "..", "..",
                                                                         "mlx", "main.py"))
    mlx_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mlx_main)
    m = {"arch": "krea2", "denoiser": "transformer", "components": registry.ARCHS["krea2"]["fallback_params"]}
    bits, plan, quantize_te = mlx_main.choose_quant(m, ram_gb=24)
    assert bits == 4 and plan["fits"] and quantize_te      # 16-bit text encoder does not fit next to it
    bits, plan, quantize_te = mlx_main.choose_quant(m, ram_gb=64)
    assert plan["fits"] and not quantize_te                # big Macs keep mflux's 16-bit text encoder
    # 16 GB (Mac mini M4): only with the text encoder freed after encoding the prompt
    m = {"arch": "krea2", "denoiser": "transformer", "components": {"text_encoder": 4.44, "transformer": 12.82, "vae": 0.13}}
    bits, plan, quantize_te = mlx_main.choose_quant(m, ram_gb=16)
    assert bits == 4 and plan["fits"] and plan["staged_text_encoder"]
    assert not mlx_main.choose_quant(m, ram_gb=24)[1]["staged_text_encoder"]


def _lora(tmp_path, names):
    from safetensors.numpy import save_file
    import numpy as np
    path = str(tmp_path / "lora.safetensors")
    save_file({n: np.zeros((4, 4), np.float16) for n in names}, path)
    return path


def test_krea2_lora_detection(tmp_path):
    native = _lora(tmp_path, ["diffusion_model.blocks.0.attn.wq.lora_A.weight", "diffusion_model.blocks.0.attn.wq.lora_B.weight"])
    assert registry.inspect_lora(native)["family"] == "krea2"
    diffusers = _lora(tmp_path, ["transformer.transformer_blocks.0.attn.to_gate.lora_A.weight",
                                 "transformer.transformer_blocks.0.attn.to_gate.lora_B.weight"])
    assert registry.inspect_lora(diffusers)["family"] == "krea2"


def test_lora_family_from_the_source_when_the_file_does_not_tell(tmp_path):
    unclear = _lora(tmp_path, ["some_net.layer.lora_A.weight", "some_net.layer.lora_B.weight"])
    assert registry.inspect_lora(unclear, family_hint="krea2")["family"] == "krea2"
    import pytest
    with pytest.raises(registry.UnsupportedModel):
        registry.inspect_lora(unclear)


def test_an_anima_lora_in_kohya_names_is_not_taken_for_sdxl(tmp_path):
    """kohya names an Anima (Cosmos-Predict2) LoRA lora_unet_ like a UNet one; its blocks give it away."""
    names = ["lora_unet_blocks_0_adaln_modulation_cross_attn_1.lora_down.weight",
             "lora_unet_blocks_0_adaln_modulation_cross_attn_1.lora_up.weight",
             "lora_unet_blocks_0_self_attn_q_proj.lora_down.weight", "lora_unet_blocks_0_self_attn_q_proj.lora_up.weight"]
    assert registry.inspect_lora(_lora(tmp_path, names))["family"] == "anima"



def test_krea2_decodes_in_smaller_tiles_on_small_macs(monkeypatch):
    # its Qwen VAE in 512 px tiles added 6.6 GB on a 16 GB Mac mini, in 256 px tiles 3.6 GB (MEASUREMENTS 7bd)
    import importlib.util
    import os
    import sys
    import types
    seen = []

    class TilingConfig:
        def __init__(self, **k):
            seen.append(k)

        @staticmethod
        def may_tile_implicitly(model):
            return True

    for name in ("mflux", "mflux.models", "mflux.models.common", "mflux.models.common.vae"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "mflux.models.common.vae.tiling_config", types.SimpleNamespace(TilingConfig=TilingConfig))
    spec = importlib.util.spec_from_file_location("mlx_main", os.path.join(os.path.dirname(__file__), "..", "..", "mlx", "main.py"))
    mlx_main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mlx_main)
    mlx_main.low_ram(types.SimpleNamespace(tiling_config=None), "krea2")
    mlx_main.low_ram(types.SimpleNamespace(tiling_config=None), "z_image")
    assert seen == [{"vae_decode_tile_size": 256}, {}]
