# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
import torch

import streaming


class Toy(torch.nn.Module):
    """a denoiser in miniature: a resident input layer, two lists of blocks, a resident output layer"""

    def __init__(self):
        super().__init__()
        self.proj_in = torch.nn.Linear(8, 16)
        self.transformer_blocks = torch.nn.ModuleList([torch.nn.Linear(16, 16) for _ in range(3)])
        self.single_transformer_blocks = torch.nn.ModuleList([torch.nn.Linear(16, 16) for _ in range(2)])
        self.proj_out = torch.nn.Linear(16, 4)

    def forward(self, x):
        x = self.proj_in(x)
        for b in list(self.transformer_blocks) + list(self.single_transformer_blocks):
            x = torch.tanh(b(x))
        return self.proj_out(x)


def test_streamed_blocks_give_the_same_result_and_stay_off_memory(tmp_path):
    torch.manual_seed(0)
    model, x = Toy(), torch.randn(2, 8)
    expected = model(x)
    n, kept = streaming.enable(model, torch.device("cpu"), torch.float32, str(tmp_path))
    assert (n, kept) == (5, 0) and len(list(tmp_path.glob("*.safetensors"))) == 5
    assert model.transformer_blocks[0].weight.device.type == "meta"  # not resident
    for _ in range(2):  # the second pass reads the blocks again (prefetch wraps around)
        assert torch.allclose(model(x), expected, atol=1e-6)
    assert model.single_transformer_blocks[1].weight.device.type == "meta"


def test_on_mps_at_most_two_streamed_blocks_wait_on_the_gpu(tmp_path, monkeypatch):
    if not torch.backends.mps.is_available():
        return
    queued = []  # events not yet waited for, at each load

    class Event:
        def record(self):
            queued.append(self)

        def synchronize(self):
            queued.remove(self)
    monkeypatch.setattr(torch.mps, "Event", Event)
    torch.manual_seed(0)
    model, x = Toy(), torch.randn(2, 8)
    expected = model(x)
    streaming.enable(model, torch.device("mps"), torch.float32, str(tmp_path))
    seen = []
    for b in list(model.transformer_blocks) + list(model.single_transformer_blocks):
        b.register_forward_pre_hook(lambda m, a: seen.append(len(queued)))
    out = model(x.to("mps"))
    assert torch.allclose(out.cpu(), expected, atol=1e-5)
    assert seen and max(seen) <= streaming.QUEUED - 1


def test_loras_are_merged_while_streaming_and_removed_again(tmp_path):
    torch.manual_seed(0)
    model, x = Toy(), torch.randn(2, 8)
    reference = Toy()
    reference.load_state_dict(model.state_dict())
    plain = model(x)
    A, B = torch.randn(2, 16), torch.randn(16, 2)
    Ai, Bi = torch.randn(2, 8), torch.randn(16, 2)
    with torch.no_grad():  # the same LoRA applied the classic way
        reference.transformer_blocks[1].weight += 0.5 * (B @ A)
        reference.proj_in.weight += 0.5 * (Bi @ Ai)
    streaming.enable(model, torch.device("cpu"), torch.float32, str(tmp_path))
    matched = streaming.set_loras(model, [("transformer_blocks.1", A, B, 0.5), ("proj_in", Ai, Bi, 0.5),
                                          ("not_there", A, B, 1.0)])
    assert matched == 2
    assert torch.allclose(model(x), reference(x), atol=1e-5)
    streaming.set_loras(model, [])
    assert torch.allclose(model(x), plain, atol=1e-5)


def test_kept_blocks_stay_resident_spread_over_the_model_and_give_the_same_result(tmp_path):
    torch.manual_seed(0)
    model, x = Toy(), torch.randn(2, 8)
    expected = model(x)
    n, kept = streaming.enable(model, torch.device("cpu"), torch.float32, str(tmp_path), resident_share=0.4)
    assert (n, kept) == (3, 2)
    resident = [b.weight.device.type != "meta" for b in list(model.transformer_blocks) + list(model.single_transformer_blocks)]
    assert resident == [False, False, True, False, True]  # spread over the model, not the first ones
    for _ in range(3):
        assert torch.allclose(model(x), expected, atol=1e-6)


def test_loras_reach_kept_blocks_too(tmp_path):
    torch.manual_seed(0)
    model, x = Toy(), torch.randn(2, 8)
    reference = Toy()
    reference.load_state_dict(model.state_dict())
    plain = model(x)
    A, B = torch.randn(2, 16), torch.randn(16, 2)
    with torch.no_grad():
        reference.transformer_blocks[1].weight += 0.5 * (B @ A)
        reference.transformer_blocks[2].weight += 0.5 * (B @ A)
    streaming.enable(model, torch.device("cpu"), torch.float32, str(tmp_path), resident_share=0.4)
    assert streaming.set_loras(model, [("transformer_blocks.1", A, B, 0.5), ("transformer_blocks.2", A, B, 0.5)]) == 2
    assert torch.allclose(model(x), reference(x), atol=1e-5)
    streaming.set_loras(model, [])
    assert torch.allclose(model(x), plain, atol=1e-5)


def test_resident_blocks_are_spread_and_stay_within_the_share():
    sizes = [10] * 10
    assert streaming.resident_blocks(sizes, 0) == set()
    assert streaming.resident_blocks(sizes, 0.5) == {1, 3, 5, 7, 9}
    assert len(streaming.resident_blocks(sizes, 0.34)) == 3
    assert streaming.resident_blocks(sizes, 1.0) == set(range(10))


def test_kept_blocks_make_room_and_come_back_with_their_loras(tmp_path):
    torch.manual_seed(0)
    model, x = Toy(), torch.randn(2, 8)
    reference = Toy()
    reference.load_state_dict(model.state_dict())
    A, B = torch.randn(2, 16), torch.randn(16, 2)
    with torch.no_grad():
        reference.transformer_blocks[2].weight += 0.5 * (B @ A)
    streaming.enable(model, torch.device("cpu"), torch.float32, str(tmp_path), resident_share=0.4)
    streaming.set_loras(model, [("transformer_blocks.2", A, B, 0.5)])
    streaming.release_kept(model)
    assert model.transformer_blocks[2].weight.device.type == "meta"
    streaming.restore_kept(model)
    assert model.transformer_blocks[2].weight.device.type == "cpu"
    assert torch.allclose(model(x), reference(x), atol=1e-5)


def _q8_0(w):
    """w (out x in, in a multiple of 32) packed as GGUF Q8_0: per 32 values a float16 scale and 32 int8"""
    import numpy as np
    from diffusers.quantizers.gguf.utils import GGUFParameter
    blocks = w.detach().float().numpy().reshape(-1, 32)
    d = np.abs(blocks).max(axis=1, keepdims=True) / 127
    q = np.round(blocks / np.where(d == 0, 1, d)).astype(np.int8)
    raw = np.concatenate([d.astype(np.float16).view(np.uint8), q.view(np.uint8)], axis=1)
    return GGUFParameter(torch.from_numpy(raw.reshape(w.shape[0], -1).copy()), quant_type=8)


class GgufToy(torch.nn.Module):
    """Toy with its block layers (and the output layer) in GGUF Q8_0, as diffusers loads a GGUF file"""

    def __init__(self, plain):
        super().__init__()
        from diffusers.quantizers.gguf.utils import GGUFLinear
        self.proj_in = torch.nn.Linear(32, 32)
        self.transformer_blocks = torch.nn.ModuleList()
        for b in plain.transformer_blocks:
            g = GGUFLinear(32, 32, bias=True, compute_dtype=torch.float32)
            g.weight, g.bias = _q8_0(b.weight), torch.nn.Parameter(b.bias.detach().clone())
            self.transformer_blocks.append(g)
        self.proj_out = GGUFLinear(32, 4, bias=False, compute_dtype=torch.float32)
        self.proj_out.weight = _q8_0(plain.proj_out.weight)
        self.proj_in.load_state_dict(plain.proj_in.state_dict())


class PlainToy(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.proj_in = torch.nn.Linear(32, 32)
        self.transformer_blocks = torch.nn.ModuleList([torch.nn.Linear(32, 32) for _ in range(3)])
        self.proj_out = torch.nn.Linear(32, 4, bias=False)

    def forward(self, x):
        x = self.proj_in(x)
        for b in self.transformer_blocks:
            x = torch.tanh(b(x))
        return self.proj_out(x)


def test_a_gguf_model_is_unpacked_once_and_then_streams_without_its_file(tmp_path):
    from diffusers.quantizers.gguf.utils import dequantize_gguf_tensor
    torch.manual_seed(0)
    plain, x = PlainToy(), torch.randn(2, 32)
    packed = GgufToy(plain)
    # the reference: the plain model with the GGUF weights as they unpack (Q8_0 rounds a little)
    for b, g in zip(plain.transformer_blocks, packed.transformer_blocks):
        b.weight.data = dequantize_gguf_tensor(g.weight).float()
    plain.proj_out.weight.data = dequantize_gguf_tensor(packed.proj_out.weight).float()
    expected = plain(x)

    def empty():
        with torch.device("meta"):
            return PlainToy()

    loads = []

    def load():
        loads.append(1)
        return GgufToy(plain)

    for _ in range(2):  # the second time only the cache is read
        model = streaming.unpack_gguf(load, empty, str(tmp_path), torch.float32, "sha-1")
        assert model.transformer_blocks[0].weight.device.type == "meta" and model.proj_out.weight.device.type == "cpu"
        n, kept = streaming.enable(model, torch.device("cpu"), torch.float32, str(tmp_path))
        assert (n, kept) == (3, 0)
        assert torch.allclose(model(x), expected, atol=1e-5)
    assert len(loads) == 1
    streaming.unpack_gguf(load, empty, str(tmp_path), torch.float32, "sha-2")  # another file: unpacked anew
    assert len(loads) == 2
