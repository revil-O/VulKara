# Measurements

Every benchmark and measurement made while developing VulKara, with its setup, so that a question that was answered
once is not measured again. New measurements go here too (date, machine, what was measured, the numbers, what was
concluded). The developer guide points here from its guardrails.

**Machines.** *M2*: MacBook Pro (13-inch, M2, 2022), 24 GB unified memory, 10 GPU cores, macOS 27, internal SSD plus
a 2 TB Crucial USB SSD (exFAT) holding the models and the streaming caches. *M4*: Mac mini (2024), Apple M4, 16 GB
(the user's second Mac; results there are the user's live reports). A *16 GB simulation* on the M2 means
Settings → *Memory kept free for other apps* = 12 GB (`VK_MEMORY_RESERVE_GB=12`), which gives the 12 GB budget of a
16 GB Mac.

## 1. SSD read speed (2026-10-09, M2)

Reading 24 whole stream-cache blocks of FLUX.1 [dev] (`scratchpad io_bench.py`: `os.readv` of whole files; `F_NOCACHE`
bypasses the macOS file cache).

| Disk | Data | 1 read at a time | 2 at a time | 3 at a time | 64 MB chunks | plain read (cached) |
| --- | --- | --- | --- | --- | --- | --- |
| 2 TB Crucial, USB | 6.8 GB | 0.92 GB/s | 0.92 GB/s | 0.93 GB/s | 0.90 GB/s | 0.94 GB/s |
| internal SSD | 9.9 GB | 2.73 GB/s | 3.30 GB/s | 3.32 GB/s | 2.70 GB/s | 3.13 GB/s |

Conclusions: the USB SSD is saturated by one read; the internal one gains about 20 % from two reads at once and
nothing more from three. `F_NOCACHE` and chunking change nothing. Streaming therefore reads two blocks ahead with two
readers (`streaming.PREFETCH`, `READERS`). A streaming cache on the internal SSD reads three times faster than on the
USB disk.

## 2. SSD streaming profiles (2026-10-09, M2, cache on the USB SSD)

`VK_STREAM_PROFILE=1` per picture: passes of the denoiser (two per step with true guidance), blocks read, GB read, time
waiting for the SSD / copying to the GPU / computing. "Before" is the original streaming (every block read every
step, 15 % resident share); "after" keeps the blocks the memory plan has room for (`engine.keep_plan`).

| Case | Picture | Blocks kept | Read | Waiting | Copying | Computing | Waiting share | Picture time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FLUX.1 [dev], 16 GB sim, before | 3 steps, 512² | 0 | 66.8 GB | 50.7 s | 2.7 s | 26.6 s | 63 % | 81.0 s |
| FLUX.1 [dev], 16 GB sim, after | 3 steps, 512² | 8 (2.8 GB), released per prompt | 61.7 GB | 38.1 s | 8.5 s | 22.6 s | 55 % | 70.7 s |
| FLUX.1 [dev], 24 GB, after | 3 steps, 512² | per plan (30 %) | | | | | | 57.2 s |
| FLUX.1 [dev], 16 GB sim, after | 2 steps, 1024² | 8 (2.8 GB) | 42.5 GB | 4.1 s | 11.9 s | 50.5 s | 6 % | 72.0 s (GPU peak 5.3 GB) |
| Chroma1-Flash, guidance 4, 16 GB sim, after | 2 steps, 1024² | 5 (1.3 GB) | 59.9 GB | 1.0 s | 15.6 s | 108.6 s | 1 % | 130.1 s (GPU peak 4.2 GB) |

What the memory plan keeps of FLUX.1 [dev] (`keep_plan`): 16 GB → 10 % (released while a new prompt is encoded),
24 GB → 30 %, 32 GB → 60 %.

Conclusions: at 512 px streaming is bound by reading (55–63 % waiting), at 1024 px by computing (1–6 % waiting), so
at the usual size the reading is already hidden behind the GPU. Batching the guided and the unguided pass of true
guidance would save only reading and nothing at 1024 px; it was not built. The kept blocks gave −13 % at 512 px on
16 GB. Further speed at 1024 px can only come from fewer steps (step caching, turbo LoRAs).

### A GGUF model streamed (2026-10-11, M2 24 GB, 16 GB sim, cache on the internal SSD)

xeHentaiAnimeFLUX_04, a FLUX.1 [dev] fine-tune imported from an FP8 file and stored as 8 bit GGUF (12.6 GB), which
before was refused on 16 GB ("needs about 23 GB"). `streaming.unpack_gguf` unpacks it into the stream cache once.

| Run | Picture | Unpacking | Picture time | Total | Notes |
| --- | --- | --- | --- | --- | --- |
| first | 12 steps, 768², guidance 3.5 | ≈ 2½ min (57 blocks, 22 GB written; the process stayed near 2 GB RAM) | 250.4 s | 427.5 s | 49 blocks streamed, 8 (2.8 GB) kept; 0 % waiting; GPU peak 5.3 GB |
| second | 4 steps, 512² | none (only rest.safetensors read) | 51.7 s | 80.5 s | the GGUF file is not read again |

The reads (234.5 GB in the first run) came from the page cache of the 24 GB Mac; a real 16 GB Mac reads them from the
SSD, as in the table above.

## 3. Step caching (2026-10-10, M2, 24 GB)

FLUX.1 [dev], 28 steps, 768², same seed, diffusers' First Block Cache (`step_cache.py`). The *off* run was slowed by
a leftover engine process that pushed the Mac into swap, so its time is not comparable; the expected speed-ups
follow from the runs reused.

| Level | Threshold | Runs reused | Picture time | PSNR against off | Expected speed-up (from the reuse) |
| --- | --- | --- | --- | --- | --- |
| off | – | 0 of 28 | 753 s (swap-affected) | – | 1× |
| light | 0.05 | 5 of 28 | 547 s | 41.0 dB | about 1.2× |
| strong | 0.12 | 15 of 28 | 294 s | 31.3 dB | about 2× |

Conclusions: light is practically identical to off (41 dB), strong keeps the picture and loses fine detail.

2026-10-11 (M2, Diffusers runtime forced): Z-Image Turbo, Qwen-Image 2.1 (Q4 GGUF) and FLUX.2 [klein] 4B are not
cached at all: the engine logs "step caching: not available for ZImageTransformer2DModel / QwenImage21Transformer2DModel
/ Flux2Transformer2DModel", because diffusers' block registry (0.41) does not know their blocks. Their pictures with
off, light and strong took the same time (Z-Image 165–168 s, Qwen-Image 248–256 s at 768², 8 steps). So the
thresholds stay those of FLUX.1, the only family the cache works for here; the setting's texts say so.

## 4. Photo tools (2026-10-10, M2, CPU via onnxruntime)

A 768 × 768 picture, the recommended tools of `photo_tools.json`, run from a script and again as jobs in the app.

| Tool | Model | Download | Script | In the app |
| --- | --- | --- | --- | --- |
| Sharpen | NAFNet (opencv export, quantized) | 92 MB, 7 s | 14.1 s | 14.8 s |
| Denoise | SCUNet | 77 MB, 8 s | 20.0 s | |
| Upscale ×4 | SwinIR-M (rocca export, dynamic) | 61 MB, 13 s | 162 s (→ 3072²) | |
| Remove background | BiRefNet lite fp16 | 115 MB, 2 s | 7.6 s | 8.2 s |
| Select objects | SAM 2.1 hiera tiny | 155 MB, 5 s | first click 1.6 s, next 0.03 s | 2.0 s, next 0.07 s |

### CPU against CoreML (onnxruntime's CoreML execution provider, MLProgram), one tile each

| Tool | Tile | CPU | CoreML, static shapes | CoreML, dynamic shapes |
| --- | --- | --- | --- | --- |
| NAFNet | 512² | 3.36 s | 3.57 s (max diff 0) | 139.6 s (max diff 0.003), 71 s to compile |
| SCUNet | 512² | 4.41 s | 4.61 s (max diff 0) | fails to load (axis out of range) |
| SwinIR ×4 | 64² | 0.56 s | 0.58 s (max diff 0) | fails at run time (zero-element dynamic shape) |

Conclusions: CoreML does not know the operators of these exports; with static shapes everything falls back to the
CPU (identical times and results), with dynamic shapes it is 40× slower or breaks. CoreML through onnxruntime is a
dead end for these three. The way to speed is the GPU through PyTorch: `spandrel` 0.4.2 (MIT) loads the original
weights of NAFNet, SCUNet, SwinIR, HAT, DAT, FBCNN, ESRGAN, SPAN, OmniSR, RealCUGAN, GFPGAN on MPS (Real-ESRGAN of
the Upscale page already runs this way); since 0.4.14 it is in the Diffusers runtime's requirements.

### The original weights on the GPU (2026-10-10, M2 24 GB, spandrel 0.4.2, torch 2.14.1, MPS, fp32)

One tile each, after a warm-up run:

| Model | File | 256² | 512² |
| --- | --- | --- | --- |
| NAFNet-GoPro-width64 | 272 MB .pth (HF mirror, pinned) | 0.26 s | 0.95 s (CPU ONNX 3.36 s) |
| SCUNet colour real PSNR | 72 MB .pth (KAIR release v1.0) | 0.35 s | 1.46 s (CPU ONNX 4.41 s) |
| SwinIR-M ×4 real GAN | 67 MB .pth (SwinIR release v0.0) | 4.17 s (→ 1024²) | 16.3 s (→ 2048²) |
| FBCNN colour | 288 MB .pth (FBCNN release v1.0) | 0.15 s | 0.59 s |

The whole 768² picture through `run_image` (tiles with overlap 32, GPU alone):

| Tool | Tile | Time | Against the first setting |
| --- | --- | --- | --- |
| SCUNet | 512 | 5.9–7.2 s | |
| SCUNet | 768 (one tile) | 3.1–4.1 s | max diff 3, mean 0.03 |
| SCUNet fp16 | 512 / 768 | 5.9 s / 3.0 s | max diff 1–3, mean 0.02–0.05 |
| FBCNN | 512 | 3.0 s | |
| FBCNN | 768 (one tile) | 1.7–1.9 s | max diff 2, mean 0.01 |
| FBCNN fp16 | 512 / 768 | 3.5 s / 1.6 s | max diff 1–2 |
| SwinIR ×4 | 256 | 73 s | |
| SwinIR ×4 | 384 | 77 s | max diff 26, mean 0.18 |
| SwinIR ×4 | 512 | 61–65 s | max diff 22, mean 0.19 |
| SwinIR ×4 | 768 (one tile) | 34–35 s | max diff 23, mean 0.15 |
| SwinIR ×4 | 1024 (one 1024² tile) | 214 s | far slower than 768 |

SwinIR does not support half precision (spandrel: `supports_half` false, the fp16 runs were fp32). fp16 gains
25–30 % for SCUNet and FBCNN at 768 with tiny differences; it is not switched on in the catalog (a manifest can set
`"half": true`), because the risk of overflow on other content is not worth a second.

Peak Metal memory per tile (driver allocation, model included, read just before the cache is emptied):

| Tool | 256² | 384² | 512² | 768² | 1024² | 1536² |
| --- | --- | --- | --- | --- | --- | --- |
| SwinIR ×4 | 2.3 GB | 4.5 GB | 7.1 GB | 16.1 GB | – | – |
| SCUNet | | | 2.3 GB | 3.4 GB | 4.9 GB | 12.1 GB |
| FBCNN | | | 1.4 GB | 2.5 GB | 2.5 GB | 5.4 GB |

Seconds per megapixel of input from these runs: SCUNet 6.1 (512) → 5.3 (768) → 5.0 (1024) → 4.6 (1536); FBCNN
3.5 → 2.9 → 2.4 → 2.2. The catalog's `tile_metal_gb` tables hold the measured tiles up to SCUNet 1024, FBCNN 1024 and
SwinIR 512 (7 GB; 768 would take 16 GB and is left out); `metal_tile` picks the largest that fits in what is left of
Metal's budget (0.74 × RAM) beside the loaded diffusion model, with 1 GB headroom. On a 16 GB Mac (budget 11.8 GB)
with SDXL loaded (7 GB) SwinIR therefore runs at 256, SCUNet at 768; with nothing loaded at 512 and 1024.

**NAFNet's original weights are unusable in tiles.** On the 768² benchmark picture, crops through the raw model
(CPU and MPS alike, fp32 and fp64 alike) give outputs with means far from the input and values in the thousands:

| Weights | 512² crops (128 grid, 9) | 256² crops (25) | Whole picture |
| --- | --- | --- | --- |
| NAFNet-GoPro-width64 | 2 bad | 7 bad | fine |
| NAFNet-REDS-width64 | 1 bad | 5 bad | fine |
| NAFNet-GoPro-width32 | 8 bad | 15 bad | bad (mean 0.41 for 0.35, max 5.9) |
| NAFNet-SIDD-width32 (a denoiser) | 0 bad | 0 bad | fine |

A tiled run shows this as noise over whole tiles. OpenCV's ONNX export (`deblurring_nafnet_2025may`) showed none
of it in the earlier runs, so Sharpen keeps that export on the CPU (14 s for 768²); Denoise, Upscale and the new
JPEG tool run from their original weights on the GPU. Whole 768² picture through `run_image` with the catalog's
tiles on this Mac: Denoise 3–4 s, JPEG artefacts 1.7 s, Upscale ×4 (tile 512) 61–65 s; the first run of a process
adds 1–5 s for loading. As jobs in the app (engine log): Denoise 5.4 s (first run, model loading included), JPEG
artefacts 1.7 s.

### Upscale page: Real-ESRGAN x4plus through ComfyUI (2026-10-10, M2 24 GB, test instance)

Pictures over 2048 px are made smaller to 2048 first; the model enlarges 4 times, the result is scaled to the exact
size asked for (ComfyUI `ImageScale`, Lanczos).

| Picture | Factor | Model gets | Result | Time (job, ComfyUI start included) |
| --- | --- | --- | --- | --- |
| 3072 × 2048 | × 2 | 2048 × 1365 | 6144 × 4096 | 74 s (twice) |
| 1567 × 2417 (the user's photo) | × 2 | 1328 × 2048 | 3135 × 4834 (before the exact size: one pixel too wide) | – |

### Fine-tuning: FBCNN's JPEG quality and SCUNet's sharp weights (2026-10-10, M2 24 GB)

The 768² example saved as JPEG quality 15 (mean difference to the clean picture 5.72 of 255); each result against the
clean picture.

| Setting | Time | Mean difference |
| --- | --- | --- |
| JPEG cleanup, Auto (estimated) | 6.1 s (first, loading) | 4.09 |
| JPEG cleanup, quality 10 | 2.7 s | 4.31 |
| JPEG cleanup, quality 30 | 2.7 s | 4.33 |
| JPEG cleanup, quality 50 | 2.7 s | 4.75 |
| JPEG cleanup, quality 90 | 2.7 s | 5.57 |
| Denoise, Natural (real_psnr) | 6.4 s | 4.30 |
| Denoise, Sharp (real_gan) | 7.8 s | 5.06 |

FBCNN's quality embedding takes 1 − quality/100 (as in its own test code); the first try passed quality/100 and the
direction was reversed (10 left the blocks, 90 smoothed most). Sharp is further from the clean picture by design: it
adds texture. In the app, quality 30 and Sharp together took 17 s, the Sharp download (72 MB) included.

### Baking LoRAs into a model (2026-10-10, M2 24 GB, test instance)

| Base | LoRA | Time | Result |
| --- | --- | --- | --- |
| SD-1.5 (single file) | Tattoo_Maker_SD1 at 0.8 | 12 s (load, bake, save, manifest) | 512², 20 steps, seed 5: baked model vs base + LoRA mean difference 3.46 of 255; base alone vs base + LoRA 65.2 |
| Juggernaut XL v7 (single file), 2026-10-11 | Tattoo_gen at 0.8 | 34 s; 6.9 GB written | the new model in folder layout, its trigger word taken over |
| FLUX.2 [klein] 9B, 2026-10-11 | flux2klein_br33zy_v1 | refused at once | "needs about 24 GB of free memory, 17 GB are free now" (9 B parameters at 2 bytes, × 1.3) |

**Export as one file** (2026-10-11, M2): the baked Juggernaut XL written as one `.safetensors` checkpoint and loaded back
with diffusers' `from_single_file`: the same picture as from the folder (768², 8 steps, seed 7: mean difference
0.00 of 255, PSNR 138 dB). transformers 5 saves the first text encoder without `text_model.` in its keys; the export
puts it back, else `from_single_file` finds no CLIP model.

**ControlNet end to end** (2026-10-11, M2): Juggernaut XL with ControlNet Union ProMax (pose), a skeleton from the Pose
editor, 768 × 1024, 25 steps: 169 s; the dancer takes the drawn pose.

### Restore: faces and soft detail (2026-10-10, M2 24 GB)

The user's photo, a 1950s wedding scan (1567 × 2417, grey, faces about 60 px from the eyes to the mouth), and AI-made
test pictures made old (grey, blurred, three or four times smaller, grain, JPEG) with the original as the truth.

**Faces, GFPGAN v1.4 against CodeFormer** (YuNet landmarks, FFHQ alignment, 512 px):

| | GFPGAN 1.4 | CodeFormer 0.5 | CodeFormer 0.8 | CodeFormer 1.0 |
| --- | --- | --- | --- | --- |
| Test face, PSNR / SSIM to the original (made old: 23.85 / 0.572) | 23.99 / 0.575 | 23.90 / 0.578 | 24.26 / 0.587 | 24.34 / 0.588 |
| Wedding scan | invented glasses on the groom and earrings | eyes changed a little | faces kept | faces kept |
| Sepia picture | tinted the skin pink | tone kept | tone kept | tone kept |
| Time per face | 0.3 s | 0.5 s | 0.5 s | 0.5 s |

Chosen: CodeFormer. Taken from Real-ESRGAN's result, it turned the texture into wrinkles and aged the faces; taken
from the photo before the AI steps and blended at 50–60 % the faces stayed closest to themselves (defaults: faithful
90 %, strength 60 %).

**Whole picture** (test pictures made 3 × smaller; PSNR / SSIM to the original):

| | Made old | SCUNet | SCUNet GAN | SwinIR via ÷3 | SwinIR via ÷2 | Real-ESRGAN via ÷3 |
| --- | --- | --- | --- | --- | --- | --- |
| Hands | 34.98 / 0.931 | 36.41 / 0.965 | 34.10 / 0.963 | 34.74 / 0.952 | 30.80 / 0.931 | 35.03 / 0.955 |
| Street at night | 24.20 / 0.717 | 24.20 / 0.733 | 23.84 / 0.727 | 21.84 / 0.657 | 21.59 / 0.666 | 22.28 / 0.623 |

SCUNet wins the numbers but only smooths (the soft mush stays); SwinIR is the crispest but invents patterns (grids in
walls); Real-ESRGAN rebuilt clear edges with the least made up and is the fastest. Chosen: Real-ESRGAN x4plus. On the
wedding scan, ÷ 3 turned a stain into an object; ÷ 2 is the default. Texture that is lost entirely (fabric, leaves)
stays soft: only the FLUX.2 repair makes it up.

**Real-ESRGAN x4plus, tiles on the GPU** (input 784 × 1208, output 4×):

| | Tile 256 | Tile 384 | Tile 512 |
| --- | --- | --- | --- |
| float32: time, Metal peak | 27.3 s, 1.08 GB | 30.0 s, 2.32 GB | 26.0 s, 4.34 GB |
| float16: time, Metal peak | 21.4 s, 1.11 GB | 22.5 s, 2.15 GB | 19.7 s, 2.18 GB |

float16 differs from float32 by 0.08 of 255 on average; the tile size by 0.17. Restore uses float16 with the tile the
room in Metal allows (`tile_metal_gb` 1.3 / 2.4 / 3.0 GB with headroom). In the app the whole wedding scan (correct,
details ÷ 2, two faces) took 24 s, a 768 px preview 18 s.

**Dust and scratches**: the ratio of a candidate's response (black-hat / top-hat) to the average response of its
surroundings (Gaussian, σ = 2 kernels): on the AI-made old photo (drawn dust and scratches) the 75th/90th/97th
percentiles were 7.7 / 12.1 / 14.1, on the wedding scan's leaves and blossoms 3.8 / 5.0 / 8.0. A threshold of 9 − 5 ×
sensitivity (6.5 at the default 0.5) kept the drawn dust and all nine scratches and 0.17 % of the scan (the speck on
a cheek, part of a brooch) instead of 3.8 % (the leaves) with the response threshold alone.

**AI repair on a 16 GB Mac** (16 GB simulation: 12 GB kept free; FLUX.2 [klein] 4B, 4 steps, the AI-made old photo
768 × 1024 with dust removal, details and faces): the model was loaded compressed as on a 16 GB Mac, the picture took
213 s, the whole restoration 305 s, without running out of memory. The repair works at the model's pixel count (about
1 MP in the photo's proportions) whatever the photo's size, so large scans need no more.

**Correction**: the wedding scan before had 0.54 % of its pixels clipped to white (the dress), with the soft shoulder
0.00 %; the folds stayed.

**Colour profiles**: a JPEG with the profile *Rec. 2020 PQ* has paper white at code 144 of 255; read without the
profile its brightest 1 % reached 144, through LittleCMS 181, decoded by hand (203 cd/m² = white) 238.

## 5. Metal's memory budget (2026-10-10)

`torch.mps.recommended_max_memory()` on the M2 (24 GiB): 17.76 GiB = 74 %. LM Studio shows 11.84 GB on a 16 GB M4 =
74 %. The Hardware page puts the GPU budget at 74 % of the unified memory (`system_stats.metalBudgetGb`).

## 6. Mac mini M4, 16 GB (the user's live reports, 2026-10-09, release 0.4.2 and later)

| Case | Before | Now |
| --- | --- | --- |
| FLUX.1 [dev] | MLX refused ("needs about 26 GB RAM"), no picture | hands over to Diffusers, streams from the SSD, picture made |
| Krea 2 | refused | runs |
| Qwen-Image 2.1 repository | MemoryError (23 GB) | runs (text encoder in 4 bit, cached) |
| Fluxtrait single-file import | "too large" | imports |

### A GGUF model streamed on the M4 (2026-10-12, release 0.4.16, the user's log)

FLUX.1 [schnell] 8 bit GGUF (refused by 0.4.15: "needs about 23 GB"), stream cache next to the model on an external
USB disk; 1280 × 832, 18 steps (the model is made for 4), guidance 6.2 (without effect on [schnell]).

| Step | Time |
| --- | --- |
| GGUF file unpacked into the stream cache (once) | 2 min 17 s |
| T5 text encoder quantized and cached (once) | 27.3 s |
| First picture: 49 blocks streamed, 8 (2.8 GB) kept, released per prompt | 786.5 s (≈ 44 s per step) |

Per megapixel and step that is close to the M2 in the 16 GB simulation (FLUX.1 [dev], 768², ≈ 21 s per step, cache
in the page cache): the M4 is not slower, the extra comes from the size and the USB disk. With 4 steps the same
picture takes about 3 minutes. The first picture after unpacking also pays for the memory macOS still had to free.

Not yet checked on the M4 (only in the 16 GB simulation on the M2): step caching, the photo tools, the stream cache on
the internal SSD.

## 7. Interface measurements (2026-10-10, M2)

- Navigation: the rail switches to two columns below a window height of 1054 px and back above 1074 px, once in
  each direction; no jitter (2 px steps, every change of the rail width logged).
- Models → Installed, cards fixed at 230 px: 1100 px window → 3 columns, 1360 → 4, 1600 → 5, 1919 → 7, 3405 → 10
  (the maximum).
- Status bar and Hardware page: measuring every 2 s (`ps`, `vm_stat`, `os.cpus`) is not visible in the CPU figure;
  the streaming caches are measured every 30 s. On the M2 the caches took 61 GB with 13 GB left on the USB SSD.

## 7d. Z-Image Turbo on the M2: MLX or Diffusers (2026-10-13, M2, 24 GB)

The gallery pictures of the landing page again: 1024 × 1024, 9 steps, guidance 0, a freshly started app. A virtual
machine (6.6 GB) and other programs (5 GB) were open as on the day the gallery was made.

| Runtime | Per picture | Per step |
| --- | --- | --- |
| MLX, 8 bit | 321 s (with loading), 314 s, 315 s | ≈ 33 s |
| Diffusers (Apple GPU) | 366 s for the picture, 501 s with loading the model (about 2 min) | ≈ 40 s |

MLX stays the faster runtime for Z-Image Turbo. The landing page said "under a minute per picture"; it now says
"about five minutes per picture". A first Diffusers run with three pictures in a row ended without a picture: the
engine restarted twice and the window of the test instance went away; one picture at a time went through.

## 7e. Attention in slices for SD 1.5 and SD 2 (2026-10-14, M2 24 GB, test instance)

A SD 1.5 model (epiCPhotoGasm) at 768 × 768 on a Mac kept at the 16 GB budget. Without slicing the step needed about
16 GB, the Mac swapped and a step took 20 s. `enable_attention_slicing` above 512 × 512 keeps the same picture under
7.5 GB, and the step takes 4.2 s — about five times faster, with no change to the picture. SDXL only slices above
1536 × 1536, where the same effect starts; below that slicing costs time without saving memory.

## 7f. FLUX 3 Image Klein with flux3-mlx, and the MLX runtime update (2026-10-22, M2, 24 GB)

A red fox in snow, 1024 × 1024, 16 steps, seed 7, a full scene caption (the model card's style); VulKara's MLX engine in
a separate venv with the new lock (mflux 0.23.0, flux3-mlx 0.1.0, mlx-lm 0.32.2, MLX 0.32.4), each case its own process
as the app runs it. Peak: the larger of the process's resident memory and MLX's peak (`mx.get_peak_memory`).

| Case | Time per picture | Peak | Note |
| --- | --- | --- | --- |
| VisualInference 6 bit | 387 s | 12.1 GB | both parts resident |
| VisualInference 8 bit | 376 s | 13.3 GB | finer fur than 6 bit, otherwise the same picture |
| 6 bit, 16 GB budget (12 GB kept free) | 377 s | 8.5 GB | prompt encoded before the transformer loads; same picture |
| 8 bit, 16 GB budget | 364 s | 9.7 GB | fits a 16 GB Mac too |
| Black Forest Labs' 16 bit files | 314 s | 14.3 GB | 18.9 GB download (of about 41 GB in the repository); planned 19 GB RAM |
| 6 bit, edit with a reference picture | 188 s | 10.0 GB | size of the reference (512 px) |
| 6 bit, prompt upsampler (4 bit, mlx-lm) | +30–37 s | 14.0 GB (8.5 GB in the 16 GB budget) | from "a red fox in snow at golden hour"; caption of about 1,500 characters |
| 6 bit, LoRA in diffusers' names (SimpleTuner photo aesthetics, rank 32) | 387 s | 12.1 GB | 172 of 172 layers; cooler colours, more contrast |
| 6 bit, LoRA in Black Forest Labs' names (Radiance Chrome, rank 32), 832 × 1216 | 378 s | 12.0 GB | 258 of 258 layers |

The memory plan (`importer.make_plan`, `staging_frees_denoiser`) came out 0.2–0.6 GB above each measured peak. A first
version encoded the prompt with the transformer already loaded (flux3-mlx's own order): then both parts are in memory
at once, and Black Forest Labs' files would have needed 27 GB.

The same matrix with the MLX runtime before and after the update (mflux 0.20.0 / MLX 0.32.3 against mflux 0.23.0 /
MLX 0.32.4), 512 × 512, seed 7: every case ran with both; times within ±15 %, peaks the same (FLUX.2 [klein] 4B 40 s /
9.4 GB, 9B 77 s / 10.3 GB, Z-Image Turbo 103 s / 11.9 GB, FLUX.1 [dev] 12 steps 193 s / 11.9 GB, with a LoRA 222 s,
Krea 2 141 s / 15.4 GB, with a LoRA 154 s, Ideogram 4 12 steps 345 s / 15.0 GB). The pictures are not bit-identical
(PSNR 24–36 dB against the old runtime) but show the same subject and composition; only fine detail moves. In the 16 GB
budget Krea 2 ran (13.3 GB); FLUX.2 [klein] 9B and Ideogram 4 are refused by MLX there and go to Diffusers, as before.
LoRA training (FLUX.2 [klein] 4B, 3 pictures, 6 steps, 256 px) finished with both runtimes in 82–83 s.

## 7g. New model types: Lumina 2, ERNIE-Image, Pony V7 (2026-10-24, M2 24 GB, own test instance)

1024 × 1024, one picture each, the app's queue (engine log / ComfyUI log). A run beside another busy engine (9 GB held)
swapped and took 67–400 s per step; these are the runs alone:

| Model | Runtime | Steps | Per step | Per picture |
| --- | --- | --- | --- | --- |
| NetaYume Lumina v4 (2.6B, bf16, CFG 5.5) | ComfyUI | 20 | 30 s (PyTorch attention) / 34 s (ComfyUI's default sub-quadratic) | about 10 min |
| ERNIE-Image-Turbo (8B, 4 bit, no guidance) | MLX | 8 | 42 s | 5.7 min (load 36 s) |
| Pony V7 base (6.8B, GGUF Q8_0, CFG 3.5) | ComfyUI | 30 | 50 s | about 25 min |

ComfyUI allows Lumina 2 only in bf16 or fp32 (no fp16 on M1/M2). The attention option is within 10 %, so ComfyUI keeps
its default. ComfyUI keeps the text encoder in RAM until memory runs short (Lumina: Gemma 2 2B, 5 GB, on the CPU).

## 7h. ComfyUI on the Mac without the whole model in memory (2026-10-25, M2 24 GB, ComfyUI 0.38.0)

Pony V7 base GGUF Q8_0 (7.3 GB on the external USB SSD), 1024 × 1024, 3 steps, CFG 3.5, a private ComfyUI started
beside the app (scratchpad `cfexp/run.py`); *footprint* is the peak of macOS' `footprint` for the ComfyUI process
(memory macOS can not drop; file pages mapped from the model file do not count). ComfyUI forces its memory mode to
SHARED on MPS (`--lowvram` / `--novram` are ignored, PR #15998 open); the experiment set the mode from a custom node.
comfy-aimdo (Dynamic VRAM) logs "unsupported operating system: Darwin". 16 GB simulation here: 8 GB locked with
`mlock` (wired), as the 12 GB reserve of the app does not limit ComfyUI.

| Memory mode | RAM | Per step | Footprint | Resident transformer |
| --- | --- | --- | --- | --- |
| SHARED (ComfyUI's Mac default) | 24 GB | 44 s | 15.0 GB | 7.1 GB, text encoder kept |
| NO_VRAM | 24 GB | 50 s | 7.7 GB | none, every layer copied in per step |
| SHARED | 16 GB simulated | 225 s (swapping) | 14.0 GB | 7.1 GB, "0 models unloaded" |
| NO_VRAM | 16 GB simulated | 97 s | 6.8 GB | none |
| LOW_VRAM | 16 GB simulated | 88 s | 8.9 GB | 2.0 GB, 5.0 GB from the file |

The GGUF loader maps the file (numpy memmap) and ComfyUI copies each offloaded layer to the GPU for its turn, so in
NO_VRAM / LOW_VRAM the model streams from the file through the macOS file cache. On 24 GB that costs 14 % per step; on
16 GB the SHARED default swaps and is 2.5 times slower than LOW_VRAM.

In the app (Settings → *ComfyUI: load GGUF models piece by piece from the SSD*, the engine switching ComfyUI to
LOW_VRAM through `custom_nodes/vulkara_memory`): Pony V7 Q8_0 with 12 GB kept free on the M2 (so LOW_VRAM was chosen,
24 GB physically), 30 steps at 1024 px: 45 s per step, 1396 s per picture, the picture as expected.

## 7i. SDXL and the Metal memory between jobs (2026-10-26, M2 24 GB, Diffusers runtime)

JuggernautXL v7 (single file, 16 bit, 6.95 GB of weights), 8 to 12 steps, one engine running job after job;
`torch.mps.current_allocated_memory()` (alloc), `driver_allocated_memory()` (driver) after each job and the driver's
peak sampled every 0.1 s during it.

| Job | alloc after | driver after | driver peak |
| --- | --- | --- | --- |
| text to image 1024 px (eight jobs, also 1536 px and 832 × 1216 × 2 between them) | 6.95 GB | 7.68 GB each time | 8.96 GB (1536 px: 10.12, two pictures: 10.18) |
| LoRA A, B, A + B, A, none | 7.18 / 7.41 / 6.95 GB | up to 8.15 GB, 7.68 again without LoRA | 9.45 GB |
| img2img 1024 px, before | 6.96 GB | **8.76 GB** (kept until the model changed) | 10.21 GB |
| img2img 1024 px, after the fix (twice, then inpaint) | 6.95 GB | 7.67 GB | 8.96 GB |
| a job stopped after 3 steps, before | 6.95 GB | **8.69 GB** until the next job ended | 8.76 GB |
| a job stopped after 3 steps, after the fix | 6.95 GB | 7.61 GB | 8.76 GB |

Text to image does not grow: the cache is emptied after every picture. Two leaks were found and closed:

- img2img and inpaint moved SDXL's VAE to float32 for every input picture and back to float16 (`force_upcast`); the
  weights moved in the middle of a job land between its buffers, and 1.8 GB of the Metal cache could not be given back.
  The VAE now stays in bfloat16 (float32's range) for encoding too: no move, 1.25 GB less peak, pictures as before.
- A stopped or failed job skipped the cleanup after its picture: the engine now empties the cache after every job.

The process footprint (CPU side) still grows slowly with LoRA changes: 7.7 to 8.6 GB over ten jobs with four LoRA
changes and a model change; not traced further.

## 7j. AuraFlow on the Diffusers runtime (2026-10-26, M2 24 GB, planned as on 16 GB)

fal/AuraFlow-v0.3 (repository, fp16 files, 15.7 GB download), the engine planning with 16 GB: transformer in 8 bit
(quantized once, 32 s, then from the cache), text encoder loaded per prompt; guidance 3.5, prompts padded to 768 tokens.

- 1024 px, 20 steps: 889 s per picture (44 s per step), footprint about 9.8 GB; the fox in snow as asked.
- 768 px, 16 steps with an AuraFlow LoRA for ComfyUI (p1atdev's PVC style, original layer names, converted on loading):
  433 s; the figure clearly in the LoRA's style.
- With the 24 GB plan (transformer in 16 bit, 18.7 GB estimated) the M2 swapped while other engines held 5 GB: the
  first step took minutes, stopped.

## 7k. MLX: compiling, the noise schedule, the VAE (2026-10-26, M2 24 GB, mflux 0.23.0)

**Noise schedules against diffusers (the reference, with each model's scheduler_config.json), 1024 px:** FLUX.1 [dev]
(25 steps), FLUX.1 [schnell] (4), FLUX.2 [klein] 4B (4) and ERNIE-Image Turbo (8) match to four decimals. Z-Image does
not: mflux shifts by the resolution (Turbo: 3.16 at 1024 px), its configs ask for a fixed shift (Turbo 3, Base 6). Turbo,
9 steps: mflux 0.9619, 0.9170, … 0.2830; reference 0.9600, 0.9130, … 0.2727. VulKara now hands mflux the reference
schedule (`mlx_schedulers.py`, equal to diffusers' to 1e-7).

| Z-Image Turbo, 1024 px, 9 steps, seed 11 | per picture | per step | peak |
| --- | --- | --- | --- |
| mflux's schedule (before) | 310 s | 30.6 s | 17.95 GB |
| reference schedule | 300 s | 30.4 s | 17.95 GB |
| reference schedule + `mx.compile` forced on | stopped: 130 to 185 s per step | | |

The pictures with the two schedules differ slightly (34.8 dB PSNR, same subject and layout); the same settings twice give
the same picture (168 dB).

**`mx.compile`:** mflux already compiles the denoising step of Z-Image, FLUX.2 [klein], Krea 2, Ideogram 4 and ERNIE-Image
on M3 and newer, and deliberately not on M1/M2 (`AppleSiliconUtil.is_m1_or_m2`). Forced on the M2 it makes each step
four to six times slower. FLUX.1 is not compiled by mflux on any chip. The M4 (Mac mini) compiles already; not measured.

**VAE decoding:** encoding the prompt, decoding and saving take about 25 s of the 300 s per Z-Image picture together. A
tiny VAE (TAESD / TAEF1) would save a few seconds per picture at a visible loss of detail; it is only worth it for live
previews during the steps.

## 7l. Z-Image on MLX on a 16 GB Mac (2026-10-26, M2 24 GB with the 16 GB plan, mflux 0.23.0)

The user's Mac mini M4 (16 GB) made Z-Image Turbo on MLX at 1024 px with 92.9 s and then 104 s per step; the M2 needs
about 30 s. Measured on the M2 with the memory plan of a 16 GB Mac (`choose_quant` with 16 GB), 1024 px, 9 steps, seed 11,
MLX's own peaks (`mx.get_peak_memory`) per phase:

| Plan | per step | per picture | steps | VAE decode (whole peak) |
| --- | --- | --- | --- | --- |
| before: 4 bit, text encoder kept | 30.9 s | 304 s | | 12.9 GB |
| 8 bit, text encoder dropped after the prompt | 30.2–30.6 s | 345 s, again 286 s | 7.5–8.0 GB | 12.3–13.8 GB |
| as above + mflux's low-RAM settings (VAE in tiles, 1 GB buffer cache) | 29.8 s | 298 s, again 272 s | 7.5–8.0 GB | 8.8 GB |

The peak was never the steps but the VAE decoding the picture. With 12.9 GB for MLX alone (Metal lets one process use
about 11.8 GB of 16 GB) and macOS and the app beside it, the Mac mini swapped. Now a 16 GB Mac loads Z-Image in 8 bit,
drops the text encoder after encoding (the encoded prompts stay cached, the same prompt again loads nothing), decodes in
tiles (`low_ram`, as mflux's MemorySaver does) and keeps at most 1 GB of freed buffers (`free_buffers`, below): 8.8 GB at
most. The tiled
picture against the untiled one: 38.6 dB PSNR, no seam visible at full size. Not yet measured on the M4 itself (Hardware
→ Benchmark there).

**MLX's buffer cache, every model and Mac.** The first benchmark in the test instance (FLUX.2 [klein] 4B, 512 px, two
pictures) showed the MLX engine with a footprint of 17.9 GB for a peak of 10.1 GB: MLX keeps freed buffers for reuse
without a limit, 9.9 GB of them after each picture beside 7.5 GB in use, and the M2 swapped (4 GB added). The resident
size the status bar counts showed 0.8–2.4 GB of it. Now the cache is limited to 1 GB (mflux's low-RAM value) and emptied
after loading and after each picture; each picture logs what it gave back:

| FLUX.2 [klein] 4B, 512 px, 2 pictures (M2 under load from other apps) | per picture | footprint at most | swap added |
| --- | --- | --- | --- |
| cache without a limit | 90 s, 116 s | 17.9 GB | 4.1 GB, 0.7 GB |
| emptied after each picture | 71 s, 71 s | 11.2 GB, 10.6 GB | 2.5 GB, 0 |
| limited to 1 GB and emptied | 87 s (with loading), 69 s | 9.1 GB, 10.3 GB | 0, 0 |

## 7m. The memory plan against what the engines used (2026-10-26, M2 24 GB)

Every engine now measures its own peak per job (macOS's footprint of its processes, with what the GPU holds, reset at
the start of the job: `proc_pid_rusage`, `interval_max_phys_footprint`) and reports what its memory plan expected for
the picture size. Benchmarks at 1024 px, 3 steps, 2 pictures per model, seed 11; the second picture (no loading)
counts. The Mac had 10 to 18 GB in swap throughout (other apps), so the seconds per step are not comparable; the
footprints are.

| Model (runtime, bit size) | engine at most | planned | over the plan |
| --- | --- | --- | --- |
| Z-Image Turbo (MLX, 8 bit) | 16.8 GB | 14.9 GB | +1.9 |
| FLUX.2 [klein] 4B (MLX, 8 bit) | 13.3 GB | 12.5 GB | +0.8 |
| FLUX.2 [klein] 9B (MLX, 4 bit) | 14.3 GB | 14.5 GB | -0.2 |
| Krea 2 Turbo (MLX, 4 bit) | 18.2 GB | 14.7 GB | +3.5 |
| ERNIE-Image Turbo (MLX, 4 bit) | 13.7 GB | 11.2 GB | +2.5 |
| FLUX 3 Image Klein (MLX, 6 bit) | 13.1 GB | 12.5 GB | +0.6 |
| FLUX.1 dev (MLX, 4 bit) | 18.1 GB | 13.9 GB | +4.2 |
| JuggernautXL v7 (Diffusers, 16 bit) | 8.8 GB | 9.4 GB | -0.6 |
| epiCPhotoGasm, SD 1.5 (Diffusers, 16 bit) | 8.8 GB | 3.9 GB | +4.9 |
| SD3.5 Medium (Diffusers) | 14.0 GB | 14.7 GB | -0.7 |
| Chroma1 Flash (Diffusers, 8 bit) | 11.9 GB | 15.5 GB | -3.6 |
| Qwen-Image 2.1 (Diffusers, streamed from the SSD) | 15.7 GB | 13.0 GB | +2.7 |
| AuraFlow v0.3 (Diffusers, 8 bit) | 14.6 GB | 13.3 GB | +1.3 |
| Pony V7 Q8_0 (ComfyUI) | 14.9 GB | (no plan) | |

The first picture after a change of model counts the old model as well (it is unloaded inside the job): AuraFlow 20.8 GB.
MLX's own peaks (`mx.get_peak_memory`) were 10 to 12 GB over the weights for every mflux model: as with Z-Image (7l)
it is the VAE decoding the picture in one piece. The Diffusers runtime decodes in tiles anyway, its plan holds.

**What changed.** The MLX plan counts the one-piece decode per family (`DECODE_GB`: Z-Image 2.5, FLUX.2 1, Krea 2 2,
ERNIE 2.5, FLUX.1 4.5 GB at 1024 px), but not for choosing the bit size, so 16 GB Macs keep theirs (they decode in tiles
anyway). Before each picture the engine holds the plan against what macOS has available plus what the engine itself
holds: if the one-piece decode does not fit, it decodes in tiles (no visible difference, 7l) and the job says so; if
the picture is short even then, the job says how much was free (also Diffusers and FLUX 3). The Diffusers runtime now
also empties the Metal cache after it dropped the old model object (its transformer or streamed model stayed until the
next job).

| After (same Mac, same load) | engine at most | planned | per step |
| --- | --- | --- | --- |
| FLUX.1 dev, decoded in tiles (free memory short) | 13.0 GB (was 18.1) | 13.9 GB | 46 s (was 175 s) |
| Krea 2 Turbo, decoded in tiles | 15.6–16.6 GB (was 18.2) | 14.7 GB | 78–85 s (was 211–214 s) |
| Z-Image Turbo, in one piece (enough free) | 17.0–17.5 GB | 16.9 GB (was 14.9) | 76–92 s |

Open: SD 1.5 uses 7.3 GB at 512 px too (2.6 GB when idle, 2 GB of 16 bit weights; plan 3.3 GB), also right after a
fresh load, so it is not the model before; the cause is not found yet, and on 16 GB it still fits. Krea 2 stays 1.9 GB
over its plan when tiled; raising its activations would make it not fit 16 GB at all, so the plan stays. AuraFlow's
1.3 GB over the plan: raising it made Pony V7 (GGUF) not fit 16 GB, so it stays too. Qwen-Image 2.1 streamed: 2.7 GB
over, the blocks in flight while streaming; not changed without a measurement of its own.

## 7n. Attention on MPS: head sizes the fused kernel does not take (2026-10-27, M2 24 GB, torch 2.14.1)

SD 1.5 used 7.3 GB at 512 px for 2 GB of weights (7m). Sampling the engine's footprint and the MPS allocations through
a job: idle 2.5 GB, the first step jumps to 7.1 GB, inside the UNet's first down block. `scaled_dot_product_attention`
on MPS runs a fused kernel only for some head sizes; for the others it holds the whole attention matrix:

| head size, 2 x 8 heads, 4096 tokens | extra MPS memory | time |
| --- | --- | --- |
| 32, 64, 72, 80, 96, 128, 160, 256 | 0 | 31 ms (64) |
| 8, 16, 24, 40, 48, 56, 60, 65, 70 | 2.5 to 3.5 GB | 193 ms (40) |
| 40 at 8192 tokens | 10 GB | 898 ms |
| 40 padded with zeros to 64 | 0.03 GB | 31 ms, same result (max. difference 6e-5) |

SD 1.5's first attention level has a head size of 40. The Diffusers runtime now pads such heads with zeros to 64 on MPS
(`fused_attention`; zeros add nothing to the scores, the padded output is cut off) and no longer slices the attention
of SD 1.5/2 and SDXL on MPS (`enable_attention_slicing` above 512² or 1536²), as the fused kernel never holds the maps.
The picture against the unpadded one: 49.0 dB PSNR.

| Measured (engine probe and Hardware → Benchmark) | before | after |
| --- | --- | --- |
| epiCPhotoGasm (SD 1.5), 512 px, 25 steps | 1.55 s/step, 7.3 GB | 0.72 s/step, 3.7 GB |
| epiCPhotoGasm (SD 1.5), 1024 px (was sliced) | 9.4 s/step, 9.8 GB | 4.8 s/step, 5.0 GB |
| JuggernautXL (SDXL), 2048 px, 3 steps (was sliced) | 111 s/step, 17.4 GB | 28 s/step, 12.1 GB |
| JuggernautXL (SDXL), 1024 px | 4.9 s/step, 9.0 GB | 5.0 s/step, 8.8 GB |

SD 1.5's plan (3.3 GB at 512 px, 3.9 GB at 1024 px) is now close at 512 and 1.1 GB under at 1024; it stays, since a
bigger activation figure would let it not fit an 8 GB Mac at all. ComfyUI's attention: 7o.

## 7o. ComfyUI's attention on MPS (2026-10-28, M2 24 GB, ComfyUI runtime, torch fp16)

ComfyUI turns on PyTorch's attention only on NVIDIA, Intel, Ascend and some AMD cards; on the Mac it used its
sub-quadratic attention (log: "Using sub quadratic optimization for attention"), which computes in chunks with plain
tensor operations. Its attention functions alone (`attention_sub_quad`, `attention_pytorch`), 5 runs each:

| case (batch, heads, head size, tokens) | sub-quadratic | PyTorch (SDPA) |
| --- | --- | --- |
| SD 1.5 at 512 px (2, 8, 40, 4096) | 108 ms, +3.0 GB | 189 ms, +3.0 GB; padded to 64: 32 ms, 0 GB |
| SD 1.5 at 1024 px (2, 8, 40, 16384) | 2337 ms, +2.0 GB | ends the process (16 GB buffer); padded: 494 ms, 0 GB |
| SDXL at 1024 px (2, 10, 64, 4096) | 118 ms, +2.5 GB | 39 ms, 0 GB |
| SDXL at 2048 px (2, 10, 64, 16384) | 2396 ms, +3.2 GB | 624 ms, 0 GB |
| FLUX at 1024 px (1, 24, 128, 4608) | 239 ms, +2.7 GB | 122 ms, 0 GB |
| AuraFlow at 1024 px (2, 12, 256, 4352) | 283 ms, +2.6 GB | 344 ms, 0 GB |

ComfyUI now starts with `--use-pytorch-cross-attention`; its node `vulkara_memory` pads heads the fused kernel does not
take to 64, as the Diffusers runtime does (7n), and keeps the VAE on split attention: an MPS allocation that does not
fit ends the process instead of raising, so ComfyUI's fallback to slices would not run. Whole pictures (Hardware →
Benchmark, 1024 px, 6 steps, 2 pictures each, the Mac swapping 7 to 16 GB of other programs):

| model | before | after | picture against before |
| --- | --- | --- | --- |
| Anima-Turbo | 12.1 s/step, engine 10.0 GB | 11.8 s/step, 10.0 GB | 31.5 dB, same picture |
| NetaYume v4 (Lumina 2) | 31.9–33.0 s/step, 15.5–16.2 GB | 28.7 s/step, 14.1–15.3 GB | 37.0 dB |
| Pony V7 Q8 GGUF (AuraFlow) | 46.0–46.1 s/step, 14.8–15.9 GB | 46.7 s/step, 12.3–13.7 GB | 55.7 dB |

The attention is a small part of a step of these models: Lumina 2 gets 10 % faster, all of them use up to 2.2 GB less.
Wan and upscaling (same day, test instance, the ComfyUI files before and after in turn): Wan 2.2 I2V 14B Q4_K (both
experts streamed from the SSD, text encoder FP8), 832 × 480, 1 s, 4 steps: 210.5 s per step and 669 s before, 148.3 s
per step and 515 s after (30 % less per step), engine at most 12.7 and 12.9 GB, 44 and 30 GB read; the last frame
against before 43.2 dB, the same video. Upscale × 2 (Real-ESRGAN, no attention): 20.7 and 21.9 s, 7.7 and 7.6 GB.

## 7p. Plans brought to the measurements (2026-10-28)

**SD 1.5.** With fused attention (7n) SD 1.5 used 3.7 GB at 512 px and 5.0 GB at 1024 px; the plan said 3.3 and 3.9.
Its activations at 1024 px are now 1.9 GB (were 0.8), and whether SD 1.5 (and SD 2) fits is judged at its own size
(512 and 768 px, `NATIVE_SIDE`), not at 1024 px: plan 3.6 GB at 512 px, 5.0 GB at 1024 px. It still fits an 8 GB Mac
(budget 4 GB) at 512 px, in 16 bit. A plan stores the size its activations are for (`activations_side`); older plans
without it are for 1024 px as before.

**ComfyUI.** Its jobs now report the plan of a model held whole in memory (the one that chooses SHARED or LOW_VRAM), so
the benchmark shows it beside the engine's peak; streamed models and videos report none. Against 7o at 1024 px:
Anima-Turbo 9.1 GB planned / 10.0 GB used, NetaYume v4 14.1 / 14.1–15.3, Pony V7 Q8 13.9 / 12.3–13.7.

**Left as they are.** Krea 2 tiled (+1.9 GB) and AuraFlow on Diffusers (+1.3 GB): a higher figure makes them or Pony V7
not fit 16 GB (7m). Qwen-Image 2.1 streamed (+2.7 GB): needs a streamed measurement of its own.

## 7q. FP8 files on ComfyUI (2026-10-28, M2 24 GB, torch 2.14.1)

The memory plan counts an FP8 safetensors file of a ComfyUI model as 16 bit. That is what the Mac holds: ComfyUI
loads FP8 weights in 16 bit where they fit (`unet_dtype`), MPS has no FP8 compute. Where 16 bit does not fit (more
parameters x 2 than 88 % of the memory less a reserve: Pony V7 in FP8 on 16 GB) ComfyUI keeps the weights in FP8 and
casts them per layer, which MPS cannot do. Anima-Turbo converted to FP8 and loaded as on a Mac too small for it: weights
in FP8 (3.0 GB), the first layer stops with "Undefined type Float8_e4m3fn". `vulkara_memory` now keeps such a model in
16 bit on MPS (same probe: bfloat16, 4.9 GB, runs): a Mac short of memory swaps instead of stopping the job.

## 7r. Stopping while SSD streaming is prepared (2026-10-28, M2 24 GB)

Writing the blocks into the SSD streaming cache (and unpacking a GGUF file for it) did not look at a stop: a job
stopped there said "Stopping" until the whole preparation was done. Chroma1 Flash streamed (VK_SSD_STREAMING=always,
empty cache), stopped at 21 % of the preparation: before 84.9 s from the stop to the end of the job (the preparation
went on, the model was loaded), now 0.0 s (it ends at the next block; the blocks written are written again next
time). Loading the checkpoint before the preparation (36 s here) still runs to its end.

## 7s. Qwen-Image 2.1 streamed with the 16 GB plan (2026-10-28, M2 24 GB, memory kept free 12 GB)

Benchmark, 1024 px, two pictures, Diffusers runtime, transformer streamed from the SSD, text encoder in 4 bit.

| Picture | s/step | whole | peak (engine) | plan | read from the SSD | swap |
| --- | --- | --- | --- | --- | --- | --- |
| 1st (text encoder quantized) | 40.7 | 10 971 s | 14.5 GB | 9.1 GB | 69.8 GB | 7.8 → 12.0 GB |
| 2nd (from the quantized cache) | 51.7 | 221 s | 11.8 GB | 9.1 GB | 37.4 GB | 7.3 → 8.5 GB |

The 16 GB plan quantizes the 8.8B text encoder to 4 bit (on 24 GB it stays in 16 bit), once per model: 10 766 s on the
CPU here, with the Mac swapping (12 GB kept free). The quantized copy is kept (`quant_cache`), the second picture
started generating within seconds. The peak of a cached run is 2.7 GB over the plan, as in 7m: the blocks streamed in
and read ahead are not in the plan. Left as it is until the streamed blocks are planned (16 GB still falls back to
streaming more of the model). Open: quantizing the text encoder took three hours on a Mac short of memory.

## 7t. Prompt embeddings kept on disk (2026-10-29, M2 24 GB, memory kept free 12 GB)

Benchmark, Qwen-Image 2.1, 1024 px, 4 steps, seed 12, Diffusers runtime, transformer streamed from the SSD, text
encoder in 4 bit. First run with an empty `prompt_cache`, then the app restarted and the same job again.

| Run | text encoder | generating | whole | peak (engine) | plan | swap at start |
| --- | --- | --- | --- | --- | --- | --- |
| empty prompt cache | loaded 8.6 s (+ 11 911 s quantized again, see below) | 2 354 s | 14 292 s | 14.5 GB | 9.1 GB | 6.7 GB |
| prompt from the cache | not loaded | 1 697 s | 1 711 s | 12.1 GB | 9.1 GB | 6.7 GB |
| 4 bit copy, empty prompt cache (after the fix) | from `quant_cache` and encoding: 2 586 s | 1 658 s | 4 264 s | 12.0 GB | 9.1 GB | 6.1 GB |

The second run never loads the text encoder: the embeddings (156 KB) come from
`<data>/prompt_cache/<sha256>.safetensors`, the kept blocks of the transformer stay in memory, the peak is 2.4 GB lower
and the picture is the same to the pixel. The seconds of generating differ by swap (the Mac swapped 6.7 → 11.4 GB), not
by the cache.

The first run quantized the text encoder again although its 4 bit copy was cached: loading int4 weights on the CPU made
optimum-quanto compile its C++ unpack kernel, which needs a compiler and fails under `Application Support` (torch
passes the `-L` path with its space unquoted); `quant_cache` then took the copy for broken and rebuilt it. Fixed: the
pure torch unpack that already served MPS now serves the CPU too (`quanto_mps.patch`, before every restore), and
`test_quant_cache` covers 4 bit and checks the kernel is never built. With the fix the third run loaded the 4 bit copy
(21.7 s alone in a probe, 368 int4 layers unpacked in torch on the CPU: 10.8 s of it) but stayed 2 586 s in *Loading
text_encoder* before generating: the time goes to encoding the prompt with the restored int4 encoder, not to loading.
Found and fixed in 7u: moving the int4 layers to the GPU repacked each of them (now 28.9 s instead of 2 586 s). This also hit 0.7.5 on 16 GB Macs: Qwen-Image
2.1's text encoder was quantized for hours on every engine start.

## 7u. int4 weights moved to the GPU (2026-10-29, M2 24 GB, memory kept free 12 GB)

Why encoding took 2 586 s in 7t: optimum-quanto stores int4 weights made or restored on the CPU in its TinyGemm layout
(meant for computing on the CPU); `.to("mps")` unpacks and packs every layer again. One layer of Qwen-Image 2.1's text
encoder (3584 x 18944, bfloat16, group 128):

| | to MPS | forward, 64 tokens | max. difference to the CPU result |
| --- | --- | --- | --- |
| TinyGemm on the CPU (before) | 20.7–21.8 s | 0.07–0.21 s | |
| plain packing on the CPU (after) | 0.04 s | 0.045 s | 0.008 of 2.8 (bfloat16 rounding) |

`quanto_mps.patch` keeps the plain packing on the CPU on Macs with MPS (nothing computes int4 weights on the CPU there).
The run of 7t again (Qwen-Image 2.1, 4 bit copy, empty prompt cache, new start):

| Run | *Loading text_encoder* (with encoding) | generating | whole | peak (engine) |
| --- | --- | --- | --- | --- |
| before | 2 586 s | 1 658 s | 4 264 s | 12.0 GB |
| after | 28.9 s | 1 677 s | 1 724 s | 11.8 GB |

The picture is the same to the pixel. It applies to every int4 component of the Diffusers runtime (16 GB plans), also
to one quantized freshly.

## 7v. Seams between VAE tiles of Qwen-Image (2026-10-29, M2 24 GB)

Qwen-Image 2.1 showed faint vertical streaks in plain areas (a sky at x 825 and 974 of 1024 px). They are the seams of
the VAE's tiles: its decoder tiles at 256 px with a stride of 192, so neighbours are blended over 64 px only (the
setting `tile_sample_min_size` VulKara capped before does not exist on this VAE). One latent of that picture decoded
in tiles against decoded whole (0–255 per channel, bfloat16):

| Tiles | strongest column | mean | memory of decoding | seconds |
| --- | --- | --- | --- | --- |
| 256 px, stride 192 (before) | 4.4 | 1.19 | 1.1 GB | 20 |
| 256 px, stride 128 | 2.8 | 0.91 | 1.15 GB | 40 |
| 256 px, stride 128, next tile whole 16 px before the end (16 GB plans) | 2.0 | 0.79 | 1.15 GB | 40 |
| 512 px, stride 384 | 2.1 | 0.46 | 3.3 GB | 18 |
| 512 px, stride 384, next tile whole 16 px before the end (where the plan has room) | 0.96 | 0.42 | 3.3 GB | 18 |
| whole, no tiles | 0 | 0 | 13.2 GB | |

The outermost pixels of a tile differ most from its neighbour, so the blend now reaches the next tile 16 px before the
overlap ends. 512 px tiles are used only where the plan leaves 2.5 GB beside denoising and the model is not streamed.
The real run of 7u (Qwen-Image 2.1, 1024 px, seed 12), sky x 700–1024, y 60–420, mean step between
neighbouring columns (the median column is 0.23):

| Run | strongest seam | peak (engine) | whole |
| --- | --- | --- | --- |
| 16 GB plan, before (7u) | 0.73 (x 825), 0.64 (x 974) | 11.8 GB | 1 724 s |
| 16 GB plan, 512 px tiles tried first | 0.78 (x 885) | 13.6 GB | 1 805 s |
| 16 GB plan, 256 px, stride 128, new blend | 0.47 | 12.1 GB | 1 757 s |
| memory kept free 8 GB (streamed, the same tiles) | 0.48 | 16.7 GB | 1 843 s |

At normal contrast the streaks are gone; boosted 4 times one faint seam is left. 512 px tiles were dropped for the
16 GB plan: 1.7 GB more and the seam only moved.

## 7w. Where the peak of a streamed Qwen-Image 2.1 picture lies (2026-10-29, M2 24 GB, memory kept free 12 GB)

The 16 GB plan of 7v plans 9.1 GB, the engine peaks at 12.1 GB. Whether decoding is the missing part: the same run
(prompt from the prompt cache, 9 of 32 blocks kept, 3.7 GB) with the footprint of the engine sampled about every 2 s
next to its log:

| Phase | footprint (sampled) |
| --- | --- |
| model loaded, before the first step | 9.9–10.1 GB |
| denoising, blocks streamed | 9.4–11.6 GB, swinging with the blocks in flight |
| VAE decoding in 256 px tiles (about 40 s) | 9.7 GB at its start, then 7.6 GB |
| after the picture | 6.6–7.1 GB |

Peak of the job (macOS's interval maximum): 12.1 GB, 1 863 s. Decoding is not the peak in the Diffusers runtime: its
tiles need about 1.1 GB, less than the denoising's activations it follows.

The gap was the plan itself: where a 16 GB plan keeps blocks and releases them while a new prompt is encoded
(`keep_plan`), it returned the streamed plan without them, so 9.1 GB was the encoding's peak and the 3.7 GB of kept
blocks were not counted while denoising (also not in the warning about free memory and the room for a ControlNet). Now
the plan counts them while denoising:

| Run (same picture) | planned | engine at most | whole |
| --- | --- | --- | --- |
| before | 9.1 GB | 12.1 GB | 1 863 s |
| after | 11.8 GB | 12.1 GB | 1 705 s |

The rest, 0.3 GB, is within what the blocks in flight swing by. Also seen: after the last step two blocks read ahead
for the next picture stay in memory (0.85 GB, until the next picture or the model is unloaded), and reading a block into
one buffer that the tensors view (no second copy) is faster (3 blocks 0.8 s instead of 1.4 s) but holds the same
memory; neither is changed.

## 7x. Prompt encodings of MLX models on disk (2026-10-29, M2 24 GB, memory kept free 12 GB)

On a 16 GB plan Z-Image, Krea 2 and Ideogram 4 on MLX drop their text encoder after encoding a prompt; another prompt
loads the whole model again. Their encodings (the entries of mflux's prompt caches) now go into the prompt cache on
disk as well (`prompt_cache.save_mlx`), so a prompt encoded before needs neither the text encoder nor a new load, also
after a restart. Z-Image Turbo (MLX, 8 bit, staged), 512 px, 9 steps, seed 5: prompt A, prompt B, A again, a restart
of the app, A again:

| Picture | cache off | cache on | read from disk (off / on) |
| --- | --- | --- | --- |
| A, first | 105.5 s | 104.2 s | 30.5 / 30.4 GB |
| B | 97.7 s | 97.8 s | 30.4 / 30.3 GB |
| A again (the model held B's prompt) | 98.7 s (loaded again) | 64.4 s (not loaded) | 30.4 / 0 GB |
| A after a restart | 104.7 s | 95.5 s (text encoder not run) | 30.5 / 23.2 GB |

Peaks 8.7–9.7 GB either way; the four pictures of A are the same to the pixel. Again after the review's fixes (keys per model as mflux's own: the size only for Ideogram 4): A again 61.6 s with nothing read, after a restart 96.4 s, the same pictures. One entry is about 80 KB at 512 px. Also
fixed: the key of what a staged model had encoded held neither the negative prompt nor the guidance, which Krea 2's
encodings depend on. Not done: a model loaded for a prompt from the cache still loads its text encoder (mflux loads
every part at once).

## 7y. Engines without a job, and after the app is gone (2026-10-29, M2 24 GB)

**Idle.** The engines kept their model after the last picture until the next job or the end of the app. Now they free it
after a time without a job (Settings → Engine, default 10 min). Z-Image Turbo (MLX, 512 px), then the footprint of the
engine processes every 30 s with the time set to 5 min:

| After the picture | engines' footprint |
| --- | --- |
| 0–4.5 min | 7 486 MB |
| from 4 min 54 s (freed) | 1 103 MB |

The next picture loads the model again (Z-Image Turbo 8 bit: 2–3 s from the file cache of macOS, 7x).

**After the app.** Whether engines outlive a crashed app (needed for a watchdog): a parent that starts an engine and
ends with `os._exit` (as a crash: the kernel closes its pipes). An idle Diffusers or MLX engine ends at once; an MLX
engine in the middle of a Z-Image picture at 1024 px ended 45 s later without a picture (its next progress line fails
on the closed pipe, the job ends, then the engine reads the closed stdin). The app told to quit ends both engines; the
ComfyUI engine stops its server when it ends. A watchdog thread would add nothing, so there is none.

## 7z. Qwen-Image 2.1 in stages instead of streamed (2026-10-29, M2 24 GB, memory kept free 12 GB)

Step 2 of the memory plan: on a 16 GB plan the prompt is encoded with the text encoder alone, then the transformer
stays whole in memory in 8 bit (no SSD streaming) beside the VAE. A probe with the engine's own loading
(`LoadedModel`, quantized caches), against the 16 GB plan's streamed run of 7w (16 bit, 9 blocks kept), the same
prompt, seed 12, 1024 px, 40 steps:

| | streamed, 16 bit (now) | in stages, 8 bit |
| --- | --- | --- |
| encoding a new prompt | text encoder 4 bit, kept blocks released | 30.6 s, peak 9.9 GB (text encoder alone) |
| loading the transformer | 11–16 s (streaming prepared) | 15–21 s from its 8 bit cache (each new prompt) |
| per step | about 41 s | about 44 s |
| 40 steps and decoding | 1 692 s | 1 781 s |
| peak while denoising | 12.1 GB | 10.5 GB |
| read from the SSD per picture | 382 GB | 0 |

The two pictures: 37.0 dB PSNR, mean difference 1.1 of 255; same composition, lighthouse and rocks, the person
slightly different and a small second figure missing in the 8 bit picture. Not faster on the M2 (quanto's int8 layers on
MPS cost what the SSD waits cost), but 1.6 GB less and no reads from the SSD.

Built in (`memory.fitting_plan`: before streaming, a big text encoder may go to 4 bit, then the denoiser makes room
while a new prompt is encoded). The engine on the 16 GB plan picks the text encoder in 8 bit (alone it fits); the
benchmark, the same prompt, a new prompt and then the same from the prompt cache:

| Run | phases | whole | engine at most | read from disk |
| --- | --- | --- | --- | --- |
| new prompt | text encoder 34.8 s, transformer 11.9 s, generating 1 790 s | 1 847 s | 12.2 GB (loading the 8 bit text encoder) | 20 GB |
| from the prompt cache | transformer 12.9 s, generating 1 813 s | 1 832 s | 9.9 GB | 9 GB |
| streamed before (7w, 7v) | | 1 705–1 863 s | 12.1 GB | 382–402 GB |

The two runs give the same picture to the pixel. Against the streamed one with its 4 bit text encoder: 26.3 dB, same
scene, the people on the rock placed differently (the 8 bit text encoder's prompt, not the transformer). `ACTIVATIONS_GB`
of Qwen-Image 2.1 is 2.8 now (was 3.0; 10.5 GB measured in stages): with 3.0 the plan missed the 16 GB budget by
0.15 GB.

## 7aa. MLX wired limit (2026-10-30, M2 24 GB)

Step 4 of the memory plan, measured only: `mx.set_wired_limit` set when the MLX engine starts, Z-Image Turbo, FLUX.2
[klein] 9B and Krea 2 Turbo through the benchmark, 1024 px, seed 12, the makers' steps. Limits: off, 68 % of the RAM
(16.3 GB) and MLX's recommended working set (17.75 GB; 17.8 is refused: "larger than the maximum working set size").
Whole picture, engine at most:

| Plan, round | limit | Z-Image Turbo | FLUX.2 [klein] 9B | Krea 2 Turbo |
| --- | --- | --- | --- | --- |
| 24 GB, 1 | off | 308 s, 13.5 GB | 196 s, 15.3 GB | 513 s, 14.5 GB |
| 24 GB, 1 | 16.3 GB | 486 s, 13.5 GB | 308 s, 15.2 GB | 917 s, 13.9 GB |
| 24 GB, 2 | off | 933 s, 13.4 GB | 562 s, 15.3 GB | 1 709 s, 14.6 GB |
| 24 GB, 2 | 17.75 GB | 913 s, 13.6 GB | 552 s, 15.1 GB | 1 672 s, 14.5 GB |
| 24 GB, 2 | 16.3 GB | 899 s, 13.6 GB | 611 s, 15.1 GB | 1 694 s, 16.3 GB |
| 16 GB (memory kept free 12 GB), 1 | off | 1 266 s, 9.5 GB | (Diffusers, streamed) | 2 000 s, 12.9 GB |
| 16 GB, 1 | 10.9 GB | 895 s, 9.6 GB | (Diffusers, streamed) | 1 675 s, 16.8 GB |
| 16 GB, 1 | 11.8 GB | 874 s, 13.8 GB | (Diffusers, streamed) | 1 663 s, 13.3 GB |

The Mac had 8–17 GB swapped out and other programs open (19–22 GB used): round 2 took three times as long as round 1
with the same settings. Within a round no limit is faster in all three models: in round 1 on 24 GB it was 50–80 %
slower, in round 2 within ±9 %, on the 16 GB plan 16–31 % faster but with up to 16.8 GB at most (over the plan). Swap
read during a picture: 0.2–2.6 GB without a limit, 0.04–0.4 GB with one in round 2, but there the run without a limit
came first each time (it pushed the other programs out). Not built in: no limit is measurably faster, and less swap is
not shown apart from the order. On the 16 GB plan FLUX.2 [klein] 9B went from MLX to Diffusers with streaming in every
run (MLX did not fit); there Diffusers used 17.7–21.1 GB at most, above the budget (streamed blocks queued on the busy GPU, 7ac).

## 7ab. Anima in ComfyUI: bfloat16 against float16 on MPS (2026-10-30, M2 24 GB)

MiaoMiao RealSkin (Anima, 2 B) at 1024 × 1536 with CFG 5 and 60 steps ran at 117–130 s per step: about two hours a
picture. Nothing in ComfyUI's path changed since 0.7.9. Anima-Turbo at 1024², 10 steps, CFG 1 took 140 s on
2026-10-04 and 151 s on 2026-10-19 (12–14 s per step), so the speed of the M2 has not dropped; a picture with CFG
(two passes) at 1.5 times the pixels is simply this slow. Where the time goes:

- ComfyUI picks bfloat16 for Anima (its first supported type, and MPS reports bfloat16 as supported). MPS on the M2
  computes it at half the speed of float16, at Anima's shapes (2 × 6144 tokens, 2048 wide, 16 heads of 128):

  | | matmul 12288 × 2048 × 8192 | attention 2 × 16 × 6144 × 128 |
  | --- | --- | --- |
  | float16 | 300 ms (1.37 TFLOPS) | 646 ms |
  | bfloat16 | 584 ms (0.71 TFLOPS) | 1 171 ms |

- The GPU was shared: over 60 s of a running picture ComfyUI got 46 % of the GPU time, the window server 26 % (Screen
  Sharing), the Claude app 26 %, other apps 13 %; the GPU stood at 95–100 % even without a picture.

Now ComfyUI on MPS runs a model in float16 where the model allows it and would get bfloat16 (`vulkara_memory`;
Anima, also Chroma and FLUX; Lumina 2, Z-Image, Qwen-Image and HiDream allow only bfloat16 and keep it). MiaoMiao,
the same prompt and seed:

| | bfloat16 | float16 |
| --- | --- | --- |
| 512 × 768, 8 steps | 21.2 s/step | 18.1 s/step |
| 1024 × 1536 | 117–130 s/step | 92 s/step |

The two 512 × 768 pictures: 23.6 dB, same composition and person. 60 steps at 1024 × 1536 stay at about 90 minutes
on this M2 with the GPU shared as above.

## 7ac. Streamed blocks waiting on a busy GPU (2026-10-30, M2 24 GB, memory kept free 12 GB)

FLUX.2 [klein] 9B through Diffusers on the 16 GB plan (23 blocks streamed, 9 kept, 4.5 GB; 1024 px, 4 steps, prompt
from the prompt cache) peaked at 17.7–21.1 GB in the runs of 7aa, planned 12 GB. A profiled run stayed at 13.1 GB
(peak on the GPU 8.4 GB): the profile waits for the GPU after every block. Without it Python runs ahead of the GPU
(MPS is asynchronous), and every block queued for computing holds its weights (a double block 0.87 GB) until it ran.
On a GPU busy with other programs (here a loop of float16 matmuls beside it, as Screen Sharing and other apps did) the
queue grew. Now a streamed block is loaded only when at most two before it still wait on the GPU (an MPS event after
each). The engine's footprint sampled every 0.5 s, the same picture:

| GPU shared with a busy program | footprint while denoising | engine at most | swap read | whole |
| --- | --- | --- | --- | --- |
| no bound (before) | 12.8–18.2 GB | 19.6 GB | 43.6 GB | 279 s |
| at most two blocks waiting | 12.2–13.9 GB | 14.3 GB | 0.5 GB | 225 s |

Faster too, as the Mac no longer swaps. The rest above the plan (12 GB) is the blocks in flight: the plan counts 15 %
of the model for them (2.7 GB), while three blocks of klein 9B in flight on the GPU and two read ahead come to more;
the plan counts them since 7ad.

## 7ad. The plan of a streamed FLUX.2 counts its large blocks (2026-10-30, M2 24 GB, memory kept free 12 GB)

After 7ac klein 9B on the 16 GB plan still peaked 2.3 GB above its plan: the plan counted 15 % of a streamed model
for the blocks in flight and the rest of the model, true for Qwen-Image 2.1 (60 blocks, 7w), but a FLUX.2 double block
is 4.8 % of the model and up to five are in flight (three on the GPU, two read ahead). Now the share is per family
(`memory.stream_resident_share`): 27 % for FLUX.2, 15 % for the others. The engine keeps 2 blocks (0.8 GB) instead of 9
(4.5 GB). The same picture as 7ac (1024 px, 4 steps, prompt from the prompt cache):

| | planned | engine at most | swap read | whole |
| --- | --- | --- | --- | --- |
| 15 %, 9 blocks kept, busy GPU (7ac) | 12.0 GB | 14.3 GB | 0.5 GB | 225 s |
| 27 %, 2 blocks kept, GPU free | 11.5 GB | 11.9 GB | 0.2 GB | 310 s |
| 27 %, 2 blocks kept, busy GPU | 11.5 GB | 10.6 GB | 0.1 GB | 237 s |

Within the plan now; reading 7 more blocks per step costs about 5 % (237 against 225 s under the same load; the run
with the GPU free was slower, the Mac was busy with other programs then).

## 7ae. ComfyUI drops the text encoder when memory runs short (2026-10-30, M2 24 GB)

Step 2 of the memory plan for ComfyUI. On the 24 GB Mac ComfyUI kept the text encoder through the whole picture
("0 models unloaded"): it frees cached node outputs only when less than 10 % of the RAM is left. NetaYume v4
(Lumina 2, Gemma 2 2B text encoder, 5.2 GB) peaked at 14.1 GB. The engine now starts ComfyUI with `--cache-ram` set
to the memory the app keeps free: below that ComfyUI drops the text encoder once the prompt is encoded (the
footprint falls from 5.7 to 2.0 GB before the model loads), and the plan counts ComfyUI's models staged, so Pony V7
Q8_0 on 16 GB stays whole in memory (SHARED) instead of loading piece by piece from the SSD (LOW_VRAM, 7h).

1024 px, the engine's footprint every 0.5 s with ComfyUI's log; first with 12 GB kept free on the 24 GB Mac (6 steps),
then with 8 GB wired by `mlock` as well, so that ComfyUI really has the memory of a 16 GB Mac (3 steps, as in 7h):

| | before | after |
| --- | --- | --- |
| NetaYume v4, 12 GB kept free | 14.1 GB, 30.8 s/step | 9.2 GB, 29.3 s/step (planned 11.6 GB) |
| NetaYume v4, 8 GB wired | 10.6 GB, 30.6 s/step, 6.1 GB read from swap, 155 s | 8.7 GB, 28.3 s/step, 2.1 GB, 136 s |
| Pony V7 Q8_0, 8 GB wired | LOW_VRAM: 64.7 s/step, 19.4 GB read from swap, 226 s | SHARED: 9.7 GB, 46.9 s/step, 4.6 GB, 185 s |

A new prompt loads the text encoder again (NetaYume 13 s, Pony 6 s); the same prompt again comes from ComfyUI's
cache of the encoded prompt. Not changed for MLX: freeing the model before decoding would not lower a job's peak, as
a Mac short of memory decodes in tiles (no visible difference, 7m) and then the denoising is the peak; the next
picture would have to load the model again.

## 7af. 0.7.11 on the Mac mini M4, 16 GB (2026-10-31, the user's benchmark, Hardware → Benchmark)

The first real 16 GB runs after 7ab–7ae (until now the 16 GB plan was simulated on the M2). 1024², the maker's steps;
engine = the engine's peak footprint, system = the Mac's memory in use at most:

| Model | Runtime | Steps | s/step | Whole | Engine (planned) | System | Swap added / read back |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CyberRealistic Pony v18 (SDXL) | Diffusers, 16 bit | 30 | 3.82 | 121 s | 8.8 GB (9.4) | 13.4 GB | 0 / 0.3 GB |
| NetaYume v4 (Lumina 2) | ComfyUI | 45 | 13.76 | 659 s | 10.8 GB (11.6) | 13.0 GB | 4.7 / 1.8 GB |
| MiaoMiao RealSkin (Anima) | ComfyUI, float16 | 30 | 11.67 | 409 s | 7.0 GB (9.1) | 12.7 GB | 0 / 0.3 GB |
| FLUX.2 [klein] 9B, prompt cached | Diffusers, streamed | 4 | 26.37 | 111 s | 10.5 GB (11.5) | 13.7 GB | 0.4 / 0.2 GB |
| FLUX.2 [klein] 9B, new prompt | Diffusers, streamed | 4 | 26.51 | 153 s | 10.6 GB (11.5) | 13.8 GB | 3.0 / 3.0 GB |

- Every engine stayed within its plan, also streamed klein 9B (7ad) and the ComfyUI models with `--cache-ram` (7ae).
- The M4 computes about twice as fast as the M2: NetaYume 13.8 against 28.3–29.3 s per step (7ae), klein 9B streamed
  26.4 against 54.3 (7ad), SDXL 3.8 against 5.0 (JuggernautXL, 7n).
- klein 9B waited 22–25 s of a picture for blocks from the SSD (62–76 GB read in 4 steps). For the second picture
  (new prompt, text encoder loaded in 35 s) other programs held 6.1 GB, only 9.9 GB were free for the planned 11.5:
  3 GB swapped, the app warned, the steps were as fast.
- NetaYume swapped 4.7 GB while loading (10.8 GB read from the disk), with the engine 0.8 GB under its plan: macOS
  and the other programs took the rest of the 16 GB.

## 7ag. MOSS-Image on ComfyUI 0.43 (2026-10-31, M2 24 GB)

Step 5 of the memory plan. MOSS-Image (OpenMOSS, 5B single-stream DiT, Qwen 3.5 9B text encoder, small FLUX.2 VAE,
Apache 2.0) runs on ComfyUI from 0.42 on; the runtime moved from 0.38.0 to 0.43.0 (only ComfyUI's own packages
changed in the lock). Comfy-Org's files: the transformer in int8 (5.4 GB), the text encoder in 4 bit weights (W4A8,
7.3 GB), on the Mac both computed by ComfyUI's emulated kernels. The maker's settings: Euler, 50 steps, CFG 3, shift
5, layer 22 skipped in the negative branch. 1024² unless noted, the GPU shared with other programs as in 7ab.

Which precision, ComfyUI alone (the same prompt and seed; the int8 file's layers compute in the model's type):

| File | Computed in | 512², 8 steps | 1024² |
| --- | --- | --- | --- |
| int8 (5.4 GB) | bfloat16 (ComfyUI's choice: MOSS-Image allows only bfloat16) | 21.6 s/step | 72.8 s/step |
| bf16 (10.2 GB) | bfloat16 | 15.0 s/step | 66.6 s/step |
| bf16 | float16 | 9.3 s/step | 41.2 s/step |
| int8 | float16 | | 48.9 s/step |

float16 against bfloat16 at 512²: 32.2 dB, the int8 file against the bf16 file 32.8 dB (both: same picture, text
alike). MOSS-Image's residual stream peaks at about 62,000 at 1024²–2048², float16 ends at 65,504; the first black
picture comes at 2560² (KBlueLeaf's measurements, MOSS-Image-FP16-fixed). The app's sizes end at 2048, so
`vulkara_memory` lets MOSS-Image compute in float16 on MPS: 48 instead of 73 s per step with the 5.4 GB file.

The app's benchmark (a sign with the words "VulKara Books"; 16 GB: 12 GB kept free and 8 GB wired, as in 7ae):

| | Steps | s/step | Whole | Engine at most (planned) | Swap added / read back |
| --- | --- | --- | --- | --- | --- |
| MOSS-Image, 24 GB | 50 | 47.7 | 2454 s (41 min) | 9.9 GB (9.2) | 0.1 / 0.8 GB |
| MOSS-Image, 24 GB | 8 | 47.6 | 458 s | 9.9 GB | 0.4 / 0.1 GB |
| MOSS-Image, 16 GB | 8 | 48.1 | 477 s | 8.4 GB (9.2) | 5.2 / 5.4 GB |
| MOSS-Image 8-step DMD, 24 GB | 8 | 24.4 | 268 s | 10.0 GB (9.2) | 0.7 / 0.3 GB |
| MOSS-Image 8-step DMD, 16 GB | 8 | 24.6 | 283 s | 8.4 GB (9.2) | 4.5 / 2.2 GB |

- The 50-step picture renders the sign letter for letter; float16 stayed finite through all steps.
- The 8-step version (lodestones' DMD distillation merged into the int8 file, Spectrallic): CFG 1, one pass per step,
  so half the time per step and a picture in 4½ minutes; the sign right as well.
- ComfyUI runs text encoders on the CPU on the Mac; MOSS-Image's encodes a new prompt (and the empty negative one) in
  about 50 s. Short of memory ComfyUI dropped everything after a picture (footprint 0.9 GB), so two new prompts in a
  row on 16 GB each loaded the encoder alone first, then the model: 8.4 GB at most, 160 s for 2 steps each.
- The plan counted the encoder and the model together (14 GB, "needs 19 GB" on 16 GB, the import refused). Now a
  ComfyUI picture is planned with them apart (as measured here and in 7ae): MOSS-Image 9.2 GB; on 16 GB NetaYume v4
  8.9 instead of 11.6 GB (measured 8.7), Pony V7 Q8_0 11.0 instead of 13.9 (measured 9.7). Video keeps both counted.
- The swap on 16 GB comes with the 8 GB wired on top of the other programs (19–20 GB in use on 24 GB without it).

The other ComfyUI models on 0.43, short runs against before: Anima Turbo 7.7 s/step (4 steps), NetaYume v4 29.6
(3 steps; 7ae 29.3–30.8), Pony V7 Q8_0 49.0 (3 steps; 7ae 44–47), Wan 2.2 I2V 14B 152.6 (832 × 480, 1 s, 4 steps; 7o
148.3), Upscale × 2 in 21 s.

## 7ah. MOSS-Image on the Mac mini M4, 16 GB (2026-10-31, the user's benchmark with the test build b875d85)

The 16 GB plan of 7ag on real hardware: MOSS-Image (int8 transformer, W4A8 text encoder), 1024², the maker's 50 steps
with CFG 3, two runs:

| Run | s/step | Whole | Engine (planned) | VulKara | System | Swap added / read back | Read from disk |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 (ComfyUI started 5 s) | 36.97 | 1911 s (32 min) | 9.1 GB (9.2) | 9.5 GB | 13.7 GB | 3.0 / 1.5 GB | 11.4 GB |
| 2 | 36.92 | 1897 s | 9.1 GB (9.2) | 10.3 GB | 14.0 GB | 2.6 / 1.8 GB | 12.3 GB |

- The engine stayed within its plan (9.1 of 9.2 GB): ComfyUI held the text encoder and the model apart, as planned.
- The M4 needs 37 s per step against 47.7 on the M2 (7ag): a picture in 32 instead of 41 minutes, a smaller gain
  than the 2× of 7af.
- The swap (2.6–3.0 GB) came while loading, as with NetaYume in 7af.

## 7ai. Fibo 2.0 Edit Turbo on ComfyUI 0.43 (2026-10-31, M2 24 GB)

Step 6 of the memory plan. Fibo 2.0 (Bria AI, CC BY-NC 4.0): an 8B single-stream DiT with 44 blocks, Qwen3-VL 4B
reading the prompt and the pictures, the FLUX.2 VAE. Edit Turbo is its 4-step distillation without guidance; it edits
and also paints new pictures. Where it runs:

- **diffusers:** the runtime's 0.41 knows only Fibo-Edit 1.5 (SmolLM3 text encoder); `BriaFibo2Pipeline` came with
  0.42. Bria's repositories are gated (a form), our token got 403.
- **ComfyUI 0.43** (already shipped with 7ag) has Fibo 2.0 (`TextEncodeFibo2`); Comfy-Org's files are not gated:
  the transformer in int8 (8.4 GB), Qwen3-VL 4B in int8 (4.9 GB), the VAE (0.3 GB). Chosen for VulKara.
- **mflux 0.24** (2026-10-27) has it too; our MLX runtime has 0.23. Tried in a scratch venv below.

Which precision, ComfyUI alone (edit of a 1024² picture, 4 steps, same seed):

| Computed in | s/step | Whole | Peak (text encoder kept) |
| --- | --- | --- | --- |
| bfloat16 (ComfyUI's choice: Fibo 2.0 allows only bfloat16 and float32) | 110.7 | 516 s | 14.3 GB |
| float16 | 69.3 | 338 s | 14.7 GB |

float16 against bfloat16: PSNR 46.7 dB (mean difference 0.6 of 255), the same picture. float16 stayed finite at
1536² (text to image) and 1536 × 1024 (edit), the app's largest sizes for the model. `vulkara_memory` lets Fibo 2.0
compute in float16 on MPS.

The app's benchmark (test instance, M2 24 GB, memory kept free 8 GB; the lighthouse picture of the app's own tests):

| Job | Size | s/step | Whole | Engine at most (planned) |
| --- | --- | --- | --- | --- |
| Edit ("Make it a snowy winter night with a full moon") | 1024² | 74.9 | 353 s | 14.8 GB (12.1) |
| Masked edit (a cabin beside the tower) | 1024² | 75.1 | 352 s | 14.8 GB (12.1) |
| Text to image ("VulKara Books" sign) | 1024² | 35.4 | 181 s | 13.4 GB (12.1) |
| Text to image | 512² | 13.4 | 90 s | 12.4 GB (10.2) |

- An edit runs the picture's tokens beside the new ones (twice the sequence), so a step takes twice as long as one of
  text to image. The sign came out letter for letter at 4 steps.
- Masked edit: the masked part, grown by 1/48 of the shorter side (21 px at 1024), is greyed out as in training; the
  result goes back into the picture with a soft edge (blur 1/24, 42 px), the same edge as the Diffusers inpainting.
  Outside the grown mask no pixel changed (0 of 570,791 checked); at 2× zoom no seam.
- The text encoder runs on the CPU and is mapped from its file; at 1024² the step itself adds 5.2 GB over the loaded
  model (MPS keeps the step's buffers, 3.1 GB already at 512²).

**16 GB (12 GB kept free and 8 GB wired, as in 7ae):** ComfyUI dropped the text encoder as planned (9.1 GB after
loading the model), but the first step of an edit at 1024² grew it to 14.3 GB: 1,167 s for the first step, swapping.
The job was cancelled. The plan now counts 5 GB of activations for Fibo 2.0 (14.6 GB, needs 19 GB of memory; it was
12.1), so a 16 GB Mac is told before it starts; Recommended lists it for 20 GB.

**mflux 0.24 (scratch venv, mflux-community's 8-bit files, 13 GB):** the same edit at 1024² in 97–98 s per step (398 s
whole), at most 11.8 GB with `--low-ram` (18.6 GB without; MLX itself 10.3 GB). Slower than ComfyUI in float16 on the
M2, but within a 16 GB Mac's budget: the MLX runtime moved to mflux 0.24 for it (7aj).

## 7aj. The MLX runtime on mflux 0.24, Fibo 2.0 on 16 GB (2026-10-31, M2 24 GB)

mflux 0.24.0 (2026-10-27) runs Fibo 2.0 (and MOSS-Image). The MLX runtime moved from 0.23.0 to it; mflux 0.24 needs
Pillow 13, so Pillow went from 12.3.0 to 13.0.0 (12.3 was kept because 13.0.0 broke an import in mflux 0.23 on
Python 3.11; 0.24 imports and runs). Nothing else in the lock moved (torch 2.14.1, transformers 5.18.0, mlx 0.32.4).

The models the runtime ran before, one short picture each (512², the app's benchmark, memory kept free 8 GB; the
benchmark's s/step, the model loaded within the job):

| Model | Steps | s/step | Whole | Engine at most (planned) |
| --- | --- | --- | --- | --- |
| Z-Image Turbo (8 bit) | 4 | 17.7 | 70 s | 12.0 GB (12.7) |
| FLUX.2 [klein] 4B (8 bit) | 2 | 18.0 | 26 s | 10.5 GB (10.5) |
| ERNIE-Image Turbo (4 bit) | 3 | 8.5 | 57 s | 8.1 GB (9.3) |
| FLUX 3 Image Klein (MLX 6 bit, flux3-mlx) | 4 | 5.5 | 35 s | 11.8 GB (12.5) |
| Krea 2 Turbo (4 bit) | 2 | 12.7 | 42 s | 13.3 GB (13.0) |
| FLUX.1 dev (4 bit) | 2 | 41.8 | 55 s | 13.2 GB (13.2) |

All pictures as expected for so few steps (FLUX.1 dev after 2 of its 28 still dark). Ideogram 4 did not run: on this
Mac with 8 GB kept free its plan needs 26 GB, so the engine refuses it before loading, as before the update.

**Fibo 2.0 on MLX** (`fibo2_mlx`, mflux-community's 8-bit files, 13.4 GB; the weights load lazily, so on a small Mac
the text encoder is dropped before the transformer's come in; the plan counts 1.7 GB of activations):

| Job | Size | s/step | Whole | Engine at most (planned) |
| --- | --- | --- | --- | --- |
| Edit (the lighthouse, as in 7ai) | 1024² | 96.4 | 401 s | 11.1 GB (11.5) |
| Masked edit | 1024² | 96.5 | 397 s | 11.0 GB (11.5) |
| Text to image ("VulKara Books") | 1024² | 42.1 | 181 s | 10.9 GB (11.5) |
| Edit, 16 GB (12 GB kept free, 8 GB wired) | 1024² | 99.3 | 412 s | 11.0 GB (11.5) |
| Edit, installed from Hugging Face (Recommended) | 1024² | 96.3 | 397 s | 11.0 GB (11.5) |

- On 16 GB the edit runs within its plan, 3 % slower; 37 GB read from the disk (the text encoder, then the
  transformer, while other programs held 15.8 GB of the 24).
- About 30 % slower per step than ComfyUI in float16 (75 s, 7ai), which needs 14.5 GB: ComfyUI stays the choice from
  20 GB, MLX below. The masked edit is blended back as on ComfyUI (no pixel outside the grown mask changed).

## 7ak. MOSS-Image on MLX against ComfyUI (2026-10-31, M2 24 GB)

mflux 0.24 runs MOSS-Image in MLX, its Qwen 3.5 9B text encoder too (ComfyUI runs that on the CPU, about 50 s per new
prompt, 7ag). mflux-community's saved files (8 bit 14.0 GB, 4 bit 7.5 GB), mflux's command line with `--low-ram`, the
bookshop prompt at 1024², 6 steps (the first one with loading):

| Files | Computed in | s/step | Whole (6 steps) | Footprint at most |
| --- | --- | --- | --- | --- |
| 8 bit | bfloat16 (mflux) | 53.5 | 338 s | 14.6 GB |
| 4 bit | bfloat16 | 54.2 | 337 s | 8.2 GB |
| 8 bit | float16 (text encoder bfloat16), 4 steps | 54.7 | | 26.3 GB without `--low-ram` |
| 4 bit | float16, 4 steps | 54.1 | | 19.8 GB without `--low-ram` |

- On the M2 MLX takes 54 s per step against 47.7 with ComfyUI (int8 in float16, 7ag), whatever the bits or the
  precision: for 50 steps about 5 minutes more, against about 50 s saved per new prompt. Not worth a second way for
  MOSS-Image; the M4 (bfloat16 in hardware) was not measured.
- Fibo 2.0 on MLX in float16 likewise: 101.9 s per step against 96.4 in bfloat16 (7aj), so it stays in mflux's
  bfloat16.

## 7al. Fibo 2.0 with two pictures (2026-10-31, M2 24 GB)

Image to image takes up to three more pictures for Fibo 2.0 (*More pictures*; <image_2> to <image_4> in the prompt).
The lighthouse and the bookshop picture of the app's own tests, "Put the lighthouse from <image_1> as a small framed
painting in the shop window of <image_2>", 1024², 4 steps:

| Runtime | s/step | Whole | Engine at most (planned) |
| --- | --- | --- | --- |
| ComfyUI (int8, float16) | 125.7 | 565 s | 16.2 GB (14.6) |
| MLX (8 bit) | 166.2 | 675 s | 11.6 GB (11.5) |

- Both put the lighthouse as a framed picture into the shop window and kept the shop as it was.
- A second picture makes the sequence about half as long again: 1.7 times the step of a one-picture edit, and on
  ComfyUI 1.4 GB more than one picture (7ai), 1.6 GB over the plan, which counts one picture; on MLX 0.5 GB more. The
  plan counts further pictures since 7am; on 16 GB MLX still stays within the budget (12 GB).

## 7am. Fibo 2.0 with three and four pictures, the plan counting them (2026-11-01, M2 24 GB)

The edit of 7al with one and two more pictures (<image_3>: the 8-step MOSS-Image bookshop, <image_4>: the Z-Image
one), 1024², 4 steps, 8 GB kept free (ComfyUI also with 4 GB kept free). Both runtimes crop each further picture to
about 1 megapixel whatever its size (ComfyUI's `TextEncodeFibo2`, mflux's `Fibo2EditImages.trained_size`), so each
one costs about the same:

| Pictures | ComfyUI s/step | Whole | Engine at most | MLX s/step | Whole | Engine at most |
| --- | --- | --- | --- | --- | --- | --- |
| 1 (7ai, 7aj) | 74.9 | 353 s | 14.8 GB | 96.4 | 401 s | 11.1 GB |
| 2 (7al) | 125.7 | 565 s | 16.2 GB | 166.2 | 675 s | 11.6 GB |
| 3 | 191.0 (195.4) | 839 s (858) | 18.8 GB (18.9) | 245.1 | 989 s | 12.3 GB |
| 4 | 284.4 (275.6) | 1202 s (1179) | 19.2 GB (20.3) | 337.2 | 1355 s | 13.0 GB |

- A step grows faster than the pictures: four pictures take 3.8 times one picture's step on ComfyUI, 3.5 times on
  MLX.
- With three and four pictures ComfyUI already pages on the 24 GB M2: it read 27 to 53 GB from the disk (the weights
  again during the steps), so its peak is held down by the memory there is and its real need may be higher.
- The plan now counts each further picture: 2.2 GB on ComfyUI, 0.5 GB on MLX, enough for every peak measured
  (`reference_gb` in the registry). Checked in the app with four pictures and 1 step: ComfyUI planned 21.2 GB
  (measured 19.6), MLX 13.0 GB (12.5); a masked edit takes no further pictures and stays at 11.5 (11.1).
- On 16 GB (12 GB budget) four pictures on MLX are planned at 13.0 GB, over the budget; the job notes that it may swap
  when less than that is free when it starts.
- The results: all four put the lighthouse as a framed picture into a shop window. ComfyUI kept the shop of
  <image_2> and its sign; MLX took the shop and the sign of <image_3> ("VulKara Books" readable) and with four
  pictures put books on the sill.
- ComfyUI now notes a shortage too (as MLX did): with four pictures, 1 step and 8 GB held by another process
  (`memlock`), the job said "Only 7.0 GB of memory free for the planned 21.2 GB": 4592 s instead of 358 s, 618 GB read
  from the disk, peak 19.2 GB. One picture without the lock: 14.8 GB free for 14.6 planned, no note, 128 s (14.8 GB).

## 7an. Fibo 2.0 Dev on ComfyUI (2026-11-01, M2 24 GB)

Comfy-Org's `fibo2_dev_int8_convrot.safetensors` (8.4 GB) imported in the test instance like a user would (Models →
import from Hugging Face, `Comfy-Org/Fibo-2.0`, 12.7 GB with the text encoder and the VAE): recognised as Fibo 2.0
with the maker's 50 steps and guidance 5. Benchmark, 1024², memory kept free 8 GB, seed 12:

| Job | Steps | s/step | Whole | Engine at most (planned) |
| --- | --- | --- | --- | --- |
| Text to image ("VulKara Books" sign) | 4 | 71.3 | 340 s | 13.4 GB (14.6) |
| Edit ("Make it a snowy winter night with a full moon") | 4 | 147.3 | 646 s | 15.0 GB (14.6) |
| Text to image | 50 | 72.0 | 3643 s (61 min) | 13.4 GB (14.6) |

- Guidance runs two passes per step: a step takes twice as long as one of Edit Turbo (35.4 and 74.9 s, 7ai). With
  the maker's 50 steps a new picture takes about an hour, an edit about two hours.
- The edit's peak is 0.4 GB over the plan (guidance's second pass); text to image stays 1.2 GB under it.
- The pictures: at 50 steps the sign "VulKara Books" letter for letter, a detailed shop with readable small signs;
  already at 4 steps the sign was right and the edit kept the lighthouse (snow, full moon, beam).
- The benchmark's memory note came in all three jobs (8.6 to 14.4 GB free for 14.6 planned), and it was right:
  macOS moved 3.4 to 6.7 GB of other programs to the swap during each job (swap 6.6 to 13.3 GB in the first). The
  picture was not slower for it: what went to the swap was idle, the engine itself read no more than its model (14 GB
  for 4 steps). Compare 7am's four pictures with 14 GB missing: 13 times as slow, 778 GB read back from the swap.

## 7ao. Loading a checkpoint from the USB SSD against the internal SSD (2026-11-01, M2 24 GB)

Would a copy of the model on the internal SSD pay off (protoart-studio's `local_copy.py` claims "60-90 s from the disk,
3-10 s internal")? `safetensors.torch.load_file` in the diffusers runtime, then a copy of every tensor on the CPU, since
load_file only maps the file. One run each, file cache cold (0 % resident by mincore, 7 % for JuggernautXL external).
The full engine load, the move to MPS and the Mac mini were not measured.

| Checkpoint | Order of reading | USB SSD | Internal SSD | Saved |
| --- | --- | --- | --- | --- |
| JuggernautXL v7, 6.46 GB | file | 17.6 s | 9.9 s | 7.7 s |
| RedCraft Krea 2, 12.24 GB | file | 32.1 s | 22.0 s | 10.1 s |
| mopMix, 6.46 GB | random | 12.9 s | 9.7 s | 3.2 s |

Plain uncached reading is 0.81 GB/s from USB (0.92 in section 1, a different file) and 2.74 GB/s internally, but reading
through the mapped file stays at 0.56-0.66 GB/s even internally: the page faults limit it, not the disk. The internal
copy saves 3 to 10 s per cold load, a third of the time, not protoart's factor of 10; a model already in the file cache
gains nothing. The copy itself took 10.5 s (6.46 GB) and 19.6 s (12.24 GB) once.

## 7ap. Blocks read ahead after the last step (2026-11-01, M2 24 GB, memory kept free 12 GB)

7w saw that after the last step the two blocks read ahead for a further pass stay in memory until the next picture.
Now the step callback drops them after the last step (and after a stop), before decoding. FLUX.2 [klein] 9B streamed
through Diffusers on the 16 GB plan, Hardware → Benchmark, 1024 px, one run each; the footprint sampled every 0.5 s
(fpsample.py); the whole job includes loading.

| Run | whole | read per picture | engine at most | held after the picture (model loaded) | after the job |
| --- | --- | --- | --- | --- | --- |
| before | 226.7 s | 65.3 GB | 10.73 GB | 9.6 GB | 5.2 GB |
| after | 223.7 s | 64.1 GB | 11.08 GB | 8.6 GB | 3.2 GB |

1.2 GB less read per picture (two blocks of 9B in 16 bit) and 1 GB less held after the picture; the peak while
denoising is set by the blocks in flight, not by these two (the 0.35 GB difference of the peaks is one run against
one run). The 2 GB difference after the job was not looked into.

## 7aq. FLUX.2 [klein] 4B on the 16 GB plan (2026-11-01, M2 24 GB, memory kept free 12 GB)

Open since 7o: is klein 4B streamed on a 16 GB Mac? It is not: the plan takes transformer and text encoder in 8 bit
(9.5 GB planned) and the model runs whole. Hardware → Benchmark, Diffusers runtime, 1024 px, 4 steps, one run: 24.1 s
per step, 136 s whole (loading 28 s), engine at most 9.42 GB, 8.1 GB read; the plan held. Streaming stays for the 9B.

## 7ar. Stopping while the model loads (2026-11-01, M2 24 GB, memory kept free 12 GB)

7r left the checkpoint load before the streaming preparation running to its end after a stop. Now the reader thread
raises the stop inside the loading thread (PyThreadState_SetAsyncExc, between two tensors) while a model, its
denoiser or its text encoders load; caches are written whole or renamed into place, so a load broken off leaves
nothing half. Chroma1 Flash through Diffusers on the 16 GB plan (8 bit from the quantized cache on the USB SSD, the
denoiser streamed), cancelled 3 s after "Loading model", one run each:

| | from the cancel to the end of the job |
| --- | --- |
| before | 61.6 s (the checkpoint shards loaded to their end, 52 s, then the stop was seen) |
| after | 0.8 s |

Checked after: the same engine process painted the next picture (FLUX.2 [klein] 4B, 512 px, done in 32 s). A stop
while a step runs still ends with that step (klein 9B streamed: 60 s), as before. MLX and ComfyUI loads are not changed.

## 7as. What a ControlNet adds, and what the plan says (2026-11-01, M2 24 GB)

Open since 0.7.10: the ControlNet is not counted in a staged plan's encoding. Measured first what a ControlNet adds at
all. Hardware → Benchmark, Diffusers runtime, 1024 px, 4 steps, Canny from a picture, one run each; "planned" is what
the job reports (memory.peak_at), the room for the ControlNet is judged by controlnet_room (budget − denoise peak −
twice the activations).

| Job | planned | engine at most | note |
| --- | --- | --- | --- |
| Juggernaut XL (SDXL), 24 GB plan | 9.4 GB | 8.79 GB | |
| Juggernaut XL + ControlNet Union ProMax (16 bit, 2.5 GB), 24 GB plan | 9.4 GB | 11.97 GB | the ControlNet adds 3.2 GB: its weights and 0.7 GB activations, not the 5 GB (twice 2.5) the room check takes |
| Juggernaut XL + ControlNet, 16 GB plan (memory kept free 12 GB) | 9.4 GB | refused | "Not enough RAM for the ControlNet (2.5 GB, 1.2 GB in 8 bit)": the room is 12 − 9.4 − 5 < 0, yet 8.8 + 1.2 + 0.7 would fit |
| FLUX.1 [dev] + ControlNet Union Pro 2.0 (4.3 GB), 16 GB plan and 768 px on a budget of 16 GB | 12 / 15.9 GB | refused | the FLUX ControlNet never fits on this Mac under the rule; not measured |

The planned figure leaves the ControlNet out altogether (9.4 against 12.0 measured), and the room check counts its
activations at twice the model's where SDXL's ControlNet took 0.3 times. The encoding peak of a staged plan with the
ControlNet resident (the open point) could not be measured: no staged model with a ControlNet fits here.

Changed: the job's planned peak takes the loaded ControlNet (its weights at the bit size it got and half the model's
activations, `memory.CONTROLNET_ACTIVATIONS`), through the encoding of a staged plan too, and the room check judges by
that peak instead of twice the activations. The same jobs after:

| Job | planned | engine at most |
| --- | --- | --- |
| Juggernaut XL + ControlNet Union ProMax (16 bit), 24 GB plan | 12.65 GB | 12.17 GB |
| Juggernaut XL + ControlNet (8 bit, quantized once), 16 GB plan | 11.46 GB | 11.62 GB (budget 12) |

The 16 GB job runs now (80 s with the one-time quantizing, the picture follows the edges); the FLUX.1 ControlNet is
still refused here, its weights alone pass the room.

Also seen, FLUX.1 [dev] streamed (budget 16 GB, stream cache present): the engine's footprint reached 24.6 GB while the
model was prepared for streaming (86 s), before any step: the transformer is loaded whole in 16 bit before its blocks
go to the meta device. On a 16 GB Mac that load swaps. Release todo.

## 7at. The streaming preparation without the whole model (2026-11-01, M2 24 GB)

7as saw FLUX.1 [dev] streamed reach 24.6 GB before its first step. The cause: the M2 computes FLUX.1 in float16, the
file holds bfloat16, so loading the transformer whole for the cache check converted every tensor into RAM (24 GB);
klein 9B, computed in bfloat16, is only mapped and showed no spike. Now the stream cache also holds the weights outside
the blocks (rest.safetensors, 128 MB for FLUX.1), and a later load builds the model empty and reads only those; the
first use of a model (writing the cache) still loads it whole. FLUX.1 [dev] on a budget of 16 GB (memory kept free
8 GB), 768 px, 4 steps, one run each:

| Run | preparation | whole job | engine at most | read |
| --- | --- | --- | --- | --- |
| first use (cache written, rest.safetensors added) | 100.2 s | 205.6 s | 23.53 GB | 101.6 GB |
| from the cache | 8.1 s | 115.5 s | 11.02 GB (planned 15.9) | 77.8 GB |

Existing caches get rest.safetensors at their next load (that load is still the whole one). On an M4, which computes
in bfloat16, the first load maps the file and does not spike; a 16 GB M1 or M2 swaps once per model.

## 7au. Chroma1 Flash in 8 and 16 bit (2026-11-01, M2 24 GB)

Open since 0.7.9: whether Chroma should run in 8 bit or 16 bit. Hardware → Benchmark, Diffusers runtime, 1024 px, 12
steps, seed 7, two pictures per route; the route follows the memory kept free (Settings → Engine), the plan picks it:

| Route (memory kept free) | plan | s/step (1st, 2nd picture) | engine at most | read per picture | picture |
| --- | --- | --- | --- | --- | --- |
| 8 bit whole, text encoder resident (4 GB) | 18.0 GB | 52.8, 49.3 | 17.4 GB | 69, 53 GB | A |
| 8 bit in stages, text encoder per new prompt (8 GB, the default here) | 15.5 GB | 42.6, 41.5 | 11.1 GB | 14, 0.3 GB | A, to the pixel |
| 16 bit streamed from the SSD, 5 blocks kept (12 GB) | 11.5 GB | 35.2, 63.3 | 17.3 GB first use (loaded whole for rest.safetensors, 7at), 8.0 GB then | 197, 178 GB | B, 30.3 dB to A |

8 bit whole was the slowest and held 17.4 GB: the Mac (24 GB) swapped under it. 8 bit in stages gives the same
picture, a fifth faster, with 11 GB. 16 bit streamed reads 180–200 GB per picture; its second picture was slower than
its first (the USB SSD's reading varies), and the picture differs: the same shop, lamps and open books, the wall left of
the window shows shelves of books in 16 bit and ivy in 8 bit, the ceiling lamps differ. Neither is wrong; 8 bit rounds,
the difference is in details the prompt leaves open. Conclusion: 8 bit in stages, as the plan picks it with 8 GB kept
free, is the route for this Mac; nothing changed.

## 7av. MOSS-Image: layouts, image to image, LoRAs (2026-11-01, M2 24 GB)

Open since 0.7.10. MOSS-Image 8-step (DMD), ComfyUI runtime, 768 px, 8 steps, memory kept free 8 GB, one run each.

- **Layout as the prompt.** The JSON ComfyUI's *MOSS-Image Layout Prompt* node writes (`summary.caption`, `items` with
  `label`, `caption`, `text`, `bbox` as [top, left, bottom, right] in pixels from the centre, `bbox_coord_space`
  "abs_centralized", `bbox_format` "yxyx"), pasted as the prompt, needs nothing of the app: a bakery poster put
  "FRESH BREAD" in the top box, the loaf in the middle one and "baked every morning" in the bottom one. 210.8 s whole.
- **Image to image** through the general path (the picture encoded by the VAE, denoised from strength 0.6): the shop,
  its sign and door stay, the sign's text changes (the model has no image input of its own; ComfyUI's documentation
  describes the same as a refinement pass). 14.7 s per step, 186 s whole, 8.6 GB (planned 8.1). The spec's `img2img`
  flag was all that hid it.
- **LoRAs.** ComfyUI 0.43 maps a MOSS LoRA's keys (`diffusion_model.layers.N.proj.q`, `lora_unet_layers_N_proj_q`, …)
  onto the fused q/k/v files VulKara uses (comfy/lora.py). The app's LoRA import did not know the family: now a rule
  for `layers_N_proj_(q|k|v|qkv|o|ffn_up_gate|ffn_down)` and `shared_block_modulation`, the metadata name "moss-image"
  and the Hugging Face bases openmoss-team/moss-image, comfy-org/moss-image. nynxz's destripe LoRA (1.9 MB, Apache 2.0,
  extracted from SFT minus Base) imported through the app as *LoRA for MOSS-Image*; a poster without and with it:
  14.6 s per step both, the pictures differ (31.0 dB), the composition stays. An Anima LoRA on MOSS-Image is refused
  with the family message, as before.

Public MOSS LoRAs are few as yet (the destripe one, a 4-step LoRA in diffusers' names, lodestones' DMD already merged
into the 8-step model); ComfyUI's edit LoRA node (TextEncodeMOSSImageEdit, references) waits for a public edit LoRA.

## 7aw. ERNIE-Image's prompt enhancer (2026-11-01, M2 24 GB)

Open since 0.7.1: the repository's prompt enhancer (pe/, Ministral 3 3B, 7.66 GB in bfloat16) as an option. Run with
mlx_lm as diffusers' pipeline runs it (the user message is JSON with the prompt and the size; its chat template holds the
instruction, in Chinese; temperature 0.6, top-p 0.95, seeded with the job's seed). ERNIE-Image Turbo (MLX, 4 bit), 1024
px, 8 steps, seed 11, memory kept free 8 GB; the helper downloaded through the app in 107 s.

| Picture | enhancer | s/step | whole job | engine at most |
| --- | --- | --- | --- | --- |
| with the enhancer | 65 s, 383 characters | 45.6 | 373 s | 10.6 GB |
| with it again (same prompt and seed) | 53 s, the same 383 characters, the same picture to the pixel | 45.7 | 371 s | 9.5 GB (the model was unloaded for the enhancer: memory short) |
| without | – | 40.1 | 332 s | 9.0 GB |

The enhancer writes Chinese whatever the prompt's language (its instruction is Chinese; ERNIE reads both): "这是一张高分辨率的
自然风光摄影作品，呈现了一座灯塔矗立在海岸岩石上的黄昏景象 …" (a high-resolution landscape photograph of a lighthouse on
coastal rocks at dusk, the tower of weathered grey stone, a beam to the upper left, wet rocks, a tidal flat mirroring
the sky, a sky from orange and pink to deep blue, no text). The picture follows it: the beam, the wet flat with pools,
the colour gradient; without the enhancer a plainer dusk. The steps take 14 % longer with the long prompt. Not measured:
a 16 GB Mac (the enhancer alone holds 7.7 GB; the image model is unloaded first there) and 4 bit for it.

Since 2026-11-02 the enhancer is instructed in English and writes English (the user asked for a readable description);
the picture of the same prompt and seed is then another one.

## 7ax. LoRAs for Fibo 2.0 (2026-11-02, M2 24 GB)

Open since 0.7.10 ("no LoRAs yet"). Public LoRAs for Fibo 2.0 come in two layouts: diffusers' (peft, to_q / to_k /
to_v, w1 / w3) and ComfyUI's, fused for Comfy-Org's repacked files (attention.qkv, feed_forward.w13 with the hidden
width 9536 padded to 9728, attention.out, to_kv). ComfyUI 0.43 maps neither onto the other, and mflux maps diffusers'
names only; VulKara's import did not know the family (3584-wide layers under NextDiT's names). Now the import tells a
Fibo 2.0 LoRA by its width, its perceiver and cross-attention layers or the fused w13, the metadata and the Hugging
Face bases; the ComfyUI engine fuses diffusers' layout once (the rank stacked, alpha times the parts), the MLX engine
splits ComfyUI's once. axiomofmind's anime LoRA (a 400-step pilot, both files, base Fibo-2.0-dev) imported through the
app as *LoRA for Fibo 2.0*; 768 px, seed 5, strength 0.9, the trigger word in the prompt, memory kept free 8 GB:

| Runtime, model | LoRA file | s/step | engine at most | picture |
| --- | --- | --- | --- | --- |
| ComfyUI, Fibo 2.0 Dev int8, 10 steps, guidance 5 | – | 45.5 | 12.3 GB (planned 12.4) | A |
| ComfyUI | diffusers' layout, fused by VulKara (no key skipped) | 43.1, 45.1 | 13.0, 13.3 GB | 9.5 dB to A |
| MLX, Fibo 2.0 Edit Turbo 8 bit, 4 steps | – | 22.7 | 10.3 GB (planned 10.8) | B |
| MLX | ComfyUI's layout, split by VulKara, every layer placed (mflux: "all LoRA weights applied") | 25.7 | 11.3 GB | 9.6 dB to B |

The LoRA changes both pictures (another composition, the same woman reading at a café window); its seinen style shows
little, as its card's examples use Fibo's structured JSON prompts with the trigger in style_medium. The first MLX run
left 27 keys unplaced (cross_attention.to_out named without diffusers' ".0"), fixed before the figures above. The
fused file holds 0.5 to 1 GB more while loading on ComfyUI (13.0 and 13.3 against 12.3 GB).

## 7ay. Wan 2.2 I2V 14B, clips of one to five seconds (2026-11-02, M2 24 GB)

Open since 7o (one second only). Wan 2.2 I2V 14B as the app installs it (QuantStack's Q4_K_M GGUF of both experts,
9.65 GB each, the lightx2v 4-step LoRAs, UMT5-XXL in FP8, the Wan 2.1 VAE), ComfyUI in LOW_VRAM mode (7h), the text
encoder dropped after the prompt (7ae), 832 × 480, 4 steps, guidance 1, seed 3, image to video from the lighthouse
picture, memory kept free 8 GB. Wan takes 4n + 1 frames at 16 fps, so the slider's seconds become 13, 29, 45 and 77
frames (0.81 to 4.81 s of film). One clip per length, the engine's footprint and disk reads from the job:

| Length | Frames | s/step | whole clip | per second of film | engine at most | read from the SSD |
| --- | --- | --- | --- | --- | --- | --- |
| 1 s | 13 | 140.3 | 486 s (8.1 min) | 598 s | 7.3 GB | 27 GB |
| 2 s | 29 | 293.9 | 959 s (16.0 min) | 529 s | 8.3 GB | 32 GB |
| 3 s | 45 | 1071.2 | 3134 s (52.2 min) | 1114 s | 8.9 GB | 49 GB |
| 5 s | 77 | 2155.0 | 6601 s (110.0 min) | 1372 s | 10.0 GB | 58 GB |

Against 7o the one-second clip holds 7.3 instead of 12.7 to 12.9 GB (the text encoder is dropped, 7ae) at the same
speed (140 against 148 s per step). Memory grows little with the length (2.7 GB from 1 to 5 s); time grows faster than
the frames: a step takes 2.1 times longer from 1 to 2 s, 3.6 times from 2 to 3 s and 2.0 times from 3 to 5 s, as the
attention over the frames grows with the square of the tokens. Why the step from 2 to 3 s costs more than the square
is open: ComfyUI's step log is not kept, and the footprint sampler of this run watched the Diffusers engine only.
The five-second clip is 1.5 MB, every clip plays as expected (ffprobe: 832 × 480, 16 fps, 13 / 29 / 45 / 77 frames).

The plan on disk (written at the import of 10 October, when ComfyUI held both experts whole) says 17.9 GB at the peak
and 23 GB of RAM at least, and the curated list asks for 24 GB; a job reports no plan for a video (7p). Measured, the
whole route stays at 10 GB on a 24 GB Mac up to five seconds; the app refuses the import on a 16 GB Mac
(`tooLittleRam`), and LOW_VRAM reads the experts from the SSD per step (27 to 58 GB per clip).

**The 16 GB simulation** (the same day, 12 GB kept free and 8 GB wired by `mlock` as in 7ae, the swap already at
6.3 GB from other programs; the ComfyUI processes' footprint every 0.5 s, the swap every 10 s):

| Length | s/step | whole clip | ComfyUI at most | read from the SSD | swap in use |
| --- | --- | --- | --- | --- | --- |
| 1 s | 205.6 | 694 s (11.6 min) | 6.0 GB | 65 GB | 6.3 → 10.1 GB |
| 5 s | – | ended after 7 min | 8.7 GB | – | 10.1 → 21.3 GB |

The one-second clip is made (13 frames, the same length as on 24 GB) at 47 % more per step, reading 65 instead of
27 GB: the experts' file pages no longer stay in the file cache between the steps. The five-second clip drove the swap
to 21 GB within four minutes of denoising; at 09:47 macOS sent its memory-pressure notification and the app's GPU
process ended (Electron: "GPU process exited unexpectedly: exit_code=15", the network service with it), the window was
lost and the queue could no longer be followed, so the run was stopped. Whether ComfyUI would have finished the clip
is not known. Wan 2.2 14B stays a 24 GB model in the curated list: a 16 GB Mac makes a one-second clip in LOW_VRAM,
but longer clips push everything else into the swap.

## 7az. The memory note between 6 and 14 GB short (2026-11-02, M2 24 GB)

For the release todo "grade the memory note": up to 6 GB short the picture was as fast (7an, 7af), 14 GB short made
it 13 times slower (7am); nothing in between. NetaYume v4 (Lumina 2, ComfyUI, the text encoder dropped after the
prompt), 1024 px, 3 steps, memory kept free 8 GB, through Hardware → Benchmark, which records the note, the swap and
the reads; memory wired by `mlock` in 6 to 7.5 GB pieces (one piece of 17.9 GB was refused) so that other programs
could not give it up. "Short" is the planned 14.1 GB less what was free at the start (the note's figures):

| Wired | Free at the start | Short | s/step | whole picture | swap | read back from the swap | read from the disk | engine at most |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 GB | 8.4 GB | 5.7 GB | 29.1 | 135 s | 6.5 → 8.2 GB | 0.1 GB | 11.1 GB | 9.2 GB |
| 7.5 GB | 4.5 GB | 9.6 GB | 29.3 | 137 s | 8.1 → 13.1 GB | 1.4 GB | 12.3 GB | 8.7 GB |
| 0 GB (17.9 GB refused) | 9.0 GB | 5.1 GB | 29.0 | 131 s | 11.7 → 11.8 GB | 1.3 GB | 13.0 GB | 10.6 GB |
| 12 GB (two pieces) | 3.0 GB | 11.1 GB | 412.0 | 1221 s | 10.2 → 16.3 GB | 244.9 GB | 90.4 GB | 7.8 GB |

Up to 9.6 GB short the picture stays as fast: macOS moves other programs to the swap (5 GB in the second run) and
the engine reads back little. At 11.1 GB short, with 12 GB that could not move, the picture took 14 times as long
and read 245 GB back from the swap (7am: 14.2 GB short, 13 times). The cliff lies between 9.6 and 11.1 GB on this Mac
with these other programs; what decides is whether the shortage can be covered by idle programs, which the app cannot
see. Grading proposed from this: no note up to 2 GB short (the measurement's noise), a mild note up to 8 GB, a strong
one above (the 9.6 GB run would get a strong note although it was fast: the margin below the cliff).
On the 16 GB Mac mini the mild grade was wrong at 6.3 GB short (7ba: 18.9 GB read back from the swap, the picture
slower than on the M2): the thresholds of a 24 GB Mac do not carry over to 16 GB.

## 7ba. The test build of 2026-11-02 on the Mac mini M4, 16 GB (2026-11-02, the user's benchmark)

Hardware → Benchmark with the test build d10c0ab+ (the memory note in two grades, 7az, and everything before it), the
maker's steps; engine = the engine's peak footprint, VulKara = the app with its engines, system = the Mac's memory in
use at most:

| Model | Runtime | Size, steps | s/step | Whole | Engine (planned) | VulKara | System | Swap added / read back | Read from disk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ERNIE-Image Turbo | MLX, 4 bit | 1024², 8 | 27.98 | 262 s | 8.7 GB (11.2) | 9.9 GB | 13.1 GB | 0.7 / 0.2 GB | 22.1 GB |
| Juggernaut XL v7 (SDXL) | Diffusers, 16 bit | 1024², 35 | 3.85 | 164 s | 8.9 GB (9.4) | 10.9 GB | 13.8 GB | 4.1 / 2.2 GB | 7.4 GB |
| Fibo 2.0 Edit Turbo | MLX, 8 bit | 768², 4 | 28.47 | 132 s | 10.2 GB (10.8) | 13.6 GB | 14.0 GB | 7.6 / 18.9 GB | 20.3 GB |

- Every engine stayed within its plan. ERNIE-Image: 28.0 against 40.1 s per step on the M2 (7aw, without the
  enhancer); SDXL 3.85 against 5.0 (7n), as in 7af.
- **Fibo 2.0 Edit Turbo was slower than on the M2** (28.5 against 22.7 s per step at 768², 7ax) although the M4
  computes faster: the job started with 4.5 GB free for the planned 10.8 (6.3 GB short, other programs held 11.5 of
  the 16 GB), 7.6 GB went to the swap and 18.9 GB were read back from it. The note said "macOS moves other programs
  to the swap, the picture is usually as fast" (the mild grade of 7az, measured on the 24 GB Mac): on a 16 GB Mac what
  the others hold is largely macOS itself and cannot move, so the engine's own memory swapped. 7af had the same Mac
  1.6 GB short (klein 9B) as fast as ever; the cliff on 16 GB lies between 1.6 and 6.3 GB short, not at 10 GB.
- The MOSS-Image rows of the same list are the runs of 7ah (build b875d85).

## 7bb. The tip pictures, and Chroma's prompt mask (2026-11-02/03, M2 24 GB)

The picture pairs of the Tips page (a plain prompt against the tip's prompt, the same model, seed and the maker's
settings), made in the test instance with the user's models, runtime auto and no memory reserve (the Ideogram runs
had been refused with 8 GB reserved: a 26 GB plan). Engine = the engine's peak, as the queue reports it:

| Model | Runtime | Size, steps | s/step (plain / tip) | Engine (planned) |
| --- | --- | --- | --- | --- |
| epiCPhotoGasm (SD 1.5) | Diffusers, 16 bit | 512², 20 | 0.71 / 0.69 | 3.7 GB (3.6) |
| Juggernaut XL v7 (SDXL) | Diffusers, 16 bit | 512² / 1024², 30 | 1.18 / 4.80 | 8.8 GB (9.4) |
| SD 3.5 Medium | Diffusers | 768², 40 | 8.35 / 8.65 | 15.0 GB (13.8) |
| FLUX.1 dev | MLX, 4 bit | 768², 20 | 23.5 / 22.5 | 13.1 GB (12.8) |
| FLUX.2 [klein] 4B | MLX, 8 bit | 768², 4 | 15.4 / 11.8 | 10.5 GB (11.8) |
| Chroma1 Flash (boolean mask, below) | Diffusers, 8 bit | 768², 12 | 20.9 / 32.0 | 12.3 GB (16.9) |
| Qwen-Image 2.1 | Diffusers, streamed | 1024², 40 | 44.5 / 43.0 | 17.5 GB (14.4) |
| Z-Image Turbo | MLX, 8 bit | 768², 9 | 28.4 / 36.9 | 12.2 GB (13.6) |
| Krea 2 Turbo | MLX, 4 bit | 768², 8 | 30.9 / 30.0 | 15.6 GB (13.4) |
| Ideogram 4 | MLX, 4 bit | 768², 20 | 99.6 / 93.7 | 17.0 GB (17.2) |
| ERNIE-Image Turbo (the second with the enhancer) | MLX, 8 bit | 768², 8 | 60.8 / 48.5 | 16.0 GB (15.4) |
| MOSS-Image 8-step DMD | ComfyUI | 768², 8 | 14.3 | 9.7 GB (8.1) |
| Wan 2.2 I2V 14B, 1 s | ComfyUI | 832 × 480, 4 | 165 | 7.3 GB |
| FLUX 3 Image Klein (the second with the upsampler) | MLX, 6 bit | 768², 16 | 12.6 / 13.9 | 11.9 / 14.7 GB (12.5) |
| Anima-Turbo | ComfyUI | 1024², 10 | 7.8 / 7.8 | 10.0 GB (9.1) |
| NetaYume v4 (Lumina 2) | ComfyUI | 768², 40 | 30.1 / 28.9 | 15.3 GB (14.1) |
| AuraFlow v0.3 (the 24 GB plan, below) | Diffusers, 16 bit | 1024², 50 | 73.4 / 71.7 | 18.7 GB (18.7) |
| FLUX.1 dev, Flux Skin Detailer DoRA at 0.7 (the second) | MLX, 4 bit | 768², 20 | 31.6 / 24.8 | 15.3 / 13.3 GB (15.3 / 12.8) |

- **Chroma's short prompts came out as noise.** *a fox* gave a grid of noise at 512 and 768 px (the same picture on a
  second run), *a red fox, photo* half noise with the ghost of a fox, *a red fox in a forest* and the tip's sentence a
  clean picture. diffusers 0.41.0 builds Chroma's prompt mask as 0/1 floats (`pipeline_chroma.py`, `_get_t5_prompt_embeds`)
  and the transformer hands it to `scaled_dot_product_attention`, which adds a float mask instead of applying it: the
  padding is attended and drowns a short prompt (huggingface/diffusers issue 12116; its fix 12263 of 2025-09-29 was
  undone by PR 12508 of 2025-10-27, and main still has the float). The engine now wraps the pipelines' mask helper to
  return booleans (`_chroma_bool_masks`, on the three Chroma pipeline classes, so derived pipelines and cached
  embeddings are covered). With it *a fox* shows a fox, still with patches and pseudo-text (two words stay thin for
  the distilled Flash), and the sentence keeps its composition (mean difference 7 of 255 in grey). The pictures of the
  results page and of 7ag–7ba were made with the float mask; their prompts were long enough.
- **Peaks above the plan:** Qwen-Image 2.1 at 1024² 3.1 GB (17.5 against 14.4), Krea 2 at 768² 2.2 GB (15.6 against
  13.4), SD 3.5 Medium 1.2 GB, Chroma with the float mask 1.6 GB (17.1), MOSS-Image 1.6 GB. Open: the plans of Qwen
  (streamed, 1024 px) and Krea 2 undercount by 2–3 GB on this Mac.
- Ideogram 4 at 768² runs at 94–100 s per step on MLX (the 512² benchmark of 7p: 29 s), 17.0 GB; its typography
  prompt needed the subject first: *tall condensed black letters* became a giant garbled block over the whole bag with
  seeds 7 and 8, *bold black serif letters* on a bag named first came out right.
- Wan 2.2 at one second (13 frames) moves the same with a still-image prompt and with a motion prompt (mean frame
  difference 8 of 255 between the two clips' last frames): the motion prompt needs the longer clip to show.
- **AuraFlow's 24 GB plan is slower than its 16 GB plan.** With 24 GB the engine keeps the transformer in 16 bit
  (18.7 GB planned, 18.7 measured) and the queue reports about 600 GB read per picture: the Mac re-reads the weights
  every step, 72–73 s per step at 1024² against 44 s with the 8 bit transformer of the 16 GB plan (7j, 9.8 GB). Short
  check at 1024², 4 steps, seed 7, the same app (a scratch manifest asking for q8, the cached q8 transformer):

  | Transformer | s/step | read during the job | peak (plan) |
  | --- | --- | --- | --- |
  | 16 bit (the 24 GB plan) | 77.6, again 81.0 | 74.8, 82.9 GB | 18.7 GB (18.7) |
  | 8 bit | 46.4 | 10.1 GB | 16.5 GB (12.2; the first job after the 16 bit model, which it unloads) |

  8 bit is 1.7 times as fast: the 16 bit weights sit 0.5 GB under the budget (19.2 GB) and are read again every step
  (about 19 GB per step). Now "auto" keeps a 16 bit denoiser only with 2 GB of room under the budget
  (`FULL_PRECISION_MARGIN_GB`; not for a streamed denoiser, not when a level is asked for). AuraFlow's own model on
  24 GB afterwards: 8 bit transformer, 16 bit text encoder, 46.3 s per step, 12.0 GB read, peak 12.8 GB (plan 13.3).
  Of the user's diffusers models the margin moves only AuraFlow; Z-Image Turbo as a diffusers repo already ran in 8 bit
  in the engine (34–38 s per step at 1024², 12.7 GB, plan 14.9).

## 7bc. The test build of 2026-11-03 on the Mac mini M4, 16 GB (2026-11-03, run over SSH)

The test DMG of 19:03 (contains the Chroma mask fix and the English ERNIE enhancer) started from the mounted image with
its own profile, the user's models and helpers on the external disk, one job after another through the queue:

| Check | Model, runtime | Size, steps | s/step | peak (plan) | result |
| --- | --- | --- | --- | --- | --- |
| ControlNet (Canny 0.7) on the 16 GB plan | Juggernaut XL v7, Diffusers 16 bit | 1024², 35 | 5.97 | 11.6 GB (11.5) | follows the edges; refused before 7as |
| Fibo LoRA (anime, 0.9) | Fibo 2.0 Edit Turbo, MLX 8 bit | 1024², 4 | 29.6 | 11.7 GB (11.5) | the LoRA's style clearly |
| ERNIE with the enhancer | ERNIE-Image Turbo, MLX 4 bit | 1024², 8 | 29.2 | 9.5 GB (11.2) | English caption ("A majestic lighthouse stands …") |
| ERNIE without | as above | 1024², 8 | 28.4 | 9.0 GB (11.2) | |
| FLUX.2 [klein] 4B | MLX 4 bit | 1024², 4 | 16.3 | 11.4 GB (9.9) | a fox with one hind leg too many (seed 7) |
| Chroma, two words (*a fox*) | GonzaLomo Chroma, Diffusers 16 bit streamed | 768², 30 | 38.8 | 12.4 GB (11.5) | a fox, no noise (oversaturated: the fine-tune at guidance 4) |

Cancel, the same build: Z-Image Turbo on MLX after the first step ended 45 s later (MLX looks between two steps), FLUX.2
[klein] 4B while loading 1 s, Juggernaut XL on Diffusers 5 s, Anima on ComfyUI 6 s.

From the user's own session log on the Mac mini (build of 2026-11-02): Z-Image Turbo on MLX, 8 bit, 1024², 126 s per
step (17 and 18 minutes per picture) with MLX's peak at 25.1 and 25.6 GB on 16 GB, against 7l's 8.8 GB.

**The cause: mflux 0.24 leaves the weights lazy.** After loading MLX held 0.0 GB; the first step then read and
quantized the transformer and the text encoder at once. The same load in a script on the Mac mini, 2 steps at 1024²:

| | after loading | peak | s/step |
| --- | --- | --- | --- |
| lazy, as the engine loaded | 0.0 GB | 29.3 GB | 84 |
| evaluated part by part (transformer 8.3 GB peak, then text encoder) | 10.8 GB | 12.3 GB | 21 |

The engine now evaluates every MLX model's parts one after another right after loading (`materialize`, the denoiser
first; Fibo with a staged text encoder keeps it for the encoding; before the one-time 8 bit cache of Krea 2 and
Ideogram 4 is written). An mlx Module is a dict: the first version looked for attributes, found none and changed
nothing (Z-Image still 117 s per step, 23.9 GB). In the app on the Mac mini, 1024², the test DMG before and after:

| Model | before | after |
| --- | --- | --- |
| Z-Image Turbo, 8 bit, 9 steps | 117–126 s/step, peak 23.9–25.6 GB | 17.8 s/step, 12.0 GB (plan 11.9) |
| FLUX.2 [klein] 4B, 4 bit | 16.3–16.7 s/step, 11.4 GB | 11.3 s/step, 7.0 GB (plan 9.9) |
| ERNIE-Image Turbo, 4 bit | 28.4–30.4 s/step, 8.7–9.5 GB | 28.5 s/step, 8.7 GB (already loaded at once) |
| Fibo 2.0 Edit Turbo + LoRA, 8 bit | 29.6–35.9 s/step, 11.7 GB | 28.1 s/step, 11.7 GB (text encoder staged) |

Typing a token in Settings while a Z-Image picture loaded and ran worked on the fixed build (the user, on the Mac
mini); the user had seen the field take no input during a picture before, very likely while the Mac swapped.
- FLUX 3's upsampler (the vision-language model) adds 2.8 GB to the peak (14.7 against 11.9 GB, 12.5 planned) and
  about 20 s before the first step. The Flux Skin Detailer DoRA on FLUX.1 dev cost nothing per step (24.8 s against
  31.6 for the plain run, which was the first picture after AuraFlow and unloaded it); the DoRA changes the whole
  picture, not only the skin.
- Anima-Turbo's seed-7 pair had an off-shoulder top on the three-tag side; the shipped pair uses another seed (the
  tip itself says short prompts bring the unexpected).

## 7bd. The three plans of 7bb on the Mac mini M4, 16 GB (2026-11-03, test DMG, run over SSH)

The models copied from the M2 and imported again on the Mac mini (a model imported on another Mac is refused; an
in-place import of a folder that has a model.json keeps it, so Krea 2's manifest was rewritten for this Mac by hand).
Peak = the engine's process footprint, MLX's own peak from its log where it differs:

| Model | Runtime, precision | Size, steps | s/step | peak (plan) | swap used after |
| --- | --- | --- | --- | --- | --- |
| SD 3.5 Medium, first load | Diffusers, 8 bit, T5 8 bit (quantized and cached now) | 768², 8 | 4.93 | 13.4 GB (10.4) | |
| SD 3.5 Medium, again | as above, prompt from the cache | 768², 8 | 4.66 | 6.3 GB (10.4) | |
| Krea 2 Turbo | MLX, 4 bit, text encoder 4 bit (staged) | 768², 8 | 22.3–22.4 | 12.0–12.4 GB (10.7); MLX 14.3 GB | |
| Krea 2 Turbo | as above | 1024², 8 | 41.3 | 11.8 GB (12.0); MLX 14.3 GB | 5.1 GB |
| Qwen-Image 2.1, first run | Diffusers, 8 bit, text encoder 8 bit | 1024², 4 | 42.2 | 20.2 GB (11.9) | 11.1 GB |
| Qwen-Image 2.1, again | as above | 1024², 4 | 42.5 | 18.7 GB (11.9) | 11.8 GB |

- SD 3.5 Medium: only the first load runs over the plan (T5 in 16 bit while it is quantized once); afterwards far
  under it. Open: quantize the text encoder without holding it whole in 16 bit.
- Krea 2: MLX peaks at 14.3 GB at 768² and at 1024² alike, 6.6 GB above the 7.7 GB the model holds after the picture.
  Logged per step through the app's MLX engine: the steps peak at 9.1 GB, the 14.3 GB is the decode alone (3 s). Its
  Qwen VAE decoded in mflux's 512 px tiles already (low-RAM mode); smaller tiles, 1024², the same latents:

  | Decode tiles | MLX peak in the decode | picture against 512 px tiles |
  | --- | --- | --- |
  | 512 px (before) | 14.3 GB | – |
  | 384 px | 13.6 GB | 44.9 dB |
  | 256 px | 11.3 GB | 44.8 dB, no seam at full size |

  Now 256 px tiles for Krea 2 on 16 GB (`DECODE_TILE`). In the app: 768² 23.3 s/step, 11.7 GB (plan 10.7); 1024² 43.8
  s/step, 11.8 GB (plan 12.0), MLX peak 11.3 GB both.
- Qwen-Image 2.1: 6.8 GB over the plan, 11–12 GB in the swap (back to 3 GB when the test app quit). Not the text
  encoder: the second and a third run took the prompt from the prompt cache (no text encoder loaded) and still peaked
  at 18.7 GB, 42.5 s per step. Sampled per process every 2 s (`footprint`): a fresh engine with the prompt from the
  cache held 9.9 GB while denoising (the plan's 11.9 holds); after the one-time quantization, and after every new
  prompt, it stayed at 18–19 GB. Two causes, both fixed:
  - **the text encoder was never let go when staged:** `encode` dropped its own reference, the pipeline object kept
    the 9.2 GB text encoder next to the transformer. Now it is dropped (`self.text_pipe = None`).
  - **the one-time quantization ran in the engine:** it loads the 16 bit weights (the transformer 14 GB) first; it now
    runs in a short-lived process of its own (`quantize_once.py`) that writes the cache and ends; the engine stayed at
    1.5–2.2 GB meanwhile and loads from the cache.

  | Qwen-Image 2.1, 1024², 4 steps, new prompts | s/step | peak (plan) | while denoising | swap used |
  | --- | --- | --- | --- | --- |
  | before | 42.2–42.5 | 18.6–20.2 GB (11.9) | 18–19 GB | 11–12 GB |
  | after | 43.9 | 12.2–12.4 GB (11.9; the encoding) | 9.9 GB | 3.6–4.1 GB (3.1 before the job) |

  The speed did not change: what went to the swap was the idle text encoder.

## 7be. The FLUX models on the Mac mini M4, 16 GB: compute or SSD (2026-11-04, test DMG)

4 steps each, the runtime and precision the app picks on 16 GB. A step bound by computing grows with the pixels
(1024² has 1.78 times the pixels of 768², more with the attention); one bound by reading weights from the SSD does not:

| Model | Runtime the app picks | 768²: s/step, read | 1024²: s/step, read | 1024 / 768 |
| --- | --- | --- | --- | --- |
| FLUX 3 Image Klein | MLX, 8 bit | 7.24, 9.7 GB | 13.68, 0 | 1.89 – computing |
| FLUX.1 dev Q4_K (GGUF) | Diffusers | 21.7, 14.9 GB | 32.3, 0.4 GB | 1.49 |
| FLUX.1 dev (repo) | Diffusers, 16 bit streamed from the SSD | 34.4, 112 GB | 30.1, 77 GB | 0.88 – reading |
| FLUX.2 [klein] 9B | Diffusers, 16 bit streamed from the SSD | 22.3, 72 GB | 26.7, 63 GB | 1.19 – reading |

The streamed models read 16–28 GB per step: their time is the SSD's, not the GPU's. FLUX.1 dev streamed at 768² is
slower than at 1024², and its Q4_K file is 1.6 times as fast at 768².

Now the planner keeps a 4 bit denoiser in memory before it streams 16 bit (`fitting_plan`, the text encoder in 8 bit or
16 bit where any way allows; quantized once in its own process, about 2 minutes on the Mac mini, cached). The same
jobs, the same seed:

| Model, Mac mini 16 GB | 768²: s/step before → after | 1024²: s/step before → after | read per job after | peak (plan) |
| --- | --- | --- | --- | --- |
| FLUX.1 dev (transformer 4 bit, T5 16 bit staged) | 34.4 → 18.9 | 30.1 → 29.8 | 0 | 9.9–10.0 GB (10.9) |
| FLUX.2 [klein] 9B (transformer 4 bit, text encoder 8 bit) | 22.3 → 17.0 | 26.7 → 26.8 | 0 | 9.0–9.1 GB (9.8) |

1.82 and 1.31 times as fast at 768², as fast at 1024² (there the step is the GPU's), no SSD reading. The pictures keep
their composition (FLUX.1 dev 28.2 dB at 768², 32.3 dB at 1024² against 16 bit; klein 9B's fox turns its head, 17–19
dB), clean at full size.

**Fewer steps: FLUX.1-Turbo-Alpha (alimama, FLUX.1-dev non-commercial licence, 694 MB) on the 4 bit FLUX.1 dev.** The
first try failed: a LoRA on the 4 bit transformer stopped with KeyError 'context_embedder.weight' (quanto names 4 bit
weights `x.weight._data._data`, the loader's lookup only knew the 8 bit `x.weight._data`); fixed. 1024², seed 7, the
lighthouse prompt:

| | steps | s/step | per picture | peak |
| --- | --- | --- | --- | --- |
| without LoRA | 28 | 23.3 | 664 s | 9.6 GB |
| Turbo-Alpha at 1.0, guidance 3.5 | 8 | 31.2–31.3 | 258–284 s | 9.6–10.2 GB |

The LoRA beside the 4 bit weights costs 34 % per step, the picture takes 2.6 times less (11:04 → 4:18 min); the
composition differs, the quality holds at full size (sharp lighthouse and rocks, clean water). FLUX.2 [klein] and FLUX
3 Klein are distilled already (4 and 16 steps, their makers' cards).

## 7bf. Inpainting on the Mac mini M4, 16 GB: three cases, the blend, removing, inpainting models (2026-11-04, test DMG)

Three fixed cases at 1024², seed 7, **Change** 100 %, each model with its maker's steps and guidance: *remove* the
small house beside the lighthouse (rectangle, empty prompt), *replace* the fox with a brown rabbit (ellipse; one ear
deliberately outside the mask), *add* a seagull in the free evening sky (ellipse). Fibo 2.0 Edit Turbo (MLX) got the
same as instructions (*remove the small house* …).

**Before.** No model removed the house: SD 1.5 Inpainting left a scaffold, Juggernaut XL an orange patch and a steel
tower, Z-Image Turbo painted a woman in a white dress, FLUX.1 dev a scaffold with two people, Fibo 2.0 the house again.
In four of five a half-transparent house showed through, and the added seagull of FLUX.1 dev and Z-Image sat in a
lighter disc. Cause of the see-through: `masks.blend_into` blurred the grown mask into its inside, so 15 % of the old
picture on average and up to 40 % stayed inside the user's mask (the house mask: share of the new picture 0.60–0.98,
68 % of its area below 0.9). Replacing worked with all but SD 1.5 Inpainting (a second body); its seagull was a blur.

**Changed.** (1) The soft edge lies outside the grown mask, inside it everything is new (all three engines). (2) An
empty prompt removes: LaMa (already in the app for Restore) fills the part from its surroundings, the model refines
that at **Change** 40 %. (3) SDXL inpainting checkpoints (9 channel UNet) and FLUX.1 Fill [dev] are recognised, FLUX.2
[klein] inpaints with diffusers' Flux2KleinInpaintPipeline. (4) SDXL's VAE also casts a picture it encodes to bfloat16
when its config has no force_upcast: the SDXL inpainting VAE failed with "Input type Half and bias type BFloat16".

**After**, the same cases (s/step of *remove* counts the nominal steps, 40 % of them run):

| Model | remove | replace | add | per picture (replace / add) | peak (plan) |
| --- | --- | --- | --- | --- | --- |
| SDXL Inpainting 0.1 (25 steps, guidance 8) | sky, a little haze | good, softer | good, warmer sky | 102 s (3.8 s/step) | 9.5 GB (9.4) |
| FLUX.2 [klein] 4B (4 / 1) | sky, haze, the roof left outside the mask | good | good, sharp | 122 s (24.4 s/step) | 10.5 GB (9.5) |
| FLUX.2 [klein] 9B (4 / 1) | sky, haze | good | good | 280 s (52.3 s/step) | 12.2–13.7 GB (9.8) |
| SD 1.5 Inpainting (25 / 7) | the house's shape stays white | a second body | a blur | 16 s | 4.7 GB (3.6) |
| Juggernaut XL v7 (35 / 4.5) | sky, spray | good | good, a faint disc | 147 s (3.9 s/step) | 9.8 GB (9.4) |
| Z-Image Turbo (9 / 0) | sky, haze | good, a lighter disc | good, a lighter disc | 185 s (19.3 s/step) | 9.7 GB (11.9) |
| FLUX.1 dev, 4 bit (28 / 3.5) | sky, haze | good, a lighter disc | good, a lighter disc | 702 s (22.6 s/step) | 11.6 GB (10.9) |

Nothing shows through any more and no model invents an object where something was removed; the haze is LaMa's
smoothing beside the lighthouse, where the test mask left part of the house. The lighter disc of Z-Image and FLUX.1 dev
(fainter with Juggernaut XL) is not the old picture: these pipelines (not trained for masks) shift the tone of the whole repainted part, in the strip
around the mask by up to 25 levels (Z-Image, blue) against 2–6 with FLUX.2 [klein]. FLUX.2 [klein] takes twice as long
per step as for a new picture: its inpainting pipeline passes the picture along as reference tokens (twice the image
tokens), which also takes 3–4 GB more than its plan. FLUX.1 dev reads 19 GB per job because a new prompt reloads its
staged T5 and 4 bit transformer, not from streaming (as fast per step as a new picture, 7be).

**The disc, second and third round.** A soft edge inside the grown strip (instead of across its edge) only blurred the
disc and faded wing tips reaching into the strip; matching the colours of the whole repainted part (tried on the saved
pictures first) left it too, because the seagull itself counts in. What removes it: `masks.blend_into` measures the
painted picture's offset against the original in a band along the grown mask's inner edge (leaving out what the
model drew there, more than 48 levels), fills it smoothly inwards (push-pull in blocks of half the strip width, like
seamless cloning) and subtracts it inside the mask; the soft edge is narrow again (a quarter of the strip). Across the
edge the offset is now 0–2 levels (FLUX.1 dev before: 3–8, Z-Image 6–25). SDXL Inpainting 0.1 had a dark noisy disc:
its card says strength below 1 (at 1 the picture is degraded), it now runs at 0.99 at most. FLUX.2 [klein]'s plan
counts the reference tokens (one more set of activations).

| Model, case | round 2 (soft edge in the strip) | round 3 (offset removed) | per picture | peak (plan) |
| --- | --- | --- | --- | --- |
| Z-Image Turbo, add | disc, softer edge | no disc | 209 s | 8.9 GB (11.9) |
| Z-Image Turbo, replace / remove | good / sky, haze | good / sky, haze | 180 / 88 s | 8.9 / 9.4 GB (11.9) |
| Juggernaut XL v7, add | a faint disc | no disc | 162 s | 9.6 GB (9.4) |
| SDXL Inpainting 0.1, add | a dark noisy disc | no disc, a smaller seagull | 116 s | 9.5 GB (9.4) |
| FLUX.2 [klein] 9B, replace | good | good | 235 s | 11.8 GB (12.6, before 9.8) |
| FLUX.1 dev, add | a lighter disc | a faint outline, clouds painted anew | 719 s | 10.7 GB (10.9) |
| Juggernaut XL v7, AI Canvas extend | good | good, no seam | 163 s | 9.7 GB (9.4) |

Restore's repair with FLUX.2 [klein] 4B (scratches on the lighthouse photo, 4 steps): 166 s, 8.7 GB (9.5); the first
test photo (a fox) was refused by Restore's own face check (the fox's head counted as a new face), as it should.

**FLUX.1 Fill [dev]** (YarvixPA's Q4_K_S GGUF, 6.8 GB, base components from black-forest-labs/FLUX.1-Fill-dev with a
Hugging Face token; 50 steps, guidance 30 as its card says). First run: a black or flat brown mask in all three
cases. In float16 (the app computes FLUX.1 in float16 where bfloat16 is slow) its activations overflow at 1024 px and
guidance 30, NaN from step 4–10 on (plain diffusers at 512 px stayed clean in both); bfloat16 is clean, so FLUX.1
Fill now always computes in bfloat16. After that:

| Case | result | per picture | peak (plan) |
| --- | --- | --- | --- |
| add | a seagull, no disc, the sky continues | 817 s (14.2 s/step, step caching 27 of 50) | 13.6 GB (10.6) |
| replace | a rabbit, the best of all models | 782 s | 14.2 GB (10.6) |
| remove | sky, a little haze | 424 s (20 of 50 steps) | 14.8 GB (10.6) |

The peak lies 3–4 GB above the plan, and not while denoising (10.3–11.0 GB, as planned): a new prompt loads the
staged 4 bit T5 next to the transformer, +5.2 GB against 3.1 planned. Cause: transformers' quanto quantizer leaves the
layers a model keeps in float32 out, T5's wo (1.0B of its 4.76B parameters), so 2.0 GB of the "4 bit" T5 stayed 16
bit. In 4 bit too, one of three test prompts went off (cosine to the 16 bit embedding 0.91 against 0.97); in 8 bit
they stay as close as before (0.959 / 0.969 / 0.975 against 0.961 / 0.969 / 0.975), so the cache now quantizes them in
8 bit (only with a bfloat16 text encoder; float32 guards against float16 overflow). Restored alone: +3.96 GB instead
of 5.2. FLUX.1 Fill with a new prompt: 11.9–12.6 GB instead of 13.1–13.6. Tried and dropped: restoring the cache
straight onto the GPU (20.3 GB, quanto lays out its empty 16 bit weights there first), and reading the cache mapped
from the disk instead of into the heap (no change: quanto copies into tensors of its own). T5 alone in a process: 3.2
GB as planned, after moving to the GPU the process keeps 1.2 GB on the CPU side, which macOS takes back on the next
load (4.3 → 3.1 GB). A general surcharge in the plan would have changed ten measured plans of other models, so FLUX.1
Fill alone gets one (+2.0 GB while a new prompt is encoded): on 16 GB it plans T5 in 8 bit and lets the transformer
make room for a new prompt. Through the engine on the Mac mini, three jobs (the first with the one-time 8 bit
quantization of T5): peak 10.9–11.0 GB, under the budget of 12; a cached prompt needs neither. In the test app
(2026-11-05), two new prompts, 8 steps: 313 and 289 s per job, of which the picture took 254 s each, so a new prompt
costs about 35 s (T5 in 8 bit loaded and encoded, the transformer loaded again; the first job 60 s with loading the
model); peak 10.9 GB both times (planned 10.0). FLUX.1 Fill is in the recommended models now.

## 7bg. Fibo 2.0 Edit Turbo on MLX, Mac mini M4 16 GB: where an edit takes its memory (2026-11-05)

Masked edits on MLX peaked at 13.1–13.8 GB on the Mac mini (7bf, first round) against a plan of 11.5; the M2 measured
11.0–11.1 for the same jobs (7aj). Through the app's MLX engine, 1024², 4 steps, seed 7, the footprint sampled per
phase of mflux's run:

| Job | Whole | prompt encoded | denoising | VAE decode |
| --- | --- | --- | --- | --- |
| masked edit (add a seagull) | 250 s | 8.7 GB | 13.2 GB | 10.8 GB |
| masked edit (replace the fox) | 248 s | 8.8 GB | 13.2 GB | 10.8 GB |
| edit without a mask (a snowy night) | 252 s | 8.9 GB | 13.4 GB | 10.9 GB |
| text to image | 123 s | – | 10.5 GB | 10.7 GB |

The peak lies in the steps of an edit, masked or not: the picture to edit goes along as context tokens (twice the
tokens, twice the time per step); the prompt with its picture and the decode stay low. On the M4 that costs 2.9 GB
above text to image, on the M2 0.2. The plan counts it now for every edit on MLX (`edit_gb`), so the job notes when
less memory is free than that; how the steps could take less on the M4 is open. In the test app afterwards: the
masked edit planned at 14.4 GB, measured 13.5 GB, 250 s.

## 7bh. Restore's repair with a consistency LoRA, Mac mini M4 16 GB (2026-11-05, test DMG)

A helper for Restore: lrzjason's consistency LoRAs for FLUX.2 [klein] (huggingface.co/lrzjason/Consistance_Edit_Lora,
Apache-2.0; `f2k_4B_consist_20260314` 368 MB and `f2k_9B_lcs_consist_20260415` 332 MB, made for the Base models
against drift while editing). Restore's repair (repair only, size kept, 4 steps, seed 7, LoRA at 1.0) on three cases:
the AI-made photo of two women (832 × 1024, made old: sepia, half size, grain, JPEG 35, five scratches, dust, a
stain) with the damage painted and without a mask (the whole photo), and the lighthouse with painted scratches (7bf).
LM Studio held 6.9 GB on the Mac mini during the run (the user's, left running).

Both files fail in the app: they name 20 (4B) and 32 (9B) of their layers `lora.down/up` and the rest `lora_A/B`;
diffusers' reader takes one naming per file, so 80 % / 77 % of the layers found their place and the job was refused.
Measured with copies renamed to `lora_A/B` only (all layers found).

| | 4B | 4B + LoRA | 9B | 9B + LoRA |
| --- | --- | --- | --- | --- |
| Women, painted damage: time, peak | 141 s, 9.7 GB | 129 s, 11.7 GB | 289 s, 13.0 GB | 271 s, 14.7 GB |
| Women, whole photo: time, peak | 108 s, 10.6 GB | 111 s, 11.7 GB | 221 s, 12.5 GB | 251 s, 14.9 GB |
| Lighthouse, painted scratches: time, peak | 112 s, 9.5 GB | 116 s, 11.7 GB | 227 s, 12.5 GB | 256 s, 14.8 GB |
| Planned | 9.5 GB | 9.5 GB | 9.8 GB | 9.8 GB |
| Guard (whole photo): change in the picture | 3.0 % | 4.1 % | 4.3 % | 3.8 % |
| Women vs the clean picture, PSNR whole / faces (painted) | 23.6 / 25.1 | 23.1 / 25.1 | 23.8 / 25.1 | 23.4 / 25.1 |
| Women vs the clean picture, PSNR whole / faces (whole photo) | 18.5 / 18.9 | 15.6 / 14.7 | 18.6 / 17.8 | 16.5 / 15.0 |

(The damaged input: 20.5 / 25.1. PSNR on luminance with the levels matched outside the damage.)

Seen at full size:
- Lighthouse: without the LoRA both models left the scratches as light streaks; with it 4B removed them entirely and
  9B left one faint streak.
- Women, painted: all four removed the scratches and the stain; no difference to see.
- Women, whole photo: 9B without the LoRA coloured the sepia photo (red bricks, green hedge) despite the rule "do not
  colorize it"; with the LoRA it stayed sepia. 4B stayed sepia either way; with the LoRA it left a few dust specks and
  moved the picture a little (the lower PSNR of both LoRA runs is mostly that shift).
- All results passed the guard rails; none was refused.

Memory: the plan of every FLUX.2 [klein] edit with a picture is too low. The picture goes along as reference tokens;
the plan counts that only for inpainting with a mask (`engine.py`, `inpaint_reference`), Restore hands the generation
no mask: 9B 12.5–13.0 GB against 9.8 planned, 4B up to 10.6 against 9.5. The LoRA adds another 1.1–2.2 GB.

Checked in the test app afterwards (same day, test DMG, nothing else running on the Mac mini; the original LoRA file,
fetched as the helper on first use; option "Consistency LoRA" in Restore; repair only, 4 steps, seed 7):

| | Time | Peak | Planned | Guard |
| --- | --- | --- | --- | --- |
| Lighthouse, 4B, option on | 130 s | 10.8 GB | 12.9 GB | 0.1 % |
| Women, painted, 4B, option on | 116 s | 11.7 GB | 12.9 GB | 0.2 % |
| Lighthouse, 4B, option off | 105 s | 9.6 GB | 11.2 GB | 0.1 % |
| Lighthouse, 9B, option on (repairs without it) | 238 s | 12.5 GB | 12.6 GB | 0.2 % |

The mixed file loads whole now (no refusal); 9B shows the note that the LoRA is made for 4B. The pictures match the
first run: with the option 4B removes the lighthouse scratches entirely, without it they stay as streaks; the women stay
sepia with scratches, dust and stain gone. The plans now lie above every peak.

## 7bi. Image to image with FLUX.2 [klein] 4B and the consistency LoRA, Mac mini M4 16 GB (2026-11-05, test DMG)

klein has no image to image of its own: the picture goes along as a reference and the prompt says what to change, so
the consistency LoRA of 7bh works there too. Three edits (4 steps, guidance 1, seed 7, size of the picture): a snowy
winter night at the lighthouse (the whole picture), a red coat for the woman on the left (a small part), the black and
white photo of the two women as a loose watercolour (the style). The LoRA as a user LoRA (the original file).

| | without | LoRA 0.5 | LoRA 1.0 |
| --- | --- | --- | --- |
| Time | 115–131 s | 107–121 s | 108–110 s |
| Peak (planned 11.2) | 9.5–9.8 GB | 10.0–10.1 GB | 10.1 GB |
| PSNR to the picture: winter / coat / watercolour | 9.2 / 11.5 / 11.8 | 10.1 / 12.6 / 12.9 | 17.7 / 13.3 / 14.3 |

(PSNR on luminance, the input scaled to the result; a higher value is closer to the picture.)

Seen:
- Without the LoRA every edit is done in full, but the picture is painted anew: the winter night has another coast,
  trees and a lamp; the watercolour has a new background in colour.
- LoRA 1.0 keeps the picture and holds the edit back: a little frost and the sunset sky stays, a pale pink coat, the
  watercolour only washed out.
- LoRA 0.5 does both: night and snow on the same coast and lighthouse, a red coat with the rest unchanged, a light
  watercolour on the same photo.

Checked in the test app afterwards with the new option "Keep the picture" (the helper at 0.5): the three 4B pictures
are pixel for pixel those of the run above, 108 s each, peak 10.0-10.1 GB, planned 12.9 GB (the helper's 1.7 GB
counted). 9B: 216 s, 12.0 GB (planned 12.6), the note that the LoRA is made for 4B, edited without it. The first job
waited 28 minutes between the engine's start and loading the model (every earlier run: 3-60 s): macOS asked on
the Mac mini's screen for the removable volume (7bj); the denoising itself took 108 s.

## 7bj. Security updates checked on the Mac mini M4 16 GB (2026-11-05, test DMG)

Electron 44.5.1 → 44.10.2 (Chromium 152.0.7977.169); in all three runtimes certifi 2026.10.23, filelock 4.2.9,
setuptools 84.2.1, in Diffusers and ComfyUI Pillow 12.3.0 → 13.0.0 (CHANGELOG, *Security updates*). One job per
engine and family, the same seed, first with Electron 44.10.2 on the old runtimes, then on the new ones (the test DMG
brought the Mac mini's runtimes to the new lock at its first start: 4, 3 and 4 packages, 2 s each):

| Job | old runtimes: time, peak | new runtimes: time, peak | planned |
| --- | --- | --- | --- |
| SD 1.5 (DreamShaper 8), 512², 20 steps | 34 s, 3.8 GB | 32 s, 3.8 GB | 3.6 GB |
| Z-Image Turbo, 1024², 8 steps | 195 s, 12.0 GB | 192 s, 12.0 GB | 11.9 GB |
| FLUX.2 [klein] 4B, 1024², 4 steps | 72 s, 7.0 GB | 71 s, 7.0 GB | 9.9 GB |
| klein 4B, Image to image, Keep the picture | 119 s, 10.1 GB | 118 s, 10.1 GB | 12.9 GB |
| klein 4B, Restore repair with the consistency LoRA | 120 s, 10.8 GB | 117 s, 10.9 GB | 12.9 GB |
| FLUX 3 Image Klein (MLX, 8 bit), 1024², 4 steps | 74 s, 10.8 GB | 73 s, 10.6 GB | 10.0 GB |
| FLUX.1 [schnell] 8 bit GGUF, streamed, 1024², 4 steps | 339 s, 15.9 GB | 258 s, 15.9 GB | 12.0 GB |

All pictures are fine; seven pages (Start, Models, Hardware, Settings, Image to image, Restore, Licences) look as
before. A fetch from the page to the internet stays blocked (as meant).

Then uv 0.13.7, Python 3.11.18 and ComfyUI 0.44.0 (CHANGELOG, same entry): the test DMG fetched uv, made the venvs
of Diffusers and ComfyUI again on 3.11.18 (59 packages from the cache in 7 s; MLX moved with uv's link to 3.11.18 by
itself), fetched ComfyUI 0.44.0 and its 6 changed packages; 23 s in all. The same jobs again, and ComfyUI:

| Job | time, peak | planned |
| --- | --- | --- |
| SD 1.5, Z-Image, klein 4B, Keep the picture, Restore, FLUX 3 MLX | 43, 191, 72, 127, 117, 74 s; peaks as above (±0.1 GB) | as above |
| FLUX.1 [schnell] 8 bit, streamed | 248 s, 15.9 GB | 12.0 GB |
| Anima Turbo (ComfyUI), 1024², 10 steps | 103 s, 8.8 GB | 9.1 GB |
| MOSS-Image 8-step DMD (ComfyUI), 1024², 8 steps | 209 s, 9.1 GB | 9.2 GB |
| NetaYume v4 (ComfyUI), 1024², 20 steps | 322 s, 10.7 GB | 8.9 GB |
| Upscale ×2, Real-ESRGAN (ComfyUI) | 18 s, 5.9 GB | – |

All pictures are fine. NetaYume took 10.7 GB as in 7af (10.8 at 45 steps, planned 11.6), but is planned 8.9 GB now; release todo.

Found, not changed: FLUX.1 [schnell] 8 bit streamed takes 15.9 GB against 12.0 planned on 16 GB (and reads 105 GB
from the disk per picture); release todo.

The test machine: each ad-hoc signed test build is a new app to macOS, and the first start waits for the question
about files on the removable volume (2TB_FangX) on the Mac mini's screen, at 0 % CPU: 28 min at 18:16, 2.5 min at
19:16, 6 min at 20:25; the permission's entry in the TCC database was written in the same second the engine or the
runtime installation went on. Test builds are signed with one fixed self-signed identity since; the next new build
started without the question (engine after 25 s). Released builds (Developer ID) keep their identity anyway.

## 7bk. Quanto against GGUF for the denoiser, Mac mini M4 16 GB (2026-11-05/06)

Diffusers' Quanto backend "is deprecated and will be removed in version 1.0.0" (its docs); VulKara quantizes the
denoiser through it (Transformers' Quanto, for the text encoders, has no such note). The candidate with no new
package: GGUF, written once tensor by tensor (`convert_gguf`, the diffusers names kept, which diffusers' single-file
loader takes without converting). A probe script with the app's runtime (Python 3.11.18, diffusers 0.41, torch
2.14.1), one process per variant, prompt encoded once before, 1024², seed 7, everything held on the GPU (so the peaks
are higher than in the app and compare only with each other). Z-Image's 16 bit (12 GB) swapped on 16 GB (5 GB swap
at 5 % CPU, stopped): its reference picture is from the M2 (24 GB); the same GGUF Q8_0 on the M2 and the M4 differ
by 37.8 dB, the share of the chip.

| FLUX.2 [klein] 4B, 4 steps | load | s/step | peak | read | to 16 bit |
| --- | --- | --- | --- | --- | --- |
| 16 bit | 11.6 s | 10.6 | 14.5 GB | 5.2 GB | – |
| Quanto 8 bit | 26.1 s | 11.2 | 13.9 GB | 7.8 GB | 29.8 dB |
| GGUF Q8_0 (4.12 GB, 43 s to write) | 7.4 s | 11.4 | 13.5 GB | 4.0 GB | 36.2 dB |
| Quanto 4 bit | 24.9 s | 12.0 | 10.4 GB | 7.7 GB | 20.1 dB |
| GGUF Q4_0 (2.18 GB, 8 s) | 3.7 s | 12.5 | 9.6 GB | 2.4 GB | 22.0 dB |

| Z-Image Turbo, 8 steps | load | s/step | peak | read | to 16 bit (M2) |
| --- | --- | --- | --- | --- | --- |
| Quanto 8 bit | 89.9 s | 19.3 | 13.7 GB | 23.5 GB | 31.8 dB |
| GGUF Q8_0 (6.54 GB, 108 s to write) | 13.2 s | 19.2 | 12.5 GB | 6.5 GB | 25.3 dB |
| Quanto 4 bit | 91.4 s | 20.3 | 11.4 GB | 23.4 GB | 22.9 dB |
| GGUF Q4_0 (3.47 GB, 102 s) | 6.7 s | 21.0 | 10.2 GB | 3.7 GB | 21.5 dB |

(16 bit on the M2: 38.8 s/step, 20.0 GB; GGUF Q8_0 there 39.8 s/step, 14.9 GB, 25.4 dB.)

GGUF takes 0.4–1.3 GB less and loads in a fraction of the time (written once; Quanto quantizes from 16 bit at every
load here, the app keeps a quantized cache), and is as fast per step at 8 bit, 3–4 % slower at 4 bit. Its pictures
are closer to 16 bit for klein and further for Z-Image; at full size all are the same fox, the 4 bit ones with
moved details. Quality is no reason against either; the open questions for a switch are the text encoders
(Transformers' Quanto stays) and models without a single-file mapping in diffusers.

## 7bl. The denoiser as a GGUF copy in the app, Mac mini M4 16 GB (2026-11-06, test DMG)

After 7bk the Diffusers engine writes a quantized denoiser once as GGUF (Q8_0/Q4_0, `gguf_cache.py`) instead of
quantizing it with Diffusers' Quanto backend; ControlNets in 8 bit are quantized by optimum-quanto itself. Every family
with a quantized denoiser on the Mac mini, through the app (Text to image on klein 4B and Z-Image runs on MLX here and
does not touch it). The second run of a model, from the copy; the first one wrote it:

| Job | copy | first run (writes the copy) | s/step | peak (plan), from the copy | with Quanto before |
| --- | --- | --- | --- | --- | --- |
| klein 4B, Keep the picture (LoRA) | Q8_0, 4.12 GB | 354 s (copy 46 s) | 108 s per picture | 12.6 GB (12.9), MLX still held 5.4 GB | 108 s, 10.1 GB (7bi) |
| klein 9B, 768 px, 4 steps | Q4_0, 5.11 GB | 237 s (copy about 2 min) | 17.6 | 9.0 GB (9.8) | 17.0, 9.0 GB (7be) |
| FLUX.1 dev + Turbo-Alpha, 8 steps | Q4_0 | 449 s | 30.2 | 10.9 GB (10.9) | about 32, 9.6 GB (7be) |
| SD 3.5 Medium, 10 steps | Q8_0, 2.63 GB | 394 s | 8.0 | 4.8 GB (10.4) | – |
| Qwen-Image 2.1, 8 steps, guidance 1 | Q8_0, 7.56 GB | 562 s (guidance 4) | 21.5 | 12.3 GB (11.9) | 43.9 (7bd, other settings) |
| Juggernaut XL + ControlNet Canny, 8 bit ControlNet | – | 165 s | 6.0 | 11.2 GB (11.5) | 5.97, 11.6 GB (7bc) |

Qwen-Image 2.1 with guidance 4 (two passes per step, 42.8–42.9 s/step, 11.4–12.4 GB) gave a blur at 8 steps; with its
own guidance 1 the fox is right: the setting of the test, not the copy (all 297 tensors within 0.4 % of the source,
none missing, the names taken as they are). A new prompt on Qwen-Image costs 31 s (435 against 404 s): the text encoder
in its stage, then the denoiser's copy loaded again. 4 bit for "auto" in place of that would save part of those 31 s
of 435 at 20–22 dB instead of 30–36 (7bk): left as it is. The first SD 3.5 run failed in the first test build: the
converter had packed its position table (`pos_embed`, a buffer) to 8 bit, which was not unpacked again; now only
weights are packed and buffers are unpacked too. Writing a copy took about as long as Quanto's one-time quantizing
(klein 9B in 4 bit about 2 min, as in 7be). The old Quanto copies of the denoisers were removed on the way.

## 7bm. FLUX.1 [schnell] 8 bit GGUF: streamed in 16 bit or a 4 bit copy in memory, and NetaYume's plan (2026-11-06)

The 8 bit file (12 GB) does not fit a 16 GB plan whole, so the engine streams its transformer from the SSD, unpacked to
16 bit (`stream_cache`, 22 GB): every step reads it again, 98–106 GB per picture, 248–339 s, peak 15.9 GB against a
plan of 12.0 (7bj). A probe (runtime of the app, everything on the GPU, prompt encoded before, 1024², 4 steps, seed 7)
with the file written once as Q4_0 (6.7 GB, 63–74 s from the Q8_0 file, tensor by tensor):

| | load | s/step | picture | read | peak (probe) |
| --- | --- | --- | --- | --- | --- |
| Q4_0 copy in memory | 13.2–13.7 s | 27.2 | 112 s | 6.7 GB | 14.0–14.5 GB |
| the Q8_0 file whole (swaps on 16 GB) | 74.4 s | 38.3 | 156 s | 41.0 GB | 18.6 GB |

The 4 bit picture is the same fox (21.0 dB to the 8 bit one). In the app FLUX.1 dev's 4 bit copy took 10.9 GB (7bl);
streamed in 16 bit the plan of the blocks in flight is below what they take (15.9 against 12.0), which a 4 bit copy
in memory avoids. Open: the 4 bit copy in the app.

NetaYume v4 on ComfyUI took 10.7 GB against a plan of 8.9 (7bj): the plan counts the text encoder dropped after the
prompt, and ComfyUI drops it only when less than the memory kept free is left (`--cache-ram`, 4 GB on 16 GB). On an
otherwise empty Mac mini it keeps it (under the budget of 12); with 8 GB wired it used 8.7 GB (7ae). Not a fault.

## 7bn. Picture to prompt on the Mac mini M4 16 GB (2026-11-06)

Florence-2 base and large (florence-community, MIT, transformers' own class) with `<MORE_DETAILED_CAPTION>` (3 beams),
Qwen3-VL 2B Instruct (Apache-2.0) asked for "one paragraph prompt for an image generator: subject, setting, light,
colours, style, camera", 16 bit on MPS, three pictures (the two women, the lighthouse, a fox):

| Model | files | load | per picture | peak |
| --- | --- | --- | --- | --- |
| Florence-2 base | 0.46 GB | 2.3 s | 1.0–3.7 s | 2.2 GB |
| Florence-2 large | 1.55 GB | 1.9 s | 2.4–3.1 s | 4.2 GB |
| Qwen3-VL 2B | 4.26 GB | 3.8 s | 8.4–9.4 s | 7.7 GB |

Both Florence-2 sizes describe a third woman "in the middle" of the two and put the floral pattern on the wrong
clothes; their texts read as descriptions ("The image is a photograph of …"). Qwen3-VL 2B gets the two women and their
clothes right and writes prompt-like text with light, colours and camera; it called the hedge of the black and white
photo "dark green", and 200 tokens cut its texts mid-sentence. In 8 bit it would take about half the memory (not
measured).

## 7bo. Fibo 2.0's edit on the M4 and the M2: attention (2026-11-06)

7bg left open why a Fibo 2.0 edit on MLX takes 2.9 GB above text to image on the M4 and 0.2 on the M2. Twice the tokens
would need 3.8 GB if the attention scores were materialised (24 heads, 9216 tokens, 16 bit). `mx.fast.scaled_dot_product_attention`
of that size (MLX 0.32.4) takes no memory beyond its inputs on either Mac (bfloat16 and float16): the fused kernel runs
on both. The cause lies elsewhere and stays open.

## 7bp. FLUX.1 [schnell] 8 bit GGUF streamed: the peak is the one-time unpacking, done again when the compute type flips (2026-11-06, Mac mini M4 16 GB, test DMG)

Through the app (queue taken, no other job on the Mac mini; 1024², 4 steps, a new prompt each), the engine's
footprint sampled every 2 s and `VK_STREAM_PROFILE=1`:

| Run | what happened before denoising | picture | job | peak (plan 12.0) | swap |
| --- | --- | --- | --- | --- | --- |
| first | the GGUF file unpacked into the stream cache again (16:27:20–16:29:01) | 147 s | 466 s | 14.2 GB | up to 6.7 GB |
| second | the cache used as it is | 122 s | 138 s | 9.0 GB | unchanged |

Denoising streamed takes 9.2 GB in both, under the plan; each picture reads 80.9 GB of blocks (3.4 GB/s, 20 %
waiting for the SSD when nothing else reads). The peak of 7bj and 7bm (15.9 GB, 248–339 s) was the unpacking, not the
blocks in flight: Diffusers reads the whole 12.7 GB GGUF file into memory (`tensor.data.copy()` in
`load_gguf_checkpoint`) before the blocks are written one by one. It ran again because the stream cache is kept per
compute type and the engine's check whether bfloat16 is slow flips on the M4: its logs say "fast" and "slow" on the
same days (2026-11-05: one of each, 2026-11-06: two "fast", one "slow"), a timing of ten 1024×2048 matmuls against a
limit of 1.3. Every flip unpacks the cache again (and computes the next pictures in the other type). Steady, the
streamed picture takes 122 s against 112 s for a 4 bit copy in memory (7bm).

After the fix (the unpacking reads the GGUF file memory-mapped, the bfloat16 check timed once and kept; the cache's
marker removed to unpack it again): unpacking 17:17:31–17:18:46, the engine at 4.9 GB at most, swap unchanged (2.4
GB); the blocks are byte for byte those of the copying read (flux1-dev Q4_K_S on the Mac mini, under the queue: 58
files the same, 3.2 GB instead of 8.8, 53 s instead of 58). Two pictures: 9.2 / 8.9 GB (plan 12.0), 270 s with the unpacking, 162 s without, 139 s
for the picture itself (bfloat16, timed "fast" and kept).

## 7bq. Fibo 2.0 Edit Turbo on the M4: where the edit's extra memory lies (2026-11-06, Mac mini M4 16 GB, test DMG)

Through the app (queue taken, 1024², 4 steps, seed 7, the engine sampled every 2 s): text to image 129 s, peak 10.95
GB (plan 11.5), MLX's own peak 10.2 GB; the edit of the lighthouse ("Make it a snowy winter night") 248 s, peak 13.41
GB (plan 14.4), MLX's peak 14.6 GB, swap 2.4 → 5.6 GB. Both load the model again for the job (8.8 GB in use, the text
encoder loaded only to encode). The edit's footprint stays at about 11 GB through its steps (text to image about 10);
its peak is one short rise to 13 GB right before the first step. A probe with mflux alone (text encoder kept, one
step) splits the parts: encoding the picture to edit takes +3.9 GB in one piece and +1.9 GB in the tiles the engine
uses on 16 GB (so not the cause), a step of the edit +1.6 GB above what is held, the same with every block evaluated
on its own (no graph held over). Left as the likely cause: the prompt is encoded with the picture (Fibo's text encoder
sees it) while the transformer is in memory; not measured yet.

Measured with mflux alone (the engine's order: all but the text encoder read at load, the text encoder dropped
before the loop; 1024², 2 steps, seed 7, queue taken, no okAI job): as the engine runs it 123 s, MLX's peak 2.0 GB
encoding the picture, 10.1 / 10.2 GB in the steps, 10.3 GB decoding, swap 2.0 → 1.9 GB; with the prompt evaluated
and the text encoder dropped right after it 123 s, 5.3 GB for the prompt, then the same 2.0 / 10.1 / 10.2 / 10.3 GB.
So the late prompt costs nothing: evaluated lazily inside the first step, the dropped text encoder's weights come in
and go again as they are used. The suspected cause is ruled out, and mflux alone does not reach the app's 14.6 GB.
A first run of the same probe right after an okAI job (swap 5.6 GB used at its start) ended in Metal's
"Insufficient Memory"; the app's own measurement above also started with 2.4 GB in swap. The app measured again
on a quiet Mac (queue taken, no okAI job, swap 1.9 GB at the start, same picture, 4 steps, seed 7): 252 s, 55 s a
step, peak 13.53 GB (plan 14.4), MLX's peak 14.6 GB again, swap 1.85 → 4.75 GB within 8 s of the first step, back to
2.3 GB a minute later. So the rise is the app's, not okAI's. The probe differs in one point: its loop over the model's
attributes read nothing at load (an mlx Module keeps its parts as items; "loaded 0.0 GB"), so the transformer came in
lazily inside the first step, after the prompt; the engine reads the transformer at load (8.8 GB in use) and the
staged text encoder then comes in on top of it for the prompt, inside the first step. A corrected probe (the parts read as the
engine does, 4 steps, queue taken, swap 2.1 GB) splits it: in the engine's order, but the picture to edit evaluated as
soon as it is encoded, load 13 s, 232 s, MLX's peak 10.7 GB encoding the picture, 10.3/10.4 GB in the steps and the
decode, swap 2.06 → 2.22 GB; with the prompt evaluated and the text encoder dropped before the rest is read, 244 s,
5.5 GB for the prompt, 10.8 / 10.3 GB, the same. So the order of prompt and transformer does not matter; what lifts
the app to 14.6 GB is that nothing is evaluated before the loop: the picture's encoding (VAE in tiles), the lazy
prompt and the first step run as one graph. Evaluating the encoded picture on its own looked enough (−3.9 GB, same time),
but in the app it was not: with it the test app still peaked at 13.21 GB (MLX 14.2 GB, 254 s, swap 2.0 → 5.1 GB). A
probe through the engine's own _generate_fibo2 (source copy, 4 steps, three runs) finds the peak before the loop:
MLX 14.2 GB up to the encoded picture, then 10.4 / 10.3 GB in the steps, the same with keep_encodings switched off and
with Progress not evaluating (245–250 s each). Fibo's prompt of an edit is encoded with the picture by the text
encoder and evaluated there, with the transformer already read: 8.8 + about 5.5 GB. The probe above with the prompt
first and the rest read after it peaked at 10.8 GB.
In the test app that order (prompt evaluated, text encoder dropped, then the rest read) changed nothing: 259 s, peak
13.25 GB (MLX 14.3 GB), swap 2.3 → 5.7 GB. The reason the probes stayed lower: they set mflux's TilingConfig
themselves, while the engine's low_ram() leaves Fibo untiled, because mflux marks the FLUX.2 VAE Fibo uses as
supports_implicit_tiling = False (each tile has its own GroupNorm statistics, which shifts colour between tiles). So
the app encodes the picture to edit in one piece, +3.9 GB (probe 1), next to the transformer: 8.8 + 3.9 + the
activations. The tiled numbers of the probes (10.7 GB) are not a fair target for the app: they would cost colour
seams.

## 7br. Picture to prompt: Qwen3-VL 2B in 16 and 8 bit on the Mac mini M4 16 GB (2026-11-07)

Qwen/Qwen3-VL-2B-Instruct (Apache-2.0, revision 8964489, SHA256 checked) in the diffusers runtime (transformers
5.18.0, MPS), asked for "one paragraph that an image generator can use as its prompt … the subject, the setting, the
light, the colours, the style and the camera", greedy, at most 300 new tokens, four pictures (the sepia photo of two
women, the lighthouse, a fox, the same two women in black and white); queue taken, swap 0.2 → 0.5 GB:

| Weights | load | per picture | tokens | peak footprint |
| --- | --- | --- | --- | --- |
| bfloat16 | 7.4 s | 7.8–11.7 s | 156–212 | 5.30 GB |
| int8 (optimum-quanto qint8, bf16 activations) | 10.4 s | 54.0–63.7 s | 159–190 | 5.58 GB |

8 bit saves only 1 GB at load (4.07 against 5.07 GB) and not at the peak, and is 5–6 times slower (quanto's int8
matmul on MPS); 16 bit stays. Every text ended on its own before 300 tokens (200 cut them in 7bn). Both describe the
two women, their clothes and the pose right in both photos; both still call the hedge of the black and white photo
"dark green", and the sepia one adds a "red brick wall". The texts read as prompts (light, colours, style, camera).

## 7bs. Phase 3: the recommended models, five runs each, against the target (2026-11-08, Mac mini M4 16 GB, test DMG)

Target (agreed 2026-11-06): the measured footprint at most 10 % above the app's plan, swap added at most 2 GB, five
runs per model. Test DMG 0.7.11 25b4894+ (built 2026-11-07 18:06), Hardware → Benchmark over CDP, the model's own
settings, 1024² (DreamShaper 512²), the benchmark prompt and seed. One model per queue lock (~/mini-queue): the test
app started under the lock and quit before it was freed; 30 s free between two models. 13 models, one per runtime and
plan kind (plans/BENCHMARK_PHASE3.md); the first seven ran 12:23–13:55, the other six 14:17–18:29.

| Model | Precision | Steps | s/step | First picture | Pictures 2–5 | Peak (first / 2–5) | Plan | Over plan | Swap added (max) | Target |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DreamShaper-8 | unet 16 bit | 25 | 0.51 | 24 s | 14–14 s | 3.80 / 3.78–3.79 GB | 3.6 GB | +6 % | 0.00 GB | met |
| Juggernaut-XL-v7 | unet 16 bit | 35 | 3.87 | 165 s | 140–140 s | 8.91 / 8.72–8.76 GB | 9.4 GB | -5 % | 2.03 GB | **missed** |
| FLUX.2-klein-4B | transformer 4 bit, text encoder 4 bit | 4 | 11.13 | 76 s | 50–50 s | 6.85 / 6.85–6.85 GB | 9.9 GB | -31 % | 0.00 GB | met |
| Z-Image-Turbo | transformer 8 bit, text encoder 8 bit | 9 | 17.49 | 214 s | 162–162 s | 12.03 / 8.87–8.87 GB | 11.9 GB | +1 % | 2.80 GB | **missed** |
| Anima-Turbo | transformer 16 bit, text encoder 16 bit | 10 | 5.94 | 98 s | 62–85 s | 9.36 / 9.42–9.99 GB | 9.1 GB | +10 % | 0.00 GB | met |
| SD3.5-Medium-repaired | transformer 8 bit, text encoder 3 8 bit | 40 | 8.10 | 365 s | 324–329 s | 9.72 / 5.94–5.94 GB | 10.4 GB | -7 % | 2.94 GB | **missed** |
| FLUX-3-Image-Klein-MLX-8bit | transformer 8 bit, text encoder 8 bit | 16 | 13.21 | 235 s | 216–218 s | 10.36 / 10.55–10.63 GB | 10 GB | +6 % | 0.63 GB | met |
| Fibo-2.0-Edit-Turbo-MLX | transformer 8 bit, text encoder 8 bit | 4 | 24.63 | 129 s | 124–132 s | 10.94 / 10.83–11.02 GB | 11.5 GB | -4 % | 1.61 GB | met |
| ERNIE-Image-Turbo | transformer 4 bit, text encoder 4 bit | 8 | 28.47 | 273 s | 232–235 s | 10.11 / 8.73–8.73 GB | 11.2 GB | -10 % | 0.42 GB | met |
| FLUX.2-klein-9B | transformer 4 bit, text encoder 8 bit | 4 | 27.52 | 174 s | 116–116 s | 11.41 / 8.96–9.01 GB | 9.8 GB | +16 % | 4.35 GB | **missed** |
| FLUX.1-schnell-Q8 | transformer 16 bit, streamed from the SSD, text encoder 2 8 bit | 4 | 29.25 | 134 s | 122–122 s | 8.92 / 8.91–8.93 GB | 12 GB | -26 % | 0.00 GB | met |
| NetaYume-Lumina-v4 | transformer 16 bit, text encoder 16 bit | 45 | 14.06 | 688 s | 677–680 s | 10.43 / 10.51–10.51 GB | 8.9 GB | +18 % | 2.39 GB | **missed** |
| GonzaLomo-Chroma | transformer 16 bit, streamed from the SSD, text encoder 8 bit | 30 | 53.66 | 1744 s | 1611–1623 s | 9.46 / 8.92–9.32 GB | 11.5 GB | -18 % | 2.29 GB | **missed** |

Swap added per run: Juggernaut 2.03 / 0 / 0 / 0 / 0, Z-Image 2.80 / 0 …, SD 3.5 2.94 / 0 …, klein 9B 4.35 / 0 …,
Chroma 2.29 / 0 …, NetaYume 2.22 / 2.39 / 2.07 / 1.78 / 1.85 GB. Swap in use at the start of a run stayed between 0.4
and 1.4 GB.

Result: 7 of 13 meet the target in all five runs (DreamShaper, klein 4B, Anima, FLUX 3 Klein, Fibo MLX, ERNIE,
FLUX.1 schnell Q8). Five miss it only with the first picture, the one that loads the model: Juggernaut, Z-Image,
SD 3.5 and Chroma by the swap (2.0–2.9 GB), klein 9B by both (11.41 GB, +16 %, 4.35 GB swap); pictures 2–5 of these
stay inside the plan with no swap. NetaYume misses it in every run: 10.4–10.5 GB against a plan of 8.9 (+17–18 %),
swap 1.8–2.4 GB, the same as 7bj (10.7 GB). The times per picture spread by less than 2 % after the first one
(Anima 62–85 s the exception), so five runs are enough to compare builds.

Queue state per model (owner of the lock before the run, other projects' processes before and after, from 14:17 on):
the lock was always held by the measurement itself; no okAI or LmAI job ran during any run. LM Studio was open at the
start of DreamShaper (idle), closed for all others. During Chroma an okAI job (LmAI-test/monitor/p1.command) queued
at 16:35 and waited on the lock without load; it started at 18:29:46, after the lock was freed (the count "others=3"
after Chroma is its waiting shell and tee). An LmAI job is scheduled for 2026-11-09 02:00 through the same lock.
FLUX 3 Klein's queue state after the run was taken at 14:15 (the first script stopped after the run; owner unchanged,
nothing else ran).

## 7bt. Phase 3 after the approved changes: before and after (2026-11-09, Mac mini M4 16 GB, test DMG)

Changes (approved 2026-11-08): the MLX engine saves the quantized model of Z-Image, ERNIE-Image and FLUX.2 [klein]
(`mlx_q<bits>`, as for Krea 2 and Ideogram 4); ComfyUI encodes with VulKara's node VulKaraEncodeAndFree, which frees
the text encoder before the sampler, when the plan counts it staged (SHARED, a picture, no LoRAs, no prompt padding,
not Fibo); Hardware → Benchmark has *New prompt per picture*. Test DMG 0.7.11 fc4da6a (built 2026-11-08 19:19); the
tests on the mini passed first (typecheck, vitest 398, i18n, clean, pytest 485 + 18 skipped). Same conditions as 7bs:
one model per queue lock, model defaults, 1024², the benchmark prompt and seed, five pictures. First pass 2026-11-09
03:09–03:34 and 06:41–10:31 (paused for an LmAI job), second pass 11:45–12:42. No other project's job ran during a
run (others=0, apart from NetaYume same prompt: 3 waiting shells of a queued okAI job); LM Studio closed throughout.
Raw data: plans/bench/2026-11-08_phase3_after.jsonl and 2026-11-09_phase3_cold.jsonl.

| Model | Case | First picture before → after | Peak first before → after | Swap first before → after | Pictures 2–5 before → after | Peak 2–5 before → after | Swap 2–5 after | Target |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FLUX.2-klein-4B | MLX, from mlx_q4 (2nd pass) | 76 → 62 s, 14.9 → 4.2 GB read | 6.85 → 6.91 GB | 0 → 0 | 50 → 51 s | 6.85 → 6.91 GB | 0 | met |
| Z-Image-Turbo | MLX, from mlx_q8 (2nd pass) | 214 → 188 s, 30.5 → 10.1 GB read | 12.03 → 11.69 GB | 2.80 → 2.71 GB | 162 → 165 s | 8.87 → 8.89 GB | 0 | **missed** by the first picture's swap |
| ERNIE-Image-Turbo | MLX, from mlx_q4 (2nd pass) | 273 → 252 s, 21.6 → 6.2 GB read | 10.11 → 8.97 GB | 0.42 → 0 | 232–235 → 238 s | 8.73 → 8.87–8.98 GB | 0 | met |
| NetaYume-Lumina-v4 | ComfyUI, same prompt | 688 → 692 s | 10.43 → 9.22 GB | 2.22 → 0 | 677–680 → 683–684 s | 10.51 → 9.18–9.22 GB | ≤ 0.25 GB | **met** (plan 8.9, +4 %) |
| NetaYume-Lumina-v4 | ComfyUI, new prompt per picture | – → 692 s | – → 9.22 GB | – → 0 | – → 683–687 s | – → 9.21–9.22 GB | ≤ 0.38 GB | met |
| Anima-Turbo | ComfyUI, same prompt | 98 → 100 s | 9.36 → 8.63 GB | 0 → 0 | 62–85 → 64–87 s | 9.42–9.99 → 8.06–10.02 GB | 0 | met (+10 %, at the limit as in 7bs) |
| Anima-Turbo | ComfyUI, new prompt per picture | – → 101 s | – → 9.78 GB | – → 0 | – → 63–86 s | – → 8.70–10.01 GB | 0 | met (+10 %) |
| FLUX.2-klein-9B | Diffusers, same prompt | 174 → 140 s | 11.41 → 10.13 GB | 4.35 → 0 | 116 → 116 s | 8.96–9.01 → 8.99–9.04 GB | 0 | met, see below |
| FLUX.2-klein-9B | Diffusers, new prompt per picture | – → 172 s | – → 11.64 GB | – → 4.33 GB | – → 165–169 s | – → 8.98–12.41 GB | 3.59–5.34 GB | **missed** in every picture |

The first pass wrote `mlx_q4`/`mlx_q8` during its first picture (Z-Image Turbo 10 GB in 16 s, klein 4B 4.3 GB): its
first pictures (klein 4B 80.5 s, Z-Image 228.5 s, ERNIE 281.5 s) were that one-time cost; the table takes the first
picture of the second pass, the first start reading only the saved files. Disk: 4.3 + 10 GB + ERNIE's mlx_q4 more.

NetaYume: the picture at the same prompt and seed is identical pixel for pixel before (CLIPLoader, 2026-11-08 15:26) and
after (VulKaraEncodeAndFree, 2026-11-09 08:37). ComfyUI still reads about 10 GB per picture: it drops the model after
each picture below --cache-ram, unchanged.

FLUX.2 [klein] 9B: the first pass's better first picture was not a change of ours: its encodings came from the prompt
cache on disk (log: "prompt embeddings from the prompt cache"), filled by 7bs, so the text encoder never loaded; in
7bs it did. With a new prompt per picture (the real case for a user) every picture loads the text encoder (Qwen3 8B,
8 bit, 34–37 s, about 14.5 GB read per picture) and misses the target: peak up to 12.41 GB against 9.8 planned
(+27 %), 3.6–5.3 GB swap per picture, 165–172 s instead of 116 s. The footprint sampled every second
(~/vk_test/klein9b_probe_fresh.log on the mini): while the text encoder loads the engine grows to 10–11 GB and the swap
jumps by up to 3 GB; after it is freed the engine drops to 2–3.5 GB, loads the transformer and then holds 11–12 GB
while generating, where the same prompt holds 9.0 GB. Why 2–3 GB more stay while generating after a text encoder load
is open (not measured further).

Result against the target: NetaYume now meets it in every run (was +17–18 % and 2.4 GB swap); ERNIE's first picture
no longer swaps; klein 4B, Z-Image and ERNIE load 13–26 s faster from a third of the data. Still missed: Z-Image's
first picture by its swap (2.71 GB): the saved model loads transformer and text encoder together (engine log "after
loaded: 11.0 GB in use", MLX peak 12.0 GB in the first picture) and frees the text encoder only before denoising,
although the encodings came from the prompt cache; and klein 9B whenever the prompt is new, which 7bs did not show (its pictures 2–5 reused the prompt).

## 7bu. Z-Image without its text encoder, klein 9B probe (2026-11-09, Mac mini M4 16 GB, test DMG 8aaf6c1)

Approved after 7bt: (A) the MLX engine no longer reads the text encoder of a staged model (Z-Image, Krea 2, Ideogram 4)
when the prompt's encodings are in the prompt cache on disk (the weights stay lazy until materialize, which now
skips it; a new prompt loads the model again, as after a freed text encoder); (B) a probe for FLUX.2 [klein] 9B: the
Diffusers engine logs what PyTorch and Metal hold after the text encoder is freed, after the denoiser is loaded and
after each picture (and empties Metal's cache once more after loading the denoiser). Tests on the mini first (typecheck,
vitest 398, i18n, clean, pytest 485 + 18 skipped), then one model per lock, 13:07–13:37, others=0, LM Studio closed.
Raw data: plans/bench/2026-11-09_phase3_fix.jsonl.

| Model | Case | First picture | Peak first | Swap first | Pictures 2–5 | Peak 2–5 | Swap 2–5 | Target |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Z-Image-Turbo | MLX, mlx_q8, prompt cached | 214 (7bs) → 188 (7bt) → 180.5 s | 12.03 → 11.69 → 8.97 GB | 2.80 → 2.71 → 0 GB | 165 s | 8.91–8.97 GB | 0 | **met** |
| FLUX.2-klein-9B | Diffusers, new prompt per picture | 172 → 175 s | 11.64 → 11.76 GB | 4.33 → 5.32 GB | 164–169 s | 12.41–12.42 GB | 4.5–5.2 GB | missed |

Z-Image's log: "text encoder not read (prompt encoded before)", 6.7 GB in use after loading (11.0 before), 6.5 GB read
from disk instead of 10.1.

klein 9B, engine log per picture (the same in all five): after the text encoder is freed 0.2 GB in tensors, Metal held
11.4 GB and still 2.4 GB once its cache was emptied (1.3 GB at the first picture); after the transformer loaded 5.3 GB
in tensors, 5.6 GB held by Metal. The process footprint at the same times (sampled every second): 3.9 GB right after
the text encoder (Metal 1.3 GB, so about 2.6 GB outside Metal), 9.3–9.7 GB after the transformer (Metal 5.6 GB, about
4 GB outside), 11 GB while generating. With the same prompt (7bt) it holds 9.0 GB while generating. So the 2–3 GB that
stay after a new prompt are memory of the process outside Metal's tensors: about 1–2 GB that Metal keeps although
empty_cache ran, the rest CPU memory left from loading the text encoder (Qwen3 8B, 8 bit, about 8.7 GB read per
picture). Which allocation holds the CPU part is open. Emptying Metal's cache after loading the transformer changed
nothing (5.6 GB before and after).

## 7bv. Diffusers with a new prompt: the cause, two attempts that did not help, the GGUF denoiser read mapped (2026-11-09, Mac mini M4 16 GB)

Follow-up of 7bu (FLUX.2 [klein] 9B missed the target with a new prompt per picture). Each step measured on the mini
through the queue lock, tests passed first each time; raw data plans/bench/2026-11-09_phase3_{b2,b1,c}.jsonl, the
probe plans/bench/reload_probe.py.

1. **Heap given back** (malloc_zone_pressure_relief after the text encoder, the denoiser and each picture): 0.0 GB
   given back each time, klein 9B unchanged (peak 11.4–12.4 GB, swap 2.8–5.2 GB). Taken out again.
2. **Text encoder in a short process of its own** (the embeddings handed over through the prompt cache; its whole
   memory goes back when it ends): klein 9B peak 11.8–12.1 GB, swap 4.0–5.1 GB, 166–174 s, the same as without.
   The footprint showed why: the engine held 0.7 GB while the other process encoded, and 10–11 GB again while
   generating once it had loaded the transformer. Taken out again.
3. **Probe, the denoiser alone** (the engine's LoadedModel: load, then the transformer out and in three times, no
   text encoder). After loading the 4 bit GGUF copy of klein 9B's transformer the process held 8.8 GB with 5.6 GB in
   Metal, and kept 8.8 GB with the transformer out again (Metal 0.2 GB, no CPU tensor or numpy array alive, malloc gave
   back 0.0 GB). `footprint` at that point: 3.2 GB MALLOC_LARGE, 2.2 GB IOAccelerator. diffusers 0.41 reads a GGUF file
   with a copy of every tensor (`load_gguf_checkpoint`: `torch.from_numpy(tensor.data.copy())`); read as views of the
   mapped file instead (streaming._gguf_mapped, used for unpacking since 7bp) the process held 5.75 GB after loading
   and fell back to 0.7–2.7 GB with the transformer out.
4. **Change kept (2102d25): every GGUF denoiser copy loads mapped.** Measured with a new prompt per picture:

| Model | Peak before (B1 build) → after | Swap per picture before → after | Time per picture before → after | Generating (engine, sampled) |
| --- | --- | --- | --- | --- |
| FLUX.2-klein-9B | 11.78–12.05 → 11.41–12.42 GB | 3.99–5.13 → 3.92–5.40 GB | 166–174 → 158–170 s | 11–12 → 10 GB |
| SD3.5-Medium-repaired | 11.08–11.12 → 9.72–10.77 GB | 3.97–4.61 → 3.48–4.14 GB | 364–375 → 359–373 s | – |

The pictures came out as before (looked at: klein 9B and SD 3.5, full picture). klein 9B is about 6 s faster per
picture and holds about 1–2 GB less while generating; SD 3.5's peak is now inside its plan (10.4 GB, at most +4 %).
What stays: loading the text encoder for a new prompt. Qwen3 8B in 8 bit (klein 9B) alone took the separate process
to 11 GB (step 2), more than the 9.8 GB the plan counts for the stage, and macOS swapped while it loaded (3.6–6 GB in
use for a few seconds, then back to about 1.7 GB). This is the peak the benchmark shows for klein 9B; with the same
prompt (encodings from the prompt cache) klein 9B meets the target (7bt). Not changed further in Phase 3: the plan's
count of the text encoder stage and how its 8 bit copy loads are a separate task (plans/RELEASE_TODO.md).

## 7bw. The staged text encoder of FLUX.2 [klein] 9B: three ways to load its 8 bit copy (2026-11-09, Mac mini M4 16 GB)

Probe plans/bench/te_probe.py (the engine's LoadedModel, the text encoder pipeline as encode() loads it, two new
prompts, footprint sampled every 0.05 s), one run per way through the queue lock:

| Way | Load | Peak | Tensors / Metal loaded | Left in the process once freed |
| --- | --- | --- | --- | --- |
| today: load_file into CPU memory, requantize on the CPU, then to the GPU | 26–27 s | 11.17 GB | 9.50 / 10.08 GB | 4.90–4.92 GB (Metal 0.08) |
| the file read as views of a copy-on-write mapping | 32–39 s | 11.16 GB | 9.50 / 10.08 GB | 4.91–4.92 GB |
| load_file and requantize straight on the GPU | 245–248 s | 20.51–20.56 GB | 9.50 / 13.43 GB | 2.83–5.91 GB |

Qwen3 8B in 8 bit holds 9.5 GB of tensors itself, so the stage peaks at about 11 GB on any way (the plan counts 9.8 for
the whole stage). The 4.9 GB left after freeing do not come from reading the file (mapped, the same is left): they
stay from rebuilding the model with optimum-quanto on the CPU. That library is deprecated in diffusers (removed with
1.0, plans/RELEASE_TODO.md); replacing it for text encoders is the place to fix this. Nothing changed in the app.

## 7bx. Fibo 2.0 Edit (MLX) on 16 GB: the transformer read after the text encoder and the picture (2026-11-09, Mac mini M4)

The idea deferred in 7bq, tried (b9f76b7): staged, the transformer stays lazy at loading and DropTextEncoder reads it
once the text encoder is dropped; the encoded picture to edit is evaluated at once (mflux left it lazy, computed only
at the first step beside the transformer). Hardware → Benchmark over CDP with an input picture
(plans/bench/bench_edit.mjs): Fibo-2.0-Edit-Turbo-MLX, 4 steps, guidance 1, "the same place on a snowy winter evening",
seeds 11-13, one model per queue lock, others=0; before with the test DMG of 4fa5185, after with b9f76b7.

| | Engine peak | Swap added | Time per picture | App peak |
| --- | --- | --- | --- | --- |
| before | 13.53–13.56 GB | 2.76–3.29 GB | 253–258 s | 12.9–13.9 GB |
| after | 11.02–11.05 GB | 1.60–1.96 GB | 254–274 s | 11.2–11.9 GB |

The pictures are identical pixel for pixel (all three seeds). The plan (14.4 GB) still counts the old peak; the
engine now stays 3.4 GB under it, and the swap is inside the target (at most 2 GB). The MLX log after a picture:
8.8 GB in use, peak 10.3 GB.

## 8. Earlier references (from the user guide and the changelog)

- Training on the M2 (2025–26): SDXL about 2.5 s per step at 768 px, FLUX.2 [klein] 4B about 15 s, 9B about 30 s,
  Krea 2 about 45 s per step.
- Chroma1-Flash on the M2 with 24 GB: about 7 minutes per picture at 1024 px with its 12 steps and no guidance, about
  52 with guidance (two passes per step); float16 instead of bfloat16 on M1/M2 is about 40 % faster.
- ComfyUI runtime install into an empty folder (2026-10-10): uv 0.12.23 pinned, ComfyUI 0.38.0 and ComfyUI-GGUF
  checked by content hash, 85 packages, a few minutes on a 5 MB/s download.
