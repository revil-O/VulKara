// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// One-time steps at start after an update: the installed LoRAs and models checked again with the current detection.

import { spawn } from 'node:child_process'
import { existsSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { log } from './log'
import { processEnv } from './env'

/**
 * The flag of the one-time check of the installed LoRAs and models (LoRA detection of October 2026); -2: once more,
 * now that Chroma runs, for the Chroma checkpoints the first check marked as not runnable; -3: once more, now that
 * Z-Image runs, for the labels of Z-Image LoRAs that said no model can use them.
 */
export const RECHECK_FLAG = 'loras-rechecked-6'  // 4: sub-bases out of model.json "variant"; 5: FLUX.2 [klein] inpaints; 6: advice as negative prompt

/**
 * Once: the installed LoRAs and models are checked again with the current detection (engines/diffusers/recheck.py,
 * run with the Diffusers runtime): a LoRA filed under the wrong family or without its sub-base (FLUX.2 [klein]
 * 4B / 9B), a Chroma checkpoint filed as FLUX.1 (it becomes a Chroma model, its base takes FLUX.1's T5 and VAE over).
 * Each changed manifest is kept as .bak. Without the runtime it
 * waits for a later start, as it does for a models or LoRA folder on a drive that is not connected (exit 3); the flag
 * is written only after a run that ended well. Resolves true when it ran.
 */
export function recheckLibrary(command: { command: string; args: string[]; env?: Record<string, string> } | undefined,
  env: Record<string, string>, dataDir: string, changed: () => void): Promise<boolean> {
  const flag = join(dataDir, RECHECK_FLAG)
  if (existsSync(flag) || !command) return Promise.resolve(false)
  return new Promise((resolve) => {
    let out = ''
    const proc = spawn(command.command, [...command.args, '--apply'], { env: { ...processEnv(), ...command.env, ...env } })
    proc.stdout.on('data', (d: Buffer) => { out += d.toString() })
    proc.stderr.on('data', () => {})
    proc.on('error', (err) => {
      log(`checking the installed LoRAs failed: ${String(err)}`)
      resolve(false)
    })
    proc.on('close', (code) => {
      if (code !== 0) {
        log(`checking the installed LoRAs failed (exit ${code})`)
        resolve(false)
        return
      }
      const lines = out.split('\n').filter((l) => l.startsWith('{'))
      for (const line of lines) log(`installed LoRAs / models checked again: ${line}`)
      writeFileSync(flag, '')
      if (lines.length) changed()
      resolve(true)
    })
  })
}
