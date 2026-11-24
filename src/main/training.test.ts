// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { Trainer, canTrain, trainingJob, type TrainerDeps } from './training'
import type { TrainingState } from '@shared/api'

function setup(verdict: (path: string) => { ok: boolean; reason?: string }) {
  const root = mkdtempSync(join(tmpdir(), 'vk-train-'))
  const model = join(root, 'model')
  mkdirSync(model)
  writeFileSync(join(model, 'model.json'), JSON.stringify({ arch: 'sdxl' }))
  const pictures = ['a.png', 'b.png', 'c.png'].map((n) => {
    writeFileSync(join(root, n), 'x')
    return join(root, n)
  })
  const states: TrainingState[] = []
  let prepared = 0
  let filterStopped = 0
  const deps: TrainerDeps = {
    command: () => ({ command: '/usr/bin/false', args: [], env: {} }),
    env: () => ({}), workDir: () => join(root, 'work'), lorasDir: () => join(root, 'loras'),
    prepare: () => { prepared++ }, changed: (s) => states.push(s), installed: () => {}, log: () => {},
    check: async (p) => verdict(p), checked: () => { filterStopped++ },
  }
  const trainer = new Trainer(deps)
  const request = { baseModel: model, name: 'my lora', trigger: 'mylora', images: pictures.map((path) => ({ path, caption: 'a photo' })) }
  return { trainer, request, states, root, prepared: () => prepared, filterStopped: () => filterStopped }
}

describe('training pictures and the content filter', () => {
  it('does not start when a picture does not pass, and names it', async () => {
    const t = setup((p) => (p.endsWith('b.png') ? { ok: false, reason: 'shows nudity' } : { ok: true }))
    await t.trainer.start(t.request as never)
    const last = t.trainer.state()
    expect(last.running).toBe(false)
    expect(last.error).toContain('b.png: shows nudity')
    expect(t.prepared()).toBe(0)
    expect(t.filterStopped()).toBe(1)
    expect(existsSync(join(t.root, 'work', 'my_lora', 'job.json'))).toBe(false)
    expect(t.states.some((s) => s.phase === 'checking')).toBe(true)
  })

  it('refuses captions that ask for sexual content with minors before anything is checked', async () => {
    const checked: string[] = []
    const t = setup((p) => { checked.push(p); return { ok: true } })
    const request = { ...t.request, images: t.request.images.map((i) => ({ ...i, caption: 'nude child' })) }
    await expect(t.trainer.start(request as never)).rejects.toThrow(/minor/)
    expect(checked).toEqual([])
  })

  it('ends as stopped when Stop comes while the pictures are checked', async () => {
    let trainer: Trainer | undefined
    const t = setup(() => { trainer?.stop(); return { ok: true } })
    trainer = t.trainer
    await t.trainer.start(t.request as never)
    expect(t.trainer.state()).toMatchObject({ running: false, stopped: true })
    expect(t.prepared()).toBe(0)
  })
})

describe('the models a LoRA can be trained on', () => {
  it('leaves out MLX models kept as one denoiser file', () => {
    expect(canTrain({ arch: 'z_image', layout: 'repo' })).toBe(true)
    expect(canTrain({ arch: 'flux2_klein', layout: 'folder' })).toBe(true)
    expect(canTrain({ arch: 'sdxl', layout: 'single_full' })).toBe(true)
    // a Civitai Z-Image fine-tune: mflux would read the base folder and train the stock model
    expect(canTrain({ arch: 'z_image', layout: 'single_denoiser' })).toBe(false)
    expect(canTrain({ arch: 'flux2_klein', layout: 'single_denoiser' })).toBe(false)
    expect(canTrain({ arch: 'sd15', layout: 'repo' })).toBe(false)
  })

  it('refuses such a model also when a request names it', () => {
    const root = mkdtempSync(join(tmpdir(), 'vk-train-'))
    const model = join(root, 'model')
    mkdirSync(model)
    writeFileSync(join(model, 'model.json'), JSON.stringify({ arch: 'z_image', layout: 'single_denoiser' }))
    writeFileSync(join(root, 'a.png'), 'x')
    const req = { baseModel: model, name: 'x', trigger: 'x', images: [{ path: join(root, 'a.png'), caption: '' }],
      resolution: 512, steps: 10, rank: 16, learningRate: 0.0001 }
    expect(() => trainingJob(req, join(root, 'work'), join(root, 'loras'))).toThrow()
  })
})
