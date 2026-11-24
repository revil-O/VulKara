// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { MAX_BATCH, mergeBatch, sendEach } from './batch'

describe('the pictures of a batch', () => {
  it('keep their order and take no picture twice', () => {
    expect(mergeBatch(['/a.png', '/b.png'], ['/b.png', '/c.png'])).toEqual({ paths: ['/a.png', '/b.png', '/c.png'], capped: 0 })
  })
  it('are at most a hundred, and say how many there were', () => {
    const many = Array.from({ length: 130 }, (_, i) => `/p${i}.png`)
    const got = mergeBatch([], many)
    expect(MAX_BATCH).toBe(100)
    expect(got.paths).toHaveLength(100)
    expect(got.paths[99]).toBe('/p99.png')
    expect(got.capped).toBe(130)
  })
})

describe('sending a batch', () => {
  it('goes on after a picture that fails and reports it', async () => {
    const sent: string[] = []
    const errors = await sendEach(['/a.png', '/bad.png', '/c.png'], async (p) => {
      if (p === '/bad.png') throw new Error('bad.png can not be read')
      return [`job-${p}`]
    }, (ids) => sent.push(...ids))
    expect(sent).toEqual(['job-/a.png', 'job-/c.png'])
    expect(errors).toEqual(['bad.png can not be read'])
  })
})
