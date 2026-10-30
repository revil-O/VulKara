// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// User settings of the main process and the engines, stored as JSON in the app data folder.

import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, isAbsolute, join } from 'node:path'
import { homedir } from 'node:os'
import { thisMac } from './foreign_mac'
import { DEFAULT_IMAGES_DIR, DEFAULT_MODELS_DIR, dataDir } from './paths'
import type { Settings } from '@shared/settings'
import { DEFAULT_SETTINGS, FOLDER_KEYS } from '@shared/settings'
import { EDITION } from '@shared/edition'
import { LANGS } from '@shared/i18n'
import { t } from './i18n'

const folder = (v: unknown): boolean => typeof v === 'string' && (v === '' || isAbsolute(v))

/** A template of the Restore page as the settings keep it. */
function isTemplate(t: unknown): boolean {
  if (!t || typeof t !== 'object') return false
  const r = t as Record<string, unknown>
  return typeof r.name === 'string' && r.name.length > 0 && r.name.length <= 80 && typeof r.note === 'string' && r.note.length <= 500
    && ['correct', 'repair', 'colorize', 'lock', 'checkFaces'].every((k) => typeof r[k] === 'boolean')
    && typeof r.maxChange === 'number' && r.maxChange >= 0.01 && r.maxChange <= 0.3
}

const VALID: { [K in keyof Settings]: (v: unknown) => boolean } = {
  modelsDir: folder,
  imagesDir: folder,
  historyDir: folder,
  lorasDir: folder,
  helpersDir: folder,
  runtimesDir: folder,
  defaultQuant: (v) => ['auto', 'none', 'q8', 'q4'].includes(v as string),
  memoryReserveGb: (v) => typeof v === 'number' && v >= 0 && v <= 256,
  ssdStreaming: (v) => ['auto', 'always', 'off'].includes(v as string),
  comfyStreaming: (v) => typeof v === 'boolean',
  streamCacheDir: folder,
  stepCache: (v) => ['off', 'light', 'strong'].includes(v as string),
  idleUnloadMinutes: (v) => [0, 5, 10, 30, 60].includes(v as number),
  runtime: (v) => ['auto', 'diffusers', 'mlx'].includes(v as string),
  allowExplicit: (v) => typeof v === 'boolean',
  notifySound: (v) => typeof v === 'boolean',
  theme: (v) => ['system', 'light', 'dark'].includes(v as string),
  language: (v) => v === 'system' || (LANGS as readonly unknown[]).includes(v),
  restoreRules: (v) => Array.isArray(v) && v.length <= 40 && v.every((r) => typeof r === 'string' && r.length <= 300),
  restoreTemplates: (v) => Array.isArray(v) && v.length <= 40 && v.every(isTemplate),
  firstPictureMade: (v) => typeof v === 'boolean',
  hashLookups: (v) => typeof v === 'boolean',
  updateChecks: (v) => typeof v === 'boolean',
  remoteAccess: (v) => typeof v === 'boolean',
  remotePort: (v) => typeof v === 'number' && Number.isInteger(v) && v >= 1024 && v <= 65535,
  remoteToken: (v) => typeof v === 'string' && v.length <= 128,
  remoteHttps: (v) => typeof v === 'boolean',
}

type Listener = (key: keyof Settings) => void
const listeners: Listener[] = []
let cache: Settings | undefined

const file = (): string => join(dataDir(), 'settings.json')

// own keys only: "constructor" or "toString" are in every object, but they are no settings
export const isValidSetting = (key: string, value: unknown): boolean =>
  Object.hasOwn(VALID, key) && VALID[key as keyof Settings](value)

export function getSettings(): Settings {
  if (!cache) {
    let stored: Record<string, unknown> = {}
    try {
      if (existsSync(file())) stored = JSON.parse(readFileSync(file(), 'utf8')) ?? {}
    } catch {
      // unreadable: defaults
    }
    cache = { ...DEFAULT_SETTINGS }
    for (const k of Object.keys(DEFAULT_SETTINGS) as (keyof Settings)[])
      if (Object.hasOwn(stored, k) && VALID[k](stored[k])) (cache as unknown as Record<string, unknown>)[k] = stored[k]
  }
  return { ...cache, ...(EDITION.explicitContent === 'filtered' ? { allowExplicit: false } : {}) }
}

export function setSetting<K extends keyof Settings>(key: K, value: Settings[K]): void {
  if (!isValidSetting(key, value)) throw new Error(t('main.settings.invalidValue', { key: String(key) }))
  if (key === 'allowExplicit' && value === true && EDITION.explicitContent === 'filtered') throw new Error(t('main.settings.alwaysFiltered'))
  const s = getSettings()
  s[key] = value
  cache = s
  mkdirSync(dirname(file()), { recursive: true })
  writeFileSync(file() + '.tmp', JSON.stringify(s, null, 1))
  renameSync(file() + '.tmp', file())
  for (const fn of listeners) fn(key)
}

export function onSettingChanged(fn: Listener): void {
  listeners.push(fn)
}

export const modelsDir = (): string => getSettings().modelsDir || DEFAULT_MODELS_DIR
export const imagesDir = (): string => getSettings().imagesDir || DEFAULT_IMAGES_DIR
export const historyDir = (): string => getSettings().historyDir || join(dataDir(), 'history')
export const lorasDir = (): string => getSettings().lorasDir || join(homedir(), 'VulKara', 'loras')
export const helpersDir = (): string => getSettings().helpersDir || join(homedir(), 'VulKara')
export const runtimesDir = (): string => getSettings().runtimesDir || join(dataDir(), 'runtimes')

/** What a page may set itself: everything but a folder, which it can only return to the default, and the remote
 *  token, which it can only clear (remote.ts then makes a new one: a token never comes from a page). */
export function settableByPage(key: string, value: unknown): boolean {
  if (key === 'remoteToken') return value === ''
  return !(FOLDER_KEYS as readonly string[]).includes(key) || value === ''
}

/** Environment of every engine process (engines/diffusers/paths.py reads it). */
export function engineEnv(): Record<string, string> {
  const s = getSettings()
  const env: Record<string, string> = {
    VK_DATA_DIR: dataDir(), VK_MODELS_DIR: modelsDir(), VK_IMAGES_DIR: imagesDir(), VK_LORAS_DIR: lorasDir(),
    VK_HELPERS_DIR: helpersDir(), VK_SSD_STREAMING: s.ssdStreaming,
    // this Mac's id (a hash, foreign_mac.ts), written into model.json by an import
    VK_MACHINE_ID: thisMac().machine,
    // the libraries' advice to developers (deprecations, fallbacks) is not for the log; errors still are
    TRANSFORMERS_VERBOSITY: 'error', DIFFUSERS_VERBOSITY: 'error', PYTHONWARNINGS: 'ignore',
    // compiled Python files go to the data folder, never into the signed app
    PYTHONPYCACHEPREFIX: join(dataDir(), 'pycache'),
  }
  if (s.hashLookups) env.VK_HASH_LOOKUPS = '1'
  if (!s.allowExplicit) env.VK_SAFE_MODE = '1'
  if (s.memoryReserveGb > 0) env.VK_MEMORY_RESERVE_GB = String(s.memoryReserveGb)
  if (s.streamCacheDir) env.VK_STREAM_CACHE_DIR = s.streamCacheDir
  if (s.stepCache !== 'off') env.VK_STEP_CACHE = s.stepCache
  if (!s.comfyStreaming) env.VK_COMFY_STREAMING = 'off'
  return env
}
