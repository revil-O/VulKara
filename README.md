<div align="center">

<img src="build/icon.png" width="128" alt="VulKara icon">

# VulKara

**Your local AI image generator with high privacy**<br>
Text to image · Image to image · Inpainting · AI Canvas · Image to video · Upscale · Restore · Pose · Illusion · LoRAs · Training · Remote web UI

[![Release](https://img.shields.io/github/v/release/revil-O/VulKara?label=release&color=c2662d)](https://github.com/revil-O/VulKara/releases/latest)
![macOS](https://img.shields.io/badge/macOS-Apple%20silicon-111?logo=apple&logoColor=white)
![Electron](https://img.shields.io/badge/Electron-44-47848F?logo=electron&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3.5-42b883?logo=vuedotjs&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white)
![Runs locally](https://img.shields.io/badge/runs-100%25%20local-c2662d)
[![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue)](LICENSE)
[![Discord](https://img.shields.io/badge/community-Discord-5865F2?logo=discord&logoColor=white)](https://discord.gg/SDnSHZfQY)

<img src="docs/images/banner.jpg" alt="Pictures made with VulKara">

<sub>Made with VulKara on an M2: Juggernaut XL v7, 25 steps, styles Cinematic, Digital Art, Neon Punk, Fantasy Art and Analog Film.</sub>

**VulKara is free, its source code is open, and it is made in my spare time.** If it is useful to you, a coffee keeps it going:<br>
new models, fixes and features — free, local and private for everyone.

<a href="https://buymeacoffee.com/revil.0"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me a Coffee" height="48"></a>

[Website](https://www.vulkara.net) · [Discord](https://discord.gg/SDnSHZfQY) · [Coming next](#coming-next-your-own-characters) · [Download](https://github.com/revil-O/VulKara/releases/latest) · [User guide](docs/USER_GUIDE.md) · [How the pipelines work](docs/PIPELINES.md) · [Developer guide](docs/DEVELOPMENT.md) · [Measurements](docs/MEASUREMENTS.md) · [Licence](LICENSE)

The app and its user guide in **English** · [Deutsch](docs/de/USER_GUIDE.md) · [Español](docs/es/USER_GUIDE.md) · [Português (Brasil)](docs/pt-BR/USER_GUIDE.md) · [Português (Portugal)](docs/pt-PT/USER_GUIDE.md) · [Translate it](docs/TRANSLATING.md)

<sub>Inspired by DiffusionBee &amp; ComfyUI</sub>

</div>

---

> [!TIP]
> **<img src="docs/icons/hard-drive.svg" width="16" height="16" alt=""> Model streaming from the SSD – big models on small Macs.**
> A model that does not fit into memory is streamed block by block from the SSD, internal or external, while the
> picture is computed. It keeps its full 16-bit quality, and models that need 24 GB run on a Mac with 16 GB
> (tested on a Mac mini M4: FLUX.1 [dev], Krea 2, Qwen-Image 2.1). Automatic, nothing to set up.
> [How it works](#big-models-on-small-macs-ssd-streaming)

> [!NOTE]
> **<img src="docs/icons/sparkles.svg" width="16" height="16" alt=""> New in 0.7.0: FLUX 3 Image Klein.** Black Forest Labs' newest model on the MLX runtime, for text to
> image and edits with a reference picture, with LoRAs and an optional **prompt upsampler** that turns a short prompt
> into the full scene description FLUX 3 is trained on. The 6 and 8 bit versions run on a Mac with 16 GB.
> [Text to image](#text-to-image) · [Supported models](#supported-models)
>
> **<img src="docs/icons/tablet-smartphone.svg" width="16" height="16" alt=""> Since 0.6.0: VulKara in the browser of your phone.** Watch your pictures, start new ones and share
> finished ones from an iPhone, iPad or another computer on your home network or over a VPN — encrypted (HTTPS) and
> behind an access token. Only your Mac computes. [Remote access](#remote-access-in-the-browser)

## <img src="docs/icons/sparkles.svg" width="22" height="22" alt=""> Coming next: your own characters

> [!IMPORTANT]
> **Create a character once – put them into any scene.** Face, hair, outfit and style stay the same in every picture:
> comic panels, anime shots, a whole story. Made and kept on your Mac, like everything else.
> Planned, no date yet – a [coffee](https://buymeacoffee.com/revil.0) helps it along.

<table>
<tr><td width="14%"><img src="docs/images/characters/mira.jpg" alt="Mira, the reference"></td><td width="14%"><img src="docs/images/characters/cafe.jpg" alt="Sketching in a café"></td><td width="14%"><img src="docs/images/characters/rooftop.jpg" alt="On a rooftop at sunset"></td><td width="14%"><img src="docs/images/characters/neon.jpg" alt="Neon street in the rain"></td><td width="14%"><img src="docs/images/characters/mountain.jpg" alt="Hiking at dawn"></td><td width="14%"><img src="docs/images/characters/anime.jpg" alt="As an anime character"></td><td width="14%"><img src="docs/images/characters/comic.jpg" alt="As a comic panel"></td></tr>
<tr><td><sub>Mira, the reference</sub></td><td><sub>Sketching in a café</sub></td><td><sub>On a rooftop at sunset</sub></td><td><sub>Neon street in the rain</sub></td><td><sub>Hiking at dawn</sub></td><td><sub>As an anime character</sub></td><td><sub>As a comic panel</sub></td></tr>
</table>

<sub>One character, seven pictures: the reference and six scenes, made with VulKara today (FLUX.2 klein with the reference picture on the Image page). The feature will make it a few clicks.</sub>

## Why VulKara

<table>
<tr>
<td width="33%" valign="top">

### <img src="docs/icons/monitor.svg" width="20" height="20" alt=""> Everything on the Mac
Pictures, videos, photo restoration and LoRA training run on the Apple GPU. Prompts and pictures never leave the Mac;
the network is only used to download runtimes, models and LoRA descriptions and to look for updates. Phone, tablet or a second computer reach
it over your own network, as a web UI in the browser.

</td>
<td width="33%" valign="top">

### <img src="docs/icons/boxes.svg" width="20" height="20" alt=""> Many models, one app
SD 1.5 / 2.x, SDXL (also Pony, Illustrious, NoobAI), SD 3.5, FLUX.1, FLUX.2, FLUX 3 Image Klein, Chroma, Qwen-Image,
Z-Image, Krea 2, Ideogram 4, ERNIE-Image, Anima, Lumina 2, Pony V7 (AuraFlow), MOSS-Image, Fibo 2.0 and Wan 2.2 video. Choose from a tested list, or import any model from Hugging Face, Civitai or a file.
The app speaks English, German, Spanish and Portuguese (Brazil and Portugal); a new language is a folder of JSON files.

</td>
<td width="33%" valign="top">

### <img src="docs/icons/cpu.svg" width="20" height="20" alt=""> Three engines
**Diffusers** (PyTorch on Metal), **MLX** (fast for FLUX, the only one for Krea 2, Ideogram 4 and FLUX 3) and, optionally,
**ComfyUI**. The app installs them itself and picks the right one for each model.

</td>
</tr>
<tr>
<td valign="top">

### <img src="docs/icons/paintbrush.svg" width="20" height="20" alt=""> Real tools
Inpainting with a brush, an endless canvas for outpainting, old-photo restoration with guard rails, a pose editor with
hands and faces, ControlNet, hidden-pattern illusions and 4× upscaling.

</td>
<td valign="top">

### <img src="docs/icons/layers.svg" width="20" height="20" alt=""> LoRAs, understood
LoRAs are found for each model on Civitai and Hugging Face, checked for the model they really belong to, converted
from ComfyUI, ai-toolkit and PEFT formats, described
with their makers' settings and example prompts, compared side by side, and trained from your own pictures.

</td>
<td valign="top">

### <img src="docs/icons/scale.svg" width="20" height="20" alt=""> Responsible by design
A prompt check and a result check that fails closed, the protection of minors always on, a consent question for edits
of real photos, AI marking in the metadata, and the licence of every model at a glance.

</td>
</tr>
</table>

## <img src="docs/icons/hard-drive.svg" width="20" height="20" alt=""> Big models on small Macs: SSD streaming

A model is usually only as large as the memory of the Mac allows. VulKara lifts that limit: when a model's denoiser does
not fit into memory, it is **streamed from the SSD block by block** while the picture is computed. Only the block that
is working stays in memory, the rest waits on the SSD — so the model keeps its full 16-bit quality instead of being
squeezed into 4 bits, and the text encoder can stay loaded for editing.

- **Automatic.** The memory plan of every import decides: a model that fits runs from memory, one that does not
  streams — VulKara no longer refuses a model just because the Mac is small. *Settings → SSD streaming* can also force
  it (*Always*) or turn it off (*Never*).
- **One-time preparation.** On the first streamed run the denoiser is cut into blocks and kept in a cache next to the
  model, or in a folder of your choice (*Settings → Folders → SSD streaming cache*).
- **As much in memory as fits.** The blocks the memory plan has room for stay in memory, spread over the model, and
  only the others are read in every step, two blocks ahead while the GPU computes. On a 16 GB Mac the kept blocks
  make room for the text encoder while a new prompt is read, and come back after. At 1024 px the reading is then
  almost entirely hidden behind the computing (FLUX.1 [dev]: 6 % waiting for the SSD, Chroma with guidance 1 %); at
  small sizes and on slow external disks the kept blocks save the most (FLUX.1 [dev] at 512 px: −13 %).
- **Step caching** (*Settings → Engine*, off by default): steps that barely change the picture reuse the step
  before, and a streamed model skips reading those blocks. FLUX.1 [dev], 28 steps: *Light* about 1.2× faster with a
  practically identical picture, *Strong* about 2×. It works for FLUX.1 with the Diffusers runtime.
- **Big text encoders too.** When even a streamed model does not fit because of its text encoder (Qwen-Image 2.1's is
  8.8B), that one is compressed to 4 bit once and cached — so Qwen-Image 2.1 runs on a 16 GB Mac.
- **GGUF files stream too.** A GGUF model (also an FP8 file, which becomes 8-bit GGUF on import) that does not fit is
  unpacked into the streaming cache once and then streams like a 16-bit one — a FLUX.1 [dev] fine-tune from FP8 runs
  on a 16 GB Mac.
- **MLX hands over to Diffusers.** MLX can not stream. When it has too little memory for a FLUX, FLUX.2 [klein] or
  Z-Image model, the job goes on with Diffusers, which streams it; the job, its pictures and the history say so.
  Krea 2, which only MLX runs, frees its text encoder after reading the prompt and so fits a 16 GB Mac as well.
  Tested on a Mac mini M4 with 16 GB: FLUX.1 [dev], Krea 2, Qwen-Image 2.1 and a FLUX.1 fine-tune from Civitai run.
- **Internal or external SSD.** Models and the streaming cache can live on the Mac's own SSD or on an external drive
  (USB or Thunderbolt), each in its own folder (*Settings → Folders*). Every step reads the whole model once, so the
  drive sets the pace: put the cache on the fastest one; on the internal SSD streaming is much faster than on a USB
  disk.

| Measured on an M2 with 24 GB (16 GB budget: *Memory kept free* 12 GB) | Peak memory | Time per picture |
| --- | --- | --- |
| FLUX.1 [dev] 16 bit on a **16 GB** Mac (plan) | 10 of 12 GB | runs streamed (in memory it would need 24 GB) |
| Qwen-Image 2.1 16 bit on a **16 GB** Mac (plan, text encoder 4 bit) | 9 of 12 GB | runs streamed |
| FLUX.1 [dev] 16 bit with a 16 GB budget, MLX hands over to Diffusers, cache on the internal SSD | 10 of 12 GB | ≈ 10½ min (1024 px, 12 steps, with the one-time preparation) |
| Krea 2 (RedCraft) with a 16 GB budget, MLX 4 bit, text encoder freed after the prompt | 12 of 12 GB | ≈ 8 min (1024 px, 8 steps) |
| Qwen-Image 2.1 16 bit, cache on the internal SSD | 16 of 19 GB | ≈ 44 min (1024 px, 40 steps) |
| Qwen-Image 2.1 16 bit, cache on an external USB SSD | 16 of 19 GB | ≈ 65 min |
| Qwen-Image 2.1 in memory, 8 bit, for comparison | 18 of 19 GB | ≈ 35 min |

Streaming trades speed for size: it makes models possible that would not run at all, at full quality. When a model
also fits compressed into memory, that is faster — VulKara picks it by itself.

## A tour

### The start

While the app loads, the splash shows the forge, where the rune hammer strikes pixels from the anvil and the valkyrie
is made of them. The name joins Vulcan, the Roman god of the forge, and Kára, a valkyrie of Norse legend. Then
**Start** lists three steps to the first picture (runtime, model, first picture), each ticked once done, and what is
installed.

![Start page](docs/screenshots/start.jpg)

### Text to image

Describe the picture, choose model, style and proportions, and press ⌘↩. The size tiles show the real proportions, the
guidance slider has a ruler, and up to three LoRAs can be added, each with its own weight. Switching the model keeps
steps, guidance, seed and size, to compare models with the same settings; **Model defaults** takes the new model's
suggestions, and a chosen sampler stays chosen (a model without it runs its default and says so).

![Text to image](docs/screenshots/text.jpg)

With **FLUX 3 Image Klein** the **Prompt upsampler** sits next to Generate: FLUX 3 is trained on full scene
descriptions, and Black Forest Labs' own upsampler (4 bit, MLX) first writes one from your short prompt – subject,
setting, light, camera, colours. It is downloaded once (5.7 GB), loaded only for the prompt (about 30 s), and the
description it wrote becomes the picture's note.

![Text to image with FLUX 3: the Prompt upsampler option next to Generate](docs/screenshots/generate_upsampler.jpg)

### Styles

Twenty styles in four groups (Photo, Illustration, Stylized, 3D & Craft), each with a preview.

![Styles](docs/screenshots/styles.jpg)

### Image to image and inpainting

<table>
<tr>
<td width="50%"><img src="docs/screenshots/image.jpg" alt="Image to image"></td>
<td width="50%"><img src="docs/screenshots/inpaint.jpg" alt="Inpainting"></td>
</tr>
<tr>
<td><b>Image to image</b>: the same motif, a new scene. <b>Change</b> sets how far the result may move away from the picture; FLUX.2 and Qwen-Image 2.1 take the picture as a reference instead.</td>
<td><b>Inpainting</b>: paint over the part that is to change, with brush, eraser and undo; the rest stays untouched.</td>
</tr>
</table>

<table>
<tr>
<td width="50%"><img src="docs/images/lighthouse.jpg" alt="Lighthouse"></td>
<td width="50%"><img src="docs/images/lighthouse_snow.jpg" alt="Lighthouse in snow"></td>
</tr>
<tr>
<td align="center"><sub>Text to image, style Cinematic</sub></td>
<td align="center"><sub>Image to image, change 0.6: <i>the same lighthouse in a snow storm</i></sub></td>
</tr>
</table>

### AI Canvas

An endless surface: place pictures, move the frame half over the edge, and Generate continues the picture. Paint a
mask to repaint a part. The panel always says what will happen.

![AI Canvas](docs/screenshots/canvas.jpg)

### Restore old photos

Colour cast and contrast corrected without a model; dust and thin scratches found and filled (LaMa), eyes and mouth
left alone; soft detail rebuilt by Real-ESRGAN and blurred faces restored by
CodeFormer (the faces shown as frames you can move); scratches, creases, spots and holes repaired by a FLUX.2 model
held to guard rails, which also repaints soft clothing and backgrounds while the faces stay the photo's own;
black-and-white photos coloured by DDColor, which adds colour only. A preview of a part with a compare slider (the
change left of the line, the original right), the result at the photo's size or twice that, templates for the usual
kinds of old photos, and your own templates.

![Restore](docs/screenshots/restore.jpg)

### Video, upscale, pose and illusion

<table>
<tr>
<td width="50%"><img src="docs/screenshots/video.jpg" alt="Image to video"></td>
<td width="50%"><img src="docs/screenshots/upscale.jpg" alt="Upscale"></td>
</tr>
<tr>
<td><b>Image to video</b> with Wan 2.2: a start picture and a description of the movement, 1–5 seconds at 480p or 720p.</td>
<td><b>Upscale</b> 2× or 4× with Real-ESRGAN, which adds detail instead of blur.</td>
</tr>
<tr>
<td colspan="2"><img src="docs/screenshots/enhance.jpg" alt="Enhance"></td>
</tr>
<tr>
<td colspan="2"><b>Enhance</b>: photo tools with small models — sharpen (NAFNet), denoise (SCUNet), upscale with
detail (SwinIR), remove JPEG artefacts (FBCNN), remove the background (BiRefNet) and select objects with clicks
(SAM 2.1), whose selection can go straight to Inpaint as the mask. Denoise, Upscale and the JPEG tool run from their
original weights on the GPU, the others as ONNX models on the CPU. All free for commercial use, downloaded once at a
checked version; other photo models (.pth, .safetensors, .onnx) can be imported.</td>
</tr>
<tr>
<td><img src="docs/screenshots/pose.jpg" alt="Pose editor"></td>
<td><img src="docs/screenshots/illusion.jpg" alt="Illusion"></td>
</tr>
<tr>
<td><b>Pose editor</b>: OpenPose skeletons with hands and faces, templates, mirroring, and detection from a photo. Then <i>Use in Text to image</i>.</td>
<td><b>Illusion</b>: hides a spiral, a pattern, a word or a logo in a picture.</td>
</tr>
</table>

### LoRAs and training

<table>
<tr>
<td width="50%"><img src="docs/screenshots/lora.jpg" alt="LoRAs"></td>
<td width="50%"><img src="docs/screenshots/training.jpg" alt="Training"></td>
</tr>
<tr>
<td><b>LoRAs</b>: trigger words, the makers' description and recommended settings, example prompts, a usage guide, training data, and a strength comparison (same seed, several strengths, optionally a second LoRA). LoRAs can be baked into a model of their own, and SD 1.x / SDXL models exported as one checkpoint for other apps.</td>
<td><b>Training</b>: a new LoRA from 10–30 of your own pictures, on SDXL, FLUX.2 [klein] or Krea 2, with a live loss curve.</td>
</tr>
</table>

Every LoRA is checked for the model it was made for: its layers first, then its metadata, then what its source page
says. A LoRA that tells nothing is refused instead of being filed as SDXL; FLUX.2 [klein] 4B, 9B and [dev] are kept
apart; and a LoRA of which fewer than 90 % of its layers fit the chosen model is stopped with a clear message.

### Models

<table>
<tr>
<td width="50%"><img src="docs/screenshots/models.jpg" alt="Installed models"></td>
<td width="50%"><img src="docs/screenshots/lora_finder.jpg" alt="LoRAs for a model"></td>
</tr>
<tr>
<td><b>Installed</b>: image models, video models and LoRAs, each kind in its own tint, with the memory each needs.</td>
<td><b>LoRAs for a model</b>: LoRAs made for exactly this model's base on Civitai or Hugging Face, with preview, licence line and <b>Install</b>.</td>
</tr>
<tr>
<td><img src="docs/screenshots/models_recommended.jpg" alt="Recommended models"></td>
<td><img src="docs/screenshots/models_add.jpg" alt="Add a model"></td>
</tr>
<tr>
<td><b>Recommended</b>: a tested list with memory and download size for this Mac.</td>
<td><b>Add</b>: import from Hugging Face, Civitai, a file or a folder. A repository of single files (GGUF quantizations) lists its files to pick from.</td>
</tr>
</table>

Imports get sensible names (the repository's name when the file is called `model.safetensors` or the like), take files
another model already has instead of downloading them again, are compressed or streamed from the SSD when they do not
fit into memory, and show the memory they need before anything is downloaded.

### Tips & tricks

![Tips & tricks](docs/screenshots/tips.jpg)

Prompt help and guidelines in the app: anatomy, details, lighting, LoRAs, and what each model type wants, with the
model chosen on the Text page first, a search, copyable example prompts, and small pictures: a short against a
detailed prompt, a LoRA at rising weights, how strongly a pose picture steers the result, and one prompt across
model types, guidance values, seeds and steps.

### History, favourites and the large view

<table>
<tr>
<td width="50%"><img src="docs/screenshots/history.jpg" alt="History"></td>
<td width="50%"><img src="docs/screenshots/favorites.jpg" alt="Favorites"></td>
</tr>
<tr>
<td><b>History</b>: search, multi-select, move to Trash, and <i>Use these settings</i>, which restores everything, including the model.</td>
<td><b>Favorites</b>: the heart in the upper left corner of a picture marks it; the Favorites page shows only those.</td>
</tr>
</table>

Every result opens in a **large view in a window of its own**, with its own close button, also over the app in full
screen. Use ←/→ to browse, and send a picture on to image to image, inpainting, video or upscale.

![Large view](docs/screenshots/viewer.jpg)

### Remote access in the browser

Settings → **Remote access** serves VulKara to a browser on a phone, tablet or second computer in your home network or
over a VPN: see the status of your pictures, type in and start new ideas while you are out, and look through,
download or share finished pictures in the history. Only the Mac computes, and nothing goes to the internet.

- **Off by default.** Switched on, the settings show one link per network with the access token already in it, and a
  QR code to scan with the phone's camera. **Renew token** makes a new one at once.
- **Encrypted (HTTPS)** with a certificate authority of the Mac's own, installed once per device from a link in the
  settings (valid only for addresses in your local network). Plain HTTP can be chosen instead.
- **Only the pages for generating and watching:** Text, Image, Video, Illusion, Inpaint, Pose, LoRA, History,
  Favorites, Tips, Changelog. A browser can not change settings, install models or runtimes, or reach any file other
  than the pictures it is shown. On the phone, **Share** opens its share sheet and **Copy picture** its clipboard.
- The pages fit a phone screen, and each device keeps its own language.

<img src="docs/screenshots/settings_remote.jpg" alt="Settings → Remote access: the switch, HTTPS, the links with the access token and the QR code" width="720">

### Light or dark

The app follows macOS, or stays light or dark (Settings → Appearance). The screenshots here show the light mode.

### Settings, changelog, licences, about

<table>
<tr>
<td width="25%"><img src="docs/screenshots/settings.jpg" alt="Settings"></td>
<td width="25%"><img src="docs/screenshots/changelog.jpg" alt="Changelog"></td>
<td width="25%"><img src="docs/screenshots/licenses.jpg" alt="Licenses"></td>
<td width="25%"><img src="docs/screenshots/about.jpg" alt="About"></td>
</tr>
<tr>
<td><b>Settings</b>: runtimes, folders (also on external drives, including the SSD streaming cache), memory, SSD streaming, remote access, appearance, content, privacy, tokens in the keychain.</td>
<td><b>Changelog</b>: what changed from version to version, the installed one marked.</td>
<td><b>Licenses</b>: for every model, whether it and its pictures may be used commercially.</td>
<td><b>About</b>: what runs where, licence requirements, content measures. <b>Hardware</b>: chip, cores, unified memory and the Metal budget, a resource monitor (memory of VulKara and its engines, CPU and GPU load, SSD streaming caches), and the guard rails; the same figures sit as chips in the status bar.</td>
</tr>
</table>

## How the pipelines work

What happens between pressing **Generate** and the finished picture, page by page, with diagrams: the way of a job
through the queue, the memory plan, text and image to image, inpainting, AI Canvas, ControlNet and pose, illusion,
video, upscale, restore, LoRAs, model import and privacy. They are in their own document:
**[How the pipelines work](docs/PIPELINES.md)**.

## Quick start

1. Download the DMG of the [latest release](https://github.com/revil-O/VulKara/releases/latest), open it and drag
   VulKara into *Applications*. It is signed and notarized by Apple.
   Or with [Homebrew](https://brew.sh): `brew install --cask revil-O/tap/vulkara` (updates with `brew upgrade --cask vulkara`).
2. Open VulKara and go to **Settings → Runtimes**. Install **Diffusers (Apple GPU)** (about 0.9 GB).
3. Go to **Models → Recommended** and install a model, for example *SDXL 1.0* (16 GB of memory or more) or *Stable
   Diffusion 1.5* (8 GB).
4. Go to **Text**, describe a picture and press **⌘↩**.

The [user guide](docs/USER_GUIDE.md) describes every page and setting; it is also in [German](docs/de/USER_GUIDE.md),
[Spanish](docs/es/USER_GUIDE.md) and Portuguese ([Brazil](docs/pt-BR/USER_GUIDE.md), [Portugal](docs/pt-PT/USER_GUIDE.md)).
The language of the app is chosen at the top right of the Start page or in **Settings → Appearance → Language**
(*System* follows macOS). To add a language: [Translating VulKara](docs/TRANSLATING.md).

## Requirements

| | Minimum | Recommended |
| --- | --- | --- |
| Mac | Apple silicon (M1) | M2 Pro / Max or newer |
| Memory | 8 GB (SD 1.5) | 24–32 GB or more (SDXL, FLUX, Qwen-Image, video); larger models stream from the SSD on smaller Macs |
| Storage | 5 GB | 50 GB or more for several models; external drives work; a fast internal SSD for the streaming cache |
| System | macOS 14 (Sonoma) or newer | current macOS |

Nothing has to be installed first: no Python, no Xcode command line tools, and Homebrew only if you install with it. VulKara downloads its own
Python (with uv, at a checked version) and only ready-built packages into its runtimes folder; the Python of the
Mac is never used or changed.

## Supported models

| Family | Runtime | Pictures | Inpaint | ControlNet | LoRAs | Training | Commercial use |
| --- | --- | :-: | :-: | :-: | :-: | :-: | --- |
| Stable Diffusion 1.x / 2.x | Diffusers | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> (1.5) | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | yes (Open RAIL) |
| SDXL (incl. Turbo, Pony, Illustrious, NoobAI) | Diffusers | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | yes (Open RAIL++) |
| Stable Diffusion 3.5 | Diffusers | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | below USD 1 M revenue |
| FLUX.1 [schnell] / [dev] | Diffusers, MLX | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | schnell yes; dev: model non-commercial |
| Chroma (Chroma1-HD / Base / Flash – Flash about 7 min per picture on an M2, fine-tunes) | Diffusers | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | yes (Apache 2.0) |
| FLUX.2 [klein] 4B / 9B, [dev] | Diffusers, MLX ([klein]) | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> ([klein]) | 4B yes; 9B and dev: model non-commercial |
| Qwen-Image | Diffusers | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | yes (Apache 2.0) |
| Qwen-Image 2.1 (GGUF or repository) | Diffusers (diffusers 0.41: Settings → Runtimes → Update) | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | no (research licence) |
| Z-Image Turbo / Base (Turbo about 5½ min per picture on an M2 with MLX) | Diffusers, MLX | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | yes (Apache 2.0) |
| FLUX 3 Image Klein (6 / 8 bit MLX or Black Forest Labs' files; about 6 min per picture on an M2; optional prompt upsampler) | MLX | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | model non-commercial; pictures below USD 5 M revenue |
| Krea 2 | MLX | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | below USD 1 M revenue |
| Ideogram 4 | MLX | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | no |
| Anima | ComfyUI | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | model non-commercial, pictures free |
| Lumina 2 (NetaYume, Neta Lumina) | ComfyUI | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | yes (Apache 2.0) |
| ERNIE-Image (Turbo 8 steps, text in pictures) | MLX | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | yes (Apache 2.0) |
| AuraFlow, Pony V7 (GGUF; the repositories on Diffusers) | ComfyUI, Diffusers | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | with conditions (Pony License) |
| MOSS-Image (text in pictures; 50 steps or the 8-step DMD version, about 4½ min per picture on an M2) | ComfyUI | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | | | | yes (Apache 2.0) |
| Fibo 2.0 Edit Turbo (edits a picture by instruction, also inside a mask or up to four together; 4 steps, about 6 min per edit on an M2; ComfyUI from 20 GB, MLX on 16 GB) | ComfyUI, MLX | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | <img src="docs/icons/check.svg" width="14" height="14" alt="yes"> | | | | no (CC BY-NC 4.0) |
| Wan 2.2 5B / 14B (video) | ComfyUI | video | | | | | yes (Apache 2.0) |

Models are never part of the app. They are downloaded on demand from Hugging Face or Civitai, and their licences are
shown on the Licenses page. LoRAs of families without a runtime in the app (HiDream, Hunyuan …) are shown
under their family, but no page offers them.

## For developers

```bash
npm install
npm run dev          # the app with live reload
npm run start:app    # the built app as "VulKara" (dist/dev/VulKara.app)
npm run typecheck
npm test
node tools/release.mjs   # signed and notarized DMG (notarytool profile "VulKara")
```

Architecture, engine protocol, migrations, release and the clean check: see the
[developer guide](docs/DEVELOPMENT.md). The pipelines of every page with diagrams: [How the pipelines work](docs/PIPELINES.md).
Concepts for what comes next: [Characters](docs/concepts/CHARACTERS.md).

## Licence

VulKara is © Oliver Schmidt and released under the [PolyForm Noncommercial License 1.0.0](LICENSE). You may use,
study, share and change it for any noncommercial purpose: private use, research, teaching, nonprofit organisations.
Commercial use is not allowed. Earlier versions keep the licence they were released under (see the
[changelog](CHANGELOG.md)). Third-party components and their
licences are listed in [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt). Models and runtimes are not part of the
app; they keep the licences of their publishers, listed in the app under **Licenses**.

VulKara costs nothing. If it is useful to you, you can support its development on
[Buy Me a Coffee](https://buymeacoffee.com/revil.0). The source code is on [GitHub](https://github.com/revil-O/VulKara).
