// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { modelVariant } from './lora_fit'
import type { ModelMeta } from './types'

/** Restore: klein 9B tints a black-and-white or sepia photo in the repair; 4B with the consistency LoRA keeps its colour. */
export const kleinTints = (monochrome: boolean, meta?: Pick<ModelMeta, 'arch' | 'variant'>): boolean =>
  monochrome && !!meta && modelVariant(meta) === 'klein9b'

/** Restore: the consistency LoRA is made for FLUX.2 [klein] 4B; for 9B the option would only add a note to each repair. */
export const takesConsistency = (meta?: Pick<ModelMeta, 'arch' | 'variant'>): boolean =>
  !!meta && meta.arch === 'flux2_klein' && modelVariant(meta) === 'klein4b'

/** Inpainting: FLUX.1 [dev] and [schnell] leave a faint outline, FLUX.1 Fill does not (MEASUREMENTS 7bf). */
export const flux1Outline = (mode: string, meta?: Pick<ModelMeta, 'family' | 'inpaintOnly'>): boolean =>
  mode === 'inpaint' && meta?.family === 'flux1' && !meta.inpaintOnly
