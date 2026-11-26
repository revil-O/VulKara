# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""A model in diffusers' layout written as one original-layout checkpoint (export_single.py): the key maps of the UNet,
the VAE and SDXL's second text encoder, and the refusal of models that can not be exported."""
import json
import os
import sys

import pytest
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import export_single as ex  # noqa: E402


def test_unet_keys_of_sd15_and_sdxl_land_where_the_original_layout_has_them():
    t = torch.zeros(1)
    sd15 = ex.convert_unet({"conv_in.weight": t, "down_blocks.0.resnets.1.norm1.weight": t,
                            "down_blocks.0.attentions.0.proj_in.weight": t, "up_blocks.3.attentions.2.proj_out.weight": t,
                            "mid_block.resnets.1.conv2.weight": t, "time_embedding.linear_1.bias": t}, sdxl=False)
    assert set(sd15) == {"model.diffusion_model.input_blocks.0.0.weight", "model.diffusion_model.input_blocks.2.0.in_layers.0.weight",
                         "model.diffusion_model.input_blocks.1.1.proj_in.weight", "model.diffusion_model.output_blocks.11.1.proj_out.weight",
                         "model.diffusion_model.middle_block.2.out_layers.3.weight", "model.diffusion_model.time_embed.0.bias"}
    sdxl = ex.convert_unet({"down_blocks.1.attentions.0.proj_in.weight": t, "up_blocks.0.attentions.2.proj_out.weight": t,
                            "add_embedding.linear_2.weight": t, "up_blocks.2.resnets.3.conv1.weight": t}, sdxl=True)
    assert set(sdxl) == {"model.diffusion_model.input_blocks.4.1.proj_in.weight", "model.diffusion_model.output_blocks.2.1.proj_out.weight",
                         "model.diffusion_model.label_emb.0.2.weight", "model.diffusion_model.output_blocks.9.0.in_layers.2.weight"}


def test_vae_attention_becomes_a_1x1_conv_and_blocks_are_renumbered():
    out = ex.convert_vae({"decoder.up_blocks.0.resnets.2.conv1.weight": torch.zeros(4, 4, 3, 3),
                          "encoder.mid_block.attentions.0.to_q.weight": torch.zeros(8, 8),
                          "encoder.mid_block.attentions.0.group_norm.weight": torch.zeros(8)})
    assert "first_stage_model.decoder.up.3.block.2.conv1.weight" in out
    assert out["first_stage_model.encoder.mid.attn_1.q.weight"].shape == (8, 8, 1, 1)
    assert "first_stage_model.encoder.mid.attn_1.norm.weight" in out


def test_sdxl_second_text_encoder_joins_q_k_v_and_turns_the_projection():
    sd = {"text_model.encoder.layers.0.self_attn.q_proj.weight": torch.full((2, 2), 1.0),
          "text_model.encoder.layers.0.self_attn.k_proj.weight": torch.full((2, 2), 2.0),
          "text_model.encoder.layers.0.self_attn.v_proj.weight": torch.full((2, 2), 3.0),
          "text_model.encoder.layers.0.self_attn.q_proj.bias": torch.zeros(2),
          "text_model.encoder.layers.0.self_attn.k_proj.bias": torch.zeros(2),
          "text_model.encoder.layers.0.self_attn.v_proj.bias": torch.zeros(2),
          "text_model.encoder.layers.0.mlp.fc1.weight": torch.zeros(3, 2),
          "text_model.final_layer_norm.weight": torch.zeros(2),
          "text_projection.weight": torch.arange(6.0).reshape(3, 2)}
    out = ex.convert_openclip(sd)
    p = "conditioner.embedders.1.model."
    joined = out[p + "transformer.resblocks.0.attn.in_proj_weight"]
    assert joined.shape == (6, 2) and joined[0, 0] == 1 and joined[2, 0] == 2 and joined[4, 0] == 3
    assert p + "transformer.resblocks.0.mlp.c_fc.weight" in out and p + "ln_final.weight" in out
    assert out[p + "text_projection"].shape == (2, 3)


def test_only_sd1_and_sdxl_in_folder_layout_are_exported(tmp_path):
    (tmp_path / "model.json").write_text(json.dumps({"family": "flux1", "layout": "repo", "label": "FLUX.1"}))
    with pytest.raises(ValueError, match="Only Stable Diffusion"):
        ex.export(str(tmp_path), str(tmp_path / "out.safetensors"))


def test_a_folder_model_is_written_as_one_file(tmp_path):
    from safetensors.torch import load_file, save_file
    w = tmp_path / "weights"
    for comp, sd in (("unet", {"conv_in.weight": torch.ones(2, 2)}), ("vae", {"encoder.conv_in.weight": torch.ones(2)}),
                     ("text_encoder", {"text_model.final_layer_norm.weight": torch.ones(2)})):
        (w / comp).mkdir(parents=True)
        save_file(sd, str(w / comp / ("model.safetensors" if comp.startswith("text") else "diffusion_pytorch_model.safetensors")))
    (tmp_path / "model.json").write_text(json.dumps({"family": "sd1", "layout": "repo", "weights_dir": "weights", "label": "SD 1.5"}))
    out = tmp_path / "x.safetensors"
    stages = []
    gb = ex.export(str(tmp_path), str(out), lambda s, p: stages.append(s))
    got = load_file(str(out))
    assert set(got) == {"model.diffusion_model.input_blocks.0.0.weight", "first_stage_model.encoder.conv_in.weight",
                        "cond_stage_model.transformer.text_model.final_layer_norm.weight"}
    assert all(v.dtype == torch.float16 for v in got.values()) and gb > 0 and stages[-1] == "Writing the file"


def test_a_failed_write_leaves_no_part_file(tmp_path, monkeypatch):
    from safetensors.torch import save_file
    w = tmp_path / "weights"
    for comp in ("unet", "vae", "text_encoder"):
        (w / comp).mkdir(parents=True)
        save_file({"text_model.x" if comp.startswith("text") else "x": torch.ones(2)}, str(w / comp / "model.safetensors"))
    (tmp_path / "model.json").write_text(json.dumps({"family": "sd1", "layout": "repo", "weights_dir": "weights"}))
    out = tmp_path / "x.safetensors"

    def full_disk(state, path, metadata=None):
        open(path, "wb").write(b"half")
        raise OSError("No space left on device")
    monkeypatch.setattr("safetensors.torch.save_file", full_disk)
    with pytest.raises(OSError):
        ex.export(str(tmp_path), str(out))
    assert not out.exists() and not (tmp_path / "x.safetensors.part").exists()


def test_text_encoder_keys_get_text_model_in_front_when_transformers_left_it_out():
    t = torch.zeros(1)
    assert set(ex.clip_keys({"embeddings.position_embedding.weight": t, "text_projection.weight": t})) == \
        {"text_model.embeddings.position_embedding.weight", "text_projection.weight"}
    kept = {"text_model.embeddings.position_embedding.weight": t}
    assert ex.clip_keys(kept) is kept


def test_a_stopped_export_leaves_no_part_file(tmp_path, monkeypatch):
    import os
    import signal
    from safetensors.torch import save_file
    w = tmp_path / "weights"
    for comp in ("unet", "vae", "text_encoder"):
        (w / comp).mkdir(parents=True)
        save_file({"text_model.x" if comp.startswith("text") else "x": torch.ones(2)}, str(w / comp / "model.safetensors"))
    (tmp_path / "model.json").write_text(json.dumps({"family": "sd1", "layout": "repo", "weights_dir": "weights"}))
    out = tmp_path / "x.safetensors"

    def stopped_while_writing(state, path, metadata=None):
        open(path, "wb").write(b"half")
        os.kill(os.getpid(), signal.SIGTERM)  # the app's kill() while the file is written
    monkeypatch.setattr("safetensors.torch.save_file", stopped_while_writing)
    old = signal.getsignal(signal.SIGTERM)
    try:
        ex.stop_on_sigterm()
        with pytest.raises(SystemExit):
            ex.export(str(tmp_path), str(out))
    finally:
        signal.signal(signal.SIGTERM, old)
    assert not out.exists() and not (tmp_path / "x.safetensors.part").exists()
