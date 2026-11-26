# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""LTX-2.3 on MLX: recognising its folder, the plan on 16 GB, clip length and size, the runtime extension's path, the
prompt encoded in two stages and the mp4 writer (PyAV and MLX are not in the Diffusers runtime: stand-ins)."""
import json
import os
import sys
import types

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "mlx"))
import importer  # noqa: E402
import ltx23  # noqa: E402
import registry  # noqa: E402

SPLIT = {"format": "split", "model_version": "2.3.0", "components": ["connector"], "transformer_variants": ["distilled"]}
SIZES = {"transformer-distilled.safetensors": 11322002285, "connector.safetensors": 6344495512,
         "vae_decoder.safetensors": 814349531, "vae_encoder.safetensors": 637885319,
         "audio_vae.safetensors": 106509048, "vocoder.safetensors": 258313851,
         "spatial_upscaler_x2_v1_1.safetensors": 995745061}


def test_an_ltx_2_3_folder_is_recognised_by_its_split_format():
    assert registry.detect_ltx23(SPLIT, list(SIZES)) == "ltx23"
    assert registry.detect_ltx23({"format": "split", "model_version": "2.5.0"}) is None
    assert registry.detect_ltx23({"format": "flux3-mlx"}) is None
    with pytest.raises(registry.UnsupportedModel):
        registry.detect_ltx23(SPLIT, ["transformer-dev.safetensors"])


def test_a_local_folder_is_inspected_as_ltx23(tmp_path):
    (tmp_path / "split_model.json").write_text(json.dumps(SPLIT))
    for name in SIZES:
        (tmp_path / name).write_bytes(b"0")
    (tmp_path / "._split_model.json").write_bytes(b"exfat")
    info = importer.inspect_ltx23("dir", str(tmp_path))
    assert info["arch"] == "ltx23" and info["layout"] == "folder" and info["download_bytes"] == 0
    assert importer.inspect_ltx23("dir", str(tmp_path / "nothing")) is None


def test_only_what_the_distilled_path_reads_is_downloaded(monkeypatch):
    repo = dict(SIZES, **{"transformer-dev.safetensors": 11322002285, "ltx-2.3-22b-distilled-lora-384.safetensors": 7605507256,
                          "split_model.json": 1893, "config.json": 951, "LICENSE": 19197})
    monkeypatch.setattr(importer, "_hf_json", lambda ref, name, token=None: SPLIT)
    monkeypatch.setattr(importer, "_hf_repo_info", lambda ref, token=None: (None, repo))
    monkeypatch.setattr(importer, "_hashes", lambda ref, files: {})
    info = importer.inspect_ltx23("hf", "dgrauet/ltx-2.3-mlx-q4")
    assert "transformer-dev.safetensors" not in info["files"]
    assert not any("lora" in f for f in info["files"])
    assert set(SIZES) <= set(info["files"]) and "LICENSE" in info["files"]
    assert round(info["download_bytes"] / 1e9, 1) == 20.5


def test_it_fits_a_16_gb_mac_and_the_plan_stays_above_the_measured_peak():
    info = {"arch": "ltx23", "components": importer._ltx23_components(SIZES), "denoiser": "transformer"}
    plan = importer.make_plan(info, ram_gb=16)
    assert plan["fits"]
    assert 8.0 <= plan["est_peak_gb"] <= plan["budget_gb"]  # 7cp: 8.0 GB measured in all
    assert not importer.make_plan(info, ram_gb=8)["fits"]


def test_clip_length_and_size_on_ltx_grids():
    assert [ltx23.frames_for(s) for s in (1, 2, 5)] == [25, 49, 121]  # 8n + 1 frames at 24 fps
    assert ltx23.snap(768, 512) == (768, 512)
    assert ltx23.snap(864, 480) == (896, 512)  # the app's 480p 16:9 size, onto 64 px
    assert ltx23.snap(100, 100) == (256, 256)


def test_the_runtime_extension_is_found_beside_the_venv(tmp_path):
    for pkg in ("ltx-core-mlx", "ltx-pipelines-mlx", "ltx-trainer"):
        (tmp_path / "extensions" / "ltx-2-mlx" / "packages" / pkg / "src").mkdir(parents=True)
    paths = ltx23.extension_paths(prefix=str(tmp_path / "venv"))
    assert [os.path.basename(os.path.dirname(p)) for p in paths] == ["ltx-core-mlx", "ltx-pipelines-mlx"]


def test_gemma_is_freed_before_the_connector_loads(monkeypatch):
    events = []
    monkeypatch.setitem(sys.modules, "mlx", types.ModuleType("mlx"))
    core = types.ModuleType("mlx.core")
    core.eval = lambda *a: events.append("eval")
    monkeypatch.setitem(sys.modules, "mlx.core", core)
    for name in ("ltx_core_mlx", "ltx_core_mlx.utils"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    memory = types.ModuleType("ltx_core_mlx.utils.memory")
    memory.aggressive_cleanup = lambda: events.append("cleanup")
    monkeypatch.setitem(sys.modules, "ltx_core_mlx.utils.memory", memory)

    class Encoder:
        _text_encoder = _feature_extractor = None

        def load(self):  # as ltx-2-mlx's PromptEncoder.load: each part only when it is missing
            if self._text_encoder is None:
                events.append("load gemma")
                self._text_encoder = types.SimpleNamespace(encode_all_layers=lambda p, max_length: (["h"], "m"))
            if self._feature_extractor is None:
                assert self._text_encoder is not None
                events.append("load connector")
                self._feature_extractor = lambda h, attention_mask: ("video", "audio")

    enc = Encoder()
    assert ltx23.staged_encode(enc, "a fox") == ("video", "audio")
    assert events == ["load gemma", "eval", "cleanup", "load connector"]
    assert enc._text_encoder is None


class _Av(types.ModuleType):
    """Records what ltx23.write_mp4 asks of PyAV."""

    def __init__(self):
        super().__init__("av")
        self.log = {"video": 0, "audio": 0, "codecs": [], "metadata": {}}
        av = self

        class Stream:
            def __init__(self, codec):
                self.codec = codec

            def encode(self, frame=None):
                if frame is not None:
                    av.log[frame.kind] += 1
                return []

        class Container:
            metadata = av.log["metadata"]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def add_stream(self, codec, rate=None):
                av.log["codecs"].append((codec, rate))
                return Stream(codec)

            def mux(self, packets):
                pass

        self.open = lambda path, mode, format=None: Container()
        self.VideoFrame = types.SimpleNamespace(from_ndarray=lambda a, format: types.SimpleNamespace(kind="video", shape=a.shape))
        self.AudioFrame = types.SimpleNamespace(
            from_ndarray=lambda a, format, layout: types.SimpleNamespace(kind="audio", shape=a.shape, layout=layout))


def test_the_mp4_gets_every_frame_the_sound_and_the_ai_notice(monkeypatch):
    av = _Av()
    monkeypatch.setitem(sys.modules, "av", av)
    chunks = [np.zeros((1, 3, n, 64, 96), np.float32) for n in (17, 16, 16)]  # tiled_decode's (B, 3, T, H, W)
    wave = np.zeros((1, 2, 48000 * 2), np.float32)
    assert ltx23.write_mp4("x.mp4", iter(chunks), wave, 24, "AI generated with VulKara (model: LTX-2.3)") == 49
    assert av.log["video"] == 49 and av.log["audio"] == -(-96000 // 1024)
    assert av.log["codecs"] == [("aac", 48000), ("h264_videotoolbox", 24)]
    assert av.log["metadata"]["comment"] == "AI generated with VulKara (model: LTX-2.3)"
    av.log.update(video=0, audio=0, codecs=[])
    assert ltx23.write_mp4("y.mp4", iter(chunks), None, 24, "n") == 49  # without sound: no audio stream
    assert av.log["codecs"] == [("h264_videotoolbox", 24)] and av.log["audio"] == 0


def test_a_failed_encode_leaves_no_video_behind(tmp_path):
    import pytest
    path = str(tmp_path / "ltx23_x.mp4")

    def broken(part):
        open(part, "wb").write(b"half a video")
        raise RuntimeError("encoder failed")
    with pytest.raises(RuntimeError):
        ltx23.written(path, broken)
    assert list(tmp_path.iterdir()) == []

    def good(part):
        open(part, "wb").write(b"video")
        return 49
    assert ltx23.written(path, good) == 49
    assert [p.name for p in tmp_path.iterdir()] == ["ltx23_x.mp4"]


def test_frame_counts_for_long_clips_and_30_fps():
    """LTX takes 8n + 1 frames: the counts of the measured clips (MEASUREMENTS 7cy)."""
    assert [ltx23.frames_for(s) for s in (5, 10, 20)] == [121, 241, 481]
    assert ltx23.frames_for(5, 30) == 153
