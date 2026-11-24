// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Training a LoRA on the user's pictures: SDXL with the Diffusers runtime, FLUX.2 [klein] and Krea 2 with MLX.
// One training at a time; it runs in the main process' care, so its state survives page changes.

import { spawn, type ChildProcess } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { basename, isAbsolute, join } from 'node:path'
import { safeName } from './loras'
import type { Command } from './runtimes'
import type { TrainingImage, TrainingRequest, TrainingState } from '@shared/api'
import { processEnv } from './env'
import { lineSplitter } from './tool_process'
import { prohibitedPrompt } from '@shared/content_policy'
import { engineLine, mainLanguage, t } from './i18n'

export interface TrainerDeps {
  /** how to start the trainer of a model architecture with a job file; undefined when its runtime is missing */
  command(arch: string, jobFile: string): Command | undefined
  env(): Record<string, string>
  workDir(): string
  lorasDir(): string
  /** before the training starts: the engines give their memory back */
  prepare(): void
  changed(state: TrainingState): void
  /** a LoRA was written */
  installed(): void
  log(chunk: string): void
  /** the content filter for one training picture (safe mode as set); the picture itself is never changed or removed */
  check?(path: string): Promise<{ ok: boolean; reason?: string }>
  /** all pictures are checked: the filter can give its memory back before the training loads the model */
  checked?(): void
}

const IMAGE = /\.(png|jpe?g|webp|bmp)$/i
const MLX_ARCHS = ['flux2_klein', 'krea2', 'z_image', 'ernie_image']

/** The architectures a LoRA can be trained for. */
export const TRAINABLE = ['sdxl', ...MLX_ARCHS]

/** The pictures of a folder, each with the caption of a .txt file of the same name. */
export function folderImages(dir: string): TrainingImage[] {
  return readdirSync(dir).filter((f) => IMAGE.test(f) && !f.startsWith('.')).sort().slice(0, 500).map((f) => {
    const path = join(dir, f)
    const text = path.replace(/\.[^.]+$/, '.txt')
    let caption = ''
    try {
      if (existsSync(text)) caption = readFileSync(text, 'utf8').trim().slice(0, 500)
    } catch {
      // unreadable: no caption
    }
    return { path, caption }
  })
}

/** The request as the trainers take it; throws with what is missing. */
export function trainingJob(req: TrainingRequest, workDir: string, lorasDir: string): { arch: string; name: string; job: Record<string, unknown>; folder: string } {
  const baseModel = String(req.baseModel ?? '')
  const manifestFile = join(baseModel, 'model.json')
  if (!isAbsolute(baseModel) || !existsSync(manifestFile)) throw new Error(t('main.training.chooseModel'))
  const arch = String((JSON.parse(readFileSync(manifestFile, 'utf8')) as { arch?: string }).arch ?? '')
  if (!TRAINABLE.includes(arch)) throw new Error(t('main.training.notTrainable'))
  const images = (Array.isArray(req.images) ? req.images : [])
    .filter((i) => i && IMAGE.test(String(i.path)) && existsSync(i.path))
    .map((i) => ({ path: i.path, caption: String(i.caption ?? '').slice(0, 500) }))
  if (!images.length) throw new Error(t('main.training.addPictures'))
  const name = safeName(req.name)
  if (!name) throw new Error(t('main.training.giveName'))
  const folder = join(workDir, name)
  const job = {
    name, trigger: String(req.trigger ?? '').trim().slice(0, 60), base_model: baseModel, images,
    resolution: Math.min(1024, Math.max(256, Number(req.resolution) || 512)),
    steps: Math.min(5000, Math.max(1, Math.round(Number(req.steps) || 500))),
    rank: [4, 8, 16, 32, 64].includes(Number(req.rank)) ? Number(req.rank) : 16,
    learning_rate: Math.min(1e-2, Math.max(1e-6, Number(req.learningRate) || 1e-4)),
    work_dir: folder, loras_dir: lorasDir,
  }
  return { arch, name, job, folder }
}

export class Trainer {
  private proc?: ChildProcess
  private current: TrainingState = { running: false, losses: [] }
  /** Stop was pressed while the pictures were being checked */
  private stopChecking = false

  constructor(private readonly deps: TrainerDeps) {}

  state(): TrainingState {
    return { ...this.current, losses: [...this.current.losses] }
  }

  get running(): boolean {
    return this.current.running
  }

  private set(patch: Partial<TrainingState>): void {
    this.current = { ...this.current, ...patch }
    this.deps.changed(this.state())
  }

  async start(req: TrainingRequest): Promise<void> {
    if (this.current.running) throw new Error(t('main.training.running'))
    const { arch, name, job, folder } = trainingJob(req, this.deps.workDir(), this.deps.lorasDir())
    // the captions and the trigger word teach the LoRA what it makes: checked like a prompt
    const images = job.images as { path: string; caption: string }[]
    const refused = prohibitedPrompt([String(job.trigger), ...images.map((i) => i.caption)].join('\n'), mainLanguage().lang)
    if (refused) throw new Error(refused)
    const jobFile = join(folder, 'job.json')
    const cmd = this.deps.command(arch, jobFile)
    if (!cmd) {
      throw new Error(arch === 'sdxl' ? t('main.training.needsDiffusers') : t('main.training.needsMlx'))
    }
    if (this.deps.check) {
      const check = this.deps.check
      this.stopChecking = false
      this.current = { running: true, name, phase: 'checking', message: t('main.training.checking'), losses: [] }
      this.deps.changed(this.state())
      const refusedPictures: string[] = []
      try {
        for (const [i, img] of images.entries()) {
          if (this.stopChecking) break
          this.set({ message: t('main.training.checkingOf', { i: i + 1, n: images.length }) })
          const verdict = await check(img.path)
          if (!verdict.ok) refusedPictures.push(`${basename(img.path)}: ${verdict.reason ?? t('main.training.notPassed')}`)
        }
      } finally {
        this.deps.checked?.()
      }
      if (this.stopChecking) {
        this.set({ running: false, phase: undefined, message: undefined, stopped: true })
        return
      }
      if (refusedPictures.length) {
        this.set({
          running: false, phase: undefined, message: undefined,
          error: t('main.training.refused', {
            count: refusedPictures.length, list: refusedPictures.slice(0, 5).join(' · ') + (refusedPictures.length > 5 ? ' …' : ''),
          }),
        })
        return
      }
    }
    mkdirSync(folder, { recursive: true })
    writeFileSync(jobFile, JSON.stringify(job, null, 1))
    this.deps.prepare()
    this.current = { running: true, name, phase: 'loading', losses: [] }
    this.deps.changed(this.state())
    const proc = spawn(cmd.command, cmd.args, { env: { ...processEnv(), ...cmd.env, ...this.deps.env() } })
    this.proc = proc
    let stderr = ''
    let result = ''
    let error = ''
    proc.stdout?.on('data', lineSplitter((line) => {
      if (!line.startsWith('__train__ ')) {
        this.deps.log(line)
        return
      }
      let msg: Record<string, unknown>
      try {
        msg = JSON.parse(line.slice(10))
      } catch {
        return
      }
      if (typeof msg.done === 'string') {
        result = msg.done
      } else if (msg.error) {
        error = String(msg.error)
      } else {
        const loss = typeof msg.loss === 'number' ? msg.loss : undefined
        this.set({
          phase: typeof msg.phase === 'string' ? msg.phase : this.current.phase,
          message: typeof msg.message === 'string' ? engineLine(msg.message) : undefined,
          step: typeof msg.step === 'number' ? msg.step : this.current.step,
          total: typeof msg.total === 'number' ? msg.total : this.current.total,
          loss: loss ?? this.current.loss,
          eta: typeof msg.eta_s === 'number' ? msg.eta_s : undefined,
          losses: loss !== undefined ? [...this.current.losses, loss].slice(-2000) : this.current.losses,
        })
      }
    }))
    proc.stderr?.on('data', (data: Buffer) => {
      const text = data.toString()
      stderr = (stderr + text).slice(-2000)
      this.deps.log(text)
    })
    const finish = (patch: Partial<TrainingState>): void => {
      if (this.proc !== proc) return
      this.proc = undefined
      this.set({ running: false, eta: undefined, ...patch })
    }
    proc.on('error', (err) => finish({ error: err.message }))
    proc.on('close', (_code, signal) => {
      if (result) {
        let trigger = ''
        try {
          trigger = String((JSON.parse(readFileSync(join(result, 'lora.json'), 'utf8')) as { trigger_words?: string[] }).trigger_words?.[0] ?? '')
        } catch {
          // the manifest tells it later
        }
        this.deps.installed()
        finish({ result: { folder: result, name: result.split('/').pop() ?? name, trigger } })
      } else if (signal) {
        finish({ stopped: true })
      } else {
        finish({ error: error || t('main.training.failed', { reason: stderr.split('\n').filter((l) => l.trim()).pop() ?? t('main.training.noReason') }) })
      }
    })
  }

  stop(): void {
    this.stopChecking = true
    this.proc?.kill()
  }
}
