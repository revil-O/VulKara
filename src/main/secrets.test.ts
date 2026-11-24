// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { mkdtempSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

const dir = mkdtempSync(join(tmpdir(), 'vk-secrets-'))
vi.mock('electron', () => ({
  app: { getPath: () => dir },
  safeStorage: {
    isEncryptionAvailable: () => true,
    encryptString: (s: string) => Buffer.from(s.split('').reverse().join('')),
    decryptString: (b: Buffer) => b.toString().split('').reverse().join(''),
  },
}))

const { checkToken, cleanToken, getToken, hasToken, setToken } = await import('./secrets')

describe('access tokens', () => {
  it('keeps a token per service, in a file only the user can read', () => {
    expect(setToken('civitai', ' abc ')).toBe('stored')
    expect(getToken('civitai')).toBe('abc')
    expect(statSync(join(dir, 'tokens.json')).mode & 0o077).toBe(0)
    expect(setToken('civitai', '')).toBe('removed')
    expect(hasToken('civitai')).toBe(false)
  })

  it('knows no other services', () => {
    expect(() => setToken('github' as 'civitai', 'x')).toThrow()
    for (const service of ['__proto__', 'constructor', 'toString'])
      expect(hasToken(service as 'civitai')).toBe(false)
  })

  it('takes only the Hugging Face token of what was pasted, and refuses what is none', () => {
    const hf = 'hf_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7'  // made up, the shape of one
    for (const pasted of [hf, ` ${hf}\n`, `Bearer ${hf}`, `HF_TOKEN=${hf}`, `export HF_TOKEN="${hf}"`, `'${hf}'`]) expect(cleanToken(pasted)).toBe(hf)
    expect(setToken('huggingface', `export HF_TOKEN=${hf}`)).toBe('stored')
    expect(getToken('huggingface')).toBe(hf)
    // 65-79 characters were stored once (more than the token) and Hugging Face refused them
    expect(() => setToken('huggingface', `${hf} ${hf}`)).toThrow()
    expect(() => setToken('huggingface', 'abc123')).toThrow()
    expect(getToken('huggingface')).toBe(hf)  // the stored one stays
    expect(setToken('civitai', 'Bearer 0123abcd')).toBe('stored')
    expect(getToken('civitai')).toBe('0123abcd')
  })

  it('asks Hugging Face whether it takes the stored token', async () => {
    const asked: string[] = []
    const answer = (status: number) => async (url: string, init: RequestInit) => {
      asked.push(`${url} ${(init.headers as Record<string, string>).Authorization}`)
      return new Response('{}', { status })
    }
    expect(await checkToken('huggingface', answer(200))).toBe('valid')
    expect(await checkToken('huggingface', answer(401))).toBe('refused')
    expect(await checkToken('huggingface', answer(503))).toBe('unknown')
    expect(await checkToken('huggingface', async () => { throw new Error('offline') })).toBe('unknown')
    expect(asked[0]).toBe('https://huggingface.co/api/whoami-v2 Bearer hf_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7')
    expect(await checkToken('civitai', answer(401))).toBe('refused')
    expect(asked.at(-1)).toBe('https://civitai.com/api/v1/me Bearer 0123abcd')
  })
})
