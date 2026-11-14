# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Which model a LoRA is for, from the headers of real LoRAs (tests/fixtures/lora_headers.json.gz: tensor names,
shapes and a few metadata fields of LoRAs from Civitai and of installed ones, no weights). Each case is a
file the detection once filed wrongly or could not place, or one that must stay as it was."""
import gzip
import json
import os

import pytest
import torch

import civitai
import engine
import recheck
import registry
import streaming

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "lora_headers.json.gz")
with gzip.open(FIXTURES, "rt") as f:
    HEADERS = json.load(f)

# fixture -> (family, variant) from the file alone
EXPECTED = {
    # once taken for SDXL (kohya names everything lora_unet_)
    "flux1_kohya_nometa_krea": ("flux1", None),
    "flux1_kohya_nometa_kontext": ("flux1", None),
    "chroma_kohya_meta": ("chroma", None),
    "wan_musubi_5b_label": ("wan", "14b"),  # Civitai calls it 5B, its layers are 5120 wide
    "wan21_musubi_14b": ("wan", "14b"),
    "hunyuan_dit_kohya": ("hunyuan_dit", None),
    # once taken for FLUX.1
    "klein9_peft_dump": ("flux2", "klein9b"),
    "klein9_lcs_mixed_factor_names": ("flux2", "klein9b"),
    "hunyuan_video_diffusers": ("hunyuan_video", None),
    # once Qwen-Image instead of 2.1
    "qwen21_aitoolkit": ("qwen_image21", None),
    "qwen21_diffusers": ("qwen_image21", None),
    # once not recognised at all
    "qwen_diffusers_attn_only": ("qwen_image", None),
    "wan22_14b_aitoolkit": ("wan", "14b"),
    "wan22_5b_aitoolkit": ("wan", "5b"),
    "ideogram4_aitoolkit": ("ideogram4", None),
    "zimage_aitoolkit": ("z_image", None),
    "zimage_comfy_nometa": ("z_image", None),
    "hidream_aitoolkit_sd15meta": ("hidream", None),  # ai-toolkit writes "sd_1.5" for it
    "hidream_o1_aitoolkit": ("hidream_o1", None),
    "lumina_comfy": ("lumina", None),
    "ernie_aitoolkit": ("ernie", None),
    "auraflow_kohya": ("auraflow", None),
    "lokr_flux_simpletuner": ("flux1", None),
    "anima_kohya_meta": ("anima", None),  # no modulation layers: its Cosmos blocks tell
    "moss_comfy_nometa": ("moss_image", None),  # layers.N.proj.q/k/v/o, ffn_up_gate, ffn_down
    "moss_kohya_nometa": ("moss_image", None),
    "fibo2_diffusers_nometa": ("fibo2", None),  # 3584 wide, else NextDiT's names
    "fibo2_comfy_nometa": ("fibo2", None),  # ComfyUI's fused qkv and w13
    # stay as they were
    "flux1_kohya_meta": ("flux1", None),
    "flux1_aitoolkit_meta": ("flux1", None),
    "flux1_aitoolkit_sd15meta_schnell": ("flux1", None),
    "flux2_dev_aitoolkit": ("flux2", "dev"),
    "klein9_aitoolkit": ("flux2", "klein9b"),
    "klein4_aitoolkit": ("flux2", "klein4b"),
    "klein4_peft_bfl": ("flux2", "klein4b"),  # fal's outpaint LoRA: peft prefix, FLUX.2 original names
    "qwen_aitoolkit": ("qwen_image", None),
    "krea2_aitoolkit": ("krea2", None),
    "krea2_kohya": ("krea2", None),
    "anima_aitoolkit": ("anima", None),
    "anima_kohya_sd1_modelspec": ("anima", None),  # its modelspec says SD 1
    "sd1_kohya_te": ("sd1", None),
    "sd1_kohya_nometa": ("sd1", None),
    "sd2_kohya": ("sd2", None),
    "sdxl_kohya_te": ("sdxl", None),
    "sdxl_kohya_v09meta": ("sdxl", None),
    "pony_kohya": ("sdxl", None),
    "sdxl_aitoolkit_lora_transformer": ("sdxl", None),
    "illustrious_stabilizer_diffusers_names": ("sdxl", None),
    "noobai_diffusers_names_nometa": ("sdxl", None),
    "lokr_sdxl": ("sdxl", None),
    "sdxl_dora_mixed_prefixes": ("sdxl", None),  # lora_unet_ and stray diffusion_model_ keys, DoRA
}


def identify(name, hint=None):
    h = HEADERS[name]
    return registry.lora_identity(h["shapes"], h["meta"], hint)


def test_every_fixture_has_an_expectation():
    assert set(HEADERS) - {"chroma_kohya_nometa", "chroma_aitoolkit_comfy"} == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_family_from_the_file(name):
    r = identify(name)
    assert (r["family"], r["variant"]) == EXPECTED[name]


def test_no_lora_is_taken_for_sdxl_by_default():
    with pytest.raises(registry.UnsupportedModel, match="Could not tell"):
        registry.lora_identity({"lora_unet_something_new_0_proj.lora_down.weight": [8, 777],
                                "lora_unet_something_new_0_proj.lora_up.weight": [777, 8]})


def test_chroma_without_metadata_needs_its_source():
    # a FLUX.1 LoRA without modulation layers fits FLUX.1 and Chroma: the source decides, else FLUX.1
    for name in ("chroma_kohya_nometa", "chroma_aitoolkit_comfy"):
        assert identify(name)["family"] == "flux1"
        r = identify(name, civitai.lora_hint("Chroma"))
        assert r["family"] == "chroma" and r["detected_by"] == "source" and not r["hint_mismatch"]
    # with modulation layers it is FLUX.1 whatever the source says
    r = identify("flux1_kohya_nometa_krea", civitai.lora_hint("Chroma"))
    assert r["family"] == "flux1" and r["hint_mismatch"]


def test_the_file_wins_over_the_source_and_both_are_kept():
    r = identify("flux1_kohya_nometa_kontext", civitai.lora_hint("Flux.1 Kontext"))
    assert r["family"] == "flux1" and not r["hint_mismatch"]
    r = identify("qwen21_aitoolkit", civitai.lora_hint("Qwen"))
    assert r["family"] == "qwen_image21" and r["hint_mismatch"] and r["hint"]["family"] == "qwen_image"
    r = identify("wan_musubi_5b_label", civitai.lora_hint("Wan Video 2.2 TI2V-5B"))
    assert (r["family"], r["variant"]) == ("wan", "14b") and r["hint_mismatch"]
    r = identify("pony_kohya", civitai.lora_hint("Pony V7"))  # an SDXL LoRA filed under Pony V7 (AuraFlow)
    assert r["family"] == "sdxl" and r["hint_mismatch"]


def test_metadata_values():
    assert registry.family_of_base("qwen_image_2") == ("qwen_image21", None)
    assert registry.family_of_base("qwen_image_2512") == ("qwen_image", None)
    assert registry.family_of_base("flux2_klein_9b") == ("flux2", "klein9b")
    assert registry.family_of_base("flux2_klein_4b") == ("flux2", "klein4b")
    assert registry.family_of_base("krea-dev")[0] == "flux1"  # mflux's FLUX.1 Krea, not Krea 2
    assert registry.family_of_base("flux-1-krea-dev/lora")[0] == "flux1"
    assert registry.family_of_base("krea-2/lora")[0] == "krea2"
    assert registry.family_of_base("anima-preview/lora")[0] == "anima"
    assert registry.family_of_base("animagine-xl-3.1")[0] is None
    assert registry.family_of_base("wan_2.2_5b") == ("wan", "5b")
    assert registry.family_of_base("sd_v2_v")[0] == "sd2"
    # ai-toolkit's default value and kohya forks' modelspec are not believed
    meta = {"ss_base_model_version": "sd_1.5", "software": json.dumps({"name": "ai-toolkit"})}
    assert registry._family_from_metadata(meta)[0] is None
    assert registry._family_from_metadata({"modelspec.architecture": "stable-diffusion-v1/lora"})[0] is None
    assert registry._family_from_metadata({"ss_base_model_version": "sd_v1"})[0] == "sd1"


def test_metadata_chooses_where_the_layers_leave_a_choice():
    names = {"transformer.transformer_blocks.0.attn.to_q.lora_A.weight": [4, 4],
             "transformer.transformer_blocks.0.attn.to_q.lora_B.weight": [4, 4]}
    with pytest.raises(registry.UnsupportedModel, match="fit"):
        registry.lora_identity(names)
    assert registry.lora_identity(names, {"ss_base_model_version": "qwen_image"})["family"] == "qwen_image"
    assert registry.lora_identity(names, None, "flux1")["family"] == "flux1"


def test_civitai_bases():
    assert civitai.arch_of("Pony V7") == "auraflow" and civitai.family_of("Pony V7") == ("auraflow", None)
    assert civitai.arch_of("Pony") == "sdxl"
    assert civitai.arch_of("Qwen") == "qwen_image" and civitai.arch_of("Qwen 2.1") == "qwen_image21"
    assert civitai.family_of("Qwen 2") == (None, None)  # not known: no guess
    assert civitai.family_of("Chroma") == ("chroma", None) and civitai.arch_of("Chroma") == "chroma"
    assert civitai.family_of("Flux.2 Klein 9B-base") == ("flux2", "klein9b")
    assert civitai.family_of("Flux.2 Klein 4B") == ("flux2", "klein4b")
    assert civitai.family_of("Flux.2 D") == ("flux2", "dev")
    assert civitai.arch_of("Flux.3") == "unknown"
    assert civitai.family_of("Flux.3 Klein") == ("flux3", None) and civitai.family_of("Flux.3 Klein-base") == ("flux3", None)
    assert civitai.arch_of("Wan Video 2.2 TI2V-5B") == "wan22_ti2v"
    assert civitai.family_of("Wan Video 14B t2v") == ("wan", "14b")
    assert civitai.family_of("ZImageTurbo") == ("z_image", None)
    assert civitai.lora_hint("Other") is None


def test_hugging_face_bases():
    assert registry.family_of_repo("black-forest-labs/FLUX.2-klein-base-9B") == ("flux2", "klein9b")
    assert registry.family_of_repo("black-forest-labs/FLUX.1-dev") == ("flux1", None)
    assert registry.family_of_repo("Qwen/Qwen-Image-2.1") == ("qwen_image21", None)
    assert registry.family_of_repo("Qwen/Qwen-Image") == ("qwen_image", None)
    assert registry.family_of_repo("stabilityai/stable-diffusion-xl-base-1.0") == ("sdxl", None)
    assert registry.family_of_repo("black-forest-labs/flux-3-image-klein") == ("flux3", None)
    assert registry.family_of_repo("black-forest-labs/flux-3-image-klein-base") == ("flux3", None)
    assert registry.family_of_repo("someone/my-merge") == (None, None)


# ---------------------------------------------------------------- sub-bases and the engines' check

KLEIN4 = {"arch": "flux2_klein", "family": "flux2", "label": "FLUX.2 [klein]", "components": {"transformer": 3.88}}
KLEIN9 = {"arch": "flux2_klein", "family": "flux2", "label": "FLUX.2 [klein]", "components": {"transformer": 9.08}}


def test_model_variants():
    assert registry.model_variant(KLEIN4) == "klein4b" and registry.model_variant(KLEIN9) == "klein9b"
    assert registry.model_variant({"arch": "flux2_klein", "name": "FLUX.2-klein-9B"}) == "klein9b"
    assert registry.model_variant({"arch": "flux2_dev"}) == "dev"
    assert registry.model_variant({"arch": "wan22_ti2v"}) == "5b"
    assert registry.model_variant({"arch": "sdxl"}) is None


def test_a_klein_9b_lora_is_refused_for_4b():
    lora = {"name": "br33zy", "family": "flux2", "variant": "klein9b"}
    assert registry.lora_mismatch(lora, KLEIN9) is None
    assert "9B" in registry.lora_mismatch(lora, KLEIN4)
    assert registry.lora_mismatch({"name": "old", "family": "flux2"}, KLEIN4) is None  # sub-base unknown: allowed
    assert "made for Stable Diffusion XL models" in registry.lora_mismatch({"name": "x", "family": "sdxl"}, KLEIN4)
    wan14 = {"arch": "wan22_i2v_14b", "family": "wan", "label": "Wan 2.2 14B"}
    assert "no LoRAs" in registry.lora_mismatch({"name": "w", "family": "wan", "variant": "14b"}, wan14)
    chroma = {"arch": "chroma", "family": "chroma", "label": "Chroma"}
    assert registry.lora_mismatch({"name": "c", "family": "chroma"}, chroma) is None
    assert "FLUX.1" in registry.lora_mismatch({"name": "f", "family": "flux1"}, chroma)
    assert registry.lora_mismatch({"name": "c", "family": "chroma"}, dict(chroma, unsupported="no runtime")) == "no runtime"


def test_chroma_checkpoints_are_recognised():
    shapes = {"distilled_guidance_layer.in_proj.weight": [5120, 64], "double_blocks.0.img_attn.qkv.weight": [9216, 3072],
              "single_blocks.0.linear1.weight": [21504, 3072], "img_in.weight": [3072, 64]}
    assert registry.is_chroma(shapes)
    assert registry.detect_from_single_file(shapes, "gonzalomoChroma_v20.safetensors")[:2] == ("chroma", "single_denoiser")
    shapes.pop("distilled_guidance_layer.in_proj.weight")
    assert registry.detect_from_single_file(dict(shapes, **{"guidance_in.in_layer.weight": [3072, 256]}))[0] == "flux1_dev"


# ---------------------------------------------------------------- loading: the 90 % check


class _Adapted(torch.nn.Module):
    def __init__(self, with_adapter):
        super().__init__()
        self.lora_A = torch.nn.ModuleDict({"lora0": torch.nn.Linear(2, 2)} if with_adapter else {})


class _Pipe:
    def __init__(self, n_layers, n_applied):
        self.n_layers = n_layers
        self.transformer = torch.nn.ModuleList([_Adapted(i < n_applied) for i in range(n_layers)])
        self.adapters = []

    def lora_state_dict(self, file, **kwargs):
        return {"transformer.l%d.lora_A.weight" % i: torch.zeros(2, 2) for i in range(self.n_layers)}, {}


def _model():
    m = engine.LoadedModel.__new__(engine.LoadedModel)
    m.m, m.spec = {"denoiser": "transformer"}, {"label": "FLUX.1 [dev]"}
    return m


def test_a_lora_of_which_too_few_layers_arrive_is_refused():
    lora = {"file": "x.safetensors", "name": "Half"}
    _model()._check_applied(_Pipe(10, 10), lora, "lora0")
    _model()._check_applied(_Pipe(10, 9), lora, "lora0")  # 90 %: still fits
    with pytest.raises(ValueError, match=r"Half does not fit this FLUX.1 \[dev\] model: only 80% of its layers \(8 of 10\)"):
        _model()._check_applied(_Pipe(10, 8), lora, "lora0")
    with pytest.raises(ValueError, match="none of its layers"):
        _model()._check_applied(_Pipe(0, 0), lora, "lora0")


class _FailingPipe(_Pipe):
    def __init__(self):
        super().__init__(4, 4)
        self.unloaded = False

    def load_lora_weights(self, *a, **k):
        pass

    def set_adapters(self, names, adapter_weights=None):
        raise ValueError("Adapter name(s) {'lora0'} not in the list of present adapters: set().")

    def unload_lora_weights(self):
        self.unloaded = True


def test_the_adapters_error_of_diffusers_never_surfaces_raw():
    m = _model()
    m.stream, m.lora_key, m.separate_text = False, (), False
    m.pipe = _FailingPipe()
    with pytest.raises(ValueError) as e:
        m.apply_loras([{"file": "x.safetensors", "scale": 1.0, "name": "Mine"}])
    assert str(e.value).startswith("The LoRAs could not be switched on for this FLUX.1 [dev] model")
    assert m.pipe.unloaded and m.lora_key == ()


def test_kohya_sdxl_loras_keep_their_unet_part():
    """_lora_state_dict passes the UNet's config: without it kohya's SDXL block names (input_blocks_4_1 …) match no
    UNet layer and only the fallback without the text encoder part loaded them."""
    seen = {}

    class P:
        unet = type("U", (), {"config": {"sample_size": 128}})()

        def lora_state_dict(self, file, **kwargs):
            seen.update(kwargs)
            return {}, None
    engine.LoadedModel._lora_state_dict(P(), "x")
    assert seen.get("unet_config") == {"sample_size": 128}


# ---------------------------------------------------------------- streaming: names and sizes checked first


class _Toy(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.proj_in = torch.nn.Linear(8, 16)
        self.transformer_blocks = torch.nn.ModuleList([torch.nn.Linear(16, 16) for _ in range(3)])

    def forward(self, x):
        x = self.proj_in(x)
        for b in self.transformer_blocks:
            x = torch.tanh(b(x))
        return x


def test_streamed_loras_of_another_size_are_left_out_before_generating(tmp_path):
    torch.manual_seed(0)
    model, x = _Toy(), torch.randn(2, 8)
    plain = model(x)
    streaming.enable(model, torch.device("cpu"), torch.float32, str(tmp_path))
    good = ("transformer_blocks.0", torch.zeros(2, 16), torch.zeros(16, 2), 1.0)
    wide = ("transformer_blocks.1", torch.randn(2, 24), torch.randn(24, 2), 1.0)  # a larger model's layer
    unknown = ("transformer_blocks.2.missing", torch.randn(2, 16), torch.randn(16, 2), 1.0)
    assert streaming.fitting(model, [good, wide, unknown]) == 1
    assert streaming.set_loras(model, [good, wide, unknown]) == 1
    assert torch.allclose(model(x), plain, atol=1e-6)  # runs through: the misfit was never merged


# ---------------------------------------------------------------- the one-time check of the library


def _lora_folder(root, name, fixture, manifest):
    from safetensors.numpy import save_file
    import numpy as np
    folder = root / name
    folder.mkdir(parents=True)
    h = HEADERS[fixture]
    save_file({k: np.zeros(v, np.float16) for k, v in h["shapes"].items()}, str(folder / "lora.safetensors"),
              metadata=h["meta"] or None)
    (folder / "lora.json").write_text(json.dumps(dict({"name": name, "file": "lora.safetensors"}, **manifest)))
    return folder


def test_recheck_corrects_wrong_families_and_keeps_a_backup(tmp_path):
    loras, models = tmp_path / "loras", tmp_path / "models"
    wrong = _lora_folder(loras, "kontext", "flux1_kohya_nometa_kontext", {"family": "sdxl"})
    klein = _lora_folder(loras, "klein", "klein4_aitoolkit", {"family": "flux2"})
    fine = _lora_folder(loras, "fine", "sd1_kohya_te", {"family": "sd1"})
    m = models / "FLUX.2-klein-9B"
    m.mkdir(parents=True)
    (m / "model.json").write_text(json.dumps(KLEIN9))
    report = recheck.recheck(str(models), str(loras))
    by_name = {r["name"]: r for r in report}
    assert by_name["kontext"]["changes"] == {"family": ["sdxl", "flux1"]}
    assert by_name["klein"]["changes"] == {"variant": [None, "klein4b"]}
    # a model keeps its sub-base apart from "variant", the file variant diffusers loads
    assert by_name["FLUX.2-klein-9B"]["changes"] == {"sub_base": [None, "klein9b"]}
    assert "fine" not in by_name
    assert not (wrong / "lora.json.bak").exists()  # a dry run changes nothing
    recheck.recheck(str(models), str(loras), apply=True)
    assert json.loads((wrong / "lora.json").read_text())["family"] == "flux1"
    assert json.loads((wrong / "lora.json.bak").read_text())["family"] == "sdxl"
    assert json.loads((klein / "lora.json").read_text())["variant"] == "klein4b"
    written = json.loads((m / "model.json").read_text())
    assert written["sub_base"] == "klein9b" and "variant" not in written
    assert not (fine / "lora.json.bak").exists()
    assert recheck.recheck(str(models), str(loras)) == []  # once is enough


def test_a_sub_base_written_into_the_file_variant_is_moved_back(tmp_path):
    """The recheck of 2026-10-07 wrote klein4b / klein9b into model.json "variant"; diffusers then looked for
    model.klein4b.safetensors and the model could not load."""
    models = tmp_path / "models"
    broken = models / "FLUX.2-klein-4B"
    broken.mkdir(parents=True)
    (broken / "model.json.bak").write_text(json.dumps(dict(KLEIN4, variant=None)))
    (broken / "model.json").write_text(json.dumps(dict(KLEIN4, variant="klein4b")))
    # one whose weights were the fp16 files before: that comes back
    fp16 = models / "Klein-fp16"
    fp16.mkdir()
    (fp16 / "model.json.bak").write_text(json.dumps(dict(KLEIN9, variant="fp16")))
    (fp16 / "model.json").write_text(json.dumps(dict(KLEIN9, variant="klein9b")))
    assert registry.file_variant(dict(KLEIN4, variant="klein4b")) is None  # the engine never passes a sub-base
    assert registry.file_variant(dict(KLEIN4, variant="fp16")) == "fp16"
    by_name = {r["name"]: r for r in recheck.recheck(str(models), None)}
    assert by_name["FLUX.2-klein-4B"]["changes"] == {"sub_base": [None, "klein4b"], "variant": ["klein4b", None]}
    assert by_name["Klein-fp16"]["changes"] == {"sub_base": [None, "klein9b"], "variant": ["klein9b", "fp16"]}
    recheck.recheck(str(models), None, apply=True)
    a = json.loads((broken / "model.json").read_text())
    b = json.loads((fp16 / "model.json").read_text())
    assert (a.get("variant"), a["sub_base"]) == (None, "klein4b") and (b["variant"], b["sub_base"]) == ("fp16", "klein9b")
    assert registry.model_variant(a) == "klein4b" and registry.model_variant(b) == "klein9b"
    assert recheck.recheck(str(models), None) == []


def test_recheck_files_a_chroma_checkpoint_as_chroma(tmp_path):
    import numpy as np
    from safetensors.numpy import save_file
    m = tmp_path / "models" / "GonzaLomo_Chroma"
    m.mkdir(parents=True)
    save_file({"distilled_guidance_layer.in_proj.weight": np.zeros((2, 2), np.float16),
               "double_blocks.0.img_attn.qkv.weight": np.zeros((2, 2), np.float16)}, str(m / "model.safetensors"))
    (m / "model.json").write_text(json.dumps({"name": "GonzaLomo_Chroma", "arch": "flux1_schnell", "family": "flux1",
                                              "label": "FLUX.1 [schnell]", "layout": "single_denoiser",
                                              "file": "model.safetensors"}))
    recheck.recheck(str(tmp_path / "models"), str(tmp_path / "loras"), apply=True, ram_gb=24)
    data = json.loads((m / "model.json").read_text())
    assert (data["arch"], data["family"], data["label"]) == ("chroma", "chroma", "Chroma")
    assert "unsupported" not in data and data["negative_prompt"] is True
