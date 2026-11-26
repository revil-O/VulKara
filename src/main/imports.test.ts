// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { ImportError, ImportQueue, processRunner, publicRef, reason, toInfo, type ImportRunner } from './imports'
import type { ImportRequest } from '@shared/api'

const REQ: ImportRequest = { source: 'hf', ref: 'org/model' }

function setup() {
  const runs: { req: ImportRequest; dryRun: boolean; resolve: (v: Record<string, unknown>) => void; reject: (e: Error) => void; progress: (s: string, p: number) => void }[] = []
  let installed = 0
  const runner: ImportRunner = (req, dryRun, onProgress) => {
    let resolve!: (v: Record<string, unknown>) => void
    let reject!: (e: Error) => void
    const done = new Promise<Record<string, unknown>>((res, rej) => { resolve = res; reject = rej })
    runs.push({ req, dryRun, resolve, reject, progress: onProgress })
    return { done, cancel: () => reject(new ImportError('Cancelled', 'cancelled')) }
  }
  const queue = new ImportQueue(runner, () => {}, () => { installed++ })
  const settle = (): Promise<void> => new Promise((r) => setTimeout(r, 0))
  return { queue, runs, settle, installed: () => installed }
}

describe('imports', () => {
  it('runs one import at a time and reports progress', async () => {
    const { queue, runs, settle, installed } = setup()
    queue.add(REQ, 'One')
    queue.add({ ...REQ, ref: 'org/two' }, 'Two')
    expect(runs).toHaveLength(1)
    runs[0].progress('Downloading', 40)
    expect(queue.list()[0]).toMatchObject({ state: 'running', stage: 'Downloading', percent: 40 })
    runs[0].resolve({})
    await settle()
    expect(queue.list().map((j) => j.state)).toEqual(['done', 'running'])
    expect(installed()).toBe(1)
    expect(runs[1].req.ref).toBe('org/two')
  })

  it('keeps the reason of a failure and goes on', async () => {
    const { queue, runs, settle } = setup()
    queue.add(REQ, 'One')
    queue.add(REQ, 'Two')
    runs[0].reject(new ImportError('This repository needs an access token', 'GatedRepoError'))
    await settle()
    expect(queue.list()[0]).toMatchObject({ state: 'failed', error: 'This repository needs an access token' })
    expect(queue.list()[1].state).toBe('running')
  })

  it('cancels the running import and removes waiting ones', async () => {
    const { queue, runs, settle } = setup()
    const a = queue.add(REQ, 'One')
    const b = queue.add(REQ, 'Two')
    queue.cancel(b)
    expect(queue.list()).toHaveLength(1)
    queue.cancel(a)
    await settle()
    expect(queue.list()[0]).toMatchObject({ state: 'cancelled', error: undefined })
    expect(runs).toHaveLength(1)
    queue.clearFinished(() => false)  // the remote web UI clears only its own (from the web)
    expect(queue.list()).toHaveLength(1)
    queue.clearFinished()
    expect(queue.list()).toHaveLength(0)
  })

  it('says in one sentence why an import failed', () => {
    expect(reason('RepositoryNotFoundError', '404 Client Error. (Request ID: Root=1-6a)\n\nRepository Not Found for url')).toMatch(/does not exist/)
    expect(reason('ValueError', 'Could not recognize the model architecture (Request ID: x)\nmore')).toBe('Could not recognize the model architecture')
    expect(reason('X', '')).toBe('The import failed.')
    expect(reason('TokenRejected', '401 Client Error.')).toMatch(/refused the stored access token/)
    expect(reason('NotEnoughSpace', 'Only 31 GB free on the models disk: models are installed with 50 GB free or more')).toMatch(/^Only 31 GB are free/)
  })

  it('translates the dry run of the importer', async () => {
    expect(toInfo({ arch: 'sdxl', label: 'SDXL', download_gb: 6.9, gated: false, plan: { fits: true, min_ram_gb: 12, quant: { unet: 'none' } } }))
      .toEqual({ kind: 'model', label: 'SDXL', downloadGb: 6.9, gated: false, fits: true, minRamGb: 12, streamed: false, quant: undefined, inPlace: false, note: undefined, triggerWords: undefined })
    expect(toInfo({ type: 'lora', label: 'Style (SDXL)', download_gb: 0.2, trigger_words: ['styl3'], plan: { quant: { transformer: 'q8' } } }))
      .toMatchObject({ kind: 'lora', triggerWords: ['styl3'], quant: 'q8' })
    expect(toInfo({ label: 'FLUX.1', plan: { fits: true, streamed: true, min_ram_gb: 14 } })).toMatchObject({ streamed: true, minRamGb: 14 })
    // Civitai: the versions of the model to choose another
    expect(toInfo({ type: 'lora', source: 'civitai', model_id: 7, version_id: 71, model_name: 'Grain', version_name: 'v2',
      versions: [{ id: 71, name: 'v2', base_model: 'SDXL 1.0', usable: true, reason: '' }, { id: 70, name: 'v1', usable: false, reason: 'only a .pt file' }, { name: 'no id' }] }).civitai)
      .toEqual({ modelId: 7, versionId: 71, modelName: 'Grain', versionName: 'v2', versions: [
        { id: 71, name: 'v2', baseModel: 'SDXL 1.0', usable: true, reason: undefined }, { id: 70, name: 'v1', baseModel: undefined, usable: false, reason: 'only a .pt file' }] })
    expect(toInfo({ type: 'lora', source: 'hf' }).civitai).toBeUndefined()
    const { queue, runs } = setup()
    const info = queue.inspect(REQ)
    expect(runs[0].dryRun).toBe(true)
    runs[0].resolve({ label: 'X', download_gb: 1 })
    expect(await info).toMatchObject({ label: 'X', downloadGb: 1 })
  })

  it('passes every value joined to its option, so a value can not pose as another option', async () => {
    let args: string[] = []
    const run = processRunner((a) => { args = a; return undefined }, () => ({}), () => {})
    const { done } = run({ source: 'hf', ref: '--root=/tmp', name: '-x', file: 'a.safetensors', quant: 'q8' }, true, () => {})
    await expect(done).rejects.toMatchObject({ code: 'no_runtime' })
    expect(args).toEqual(['import_model', '--source=hf', '--ref=--root=/tmp', '--quant=q8', '--file=a.safetensors', '--name=-x', '--dry-run'])
  })

  it('drops an API key from a copied download link and keeps the version', () => {
    expect(publicRef('https://civitai.com/api/download/models/123?token=SECRET&type=Model')).toBe('https://civitai.com/api/download/models/123')
    expect(publicRef('https://civitai.com/models/5/x?modelVersionId=9&token=SECRET')).toBe('https://civitai.com/models/5/x?modelVersionId=9')
    expect(publicRef('https://user:pw@huggingface.co/a/b')).toBe('https://huggingface.co/a/b')
    expect(publicRef(' black-forest-labs/FLUX.1-dev ')).toBe('black-forest-labs/FLUX.1-dev')
  })
})
