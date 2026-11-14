// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Photo tools: small models that sharpen, denoise, enlarge, clean or cut out a photo (engines/diffusers/photo_tools.py):
// PyTorch weights on the GPU (spandrel) or ONNX files on the CPU. The recommended ones are listed in
// engines/diffusers/photo_tools.json (pinned by commit or URL and checksum); installed ones are folders with a tool.json
// under <helpers>/photo_tools. Selecting objects (SAM 2) is interactive: one long-lived process keeps the tool and the
// picture's encoding and answers each set of clicks in a few hundredths of a second.

import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import type { PhotoTool, RecommendedTool, Selected } from '@shared/api'
import type { Command } from './runtimes'
import { processEnv } from './env'
import { lineSplitter } from './tool_process'
import { mainLanguage, t } from './i18n'
import { toolText, variantText } from '@shared/i18n/data'

type Raw = Record<string, unknown>
const str = (v: unknown): string => (typeof v === 'string' ? v : '')
const runtime = (v: unknown): 'torch' | 'onnx' => (v === 'torch' ? 'torch' : 'onnx')

/** The recommended tools of the catalog; installed: those of them that are there. */
export function recommendedTools(enginesDir: string, toolsDir: string): RecommendedTool[] {
  let tools: Raw[] = []
  try {
    tools = (JSON.parse(readFileSync(join(enginesDir, 'diffusers', 'photo_tools.json'), 'utf8')) as { tools: Raw[] }).tools
  } catch {
    return []
  }
  const have = new Set(installedTools(toolsDir).map((t) => t.recommended).filter(Boolean))
  const lang = mainLanguage().lang
  return tools.map((t) => ({
    id: str(t.id), name: toolText(lang, str(t.id), 'name', str(t.name)), task: str(t.task), kind: str(t.kind) as RecommendedTool['kind'],
    runtime: runtime(t.runtime), summary: str(t.summary) ? toolText(lang, str(t.id), 'summary', str(t.summary)) : undefined,
    description: toolText(lang, str(t.id), 'description', str(t.description)),
    scale: Number(t.scale) || undefined, maxSide: Number(t.max_side) || undefined,
    variants: t.variants && typeof t.variants === 'object'
      ? Object.entries(t.variants as Record<string, Raw>).map(([id, v]) => ({
        id, label: variantText(lang, str(t.id), id, 'label', str(v.label) || id),
        description: variantText(lang, str(t.id), id, 'description', str(v.description)), sizeMb: Number(v.size_mb) || 0,
      }))
      : undefined,
    defaultLabel: str(t.default_label) ? toolText(lang, str(t.id), 'defaultLabel', str(t.default_label)) : undefined, quality: t.quality === true, sizeMb: Number(t.size_mb) || 0, licence: str(t.licence),
    licenceUrl: str(t.licence_url), licenceNote: str(t.licence_note) || undefined, sourceUrl: str(t.source_url),
    installed: have.has(str(t.id)),
  }))
}

/** The installed tools (folders with a tool.json of type photo_tool). */
export function installedTools(toolsDir: string): PhotoTool[] {
  if (!existsSync(toolsDir)) return []
  const out: PhotoTool[] = []
  for (const name of readdirSync(toolsDir).sort()) {
    const folder = join(toolsDir, name)
    let m: Raw
    try {
      m = JSON.parse(readFileSync(join(folder, 'tool.json'), 'utf8')) as Raw
    } catch {
      continue
    }
    if (m.type !== 'photo_tool') continue
    // a tool of the catalog in the app's language; one of the user's own as its tool.json has it
    const [id, lang] = [str(m.recommended), mainLanguage().lang]
    out.push({
      folder, name: toolText(lang, id, 'name', str(m.name) || name), task: str(m.task), kind: str(m.kind) as PhotoTool['kind'],
      runtime: runtime(m.runtime), summary: str(m.summary) ? toolText(lang, id, 'summary', str(m.summary)) : undefined,
      description: toolText(lang, id, 'description', str(m.description)), scale: Number(m.scale) || 1, maxSide: Number(m.max_side) || undefined,
      licence: str(m.licence) || undefined, licenceUrl: str(m.licence_url) || undefined,
      licenceNote: str(m.licence_note) || undefined,
      sourceUrl: str(m.source_url) || undefined, recommended: str(m.recommended) || undefined,
    })
  }
  return out
}

interface Answer {
  mask?: string
  score?: number
  pick?: number
  candidates?: number
  error?: string
}

/** The selection process (main.py photo_select): JSON lines in and out, one answer per request. */
export class PhotoSelector {
  private proc?: ChildProcessWithoutNullStreams
  private waiting = new Map<number, (a: Answer) => void>()
  private nextId = 1

  constructor(
    private readonly command: () => Command | undefined,
    private readonly env: () => Record<string, string>,
    private readonly log: (line: string) => void,
  ) {}

  private start(): ChildProcessWithoutNullStreams {
    const cmd = this.command()
    if (!cmd) throw new Error(t('main.tools.needsDiffusers'))
    const proc = spawn(cmd.command, cmd.args, { env: { ...processEnv(), ...cmd.env, ...this.env() } })
    const waiting = new Map<number, (a: Answer) => void>()
    this.proc = proc
    this.waiting = waiting
    proc.stdout.on('data', lineSplitter((line) => {
      if (!line.startsWith('{')) return
      try {
        const a = JSON.parse(line) as Answer & { id?: number }
        const resolve = a.id !== undefined ? waiting.get(a.id) : undefined
        if (resolve && a.id !== undefined) {
          waiting.delete(a.id)
          resolve(a)
        }
      } catch {
        // not an answer
      }
    }))
    proc.stderr.on('data', (data: Buffer) => this.log(data.toString('utf8')))
    proc.on('error', (err) => this.log(err.message))
    proc.stdin.on('error', (err) => this.log(err.message))
    proc.on('close', () => {
      if (this.proc === proc) this.proc = undefined
      for (const resolve of waiting.values()) resolve({ error: t('main.tools.selectionStopped') })
      waiting.clear()
    })
    return proc
  }

  /** points: [x, y, 1 = belongs to it | 0 = does not] in picture pixels; pick: which of SAM's candidates by size
   *  (0 = the largest), left out: the one SAM rates best. */
  select(tool: string, image: string, points: [number, number, number][], pick?: number): Promise<Selected> {
    return new Promise((resolve, reject) => {
      try {
        const proc = this.proc ?? this.start()
        const id = this.nextId++
        this.waiting.set(id, (a) => (a.error || !a.mask ? reject(new Error(a.error ?? t('main.tools.noSelection'))) : resolve({ mask: a.mask, score: a.score ?? 0, pick: a.pick ?? 0, candidates: a.candidates ?? 1 })))
        proc.stdin.write(JSON.stringify({ id, tool, image, points, pick }) + '\n')
      } catch (err) {
        reject(err as Error)
      }
    })
  }

  stop(): void {
    this.proc?.kill()
    this.proc = undefined
  }
}
