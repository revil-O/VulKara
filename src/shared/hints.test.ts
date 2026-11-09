// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { flux1Outline, kleinTints, takesConsistency } from './hints'

describe('page hints', () => {
  it('names the 9B tint only for a black-and-white photo and klein 9B', () => {
    const k9 = { arch: 'flux2_klein', variant: 'klein9b' }
    expect(kleinTints(true, k9)).toBe(true)
    expect(kleinTints(false, k9)).toBe(false)
    expect(kleinTints(true, { arch: 'flux2_klein', variant: 'klein4b' })).toBe(false)
    expect(takesConsistency({ arch: 'flux2_klein', variant: 'klein4b' })).toBe(true)
    expect(takesConsistency({ arch: 'flux2_klein', variant: 'klein9b' })).toBe(false)
    expect(takesConsistency({ arch: 'z_image' })).toBe(false)
    expect(takesConsistency(undefined)).toBe(false)
    expect(kleinTints(true, undefined)).toBe(false)
  })

  it('names the FLUX.1 outline only when inpainting with dev or schnell, not with Fill', () => {
    expect(flux1Outline('inpaint', { family: 'flux1' })).toBe(true)
    expect(flux1Outline('inpaint', { family: 'flux1', inpaintOnly: true })).toBe(false)
    expect(flux1Outline('image', { family: 'flux1' })).toBe(false)
    expect(flux1Outline('inpaint', { family: 'flux2' })).toBe(false)
    expect(flux1Outline('inpaint', undefined)).toBe(false)
  })

  it('loads the mask picture with CORS, so the pages may read its pixels (black-and-white check)', () => {
    const vue = readFileSync('src/renderer/src/components/MaskCanvas.vue', 'utf8')
    expect(vue).toMatch(/<img :src="src" crossorigin="anonymous"/)
  })
})
