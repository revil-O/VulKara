// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The recommended models: a list shipped with the app. Nothing of it is part of the app; "Install" downloads.

import list from '@shared/data/curated_models.json'
import licences from '@shared/data/licenses.json'
import { EDITION, INTEL_FAMILIES, commerciallyUsable, type Edition } from '@shared/edition'
import type { ImportRequest } from '@shared/api'
import type { LoraHit } from '@shared/lora_bases'
import type { Asset } from '@shared/types'
import { t } from '../i18n'

// families only ComfyUI runs (i18n-ok: family names)
const COMFY_ONLY = ['Wan', 'Anima', 'Lumina 2', 'MOSS-Image', 'Fibo 2.0']

export interface CuratedModel {
  id: string
  title: string
  description: string
  source: 'hf' | 'civitai'
  ref: string
  file?: string
  family: string
  group: 'base' | 'community' | 'nsfw'
  min_ram_gb: number
  /** the least memory when the engine streams the 16 bit model from the SSD (only where that needs less) */
  min_ram_gb_streamed?: number
  download_gb: number
  /** the service whose access token the download needs */
  needs_token: 'hf' | 'civitai' | null
  /** the licence has to be accepted on the model's page first */
  gated: boolean
  nsfw: boolean
  tested: string
  default?: boolean
}

const ALL = list as CuratedModel[]

/** Does an edition offer this recommendation? */
export const offers = (e: Edition, m: CuratedModel): boolean => (!e.commercialModelsOnly || commerciallyUsable(licences.models.find((l) => l.id === m.id)))
  && (e.explicitContent === 'choice' || !m.nsfw)
  && (e.comfyui || !COMFY_ONLY.includes(m.family))
  && (e.arch === 'arm64' || INTEL_FAMILIES.includes(m.family))

/** The recommended models this edition offers. */
export const CURATED = ALL.filter((m) => offers(EDITION, m))

// the title in the app's language at the moment it is read
export const GROUPS: { id: CuratedModel['group']; readonly title: string }[] = [
  { id: 'base', get title() { return t('generate.curated.base') } },
  { id: 'community', get title() { return t('generate.curated.community') } },
  { id: 'nsfw', get title() { return t('generate.curated.nsfw') } },
]

/** How the model runs on a Mac with this much memory: in memory, streamed from the SSD (slower), or not at all. */
export function memoryFit(m: CuratedModel, ramGb: number): 'memory' | 'streamed' | 'none' {
  if (!ramGb || m.min_ram_gb <= ramGb) return 'memory'
  return m.min_ram_gb_streamed && m.min_ram_gb_streamed <= ramGb ? 'streamed' : 'none'
}

export const importRequest = (m: CuratedModel): ImportRequest => ({ source: m.source, ref: m.ref, file: m.file, name: m.id })

/** The installed model a recommendation corresponds to: same source, or the folder it installs into. */
export function installedAs(m: CuratedModel, assets: Asset[]): Asset | undefined {
  return assets.find((a) => {
    if (a.type !== 'model') return false
    const folder = a.folder.split('/').pop() ?? ''
    if (folder === m.id) return true
    // models taken over from an older installation are named after their repository
    if (m.source === 'hf' && !m.file && folder.startsWith(m.ref.replace('/', '_'))) return true
    return a.source?.type === m.source && a.source.ref === m.ref && (a.source.file ?? undefined) === m.file
  })
}

/** The page where the licence of a gated model is accepted. */
export const licencePage = (m: CuratedModel): string | undefined =>
  m.source === 'hf' ? `https://huggingface.co/${m.ref}` : /^https:\/\//.test(m.ref) ? m.ref : undefined

const words = (text: string): string[] =>
  text.toLowerCase().replace(/\bsd(?=\s|\d|$)/g, 'stable diffusion ').split(/[^a-z0-9.]+/).filter(Boolean)

/** The recommended models a search names: every word of it in the title, id or repository ("sd" also as Stable
 *  Diffusion), as finder hits. */
export function curatedHits(query: string, source: 'hf' | 'civitai', explicit: boolean): LoraHit[] {
  const want = words(query)
  if (!want.length) return []
  return CURATED
    .filter((m) => m.source === source && (explicit || !m.nsfw))
    .filter((m) => { const have = words(`${m.title} ${m.id} ${m.ref} ${m.file ?? ''}`).join(' '); return want.every((w) => have.includes(w)) })
    .map((m) => ({
      source: m.source, ref: m.ref, page: licencePage(m) ?? m.ref, file: m.file, files: m.file ? [m.file] : undefined,
      title: m.title, baseModel: m.family, triggerWords: [], nsfw: m.nsfw, gated: m.gated, needsToken: !!m.needs_token,
      installed: false, recommended: true,
    }))
}
