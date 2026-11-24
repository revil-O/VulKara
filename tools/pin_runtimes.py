# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Pins of the runtime installs (src/main/runtimes.ts): the SHA-256 of the uv archives (compared with the ones
published with the release) and the content hashes of the ComfyUI, ComfyUI-GGUF and ltx-2-mlx archives.
Content hash = sha256 over sorted lines "<relative posix path>\\0<sha256 of the file>\\n" of all regular files
(symlinks: "<path>\\0link:<target>\\n"), the archive's single top folder stripped. Same as treeHash in src/main/archive_hash.ts."""
import hashlib
import os
import subprocess
import sys
import urllib.request

# usage: python3 -I tools/pin_runtimes.py <empty folder> <uv version> <ComfyUI release> <ComfyUI-GGUF commit> <ltx-2-mlx commit>
WORK, UV, COMFY, GGUF, LTX = sys.argv[1:6]


def get(url, to):
    with urllib.request.urlopen(url, timeout=120) as r, open(to, "wb") as f:
        f.write(r.read())


def file_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def tree_hash(root):
    lines = []
    for d, dirs, files in os.walk(root):
        for name in dirs + files:
            p = os.path.join(d, name)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            if os.path.islink(p):
                lines.append("%s\0link:%s\n" % (rel, os.readlink(p)))
            elif os.path.isfile(p) and name in files:
                lines.append("%s\0%s\n" % (rel, file_sha(p)))
    lines.sort()
    return hashlib.sha256("".join(lines).encode()).hexdigest(), len(lines)


for arch in ("aarch64", "x86_64"):
    url = "https://github.com/astral-sh/uv/releases/download/%s/uv-%s-apple-darwin.tar.gz" % (UV, arch)
    with urllib.request.urlopen(url + ".sha256", timeout=60) as r:
        published = r.read().decode().split()[0]
    to = os.path.join(WORK, "uv-%s.tar.gz" % arch)
    get(url, to)
    print("uv", arch, published, "match" if file_sha(to) == published else "MISMATCH")

for name, url in [("comfyui", "https://github.com/comfyanonymous/ComfyUI/archive/refs/tags/v%s.zip" % COMFY),
                  ("gguf", "https://github.com/city96/ComfyUI-GGUF/archive/%s.zip" % GGUF),
                  ("ltx-2-mlx", "https://github.com/dgrauet/ltx-2-mlx/archive/%s.zip" % LTX)]:
    z = os.path.join(WORK, name + ".zip")
    get(url, z)
    out = os.path.join(WORK, name)
    subprocess.run(["ditto", "-x", "-k", z, out], check=True)
    inner = [n for n in os.listdir(out) if not n.startswith(".")][0]
    print(name, *tree_hash(os.path.join(out, inner)), "zip", file_sha(z))
