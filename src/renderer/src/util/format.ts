// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import type { QueuedJob } from '@shared/api'
import { numLocale, t, type PlainKey } from '../i18n'
import { styleLabel } from './labels'

/** 75 -> "1:15 min", 40 -> "40 s", 3700 -> "1:01 h" */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s} s`
  const pad = (n: number): string => String(n).padStart(2, '0')
  if (s < 3600) return `${Math.floor(s / 60)}:${pad(s % 60)} min`
  return `${Math.floor(s / 3600)}:${pad(Math.floor((s % 3600) / 60))} h`
}

/** 2.345 -> "2.35 s/step" (in the number format of the language) */
export const perStep = (seconds: number): string =>
  t('jobs.perStep', { seconds: seconds.toLocaleString(numLocale(), { maximumFractionDigits: 2, useGrouping: false }) })

const PAGE_NAMES: Record<string, PlainKey> = {
  text: 'jobs.pages.text', image: 'jobs.pages.image', inpaint: 'jobs.pages.inpaint', canvas: 'jobs.pages.canvas', video: 'jobs.pages.video',
  upscale: 'jobs.pages.upscale', illusion: 'jobs.pages.illusion', lora: 'jobs.pages.lora', start: 'jobs.pages.start',
  benchmark: 'jobs.pages.benchmark',
}

export const pageName = (page: string): string => (PAGE_NAMES[page] ? t(PAGE_NAMES[page]) : page)

/** One line that tells jobs apart: size, steps, seed. */
export function jobFacts(q: QueuedJob): string {
  const j = q.job
  if (j.upscale) return t('jobs.upscaleTo', { from: `${j.width}×${j.height}`, to: `${j.width * j.upscale}×${j.height * j.upscale}` })
  const parts = [`${j.width}×${j.height}`]
  // Restore without the AI repair uses no model: steps and seed mean nothing there
  if (j.restore && !j.restore.repair) return parts[0]
  if (j.videoSeconds) parts.push(`${j.videoSeconds} s`)
  if (j.steps) parts.push(t('jobs.steps', { n: j.steps }))
  if (j.style) parts.push(styleLabel(j.style))
  parts.push(t('jobs.seed', { seed: j.seed }))
  return parts.join(' · ')
}

/** What the job is doing right now, e.g. "42 % · 1:10 min left · 2.1 s/step". */
export function jobProgress(q: QueuedJob): string {
  if (q.state === 'waiting') return t('jobs.waiting')
  if (q.state !== 'running') return q.state === 'done' ? t('jobs.done') : q.state === 'cancelled' ? t('jobs.cancelled') : q.error || t('jobs.failed')
  const parts: string[] = []
  if (q.progress > 0) parts.push(`${Math.round(q.progress)} %`)
  else if (q.status) parts.push(q.status)
  if (q.eta !== undefined) parts.push(t('jobs.left', { time: formatDuration(q.eta) }))
  if (q.secondsPerStep) parts.push(perStep(q.secondsPerStep))
  return parts.join(' · ') || t('jobs.starting')
}
