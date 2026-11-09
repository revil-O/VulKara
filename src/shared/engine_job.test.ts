// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { toEngineJob } from './engine_job'
import type { Job } from './types'

const BASE: Job = {
  id: '1', page: 'restore', prompt: '', modelId: '', modelDir: '', width: 400, height: 600, seed: -1, steps: 0, inputImage: '/p.png',
  restore: { correct: true, repair: false, colorize: false, colorStrength: 1, sharpen: false, sharpness: 0.25, lock: true, maxChange: 0.06, rules: [], checkFaces: true },
}

describe('the engine job', () => {
  it('passes the prompt upsampler of FLUX 3 on, and nothing when it is off', () => {
    const job: Job = { id: '2', page: 'text', prompt: 'a fox', modelId: 'm', modelDir: '/m', width: 1024, height: 1024, seed: 7 }
    expect(toEngineJob({ ...job, upsample: true }).upsample).toBe(true)
    expect('upsample' in toEngineJob(job)).toBe(false)
  })

  it('passes keep the picture on only when it is on', () => {
    const job: Job = { id: '3', page: 'image', prompt: 'snow', modelId: 'm', modelDir: '/m', width: 1024, height: 1024, seed: 7, inputImage: '/in.png' }
    expect(toEngineJob({ ...job, keepPicture: true }).keep_picture).toBe(true)
    expect('keep_picture' in toEngineJob(job)).toBe(false)
  })
})

describe('Restore jobs for the engine', () => {
  it('fills in the defaults of the AI steps an older job or template does not have', () => {
    const r = toEngineJob(BASE).restore as Record<string, unknown>
    expect(r).toMatchObject({ correct_strength: 0.8, details: false, detail_level: 2, detail_strength: 1, faces: false, face_fidelity: 0.9, face_strength: 0.6, scale: 1, consistency: false })
    expect(r.preview).toBeUndefined()
    expect(r.face_points).toBeUndefined()
  })

  it('passes the chosen steps, the faces as placed and a preview part', () => {
    const points: [number, number][][] = [[[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]]]
    const job: Job = {
      ...BASE,
      restore: { ...BASE.restore!, details: true, detailLevel: 2.5, detailStrength: 0.7, faces: true, faceFidelity: 1, faceStrength: 0.5, scale: 2, consistency: true, facePoints: points, preview: { x: 10, y: 20, w: 300, h: 300 } },
    }
    const r = toEngineJob(job).restore as Record<string, unknown>
    expect(r).toMatchObject({ details: true, detail_level: 2.5, detail_strength: 0.7, faces: true, face_fidelity: 1, face_strength: 0.5, scale: 2, consistency: true })
    expect(r.face_points).toEqual(points)
    expect(r.preview).toEqual({ x: 10, y: 20, w: 300, h: 300 })
  })
})
