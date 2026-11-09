# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Masks of inpainting: grown so new and old parts blend, and the result put back into the original picture with a
soft edge. Pillow and numpy only, so the ComfyUI and MLX engines share them (Fibo 2.0's masked edits)."""


def grow_mask(mask, fraction=16):
    """The model also repaints a strip of the existing picture along the mask's edge (1/fraction
    of the size), so new and old parts blend instead of meeting at a seam."""
    from PIL import ImageFilter
    r = max(4, min(mask.size) // fraction)
    return mask.filter(ImageFilter.GaussianBlur(r)).point(lambda v: 255 if v > 8 else 0)


def blend_into(original, painted, mask, painted_part=None, fraction=48):
    """Only the masked area comes from the new picture (soft edge); the rest stays pixel-exact
    (the VAE round trip of the pipeline would change it slightly).

    mask: the grown mask the model painted (grow_mask with this fraction); painted_part: the part the user painted,
    which comes from the new picture whole."""
    from PIL import Image, ImageChops, ImageFilter
    original = original.convert("RGB")
    r = max(4, min(original.size) // fraction)
    grown = mask.convert("L").resize(original.size).point(lambda v: 255 if v > 127 else 0)
    painted = _match_edge(original, painted.convert("RGB").resize(original.size), grown, r)
    # a narrow soft edge inside the grown strip: a blur across the edge left 15-40 % of the old picture in the
    # painted part (a removed house showed through, MEASUREMENTS 7bf), a wide one faded wings reaching into the strip
    soft = grown.filter(ImageFilter.GaussianBlur(max(2, r // 4))).point(lambda v: max(0, 2 * v - 255))
    if painted_part is not None:
        soft = ImageChops.lighter(soft, painted_part.convert("L").resize(original.size).point(
            lambda v: 255 if v > 127 else 0))
    return Image.composite(painted, original, soft)


def _match_edge(original, painted, grown, r):
    """The painted picture without its tone offset against the original. The pipelines that are not trained for
    masks keep the old picture outside the mask and shift its tone inside: a lighter or darker disc around an added
    seagull (MEASUREMENTS 7bf). The offset is measured in a band along the grown mask's edge and filled smoothly
    inwards (push-pull, Gortler et al. 1996, in blocks of r/2 so it carries no detail), like seamless cloning."""
    import numpy as np
    from PIL import Image, ImageFilter
    box = grown.getbbox()
    if box is None:
        return painted
    # only the mask's box: a small mask in a large canvas
    whole, (original, painted, grown) = painted, (im.crop(box) for im in (original, painted, grown))
    g = np.asarray(grown) > 127
    inner = np.asarray(grown.filter(ImageFilter.GaussianBlur(max(2, r // 2)))) > 250
    o, p = np.asarray(original, np.float32), np.asarray(painted, np.float32)
    d = p - o
    # what the model drew into the band (a wing tip) is no tone offset
    w = (g & ~inner & (np.abs(d).max(2) < 48)).astype(np.float32)
    if not w.any():
        return whole

    def down(a, f):
        h, x = -(-a.shape[0] // f) * f, -(-a.shape[1] // f) * f
        a = np.pad(a, [(0, h - a.shape[0]), (0, x - a.shape[1])] + [(0, 0)] * (a.ndim - 2))
        return a.reshape(h // f, f, x // f, f, *a.shape[2:]).sum((1, 3))

    def up(a, f, shape):
        return np.stack([np.asarray(Image.fromarray(np.ascontiguousarray(a[..., i]), "F").resize(
            (a.shape[1] * f, a.shape[0] * f), Image.BILINEAR)) for i in range(3)], -1)[:shape[0], :shape[1]]

    def fill(s, n):
        known = n > 0
        v = s / np.maximum(n, 1e-6)[..., None]
        if known.all():
            return v
        if min(n.shape) < 2:
            return np.broadcast_to(s.sum((0, 1)) / n.sum(), s.shape)
        return np.where(known[..., None], v, up(fill(down(s, 2), down(n, 2)), 2, n.shape))

    f = max(1, r // 2)
    offset = up(fill(down(d * w[..., None], f), down(w, f)).astype(np.float32), f, g.shape)
    whole = whole.copy()
    whole.paste(Image.fromarray(np.clip(p - offset * g[..., None] + 0.5, 0, 255).astype(np.uint8)), box[:2])
    return whole


def grey_out(image, mask):
    """The picture with the masked part flat grey (128): how Fibo 2.0 was trained to see the part to repaint."""
    from PIL import Image
    grey = Image.new("RGB", image.size, (128, 128, 128))
    return Image.composite(grey, image.convert("RGB"), mask.convert("L").point(lambda v: 255 if v >= 128 else 0))
