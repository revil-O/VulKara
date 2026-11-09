// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Runtimes: every engine gets its own Python environment in <app data>/runtimes/<id>/, created with uv (which
// also downloads a matching Python). The app ships only the engine scripts; models are never part of the app.

import { app, net } from 'electron'
import { spawn, spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { enginesDir } from './paths'
import { runtimesDir } from './settings'
import type { RuntimeInfo } from '@shared/api'
import { targetsOf, type RuntimeTargets, type VersionSource } from './runtime_updates'
import { EDITION } from '@shared/edition'
import { processEnv } from './env'
import { sha256File, treeHash } from './archive_hash'
import { t } from './i18n'

export type RuntimeId = 'diffusers' | 'mlx' | 'comfyui'

/** How to start a program of a runtime: no shell, the arguments as they are. */
export type Command = { command: string; args: string[]; env: Record<string, string> }

interface Runtime {
  id: RuntimeId
  name: string
  /** in the app's language when the list is asked for */
  description: () => string
  details?: (() => string)[]
  engine: 'diffusers' | 'mlx' | 'comfy'
  /** distribution whose version is shown */
  versionPackage?: string
  /** what the update check compares (runtime_updates.ts): PyPI packages, whose allowed range is read from the
   *  engine's requirements.txt, and components installed from a pinned GitHub release. Without it the
   *  versionPackage is checked. A new runtime gets the check by listing its key packages here. */
  versions?: VersionSource[]
  python: string
  comfyRelease?: string
  /** content of the ComfyUI release archive (archive_hash.treeHash) */
  comfyTree?: string
  /** treeSha256: the content of the archive at that commit */
  extensions?: { name: string; repo: string; commit: string; treeSha256: string }[]
}

// a new release or commit is a reviewed change of these lines, with the content hashes of tools/pin_runtimes.py
const COMFY_RELEASE = '0.44.0'
const COMFY_TREE = '9c1f736c84577505586d3805b0e7040117e79c3bed04acc82f0a91ccbb9e6fc6'
// the exact Python of every runtime: 3.11.18 rejects the compromised eMudhra intermediate certificates in ssl
const PYTHON = '3.11.18'

const CATALOG: Runtime[] = [
  {
    id: 'diffusers', name: 'Diffusers (Apple GPU)', engine: 'diffusers', versionPackage: 'diffusers', python: PYTHON,
    versions: [{ kind: 'pypi', package: 'diffusers' }, { kind: 'pypi', package: 'spandrel' }, { kind: 'pypi', package: 'spandrel_extra_arches' }],
    description: () => t('main.runtimes.diffusersDescription'),
  },
  {
    id: 'mlx', name: 'MLX', engine: 'mlx', versionPackage: 'mflux', python: PYTHON,
    versions: [{ kind: 'pypi', package: 'mflux' }],
    description: () => t('main.runtimes.mlxDescription'),
  },
  {
    id: 'comfyui', name: 'ComfyUI', engine: 'comfy', python: PYTHON, comfyRelease: COMFY_RELEASE,
    comfyTree: COMFY_TREE,
    versions: [{ kind: 'github', name: 'ComfyUI', repo: 'Comfy-Org/ComfyUI', pinned: COMFY_RELEASE, versionFile: 'ComfyUI/comfyui_version.py' }],
    extensions: [{
      name: 'ComfyUI-GGUF', repo: 'city96/ComfyUI-GGUF', commit: '6ea2651e7df66d7585f6ffee804b20e92fb38b8a',
      treeSha256: '253524784d571b44f93cfa4401fc29b132399172f4b83f32aaba03bc04ab094b',
    }],
    description: () => t('main.runtimes.comfyDescription'),
    details: [
      () => t('main.runtimes.comfyGraphs'),
      () => t('main.runtimes.comfyInstall', { release: COMFY_RELEASE }),
      () => t('main.runtimes.comfyAutomatic'),
      () => t('main.runtimes.comfyLinked'),
    ],
  },
]

// uv at a fixed version, checked against the SHA-256 published with that release
export const UV_VERSION = '0.13.7'
const UV_ARCH = process.arch === 'arm64' ? 'aarch64' : 'x86_64'
const UV_SHA256: Record<string, string> = {
  aarch64: '81b811b57e4624df7ed3aac148e0359100d9962f3d9dce00aec533dc2e086731',
  x86_64: '20c47e4c1f630b8abaff8c291fa9b9aa300fef92c4fbff95adf198b55287cda7',
}
const UV_URL = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${UV_ARCH}-apple-darwin.tar.gz`

/** A download that does not match its pinned checksum is removed and refused. */
export function checkDownload(path: string, expected: string, what: string): void {
  const actual = sha256File(path)
  if (actual !== expected) {
    rmSync(path, { force: true })
    throw new Error(t('main.runtimes.checksum', { what, expected: expected.slice(0, 12), actual: actual.slice(0, 12) }))
  }
}

export const runtimeDir = (id: RuntimeId): string => join(runtimesDir(), id)

export function runtimePython(id: RuntimeId): string | undefined {
  const p = join(runtimeDir(id), 'venv', 'bin', 'python')
  return existsSync(p) && existsSync(join(runtimeDir(id), 'runtime.json')) ? p : undefined
}

/** What a runtime of this app version is made of: its package lock and the pinned ComfyUI with its extensions.
 *  Kept in runtime.json at install; when the app brings another one, the runtime is brought to it at the next start. */
/** The Python version a venv runs (pyvenv.cfg only says 3.11: uv links the minor version), undefined without one. */
export function venvPython(venv: string): string | undefined {
  const python = join(venv, 'bin', 'python')
  if (!existsSync(python)) return undefined
  const r = spawnSync(python, ['-c', 'import platform; print(platform.python_version())'], { encoding: 'utf8', timeout: 30000 })
  return r.status === 0 ? r.stdout.trim() : undefined
}

function lockOf(rt: Runtime): string {
  const lock = join(enginesDir(), rt.engine, 'constraints.txt')
  if (!existsSync(lock)) return ''
  const comfy = [rt.python, rt.comfyRelease ?? '', ...(rt.extensions ?? []).map((e) => e.commit)].join(',')
  return createHash('sha256').update(readFileSync(lock)).update(comfy).digest('hex')
}

/** Installed runtimes whose packages are not (or not known to be) the set this app version was tested with: installed
 *  by an earlier version, or reached by a broken release of some package before the lock existed (Pillow 13). */
export function staleRuntimes(): RuntimeId[] {
  return offered().filter((rt) => {
    const want = lockOf(rt)
    if (!want || !runtimePython(rt.id)) return false
    try {
      return JSON.parse(readFileSync(join(runtimeDir(rt.id), 'runtime.json'), 'utf8')).lock !== want
    } catch {
      return true
    }
  }).map((rt) => rt.id)
}

export function dirSize(dir: string): number {
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

const offered = (): Runtime[] => CATALOG.filter((rt) => rt.id !== 'comfyui' || EDITION.comfyui)

/** For the update check: every offered runtime, whether it is installed, and what its definition asks to check. */
export function updateTargets(): RuntimeTargets[] {
  return offered().map((rt) => targetsOf(rt, { runtimeDir: runtimeDir(rt.id), enginesDir: enginesDir(), installed: !!runtimePython(rt.id) }))
}

export function listRuntimes(): RuntimeInfo[] {
  return offered().map((rt) => {
    let info: { version?: string; installedAt?: number } = {}
    try {
      info = JSON.parse(readFileSync(join(runtimeDir(rt.id), 'runtime.json'), 'utf8'))
    } catch {
      // not installed
    }
    const installed = !!runtimePython(rt.id)
    return {
      id: rt.id, name: rt.name, description: rt.description(), details: (rt.details ?? []).map((d) => d()), installed,
      version: info.version, path: runtimeDir(rt.id),
      sizeGb: installed ? Math.round((dirSize(runtimeDir(rt.id)) / 1024 ** 3) * 10) / 10 : 0,
    }
  })
}

function run(cmd: string, args: string[], onLine?: (l: string) => void, env?: Record<string, string>): Promise<void> {
  return new Promise((resolve, reject) => {
    const proc = spawn(cmd, args, { env: { ...processEnv(), ...env } })
    let tail = ''
    const handle = (data: Buffer): void => {
      const text = data.toString()
      tail = (tail + text).slice(-2000)
      for (const line of text.split(/[\r\n]+/)) if (line.trim()) onLine?.(line.trim())
    }
    proc.stdout.on('data', handle)
    proc.stderr.on('data', handle)
    proc.on('error', reject)
    proc.on('close', (code) => (code === 0 ? resolve() : reject(new Error(failure(tail) || `exit ${code}`))))
  })
}

/** Why a package installation failed, in words for the user: a package without a ready-built wheel for this Mac
 * (packages are never compiled here, which would need Apple's command line tools) is named as such. */
export function packageInstallError(message: string): string {
  const pkg = /\b([A-Za-z0-9_.-]+)(?:==[^\s]+)? has no (?:usable )?wheels?/.exec(message)?.[1]
  if (!pkg && !/no usable wheels|building from source is disabled|only-binary/i.test(message)) return message
  return pkg ? t('main.runtimes.notReadyBuilt', { pkg, message }) : t('main.runtimes.notReadyBuiltAny', { message })
}

/** The line of a failed command's output that says why: the first error, not the closing remark after it. */
function failure(output: string): string {
  const lines = output.split(/[\r\n]+/).map((l) => l.trim()).filter(Boolean)
  return lines.find((l) => /error|failed|no such|not found|denied/i.test(l) && !/exit delayed/i.test(l)) ?? lines.pop() ?? ''
}

async function download(url: string, to: string): Promise<void> {
  const res = await net.fetch(url)
  if (!res.ok) throw new Error(t('main.runtimes.downloadFailed', { status: res.status, url }))
  writeFileSync(to, Buffer.from(await res.arrayBuffer()))
}

let uvReady: Promise<string> | undefined

/** uv at its pinned version, downloaded once into the runtimes folder (one download, whoever asks). A uv the Mac has
 * already (Homebrew, the installer of astral) is not used: its version is not the checked one. */
function ensureUv(progress: Progress): Promise<string> {
  uvReady ??= findOrDownloadUv(progress).catch((err) => {
    uvReady = undefined
    throw err
  })
  return uvReady
}

async function findOrDownloadUv(progress: Progress): Promise<string> {
  const bin = join(runtimesDir(), 'bin')
  const uv = join(bin, 'uv')
  if (existsSync(uv)) {
    // a copy of another version (downloaded before uv was pinned) is replaced by the checked one
    let version = ''
    await run(uv, ['--version'], (line) => { version = line }).catch(() => undefined)
    if (version.split(' ')[1] === UV_VERSION) return uv
  }
  progress(t('main.runtimes.downloading', { name: 'uv' }), -1)
  mkdirSync(bin, { recursive: true })
  // unpacked next to its place and moved there, so a broken download never leaves a half uv behind
  const work = join(bin, `unpack-${process.pid}`)
  rmSync(work, { recursive: true, force: true })
  mkdirSync(work, { recursive: true })
  try {
    const archive = join(work, 'uv.tar.gz')
    await download(UV_URL, archive)
    checkDownload(archive, UV_SHA256[UV_ARCH], `uv ${UV_VERSION}`)
    await run('tar', ['-xzf', archive, '-C', work, '--strip-components', '1'])
    if (!existsSync(join(work, 'uv'))) throw new Error(t('main.runtimes.noUvInArchive'))
    renameSync(join(work, 'uv'), uv)
  } finally {
    rmSync(work, { recursive: true, force: true })
  }
  return uv
}

/** Unpacks a GitHub archive (ZIP) into target, replacing it; the archive's single top folder becomes target. tree: its
 * expected content (archive_hash.treeHash); a different archive is refused before anything is replaced. */
async function installArchive(url: string, work: string, target: string, tree: string, what: string): Promise<void> {
  const zip = join(work, 'download.zip')
  const unpack = join(work, 'unpack')
  await download(url, zip)
  rmSync(unpack, { recursive: true, force: true })
  await run('ditto', ['-x', '-k', zip, unpack])
  const inner = readdirSync(unpack).find((n) => !n.startsWith('.'))
  if (!inner) throw new Error(t('main.runtimes.archiveEmpty'))
  if (treeHash(join(unpack, inner)) !== tree) {
    rmSync(unpack, { recursive: true, force: true })
    rmSync(zip, { force: true })
    throw new Error(t('main.runtimes.githubChecksum', { what }))
  }
  rmSync(target, { recursive: true, force: true })
  renameSync(join(unpack, inner), target)
  rmSync(unpack, { recursive: true, force: true })
  rmSync(zip, { force: true })
}

type Progress = (stage: string, percent: number) => void

let installs: Promise<unknown> = Promise.resolve()

/** Installs a runtime. Installations run one after the other: they share uv, its cache and the Python it manages. */
export function installRuntime(id: RuntimeId, progress: Progress): Promise<{ version: string }> {
  progress(t('main.runtimes.waiting'), -1)
  const mine = installs.then(() => installNow(id, progress))
  installs = mine.catch(() => undefined)
  return mine
}

async function installNow(id: RuntimeId, progress: Progress): Promise<{ version: string }> {
  const rt = offered().find((r) => r.id === id)
  if (!rt) throw new Error(`unknown runtime ${id}`)
  const src = join(enginesDir(), rt.engine)
  if (!existsSync(join(src, 'main.py'))) throw new Error(t('main.runtimes.engineFilesMissing', { name: rt.name }))
  const uv = await ensureUv(progress)
  const dir = runtimeDir(id)
  const venv = join(dir, 'venv')
  mkdirSync(dir, { recursive: true })
  // a Python managed by uv inside the runtimes folder, independent of the system's (Homebrew updates)
  const uvEnv = { UV_PYTHON_INSTALL_DIR: join(runtimesDir(), 'python'), UV_CACHE_DIR: join(runtimesDir(), 'cache') }
  progress(t('main.runtimes.preparingPython', { version: rt.python }), -1)
  // a venv on another Python (an earlier version's) is made again; its packages come back from the cache below. The
  // new Python is fetched first, so without a network the old venv stays usable
  if (existsSync(venv) && venvPython(venv) !== rt.python) {
    await run(uv, ['python', 'install', rt.python], undefined, uvEnv)
    rmSync(venv, { recursive: true, force: true })
  }
  if (!existsSync(join(venv, 'bin', 'python')))
    await run(uv, ['venv', '--python', rt.python, '--python-preference', 'only-managed', venv], undefined, uvEnv)

  const requirements = ['-r', join(src, 'requirements.txt')]
  if (rt.comfyRelease) {
    const comfy = join(dir, 'ComfyUI')
    const marker = join(comfy, 'comfyui_version.py')
    if (!(existsSync(marker) && readFileSync(marker, 'utf8').includes(`"${rt.comfyRelease}"`))) {
      progress(t('main.runtimes.downloading', { name: `ComfyUI ${rt.comfyRelease}` }), -1)
      await installArchive(`https://github.com/comfyanonymous/ComfyUI/archive/refs/tags/v${rt.comfyRelease}.zip`, dir, comfy,
        rt.comfyTree ?? '', `ComfyUI ${rt.comfyRelease}`)
    }
    for (const ext of rt.extensions ?? []) {
      const target = join(comfy, 'custom_nodes', ext.name)
      const commitFile = join(target, '.installed_commit')
      if (existsSync(commitFile) && readFileSync(commitFile, 'utf8').trim() === ext.commit) continue
      progress(t('main.runtimes.downloading', { name: ext.name }), -1)
      await installArchive(`https://github.com/${ext.repo}/archive/${ext.commit}.zip`, dir, target, ext.treeSha256, ext.name)
      writeFileSync(commitFile, ext.commit)
    }
    requirements.unshift('-r', join(comfy, 'requirements.txt'))
  }
  progress(t('main.runtimes.installingPackages'), -1)
  // the tested set and nothing else: every package at its locked version, also the ones that only come in through
  // other packages and ComfyUI's own. A sync also takes out what is not in it, so a runtime an untested release had
  // reached (Pillow 13) is whole again without deleting it; unchanged packages stay, the rest comes from the cache.
  const lock = join(src, 'constraints.txt')
  // the key packages move to the newest version their requirements allow (only without a lock)
  const upgrade = (rt.versions ?? []).flatMap((s) => (s.kind === 'pypi' ? ['--upgrade-package', s.package] : []))
  const packages = existsSync(lock) ? ['sync', lock] : ['install', ...upgrade, ...requirements]
  // ready-built wheels only: compiling a package would need Apple's command line tools, which a Mac may not have
  await run(uv, ['pip', packages[0], '--python', join(venv, 'bin', 'python'), '--only-binary', ':all:', ...packages.slice(1)],
    (line) => { if (/^(Downloading|Downloaded|Installed|Prepared|Resolved)/.test(line)) progress(line.slice(0, 80), -1) }, uvEnv)
    .catch((err: Error) => { throw new Error(packageInstallError(err.message)) })

  let version = rt.comfyRelease ?? ''
  if (rt.versionPackage) {
    let out = ''
    await run(join(venv, 'bin', 'python'), ['-c', `import importlib.metadata as m; print(m.version('${rt.versionPackage}'))`],
      (line) => { out = line })
    version = out
  }
  writeFileSync(join(dir, 'runtime.json'), JSON.stringify({ id, version, installedAt: Date.now(), lock: lockOf(rt) }))
  return { version }
}

export function removeRuntime(id: RuntimeId): void {
  if (!CATALOG.some((r) => r.id === id)) throw new Error(`unknown runtime ${id}`)
  rmSync(runtimeDir(id), { recursive: true, force: true })
}

/** How to start an engine: its runtime's Python with the engine's main.py, undefined when not installed. */
export function engineCommand(id: RuntimeId, args: string[] = []): Command | undefined {
  const rt = offered().find((r) => r.id === id)
  const python = runtimePython(id) ?? (id === 'diffusers' && !app.isPackaged ? process.env.VK_DEV_PYTHON : undefined)
  if (!rt || !python) return undefined
  const env: Record<string, string> = {}
  if (id === 'comfyui') env.VK_COMFY_RUNTIME = runtimeDir('comfyui')
  // the MLX engine never downloads: nothing of it may reach the network
  if (id === 'mlx' && !args.length) env.HF_HUB_OFFLINE = '1'
  return { command: python, args: [join(enginesDir(), rt.engine, 'main.py'), ...args], env }
}
