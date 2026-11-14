// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The benchmarks page of the website (site/benchmarks/, written by tools/build_site_pages.mjs): the measurements of
// docs/MEASUREMENTS.md as charts. The figures below are copied from there by hand (section in `ref`); a new
// measurement goes into MEASUREMENTS.md first, then here. The charts are plain HTML and CSS (no script needed), a
// tooltip comes from site/bench.js, and every chart has its table.

import { createHash } from 'node:crypto'

const MEASURED = 'Apple M2, 24 GB'

// before → after, per step and the engine's peak (MEASUREMENTS 7m, 7n, 7o, 7ab, 7ac, 7ad, 7ae, 7ag, 7ai; gb left out where not measured)
const CHANGES = [
  { ref: '7n', model: 'SD 1.5 (epiCPhotoGasm), 512 px', runtime: 'Diffusers', step: [1.55, 0.72], gb: [7.3, 3.7], why: 'attention heads padded to a size the fused kernel takes' },
  { ref: '7n', model: 'SD 1.5 (epiCPhotoGasm), 1024 px', runtime: 'Diffusers', step: [9.4, 4.8], gb: [9.8, 5.0], why: 'padded heads, no attention slicing' },
  { ref: '7n', model: 'SDXL (JuggernautXL), 2048 px', runtime: 'Diffusers', step: [111, 28], gb: [17.4, 12.1], why: 'no attention slicing on MPS' },
  { ref: '7n', model: 'SDXL (JuggernautXL), 1024 px', runtime: 'Diffusers', step: [4.9, 5.0], gb: [9.0, 8.8], why: 'unchanged: its heads were fused already' },
  { ref: '7m', model: 'FLUX.1 dev, 1024 px', runtime: 'MLX, 4 bit', step: [175, 46], gb: [18.1, 13.0], why: 'decoded in tiles when the free memory is short' },
  { ref: '7m', model: 'Krea 2 Turbo, 1024 px', runtime: 'MLX, 4 bit', step: [212.5, 81.5], gb: [18.2, 16.1], range: ['211–214', '78–85', '18.2', '15.6–16.6'], why: 'decoded in tiles when the free memory is short' },
  { ref: '7o', model: 'Wan 2.2 I2V 14B, 832×480, 1 s', runtime: 'ComfyUI, Q4_K', step: [210.5, 148.3], gb: [12.7, 12.9], why: 'PyTorch attention instead of sub-quadratic' },
  { ref: '7o', model: 'NetaYume v4 (Lumina 2), 1024 px', runtime: 'ComfyUI', step: [32.45, 28.7], gb: [15.85, 14.7], range: ['31.9–33.0', '28.7', '15.5–16.2', '14.1–15.3'], why: 'PyTorch attention instead of sub-quadratic' },
  { ref: '7o', model: 'Pony V7 Q8_0 (AuraFlow), 1024 px', runtime: 'ComfyUI, GGUF', step: [46.05, 46.7], gb: [15.35, 13.0], range: ['46.0–46.1', '46.7', '14.8–15.9', '12.3–13.7'], why: 'PyTorch attention instead of sub-quadratic' },
  { ref: '7o', model: 'Anima-Turbo, 1024 px', runtime: 'ComfyUI', step: [12.1, 11.8], gb: [10.0, 10.0], why: 'PyTorch attention instead of sub-quadratic' },
  { ref: '7ae', model: 'NetaYume v4 (Lumina 2), 16 GB (8 GB wired)', runtime: 'ComfyUI', step: [30.6, 28.3], gb: [10.6, 8.7], why: 'the text encoder dropped after encoding' },
  { ref: '7ae', model: 'Pony V7 Q8_0, 16 GB (8 GB wired)', runtime: 'ComfyUI, GGUF', step: [64.7, 46.9], gb: [6.6, 9.7], why: 'whole in memory without its text encoder instead of LOW_VRAM' },
  { ref: '7ad', model: 'FLUX.2 [klein] 9B streamed, 16 GB plan, the plan counts its blocks', runtime: 'Diffusers', step: [50.4, 54.3], gb: [14.3, 10.6], why: 'blocks in flight counted at their size: 2 instead of 9 blocks kept' },
  { ref: '7ac', model: 'FLUX.2 [klein] 9B streamed, 16 GB plan, busy GPU', runtime: 'Diffusers', step: [67.0, 50.4], gb: [19.6, 14.3], why: 'at most two streamed blocks wait on the GPU' },
  { ref: '7ag', model: 'MOSS-Image (int8 file), 1024 px, CFG 3', runtime: 'ComfyUI', step: [72.8, 48.9], why: 'float16 instead of bfloat16, also for its int8 layers' },
  { ref: '7ai', model: 'Fibo 2.0 Edit Turbo (int8 file), edit at 1024 px', runtime: 'ComfyUI', step: [110.7, 69.3], why: 'float16 instead of bfloat16, the same picture (PSNR 47 dB)' },
  { ref: '7ab', model: 'MiaoMiao RealSkin (Anima), 1024×1536, CFG 5', runtime: 'ComfyUI', step: [123.5, 92.3], range: ['117–130', '92.3'], why: 'float16 instead of bfloat16, which MPS computes at half the speed' },
  { ref: '7ab', model: 'MiaoMiao RealSkin (Anima), 512×768, CFG 5', runtime: 'ComfyUI', step: [21.2, 18.1], why: 'float16 instead of bfloat16' },
  { ref: '7bb', model: 'AuraFlow v0.3, 1024 px, 24 GB', runtime: 'Diffusers', step: [79.3, 46.3], gb: [18.7, 12.8], range: ['77.6–81.0', '46.3'], why: '16 bit only with 2 GB of room under the budget: 8 bit instead of weights read again every step' },
  { ref: '7bc', model: 'Z-Image Turbo, 1024 px, Mac mini M4 16 GB', runtime: 'MLX, 8 bit', step: [121.5, 17.8], gb: [24.8, 12.0], range: ['117–126', '17.8', '23.9–25.6', '12.0'], why: 'the weights read part by part after loading, not all at once in the first step' },
  { ref: '7bc', model: 'FLUX.2 [klein] 4B, 1024 px, Mac mini M4 16 GB', runtime: 'MLX, 4 bit', step: [16.5, 11.3], gb: [11.4, 7.0], range: ['16.3–16.7', '11.3'], why: 'the weights read part by part after loading' },
  { ref: '7be', model: 'FLUX.1 dev, 1024 px, Mac mini M4 16 GB, 28 steps → Turbo-Alpha 8 steps (s per picture)', runtime: 'Diffusers, 4 bit', step: [664, 258], gb: [9.6, 9.6], why: 'a step-distilling LoRA: 8 steps at 1.34 times the time each' },
  { ref: '7be', model: 'FLUX.1 dev, 768 px, Mac mini M4 16 GB', runtime: 'Diffusers', step: [34.4, 18.9], gb: [10.1, 9.95], why: 'transformer in 4 bit in memory instead of 16 bit streamed from the SSD' },
  { ref: '7be', model: 'FLUX.2 [klein] 9B, 768 px, Mac mini M4 16 GB', runtime: 'Diffusers', step: [22.3, 17.0], gb: [10.7, 9.0], why: 'transformer in 4 bit in memory instead of 16 bit streamed from the SSD' },
  { ref: '7bf', model: 'Inpainting, remove (empty prompt), FLUX.1 dev, 1024 px, Mac mini M4 16 GB (s per picture)', runtime: 'Diffusers, 4 bit', step: [832, 491], gb: [10.8, 11.5], why: 'LaMa fills the part first, the model refines 40 % of the steps; nothing invented there any more' },
  { ref: '7bd', model: 'Krea 2 Turbo, 1024 px, Mac mini M4 16 GB (MLX peak)', runtime: 'MLX, 4 bit', step: [41.3, 43.8], gb: [14.3, 11.3], why: 'the picture decoded in 256 px tiles instead of 512' },
  { ref: '7bd', model: 'Qwen-Image 2.1, 1024 px, Mac mini M4 16 GB', runtime: 'Diffusers, 8 bit', step: [42.4, 43.9], gb: [18.7, 12.3], range: ['42.2–42.5', '43.9', '18.6–20.2', '12.2–12.4'], why: 'the staged text encoder let go after encoding, the one-time quantization in a process of its own' },
  { ref: '7bt', model: 'NetaYume v4 (Lumina 2), 1024 px, Mac mini M4 16 GB, pictures 2–5 (s per picture)', runtime: 'ComfyUI', step: [679, 684], gb: [10.51, 9.22], range: ['677–680', '683–684', '10.51', '9.18–9.22'], why: 'the text encoder freed before the sampler (VulKaraEncodeAndFree), the same picture' },
  { ref: '7bt', model: 'FLUX.2 [klein] 4B, first picture, Mac mini M4 16 GB (s per picture)', runtime: 'MLX, 4 bit', step: [76, 62], gb: [6.85, 6.91], why: 'its 4 bit copy saved once next to it: 4.2 instead of 14.9 GB read' },
  { ref: '7bt', model: 'ERNIE-Image Turbo, first picture, Mac mini M4 16 GB (s per picture)', runtime: 'MLX, 4 bit', step: [273, 252], gb: [10.11, 8.97], why: 'its 4 bit copy saved once: 6.2 instead of 21.6 GB read, no swap' },
  { ref: '7bu', model: 'Z-Image Turbo, first picture, Mac mini M4 16 GB (s per picture)', runtime: 'MLX, 8 bit', step: [214, 180.5], gb: [12.03, 8.97], why: 'its 8 bit copy saved once, and a prompt encoded before does not read the text encoder' },
  { ref: '7bv', model: 'SD 3.5 Medium, new prompt per picture, Mac mini M4 16 GB (s per picture)', runtime: 'Diffusers, 8 bit', step: [365, 361], gb: [11.1, 10.2], range: ['364–375', '359–373', '11.08–11.12', '9.72–10.77'], why: 'its GGUF copy read as views of the file instead of a copy of every tensor' },
  { ref: '7bx', model: 'Fibo 2.0 Edit Turbo, edit at 1024 px, Mac mini M4 16 GB (s per picture)', runtime: 'MLX, 8 bit', step: [254, 263], gb: [13.55, 11.03], range: ['253–258', '254–274', '13.53–13.56', '11.02–11.05'], why: 'the transformer read after the text encoder and the picture to edit, the same pictures' },
]

// the memory plan against the engine's measured peak, 1024 px (MEASUREMENTS 7m): [model, runtime, used, planned]
const PLAN = [
  ['Z-Image Turbo', 'MLX, 8 bit', 16.8, 14.9],
  ['FLUX.2 [klein] 4B', 'MLX, 8 bit', 13.3, 12.5],
  ['FLUX.2 [klein] 9B', 'MLX, 4 bit', 14.3, 14.5],
  ['Krea 2 Turbo', 'MLX, 4 bit', 18.2, 14.7],
  ['ERNIE-Image Turbo', 'MLX, 4 bit', 13.7, 11.2],
  ['FLUX 3 Image Klein', 'MLX, 6 bit', 13.1, 12.5],
  ['FLUX.1 dev', 'MLX, 4 bit', 18.1, 13.9],
  ['JuggernautXL v7', 'Diffusers, 16 bit', 8.8, 9.4],
  ['epiCPhotoGasm (SD 1.5)', 'Diffusers, 16 bit', 8.8, 3.9],
  ['SD3.5 Medium', 'Diffusers', 14.0, 14.7],
  ['Chroma1 Flash', 'Diffusers, 8 bit', 11.9, 15.5],
  ['Qwen-Image 2.1', 'Diffusers, streamed', 15.7, 13.0],
  ['AuraFlow v0.3', 'Diffusers, 8 bit', 14.6, 13.3],
]

// the plans brought to the measurements (MEASUREMENTS 7p, 7ag, 7ai, 7aj, 7an; used = 7n for SD 1.5, the middle of 7o's range for ComfyUI)
const PLAN_AFTER = [
  ['epiCPhotoGasm (SD 1.5), 512 px', 'Diffusers, 16 bit', 3.7, 3.6],
  ['epiCPhotoGasm (SD 1.5), 1024 px', 'Diffusers, 16 bit', 5.0, 5.0],
  ['FLUX.2 [klein] 4B, 1024 px', 'Diffusers, 8 bit (16 GB plan)', 9.5, 9.4],
  ['Juggernaut XL (SDXL), 1024 px', 'Diffusers, 16 bit', 9.4, 8.8],
  ['Juggernaut XL + ControlNet Union, 1024 px', 'Diffusers, 16 bit: the ControlNet counted (7as; 9.4 planned before)', 12.65, 12.2],
  ['Juggernaut XL + ControlNet Union, 1024 px, 16 GB plan', 'Diffusers, ControlNet in 8 bit: refused before', 11.5, 11.6],
  ['Anima-Turbo', 'ComfyUI', 10.0, 9.1],
  ['NetaYume v4 (Lumina 2)', 'ComfyUI', 14.7, 14.1],
  ['Pony V7 Q8_0 (AuraFlow)', 'ComfyUI, GGUF', 13.0, 13.9],
  ['Qwen-Image 2.1, streamed (16 GB plan)', 'Diffusers, kept blocks counted (7w)', 12.1, 11.8],
  ['MOSS-Image, 16 GB (8 GB wired)', 'ComfyUI, int8; encoder and model apart (7ag)', 8.4, 9.2],
  ['NetaYume v4 (Lumina 2), 16 GB (8 GB wired)', 'ComfyUI; encoder and model apart (7ae, 7ag)', 8.7, 8.9],
  ['Fibo 2.0 Edit Turbo, edit', 'ComfyUI, int8; its activations counted (7ai)', 14.8, 14.6],
  ['Fibo 2.0 Edit Turbo, edit, 16 GB (8 GB wired)', 'MLX, 8 bit; text encoder dropped first (7aj)', 11.0, 11.5],
  ['Fibo 2.0 Dev, edit', 'ComfyUI, int8; guidance, two passes per step (7an)', 15.0, 14.6],
  ['Ideogram 4, 768 px', 'MLX, 4 bit · 94–100 s/step (7bb)', 17.0, 17.2],
  ['Qwen-Image 2.1, 1024 px', 'Diffusers, streamed · 3.1 GB above its plan (7bb)', 17.5, 14.4],
  ['Krea 2 Turbo, 768 px', 'MLX, 4 bit · 2.2 GB above its plan (7bb)', 15.6, 13.4],
  ['AuraFlow v0.3, 1024 px, 24 GB plan', 'Diffusers, 16 bit · 72 s/step, the 8 bit plan of 16 GB does 44 (7bb)', 18.7, 18.7],
  ['AuraFlow v0.3, 1024 px, 24 GB, 2 GB margin for 16 bit', 'Diffusers, 8 bit · 46 s/step (7bb)', 12.8, 13.3],
  ['FLUX 3 Image Klein, 768 px, with the upsampler', 'MLX, 6 bit · the upsampler adds 2.8 GB (7bb)', 14.7, 12.5],
  ['NetaYume v4 (Lumina 2), 768 px', 'ComfyUI (7bb)', 15.3, 14.1],
]

// 0.7.11 on the Mac mini M4, 16 GB, 1024 px (MEASUREMENTS 7af, 7ah)
const PLAN_M4 = [
  ['CyberRealistic Pony v18 (SDXL)', 'Diffusers, 16 bit · 3.8 s/step', 8.8, 9.4],
  ['NetaYume v4 (Lumina 2)', 'ComfyUI · 13.8 s/step', 10.8, 11.6],
  ['MiaoMiao RealSkin (Anima)', 'ComfyUI, float16 · 11.7 s/step', 7.0, 9.1],
  ['FLUX.2 [klein] 9B', 'Diffusers, streamed · 26.4 s/step', 10.5, 11.5],
  ['MOSS-Image (test build)', 'ComfyUI, int8 · 37.0 s/step', 9.1, 9.2],
  ['ERNIE-Image Turbo (test build 2026-11-02)', 'MLX, 4 bit · 28.0 s/step', 8.7, 11.2],
  ['Juggernaut XL v7 (SDXL, test build 2026-11-02)', 'Diffusers, 16 bit · 3.85 s/step', 8.9, 9.4],
  ['Fibo 2.0 Edit Turbo, 768 px (test build 2026-11-02)', 'MLX, 8 bit · 28.5 s/step, 6.3 GB short: 18.9 GB read back from the swap', 10.2, 10.8],
  ['Juggernaut XL v7 + ControlNet Canny (test build 2026-11-03)', 'Diffusers, 16 bit · 5.97 s/step (7bc)', 11.6, 11.5],
  ['Fibo 2.0 Edit Turbo + anime LoRA (test build 2026-11-03)', 'MLX, 8 bit · 29.6 s/step (7bc)', 11.7, 11.5],
  ['ERNIE-Image Turbo with the enhancer (test build 2026-11-03)', 'MLX, 4 bit · 29.2 s/step (7bc)', 9.5, 11.2],
  ['FLUX.2 [klein] 4B (test build 2026-11-03)', 'MLX, 4 bit · 16.3 s/step (7bc)', 11.4, 9.9],
  ['GonzaLomo Chroma, 768 px (test build 2026-11-03)', 'Diffusers, streamed · 38.8 s/step (7bc)', 12.4, 11.5],
  ['FLUX.1 Fill [dev], new prompt (test build 2026-11-05)', 'Diffusers, 4 bit GGUF · 254 s per picture, 8 steps (7bf)', 10.9, 10.0],
  ['Fibo 2.0 Edit Turbo, masked edit (test build 2026-11-05)', 'MLX, 8 bit · 250 s; the picture goes along as context tokens (7bg)', 13.5, 14.4],
  ['Fibo 2.0 Edit Turbo, edit on a quiet Mac (test build 2026-11-06, before 7bx)', 'MLX, 8 bit · 252 s; the picture to edit encoded whole, as its VAE needs (7bq)', 13.53, 14.4],
  ['Restore, repair with the consistency LoRA, klein 4B', 'Diffusers · 116–130 s (7bh)', 11.7, 12.9],
  ['Restore, repair, klein 9B', 'Diffusers · 238 s; the reference tokens counted, 9.8 planned before (7bh)', 12.5, 12.6],
  ['Image to image, Keep the picture, klein 4B', 'Diffusers · 108 s (7bi)', 10.1, 12.9],
  ['Z-Image Turbo, Electron 44.10.2 and new runtimes', 'Diffusers · 191 s (7bj)', 12.0, 11.9],
  ['FLUX 3 Image Klein, new runtimes', 'MLX, 8 bit · 74 s (7bj)', 10.6, 10.0],
  ['FLUX.1 [schnell] 8 bit, streamed, new runtimes', 'Diffusers · 248 s, 98–106 GB read per picture (7bj)', 15.9, 12.0],
  ['Anima Turbo, ComfyUI 0.44.0', 'ComfyUI · 103 s (7bj)', 8.8, 9.1],
  ['MOSS-Image 8-step DMD, ComfyUI 0.44.0', 'ComfyUI · 209 s (7bj)', 9.1, 9.2],
  ['NetaYume v4, ComfyUI 0.44.0, 20 steps', 'ComfyUI · 322 s; planned 11.6 in 0.7.11 (7bj)', 10.7, 8.9],
  ['FLUX.2 [klein] 9B, 768 px, GGUF copy instead of Quanto', 'Diffusers, 4 bit · 17.6 s/step (7bl)', 9.0, 9.8],
  ['FLUX.1 dev + Turbo-Alpha, GGUF copy instead of Quanto', 'Diffusers, 4 bit · 30.2 s/step (7bl)', 10.9, 10.9],
  ['SD 3.5 Medium, GGUF copy', 'Diffusers, 8 bit · 8.0 s/step (7bl)', 4.8, 10.4],
  ['Qwen-Image 2.1, GGUF copy instead of Quanto', 'Diffusers, 8 bit · 21.5 s/step, guidance 1 (7bl)', 12.3, 11.9],
  ['Juggernaut XL + ControlNet Canny, ControlNet by optimum-quanto', 'Diffusers · 6.0 s/step (7bl)', 11.2, 11.5],
  ['DreamShaper 8, 512 px, pictures 2–5 (Phase 3)', 'Diffusers, 16 bit · 14 s (7bs)', 3.79, 3.6],
  ['Juggernaut XL v7, pictures 2–5 (Phase 3)', 'Diffusers, 16 bit · 140 s (7bs)', 8.76, 9.4],
  ['SD 3.5 Medium, pictures 2–5 (Phase 3)', 'Diffusers, 8 bit · 327 s (7bs)', 5.94, 10.4],
  ['FLUX 3 Image Klein, pictures 2–5 (Phase 3)', 'MLX, 8 bit · 217 s (7bs)', 10.63, 10.0],
  ['FLUX.1 [schnell] Q8, streamed, pictures 2–5 (Phase 3)', 'Diffusers · 122 s (7bs)', 8.93, 12.0],
  ['GonzaLomo Chroma, streamed, pictures 2–5 (Phase 3)', 'Diffusers · 1617 s (7bs)', 9.32, 11.5],
  ['FLUX.2 [klein] 4B, pictures 2–5 (Phase 3, after)', 'MLX, 4 bit · 51 s (7bt)', 6.91, 9.9],
  ['ERNIE-Image Turbo, pictures 2–5 (Phase 3, after)', 'MLX, 4 bit · 238 s (7bt)', 8.98, 11.2],
  ['Anima Turbo, pictures 2–5 (Phase 3, after)', 'ComfyUI · 64–87 s (7bt)', 10.02, 9.1],
  ['NetaYume v4, pictures 2–5 (Phase 3, after)', 'ComfyUI · 683 s (7bt)', 9.22, 8.9],
  ['Z-Image Turbo, first picture (Phase 3, after)', 'MLX, 8 bit · 180 s (7bu)', 8.97, 11.9],
  ['FLUX.2 [klein] 9B, same prompt (Phase 3, after)', 'Diffusers · 116 s (7bt)', 9.04, 9.8],
  ['FLUX.2 [klein] 9B, new prompt per picture', 'Diffusers · 158–170 s; the 8 bit text encoder alone takes 11 GB (7bv, 7bw)', 12.42, 9.8],
  ['Fibo 2.0 Edit Turbo, edit (Phase 3, after)', 'MLX, 8 bit · 254–274 s (7bx)', 11.03, 14.4],
  ['AI Canvas Extend, FLUX.2 [klein] 4B + outpaint LoRA', 'Diffusers · 104–126 s per picture (7cg)', 10.2, 11.6],
]

// work done once and kept, and a stop that waited (MEASUREMENTS 7r, 7s, 7t, 7u, 7x, 7y, 7z): before, after, unit
const ONCE = [
  { ref: '7s', what: 'Qwen-Image 2.1, whole picture', sub: '16 GB plan: text encoder quantized to 4 bit, then from the quantized cache', a: 10971, b: 221, unit: 's' },
  { ref: '7s', what: 'Qwen-Image 2.1, memory at most', sub: 'the same two pictures', a: 14.5, b: 11.8, unit: 'GB' },
  { ref: '7t', what: 'Qwen-Image 2.1, prompt from the prompt cache', sub: 'memory at most; the text encoder is not loaded, same picture to the pixel', a: 14.5, b: 12.1, unit: 'GB' },
  { ref: '7t', what: 'Qwen-Image 2.1, a prompt used before, after a restart', sub: 'whole picture: text encoder from its 4 bit copy, then the prompt from the prompt cache', a: 4264, b: 1711, unit: 's' },
  { ref: '7u', what: 'Qwen-Image 2.1, text encoder for a new prompt', sub: 'its 4 bit copy moved to the GPU and the prompt encoded: TinyGemm repacked per layer, then the plain packing', a: 2586, b: 28.9, unit: 's' },
  { ref: '7z', what: 'Qwen-Image 2.1, read from the SSD per picture', sub: 'transformer streamed in 16 bit, then in stages: text encoder alone, then the transformer whole in 8 bit (about as fast)', a: 382, b: 20, unit: 'GB' },
  { ref: '7z', what: 'Qwen-Image 2.1 in stages, memory at most', sub: 'prompt from the prompt cache: streamed (16 bit) against the transformer whole in 8 bit', a: 12.1, b: 9.9, unit: 'GB' },
  { ref: '7au', what: 'Chroma1 Flash in 8 bit, whole against in stages', sub: 'seconds per step, 1024 px, 12 steps: the text encoder resident (memory kept free 4 GB) against loaded per new prompt (8 GB); same picture to the pixel; 16 bit streamed: 35–63 s, 180–200 GB read', a: 52.8, b: 42.6, unit: 's' },
  { ref: '7au', what: 'Chroma1 Flash in 8 bit, memory at most', sub: 'the same two routes', a: 17.4, b: 11.1, unit: 'GB' },
  { ref: '7at', what: 'FLUX.1 [dev] streamed, memory while preparing', sub: '16 GB budget, M2 (float16): loaded whole to check the cache, then built empty from the cache (rest.safetensors)', a: 23.5, b: 11.0, unit: 'GB' },
  { ref: '7at', what: 'FLUX.1 [dev] streamed, preparation', sub: 'the same two runs: the first writes the cache', a: 100.2, b: 8.1, unit: 's' },
  { ref: '7ar', what: 'Chroma1 Flash, cancelled while loading', sub: '16 GB plan, Diffusers: from the cancel to the end of the job; the load now stops between two tensors', a: 61.6, b: 0.8, unit: 's' },
  { ref: '7ap', what: 'FLUX.2 [klein] 9B streamed, held after the picture', sub: '16 GB plan: the two blocks read ahead for a further pass dropped after the last step; read per picture 65.3 → 64.1 GB', a: 9.6, b: 8.6, unit: 'GB' },
  { ref: '7x', what: 'Z-Image Turbo (MLX), a prompt used before', sub: '16 GB plan, 512 px, after another prompt: the model loaded again, then its encodings from the prompt cache', a: 98.7, b: 64.4, unit: 's' },
  { ref: '7y', what: 'Engines without a job', sub: 'Z-Image Turbo (MLX) loaded: memory held after the picture, then freed after the idle time', a: 7.5, b: 1.1, unit: 'GB' },
  { ref: '7bm', what: 'FLUX.1 [schnell] 8 bit GGUF, whole picture', sub: 'Mac mini M4 16 GB, 1024 px, 4 steps: 16 bit streamed from the SSD (the app today, 7bj) against a 4 bit copy written once and held in memory (probe)', a: 248, b: 112, unit: 's' },
  { ref: '7bm', what: 'FLUX.1 [schnell] 8 bit GGUF, read per picture', sub: 'the same two routes', a: 98, b: 6.7, unit: 'GB' },
  { ref: '7bp', what: 'FLUX.1 [schnell] 8 bit GGUF, unpacking into the stream cache', sub: 'Mac mini M4 16 GB, memory at most: the GGUF file read whole into memory, then memory-mapped; the bfloat16 check timed once and kept, so the cache is not unpacked again', a: 14.2, b: 4.9, unit: 'GB' },
  { ref: '7ca', what: 'ObjectClear (Remove, With shadows), GPU memory at most', sub: 'Mac mini M4 16 GB, 11 pictures: the whole pipeline at once, then the fixed prompt kept as embeddings and the parts read in turn; the results the same to the pixel', a: 10.24, b: 8.38, unit: 'GB' },
  { ref: '7cc', what: 'ObjectClear, picture changed outside the painted mask', sub: '11 photos, mean: beyond the mask only where its fill is lighter (a removed shadow), never on another face', a: 14.3, b: 6.5, unit: '%' },
  { ref: '7cc', what: 'ObjectClear, the same on architecture', sub: '28 pictures of buildings and streets, mean', a: 11.7, b: 6.0, unit: '%' },
  { ref: '7cd', what: 'ObjectClear, a person beside the removed one', sub: 'picture changed beyond twice the mask growth: people found by Apple Vision protected', a: 0.36, b: 0.11, unit: '%' },
  { ref: '7r', what: 'Stop while SSD streaming is prepared', sub: 'Chroma1 Flash, stopped at 21 %: seconds until the job ended', a: 84.9, b: 0, unit: 's' },
]

// attention alone on MPS, ComfyUI's functions, 5 runs (MEASUREMENTS 7o): [case, sub-quadratic ms, PyTorch ms, note]
const ATTENTION = [
  ['SD 1.5 at 512 px', '2 × 8 heads × 40, 4096 tokens', 108, 32, 'padded to 64'],
  ['SD 1.5 at 1024 px', '2 × 8 × 40, 16384', 2337, 494, 'padded to 64'],
  ['SDXL at 1024 px', '2 × 10 × 64, 4096', 118, 39, ''],
  ['SDXL at 2048 px', '2 × 10 × 64, 16384', 2396, 624, ''],
  ['FLUX at 1024 px', '1 × 24 × 128, 4608', 239, 122, ''],
  ['AuraFlow at 1024 px', '2 × 12 × 256, 4352', 283, 344, 'slower: head size 256'],
]

// the same model on ComfyUI and on MLX, 1024 px on the M2 (MEASUREMENTS 7ag, 7ai, 7aj, 7ak, 7al, 7am, 7an): [label, s/step, engine GB]
const RUNTIMES = [
  ['MOSS-Image, ComfyUI (int8, float16)', 47.7, 9.9],
  ['MOSS-Image, MLX (8 bit)', 53.5, 14.6],
  ['MOSS-Image, MLX (4 bit)', 54.2, 8.2],
  ['Fibo 2.0 edit, ComfyUI (int8, float16)', 74.9, 14.8],
  ['Fibo 2.0 edit, MLX (8 bit)', 96.4, 11.1],
  ['Fibo 2.0 edit of two pictures, ComfyUI', 125.7, 16.2],
  ['Fibo 2.0 edit of two pictures, MLX', 166.2, 11.6],
  ['Fibo 2.0 edit, 4 pictures, ComfyUI', 284.4, 19.2],
  ['Fibo 2.0 edit, 4 pictures, MLX', 337.2, 13.0],
  ['Fibo 2.0 Dev text to image, ComfyUI (guidance 5)', 72.0, 13.4],
  ['Fibo 2.0 Dev edit, ComfyUI (guidance 5)', 147.3, 15.0],
]

// the denoiser quantized with Quanto or written once as GGUF, Mac mini M4 16 GB, 1024 px (MEASUREMENTS 7bk):
// [label, s/step, peak GB, dB to 16 bit, load s]
const QUANT = [
  ['FLUX.2 [klein] 4B, Quanto 8 bit', 11.2, 13.9, 29.8, 26.1],
  ['FLUX.2 [klein] 4B, GGUF Q8_0', 11.4, 13.5, 36.2, 7.4],
  ['FLUX.2 [klein] 4B, Quanto 4 bit', 12.0, 10.4, 20.1, 24.9],
  ['FLUX.2 [klein] 4B, GGUF Q4_0', 12.5, 9.6, 22.0, 3.7],
  ['Z-Image Turbo, Quanto 8 bit', 19.3, 13.7, 31.8, 89.9],
  ['Z-Image Turbo, GGUF Q8_0', 19.2, 12.5, 25.3, 13.2],
  ['Z-Image Turbo, Quanto 4 bit', 20.3, 11.4, 22.9, 91.4],
  ['Z-Image Turbo, GGUF Q4_0', 21.0, 10.2, 21.5, 6.7],
]

// picture to prompt, Mac mini M4 16 GB, 16 bit, three pictures (MEASUREMENTS 7bn): [model, s per picture, peak GB]
const CAPTION = [
  ['Florence-2 base (MIT, 0.46 GB)', 3.7, 2.2],
  ['Florence-2 large (MIT, 1.55 GB)', 3.1, 4.2],
  ['Qwen3-VL 2B (Apache-2.0, 4.26 GB)', 9.4, 7.7],
]

// the tools of 0.9.0 on the Mac mini M4 16 GB: [label, sub, s per picture, GB at most, ref]
const TOOLS = [
  ['Remove, LaMa (Fast)', '28 pictures, CPU', 1.5, 1.2, '7cb'],
  ['Remove, RORem (Thorough)', '28 pictures, 512 px, 20 steps', 26.9, 10.4, '7cb'],
  ['Remove, ObjectClear (With shadows)', '28 pictures', 32.0, 8.6, '7cb'],
  ['Remove, Auto: ObjectClear kept the object, filled again', 'RORem after ObjectClear, 16 % mask', 66, 8.8, '7ci'],
  ['Upscale ×4 to 2048 px, Real-ESRGAN x4plus', '512 px tile', 3.5, 4.5, '7ce'],
  ['Upscale ×4 to 2048 px, SwinIR-M (Enhance)', '512 px tile', 11.2, 7.2, '7ce'],
  ['Upscale ×4 to 2048 px, 4xBHI_dat2_real (Natural)', '384 px tile', 32.0, 6.2, '7ce'],
  ['Picture to prompt, Qwen3-VL 2B, 16 bit', 'up to 300 tokens', 11.7, 5.3, '7br'],
  ['Picture to prompt, Qwen3-VL 2B, 8 bit (not taken)', 'optimum-quanto int8', 63.7, 5.58, '7br'],
  ['Text to image + Refine faces, SD 1.5, 4 faces', '23 s without', 70.8, 4.9, '7cf'],
  ['Text to image + Refine faces, SDXL, 3 faces', '137 s without', 340.8, 10.2, '7cf'],
  ['AI Canvas Extend, klein 4B, prefill and inpaint (before)', 'smeared bars stayed in 4 of 10', 126, 9.5, '7cg'],
  ['AI Canvas Extend, klein 4B + outpaint LoRA (0.9.0)', 'all 10 without seams', 126, 10.2, '7cg'],
  ['AI Canvas Extend, Juggernaut XL v7', '', 145, 10.2, '7cg'],
  ['AI Canvas Extend, klein 9B, reference as it is', 'bars stayed in 7 of 10', 259, 11.7, '7ch'],
  ['AI Canvas Extend, klein 9B, reference blanked under the mask (0.9.0)', '', 214, 11.9, '7ch'],
]

// the fused kernel by head size, 2 × 8 heads, 4096 tokens (MEASUREMENTS 7n): [label, ms, extra GB]
const HEADS = [
  ['head size 64 (fused)', 31, 0],
  ['head size 40 (not fused)', 193, 3.0],
  ['head size 40 padded to 64', 31, 0.03],
]

// seams between the VAE tiles of Qwen-Image, one latent decoded in tiles against whole (MEASUREMENTS 7v):
// [tiles, when, strongest column 0–255, mean, GB, s]
const SEAMS = [
  ['256 px, 64 px overlap', 'before', 4.4, 1.19, 1.1, 20],
  ['256 px, 128 px overlap, new blend', '16 GB plans', 2.0, 0.79, 1.15, 40],
  ['512 px, 128 px overlap, new blend', 'where the plan has room', 0.96, 0.42, 3.3, 18],
]

// a checkpoint loaded cold from the USB SSD and from the internal SSD (MEASUREMENTS 7ao): [label, order of reading, USB s, internal s]
const LOADS = [
  ['JuggernautXL, 6.46 GB', 'file order', 17.6, 9.9],
  ['RedCraft Krea 2, 12.24 GB', 'file order', 32.1, 22.0],
  ['mopMix, 6.46 GB', 'random order', 12.9, 9.7],
]

// Wan 2.2 I2V 14B, ComfyUI LOW_VRAM, 832 × 480, 4 steps, one clip per length (MEASUREMENTS 7ay): [seconds, frames, s/step, whole s, GB at most, GB read]
const VIDEO = [
  [1, 13, 140.3, 486, 7.3, 27],
  [2, 29, 293.9, 959, 8.3, 32],
  [3, 45, 1071.2, 3134, 8.9, 49],
  [5, 77, 2155.0, 6601, 10.0, 58],
]

// the memory note: NetaYume v4 on ComfyUI, 1024 px, 3 steps, memory wired so that it is short (MEASUREMENTS 7az): [wired GB, short GB, s/step, whole s, swap read GB]
const SHORT = [
  [0, 5.7, 29.1, 135, 0.1],
  [7.5, 9.6, 29.3, 137, 1.4],
  [12, 11.1, 412.0, 1221, 244.9],
]

// the site's Content-Security-Policy allows no inline styles: every position becomes a class in charts.css
let RULES = []
const at = (css) => { RULES.push(css); return 'p' + (RULES.length - 1) }

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
const cap = (s) => s[0].toUpperCase() + s.slice(1)
const fmt = (v, d = 1) => (Math.round(v * 10 ** d) / 10 ** d).toString()
const pct = (v, max) => (Math.max(0, Math.min(1, v / max)) * 100).toFixed(2)

/** A clean axis maximum and its ticks. */
function axis(max, count = 4) {
  const raw = max / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw)
  const top = Math.ceil(max / step) * step
  return { top, ticks: Array.from({ length: Math.round(top / step) + 1 }, (_, i) => +(i * step).toFixed(6)) }
}

const legend = (a, b) => `<p class="legend"><span><i class="k a"></i>${a}</span><span><i class="k b"></i>${b}</span></p>`
const ticksRow = (ax, unit, label = 'dot-label') => `
        <div class="bx-row bx-axis" aria-hidden="true"><span class="${label}"></span><span class="bx-track">${ax.ticks.map((t) => `<span class="tick ${at(`left:${pct(t, ax.top)}%`)}">${t}${unit}</span>`).join('')}</span><span></span></div>`
const grid = (ax) => ax.ticks.map((t) => `<span class="grid ${at(`left:${pct(t, ax.top)}%`)}"></span>`).join('')

/** A dumbbell row: two values on one axis, a line between them; the tooltip carries both. */
function dumbbell({ label, sub, a, b, ax, tip, value }) {
  const [lo, hi] = a < b ? [a, b] : [b, a]
  return `
        <div class="bx-row" data-tip="${esc(tip)}" tabindex="0">
          <span class="dot-label">${esc(label)}${sub ? `<small>${esc(sub)}</small>` : ''}</span>
          <span class="bx-track">${grid(ax)}<span class="bar-link ${at(`left:${pct(lo, ax.top)}%;width:${(pct(hi, ax.top) - pct(lo, ax.top)).toFixed(2)}%`)}"></span><span class="bd a ${at(`left:${pct(a, ax.top)}%`)}"></span><span class="bd b ${at(`left:${pct(b, ax.top)}%`)}"></span></span>
          <span class="bx-value">${value}</span>
        </div>`
}

/** Two thin bars, before and after, scaled to the larger one (the tiles' microspark). */
function spark(a, b) {
  const max = Math.max(a, b)
  const w = (v) => (4 + (v / max) * 96).toFixed(1)
  return `<svg class="spark" viewBox="0 0 104 22" aria-hidden="true" focusable="false"><rect class="a" x="0" y="2" height="7" rx="3.5" width="${w(a)}"/><rect class="b" x="0" y="13" height="7" rx="3.5" width="${w(b)}"/></svg>`
}

const table = (head, rows) => `
      <details class="bx-table"><summary>Table</summary>
        <table><thead><tr>${head.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>
${rows.map((r) => `          <tr>${r.map((c, i) => `<td${i ? ' class="num"' : ''}>${c}</td>`).join('')}</tr>`).join('\n')}
        </tbody></table>
      </details>`

function tiles() {
  const pick = (model) => CHANGES.find((c) => c.model.startsWith(model))
  const items = [
    [pick('SD 1.5 (epiCPhotoGasm), 512'), 'step', '× faster', 'SD 1.5 at 512 px', 's per step'],
    [pick('SDXL (JuggernautXL), 2048'), 'step', '× faster', 'SDXL at 2048 px', 's per step'],
    [pick('SD 1.5 (epiCPhotoGasm), 512'), 'gb', '% less memory', 'SD 1.5 at 512 px', 'GB'],
    [pick('Wan 2.2'), 'step', '% less per step', 'Wan 2.2 video', 's per step'],
  ]
  return items.map(([c, k, unit, label, u]) => {
    const [a, b] = c[k]
    const big = unit.startsWith('×') ? fmt(a / b, 1) : Math.round((1 - b / a) * 100)
    return `
      <div class="tile" data-tip="${esc(`${label}: ${fmt(a, 2)} → ${fmt(b, 2)} ${u} (${c.runtime})`)}" tabindex="0">
        <p class="big">${big}<span>${unit}</span></p>
        <p class="what">${esc(label)}</p>
        ${spark(a, b)}
        <p class="vals"><span>${fmt(a, 2)}</span> → <span>${fmt(b, 2)}</span> ${u}</p>
      </div>`
  }).join('')
}

function speedChart() {
  // seconds per step as a share of before: one axis for models from 0.7 to 200 s
  const ax = { top: 110, ticks: [0, 25, 50, 75, 100] }
  const rows = CHANGES.map((c) => {
    const [a, b] = c.step
    const r = c.range
    const v = `${r ? r[0] : fmt(a, 2)} → ${r ? r[1] : fmt(b, 2)} s`
    return dumbbell({ label: c.model, sub: c.runtime, a: 100, b: (b / a) * 100, ax, value: v,
      tip: `${c.model} (${c.runtime}): ${v} per step, ${Math.round((b / a) * 100)} % of before. ${cap(c.why)}. MEASUREMENTS ${c.ref}` })
  }).join('')
  return `
    <section class="chart" id="speed">
      <h2>Time per step, before and after</h2>
      <p class="sub">Seconds per step as a share of before (before = 100 %), so models from under a second to minutes share one axis. The seconds are on the right.</p>
      ${legend('before', 'after')}
      <div class="bx">${ticksRow(ax, ' %')}${rows}
      </div>${table(['Model', 'Runtime', 'Before s/step', 'After s/step', 'After / before', 'Why'], CHANGES.map((c) => [esc(c.model), esc(c.runtime), c.range?.[0] ?? fmt(c.step[0], 2), c.range?.[1] ?? fmt(c.step[1], 2), Math.round((c.step[1] / c.step[0]) * 100) + ' %', esc(c.why)]))}
    </section>`
}

function memoryChart() {
  const measured = CHANGES.filter((c) => c.gb)
  const ax = axis(Math.max(...measured.flatMap((c) => c.gb)), 4)
  const rows = measured.map((c) => {
    const [a, b] = c.gb
    const r = c.range
    const v = `${r ? r[2] : fmt(a)} → ${r ? r[3] : fmt(b)} GB`
    return dumbbell({ label: c.model, sub: c.runtime, a, b, ax, value: v, tip: `${c.model} (${c.runtime}): engine at most ${v}. ${cap(c.why)}. MEASUREMENTS ${c.ref}` })
  }).join('')
  return `
    <section class="chart" id="memory">
      <h2>Memory at most, before and after</h2>
      <p class="sub">The engine's peak footprint during the picture (macOS, with what the GPU holds), in GB.</p>
      ${legend('before', 'after')}
      <div class="bx">${ticksRow(ax, '')}${rows}
      </div>${table(['Model', 'Runtime', 'Before GB', 'After GB'], measured.map((c) => [esc(c.model), esc(c.runtime), c.range?.[2] ?? fmt(c.gb[0]), c.range?.[3] ?? fmt(c.gb[1])]))}
    </section>`
}

function planChart(id, title, sub, data, ref) {
  const ax = axis(Math.max(...data.flatMap((p) => [p[2], p[3]])), 4)
  const rows = data.map(([model, rt, used, plan]) => {
    const d = used - plan
    const v = `${d >= 0 ? '+' : '−'}${fmt(Math.abs(d))} GB`
    return dumbbell({ label: model, sub: rt, a: plan, b: used, ax, value: v, tip: `${model} (${rt}): planned ${fmt(plan)} GB, used ${fmt(used)} GB (${v}). MEASUREMENTS ${ref}` })
  }).join('')
  return `
    <section class="chart" id="${id}">
      <h2>${title}</h2>
      <p class="sub">${sub}</p>
      ${legend('planned', 'measured')}
      <div class="bx">${ticksRow(ax, '')}${rows}
      </div>${table(['Model', 'Runtime', 'Planned GB', 'Measured GB', 'Difference'], data.map(([m, rt, u, p]) => [esc(m), esc(rt), fmt(p), fmt(u), (u - p >= 0 ? '+' : '−') + fmt(Math.abs(u - p))]))}
    </section>`
}

function onceTable() {
  const rows = ONCE.map((o) => {
    const f = (v) => fmt(v, v < 1 ? 2 : 1)
    const max = Math.max(o.a, o.b)
    const bar = (v, cls) => `<span class="mbar ${cls} ${at(`width:${pct(v, max)}%`)}"></span>`
    const less = o.a ? Math.round((1 - o.b / o.a) * 100) : 0
    return `
          <tr data-tip="${esc(`${o.what}: ${f(o.a)} → ${f(o.b)} ${o.unit}. MEASUREMENTS ${o.ref}`)}" tabindex="0">
            <td>${esc(o.what)}<small>${esc(o.sub)}</small></td>
            <td class="bars">${bar(o.a, 'a')}${bar(o.b, 'b')}</td>
            <td class="num">${f(o.a)} ${o.unit}</td><td class="num">${f(o.b)} ${o.unit}</td>
            <td class="num">−${less} %</td>
          </tr>`
  }).join('')
  return `
    <section class="chart" id="once">
      <h2>Done once, then kept</h2>
      <p class="sub">What a cache or a fix saves on a 16 GB plan (memory kept free 12 GB on the 24 GB Mac). Each row's bars share its own scale. Also measured: an FP8 model on a Mac short of memory stopped at its first step (MPS cannot compute FP8); it now runs in 16 bit (Anima-Turbo, 4.9 GB, MEASUREMENTS 7q). Not built in: MLX's wired limit (68 % of the RAM or its recommended working set) was not faster in all three MLX models tried (MEASUREMENTS 7aa).</p>
      ${legend('before', 'after')}
      <table class="micro">
        <thead><tr><th>Case</th><th>per row</th><th class="num">before</th><th class="num">after</th><th class="num">less</th></tr></thead>
        <tbody>${rows}
        </tbody>
      </table>
    </section>`
}

function attentionTable() {
  const rows = ATTENTION.map(([name, shape, sub, sdpa, note]) => {
    const max = Math.max(sub, sdpa)
    const bar = (v, cls) => `<span class="mbar ${cls} ${at(`width:${pct(v, max)}%`)}"></span>`
    const ratio = sub / sdpa
    return `
          <tr data-tip="${esc(`${name}: sub-quadratic ${sub} ms, PyTorch ${sdpa} ms${note ? ' (' + note + ')' : ''}`)}" tabindex="0">
            <td>${esc(name)}<small>${esc(shape)}</small></td>
            <td class="bars">${bar(sub, 'a')}${bar(sdpa, 'b')}</td>
            <td class="num">${sub} ms</td><td class="num">${sdpa} ms</td>
            <td class="num ${ratio < 1 ? 'worse' : ''}">${ratio >= 1 ? fmt(ratio, 1) + '×' : '−' + Math.round((1 - ratio) * 100) + ' %'}</td>
          </tr>`
  }).join('')
  return `
    <section class="chart" id="attention">
      <h2>Attention alone: ComfyUI's two functions</h2>
      <p class="sub">One attention call per case on the GPU (MPS), 5 runs. Each row's bars share its own scale. Sub-quadratic was ComfyUI's choice on the Mac; PyTorch's fused attention is used now.</p>
      ${legend('sub-quadratic', 'PyTorch (SDPA)')}
      <table class="micro">
        <thead><tr><th>Case</th><th>per row</th><th class="num">sub-quad.</th><th class="num">PyTorch</th><th class="num">faster</th></tr></thead>
        <tbody>${rows}
        </tbody>
      </table>
    </section>`
}

function headsChart() {
  const ax = axis(Math.max(...HEADS.map((h) => h[1])), 4)
  const rows = HEADS.map(([label, ms, gb]) => `
        <div class="bx-row" data-tip="${esc(`${label}: ${ms} ms, ${gb} GB extra`)}" tabindex="0">
          <span class="dot-label">${esc(label)}</span>
          <span class="bx-track">${grid(ax)}<span class="hbar ${at(`width:${pct(ms, ax.top)}%`)}"></span></span>
          <span class="bx-value">${ms} ms · +${gb} GB</span>
        </div>`).join('')
  return `
    <section class="chart" id="heads">
      <h2>Why SD 1.5 was slow: head sizes on MPS</h2>
      <p class="sub">PyTorch's attention on Apple GPUs runs fused only for some head sizes; for the others it holds the whole attention matrix (extra GB). SD 1.5 has heads of 40. Padded with zeros to 64 it gives the same result.</p>
      <div class="bx">${ticksRow(ax, ' ms')}${rows}
      </div>${table(['Case', 'ms', 'extra GB'], HEADS.map(([l, ms, gb]) => [esc(l), ms, gb]))}
    </section>`
}

function runtimesChart() {
  const ax = axis(Math.max(...RUNTIMES.map((r) => r[1])), 4)
  const rows = RUNTIMES.map(([label, step, gb]) => `
        <div class="bx-row" data-tip="${esc(`${label}: ${fmt(step)} s per step, ${fmt(gb)} GB at most. MEASUREMENTS 7ak`)}" tabindex="0">
          <span class="dot-label">${esc(label)}</span>
          <span class="bx-track">${grid(ax)}<span class="hbar ${at(`width:${pct(step, ax.top)}%`)}"></span></span>
          <span class="bx-value">${fmt(step)} s · ${fmt(gb)} GB</span>
        </div>`).join('')
  return `
    <section class="chart" id="runtimes">
      <h2>One model, two runtimes</h2>
      <p class="sub">MOSS-Image and Fibo 2.0 on ComfyUI and on MLX (mflux 0.24), 1024 px on an M2 with 24 GB. ComfyUI is quicker per step on the M2; MLX holds less where its text encoder is dropped first, so Fibo 2.0 runs on 16 GB Macs with it. Fibo 2.0 Dev (ComfyUI only) computes two passes per step for its guidance.</p>
      <div class="bx">${ticksRow(ax, ' s')}${rows}
      </div>${table(['Model and runtime', 's/step', 'Engine GB'], RUNTIMES.map(([l, step, gb]) => [esc(l), fmt(step), fmt(gb)]))}
    </section>`
}

function quantChart() {
  const ax = axis(Math.max(...QUANT.map((r) => r[2])), 4)
  const rows = QUANT.map(([label, step, gb, db, load]) => `
        <div class="bx-row" data-tip="${esc(`${label}: ${fmt(gb)} GB at most, ${fmt(step)} s per step, ${fmt(db)} dB to 16 bit, loaded in ${fmt(load)} s. MEASUREMENTS 7bk`)}" tabindex="0">
          <span class="dot-label">${esc(label)}</span>
          <span class="bx-track">${grid(ax)}<span class="hbar ${at(`width:${pct(gb, ax.top)}%`)}"></span></span>
          <span class="bx-value">${fmt(gb)} GB · ${fmt(step)} s · ${fmt(db)} dB</span>
        </div>`).join('')
  return `
    <section class="chart" id="quant">
      <h2>Quanto or GGUF for the denoiser</h2>
      <p class="sub">Diffusers will drop its Quanto backend with version 1.0; GGUF, written once, is the candidate without a new package. Mac mini M4 with 16 GB, 1024 px, everything held on the GPU (the peaks compare only with each other). The bar is the memory at most; dB is how close the picture is to 16 bit (Z-Image's 16 bit picture from the M2: on 16 GB it swapped). GGUF takes 0.4–1.3 GB less and loads in seconds, is as fast at 8 bit and 3–4 % slower at 4 bit; its pictures are closer for klein, further for Z-Image.</p>
      <div class="bx">${ticksRow(ax, ' GB')}${rows}
      </div>${table(['Model and quantization', 's/step', 'GB at most', 'dB to 16 bit', 'load s'], QUANT.map(([l, step, gb, db, load]) => [esc(l), fmt(step), fmt(gb), fmt(db), fmt(load)]))}
    </section>`
}

function captionChart() {
  const ax = axis(Math.max(...CAPTION.map((r) => r[2])), 4)
  const rows = CAPTION.map(([label, sec, gb]) => `
        <div class="bx-row" data-tip="${esc(`${label}: ${fmt(gb)} GB at most, up to ${fmt(sec)} s per picture. MEASUREMENTS 7bn`)}" tabindex="0">
          <span class="dot-label">${esc(label)}</span>
          <span class="bx-track">${grid(ax)}<span class="hbar ${at(`width:${pct(gb, ax.top)}%`)}"></span></span>
          <span class="bx-value">${fmt(gb)} GB · ${fmt(sec)} s</span>
        </div>`).join('')
  return `
    <section class="chart" id="caption">
      <h2>Picture to prompt</h2>
      <p class="sub">Candidates for a prompt from a picture, Mac mini M4 with 16 GB, 16 bit, the longest of three pictures. The bar is the memory at most. Both Florence-2 sizes saw a third woman between two and put a pattern on the wrong clothes; Qwen3-VL 2B got the people and clothes right and wrote prompt-like text with light, colours and camera.</p>
      <div class="bx">${ticksRow(ax, ' GB')}${rows}
      </div>${table(['Model', 's per picture', 'GB at most'], CAPTION.map(([l, sec, gb]) => [esc(l), fmt(sec), fmt(gb)]))}
    </section>`
}

function toolsChart() {
  const ax = axis(Math.max(...TOOLS.map((r) => r[2])), 4)
  const rows = TOOLS.map(([label, sub, sec, gb, ref]) => `
        <div class="bx-row" data-tip="${esc(`${label}: up to ${fmt(sec)} s per picture, ${fmt(gb)} GB at most. MEASUREMENTS ${ref}`)}" tabindex="0">
          <span class="dot-label">${esc(label)}${sub ? `<small>${esc(sub)}</small>` : ''}</span>
          <span class="bx-track">${grid(ax)}<span class="hbar ${at(`width:${pct(sec, ax.top)}%`)}"></span></span>
          <span class="bx-value">${fmt(sec)} s · ${fmt(gb)} GB</span>
        </div>`).join('')
  return `
    <section class="chart" id="tools">
      <h2>Remove, upscale, refine faces, extend: on a 16 GB Mac</h2>
      <p class="sub">The tools of 0.9.0 on a Mac mini M4 with 16 GB, through the app's engine, one job per picture (the mean or the slowest picture). The bar is the time per picture, the memory is the job's peak. ObjectClear removed shadows with the object where LaMa and RORem left a dark patch, and invented things in about 6 of 28 architecture pictures; DAT2 kept the most natural texture. klein Base 4B with the LoRA (50 steps) was as good as the distilled one but took 42–43 minutes per picture.</p>
      <div class="bx">${ticksRow(ax, ' s')}${rows}
      </div>${table(['Tool', 's per picture', 'GB at most', 'MEASUREMENTS'], TOOLS.map(([l, sub, sec, gb, ref]) => [esc(l + (sub ? ` (${sub})` : '')), fmt(sec), fmt(gb), ref]))}
    </section>`
}

function seamsChart() {
  const ax = axis(Math.max(...SEAMS.map((r) => r[2])), 4)
  const rows = SEAMS.map(([tiles, when, col, mean, gb, sec]) => `
        <div class="bx-row" data-tip="${esc(`${tiles} (${when}): strongest column ${fmt(col, 2)}, mean ${fmt(mean, 2)}, ${fmt(gb)} GB, ${sec} s. MEASUREMENTS 7v`)}" tabindex="0">
          <span class="dot-label">${esc(tiles)}<small>${esc(when)}</small></span>
          <span class="bx-track">${grid(ax)}<span class="hbar ${at(`width:${pct(col, ax.top)}%`)}"></span></span>
          <span class="bx-value">${fmt(col, 2)} · ${fmt(gb)} GB</span>
        </div>`).join('')
  return `
    <section class="chart" id="seams">
      <h2>Seams between VAE tiles (Qwen-Image)</h2>
      <p class="sub">Qwen-Image's VAE decodes 1024 px in tiles; where they meet, plain areas showed faint streaks. The bar is the strongest column's difference to decoding whole (0–255); decoding whole needs 13.2 GB. In the real 16 GB run: 0.3 GB and 33 s more per picture, the streaks gone. Decoding is not the peak there (MEASUREMENTS 7w): sampled 9.7 GB at its start, then 7.6 GB, against up to 11.6 GB in the steps.</p>
      <div class="bx">${ticksRow(ax, '')}${rows}
      </div>${table(['Tiles', 'Used', 'Strongest column', 'Mean', 'GB', 's'], SEAMS.map(([t, w, c, m, gb, sec]) => [esc(t), esc(w), fmt(c, 2), fmt(m, 2), fmt(gb, 2), sec]))}
    </section>`
}

function loadsChart() {
  const ax = axis(Math.max(...LOADS.map((r) => r[2])), 4)
  const rows = LOADS.map(([label, order, usb, inside]) => dumbbell({
    label, sub: order, a: usb, b: inside, ax, value: `${fmt(usb)} → ${fmt(inside)} s`,
    tip: `${label}, ${order}: ${fmt(usb)} s from the USB SSD, ${fmt(inside)} s from the internal SSD. MEASUREMENTS 7ao`,
  })).join('')
  return `
    <section class="chart" id="loads">
      <h2>Loading from a USB SSD or the internal SSD</h2>
      <p class="sub">A checkpoint read cold through its mapped file, one run each on an M2 with 24 GB. Plain reading is 0.81 GB/s over USB and 2.74 GB/s internally, yet mapped reading stays near 0.6 GB/s even internally. A copy on the internal SSD saves 3 to 10 s per cold load.</p>
      ${legend('USB SSD', 'internal SSD')}
      <div class="bx">${ticksRow(ax, ' s')}${rows}
      </div>${table(['Checkpoint', 'Order', 'USB s', 'Internal s'], LOADS.map(([l, o, u, i]) => [esc(l), esc(o), fmt(u), fmt(i)]))}
    </section>`
}

function videoChart() {
  const max = Math.max(...VIDEO.map((r) => r[3]))
  const rows = VIDEO.map(([sec, frames, step, whole, gb, read]) => `
          <tr data-tip="${esc(`${sec} s (${frames} frames): ${fmt(step)} s per step, ${whole} s for the clip, ${fmt(gb)} GB at most, ${read} GB read. MEASUREMENTS 7ay`)}" tabindex="0">
            <td>${sec} s<small>${frames} frames, ${fmt(whole / 60)} min</small></td>
            <td class="bars"><span class="mbar b ${at(`width:${pct(whole, max)}%`)}"></span></td>
            <td class="num">${fmt(step)}</td><td class="num">${whole}</td><td class="num">${fmt(gb)}</td><td class="num">${read}</td>
          </tr>`).join('')
  return `
    <section class="chart" id="video">
      <h2>Video: clips of one to five seconds</h2>
      <p class="sub">Wan 2.2 I2V 14B (Q4_K GGUF, both experts read from the SSD per step, the text encoder dropped after the prompt), 832 × 480, 4 steps, one clip per length on the M2 with 24 GB. The bars are the whole time of the clip. Memory grows little with the length; the time per step grows faster than the frames, as the attention over the frames grows with the square of the tokens. On the 16 GB simulation (12 GB kept free, 8 GB wired) the one-second clip took 205.6 s per step and 11.6 min at 6.0 GB, reading 65 GB; the five-second clip drove the swap to 21 GB and the app's GPU process ended after 7 minutes, so Wan 2.2 14B stays a 24 GB model.</p>
      <table class="micro">
        <thead><tr><th>Clip</th><th>whole time</th><th class="num">s/step</th><th class="num">whole s</th><th class="num">GB at most</th><th class="num">GB read</th></tr></thead>
        <tbody>${rows}
        </tbody>
      </table>
    </section>`
}

function shortTable() {
  const max = Math.max(...SHORT.map((r) => r[2]))
  const rows = SHORT.map(([wired, short, step, whole, swap]) => `
          <tr data-tip="${esc(`${short} GB short (${wired} GB wired): ${fmt(step)} s per step, ${whole} s for the picture, ${fmt(swap)} GB read back from the swap. MEASUREMENTS 7az`)}" tabindex="0">
            <td>${fmt(short)} GB short<small>${wired} GB wired</small></td>
            <td class="bars"><span class="mbar b ${at(`width:${pct(step, max)}%`)}"></span></td>
            <td class="num">${fmt(step)}</td><td class="num">${whole}</td><td class="num">${fmt(swap)}</td>
          </tr>`).join('')
  return `
    <section class="chart" id="short">
      <h2>When less memory is free than the plan needs</h2>
      <p class="sub">NetaYume v4 (Lumina 2) on ComfyUI, 1024 px, 3 steps, planned 14.1 GB, on the M2 with 24 GB. Memory wired with mlock so that other programs could not give it up; "short" is the plan less what was free when the picture started. Up to 9.6 GB short the picture stays as fast (macOS moves idle programs to the swap); at 11.1 GB short it took 14 times as long and read 245 GB back from the swap. The bars are the seconds per step.</p>
      <table class="micro">
        <thead><tr><th>Shortage</th><th>per step</th><th class="num">s/step</th><th class="num">whole s</th><th class="num">GB from the swap</th></tr></thead>
        <tbody>${rows}
        </tbody>
      </table>
    </section>`
}

/** The page and its charts.css (the positions of the marks). */
export function benchmarksPage({ BASE, GH, BLOB, VERSION, CSS_V, JS_V, BENCH_V }) {
  RULES = []
  const body = [speedChart(), memoryChart(),
    planChart('plan', 'The memory plan against the measurement', 'Before every picture VulKara plans the memory a model needs and picks bit size, staging or streaming from it. Here the plan against what the engine used, 1024 px; the right column is the difference. Before the fixes of the same day (decoding in tiles, padded attention).', PLAN, '7m'),
    planChart('plan-after', 'Plans brought to the measurements', 'SD 1.5 planned at its own size with fused attention, ComfyUI models with the plan of a model held whole (shown in the benchmark since 0.7.5). The ComfyUI figures are the middle of two runs. Qwen-Image 2.1 streamed: the blocks kept in memory were not counted while denoising (planned 9.1 GB before). ComfyUI on 16 GB: the text encoder and the model planned apart, as ComfyUI loads them (MOSS-Image 14 GB before, NetaYume 11.6). Fibo 2.0: the activations of an edit counted (12.1 GB planned before).', PLAN_AFTER, '7p'),
    planChart('plan-m4', 'On a 16 GB Mac: Mac mini M4', 'VulKara 0.7.11 on an Apple M4 with 16 GB (the other charts: the M2, 16 GB simulated there); from MOSS-Image on, test builds after it (MEASUREMENTS 7ah, 7ba–7bl). The plan against what the engine used, 1024 px (Fibo 768 px), with the seconds per step or per picture. Fibo 2.0 on MLX started 6.3 GB short and read 18.9 GB back from the swap: slower than on the M2 (7ba). Above their plan and open: FLUX.1 [schnell] 8 bit streamed (3.9 GB), NetaYume v4 (1.8 GB), FLUX.1 Fill (0.9 GB) (7bf, 7bj).', PLAN_M4, '7af'),
    onceTable(), toolsChart(), runtimesChart(), quantChart(), captionChart(), loadsChart(), videoChart(), shortTable(), seamsChart(), headsChart(), attentionTable()].join('\n')
  const tileHtml = tiles()
  const css = RULES.map((r, i) => `.bench-page .p${i}{${r}}`).join('\n') + '\n'
  const cssV = createHash('sha256').update(css).digest('hex').slice(0, 10)
  const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; base-uri 'none'; form-action 'none'">
  <meta name="referrer" content="strict-origin-when-cross-origin">
  <title>Benchmarks – VulKara</title>
  <meta name="description" content="Measured speed and memory of VulKara's runtimes on Apple Silicon: before and after, and the memory plan against the measurement.">
  <link rel="canonical" href="${BASE}benchmarks/">
  <meta name="color-scheme" content="light dark">
  <link rel="icon" href="../assets/icon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="../style.css?v=${CSS_V}">
  <link rel="stylesheet" href="charts.css?v=${cssV}">
  <script src="../theme.js?v=${JS_V}"></script>
  <script src="../bench.js?v=${BENCH_V}" defer></script>
</head>
<body class="changes-page bench-page">
  <header class="cl-top">
    <div class="wrap">
      <a class="brand" href="../"><img src="../assets/icon.svg" width="26" height="26" alt="">VulKara<span class="ver">v${VERSION}</span></a>
      <span class="path">~/vulkara <b>$</b> benchmark --report</span>
      <span class="spacer"></span>
      <a class="gh" href="../results/">results</a>
      <a class="gh" href="../changes/">changes</a>
      <a class="gh" href="${BLOB}/docs/MEASUREMENTS.md" rel="noopener">MEASUREMENTS.md ↗</a>
    </div>
  </header>
  <main id="main" class="wrap">
    <div class="intro">
      <h1>Benchmarks</h1>
      <p>Speed and memory of VulKara's three runtimes (Diffusers, MLX, ComfyUI), measured with the app's own benchmark
      (Hardware → Benchmark) and engine probes. Every figure is in the measurement log with how it was taken.
      <span class="stat">${MEASURED} · seconds per step of the second picture · peaks = the engine's footprint · the Mac swapped other programs throughout, so seconds compare within a row, not across rows</span></p>
    </div>
    <div class="tiles">${tileHtml}
    </div>
${body}
  </main>
  <footer>
    <div class="wrap">
      <p class="legal"><a href="../">VulKara</a> · <a href="../changes/">Changes</a> · <a href="../impressum/">Impressum</a> · <a href="../datenschutz/">Datenschutz</a> · <a href="${GH}" rel="noopener">GitHub</a></p>
    </div>
  </footer>
</body>
</html>
`
  return { html, css }
}
