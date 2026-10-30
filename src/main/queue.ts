// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The job queue. It lives in the main process, so jobs keep running while pages change or reload; the pages
// only see snapshots. One job runs at a time (the engines share the unified memory). A result reaches a job
// only after the content filter passed it.

import { randomUUID } from 'node:crypto'
import { basename } from 'node:path'
import { CONSENT_QUESTION, isSexualPrompt, prohibitedPrompt } from '@shared/content_policy'
import { toEngineJob } from '@shared/engine_job'
import type { QueuedJob } from '@shared/api'
import type { AiLabel, EngineEvent, Job } from '@shared/types'
import { engineLine, mainLanguage, t } from './i18n'

export type QueueEvent = EngineEvent | { event: 'exit'; message: string }

export interface QueueDeps<E = string> {
  /** starts the job on its engine and returns which one; throws when that is not possible */
  dispatch(job: Record<string, unknown>, listener: (event: QueueEvent) => void): E
  stop(engine: E): void
  /** label: write "AI generated .." into the picture once it passed */
  check(path: string, model: string, label?: AiLabel): Promise<{ ok: boolean; reason?: string }>
  now(): number
  changed(): void
  /** a job ended with results (after the content filter), with how long it ran */
  finished?(job: Job, results: string[], timing: { seconds?: number; secondsPerStep?: number }): void
  /** a result the content filter did not pass (or could not check) is removed from the disk */
  discard?(path: string): void
  /** whether an input picture is VulKara's own making with no real photo behind it (a pose editor skeleton): no
   *  consent question for it */
  generated?(path: string): boolean
  log?(line: string): void
}

interface Entry<E> extends QueuedJob {
  engine?: E
  cancelRequested?: boolean
  /** results are checked one after the other, the job ends after the last one */
  delivery: Promise<void>
  /** first progress report: [time, percent] */
  progressStart?: [number, number]
}

const MAX_FINISHED = 200
const FINISHED = ['done', 'failed', 'cancelled']

export class ConsentRequired extends Error {
  constructor() {
    super(CONSENT_QUESTION)
    this.name = 'ConsentRequired'
  }
}

export class JobQueue<E = string> {
  private entries: Entry<E>[] = []
  private running?: Entry<E>

  constructor(private readonly deps: QueueDeps<E>) {}

  /** Adds the job count times (seeds counting up); returns the job ids. */
  add(job: Omit<Job, 'id'>, count = 1): string[] {
    // the restore rules go into the prompt of the edit model, so they are checked with it
    const text = [job.prompt, ...(job.restore?.rules ?? [])].join('\n')
    const refused = prohibitedPrompt(text, mainLanguage().lang)
    if (refused) throw new Error(refused)
    // a picture of a person reaches the model as input, as pose or depth guide, or to be restored; a skeleton of the
    // pose editor shows no person
    const pictures = [job.inputImage, job.controlnet?.image].filter((f): f is string => typeof f === 'string' && !!f)
    const fromPicture = !!job.restore || pictures.some((f) => !this.deps.generated?.(f))
    if (fromPicture && isSexualPrompt(text) && job.consent !== true) throw new ConsentRequired()
    const n = Math.max(1, Math.min(100, Math.floor(Number(count) || 1)))
    const seed = Number.isFinite(job.seed) && job.seed >= 0 ? Math.floor(job.seed) % 2 ** 31 : Math.floor(Math.random() * 2 ** 31)
    const loras = job.loras?.map((l) => ({ ...l, scale: Number.isFinite(Number(l.scale)) ? Number(l.scale) : 0 }))
    const ids: string[] = []
    for (let i = 0; i < n; i++) {
      const id = randomUUID()
      ids.push(id)
      this.entries.push({
        job: { ...job, ...(loras ? { loras } : {}), id, seed: (seed + i) % 2 ** 31, note: undefined }, state: 'waiting', progress: -1, status: '', results: [],
        addedAt: this.deps.now(), delivery: Promise.resolve(),
      })
    }
    this.deps.changed()
    this.pump()
    return ids
  }

  /** A waiting or finished job is removed; the running one is stopped. */
  cancel(id: string): void {
    const entry = this.entries.find((e) => e.job.id === id)
    if (!entry) return
    if (entry.state === 'running') {
      if (!entry.cancelRequested && entry.engine !== undefined) {
        entry.cancelRequested = true
        entry.status = t('main.status.stopping')
        this.deps.stop(entry.engine)
      }
    } else {
      this.entries = this.entries.filter((e) => e !== entry)
    }
    this.deps.changed()
  }

  clearFinished(): void {
    this.entries = this.entries.filter((e) => !FINISHED.includes(e.state))
    this.deps.changed()
  }

  snapshot(): QueuedJob[] {
    return this.entries.map((e) => ({
      job: e.job, state: e.state, progress: e.progress, status: e.status, eta: e.eta, secondsPerStep: e.secondsPerStep, precision: e.precision, waited: e.waited, footprint: e.footprint,
      results: [...e.results], error: e.error, addedAt: e.addedAt, startedAt: e.startedAt, finishedAt: e.finishedAt,
    }))
  }

  get busy(): boolean {
    return this.running !== undefined
  }

  private pump(): void {
    if (this.running) return
    const entry = this.entries.find((e) => e.state === 'waiting')
    if (!entry) return
    this.running = entry
    entry.state = 'running'
    entry.startedAt = this.deps.now()
    entry.status = t('main.status.starting')
    try {
      entry.engine = this.deps.dispatch(toEngineJob(entry.job), (event) => this.onEvent(entry, event))
    } catch (err) {
      entry.error = (err as Error).message
      this.finish(entry)
      return
    }
    this.deps.changed()
  }

  private onEvent(entry: Entry<E>, event: QueueEvent): void {
    if (this.running !== entry) return  // a late event of an earlier job
    switch (event.event) {
      case 'progress':
        this.onProgress(entry, event.value)
        break
      case 'status':
        if (!entry.cancelRequested) entry.status = engineLine(event.message)
        break
      case 'precision':
        entry.precision = event.message
        break
      case 'footprint':
        entry.footprint = { peakGb: event.peak_gb, readGb: event.read_gb, ...(event.plan_gb ? { planGb: event.plan_gb } : {}) }
        break
      case 'waited': {
        // one entry per kind, summed over the pictures of the job
        const same = entry.waited?.find((w) => w.what === event.what)
        if (same) {
          same.seconds += event.seconds
          same.gb += event.gb
        } else entry.waited = [...(entry.waited ?? []), { what: event.what, seconds: event.seconds, gb: event.gb }]
        break
      }
      case 'note':
        // a job can be made differently in more than one way (Diffusers instead of MLX, step caching)
        if (!entry.job.note?.split('\n').includes(event.message))
          entry.job = { ...entry.job, note: entry.job.note ? `${entry.job.note}\n${event.message}` : event.message }
        break
      case 'result': {
        const path = event.path
        entry.delivery = entry.delivery.then(async () => {
          const verdict = await this.deps.check(path, basename(entry.job.modelDir), entry.job.aiLabel).catch((err: Error) => ({ ok: false, reason: err.message }))
          if (verdict.ok) entry.results.push(path)
          else {
            entry.error = verdict.reason || t('main.queue.notPassed')
            // fails closed on the disk too: what was not passed is not left in the pictures folder
            try {
              this.deps.discard?.(path)
            } catch (err) {
              this.deps.log?.(`[queue] an unchecked result could not be removed: ${(err as Error).message}`)
            }
          }
          this.deps.changed()
        })
        return
      }
      case 'error':
        entry.error = event.message
        break
      case 'state':
        if (event.state !== 'idle') return
        void entry.delivery.then(() => this.finish(entry))
        return
      case 'exit':
        if (!entry.cancelRequested && !entry.error) entry.error = event.message || t('main.queue.engineStopped')
        void entry.delivery.then(() => this.finish(entry))
        return
      default:
        return
    }
    this.deps.changed()
  }

  private onProgress(entry: Entry<E>, value: number): void {
    entry.progress = value
    if (value <= 0) return
    const now = this.deps.now()
    if (!entry.progressStart) {
      entry.progressStart = [now, value]
      return
    }
    const [t0, v0] = entry.progressStart
    if (value <= v0) return
    const perPercent = (now - t0) / 1000 / (value - v0)
    entry.eta = Math.max(0, Math.round(perPercent * (100 - value)))
    if (entry.job.steps) entry.secondsPerStep = Math.round(perPercent * (100 / entry.job.steps) * 100) / 100
  }

  private finish(entry: Entry<E>): void {
    if (this.running !== entry) return
    this.running = undefined
    entry.finishedAt = this.deps.now()
    entry.eta = undefined
    entry.status = ''
    entry.state = entry.results.length ? 'done' : entry.cancelRequested ? 'cancelled' : entry.error ? 'failed' : 'done'
    if (entry.state === 'done' && !entry.results.length) {
      entry.state = 'failed'
      entry.error = t('main.queue.noResult')
    }
    try {
      const seconds = entry.startedAt !== undefined ? Math.round((entry.finishedAt - entry.startedAt) / 100) / 10 : undefined
      if (entry.results.length) this.deps.finished?.(entry.job, [...entry.results], { seconds, secondsPerStep: entry.secondsPerStep })
    } catch (err) {
      // the history could not be written (disk full, folder gone): the queue goes on
      this.deps.log?.(`[queue] the finished job could not be saved: ${(err as Error).message}`)
    }
    const finished = this.entries.filter((e) => FINISHED.includes(e.state))
    if (finished.length > MAX_FINISHED) {
      const drop = new Set(finished.slice(0, finished.length - MAX_FINISHED))
      this.entries = this.entries.filter((e) => !drop.has(e))
    }
    this.deps.changed()
    this.pump()
  }
}
