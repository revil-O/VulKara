// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Scans page: what the page sends about the photos on a scan is checked here before the engine cuts them out
// (engines/diffusers/scans.py); a frame reaching past the scan is clipped there.
import { constants, copyFileSync, existsSync, mkdirSync } from 'node:fs'
import { basename, join } from 'node:path'
import type { ScanPhoto } from '@shared/api'
import { t } from './i18n'

const MAX_PHOTOS = 50
// no scanner makes a side this long (A3 at 2400 dpi is 40 000 px); the engine checks each frame against its scan
const MAX_SIDE = 100_000
const TURNS = [0, 90, 180, 270]

/** The page's frames as rectangles the engine can take (its size against the scan is checked there); throws on
 *  anything else. */
export function checkPhotos(photos: unknown): ScanPhoto[] {
  if (!Array.isArray(photos) || photos.length > MAX_PHOTOS) throw new Error(t('main.scans.badFrames'))
  return photos.map((p: Record<string, unknown>) => {
    const { cx, cy, w, h, angle, turn } = p ?? {}
    if (![cx, cy, w, h, angle].every((n) => typeof n === 'number' && Number.isFinite(n))) throw new Error(t('main.scans.badFrames'))
    const r = { cx, cy, w, h, angle, turn } as ScanPhoto
    if (r.w <= 0 || r.h <= 0 || r.w > MAX_SIDE || r.h > MAX_SIDE || r.cx < 0 || r.cy < 0 || Math.abs(r.angle) > 45 || !TURNS.includes(r.turn))
      throw new Error(t('main.scans.badFrames'))
    return r
  })
}

/** A restored photo copied into the export folder as "<name> – <word>.png" ((2), (3) … when taken); the copy's path. */
export function exportCopy(result: string, name: string, dir: string, word: string): string {
  mkdirSync(dir, { recursive: true })
  const stem = `${basename(name)} \u2013 ${word}`
  for (let n = 1; ; n++) {
    const target = join(dir, n === 1 ? `${stem}.png` : `${stem} (${n}).png`)
    if (existsSync(target)) continue
    copyFileSync(result, target, constants.COPYFILE_EXCL)
    return target
  }
}
