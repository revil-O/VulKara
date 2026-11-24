// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The app's own updates: the newest release on GitHub against this version. Chosen, its DMG is downloaded and checked
// (the SHA-256 GitHub lists for it, the version inside, a Developer ID signature of the release team accepted by
// Gatekeeper), copied next to the running app and swapped in by a small script once the app has quit; then it starts.
// Only the public release list is read; nothing of the user's is sent.
import { execFile, spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { accessSync, constants, createWriteStream, existsSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { once } from 'node:events'
import { tmpdir } from 'node:os'
import { basename, dirname, join } from 'node:path'
import { finished } from 'node:stream/promises'
import { compare, type FetchLike } from './runtime_updates'
import type { AppUpdateState } from '@shared/api'
import { EDITION } from '@shared/edition'

export const LATEST_URL = 'https://api.github.com/repos/revil-O/VulKara/releases/latest'
const DOWNLOADS = 'https://github.com/revil-O/VulKara/releases/download/'
/** the Developer ID team the releases are signed with */
export const RELEASE_TEAM = '6M74JN9889'
/** what codesign must find: this app, signed with a Developer ID of that team */
const REQUIREMENT = `identifier "de.netfx2.vulkara" and anchor apple generic and certificate leaf[subject.OU] = "${RELEASE_TEAM}"`
/** a download that sends nothing for this long is given up */
const STALL_MS = 60_000

export interface Release { version: string; notesUrl: string; dmgUrl: string; sha256: string; size: number }

/** The newest release if it is newer than current and has a DMG with a checksum; else undefined. */
export function parseLatest(data: unknown, current: string): Release | undefined {
  const d = data as { tag_name?: unknown; draft?: unknown; prerelease?: unknown; assets?: unknown }
  const version = String(d?.tag_name ?? '').replace(/^v/, '')
  if (!/^\d+\.\d+\.\d+$/.test(version) || d.draft || d.prerelease || compare(version, current) <= 0) return undefined
  const name = `VulKara-${version}-${EDITION.arch}.dmg`  // the Intel-Mac build takes the x64 DMG
  const asset = (Array.isArray(d.assets) ? d.assets : []).find((a) => a?.name === name) as
    { digest?: unknown; browser_download_url?: unknown; size?: unknown } | undefined
  const sha = /^sha256:([0-9a-f]{64})$/.exec(String(asset?.digest ?? ''))
  const url = String(asset?.browser_download_url ?? '')
  if (!sha || url !== `${DOWNLOADS}v${version}/${name}`) return undefined
  return { version, notesUrl: `https://github.com/revil-O/VulKara/releases/tag/v${version}`, dmgUrl: url, sha256: sha[1], size: Number(asset?.size) || 0 }
}

/** Where the running app can be replaced, or why not (not packaged, started from the DMG, a read-only folder). */
export function replaceableBundle(exe: string, packaged: boolean): { bundle?: string; reason?: string } {
  const bundle = dirname(dirname(dirname(exe)))
  if (!packaged || !bundle.endsWith('.app')) return { reason: 'notPackaged' }
  if (bundle.startsWith('/Volumes/') || bundle.includes('/AppTranslocation/')) return { reason: 'notInstalled' }
  try {
    accessSync(dirname(bundle), constants.W_OK)
    accessSync(bundle, constants.W_OK)
  } catch {
    return { reason: 'readOnly' }
  }
  return { bundle }
}

const run = (cmd: string, args: string[]): Promise<{ out: string; err: string }> => new Promise((resolve, reject) => {
  execFile(cmd, args, { timeout: 10 * 60_000 }, (e, out, err) => e ? reject(new Error(`${basename(cmd)}: ${(err || e.message).trim()}`)) : resolve({ out, err }))
})

type Run = typeof run

/** Mounts the DMG read-only and hidden at mount: `diskutil image attach` (macOS 27 calls hdiutil's attach/detach
 *  deprecated; same options on macOS 15, 26 and 27), hdiutil where diskutil has no "image" verb (macOS 14, unchecked). */
export async function attachDmg(dmg: string, mount: string, exec: Run = run): Promise<void> {
  await exec('/usr/sbin/diskutil', ['image', 'attach', '--readOnly', '--nobrowse', '--mountPoint', mount, dmg])
    .catch(async () => {
      // diskutil may have attached it before it failed: free the mount point first
      await exec('/usr/sbin/diskutil', ['eject', 'force', mount]).catch(() => undefined)
      await exec('/usr/bin/hdiutil', ['attach', '-nobrowse', '-readonly', '-noautoopen', '-mountpoint', mount, dmg])
    })
}

/** Ejects the DMG mounted at mount (force: also while a reader still holds it), hdiutil as above. */
export async function detachDmg(mount: string, force = false, exec: Run = run): Promise<void> {
  await exec('/usr/sbin/diskutil', ['eject', ...(force ? ['force'] : []), mount])
    .catch(() => exec('/usr/bin/hdiutil', ['detach', '-quiet', ...(force ? ['-force'] : []), mount]))
}

export interface UpdaterOptions {
  fetcher: FetchLike
  current: string
  exe: string
  packaged: boolean
  pid: number
  /** the arguments the app was started with, for the new one */
  args: string[]
  /** called on every change of the state */
  changed: (s: AppUpdateState) => void
  log?: (line: string) => void
}

export class AppUpdater {
  private state: AppUpdateState
  private checking: Promise<AppUpdateState> | undefined
  private release: Release | undefined
  private readonly opts: UpdaterOptions

  constructor(opts: UpdaterOptions) {
    this.opts = opts
    this.state = { current: opts.current, stage: 'idle', percent: 0 }
    // copies an update left beside the app (it quit while one was being prepared)
    const where = replaceableBundle(opts.exe, opts.packaged)
    if (where.bundle) {
      const dir = dirname(where.bundle)
      try {
        for (const f of readdirSync(dir)) if (/^\.VulKara-\d+\.\d+\.\d+\.app$/.test(f)) rmSync(join(dir, f), { recursive: true, force: true })
      } catch {
        // nothing to clear
      }
    }
  }

  status(): AppUpdateState {
    return { ...this.state, checking: !!this.checking }
  }

  private set(patch: Partial<AppUpdateState>): void {
    this.state = { ...this.state, ...patch }
    this.opts.changed(this.status())
  }

  /** Asks GitHub for the newest release. */
  check(): Promise<AppUpdateState> {
    if (this.checking) return this.checking
    this.checking = (async () => {
      try {
        const res = await this.opts.fetcher(LATEST_URL, { headers: { Accept: 'application/vnd.github+json' }, signal: AbortSignal.timeout(20_000) })
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        this.release = parseLatest(await res.json(), this.opts.current)
        this.set({ checkedAt: Date.now(), available: this.release?.version, notesUrl: this.release?.notesUrl, checkError: undefined })
      } catch (err) {
        this.opts.log?.(`[app update] could not check: ${(err as Error).message}`)
        this.set({ checkedAt: Date.now(), checkError: (err as Error).message })
      }
    })().finally(() => {
      this.checking = undefined
      this.opts.changed(this.status())
    }).then(() => this.status())
    this.opts.changed(this.status())
    return this.checking
  }

  /** Downloads, checks and stages the release, then quits the app through quit(); the script starts the new one. */
  async install(quit: () => void): Promise<void> {
    const rel = this.release
    if (!rel || ['downloading', 'checking', 'restarting'].includes(this.state.stage)) return
    const where = replaceableBundle(this.opts.exe, this.opts.packaged)
    if (!where.bundle) {
      this.set({ stage: 'error', error: where.reason })
      return
    }
    const work = mkdtempSync(join(tmpdir(), 'vulkara-update-'))
    const staged = join(dirname(where.bundle), `.VulKara-${rel.version}.app`)
    const mount = join(work, 'mnt')
    let mounted = false
    try {
      this.set({ stage: 'downloading', percent: 0, error: undefined })
      const dmg = join(work, `VulKara-${rel.version}.dmg`)
      await this.download(rel, dmg)
      this.set({ stage: 'checking', percent: 100 })
      await attachDmg(dmg, mount)
      mounted = true
      const app = join(mount, 'VulKara.app')
      const version = (await run('/usr/bin/plutil', ['-extract', 'CFBundleShortVersionString', 'raw', join(app, 'Contents', 'Info.plist')])).out.trim()
      if (version !== rel.version) throw new Error(`the DMG holds version ${version}`)
      await run('/usr/bin/codesign', ['--verify', '--deep', '--strict', `-R=${REQUIREMENT}`, app])
        .catch(() => { throw new Error('not signed by the VulKara release team') })
      await run('/usr/sbin/spctl', ['--assess', '--type', 'execute', app])
      rmSync(staged, { recursive: true, force: true })
      await run('/usr/bin/ditto', [app, staged])
      // the copy is checked and done: a volume still held (Spotlight, XProtect) does not fail the update
      await detachDmg(mount).catch(() => detachDmg(mount, true)).catch(() => undefined)
      mounted = false
      // waits for this app to quit, swaps the bundles (the old one back if that fails) and starts the new one with
      // the arguments this one got (a test instance keeps its data folder)
      const script = join(work, 'swap.sh')
      writeFileSync(script, [
        'pid="$1"; app="$2"; new="$3"; work="$4"; shift 4',
        // also other instances of the same bundle (a second data folder) must have quit
        'while kill -0 "$pid" 2>/dev/null || pgrep -f "$app/Contents/" >/dev/null; do sleep 0.5; done',
        'old="$app.old"; rm -rf "$old"',
        'if mv "$app" "$old" && mv "$new" "$app"; then rm -rf "$old"; else [ -d "$app" ] || mv "$old" "$app"; rm -rf "$new"; fi',
        'rm -rf "$work"',
        'open -n "$app" --args "$@"',
      ].join('\n') + '\n')
      const args = this.opts.args.filter((a) => !a.startsWith('-psn'))
      spawn('/bin/sh', [script, String(this.opts.pid), where.bundle, staged, work, ...args], { detached: true, stdio: 'ignore' }).unref()
      this.opts.log?.(`[app update] ${this.opts.current} → ${rel.version} staged, restarting`)
      this.set({ stage: 'restarting' })
      quit()
    } catch (err) {
      this.opts.log?.(`[app update] ${(err as Error).message}`)
      if (mounted) await detachDmg(mount, true).catch(() => undefined)
      rmSync(staged, { recursive: true, force: true })
      rmSync(work, { recursive: true, force: true })
      this.set({ stage: 'error', error: (err as Error).message })
    }
  }

  /** The DMG into file, its SHA-256 against the one GitHub lists. */
  private async download(rel: Release, file: string): Promise<void> {
    const stall = new AbortController()
    let timer = setTimeout(() => stall.abort(), STALL_MS)
    const alive = (): void => {
      clearTimeout(timer)
      timer = setTimeout(() => stall.abort(), STALL_MS)
    }
    try {
      await this.save(await this.opts.fetcher(rel.dmgUrl, { signal: stall.signal }), rel, file, alive)
    } catch (err) {
      throw stall.signal.aborted ? new Error('download: no data for a minute') : err
    } finally {
      clearTimeout(timer)
    }
  }

  private async save(res: Response, rel: Release, file: string, alive: () => void): Promise<void> {
    if (!res.ok || !res.body) throw new Error(`download: HTTP ${res.status}`)
    const total = Number(res.headers.get('content-length')) || rel.size
    const hash = createHash('sha256')
    const out = createWriteStream(file)
    out.on('error', () => undefined)  // a write error is reported by once() or finished() below
    let got = 0
    try {
      const reader = res.body.getReader()
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        alive()
        hash.update(value)
        got += value.length
        if (!out.write(value)) await once(out, 'drain')  // rejects on a write error (disk full)
        const percent = total ? Math.min(99, Math.floor((got / total) * 100)) : 0
        if (percent !== this.state.percent) this.set({ percent })
      }
    } finally {
      out.end()
      await finished(out)
    }
    if (hash.digest('hex') !== rel.sha256) throw new Error('the download does not match its checksum')
    if (!existsSync(file)) throw new Error('download: no file')
  }
}
