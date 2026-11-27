// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

const dir = mkdtempSync(join(tmpdir(), 'vk-settings-'))
vi.mock('electron', () => ({ app: { getPath: () => dir, isPackaged: false, getAppPath: () => dir } }))

const { engineEnv, getSettings, isValidSetting, scanExportDir, setSetting, settableByPage } = await import('./settings')

describe('settings', () => {
  it('puts cut-out scans into ~/VulKara/scans unless a folder is chosen', () => {
    expect(scanExportDir()).toMatch(/VulKara\/scans$/)
    expect(isValidSetting('scanExportDir', '/Volumes/Photos/Scans')).toBe(true)
    expect(isValidSetting('scanExportDir', 'scans')).toBe(false)
  })

  it('takes only the settings there are, with values they can have', () => {
    expect(isValidSetting('theme', 'dark')).toBe(true)
    expect(isValidSetting('modelsDir', '/Volumes/Models')).toBe(true)
    expect(isValidSetting('modelsDir', 'models')).toBe(false)
    expect(isValidSetting('memoryReserveGb', Number.NaN)).toBe(false)
    for (const key of ['constructor', 'toString', 'valueOf', '__proto__', 'hasOwnProperty'])
      expect(isValidSetting(key, {})).toBe(false)
  })

  it('stores nothing that is not a setting', () => {
    expect(() => setSetting('constructor' as 'theme', 'x' as 'dark')).toThrow(/Invalid value/)
    setSetting('theme', 'light')
    expect(getSettings().theme).toBe('light')
    expect(Object.hasOwn(getSettings(), 'constructor')).toBe(false)
  })

  it('lets a page reset a folder but not point it somewhere', () => {
    expect(settableByPage('runtimesDir', '/tmp/evil')).toBe(false)
    expect(settableByPage('helpersDir', '/Volumes/x')).toBe(false)
    expect(settableByPage('runtimesDir', '')).toBe(true)
    expect(settableByPage('theme', 'dark')).toBe(true)
  })

  it('lets a page clear the remote token but never choose one', () => {
    expect(settableByPage('remoteToken', '')).toBe(true)
    expect(settableByPage('remoteToken', 'mine')).toBe(false)
    expect(isValidSetting('remotePort', 80)).toBe(false)  // below 1024: a port that needs root
    expect(isValidSetting('remotePort', 8787)).toBe(true)
  })

  it('sends mflux\'s own downloads to the helpers folder', () => {
    setSetting('helpersDir', join(dir, 'helpers'))
    expect(engineEnv().MFLUX_CACHE_DIR).toBe(join(dir, 'helpers', 'mflux'))
  })
})
