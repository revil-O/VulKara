// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { delta, EXPECTED, expectationFor } from './expectations'

const mini = { chip: 'Apple M4', ramGb: 16 }

describe('expectations', () => {
  it('names a section of the measurements for every figure, and the figure is in it', () => {
    const doc = readFileSync(join(__dirname, '..', '..', 'docs', 'MEASUREMENTS.md'), 'utf8')
    for (const e of EXPECTED) {
      const start = doc.indexOf(`## ${e.ref}. `)
      expect(start, e.ref).toBeGreaterThan(0)
      const section = doc.slice(start, doc.indexOf('\n## ', start + 4))
      expect(section, `${e.model} in ${e.ref}`).toContain(e.model)
    }
  })

  it('holds only on the Mac and at the settings it was measured with', () => {
    expect(expectationFor('/Volumes/x/models/FLUX.2-klein-4B', 4, 1024, 1024, mini)?.secondsPerPicture).toBe(51)
    expect(expectationFor('/Volumes/x/models/FLUX.2-klein-4B/', 4, 1024, 1024, mini)?.ref).toBe('7bt')
    expect(expectationFor('/Volumes/x/models/FLUX.2-klein-4B', 8, 1024, 1024, mini)).toBeUndefined()
    expect(expectationFor('/Volumes/x/models/FLUX.2-klein-4B', 4, 768, 768, mini)).toBeUndefined()
    expect(expectationFor('/Volumes/x/models/FLUX.2-klein-4B', 4, 1024, 1024, { chip: 'Apple M2', ramGb: 24 })).toBeUndefined()
    expect(expectationFor('/Volumes/x/models/FLUX.2-klein-4B', 4, 1024, 1024, undefined)).toBeUndefined()
  })

  it('rates a figure against what was expected, lower being better, never "-0 %"', () => {
    expect(delta(9.2, 8.9)).toEqual({ pct: 3, tone: 'neutral' })
    expect(delta(8.0, 8.9)).toEqual({ pct: -10, tone: 'neutral' })
    expect(delta(7.0, 8.9)).toEqual({ pct: -21, tone: 'better' })
    expect(delta(10.5, 8.9)).toEqual({ pct: 18, tone: 'worse' })
    expect(delta(12.4, 9.8)).toEqual({ pct: 27, tone: 'bad' })
    expect(delta(8.899, 8.9).pct).toBe(0)
    expect(Object.is(delta(8.899, 8.9).pct, -0)).toBe(false)
    expect(delta(3, 0)).toEqual({ pct: 0, tone: 'neutral' })
  })
})
