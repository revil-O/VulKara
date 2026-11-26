# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Civitai: which version and which file of a model the import takes."""
import civitai


def f(name, fp, primary=False, ftype="Diffusion Model"):
    return {"name": name, "type": ftype, "primary": primary, "metadata": {"format": "SafeTensor", "fp": fp}}


def test_files_the_mac_can_compute_are_picked():
    # the primary file is int8 (ComfyUI): the bf16 one is taken instead
    v = {"files": [f("a", "int8", True), f("b", "nvfp4"), f("c", "bf16"), f("d", "fp8")]}
    assert civitai.pick_file(v)["name"] == "c"
    # a usable primary file wins
    assert civitai.pick_file({"files": [f("a", "fp8", True), f("c", "bf16")]})["name"] == "a"
    assert civitai.pick_file({"files": [f("a", "int4", True), f("b", "int8")]}) is None
    # "Model" and "Diffusion Model" files count, training data does not
    assert civitai.pick_file({"files": [f("t", "bf16", ftype="Training Data")]}) is None


def test_gguf_versions_are_usable():
    # Civitai files GGUF as "GGUF" or as "Other"; a SafeTensor file of the same version is preferred
    gguf = {"name": "m-Q8_0.gguf", "type": "Model", "metadata": {"format": "Other", "fp": None}}
    assert civitai.pick_file({"files": [gguf]})["name"] == "m-Q8_0.gguf"
    assert civitai.pick_file({"files": [dict(gguf, metadata={"format": "GGUF", "fp": "bf16"})]}) is not None
    assert civitai.pick_file({"files": [gguf, f("m.safetensors", "bf16")]})["name"] == "m.safetensors"
    pickle = {"name": "m.ckpt", "type": "Model", "metadata": {"format": "PickleTensor", "fp": "fp16"}}
    assert civitai.pick_file({"files": [pickle]}) is None


def test_model_types():
    assert civitai.arch_of("Krea 2") == "krea2"
    assert civitai.arch_of("NoobAI") == "sdxl"
    assert civitai.arch_of("SD 1.5") == "sd15"
    assert civitai.arch_of("Anima") == "anima"
    assert civitai.arch_of("Wan Video 14B t2v") == "unknown"


def test_newest_runnable_version_is_taken(monkeypatch):
    model = {"type": "Checkpoint", "name": "M", "modelVersions": [
        {"id": 3, "name": "v3", "baseModel": "Wan Video 14B t2v", "files": [f("x", "bf16", True)]},
        {"id": 2, "name": "v2", "baseModel": "Krea 2", "files": [f("y", "int8", True)]},
        {"id": 1, "name": "v1", "baseModel": "Illustrious", "files": [f("z", "fp16", True, "Model")]},
    ]}
    monkeypatch.setattr(civitai, "_get_json", lambda url, token=None: model)
    c = civitai.resolve("https://civitai.com/models/7/m")
    assert (c["version_id"], c["arch"], c["file_name"]) == (1, "sdxl", "z")
    assert "v3" in c["note"] and "v2" in c["note"]
    # every version for the choice in the app, the ones it can not run with their reason
    assert [(v["id"], v["usable"]) for v in c["versions"]] == [(3, False), (2, False), (1, True)]
    assert c["versions"][0]["reason"] == "model type not supported" and c["versions"][1]["reason"]
