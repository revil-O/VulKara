// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The engine processes. Each one is a Python program of engines/ that takes JSON requests on stdin and reports
// events on stdout (engines/diffusers/protocol.py):
//   diffusers  PyTorch on the GPU (SD 1.x to 3.5, SDXL, FLUX)
//   mlx        MLX (FLUX, Z-Image, Krea 2, Ideogram 4)
//   comfyui    ComfyUI (model types the others do not run)
// Only one engine keeps a model in the unified memory at a time.

import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { ContentGuard } from './content_guard'
import { engineCommand, runtimePython, type RuntimeId } from './runtimes'
import { engineEnv, getSettings, onSettingChanged } from './settings'
import { log, logOutput } from './log'
import type { EngineEvent } from '@shared/types'
import { DIFFUSERS_NOTE, mlxOrDiffusers } from './mlx_fallback'
import { processEnv } from './env'
import { lineSplitter } from './tool_process'
import { getToken } from './secrets'
import { t } from './i18n'

const EVENT_PREFIX = '@vk '

// only the MLX runtime loads these checkpoints
const MLX_ONLY = ['krea2', 'ideogram4', 'flux3_klein', 'ernie_image', 'fibo2_mlx']
// what MLX runs as well as Diffusers (models in repository layout, text to image)
const MLX_ALSO = ['flux1_schnell', 'flux1_dev', 'flux2_klein', 'z_image']

export type EngineRequest =
  | { op: 'generate' | 'preview'; job: Record<string, unknown> }
  | { op: 'stop' | 'unload' | 'ping' }

type Listener = (event: EngineEvent | { event: 'exit'; message: string }) => void

// models the MLX engine refused for this Mac's memory: they go to Diffusers, which can stream them from the SSD
const tooLargeForMlx = new Set<string>()
// where a job that MLX refused went on to, so that Stop reaches it
let redirected: RuntimeId | undefined
// Stop was pressed for the job being dispatched: a job MLX refuses then ends instead of going on with Diffusers
let stopRequested = false

/** Forgets which models MLX refused (memory or runtime settings changed, a runtime was installed or removed). */
export function forgetMlxRefusals(): void {
  tooLargeForMlx.clear()
}

class EngineProcess {
  private proc?: ChildProcessWithoutNullStreams
  private lastError = ''
  listener: Listener = () => {}

  constructor(readonly id: RuntimeId) {}

  get running(): boolean {
    return this.proc !== undefined
  }

  /** The Diffusers engine completes gated base parts (FLUX.1 [dev] for single files) with the stored token. */
  private tokenEnv(): Record<string, string> {
    const hf = this.id === 'diffusers' ? getToken('huggingface') : undefined
    return hf ? { HF_TOKEN: hf } : {}
  }

  private start(): ChildProcessWithoutNullStreams {
    const cmd = engineCommand(this.id)
    if (!cmd) {
      throw new Error(this.id === 'comfyui' ? t('main.engines.needsComfy') : t('main.engines.notInstalled', { id: this.id }))
    }
    log(`[${this.id}] starting`)
    const proc = spawn(cmd.command, cmd.args, { env: { ...processEnv(), ...engineEnv(), ...this.tokenEnv(), ...cmd.env } })
    this.proc = proc
    this.lastError = ''
    // events are line based; a chunk can end in the middle of a line
    const onStdout = lineSplitter((line) => this.onLine(line))
    // a stopped process may still print: its events must not reach the job of the next one
    proc.stdout.on('data', (data: Buffer) => { if (this.proc === proc) onStdout(data) })
    proc.stderr.on('data', (data: Buffer) => {
      const text = data.toString('utf8').trimEnd()
      this.lastError = (this.lastError + '\n' + text).slice(-400)
      logOutput(this.id, text)
    })
    proc.on('error', (err) => { this.lastError = err.message })
    // a request written while the process ends fails with EPIPE; its exit is reported by "close"
    proc.stdin.on('error', (err) => log(`[${this.id}] ${err.message}`))
    proc.on('close', (code) => {
      if (this.proc !== proc) return
      this.proc = undefined
      const why = this.lastError.trim().split('\n').pop() || 'exit ' + code
      log(`[${this.id}] The ${this.id} engine stopped: ${why}`)
      this.listener({ event: 'exit', message: t('main.engines.stopped', { id: this.id, reason: why }) })
    })
    return proc
  }

  private onLine(line: string): void {
    if (!line) return
    if (!line.startsWith(EVENT_PREFIX)) {
      logOutput(this.id, line)
      return
    }
    try {
      this.listener(JSON.parse(line.slice(EVENT_PREFIX.length)) as EngineEvent)
    } catch {
      log(`[${this.id}] unreadable event: ${line}`)
    }
  }

  send(request: EngineRequest): void {
    const proc = this.proc ?? this.start()
    proc.stdin.write(JSON.stringify(request) + '\n')
  }

  /** Ends the process; a new one starts with the next request. */
  stop(): void {
    const proc = this.proc
    if (!proc) return
    this.proc = undefined
    proc.kill()
  }
}

const engines: Record<RuntimeId, EngineProcess> = {
  diffusers: new EngineProcess('diffusers'),
  mlx: new EngineProcess('mlx'),
  comfyui: new EngineProcess('comfyui'),
}
let current: RuntimeId | undefined
// the engines read their settings when they start; a change applies with the next job, not in the middle of one
let restartPending = false

/** The content filter of the results; it runs in the Diffusers runtime with the folders of the engines. */
export const guard = new ContentGuard(() => {
  const cmd = engineCommand('diffusers', ['content_check'])
  return cmd && { ...cmd, env: { ...engineEnv(), ...cmd.env } }
}, (chunk) => logOutput('content filter', chunk))

export interface Manifest {
  arch?: string
  runtime?: string
  layout?: string
  kind?: string
  label?: string
  name?: string
}

export function readManifest(modelDir: string): Manifest | undefined {
  const file = join(modelDir, 'model.json')
  if (!existsSync(file)) return undefined
  try {
    return JSON.parse(readFileSync(file, 'utf8')) as Manifest
  } catch {
    return {}  // broken manifest: the engine reports it
  }
}

/** Which engine runs a job (as the engines take it) on this model. */
export function engineFor(job: Record<string, unknown>): RuntimeId {
  if (job.upscale) return 'comfyui'  // enlarging needs no model of the user
  if (job.restore) return 'diffusers'  // correcting needs no model; the AI steps edit with FLUX.2 there
  if (job.photo_tool) return 'diffusers'  // ONNX on the CPU with the Diffusers runtime's onnxruntime
  const m = readManifest(String(job.model_dir ?? ''))
  if (!m) throw new Error(t('main.engines.modelGone'))
  if (m.runtime === 'comfyui') return 'comfyui'
  if (m.arch && MLX_ONLY.includes(m.arch)) return 'mlx'
  const preferred = getSettings().runtime
  const mlxCan = !!m.arch && MLX_ALSO.includes(m.arch) && m.layout === 'repo' && !job.input_image && !job.controlnet_image
  const roomy = !tooLargeForMlx.has(String(job.model_dir ?? ''))
  if (mlxCan && roomy && (preferred === 'mlx' || (preferred === 'auto' && runtimePython('mlx')))) return 'mlx'
  return 'diffusers'
}


/** Sends a job to its engine; the engine that held a model before frees the memory first. */
export function dispatch(op: 'generate' | 'preview', job: Record<string, unknown>, listener: Listener): RuntimeId {
  const id = engineFor(job)
  redirected = undefined
  stopRequested = false
  if (restartPending) stopEngines()
  if (current && current !== id && engines[current].running) engines[current].send({ op: 'unload' })
  current = id
  const shared = id === 'mlx' && MLX_ALSO.includes(String(readManifest(String(job.model_dir ?? ''))?.arch ?? ''))
  const dir = String(job.model_dir ?? '')
  engines[id].listener = !shared ? listener : mlxOrDiffusers(listener, () => !!runtimePython('diffusers'), () => {
    // MLX is done with this job: what it may still print or an exit of it must not reach the job any more
    engines.mlx.listener = () => {}
    if (stopRequested) {
      listener({ event: 'state', state: 'idle' })  // cancelled while MLX was refusing: the job ends
      return
    }
    tooLargeForMlx.add(dir)
    log('[mlx] too little memory for this model on this Mac: the job goes on with Diffusers (SSD streaming)')
    try {
      dispatch(op, job, listener)
      redirected = 'diffusers'
    } catch (err) {
      // the job must end, not hang, and the main process must not fail on it
      listener({ event: 'error', message: (err as Error).message })
      listener({ event: 'state', state: 'idle' })
    }
  })
  // the note only where MLX would have run the model otherwise
  const mlxWanted = getSettings().runtime !== 'diffusers' && !!runtimePython('mlx')
  if (id === 'diffusers' && op === 'generate' && mlxWanted && tooLargeForMlx.has(dir)) listener({ event: 'note', message: DIFFUSERS_NOTE })
  engines[id].send({ op, job })
  return id
}

export function stopJob(id: RuntimeId): void {
  stopRequested = true
  const target = redirected ?? id
  if (engines[target].running) engines[target].send({ op: 'stop' })
}

/** Frees the unified memory for something else (training): the engines drop their models. */
export function unloadEngines(): void {
  for (const e of Object.values(engines)) if (e.running) e.send({ op: 'unload' })
}

export function stopEngines(): void {
  restartPending = false
  for (const e of Object.values(engines)) e.stop()
  guard.stop()
}

export const anyEngineInstalled = (): boolean =>
  (['diffusers', 'mlx', 'comfyui'] as RuntimeId[]).some((id) => !!engineCommand(id))

onSettingChanged((key) => {
  if (['modelsDir', 'imagesDir', 'lorasDir', 'helpersDir', 'runtimesDir', 'memoryReserveGb', 'ssdStreaming', 'comfyStreaming', 'streamCacheDir', 'runtime', 'stepCache'].includes(key)) restartPending = true
  if (['runtimesDir', 'memoryReserveGb', 'ssdStreaming', 'runtime'].includes(key)) forgetMlxRefusals()
})
