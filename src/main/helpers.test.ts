// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { EDITION } from '@shared/edition'
import { listHelpers, usesNonCommercialHelper } from './helpers'

describe('helper models', () => {
  it('lists the catalog and tells which are on this Mac by their files', () => {
    const helpers = mkdtempSync(join(tmpdir(), 'vk-helpers-'))
    mkdirSync(join(helpers, 'upscalers'), { recursive: true })
    writeFileSync(join(helpers, 'upscalers', 'RealESRGAN_x4plus.safetensors'), Buffer.alloc(40 * 1024 ** 2))
    mkdirSync(join(helpers, 'annotators', 'depth'), { recursive: true })
    writeFileSync(join(helpers, 'annotators', 'depth', 'config.json'), '{}')  // a download that broke off
    const list = listHelpers(resolve('engines'), helpers)
    expect(list.length).toBeGreaterThanOrEqual(20)
    expect(list.find((h) => h.id === 'realesrgan')).toMatchObject({ installed: true, diskMb: 40, group: 'Upscale' })
    expect(list.find((h) => h.id === 'depth')?.installed).toBe(false)
    // RORem half downloaded: not there until pinned.py marked it complete
    const rorem = join(helpers, 'annotators', 'inpaint', 'LetsThink--RORem')
    mkdirSync(rorem, { recursive: true })
    writeFileSync(join(rorem, 'unet.safetensors'), Buffer.alloc(4000 * 1024 ** 2 / 1000))
    expect(listHelpers(resolve('engines'), helpers).find((h) => h.id === 'rorem')?.installed).toBe(false)
    // a mark of an older pin: downloaded again on the next use, so not there yet
    writeFileSync(join(rorem, '.vk-checked.json'), '{"revision": "an-older-commit"}')
    expect(listHelpers(resolve('engines'), helpers).find((h) => h.id === 'rorem')?.installed).toBe(false)
    writeFileSync(join(rorem, '.vk-checked.json'), '{"revision": "22d02de974c8dc92c717cd3431f8b0fe0eeecc3b"}')
    expect(listHelpers(resolve('engines'), helpers).find((h) => h.id === 'rorem')?.installed).toBe(true)
    expect(list.filter((h) => h.required).map((h) => h.id).sort()).toEqual(['content-age', 'content-nsfw'])
    expect(list.every((h) => h.preview && h.folder.startsWith(helpers))).toBe(true)
    // ObjectClear the same way
    const oc = join(helpers, 'annotators', 'inpaint', 'jixin0101--ObjectClear')
    mkdirSync(oc, { recursive: true })
    writeFileSync(join(oc, 'unet.safetensors'), Buffer.alloc(5000 * 1024 ** 2 / 1000))
    expect(listHelpers(resolve('engines'), helpers).find((h) => h.id === 'objectclear')).toMatchObject({ installed: false, sizeMb: 7460 })
    writeFileSync(join(oc, '.vk-checked.json'), '{"revision": "c73af80888dbd519819d0a521b5c8d0f3cda6859"}')
    expect(listHelpers(resolve('engines'), helpers).find((h) => h.id === 'objectclear')?.installed).toBe(true)
  })

  it('leaves out the non-commercial ObjectClear and CodeFormer in a build with commercially usable models only', () => {
    const helpers = mkdtempSync(join(tmpdir(), 'vk-helpers-'))
    try {
      EDITION.commercialModelsOnly = true
      const ids = listHelpers(resolve('engines'), helpers).map((h) => h.id)
      expect(ids).not.toContain('objectclear')
      expect(ids).not.toContain('codeformer')
      expect(ids).toContain('rorem')
    } finally {
      EDITION.commercialModelsOnly = false
    }
  })

  it('tells which jobs need a non-commercial helper (refused in a build with commercially usable models only)', () => {
    expect(usesNonCommercialHelper({ removeObject: { method: 'objectclear' } })).toBe(true)
    expect(usesNonCommercialHelper({ restore: { faces: true } as never })).toBe(true)
    // the engine runs CodeFormer for any true value: 1 or 'yes' sent by hand are refused too
    expect(usesNonCommercialHelper({ restore: { faces: 1 } as never })).toBe(true)
    expect(usesNonCommercialHelper({ removeObject: { method: 'rorem' } })).toBe(false)
    expect(usesNonCommercialHelper({ restore: { faces: false } as never })).toBe(false)
    expect(usesNonCommercialHelper({})).toBe(false)
  })
})
