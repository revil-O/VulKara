# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""RestoreFormer++ (wzhouxiff/RestoreFormerPlusPlus, Apache-2.0), the second face model of Restore, built from
spandrel's RestoreFormer parts.

It differs from RestoreFormer (v1, which spandrel loads by itself) in three points: 4 attention heads instead of 8, the
decoder also attends at 32 px (besides 16 px), and that second level takes the encoder's features of the same size
("block_4", kept before the encoder's last downsampling) as its keys."""
from spandrel.architectures.RestoreFormer import RestoreFormer
from spandrel.architectures.RestoreFormer.__arch.restoreformer_arch import MultiHeadDecoderTransformer


class RestoreFormerPP(RestoreFormer):
    def __init__(self):
        super().__init__(head_size=4)
        self.decoder = MultiHeadDecoderTransformer(ch=64, out_ch=3, ch_mult=(1, 2, 2, 4, 4, 8), num_res_blocks=2,
                                                   attn_resolutions=(16, 32), resolution=512, z_channels=256,
                                                   head_size=4)

    def encode(self, x):
        quant, diff, info, hs = super().encode(x)
        hs.setdefault("block_4_atten", hs["block_4"])
        return quant, diff, info, hs


def load(path, sha256):
    """The network with the release's weights. The file (a pickle) must still have the release's SHA-256 (it may have
    been swapped in the helpers folder since its download) and is read with spandrel's unpickler, which takes only
    tensors and ordered dicts, as CodeFormer's file is: also safe on the Intel build's PyTorch 2.2, where weights_only
    can be tricked by a crafted file (CVE-2025-32434)."""
    import hashlib
    import torch
    from spandrel.__helpers.unpickler import RestrictedUnpickle
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    if h.hexdigest() != sha256:
        raise ValueError("%s is not the file of the pinned release (its SHA-256 differs); delete it so that it is "
                         "downloaded again" % path)
    sd = torch.load(path, map_location="cpu", pickle_module=RestrictedUnpickle)
    sd = {k[len("vqvae."):]: v for k, v in sd.get("state_dict", sd).items() if k.startswith("vqvae.")}
    net = RestoreFormerPP()
    net.load_state_dict(sd, strict=True)  # every tensor of the release must find its place, and no layer stay empty
    return net.eval()
