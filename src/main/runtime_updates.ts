// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Update check of the runtimes: which version of a runtime's key package is installed, and whether a newer one is
// published that the runtime may use. Data-driven: a runtime definition lists its version sources
// (src/main/runtimes.ts, field `versions`); everything here works on that list alone.
//
//   pypi:   a package from pypi.org; the allowed range comes from the engine's requirements.txt, so an update never
//           leaves it (diffusers>=0.41,<1.0 never offers 1.0; mflux==0.20.0 offers nothing until the app pins another)
//   github: a component installed from a GitHub release the app pins (ComfyUI); the update is the app's pin, the
//           newest release on GitHub is only reported
//
// No Electron in here: the fetcher, the clock and the file are handed in, so the logic is tested without network.

import { mkdirSync, readFileSync, readdirSync, renameSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import type { RuntimeComponentUpdate, RuntimeUpdate, RuntimeUpdates } from '@shared/api'
import type { PlainKey } from '@shared/i18n'
import { pinFile } from '@shared/edition'
import { t } from './i18n'

export type VersionSource =
  | { kind: 'pypi'; package: string }
  | {
      kind: 'github'
      /** shown name, e.g. ComfyUI */
      name: string
      /** owner/repository */
      repo: string
      /** the release the app installs */
      pinned: string
      /** file in the runtime folder whose first version number is the installed version */
      versionFile: string
    }

/** What a runtime definition needs for the check (a subset of the definitions in runtimes.ts). */
export interface CheckableRuntime {
  id: string
  /** folder of the engine scripts with its requirements.txt */
  engine: string
  versions?: VersionSource[]
  /** used when versions is not given: the package whose version is shown */
  versionPackage?: string
}

/** A version source with what is known locally: the allowed range and the installed version. */
export interface Target {
  /** cache key of the published versions: pypi:<package> or github:<repo> */
  key: string
  name: string
  url: string
  kind: 'pypi' | 'github'
  /** specifiers from the requirements, e.g. ">=0.41,<1.0" (pypi) */
  spec?: string
  /** the version the app installs (github) */
  pinned?: string
  installed?: string
  /** the runtime is installed but lacks this package (the requirements gained it): an update brings it */
  missing?: boolean
}

export interface RuntimeTargets {
  id: string
  installed: boolean
  targets: Target[]
}

export type FetchLike = (url: string, init?: RequestInit) => Promise<Response>

export const CACHE_TTL = 12 * 60 * 60 * 1000
export const AUTO_INTERVAL = 24 * 60 * 60 * 1000
const TIMEOUT = 15_000
const MAX_BYTES = 40 * 1024 * 1024

// ---------------------------------------------------------------- versions (PEP 440, the parts packages use)

export interface Version {
  release: number[]
  /** a, b or rc with its number */
  pre?: [string, number]
  post?: number
  dev?: number
}

const VERSION_RE = /^v?(\d+(?:\.\d+)*)(?:[-_.]?(a|alpha|b|beta|c|rc|pre|preview)[-_.]?(\d*))?(?:-(\d+)|[-_.]?(post|rev|r)[-_.]?(\d*))?(?:[-_.]?(dev)[-_.]?(\d*))?(?:\+[a-z0-9.]+)?$/i

export function parseVersion(text: string): Version | undefined {
  const m = VERSION_RE.exec(String(text).trim())
  if (!m) return undefined
  const v: Version = { release: m[1].split('.').map(Number) }
  if (m[2]) {
    const phase = m[2].toLowerCase()
    v.pre = [phase.startsWith('a') ? 'a' : phase.startsWith('b') ? 'b' : 'rc', Number(m[3] || 0)]
  }
  if (m[4] !== undefined) v.post = Number(m[4])
  else if (m[5]) v.post = Number(m[6] || 0)
  if (m[7]) v.dev = Number(m[8] || 0)
  return v
}

export const isPrerelease = (v: Version): boolean => v.pre !== undefined || v.dev !== undefined

const PHASE: Record<string, number> = { a: 0, b: 1, rc: 2 }

/** Sort key of the parts after the release: a dev of a final release before its pre-releases, the final after them. */
function tail(v: Version): number[] {
  const pre = v.pre ? [PHASE[v.pre[0]], v.pre[1]] : v.post === undefined && v.dev !== undefined ? [-1, 0] : [9, 0]
  return [...pre, v.post ?? -1, v.dev ?? Infinity]
}

function compareRelease(a: number[], b: number[]): number {
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const d = (a[i] ?? 0) - (b[i] ?? 0)
    if (d) return Math.sign(d)
  }
  return 0
}

export function compareVersions(a: Version, b: Version): number {
  const r = compareRelease(a.release, b.release)
  if (r) return r
  const [ta, tb] = [tail(a), tail(b)]
  for (let i = 0; i < ta.length; i++) if (ta[i] !== tb[i]) return ta[i] < tb[i] ? -1 : 1
  return 0
}

/** Compares two version texts; texts that are no versions sort first. */
export function compare(a: string, b: string): number {
  const [va, vb] = [parseVersion(a), parseVersion(b)]
  if (!va || !vb) return va ? 1 : vb ? -1 : 0
  return compareVersions(va, vb)
}

/** Does a version satisfy specifiers like ">=0.41,<1.0", "==0.20.0", "~=0.2.7", "==1.*"? Empty: any. */
export function satisfies(version: string, spec: string | undefined): boolean {
  const v = parseVersion(version)
  if (!v) return false
  for (const part of (spec ?? '').split(',').map((s) => s.trim()).filter(Boolean)) {
    const m = /^(===|~=|==|!=|<=|>=|<|>)\s*(.+)$/.exec(part)
    if (!m) return false
    const [, op, text] = m
    if (op === '===') {
      if (version !== text) return false
      continue
    }
    if ((op === '==' || op === '!=') && text.endsWith('.*')) {
      const prefix = text.slice(0, -2).split('.').map(Number)
      const same = prefix.every((n, i) => (v.release[i] ?? 0) === n)
      if (same !== (op === '==')) return false
      continue
    }
    const w = parseVersion(text)
    if (!w) return false
    const c = compareVersions(v, w)
    const sameRelease = compareRelease(v.release, w.release) === 0
    const ok =
      op === '==' ? c === 0 :
      op === '!=' ? c !== 0 :
      op === '>=' ? c >= 0 :
      op === '<=' ? c <= 0 :
      // >V never matches a post-release of V, <V never a pre-release of V
      op === '>' ? c > 0 && !(sameRelease && v.post !== undefined && w.post === undefined) :
      op === '<' ? c < 0 && !(sameRelease && isPrerelease(v) && !isPrerelease(w)) :
      // ~=X.Y.Z: >=X.Y.Z and ==X.Y.*
      c >= 0 && w.release.length > 1 && w.release.slice(0, -1).every((n, i) => (v.release[i] ?? 0) === n)
    if (!ok) return false
  }
  return true
}

/** The newest final release of versions inside spec (pre-releases and development releases left out). */
export function newestAllowed(versions: string[], spec?: string): string | undefined {
  let best: string | undefined
  for (const text of versions) {
    const v = parseVersion(text)
    if (!v || isPrerelease(v) || !satisfies(text, spec)) continue
    if (!best || compare(text, best) > 0) best = text
  }
  return best
}

// ---------------------------------------------------------------- requirements and installed versions

/** PEP 503 name: case and runs of - _ . do not matter. */
export const normName = (name: string): string => name.toLowerCase().replace(/[-_.]+/g, '-')

/** The specifiers of a package in a requirements file ('' when listed without a range, undefined when not listed). */
export function requirementSpec(requirements: string, pkg: string): string | undefined {
  const want = normName(pkg)
  for (const raw of requirements.split(/\r?\n/)) {
    const line = raw.replace(/(^|\s)#.*$/, '').split(';')[0].trim()
    const m = /^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$/.exec(line)
    if (!m || line.startsWith('-') || normName(m[1]) !== want) continue
    return m[3].replace(/\s+/g, '')
  }
  return undefined
}

/** The installed version of a package in a venv, from its .dist-info folder (no Python started). */
export function installedPackageVersion(venv: string, pkg: string): string | undefined {
  const want = normName(pkg)
  let pythons: string[] = []
  try {
    pythons = readdirSync(join(venv, 'lib')).filter((n) => n.startsWith('python'))
  } catch {
    return undefined
  }
  for (const py of pythons) {
    let entries: string[] = []
    try {
      entries = readdirSync(join(venv, 'lib', py, 'site-packages'))
    } catch {
      continue
    }
    for (const e of entries) {
      if (!e.endsWith('.dist-info')) continue
      const base = e.slice(0, -'.dist-info'.length)
      const cut = base.lastIndexOf('-')
      if (cut > 0 && normName(base.slice(0, cut)) === want) return base.slice(cut + 1)
    }
  }
  return undefined
}

/** The first version number in a file (e.g. __version__ = "0.38.0"). */
export function versionInFile(path: string): string | undefined {
  try {
    return /(\d+\.\d+(?:\.\d+)*)/.exec(readFileSync(path, 'utf8'))?.[1]
  } catch {
    return undefined
  }
}

export const sourcesOf = (rt: CheckableRuntime): VersionSource[] =>
  rt.versions ?? (rt.versionPackage ? [{ kind: 'pypi', package: rt.versionPackage }] : [])

const PYPI_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/
const GITHUB_REPO = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/

/** What a runtime's definition asks to check, with the range from its requirements and what is installed. */
export function targetsOf(rt: CheckableRuntime, opts: { runtimeDir: string; enginesDir: string; installed: boolean }): RuntimeTargets {
  let requirements = ''
  try {
    requirements = readFileSync(join(opts.enginesDir, rt.engine, pinFile('requirements')), 'utf8')
  } catch {
    // no requirements: any version is allowed
  }
  const venv = join(opts.runtimeDir, 'venv')
  const targets: Target[] = []
  for (const s of sourcesOf(rt)) {
    if (s.kind === 'pypi' && PYPI_NAME.test(s.package)) {
      const installed = opts.installed ? installedPackageVersion(venv, s.package) : undefined
      targets.push({
        key: `pypi:${normName(s.package)}`, name: s.package, kind: 'pypi',
        url: `https://pypi.org/pypi/${encodeURIComponent(s.package)}/json`,
        spec: requirementSpec(requirements, s.package),
        installed, missing: opts.installed && installed === undefined,
      })
    }
    else if (s.kind === 'github' && GITHUB_REPO.test(s.repo))
      targets.push({
        key: `github:${s.repo.toLowerCase()}`, name: s.name, kind: 'github',
        url: `https://api.github.com/repos/${s.repo}/releases?per_page=30`,
        pinned: s.pinned,
        installed: opts.installed ? versionInFile(join(opts.runtimeDir, s.versionFile)) : undefined,
      })
  }
  return { id: rt.id, installed: opts.installed, targets }
}

// ---------------------------------------------------------------- published versions

/** Final, not yanked releases from a PyPI JSON answer (https://pypi.org/pypi/<name>/json). */
export function parsePypi(body: unknown): string[] {
  const releases = (body as { releases?: Record<string, { yanked?: boolean }[]> })?.releases
  if (!releases || typeof releases !== 'object') throw new Error('unexpected answer from PyPI')
  return Object.entries(releases)
    .filter(([v, files]) => Array.isArray(files) && files.length > 0 && files.some((f) => !f?.yanked) && parseVersion(v) && !isPrerelease(parseVersion(v)!))
    .map(([v]) => v)
}

/** Released versions from a GitHub releases answer (drafts and pre-releases left out, a leading v dropped). */
export function parseGithubReleases(body: unknown): string[] {
  if (!Array.isArray(body)) throw new Error('unexpected answer from GitHub')
  return body
    .filter((r) => r && !r.draft && !r.prerelease && typeof r.tag_name === 'string')
    .map((r) => String(r.tag_name).replace(/^v/i, ''))
    .filter((v) => { const p = parseVersion(v); return !!p && !isPrerelease(p) })
}

/** Only these hosts are asked, only over https. */
export function allowedUrl(url: string): boolean {
  try {
    const u = new URL(url)
    return u.protocol === 'https:' && !u.username && !u.password && !u.port && ['pypi.org', 'api.github.com'].includes(u.hostname)
  } catch {
    return false
  }
}

async function fetchVersions(fetcher: FetchLike, t: Target): Promise<string[]> {
  if (!allowedUrl(t.url)) throw new Error('address not allowed')
  let res: Response
  try {
    res = await fetcher(t.url, {
      signal: AbortSignal.timeout(TIMEOUT), credentials: 'omit',
      headers: { Accept: t.kind === 'github' ? 'application/vnd.github+json' : 'application/json' },
    })
  } catch (err) {
    throw new Error((err as Error).name === 'TimeoutError' ? 'no answer in time' : 'no connection')
  }
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const text = await res.text()
  if (text.length > MAX_BYTES) throw new Error('answer too large')
  let body: unknown
  try {
    body = JSON.parse(text)
  } catch {
    throw new Error('unreadable answer')
  }
  return t.kind === 'pypi' ? parsePypi(body) : parseGithubReleases(body)
}

// ---------------------------------------------------------------- the decision

export interface Published {
  versions: string[]
  fetchedAt: number
  /** why the last attempt failed (the versions are then the ones fetched before, if any) */
  error?: string
}

export interface Stored {
  checkedAt?: number
  sources: Record<string, Published>
}

// why a check failed, as kept in English (file and log), and its text in the app's language
const CHECK_ERRORS: Record<string, PlainKey> = {
  'no answer in time': 'main.updates.noAnswer', 'no connection': 'main.updates.noConnection',
  'answer too large': 'main.updates.tooLarge', 'unreadable answer': 'main.updates.unreadable',
  'unexpected answer from PyPI': 'main.updates.unexpectedPypi', 'unexpected answer from GitHub': 'main.updates.unexpectedGithub',
  'address not allowed': 'main.updates.notAllowed',
}

function shownError(error: string): string {
  const reason = /^could not check \((.*)\)$/.exec(error)?.[1]
  if (reason === undefined) return error
  return t('main.updates.couldNotCheck', { reason: CHECK_ERRORS[reason] ? t(CHECK_ERRORS[reason]) : reason })
}

export function componentStatus(tg: Target, published: Published | undefined): RuntimeComponentUpdate {
  const versions = published?.versions ?? []
  const latest = tg.kind === 'github' ? tg.pinned : published?.versions.length ? newestAllowed(versions, tg.spec) : undefined
  const newestAll = newestAllowed(versions)
  const status: RuntimeComponentUpdate = {
    name: tg.name, installed: tg.installed, latest,
    updateAvailable: !!latest && (tg.missing === true || (!!tg.installed && compare(latest, tg.installed) > 0)),
  }
  // a release the app does not allow yet: reported, never offered
  if (newestAll && latest && compare(newestAll, latest) > 0) status.newest = newestAll
  if (published?.error) status.error = shownError(published.error)
  else if (!published && tg.kind === 'pypi') status.error = t('main.updates.notChecked')
  return status
}

export function runtimeStatus(rt: RuntimeTargets, stored: Stored): RuntimeUpdate {
  const components = rt.targets.map((t) => componentStatus(t, stored.sources[t.key]))
  const first = components[0]
  const failed = components.find((c) => c.error && !c.latest)
  return {
    id: rt.id as RuntimeUpdate['id'],
    installed: first?.installed, latest: first?.latest,
    updateAvailable: components.some((c) => c.updateAvailable),
    checkedAt: stored.checkedAt,
    error: failed?.error,
    components,
  }
}

// ---------------------------------------------------------------- cache, persistence, checking

export interface CheckerOptions {
  fetcher: FetchLike
  /** the installed runtimes and what to check of them, read anew on every call */
  targets: () => RuntimeTargets[]
  /** where the last result is kept */
  file: string
  now?: () => number
  log?: (line: string) => void
}

export class UpdateChecker {
  private stored: Stored = { sources: {} }
  private running: Promise<RuntimeUpdates> | undefined

  private readonly opts: CheckerOptions

  constructor(opts: CheckerOptions) {
    this.opts = opts
    try {
      const data = JSON.parse(readFileSync(opts.file, 'utf8')) as Stored
      if (data && typeof data === 'object' && data.sources && typeof data.sources === 'object') this.stored = data
    } catch {
      // nothing checked yet
    }
  }

  private now(): number {
    return (this.opts.now ?? Date.now)()
  }

  /** The last result, against what is installed now (no network). */
  status(): RuntimeUpdates {
    return {
      checkedAt: this.stored.checkedAt,
      checking: !!this.running,
      runtimes: this.opts.targets().filter((r) => r.installed).map((r) => runtimeStatus(r, this.stored)),
    }
  }

  /** Is the last check older than age (or was there none)? */
  olderThan(age: number): boolean {
    return !this.stored.checkedAt || this.now() - this.stored.checkedAt >= age
  }

  /** Asks PyPI and GitHub, unless the last check is younger than 12 hours and nothing new is to be checked. */
  check(force = false): Promise<RuntimeUpdates> {
    if (this.running) return this.running
    const targets = this.opts.targets().filter((r) => r.installed).flatMap((r) => r.targets)
    const unknown = targets.some((t) => !this.stored.sources[t.key])
    if (!force && !unknown && !this.olderThan(CACHE_TTL)) return Promise.resolve(this.status())
    this.running = this.fetchAll(targets).finally(() => {
      this.running = undefined
    }).then(() => this.status())
    return this.running
  }

  private async fetchAll(targets: Target[]): Promise<void> {
    const seen = new Map<string, Target>()
    for (const t of targets) if (!seen.has(t.key)) seen.set(t.key, t)
    await Promise.all([...seen.values()].map(async (t) => {
      try {
        this.stored.sources[t.key] = { versions: await fetchVersions(this.opts.fetcher, t), fetchedAt: this.now() }
      } catch (err) {
        const before = this.stored.sources[t.key]
        const error = `could not check (${(err as Error).message})`
        this.opts.log?.(`[runtime updates] ${t.name}: ${error}`)
        this.stored.sources[t.key] = { versions: before?.versions ?? [], fetchedAt: before?.fetchedAt ?? 0, error }
      }
    }))
    this.stored.checkedAt = this.now()
    this.save()
  }

  private save(): void {
    try {
      mkdirSync(dirname(this.opts.file), { recursive: true })
      const tmp = `${this.opts.file}.tmp`
      writeFileSync(tmp, JSON.stringify(this.stored))
      renameSync(tmp, this.opts.file)
    } catch (err) {
      this.opts.log?.(`[runtime updates] could not save the result: ${(err as Error).message}`)
    }
  }
}
