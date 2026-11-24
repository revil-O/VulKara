# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Helper models at a fixed commit, checked by their SHA-256.

The content filter, the filling model (LaMa), the colouring model (DDColor), the photo tools, the ControlNets, pose and
depth detection and the upscaling model come from third-party repositories. A later commit there could change what
they do (a content filter that lets everything pass), so every file is fetched at the commit the app was tested with
and its checksum is compared. Once a folder is complete and checked, it is used from the disk without asking Hugging
Face again. The pins of the helpers are in helper_pins.json (tools/pin_helpers.py writes it).
"""

import glob
import hashlib
import json
import os

MARK = ".vk-checked.json"
PINS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "helper_pins.json")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _checked(folder):
    try:
        with open(os.path.join(folder, MARK)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def pins(repo):
    """(revision, {remote file: sha256 or None}) of a helper repository; KeyError when it is not pinned."""
    with open(PINS_FILE) as f:
        entry = json.load(f)[repo]
    return entry["revision"], entry["files"]


def fetch(repo, revision, files, folder, rename=None, token=None, report=None):
    """The folder with files (remote name -> SHA-256, None for small text files that the commit fixes) of repo at
    revision; rename: remote name -> name in the folder. Raises when a file does not match its checksum; the file is
    removed then."""
    rename = rename or {}
    local = {name: os.path.join(folder, rename.get(name, name)) for name in files}
    os.makedirs(folder, exist_ok=True)
    done = _checked(folder)
    if done.get("revision") == revision and all(os.path.isfile(p) for p in local.values()):
        return folder
    from huggingface_hub import hf_hub_download
    for name, digest in files.items():
        path = local[name]
        present = os.path.isfile(path)
        if present and digest:
            if report:
                report("Checking %s (one-time)" % os.path.basename(path))
            present = _sha256(path) == digest
        if not present:
            got = hf_hub_download(repo, name, revision=revision, local_dir=folder, token=token)
            if os.path.abspath(got) != os.path.abspath(path):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                os.replace(got, path)
            if digest and _sha256(path) != digest:
                os.remove(path)
                raise RuntimeError("%s of %s does not match its checksum: it was removed" % (name, repo))
    with open(os.path.join(folder, MARK), "w") as f:
        json.dump({"repo": repo, "revision": revision}, f)
    return folder


# a few short network failures are tried again (github.com came and went for minutes on 2026-11-14), the pause
# growing each time; what was downloaded stays, the next try asks only for the rest (MEASUREMENTS D1, 2026-11-15)
TRIES, PAUSE = 5, 5


def resume_into(part, open_at, report=None, sleep=None):
    """Downloads into the file part, going on from its size: open_at(start) -> the response for the bytes from start
    (a Range request when start > 0). A server answering 200 instead of 206 sends the whole file, which then starts
    over; 416 means part already holds all of it. A broken connection or a 5xx answer is tried again TRIES times, the
    part kept (also for a later job); other HTTP errors go to the caller. report(percent) on the way. The caller
    checks the result (SHA-256): a part of another file can not pass."""
    import http.client
    import time
    import urllib.error
    sleep = sleep or time.sleep
    for attempt in range(TRIES):
        start = os.path.getsize(part) if os.path.exists(part) else 0
        try:
            with open_at(start) as r:
                if start and getattr(r, "status", 200) != 206:
                    start = 0  # no ranges here: the whole file comes again
                length = int(r.headers.get("Content-Length") or 0)
                total = start + length
                got = start
                with open(part, "ab" if start else "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        if report and total:
                            report(100.0 * got / total)
            if length and got < total:
                raise http.client.IncompleteRead(b"", total - got)
            return got
        except urllib.error.HTTPError as e:
            if e.code == 416 and start:
                return start
            if e.code < 500 or attempt == TRIES - 1:
                raise
        except (urllib.error.URLError, http.client.HTTPException, ConnectionError, TimeoutError):
            if attempt == TRIES - 1:
                raise
        sleep(PAUSE * (attempt + 1))


def fetch_urls(urls, files, folder, report=None):
    """Like fetch() for files published outside Hugging Face (GitHub releases): urls: name -> https URL, files:
    name -> SHA-256 (required here, there is no commit to pin). A file is downloaded to a .part file named after its
    checksum (a broken download goes on from there, resume_into), checked and renamed; a mismatch removes it and
    raises."""
    import urllib.request
    os.makedirs(folder, exist_ok=True)
    local = {name: os.path.join(folder, name) for name in files}
    done = _checked(folder)
    if done.get("urls") == urls and all(os.path.isfile(p) for p in local.values()):
        return folder
    for name, digest in files.items():
        if not digest:
            raise ValueError("%s has no checksum; files from a URL need one" % name)
        url = urls[name]
        if not url.startswith("https://"):
            raise ValueError("%s is not an https URL" % url)
        path = local[name]
        if os.path.isfile(path):
            if report:
                report("Checking %s (one-time)" % name)
            if _sha256(path) == digest:
                continue
            os.remove(path)
        if report:
            report("Downloading %s" % name)
        # the checksum in the name: a part of an older version of the file is never continued
        part = "%s.%s.part" % (path, digest[:12])
        for stale in glob.glob(glob.escape(path) + ".*part"):
            if stale != part:
                os.remove(stale)

        def open_at(start, url=url):
            headers = {"User-Agent": "VulKara", **({"Range": "bytes=%d-" % start} if start else {})}
            return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60)
        resume_into(part, open_at, report=report)
        if _sha256(part) != digest:
            os.remove(part)
            raise RuntimeError("%s does not match its checksum: it was removed" % name)
        os.replace(part, path)
    with open(os.path.join(folder, MARK), "w") as f:
        json.dump({"urls": urls}, f)
    return folder


def ready(repo, folder, rename=None):
    """Whether the folder holds the pinned, checked files already (nothing to read or download)."""
    revision, files = pins(repo)
    rename = rename or {}
    return (_checked(folder).get("revision") == revision
            and all(os.path.isfile(os.path.join(folder, rename.get(n, n))) for n in files))


def fetch_pinned(repo, folder, rename=None, token=None, report=None):
    """fetch() with the pins of helper_pins.json."""
    revision, files = pins(repo)
    return fetch(repo, revision, files, folder, rename=rename, token=token, report=report)
