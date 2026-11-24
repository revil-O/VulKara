// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { EDITION, INTEL_FAMILIES, commerciallyUsable, editionFor } from './edition'
import curated from './data/curated_models.json'
import licences from './data/licenses.json'

describe('the edition', () => {
  it('offers everything', () => {
    expect(EDITION).toMatchObject({ id: 'full', arch: 'arm64', comfyui: true, mlx: true, explicitContent: 'choice', commercialModelsOnly: false })
  })

  it('leaves MLX and ComfyUI out of the Intel build, and nothing else', () => {
    expect(editionFor('x64')).toEqual({ ...editionFor('arm64'), arch: 'x64', comfyui: false, mlx: false })
    for (const f of INTEL_FAMILIES) expect(curated.some((m) => m.family === f), f).toBe(true)
  })

  it('has a licence for every recommended model, so a restricted build could decide', () => {
    for (const m of curated) expect(licences.models.find((l) => l.id === m.id), m.id).toBeDefined()
    expect(commerciallyUsable({ model: 'yes', outputs: 'yes' })).toBe(true)
    expect(commerciallyUsable({ model: 'limited', outputs: 'limited' })).toBe(true)
    expect(commerciallyUsable({ model: 'no', outputs: 'yes' })).toBe(false)
    expect(commerciallyUsable(undefined)).toBe(false)
  })
})
