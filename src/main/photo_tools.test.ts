// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { installedTools, recommendedTools } from './photo_tools'

describe('photo tools', () => {
  it('lists the catalog with what is installed, and only folders that are photo tools', () => {
    const tools = mkdtempSync(join(tmpdir(), 'vk-tools-'))
    mkdirSync(join(tools, 'sam21-tiny'))
    writeFileSync(join(tools, 'sam21-tiny', 'tool.json'), JSON.stringify({
      type: 'photo_tool', name: 'Select objects (SAM 2.1)', task: 'select', kind: 'segment', recommended: 'sam21-tiny', licence: 'Apache-2.0',
    }))
    mkdirSync(join(tools, 'mine'))
    writeFileSync(join(tools, 'mine', 'tool.json'), JSON.stringify({ type: 'photo_tool', name: 'Mine', kind: 'image', scale: 2, task: 'custom' }))
    mkdirSync(join(tools, 'not-a-tool'))
    writeFileSync(join(tools, 'not-a-tool', 'tool.json'), JSON.stringify({ type: 'lora' }))
    const installed = installedTools(tools)
    expect(installed.map((t) => t.name)).toEqual(['Mine', 'Select objects (SAM 2.1)'])
    expect(installed[0]).toMatchObject({ kind: 'image', scale: 2, runtime: 'onnx' })
    const recommended = recommendedTools(resolve('engines'), tools)
    expect(recommended.length).toBeGreaterThanOrEqual(6)
    expect(recommended.find((t) => t.id === 'sam21-tiny')).toMatchObject({ installed: true, runtime: 'onnx' })
    expect(recommended.find((t) => t.id === 'nafnet-deblur')).toMatchObject({ installed: false, licence: 'MIT', kind: 'image', runtime: 'onnx' })
    expect(recommended.find((t) => t.id === 'scunet-real')).toMatchObject({ task: 'denoise', runtime: 'torch' })
    expect(recommended.find((t) => t.id === 'fbcnn-color')).toMatchObject({ task: 'dejpeg', runtime: 'torch', quality: true })
    const scunet = recommended.find((t) => t.id === 'scunet-real')
    expect(scunet).toMatchObject({ defaultLabel: 'Natural', quality: false })
    expect(scunet?.variants).toEqual([expect.objectContaining({ id: 'sharp', label: 'Sharp', sizeMb: 72 })])
    expect(recommended.find((t) => t.id === 'swinir-real-x4')?.variants).toEqual([expect.objectContaining({ id: 'natural', label: 'Natural (slow)', sizeMb: 140 })])
    expect(installedTools(join(tools, 'missing'))).toEqual([])
  })
})
