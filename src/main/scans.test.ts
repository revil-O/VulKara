// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { checkPhotos, exportCopy } from './scans'

const ok = { cx: 640, cy: 760, w: 880, h: 680, angle: 2.5, turn: 0 }

describe('checkPhotos', () => {
  it('takes rectangles inside the scan, also with a quarter turn', () => {
    expect(checkPhotos([ok, { ...ok, turn: 270, angle: -45 }])).toEqual([ok, { ...ok, turn: 270, angle: -45 }])
  })

  it('keeps only the fields of a rectangle', () => {
    expect(checkPhotos([{ ...ok, extra: 'x' }])).toEqual([ok])
  })

  it.each([
    ['no list', 'x'],
    ['too many', Array.from({ length: 51 }, () => ok)],
    ['not a number', [{ ...ok, cx: 'a' }]],
    ['not finite', [{ ...ok, w: Number.POSITIVE_INFINITY }]],
    ['NaN', [{ ...ok, cy: Number.NaN }]],
    ['no width', [{ ...ok, w: 0 }]],
    ['negative height', [{ ...ok, h: -3 }]],
    ['too steep', [{ ...ok, angle: 46 }]],
    ['odd turn', [{ ...ok, turn: 45 }]],
    ['centre above', [{ ...ok, cy: -1 }]],
    ['larger than any scan', [{ ...ok, w: 1e6 }]],
  ])('refuses %s', (_, photos) => {
    expect(() => checkPhotos(photos)).toThrow()
  })

  it('leaves the check against the scan itself to the engine, which reads it anyway', () => {
    expect(checkPhotos([{ ...ok, cx: 9000 }])).toHaveLength(1)
  })
})

describe('exportCopy', () => {
  const setup = (): { dir: string; result: string } => {
    const dir = mkdtempSync(join(tmpdir(), 'vk-scans-'))
    const result = join(dir, 'result.png')
    writeFileSync(result, 'picture')
    return { dir, result }
  }

  it('copies a restored photo under its name into the folder, never over another file', () => {
    const { dir, result } = setup()
    const out = join(dir, 'out')
    expect(exportCopy(result, 'Album3_Seite12 \u2013 Foto 1', out, 'restauriert')).toBe(join(out, 'Album3_Seite12 \u2013 Foto 1 \u2013 restauriert.png'))
    expect(exportCopy(result, 'Album3_Seite12 \u2013 Foto 1', out, 'restauriert')).toBe(join(out, 'Album3_Seite12 \u2013 Foto 1 \u2013 restauriert (2).png'))
    expect(readFileSync(join(out, 'Album3_Seite12 \u2013 Foto 1 \u2013 restauriert.png'), 'utf8')).toBe('picture')
  })

  it('keeps a name with folders or dots inside the folder', () => {
    const { dir, result } = setup()
    const out = join(dir, 'out')
    expect(exportCopy(result, '../../etc/evil', out, 'restored')).toBe(join(out, 'evil \u2013 restored.png'))
    expect(existsSync(join(dir, 'etc'))).toBe(false)
  })
})
