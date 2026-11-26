// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Getting models and LoRAs: downloads from Hugging Face and Civitai, files and folders of the user. The work is
// done by "main.py import_model" of the Diffusers engine; here its runs are queued (one at a time, they are
// large downloads) and their progress is passed on.

import { spawn } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import type { ImportInfo, ImportJob, ImportRequest } from '@shared/api'
import type { Command } from './runtimes'
import { processEnv } from './env'
import { lineSplitter } from './tool_process'
import { engineLine, t } from './i18n'
import type { PlainKey } from '@shared/i18n'

export interface ImportRun {
  done: Promise<Record<string, unknown>>
  cancel(): void
}

/** Starts one run of the importer; onProgress gets its stage reports. */
export type ImportRunner = (req: ImportRequest, dryRun: boolean, onProgress: (stage: string, percent: number) => void) => ImportRun

const REASONS: Record<string, PlainKey> = {
  RepositoryNotFoundError: 'main.imports.repoNotFound',
  GatedRepoError: 'main.imports.gated',
  TokenRejected: 'main.imports.tokenRejected',
  EntryNotFoundError: 'main.imports.noSuchFile',
  LocalEntryNotFoundError: 'main.imports.hfUnreachable',
  ConnectionError: 'main.imports.serverUnreachable',
}

/** What the importer reported, as one sentence for the page. */
export function reason(code: string, message: string): string {
  if (code === 'NotEnoughSpace') return t('main.imports.notEnoughSpace', { free: /(\d+) GB free/.exec(message)?.[1] ?? '?' })
  if (REASONS[code]) return t(REASONS[code])
  const line = message.replace(/\(Request ID:[^)]*\)/g, '').split('\n').map((l) => l.trim()).find(Boolean)
  return line || t('main.imports.failed')
}

export class ImportError extends Error {
  constructor(message: string, readonly code: string) {
    super(message)
  }
}

/** A link without what must not be kept or shown: copied Civitai download links carry the user's API key
 * (?token=…), and user:password@ never belongs into a link. Only Civitai's modelVersionId stays of the query. */
export function publicRef(ref: string): string {
  let u: URL
  try {
    u = new URL(ref.trim())
  } catch {
    return ref.trim()
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return ref.trim()
  const version = u.searchParams.get('modelVersionId')
  u.username = ''
  u.password = ''
  u.hash = ''
  u.search = version ? `?modelVersionId=${encodeURIComponent(version)}` : ''
  return u.toString()
}

/** The runner that spawns the importer. command(args): how to start it, undefined without the runtime. */
export function processRunner(command: (args: string[]) => Command | undefined, env: () => Record<string, string>,
  log: (line: string) => void): ImportRunner {
  return (req, dryRun, onProgress) => {
    // option=value: a value starting with "-" stays a value and is never read as another option
    const args = ['import_model', `--source=${req.source}`, `--ref=${req.ref}`, `--quant=${req.quant ?? 'auto'}`]
    if (req.file) args.push(`--file=${req.file}`)
    if (req.name) args.push(`--name=${req.name}`)
    if (req.force) args.push('--force')
    if (dryRun) args.push('--dry-run')
    const cmd = command(args)
    if (!cmd) {
      return {
        done: Promise.reject(new ImportError(t('main.imports.noRuntime'), 'no_runtime')),
        cancel: () => {},
      }
    }
    const proc = spawn(cmd.command, cmd.args, { env: { ...processEnv(), ...cmd.env, ...env() } })
    let cancelled = false
    const done = new Promise<Record<string, unknown>>((resolve, reject) => {
      let stderr = ''
      let result: Record<string, unknown> | undefined
      let error: { code?: string; message?: string } | undefined
      proc.stdout.on('data', lineSplitter((line) => {
        const space = line.indexOf(' ')
        const tag = line.slice(0, space)
        if (!tag.startsWith('__import_')) return
        let payload: Record<string, unknown>
        try {
          payload = JSON.parse(line.slice(space + 1))
        } catch {
          return
        }
        if (tag === '__import_progress__') onProgress(String(payload.stage ?? ''), Number(payload.progress ?? -1))
        else if (tag === '__import_done__' || tag === '__import_info__') result = payload
        else if (tag === '__import_error__') error = payload
      }))
      proc.stderr.on('data', (data: Buffer) => {
        const text = data.toString()
        stderr = (stderr + text).slice(-2000)
        if (!dryRun) log(text)
      })
      proc.on('error', (err) => reject(new ImportError(err.message, 'failed')))
      proc.on('close', (code) => {
        if (cancelled) reject(new ImportError(t('main.status.cancelled'), 'cancelled'))
        else if (code === 0 && result) resolve(result)
        else if (error) reject(new ImportError(reason(String(error.code ?? ''), String(error.message ?? '')), String(error.code ?? 'failed')))
        else reject(new ImportError(stderr.trim().split('\n').pop() || `exit code ${code}`, 'failed'))
      })
    })
    return { done, cancel: () => { cancelled = true; proc.kill() } }
  }
}

const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined)

/** What a dry run of the importer says, in the words of the app. */
export function toInfo(summary: Record<string, unknown>): ImportInfo {
  const plan = (summary.plan ?? {}) as Record<string, unknown>
  const quant = Object.values((plan.quant ?? {}) as Record<string, string>).find((q) => q && q !== 'none')
  return {
    kind: summary.type === 'lora' ? 'lora' : 'model',
    label: String(summary.label ?? summary.arch ?? ''),
    downloadGb: num(summary.download_gb) ?? 0,
    gated: summary.gated === true,
    fits: typeof plan.fits === 'boolean' ? plan.fits : undefined,
    minRamGb: num(plan.min_ram_gb),
    streamed: plan.streamed === true,
    quant,
    inPlace: summary.in_place === true,
    note: typeof summary.note === 'string' && summary.note ? summary.note : undefined,
    triggerWords: Array.isArray(summary.trigger_words) ? (summary.trigger_words as string[]) : undefined,
    civitai: civitaiOf(summary),
  }
}

function civitaiOf(summary: Record<string, unknown>): ImportInfo['civitai'] {
  const modelId = num(summary.model_id)
  const versionId = num(summary.version_id)
  if (summary.source !== 'civitai' || !modelId || !versionId) return undefined
  const text = (v: unknown): string | undefined => (typeof v === 'string' && v ? v : undefined)
  const versions = (Array.isArray(summary.versions) ? summary.versions as Record<string, unknown>[] : [])
    .filter((v) => num(v.id)).map((v) => ({ id: num(v.id)!, name: text(v.name), baseModel: text(v.base_model), usable: v.usable === true, reason: text(v.reason) }))
  return { modelId, versionId, modelName: text(summary.model_name), versionName: text(summary.version_name), versions }
}

interface Entry extends ImportJob {
  run?: ImportRun
}

const OPEN = ['waiting', 'running']

export class ImportQueue {
  private entries: Entry[] = []
  private running?: Entry

  constructor(
    private readonly runner: ImportRunner,
    private readonly changed: () => void,
    /** something was installed; result: what the importer reported */
    private readonly installed: (result: Record<string, unknown>) => void = () => {},
  ) {}

  async inspect(req: ImportRequest): Promise<ImportInfo> {
    return toInfo(await this.runner(req, true, () => {}).done)
  }

  add(req: ImportRequest, title: string): string {
    const id = randomUUID()
    this.entries.push({ id, title, request: req, state: 'waiting', stage: '', percent: -1 })
    this.changed()
    this.pump()
    return id
  }

  /** The running import is stopped, a waiting or finished one is removed. */
  cancel(id: string): void {
    const entry = this.entries.find((e) => e.id === id)
    if (!entry) return
    if (entry.state === 'running') entry.run?.cancel()
    else this.entries = this.entries.filter((e) => e !== entry)
    this.changed()
  }

  /** only: the finished imports that may go (the remote web UI's: those from the web) */
  clearFinished(only: (job: ImportJob) => boolean = () => true): void {
    this.entries = this.entries.filter((e) => OPEN.includes(e.state) || !only(e))
    this.changed()
  }

  list(): ImportJob[] {
    return this.entries.map(({ run: _run, ...job }) => ({ ...job }))
  }

  get busy(): boolean {
    return this.running !== undefined
  }

  cancelAll(): void {
    this.entries = this.entries.filter((e) => e.state !== 'waiting')
    this.running?.run?.cancel()
  }

  private pump(): void {
    if (this.running) return
    const entry = this.entries.find((e) => e.state === 'waiting')
    if (!entry) return
    this.running = entry
    entry.state = 'running'
    entry.stage = t('main.status.starting')
    entry.run = this.runner(entry.request, false, (stage, percent) => {
      entry.stage = engineLine(stage)
      entry.percent = percent
      this.changed()
    })
    this.changed()
    entry.run.done.then(
      (result) => {
        entry.state = 'done'
        this.installed(result)
      },
      (err: ImportError) => {
        entry.state = err.code === 'cancelled' ? 'cancelled' : 'failed'
        entry.error = err.code === 'cancelled' ? undefined : err.message
      },
    ).finally(() => {
      entry.run = undefined
      entry.stage = ''
      entry.percent = -1
      this.running = undefined
      this.changed()
      this.pump()
    })
  }
}
