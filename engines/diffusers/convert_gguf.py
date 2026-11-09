# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Converts a single-file transformer checkpoint to GGUF.

Used for weights the Apple GPU can not work with directly (FP8 checkpoints), and to
pre-quantize large models so that loading them never needs a 16 bit copy in RAM.

Works tensor by tensor in two passes (header first, then data), so memory use stays at
about one tensor regardless of the model size.
"""
import numpy as np

import registry

UNSUPPORTED_ON_MPS = ("F8_E4M3", "F8_E5M2", "F8_E4M3FNUZ", "F8_E5M2FNUZ")
PREFIXES = ("model.diffusion_model.", "diffusion_model.")


def safetensors_dtypes(path):
    return {v["dtype"] for k, v in registry.read_safetensors_json(path).items() if k != "__metadata__"}


def needs_conversion(path):
    return path.lower().endswith(".safetensors") and bool(safetensors_dtypes(path) & set(UNSUPPORTED_ON_MPS))


def _plan_tensor(shape, qtype_name):
    """Which GGML type a tensor gets: small and 1-D tensors (norms, biases) stay F32."""
    numel = int(np.prod(shape)) if shape else 1
    if len(shape) >= 2 and shape[-1] % 32 == 0 and numel >= 4096:
        return qtype_name
    return "F32"


def convert(src, dst, qtype="Q8_0", arch="flux", progress=None):
    """src: one safetensors file or a list of them (the shards of one model): every tensor header first, then the
    data tensor by tensor, so memory stays at about one tensor."""
    import gguf
    import torch
    from gguf import quants
    from safetensors import safe_open

    qtypes = {"Q8_0": gguf.GGMLQuantizationType.Q8_0, "Q4_0": gguf.GGMLQuantizationType.Q4_0,
              "F32": gguf.GGMLQuantizationType.F32}
    files = [src] if isinstance(src, str) else list(src)

    writer = gguf.GGUFWriter(dst, arch=arch)
    writer.add_quantization_version(gguf.GGML_QUANT_VERSION)
    writer.add_file_type(gguf.LlamaFileType.MOSTLY_Q8_0 if qtype == "Q8_0" else gguf.LlamaFileType.MOSTLY_Q4_0)

    plan = []
    for path in files:
        with safe_open(path, framework="pt", device="cpu") as f:
            for k in f.keys():
                name = k
                for p in PREFIXES:
                    if name.startswith(p):
                        name = name[len(p):]
                        break
                shape = list(f.get_slice(k).get_shape())
                # only weights: tables read directly (SD 3.5's pos_embed) stay whole
                t = _plan_tensor(shape, qtype) if name.endswith(".weight") else "F32"
                qt = qtypes[t]
                if t == "F32":
                    nbytes = int(np.prod(shape) if shape else 1) * 4
                    writer.add_tensor_info(name, shape, np.dtype(np.float32), nbytes, raw_dtype=qt)
                else:
                    block, type_size = gguf.GGML_QUANT_SIZES[qt]
                    byte_shape = shape[:-1] + [shape[-1] // block * type_size]
                    nbytes = int(np.prod(byte_shape))
                    writer.add_tensor_info(name, byte_shape, np.dtype(np.uint8), nbytes, raw_dtype=qt)
                plan.append((path, k, t, qt))

    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_ti_data_to_file()

    done = 0
    for path in files:
        with safe_open(path, framework="pt", device="cpu") as f:
            for p, k, t, qt in plan:
                if p != path:
                    continue
                data = f.get_tensor(k).to(torch.float32).numpy()
                if t != "F32":
                    data = quants.quantize(data, qt)
                writer.write_tensor_data(data)
                done += 1
                if progress and (done % 20 == 0 or done == len(plan)):
                    progress(int(100 * done / len(plan)))
    writer.close()
    return dst


if __name__ == "__main__":
    import sys
    convert(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "Q8_0",
            progress=lambda p: print("progress", p, flush=True))
