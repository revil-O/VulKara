// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Picture sizes: a model works best around its native pixel count; an aspect ratio picks the size closest to it.

export const RATIOS: { label: string; w: number; h: number }[] = [
  { label: '1:1', w: 1, h: 1 },
  { label: '4:3', w: 4, h: 3 },
  { label: '3:2', w: 3, h: 2 },
  { label: '16:9', w: 16, h: 9 },
  { label: '3:4', w: 3, h: 4 },
  { label: '2:3', w: 2, h: 3 },
  { label: '9:16', w: 9, h: 16 },
]

const nearest = (value: number, choices: number[]): number =>
  choices.reduce((best, c) => (Math.abs(c - value) < Math.abs(best - value) ? c : best), choices[0])

/** Width and height for a ratio at about the pixel count of nativeW × nativeH, from the sizes the model takes. */
export function sizeForRatio(ratio: { w: number; h: number }, nativeW: number, nativeH: number, choices: number[]): [number, number] {
  const pixels = nativeW * nativeH
  const r = ratio.w / ratio.h
  return [nearest(Math.sqrt(pixels * r), choices), nearest(Math.sqrt(pixels / r), choices)]
}

/** The ratio label a size has, if it is one of the offered ones. */
export function ratioOf(width: number, height: number, nativeW: number, nativeH: number, choices: number[]): string | undefined {
  return RATIOS.find((r) => {
    const [w, h] = sizeForRatio(r, nativeW, nativeH, choices)
    return w === width && h === height
  })?.label
}

/** The sizes offered when a model does not say which it takes. */
export const DEFAULT_SIZES = Array.from({ length: 13 }, (_, i) => 256 + i * 64)

export type VideoResolution = '480p' | '720p' | '1080p'
// shorter side of a video (Wan sizes are multiples of 32, LTX-2.3's of 64: 1080 → 1088)
const SHORT_SIDE: Record<VideoResolution, number> = { '480p': 480, '720p': 704, '1080p': 1088 }
const MAX_LONG_SIDE: Record<VideoResolution, number> = { '480p': 1280, '720p': 1280, '1080p': 1920 }
/** LTX-2.3 at 1080p needed 15.96 GB and swapped on a 16 GB Mac, about an hour for 5 s (MEASUREMENTS 7cy) */
export const VIDEO_1080P_MIN_RAM_GB = 24

/** The size of a video with the proportions of its start picture (16:9 while that is not known). */
export function videoSize(picture: [number, number] | undefined, resolution: VideoResolution): [number, number] {
  const short = SHORT_SIDE[resolution]
  const ratio = picture && picture[0] && picture[1] ? picture[0] / picture[1] : 16 / 9
  const landscape = ratio >= 1
  const long = Math.min(MAX_LONG_SIDE[resolution], Math.round((short * (landscape ? ratio : 1 / ratio)) / 32) * 32)
  return landscape ? [long, short] : [short, long]
}
