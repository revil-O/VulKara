// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { REMOTE_CHANNELS } from './remote_channels'

describe('what the remote web UI may call', () => {
  it('has generating and watching', () => {
    for (const c of ['queue:add', 'queue:snapshot', 'assets:list', 'history:list', 'files:writeImage']) expect(REMOTE_CHANNELS.has(c)).toBe(true)
  })

  it('has finding and installing models', () => {
    for (const c of ['loras:search', 'imports:inspect', 'imports:add', 'imports:list']) expect(REMOTE_CHANNELS.has(c)).toBe(true)
  })

  it('has nothing that changes the Mac, its settings or its secrets', () => {
    for (const c of ['settings:set', 'settings:chooseFolder', 'tokens:set', 'files:choose', 'files:chooseMany', 'files:saveAs', 'files:reveal',
      'assets:remove', 'assets:rename', 'assets:exportSingle', 'runtimes:install', 'training:start', 'app:openExternal', 'app:logs', 'app:clearPromptCache', 'dialog:ask']) {
      expect(REMOTE_CHANNELS.has(c)).toBe(false)
    }
  })
})
