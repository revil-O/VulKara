// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// LoRAs that fit a model, and models made from a base (checkpoints, fine-tunes), found on Civitai and Hugging Face
// through their public APIs (no token is sent).
// Answers are kept for ten minutes; preview pictures are fetched here, with a size limit, and handed to the
// page as data URLs, since the page itself loads nothing from the internet.

import { TERMS } from '@shared/licence_terms'
import { LORA_BASES, isInstalled, loraBase, type FindKind, type LoraBase, type LoraHit, type LoraSearchPage, type LoraSearchRequest } from '@shared/lora_bases'
import type { Asset } from '@shared/types'
import { mainLanguage, t } from './i18n'

type Raw = Record<string, unknown>
/** fetch as the main process has it (Electron's net.fetch); injected for the tests */
export type FetchLike = (url: string, init?: RequestInit) => Promise<Response>

const PAGE = 20
const TTL = 10 * 60 * 1000
const TIMEOUT = 10_000
const THUMB_BYTES = 3 * 1024 * 1024
const THUMB_WIDTH = 320

/** Only these hosts are asked: Civitai with its picture and file servers, Hugging Face with its file storage. */
export function allowedHost(url: string): boolean {
  let u: URL
  try {
    u = new URL(url)
  } catch {
    return false
  }
  if (u.protocol !== 'https:' || u.username || u.password || (u.port && u.port !== '443')) return false
  const host = u.hostname.toLowerCase()
  return ['civitai.com', 'huggingface.co', 'hf.co'].some((h) => host === h || host.endsWith('.' + h))
}

const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined)
const str = (v: unknown): string | undefined => (typeof v === 'string' && v.trim() ? v.trim() : undefined)
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])

// ------------------------------------------------------------------ cursors

/** A cursor of this module: which repository (Hugging Face) or page token comes next. */
interface Cursor { i: number; c?: string }

export function encodeCursor(c: Cursor): string {
  return Buffer.from(JSON.stringify(c)).toString('base64url')
}

export function decodeCursor(text: string | undefined): Cursor {
  if (!text) return { i: 0 }
  try {
    const c = JSON.parse(Buffer.from(String(text), 'base64url').toString('utf8')) as Raw
    const i = num(c.i)
    if (i === undefined || i < 0 || i > 20 || !Number.isInteger(i)) return { i: 0 }
    return { i, c: typeof c.c === 'string' && c.c.length < 2000 ? c.c : undefined }
  } catch {
    return { i: 0 }
  }
}

// ------------------------------------------------------------------ Civitai

// Civitai's levels: 1 PG, 2 PG-13, 4 R, 8 X, 16 XXX (a model's level is the sum of its pictures' levels)
const SAFE_LEVELS = 1 | 2
// Civitai's adult flag misses many LoRAs that are made for nudity; their tags and names tell
const ADULT_WORDS = new Set(['nsfw', 'nude', 'nudity', 'naked', 'sex', 'porn', 'hentai', 'explicit', 'boobs', 'breasts', 'tits', 'vagina', 'penis', 'genitals', 'topless', 'lingerie', 'erotic'])
const ADULT_NAME = /(^|[^a-z])(nsfw|nude|nudity|naked|porn|hentai|xxx|sex|erotic)([^a-z]|$)/i

/** A Civitai model made for adult content: flagged, only adult pictures, or tagged or named so. */
export function civitaiAdult(model: Raw): boolean {
  const level = num(model.nsfwLevel) ?? 0
  const tags = list(model.tags).map((t) => String(t).toLowerCase())
  return model.nsfw === true || (level > 0 && !(level & SAFE_LEVELS)) || tags.some((t) => ADULT_WORDS.has(t)) || ADULT_NAME.test(String(model.name ?? ''))
}

export function civitaiUrl(base: LoraBase, query: string | undefined, cursor: string | undefined, safe: boolean, kind: FindKind = 'lora'): string {
  const p = new URLSearchParams({ types: kind === 'model' ? 'Checkpoint' : 'LORA', sort: 'Most Downloaded', limit: String(PAGE) })
  if (safe) p.set('nsfw', 'false')
  for (const b of base.civitai) p.append('baseModels', b)
  if (query) p.set('query', query)
  if (cursor) p.set('cursor', cursor)
  return `https://civitai.com/api/v1/models?${p.toString()}`
}

/** A Civitai picture address at preview width (its path names the size, e.g. /original=true/ or /width=450/). */
export function civitaiThumb(url: string): string | undefined {
  if (!allowedHost(url)) return undefined
  const u = new URL(url)
  const parts = u.pathname.split('/')
  // /<key>/<id>/<options>/<name>, or without options
  if (parts.length === 5 && parts[3].includes('=')) parts[3] = `width=${THUMB_WIDTH}`
  else if (parts.length === 4) parts.splice(3, 0, `width=${THUMB_WIDTH}`)
  else return url
  u.pathname = parts.join('/')
  return u.toString()
}

function civitaiLicence(model: Raw): string | undefined {
  const uses = Array.isArray(model.allowCommercialUse) ? model.allowCommercialUse.map(String)
    : typeof model.allowCommercialUse === 'string' ? [model.allowCommercialUse] : undefined
  if (!uses) return undefined
  const named = uses.filter((u) => u && u !== 'None')
  return named.includes('Image') ? t('main.loras.maySell') : t('main.loras.mayNotSell')
}

const CIVITAI_TYPES: Record<FindKind, string[]> = { lora: ['lora', 'locon', 'dora'], model: ['checkpoint'] }

/** The LoRAs (or checkpoints) of one page of Civitai's model list; safe: no adult models and no adult pictures. */
export function parseCivitai(body: Raw, base: LoraBase, safe: boolean, assets: Asset[], kind: FindKind = 'lora'): LoraSearchPage {
  const hits: LoraHit[] = []
  for (const model of list(body.items) as Raw[]) {
    const id = num(model.id)
    const type = String(model.type ?? '').toLowerCase()
    if (!id || !CIVITAI_TYPES[kind].includes(type)) continue
    const nsfw = civitaiAdult(model)
    if (safe && nsfw) continue
    // the newest version made for this base (any base: the newest), with a SafeTensor file
    const versions = list(model.modelVersions) as Raw[]
    const version = versions.find((v) => (!base.civitai.length || base.civitai.includes(String(v.baseModel))) && hasSafetensors(v))
    if (!version) continue
    const versionId = num(version.id)
    const file = (list(version.files) as Raw[]).find((f) => f.primary === true && isSafetensors(f)) ?? (list(version.files) as Raw[]).find(isSafetensors)
    const image = (list(version.images) as Raw[]).find((i) => (i.type ?? 'image') === 'image' && typeof i.url === 'string'
      && (!safe || (num(i.nsfwLevel) ?? 1) <= 2))
    const imageLevel = image ? num(image.nsfwLevel) ?? 1 : 0
    const page = `https://civitai.com/models/${id}${versionId ? `?modelVersionId=${versionId}` : ''}`
    const hit: LoraHit = {
      source: 'civitai', ref: page, page,
      title: str(model.name) ?? t('main.loras.model', { id }), version: str(version.name),
      author: str((model.creator as Raw | undefined)?.username),
      baseModel: str(version.baseModel),
      downloads: num((model.stats as Raw | undefined)?.downloadCount),
      likes: num((model.stats as Raw | undefined)?.thumbsUpCount),
      triggerWords: [...new Set(list(version.trainedWords).flatMap((w) => String(w).split(',')).map((w) => w.trim()).filter(Boolean))].slice(0, 12),
      sizeMb: file && num(file.sizeKB) ? Math.round(num(file.sizeKB)! / 1024) : undefined,
      previewUrl: image ? civitaiThumb(String(image.url)) : undefined,
      previewExplicit: image ? imageLevel > 2 : undefined,
      nsfw,
      licence: civitaiLicence(model),
      needsToken: version.availability !== undefined && version.availability !== 'Public',
      installed: false,
    }
    hit.installed = isInstalled(hit, assets, kind)
    hits.push(hit)
  }
  const next = str((body.metadata as Raw | undefined)?.nextCursor)
  return { hits, cursor: next ? encodeCursor({ i: 0, c: next }) : undefined }
}

const isSafetensors = (f: Raw): boolean => ((f.metadata as Raw | undefined)?.format === 'SafeTensor' || /\.safetensors$/i.test(String(f.name ?? '')))
  && (f.type === undefined || f.type === 'Model')
const hasSafetensors = (v: Raw): boolean => (list(v.files) as Raw[]).some(isSafetensors)

// ------------------------------------------------------------------ Hugging Face

const HF_EXPAND = ['siblings', 'cardData', 'downloads', 'likes', 'tags', 'author', 'gated']

export function hfUrl(repo: string, query: string | undefined, cursor: string | undefined, kind: FindKind = 'lora'): string {
  const p = new URLSearchParams({ sort: 'downloads', direction: '-1', limit: String(PAGE) })
  // any base (repo ''): pictures models of every kind, by the search words
  if (!repo) {
    p.append('pipeline_tag', 'text-to-image')
    if (kind === 'lora') p.append('filter', 'lora')
  } else if (kind === 'model') p.append('filter', `base_model:finetune:${repo}`)
  else {
    // adapters of the base that are LoRAs (not ControlNets or embeddings)
    p.append('filter', `base_model:adapter:${repo}`)
    p.append('filter', 'lora')
  }
  for (const e of HF_EXPAND) p.append('expand[]', e)
  if (query) p.set('search', query)
  if (cursor) p.set('cursor', cursor)
  return `https://huggingface.co/api/models?${p.toString()}`
}

/** The cursor of the next page in Hugging Face's Link header (<…&cursor=…>; rel="next"). */
export function hfNextCursor(link: string | null): string | undefined {
  const next = /<([^>]+)>\s*;\s*rel="next"/.exec(link ?? '')?.[1]
  if (!next) return undefined
  try {
    return new URL(next).searchParams.get('cursor') ?? undefined
  } catch {
    return undefined
  }
}

/**
 * The LoRA file of a repository, as the import would take it: the one diffusers writes (pytorch_lora_weights),
 * else one named like a LoRA, else the first. Other .safetensors files can be chosen instead.
 */
export function pickLoraFile(files: string[]): string | undefined {
  const ok = files.filter((f) => /\.safetensors$/i.test(f) && !/(^|\/)(diffusion_pytorch_model|model)(-\d+-of-\d+)?\.safetensors$/i.test(f)
    && !/(^|\/)(text_encoder|vae|unet|transformer|tokenizer)\//i.test(f))
  return ok.find((f) => /(^|\/)pytorch_lora_weights\.safetensors$/i.test(f)) ?? ok.find((f) => /lora/i.test(f) && !f.includes('/'))
    ?? ok.find((f) => !f.includes('/')) ?? ok[0]
}

// parts a model needs beside it, never the model itself (FLUX's ae, SD 3.5's clip_g, Wan's umt5 …)
const PART_FILE = /^(ae|vae|clip_[gl]|clip_vision|t5xxl|umt5|text_encoders?|llava)([-_.][^/]*)?\.(safetensors|gguf)$/i

/**
 * What the import takes of a fine-tuned model's repository: the whole repository when it is in diffusers' layout or
 * one the MLX runtime reads (mflux's mflux_model.json, LTX-2.3's split_model.json, FLUX 3's config.json in an MLX repo;
 * file undefined), else a checkpoint file at its top (safetensors, or GGUF – Q4_K_S first, it fits 16 GB); null when
 * neither is there.
 */
export function pickModelFile(files: string[], tags: string[] = []): { file?: string; files?: string[] } | null {
  if (['model_index.json', 'mflux_model.json', 'split_model.json'].some((f) => files.includes(f))) return {}
  if (files.includes('config.json') && tags.some((t) => t === 'mlx' || t === 'mflux')) return {}
  const top = files.filter((f) => !f.includes('/') && !/lora/i.test(f) && !PART_FILE.test(f))
  const ok = [...top.filter((f) => /\.safetensors$/i.test(f)), ...top.filter((f) => /\.gguf$/i.test(f))]
  return ok.length ? { file: ok.find((f) => /q4_k_s\.gguf$/i.test(f)) ?? ok[0], files: ok.slice(0, 30) } : null
}

const NOT_A_MODEL = /control-?net|ip-?adapter|upscaler/i
const ADULT_TAGS = ['not-for-all-audiences', 'nsfw']

/** A picture of the model card's widget, as an address on Hugging Face. */
function hfPreview(repo: string, card: Raw): string | undefined {
  for (const w of list(card.widget) as Raw[]) {
    const url = str((w?.output as Raw | undefined)?.url)
    if (!url || !/\.(png|jpe?g|webp)$/i.test(url)) continue
    const full = /^https:\/\//.test(url) ? url : `https://huggingface.co/${repo}/resolve/main/${url.replace(/^\.?\//, '').split('/').map(encodeURIComponent).join('/')}`
    if (allowedHost(full)) return full
  }
  return undefined
}

/** The base a repository names (base_model:…:<repo>), as the app calls it; for a search over all bases. */
function hfBaseLabel(tags: string[]): string | undefined {
  const repos = tags.filter((t) => t.startsWith('base_model:')).map((t) => t.split(':').pop()!)
  return LORA_BASES.find((b) => b.hf.some((r) => repos.includes(r.toLowerCase())))?.label
}

function hfLicence(card: Raw, tags: string[]): string | undefined {
  const id = String(card.license ?? tags.find((t) => t.startsWith('license:'))?.slice(8) ?? '').toLowerCase()
  const name = typeof card.license_name === 'string' ? card.license_name.toLowerCase() : ''
  const terms = TERMS[id] ?? TERMS[name]
  return terms?.name ?? (name || (id && id !== 'other' ? id : undefined))
}

/** The LoRAs (or models) of one page of Hugging Face's model list; repositories without a file to take are left out. */
export function parseHf(body: unknown, base: LoraBase, safe: boolean, assets: Asset[], kind: FindKind = 'lora'): LoraHit[] {
  const hits: LoraHit[] = []
  for (const m of list(body) as Raw[]) {
    const repo = str(m.id)
    if (!repo || !/^[\w.-]+\/[\w.-]+$/.test(repo)) continue
    const card = (m.cardData ?? {}) as Raw
    const tags = [...list(m.tags), ...list(card.tags)].map((t) => String(t).toLowerCase())
    const nsfw = tags.some((t) => ADULT_TAGS.includes(t))
    if (safe && nsfw) continue
    const names = (list(m.siblings) as Raw[]).map((s) => String(s.rfilename ?? ''))
    const files = names.filter((f) => /\.safetensors$/i.test(f))
    // a model: not a LoRA, ControlNet, IP-Adapter or upscaler, which Hugging Face lists as fine-tunes too
    const pick = kind === 'model'
      ? (tags.some((t) => t === 'lora' || NOT_A_MODEL.test(t)) || NOT_A_MODEL.test(repo) ? null : pickModelFile(names, tags))
      : { file: pickLoraFile(files), files: files.filter((f) => !/(^|\/)(diffusion_pytorch_model|model)(-\d+-of-\d+)?\.safetensors$/i.test(f)).slice(0, 30) }
    if (!pick || (kind === 'lora' && !pick.file)) continue
    const instance = card.instance_prompt
    const words = (Array.isArray(instance) ? instance : [instance]).map((w) => str(w)).filter((w): w is string => !!w)
    const gated = m.gated === 'auto' || m.gated === 'manual' || m.gated === true
    const preview = hfPreview(repo, card)
    const hit: LoraHit = {
      source: 'hf', ref: repo, page: `https://huggingface.co/${repo}`, file: pick.file, files: pick.files,
      title: repo.split('/')[1], author: str(m.author) ?? repo.split('/')[0], baseModel: base.label || hfBaseLabel(tags),
      downloads: num(m.downloads), likes: num(m.likes), triggerWords: words.slice(0, 12),
      previewUrl: preview, previewExplicit: preview ? nsfw : undefined, nsfw,
      licence: hfLicence(card, tags), gated, needsToken: gated, installed: false,
    }
    hit.installed = isInstalled(hit, assets, kind)
    hits.push(hit)
  }
  return hits
}

// ------------------------------------------------------------------ fetching

async function getJson(fetcher: FetchLike, url: string): Promise<{ body: unknown; link: string | null }> {
  if (!allowedHost(url)) throw new Error(t('main.loras.notAsked'))
  let res: Response
  try {
    res = await fetcher(url, { signal: AbortSignal.timeout(TIMEOUT), headers: { Accept: 'application/json' }, credentials: 'omit' })
  } catch (err) {
    const name = (err as Error).name
    throw new Error(name === 'TimeoutError' || name === 'AbortError' ? t('main.loras.noAnswer') : t('main.loras.unreachable'))
  }
  if (!allowedHost(res.url || url)) throw new Error(t('main.loras.elsewhere'))
  if (res.status === 429) throw new Error(t('main.loras.tooMany'))
  if (!res.ok) throw new Error(t('main.loras.httpError', { status: res.status }))
  return { body: await res.json(), link: res.headers.get('link') }
}

const cache = new Map<string, { at: number; page: LoraSearchPage }>()
/** preview addresses handed out, with whether their picture is adult content: only these are fetched */
const issued = new Map<string, boolean>()

export function clearSearchCache(): void {
  cache.clear()
  issued.clear()
  thumbs.clear()
}

/** The search with "sd" written out ("sd3.5 large" → "stable diffusion 3.5 large"), or undefined without one. */
export function spellSd(query: string): string | undefined {
  const out = query.replace(/\bsd(?=\s|\d|$)/gi, 'stable diffusion ').replace(/\s+/g, ' ').trim()
  return out !== query ? out : undefined
}

/** One page of LoRAs (or models) for a base. Throws with a readable message. */
export async function searchLoras(req: LoraSearchRequest, opts: { fetcher: FetchLike; safe: boolean; assets: Asset[]; now?: number }): Promise<LoraSearchPage> {
  const base = loraBase(String(req?.base ?? ''))
  if (!base) throw new Error(t('main.loras.chooseModel'))
  const source = req.source === 'hf' ? 'hf' : 'civitai'
  const kind: FindKind = req.kind === 'model' ? 'model' : 'lora'
  const query = typeof req.query === 'string' ? req.query.trim().slice(0, 100) || undefined : undefined
  const cursor = decodeCursor(typeof req.cursor === 'string' ? req.cursor : undefined)
  const now = opts.now ?? Date.now()
  // the language too: the licence line is kept as text
  const key = JSON.stringify([base.id, source, kind, query ?? '', cursor, opts.safe, mainLanguage().lang])
  const kept = cache.get(key)
  let page: LoraSearchPage
  if (kept && now - kept.at < TTL) page = kept.page
  else {
    page = source === 'civitai'
      ? parseCivitai((await getJson(opts.fetcher, civitaiUrl(base, query, cursor.c, opts.safe, kind))).body as Raw, base, opts.safe, opts.assets, kind)
      : await hfPage(base, query, cursor, kind, opts)
    // Hugging Face searches the repository's name: "sd 3.5" misses stabilityai/stable-diffusion-3.5-large; the first
    // page also asks with "stable diffusion" and puts those hits first
    const spelled = query && source === 'hf' && !cursor.c && cursor.i === 0 ? spellSd(query) : undefined
    if (spelled) {
      const more = await hfPage(base, spelled, { i: 0 }, kind, opts)
      const seen = new Set(more.hits.map((h) => h.ref))
      page = { hits: [...more.hits, ...page.hits.filter((h) => !seen.has(h.ref))], cursor: page.cursor }
    }
    if (cache.size > 200) cache.delete(cache.keys().next().value!)
    cache.set(key, { at: now, page })
  }
  // installed may have changed since the answer was kept
  const hits = page.hits.map((h) => ({ ...h, installed: isInstalled(h, opts.assets, kind) }))
  for (const h of hits) if (h.previewUrl) issued.set(h.previewUrl, !!h.previewExplicit)
  return { hits, cursor: page.cursor }
}

/** Hugging Face asks one base repository after the other; the cursor says which one and where in it. */
async function hfPage(base: LoraBase, query: string | undefined, cursor: Cursor, kind: FindKind, opts: { fetcher: FetchLike; safe: boolean; assets: Asset[] }): Promise<LoraSearchPage> {
  let { i, c } = cursor
  const hits: LoraHit[] = []
  const seen = new Set<string>()
  // a page full of left-out repositories still moves on; three requests at most per page
  for (let round = 0; round < 3 && i < base.hf.length && hits.length < PAGE / 2; round++) {
    const { body, link } = await getJson(opts.fetcher, hfUrl(base.hf[i], query, c, kind))
    for (const h of parseHf(body, base, opts.safe, opts.assets, kind)) {
      if (seen.has(h.ref)) continue
      seen.add(h.ref)
      hits.push(h)
    }
    c = hfNextCursor(link)
    if (!c) i += 1
  }
  return { hits, cursor: i < base.hf.length ? encodeCursor({ i, c }) : undefined }
}

// ------------------------------------------------------------------ previews

const thumbs = new Map<string, string>()
const IMAGE_TYPES = /^image\/(jpeg|png|webp|gif|avif)$/

/**
 * A preview picture as a data URL; only for addresses a search handed out, and with explicit allowed only.
 * undefined when it can not be had (too large, not a picture, the site does not answer).
 */
export async function previewPicture(url: string, opts: { fetcher: FetchLike; safe: boolean }): Promise<string | undefined> {
  if (typeof url !== 'string' || !issued.has(url) || !allowedHost(url)) return undefined
  if (opts.safe && issued.get(url)) return undefined
  const kept = thumbs.get(url)
  if (kept) return kept
  let res: Response
  try {
    res = await opts.fetcher(url, { signal: AbortSignal.timeout(TIMEOUT), credentials: 'omit' })
  } catch {
    return undefined
  }
  const type = (res.headers.get('content-type') ?? '').split(';')[0].trim().toLowerCase()
  if (!res.ok || !allowedHost(res.url || url) || !IMAGE_TYPES.test(type)) return undefined
  if (Number(res.headers.get('content-length') ?? 0) > THUMB_BYTES) return undefined
  const data = await readLimited(res, THUMB_BYTES)
  if (!data) return undefined
  const dataUrl = `data:${type};base64,${data.toString('base64')}`
  // about 40 MB at most
  if (thumbs.size > 120) thumbs.delete(thumbs.keys().next().value!)
  thumbs.set(url, dataUrl)
  return dataUrl
}

/** The body, or undefined when it grows beyond limit bytes. */
export async function readLimited(res: Response, limit: number): Promise<Buffer | undefined> {
  if (!res.body) {
    const all = Buffer.from(await res.arrayBuffer())
    return all.length > limit ? undefined : all
  }
  const reader = res.body.getReader()
  const chunks: Uint8Array[] = []
  let size = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    size += value.byteLength
    if (size > limit) {
      await reader.cancel().catch(() => undefined)
      return undefined
    }
    chunks.push(value)
  }
  return Buffer.concat(chunks)
}
