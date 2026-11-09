// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { chmodSync, existsSync, mkdirSync, mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

const dir = mkdtempSync(`${tmpdir()}/vk-runtimes-`)
vi.mock('electron', () => ({ app: { getPath: () => dir, isPackaged: false, getAppPath: () => resolve('.') }, net: {} }))

const { checkDownload, packageInstallError, updateTargets, staleRuntimes, runtimeDir, venvPython } = await import('./runtimes')

describe('the runtimes in the update check', () => {
  it('every runtime declares what identifies its version, with the range from its requirements', () => {
    const targets = updateTargets()
    expect(targets.length).toBeGreaterThan(0)
    for (const rt of targets) {
      expect(rt.installed).toBe(false)  // an empty app data folder
      expect(rt.targets.length, rt.id).toBeGreaterThan(0)
    }
    const byId = Object.fromEntries(targets.map((t) => [t.id, t.targets]))
    // locked: an update offers nothing beyond the accepted version (tools/lock_runtimes.py)
    expect(byId.diffusers[0]).toMatchObject({ key: 'pypi:diffusers', spec: expect.stringMatching(/^==/) })
    expect(byId.mlx[0]).toMatchObject({ key: 'pypi:mflux', spec: expect.stringMatching(/^==/) })
    if (byId.comfyui) expect(byId.comfyui[0]).toMatchObject({ kind: 'github', name: 'ComfyUI', pinned: expect.stringMatching(/^\d+\.\d+/) })
  })
})

describe('pinned downloads', () => {
  it('keeps a file with the expected checksum and removes one with another', () => {
    const file = `${dir}/uv.tar.gz`
    writeFileSync(file, 'hi')
    checkDownload(file, '8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4', 'uv')
    expect(existsSync(file)).toBe(true)
    expect(() => checkDownload(file, '0'.repeat(64), 'uv 0.13.7')).toThrow(/uv 0.13.7 does not match its checksum/)
    expect(existsSync(file)).toBe(false)
  })
})

describe('the Python of a runtime', () => {
  it('reads the patch version the venv runs, none without a venv', () => {
    // an earlier version's venv on 3.11.17 is made again on 3.11.18 (eMudhra certificates rejected in ssl)
    const venv = `${dir}/venv-old`
    mkdirSync(`${venv}/bin`, { recursive: true })
    writeFileSync(`${venv}/bin/python`, '#!/bin/sh\necho 3.11.17\n')
    chmodSync(`${venv}/bin/python`, 0o755)
    expect(venvPython(venv)).toBe('3.11.17')
    expect(venvPython(`${dir}/no-venv`)).toBeUndefined()
  })
})

describe('packages are never compiled', () => {
  it('names a package without a ready-built wheel in words, and leaves other failures as they are', () => {
    // uv's own words for a package that exists only as source (--only-binary :all:)
    const uv = 'Because antlr4-python3-runtime==4.9.3 has no usable wheels and you require antlr4-python3-runtime==4.9.3, we can conclude that your requirements are unsatisfiable.'
    expect(packageInstallError(uv)).toMatch(/^antlr4-python3-runtime is not available ready-built for this Mac/)
    expect(packageInstallError('error: Failed to fetch: https://pypi.org/simple/torch/')).toBe('error: Failed to fetch: https://pypi.org/simple/torch/')
  })
})

describe('runtimes from an earlier version', () => {
  it('are brought to the tested set when their lock is missing or another, and left alone when it matches', async () => {
    const { mkdirSync, readFileSync } = await import('node:fs')
    const { createHash } = await import('node:crypto')
    const { join } = await import('node:path')
    const rt = runtimeDir('mlx')
    mkdirSync(join(rt, 'venv', 'bin'), { recursive: true })
    writeFileSync(join(rt, 'venv', 'bin', 'python'), '')
    // installed before the lock existed (0.5.1 and earlier): no lock in runtime.json
    writeFileSync(join(rt, 'runtime.json'), JSON.stringify({ id: 'mlx', version: '0.20.0', installedAt: 1 }))
    expect(staleRuntimes()).toEqual(['mlx'])
    writeFileSync(join(rt, 'runtime.json'), JSON.stringify({ id: 'mlx', version: '0.20.0', installedAt: 1, lock: 'older' }))
    expect(staleRuntimes()).toEqual(['mlx'])
    const lockFor = (python: string) => createHash('sha256').update(readFileSync(resolve('engines/mlx/constraints.txt'))).update(`${python},`).digest('hex')
    // the same packages on the Python of an earlier version: made again on 3.11.18
    writeFileSync(join(rt, 'runtime.json'), JSON.stringify({ id: 'mlx', version: '0.20.0', installedAt: 1, lock: lockFor('3.11.17') }))
    expect(staleRuntimes()).toEqual(['mlx'])
    writeFileSync(join(rt, 'runtime.json'), JSON.stringify({ id: 'mlx', version: '0.20.0', installedAt: 1, lock: lockFor('3.11.18') }))
    expect(staleRuntimes()).toEqual([])
  })
})
