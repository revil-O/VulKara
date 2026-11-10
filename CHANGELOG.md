# Changelog

## 0.8.1 – 2026-11-10

- **Fixed:** a model card that only gives advice after "Negative:" no longer becomes the negative prompt (Juggernaut
  XL: "Start with no negative, and add afterwards the Stuff you don´t wanna see"); Model defaults left it in the field.
  Installed models lose it once at the first start after the update, while it is still the maker's (the manifest
  before is kept as `model.json.bak`; models on a drive that is not connected are cleaned at a later start). A
  negative prompt already in the field stays until Model defaults is clicked again. On Text to image and the other pages the Generate
  button stays on the right when the row under the prompt wraps (longer languages).
- **The Edit, View and Window menus in the app's language.** Electron's own labels for them are English only; the
  entries keep their roles, so copy, paste and the shortcuts work as before. The View menu of the released app no
  longer offers Reload (it dropped what was typed or painted) and the developer tools; zoom and full screen stay.

## 0.8.0 – 2026-11-09

- **App menu, menu bar icon and Monitor.** VulKara has its own app menu in five languages (Settings… with ⌘, ,
  Monitor). Closing the window no longer ends the jobs: VulKara keeps running with an icon in the menu bar that shows
  the running job, its progress and how many wait; Quit (⌘Q or the icon's menu) ends it and its engines. With remote
  access on, the remote web UI stays reachable until then, and the icon's menu says so. **Monitor**
  shows the running job against its memory plan (memory with the GPU's share, peak, swap added) and, on the Mac mini
  the measurements were made on, against the measured time and memory of its model; below it this Mac's CPU, GPU and
  memory with the last minutes. The engines now report their plan when a job starts.
- **NetaYume v4 and other ComfyUI models on 16 GB: the text encoder is freed before the picture model loads.** As the
  memory plan counts it: ComfyUI had kept it while more than the memory kept free was left. NetaYume v4 on a Mac mini
  M4 16 GB now 9.2 instead of 10.5 GB, swap at most 0.4 instead of 2.4 GB, the same picture (identical pixels at the
  same seed), under 1 % slower (MEASUREMENTS 7bt). Not with LoRAs, AuraFlow/Pony V7 or Fibo 2.0.
- **Z-Image, ERNIE-Image and FLUX.2 [klein] on MLX load faster after their first start.** The quantized model is saved
  next to it once (`mlx_q8`/`mlx_q4`, Z-Image Turbo about 10 GB), as for Krea 2 and Ideogram 4: the first picture
  of Z-Image Turbo 188 instead of 214 s (10 instead of 30 GB read), ERNIE 252 instead of 273 s, klein 4B 62 instead
  of 76 s (MEASUREMENTS 7bt). A prompt encoded before does not read the text encoder at all: Z-Image Turbo's
  first picture 180 s, 9.0 instead of 12.0 GB, no swap on a Mac mini M4 16 GB (MEASUREMENTS 7bu).
- **Diffusers: 8 and 4 bit models hold less memory after loading.** Their GGUF copy is read as views of the file
  instead of a copy of every tensor, which the process kept: FLUX.2 [klein] 9B about 3 GB less right after loading
  and about 6 s faster per picture with a new prompt, SD 3.5 Medium's peak back inside its plan (MEASUREMENTS 7bv).
  A new prompt still swaps on a 16 GB Mac while a large text encoder loads (klein 9B, SD 3.5).
- **Icons from @lucide/vue.** lucide-vue-next is deprecated by its makers; the same icons now come from its successor
  (@lucide/vue 1.70.0, ISC). One icon looks a little different: rotate-3d, redrawn by Lucide.
- **User guide, Privacy: which services VulKara contacts and when** (Hugging Face, Civitai, GitHub, PyPI); no prompt,
  picture or path is sent, and there is no telemetry.
- **Fibo 2.0 edits (MLX) on 16 GB: about 2.5 GB less.** The transformer is read only after the prompt and the picture
  to edit are encoded: 11.0 instead of 13.5 GB, swap 1.6–2.0 instead of 2.8–3.3 GB on a Mac mini M4, the same
  pictures (MEASUREMENTS 7bx).
- **Fixed:** Stop while a model loads no longer deletes its 8/4 bit text encoder copy (it was quantized again at the
  next job). A disk without room for a model's 8/4 bit copy now says how many GB are missing. The old Quanto copies of
  a model part (8 and 4 bit) go once its GGUF copy is written. Streaming files are written whole or not at all. With
  Fast on (FLUX.1 [dev]), a third LoRA is no longer dropped silently for Turbo-Alpha: the page says so. Restore offers
  the consistency LoRA only for FLUX.2 [klein] 4B. Prompt from picture waits while a runtime installs or a model
  exports. Models that no longer stream on a 16 GB Mac (now a 4 bit copy in memory) leave their SSD streaming cache
  behind (about twice the model's size, in the model's folder or in the folder set in Settings → Folders → SSD
  streaming cache); it can be deleted by hand, the model writes it again if it ever streams.
- **Benchmark: New prompt per picture.** Each picture gets a number added to its prompt, so every one encodes it as a
  changed prompt does; before, the pictures after the first took the encoded prompt from the cache.
- **Prompt from picture (Image to image).** A button next to the prompt writes a prompt for the chosen picture:
  subject, setting, light, colours, style and camera in one English paragraph, to change before you create.
  Qwen3-VL 2B Instruct (Qwen, Apache-2.0) does it on the Mac, downloaded once as a helper model (4.1 GB, pinned) and
  freed again: about 15 s and 5.3–6.1 GB on a Mac mini M4 16 GB; the loaded picture model is freed for it, the
  button waits while a job runs, and Cancel stops it. 8 bit was 5–6 times slower and saved no memory at the peak, so
  it runs in 16 bit (MEASUREMENTS 7br). Not in the remote web UI.
- **Inpainting with FLUX.1 [dev] or [schnell]: a note next to the model.** Neither was trained to paint into a mask,
  so a faint outline of the painted part can stay (MEASUREMENTS 7bf); the page now says so and points to FLUX.1 Fill
  [dev], which blends it in.
- **FLUX.1 GGUF models that stream on 16 GB no longer swap while they are prepared.** Unpacking the GGUF file for
  SSD streaming read the whole file into memory (14.2 GB for FLUX.1 [schnell] in 8 bit, up to 6.7 GB swap); it now
  reads it mapped from the disk: 4.9 GB, the same blocks byte for byte. That unpacking also ran far more often than
  once: the engine timed at every start whether bfloat16 is slow, the timing flipped on the M4, and every flip wrote
  the stream cache (22 GB) and the 8 bit text encoder again in the other number format. The check now runs once per
  Mac and is kept, so the caches stay and the same seed gives the same picture.
- **Restore: a note for black-and-white and sepia photos with FLUX.2 [klein] 9B.** 9B tints such a photo when it
  repairs the whole of it; the Restore page now says so next to the model and points to FLUX.2 [klein] 4B with the
  consistency LoRA, which keeps the colour. The photo is recognised the way the engine does (spread of its LAB colour).
- **Restore recognises black-and-white photos again.** The page could not read the photo's pixels (it was loaded
  without CORS), so "This photo is black and white" never showed and colouring was not ticked for such a photo.
- **Security updates (big change): Electron 44.10.2, Python 3.11.18, uv 0.13.7, Pillow 13, new certificates.**
  - Electron 44.5.1 → 44.10.2 (Chromium 152.0.7977.169). It blocks the compromised eMudhra intermediate certificates
    in Chromium and in Node's `tls`, `https` and `fetch` (GHSA-jr5w-w6x2-84p9, high): before, someone who could
    intercept the network could pose as Hugging Face, Civitai or the update check.
  - The Python runtimes (Diffusers, MLX, ComfyUI): certifi 2026.10.23 drops the emSign root certificates with
    compromised intermediate keys (critical); Pillow 12.3.0 → 13.0.0 in Diffusers and ComfyUI fixes 41
    advisories in its picture decoders (crafted TIFF, BMP, PDF and other files could hang or crash the engine; no
    fix for 12.x); filelock 4.2.9 and setuptools 84.2.1 fix lower ones. The runtimes update themselves to the new
    lock at the first start.
  - uv 0.12.23 → 0.13.7: uv downloads every Python package and Python itself, and before 0.13.4 its own certificate
    store still trusted the emSign root of the compromised keys (GHSA-hq85-5cpj-mr62, critical).
  - Python 3.11.17 → 3.11.18 in every runtime: its ssl rejects the compromised eMudhra intermediate certificates, and
    it fixes Expat and tarfile flaws. A runtime on an older Python is made again at the first start; its packages
    come back from the local cache (same versions, nothing new).
  - ComfyUI 0.43.0 → 0.44.0 (no security fix of its own; only its frontend, template and docs packages move).
  - Building: Vite 7.3.7 (two dev server advisories), fast-uri, electron-builder 26.18.0. Left: minimatch inside
    electron-builder (a slow build from crafted glob patterns; VulKara's patterns are its own, the fix needs
    minimatch 11, which electron-builder does not take yet).
- **Inpainting: nothing of the old picture shows through any more.** Inside the painted part 15 % of the old picture
  stayed on average, up to 40 %: a removed house still showed half-transparent. The soft edge now lies outside the
  painted part (all engines).
- **Inpainting: no lighter disc around what was added.** Models not trained for masks (Z-Image, FLUX.1 [dev],
  Juggernaut XL …) shift the tone of the whole repainted part, so an added seagull sat in a lighter or darker disc.
  The tone offset is now measured along the edge and taken out inside (all engines); SDXL Inpainting runs at strength
  0.99 at most, as its card says (a dark noisy disc at 1).
- **FLUX.2 [klein] inpainting plans its memory right.** Its inpainting passes the picture along as reference tokens: the
  plan counts them now (9B took 12–14 GB against a plan of 9.8).
- **Every FLUX.2 edit with a picture plans its memory right.** Editing and Restore's repair take the picture along as
  reference tokens too; the plan counted them only for inpainting (Restore with klein 9B took 12.5–13 GB against 9.8).
- **Restore: consistency LoRA for FLUX.2 [klein] 4B.** A new option, on by default: lrzjason's LoRA (Apache-2.0,
  0.4 GB, downloaded once as a helper model) keeps the repair closer to the photo; scratches the repair left as light
  streaks are gone. About 1.7 GB more memory while the model works (11.7 GB on a 16 GB Mac mini).
- **Quantized models no longer depend on Diffusers' Quanto backend**, which Diffusers drops with version 1.0. A model
  in 8 or 4 bit on the Diffusers runtime is written once as a GGUF copy next to it (in a process of its own, tensor
  by tensor) and loaded from there: about as fast per step, 0.4–1.3 GB less in a probe, loaded in seconds. Its old
  copy is removed on the way; the first use of each model writes the new one once (FLUX.2 [klein] 9B in 4 bit about
  2 minutes on a Mac mini). ControlNets in 8 bit are quantized by optimum-quanto itself, text encoders stay as they are.
- **Image to image: keep the picture with FLUX.2 [klein] 4B.** A new option, off at first: the consistency LoRA of
  Restore at half strength changes only what the prompt asks for (a snowy night on the same coast, a red coat with
  nothing else changed); without it klein paints the picture anew. A strong change of style comes out lighter. About
  0.3 GB more memory (10.1 GB on a 16 GB Mac mini).
- **LoRAs that mix two layer namings load.** Some files name part of their layers `lora.down/up` and the rest
  `lora_A/B`; only the second part loaded and the LoRA was refused ("only 77 % of its layers found their place").
- **Fibo 2.0 edits on MLX plan their memory right.** An edit (masked or not) took 13.2–13.4 GB on a 16 GB Mac mini
  against 11.5 planned: the picture goes along through every step. The plan counts it, so a shortage is noted.
- **FLUX.1 Fill [dev] in the recommended models.** The 4 bit GGUF (needs a Hugging Face token); on a 16 GB Mac its
  transformer makes room while a new prompt is encoded (a new prompt took 13.6 GB before, now 11 GB).
- **FLUX.1 Fill [dev] paints.** It computed in float16 on Macs where bfloat16 is slow and overflowed at 1024 px:
  the painted part came out black or flat brown. It computes in bfloat16 now.
- **T5 in 4 or 8 bit really is smaller.** The quantized T5 of FLUX.1, Chroma and SD 3.5 left its wo layers (a fifth of
  its weights) in 16 bit: the 4 bit one took 5.2 GB, now 4.0. They are quantized in 8 bit (the
  embeddings stay as close as before); a cached T5 is made again once (a few minutes). FLUX.1 Fill on a 16 GB Mac
  with a new prompt: 12 instead of 13.6 GB.
- **A gated model without a token says so.** Importing a model whose base is gated on Hugging Face (FLUX.1 Fill [dev])
  without a saved token asked to accept the licence, also when it was accepted; it now asks for the token in Settings
  → Access tokens.
- **Inpainting with an empty prompt removes.** Asked for nothing, every model invented something where the painted
  part was (a woman, a scaffold, the house again). LaMa now fills it from its surroundings first and the model only
  refines that; the prompt field says so.
- **Models trained for inpainting.** SDXL inpainting checkpoints (*SDXL Inpainting* is in the recommended models, 6.5
  GB, about 1½ minutes per picture on a 16 GB Mac mini) and FLUX.1 Fill [dev] are recognised, and FLUX.2 [klein] 4B /
  9B can inpaint now (installed ones learn it at the next start).
- **Fast (8 steps) for FLUX.1 [dev].** FLUX.1 [dev] and its fine-tunes have an option *Fast (8 steps)* below Steps:
  alimama's Turbo-Alpha LoRA makes the picture in 8 instead of 20–50 steps (guidance 3.5, as its card says). On a 16 GB
  Mac mini a 1024 px picture took 4:18 instead of 11:04 min with 28 steps, the quality held. The LoRA is downloaded once
  into the LoRAs with the button next to the option (694 MB, FLUX.1 [dev] non-commercial licence).
- **LoRAs on a model kept in 4 bit.** A LoRA on a model compressed to 4 bit (FLUX.1 dev on 16 GB since this version)
  stopped with "does not fit this model": the names of 4 bit weights were not recognised. Fixed.
- **FLUX.1 dev and FLUX.2 [klein] 9B on a 16 GB Mac: in 4 bit instead of streamed.** When a model fits neither in 16
  nor in 8 bit, it now keeps its denoiser in memory in 4 bit (compressed once and cached) before it streams 16 bit from
  the SSD. Streamed, each step read 16–28 GB from the SSD and waited for it: on the Mac mini FLUX.1 dev now takes 18.9
  s per step at 768 px instead of 34.4, FLUX.2 [klein] 9B 17.0 instead of 22.3; at 1024 px as fast as before, with
  nothing read from the SSD. *Always* under Settings → Engine still streams in 16 bit.
- **A model folder from another Mac is refused at once.** Importing a model's own folder in place took a folder that
  had been imported on another Mac as it was, reported it done, and the model could then not be used. The import now
  says why and what to do: import it again from its source, or import its weights folder.
- **History names the Enhance and Restore pages.** Their pictures showed the page's internal name.
- **Krea 2 on a 16 GB Mac: 3 GB less at the end of each picture.** Decoding the picture was its peak (14.3 GB, 6.6 GB
  above the model); it now decodes in smaller tiles on Macs with 16 GB: 11.3 GB, no visible seam.
- **Qwen-Image 2.1 on a 16 GB Mac without 7 GB too many.** On Macs that load the text encoder only to encode a new
  prompt, the pipeline still held it afterwards: Qwen-Image 2.1 kept its 9.2 GB text encoder next to the transformer,
  18.7 GB instead of the planned 11.9, with 11 GB moved to the swap. It is now let go after encoding: 9.9 GB while
  denoising. The one-time quantization of a model runs in a short-lived process of its own, so the 16 bit weights it
  loads go back to macOS when it ends.
- **The run time in History in its parts.** A picture's run time now shows, one below the other, what it spent
  loading the model and the prompt, its steps with the time per step, and decoding and saving, e.g. *2:48 min*,
  *loading and prompt 1:58 min*, *8 steps 39 s (4.93 s/step)*, *decoding and saving 11 s*. Before, only the whole time
  and the time per step were shown, which did not add up when the model was loaded first.
- **MLX models load part by part: Z-Image on a 16 GB Mac 7 times as fast.** mflux leaves the weights unread after
  loading, and the first step then read and quantized all parts at once: Z-Image Turbo peaked at 25 GB on a 16 GB
  Mac mini and took 2 minutes per step. The MLX engine now reads them one part after another right after loading:
  18 s per step at 12 GB, FLUX.2 [klein] 4B 11 s instead of 17 s at 7 GB instead of 11. The Mac stays usable while a
  picture runs (typing in Settings had stalled while it swapped).
- **16 bit only with room to spare.** The memory plan keeps a model in 16 bit only when 2 GB stay free under its
  budget, otherwise it takes 8 bit. AuraFlow on a 24 GB Mac had planned 16 bit 0.5 GB under the budget, and macOS read
  its weights from the disk again in every step: 78–81 s per step, now 46 s in 8 bit. Streamed models and a precision
  chosen by hand are not affected.
- **Chroma: short prompts no longer come out as noise.** diffusers 0.41 builds Chroma's prompt mask as 0/1 floats and
  hands it to the attention, which adds a float mask instead of applying it (huggingface/diffusers issue 12116; the
  fix was undone by a later rework), so the padding was attended and a two-word prompt gave a grid of noise on
  Chroma1-Flash. The engine now gives the pipelines' mask helper boolean masks, for the pipeline's own encoding,
  the staged one, cached embeddings, image to image and masked edits alike. Longer prompts keep their composition and
  move a little in detail.
- **Tips & tricks for ERNIE-Image, MOSS-Image, Fibo 2.0, FLUX 3 Image Klein, Anima, Lumina 2 and AuraFlow**, and a
  picture pair for every model type. Seven new groups from the makers' cards and guides: ERNIE's 8 steps, its prompt
  enhancer, dense text and its sizes; MOSS's 50 steps with CFG 3 against the 8-step version, line breaks in text, a layout as the prompt, the Destripe LoRA
  against stripes; Fibo's 4-step edits by instruction, masked edits, up to four pictures, caption-like prompts, sizes
  and LoRAs. Every model type now shows a plain prompt against the tip's prompt with the same seed (SD 1.5 keywords
  and negative prompt, SDXL at 512 and 1024 px, SD 3.5 sentences, FLUX.1 prose, FLUX.2 hex colors and quoted text,
  Chroma, Qwen-Image posters, Z-Image paragraphs, Krea 2 art direction, Ideogram typography, Wan motion as three
  frames of the five-second clip, ERNIE with and without the enhancer, MOSS words against a layout, Fibo before and
  after an edit). From the makers' cards for the later four: FLUX 3's 16 steps, its prompt upsampler and seeds;
  Anima's Turbo settings, lowercase Danbooru tags with the safety tag, artists with @; the Neta models' system prompt,
  40-50 steps and three languages; AuraFlow's 50 steps and Pony V7's tag template and character pattern. The helpers
  group shows a skin LoRA and an expanded prompt.
- **The memory note in two grades.** When less memory is free than a picture's plan needs, the job's note now says
  what to expect: up to 10 GB short, *macOS moves other programs to the swap, the picture is usually as fast* (measured:
  as fast up to 9.6 GB short, idle apps go to the swap); above that, *this picture may take many times longer* (14 times
  at 11.1 GB short). On a Mac with 16 GB or less the strong note comes from 4 GB short: what the other programs hold
  there is largely macOS itself and cannot move (the Mac mini M4 swapped at 6.3 GB short). A shortage within 2 GB, the
  noise of the free figure, gets no note.
- **LoRAs for Fibo 2.0.** A LoRA trained for Fibo 2.0 is recognised at import (its 3584-wide layers, the metadata, the
  Hugging Face bases briaai/Fibo-2.0 and Comfy-Org/Fibo-2.0) and loads on both runtimes: ComfyUI's repacked files fuse
  q, k and v and the feed-forward's w1 and w3, so a LoRA in diffusers' layout (ai-toolkit, peft) is fused once for them
  (the rank stacked, the hidden width padded as in the files), and one in ComfyUI's layout is split once for the MLX
  runtime (mflux maps diffusers' names). Fibo 2.0 on MLX takes LoRAs now too.
- **ERNIE-Image's prompt enhancer.** Baidu's own enhancer (the pe/ model of ERNIE-Image-Turbo, Ministral 3 3B,
  Apache-2.0) is a helper model now: with the option *Prompt enhancer* next to Generate it rewrites a short prompt into
  a rich description before the picture is made, the description becomes the picture's note, and the prompt and seed
  give the same description again. Downloaded once (7.7 GB) with the button next to the option or on the Models page;
  on a 16 GB Mac the image model is unloaded while it writes (about a minute on an M2; the description is written in
  English, Baidu's own instruction to the enhancer translated). Off, the prompt goes as written.
- **MOSS-Image: layouts, image to image and LoRAs.** A layout is the JSON that ComfyUI's *MOSS-Image Layout Prompt*
  node writes, pasted as the prompt (the guide shows the format with a poster); Image to image is offered for MOSS-Image
  (the picture is denoised from the chosen strength, as ComfyUI's documentation describes); and LoRAs made for
  MOSS-Image are recognised at import (ComfyUI's layer names, kohya's, the metadata, the Hugging Face bases) and
  loaded by ComfyUI onto the fused model files (MEASUREMENTS 7av).
- **Streamed models load from their cache alone.** A model streamed from the SSD was first loaded whole to check its
  cache; on an M1 or M2, which compute FLUX.1 in float16, that converted the whole transformer into memory (FLUX.1
  [dev]: 24 GB before the first step, swapping on a 16 GB Mac). The cache now also holds the weights outside the blocks,
  and a later load reads only those: FLUX.1 [dev] on a 16 GB budget prepares in 8 instead of 100 s and stays at 11 GB
  (MEASUREMENTS 7at). The first use of a model still loads it whole once.
- **ControlNets count in the memory plan.** A job with a ControlNet reported the plan without it (Juggernaut XL: 9.4 GB
  planned, 12.0 used), and the room for the ControlNet was judged with twice the model's activations where it takes a
  third: a 16 GB Mac refused SDXL with ControlNet Union at 1024 px although it fits in 8 bit. The plan now counts the
  ControlNet's weights and half the activations, through the encoding of a staged model too; the 16 GB Mac runs the
  job (planned 11.5 GB, used 11.6; MEASUREMENTS 7as).
- **Cancel ends a model load at once.** A picture cancelled while its model was loading on the Diffusers runtime went
  on until the load was done (Chroma1 Flash on a 16 GB plan: 62 s). The load now stops within a second, and the engine
  goes on with the next job (MEASUREMENTS 7ar). A stop while a step runs still ends with that step.
- **Streamed models hold less after the last step.** While a model is streamed from the SSD, the next blocks are read
  ahead; after the last step the two read ahead for a further pass stayed in memory until the next picture (0.85 GB
  on Qwen-Image 2.1). They are dropped now, before decoding: FLUX.2 [klein] 9B on a 16 GB plan reads 1.2 GB less per
  picture and holds 1 GB less afterwards (MEASUREMENTS 7ap).
- **New model: Fibo 2.0 Edit Turbo** (Bria AI, CC BY-NC 4.0) on the ComfyUI runtime: an 8B model that edits a picture
  by instruction (Image to image: *make it a snowy night*), only inside a mask (Inpainting, AI Canvas: the masked part
  is repainted, the rest stays pixel for pixel), and paints new pictures from text, with Qwen3-VL 4B reading the
  prompt and the picture. Up to four pictures in one edit: Image to image takes up to three more under **More
  pictures** (<image_2> to <image_4> in the prompt); the memory plan counts each further picture (2.2 GB on ComfyUI,
  0.5 GB on MLX), and with four pictures a step takes 3.5 to 4 times as long. 4 steps without guidance: about 6
  minutes per edit and 3 per new picture at 1024 px on an M2 with 24 GB. In Models → Recommended (13.6 GB download,
  transformer and text encoder in 8 bit, from Comfy-Org's files, no Hugging Face form needed). Computed in float16, 69
  instead of 111 s per step. An edit needs about 14.5 GB, so it is listed for 20 GB Macs and up; a 16 GB Mac is told
  before it starts. Fibo 2.0 Dev files are recognised as well (the maker's 50 steps with guidance 5): two passes per
  step, 72 s, about an hour per new picture and two per edit at 1024 px on an M2 with 24 GB. The Diffusers runtime's diffusers 0.41 only knew FIBO-Edit 1.5 (with SmolLM3), not Fibo 2.0. No LoRAs yet.
- **Fibo 2.0 on 16 GB Macs: *Fibo 2.0 Edit Turbo (MLX, 8 bit)*** in Models → Recommended (13.4 GB download,
  mflux-community's files): the same edits, masked edits and new pictures on the MLX runtime, at most about 11 GB (the
  text encoder only for the prompt), about 7 minutes per edit at 1024 px on an M2 with 24 GB.
- **MLX runtime on mflux 0.24.0** (was 0.23.0) with Pillow 13.0.0: needed for Fibo 2.0. The runtime updates itself at
  the first start; FLUX.1, FLUX.2 [klein], Z-Image, Krea 2, ERNIE-Image and FLUX 3 run as before.
- **New model: MOSS-Image** (OpenMOSS, Apache 2.0) on the ComfyUI runtime: a 5B model for text in pictures (English
  and Chinese), posters and layouts, photographs and anime, with Qwen 3.5 9B reading the prompt. In Models →
  Recommended as *MOSS-Image* (the maker's 50 steps with guidance 3, about 40 minutes per picture at 1024 px on an M2
  with 24 GB) and *MOSS-Image 8-step (DMD)* (lodestones' distillation merged in: 8 steps without guidance, about 4½
  minutes). Both download 13 GB (transformer in 8 bit, text encoder in 4 bit) and run on 16 GB Macs (8.4 GB at
  most; on a Mac mini M4: 37 s per step, 9.1 GB). Computed in float16, 48 instead of 73 s per step. Text to image for
  now; no LoRAs yet.
- **ComfyUI 0.43.0** (was 0.38.0): needed for MOSS-Image. The runtime updates itself at the first start; Anima,
  Lumina 2, Pony V7, Wan 2.2 and upscaling run as before.
- **ComfyUI models are planned with less memory on small Macs.** ComfyUI loads the text encoder and the model one
  after the other when memory is short, so the plan no longer counts both together: NetaYume v4 on 16 GB 8.9 instead
  of 11.6 GB (measured 8.7); MOSS-Image would otherwise have been refused on 16 GB.
- The benchmark names the bit size of files ComfyUI quantized itself (8 bit int8, 4 bit W4A8) and counts them by their
  size.
- **ComfyUI pictures say when memory is short**, as MLX pictures do: before each picture the engine compares the plan
  with the memory free at that moment (what ComfyUI's server already holds counts as free), and the job says how much
  was free and that the picture may be slow while macOS swaps. Checked with Fibo 2.0 and four pictures while 8 GB were
  held elsewhere: 7.0 GB free for 21.2 GB planned, 77 instead of 6 minutes.

## 0.7.11 – 2026-10-30

- **FLUX.2 [klein] 9B streamed on a 16 GB Mac stays within its memory plan.** The plan counts the model's large
  blocks in flight (27 % of the model instead of 15 %) and keeps fewer blocks on the GPU: at most 10.6–11.9 GB
  instead of 14.3 GB (planned 11.5 GB), about 5 % slower.
- **ComfyUI models need less memory on small Macs.** ComfyUI now drops the text encoder after the prompt is encoded
  when memory runs short (below what Settings keep free), instead of holding it through the whole picture: NetaYume v4
  9.2 instead of 14.1 GB; Pony V7 Q8_0 on a 16 GB Mac stays whole in memory instead of loading piece by piece from the
  SSD (47 instead of 65 s per step).

## 0.7.10 – 2026-10-30

- **Qwen-Image 2.1 on a 16 GB Mac without SSD streaming.** A model that does not fit beside its text encoder now runs
  in stages before it is streamed: a new prompt is encoded with the text encoder alone, then the model is loaded in 8
  bit; a prompt from the prompt cache needs neither. Qwen-Image 2.1: about as fast as streamed (1 830 s per picture at
  1024 px), at most 9.9–12.2 GB instead of 12.1 GB, and 20 GB read from the disk instead of about 380 GB per picture.
  Streaming in 16 bit stays available (Settings → Engine → *Always*).
- **The version in the title row of every page.** Beside Discord each page shows *v0.7.9* (a click opens the
  Changelog) or, when a newer version is out, *Update to version … available!*: a click brings back the card with
  **Update and restart**, also after **Later**. The Changelog page's button is now called **Check for update**.
- **Memory back to the Mac when idle.** After 10 minutes without a job (Settings → Engine: 5, 10, 30 or 60 minutes,
  or never) the engines free their loaded model; the next picture loads it again. Z-Image Turbo: 7.5 GB held before,
  1.1 GB after.
- **Pictures say that a click opens them.** Results on the pages and the picture in the History carry a see-through
  band along their bottom: *Click to show preview* (in light and dark, in all five languages; in the
  remote web UI *Click for the large view*). A picture's label and its (i) sit in that band.
- **Fixed:** the History hid the settings and prompts of the selected entry while its large view was open.
- **Run time in the History.** Every new entry keeps how long its job ran (loading included) and its seconds per
  step; the History shows them under *Run time*, so a picture that took much longer than the ones before stands out.
- **Streamed models stay in their memory when the GPU is busy.** A model streamed from the SSD let blocks pile up while
  the GPU was busy with other programs, each holding its weights: FLUX.2 [klein] 9B on a 16 GB plan rose to 19.6 GB
  and the Mac swapped. Now at most two blocks wait on the GPU: 14.3 GB, and the picture is faster (225 instead of 279 s).
- **Anima faster on the Mac.** ComfyUI ran Anima models in bfloat16, which MPS computes at half the speed of float16;
  they now run in float16 (MiaoMiao RealSkin at 1024 × 1536: 92 instead of 117–130 s per step on an M2).

## 0.7.9 – 2026-10-29

- **Prompt cache for MLX models too.** Z-Image, Krea 2 and Ideogram 4 on a 16 GB Mac load their text encoder only for
  new prompts; a prompt used before (also after a restart) now comes from the prompt cache on disk instead of loading
  the model again: Z-Image Turbo 64 s instead of 99 s per picture for a prompt used before, the same picture. A
  negative prompt or guidance changed for Krea 2 is encoded anew.
- **Prompt cache in the settings.** Settings → Privacy shows how much the encoded prompts take on disk, and **Clear**
  removes them.
- **The memory plan of streamed models counts the blocks kept in memory.** On a 16 GB Mac VulKara keeps some blocks
  of a model streamed from the SSD in memory and frees them only while a new prompt is encoded; the plan left them out
  while denoising (Qwen-Image 2.1: 9.1 GB planned, 12.1 GB used, now 11.8 GB planned). The warning about free memory
  and the room for a ControlNet next to such a model now go by the right figure.

## 0.7.8 – 2026-10-29

- **4 bit models start their work in seconds, not minutes.** Moving a part kept in 4 bit onto the GPU repacked every
  layer (about 20 s each): Qwen-Image 2.1 on a 16 GB Mac needed 43 minutes for its text encoder before each new
  prompt; now 29 seconds, with the same picture. All parts in 4 bit of the Diffusers runtime gain from it.
- **No more streaks in Qwen-Image pictures.** Its VAE decodes in tiles and blended them over only 64 px, which left
  faint vertical streaks in plain areas such as a sky. The tiles now overlap by 128 px and blend so that the edge
  pixels of a tile are not used; with room in memory the tiles are twice as large. About 30 s more per picture on a
  16 GB Mac.

## 0.7.7 – 2026-10-29

- **Updates from inside the app.** Once a day (Settings → Privacy, with the runtime check) and with **Look for an
  update** on the Changelog page, VulKara asks GitHub for its newest release. A newer one shows a card: **Update and
  restart** downloads it, checks its SHA-256 checksum, the version inside, the Developer ID signature of the releases and
  Gatekeeper, puts it in place of the app when VulKara quits and starts it; **What's new** opens the release notes,
  **Later** waits for the next version. Not while pictures are made or something is installed.

## 0.7.6 – 2026-10-29

- **Prompts kept on disk.** What the text encoder makes of a prompt is kept in the data folder (`prompt_cache`, up to
  2 GB, the least used go first). The same prompt again, also after a restart, needs no text encoder: Qwen-Image 2.1
  streamed on a 16 GB plan peaked 2.4 GB lower and did not load its text encoder; the picture is the same.
- **4 bit text encoders are quantized only once again.** Loading a text encoder kept in 4 bit made the compression
  library build a C++ part, which failed on every Mac; the cached copy was dropped and the text encoder compressed again
  on every start, hours for Qwen-Image 2.1 on a 16 GB Mac. The copy is now unpacked without it.

## 0.7.5 – 2026-10-28

- **ComfyUI switches memory mode cleanly.** When a job needs the other memory mode (a GGUF model streamed from the SSD
  after one held whole), the models of the previous job are unloaded before the new one starts, not after it; the
  benchmark names an FP8 model "16 bit (from FP8)", as the Mac computes it.
- **Remote web UI: imports.** Clearing finished imports and stopping one in the browser only reach the imports made
  from the web, not the Mac's own.
- **History: larger picture, buttons first.** The picture of the selected entry is twice as large (a portrait picture only as high as a square one), with its buttons under
  it: one below the other in the left third, the settings beside them, behind a line, and prompt and negative prompt under headings of their own. While the large view is
  open, the panel shows only the buttons. Going back to the main window closes the large views. The large view itself shows only its buttons, no prompt and no settings.
- **Stopping while SSD streaming is prepared.** A picture stopped while the model was being prepared for SSD streaming
  (or its GGUF file unpacked for it) went on until the preparation was done, 85 s in a test; it now stops at once.
- **FP8 ComfyUI models no longer stop on Macs short of memory.** Where a model in FP8 did not fit in 16 bit, ComfyUI
  kept it in FP8, which Apple GPUs cannot compute ("Undefined type Float8_e4m3fn" at the first step). It now stays in
  16 bit there, as on every other Mac.
- **Memory plans closer to what the models use.** SD 1.5's plan now matches the measurement at 512 and 1024 px, and
  whether SD 1.5 and SD 2 fit is judged at their own picture size (an 8 GB Mac keeps SD 1.5 in 16 bit). ComfyUI models
  now show their planned memory in the benchmark too.
- **ComfyUI models use less memory.** On the Mac ComfyUI computed attention in chunks; it now uses PyTorch's attention
  with the same padding of head sizes as the Diffusers runtime: Pony V7 up to 2.2 GB less, Lumina 2 (NetaYume) 1 GB
  less and 10 % faster per step, Anima unchanged in speed, Wan 2.2 videos 30 % faster per step. The pictures and
  videos stay the same.
- **SD 1.5 twice as fast with half the memory, large SDXL pictures four times as fast.** On Apple GPUs attention with
  a head size the fused kernel does not take (SD 1.5's 40) held the whole attention matrix: 3.5 GB more and 6 times as
  slow. The Diffusers runtime pads those heads to a size it takes (same picture) and no longer computes attention in
  slices on the Mac: SD 1.5 at 512 px 0.72 instead of 1.55 s per step and 3.7 instead of 7.3 GB, at 1024 px 4.8 instead
  of 9.4 s; SDXL at 2048 px 28 instead of 111 s per step and 12.1 instead of 17.4 GB.
- **The memory plan meets the free memory.** Every engine now measures its own peak per picture and the benchmark shows
  it beside what the memory plan expected. Measured on 14 models, MLX models used up to 4.2 GB more than planned: decoding
  the picture in one piece. The MLX plan counts it now, and before each picture the engine checks the memory free at that
  moment: if decoding in one piece does not fit, it decodes in tiles (no visible difference; FLUX.1 dev 18.1 GB down to
  13.0 GB, 46 s per step instead of 175 s on a Mac short of memory), and a picture still short of memory says in its job
  how much was free. Bit sizes do not change. The Diffusers runtime gives the memory of a model back right after
  changing to another one.
- **Z-Image on MLX fits 16 GB.** On a 16 GB Mac Z-Image swapped while it decoded the picture (MLX alone peaked at
  12.9 GB; the Mac mini took 93–104 s per step instead of about 30). It now loads in 8 bit, frees its text encoder after
  the prompt (the same prompt again needs no reload) and, like every MLX model on a Mac with 16 GB or less, decodes in
  tiles, as mflux's own low-RAM mode does: 8.8 GB at most.
- **MLX gives memory back.** MLX kept every freed buffer for reuse: after one FLUX.2 [klein] picture 9.9 GB of them
  beside 7.5 GB in use, enough to make a 24 GB Mac swap. The engine now keeps at most 1 GB of them and empties them
  after loading and after each picture (footprint 17.9 GB down to about 10 GB); the log says what each picture gave
  back.
- **Benchmark a model.** Hardware → Benchmark makes one to three pictures with a model's own settings, the same prompt
  and seed for every model, and shows the seconds per step, the whole picture, the most memory VulKara with its engines
  (with what the GPU holds) and the system used and the swap the picture added, and in a column of its own the
  phases the engine went through (handing over to Diffusers, preparing SSD streaming, quantizing, loading, generating)
  with their times, the bit size each part of the model ran in, what was read again meanwhile (from the disks, back
  from the swap) and the time the steps waited for blocks streamed from the SSD; one block per run. Stopping one picture
  stops the whole benchmark, and stopped runs leave the list. Each run notes the app version and the code state it was built from. *Copy as table* gives
  a Markdown table with the chip and its memory. The resource monitor shows the
  swap in use too.
- **Z-Image on MLX follows its own noise schedule.** mflux shifted Z-Image's steps by the picture's size; the MLX
  runtime now uses the fixed shift the model's configuration asks for (Turbo 3, Base 6), as the Diffusers runtime does.
  Pictures change slightly.
- **SDXL keeps its memory steady.** img2img and inpainting no longer move SDXL's VAE to 32 bit and back for every
  picture, which left 1.8 GB in the Metal cache until the model changed; the peak is 1.25 GB lower. A stopped or
  failed job now gives its memory back too.
- **AuraFlow repositories on the Diffusers runtime.** Models in the diffusers layout with AuraFlowPipeline
  (fal/AuraFlow-v0.3, the repository of purplesmartai/pony-v7-base, such folders) now import and run on the Diffusers
  runtime, in 8 bit or with the text encoder loaded per prompt on 16 GB. AuraFlow and Pony V7 LoRAs made for ComfyUI
  are converted to diffusers' names as they load. The GGUF files keep running on ComfyUI.
- **Enlarged pictures show their new size.** Upscale and the enlarging tools of Enhance kept the size of the picture
  they started from, so the viewer and the library showed it; the viewer now shows every picture's own size.
- **ComfyUI models in GGUF from the SSD.** Pony V7 and other ComfyUI models in GGUF that do not fit into memory
  beside their text encoder (Macs with 16 GB) keep only part of themselves in memory and read the rest from their file
  for each step: Pony V7 on 16 GB about 88 s per step instead of 225 s. Settings → Engine and memory → *ComfyUI: load
  GGUF models piece by piece from the SSD* (on by default) switches it off. The finders' cards count a Civitai GGUF
  by its file size, not as 16 bit.
- **Models in the remote web UI.** The browser now has the Models page: it chooses, finds (*Find models*, *Find
  LoRAs*) and installs models and LoRAs from *Recommended*, Hugging Face and Civitai. Adding the Mac's own files,
  renaming, exporting, removing and the helper models stay on the Mac; the Mac checks that a browser's import comes
  from Hugging Face or Civitai. A model's page opens in the browser, not on the Mac.
- **Installs need 50 GB free.** Models and LoRAs are only installed while the models disk has at least 50 GB free;
  with less, the import is refused and says how much is free, and the finders' cards say so before installing.
- **New model types.** *Lumina 2* on the ComfyUI runtime (NetaYume and Neta Lumina among the recommended; the
  system prompt the model expects goes before the prompt by itself, the anime fine-tunes use their own); *ERNIE-Image*
  (Baidu, Turbo in 8 steps, strong on text in pictures) on the MLX runtime, 4 or 8 bit, without the repository's 7 GB
  prompt enhancer; *AuraFlow / Pony V7* on the ComfyUI runtime from GGUF files, with prompts padded to 768 tokens as in
  Pony's own workflow. A GGUF transformer counts with its own size in the memory check. LoRAs of these families now fit
  their models.
- **Find models / LoRAs: Any base model.** The first entry of the base menu searches all of Civitai or Hugging Face;
  *Find models* starts there. Each card's check tells whether this Mac can run what it found.
- **Find models.** Next to *Find LoRAs*, *Find models* searches Civitai (checkpoints) and Hugging Face (fine-tunes)
  for models made from a base model, most downloaded first, and installs them through the downloads, with the same
  cards and adult filter. Each card shows the memory the model needs; one too large for this Mac is marked *SSD
  streaming* (it runs streamed from the SSD). The model check of *Add* marks such models the same way. A model the Mac
  can not compute (NF4, int4, nvfp4 …) shows why and can not be installed; *File formats* explains bf16, fp8, GGUF
  and the rest. The search answers are kept per language (licence lines no longer stay in the language of the first
  search). The base menu of both finders is sorted into the main model groups (Stable
  Diffusion, SDXL, FLUX, Qwen-Image, Z-Image, Krea · Ideogram · ERNIE, Anima · Lumina · Pony V7, Wan).
- **The sampler picker follows the model's maker.** When a model card names the sampler(s) it runs with, the picker
  now shows only those (plus *Default*, which is the recommended one). A model whose maker runs it with DPM++ only no
  longer offers Euler. Read at import; for models already installed, `python main.py maker_settings` reads the cards
  again. A card that names no sampler keeps the full list for its family.

## 0.7.1 – 2026-10-23

- Qwen-Image 2.1 from its repository no longer fails at the first step with "Cannot copy out of meta tensor" when
  its transformer comes from the quantized cache: what a model computes itself while it is built (Qwen-Image 2.1's
  rotary frequencies) now stays real; only the weights wait on the meta device for the cache.
- **Stable Diffusion 1.x fine-tunes no longer break faces and animals into coloured patches.** Without a chosen
  sampler they ran with PNDM, the scheduler the SD 1.x/2.x base configuration names; the base model hides its
  weakness, fine-tunes such as epiCPhotoGasm or animatrix do not. They now run with DPM++ 2M Karras, the default of
  the tools their makers use. A sampler chosen in the form stays as it is.
- **A model imported from a Hugging Face repository only takes over a file of another installed model when its
  content is the same.** Until now the same path and size were enough, so Stable Diffusion 3.5 Medium could get
  FLUX.1's VAE (both 167,666,902 bytes) and painted only a grid. Now the SHA-256 the Hub lists has to match as well;
  without one the file is downloaded. A Stable Diffusion 3.5 imported next to FLUX.1 should be imported again.
- epiCPhotoGasm is no longer among the recommended models: the copy offered (Yntec/epiCPhotoGasm) is a re-upload, not
  the maker's file. The original is on Civitai (civitai.com/models/132632) and can be imported by its link.

## 0.7.0 – 2026-10-22

- **FLUX 3 Image Klein** (Black Forest Labs, MLX runtime): text to image and edits with the input picture as a
  reference, 16 steps without guidance (Base: 50 steps with guidance 3.5). It imports from Black Forest Labs' repository
  (18.9 GB of it are downloaded, about 19 GB of memory) or from the MLX repositories in 6 bit (8.4 GB) and 8 bit
  (9.6 GB), which run on a 16 GB Mac: when the model's parts do not fit together, the prompt is encoded before the
  transformer is loaded (6 bit at most 8.5 GB in a 16 GB budget). LoRAs for it come from Hugging Face and Civitai in
  Black Forest Labs', diffusers' and kohya's names. About 6 minutes per picture at 1024 px on an M2 with 24 GB.
- **Prompt upsampler** for FLUX 3 (Text to image, next to Generate): Black Forest Labs' own model (4 bit) writes the
  full scene description FLUX 3 is trained on from a short prompt, in about 30 seconds, and the description becomes
  the picture's note. It is downloaded once (5.7 GB, checked against pinned checksums) with the button next to the
  option or on the Models page, and freed after each prompt; the MLX engine itself still never reaches the network.
- The MLX runtime gets mflux 0.23, flux3-mlx 0.1 and mlx-lm 0.32 (and MLX 0.32.4), tested with every MLX model family,
  LoRAs, the 16 GB budget and LoRA training; an installed MLX runtime is brought to this set at the first start.
- **VulKara needs macOS 14 (Sonoma) or newer.** The runtimes' packages (PyTorch, MLX, ONNX Runtime) exist from macOS 14
  on, so on macOS 13 no runtime could be installed even though the app started; the app and the Homebrew cask now
  say so before the download.
- A LoRA's weight steps by a tenth with the − and + next to it, also in the remote web UI on an iPhone or iPad, where
  a number field has no arrows.
- A LoRA weight that stayed on the CPU no longer stops a picture at its first step with "tensors on two devices"
  (seen once with two LoRAs on a FLUX model): every weight is brought onto the GPU before the first step, and the log
  names any that were not.
- Tips & tricks shows every small picture at the same size; a long caption ends with "…" instead of widening its
  picture.

## 0.6.0 – 2026-10-22

- **Share** and **Copy picture** in the history and the large view: macOS's share menu (Mail, Messages, AirDrop,
  WhatsApp, Telegram and every app that offers itself there) and the picture on the clipboard, to paste into Signal,
  Threema or any other app. In the remote web UI they open the phone's own share sheet and clipboard, when the page
  is loaded over HTTPS.
- The LoRA page keeps its family chips and the search at the top while the cards scroll under them, as the Models
  page does.
- **Remote access: VulKara in a browser on your local network.** Settings → Remote access serves the generating and
  watching pages — Text, Image, Video, Illusion, Inpaint, Pose, LoRA, History (view, favourite, delete), Favorites,
  Tips, Changelog — to a phone, tablet or second computer, behind a random access token shown as a link and a QR code
  (**Renew token** replaces it; the port defaults to 8787, the next free one if it is taken). Only this Mac computes
  and only the local network is used: a browser cannot change settings, install models or runtimes, or reach any file
  on the Mac other than the pictures it is shown. The pages are responsive, the status bar wraps to two lines on a
  narrow screen, and each device keeps its own language. Off by default; the connection is HTTPS with a certificate
  authority of this Mac's own (its certificate is installed once per device from a link in the settings; plain HTTP
  can be chosen instead), and macOS may need an incoming-connections allowance (System Settings → Network → Firewall).
- The sound after a finished queue is labelled *Play a sound when the queue is finished* (it plays once the whole
  queue is done, not after each job).
- **New licence: PolyForm Noncommercial License 1.0.0.** From this version on, VulKara may be used, studied, shared
  and changed for any noncommercial purpose (private use, research, teaching, nonprofit organisations); commercial use
  is not allowed. Versions up to 0.5.1 were released under the GNU Affero General Public License v3.0 or later and
  stay under it. Every source file names the new licence (SPDX), and CONTRIBUTING.md says on which terms contributions
  are taken.
- **A model brings the settings its maker recommends.** When a model card names them (the Hugging Face README, the
  Civitai description), the steps, guidance, sampler, sigma schedule and negative prompt of its maker are read while
  the model is imported and become the model's own defaults. The hint above the sliders names the sampler as well
  (*Its maker recommends the sampler DPM++ SDE Karras.*), and **Model defaults** sets all of it. A model whose card
  says nothing keeps the values VulKara holds for its family. For models already installed,
  `python main.py maker_settings` reads the cards again (`--dry` prints what would change); the look-up by the file's
  SHA256 only runs when hash look-ups are switched on in Settings.
- A job that names no sampler runs with the one its model's maker recommends instead of the pipeline's own.
- **SD 1.5 and SD 2 above 512×512** compute attention in slices: a 768×768 picture needs under 7.5 GB instead of
  16 GB, so a Mac with 16 GB no longer swaps (4.2 s a step instead of 20 s).
- Three Pose templates drew a limb where a body can not have one: in *Kneeling upright, hands in hair* a shin ended
  between the knees (a third lower leg in every picture), in two *Lying on the back* poses the raised knee lay across
  the other leg. A test now keeps every template free of both.
- The Pose editor brings the person inside the canvas when a template is applied or the canvas is resized; lying
  poses had reached out over the edge. Its hand and face rows use icon buttons and shorter names, so the choices stay
  readable in every language.
- The job bar keeps a minimum width for the job's name and cuts its text: a long name had shrunk the name to nothing
  and run over the progress bar and the status.
- A **Discord** button at the top right of every page opens the VulKara community (questions, ideas, pictures);
  *About VulKara* links it as well.

## 0.5.2 – 2026-10-21

- **Every package of the runtimes is locked to a tested version** — the direct requirements, everything they bring
  in, and ComfyUI's own packages. A fresh install or **Update** gets exactly the set VulKara was tested with, so a new
  release of any package can no longer reach a runtime unchecked (a fresh ComfyUI runtime would otherwise have got
  Pillow 13 and huggingface-hub 2). Newer versions come with an app update after they were tested.
- Pillow stays at 12.3.0 in all three runtimes, so the start crash of the MLX runtime with Pillow 13 (0.5.1_hf_1) can
  not come back, also not through ComfyUI. At its first start, 0.5.2 brings every installed runtime to this
  set by itself, in seconds: a runtime that got Pillow 13 or another untested package is repaired, nothing is deleted.
- 0.5.2 replaces 0.5.1_hf_1: its download had been built from a development state by mistake and held changes that
  were not released yet. 0.5.2 is 0.5.1 with these fixes only.
- The Changelog page no longer lists the note at the end of the changelog as a version of its own.

## 0.5.1_hf_1 – 2026-10-21

- A crash on start with the MLX runtime is fixed: Pillow 13.0.0 broke an import inside mflux (its private
  `PIL._typing` runs `from numbers import _IntegralLike`, a name Python 3.11 does not have), so VulKara now
  installs Pillow 12.x (`pillow<13`). If the MLX runtime already crashed, mend it with Settings → Runtimes → Update.

## 0.5.1 – 2026-10-12

- The Hardware page shows a folder in your home folder as `~/…`, also in **Copy info**: your user name stays out
  of screenshots and of what you paste into an issue.

## 0.5.0 – 2026-10-12

- **VulKara speaks German, Spanish and Portuguese (Brazil and Portugal)** as well as English: the menu at the top
  right of the Start page, or Settings → Appearance → Language, with *System* (the first language in macOS's list
  that the app has, else English). The language changes at once, in every window, large views included, without a
  restart. Translated: every page, dialog, hint, the status bar and the queue, the messages of the app, the status
  lines of the engines (loading, decoding, downloads, training), the tips, the descriptions of the recommended
  models, helper models and photo tools, and the licence list's notes. Model, LoRA and sampler names, prompts, the
  logs, the problem report and the engines' error messages stay English. Numbers take the language's decimal mark
  (2,5 GB); dates follow macOS's region with *System*.
- **More languages without a change to the code**: a language is a folder of JSON files
  (`src/shared/i18n/locales/<code>/`), found when the app is built. `node tools/new_language.mjs` starts one with every
  text in English; [Translating VulKara](docs/TRANSLATING.md) tells translators what to do and how to send it as a
  pull request.
- The user guide in German, Spanish and Portuguese (`docs/de`, `docs/es`, `docs/pt-BR`, `docs/pt-PT`), with
  screenshots of the app in that language; the wiki has a page per language.
- Text to image and the other pages wrap the bar under the prompt to a second line instead of cutting off the label
  options in a narrow window; the Pose editor's hand and face rows make room for longer names.
- The text behind an **i** or **!** inside a card or a list that scrolls opens over everything instead of being cut
  off by the card (the **!** of a model imported on another Mac showed only its first lines).
- A model imported on another Mac shows only **Import again** and **Remove** on its card; the other buttons did not
  fit and ran over the card's edge.
- **Steps and guidance that do not suit the model** get an orange **!** next to the slider on Text, Image, Inpaint,
  Illusion and Video (and next to *Steps* on the Canvas), with a button that sets the model's own value. Switching
  the model keeps steps and guidance, so values meant for one model could end up on a distilled one: FLUX.1
  [schnell] at 18 steps and guidance 6.2 took 13 minutes instead of about 3, without a word. Now: steps more than
  twice what a distilled model is made for (*Made for 4 steps: more take longer without a better picture.*);
  guidance on a model that has none (*FLUX.1 [schnell] has no guidance: this value has no effect.*; also a
  distilled FLUX.2 [klein], and Z-Image-Turbo with MLX); guidance above 1 on other models made without it (SDXL
  Turbo, Z-Image-Turbo with Diffusers, Chroma1-Flash, Qwen-Image Lightning, Wan 2.2 14B), where every step runs
  twice.

## 0.4.16 – 2026-10-09

- **Report a problem** (Logs page, and About): choose one of the last 10 sessions (each with its time, lines and
  error lines), read its log with personal data replaced by `****` (user and Mac names, home, disk and folder names,
  picture and video names, prompts and other texts, tokens, link queries, e-mail and network addresses, IDs; model
  names, app folders, checksums and errors stay) and a summary of what was hidden, then **Copy** it or **Open GitHub
  issue**, which copies it and opens a new issue to paste it into. The app sends nothing itself.
- Every start of the app writes a log file of its own (`logs/session-<date>_<time>.log`, at most 5 MB); the last
  10 are kept. The single `vulkara.log` of earlier versions is split into session files once.
- Runtimes always use the app's own uv at its checked version (a uv from Homebrew is no longer taken) and install
  ready-built packages only, so no Mac needs the Xcode command line tools; a package without one is named in the
  message. README and wiki say that nothing has to be installed first.
- Releases are notarized by Apple: macOS opens them after the usual question, without Open Anyway. The DMG of
  0.4.15 was notarized afterwards and replaced on the release page.
- **Models copied from another Mac are recognised**: an import now notes the Mac it was made on (`imported_on` in
  `model.json`: a hashed id of the Mac and its memory; older imports are told by their memory plan). A model folder
  copied from another Mac does not run, because its import decided for that Mac (memory plan, FP8 stored as GGUF,
  compressed copies): jobs, bakes and trainings with it are refused, and its card on the Models page has a **!**,
  **Import again** (to the Trash, then imported from its file, Hugging Face or Civitai under the same name, after a
  check) and **Remove**.
- **GGUF models stream from the SSD** where they do not fit, like 16 bit ones: FLUX.1 [dev] fine-tunes imported
  from FP8 files (stored as 8 bit GGUF) and the 4 and 8 bit FLUX.1 GGUF files now run on a 16 GB Mac. The first
  time, the file is unpacked into the streaming cache (once, a few minutes); later only the cache is read.
- A streaming cache folder set in Settings that does not exist yet no longer stops the job (its disk's free space
  is checked at the nearest existing folder).
- Code tidied for reading (no change in behaviour): one helper starts the engine's one-off tools (export, pose
  detection, face search) instead of two copies; Restore's detail and face steps in a function of their own;
  repeated lookups and clamps in restore.py in one place each; unused imports and names removed; the engines,
  the content filter, the selection and training split their output into lines with one shared helper; Restore's
  sliders are one component (SliderRow); the fields of Restore and the bake dialog share one style (.entry);
  the dust finder and the face restoring of Restore split into named steps (same masks and pixels, checked on a
  photo); the dust finder sorts its candidates in one pass instead of one per speck (a 7 MP scan: 0.24 s instead of
  up to 0.83 s).

- The problem report hides the whole of a folder or file name with spaces, commas, brackets or an apostrophe in it
  (before, only its first word was hidden).
- **Import again** imports under the name of the folder it moves to the Trash, and refuses before moving anything
  when a model folder of that name is there already.
- A move of the earlier log file into session files that stopped halfway does not write a session twice.

## 0.4.15 – 2026-10-07

- **Restore removes dust and scratches**: small specks and thin scratches that stand out from calm surroundings are
  found and filled (LaMa); leaves and fabric stay, so do eyes and mouth; a sensitivity slider; on by default.
- **GPU load** in the status bar and on the Hardware page, next to the CPU (as the graphics driver reports it).
- **Export as one file**: SD 1.x and SDXL models in folder layout (baked models among them) can be written as one
  `.safetensors` checkpoint that ComfyUI, Automatic1111 and Forge load.
- Zooming with a mouse wheel goes in steps (at most ×1.4 per notch) instead of jumping to 800 %.
- The card picture of *Remove JPEG artefacts* shows that tool at work (it was the Denoise picture).
- A concept for recurring characters (docs/concepts/CHARACTERS.md).
- Step caching is said to work for FLUX.1 only: measured, FLUX.2, Qwen-Image 2.1 and Z-Image are not cached by diffusers.
- The user guide's Restore chapter shows a restored example; the repair is measured on a 16 GB Mac.
- **Restore rebuilt for soft and blurred photos**:
  - **Rebuild soft details (AI)**: Real-ESRGAN rebuilds edges and textures of the whole photo; how soft the photo is
    and how strong the step is are set with sliders.
  - **Restore faces (AI)**: CodeFormer restores blurred faces (chosen over GFPGAN, which invented glasses and earrings
    in the tests); faithfulness and strength are set with sliders. The faces are shown as rounded frames over the photo,
    can be dragged onto the right place or left out, and are taken from the photo before the AI steps, so a repair can
    no longer turn them into other people.
  - **Preview** restores a part of the photo in seconds (what is zoomed in on, else the largest face), and a
    **compare slider** shows the change left of the line and the original right of it.
  - The result can be **twice the size** of the photo.
  - The correction keeps light tones (a white dress kept its folds instead of turning pure white); its strength is set
    with a slider.
- **Pictures with a colour profile** (Display P3, Adobe RGB, HDR like Rec. 2020 PQ) are converted to sRGB on every page
  that takes a picture; read without their profile they came out flat and grey, and Restore made them worse.
- A Restore without the AI repair no longer shows steps and a seed, which it does not use.
- README and user guide show the app's own icons instead of emoji.
- The pipelines with their diagrams have a document of their own (docs/PIPELINES.md); the README is shorter.
- The one-time move from the app's earlier name is gone (done on every installation).
- Hardware page and status bar: before the models folder exists (a new installation), the free room of its disk is shown instead of 0 MB.
- All screenshots of the documents taken again (1600 × 1100, the status bar and the tinted navigation); none shows a personal photo.
- Photos taken with a phone (an EXIF orientation) are restored upright, and their face frames, preview part and
  painted mask sit where the app shows them.
- A Restore preview is made at the photo's size even when *Twice the size* is chosen.
- Exporting a model as one file: no job starts while it runs, an installation blocks it, quitting the app stops it,
  a failed write leaves no half file behind, and a crash shows Python's last lines instead of an exit code.
- A face search of a photo that is no longer shown can not overwrite the frames of the current one.

## 0.4.14 – 2026-10-01

- Baking LoRAs: the free memory and disk space it needs are reckoned at 2 bytes per parameter (they were half of
  that, so a large base could pass the check and then run out of memory); a base imported with fp16 files gives a
  model that loads (its linked text encoders get the plain file names); a cancelled bake leaves no half-written model
  that blocks baking again under the same name.
- The copy of a labelled picture without the icon carries the AI notice in its file too.
- AI Canvas: pictures it can no longer open (moved, deleted, or chosen before this version outside the app's folders)
  are taken off the canvas with a note, so it can still paint.
- Choosing many training pictures at once no longer stalls the app (the list of pictures given to it is written once).
- **The label is the EU's icon for AI content** instead of the text “AI generated ..”: *AI GENERATED* for pictures made
  from a prompt, *AI MODIFIED* where a picture of yours is changed (Image, Inpaint), or the round *AI*; black or white
  by the brightness of the corner (or as chosen), small to large, optionally subtle (50 % transparent), with a preview
  next to the switch. The font list of the text label is gone.
- A labelled picture used as an input again is taken without its label (a copy is kept for that), so pictures made
  from pictures carry one label, not the old one showing through.
- The app's own example pictures (Tips & tricks, helper previews, the splash) and the README pictures carry the EU icon
  *AI GENERATED*, small, instead of the text “AI generated”.
- **Security: ComfyUI is locked with a key.** The ComfyUI process (Upscale, Anima, Wan) only accepts requests with a
  random key the app makes at each start; other programs on the Mac and web pages in a browser are refused. If the
  lock does not load, ComfyUI is stopped instead of running open.
- **Security: the pages only see pictures they were given.** Pictures are shown and taken into jobs only from
  VulKara's folders, the history, and what you chose in a dialog or dropped onto a field (the choices are
  remembered). Before, a page could show any picture on the Mac, so code smuggled into it could have read them.
- **Bake LoRAs into a new model**: on the LoRA page and after a training, one or more LoRAs with their strength
  become part of a new model of its own (a diffusers folder under Models), which needs no LoRA any more and puts the
  LoRAs' trigger words into the prompt by itself. Runs in the import queue with its progress; compressed (GGUF, FP8,
  NF4) and ComfyUI models are refused with the reason, and the free memory is checked first.
- Fixed: on exFAT drives, macOS' companion files (`._name`) were taken for weights when a folder was inspected.
- Fixed: a ControlNet next to a large model (FLUX.1 [schnell] Q8 on 24 GB) was refused for lack of memory also at
  small sizes: the room was reckoned for 1024 × 1024. It now follows the picture's size (512 × 768 leaves room for
  the ControlNet in 8 bit), and the message says the size and that a smaller picture leaves more room.
- **Zoom into loaded pictures** on Image, Inpaint, Enhance, Upscale and Restore, also while painting a mask or
  selecting objects: ⌘-scroll or pinch zooms (up to 800 %), scrolling, Space-drag or the middle button move it, and
  small controls zoom out, in and fit; strokes and clicks land where they are shown.
- Fixed: FLUX.2 [klein] 4B and 9B (and Wan 2.2 14B) no longer loaded (“no file named model.klein4b.safetensors”):
  the check of the installed models had written the LoRA sub-base into the field diffusers reads as the weights'
  file variant. The sub-base now has a field of its own (`sub_base`), the engine never takes it for a file variant,
  and the affected models are repaired once at the next start (the first backup `model.json.bak` stays).
- **Fine-tuning of the photo tools**: JPEG cleanup takes a JPEG quality (Auto, or 10–90 as tiles and a slider; lower
  cleans more strongly), Denoise a character (*Natural*, or *Sharp* with SCUNet's GAN weights, downloaded on first use
  at a pinned checksum).
- **Upscale takes pictures over 2048 px** too: they are made smaller to 2048 first, the result is still the factor
  chosen times the picture given (up to four times the smaller one), and its note says so.
- **Any enlargement**: Upscale and the enlarging tools of Enhance take a factor from preset tiles (×1.5, ×2, ×2.2, ×2.5,
  ×3, ×3.5, ×4) or a slider in steps of 0.1, instead of only 2× or 4×; the model works at its own scale and its
  result is brought to the size chosen.
- Fixed: Upscale ×4 on Enhance did not start with a picture over 2048 px, and after switching the tool the page lost
  the picture's size (the job showed 0×0). A larger picture is now made smaller to 2048 px first and then enlarged
  (up to 8192 px, about 7 minutes on an M2); the result's note says so, and the page shows the size it becomes.
- A result whose file is gone (deleted, moved, on a disk that is not connected) shows as **File missing** with its file
  name instead of a broken picture; it no longer opens, and ✕ removes it from the list.
- Enhance jobs carry the tool's current name (an earlier install could still show the old, longer one).
- **AI Canvas: queue and results** in a row below the surface, like on the other pages (progress, cancel, open in the
  large view, favourites).
- **AI Canvas: the frame can be resized** by its round corner handles: the opposite corner stays, sides in steps of 64
  from 256 to 2048 px and at most twice the model's pixels (for 16 GB Macs); the frame then reads *free*.
- **Picture picker**: wherever a picture is chosen (Image, Enhance, Upscale, Restore, AI Canvas, a pose from a photo,
  the Illusion pattern) a picker opens with your results from the history, searchable and with a favourites filter;
  **From disk …** opens the file dialog as before.
- Fixed: the consent question for a sexual prompt with an input picture showed as an error text on the Canvas, Image
  and LoRA pages, so nothing could be answered. It is now a dialog with **Yes, continue** and **No, cancel**.
- **AI Canvas: pictures can be resized** before generating: the selected picture has corner handles (proportions
  kept, ⇧ for free ones, its size shown below it), and a new toolbar button fits it into the frame.
- The info badges in a page's side panel open centred over the whole panel, so their text is never cut off at
  the panel's edge.
- **Photo tools on the GPU**: Denoise (SCUNet) and Upscale ×4 (SwinIR) now run from their original
  PyTorch weights on the GPU through spandrel, three to five times faster than the ONNX versions on the CPU (a 768²
  photo on an M2: Denoise 4 s instead of 20, Upscale 35 s instead of 160). The weights come from their publishers'
  GitHub releases, pinned by checksum. **JPEG cleanup (FBCNN)** is a new, sixth tool. Sharpen stays with
  OpenCV's ONNX export: the original NAFNet weights break down on many picture crops (docs/MEASUREMENTS.md). Each
  tool says whether it runs on the GPU or the CPU. The Diffusers runtime needs an update for this (Settings →
  Runtimes), which is offered.
- The Enhance page's tool list is compact: the name on one line (the model's name moved into the badge), a few words
  with GPU or CPU in front (tinted like the navigation's groups: violet GPU, teal CPU), a short line between the tools
  instead of a frame around each, and everything else in the (i) badge: what the tool does in full, size limits and
  download size, and below a line the licence, its note and the source. Strength and the import field explain
  themselves in a badge too; a full line sets the panel's sections (tool, strength or result, recommended, import)
  apart.
- **Import a model file** on the Enhance page takes PyTorch weights too (.pth, .safetensors) of any architecture
  spandrel knows (ESRGAN, SwinIR, HAT, DAT, SCUNet, FBCNN, SPAN, …), besides ONNX files; .pth files are read
  without running code.
- Tools installed earlier keep working; a tool downloaded again lands in a folder of its own.
- **Status bar with the Mac's figures**: three chips show the memory VulKara and its engines hold, the CPU, and the
  SSD streaming caches with the room left on their disk (orange below 20 GB); a click opens the new page. The CPU chip is a level meter of ten
  segments, like a hardware monitor's.
- **Hardware** page (bottom icons): chip and cores, unified memory and the Metal budget, GPU cores, a resource
  monitor every two seconds, the streaming caches, and the guard rails from Settings with a way there; **Copy info**
  for bug reports. The CPU is a level meter of thirty segments there.
- Every source file carries the licence notice (SPDX) and the copyright line.
- **VulKara is free software**: released under the GNU Affero General Public License v3.0 or later. The licence text
  ships with the app; About and the README say what it means. The sale editions and the EULA draft are gone, and
  CONTRIBUTING.md says how to help.
- The font list of the “AI generated ..” label shows script fonts with tall swashes (Zapfino, Snell Roundhand,
  Brush Script) a little smaller, so nothing is cut off in the button or the list.
- The licence badges of the photo tools and the Licenses page say where a source's own licence statement is
  incomplete (the SAM 2.1 ONNX export: Meta's Apache-2.0 weights) or inconsistent (SCUNet: MIT file, Apache-2.0 card).

## 0.4.13 – 2026-08-22

- **The font of the “AI generated ..” label** can be chosen: 15 macOS fonts, among them the script fonts Snell
  Roundhand, Brush Script and Zapfino, each shown in the list as the label will look in the chosen style.
- The in-app changelog shows versions without dates.

## 0.4.12 – 2026-08-21

- In a window too low for the navigation, the rail gets wider and shows its groups in two columns, so every page
  stays in reach without scrolling.
- The **Download** button of a helper model has an orange border.
- Models → Installed uses the width of a wide window: up to ten cards side by side (before: five). The cards keep
  one size (230 px wide) whatever the window: a wider window shows more of them, not larger ones.
- The kind tabs (All, Models, LoRAs, Helpers), Find LoRAs and the search stay at the top of Models → Installed
  while the cards scroll, and so does the title of the kind being scrolled (e.g. *LoRAs 54*, *Helper models 18 of
  26 on this Mac*) right below them.
- Resizing the window no longer makes the page jitter, also not slowly right at the point where the navigation
  changes its layout: it switches between one and two columns by the window's height only (the app icons at its
  foot take less room in two columns, which made it switch back and forth), with room to spare, and lays the page
  out anew only when it really switches.

## 0.4.11 – 2026-08-10

- **“AI generated ..” label**: a switch next to Generate writes *AI generated ..* into the lower right corner of each
  picture, in a size (small, medium, large) and style (italic, regular, bold, bold italic) of your choice.
- **Navigation regrouped**: *Create* (Text, Image, Canvas, Video, Illusion), *Edit* (Inpaint, Enhance, Upscale,
  Restore), *Tools* (Pose, LoRA, Training) and *Library*, each group in a tint of its own; in a low window the groups
  scroll with a thin scroll bar.
- The buttons of the cards on the Models page and in the LoRA finder are always at the foot of the card.
- **Helper models under Models**: *Installed → Helpers* shows the content filter, Restore's LaMa and DDColor, pose
  and depth detection, all ControlNets, Real-ESRGAN and the photo tools in a tint of their own, each with a picture of
  what it does and how much space it takes; **Download** fetches one ahead, **Move to Trash** frees its space (it comes
  back when needed). The content filter is required and stays.
- **All helper models pinned**: the ControlNets, DWPose, Depth Anything and Real-ESRGAN are now fetched at a fixed
  commit and checked by their SHA-256 too, like the content filter, LaMa, DDColor and the photo tools; copies
  downloaded before are checked once (the ones on the test Mac all matched).
- Selections of the Enhance page are kept in the app's data folder, so *Paint in Inpaint* still works after a restart.
- Cut-outs show on a checkerboard in the large view as well.

## 0.4.10 – 2026-08-04

- **Enhance**, a new page under Tools: photo tools with small ONNX models on this Mac, no prompt needed.
  - Recommended, free also for commercial use, downloaded once at a fixed, checked version: **Sharpen** (NAFNet),
    **Denoise** (SCUNet), **Upscale with detail** (SwinIR ×4), **Remove background** (BiRefNet) and **Select
    objects** (SAM 2.1).
  - **Select objects**: clicks select (⌥-click removes), the selection shows over the picture; cut it out, save its
    mask, or **Paint in Inpaint**, which opens Inpaint with the selection as the painted mask.
  - **Import an ONNX file**: other photo models, checked first (one picture in, one picture or mask out, no custom
    operators); large pictures are worked on in tiles; Strength mixes the result with the original.
  - Results go through the queue, the content filter and the history; transparent results show on a checkerboard.
- The Inpaint page can start from a given mask; the Licenses page lists the photo tools.

## 0.4.9 – 2026-07-18

- **Step caching** (Settings → Engine: Off, Light, Strong): steps that barely change the picture reuse the step
  before instead of being computed in full; a streamed model does not read those blocks from the SSD either.
  FLUX.1 [dev] with 28 steps: Light about 1.2× faster with a practically identical picture, Strong about 2× faster
  with slightly fewer fine details. A result made that way says so in its note.
- A job made in more than one non-standard way keeps all its notes (e.g. Diffusers instead of MLX and step caching).
- **Faster SSD streaming**: the part of a streamed model the memory has room for stays in memory, spread over the
  model, and only the rest is read in every step, two blocks ahead (two reads at a time, which a fast internal SSD
  turns into about 20 % more speed). On a 16 GB Mac these blocks make room for the text encoder while a new prompt is
  read. FLUX.1 [dev] on a 16 GB Mac at 512 px: 81 → 71 s; at 1024 px the reading was hidden behind the computing
  already, and stays so.
- The stream profile (`VK_STREAM_PROFILE=1`) shows where the time goes: waiting for the SSD, copying, computing, GB read
  and the GPU memory peak.

## 0.4.8 – 2026-07-12

- **Runtime installs checked**: uv comes at a fixed version (0.12.23) and ComfyUI 0.38.0 with its GGUF extension at a
  fixed commit, each compared with its SHA-256 before anything is installed; a download that differs is refused. A
  uv of another version in the runtimes folder is replaced by the checked one.
- **Folders only in the folder dialog**: the folders in Settings can only be chosen with **Choose** (the macOS
  dialog) or reset with **Default**; nothing else can point them somewhere.
- **Training pictures pass the content filter** before a LoRA learns from them (*Checking the pictures*); one that
  does not pass stops the training and is named. Your pictures are only looked at, never changed or removed. The
  captions and the trigger word are checked like a prompt.

## 0.4.7 – 2026-06-29

Security and bug fixes from a review of the whole code (app, engines, runtimes).

- **Privacy**: a new section in Settings. *Look up files on Civitai by their checksum* is now **off** by default (it
  told Civitai which models are on the Mac); *Look for runtime updates once a day* can be switched off. The usage
  reports of Hugging Face, diffusers and transformers are switched off, a Hugging Face login of the command line is
  no longer used, the MLX engine and ComfyUI run offline, and ComfyUI no longer writes the prompt into its pictures.
- **Content protection**: a result the content filter did not pass, or could not check, is now removed from the
  pictures folder too, not only hidden. Without the Diffusers runtime (which runs the filter) no job starts. The
  restore rules are checked like the prompt, fullwidth letters and invisible characters no longer get past the
  check, and the consent question also comes with a pose or depth picture and with Restore. Preview pictures of
  imports go through the filter, and in safe mode no explicit Civitai sample is taken as preview.
- **Pinned helper models**: the content filter, LaMa and DDColor are fetched at a fixed commit and checked by their
  SHA-256; once on the Mac they are used without asking Hugging Face again.
- **Civitai links with `?token=…`**: the token is taken out before the link is used, logged or kept.
- **The packaged app** has no developer tools, ignores the development variables, cannot be run as plain Node or with
  a debugger, and allows no websocket in its pages. Python environment variables from a terminal (`PYTHONPATH`, …)
  no longer reach the engines; compiled Python goes to the data folder instead of into the app.
- Completing gated base parts (FLUX.1 [dev] parts of a single file) uses the stored Hugging Face token, and a missing
  token is named as such.
- **Fixed**: Cancel during the hand-over from MLX to Diffusers was lost, and the job ran to the end anyway; the
  hand-over note no longer comes with a cancelled job; a model MLX refused stays refused only until the memory or
  runtime settings change; the queue no longer stalls when the history cannot be written; no job or import starts
  while a runtime is installed; removing a picture of a running job no longer stops it; a reused job keeps its size
  when the model changes; a seed like `1e309` and an empty LoRA weight no longer break a job; the import check shows
  the answer to the latest request; the Tips preview keys no longer act on other pages; the main window comes at
  once when the splash is closed early; the large view opens on the right picture; a history line cut off by a crash
  no longer takes the next entry with it; the tokens file is written atomically; the queue and the log pages no
  longer miss changes while they start; the Mac's name is read without blocking; LoRA files of MLX and ComfyUI must
  lie in their folder; result names can no longer collide; unclear errors such as `'arch'` now say what is missing.

## 0.4.6 – 2026-06-11

- **About names this Mac**: *MacBook Pro (13-inch, M2, 2022) · 24 GB* or *Mac mini (2024) · Apple M4 · 16 GB* and the
  macOS version, instead of "darwin arm64". Models → Recommended starts with it too.
- **Two kinds of badges**: **ⓘ** (an orange ring) for plain information, **!** (filled) only where the app does something
  differently from the standard (values that differ from the model's suggestion, a replaced sampler, a model that runs
  streamed from the SSD, an import note). On Models → Recommended and Add, explanations moved into them; Settings keep
  their visible text.
- A click on a badge inside a setting's row no longer switches that setting.
- **Tested on a Mac mini M4 with 16 GB**: FLUX.1 [dev] streamed from the SSD after MLX hands it over, Krea 2, the
  Qwen-Image 2.1 repository and the Fluxtrait import all work.
- Screenshots of Models → Recommended and About updated.

## 0.4.5 – 2026-06-04

- **Tips & tricks**: a page of its own (Tips in the navigation) with prompt help and guidelines: prompt structure,
  anatomy, details and materials, lighting, LoRAs, popular helpers, and what each model type wants, from SD 1.5 to
  Wan 2.2 video. The tips for the model chosen on the Text page come first; search, copyable example prompts, and six
  picture pairs (short against worked-out prompt: hands, eye, hair, a teapot, a street at night, skin). Collected from
  model cards and guides, written in our own words; the public sources are collected in one list under **Sources**
  (no claim to completeness).
- **Tips with LoRAs and poses**: a row shows a LoRA at the weights 0, 0.5, 1 and 1.5 (from no effect to a picture that
  falls apart), another a pose picture with the result without the pose and with it at 0.5 and 1. All tip pictures are
  small and keep their proportions.
- **Tips on settings**: one prompt and seed on five model types (SD 1.5, SDXL Turbo, FLUX.2 klein 4B, Z-Image Turbo,
  Chroma1-Flash), and one model at guidance 1.5 to 20, at four seeds and at 5 to 40 steps, each as a small row.
- **Preview of the tip pictures**: a click opens a picture large, ← → step through the row of its tip, Esc closes.
- The example pictures of the tips and the splash picture are marked "AI generated" in their lower right corner.

## 0.4.4 – 2026-05-14

- **Switching the model keeps steps, guidance, seed and size**, also where they still were the old model's defaults, so
  that models can be compared with the same settings. An orange **!** next to **Model defaults** shows what the new
  model suggests when the pointer is on it; the button sets it. A sampler the model does not have is marked the same
  way instead of a line of text. A size the new model can not compute changes in the same proportions and comes back
  on a model that can.
- **Cancelled and failed jobs leave the list like finished ones**: their tile has the **×** in the corner too, always
  in reach. The tile shows the essentials (prompt in two lines, size and steps, a short note, the start of an error);
  everything else, such as the full prompt, the note and the whole error, opens over the tile while the pointer is on
  the **ⓘ** in its corner. The **ⓘ** on a picture shows its note the same way (the system tooltip did not appear).
- **Cancel while a model loads works**: a Cancel sent while the engine was still starting or loading the model was
  lost, and the job ran on to the finished picture; now the job stops.

## 0.4.3 – 2026-05-01

- **Changelog in the app**: a page of its own (icon next to Logs) shows what changed from version to version and marks
  the installed one; the small icons for Settings, Logs, Changelog, Licenses and About sit in two rows.
- **Recommended**: the memory figures are computed for all large models again, with SSD streaming: FLUX.1 [dev] and
  Chroma show what they need in memory and, on a smaller Mac such as a 16 GB Mac mini, *SSD streaming* with the memory
  that needs (FLUX.1 [dev] about 11 GB, Chroma about 10 GB).
- The hand-over from MLX to Diffusers is covered by tests.
- **Krea 2 loads faster**: the 4 bit model is saved once next to the model (about 9 GB, as for Ideogram 4); a new
  prompt on a 16 GB Mac, which reloads the model, then takes about 12 seconds to load instead of about 30. Tested
  with a 16 GB budget, three prompts, about 7 minutes per picture.

## 0.4.2 – 2026-04-26

- **Qwen-Image 2.1 on a 16 GB Mac** (e.g. Mac mini M4): with SSD streaming its 8.8B text encoder is compressed to 4 bit
  when 8 bit leaves no room, instead of refusing the model ("needs about 23 GB RAM"). A GGUF file, which can not
  stream, now says that the 16 bit repository or safetensors file runs on such a Mac.
- **FLUX.1 [dev] on a 16 GB Mac**: when MLX (which can not stream) has too little memory for a FLUX.1, FLUX.2 [klein] or
  Z-Image model, the job goes on with Diffusers, which streams it from the SSD, instead of failing. A note on the job,
  its pictures (ⓘ), the large view and the history says so. Tested with a 16 GB budget: about 10½ minutes for
  1024 px and 12 steps.
- **Krea 2 on a 16 GB Mac**: MLX frees its text encoder after reading the prompt (as for Ideogram 4); tested with a
  16 GB budget, about 8 minutes per picture.
- **Civitai imports**: a 16 bit single file too large for the memory counts as streamable, as the engine runs it (FLUX.1
  fine-tunes such as Fluxtrait were refused as too large); GGUF versions can be imported from Civitai.
- **Z-Image tested further** on an M2 with 24 GB: Turbo repository with MLX (8 bit) about 5½ minutes at 1024 px, Base
  with MLX about 33 minutes at 30 steps with guidance, LoRAs in kohya and ComfyUI names (fused qkv) with MLX and
  Diffusers. Z-Image-Turbo is marked as tested among the recommendations.
- **LoRAs for a model opens every time**: after the window had been closed with Escape, the next *LoRAs* click on a
  model card sometimes showed nothing; opening it for another model now also searches that model's base.
- **Splash**: shown for at least five seconds (was two and a half), then it closes by itself once the app is ready;
  a click closes it earlier.
- **Recommended**: models that only fit streamed say *SSD streaming* instead of *Needs more memory* (FLUX.2 [klein] 9B
  and SD 3.5 Large on 16 GB).

## 0.4.1 – 2026-04-05

- **LoRAs on a quantized Chroma (or FLUX.1) load again**: diffusers' loader looked each layer up as `x.weight`, which
  an 8-bit transformer keeps as `x.weight._data`, and stopped with *does not fit this Chroma model*. Tested with
  Chroma1-Flash and a Chroma LoRA (80s Fantasy Movie, kohya names) on an M2 with 24 GB.
- **Z-Image Turbo and Base** (Tongyi-MAI, Apache 2.0): import from Hugging Face, Civitai or a file (repository,
  safetensors, GGUF), text to image, image to image and inpainting with Diffusers, text to image with MLX; LoRAs in
  ai-toolkit, ComfyUI, kohya and peft names. Tested on an M2 with 24 GB with Comfy-Org's Z-Image Turbo bf16 file
  (19 GB download with the text encoder and VAE): text to image about 6½ minutes at 1024 px and 9 steps, image to
  image about 4 minutes, inpainting about 6½ minutes, a LoRA (pixel art) about 7 minutes.
- Tested on an M2 with 24 GB: Chroma1-Flash image to image and inpainting; Qwen-Image 2.1 with the turbo LoRA alone,
  with a ComfyUI LoRA (gate_up split) and with a peft LoRA.

## 0.4.0 – 2026-04-02

- **Splash**: a small window (640×384) that closes by itself as soon as the app is ready and the splash has been
  shown for a moment. No Continue button any more; a click closes it earlier. With *Prefer tabs: Always* in the macOS
  settings, the splash (and the large view) no longer open as tabs of the main window and so no longer take its size.
- **Runtime update check** in Settings: each runtime shows its installed version and, when there is one, the newer
  version of its key packages (diffusers, torch, mlx, ComfyUI …), with *Check now* and the time of the last check. It
  runs once a day while nothing is generated or installed; a dot on Settings in the navigation marks available
  updates. New runtimes take part without extra code.
- New slogan: *Your local AI image generator with high privacy*.
- README: “How the pipelines work”, with flow diagrams for every pipeline (job, memory plan, text and image to image,
  inpainting, canvas, ControlNet and pose, illusion, video, upscale, restore, LoRAs, import, privacy).

## 0.3.0 – 2026-03-23

- **More LoRAs load**: files in ComfyUI / ai-toolkit original names (FLUX.1, Chroma), PEFT dumps (`.default.`),
  SDXL from ai-toolkit (`lora_transformer_`) and files with mixed prefixes are converted before loading;
  Qwen-Image 2.1 LoRAs from ai-toolkit get their fused MLP layers split (100 % instead of 83 %).
  LoKr/LoHa files are refused with a clear message.
- Chroma1-Flash tested: about 7 minutes per picture at 1024 px on an M2 with 24 GB (12 steps, no guidance);
  its import took the T5 text encoder from an installed Chroma model instead of downloading it again.
- README: SSD streaming as a feature of its own, with measured times and memory.

## 0.2.0 – 2026-02-18

- **Chroma is about 40 % faster** on M1/M2: the denoiser and VAE compute in float16 where the chip only emulates
  bfloat16 (the T5 text encoder stays bfloat16). Same picture, 52 instead of 85 minutes for 30 steps with guidance on
  an M2 with 24 GB.
- **Chroma1-Flash among the recommendations**: the distilled Chroma with about 12 steps and no guidance (one pass per
  step instead of two), several times quicker than Chroma1-HD. Apache 2.0.
- Guides: Chroma's speed and the float16 switch for new architectures.

## 0.1.0 – 2026-01-08

The first release.

- Pictures and videos: text to image, image to image, inpainting, AI canvas, image to video, upscaling, illusion
  pictures, pose editor, Restore for old photos (correction, AI repair under guard rails, LaMa, DDColor, sharpening,
  templates).
- Models: SD 1.5 / 2.x, SDXL (Pony, Illustrious, NoobAI), SD 3.5, FLUX.1, FLUX.2 [klein] 4B / 9B and [dev], Krea 2,
  Qwen-Image and Qwen-Image 2.1, Chroma, Anima and Wan (ComfyUI), Ideogram 4 (MLX); import from Hugging Face, Civitai
  or disk including GGUF; memory planning, SSD streaming with its own cache folder; licences per model.
- LoRAs: matching LoRAs from Civitai and Hugging Face with install, reliable family detection, 90 % fit check,
  training and strength comparison.
- App: history, favorites, viewer, light/dark appearance, content filter, settings kept when switching models,
  one-time move of data from earlier versions.

## Versions below 0.1.0 truncated   ..
