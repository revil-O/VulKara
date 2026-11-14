# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""ObjectClear's own parts (objectclear.py) with tiny random tensors and synthetic maps: no weights, no network."""
import os
import sys

import numpy as np
import pytest
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import objectclear as oc  # noqa: E402

# the published postfuse_module/model.fp16.safetensors: key -> shape
POSTFUSE_KEYS = {
    "mlp1.layernorm.weight": (768,), "mlp1.layernorm.bias": (768,),
    "mlp1.fc1.weight": (2048, 768), "mlp1.fc1.bias": (2048,),
    "mlp1.fc2.weight": (2048, 2048), "mlp1.fc2.bias": (2048,),
    "mlp2.layernorm.weight": (2048,), "mlp2.layernorm.bias": (2048,),
    "mlp2.fc1.weight": (2048, 2048), "mlp2.fc1.bias": (2048,),
    "mlp2.fc2.weight": (2048, 2048), "mlp2.fc2.bias": (2048,),
    "layer_norm.weight": (2048,), "layer_norm.bias": (2048,),
}


def test_working_size_short_side_512_rounded_to_16():
    assert oc.working_size(1024, 768) == (688, 512)
    assert oc.working_size(768, 1024) == (512, 688)
    assert oc.working_size(512, 512) == (512, 512)
    # smaller pictures keep their size, only rounded up
    assert oc.working_size(300, 200) == (304, 208)


def test_working_size_caps_the_longer_side():
    assert oc.working_size(912 * 4, 512 * 4) == (912, 512)  # within 2:1 the short side stays 512
    assert oc.working_size(3000, 1000) == (1024, 352)  # a 3:1 panorama
    assert oc.working_size(1000, 3000) == (352, 1024)


def test_postfuse_keys_match_the_published_weights():
    got = {k: tuple(v.shape) for k, v in oc.Postfuse().state_dict().items()}
    assert got == POSTFUSE_KEYS


def test_postfuse_shapes_and_residual():
    torch.manual_seed(0)
    pf = oc.Postfuse(text_dim=16, image_dim=8).eval()
    out = pf(torch.randn(2, 1, 8))
    assert out.shape == (2, 1, 16)
    # the final LayerNorm (weight 1, bias 0 when new): mean 0 per vector
    assert torch.allclose(out.mean(-1), torch.zeros(2, 1), atol=1e-5)
    # the second block keeps the width and adds its input back; the first changes the width and does not
    with torch.no_grad():
        pf.mlp2.fc2.weight.zero_()
        pf.mlp2.fc2.bias.zero_()
    x = torch.randn(1, 1, 16)
    assert torch.equal(pf.mlp2(x), x)
    assert pf.mlp1(torch.randn(1, 1, 8)).shape == (1, 1, 16)


def test_put_object_replaces_only_its_token():
    pe = torch.randn(1, 77, 16)
    obj = torch.randn(1, 1, 16)
    out = oc.put_object(pe, obj)
    assert torch.equal(out[:, oc.TOKEN], obj[:, 0])
    rest = [i for i in range(77) if i != oc.TOKEN]
    assert torch.equal(out[:, rest], pe[:, rest])
    assert not torch.equal(pe[:, oc.TOKEN], obj[:, 0])  # a copy: the input stays


def test_clip_pixels_keep_only_the_object():
    pixels = torch.rand(1, 3, 64, 96) * 2 - 1
    binary = torch.zeros(1, 1, 64, 96)
    binary[..., 20:40, 30:60] = 1
    x = oc.clip_pixels(pixels, binary)
    assert x.shape == (1, 3, oc.CLIP_SIZE, oc.CLIP_SIZE)
    # far from the object the picture is 0, normalised like everything else
    corner = x[0, :, 0, 0]
    want = -torch.tensor(oc.CLIP_MEAN) / torch.tensor(oc.CLIP_STD)
    assert torch.allclose(corner, want, atol=1e-5)
    assert x[0, :, 112, 112].sub(want).abs().max() > 0.01


def test_attention_map_mean_of_heads_resized_and_stretched():
    heads, h, w = 3, 8, 12
    probs = torch.full((2 * heads, (h // 2) * (w // 2), 1), 0.1)
    # one hot spot in the second (conditional) half, all heads
    probs.view(2, heads, h // 2, w // 2)[1, :, 1, 2] = 0.9
    m = oc.attention_map(probs, heads, h, w)
    assert m.shape == (2, h, w)
    assert float(m[1].min()) == pytest.approx(0) and float(m[1].max()) == pytest.approx(1, abs=1e-6)
    y, x = divmod(int(m[1].argmax()), w)
    assert (y // 2, x // 2) == (1, 2)
    # an even map stays 0 (no division by zero)
    assert float(m[0].abs().max()) == 0


def test_keep_token_processor_matches_sdpa_and_keeps_the_column():
    from diffusers.models.attention_processor import Attention, AttnProcessor2_0
    torch.manual_seed(0)
    attn = Attention(query_dim=8, cross_attention_dim=6, heads=2, dim_head=4).eval()
    hs, enc = torch.randn(2, 10, 8), torch.randn(2, 7, 6)
    with torch.no_grad():
        ref = AttnProcessor2_0()(attn, hs, enc)
        keep = oc._KeepToken(3)
        attn.set_processor(keep)
        out = attn(hs, encoder_hidden_states=enc)
    assert torch.allclose(out, ref, atol=1e-5)
    assert keep.probs.shape == (2 * 2, 10, 1)
    assert "get_attention_scores" not in vars(attn)  # the module's own method is back


def test_colour_fix_of_a_picture_with_itself_is_the_picture():
    rng = np.random.default_rng(0)
    a = rng.integers(0, 256, (64, 48, 3)).astype(np.uint8)
    assert np.abs(oc.colour_fix(a, a).astype(int) - a).max() <= 1


def test_colour_fix_takes_detail_from_one_and_colour_from_the_other():
    rng = np.random.default_rng(1)
    detail = np.clip(rng.normal(100, 30, (64, 64, 3)), 0, 255).astype(np.uint8)
    flat = np.full((64, 64, 3), 160, np.uint8)
    out = oc.colour_fix(detail, flat).astype(float)
    # coarse colour of the second, fine structure of the first
    assert abs(out.mean() - 160) < 2
    assert np.corrcoef(out.ravel(), detail.astype(float).ravel())[0, 1] > 0.9


def fuse_case(size=(160, 192)):
    h, w = size
    yy, xx = np.mgrid[0:h, 0:w]
    original = np.stack([xx * 2 % 256, yy * 2 % 256, (xx + yy) % 256], -1).astype(np.uint8)
    removed = original.copy()
    removed[32:56, 40:80] = (10, 200, 10)  # exactly the marked area
    attention = np.zeros((h // 8, w // 8), np.uint8)
    attention[4:7, 5:10] = 200  # over the changed block
    return original, removed, attention


def test_fuse_inside_the_map_is_the_result_far_outside_the_original():
    original, removed, attention = fuse_case()
    out = oc.fuse(original, removed, attention)
    assert out.shape == original.shape and out.dtype == np.uint8
    assert np.array_equal(out[32:56, 40:80], removed[32:56, 40:80])
    # far from the map the result equals the original there: detail and colour come back as they were
    assert np.abs(out[120:, :20].astype(int) - original[120:, :20]).max() <= 1


def test_fuse_threshold_is_strictly_above_128():
    original, removed, _ = fuse_case()
    at = np.full((20, 24), oc.THRESHOLD, np.uint8)
    out = oc.fuse(original, removed, at)
    # nothing marked: the changed block is not taken over wholesale
    assert not np.array_equal(out[32:56, 40:80], removed[32:56, 40:80])


def test_fuse_takes_the_results_colour_outside_the_map():
    original, removed, attention = fuse_case()
    shifted = np.clip(removed.astype(int) + 12, 0, 255).astype(np.uint8)
    out = oc.fuse(original, shifted, attention)
    far = (slice(120, None), slice(0, 20))
    assert abs(out[far].astype(float).mean() - shifted[far].astype(float).mean()) < 2


def test_fuse_any_size():
    original, removed, attention = fuse_case((90, 130))
    assert oc.fuse(original, removed, attention).shape == (90, 130, 3)


def test_vision_half_loads_from_a_full_clip_checkpoint(tmp_path):
    from transformers import CLIPConfig, CLIPModel, CLIPVisionModelWithProjection
    # as in the published config, the vision part names its projection width itself
    cfg = CLIPConfig(text_config=dict(hidden_size=16, intermediate_size=32, num_hidden_layers=1,
                                      num_attention_heads=2, vocab_size=100, max_position_embeddings=16,
                                      bos_token_id=0, eos_token_id=1),
                     vision_config=dict(hidden_size=16, intermediate_size=32, num_hidden_layers=1,
                                        num_attention_heads=2, image_size=28, patch_size=14, projection_dim=8),
                     projection_dim=8)
    full = CLIPModel(cfg).eval()
    full.save_pretrained(tmp_path)
    vision = CLIPVisionModelWithProjection.from_pretrained(tmp_path).eval()
    x = torch.randn(1, 3, 28, 28)
    with torch.no_grad():
        want = full.visual_projection(full.vision_model(pixel_values=x).pooler_output)
        assert torch.allclose(vision(pixel_values=x).image_embeds, want, atol=1e-6)


def test_effects_keep_what_touches_the_mask_widened_at_the_pictures_size():
    attention = np.zeros((16, 16), np.uint8)  # latent size of a 128×128 working size
    attention[6:10, 6:12] = 255  # object and its shadow, next to the mask
    attention[0:2, 0:2] = 255  # another object's shadow, far off
    grown = np.zeros((256, 256), np.uint8)  # the picture at twice the working size
    grown[96:128, 96:128] = 1
    e = oc.effects(attention, grown)
    assert e.shape == grown.shape and e.dtype == np.uint8 and set(np.unique(e)) <= {0, 1}
    assert e[100, 180] == 1  # the shadow beside the mask (latent 6..10, 6..12 -> 96..160, 96..192 here)
    assert e[100, 195] == 1  # widened beyond the thresholded map
    assert e[:20, :20].sum() == 0  # not connected to the mask: left alone
    assert e[250, 250] == 0


def test_effects_are_empty_when_the_map_marks_nothing_strong():
    attention = np.full((16, 16), oc.THRESHOLD, np.uint8)
    grown = np.zeros((128, 128), np.uint8)
    grown[60:70, 60:70] = 1
    assert oc.effects(attention, grown).sum() == 0


def test_objectclear_counts_as_there_only_with_the_mark_of_its_pinned_revision(tmp_path):
    import json
    assert not oc.ready(str(tmp_path))
    (tmp_path / ".vk-checked.json").write_text(json.dumps({"repo": oc.REPO, "revision": "older"}))
    assert not oc.ready(str(tmp_path))
    (tmp_path / ".vk-checked.json").write_text(json.dumps({"repo": oc.REPO, "revision": oc.PIN[0]}))
    assert not oc.ready(str(tmp_path))  # the mark, but the files are gone
    for f in oc.PIN[1]:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_bytes(b"")
    assert oc.ready(str(tmp_path))
    (tmp_path / sorted(oc.PIN[1])[-1]).unlink()
    assert not oc.ready(str(tmp_path))
    assert all(len(d) == 64 for d in oc.PIN[1].values())


def test_kept_prompt_embeddings_are_read_without_the_text_encoders(tmp_path):
    from safetensors.torch import save_file
    kept = dict(pe=torch.randn(1, 77, 2048).half(), npe=torch.zeros(1, 77, 2048).half(),
                ppe=torch.randn(1, 1280).half(), nppe=torch.zeros(1, 1280).half())
    path = oc._embeds_file(str(tmp_path))
    assert oc.PIN[1]["text_encoder/model.fp16.safetensors"][:12] in path
    assert oc.PIN[1]["text_encoder_2/model.fp16.safetensors"][:12] in path
    save_file(kept, path)
    # no weights in the folder: loading the encoders would fail
    got = oc.prompt_embeds(str(tmp_path), "cpu")
    assert all(torch.equal(g, kept[k]) for g, k in zip(got, ("pe", "npe", "ppe", "nppe")))


def test_the_models_page_expects_the_revisions_pinned_here():
    """src/main/helpers.ts shows RORem and ObjectClear as there only with the mark of the revision in helpers.json."""
    import helpers
    import remove
    by_id = {h["id"]: h for h in helpers.catalog()}
    assert by_id["rorem"]["revision"] == remove.PIN[0]
    assert by_id["objectclear"]["revision"] == oc.PIN[0]


def test_the_engine_refuses_objectclear_where_it_is_not_allowed():
    import engine
    eng = engine.DiffusersEngine.__new__(engine.DiffusersEngine)
    for allowed in (False, None, 1):
        with pytest.raises(ValueError, match="non-commercial use only"):
            eng.remove_object({"remove_object": {"method": "objectclear", "objectclear": allowed},
                               "input_image": "/nowhere.png", "mask_image": "/nowhere.png"})
