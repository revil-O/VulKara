# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Broken downloads go on where they stopped (pinned.resume_into): photo tools and helpers from a URL (fetch_urls) and
Civitai, against a local server that cuts the connection off, ignores ranges or answers 404."""
import hashlib
import http.server
import os
import threading
import urllib.error
import urllib.request

import pytest

import civitai
import pinned

DATA = bytes(range(256)) * 4000  # 1 MB


class Server:
    """Serves DATA; cut: bytes after which the next answers break off (one per entry), ranges: answers 206 to a Range."""

    def __init__(self):
        self.cut, self.ranges, self.seen, self.status = [], True, [], 200
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                rng = self.headers.get("Range")
                server.seen.append(rng)
                if server.status != 200:
                    self.send_error(server.status)
                    return
                start = int(rng[6:-1]) if rng and server.ranges else 0
                if start >= len(DATA):
                    self.send_error(416)
                    return
                body = DATA[start:]
                self.send_response(206 if start else 200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                cut = server.cut.pop(0) if server.cut else None
                self.wfile.write(body[:cut] if cut is not None else body)
                if cut is not None:
                    self.wfile.flush()
                    self.connection.close()

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d" % self.httpd.server_address[1]


@pytest.fixture
def server(monkeypatch):
    s = Server()
    # the code asks for https and Civitai; the requests go to the local server instead
    def local(req, **kw):
        req.full_url = s.url + "/" + req.full_url.rsplit("/", 1)[1]
        return urllib.request.build_opener().open(req, timeout=10)
    monkeypatch.setattr(urllib.request, "urlopen", local)
    monkeypatch.setattr(civitai._opener, "open", local)
    monkeypatch.setattr(pinned, "PAUSE", 0)
    yield s
    s.httpd.shutdown()


DIGEST = hashlib.sha256(DATA).hexdigest()


def test_a_broken_download_goes_on_from_where_it_stopped(server, tmp_path):
    server.cut = [300_000, 200_000]  # two breaks, then the rest
    seen = []
    folder = pinned.fetch_urls({"w.bin": "https://example.org/w.bin"}, {"w.bin": DIGEST}, str(tmp_path), report=seen.append)
    assert open(os.path.join(folder, "w.bin"), "rb").read() == DATA
    assert server.seen == [None, "bytes=300000-", "bytes=500000-"] and seen[-1] == 100.0
    assert sorted(os.listdir(tmp_path)) == [".vk-checked.json", "w.bin"]  # no part left


def test_a_server_without_ranges_starts_over(server, tmp_path):
    server.cut, server.ranges = [300_000], False
    pinned.fetch_urls({"w.bin": "https://example.org/w.bin"}, {"w.bin": DIGEST}, str(tmp_path))
    assert open(tmp_path / "w.bin", "rb").read() == DATA and server.seen == [None, "bytes=300000-"]


def test_the_part_stays_for_the_next_job_and_an_old_versions_part_goes(server, tmp_path):
    server.cut = [100_000] * pinned.TRIES  # every try breaks off at once: the job fails
    with pytest.raises(Exception):
        pinned.fetch_urls({"w.bin": "https://example.org/w.bin"}, {"w.bin": DIGEST}, str(tmp_path))
    part = tmp_path / ("w.bin.%s.part" % DIGEST[:12])
    assert part.stat().st_size == 100_000 * pinned.TRIES
    (tmp_path / "w.bin.000000000000.part").write_bytes(b"older version")
    server.seen.clear()
    pinned.fetch_urls({"w.bin": "https://example.org/w.bin"}, {"w.bin": DIGEST}, str(tmp_path))
    assert server.seen == ["bytes=%d-" % (100_000 * pinned.TRIES)]
    assert sorted(os.listdir(tmp_path)) == [".vk-checked.json", "w.bin"]


def test_a_whole_part_is_taken_as_it_is_and_a_404_is_not_tried_again(server, tmp_path):
    (tmp_path / ("w.bin.%s.part" % DIGEST[:12])).write_bytes(DATA)
    pinned.fetch_urls({"w.bin": "https://example.org/w.bin"}, {"w.bin": DIGEST}, str(tmp_path))  # 416: nothing left
    assert open(tmp_path / "w.bin", "rb").read() == DATA
    server.status, server.seen = 404, []
    with pytest.raises(urllib.error.HTTPError):
        pinned.fetch_urls({"x.bin": "https://example.org/x.bin"}, {"x.bin": DIGEST}, str(tmp_path / "x"))
    assert server.seen == [None]


def test_civitai_goes_on_with_a_known_checksum_and_starts_over_without_one(server, tmp_path):
    info = {"file_name": "m.safetensors", "download_url": "https://civitai.com/api/download/models/1",
            "sha256": DIGEST.upper(), "size_bytes": len(DATA)}
    server.cut = [100_000] * pinned.TRIES
    with pytest.raises(Exception):
        civitai.download(info, str(tmp_path / "a"))
    assert os.listdir(tmp_path / "a") == ["m.safetensors.%s.partial" % DIGEST[:12]]
    server.seen.clear()
    path = civitai.download(info, str(tmp_path / "a"), progress=lambda p: None)
    assert open(path, "rb").read() == DATA and server.seen == ["bytes=%d-" % (100_000 * pinned.TRIES)]
    assert os.listdir(tmp_path / "a") == ["m.safetensors"]
    # without a checksum a part could not be checked: it goes, and the next download starts over
    server.cut = [100_000] * pinned.TRIES
    with pytest.raises(Exception):
        civitai.download(dict(info, sha256=""), str(tmp_path / "b"))
    assert os.listdir(tmp_path / "b") == []


def test_a_stop_ends_the_download_and_the_next_job_goes_on(server, tmp_path, monkeypatch):
    monkeypatch.setattr(pinned, "CHUNK", 100_000)
    asked = []
    stop = lambda: asked.append(1) or len(asked) >= 3  # stop after the third chunk
    with pytest.raises(pinned.Stopped):
        pinned.fetch_urls({"w.bin": "https://example.org/w.bin"}, {"w.bin": DIGEST}, str(tmp_path), stop=stop)
    part = tmp_path / ("w.bin.%s.part" % DIGEST[:12])
    kept = part.stat().st_size
    assert 0 < kept < len(DATA) and not (tmp_path / "w.bin").exists()  # a part, not the whole file
    server.seen.clear()
    folder = pinned.fetch_urls({"w.bin": "https://example.org/w.bin"}, {"w.bin": DIGEST}, str(tmp_path))
    assert open(os.path.join(folder, "w.bin"), "rb").read() == DATA
    assert server.seen == ["bytes=%d-" % kept]


def test_a_stop_while_the_connection_breaks_off_ends_before_the_next_try(server, tmp_path):
    server.cut = [100_000] * pinned.TRIES  # every try breaks off
    stop = lambda: len(server.seen) >= 2  # asked for before the third try
    with pytest.raises(pinned.Stopped):
        pinned.fetch_urls({"w.bin": "https://example.org/w.bin"}, {"w.bin": DIGEST}, str(tmp_path), stop=stop)
    assert len(server.seen) == 2  # not all TRIES
