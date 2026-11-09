// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt

// the same limit as the engine's restore.MONOCHROME_SPREAD (spread of LAB a/b)
const MONOCHROME_SPREAD = 6

const linear = (c: number): number => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
const f = (t: number): number => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116)

/** A black-and-white photo, also a toned one (sepia): its colour hardly varies over the picture (RGBA pixels, as
 * engines/diffusers/restore.py is_grayscale decides). */
export function isMonochrome(rgba: ArrayLike<number>): boolean {
  const n = rgba.length / 4
  let sa = 0, sa2 = 0, sb = 0, sb2 = 0
  for (let i = 0; i < rgba.length; i += 4) {
    const r = linear(rgba[i] / 255), g = linear(rgba[i + 1] / 255), b = linear(rgba[i + 2] / 255)
    const x = f((0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047)
    const y = f(0.2126 * r + 0.7152 * g + 0.0722 * b)
    const z = f((0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883)
    const a = 500 * (x - y), bb = 200 * (y - z)
    sa += a; sa2 += a * a; sb += bb; sb2 += bb * bb
  }
  const spread = (s: number, s2: number): number => Math.sqrt(Math.max(0, s2 / n - (s / n) ** 2))
  return Math.max(spread(sa, sa2), spread(sb, sb2)) < MONOCHROME_SPREAD
}
