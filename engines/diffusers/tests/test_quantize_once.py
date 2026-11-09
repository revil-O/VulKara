# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""The one-time quantization runs in a process of its own and the engine loads the result from the cache."""
import types

import engine
import quant_cache
import quantize_once


class FakeProc:
    def __init__(self, code=0, polls=1):
        self.code, self.polls, self.terminated = code, polls, False

    def poll(self):
        if self.terminated:
            return -15
        self.polls -= 1
        return None if self.polls >= 0 else self.code

    @property
    def returncode(self):
        return -15 if self.terminated else self.code

    def terminate(self):
        self.terminated = True

    def wait(self):
        return self.returncode


def test_run_reports_the_child_and_ends_it_on_a_stop(monkeypatch):
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)
    procs = [FakeProc(), FakeProc(polls=100)]
    started = iter(procs)
    monkeypatch.setattr(quantize_once.subprocess, "Popen", lambda *a, **k: next(started))
    assert quantize_once.run({"kind": "component"}) is True
    # a cancelled job: the child still running is ended
    assert quantize_once.run({"kind": "component"}, stop=lambda: True) is False and procs[1].terminated


def test_a_component_is_quantized_in_its_own_process_then_loaded_from_the_cache(monkeypatch):
    calls = []
    model = types.SimpleNamespace(model_dir="/m", stop=None, _component_class=lambda folder, comp: types.SimpleNamespace(
        from_pretrained=lambda *a, **k: calls.append("in process")))
    loads = iter([None, "cached model"])
    monkeypatch.setattr(quant_cache, "load", lambda *a: next(loads))
    monkeypatch.setattr(quant_cache, "enabled", lambda: True)
    monkeypatch.setattr(quantize_once, "run", lambda job, stop: calls.append(job["kind"]) or True)
    monkeypatch.setattr(engine.protocol, "status", lambda s: None)
    out = engine.LoadedModel._load_component(model, "/m/weights", "transformer", None, "q8", dtype="bfloat16")
    assert out == "cached model" and calls == ["component"]
