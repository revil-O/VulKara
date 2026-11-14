// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { afterAll, describe, expect, it } from 'vitest'
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readdirSync, rmSync, utimesSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pruneSelections, selectionsDir, subjectMask, subjectMaskHelper } from './subject_mask'

// stand-ins for the Swift helper: shell scripts that exit as it does
const dir = mkdtempSync(join(tmpdir(), 'vk-subject-'))
afterAll(() => rmSync(dir, { recursive: true, force: true }))
function helper(name: string, body: string): string {
  const path = join(dir, name)
  writeFileSync(path, `#!/bin/sh\n${body}\n`)
  chmodSync(path, 0o755)
  return path
}

describe('select subject (Apple Vision helper)', () => {
  it('answers with the mask the helper wrote and logs what it said', async () => {
    const lines: string[] = []
    const ok = helper('ok', 'echo "found 1" >&2; : > "$2"; echo subjects 1')
    expect(await subjectMask(ok, '/a/picture.png', join(dir, 'm.png'), (l) => lines.push(l))).toEqual({ mask: join(dir, 'm.png'), subjects: 1 })
    expect(lines).toEqual(['subject mask: found 1'])
  })

  it('answers with the map of which pixel is which subject when there are several', async () => {
    const two = helper('two', ': > "$2"; : > "$3"; echo subjects 2')
    expect(await subjectMask(two, '/a.png', join(dir, 's.png'), () => {})).toEqual({ mask: join(dir, 's.png'), labels: join(dir, 's_labels.png'), subjects: 2 })
    // a helper of an older build: no count, no map
    expect(await subjectMask(helper('old', ': > "$2"'), '/a.png', join(dir, 'o.png'), () => {})).toEqual({ mask: join(dir, 'o.png'), subjects: 1 })
  })

  it('says so when there is no subject, the picture can not be read or the helper fails', async () => {
    await expect(subjectMask(helper('none', 'exit 4'), '/a.png', '/m.png', () => {})).rejects.toThrow(/No subject/)
    await expect(subjectMask(helper('unreadable', 'exit 3'), '/a.png', '/m.png', () => {})).rejects.toThrow(/picture/i)
    await expect(subjectMask(helper('broken', 'exit 5'), '/a.png', '/m.png', () => {})).rejects.toThrow(/could not/i)
  })

  it('stops a helper that takes too long, and says when the helper is missing', async () => {
    await expect(subjectMask(helper('slow', 'sleep 5'), '/a.png', '/m.png', () => {}, 200)).rejects.toThrow(/too long/)
    await expect(subjectMask(join(dir, 'nothing'), '/a.png', '/m.png', () => {})).rejects.toThrow(/not part of this build/)
  })

  it('deletes the half-written mask of a helper that failed or was stopped', async () => {
    const out = join(dir, 'half.png')
    await expect(subjectMask(helper('fails', ': > "$2"; : > "$3"; exit 5'), '/a.png', out, () => {})).rejects.toThrow(/could not/i)
    expect(existsSync(out) || existsSync(join(dir, 'half_labels.png'))).toBe(false)
    await expect(subjectMask(helper('stalls', ': > "$2"; sleep 5'), '/a.png', out, () => {}, 200)).rejects.toThrow(/too long/)
    expect(existsSync(out)).toBe(false)
  })

  it('deletes selections older than a week at app start, keeps newer ones and folders', async () => {
    const sel = selectionsDir(join(dir, 'data'))
    expect(sel).toBe(join(dir, 'data', 'inputs', 'selections'))
    expect(await pruneSelections(sel)).toBe(0)  // no folder yet
    mkdirSync(join(sel, 'folder'), { recursive: true })
    const now = Date.now()
    for (const [name, days] of [['subject_old.png', 8], ['mask_old.png', 30], ['subject_new.png', 6], ['mask_new.png', 0]] as const) {
      writeFileSync(join(sel, name), '')
      const at = (now - days * 86_400_000) / 1000
      utimesSync(join(sel, name), at, at)
    }
    // an old selection a history entry still uses (Enhance runs it again) stays
    expect(await pruneSelections(sel, (path) => path === join(sel, 'mask_old.png'), undefined, now)).toBe(1)
    expect(readdirSync(sel).sort()).toEqual(['folder', 'mask_new.png', 'mask_old.png', 'subject_new.png'])
  })

  it('finds the helper in the app bundle, and the built one in development', () => {
    expect(subjectMaskHelper(true, '/App/Contents/Resources', '/x')).toBe('/App/Contents/Resources/native/subject-mask')
    expect(subjectMaskHelper(false, '/r', '/src/vulkara')).toBe('/src/vulkara/out/native/subject-mask')
  })
})
