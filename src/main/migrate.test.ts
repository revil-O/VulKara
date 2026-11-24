// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

const { recheckLibrary, RECHECK_FLAG, RECHECK_TRIES } = await import('./migrate')

describe('the one-time check of the installed LoRAs and models', () => {
  // "--" before the --apply the check adds: node takes what follows as the script's arguments
  const node = (script: string) => ({ command: process.execPath, args: ['-e', script, '--'] })
  const noTrash = () => Promise.reject(new Error('nothing to trash'))

  it('runs once, with --apply, and has the pages reload the list when something changed', async () => {
    const data = mkdtempSync(join(tmpdir(), 'vk-recheck-'))
    const changed = vi.fn()
    const script = 'if (!process.argv.includes("--apply")) process.exit(3); console.log(JSON.stringify({ type: "lora", name: "x" }))'
    expect(await recheckLibrary(node(script), {}, data, changed, noTrash)).toBe(true)
    expect(existsSync(join(data, RECHECK_FLAG))).toBe(true)
    expect(changed).toHaveBeenCalledTimes(1)
    expect(await recheckLibrary(node('process.exit(1)'), {}, data, changed, noTrash)).toBe(false)  // done already
    expect(changed).toHaveBeenCalledTimes(1)
  })

  it('waits for a later start without the runtime or after a failed run', async () => {
    const data = mkdtempSync(join(tmpdir(), 'vk-recheck-'))
    expect(await recheckLibrary(undefined, {}, data, () => {}, noTrash)).toBe(false)
    expect(await recheckLibrary(node('process.exit(2)'), {}, data, () => {}, noTrash)).toBe(false)
    expect(existsSync(join(data, RECHECK_FLAG))).toBe(false)
  })

  it('moves a whole model filed as a LoRA to the trash, and nothing else', async () => {
    const data = mkdtempSync(join(tmpdir(), 'vk-recheck-'))
    const trash = vi.fn(() => Promise.resolve())
    const lines = [{ type: 'lora', folder: '/l/GhostMix-v2', error: 'Not a LoRA file', not_lora: true },
      { type: 'lora', folder: '/l/broken', error: 'unreadable' }, { type: 'model', folder: '/m/x', not_lora: true }]
    const script = lines.map((l) => `console.log(${JSON.stringify(JSON.stringify(l))})`).join(';')
    expect(await recheckLibrary(node(script), {}, data, () => {}, trash)).toBe(true)
    expect(trash.mock.calls).toEqual([['/l/GhostMix-v2']])
  })

  it('tries a failed move to the trash again at the next start', async () => {
    const data = mkdtempSync(join(tmpdir(), 'vk-recheck-'))
    const line = JSON.stringify(JSON.stringify({ type: 'lora', folder: '/l/GhostMix-v2', not_lora: true }))
    expect(await recheckLibrary(node(`console.log(${line})`), {}, data, () => {}, noTrash)).toBe(true)
    expect(existsSync(join(data, RECHECK_FLAG))).toBe(false)  // not done: runs again
    const trash = vi.fn(() => Promise.resolve())
    expect(await recheckLibrary(node(`console.log(${line})`), {}, data, () => {}, trash)).toBe(true)
    expect(trash).toHaveBeenCalledTimes(1)
    expect(existsSync(join(data, RECHECK_FLAG))).toBe(true)
  })

  it('gives a move that keeps failing up after a few starts', async () => {
    const data = mkdtempSync(join(tmpdir(), 'vk-recheck-'))
    const line = JSON.stringify(JSON.stringify({ type: 'lora', folder: '/readonly/x', not_lora: true }))
    for (let i = 1; i <= RECHECK_TRIES; i++) {
      expect(existsSync(join(data, RECHECK_FLAG))).toBe(false)
      await recheckLibrary(node(`console.log(${line})`), {}, data, () => {}, noTrash)
    }
    expect(existsSync(join(data, RECHECK_FLAG))).toBe(true)  // the third failed start ends it
    expect(existsSync(join(data, `${RECHECK_FLAG}.tries`))).toBe(false)
  })
})
