// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { LANGS } from '@shared/i18n'
import { TIPS_BY_LANG, TIP_GROUPS, TIP_SOURCES, TOPICS, groupForFamily, searchTips } from './tips'

const FAMILIES = ['sd1', 'sdxl', 'sd3', 'flux1', 'flux2', 'chroma', 'qwen_image', 'z_image', 'krea2', 'ideogram4', 'wan', 'ernie', 'moss_image', 'fibo2', 'flux3', 'anima', 'lumina', 'auraflow']

describe('tips & tricks', () => {
  it('has complete groups with unique ids and sources as links', () => {
    expect(new Set(TIP_GROUPS.map((g) => g.id)).size).toBe(TIP_GROUPS.length)
    for (const g of TIP_GROUPS) {
      expect(g.title && g.intro).toBeTruthy()
      expect(g.tips.length).toBeGreaterThan(0)
      for (const t of g.tips) expect(t.title && t.body).toBeTruthy()
    }
    for (const s of TIP_SOURCES) expect(s.url).toMatch(/^https:\/\//)
  })

  it("finds the group of the chosen model's family", () => {
    expect(groupForFamily('flux1')?.id).toBe('flux1')
    expect(groupForFamily('nope')).toBeUndefined()
    expect(groupForFamily(undefined)).toBeUndefined()
    for (const t of TOPICS) expect(groupForFamily(t)).toBeUndefined()
  })

  it('searches all words in a tip', () => {
    const hits = searchTips(TIP_GROUPS, 'fisherman pier')
    expect(hits.length).toBeGreaterThan(0)
    expect(searchTips(TIP_GROUPS, 'no-such-word-anywhere')).toEqual([])
    expect(searchTips(TIP_GROUPS, '  ')).toBe(TIP_GROUPS)
  })

  it('covers every model family and topic', () => {
    for (const id of [...TOPICS, ...FAMILIES]) expect(TIP_GROUPS.map((g) => g.id)).toContain(id)
  })
})

describe('the tips in the other languages', () => {
  it('every language of the app has its tips', () => {
    expect(Object.keys(TIPS_BY_LANG).sort()).toEqual(LANGS.filter((l) => l !== 'en').slice().sort())
  })
  for (const [lang, other] of Object.entries(TIPS_BY_LANG)) {
    it(`${lang} has the same groups, tips, pictures and sources; prompts stay English`, () => {
      expect(other.groups.map((g) => g.id)).toEqual(TIP_GROUPS.map((g) => g.id))
      expect(other.sources).toEqual(TIP_SOURCES)
      TIP_GROUPS.forEach((g, i) => {
        const o = other.groups[i]
        expect(o.title && o.intro).toBeTruthy()
        expect(o.tips.length).toBe(g.tips.length)
        g.tips.forEach((tip, j) => {
          const x = o.tips[j]
          expect(x.title && x.body).toBeTruthy()
          // a prompt is written for the model, which reads English best
          expect(x.example).toBe(tip.example)
          expect(x.do?.length).toBe(tip.do?.length)
          expect(x.avoid?.length).toBe(tip.avoid?.length)
          expect(x.images?.map((im) => [im.file, im.prompt])).toEqual(tip.images?.map((im) => [im.file, im.prompt]))
        })
      })
    })
  }
})
