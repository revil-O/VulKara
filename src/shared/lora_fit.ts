// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Which LoRAs fit which model: the same family (engines/diffusers/registry.py lora_identity) and, where a family
// has models of different sizes, the same sub-base (FLUX.2 [klein] 4B / [klein] 9B / [dev], Wan 5B / 14B). The
// engines check the same before they load a LoRA (registry.lora_mismatch).

import type { Asset, ModelMeta } from './types'

/** The names of the LoRA families, also of those no model of the app can use yet. */
export const FAMILY_TITLES: Record<string, string> = {
  sd1: 'SD 1.x', sd2: 'SD 2.x', sdxl: 'SDXL', sd3: 'SD 3.5', flux1: 'FLUX.1', flux2: 'FLUX.2', flux3: 'FLUX 3', krea2: 'Krea 2',
  ideogram4: 'Ideogram 4', anima: 'Anima', qwen_image: 'Qwen-Image', qwen_image21: 'Qwen-Image 2.1', wan: 'Wan',
  chroma: 'Chroma', z_image: 'Z-Image', lumina: 'Lumina 2', ernie: 'ERNIE-Image', hidream: 'HiDream', hidream_o1: 'HiDream-O1',
  hunyuan_video: 'HunyuanVideo', hunyuan_dit: 'Hunyuan-DiT', auraflow: 'AuraFlow', moss_image: 'MOSS-Image', fibo2: 'Fibo 2.0',
}

export const VARIANT_TITLES: Record<string, string> = {
  klein4b: 'FLUX.2 [klein] 4B', klein9b: 'FLUX.2 [klein] 9B', dev: 'FLUX.2 [dev]', '5b': 'Wan 5B', '14b': 'Wan 14B', '1.3b': 'Wan 1.3B',
}

/** The name of a family, or of its sub-base when there is one. */
export const familyTitle = (family: string, variant?: string): string =>
  (variant && VARIANT_TITLES[variant]) || FAMILY_TITLES[family] || family || 'Other'

// the sub-base an architecture always has (FLUX.2 [klein] comes in two sizes: its manifest says which)
const ARCH_VARIANT: Record<string, string> = { flux2_dev: 'dev', wan22_ti2v: '5b', wan22_i2v_14b: '14b' }

/** The sub-base of an installed model its LoRAs must match, undefined when its family has none or it is not known. */
export const modelVariant = (meta: Pick<ModelMeta, 'arch' | 'variant'>): string | undefined => meta.variant || ARCH_VARIANT[meta.arch]

/** Whether a LoRA fits a model: its family, and its sub-base when both know theirs. */
export function loraFits(lora: Pick<Asset, 'meta'>, model: Pick<Asset, 'meta'>): boolean {
  if (model.meta.noLoras || model.meta.unsupported) return false
  if (lora.meta.family !== model.meta.family) return false
  const lv = lora.meta.variant
  const mv = modelVariant(model.meta)
  return !lv || !mv || lv === mv
}
