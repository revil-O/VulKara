// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The history: every finished job with the files it produced, one JSON object per line in
// <history folder>/entries.jsonl. The folder is a setting; the pictures themselves stay where they were saved.

import { appendFileSync, closeSync, copyFileSync, existsSync, fstatSync, mkdirSync, openSync, readFileSync, readSync, renameSync, writeFileSync } from 'node:fs'
import { basename, extname, join } from 'node:path'
import type { HistoryPage } from '@shared/api'
import type { HistoryEntry, Job } from '@shared/types'

const FILE = 'entries.jsonl'
const VIDEO = new Set(['.mp4', '.webm'])

export class History {
  private entries?: HistoryEntry[]  // oldest first, as in the file
  private files?: Set<string>  // every file of the entries, built when first asked

  constructor(
    private readonly dir: () => string,
    private readonly changed: () => void = () => {},
  ) {}

  private get file(): string {
    return join(this.dir(), FILE)
  }

  /** The file ends inside a line (an append cut off by a crash). */
  private endsOpen(): boolean {
    if (!existsSync(this.file)) return false
    const fd = openSync(this.file, 'r')
    try {
      const size = fstatSync(fd).size
      if (!size) return false
      const last = Buffer.alloc(1)
      readSync(fd, last, 0, 1, size - 1)
      return last[0] !== 0x0a
    } finally {
      closeSync(fd)
    }
  }

  private load(): HistoryEntry[] {
    if (this.entries) return this.entries
    const out: HistoryEntry[] = []
    if (existsSync(this.file)) {
      for (const line of readFileSync(this.file, 'utf8').split('\n')) {
        if (!line.startsWith('{')) continue
        try {
          const e = JSON.parse(line) as HistoryEntry
          if (e.id && e.job && Array.isArray(e.files)) out.push(e)
        } catch {
          // a damaged line loses one entry, not the history
        }
      }
      out.sort((a, b) => a.createdAt - b.createdAt)
    }
    this.entries = out
    return out
  }

  add(job: Job, files: string[], createdAt = Date.now(), timing: { seconds?: number; secondsPerStep?: number } = {}): HistoryEntry {
    const { consent: _consent, ...kept } = job
    const entry: HistoryEntry = {
      id: job.id, createdAt, job: kept, modelName: basename(job.modelDir) || (job.upscale ? 'Real-ESRGAN' : ''), files,
      kind: files.some((f) => VIDEO.has(extname(f).toLowerCase())) ? 'video' : 'image', ...timing,
    }
    this.load().push(entry)
    for (const f of [...files, job.inputImage, job.maskImage, job.controlnet?.image]) if (typeof f === 'string' && f) this.files?.add(f)
    mkdirSync(this.dir(), { recursive: true })
    appendFileSync(this.file, (this.endsOpen() ? '\n' : '') + JSON.stringify(entry) + '\n')
    this.changed()
    return entry
  }

  /**
   * Newest first. The query's words must all occur in the prompt, the model name or the label. titleOf gives the
   * name the app shows for a model folder, so a model is found under its own name too.
   */
  list(
    opts: { query?: string; offset?: number; limit?: number; favorites?: boolean },
    titleOf?: (folder: string) => string,
  ): HistoryPage {
    const words = (opts.query ?? '').toLowerCase().split(/\s+/).filter(Boolean)
    let found = this.load()
    if (opts.favorites) found = found.filter((e) => e.favorites?.length)
    if (words.length) {
      found = found.filter((e) => {
        const shown = titleOf && e.job.modelDir ? titleOf(e.job.modelDir) : ''
        const text = `${e.job.prompt}\n${e.modelName}\n${shown}\n${e.job.label ?? ''}`.toLowerCase()
        return words.every((w) => text.includes(w))
      })
    }
    const offset = Math.max(0, Math.floor(opts.offset ?? 0))
    const limit = Math.max(1, Math.min(500, Math.floor(opts.limit ?? 100)))
    const newestFirst = found.slice().reverse()
    return { total: found.length, entries: newestFirst.slice(offset, offset + limit) }
  }

  /**
   * Marks one file of an entry as a favourite or takes the mark away. A favourite belongs to its file, not to the
   * whole entry: a job can leave several pictures and only some of them may be worth keeping. False when the entry
   * or the file is not in the history.
   */
  favorite(id: string, file: string, on: boolean): boolean {
    const entry = this.load().find((e) => e.id === id)
    if (!entry || !entry.files.includes(file)) return false
    const marked = new Set(entry.favorites ?? [])
    if (marked.has(file) === on) return true
    if (on) marked.add(file)
    else marked.delete(file)
    // in the order of the files, and no empty list in the file
    const favorites = entry.files.filter((f) => marked.has(f))
    if (favorites.length) entry.favorites = favorites
    else delete entry.favorites
    this.write()
    this.changed()
    return true
  }

  /** The files marked as favourites, newest first. */
  favorites(): string[] {
    return this.load().slice().reverse().flatMap((e) => e.favorites ?? [])
  }

  /** Whether an entry lists this file, as a result or as a picture its job started from (the user gave it then). */
  hasFile(path: string): boolean {
    if (!this.files) {
      this.files = new Set(this.load().flatMap((e) => [
        ...e.files, e.job.inputImage, e.job.maskImage, e.job.controlnet?.image,
      ].filter((f): f is string => typeof f === 'string' && !!f)))
    }
    return this.files.has(path)
  }

  /** Removes entries (their favourites with them) and returns their files (which stay on disk). */
  remove(ids: string[]): string[] {
    const drop = new Set(ids)
    const all = this.load()
    const removed = all.filter((e) => drop.has(e.id))
    if (!removed.length) return []
    this.entries = all.filter((e) => !drop.has(e.id))
    this.files = undefined
    this.write()
    this.changed()
    return removed.flatMap((e) => e.files)
  }

  private write(): void {
    mkdirSync(this.dir(), { recursive: true })
    const tmp = this.file + '.tmp'
    writeFileSync(tmp, (this.entries ?? []).map((e) => JSON.stringify(e)).join('\n') + (this.entries?.length ? '\n' : ''))
    renameSync(tmp, this.file)
  }

  /** Before the folder setting changes: a new folder without a history gets a copy of the current one. */
  relocate(target: string): void {
    const to = join(target, FILE)
    if (to === this.file || existsSync(to) || !existsSync(this.file)) return
    mkdirSync(target, { recursive: true })
    copyFileSync(this.file, to)
  }

  /** After the folder setting changed. */
  reload(): void {
    this.entries = undefined
    this.files = undefined
    this.changed()
  }
}
