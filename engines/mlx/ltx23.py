# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""LTX-2.3 (Lightricks, LTX-2 Community License): video with sound from a prompt, or from a start picture, on MLX.

The distilled two-stage path of ltx-2-mlx (dgrauet, MIT; pinned commit, installed with the MLX runtime as a GitHub
extension, src/main/runtimes.ts): 8 steps at half size, the latent ×2 with the spatial upscaler, 3 refining steps,
no guidance. Text is encoded by Gemma 3 12B (MLX 4 bit, a helper model) and freed before the transformer loads. The
transformer blocks stream from the mapped file (low_ram_streaming: same clip, a little faster, MEASUREMENTS 7cp).
ltx-2-mlx calls the ffmpeg program, which Macs do not have, to save and to compress the start picture: the frames and
the sound are taken from its decoders here and written with PyAV (H.264 with Apple's encoder + AAC), with the AI notice
in the metadata, and the start picture's one-frame compression goes through PyAV as in Lightricks' own pipeline.
"""
import glob
import os
import sys
import tempfile
import time
import uuid

FPS = 24
GRID = 64  # two stages: the half size must be a multiple of the VAE's 32 px (ltx_core_mlx snap_output_dimensions)
SAMPLE_RATE = 48000
BITS_PER_PIXEL = 0.4  # about 3.8 Mbit/s at 768 × 512, 24 fps
GEMMA_HELPER = "ltx23_gemma"  # engines/diffusers/helpers.json


def frames_for(seconds, fps=FPS):
    """The frame count nearest to a clip length: LTX takes 8n + 1 frames."""
    n = max(1, round(float(seconds) * fps))
    return max(1, round((n - 1) / 8)) * 8 + 1


def snap(width, height):
    """The size nearest to the asked one on LTX's 64 px grid (at least 256 px a side)."""
    return tuple(max(256, int(round(v / GRID)) * GRID) for v in (width, height))


def extension_paths(prefix=None):
    """The src folders of ltx-2-mlx's packages in the MLX runtime (<runtime>/extensions/ltx-2-mlx, beside the venv)."""
    root = os.path.join(os.path.dirname(prefix or sys.prefix), "extensions", "ltx-2-mlx", "packages")
    return sorted(glob.glob(os.path.join(root, "ltx-*-mlx", "src")))


def _import_ltx():
    for p in extension_paths():
        if p not in sys.path:
            sys.path.insert(0, p)
    try:
        from ltx_pipelines_mlx.distilled import DistilledPipeline
    except ImportError as e:
        raise RuntimeError("The MLX runtime has no LTX-2.3 yet: update it in Settings → Runtimes (%s)" % e)
    return DistilledPipeline


class _Steps:
    """Stands in for tqdm in ltx-2-mlx's denoising loop: reports every step and stops between them."""

    def __init__(self, iterable, *args, **kwargs):
        self.iterable = iterable

    def __iter__(self):
        for item in self.iterable:
            _Steps.on_step()
            yield item
        _Steps.on_step()

    def __getattr__(self, name):  # set_postfix, update, close …
        return lambda *a, **k: None

    on_step = staticmethod(lambda: None)


def staged_encode(encoder, prompt):
    """PromptEncoder.encode of ltx-2-mlx with Gemma and the connector one after the other: its load() fetches both
    (8.0 + 6.3 GB at once, the run's peak on 16 GB: MEASUREMENTS 7cp); here it is called twice with the other part
    marked as present, and Gemma is freed once its hidden states are computed."""
    import mlx.core as mx
    from ltx_core_mlx.utils.memory import aggressive_cleanup
    held = object()
    encoder._feature_extractor = held  # load() fetches Gemma only
    encoder.load()
    hidden, mask = encoder._text_encoder.encode_all_layers(
        prompt, max_length=int(os.environ.get("LTX2_GEMMA_MAX_LENGTH", "1024")))
    mx.eval(hidden, mask)
    encoder._text_encoder, encoder._feature_extractor = held, None  # load() fetches the connector only
    aggressive_cleanup()
    encoder.load()
    try:
        return encoder._feature_extractor(hidden, attention_mask=mask)
    finally:
        encoder._text_encoder = None


def encode_single_frame(output_file, image_array, crf):
    """ltx-2-mlx's media_io.encode_single_frame through PyAV instead of the ffmpeg program, as Lightricks' own pipeline
    does it: the start picture as one H.264 frame at the model's CRF (yuv420p, even sides), so it looks like the
    compressed video the model learned from."""
    import av
    import numpy as np
    arr = np.asarray(image_array)
    arr = arr if arr.dtype == np.uint8 else arr.astype(np.uint8)
    h, w = arr.shape[0] // 2 * 2, arr.shape[1] // 2 * 2
    with av.open(output_file, "w", format="mp4") as out:
        stream = out.add_stream("libx264", rate=1)
        stream.width, stream.height, stream.pix_fmt = w, h, "yuv420p"
        stream.options = {"crf": str(int(crf)), "preset": "veryfast"}
        out.mux(stream.encode(av.VideoFrame.from_ndarray(np.ascontiguousarray(arr[:h, :w]), format="rgb24")))
        out.mux(stream.encode())


def decode_single_frame(video_file):
    """ltx-2-mlx's media_io.decode_single_frame through PyAV: the first frame as HxWx3 RGB."""
    import av
    if hasattr(video_file, "seek"):
        video_file.seek(0)
    with av.open(video_file) as f:
        return next(f.decode(video=0)).to_ndarray(format="rgb24")


class Stopped(Exception):
    pass


def write_mp4(path, chunks, waveform, fps, notice):
    """Writes the decoded chunks ((B, 3, T, H, W) in [-1, 1], MLX or numpy) as H.264 and the waveform ((B, C, T) at
    48 kHz, or None) as AAC to path, with the AI notice in the metadata. Returns the number of frames."""
    import av
    import numpy as np
    frames = 0
    with av.open(path, "w", format="mp4") as out:
        out.metadata.update({"comment": notice, "description": notice, "encoder": "VulKara"})
        video = None
        audio = out.add_stream("aac", rate=SAMPLE_RATE) if waveform is not None else None
        for chunk in chunks:
            arr = np.asarray(chunk, dtype=np.float32)[0]  # (3, T, H, W)
            arr = ((np.clip(arr, -1.0, 1.0) + 1.0) * 127.5).astype(np.uint8).transpose(1, 2, 3, 0)  # (T, H, W, 3)
            if video is None:
                # Apple's hardware encoder: on every Mac, fast, and no GPL code (PyAV's wheels also carry libx264)
                video = out.add_stream("h264_videotoolbox", rate=fps)
                video.width, video.height = arr.shape[2], arr.shape[1]
                video.pix_fmt = "nv12"
                video.bit_rate = int(arr.shape[1] * arr.shape[2] * fps * BITS_PER_PIXEL)
            for frame in arr:
                out.mux(video.encode(av.VideoFrame.from_ndarray(np.ascontiguousarray(frame), format="rgb24")))
                frames += 1
        out.mux(video.encode())
        if audio is not None:
            wav = np.asarray(waveform, dtype=np.float32)[0]
            wav = np.clip(wav if wav.ndim == 2 else wav[None, :], -1.0, 1.0)
            layout = "stereo" if wav.shape[0] == 2 else "mono"
            step = 1024
            for i in range(0, wav.shape[1], step):
                part = np.ascontiguousarray(wav[:, i:i + step])
                frame = av.AudioFrame.from_ndarray(part, format="fltp", layout=layout)
                frame.sample_rate = SAMPLE_RATE
                out.mux(audio.encode(frame))
            out.mux(audio.encode())
    return frames


def written(path, write):
    """write(part) into a hidden part file beside path (same disk), then renamed: a failed encode leaves no broken
    video in the pictures folder. Returns what write returns."""
    folder, name = os.path.split(path)
    part = os.path.join(folder, "." + name.replace(".mp4", ".part.mp4"))
    try:
        got = write(part)
        os.replace(part, path)
        return got
    finally:
        if os.path.exists(part):
            os.remove(part)


def run(job, model_dir, gemma_dir, images_dir, stop=None, state=None, progress=None, note=None, log=None):
    """A video job: the mp4's path, or None when stopped. stop: () -> bool, asked at every denoising step."""
    import mlx.core as mx
    state = state or (lambda s: None)
    progress = progress or (lambda p: None)
    log = log or (lambda s: None)
    DistilledPipeline = _import_ltx()
    import ltx_pipelines_mlx.utils.media_io as media_io
    import ltx_pipelines_mlx.utils.samplers as samplers
    # the start picture's compression without the ffmpeg program (media_io's preprocess looks them up there)
    media_io.encode_single_frame, media_io.decode_single_frame = encode_single_frame, decode_single_frame
    from ltx_core_mlx.model.video_vae.video_vae import _compute_decode_tiling

    seconds = float(job.get("video_seconds") or 2)
    num_frames = frames_for(seconds)
    width, height = snap(int(job.get("width") or 768), int(job.get("height") or 512))
    with_sound = job.get("audio", True) is not False
    total, done = 8 + 3, [0]

    def on_step():
        if stop and stop():
            raise Stopped()
        done[0] += 1
        progress(min(99.0, 100.0 * (done[0] - 1) / total))

    start = None
    t0 = time.time()
    try:
        with tempfile.TemporaryDirectory() as work:
            if job.get("input_image"):
                import colour
                # upright as the app shows it, in sRGB whatever profile it carries
                start = os.path.join(work, "start.png")
                colour.open_rgb(job["input_image"]).save(start)
            state("Encoding the prompt (Gemma 3 12B)")
            progress(-1)
            pipe = DistilledPipeline(model_dir, gemma_model_id=gemma_dir, low_memory=True, low_ram_streaming=True)
            pipe.verbose = False
            pipe.generate_audio = with_sound
            pipe.prompt_encoder.encode = lambda prompt: staged_encode(pipe.prompt_encoder, prompt)
            samplers.tqdm, _Steps.on_step = _Steps, staticmethod(on_step)
            state("Making the video (LTX-2.3, %d × %d, %d frames)" % (width, height, num_frames))
            video, audio = pipe.generate_two_stage(job.get("prompt") or "", height=height, width=width,
                                                   num_frames=num_frames, frame_rate=FPS, seed=int(job.get("seed") or 0),
                                                   image=start)
            # the transformer is not needed for decoding (ltx-2-mlx frees it there too)
            pipe.dit = None
            pipe._loaded = False
            mx.clear_cache()
            if stop and stop():
                return None
            state("Decoding the video" + (" and the sound" if with_sound else ""))
            progress(-1)
            waveform = pipe.audio_decoder_block(audio) if with_sound else None
            if waveform is not None:
                waveform = waveform.astype(mx.float32)  # numpy reads no bfloat16
                mx.eval(waveform)
                pipe.audio_decoder_block.free()
            decoder = pipe.video_decoder_block.load()
            tiling = _compute_decode_tiling(video.shape, frame_rate=FPS)
            name = "ltx23_%s.mp4" % uuid.uuid4().hex[:12]
            path = os.path.join(images_dir, name)
            os.makedirs(images_dir, exist_ok=True)
            notice = "AI generated with VulKara (model: LTX-2.3)"
            chunks = (c.astype(mx.float32) for c in decoder.tiled_decode(video, tiling))
            frames = written(path, lambda part: write_mp4(part, chunks, waveform, FPS, notice))
            log("[ltx23] %d × %d, %d frames%s in %.0fs" % (width, height, frames, " with sound" if with_sound else "",
                                                          time.time() - t0))
            return path
    except Stopped:
        return None
    finally:
        samplers.tqdm = __import__("tqdm").tqdm
        mx.clear_cache()
