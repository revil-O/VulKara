# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""End-to-end import + generation with tiny random pipelines from the Hub.

Needs network on first run:  VK_INTEGRATION=1 python -m pytest tests/test_integration.py
"""
import contextlib
import json
import os

import pytest
from PIL import Image

pytestmark = pytest.mark.skipif(os.environ.get("VK_INTEGRATION") != "1", reason="set VK_INTEGRATION=1")

TINY = {
    "flux1": "hf-internal-testing/tiny-flux-pipe",
    "sd3": "hf-internal-testing/tiny-sd3-pipe",
    "sdxl": "hf-internal-testing/tiny-sdxl-pipe",
}


@pytest.fixture(scope="module")
def imported(tmp_path_factory):
    import importer
    root = tmp_path_factory.mktemp("models")
    return {k: importer.run_import("hf", repo, k, root=str(root))["name"] and str(root / k) for k, repo in TINY.items()}


def make_engine(tmp_path, ram_gb=None):
    from engine import DiffusersEngine
    return DiffusersEngine(images_dir=tmp_path / "imgs", ram_gb=ram_gb)


def job(model_dir, **kw):
    return {"prompt": "a red cube", "model_dir": model_dir, "num_steps": 2,
            "width": 64, "height": 64, "seed": 3, **kw}


@pytest.mark.parametrize("family", list(TINY))
def test_txt2img(imported, tmp_path, family):
    paths = make_engine(tmp_path).generate(job(imported[family], count=2))
    assert len(paths) == 2
    assert Image.open(paths[0]).size == (64, 64)


@pytest.mark.parametrize("family", list(TINY))
def test_img2img(imported, tmp_path, family):
    src = tmp_path / "in.png"
    Image.new("RGB", (80, 64), "blue").save(src)
    paths = make_engine(tmp_path).generate(job(imported[family], input_image=str(src), strength=0.6,
                                               exact_size=True))
    assert Image.open(paths[0]).size == (64, 64)


@contextlib.contextmanager
def full_size(model_dir):
    """Pretend the tiny model has the parameter counts of the real one (for the RAM plan)."""
    import registry
    manifest_path = os.path.join(model_dir, "model.json")
    with open(manifest_path) as f:
        m = json.load(f)
    real_components = m["components"]
    m["components"] = registry.ARCHS[m["arch"]]["fallback_params"]
    with open(manifest_path, "w") as f:
        json.dump(m, f)
    try:
        yield
    finally:
        m["components"] = real_components
        with open(manifest_path, "w") as f:
            json.dump(m, f)


# the smallest Macs on which the full-size models fit with the Diffusers runtime
@pytest.mark.parametrize("family, ram_gb", [("flux1", 24), ("sd3", 16)])
def test_staged_and_quantized(imported, tmp_path, family, ram_gb):
    """On a small Mac the plan stages the text encoders and quantizes to 8 bit."""
    with full_size(imported[family]):
        engine = make_engine(tmp_path, ram_gb=ram_gb)
        engine.generate(job(imported[family], guidance_scale=4.0, negative_prompt="blurry"))
        plan = engine.model.plan
        assert engine.model.staged, plan
        assert "q8" in plan["quant"].values(), plan
        # same prompt again: embeddings come from the cache
        engine.generate(job(imported[family], guidance_scale=4.0, negative_prompt="blurry"))


def test_too_little_ram_points_to_mlx(imported, tmp_path, monkeypatch):
    # 14 GB: below the 4 bit plan (fits from 16 GB, 7be); with streaming (auto) it goes from the SSD instead
    # (test_stream_mode.py; the tiny model has no blocks to stream)
    monkeypatch.setenv("VK_SSD_STREAMING", "off")
    with full_size(imported["flux1"]):
        with pytest.raises(MemoryError, match="MLX"):
            make_engine(tmp_path, ram_gb=14).generate(job(imported["flux1"]))


def test_stop(imported, tmp_path):
    import engine as engine_mod

    class Reader:
        def stop_requested(self):
            return True

    e = engine_mod.DiffusersEngine(reader=Reader(), images_dir=tmp_path / "imgs")
    with pytest.raises(engine_mod.StopRequested):
        e.generate(job(imported["flux1"]))


@pytest.fixture(scope="module")
def tiny_controlnets(imported, tmp_path_factory):
    """Randomly initialised ControlNets derived from the tiny models, placed where the engine looks."""
    import diffusers
    import controlnet
    import engine as engine_mod
    root = tmp_path_factory.mktemp("controlnets")
    made = {}
    for family, cls_name in (("sdxl", "ControlNetUnionModel"), ("flux1", "FluxControlNetModel"),
                             ("sd3", "SD3ControlNetModel")):
        m = engine_mod.load_manifest(imported[family])
        model = engine_mod.LoadedModel(imported[family], "cpu")
        model.load()
        cls = getattr(diffusers, cls_name)
        if family == "sdxl":
            ch = model.pipe.unet.config.block_out_channels
            cn = cls.from_config(model.pipe.unet.config, num_control_type=8,
                                 conditioning_embedding_out_channels=(ch[0] // 2, ch[0]),
                                 num_trans_channel=ch[0], num_proj_channel=ch[0], num_trans_head=2)
        else:
            extra = {"num_single_layers": 0} if family == "flux1" else {"dual_attention_layers": ()}
            cn = cls.from_config(model.pipe.transformer.config, num_layers=1, **extra)
        control_type = "Depth"
        spec = controlnet.resolve(m["arch"], m["family"], control_type)
        cn.save_pretrained(str(root / spec["id"]))
        made[family] = (m["arch"], control_type)
        model.destroy()
    old_root, old_fetch = controlnet.root, controlnet.ensure_downloaded
    controlnet.root = lambda models_dir=None: root
    # the tiny ControlNets do not match the pinned checksums: take them as they are, never download the real ones
    controlnet.ensure_downloaded = lambda spec, **kw: controlnet.local_dir(spec)
    yield made
    controlnet.root, controlnet.ensure_downloaded = old_root, old_fetch


@pytest.mark.parametrize("family", list(TINY))
def test_controlnet(imported, tiny_controlnets, tmp_path, family):
    control = tmp_path / "control.png"
    Image.new("RGB", (64, 64), "white").save(control)
    arch, control_type = tiny_controlnets[family]
    e = make_engine(tmp_path)
    cn_job = job(imported[family], controlnet_model=control_type, controlnet_image=str(control),
                 controlnet_weight=0.8)
    assert Image.open(e.generate(cn_job)[0]).size == (64, 64)
    assert e.model.controlnet is not None
    src = tmp_path / "in.png"
    Image.new("RGB", (64, 64), "blue").save(src)
    i2i = dict(cn_job, input_image=str(src), strength=0.6, exact_size=True)
    if family == "sd3":
        with pytest.raises(ValueError, match="can not combine ControlNet"):
            e.generate(i2i)
    else:
        assert Image.open(e.generate(i2i)[0]).size == (64, 64)
    # without ControlNet the model is released again
    e.generate(job(imported[family]))
    assert e.model.controlnet is None


@pytest.mark.parametrize("family", list(TINY))
def test_samplers(imported, tmp_path, family):
    """Every sampler offered for a family generates an image; unknown ones are refused."""
    import samplers
    e = make_engine(tmp_path)
    failed = {}
    for s in ["default"] + samplers.for_family(family):
        try:
            e.generate(job(imported[family], sampler=s))
        except Exception as ex:  # collect all, report together
            failed[s] = "%s: %s" % (type(ex).__name__, str(ex)[:120])
    for sigmas in ("karras", "exponential", "beta"):
        try:
            e.generate(job(imported[family], sampler="default", sigma_schedule=sigmas))
        except Exception as ex:
            failed["default+" + sigmas] = "%s: %s" % (type(ex).__name__, str(ex)[:120])
    assert not failed, failed
    other = "flow_euler" if family == "sdxl" else "ddim"
    with pytest.raises(ValueError, match="does not work"):
        e.generate(job(imported[family], sampler=other))
    # back to the model's own scheduler
    e.generate(job(imported[family]))
    assert e.model.pipe.scheduler is e.model.default_scheduler
