# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""The lock on ComfyUI's server (engines/comfy/custom_nodes/vulkara_guard): only requests with the key get through.
Needs aiohttp, which the ComfyUI runtime has (skipped elsewhere)."""
import asyncio
import importlib.util
import os
import sys
import types

import pytest

aiohttp = pytest.importorskip("aiohttp")
from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

GUARD = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "comfy", "custom_nodes", "vulkara_guard", "__init__.py")


def _app_with_guard(monkeypatch, token):
    app = web.Application()
    app.router.add_get("/system_stats", lambda request: web.json_response({"ok": True}))
    # ComfyUI's PromptServer as the guard finds it when ComfyUI loads custom nodes
    server = types.ModuleType("server")
    server.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(app=app))
    monkeypatch.setitem(sys.modules, "server", server)
    monkeypatch.setenv("VK_COMFY_TOKEN", token)
    spec = importlib.util.spec_from_file_location("vulkara_guard_test", GUARD)
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    return app


def test_only_requests_with_the_key_get_through(monkeypatch):
    app = _app_with_guard(monkeypatch, "secret-key")

    async def run():
        async with TestClient(TestServer(app)) as client:
            ok = await client.get("/system_stats", headers={"X-VK-Token": "secret-key"})
            none = await client.get("/system_stats")
            wrong = await client.get("/system_stats", headers={"X-VK-Token": "guess"})
            return ok.status, none.status, wrong.status

    assert asyncio.run(run()) == (200, 403, 403)


def test_without_a_key_from_the_app_nothing_gets_through(monkeypatch):
    app = _app_with_guard(monkeypatch, "")

    async def run():
        async with TestClient(TestServer(app)) as client:
            return (await client.get("/system_stats", headers={"X-VK-Token": ""})).status

    assert asyncio.run(run()) == 403


def test_the_memory_switch_takes_only_its_two_modes(monkeypatch):
    import enum
    node = os.path.join(os.path.dirname(GUARD), "..", "vulkara_memory", "__init__.py")
    mm = types.ModuleType("comfy.model_management")
    mm.VRAMState = enum.Enum("VRAMState", "LOW_VRAM NO_VRAM SHARED")
    mm.vram_state = mm.VRAMState.SHARED
    # ComfyUI keeps an FP8 file in FP8 where 16 bit does not fit
    mm.FLOAT8_TYPES = ["fp8"]
    import torch
    mm.unet_dtype = lambda model_params=0, supported_dtypes=(), weight_dtype=None: \
        weight_dtype if weight_dtype == "fp8" and model_params > 10 else torch.bfloat16
    mm.get_torch_device = lambda: types.SimpleNamespace(type="mps")
    comfy = types.ModuleType("comfy")
    comfy.model_management = mm
    monkeypatch.setitem(sys.modules, "comfy", comfy)
    monkeypatch.setitem(sys.modules, "comfy.model_management", mm)
    routes = web.RouteTableDef()
    server = types.ModuleType("server")
    pending = [{"free_memory": True}, {"free_memory": True}]
    reads = []
    queue = types.SimpleNamespace(get_flags=lambda reset=True: reads.append(pending.pop(0) if pending else {}) or reads[-1])
    server.PromptServer = types.SimpleNamespace(instance=types.SimpleNamespace(routes=routes, prompt_queue=queue))
    monkeypatch.setitem(sys.modules, "server", server)
    import torch.nn.functional as F
    monkeypatch.setattr(F, "scaled_dot_product_attention", F.scaled_dot_product_attention)  # the node patches it
    spec = importlib.util.spec_from_file_location("vulkara_memory_test", node)
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
    # the VAE keeps split attention; heads of 40 are padded to the same result
    assert mm.pytorch_attention_enabled_vae() is False
    # MPS cannot cast FP8: such a model stays in 16 bit
    assert (mm.unet_dtype(model_params=20, weight_dtype="fp8"), mm.unet_dtype(model_params=1, weight_dtype="fp8")) == (torch.bfloat16,) * 2
    # MPS computes bfloat16 at half the speed: float16 where the model allows it (Anima), else bfloat16 stays (Lumina 2)
    anima, lumina = [torch.bfloat16, torch.float16, torch.float32], [torch.bfloat16, torch.float32]
    assert (mm.unet_dtype(supported_dtypes=anima), mm.unet_dtype(supported_dtypes=lumina)) == (torch.float16, torch.bfloat16)
    if torch.backends.mps.is_available():
        q, k, v = (torch.randn(1, 8, 256, 40, device="mps") for _ in range(3))
        ref = torch.softmax(q @ k.transpose(-1, -2) * 40 ** -0.5, -1) @ v
        assert torch.allclose(F.scaled_dot_product_attention(q, k, v), ref, atol=1e-4)
    app = web.Application()
    app.add_routes(routes)

    async def run():
        async with TestClient(TestServer(app)) as client:
            low = await client.post("/vulkara/memory", json={"mode": "LOW_VRAM"})
            state = mm.vram_state
            bad = await client.post("/vulkara/memory", json={"mode": "NO_VRAM"})
            return low.status, state, bad.status, mm.vram_state

    assert asyncio.run(run()) == (200, mm.VRAMState.LOW_VRAM, 400, mm.VRAMState.LOW_VRAM)
    # the mode changes only after ComfyUI's worker has read the /free sent before (it unloads before the next prompt)
    assert reads[0] == {"free_memory": True} and reads[-1] == {}
