# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""ComfyUI engine: runs model types only ComfyUI supports (e.g. Anima, Wan video) from their original files.

Speaks the same stdin/stdout protocol as the other engines (../diffusers/protocol.py) and reads
the same model.json manifests. ComfyUI runs as a child process on 127.0.0.1 (a free port, its web
interface is not opened); jobs become workflows (workflows.py) sent to its HTTP API, progress comes
over its websocket. Model files stay where they are: they are linked into ComfyUI's model folders
under unique names.
"""
import asyncio
import json
import os
import random
import shutil
import signal
import socket
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "diffusers"))

import memory  # noqa: E402
import protocol  # noqa: E402
import paths  # noqa: E402
import registry  # noqa: E402
import workflows  # noqa: E402

MANIFEST = "model.json"
LORA_MANIFEST = "lora.json"
IMAGES_DIR = paths.images_dir()
# the runtime folder (<runtimes>/comfyui): ComfyUI/ next to venv/
RUNTIME_DIR = Path(os.environ.get("VK_COMFY_RUNTIME") or Path(sys.executable).parents[2])  # venv/bin/python
COMFY_DIR = Path(os.environ.get("VK_COMFYUI_DIR") or RUNTIME_DIR / "ComfyUI")
WORK = RUNTIME_DIR / "work"
FOLDERS = ("diffusion_models", "text_encoders", "vae", "loras", "checkpoints", "upscale_models")
# the upscaling model: Real-ESRGAN x4plus (BSD-3-Clause), downloaded on first use
UPSCALER = {"repo": "Comfy-Org/Real-ESRGAN_repackaged", "file": "RealESRGAN_x4plus.safetensors"}
# larger pictures would need tens of GB at four times the size: they are made smaller to this first
UPSCALE_MAX_SIDE = 2048
UPSCALE_MAX_PIXELS = 50_000_000  # the largest picture taken at all (about 8K × 6K)



class StopRequested(Exception):
    pass


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _link(src, folder, name):
    """A link to src under name in one of ComfyUI's model folders (replaced when it points elsewhere)."""
    dst = WORK / "models" / folder / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    src = os.path.realpath(src)
    if dst.is_symlink() or dst.exists():
        if os.path.realpath(dst) == src:
            return name
        dst.unlink()
    os.symlink(src, dst)
    return name


def mark_video(path, model):
    """AI marking in the video's metadata (pictures are marked by the content filter, content_check.py)."""
    tmp = path + ".marking.mp4"
    try:
        import av
        notice = "AI generated with VulKara" + (" (model: %s)" % model if model else "")
        with av.open(path) as src, av.open(tmp, "w", format="mp4") as dst:
            dst.metadata.update({"comment": notice, "description": notice, "encoder": "VulKara"})
            streams = {s.index: dst.add_stream_from_template(s) for s in src.streams}
            for packet in src.demux():
                if packet.dts is None:
                    continue
                packet.stream = streams[packet.stream.index]
                dst.mux(packet)
        os.replace(tmp, path)
    except Exception as e:
        Path(tmp).unlink(missing_ok=True)
        protocol.log("[comfy] could not mark the video: %s" % e)


def _safe(name):
    """A file name without path separators or other characters ComfyUI's folders should not see."""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in name)


def _copy_input(source):
    """A copy of a picture in ComfyUI's input folder under a unique name; returns that name. A picture with a colour
    profile other than sRGB (Display P3, HDR) is converted, as ComfyUI reads the values without their profile."""
    import colour
    from PIL import Image
    with Image.open(source) as im:
        name = colour.profile_name(im)
        if name and "srgb" not in name.lower():
            im.load()
            out = "pf_input_%s.png" % uuid.uuid4().hex[:8]
            colour.to_srgb(im).save(WORK / "input" / out)
            return out
    name = "pf_input_%s%s" % (uuid.uuid4().hex[:8], os.path.splitext(source)[1] or ".png")
    shutil.copy(source, WORK / "input" / name)
    return name


# the custom node that locks ComfyUI's server with a key only this engine knows (custom_nodes/vulkara_guard) and the
# one that switches its memory mode (custom_nodes/vulkara_memory)
GUARD_NODES = os.path.join(HERE, "custom_nodes")
GUARD_HEADER = "X-VK-Token"


def bit_sizes(model_dir, m, mode):
    """The bit size of the model's own files (benchmarks): its GGUF type or 16 bit / FP8, and whether LOW_VRAM streams
    the diffusion model from its file."""
    out = []
    for part, rel in m["files"].items():
        if part.startswith("diffusion_model") or part == "text_encoder":
            label = registry.file_precision(rel if os.path.isabs(rel) else os.path.join(model_dir, rel))
            if part.startswith("diffusion_model") and label == "8 bit (FP8)":
                label = "16 bit (from FP8)"  # MPS cannot compute FP8: vulkara_memory keeps it in 16 bit
            if part.startswith("diffusion_model") and mode == "LOW_VRAM":
                label += ", streamed from the SSD"
            out.append(("transformer" if part == "diffusion_model" else part, label))
    return out


def memory_mode(m, files, ram_gb):
    """ComfyUI's memory mode for a model (m: its model.json): LOW_VRAM when SHARED would not hold it. In SHARED ComfyUI
    drops the text encoder once the prompt is encoded when less than the memory kept free is left (--cache-ram), so it
    is counted staged (Pony V7 Q8_0 on 16 GB: SHARED, 10.6 GB, docs/MEASUREMENTS.md 7ae). Only a GGUF model streams
    from its file; Settings → ComfyUI streaming off (VK_COMFY_STREAMING=off) keeps SHARED."""
    if os.environ.get("VK_COMFY_STREAMING", "on").strip().lower() in ("off", "0"):
        return "SHARED"
    if not str(files.get("diffusion_model", "")).lower().endswith(".gguf"):
        return "SHARED"
    return "SHARED" if shared_plan(m, ram_gb)["fits"] else "LOW_VRAM"


def shared_plan(m, ram_gb):
    """The memory plan of a model held whole in memory (SHARED), its text encoder loaded only while encoding (not
    measured for video: Wan 2.2 14B has two experts the plan counts as one, so it keeps the text encoder counted)."""
    spec = registry.ARCHS[m["arch"]]
    return memory.plan(m.get("components") or spec["fallback_params"], spec["denoiser"], spec["family"], ram_gb,
                       quant="none", allow_staging=spec.get("kind") != "video")


class ComfyServer:
    def __init__(self):
        self.proc = None
        self.port = None
        self.token = ""
        self.mode = "SHARED"  # ComfyUI's own on the Mac

    @property
    def headers(self):
        """What every request to ComfyUI carries: the key of this start."""
        return {GUARD_HEADER: self.token}

    def _open(self, path, data=None, timeout=30, key=True):
        req = urllib.request.Request(self.url + path, data=None if data is None else json.dumps(data).encode(),
                                     headers={"Content-Type": "application/json", **(self.headers if key else {})},
                                     method="GET" if data is None else "POST")
        return urllib.request.urlopen(req, timeout=timeout)

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def ensure(self, state):
        if self.proc and self.proc.poll() is None:
            return
        if not (COMFY_DIR / "main.py").is_file():
            raise RuntimeError("ComfyUI is not installed: Settings → Runtimes → ComfyUI")
        state("Starting ComfyUI")
        for d in FOLDERS:
            (WORK / "models" / d).mkdir(parents=True, exist_ok=True)
        for d in ("output", "temp", "input", "user"):
            (WORK / d).mkdir(parents=True, exist_ok=True)
        cfg = WORK / "extra_model_paths.yaml"
        cfg.write_text("vulkara:\n    base_path: %s\n" % (WORK / "models") +
                       "".join("    %s: %s\n" % (d, d) for d in FOLDERS) +
                       # the app's own custom node (the lock), from the app itself, not from the runtime folder
                       "vulkara_nodes:\n    custom_nodes: %s\n" % GUARD_NODES)
        import secrets
        self.token = secrets.token_urlsafe(32)
        self.port = _free_port()
        self.mode = "SHARED"
        # only on the loopback interface; API nodes (paid online services) are not loaded; attention: vulkara_memory;
        # --cache-ram: ComfyUI drops cached node outputs (the text encoder once the prompt is encoded) when less than
        # the memory kept free is left, not only below its own 10 % (MEASUREMENTS 7ae)
        ram = memory.total_ram_gb()
        with open(WORK / "comfyui.log", "w") as log:
            self.proc = subprocess.Popen(
                [sys.executable, "main.py", "--listen", "127.0.0.1", "--port", str(self.port), "--disable-auto-launch",
                 "--disable-api-nodes", "--disable-metadata", "--disable-all-custom-nodes", "--use-pytorch-cross-attention",
                 "--whitelist-custom-nodes", "ComfyUI-GGUF", "vulkara_guard", "vulkara_memory",
                 "--cache-ram", "%.1f" % min(ram - memory.budget_gb(ram), ram / 2),
                 "--extra-model-paths-config", str(cfg),
                 "--output-directory", str(WORK / "output"), "--temp-directory", str(WORK / "temp"),
                 "--input-directory", str(WORK / "input"), "--user-directory", str(WORK / "user")],
                cwd=str(COMFY_DIR), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                env=dict(os.environ, HF_HUB_OFFLINE="1", DO_NOT_TRACK="1", VK_COMFY_TOKEN=self.token))
        t0 = time.time()
        while time.time() - t0 < 240:
            if self.proc.poll() is not None:
                raise RuntimeError("ComfyUI stopped while starting (see %s)" % (WORK / "comfyui.log"))
            try:
                self._open("/system_stats", timeout=2).read()
            except Exception:
                time.sleep(1)
                continue
            self._check_locked()
            protocol.log("[comfy] ComfyUI ready on port %d (locked with a key)" % self.port)
            return
        self.stop()
        raise RuntimeError("ComfyUI did not start (see %s)" % (WORK / "comfyui.log"))

    def _check_locked(self):
        """A request without the key must be refused; a ComfyUI that answers it (the lock did not load) is stopped."""
        try:
            self._open("/system_stats", timeout=5, key=False).read()
        except urllib.error.HTTPError as e:
            if e.code == 403:
                return
        except Exception:
            pass
        self.stop()
        raise RuntimeError("ComfyUI could not be locked with a key and was stopped (see %s)" % (WORK / "comfyui.log"))

    def post(self, path, data):
        with self._open(path, data) as r:
            body = r.read()
        return json.loads(body) if body else {}

    def set_mode(self, mode):
        """ComfyUI's memory mode (vulkara_memory); the loaded models are freed first, they were loaded for the other."""
        if mode == self.mode:
            return
        self.free()
        self.post("/vulkara/memory", {"mode": mode})
        self.mode = mode
        protocol.log("[comfy] memory mode %s" % mode)

    def free(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.post("/free", {"unload_models": True, "free_memory": True})
            except Exception as e:
                protocol.log("[comfy] free: %s" % e)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self.proc = None
        self.mode = "SHARED"


class ComfyEngine:
    def __init__(self, reader=None):
        self.reader = reader
        self.server = ComfyServer()
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    def _state(self, state):
        protocol.progress(-1)
        protocol.status(state)
        if self.reader is not None and self.reader.stop_requested():
            raise StopRequested()

    def _model_files(self, model_dir, m):
        """The model's files linked into ComfyUI's folders, named after the model (unique).
        Parts: diffusion_model(_low), text_encoder, vae, lora_* (a model's own LoRAs, e.g. distillation)."""
        out = {}
        for part, rel in m["files"].items():
            folder = ("diffusion_models" if part.startswith("diffusion_model") else "loras" if part.startswith("lora_")
                      else "text_encoders" if part == "text_encoder" else "vae" if part == "vae" else None)
            if folder is None:
                continue
            path = rel if os.path.isabs(rel) else os.path.join(model_dir, rel)
            if not os.path.exists(path):
                raise FileNotFoundError("%s: the file %s is missing (moved, or its disk is not connected)" % (m["name"], rel))
            out[part] = _link(path, folder, _safe("%s__%s%s" % (m["name"], part, os.path.splitext(path)[1] or ".safetensors")))
        return out

    def _loras(self, entries, m):
        """The job's LoRAs as (file name in ComfyUI's folder, strength) and their trigger words; refused when
        one does not fit the model (m: its model.json): another family, another size (Wan 5B / 14B), or a
        model that takes no LoRAs yet (Wan 2.2 14B's two-stage workflow)."""
        out, words = [], []
        for e in entries or []:
            if not e or not e.get("path"):
                continue
            with open(os.path.join(e["path"], LORA_MANIFEST)) as f:
                lm = json.load(f)
            problem = registry.lora_mismatch(lm, m)
            if problem:
                raise ValueError(problem)
            folder = os.path.abspath(e["path"])
            file = os.path.normpath(os.path.join(folder, lm["file"]))
            if os.path.dirname(file) != folder:
                raise ValueError("The LoRA %s names a file outside its folder" % lm.get("name", "?"))
            name = _link(file, "loras", _safe(lm["name"]) + ".safetensors")
            out.append((name, float(e.get("scale", 1.0))))
            words += lm.get("trigger_words") or []
        return out, words

    def _upscaler(self):
        """The file of the upscaling model in ComfyUI's folder, downloaded on first use."""
        folder = paths.helpers_dir("upscalers")
        target = folder / UPSCALER["file"]
        # at its pinned commit and checked (pinned.py); a copy from before the pins is checked once
        import pinned
        if not target.is_file():
            self._state("Downloading the upscaling model (64 MB)")
        pinned.fetch_pinned(UPSCALER["repo"], str(folder))
        return _link(str(target), "upscale_models", UPSCALER["file"])

    def upscale(self, d):
        """Enlarges d["input_image"] to d["upscale"] (1.1 to 4) times its size."""
        source = d.get("input_image")
        if not source or not os.path.isfile(source):
            raise ValueError("Choose a picture to enlarge")
        from PIL import Image
        factor = min(4.0, max(1.1, round(float(d.get("upscale") or 4), 2)))
        (WORK / "input").mkdir(parents=True, exist_ok=True)  # also before ComfyUI has run once
        with Image.open(source) as im:
            size = im.size
            if size[0] * size[1] > UPSCALE_MAX_PIXELS:
                raise ValueError("This picture is too large to enlarge: at most %d megapixels" % (UPSCALE_MAX_PIXELS // 1_000_000))
            small, target = workflows.upscale_plan(size, factor, UPSCALE_MAX_SIDE)
            if small != size:
                # made smaller first; the result is still measured on the picture given
                input_name = "pf_input_%s.png" % uuid.uuid4().hex[:8]
                import colour
                colour.to_srgb(im).resize(small, Image.LANCZOS).save(WORK / "input" / input_name)
                protocol.note("The picture (%d × %d) was made smaller to %d × %d first (Upscale takes up to %d pixels on "
                              "the longer side); the result is %d × %d." % (size[0], size[1], small[0], small[1],
                                                                          UPSCALE_MAX_SIDE, target[0], target[1]))
            else:
                input_name = _copy_input(source)
        try:
            self.server.ensure(self._state)
            model_name = self._upscaler()
            self._state("Enlarging")
            t0 = time.time()
            # the model gives four times what it got; anything else is scaled to the exact size
            exact = None if target == (small[0] * 4, small[1] * 4) else target
            out = asyncio.run(self._run(workflows.build_upscale(input_name, model_name, size=exact), 1))
            stem = "".join(filter(str.isalnum, os.path.splitext(os.path.basename(source))[0][:30])) or "picture"
            path = IMAGES_DIR / ("%s_x%s_%s.png" % (stem, ("%g" % factor).replace(".", "_"), uuid.uuid4().hex[:12]))
            shutil.move(out, path)
            protocol.log("[comfy] enlarged in %.1fs" % (time.time() - t0))
            protocol.result(str(path))
            return [str(path)]
        finally:
            (WORK / "input" / input_name).unlink(missing_ok=True)

    def generate(self, d):
        if d.get("upscale"):
            return self.upscale(d)
        model_dir = d.get("model_dir")
        if not model_dir or not os.path.isfile(os.path.join(model_dir, MANIFEST)):
            raise ValueError("Model not found, please re-import it")
        with open(os.path.join(model_dir, MANIFEST)) as f:
            m = json.load(f)
        spec = registry.ARCHS[m["arch"]]
        comfy = spec.get("comfy") or {}
        defaults = m.get("defaults") or spec["defaults"]
        self.server.ensure(self._state)
        files = self._model_files(model_dir, m)
        mode = memory_mode(m, files, memory.total_ram_gb())
        self.server.set_mode(mode)
        protocol.precision(bit_sizes(model_dir, m, mode))
        loras, words = self._loras(d.get("loras"), m)

        prompt = d.get("prompt") or ""
        for w in words:
            if w and w.lower() not in prompt.lower():
                prompt = w + ", " + prompt
        # a system prompt the model expects before the prompt (Lumina 2); not in the file names of the results
        prefix = defaults.get("prompt_prefix") or ""
        multiple = spec.get("size_multiple", 16)
        job = {
            # the negative prompt the model card recommends when the job has none
            "prompt": prefix + prompt, "negative_prompt": d.get("negative_prompt") or defaults.get("negative_prompt", ""),
            "width": int(d.get("width") or defaults.get("width", 1024)) // multiple * multiple,
            "height": int(d.get("height") or defaults.get("height", 1024)) // multiple * multiple,
            "steps": int(d.get("num_steps") or defaults["num_steps"]),
            "cfg": float(d["guidance_scale"]) if d.get("guidance_scale") is not None else defaults["guidance_scale"],
            "sampler": d.get("sampler"), "sigma_schedule": d.get("sigma_schedule"),
        }
        seed = d.get("seed")
        seed = int(seed) if seed not in (None, "") and int(seed) >= 0 else random.randint(0, 2 ** 31 - 1)
        video = spec.get("kind") == "video"
        if video:
            job["fps"] = int(d.get("fps") or defaults.get("fps", 24))
            job["frames"] = workflows.video_frames(d["video_seconds"], job["fps"]) if d.get("video_seconds") \
                else int(defaults.get("num_frames", 49))
        elif d.get("input_image"):
            job["strength"] = float(d.get("strength", 0.6))  # how much of the picture changes
        # a video's start picture is used as it is, a picture to change is scaled to the size
        input_name = _copy_input(d["input_image"]) if d.get("input_image") else None
        # what the benchmark shows beside the engine's peak; a streamed model or a video has no plan of its own
        protocol.planned(memory.peak_at(shared_plan(m, memory.total_ram_gb()), job["width"], job["height"])
                         if mode == "SHARED" and not video else None)

        saved = []
        try:
            for i in range(int(d.get("count") or 1)):
                self._state("Generating")
                t0 = time.time()
                build = workflows.build_video if video else workflows.build
                graph = build(dict(job, seed=seed + i), files, comfy, loras, input_image=input_name)
                out = asyncio.run(self._run(graph, job["steps"], quiet=d.get("_quiet", False)))
                stem = "".join(filter(str.isalnum, prompt[:30])) or ("video" if video else "image")
                path = IMAGES_DIR / ("%s_%s%s" % (stem, uuid.uuid4().hex[:12], os.path.splitext(out)[1] or ".png"))
                shutil.move(out, path)
                if video:
                    mark_video(str(path), m.get("name", ""))
                protocol.log("[comfy] %s done in %.1fs" % ("video" if video else "image", time.time() - t0))
                if not d.get("_quiet"):
                    protocol.result(str(path))
                saved.append(str(path))
        finally:
            if input_name:
                (WORK / "input" / input_name).unlink(missing_ok=True)
        return saved

    async def _run(self, graph, steps, quiet=False):
        """Sends the workflow, reports progress, returns the path of the saved picture or video."""
        import aiohttp
        cid = uuid.uuid4().hex
        async with aiohttp.ClientSession(headers=self.server.headers) as s:
            async with s.ws_connect("%s/ws?clientId=%s" % (self.server.url, cid), heartbeat=30) as ws:
                async with s.post(self.server.url + "/prompt", json={"prompt": graph, "client_id": cid}) as r:
                    status, body = r.status, await r.json()
                if status != 200:
                    err = body.get("error") or {}
                    nodes = "; ".join("%s: %s" % (k, ", ".join(e.get("message", "") for e in v.get("errors", [])))
                                      for k, v in (body.get("node_errors") or {}).items())
                    raise RuntimeError("ComfyUI rejected the job: %s %s" % (err.get("message", ""), nodes))
                pid = body["prompt_id"]
                interrupted = False
                while True:
                    try:
                        msg = await ws.receive(timeout=1.0)
                    except asyncio.TimeoutError:
                        msg = None
                    if self.reader is not None and self.reader.stop_requested() and not interrupted:
                        async with s.post(self.server.url + "/interrupt", json={}):
                            interrupted = True
                    if msg is None:
                        continue
                    if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        raise RuntimeError("Connection to ComfyUI lost")
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue  # binary preview frames
                    m = json.loads(msg.data)
                    data = m.get("data") or {}
                    if data.get("prompt_id") not in (None, pid):
                        continue
                    kind = m.get("type")
                    if kind == "progress" and not quiet:
                        protocol.progress(round(100.0 * data["value"] / max(1, data["max"]), 1))
                    elif kind == "execution_interrupted":
                        raise StopRequested()
                    elif kind == "execution_error":
                        raise RuntimeError("ComfyUI: %s" % (data.get("exception_message") or "error").strip())
                    elif kind == "executing" and data.get("node") is None:
                        break
            async with s.get("%s/history/%s" % (self.server.url, pid)) as r:
                hist = (await r.json())[pid]
        images = (hist.get("outputs") or {}).get("save", {}).get("images") or []
        if not images:
            raise RuntimeError("ComfyUI returned no picture")
        img = images[0]
        path = os.path.realpath(WORK / img.get("type", "output") / img.get("subfolder", "") / img["filename"])
        if not path.startswith(os.path.realpath(WORK) + os.sep):
            raise RuntimeError("ComfyUI returned a file outside its folders")
        return path


def serve(stream=None):
    # the app ends the engine with SIGTERM: leave through the finally below, so ComfyUI does not outlive it
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    reader = protocol.CommandReader(stream).start()
    engine = ComfyEngine(reader)
    # per job, for benchmarks: this process and the ComfyUI server it runs
    footprint = protocol.Footprint(lambda: [os.getpid()] + ([engine.server.proc.pid] if engine.server.proc else []))
    protocol.state("loaded")
    if os.environ.get("VK_ANNOUNCE_READY") == "1":
        protocol.state("idle")
    try:
        while True:
            item = reader.next_command()
            if item is None:
                break
            op, job = item
            if op in ("generate", "preview"):
                protocol.state("busy")
                footprint.start()
                target = job.get("target") or job.get("model_dir")
                try:
                    if op == "preview":
                        import previews
                        protocol.preview({"model": target, "preview": previews.paint(engine.generate, job)})
                    else:
                        engine.generate(job)
                except StopRequested:
                    protocol.log("[comfy] stopped")
                    if op == "preview":
                        protocol.preview({"model": target, "error": "stopped"})
                except Exception as e:
                    traceback.print_exc()
                    if op == "preview":
                        protocol.preview({"model": target, "error": str(e)[:300]})
                    else:
                        protocol.error(protocol.describe(e))
                footprint.report()
                protocol.state("idle")
            elif op == "unload":
                try:
                    engine.server.free()
                except Exception:
                    traceback.print_exc()
            elif op == "ping":
                protocol.event("pong")
    finally:
        engine.server.stop()


if __name__ == "__main__":
    serve()
