// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import curated from '../data/curated_models.json'
import licences from '../data/licenses.json'
import { DATA, type DataTexts } from './data'

type Raw = Record<string, unknown>
const json = (path: string): Raw => JSON.parse(readFileSync(new URL(path, import.meta.url), 'utf8')) as Raw
const helpers = (json('../../../engines/diffusers/helpers.json').helpers as Raw[])
const tools = (json('../../../engines/diffusers/photo_tools.json').tools as Raw[])

/** what every language has to translate, as the data files have it in English */
function english(): DataTexts {
  const out: DataTexts = { curated: {}, helpers: {}, groups: {}, tools: {}, licences: {} }
  for (const c of curated) out.curated[c.id] = c.description
  for (const h of helpers) {
    out.helpers[String(h.id)] = { name: String(h.name), description: String(h.description) }
    out.groups[String(h.group)] = String(h.group)
  }
  out.groups['Photo tools'] = 'Photo tools'
  for (const t of tools) {
    const variants = t.variants as Record<string, Raw> | undefined
    out.tools[String(t.id)] = {
      name: String(t.name), summary: String(t.summary ?? ''), description: String(t.description),
      ...(t.default_label ? { defaultLabel: String(t.default_label) } : {}),
      ...(variants ? { variants: Object.fromEntries(Object.entries(variants).map(([k, v]) => [k, { label: String(v.label), description: String(v.description), ...(v.warning ? { warning: String(v.warning) } : {}) }])) } : {}),
    }
  }
  for (const m of licences.models) {
    out.licences[m.group] = m.group
    if (m.note) out.licences[m.note] = m.note
  }
  for (const s of licences.software) out.licences[s.group] = s.group
  return out
}

/** every text as [path, text]; a path is a list of keys (licence keys are sentences with dots) */
function leaves(o: unknown, path: string[] = []): [string[], string][] {
  if (typeof o === 'string') return [[path, o]]
  return Object.entries(o as Raw).flatMap(([k, v]) => leaves(v, [...path, k]))
}

describe('texts of the data files', () => {
  const want = leaves(english())
  const keys = (l: [string[], string][]): string[] => l.map(([p]) => JSON.stringify(p)).sort()
  for (const [lang, texts] of Object.entries(DATA)) {
    it(`${lang} translates every text of the data files, and nothing else`, () => {
      expect(keys(leaves(texts))).toEqual(keys(want))
    })
    it(`${lang} has no empty texts`, () => {
      const got = new Map(leaves(texts).map(([p, v]) => [JSON.stringify(p), v]))
      expect(want.filter(([p, v]) => v !== '' && !(got.get(JSON.stringify(p)) ?? '').trim()).map(([p]) => p.join(' / '))).toEqual([])
    })
  }
})
