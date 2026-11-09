// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The recommended models: a list shipped with the app. Nothing of it is part of the app; "Install" downloads.

import list from '@shared/data/curated_models.json'
import licences from '@shared/data/licenses.json'
import { EDITION, commerciallyUsable } from '@shared/edition'
import type { ImportRequest } from '@shared/api'
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

/** The recommended models this edition offers. */
export const CURATED = ALL.filter((m) => (!EDITION.commercialModelsOnly || commerciallyUsable(licences.models.find((l) => l.id === m.id)))
  && (EDITION.explicitContent === 'choice' || !m.nsfw)
  && (EDITION.comfyui || !COMFY_ONLY.includes(m.family)))

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
