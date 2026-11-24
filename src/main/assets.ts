// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Installed models and LoRAs: every folder of the models / LoRA folder with a manifest (model.json, lora.json).

import { existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, realpathSync, symlinkSync, unlinkSync } from 'node:fs'
import { basename, dirname, join } from 'node:path'
import { foreignMac, reimportRequest, thisMac } from './foreign_mac'
import { writeDisplayName } from './manifest'
import { lorasDir, modelsDir } from './settings'
import type { Asset, ModelMeta } from '@shared/types'
import { t } from './i18n'
import { canTrain } from './training'

type Raw = Record<string, unknown>

function readJson(file: string): Raw | undefined {
  try {
    return JSON.parse(readFileSync(file, 'utf8')) as Raw
  } catch {
    return undefined
  }
}

function meta(m: Raw, type: Asset['type'], folder: string): ModelMeta {
  const runtime = m.runtime === 'mlx' || m.runtime === 'comfyui' ? m.runtime : 'diffusers'
  return {
    arch: String(m.arch ?? ''), family: String(m.family ?? ''), label: String(m.label ?? ''), runtime,
    kind: m.kind === 'video' ? 'video' : 'image',
    minRamGb: typeof m.min_ram_gb === 'number' ? m.min_ram_gb : undefined,
    defaults: (m.defaults as ModelMeta['defaults']) ?? undefined,
    maker: (m.maker as ModelMeta['maker']) ?? undefined,
    resolutions: Array.isArray(m.resolutions) ? (m.resolutions as number[]) : undefined,
    samplers: Array.isArray(m.samplers) ? (m.samplers as string[]) : undefined,
    negativePrompt: m.negative_prompt === true, img2img: m.img2img === true,
    inpaint: typeof m.inpaint === 'boolean' ? m.inpaint : undefined,
    inpaintOnly: m.inpaint_only === true, contentFiltered: m.content_filtered === true,
    triggerWords: Array.isArray(m.trigger_words) ? (m.trigger_words as string[]) : undefined,
    // the sub-base (models keep it as sub_base; "variant" there is the weights' file variant, e.g. fp16)
    variant: subBase(m),
    noLoras: m.user_loras === false || undefined,
    bakeBlocked: bakeBlocked(m, runtime),
    // engines/diffusers/export_single.py: SD 1.x and SDXL in folder layout (baked models, imported repositories)
    exportable: (m.family === 'sd1' || m.family === 'sdxl') && (m.layout === 'repo' || m.layout === 'folder') || undefined,
    trainable: canTrain(m) || undefined,
    unsupported: typeof m.unsupported === 'string' && m.unsupported ? m.unsupported : undefined,
    foreignMac: type === 'model' ? foreign(m, folder) : undefined,
  }
}

// imported on another Mac and copied here (foreign_mac.ts)
function foreign(m: Raw, folder: string): ModelMeta['foreignMac'] {
  const other = foreignMac(m, thisMac())
  return other && { ...other, canReimport: reimportRequest(m, folder) !== undefined }
}

// as engines/diffusers/merge.py mergeable(): a LoRA can only be baked into weights that are stored in full
function bakeBlocked(m: Raw, runtime: string): string | undefined {
  const name = String(m.name ?? t('main.assets.thisModel'))
  if (runtime === 'comfyui' || m.layout === 'comfy_files') return t('main.assets.bakeComfy', { name })
  if (m.user_loras === false) return t('main.assets.bakeNoLoras', { name })
  const file = String(m.file ?? '').toLowerCase()
  if (m.layout === 'single_denoiser' && (file.endsWith('.gguf') || ['fp8', 'nf4', 'q4', 'q8'].some((q) => file.includes(q)))) {
    return t('main.assets.bakeCompressed', { name })
  }
  return undefined
}

const SUB_BASES = ['klein4b', 'klein9b', 'dev', '5b', '14b']
function subBase(m: Record<string, unknown>): string | undefined {
  if (typeof m.sub_base === 'string' && m.sub_base) return m.sub_base
  return typeof m.variant === 'string' && SUB_BASES.includes(m.variant) ? m.variant : undefined
}

function scan(root: string, manifest: string, type: Asset['type']): Asset[] {
  if (!existsSync(root)) return []
  const out: Asset[] = []
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    if (entry.name.startsWith('.') || !(entry.isDirectory() || entry.isSymbolicLink())) continue
    const folder = join(root, entry.name)
    const m = readJson(join(folder, manifest))
    if (!m) continue
    const source = m.source as Asset['source'] | undefined
    const picture = typeof m.preview === 'string' ? join(folder, m.preview) : ''
    const name = String(m.name ?? entry.name)
    const own = typeof m.display_name === 'string' ? m.display_name.trim() : ''
    const base = (source as Raw | undefined)?.base_model ?? (m.civitai as Raw | undefined)?.base_model
    out.push({
      id: `${type}:${entry.name}`, title: own || name, name, folder, type, meta: meta(m, type, folder), source,
      preview: picture && existsSync(picture) ? picture : undefined,
      category: typeof m.user_category === 'string' ? m.user_category : undefined,
      baseModel: typeof base === 'string' && base ? base : undefined,
    })
  }
  return out.sort((a, b) => a.title.localeCompare(b.title))
}

export function listAssets(): Asset[] {
  return [...scan(modelsDir(), 'model.json', 'model'), ...scan(lorasDir(), 'lora.json', 'lora')]
}

/** Removes a model or LoRA: its folder goes to the Trash; a link to a folder elsewhere is only unlinked. */
export async function removeAsset(id: string, trash: (path: string) => Promise<void>): Promise<void> {
  const asset = listAssets().find((a) => a.id === id)
  if (!asset) throw new Error(t('main.assets.notInstalled'))
  if (lstatSync(asset.folder).isSymbolicLink()) {
    unlinkSync(asset.folder)
    return
  }
  // the models folder itself may be a link (another disk): the Trash wants the real place
  await trash(join(realpathSync(dirname(asset.folder)), basename(asset.folder)))
}

/**
 * The name the app shows for a model or LoRA, kept in its manifest as display_name. Folder, files and the id stay
 * as they are, so jobs, the history and "use these settings" still find it. An empty title removes the own name.
 */
export function setDisplayName(id: string, title: string): void {
  const asset = listAssets().find((a) => a.id === id)
  if (!asset) throw new Error(t('main.assets.notInstalled'))
  writeDisplayName(join(asset.folder, asset.type === 'model' ? 'model.json' : 'lora.json'), asset.name, title)
}

/** The name shown for the model or LoRA in a folder: its own name, else the folder's name. */
export function titleOfFolder(folder: string, assets: Asset[] = listAssets()): string {
  const name = basename(folder)
  return (assets.find((a) => a.folder === folder) ?? assets.find((a) => a.type === 'model' && basename(a.folder) === name))?.title ?? name
}

/** A model folder that stays where the user has it (imported in place) is listed through a link to it. */
export function adoptFolder(folder: string): void {
  const isLora = existsSync(join(folder, 'lora.json'))
  if (!isLora && !existsSync(join(folder, 'model.json'))) return
  const home = isLora ? lorasDir() : modelsDir()
  mkdirSync(home, { recursive: true })
  const real = realpathSync(folder)
  if (dirname(real) === realpathSync(home)) return  // it is in the folder already
  for (const name of readdirSync(home)) {
    try {
      if (realpathSync(join(home, name)) === real) return  // linked before
    } catch {
      // a link whose target is gone
    }
  }
  let name = basename(real)
  for (let i = 2; existsSync(join(home, name)); i++) name = `${basename(real)}-${i}`
  symlinkSync(real, join(home, name))
}
