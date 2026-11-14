// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The form of the generate pages and how it becomes a job.

import { controlTypesFor } from '@shared/controlnet'
import { EDITION } from '@shared/edition'
import { MAX_REFERENCES } from '@shared/engine_job'
import { loraFits } from '@shared/lora_fit'
import { SIGMA_SCHEDULES, samplersFor } from '@shared/samplers'
import type { AiLabel, Asset, Job } from '@shared/types'
import { DEFAULT_SIZES, sizeForRatio, videoSize, type VideoResolution } from './sizes'
import { t, type PlainKey } from '../i18n'

export type Mode = 'text' | 'image' | 'inpaint' | 'video' | 'illusion'

export interface GenerateForm {
  prompt: string
  negativePrompt: string
  /** name of the style, '' for none */
  style: string
  modelId: string
  width: number
  height: number
  steps: number
  guidance: number
  /** null = a new random seed for every job */
  seed: number | null
  count: number
  sampler: string
  sigmaSchedule: string
  loras: { id: string; scale: number }[]
  /** how much of the input picture changes, 0..1 */
  strength: number
  inputImage: string
  /** further pictures beside the input picture, for a model that edits several together (takesReferences) */
  references: string[]
  /** with an input picture: use width and height instead of the picture's proportions */
  customSize: boolean
  /** the size chosen before a model that can not compute it changed it, and the size it was changed to: switching to a
   *  model that can brings it back, unless the size was changed by hand in between */
  sizeWanted?: { width: number; height: number; changedTo: [number, number] }
  /** video: length in seconds and the shorter side */
  videoSeconds: number
  videoResolution: VideoResolution
  /** illusion: how strongly the hidden pattern shows through */
  patternStrength: number
  /** control picture: its kind ('' for none), the file, whether it is a photo to prepare first, its weight */
  controlType: string
  controlImage: string
  controlPreprocess: boolean
  controlWeight: number
  /** the EU's icon for AI content in the lower right corner of the pictures */
  /** FLUX 3 Image Klein, text to image: the prompt upsampler writes the full caption from the prompt */
  upsample: boolean
  /** FLUX.2 [klein] 4B, image to image: the consistency LoRA keeps the picture while the prompt changes it */
  keepPicture: boolean
  /** SD 1.5 / SDXL (Diffusers): refine the faces after the picture (K4), and how strongly */
  faceDetail: boolean
  faceDetailStrength: number
  /** FLUX.1 [dev]: the Turbo-Alpha LoRA with its 8 steps (TURBO) */
  fast: boolean
  /** Inpainting: repaint the mask with a picture model, or remove the painted object (no model, no prompt) */
  inpaintAction: 'repaint' | 'remove'
  /** removing: Fast (LaMa), Thorough (RORem), Auto by the size of the mask, or With shadows (ObjectClear) */
  removeMethod: RemoveMethod
  aiLabel: boolean
  aiLabelSize: AiLabel['size']
  /** auto: "AI GENERATED" from a prompt, "AI MODIFIED" from a picture; ai: the round icon */
  aiLabelIcon: 'auto' | 'ai'
  aiLabelTone: AiLabel['tone']
  aiLabelSubtle: boolean
}

export type RemoveMethod = NonNullable<Job['removeObject']>['method']

const REMOVE_METHODS: { id: RemoveMethod; title: PlainKey }[] = [
  { id: 'lama', title: 'generate.remove.fast' }, { id: 'auto', title: 'generate.remove.auto' },
  { id: 'rorem', title: 'generate.remove.thorough' }, { id: 'objectclear', title: 'generate.remove.shadows' },
  { id: 'compare', title: 'generate.remove.compare' },
]
/** The remove methods this edition offers: ObjectClear is non-commercial (S-Lab License 1.0). */
export const removeMethods = (): typeof REMOVE_METHODS => REMOVE_METHODS.filter((m) => m.id !== 'objectclear' || !EDITION.commercialModelsOnly)

/** The helper model a remove method needs (engines/diffusers/helpers.json), '' for LaMa and Compare (it takes what is there). */
export const removeHelper = (method: RemoveMethod): string => (method === 'lama' || method === 'compare' ? '' : method === 'objectclear' ? 'objectclear' : 'rorem')

export const MAX_LORAS = 3
/** SD 1.5 and its pattern ControlNet work up to about this size */
const SD1_ILLUSION_MAX = 768

/** What a mode asks for and offers. */
/** The label of a job: "AI MODIFIED" where a picture of the user's is changed (Image, Inpaint), else "AI GENERATED". */
export function aiLabelOf(form: Pick<GenerateForm, 'aiLabelSize' | 'aiLabelIcon' | 'aiLabelTone' | 'aiLabelSubtle'>, mode: Mode): AiLabel {
  const kind = form.aiLabelIcon === 'ai' ? 'ai' : mode === 'image' || mode === 'inpaint' ? 'modified' : 'generated'
  return { size: form.aiLabelSize ?? 'medium', kind, tone: form.aiLabelTone ?? 'auto', subtle: !!form.aiLabelSubtle }
}

export const MODES: Record<Mode, { input: boolean; mask: boolean; size: boolean; styles: boolean; loras: boolean; sampler: boolean; count: boolean; promptNeeded: boolean; control: boolean }> = {
  text: { input: false, mask: false, size: true, styles: true, loras: true, sampler: true, count: true, promptNeeded: true, control: true },
  image: { input: true, mask: false, size: false, styles: true, loras: true, sampler: true, count: true, promptNeeded: true, control: true },
  inpaint: { input: true, mask: true, size: false, styles: true, loras: true, sampler: true, count: true, promptNeeded: false, control: false },
  video: { input: true, mask: false, size: false, styles: false, loras: false, sampler: false, count: false, promptNeeded: false, control: false },
  illusion: { input: false, mask: false, size: true, styles: true, loras: true, sampler: true, count: true, promptNeeded: true, control: false },
}

/** The form page settings of a job go back to: its own page, Text to image for jobs of the other pages. */
export const formPage = (page: string): Mode => (Object.hasOwn(MODES, page) ? (page as Mode) : 'text')

export function emptyForm(mode: Mode): GenerateForm {
  return {
    prompt: '', negativePrompt: '', style: '', modelId: '', width: 512, height: 512, steps: 25, guidance: 7, seed: null, count: 1,
    sampler: 'Default', sigmaSchedule: 'Default', loras: [], strength: mode === 'inpaint' ? 1 : 0.6, inputImage: '', references: [], customSize: false,
    videoSeconds: 2, videoResolution: '480p', patternStrength: 1.1,
    controlType: '', controlImage: '', controlPreprocess: true, controlWeight: 1, upsample: true, keepPicture: false, faceDetail: false, faceDetailStrength: 0.4, fast: false,
    inpaintAction: 'repaint', removeMethod: 'auto', aiLabel: false, aiLabelSize: 'medium', aiLabelIcon: 'auto', aiLabelTone: 'auto', aiLabelSubtle: false,
  }
}

// families whose pipelines can repaint a masked part (manifests of older imports do not say it)
const INPAINT_FAMILIES = ['sd1', 'sd2', 'sdxl', 'sd3', 'flux1', 'chroma', 'qwen_image', 'z_image']

/** Can the model repaint a masked part? What its manifest says, else what its family can. */
export const canInpaint = (m: Asset): boolean =>
  m.meta.inpaint === true || m.meta.inpaintOnly === true || (m.meta.inpaint === undefined && INPAINT_FAMILIES.includes(m.meta.family))

/** The models a page can use. */
export function modelsFor(mode: Mode, models: Asset[]): Asset[] {
  return models.filter((m) => {
    if (mode === 'video') return m.meta.kind === 'video'
    if (m.meta.kind !== 'image') return false
    if (mode === 'text') return !m.meta.inpaintOnly
    if (mode === 'image') return m.meta.img2img === true && !m.meta.inpaintOnly
    // the pattern ControlNet exists for these two families
    if (mode === 'illusion') return (m.meta.family === 'sdxl' || m.meta.family === 'sd1') && !m.meta.inpaintOnly
    return canInpaint(m)
  })
}

/** The LoRAs that fit a model: made for its family, and for its size where a family has several (FLUX.2 [klein] 4B / 9B). */
export const lorasFor = (model: Asset | undefined, loras: Asset[]): Asset[] =>
  model ? loras.filter((l) => loraFits(l, model)) : []

const num = (v: unknown, fallback: number): number => (typeof v === 'number' && Number.isFinite(v) ? v : fallback)

/** What a model suggests: its steps, guidance and size, and the sampler, sigma schedule and negative prompt its maker
 *  recommends (manifest defaults, read from the model card on import: engines/diffusers/maker_settings.py). A sampler
 *  the model can not take here counts as "Default". */
export function modelDefaults(model: Asset): { steps: number; guidance: number; width: number; height: number; sampler: string; sigmaSchedule: string; negativePrompt?: string } {
  const d = model.meta.defaults ?? {}
  const sampler = typeof d.sampler === 'string' && samplersFor(model.meta)?.includes(d.sampler) ? d.sampler : 'Default'
  const sigmaSchedule = sampler !== 'Default' && typeof d.sigma_schedule === 'string' && SIGMA_SCHEDULES.includes(d.sigma_schedule) ? d.sigma_schedule : 'Default'
  return {
    steps: num(d.num_steps, 25), guidance: num(d.guidance_scale, 7), width: num(d.width, 1024), height: num(d.height, 1024), sampler, sigmaSchedule,
    ...(typeof d.negative_prompt === 'string' && d.negative_prompt ? { negativePrompt: d.negative_prompt } : {}),
  }
}

/** Steps, guidance, size, sampler and the maker's negative prompt as the model suggests them ("Model defaults"). */
export function applyDefaults(form: GenerateForm, model: Asset): void {
  const { negativePrompt, ...rest } = modelDefaults(model)
  Object.assign(form, rest)
  if (negativePrompt) form.negativePrompt = negativePrompt
  form.sizeWanted = undefined
}

/**
 * Switches the form to a model. Without a previous model (a fresh form) it takes the model's defaults. From a previous
 * model steps, guidance, seed and size stay as they are, so that models can be compared with the same settings;
 * "Model defaults" brings the new model's suggestions. Only a size the new model can not compute changes, to the
 * nearest one it can in the same proportions. The sampler stays chosen: a model without it uses its default, and
 * switching back brings it back. What the new model can not take goes: LoRAs of another family, a control type it has not.
 */
export function applyModel(form: GenerateForm, model: Asset, loras: Asset[], previous?: Asset): void {
  const d = model.meta.defaults ?? {}
  form.modelId = model.id
  if (!previous) {
    // a sampler chosen before stays unless the maker recommends one
    const { sampler, sigmaSchedule } = form
    applyDefaults(form, model)
    if (form.sampler === 'Default') Object.assign(form, { sampler, sigmaSchedule })
    form.sizeWanted = undefined
  } else {
    const sizes = model.meta.resolutions?.length ? model.meta.resolutions : DEFAULT_SIZES
    const w = form.sizeWanted
    // a size set by hand after the last change counts, not the one wanted before
    const wanted = w && w.changedTo[0] === form.width && w.changedTo[1] === form.height ? w : { width: form.width, height: form.height }
    if (sizes.includes(wanted.width) && sizes.includes(wanted.height)) {
      form.width = wanted.width
      form.height = wanted.height
      form.sizeWanted = undefined
    } else {
      const { width, height } = modelDefaults(model)
      ;[form.width, form.height] = sizeForRatio({ w: wanted.width || width, h: wanted.height || height }, width, height, sizes)
      form.sizeWanted = { width: wanted.width, height: wanted.height, changedTo: [form.width, form.height] }
    }
  }
  if (typeof d.negative_prompt === 'string' && !form.negativePrompt) form.negativePrompt = d.negative_prompt
  const fitting = new Set(lorasFor(model, loras).map((l) => l.id))
  form.loras = form.loras.filter((l) => fitting.has(l.id))
  if (!controlTypesFor(model.meta).some((ct) => ct.id === form.controlType)) form.controlType = ''
}

/** Inpainting in Remove: the painted object goes, filled from its surroundings; no model, prompt or steps. */
export const removes = (mode: Mode, form: Pick<GenerateForm, 'inpaintAction'>): boolean => mode === 'inpaint' && form.inpaintAction === 'remove'

/** Why the form can not be sent yet, or '' when it can. */
export function formProblem(mode: Mode, form: GenerateForm, model: Asset | undefined, hasMask: boolean): string {
  if (removes(mode, form)) return !form.inputImage ? t('generate.problem.choosePicture') : hasMask ? '' : t('generate.remove.paintObject')
  if (!model) return t('generate.problem.chooseModel')
  // a model the app recognised but can not run yet (manifest field unsupported) says so before anything is sent
  if (model.meta.unsupported) return model.meta.unsupported
  if (MODES[mode].input && !form.inputImage) return mode === 'video' ? t('generate.problem.chooseStartPicture') : t('generate.problem.choosePicture')
  if (MODES[mode].mask && !hasMask) return t('generate.problem.paintMask')
  if (MODES[mode].promptNeeded && !form.prompt.trim()) return t('generate.problem.describe')
  if (MODES[mode].control && form.controlType && !form.controlImage) return t('generate.problem.chooseControl')
  // Fast adds Turbo-Alpha as one of the LoRAs: one of the user's own was dropped silently before
  if (form.fast && takesTurbo(model.meta) && form.loras.length >= MAX_LORAS) return t('generate.problem.tooManyForFast', { n: MAX_LORAS - 1 })
  return ''
}

export interface JobExtras {
  maskImage?: string
  /** width and height of the input picture */
  inputSize?: [number, number]
  /** illusion: the file of the hidden pattern */
  patternImage?: string
}

/** FLUX 3 Image Klein reads full scene captions: its prompt upsampler writes one from a short prompt (MLX runtime);
 * ERNIE-Image brings its own prompt enhancer, which does the same. */
/**
 * The fast option of FLUX.1 [dev] and its fine-tunes: alimama's step-distilling LoRA (FLUX.1-dev non-commercial
 * licence), 8 steps at guidance 3.5 as its card says. On the 16 GB Mac mini a 1024 px picture took 4:18 instead of
 * 11:04 min (28 steps), each step 34 % longer beside the 4 bit weights (MEASUREMENTS 7be).
 */
export const TURBO = { ref: 'alimama-creative/FLUX.1-Turbo-Alpha', file: 'diffusion_pytorch_model.safetensors', name: 'FLUX.1-Turbo-Alpha', steps: 8, guidance: 3.5, scale: 1 }
export const takesTurbo = (meta: Asset['meta'] | undefined): boolean => meta?.arch === 'flux1_dev'
/** The installed Turbo-Alpha LoRA, by where it came from (its folder may be renamed). */
export const turboLora = (loras: Asset[]): Asset | undefined => loras.find((l) => l.source?.ref === TURBO.ref)

/** FLUX.2 [klein] edits keep closer to the picture with the consistency LoRA (made for 4B; 9B edits without it). */
export const keepsPicture = (meta: Asset['meta'] | undefined): boolean => meta?.arch === 'flux2_klein'

/** The face detailer paints small faces again with the model itself: SD 1.5 and SDXL on the Diffusers engine. */
export const takesFaceDetail = (meta: Asset['meta'] | undefined): boolean =>
  (meta?.family === 'sd1' || meta?.family === 'sdxl') && meta.runtime === 'diffusers'

export const takesUpsampler = (meta: Asset['meta'] | undefined): boolean => meta?.arch === 'flux3_klein' || meta?.arch === 'ernie_image'

/** The helper model that writes the caption for a model (Models → Helper models). */
export const upsamplerHelper = (meta: Asset['meta'] | undefined): string => (meta?.arch === 'ernie_image' ? 'ernie_pe' : 'flux3_pup')

/** Fibo 2.0 edits the input picture together with further ones (<image_2> …), on Image to image. */
export const takesReferences = (meta: Asset['meta'] | undefined): boolean => meta?.family === 'fibo2'

export function buildJob(mode: Mode, form: GenerateForm, model: Asset, loras: Asset[], opts: JobExtras = {}): Omit<Job, 'id'> {
  const does = MODES[mode]
  const job: Omit<Job, 'id'> = {
    page: mode, prompt: form.prompt.trim(), modelId: model.id, modelDir: model.folder,
    width: form.width, height: form.height, steps: form.steps, guidance: form.guidance, seed: form.seed ?? -1,
  }
  if (model.meta.negativePrompt && form.negativePrompt.trim()) job.negativePrompt = form.negativePrompt.trim()
  if (does.styles && form.style) job.style = form.style
  if (does.sampler && form.sampler !== 'Default' && samplersFor(model.meta)?.includes(form.sampler)) {
    job.sampler = form.sampler
    if (form.sigmaSchedule !== 'Default') job.sigmaSchedule = form.sigmaSchedule
  }
  const chosen = form.loras
    .map((l) => ({ asset: loras.find((a) => a.id === l.id), scale: Number.isFinite(Number(l.scale)) && String(l.scale) !== '' ? Number(l.scale) : 1 }))
    .filter((l): l is { asset: Asset; scale: number } => !!l.asset && loraFits(l.asset, model))
  if (does.loras && chosen.length) job.loras = chosen.slice(0, MAX_LORAS).map((l) => ({ path: l.asset.folder, scale: l.scale }))
  const turbo = form.fast && does.loras && takesTurbo(model.meta) ? turboLora(loras) : undefined
  if (turbo) {
    job.steps = TURBO.steps
    job.guidance = TURBO.guidance
    if (!job.loras?.some((l) => l.path === turbo.folder)) job.loras = [...(job.loras ?? []).slice(0, MAX_LORAS - 1), { path: turbo.folder, scale: TURBO.scale }]
  }
  if (form.aiLabel && mode !== 'video') job.aiLabel = aiLabelOf(form, mode)
  if (form.upsample && mode === 'text' && takesUpsampler(model.meta)) job.upsample = true
  if (form.faceDetail && (mode === 'text' || mode === 'image') && takesFaceDetail(model.meta)) job.faceDetail = form.faceDetailStrength

  if (mode === 'video') {
    job.inputImage = form.inputImage
    job.videoSeconds = form.videoSeconds
    ;[job.width, job.height] = videoSize(opts.inputSize, form.videoResolution)
  } else if (mode === 'illusion') {
    if (model.meta.family === 'sd1') {
      const f = Math.min(1, SD1_ILLUSION_MAX / Math.max(form.width, form.height))
      job.width = Math.round((form.width * f) / 64) * 64
      job.height = Math.round((form.height * f) / 64) * 64
    }
    job.controlnet = { type: 'Illusion', image: opts.patternImage ?? '', weight: form.patternStrength, preprocess: false }
  } else if (does.input) {
    job.inputImage = form.inputImage
    job.strength = form.strength
    const refs = form.references.filter(Boolean).slice(0, MAX_REFERENCES)
    if (mode === 'image' && takesReferences(model.meta) && refs.length) job.referenceImages = refs
    if (mode === 'image' && form.keepPicture && keepsPicture(model.meta)) job.keepPicture = true
    if (mode === 'inpaint') {
      job.maskImage = opts.maskImage
    } else if (form.customSize) {
      job.exactSize = true
    } else if (opts.inputSize) {
      // the engine keeps the proportions of the picture; these numbers only describe the job
      ;[job.width, job.height] = opts.inputSize
    }
  }
  if (does.control && form.controlType && form.controlImage && controlTypesFor(model.meta).some((ct) => ct.id === form.controlType)) {
    job.controlnet = { type: form.controlType, image: form.controlImage, weight: form.controlWeight, preprocess: form.controlPreprocess }
    // text to image keeps the chosen size; with an input picture the engine sizes after that
  }
  return job
}

/** Removing the painted object (Inpainting → Remove): one picture of the input picture's size. */
export function buildRemoveJob(form: GenerateForm, opts: JobExtras = {}): Omit<Job, 'id'> {
  const [width, height] = opts.inputSize ?? [form.width, form.height]
  const job: Omit<Job, 'id'> = {
    page: 'inpaint', prompt: '', modelId: '', modelDir: '', width, height, seed: form.seed ?? -1,
    inputImage: form.inputImage, maskImage: opts.maskImage, removeObject: { method: form.removeMethod },
    label: 'Object removed', // i18n-ok: stored in English, shown by jobLabel()
  }
  if (form.aiLabel) job.aiLabel = aiLabelOf(form, 'inpaint')
  return job
}

/** The installed model an earlier job used: by folder, by id, or by the folder's name when the models moved. */
export function modelOfJob(job: Pick<Job, 'modelDir' | 'modelId'>, models: Asset[]): Asset | undefined {
  const name = job.modelDir.split('/').filter(Boolean).pop()
  return models.find((m) => m.folder === job.modelDir)
    ?? models.find((m) => job.modelId && m.id === job.modelId)
    ?? (name ? models.find((m) => m.folder.split('/').pop() === name) : undefined)
}

/** Prompt and settings of an earlier job, back in the form. */
export function applyJob(form: GenerateForm, job: Job, models: Asset[], loras: Asset[]): void {
  form.prompt = job.prompt
  form.negativePrompt = job.negativePrompt ?? ''
  form.style = job.style ?? ''
  const model = modelOfJob(job, models)
  if (model) form.modelId = model.id
  if (job.width && job.height && !job.videoSeconds) [form.width, form.height] = [job.width, job.height]
  if (job.steps) form.steps = job.steps
  if (job.guidance !== undefined) form.guidance = job.guidance
  form.seed = job.seed >= 0 ? job.seed : null
  // the reused job's size stays when the model changes next
  form.sizeWanted = undefined
  form.sampler = job.sampler ?? 'Default'
  form.sigmaSchedule = job.sigmaSchedule ?? 'Default'
  if (job.strength !== undefined) form.strength = job.strength
  form.keepPicture = !!job.keepPicture
  form.faceDetail = job.faceDetail !== undefined
  if (job.faceDetail !== undefined) form.faceDetailStrength = job.faceDetail
  form.inpaintAction = job.removeObject ? 'remove' : 'repaint'
  // a method this build does not offer (ObjectClear in a build with commercially usable models only) falls back to Auto
  if (job.removeObject) form.removeMethod = removeMethods().some((m) => m.id === job.removeObject!.method) ? job.removeObject.method : 'auto'
  if (job.videoSeconds) form.videoSeconds = job.videoSeconds
  if (job.controlnet?.type === 'Illusion') {
    form.patternStrength = job.controlnet.weight
  } else if (job.controlnet) {
    form.controlType = job.controlnet.type
    form.controlImage = job.controlnet.image
    form.controlPreprocess = job.controlnet.preprocess
    form.controlWeight = job.controlnet.weight
  } else {
    form.controlType = ''
  }
  form.references = [...(job.referenceImages ?? [])]
  form.loras = (job.loras ?? [])
    .map((l) => ({ id: modelOfJob({ modelDir: l.path, modelId: '' }, loras)?.id ?? '', scale: l.scale }))
    .filter((l) => l.id)
}
