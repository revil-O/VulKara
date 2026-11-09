# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Generates the data of the Licenses page: src/shared/data/licenses.json, the models the app can download
(licence, link, commercial use) and the software it contains or installs.

    python3 tools/gen_licenses.py

Model licences are read from Hugging Face (model card) and Civitai (model permissions); what a licence allows
is described in LICENSES below (checked against the licence texts). Run again after adding models to
src/shared/data/curated_models.json or the engines. The notices of the bundled packages are made by
tools/gen_notices.mjs.
"""
import json
import os
import re
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "src", "shared", "data")

# what each license allows: model = commercial use of the model, outputs = commercial use of the pictures
# ("yes", "limited" = with conditions, "no")
LICENSES = {
    "creativeml-openrail-m": dict(
        name="CreativeML Open RAIL-M", url="https://huggingface.co/spaces/CompVis/stable-diffusion-license",
        model="yes", outputs="yes", note="Use-based restrictions (Attachment A) apply to the model and its outputs."),
    "openrail++": dict(
        name="CreativeML Open RAIL++-M", url="https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md",
        model="yes", outputs="yes", note="Use-based restrictions (Attachment A) apply to the model and its outputs."),
    "openrail": dict(
        name="OpenRAIL", url="https://huggingface.co/blog/open_rail",
        model="yes", outputs="yes", note="Use-based restrictions apply."),
    "bsd-3-clause": dict(
        name="BSD 3-Clause License", url="https://opensource.org/license/bsd-3-clause", model="yes", outputs="yes", note=""),
    "mit": dict(
        name="MIT License", url="https://opensource.org/license/mit", model="yes", outputs="yes", note=""),
    "apache-2.0": dict(
        name="Apache License 2.0", url="https://www.apache.org/licenses/LICENSE-2.0", model="yes", outputs="yes", note=""),
    "flux-1-dev-non-commercial-license": dict(
        name="FLUX.1 [dev] Non-Commercial License",
        url="https://github.com/black-forest-labs/flux/blob/main/model_licenses/LICENSE-FLUX1-dev",
        model="no", outputs="yes", note="The model only for non-commercial purposes; generated pictures may be used commercially."),
    "flux-non-commercial-license": dict(
        name="FLUX Non-Commercial License",
        url="https://github.com/black-forest-labs/flux2/blob/main/model_licenses/LICENSE-FLUX-NON-COMMERICAL",
        model="no", outputs="yes", note="The model only for non-commercial purposes; generated pictures may be used commercially."),
    "stabilityai-ai-community": dict(
        name="Stability AI Community License", url="https://stability.ai/community-license-agreement",
        model="limited", outputs="limited",
        note="Commercial use free of charge below USD 1 million annual revenue, after registering with Stability AI; above that an enterprise license."),
    "sai-nc-community": dict(
        name="Stability AI Community License", url="https://huggingface.co/stabilityai/sdxl-turbo/blob/main/LICENSE.md",
        model="limited", outputs="limited",
        note="Commercial use free of charge below USD 1 million annual revenue, after registering with Stability AI; above that an enterprise license."),
    "circlestone-labs-non-commercial-license": dict(
        name="CircleStone Labs Non-Commercial License", url="https://huggingface.co/circlestone-labs/Anima/blob/main/LICENSE.md",
        model="no", outputs="yes", note="The model only for non-commercial purposes; generated pictures may be used for any purpose."),
    "cc-by-nc-4.0": dict(
        name="Creative Commons Attribution-NonCommercial 4.0", url="https://creativecommons.org/licenses/by-nc/4.0/",
        model="no", outputs="no", note="Model and pictures for non-commercial use only; commercial use needs an agreement with the maker."),
    # Bria's Fibo 2.0 licence as mflux-community's repos name it: CC BY-NC 4.0
    "fibo-2.0-edit-turbo-license": dict(
        name="Creative Commons Attribution-NonCommercial 4.0", url="https://creativecommons.org/licenses/by-nc/4.0/",
        model="no", outputs="no", note="Model and pictures for non-commercial use only; commercial use needs an agreement with the maker."),
    "ideogram-4-non-commercial": dict(
        name="Ideogram Non-Commercial Model Agreement", url="https://huggingface.co/ideogram-ai/ideogram-4-fp8/blob/main/LICENSE.md",
        model="no", outputs="no",
        note="Generating pictures for revenue-generating products or advertising is not a non-commercial purpose; AI disclosure where the law requires it."),
    "qwen-research": dict(
        name="Qwen Research License Agreement", url="https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE",
        model="no", outputs="no",
        note="Research and evaluation only; commercial use needs a separate licence from Alibaba (Tongyi Lab)."),
    "flux-kommunity-license": dict(
        name="FLUX Kommunity License v1.0", url="https://huggingface.co/black-forest-labs/flux-3-image-klein/blob/main/LICENSE.md",
        model="no", outputs="limited",
        note="Non-commercial use of the model. Pictures may be used commercially only by people and companies below USD 5 million annual revenue, with content filter measures and the AI disclosure the law requires; anything else needs a licence from Black Forest Labs. Distributing the model needs Black Forest Labs' attribution notice."),
    "krea-2-community-license": dict(
        name="Krea 2 Community License",
        url="https://cdn.jsdelivr.net/gh/krea-ai/krea-2@db3984fbc6e13b34c0064990fc2d95ac64d00058/assets/hf_samples/LICENSE.pdf",
        model="limited", outputs="limited",
        note="Commercial use only below USD 1 million company revenue. Section 4.2 requires reasonable content filter measures against prohibited content (Acceptable Use Policy: https://www.krea.ai/krea-2-use-policy)."),
    "dreamlike": dict(
        name="Dreamlike License (modified CreativeML OpenRAIL-M)",
        url="https://huggingface.co/dreamlike-art/dreamlike-diffusion-1.0/blob/main/LICENSE.md",
        model="limited", outputs="limited",
        note="Not in websites or apps that earn revenue or donations; outputs commercially only in teams of 10 or less."),
}

# models the app downloads by itself, besides the recommended list
EXTRA = [
    ("Base models", "black-forest-labs/FLUX.1-dev", "FLUX.1 [dev]"),
    ("Base models", "black-forest-labs/FLUX.1-schnell", "FLUX.1 [schnell]"),
    ("Base models", "lodestones/Chroma1-Flash", "Chroma1-Flash (base parts of Chroma Flash checkpoints)"),
    ("Base models", "Tongyi-MAI/Z-Image", "Z-Image (base parts of Z-Image Base checkpoints)"),
    ("Base models", "black-forest-labs/FLUX.2-dev", "FLUX.2 [dev]"),
    ("Base models", "krea/Krea-2-Turbo", "Krea 2"),
    ("Base models", "black-forest-labs/flux-3-image-klein", "FLUX 3 Image Klein"),
    ("Base models", "ideogram-ai/ideogram-4-fp8", "Ideogram 4"),
    ("Base models", "Qwen/Qwen-Image", "Qwen-Image"),
    ("Base models", "Qwen/Qwen-Image-2.1", "Qwen-Image 2.1"),
    ("Base models", "sd2-community/stable-diffusion-2-1-base", "Stable Diffusion 2.1 base (512 px)"),
    ("Video", "lightx2v/Wan2.2-Lightning", "lightx2v 4-step LoRAs (Wan 2.2)"),
    ("Video", "Wan-AI/Wan2.2-I2V-A14B", "Wan 2.2 I2V A14B (original weights)"),
    ("Video", "Wan-AI/Wan2.2-TI2V-5B", "Wan 2.2 TI2V 5B (original weights)"),
    ("ControlNet", "xinsir/controlnet-union-sdxl-1.0", "ControlNet Union SDXL (xinsir)"),
    ("ControlNet", "Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro-2.0", "ControlNet Union Pro 2.0 for FLUX.1 (Shakker Labs)"),
    ("ControlNet", "lllyasviel/control_v11p_sd15_openpose", "ControlNet 1.1 for SD 1.5 (pose, depth, canny, lineart, scribble)"),
    ("ControlNet", "stabilityai/stable-diffusion-3.5-large-controlnet-depth", "SD 3.5 Large ControlNets (depth, canny, blur)"),
    ("ControlNet", "tensorart/SD3.5M-Controlnet-Depth", "SD 3.5 Medium ControlNets (TensorArt depth, canny)"),
    ("ControlNet", "monster-labs/control_v1p_sdxl_qrcode_monster", "QR Code Monster (Illusion Generator)"),
    ("Helper models", "yzd-v/DWPose", "DWPose (pose detection)"),
    ("Helper models", "depth-anything/Depth-Anything-V2-Small-hf", "Depth Anything V2 Small (depth maps)"),
    ("Helper models", "Comfy-Org/Real-ESRGAN_repackaged", "Real-ESRGAN x4plus (Upscale)"),
    ("Helper models", "VisualInference/FLUX-3-Image-Klein-pup-MLX-4bit", "FLUX 3 prompt upsampler (MLX, 4 bit)"),
    ("Helper models", "piddnad/ddcolor_modelscope", "DDColor (colouring old photos, Restore)"),
    ("Helper models", "Falconsai/nsfw_image_detection", "NSFW image detection (content filter)"),
    ("Helper models", "dima806/facial_age_image_detection", "Facial age detection (content filter)"),
]

# software the app ships or installs into its runtimes
SOFTWARE = [
    ("In the app", "Electron", "MIT", "https://github.com/electron/electron/blob/main/LICENSE"),
    ("In the app", "Vue 3, Pinia, Vue Router", "MIT", "https://github.com/vuejs/core/blob/main/LICENSE"),
    ("In the app", "Lucide (icons)", "ISC", "https://github.com/lucide-icons/lucide/blob/main/LICENSE"),
    ("Runtimes (installed on demand)", "PyTorch", "BSD-3-Clause", "https://github.com/pytorch/pytorch/blob/main/LICENSE"),
    ("Runtimes (installed on demand)", "diffusers, transformers, huggingface_hub, safetensors, optimum-quanto, accelerate",
     "Apache-2.0", "https://github.com/huggingface/diffusers/blob/main/LICENSE"),
    ("Runtimes (installed on demand)", "MLX", "MIT", "https://github.com/ml-explore/mlx/blob/main/LICENSE"),
    ("Runtimes (installed on demand)", "mflux", "MIT", "https://github.com/filipstrand/mflux/blob/main/LICENSE"),
    ("Runtimes (installed on demand)", "ComfyUI (runs as a separate process)", "GPL-3.0",
     "https://github.com/comfyanonymous/ComfyUI/blob/master/LICENSE"),
    ("Runtimes (installed on demand)", "ComfyUI-GGUF", "Apache-2.0", "https://github.com/city96/ComfyUI-GGUF/blob/main/LICENSE"),
    ("Runtimes (installed on demand)", "gguf", "MIT", "https://github.com/ggml-org/llama.cpp/blob/master/LICENSE"),
    ("Runtimes (installed on demand)", "ONNX Runtime", "MIT", "https://github.com/microsoft/onnxruntime/blob/main/LICENSE"),
    ("Runtimes (installed on demand)", "OpenCV", "Apache-2.0", "https://github.com/opencv/opencv/blob/4.x/LICENSE"),
    ("Runtimes (installed on demand)", "spandrel (photo tools and Restore on the GPU)", "MIT", "https://github.com/chaiNNer-org/spandrel/blob/main/LICENSE"),
    ("Runtimes (installed on demand)", "spandrel_extra_arches (CodeFormer's architecture)", "MIT", "https://github.com/chaiNNer-org/spandrel/blob/main/LICENSE"),
    ("Runtimes (installed on demand)", "uv (installs the runtimes)", "MIT OR Apache-2.0", "https://github.com/astral-sh/uv/blob/main/LICENSE-MIT"),
]

CIVITAI_BASE_NOTE = "The license of the base model applies as well."


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "vulkara-licenses"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def hf_entry(group, repo, title, model_id=None):
    card = (get("https://huggingface.co/api/models/" + repo).get("cardData") or {})
    key = card.get("license_name") or card.get("license") or ""
    if repo.startswith("dreamlike-art/"):
        key = "dreamlike"
    lic = LICENSES.get(key)
    if lic is None:
        raise SystemExit("unknown license %r of %s: describe it in LICENSES" % (key, repo))
    return dict(group=group, id=model_id, title=title, source="https://huggingface.co/" + repo, license=lic["name"],
                license_url=lic["url"], model=lic["model"], outputs=lic["outputs"], note=lic["note"])


def civitai_entry(group, ref, title, model_id):
    mid = int(re.search(r"/models/(\d+)", ref).group(1))
    d = get("https://civitai.com/api/v1/models/%d" % mid)
    uses = d.get("allowCommercialUse") or []
    uses = [uses] if isinstance(uses, str) else uses
    images = "yes" if "Image" in uses else "no"
    parts = ["Civitai permissions: " + (", ".join(uses) or "none") + ".",
             "Selling generated pictures: " + ("allowed" if images == "yes" else "not allowed") + ".",
             "Sharing merges / derivatives: " + ("allowed" if d.get("allowDerivatives") else "not allowed") + ".",
             CIVITAI_BASE_NOTE]
    return dict(group=group, id=model_id, title=title, source="https://civitai.com/models/%d" % mid,
                license="Civitai model license (author's permissions)", license_url="https://civitai.com/models/%d" % mid,
                model="limited" if any(u in uses for u in ("Rent", "Sell")) else "no", outputs=images, note=" ".join(parts))


TOOL_LICENSES = {"MIT": ("MIT License", "https://opensource.org/license/mit"),
                 "Apache-2.0": ("Apache License 2.0", "https://www.apache.org/licenses/LICENSE-2.0")}


def photo_tools():
    """The recommended photo tools (engines/diffusers/photo_tools.json): their licence is part of the catalog, checked
    against the upstream project when a tool is added there."""
    with open(os.path.join(ROOT, "engines", "diffusers", "photo_tools.json")) as f:
        tools = json.load(f)["tools"]
    out = []
    for t in tools:
        name, url = TOOL_LICENSES[t["licence"]]
        out.append(dict(group="Photo tools", id=None, title=t["name"], source=t["source_url"], license=name,
                        license_url=t["licence_url"] or url, model="yes", outputs="yes", note=t.get("licence_note", "")))
    return out


# helper models published outside Hugging Face (GitHub releases), with the licence of their project
GITHUB_HELPERS = [
    dict(group="Helper models", id=None, title="CodeFormer (faces, Restore)",
         source="https://github.com/sczhou/CodeFormer/releases/tag/v0.1.0", license="NTU S-Lab License 1.0",
         license_url="https://github.com/sczhou/CodeFormer/blob/master/LICENSE", model="no", outputs="no",
         note="For non-commercial use only: restored faces may not be used commercially. VulKara is free and downloads "
              "the weights from the project on first use."),
    dict(group="Helper models", id=None, title="YuNet face detection (Restore)",
         source="https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet", license="MIT License",
         license_url="https://github.com/opencv/opencv_zoo/blob/main/models/face_detection_yunet/LICENSE", model="yes",
         outputs="yes", note=""),
]


# curated models downloaded from a repackaging: the maker's page as the source, and what the entry adds
OVERRIDES = {
    "MOSS-Image": dict(source="https://huggingface.co/OpenMOSS-Team/MOSS-Image-SFT"),
    "MOSS-Image-8step-DMD": dict(note="lodestones' 8-step DMD LoRA (Apache 2.0) merged into MOSS-Image SFT."),
    "Fibo-2.0-Edit-Turbo": dict(source="https://huggingface.co/briaai/Fibo-2.0-edit-turbo",
                                note="Model and pictures for non-commercial use only; commercial use needs an agreement "
                                     "with Bria AI. ComfyUI files repackaged by Comfy-Org."),
    "Fibo-2.0-Edit-Turbo-MLX": dict(source="https://huggingface.co/briaai/Fibo-2.0-edit-turbo",
                                    note="Model and pictures for non-commercial use only; commercial use needs an "
                                         "agreement with Bria AI. Saved in 8 bit for mflux by mflux-community."),
}


def models():
    with open(os.path.join(DATA, "curated_models.json")) as f:
        curated = json.load(f)
    out = [dict((hf_entry if m["source"] == "hf" else civitai_entry)("Recommended: " + m["family"], m["ref"], m["title"],
                                                                      m["id"]), **OVERRIDES.get(m["id"], {}))
           for m in curated]
    return out + [hf_entry(group, repo, title) for group, repo, title in EXTRA] + photo_tools() + GITHUB_HELPERS


def main():
    data = {
        "software": [dict(group=g, name=n, license=l, url=u) for g, n, l, u in SOFTWARE],
        "models": models(),
    }
    with open(os.path.join(DATA, "licenses.json"), "w") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print("%d models, %d software components" % (len(data["models"]), len(SOFTWARE)))


if __name__ == "__main__":
    main()
