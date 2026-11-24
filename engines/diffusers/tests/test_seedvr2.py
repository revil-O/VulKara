# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""SeedVR2 as the Upscale tool's "Detailed" variant (engines/mlx/seedvr2.py), with mflux and MLX stood in: the size it
makes, its download, the memory saver, the phases and a stop between them."""
import json
import os
import sys
import types

import numpy as np
import pytest
from PIL import Image

import photo_tools

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "mlx"))
import seedvr2  # noqa: E402

VARIANT = {"label": "Detailed", "description": "", "engine": "mlx", "max_output": 2048, "size_mb": 6947,
           "files": {"seedvr2_ema_3b_fp16.safetensors": {"url": "https://example.org/t", "sha256": "a" * 64},
                     "ema_vae_fp16.safetensors": {"url": "https://example.org/v", "sha256": "b" * 64}}}


def test_the_result_is_the_factor_asked_for_at_most_2048_on_the_longer_side():
    assert seedvr2.target((512, 512), 4, 4, 2048) == (2048, 2048)
    assert seedvr2.target((300, 200), 2, 4, 2048) == (600, 400)
    assert seedvr2.target((1024, 768), 4, 4, 2048) == (2048, 1536)
    assert seedvr2.target((300, 200), None, 4, 2048) == (1200, 800)  # no factor: the tool's scale
    assert seedvr2.target((300, 200), 8, 4, None) == (1200, 800)  # never more than the tool's scale


@pytest.fixture
def tool(tmp_path, monkeypatch):
    monkeypatch.setenv("VK_HELPERS_DIR", str(tmp_path / "helpers"))
    folder = os.path.join(photo_tools.root(), "swinir")
    os.makedirs(folder)
    json.dump({"type": "photo_tool", "name": "Upscale ×4", "task": "upscale", "kind": "image", "scale": 4,
               "variants": {"detailed": VARIANT, "natural": {"label": "Natural", "file": "n.pth"}}},
              open(os.path.join(folder, "tool.json"), "w"))
    return folder


@pytest.fixture
def mflux(monkeypatch):
    """mflux and MLX stood in: what SeedVR2 was made with and asked for, its callbacks run around the one step."""
    seen = {"cleared": 0}

    class Registry:
        def __init__(self):
            self.all = []

        def register(self, cb):
            self.all.append(cb)

    class SeedVR2:
        def __init__(self, quantize=None, model_path=None, model_config=None):
            seen.update(quantize=quantize, model_path=model_path, config=model_config)
            self.callbacks = Registry()

        def generate_image(self, seed, image_path, resolution, softness=0.0):
            w, h = Image.open(image_path).size
            seen.update(seed=seed, resolution=resolution, callbacks=[type(c).__name__ for c in self.callbacks.all])
            for c in self.callbacks.all:
                getattr(c, "call_before_loop", lambda *a: None)(seed, "", None, None)
            for c in self.callbacks.all:
                getattr(c, "call_after_loop", lambda *a: None)(seed, "", None, None)
            k = resolution / min(w, h)  # mflux: the shorter side at resolution, rounded to its own multiple
            return types.SimpleNamespace(image=Image.new("RGB", (round(w * k) + 3, round(h * k)), (200, 10, 10)))

    class MemorySaver:
        def __init__(self, model, keep_transformer=True):
            seen["keep_transformer"] = keep_transformer

    def module(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, m)

    module("mlx")
    module("mlx.core", clear_cache=lambda: seen.update(cleared=seen["cleared"] + 1))
    for name in ("mflux", "mflux.callbacks", "mflux.callbacks.instances", "mflux.models", "mflux.models.common"):
        module(name)
    module("mflux.callbacks.instances.memory_saver", MemorySaver=MemorySaver)
    module("mflux.models.common.config", ModelConfig=types.SimpleNamespace(seedvr2_3b=lambda: "3b"))
    module("mflux.models.seedvr2", SeedVR2=SeedVR2)
    return seen


@pytest.fixture
def fetched(monkeypatch):
    import pinned
    calls = []
    monkeypatch.setattr(pinned, "fetch_urls", lambda urls, files, dest, report=None: calls.append((urls, files, dest)) or dest)
    return calls


def photo(tmp_path, size):
    path = str(tmp_path / "in.png")
    Image.fromarray(np.random.default_rng(0).integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)).save(path)
    return path


def test_seedvr2_enlarges_with_the_memory_saver_in_8_bit(tmp_path, tool, mflux, fetched):
    states, notes = [], []
    path = seedvr2.run({"photo_tool": {"folder": tool, "variant": "detailed", "factor": 4}, "input_image": photo(tmp_path, (512, 384))},
                       tmp_path, state=states.append, note=notes.append)
    out = Image.open(path)
    assert out.size == (2048, 1536) and os.path.basename(path).startswith("in_upscale_")
    assert np.asarray(out)[0, 0].tolist() == [200, 10, 10]  # strength 1: the model's picture as it is
    # both files at their checksums into the variant's own folder, loaded from there without the net
    urls, files, dest = fetched[0]
    assert dest == os.path.join(tool, "variants", "detailed") and set(urls) == set(files) == set(VARIANT["files"])
    assert mflux["model_path"] == dest and mflux["quantize"] == 8 and mflux["config"] == "3b"
    assert mflux["resolution"] == 1536 and mflux["seed"] == seedvr2.SEED
    # the transformer freed before decoding (11.3 GB instead of 15.5, MEASUREMENTS 7cl); MLX's cache cleared after
    assert mflux["keep_transformer"] is False and "_Watch" in mflux["callbacks"] and mflux["cleared"] == 1
    assert states[0] == "Downloading SeedVR2 (7.3 GB, one-time)"  # the files were not there yet
    assert states[-2:] == ["Upscaling (SeedVR2)", "Decoding (SeedVR2)"] and notes == []


def test_a_larger_result_is_made_smaller_to_2048_and_said_so(tmp_path, tool, mflux, fetched):
    notes = []
    path = seedvr2.run({"photo_tool": {"folder": tool, "variant": "detailed", "factor": 4}, "input_image": photo(tmp_path, (1024, 768))},
                       tmp_path, note=notes.append)
    assert Image.open(path).size == (2048, 1536) and mflux["resolution"] == 1536
    assert notes == ["The result is 2048 × 1536: SeedVR2 makes at most 2048 pixels on the longer side"]


def test_a_stop_between_the_phases_ends_the_job_without_a_picture(tmp_path, tool, mflux, fetched):
    asked = iter([False, True])  # after the download: go on; before the step: stop
    got = seedvr2.run({"photo_tool": {"folder": tool, "variant": "detailed"}, "input_image": photo(tmp_path, (64, 48))},
                      tmp_path, stop=lambda: next(asked))
    assert got is None and not [f for f in os.listdir(tmp_path) if f.endswith(".png") and f != "in.png"]
    assert mflux["cleared"] == 1  # the model freed all the same


def test_only_an_installed_tool_and_its_mlx_variant_run(tmp_path, tool, mflux, fetched):
    job = {"photo_tool": {"folder": tool, "variant": "natural"}, "input_image": photo(tmp_path, (64, 48))}
    with pytest.raises(ValueError, match="no MLX variant natural"):
        seedvr2.run(job, tmp_path)
    elsewhere = str(tmp_path / "elsewhere")
    os.makedirs(elsewhere)
    with pytest.raises(ValueError, match="not installed"):
        seedvr2.run({"photo_tool": {"folder": elsewhere, "variant": "detailed"}, "input_image": job["input_image"]}, tmp_path)
    assert fetched == []
