// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// What the page of a LoRA says about it: the description of its makers, the settings they recommend and the
// prompts of their example pictures. Read from Civitai (its API) or Hugging Face (the model card) and kept next
// to the LoRA as info.json, so it is fetched once and still there without a connection.

import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type { LoraExample, LoraInfo } from '@shared/api'

type Raw = Record<string, unknown>
/** Fetches a URL and returns its text; throws with a readable reason. */
export type Fetcher = (url: string, headers: Record<string, string>) => Promise<string>

const CACHE = 'info.json'
const ENTITIES: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', '#39': "'" }

/** The text of a piece of HTML as paragraphs: no tags, no scripts, entities decoded. */
export function htmlToParagraphs(html: string): string[] {
  const text = String(html ?? '')
    .replace(/<(script|style)[\s\S]*?<\/\1>/gi, '')
    .replace(/<li[^>]*>/gi, '\n• ')
    .replace(/<\/(p|div|li|h[1-6]|ul|ol|blockquote|tr)>|<br\s*\/?>|<hr\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&(#x?[0-9a-f]+|[a-z]+|#39);/gi, (all, name: string) => {
      if (name[0] === '#') {
        const code = name[1].toLowerCase() === 'x' ? parseInt(name.slice(2), 16) : parseInt(name.slice(1), 10)
        return Number.isFinite(code) && code > 31 ? String.fromCodePoint(code) : ' '
      }
      return ENTITIES[name.toLowerCase()] ?? all
    })
  return text.split('\n').map((l) => l.replace(/[ \t ]+/g, ' ').trim()).filter(Boolean)
}

/** The text of a Markdown model card as paragraphs: no front matter, pictures, tables or markup. */
export function markdownToParagraphs(markdown: string): string[] {
  return String(markdown ?? '')
    .replace(/^---\n[\s\S]*?\n---\n?/, '')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/<[^>]+>/g, '')
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .split('\n')
    .filter((l) => !/^\s*\|/.test(l))
    .map((l) => l.replace(/^#{1,6}\s*/, '').replace(/^\s*[-*]\s+/, '• ').replace(/[*_`]{1,3}/g, '').trim())
    .filter(Boolean)
}

const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : typeof v === 'string' && v.trim() && Number.isFinite(Number(v)) ? Number(v) : undefined)

function median(values: number[]): number | undefined {
  if (!values.length) return undefined
  const sorted = [...values].sort((a, b) => a - b)
  return sorted[Math.floor((sorted.length - 1) / 2)]
}

function mostCommon(values: string[]): string | undefined {
  const counts = new Map<string, number>()
  for (const v of values) counts.set(v, (counts.get(v) ?? 0) + 1)
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0]
}

/** The strength a prompt gives a LoRA in the notation <lora:name:0.8>; the first one when there are several. */
export function strengthInPrompt(prompt: string): number | undefined {
  const m = /<lora:[^:>]+:(-?\d*\.?\d+)/i.exec(prompt)
  return m ? Number(m[1]) : undefined
}

const KINDS: Record<string, LoraInfo['kind']> = { style: 'style', character: 'person', celebrity: 'person', person: 'person', concept: 'concept', clothing: 'object', objects: 'object', object: 'object', poses: 'concept', background: 'concept', tool: 'concept' }

/** A LoRA's info from what the Civitai API says about its model and its version. */
export function fromCivitai(model: Raw, version: Raw, safe: boolean): LoraInfo {
  const modelId = num(model.id) ?? num(version.modelId)
  const training = (version.trainingDetails ?? {}) as Raw
  const tags = (Array.isArray(model.tags) ? (model.tags as unknown[]) : []).map(String)
  const kind = KINDS[String(training.type ?? '').toLowerCase()] ?? tags.map((t) => KINDS[t.toLowerCase()]).find(Boolean)
  const examples: LoraExample[] = []
  for (const image of (Array.isArray(version.images) ? (version.images as Raw[]) : [])) {
    const meta = (image.meta ?? {}) as Raw
    const prompt = typeof meta.prompt === 'string' ? meta.prompt.trim() : ''
    // the levels of Civitai: 1 and 2 are for everyone, above that is adult content
    if (!prompt || (safe && (num(image.nsfwLevel) ?? 1) > 2)) continue
    examples.push({
      prompt: prompt.replace(/<lora:[^>]+>/gi, '').replace(/\s+,/g, ',').replace(/\s{2,}/g, ' ').trim().slice(0, 1500),
      negative: typeof meta.negativePrompt === 'string' ? meta.negativePrompt.trim().slice(0, 800) || undefined : undefined,
      steps: num(meta.steps), guidance: num(meta.cfgScale), sampler: typeof meta.sampler === 'string' ? meta.sampler : undefined,
      seed: num(meta.seed), strength: strengthInPrompt(prompt), clipSkip: num(meta.clipSkip) ?? num(meta['Clip skip']),
    })
  }
  const settings = (version.settings ?? {}) as Raw
  const params = (training.params ?? {}) as Raw
  const strengths = examples.map((e) => e.strength).filter((s): s is number => s !== undefined)
  const use = Array.isArray(model.allowCommercialUse) ? (model.allowCommercialUse as unknown[]).map(String) : typeof model.allowCommercialUse === 'string' ? [model.allowCommercialUse] : undefined
  return {
    source: 'civitai',
    page: `https://civitai.com/models/${modelId}${num(version.id) ? `?modelVersionId=${num(version.id)}` : ''}`,
    name: typeof model.name === 'string' ? model.name : undefined,
    version: typeof version.name === 'string' ? version.name : undefined,
    creator: typeof (model.creator as Raw | undefined)?.username === 'string' ? String((model.creator as Raw).username) : undefined,
    kind, tags: tags.slice(0, 12),
    baseModel: typeof version.baseModel === 'string' ? version.baseModel : undefined,
    description: htmlToParagraphs(String(model.description ?? '')).slice(0, 60),
    versionNotes: htmlToParagraphs(String(version.description ?? '')).slice(0, 30),
    trainedWords: (Array.isArray(version.trainedWords) ? (version.trainedWords as unknown[]) : []).map((w) => String(w).trim()).filter(Boolean),
    recommended: {
      strength: num(settings.strength) ?? median(strengths),
      minStrength: num(settings.minStrength) ?? (strengths.length > 1 ? Math.min(...strengths) : undefined),
      maxStrength: num(settings.maxStrength) ?? (strengths.length > 1 ? Math.max(...strengths) : undefined),
      fromMakers: num(settings.strength) !== undefined,
      steps: median(examples.map((e) => e.steps).filter((s): s is number => s !== undefined)),
      guidance: median(examples.map((e) => e.guidance).filter((s): s is number => s !== undefined)),
      sampler: mostCommon(examples.map((e) => e.sampler).filter((s): s is string => !!s)),
      clipSkip: num(settings.clipSkip) ?? num(params.clipSkip) ?? median(examples.map((e) => e.clipSkip).filter((s): s is number => s !== undefined)),
      examples: examples.length,
    },
    examples: examples.slice(0, 6),
    commercialUse: use,
    fetchedAt: Date.now(),
  }
}

/** A LoRA's info from the model card (README.md) of its Hugging Face repository. */
export function fromModelCard(repo: string, card: string): LoraInfo {
  const front = /^---\n([\s\S]*?)\n---/.exec(card)?.[1] ?? ''
  const field = (name: string): string | undefined => new RegExp(`^${name}:\\s*["']?(.+?)["']?\\s*$`, 'm').exec(front)?.[1]
  const tags = [...front.matchAll(/^\s*-\s+([A-Za-z0-9][\w .:-]*)$/gm)].map((m) => m[1].trim()).filter((t) => !t.includes('/'))
  const prompts = [...front.matchAll(/^\s*-?\s*text:\s*["']?(.+?)["']?\s*$/gm)].map((m) => m[1].trim()).filter((p) => p && p !== '-')
  const trigger = field('instance_prompt')
  const kind = tags.map((t) => KINDS[t.toLowerCase()]).find(Boolean)
  return {
    source: 'huggingface', page: `https://huggingface.co/${repo}`, name: repo.split('/').pop(), creator: repo.split('/')[0],
    kind, tags: [...new Set(tags)].slice(0, 12), baseModel: field('base_model'),
    description: markdownToParagraphs(card).slice(0, 60), versionNotes: [],
    trainedWords: trigger ? [trigger] : [],
    recommended: { fromMakers: false, examples: prompts.length },
    examples: prompts.slice(0, 6).map((prompt) => ({ prompt })),
    licence: field('license'),
    fetchedAt: Date.now(),
  }
}

export interface InfoSource {
  civitai?: { modelId?: number; versionId?: number }
  huggingface?: string
}

/** Where the info of a LoRA can be read, from its manifest. */
export function infoSource(manifest: Raw): InfoSource {
  const source = (manifest.source ?? {}) as Raw
  const ids = (c: Raw): InfoSource['civitai'] | undefined =>
    num(c.model_id) || num(c.version_id) ? { modelId: num(c.model_id), versionId: num(c.version_id) } : undefined
  if (source.type === 'civitai' && ids(source)) return { civitai: ids(source) }
  if (source.type === 'hf' && typeof source.ref === 'string' && /^[\w.-]+\/[\w.-]+$/.test(source.ref)) return { huggingface: source.ref }
  // a Hugging Face page the user named for a file without a known origin (a Civitai one is kept as civitai)
  if (typeof manifest.huggingface_repo === 'string' && /^[\w.-]+\/[\w.-]+$/.test(manifest.huggingface_repo)) return { huggingface: manifest.huggingface_repo }
  const civitai = ids((manifest.civitai ?? {}) as Raw)
  return civitai ? { civitai } : {}
}

/** The versions of a Civitai model newer than the one installed, for the same base and with a SafeTensor file
 *  (Civitai lists them newest first). */
export function newerVersions(model: Raw, version: Raw, modelId: number | undefined): NonNullable<LoraInfo['newer']> {
  const all = Array.isArray(model.modelVersions) ? (model.modelVersions as Raw[]) : []
  const at = all.findIndex((v) => num(v.id) !== undefined && num(v.id) === num(version.id))
  if (at <= 0 || !modelId) return []
  const safetensors = (v: Raw): boolean => (Array.isArray(v.files) ? (v.files as Raw[]) : [])
    .some((f) => (f.metadata as Raw | undefined)?.format === 'SafeTensor' || /\.safetensors$/i.test(String(f.name ?? '')))
  return all.slice(0, at).filter((v) => num(v.id) && safetensors(v) && (!version.baseModel || v.baseModel === version.baseModel))
    .map((v) => ({ name: typeof v.name === 'string' ? v.name : undefined, ref: `https://civitai.com/models/${modelId}?modelVersionId=${num(v.id)}`,
      baseModel: typeof v.baseModel === 'string' ? v.baseModel : undefined,
      date: String(v.publishedAt ?? v.createdAt ?? '').slice(0, 10) || undefined }))
}

export function cachedInfo(folder: string): LoraInfo | undefined {
  try {
    return existsSync(join(folder, CACHE)) ? (JSON.parse(readFileSync(join(folder, CACHE), 'utf8')) as LoraInfo) : undefined
  } catch {
    return undefined
  }
}

/** Reads the info of a LoRA from its page and keeps it next to the LoRA; undefined when its origin is unknown. */
export async function fetchInfo(folder: string, fetcher: Fetcher, tokens: { civitai?: string; huggingface?: string }, safe: boolean): Promise<LoraInfo | undefined> {
  const manifest = JSON.parse(readFileSync(join(folder, 'lora.json'), 'utf8')) as Raw
  const from = infoSource(manifest)
  let info: LoraInfo | undefined
  if (from.civitai) {
    const headers: Record<string, string> = tokens.civitai ? { Authorization: `Bearer ${tokens.civitai}` } : {}
    let version: Raw = {}
    let modelId = from.civitai.modelId
    if (from.civitai.versionId) {
      version = JSON.parse(await fetcher(`https://civitai.com/api/v1/model-versions/${from.civitai.versionId}`, headers)) as Raw
      modelId ??= num(version.modelId)
    }
    const model = modelId ? (JSON.parse(await fetcher(`https://civitai.com/api/v1/models/${modelId}`, headers)) as Raw) : {}
    if (!from.civitai.versionId) version = ((model.modelVersions as Raw[] | undefined) ?? [])[0] ?? {}
    info = fromCivitai({ ...model, id: modelId }, version, safe)
    const newer = newerVersions(model, version, modelId)
    if (newer.length) info.newer = newer
  } else if (from.huggingface) {
    const headers: Record<string, string> = tokens.huggingface ? { Authorization: `Bearer ${tokens.huggingface}` } : {}
    info = fromModelCard(from.huggingface, await fetcher(`https://huggingface.co/${from.huggingface}/raw/main/README.md`, headers))
  }
  if (info) writeFileSync(join(folder, CACHE), JSON.stringify(info, null, 1))
  return info
}
