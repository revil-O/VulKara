# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Entry point of the diffusers engine process.

    python main.py                 serve jobs over stdin/stdout (spawned by bridge.js)
    python main.py import_model …  import a model (spawned by native_functions.js)
    python main.py detect_pose <image>   pose (body, hands, face) of a photo for the pose editor
    python main.py find_faces <image>    the faces of a photo for Restore (5 landmarks and the restored square)
    python main.py caption_image <image> a prompt that describes the picture (Image to image, Qwen3-VL 2B)
    python main.py export_single <model folder> <out.safetensors>   SD 1.x / SDXL in folder layout as one checkpoint
    python main.py train <job.json>      LoRA training for SDXL (FLUX.2 / Krea 2: mlx/train.py)
    python main.py hardware [--tiers]    this Mac and the mode per model family (Settings, docs)
    python main.py previews [<folder> …] preview pictures of imported models / LoRAs from their sources
    python main.py content_check [<file> …]  content filter and AI marking of results (spawned by bridge.js)
    python main.py recheck_loras [--apply]   installed LoRAs / models checked again with the current detection
    python main.py maker_settings [--dry] <model folder> …  the maker's recommended settings read again from the model card
"""
import json
import os
import sys
import traceback

# optimum-quanto compiles its kernels with ninja from the venv on first use
os.environ["PATH"] = os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import protocol  # noqa: E402


def serve(stream=None):
    from engine import DiffusersEngine, StopRequested, _free_memory

    reader = protocol.CommandReader(stream).start()
    engine = DiffusersEngine(reader)
    protocol.state("loaded")
    if os.environ.get("VK_ANNOUNCE_READY") == "1":
        # the first engine started: the UI waits for it
        protocol.state("idle")

    footprint = protocol.Footprint()  # per job, for benchmarks
    while True:
        item = reader.next_command()
        if item is None:
            break
        op, job = item
        if op == "generate":
            protocol.state("busy")
            footprint.start()
            try:
                engine.generate(job)
            except StopRequested:
                protocol.log("[diffusers] stopped")
            except Exception as e:
                traceback.print_exc()
                protocol.error(protocol.describe(e))
            _free_memory("image")  # a stopped or failed job leaves its buffers in the Metal cache otherwise
            footprint.report()
            protocol.state("idle")
        elif op == "preview":
            # a preview picture painted by a model (of itself or of a LoRA); reported as a preview event
            protocol.state("busy")
            target = job.get("target") or job.get("model_dir")
            try:
                protocol.preview({"model": target, "preview": engine.make_preview(job)})
            except StopRequested:
                protocol.preview({"model": target, "error": "stopped"})
            except Exception as e:
                traceback.print_exc()
                protocol.preview({"model": target, "error": str(e)[:300]})
            _free_memory()
            protocol.state("idle")
        elif op == "unload":
            try:
                engine.unload()
            except Exception:
                traceback.print_exc()
        elif op == "ping":
            protocol.event("pong")
        else:
            protocol.log("[diffusers] unknown request " + op)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "import_model":
        import importer
        importer.main(sys.argv[2:])
    elif len(sys.argv) > 1 and sys.argv[1] == "previews":
        import previews
        sys.exit(previews.main(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "train":
        import train_sdxl
        sys.exit(train_sdxl.run(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "hardware":
        import profiles
        sys.exit(profiles.main(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "detect_pose":
        import preprocess
        sys.exit(preprocess.main(sys.argv[1:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "export_single":
        import export_single
        sys.exit(export_single.main(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "find_faces":
        import restore
        sys.exit(restore.faces_main(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "caption_image":
        import caption
        sys.exit(caption.main(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "recheck_loras":
        import recheck
        sys.exit(recheck.main(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "photo_select":
        import photo_tools
        photo_tools.segment_serve()
    elif len(sys.argv) > 1 and sys.argv[1] == "maker_settings":
        import maker_settings
        sys.exit(maker_settings.main(sys.argv[2:]))
    elif len(sys.argv) > 1 and sys.argv[1] == "content_check":
        import content_check
        sys.exit(content_check.main(sys.argv[2:]))
    else:
        serve()
