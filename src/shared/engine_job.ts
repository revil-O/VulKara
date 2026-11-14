// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// A job of the app in the field names the engines take (protocol v2, "generate").

import { applyStyle } from './styles'
import type { Job } from './types'

/** further pictures beside the input picture an edit model takes at most (Fibo 2.0 edits four together) */
export const MAX_REFERENCES = 3

export function toEngineJob(job: Job): Record<string, unknown> {
  const styled = applyStyle(job.style, job.prompt, job.negativePrompt)
  const out: Record<string, unknown> = {
    prompt: styled.prompt,
    model_dir: job.modelDir,
    width: job.width,
    height: job.height,
    seed: job.seed,
    count: 1,
  }
  const optional: [string, unknown][] = [
    ['negative_prompt', styled.negative],
    ['num_steps', job.steps],
    ['guidance_scale', job.guidance],
    ['sampler', job.sampler],
    ['sigma_schedule', job.sigmaSchedule],
    ['input_image', job.inputImage],
    ['mask_image', job.maskImage],
    ['reference_images', job.referenceImages?.length ? job.referenceImages : undefined],
    ['video_seconds', job.videoSeconds],
    ['upscale', job.upscale],
    ['upsample', job.upsample],
    ['keep_picture', job.keepPicture],
    // the remote web UI may send anything: a number within the detailer's range (20–60 %), else no detailing
    ['face_detail', Number.isFinite(job.faceDetail) && (job.faceDetail as number) > 0 ? Math.min(0.6, Math.max(0.2, job.faceDetail as number)) : undefined],
  ]
  for (const [key, value] of optional) if (value !== undefined && value !== '') out[key] = value
  if (job.inputImage) {
    if (job.strength !== undefined) out[job.maskImage ? 'inpaint_strength' : 'strength'] = job.strength
    if (job.exactSize) out.exact_size = true
    if (job.prefill) out.prefill = true
  }
  if (job.photoTool) {
    const t = job.photoTool
    out.photo_tool = { folder: t.folder, strength: t.strength ?? 1, factor: t.factor, variant: t.variant, quality: t.quality, output: t.output ?? 'cutout', mask: t.mask }
  }
  if (job.removeObject) out.remove_object = { method: job.removeObject.method, objectclear: job.removeObject.objectclear === true }
  if (job.restore) {
    const r = job.restore
    out.restore = {
      correct: r.correct, repair: r.repair, colorize: r.colorize, color_strength: r.colorStrength, sharpen: r.sharpen, sharpness: r.sharpness,
      lock: r.lock, max_change: r.maxChange, rules: r.rules, check_faces: r.checkFaces,
      correct_strength: r.correctStrength ?? 0.8, dust: !!r.dust, dust_sensitivity: r.dustSensitivity ?? 0.5, details: !!r.details, detail_level: r.detailLevel ?? 2,
      detail_strength: r.detailStrength ?? 1, faces: !!r.faces, face_fidelity: r.faceFidelity ?? 0.9,
      face_strength: r.faceStrength ?? 0.6, scale: r.scale === 2 ? 2 : 1, preview: r.preview,
      face_points: r.facePoints, consistency: !!r.consistency,
    }
  }
  if (job.loras?.length) out.loras = job.loras.map((l) => ({ path: l.path, scale: l.scale }))
  if (job.controlnet) {
    out.controlnet_model = job.controlnet.type
    out.controlnet_image = job.controlnet.image
    out.controlnet_weight = job.controlnet.weight
    out.controlnet_preprocess = job.controlnet.preprocess
  }
  return out
}
