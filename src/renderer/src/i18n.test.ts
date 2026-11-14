// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { engineNote, locale } from './i18n'

describe('a job note', () => {
  it('is shown in the app language, line by line; lines the app does not know stay as they are', () => {
    locale.value = 'de'
    const note = engineNote('Faces refined: 3\nsomething new')
    expect(note.split('\n')).toEqual([expect.not.stringContaining('Faces refined'), 'something new'])
    expect(note).toContain('3')
    locale.value = 'en'
    expect(engineNote('Faces refined: 3')).toBe('Faces refined: 3')
  })
})
