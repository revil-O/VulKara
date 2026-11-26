// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { RATIOS, ratioOf, sizeForRatio, videoSize } from './sizes'

const SDXL = [512, 576, 640, 704, 768, 832, 896, 960, 1024, 1088, 1152, 1216, 1280, 1344, 1408, 1472, 1536]
const ratio = (label: string) => RATIOS.find((r) => r.label === label)!

describe('sizes', () => {
  it('keeps about the native pixel count', () => {
    expect(sizeForRatio(ratio('1:1'), 1024, 1024, SDXL)).toEqual([1024, 1024])
    expect(sizeForRatio(ratio('16:9'), 1024, 1024, SDXL)).toEqual([1344, 768])
    expect(sizeForRatio(ratio('2:3'), 1024, 1024, SDXL)).toEqual([832, 1280])
    expect(sizeForRatio(ratio('3:4'), 512, 512, [384, 448, 512, 576, 640, 704, 768])).toEqual([448, 576])
  })

  it('recognises the ratio of a size', () => {
    expect(ratioOf(1344, 768, 1024, 1024, SDXL)).toBe('16:9')
    expect(ratioOf(1024, 640, 1024, 1024, SDXL)).toBeUndefined()
  })

  it('sizes a video after its start picture', () => {
    expect(videoSize([1024, 1024], '480p')).toEqual([480, 480])
    expect(videoSize([1920, 1080], '480p')).toEqual([864, 480])
    expect(videoSize([1080, 1920], '720p')).toEqual([704, 1248])
    expect(videoSize([4000, 1000], '720p')).toEqual([1280, 704])
    expect(videoSize(undefined, '480p')).toEqual([864, 480])
    // 1080p (LTX-2.3 from 24 GB): LTX's 64 px grid, the long side up to 1920
    expect(videoSize([1920, 1080], '1080p')).toEqual([1920, 1088])
    expect(videoSize([1080, 1920], '1080p')).toEqual([1088, 1920])
  })
})
