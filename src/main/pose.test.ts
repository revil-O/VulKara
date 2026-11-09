// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import type { ChildProcess } from 'node:child_process'
import { captionImage } from './pose'

// a stand-in for "main.py caption_image": node prints the tool's tagged lines
const node = (script: string) => ({ command: process.execPath, args: ['-e', script], env: {} })

describe('prompt from a picture (main.py caption_image)', () => {
  it('hands on the stages and answers with the text', async () => {
    const stages: string[] = []
    const script = 'console.log("__progress__ " + JSON.stringify({ stage: "Describing the picture", progress: -1 })); console.log("__caption__ " + JSON.stringify({ text: "A red fox." }))'
    expect(await captionImage(node(script), {}, (stage) => stages.push(stage), () => {})).toEqual({ text: 'A red fox.' })
    expect(stages).toEqual(['Describing the picture'])
  })

  it('says what went wrong, and that the Diffusers runtime is needed', async () => {
    const script = 'console.log("__error__ " + JSON.stringify({ error: "no picture" })); process.exit(1)'
    await expect(captionImage(node(script), {}, () => {}, () => {})).rejects.toThrow('no picture')
    await expect(captionImage(undefined, {}, () => {}, () => {})).rejects.toThrow(/Diffusers/)
  })

  it('hands out the process, so Stop can end it', async () => {
    let proc: ChildProcess | undefined
    const running = captionImage(node('setTimeout(() => {}, 60000)'), {}, () => {}, (p) => { proc = p })
    proc?.kill()
    await expect(running).rejects.toThrow()
  })
})
