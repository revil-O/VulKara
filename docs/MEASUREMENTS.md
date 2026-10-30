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
the plan is not changed yet.

## 8. Earlier references (from the user guide and the changelog)

- Training on the M2 (2025–26): SDXL about 2.5 s per step at 768 px, FLUX.2 [klein] 4B about 15 s, 9B about 30 s,
  Krea 2 about 45 s per step.
- Chroma1-Flash on the M2 with 24 GB: about 7 minutes per picture at 1024 px with its 12 steps and no guidance, about
  52 with guidance (two passes per step); float16 instead of bfloat16 on M1/M2 is about 40 % faster.
- ComfyUI runtime install into an empty folder (2026-10-10): uv 0.12.23 pinned, ComfyUI 0.38.0 and ComfyUI-GGUF
  checked by content hash, 85 packages, a few minutes on a 5 MB/s download.
