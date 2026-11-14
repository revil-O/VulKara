// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The helper models as Models → Installed shows them (engines/diffusers/helpers.json): content filter, Restore,
// pose and depth detection, ControlNets, upscaling. Each is a folder under the helpers folder; it is there when it
// holds its files. The photo tools (photo_tools.ts) are listed with them.

import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import type { HelperModel } from '@shared/api'
import type { Job } from '@shared/types'
import { EDITION } from '@shared/edition'
import { helperText } from '@shared/i18n/data'
import { mainLanguage } from './i18n'

type Raw = Record<string, unknown>
/** what engines/diffusers/pinned.py writes once every file of a download is there and checked */
const PIN_MARK = '.vk-checked.json'
const str = (v: unknown): string => (typeof v === 'string' ? v : '')

function dirBytes(dir: string): number {
  let total = 0
  const stack = [dir]
  while (stack.length) {
    const d = stack.pop() as string
    let entries
    try {
      entries = readdirSync(d, { withFileTypes: true })
    } catch {
      continue
    }
    for (const e of entries) {
      const p = join(d, e.name)
      if (e.isDirectory()) stack.push(p)
      else if (e.isFile()) try { total += statSync(p).size } catch { /* vanished */ }
    }
  }
  return total
}

/** The helpers of the catalog with where they are and whether they are there. */
/** Does the job need a helper whose licence forbids commercial use (CodeFormer, ObjectClear)? A build with
 *  commercialModelsOnly refuses it, whatever sent it (remote web UI, a job from the history). */
export const usesNonCommercialHelper = (job: Pick<Job, 'restore' | 'removeObject'>): boolean =>
  // as the engine reads it: any true value of faces runs CodeFormer
  !!job.restore?.faces || job.removeObject?.method === 'objectclear'

/** The revision pinned.py's mark in a helper's folder was written for, '' when there is none. */
function markedRevision(folder: string): string {
  try {
    return str((JSON.parse(readFileSync(join(folder, PIN_MARK), 'utf8')) as Raw).revision)
  } catch {
    return ''
  }
}

export function listHelpers(enginesDir: string, helpersDir: string): HelperModel[] {
  let helpers: Raw[] = []
  try {
    helpers = (JSON.parse(readFileSync(join(enginesDir, 'diffusers', 'helpers.json'), 'utf8')) as { helpers: Raw[] }).helpers
  } catch {
    return []
  }
  const lang = mainLanguage().lang
  // a build with commercialModelsOnly offers no helper whose licence forbids commercial use (helpers.json commercial)
  return helpers.filter((h) => !EDITION.commercialModelsOnly || h.commercial !== false).map((h) => {
    const folder = join(helpersDir, ...str(h.folder).split('/'))
    // more than a few config files: the weights are there (a download that broke off leaves little)
    const bytes = existsSync(folder) ? dirBytes(folder) : 0
    const sizeMb = Number(h.size_mb) || 0
    return {
      id: str(h.id), name: helperText(lang, str(h.id), 'name', str(h.name)), group: str(h.group),
      description: helperText(lang, str(h.id), 'description', str(h.description)), repo: str(h.repo),
      // a model of many files (RORem, ObjectClear) is half there long before its download ends: only pinned.py's mark
      // counts, and only for the revision pinned now (a new pin downloads it again)
      folder, sizeMb, installed: h.kind === 'rorem' || h.kind === 'objectclear' ? markedRevision(folder) === str(h.revision) && str(h.revision) !== '' : bytes > sizeMb * 0.5 * 1024 ** 2,
      diskMb: Math.round(bytes / 1024 ** 2), required: h.required === true, preview: str(h.preview),
    }
  })
}
