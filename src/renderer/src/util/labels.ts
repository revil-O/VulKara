// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Names that are stored or sent in English, shown in the app's language: styles (a job keeps the style's name) and the
// sampler choices "Default" and "... (flow)" (the engines take the names as they are).

import { styleSlug } from '@shared/styles'
import type { PlainKey } from '@shared/i18n'
import { toolLabel } from '@shared/i18n/data'
import { locale, t, tMaybe } from '../i18n'

/** A style's name as shown; a style the app no longer has keeps the name the job stored. */
export const styleLabel = (name: string): string => tMaybe(`generate.styles.names.${styleSlug(name)}`, name)

const FLOW = ' (flow)'

/** A sampler or noise schedule as shown in the menus. */
export function samplerLabel(name: string): string {
  if (name === 'Default') return t('generate.sampler.default')
  return name.endsWith(FLOW) ? t('generate.sampler.flow', { name: name.slice(0, -FLOW.length) }) : name
}

// the steps of a Restore job as its label names them (RestorePage.vue)
const RESTORE_STEPS: Record<string, PlainKey> = {
  corrected: 'jobs.labels.corrected', 'dust removed': 'jobs.labels.dustRemoved', repaired: 'jobs.labels.repaired',
  'details rebuilt': 'jobs.labels.detailsRebuilt', 'faces restored': 'jobs.labels.facesRestored', coloured: 'jobs.labels.coloured',
  sharpened: 'jobs.labels.sharpened', 'twice the size': 'jobs.labels.twiceTheSize',
}

/** A job's label as shown: the ones the app writes (in English, so the history reads the same in every language)
 * in the app's language; any other label (a photo tool's name) as it is. */
export function jobLabel(label: string): string {
  const up = /^Upscale ×([\d.]+)$/.exec(label)
  if (up) return t('jobs.labels.upscale', { factor: Number(up[1]) })
  if (label === 'Without LoRA') return t('lora.compare.withoutLora') // i18n-ok
  if (label === 'Object removed') return t('jobs.labels.objectRemoved') // i18n-ok
  const restore = /^(Restored|Preview): (.*)$/.exec(label)
  if (restore) {
    const steps = restore[2].split(', ').filter(Boolean).map((s) => (RESTORE_STEPS[s] ? t(RESTORE_STEPS[s]) : s)).join(', ')
    return t(restore[1] === 'Preview' ? 'jobs.labels.preview' : 'jobs.labels.restored', { steps })
  }
  return toolLabel(locale.value, label)
}
