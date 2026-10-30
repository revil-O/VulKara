// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Types shared by the main process, the preload script and the pages.

/** What a model's manifest (model.json) tells the app. */
export interface ModelMeta {
  arch: string
  family: string
  label: string
  runtime: 'diffusers' | 'mlx' | 'comfyui'
  kind: 'image' | 'video'
  minRamGb?: number
  defaults?: Record<string, number | string>
  /** what the model's maker recommends (its card), with where it was read; over the defaults (maker_settings.py) */
  maker?: Record<string, number | string>
  resolutions?: number[]
  /** the app-sampler labels this model's maker names on its card; when set, the sampler picker shows only these
   *  (plus "Default"), so a model its maker runs with DPM++ only does not offer Euler (maker_settings.py) */
  samplers?: string[]
  negativePrompt?: boolean
  img2img?: boolean
  inpaint?: boolean
  inpaintOnly?: boolean
  contentFiltered?: boolean
  triggerWords?: string[]
  /** the sub-base inside a family whose LoRAs do not fit each other: klein4b / klein9b / dev (FLUX.2), 5b / 14b (Wan) */
  variant?: string
  /** a model that takes no LoRAs yet (Wan 2.2 14B) */
  noLoras?: boolean
  /** why no LoRA can be baked into this model (compressed weights, ComfyUI), when it can not */
  bakeBlocked?: string
  /** can be written as one original-layout checkpoint (SD 1.x, SDXL in folder layout) */
  exportable?: boolean
  /** why an installed model can not run (its kind has no runtime yet) */
  unsupported?: string
  /** imported on another Mac and copied here (src/main/foreign_mac.ts): that Mac's memory where known, and whether
   * its source (a file that is still there, a Hugging Face or Civitai link) is there to import it again */
  foreignMac?: { ramGb?: number; canReimport: boolean }
}

/** An installed model or LoRA. */
export interface Asset {
  id: string
  /** the name shown in the app: the user's own name for it, else its folder's name */
  title: string
  /** the name of its folder, which a new title does not change */
  name: string
  folder: string
  type: 'model' | 'lora'
  meta: ModelMeta
  /** a picture of what the model or LoRA does */
  preview?: string
  /** the user's own grouping of LoRAs */
  category?: string
  source?: { type: string; ref: string; file?: string | null; versionId?: string | null }
  /** the base model Civitai names for it (a Pony or Illustrious checkpoint is an SDXL model of its own kind) */
  baseModel?: string
}

/** What the restoration of an old photo does. The AI steps run on a FLUX.2 model, held to guard rails. */
/** The EU's icon for AI content in the lower right corner of a picture (engines/diffusers/content_check.py label). */
export interface AiLabel {
  size: 'small' | 'medium' | 'large'
  /** "AI GENERATED" (made from a prompt), "AI MODIFIED" (from a picture of the user's), or the round "AI" */
  kind: 'generated' | 'modified' | 'ai'
  /** black or white; auto: by the brightness of the corner */
  tone: 'auto' | 'black' | 'white'
  /** the icon at 50 % transparency */
  subtle?: boolean
}

export interface PhotoToolJob {
  /** the tool's folder */
  folder: string
  /** how much of the tool's result is mixed in (image tools), 0..1 */
  strength?: number
  /** enlarging tools: how many times larger than the picture given the result is (up to the tool's scale) */
  factor?: number
  /** another weights file the tool offers (e.g. "sharp" for SCUNet); none: its own */
  variant?: string
  /** JPEG cleanup: the JPEG quality (1..100) to clean for instead of the one it estimates; lower = stronger */
  quality?: number
  /** mask and selection tools: the subject on a transparent background, or the mask in black and white */
  output?: 'cutout' | 'mask'
  /** selection tools: the mask chosen by clicks */
  mask?: string
}

export interface RestoreOptions {
  /** colour cast, faded tones and flat contrast */
  correct: boolean
  /** the AI repairs scratches, creases, spots and holes */
  repair: boolean
  /** a black-and-white photo is coloured (DDColor); the shapes stay the original's */
  colorize: boolean
  /** how strong the colours are, 0.5..1.5 */
  colorStrength: number
  /** less grain and crisper details */
  sharpen: boolean
  /** 0..1 */
  sharpness: number
  /** outside the painted damage the original stays */
  lock: boolean
  /** how much the shapes may change where the original is not kept (0..1) */
  maxChange: number
  /** the user's own rules for the AI, added to the fixed ones */
  rules: string[]
  /** refuse a result in which a face appeared, vanished or moved */
  checkFaces: boolean
  /** how strongly the correction is applied, 0..1 (default 0.8) */
  correctStrength?: number
  /** dust and scratches found and filled from their surroundings (LaMa) */
  dust?: boolean
  /** 0..1: higher finds fainter specks (and more texture by mistake) */
  dustSensitivity?: number
  /** soft detail of the whole photo rebuilt by Real-ESRGAN */
  details?: boolean
  /** how soft the photo is: it is made this many times smaller before the model enlarges it four times, 1.25..3 */
  detailLevel?: number
  /** 0..1, blended with the photo */
  detailStrength?: number
  /** faces restored by CodeFormer */
  faces?: boolean
  /** 0.5..1: higher keeps more of the face as it is, lower makes up more detail */
  faceFidelity?: number
  /** 0..1, blended with the photo */
  faceStrength?: number
  /** the faces to restore as the user placed them (5 landmarks each, photo pixels); undefined: found by the engine */
  facePoints?: [number, number][][]
  /** the result at the photo's size (1) or twice that (2) */
  scale?: 1 | 2
  /** a preview: only this part of the photo (its pixels), not kept in the history; auto: w × h around the largest
   *  face, else in the middle */
  preview?: { x: number; y: number; w: number; h: number; auto?: boolean }
}

/** A job as the engines take it (protocol v2, "generate"). */
export interface Job {
  id: string
  page: string
  prompt: string
  negativePrompt?: string
  /** the style the prompt is put into (shared/styles.ts); the prompt itself stays as written */
  style?: string
  modelId: string
  modelDir: string
  width: number
  height: number
  steps?: number
  guidance?: number
  seed: number
  sampler?: string
  sigmaSchedule?: string
  /** how much of the input picture changes, 0..1 */
  strength?: number
  inputImage?: string
  maskImage?: string
  loras?: { path: string; scale: number }[]
  controlnet?: { type: string; image: string; weight: number; preprocess: boolean }
  videoSeconds?: number
  /** enlarge the input picture to this many times its size (1.1 to 4) instead of painting */
  upscale?: number
  /** keep width and height although there is an input picture */
  exactSize?: boolean
  /** with a mask: start the masked part from the colours along its edge (extending a picture) */
  prefill?: boolean
  /** restoring an old photo (Restore page) instead of painting a new picture */
  restore?: RestoreOptions
  /** a photo tool (Enhance page) on the input picture instead of painting */
  photoTool?: PhotoToolJob
  /** the user confirmed the consent question (intimate content from a picture) */
  consent?: boolean
  /** FLUX 3 Image Klein: the prompt upsampler writes the full caption first (text to image) */
  upsample?: boolean
  /** "AI generated .." written into the lower right corner of each picture (not videos) */
  aiLabel?: AiLabel
  label?: string
  /** set by the app while the job runs, not by the form: how it was made where that differs from the usual (e.g.
   *  with Diffusers instead of MLX); shown with the job, its pictures and in the history */
  note?: string
}

/** A finished job in the history: what was asked for and the files it produced. */
export interface HistoryEntry {
  id: string
  /** milliseconds since 1970 */
  createdAt: number
  job: Job
  /** name of the model at the time, also when the model is gone */
  modelName: string
  files: string[]
  /** the files marked as favourites, in the order of files; missing when there are none */
  favorites?: string[]
  kind: 'image' | 'video'
  /** how long the job ran, loading included, and its seconds per step (entries since 0.7.10) */
  seconds?: number
  secondsPerStep?: number
}

/** Events of the engines (protocol v2) as the main process passes them on. */
export type EngineEvent =
  | { event: 'state'; state: 'loaded' | 'idle' | 'busy' }
  | { event: 'progress'; value: number }
  | { event: 'status'; message: string }
  | { event: 'note'; message: string }
  /** the bit size each part of the model runs in for this job: "transformer 8 bit, text encoder 4 bit" */
  | { event: 'precision'; message: string }
  /** time the steps waited for parts of the model read again (ssd_stream: blocks streamed from the SSD) */
  | { event: 'waited'; what: string; seconds: number; gb: number }
  /** the engine's own processes over the job: their peak footprint (with what the GPU holds), what they read from
   *  disk, and what its memory plan expected (missing where it has none) */
  | { event: 'footprint'; peak_gb: number; read_gb: number; plan_gb?: number | null }
  | { event: 'result'; path: string }
  | { event: 'error'; message: string }
  | { event: 'preview'; model: string; preview?: string; error?: string }
