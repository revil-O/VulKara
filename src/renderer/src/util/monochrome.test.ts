// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { isMonochrome } from './monochrome'

/** 64 × 64 pixels in the middle tones (the spread of a toned print grows with its range), coloured by tint(level) */
function photo(tint: (v: number, i: number) => [number, number, number]): number[] {
  const out: number[] = []
  for (let i = 0; i < 64 * 64; i++) out.push(...tint(64 + (i % 64) * 2, i), 255)
  return out
}

describe('isMonochrome', () => {
  it('finds grey and sepia photos, not coloured ones', () => {
    expect(isMonochrome(photo((v) => [v, v, v]))).toBe(true)
    expect(isMonochrome(photo((v) => [v, v * 0.85, v * 0.65]))).toBe(true)
    expect(isMonochrome(photo((v, i) => (i % 2 ? [v, 40, 40] : [40, v, 200])))).toBe(false)
  })
})
