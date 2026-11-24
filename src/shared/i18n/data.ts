// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Texts of the data files in the other languages: the descriptions of the recommended models
// (src/shared/data/curated_models.json), the helper models and photo tools (engines/diffusers/helpers.json,
// photo_tools.json) and the groups and notes of the licence list (src/shared/data/licenses.json). The English stays in
// those files; locales/<lang>/data.json holds the translations by id (licences: by the English text). The tips have a
// file of their own per language (locales/<lang>/tips.json).
/// <reference types="vite/client" />
import type { Lang } from '.'
import photoTools from '../../../engines/diffusers/photo_tools.json'

export interface ToolTexts {
  name: string
  summary: string
  description: string
  defaultLabel?: string
  variants?: Record<string, { label: string; description: string; warning?: string }>
}

export interface DataTexts {
  /** curated model id -> description */
  curated: Record<string, string>
  /** helper model id -> its texts */
  helpers: Record<string, { name: string; description: string }>
  /** English group of a helper model (and "Photo tools") -> translation */
  groups: Record<string, string>
  /** photo tool id -> its texts; variants by their id */
  tools: Record<string, ToolTexts>
  /** English group or note of licenses.json -> translation */
  licences: Record<string, string>
}

const FILES = import.meta.glob<DataTexts>('./locales/*/data.json', { eager: true, import: 'default' })
/** obj[key] when obj has it itself (an id like "constructor" finds nothing) */
const own = <T>(obj: Record<string, T> | undefined, key: string): T | undefined => (obj && Object.hasOwn(obj, key) ? obj[key] : undefined)

const DATA: Partial<Record<Lang, DataTexts>> = Object.fromEntries(Object.entries(FILES).map(([p, d]) => [p.split('/')[2], d]))

export function curatedText(lang: Lang, id: string, english: string): string {
  return own(own(DATA, lang)?.curated, id) ?? english
}

export function helperText(lang: Lang, id: string, field: keyof DataTexts['helpers'][string], english: string): string {
  return own(own(own(DATA, lang)?.helpers, id), field) ?? english
}

export function toolText(lang: Lang, id: string, field: 'name' | 'summary' | 'description' | 'defaultLabel', english: string): string {
  return own(own(own(DATA, lang)?.tools, id) as Record<string, string> | undefined, field) ?? english
}

export function variantText(lang: Lang, id: string, variant: string, field: 'label' | 'description' | 'warning', english: string): string {
  return own(own(own(own(DATA, lang)?.tools, id)?.variants, variant), field) ?? english
}

export function groupText(lang: Lang, english: string): string {
  return own(own(DATA, lang)?.groups, english) ?? english
}

export function licenceText(lang: Lang, english: string): string {
  return own(own(DATA, lang)?.licences, english) ?? english
}

export { DATA }

const TOOLS = (photoTools as { tools: { id: string; name: string }[] }).tools

/** A photo tool's name in English, for the label a job keeps. */
export const englishToolName = (id: string | undefined): string | undefined => TOOLS.find((t) => t.id === id)?.name

/** A job's label that is a photo tool's English name, in lang; any other label as it is. */
export function toolLabel(lang: Lang, label: string): string {
  const tool = TOOLS.find((t) => t.name === label)
  return tool ? toolText(lang, tool.id, 'name', label) : label
}
