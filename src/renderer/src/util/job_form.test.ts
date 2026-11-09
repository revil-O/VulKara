// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { TURBO, aiLabelOf, applyDefaults, applyJob, applyModel, buildJob, emptyForm, keepsPicture, formPage, formProblem, lorasFor, modelsFor, takesTurbo, takesUpsampler, upsamplerHelper } from './job_form'
import type { Asset, ModelMeta } from '@shared/types'

const model = (id: string, meta: Partial<ModelMeta> = {}): Asset => ({
  id: 'model:' + id, title: id, name: id, folder: '/models/' + id, type: 'model',
  meta: { arch: 'sdxl', family: 'sdxl', label: 'SDXL', runtime: 'diffusers', kind: 'image', negativePrompt: true, img2img: true, inpaint: true,
    defaults: { num_steps: 30, guidance_scale: 6, width: 1024, height: 1024 }, ...meta },
})
const lora = (id: string, family: string): Asset => ({
  id: 'lora:' + id, title: id, name: id, folder: '/loras/' + id, type: 'lora',
  meta: { arch: '', family, label: '', runtime: 'diffusers', kind: 'image' },
})
const SDXL = model('xl')
const FLUX = model('flux', { arch: 'flux1_schnell', family: 'flux1', negativePrompt: false, inpaint: false, defaults: { num_steps: 4, guidance_scale: 0, width: 1024, height: 1024 } })
const VIDEO = model('wan', { kind: 'video' })
const FLUX3 = model('flux3', { arch: 'flux3_klein', family: 'flux3', runtime: 'mlx', negativePrompt: false, inpaint: false, defaults: { num_steps: 16, guidance_scale: 1, width: 1024, height: 1024 } })
const LORAS = [lora('a', 'sdxl'), lora('b', 'flux1')]

describe('the fast option of FLUX.1 [dev]', () => {
  const DEV = model('dev', { arch: 'flux1_dev', family: 'flux1', negativePrompt: false, defaults: { num_steps: 28, guidance_scale: 3.5, width: 1024, height: 1024 } })
  const turbo: Asset = { ...lora('turbo', 'flux1'), source: { type: 'hf', ref: TURBO.ref, file: TURBO.file } }
  it('says so instead of dropping one of three LoRAs of the user for Turbo-Alpha', () => {
    const three = { ...emptyForm('text'), prompt: 'a cat', fast: true, loras: [{ id: 'a', scale: 1 }, { id: 'b', scale: 1 }, { id: 'c', scale: 1 }] }
    expect(formProblem('text', three, DEV, false)).toMatch(/Turbo-Alpha/)
    expect(formProblem('text', { ...three, loras: three.loras.slice(0, 2) }, DEV, false)).toBe('')
    expect(formProblem('text', { ...three, fast: false }, DEV, false)).toBe('')
  })

  it('adds the Turbo-Alpha LoRA with its 8 steps and guidance 3.5, only for FLUX.1 [dev]', () => {
    const form = { ...emptyForm('text'), prompt: 'x', steps: 28, guidance: 4, fast: true }
    const job = buildJob('text', form, DEV, [turbo])
    expect([job.steps, job.guidance, job.loras]).toEqual([8, 3.5, [{ path: '/loras/turbo', scale: 1 }]])
    expect(buildJob('text', { ...form, fast: false }, DEV, [turbo]).steps).toBe(28)
    expect(buildJob('text', form, DEV, []).steps).toBe(28)  // not downloaded: the page says so
    expect(takesTurbo(DEV.meta) && !takesTurbo(FLUX.meta)).toBe(true)  // schnell is distilled already
  })
})

describe('generate form', () => {
  it('sends further pictures with the input picture only to a model that edits several together (Fibo 2.0)', () => {
    const FIBO = model('fibo', { arch: 'fibo2', family: 'fibo2', runtime: 'comfyui', negativePrompt: false })
    const form = { ...emptyForm('image'), inputImage: '/a.png', references: ['/b.png', '', '/c.png', '/d.png', '/e.png'] }
    expect(buildJob('image', form, FIBO, []).referenceImages).toEqual(['/b.png', '/c.png', '/d.png'])
    expect(buildJob('image', form, SDXL, []).referenceImages).toBeUndefined()
    expect(buildJob('inpaint', { ...form, inputImage: '/a.png' }, FIBO, [], { maskImage: '/m.png' }).referenceImages).toBeUndefined()
    const back = emptyForm('image')
    applyJob(back, { ...buildJob('image', form, FIBO, []), id: 'j' }, [FIBO], [])
    expect(back.references).toEqual(['/b.png', '/c.png', '/d.png'])
  })

  it('labels a picture made from a prompt AI GENERATED and a changed picture of the user AI MODIFIED', () => {
    const form = { ...emptyForm('text'), aiLabel: true }
    expect(aiLabelOf(form, 'text')).toEqual({ size: 'medium', kind: 'generated', tone: 'auto', subtle: false })
    expect(aiLabelOf(form, 'illusion').kind).toBe('generated')
    expect(aiLabelOf(form, 'image').kind).toBe('modified')
    expect(aiLabelOf(form, 'inpaint').kind).toBe('modified')
    expect(aiLabelOf({ ...form, aiLabelIcon: 'ai', aiLabelTone: 'white', aiLabelSubtle: true, aiLabelSize: 'large' }, 'image'))
      .toEqual({ size: 'large', kind: 'ai', tone: 'white', subtle: true })
  })

  it('offers the models a page can use', () => {
    const all = [SDXL, FLUX, VIDEO]
    expect(modelsFor('text', all).map((m) => m.title)).toEqual(['xl', 'flux'])
    expect(modelsFor('inpaint', all).map((m) => m.title)).toEqual(['xl'])
  })

  it('sends the settings of a job back to its own form page, else to Text to image', () => {
    expect(['inpaint', 'video', 'canvas', 'lora', 'toString'].map(formPage)).toEqual(['inpaint', 'video', 'text', 'text', 'text'])
  })

  it('takes the defaults of a model and drops what does not fit', () => {
    const form = { ...emptyForm('text'), sampler: 'DPM++ 2M SDE', loras: [{ id: 'lora:a', scale: 1 }] }
    applyModel(form, FLUX, LORAS)
    expect(form).toMatchObject({ steps: 4, guidance: 0, width: 1024, sampler: 'DPM++ 2M SDE', loras: [] })
  })

  it('keeps steps, guidance, seed and size when the model changes, to compare models with the same settings', () => {
    const form = { ...emptyForm('text') }
    const sizes = Array.from({ length: 17 }, (_, i) => 512 + i * 64)
    const flux = { ...FLUX, meta: { ...FLUX.meta, resolutions: sizes } }
    const xl = { ...SDXL, meta: { ...SDXL.meta, resolutions: sizes } }
    applyModel(form, xl, LORAS)
    Object.assign(form, { width: 1344, height: 768, steps: 40, prompt: 'a fox', seed: 7, count: 3 })
    applyModel(form, flux, LORAS, xl)
    expect(form).toMatchObject({ steps: 40, guidance: 6, width: 1344, height: 768, prompt: 'a fox', seed: 7, count: 3 })
    applyModel(form, xl, LORAS, flux)
    expect(form).toMatchObject({ steps: 40, guidance: 6, width: 1344, height: 768, seed: 7 })
    // the defaults of the model left as they are stay too: switching does not change them either
    const fresh = { ...emptyForm('text') }
    applyModel(fresh, SDXL, LORAS)
    applyModel(fresh, FLUX, LORAS, SDXL)
    expect(fresh).toMatchObject({ steps: 30, guidance: 6, width: 1024, height: 1024 })
  })

  it('changes only a size the new model can not compute, in the same proportions', () => {
    const form = { ...emptyForm('text') }
    const sd15 = model('sd15', { family: 'sd1', resolutions: [512, 576, 640, 704, 768], defaults: { num_steps: 25, guidance_scale: 7, width: 512, height: 512 } })
    applyModel(form, SDXL, LORAS)
    Object.assign(form, { width: 1344, height: 768, steps: 40 })
    applyModel(form, sd15, LORAS, SDXL)
    expect(form.steps).toBe(40)
    expect([512, 576, 640, 704, 768]).toContain(form.width)
    expect(form.width / form.height).toBeCloseTo(1344 / 768, 0)
    // back on a model that can: the size chosen before comes back
    applyModel(form, { ...SDXL, meta: { ...SDXL.meta, resolutions: Array.from({ length: 17 }, (_, i) => 512 + i * 64) } }, LORAS, sd15)
    expect([form.width, form.height]).toEqual([1344, 768])
  })

  it('does not bring an old size back when the size was changed by hand in between', () => {
    const form = { ...emptyForm('text') }
    const xl = { ...SDXL, meta: { ...SDXL.meta, resolutions: Array.from({ length: 17 }, (_, i) => 512 + i * 64) } }
    const sd15 = model('sd15', { family: 'sd1', resolutions: [512, 576, 640, 704, 768], defaults: { num_steps: 25, guidance_scale: 7, width: 512, height: 512 } })
    applyModel(form, xl, LORAS)
    Object.assign(form, { width: 1344, height: 768 })
    applyModel(form, sd15, LORAS, xl)
    Object.assign(form, { width: 640, height: 640 })
    applyModel(form, xl, LORAS, sd15)
    expect([form.width, form.height]).toEqual([640, 640])
  })

  it("brings the model's suggestions with Model defaults", () => {
    const form = { ...emptyForm('text') }
    applyModel(form, SDXL, LORAS)
    applyModel(form, FLUX, LORAS, SDXL)
    applyDefaults(form, FLUX)
    expect(form).toMatchObject({ steps: 4, guidance: 0, width: 1024, height: 1024 })
  })

  it("takes the maker's sampler, schedule and negative prompt as the model's defaults", () => {
    const MAKER = model('rv', { defaults: { num_steps: 5, guidance_scale: 1.5, width: 1024, height: 1024, sampler: 'DPM++ SDE', sigma_schedule: 'Karras', negative_prompt: 'cartoon' } })
    const form = { ...emptyForm('text') }
    applyModel(form, MAKER, LORAS)
    expect(form).toMatchObject({ steps: 5, guidance: 1.5, sampler: 'DPM++ SDE', sigmaSchedule: 'Karras', negativePrompt: 'cartoon' })
    Object.assign(form, { sampler: 'Euler', sigmaSchedule: 'Default', negativePrompt: '' })
    applyDefaults(form, SDXL)
    expect(form).toMatchObject({ sampler: 'Default', sigmaSchedule: 'Default', negativePrompt: '' })
    applyDefaults(form, MAKER)
    expect(form).toMatchObject({ sampler: 'DPM++ SDE', sigmaSchedule: 'Karras', negativePrompt: 'cartoon' })
    // a sampler the model can not take is no default
    const odd = model('odd', { defaults: { num_steps: 4, guidance_scale: 1, sampler: 'Euler a', sigma_schedule: 'Karras' }, family: 'flux1' })
    applyDefaults(form, odd)
    expect(form).toMatchObject({ sampler: 'Default', sigmaSchedule: 'Default' })
  })

  it('builds a job', () => {
    const form = { ...emptyForm('text'), prompt: ' a fox ', negativePrompt: 'blurry', style: 'Anime', sampler: 'Euler a', sigmaSchedule: 'Karras', loras: [{ id: 'lora:a', scale: 0.8 }, { id: 'lora:b', scale: 1 }] }
    applyModel(form, SDXL, LORAS)
    expect(buildJob('text', form, SDXL, LORAS)).toEqual({
      page: 'text', prompt: 'a fox', modelId: 'model:xl', modelDir: '/models/xl', width: 1024, height: 1024, steps: 30, guidance: 6,
      seed: -1, negativePrompt: 'blurry', style: 'Anime', sampler: 'Euler a', sigmaSchedule: 'Karras', loras: [{ path: '/loras/a', scale: 0.8 }],
    })
    const flux = buildJob('text', { ...form, sampler: 'Euler a' }, FLUX, LORAS)
    expect(flux.negativePrompt).toBeUndefined()
    expect(flux.sampler).toBeUndefined()
  })

  it('asks for the prompt upsampler only with FLUX 3 on Text to image, and only when it is on', () => {
    const form = { ...emptyForm('text'), prompt: 'a fox' }
    applyModel(form, FLUX3, [])
    expect(form.upsample).toBe(true)
    expect(buildJob('text', form, FLUX3, []).upsample).toBe(true)
    expect(buildJob('text', { ...form, upsample: false }, FLUX3, []).upsample).toBeUndefined()
    expect(buildJob('image', { ...emptyForm('image'), prompt: 'x', inputImage: '/in.png' }, FLUX3, []).upsample).toBeUndefined()
    const ERNIE = model('ernie', { arch: 'ernie_image', family: 'ernie', runtime: 'mlx', negativePrompt: true, inpaint: false, defaults: { num_steps: 8, guidance_scale: 1, width: 1024, height: 1024 } })
    expect(takesUpsampler(ERNIE.meta) && upsamplerHelper(ERNIE.meta)).toBe('ernie_pe')
    expect(upsamplerHelper(FLUX3.meta)).toBe('flux3_pup')
    expect(buildJob('text', form, ERNIE, []).upsample).toBe(true)
    expect(buildJob('text', form, SDXL, []).upsample).toBeUndefined()
  })

  it('keeps the picture only on Image to image with FLUX.2 [klein], off at first', () => {
    const KLEIN = model('klein', { arch: 'flux2_klein', family: 'flux2', negativePrompt: false, inpaint: true, defaults: { num_steps: 4, guidance_scale: 1, width: 1024, height: 1024 } })
    const form = { ...emptyForm('image'), prompt: 'snow', inputImage: '/in.png' }
    expect(form.keepPicture).toBe(false)
    expect(keepsPicture(KLEIN.meta) && !keepsPicture(SDXL.meta)).toBe(true)
    expect(buildJob('image', { ...form, keepPicture: true }, KLEIN, []).keepPicture).toBe(true)
    expect(buildJob('image', form, KLEIN, []).keepPicture).toBeUndefined()
    expect(buildJob('image', { ...form, keepPicture: true }, SDXL, []).keepPicture).toBeUndefined()
    expect(buildJob('inpaint', { ...form, keepPicture: true }, KLEIN, [], { maskImage: '/m.png' }).keepPicture).toBeUndefined()
    const back = emptyForm('image')
    applyJob(back, { id: 'j', ...buildJob('image', { ...form, keepPicture: true }, KLEIN, []) }, [KLEIN], [])
    expect(back.keepPicture).toBe(true)
  })

  it('describes jobs with an input picture', () => {
    const form = { ...emptyForm('image'), prompt: 'x', inputImage: '/in.png' }
    applyModel(form, SDXL, [])
    expect(buildJob('image', form, SDXL, [], { inputSize: [640, 480] })).toMatchObject({ inputImage: '/in.png', strength: 0.6, width: 640, height: 480 })
    expect(buildJob('image', { ...form, customSize: true }, SDXL, []).exactSize).toBe(true)
    expect(buildJob('inpaint', form, SDXL, [], { maskImage: '/mask.png' })).toMatchObject({ maskImage: '/mask.png', inputImage: '/in.png' })
  })

  it('says what is missing', () => {
    expect(formProblem('text', emptyForm('text'), { ...SDXL, meta: { ...SDXL.meta, unsupported: 'Chroma models can not run yet' } }, false))
      .toBe('Chroma models can not run yet')
    const form = emptyForm('inpaint')
    expect(formProblem('inpaint', form, undefined, false)).toMatch(/model/)
    expect(formProblem('inpaint', form, SDXL, false)).toMatch(/picture/)
    expect(formProblem('inpaint', { ...form, inputImage: '/a.png' }, SDXL, false)).toMatch(/Paint/)
    expect(formProblem('inpaint', { ...form, inputImage: '/a.png' }, SDXL, true)).toBe('')
    expect(formProblem('text', emptyForm('text'), SDXL, false)).toMatch(/Describe/)
  })

  it('takes over an earlier job', () => {
    const form = emptyForm('text')
    applyJob(form, { id: '1', page: 'text', prompt: 'p', modelId: '', modelDir: '/models/xl', width: 768, height: 512, seed: 9, steps: 12, loras: [{ path: '/loras/a', scale: 0.5 }] }, [SDXL], LORAS)
    expect(form).toMatchObject({ prompt: 'p', modelId: 'model:xl', width: 768, height: 512, seed: 9, steps: 12, loras: [{ id: 'lora:a', scale: 0.5 }] })
    // the models moved to another folder since: the name of the folder still tells which it was
    const moved = emptyForm('text')
    applyJob(moved, { id: '2', page: 'text', prompt: 'p', modelId: 'model:xl', modelDir: '/old/place/xl', width: 512, height: 512, seed: 1, loras: [{ path: '/old/loras/a', scale: 1 }] }, [SDXL], LORAS)
    expect(moved.modelId).toBe('model:xl')
    expect(moved.loras).toEqual([{ id: 'lora:a', scale: 1 }])
    const byName = emptyForm('text')
    applyJob(byName, { id: '3', page: 'text', prompt: 'p', modelId: '', modelDir: '/elsewhere/xl', width: 512, height: 512, seed: 1 }, [SDXL], [])
    expect(byName.modelId).toBe('model:xl')
  })

  it('builds a video job in the proportions of the start picture', () => {
    const wan = model('wan', { kind: 'video', family: 'wan', defaults: { num_steps: 4, guidance_scale: 1, width: 832, height: 480 } })
    expect(modelsFor('video', [SDXL, wan]).map((m) => m.title)).toEqual(['wan'])
    const form = { ...emptyForm('video'), prompt: 'she turns her head', inputImage: '/in.png', videoSeconds: 3, style: 'Anime', loras: [{ id: 'lora:a', scale: 1 }] }
    applyModel(form, wan, LORAS)
    expect(formProblem('video', { ...form, inputImage: '' }, wan, false)).toMatch(/starts with/)
    const job = buildJob('video', form, wan, LORAS, { inputSize: [1080, 1920] })
    expect(job).toMatchObject({ page: 'video', inputImage: '/in.png', videoSeconds: 3, width: 480, height: 864, steps: 4 })
    expect(job.style).toBeUndefined()
    expect(job.strength).toBeUndefined()
  })

  it('builds an illusion job with the pattern as control picture', () => {
    const sd15 = model('sd15', { arch: 'sd15', family: 'sd1', defaults: { num_steps: 25, guidance_scale: 7, width: 512, height: 512 } })
    expect(modelsFor('illusion', [SDXL, FLUX, sd15]).map((m) => m.title)).toEqual(['xl', 'sd15'])
    const form = { ...emptyForm('illusion'), prompt: 'a village', width: 1024, height: 1280, patternStrength: 1.3 }
    expect(buildJob('illusion', form, SDXL, [], { patternImage: '/p.png' })).toMatchObject({
      width: 1024, height: 1280, controlnet: { type: 'Illusion', image: '/p.png', weight: 1.3, preprocess: false },
    })
    expect(buildJob('illusion', form, sd15, [], { patternImage: '/p.png' })).toMatchObject({ width: 640, height: 768 })
  })

  it('adds a control picture where the model can take one', () => {
    const form = { ...emptyForm('text'), prompt: 'a dancer', controlType: 'BodyPose', controlImage: '/pose.png', controlPreprocess: false, controlWeight: 0.9 }
    applyModel(form, SDXL, [])
    expect(buildJob('text', form, SDXL, []).controlnet).toEqual({ type: 'BodyPose', image: '/pose.png', weight: 0.9, preprocess: false })
    expect(formProblem('text', { ...form, controlImage: '' }, SDXL, false)).toMatch(/control picture/)
    // FLUX.1 has no tile control, a model without control support drops the choice
    const tile = { ...form, controlType: 'Tile' }
    applyModel(tile, FLUX, [])
    expect(tile.controlType).toBe('')
    expect(buildJob('inpaint', { ...form, inputImage: '/a.png' }, SDXL, [], { maskImage: '/m.png' }).controlnet).toBeUndefined()
  })

  it('lets the family decide when an older manifest does not say whether a model can inpaint', () => {
    const old = model('oldxl', { inpaint: undefined })
    const said = model('nope', { inpaint: false })
    const anima = model('anima', { family: 'anima', inpaint: undefined })
    expect(modelsFor('inpaint', [old, said, anima]).map((m) => m.title)).toEqual(['oldxl'])
  })

  it('offers a FLUX.2 [klein] model only the LoRAs of its size, and sends no other', () => {
    const klein4 = model('k4', { arch: 'flux2_klein', family: 'flux2', variant: 'klein4b' })
    const k9 = { ...lora('k9', 'flux2'), meta: { ...lora('k9', 'flux2').meta, variant: 'klein9b' } }
    const k4 = { ...lora('k4l', 'flux2'), meta: { ...lora('k4l', 'flux2').meta, variant: 'klein4b' } }
    const loras = [k9, k4, lora('plain', 'flux2')]
    expect(lorasFor(klein4, loras).map((l) => l.title)).toEqual(['k4l', 'plain'])
    const form = { ...emptyForm('text'), prompt: 'x', loras: [{ id: 'lora:k9', scale: 1 }, { id: 'lora:k4l', scale: 1 }] }
    expect(buildJob('text', form, klein4, loras).loras).toEqual([{ path: '/loras/k4l', scale: 1 }])
  })
})
