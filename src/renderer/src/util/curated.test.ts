// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { CURATED, GROUPS, curatedHits, importRequest, installedAs, licencePage, memoryFit, offers } from './curated'
import { editionFor } from '@shared/edition'
import type { Asset } from '@shared/types'

const asset = (name: string, source?: Asset['source']): Asset => ({
  id: 'model:' + name, title: name, name, folder: '/models/' + name, type: 'model', source,
  meta: { arch: 'sd15', family: 'sd1', label: '', runtime: 'diffusers', kind: 'image' },
})

describe('recommended models', () => {
  it('is a complete list', () => {
    expect(CURATED.length).toBeGreaterThan(20)
    const groups = GROUPS.map((g) => g.id)
    for (const m of CURATED) {
      expect(groups).toContain(m.group)
      expect(m.ref && m.title && m.description).toBeTruthy()
      expect(m.nsfw).toBe(m.group === 'nsfw')
    }
    expect(new Set(CURATED.map((m) => m.id)).size).toBe(CURATED.length)
  })

  it('recognises an installed recommendation', () => {
    const sd = CURATED.find((m) => m.id === 'SD-1.5')!
    const gguf = CURATED.find((m) => m.id === 'FLUX.1-schnell-Q8')!
    expect(installedAs(sd, [asset('SD-1.5')])?.title).toBe('SD-1.5')
    expect(installedAs(sd, [asset('mine', { type: 'hf', ref: sd.ref, file: null })])?.title).toBe('mine')
    expect(installedAs(gguf, [asset('other', { type: 'hf', ref: gguf.ref, file: 'flux1-schnell-Q4_K_S.gguf' })])).toBeUndefined()
    expect(installedAs(CURATED.find((m) => m.id === 'DreamShaper-8')!, [asset('Lykon_dreamshaper-8_SD1')])).toBeDefined()
    expect(installedAs(sd, [])).toBeUndefined()
  })

  it('knows what to import and where the licence is', () => {
    const gguf = CURATED.find((m) => m.id === 'FLUX.1-schnell-Q8')!
    expect(importRequest(gguf)).toEqual({ source: 'hf', ref: 'city96/FLUX.1-schnell-gguf', file: 'flux1-schnell-Q8_0.gguf', name: 'FLUX.1-schnell-Q8' })
    expect(licencePage(gguf)).toBe('https://huggingface.co/city96/FLUX.1-schnell-gguf')
  })

  it('says streamed where only SSD streaming makes a model fit', () => {
    // SD 3.5 Large: in memory from 24 GB, streamed on a 16 GB Mac (Mac mini M4), not on 8 GB
    const large = CURATED.find((m) => m.id === 'SD3.5-Large')!
    expect(memoryFit(large, 24)).toBe('memory')
    expect(memoryFit(large, 16)).toBe('streamed')
    expect(memoryFit(large, 8)).toBe('none')
  })

  it('streams GGUF files too (unpacked into the stream cache once)', () => {
    const gguf = CURATED.find((m) => m.id === 'FLUX.1-schnell-Q8')!
    expect(memoryFit(gguf, 24)).toBe('memory')
    expect(memoryFit(gguf, 16)).toBe('streamed')
    expect(memoryFit(gguf, 8)).toBe('none')
  })

  it('names the recommended models a search means, however it spells them', () => {
    const refs = (q: string, source: 'hf' | 'civitai' = 'hf') => curatedHits(q, source, false).map((h) => h.ref)
    expect(refs('sd 3.5 large')).toEqual(['stabilityai/stable-diffusion-3.5-large'])
    expect(refs('Stable Diffusion 3.5 Large')).toEqual(['stabilityai/stable-diffusion-3.5-large'])
    expect(refs('flux schnell q4')).toEqual(['city96/FLUX.1-schnell-gguf'])
    const q4 = curatedHits('flux.1 schnell q4', 'hf', false)[0]
    expect([q4.file, q4.recommended, q4.title]).toEqual(['flux1-schnell-Q4_K_S.gguf', true, 'FLUX.1 [schnell] (4 bit)'])
    expect(refs('')).toEqual([])
    expect(refs('stable diffusion 3.5 large', 'civitai')).toEqual([])
  })

  it('the Intel build recommends only SD 1.x, SD 2.x and SDXL, the Apple-chip build all of them', () => {
    const intel = CURATED.filter((m) => offers(editionFor('x64'), m))
    expect(new Set(intel.map((m) => m.family))).toEqual(new Set(['SD 1.x', 'SD 2.x', 'SDXL']))
    expect(CURATED.every((m) => offers(editionFor('arm64'), m))).toBe(true)
  })
})
