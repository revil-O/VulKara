// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { createHash } from 'node:crypto'
import { mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { AppUpdater, LATEST_URL, attachDmg, detachDmg, parseLatest, replaceableBundle, type Release } from './app_update'

const DMG = 'https://github.com/revil-O/VulKara/releases/download/v0.7.7/VulKara-0.7.7-arm64.dmg'
const latest = (over: Record<string, unknown> = {}, asset: Record<string, unknown> = {}): unknown => ({
  tag_name: 'v0.7.7', draft: false, prerelease: false,
  assets: [{ name: 'VulKara-0.7.7-arm64.dmg', digest: 'sha256:' + 'a'.repeat(64), size: 10, browser_download_url: DMG, ...asset }],
  ...over,
})

describe('parseLatest', () => {
  it('takes a newer release with its DMG and checksum', () => {
    expect(parseLatest(latest(), '0.7.6')).toEqual({
      version: '0.7.7', notesUrl: 'https://github.com/revil-O/VulKara/releases/tag/v0.7.7', dmgUrl: DMG, sha256: 'a'.repeat(64), size: 10,
    })
  })
  it('ignores the same or an older version, drafts, pre-releases and odd tags', () => {
    expect(parseLatest(latest(), '0.7.7')).toBeUndefined()
    expect(parseLatest(latest(), '0.10.0')).toBeUndefined()
    expect(parseLatest(latest({ draft: true }), '0.7.6')).toBeUndefined()
    expect(parseLatest(latest({ prerelease: true }), '0.7.6')).toBeUndefined()
    expect(parseLatest(latest({ tag_name: 'v0.7.7_hf_1' }), '0.7.6')).toBeUndefined()
    expect(parseLatest(null, '0.7.6')).toBeUndefined()
  })
  it('needs the DMG from the release itself with a SHA-256', () => {
    expect(parseLatest(latest({}, { digest: undefined }), '0.7.6')).toBeUndefined()
    expect(parseLatest(latest({}, { digest: 'md5:abc' }), '0.7.6')).toBeUndefined()
    expect(parseLatest(latest({}, { browser_download_url: 'https://example.com/VulKara-0.7.7-arm64.dmg' }), '0.7.6')).toBeUndefined()
    expect(parseLatest(latest({}, { name: 'VulKara-0.7.7-x64.dmg' }), '0.7.6')).toBeUndefined()
  })
})

describe('replaceableBundle', () => {
  it('replaces only an installed, writable app', () => {
    expect(replaceableBundle('/x/node_modules/electron/dist/Electron', false).reason).toBe('notPackaged')
    expect(replaceableBundle('/Volumes/VulKara/VulKara.app/Contents/MacOS/VulKara', true).reason).toBe('notInstalled')
    expect(replaceableBundle('/private/var/folders/x/AppTranslocation/y/d/VulKara.app/Contents/MacOS/VulKara', true).reason).toBe('notInstalled')
    expect(replaceableBundle('/nowhere/VulKara.app/Contents/MacOS/VulKara', true).reason).toBe('readOnly')
  })
})

describe('AppUpdater', () => {
  const body = Buffer.from('the dmg')
  const sha = createHash('sha256').update(body).digest('hex')
  function updater(reply: unknown, file = body): { u: AppUpdater; asked: string[] } {
    const asked: string[] = []
    const u = new AppUpdater({
      current: '0.7.6', exe: '/x', packaged: false, pid: 1, args: [], changed: () => undefined,
      fetcher: async (url) => (asked.push(url), url === LATEST_URL ? new Response(JSON.stringify(reply)) : new Response(file)),
    })
    return { u, asked }
  }

  it('checks GitHub and tells the newer version', async () => {
    const { u, asked } = updater(latest())
    const s = await u.check()
    expect(asked).toEqual([LATEST_URL])
    expect(s).toMatchObject({ current: '0.7.6', available: '0.7.7', checking: false })
    expect(s.checkedAt).toBeGreaterThan(0)
  })

  it('keeps a failed check as its reason', async () => {
    const u = new AppUpdater({ current: '0.7.6', exe: '/x', packaged: false, pid: 1, args: [], changed: () => undefined, fetcher: async () => new Response('', { status: 503 }) })
    const s = await u.check()
    expect(s).toMatchObject({ checkError: 'HTTP 503', checking: false })
    expect(s.available).toBeUndefined()
  })

  it('does not install where it can not replace the app', async () => {
    const { u } = updater(latest())
    await u.check()
    await u.install(() => { throw new Error('must not quit') })
    expect(u.status()).toMatchObject({ stage: 'error', error: 'notPackaged' })
  })

  it('downloads a DMG only when it matches its checksum', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'vk-upd-'))
    const rel: Release = { version: '0.7.7', notesUrl: '', dmgUrl: DMG, sha256: sha, size: body.length }
    const download = (u: AppUpdater, file: string): Promise<void> => (u as unknown as { download(r: Release, f: string): Promise<void> }).download(rel, file)
    await download(updater(latest()).u, join(dir, 'ok.dmg'))
    expect(readFileSync(join(dir, 'ok.dmg'))).toEqual(body)
    await expect(download(updater(latest(), Buffer.from('something else')).u, join(dir, 'bad.dmg'))).rejects.toThrow('checksum')
  })
})

describe('mounting the update DMG', () => {
  const recorder = (fails: string[]) => {
    const calls: string[] = []
    const exec = async (cmd: string, args: string[]) => {
      calls.push([cmd.split('/').pop(), ...args].join(' '))
      if (fails.includes(cmd.split('/').pop()!)) throw new Error(`${cmd} failed`)
      return { out: '', err: '' }
    }
    return { calls, exec }
  }

  it('uses diskutil image, read-only and hidden at its own mount point', async () => {
    const r = recorder([])
    await attachDmg('/w/u.dmg', '/w/mnt', r.exec)
    await detachDmg('/w/mnt', false, r.exec)
    await detachDmg('/w/mnt', true, r.exec)
    expect(r.calls).toEqual(['diskutil image attach --readOnly --nobrowse --mountPoint /w/mnt /w/u.dmg',
      'diskutil eject /w/mnt', 'diskutil eject force /w/mnt'])
  })

  it('falls back to hdiutil where diskutil has no image verb', async () => {
    const r = recorder(['diskutil'])
    await attachDmg('/w/u.dmg', '/w/mnt', r.exec)
    await detachDmg('/w/mnt', true, r.exec)
    expect(r.calls.filter((c) => c.startsWith('hdiutil'))).toEqual([
      'hdiutil attach -nobrowse -readonly -noautoopen -mountpoint /w/mnt /w/u.dmg', 'hdiutil detach -quiet -force /w/mnt'])
    // a diskutil attach that failed half way is ejected before hdiutil tries
    expect(r.calls.slice(0, 3)).toEqual(['diskutil image attach --readOnly --nobrowse --mountPoint /w/mnt /w/u.dmg',
      'diskutil eject force /w/mnt', 'hdiutil attach -nobrowse -readonly -noautoopen -mountpoint /w/mnt /w/u.dmg'])
  })

  it('fails when neither can mount it', async () => {
    const r = recorder(['diskutil', 'hdiutil'])
    await expect(attachDmg('/w/u.dmg', '/w/mnt', r.exec)).rejects.toThrow('hdiutil failed')
  })
})
