// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { appendFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { History } from './history'
import type { Job } from '@shared/types'

const job = (id: string, prompt: string, modelDir = '/models/SD-1.5'): Job => ({
  id, page: 'text', prompt, modelId: 'm', modelDir, width: 512, height: 512, seed: 1,
})
const folder = (): string => mkdtempSync(join(tmpdir(), 'vk-history-'))

describe('history', () => {
  it('finds pictures moved to another drive again by their name, once, with a backup', async () => {
    const dir = folder()
    const pictures = join(dir, 'pictures')
    mkdirSync(pictures)
    const here = join(dir, 'here.png')
    writeFileSync(here, 'x')
    writeFileSync(join(pictures, 'gone_1a2b.png'), 'x')
    writeFileSync(join(pictures, 'start.png'), 'x')
    const old = new History(() => dir)
    old.add({ ...job('a', 'a fox'), inputImage: '/Volumes/old-drive/input/start.png' }, ['/Volumes/old-drive/pictures/gone_1a2b.png', here], 100)
    old.favorite('a', '/Volumes/old-drive/pictures/gone_1a2b.png', true)
    old.add(job('b', 'a cat'), ['/Volumes/old-drive/pictures/lost.png'], 200)
    const lines: string[] = []
    let changes = 0
    const h = new History(() => dir, () => changes++, () => [pictures, join(dir, 'no-such-folder')], (l) => lines.push(l))
    // shown at once with the old paths; the search runs after (a hanging network drive must not hold the app)
    expect(h.list({}).entries[1].files[0]).toBe('/Volumes/old-drive/pictures/gone_1a2b.png')
    await h.settled()
    expect(changes).toBe(1)
    const [b, a] = h.list({}).entries
    expect(a.files).toEqual([join(pictures, 'gone_1a2b.png'), here])
    expect(a.favorites).toEqual([join(pictures, 'gone_1a2b.png')])
    expect(a.job.inputImage).toBe('/Volumes/old-drive/input/start.png')  // inputs keep their path: names like IMG_1234 repeat
    expect(b.files).toEqual(['/Volumes/old-drive/pictures/lost.png'])  // nowhere to be found: left as it was
    expect(lines).toHaveLength(1)
    expect(h.hasFile(join(pictures, 'gone_1a2b.png'))).toBe(true)
    // written once: a restart reads the new paths; the backup holds the old ones and is not overwritten
    const backup = readFileSync(join(dir, `entries.jsonl.before-repair-${new Date().toISOString().slice(0, 10)}`), 'utf8')
    expect(backup).toContain('/Volumes/old-drive/pictures/gone_1a2b.png')
    expect(new History(() => dir).list({}).entries[1].files[0]).toBe(join(pictures, 'gone_1a2b.png'))
    await new History(() => dir, () => {}, () => [pictures]).settled()
    expect(readFileSync(join(dir, `entries.jsonl.before-repair-${new Date().toISOString().slice(0, 10)}`), 'utf8')).toBe(backup)
    expect(existsSync(join(dir, 'entries.jsonl.tmp'))).toBe(false)
  })

  it('keeps a favourite set while the search for moved pictures runs, and the backup holds the old paths', async () => {
    const dir = folder()
    const pictures = join(dir, 'pictures')
    mkdirSync(pictures)
    writeFileSync(join(pictures, 'one_1a2b.png'), 'x')
    writeFileSync(join(pictures, 'two_3c4d.png'), 'x')
    new History(() => dir).add(job('a', 'a fox'), ['/Volumes/old/one_1a2b.png', '/Volumes/old/two_3c4d.png'], 100)
    const h = new History(() => dir, () => {}, () => [pictures])
    h.list({})  // the search starts
    h.favorite('a', '/Volumes/old/two_3c4d.png', true)  // meanwhile, on the path still shown
    await h.settled()
    const [a] = h.list({}).entries
    expect(a.files).toEqual([join(pictures, 'one_1a2b.png'), join(pictures, 'two_3c4d.png')])
    expect(a.favorites).toEqual([join(pictures, 'two_3c4d.png')])
    expect(h.hasFile(join(pictures, 'one_1a2b.png'))).toBe(true)
    const backup = readFileSync(join(dir, `entries.jsonl.before-repair-${new Date().toISOString().slice(0, 10)}`), 'utf8')
    expect(backup).toContain('/Volumes/old/one_1a2b.png')
    expect(backup).not.toContain(join(pictures, 'one_1a2b.png'))
  })

  it('keeps entries across restarts, newest first', () => {
    const dir = folder()
    const h = new History(() => dir)
    h.add(job('a', 'a lighthouse'), ['/i/a.png'], 100, { seconds: 61.5, secondsPerStep: 2.1 })
    h.add({ ...job('b', 'a fox'), consent: true }, ['/i/b.mp4'], 200)
    const again = new History(() => dir).list({})
    expect(again.total).toBe(2)
    expect(again.entries.map((e) => e.id)).toEqual(['b', 'a'])
    expect(again.entries[0]).toMatchObject({ kind: 'video', modelName: 'SD-1.5' })
    expect('consent' in again.entries[0].job).toBe(false)
    expect(again.entries[1]).toMatchObject({ seconds: 61.5, secondsPerStep: 2.1 })
  })

  it('knows its results and the pictures its jobs started from, also after a restart and a removal', () => {
    const dir = folder()
    const h = new History(() => dir)
    expect(h.hasFile('/i/a.png')).toBe(false)
    h.add({ ...job('a', 'a portrait'), inputImage: '/photos/mum.jpg', maskImage: '/data/inputs/m.png',
      photoTool: { folder: '/tools/sam', mask: '/data/inputs/selections/mask_1.png' } }, ['/i/a.png'], 100)
    expect(h.hasFile('/i/a.png') && h.hasFile('/photos/mum.jpg') && h.hasFile('/data/inputs/m.png')).toBe(true)
    expect(h.hasFile('/data/inputs/selections/mask_1.png')).toBe(true)  // Enhance's selection: kept when old selections go
    const again = new History(() => dir)
    expect(again.hasFile('/photos/mum.jpg')).toBe(true)
    expect(again.hasFile('/photos/other.jpg')).toBe(false)
    again.remove(['a'])
    expect(again.hasFile('/photos/mum.jpg')).toBe(false)
  })

  it('searches prompt and model name, pages the result', () => {
    const h = new History(folder)
    const dir = folder()
    const one = new History(() => dir)
    for (let i = 0; i < 5; i++) one.add(job('l' + i, 'red lighthouse ' + i), ['/i/x.png'], i)
    one.add(job('f', 'a fox', '/models/FLUX.2-klein'), ['/i/f.png'], 10)
    expect(one.list({ query: 'LIGHTHOUSE red' }).total).toBe(5)
    expect(one.list({ query: 'flux' }).entries.map((e) => e.id)).toEqual(['f'])
    expect(one.list({ query: 'lighthouse', offset: 1, limit: 2 }).entries.map((e) => e.id)).toEqual(['l3', 'l2'])
    expect(h.list({}).total).toBe(0)
  })

  it('removes entries and reports their files', () => {
    const dir = folder()
    const h = new History(() => dir)
    h.add(job('a', 'one'), ['/i/a.png'], 1)
    h.add(job('b', 'two'), ['/i/b.png'], 2)
    expect(h.remove(['a', 'missing'])).toEqual(['/i/a.png'])
    expect(new History(() => dir).list({}).entries.map((e) => e.id)).toEqual(['b'])
  })

  it('marks single files as favourites and keeps the marks', () => {
    const dir = folder()
    let changes = 0
    const h = new History(() => dir, () => changes++)
    h.add(job('a', 'one'), ['/i/a1.png', '/i/a2.png'], 1)
    h.add(job('b', 'two'), ['/i/b.png'], 2)
    h.add(job('c', 'three'), ['/i/c.png'], 3)
    changes = 0
    expect(h.favorite('a', '/i/a2.png', true)).toBe(true)
    expect(h.favorite('c', '/i/c.png', true)).toBe(true)
    expect(h.favorite('a', '/i/a1.png', true)).toBe(true)
    expect(changes).toBe(3)
    // marking twice changes nothing
    expect(h.favorite('c', '/i/c.png', true)).toBe(true)
    expect(changes).toBe(3)
    // a file of another entry, or one that is not there
    expect(h.favorite('b', '/i/c.png', true)).toBe(false)
    expect(h.favorite('missing', '/i/c.png', true)).toBe(false)

    const again = new History(() => dir)
    expect(again.favorites()).toEqual(['/i/c.png', '/i/a1.png', '/i/a2.png'])
    expect(again.list({}).entries.find((e) => e.id === 'a')?.favorites).toEqual(['/i/a1.png', '/i/a2.png'])
    expect(again.list({ favorites: true }).entries.map((e) => e.id)).toEqual(['c', 'a'])
    expect(again.list({ favorites: true, query: 'three' }).total).toBe(1)

    expect(again.favorite('c', '/i/c.png', false)).toBe(true)
    expect(again.favorite('a', '/i/a1.png', false)).toBe(true)
    const third = new History(() => dir)
    expect(third.favorites()).toEqual(['/i/a2.png'])
    expect(third.list({ favorites: true }).entries.map((e) => e.id)).toEqual(['a'])
    expect('favorites' in third.list({}).entries.find((e) => e.id === 'c')!).toBe(false)
  })

  it('drops the favourites of a removed entry', () => {
    const dir = folder()
    const h = new History(() => dir)
    h.add(job('a', 'one'), ['/i/a.png'], 1)
    h.add(job('b', 'two'), ['/i/b.png'], 2)
    h.favorite('a', '/i/a.png', true)
    h.favorite('b', '/i/b.png', true)
    h.remove(['a'])
    const again = new History(() => dir)
    expect(again.favorites()).toEqual(['/i/b.png'])
    expect(again.list({ favorites: true }).total).toBe(1)
  })

  it('survives a damaged line', () => {
    const dir = folder()
    const h = new History(() => dir)
    h.add(job('a', 'one'), ['/i/a.png'], 1)
    appendFileSync(join(dir, 'entries.jsonl'), '{"broken\n')
    expect(new History(() => dir).list({}).total).toBe(1)
  })

  it('takes the history along to a new folder without one', () => {
    let dir = folder()
    const h = new History(() => dir)
    h.add(job('a', 'one'), ['/i/a.png'], 1)
    const target = folder()
    h.relocate(target)
    dir = target
    h.reload()
    expect(h.list({}).total).toBe(1)
    expect(readFileSync(join(target, 'entries.jsonl'), 'utf8')).toContain('"one"')
  })

  it('keeps the next entry when the file ends in a line cut off by a crash', () => {
    const dir = folder()
    const h = new History(() => dir)
    h.add(job('a', 'one'), ['/images/a.png'], 1)
    appendFileSync(join(dir, 'entries.jsonl'), '{"id":"broken","job":')
    const h2 = new History(() => dir)
    h2.add(job('b', 'two'), ['/images/b.png'], 2)
    expect(new History(() => dir).list({}).entries.map((e) => e.id)).toEqual(['b', 'a'])
  })
})
