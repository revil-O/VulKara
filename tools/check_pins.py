# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""The release gate for the runtimes' Python packages (tools/release.mjs runs it before every build, also with
--skip-checks):

  1. every engine requirement is pinned (`name==version`) and has a lock (constraints.txt), the two agree;
  2. the lock was accepted: the runtimes installed on this Mac — the ones the tests and test pictures ran on — hold
     exactly the locked set. A lock changed without installing and testing it here does not pass.

    python3 tools/check_pins.py          exit code 0 when everything is locked and accepted, 1 with a list
"""
import os
import re
import sys

from lock_runtimes import DEV_ONLY, ENGINE, RUNTIMES, SUFFIX, freeze, norm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?==([^\s;#]+)\s*(;[^#]*)?(#.*)?$")


def pins_of(path, findings, kind):
    pins = {}
    for no, raw in enumerate(open(path, encoding="utf-8").read().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = PIN.match(line)
        if not m:
            findings.append(f"{os.path.relpath(path, ROOT)}:{no}: not pinned to one version ({kind}): {line}")
            continue
        pins[norm(m.group(1))] = m.group(3)
    return pins


def check():
    findings = []
    for (rt, engine), suffix in [(e, s) for e in ENGINE.items() for s in ("", "-x64")]:
        folder = os.path.join(ROOT, "engines", engine)
        req, lock = os.path.join(folder, f"requirements{suffix}.txt"), os.path.join(folder, f"constraints{suffix}.txt")
        rel = os.path.relpath(folder, ROOT)
        if suffix and not os.path.exists(req):
            continue  # no Intel set: the runtime is not offered on Intel Macs
        if not os.path.exists(lock):
            findings.append(f"{rel}: no constraints{suffix}.txt (python3 tools/lock_runtimes.py {rt})")
            continue
        direct = pins_of(req, findings, "requirement")
        locked = pins_of(lock, findings, "lock")
        for name, version in direct.items():
            if locked.get(name) != version:
                findings.append(f"{rel}: {name}=={version} in requirements{suffix}.txt, {locked.get(name, 'missing')} in the lock")
        if suffix != SUFFIX:
            continue  # the other processor's set is accepted on that Mac (tools/lock_runtimes.py there)
        installed = freeze(rt)
        if installed is None:
            findings.append(f"{rel}: the {rt} runtime is not installed here, so its lock is not verified (install it in "
                            f"Settings → Runtimes, test it, then build)")
            continue
        have = {k: v for k, (_, v) in installed.items() if k not in DEV_ONLY}
        for name in sorted(set(have) | set(locked)):
            if have.get(name) != locked.get(name):
                findings.append(f"{rel}: {name} locked {locked.get(name, '-')}, installed {have.get(name, '-')} "
                                f"(accept the update and run tools/lock_runtimes.py, or update the runtime to the lock)")
    return findings


if __name__ == "__main__":
    print(f"runtimes: {RUNTIMES}")
    found = check()
    for line in found:
        print(line)
    print("locked and accepted" if not found else "%d findings" % len(found), file=sys.stderr)
    sys.exit(1 if found else 0)
