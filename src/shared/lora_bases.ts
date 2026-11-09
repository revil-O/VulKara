// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The base models LoRAs are made for, as Civitai names them ("baseModel") and as Hugging Face links them
// (base_model:adapter:<repository>), and which base an installed model needs its LoRAs for.

import type { Asset, ModelMeta } from './types'

export interface LoraBase {
  id: string
  /** the name shown in the app */
  label: string
  /** the app's model family its LoRAs are filed under */
  family: string
  /** Civitai's names of the base model (several are asked for at once) */
  civitai: string[]
  /** Hugging Face repositories LoRAs name as their base, asked one after the other */
  hf: string[]
}

export const LORA_BASES: LoraBase[] = [
  { id: 'sd15', label: 'Stable Diffusion 1.5', family: 'sd1', civitai: ['SD 1.5'], hf: ['runwayml/stable-diffusion-v1-5', 'stable-diffusion-v1-5/stable-diffusion-v1-5'] },
  { id: 'sd2', label: 'Stable Diffusion 2.1', family: 'sd2', civitai: ['SD 2.1', 'SD 2.1 768'], hf: ['stabilityai/stable-diffusion-2-1'] },
  { id: 'sdxl', label: 'SDXL', family: 'sdxl', civitai: ['SDXL 1.0'], hf: ['stabilityai/stable-diffusion-xl-base-1.0'] },
  { id: 'pony', label: 'Pony (SDXL)', family: 'sdxl', civitai: ['Pony'], hf: ['AstraliteHeart/pony-diffusion-v6'] },
  { id: 'illustrious', label: 'Illustrious (SDXL)', family: 'sdxl', civitai: ['Illustrious'], hf: ['OnomaAIResearch/Illustrious-xl-early-release-v0', 'OnomaAIResearch/Illustrious-XL-v2.0'] },
  { id: 'noobai', label: 'NoobAI (SDXL)', family: 'sdxl', civitai: ['NoobAI'], hf: ['Laxhar/noobai-XL-Vpred-1.0', 'Laxhar/noobai-XL-1.1'] },
  { id: 'sd35_medium', label: 'Stable Diffusion 3.5 Medium', family: 'sd3', civitai: ['SD 3.5 Medium', 'SD 3.5'], hf: ['stabilityai/stable-diffusion-3.5-medium'] },
  { id: 'sd35_large', label: 'Stable Diffusion 3.5 Large', family: 'sd3', civitai: ['SD 3.5 Large', 'SD 3.5'], hf: ['stabilityai/stable-diffusion-3.5-large'] },
  { id: 'flux1_dev', label: 'FLUX.1 [dev]', family: 'flux1', civitai: ['Flux.1 D'], hf: ['black-forest-labs/FLUX.1-dev'] },
  { id: 'flux1_schnell', label: 'FLUX.1 [schnell]', family: 'flux1', civitai: ['Flux.1 S'], hf: ['black-forest-labs/FLUX.1-schnell'] },
  { id: 'flux1_krea', label: 'FLUX.1 Krea [dev]', family: 'flux1', civitai: ['Flux.1 Krea'], hf: ['black-forest-labs/FLUX.1-Krea-dev'] },
  { id: 'flux1_kontext', label: 'FLUX.1 Kontext [dev]', family: 'flux1', civitai: ['Flux.1 Kontext'], hf: ['black-forest-labs/FLUX.1-Kontext-dev'] },
  { id: 'chroma', label: 'Chroma', family: 'chroma', civitai: ['Chroma'], hf: ['lodestones/Chroma1-HD', 'lodestones/Chroma1-Base', 'lodestones/Chroma'] },
  { id: 'flux2_dev', label: 'FLUX.2 [dev]', family: 'flux2', civitai: ['Flux.2 D'], hf: ['black-forest-labs/FLUX.2-dev'] },
  { id: 'flux2_klein4', label: 'FLUX.2 [klein] 4B', family: 'flux2', civitai: ['Flux.2 Klein 4B', 'Flux.2 Klein 4B-base'], hf: ['black-forest-labs/FLUX.2-klein-4B', 'black-forest-labs/FLUX.2-klein-base-4B'] },
  { id: 'flux2_klein9', label: 'FLUX.2 [klein] 9B', family: 'flux2', civitai: ['Flux.2 Klein 9B', 'Flux.2 Klein 9B-base'], hf: ['black-forest-labs/FLUX.2-klein-9B', 'black-forest-labs/FLUX.2-klein-base-9B'] },
  { id: 'flux3_klein', label: 'FLUX 3 Image Klein', family: 'flux3', civitai: ['Flux.3 Klein', 'Flux.3 Klein-base', 'Flux.3'], hf: ['black-forest-labs/flux-3-image-klein', 'black-forest-labs/flux-3-image-klein-base'] },
  { id: 'qwen_image', label: 'Qwen-Image', family: 'qwen_image', civitai: ['Qwen'], hf: ['Qwen/Qwen-Image'] },
  { id: 'qwen_image21', label: 'Qwen-Image 2.1', family: 'qwen_image21', civitai: ['Qwen 2.1'], hf: ['Qwen/Qwen-Image-2.1'] },
  { id: 'z_image_turbo', label: 'Z-Image Turbo', family: 'z_image', civitai: ['ZImageTurbo'], hf: ['Tongyi-MAI/Z-Image-Turbo'] },
  { id: 'z_image_base', label: 'Z-Image Base', family: 'z_image', civitai: ['ZImageBase'], hf: ['Tongyi-MAI/Z-Image'] },
  { id: 'krea2', label: 'Krea 2', family: 'krea2', civitai: ['Krea 2'], hf: ['krea/Krea-2-Turbo'] },
  { id: 'anima', label: 'Anima', family: 'anima', civitai: ['Anima'], hf: ['circlestone-labs/Anima'] },
  { id: 'ernie_image', label: 'ERNIE-Image', family: 'ernie', civitai: ['ERNIE', 'Ernie Image'], hf: ['baidu/ERNIE-Image', 'baidu/ERNIE-Image-Turbo'] },
  { id: 'auraflow', label: 'Pony V7 (AuraFlow)', family: 'auraflow', civitai: ['Pony V7', 'AuraFlow'], hf: ['purplesmartai/pony-v7-base', 'fal/AuraFlow-v0.3'] },
  { id: 'lumina2', label: 'Lumina 2', family: 'lumina', civitai: ['Lumina'], hf: ['Alpha-VLLM/Lumina-Image-2.0', 'neta-art/Neta-Lumina'] },
  { id: 'ideogram4', label: 'Ideogram 4', family: 'ideogram4', civitai: ['Ideogram 4.0'], hf: ['ideogram-ai/ideogram-4-fp8'] },
  { id: 'wan22_5b', label: 'Wan 2.2 5B (video)', family: 'wan', civitai: ['Wan Video 2.2 TI2V-5B'], hf: ['Wan-AI/Wan2.2-TI2V-5B'] },
  { id: 'wan22_14b', label: 'Wan 2.2 14B (video)', family: 'wan', civitai: ['Wan Video 2.2 I2V-A14B', 'Wan Video 2.2 T2V-A14B'], hf: ['Wan-AI/Wan2.2-I2V-A14B', 'Wan-AI/Wan2.2-T2V-A14B'] },
]

/** Any base: the finders search all of Civitai / Hugging Face (the model's check tells what this Mac can run). */
export const ALL_BASES: LoraBase = { id: 'all', label: '', family: '', civitai: [], hf: [''] }

export const loraBase = (id: string): LoraBase | undefined => id === ALL_BASES.id ? ALL_BASES : LORA_BASES.find((b) => b.id === id)

// the model groups the finders list the bases under, most used first (labels are product names, not translated)
const GROUP_OF: Record<string, string> = {
  sd1: 'Stable Diffusion', sd2: 'Stable Diffusion', sd3: 'Stable Diffusion', sdxl: 'SDXL',
  flux1: 'FLUX', chroma: 'FLUX', flux2: 'FLUX', flux3: 'FLUX', qwen_image: 'Qwen-Image', qwen_image21: 'Qwen-Image',
  z_image: 'Z-Image', krea2: 'Krea · Ideogram · ERNIE', ideogram4: 'Krea · Ideogram · ERNIE', ernie: 'Krea · Ideogram · ERNIE', anima: 'Anima · Lumina · Pony V7', lumina: 'Anima · Lumina · Pony V7', auraflow: 'Anima · Lumina · Pony V7',
  wan: 'Wan (video)',
}

/** The bases by model group, in the order of LORA_BASES. */
export const BASE_GROUPS: { label: string; bases: LoraBase[] }[] = [...new Set(LORA_BASES.map((b) => GROUP_OF[b.family] ?? b.label))]
  .map((label) => ({ label, bases: LORA_BASES.filter((b) => (GROUP_OF[b.family] ?? b.label) === label) }))

// the app's architectures (engines/diffusers/registry.py) and the base their LoRAs are made for
const BY_ARCH: Record<string, string> = {
  sd15: 'sd15', sd15_inpaint: 'sd15', sd21: 'sd2', sd21_base: 'sd2', sdxl: 'sdxl', sdxl_inpaint: 'sdxl', sd35_medium: 'sd35_medium',
  sd35_large: 'sd35_large', flux1_dev: 'flux1_dev', flux1_fill: 'flux1_dev', flux1_schnell: 'flux1_schnell', chroma: 'chroma', flux2_dev: 'flux2_dev',
  flux2_klein: 'flux2_klein4', flux3_klein: 'flux3_klein', qwen_image: 'qwen_image', qwen_image21: 'qwen_image21', krea2: 'krea2', anima: 'anima', lumina2: 'lumina2', ernie_image: 'ernie_image', auraflow: 'auraflow', auraflow_diffusers: 'auraflow',
  ideogram4: 'ideogram4', wan22_ti2v: 'wan22_5b', wan22_i2v_14b: 'wan22_14b', z_image: 'z_image_turbo',
}

// Civitai's base model of a checkpoint is more precise than the architecture: a Pony checkpoint is an SDXL
// model, but SDXL LoRAs rarely fit it. The first match counts.
const BY_CIVITAI: [RegExp, string][] = [
  [/pony ?v ?7|aura ?flow/i, 'auraflow'], [/pony(?! ?v7)/i, 'pony'], [/illustrious/i, 'illustrious'], [/noob/i, 'noobai'],
  [/flux\.?1.*krea/i, 'flux1_krea'], [/flux\.?1.*kontext/i, 'flux1_kontext'], [/flux\.?1 ?s/i, 'flux1_schnell'], [/flux\.?1/i, 'flux1_dev'],
  [/flux\.?3/i, 'flux3_klein'], [/^chroma/i, 'chroma'], [/flux\.?2.*klein.*9b/i, 'flux2_klein9'], [/flux\.?2.*klein/i, 'flux2_klein4'], [/flux\.?2/i, 'flux2_dev'],
  [/sd ?3\.5.*large/i, 'sd35_large'], [/sd ?3/i, 'sd35_medium'], [/sdxl/i, 'sdxl'], [/sd ?2/i, 'sd2'], [/sd ?1/i, 'sd15'],
  [/qwen ?2\.1/i, 'qwen_image21'], [/qwen/i, 'qwen_image'], [/krea ?2/i, 'krea2'], [/^anima/i, 'anima'], [/^lumina|neta/i, 'lumina2'], [/^ernie/i, 'ernie_image'], [/ideogram/i, 'ideogram4'],
  [/wan.*5b/i, 'wan22_5b'], [/wan.*14b/i, 'wan22_14b'],
  [/z[-_ ]?image[-_ ]?base/i, 'z_image_base'], [/z[-_ ]?image/i, 'z_image_turbo'],
]

/** The base a Civitai "baseModel" stands for; undefined when the app does not know it. */
export function baseOfCivitai(name: string | undefined): string | undefined {
  return name ? BY_CIVITAI.find(([re]) => re.test(name))?.[1] : undefined
}

/**
 * The base an installed model needs its LoRAs for: its Civitai base model when known, else its architecture
 * (with the name telling SDXL offspring and the larger FLUX.2 [klein] apart), else the first base of its family.
 */
export function baseOfModel(meta: Pick<ModelMeta, 'arch' | 'family'> & { variant?: string }, hints: { baseModel?: string; names?: string[] } = {}): LoraBase | undefined {
  const fromCivitai = baseOfCivitai(hints.baseModel)
  if (fromCivitai) return loraBase(fromCivitai)
  const names = (hints.names ?? []).join(' ').toLowerCase()
  let id = BY_ARCH[meta.arch]
  if (id === 'sdxl') id = /pony/.test(names) ? 'pony' : /illustrious/.test(names) ? 'illustrious' : /noob/.test(names) ? 'noobai' : id
  if (id === 'flux2_klein4' && (meta.variant === 'klein9b' || (!meta.variant && /9b/.test(names)))) id = 'flux2_klein9'
  // Z-Image (Base) by name, as the import tells it (registry.is_z_image_base); distilled ones are Turbo's
  if (id === 'z_image_turbo' && !/turbo|(^|[^a-z])zi[td]([^a-z]|$)|distill/.test(names)
    && /tongyi-mai\/z-image($|[ /])|z[-_ ]?image[-_ ]?base|(^|[^a-z])zib([^a-z]|$)/.test(names)) id = 'z_image_base'
  return (id ? loraBase(id) : undefined) ?? LORA_BASES.find((b) => b.family === meta.family)
}

/** The base of an installed model, from what its manifest knows. */
export const baseOfAsset = (a: Asset): LoraBase | undefined =>
  baseOfModel(a.meta, { baseModel: a.baseModel, names: [a.title, a.name, a.source?.ref ?? '', a.source?.file ?? ''] })

/** What a finder looks for: LoRAs, or whole models (checkpoints, fine-tunes) made from a base. */
export type FindKind = 'lora' | 'model'

/** One LoRA (or model) found on Civitai or Hugging Face. */
export interface LoraHit {
  source: 'civitai' | 'hf'
  /** what the import takes: the Civitai page with modelVersionId, or the Hugging Face repository */
  ref: string
  /** the page to open in the browser */
  page: string
  /** Hugging Face: the file the import takes, and the other .safetensors files of the repository (none: the whole
   *  repository, a model in diffusers' layout) */
  file?: string
  files?: string[]
  title: string
  version?: string
  author?: string
  /** the base model as the site names it */
  baseModel?: string
  downloads?: number
  likes?: number
  triggerWords: string[]
  sizeMb?: number
  /** a picture of it, loaded through the main process (loras:thumb) */
  previewUrl?: string
  /** the preview picture is marked as adult content: shown blurred until clicked */
  previewExplicit?: boolean
  /** the LoRA is marked as adult content */
  nsfw: boolean
  /** a short line on its licence */
  licence?: string
  /** the download needs an account (Civitai early access, gated Hugging Face repository) */
  needsToken?: boolean
  gated?: boolean
  installed: boolean
}

export interface LoraSearchRequest {
  /** a LoraBase id */
  base: string
  source: 'civitai' | 'hf'
  /** lora when missing */
  kind?: FindKind
  query?: string
  cursor?: string
}

export interface LoraSearchPage {
  hits: LoraHit[]
  /** for the next page; missing on the last one */
  cursor?: string
}

type Raw = Record<string, unknown>
const civitaiId = (ref: string): string | undefined => /civitai\.com\/models\/(\d+)/.exec(ref)?.[1]

/** Whether a LoRA (or model) found online is installed: the same Civitai model, or the same file of a Hugging Face repository. */
export function isInstalled(hit: Pick<LoraHit, 'source' | 'ref' | 'file'>, assets: Asset[], kind: FindKind = 'lora'): boolean {
  return assets.some((a) => {
    if (a.type !== kind || !a.source) return false
    if (hit.source === 'civitai') {
      const id = civitaiId(hit.ref)
      const own = (a.source as Raw).model_id
      return a.source.type === 'civitai' && !!id && (String(own ?? '') === id || civitaiId(a.source.ref) === id)
    }
    return a.source.type === 'hf' && a.source.ref === hit.ref && (!hit.file || !a.source.file || a.source.file === hit.file)
  })
}
