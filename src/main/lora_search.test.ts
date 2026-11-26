// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { beforeEach, describe, expect, it } from 'vitest'
import { ALL_BASES, BASE_GROUPS, LORA_BASES, loraBase } from '@shared/lora_bases'
import type { Asset } from '@shared/types'
import {
  allowedHost, civitaiThumb, civitaiUrl, clearSearchCache, decodeCursor, encodeCursor, hfNextCursor, hfUrl, parseCivitai,
  parseHf, pickLoraFile, pickModelFile, previewPicture, readLimited, searchLoras, spellSd, type FetchLike,
} from './lora_search'

const sdxl = loraBase('sdxl')!
const flux = loraBase('flux1_dev')!
const IMG = 'https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/7c79113b-a6d7-4e22-a3d4-b06c9bb2cfa4/original=true/64739376.jpeg'

const civitaiModel = (id: number, extra: Record<string, unknown> = {}, version: Record<string, unknown> = {}) => ({
  id, name: `LoRA ${id}`, type: 'LORA', nsfw: false, nsfwLevel: 1,
  creator: { username: 'maker' }, stats: { downloadCount: 12345, thumbsUpCount: 678 },
  allowCommercialUse: ['Image', 'Rent'],
  modelVersions: [
    { id: id * 10 + 1, name: 'v2 for Pony', baseModel: 'Pony', availability: 'Public', files: [{ name: 'p.safetensors', type: 'Model', primary: true, sizeKB: 1000, metadata: { format: 'SafeTensor' } }], images: [] },
    {
      id: id * 10, name: 'v1', baseModel: 'SDXL 1.0', availability: 'Public', trainedWords: ['detailed, sharp', 'detailed'],
      files: [
        { name: 'old.pt', type: 'Model', primary: true, sizeKB: 9000, metadata: { format: 'PickleTensor' } },
        { name: 'lora.safetensors', type: 'Model', sizeKB: 223 * 1024, metadata: { format: 'SafeTensor' } },
      ],
      images: [
        { url: 'https://image.civitai.com/a/b/original=true/clip.mp4', type: 'video', nsfwLevel: 1 },
        { url: 'https://image.civitai.com/a/c/original=true/adult.jpeg', type: 'image', nsfwLevel: 8 },
        { url: IMG, type: 'image', nsfwLevel: 1 },
      ],
      ...version,
    },
  ],
  ...extra,
})

const hfModel = (id: string, extra: Record<string, unknown> = {}) => ({
  id, author: id.split('/')[0], downloads: 500, likes: 20, gated: false,
  tags: ['lora', 'base_model:adapter:black-forest-labs/FLUX.1-dev', 'license:apache-2.0'],
  cardData: { license: 'apache-2.0', instance_prompt: 'tok style', widget: [{ text: 'a cat', output: { url: 'images/cat.png' } }] },
  siblings: [{ rfilename: '.gitattributes' }, { rfilename: 'README.md' }, { rfilename: 'my_lora.safetensors' }, { rfilename: 'images/cat.png' }],
  ...extra,
})

const response = (body: unknown, init: { status?: number; headers?: Record<string, string>; url?: string } = {}): Response => {
  const res = new Response(typeof body === 'string' || body instanceof Uint8Array ? body : JSON.stringify(body), { status: init.status ?? 200, headers: init.headers })
  if (init.url) Object.defineProperty(res, 'url', { value: init.url })
  return res
}

describe('hosts asked', () => {
  it('allows https on Civitai and Hugging Face only', () => {
    expect(allowedHost('https://civitai.com/api/v1/models')).toBe(true)
    expect(allowedHost('https://image.civitai.com/x/y/width=320/z.jpeg')).toBe(true)
    expect(allowedHost('https://huggingface.co/api/models')).toBe(true)
    expect(allowedHost('https://cas-bridge.xethub.hf.co/x')).toBe(true)
    expect(allowedHost('http://civitai.com/api')).toBe(false)
    expect(allowedHost('https://civitai.com.evil.example/x')).toBe(false)
    expect(allowedHost('https://evilcivitai.com/x')).toBe(false)
    expect(allowedHost('https://user:pw@civitai.com/x')).toBe(false)
    expect(allowedHost('https://civitai.com:8443/x')).toBe(false)
    expect(allowedHost('file:///etc/passwd')).toBe(false)
    expect(allowedHost('not a url')).toBe(false)
  })
})

describe('cursors', () => {
  it('round-trips and rejects nonsense', () => {
    expect(decodeCursor(encodeCursor({ i: 1, c: 'abc|12' }))).toEqual({ i: 1, c: 'abc|12' })
    expect(decodeCursor(undefined)).toEqual({ i: 0 })
    expect(decodeCursor('%%%')).toEqual({ i: 0 })
    expect(decodeCursor(encodeCursor({ i: -3 }))).toEqual({ i: 0 })
    expect(decodeCursor(Buffer.from('{"i":2,"c":5}').toString('base64url'))).toEqual({ i: 2, c: undefined })
  })

  it('reads the next page of Hugging Face from its Link header', () => {
    expect(hfNextCursor('<https://huggingface.co/api/models?filter=x&cursor=eyJhIjoxfQ%3D%3D>; rel="next"')).toBe('eyJhIjoxfQ==')
    expect(hfNextCursor(null)).toBeUndefined()
    expect(hfNextCursor('<https://huggingface.co/api/models?x=1>; rel="prev"')).toBeUndefined()
  })
})

describe('Civitai', () => {
  it('asks for LoRAs of the base, safe ones only unless allowed', () => {
    const safe = new URL(civitaiUrl(loraBase('flux2_klein4')!, 'anime', 'c|1', true))
    expect(safe.searchParams.getAll('baseModels')).toEqual(['Flux.2 Klein 4B', 'Flux.2 Klein 4B-base'])
    expect(safe.searchParams.get('types')).toBe('LORA')
    expect(safe.searchParams.get('sort')).toBe('Most Downloaded')
    expect(safe.searchParams.get('nsfw')).toBe('false')
    expect(safe.searchParams.get('query')).toBe('anime')
    expect(safe.searchParams.get('cursor')).toBe('c|1')
    expect(new URL(civitaiUrl(sdxl, undefined, undefined, false)).searchParams.has('nsfw')).toBe(false)
  })

  it('asks for small preview pictures', () => {
    expect(civitaiThumb(IMG)).toBe(IMG.replace('original=true', 'width=320'))
    expect(civitaiThumb('https://image.civitai.com/key/id/name.jpeg')).toBe('https://image.civitai.com/key/id/width=320/name.jpeg')
    expect(civitaiThumb('https://example.com/a.jpeg')).toBeUndefined()
  })

  it('reads a page: the version for the base, its safetensors file, trigger words and a safe preview', () => {
    const page = parseCivitai({ items: [civitaiModel(1)], metadata: { nextCursor: '2026|5' } }, sdxl, true, [])
    expect(page.hits).toHaveLength(1)
    expect(page.hits[0]).toMatchObject({
      source: 'civitai', ref: 'https://civitai.com/models/1?modelVersionId=10', page: 'https://civitai.com/models/1?modelVersionId=10',
      title: 'LoRA 1', version: 'v1', author: 'maker', baseModel: 'SDXL 1.0', downloads: 12345, likes: 678,
      triggerWords: ['detailed', 'sharp'], sizeMb: 223, previewUrl: IMG.replace('original=true', 'width=320'), previewExplicit: false,
      nsfw: false, licence: 'Pictures may be sold', needsToken: false, installed: false,
    })
    expect(decodeCursor(page.cursor)).toEqual({ i: 0, c: '2026|5' })
    expect(parseCivitai({ items: [], metadata: {} }, sdxl, true, []).cursor).toBeUndefined()
    // both versions with a SafeTensor file can be chosen; the Pony one is for another base
    expect(page.hits[0].versions?.map((v) => [v.id, v.name, v.fits, v.sizeMb])).toEqual([[11, 'v2 for Pony', false, 1], [10, 'v1', true, 223]])
    expect(page.hits[0].versions?.[0].ref).toBe('https://civitai.com/models/1?modelVersionId=11')
  })

  it('leaves out adult models and pictures when nudity is not allowed', () => {
    const items = [
      civitaiModel(1, { nsfw: true }),
      civitaiModel(2, { nsfwLevel: 24 }),  // only adult pictures
      civitaiModel(3, { nsfwLevel: 31 }, { images: [{ url: IMG, type: 'image', nsfwLevel: 16 }] }),
    ]
    const safe = parseCivitai({ items }, sdxl, true, [])
    expect(safe.hits.map((h) => h.title)).toEqual(['LoRA 3'])
    expect(safe.hits[0].previewUrl).toBeUndefined()  // its only picture is adult

    const all = parseCivitai({ items }, sdxl, false, [])
    expect(all.hits.map((h) => [h.title, h.nsfw])).toEqual([['LoRA 1', true], ['LoRA 2', true], ['LoRA 3', false]])
    // allowed, but still marked so the page blurs it
    expect(all.hits[2]).toMatchObject({ previewExplicit: true })
    expect(all.hits[0]).toMatchObject({ previewExplicit: true })  // the first picture is the adult one
  })

  it('takes tags and names that say adult content for adult', () => {
    const items = [civitaiModel(1, { tags: ['style', 'nude'] }), civitaiModel(2, { name: 'NSFW MASTER' }), civitaiModel(3, { name: 'Sussex landscapes', tags: ['style'] })]
    expect(parseCivitai({ items }, sdxl, true, []).hits.map((h) => h.title)).toEqual(['Sussex landscapes'])
    expect(parseCivitai({ items }, sdxl, false, []).hits.map((h) => h.nsfw)).toEqual([true, true, false])
  })

  it('skips models without a version for the base or without a safetensors file, and marks early access', () => {
    const items = [
      civitaiModel(1, {}, { baseModel: 'SD 1.5' }),
      civitaiModel(2, {}, { files: [{ name: 'x.pt', type: 'Model', metadata: { format: 'PickleTensor' } }] }),
      civitaiModel(3, { type: 'Checkpoint' }),
      civitaiModel(4, {}, { availability: 'EarlyAccess' }),
    ]
    const page = parseCivitai({ items }, sdxl, true, [])
    expect(page.hits.map((h) => [h.title, h.needsToken])).toEqual([['LoRA 4', true]])
  })

  it('marks installed LoRAs', () => {
    const installed: Asset = {
      id: 'lora:a', title: 'a', name: 'a', folder: '/l/a', type: 'lora', meta: { arch: '', family: 'sdxl', label: '', runtime: 'diffusers', kind: 'image' },
      source: { type: 'civitai', ref: 'https://civitai.com/models/1' },
    }
    expect(parseCivitai({ items: [civitaiModel(1), civitaiModel(2)] }, sdxl, true, [installed]).hits.map((h) => h.installed)).toEqual([true, false])
  })
})

describe('Hugging Face', () => {
  it('asks for adapters of the base repository', () => {
    const u = new URL(hfUrl('black-forest-labs/FLUX.1-dev', 'anime', 'abc'))
    expect(u.hostname).toBe('huggingface.co')
    expect(u.searchParams.getAll('filter')).toEqual(['base_model:adapter:black-forest-labs/FLUX.1-dev', 'lora'])
    expect(u.searchParams.get('sort')).toBe('downloads')
    expect(u.searchParams.get('search')).toBe('anime')
    expect(u.searchParams.get('cursor')).toBe('abc')
    expect(u.searchParams.getAll('expand[]')).toContain('siblings')
  })

  it('picks the LoRA file the import should take', () => {
    expect(pickLoraFile(['a.safetensors', 'pytorch_lora_weights.safetensors'])).toBe('pytorch_lora_weights.safetensors')
    expect(pickLoraFile(['sample.safetensors', 'Hyper-FLUX-8steps-lora.safetensors'])).toBe('Hyper-FLUX-8steps-lora.safetensors')
    expect(pickLoraFile(['transformer/diffusion_pytorch_model.safetensors', 'model.safetensors'])).toBeUndefined()
    expect(pickLoraFile(['sub/x.safetensors'])).toBe('sub/x.safetensors')
    expect(pickLoraFile(['README.md'])).toBeUndefined()
  })

  it('reads repositories: file, trigger word, licence, preview; without a LoRA file they are left out', () => {
    const hits = parseHf([
      hfModel('someone/flux-style'),
      hfModel('someone/no-weights', { siblings: [{ rfilename: 'README.md' }] }),
      hfModel('someone/gated', { gated: 'manual', siblings: [{ rfilename: 'a.safetensors' }, { rfilename: 'b_lora.safetensors' }] }),
    ], flux, true, [])
    expect(hits.map((h) => h.ref)).toEqual(['someone/flux-style', 'someone/gated'])
    expect(hits[0]).toMatchObject({
      source: 'hf', ref: 'someone/flux-style', page: 'https://huggingface.co/someone/flux-style', file: 'my_lora.safetensors',
      title: 'flux-style', author: 'someone', baseModel: 'FLUX.1 [dev]', downloads: 500, likes: 20, triggerWords: ['tok style'],
      licence: 'Apache License 2.0', previewUrl: 'https://huggingface.co/someone/flux-style/resolve/main/images/cat.png',
      previewExplicit: false, nsfw: false, gated: false, installed: false,
    })
    expect(hits[1]).toMatchObject({ gated: true, needsToken: true, file: 'b_lora.safetensors', files: ['a.safetensors', 'b_lora.safetensors'] })
  })

  it('leaves out repositories not for all audiences unless allowed, and then marks their previews', () => {
    const adult = hfModel('x/adult', { tags: ['lora', 'not-for-all-audiences'] })
    const cardOnly = hfModel('x/card', { cardData: { tags: ['nsfw'], widget: [{ output: { url: 'https://evil.example/a.png' } }] } })
    expect(parseHf([adult, cardOnly, hfModel('x/fine')], flux, true, []).map((h) => h.ref)).toEqual(['x/fine'])
    const all = parseHf([adult, cardOnly], flux, false, [])
    expect(all.map((h) => [h.ref, h.nsfw, h.previewExplicit])).toEqual([['x/adult', true, true], ['x/card', true, undefined]])
    expect(all[1].previewUrl).toBeUndefined()  // a picture elsewhere is not fetched
  })

  it('marks the installed file of a repository', () => {
    const installed: Asset = {
      id: 'lora:a', title: 'a', name: 'a', folder: '/l/a', type: 'lora', meta: { arch: '', family: 'flux1', label: '', runtime: 'diffusers', kind: 'image' },
      source: { type: 'hf', ref: 'someone/flux-style', file: 'my_lora.safetensors' },
    }
    expect(parseHf([hfModel('someone/flux-style')], flux, true, [installed])[0].installed).toBe(true)
  })
})

describe('models', () => {
  beforeEach(clearSearchCache)
  const meta = { arch: '', family: 'sdxl', label: '', runtime: 'diffusers', kind: 'image' } as const

  it('asks Civitai for checkpoints and Hugging Face for fine-tunes of the base', () => {
    expect(new URL(civitaiUrl(sdxl, undefined, undefined, true, 'model')).searchParams.get('types')).toBe('Checkpoint')
    expect(new URL(hfUrl('stabilityai/stable-diffusion-xl-base-1.0', undefined, undefined, 'model')).searchParams.getAll('filter'))
      .toEqual(['base_model:finetune:stabilityai/stable-diffusion-xl-base-1.0'])
  })

  it('reads checkpoints, not LoRAs, and marks an installed model, not an installed LoRA of the same page', () => {
    const body = { items: [civitaiModel(1, { type: 'Checkpoint' }), civitaiModel(2)] }
    const asset = (type: 'model' | 'lora'): Asset => ({ id: `${type}:a`, title: 'a', name: 'a', folder: '/m/a', type, meta,
      source: { type: 'civitai', ref: 'https://civitai.com/models/1?modelVersionId=10' } })
    expect(parseCivitai(body, sdxl, true, [], 'model').hits.map((h) => h.ref)).toEqual(['https://civitai.com/models/1?modelVersionId=10'])
    expect(parseCivitai(body, sdxl, true, [asset('model')], 'model').hits[0].installed).toBe(true)
    expect(parseCivitai(body, sdxl, true, [asset('lora')], 'model').hits[0].installed).toBe(false)
  })

  it('takes a diffusers repository whole, else a checkpoint at its top; LoRAs tagged as fine-tunes are left out', () => {
    expect(pickModelFile(['model_index.json', 'unet/diffusion_pytorch_model.safetensors'])).toEqual({})
    expect(pickModelFile(['README.md', 'my-merge-v2.safetensors', 'extra_lora.safetensors', 'sub/x.safetensors']))
      .toEqual({ file: 'my-merge-v2.safetensors', files: ['my-merge-v2.safetensors'] })
    expect(pickModelFile(['README.md'])).toBeNull()
    const hits = parseHf([
      hfModel('a/whole', { tags: ['diffusers'], siblings: [{ rfilename: 'model_index.json' }] }),
      hfModel('a/single', { tags: [], siblings: [{ rfilename: 'single.safetensors' }] }),
      hfModel('a/lora-really'),
      hfModel('a/FLUX.1-dev-Controlnet-Canny', { tags: [], siblings: [{ rfilename: 'model_index.json' }] }),
      hfModel('a/adapter', { tags: ['IP-Adapter'], siblings: [{ rfilename: 'model_index.json' }] }),
    ], sdxl, true, [], 'model')
    expect(hits.map((h) => [h.ref, h.file])).toEqual([['a/whole', undefined], ['a/single', 'single.safetensors']])
  })

  it('offers GGUF checkpoints (Q4_K_S first) and never a VAE or text encoder as the model', () => {
    // city96/FLUX.1-schnell-gguf: the recommended FLUX.1 [schnell] 4 bit
    expect(pickModelFile(['README.md', 'flux1-schnell-F16.gguf', 'flux1-schnell-Q4_K_S.gguf', 'flux1-schnell-Q8_0.gguf']))
      .toEqual({ file: 'flux1-schnell-Q4_K_S.gguf', files: ['flux1-schnell-F16.gguf', 'flux1-schnell-Q4_K_S.gguf', 'flux1-schnell-Q8_0.gguf'] })
    // second-state/FLUX.1-schnell-GGUF: ae.safetensors (the VAE) was offered as the model
    expect(pickModelFile(['ae.safetensors', 'clip_l-Q8_0.gguf', 't5xxl-Q4_K_M.gguf', 'flux1-schnell-Q4_0.gguf'])?.file)
      .toBe('flux1-schnell-Q4_0.gguf')
    expect(pickModelFile(['clip_g.safetensors', 'clip_l.safetensors', 't5xxl_fp16.safetensors'])).toBeNull()
    // a checkpoint with its VAE baked in keeps its name
    expect(pickModelFile(['dreamshaper_8_vae.safetensors'])?.file).toBe('dreamshaper_8_vae.safetensors')
  })

  it('takes the repositories of the MLX runtime whole', () => {
    expect(pickModelFile(['README.md', 'mflux_model.json', 'transformer/0.safetensors'], ['mflux', 'mlx'])).toEqual({})  // Fibo 2.0
    expect(pickModelFile(['split_model.json', 'config.json', 'connector.safetensors'], ['mlx'])).toEqual({})  // LTX-2.3
    expect(pickModelFile(['config.json', 'LICENSE.md', 'transformer/model.safetensors'], ['mlx'])).toEqual({})  // FLUX 3 Klein
    // config.json alone (no MLX repository): not a model the import reads
    expect(pickModelFile(['config.json', 'README.md'])).toBeNull()
    // an mflux FLUX.1 save (manifest.json): the import does not read it
    expect(pickModelFile(['manifest.json', 'transformer/0.safetensors'], ['mflux', 'mlx'])).toBeNull()
  })

  it('also asks Hugging Face with "sd" written out, those hits first', async () => {
    expect(spellSd('sd 3.5 large')).toBe('stable diffusion 3.5 large')
    expect(spellSd('SD3.5 Large')).toBe('stable diffusion 3.5 Large')
    expect(spellSd('sdxl turbo')).toBeUndefined()
    expect(spellSd('castle')).toBeUndefined()
    const asked: string[] = []
    const fetcher: FetchLike = async (url) => {
      const q = new URL(url).searchParams.get('search')!
      asked.push(q)
      const id = q.startsWith('stable') ? 'stabilityai/stable-diffusion-3.5-large' : 'calcuis/sd3.5-large'
      return response([hfModel(id, { tags: [], siblings: [{ rfilename: 'model_index.json' }] })], { url })
    }
    const page = await searchLoras({ base: 'all', source: 'hf', kind: 'model', query: 'sd 3.5 large' }, { fetcher, safe: true, assets: [] })
    expect(page.hits.map((h) => h.ref)).toEqual(['stabilityai/stable-diffusion-3.5-large', 'calcuis/sd3.5-large'])
    expect(asked).toEqual(['sd 3.5 large', 'stable diffusion 3.5 large'])
  })

  it('keeps model and LoRA answers apart', async () => {
    const asked: string[] = []
    const fetcher: FetchLike = async (url) => (asked.push(url), response({ items: [] }, { url }))
    await searchLoras({ base: 'sdxl', source: 'civitai' }, { fetcher, safe: true, assets: [] })
    await searchLoras({ base: 'sdxl', source: 'civitai', kind: 'model' }, { fetcher, safe: true, assets: [] })
    expect(asked.map((u) => new URL(u).searchParams.get('types'))).toEqual(['LORA', 'Checkpoint'])
  })

  it('searches without a base: no base filter, the newest version, pictures models on Hugging Face', () => {
    expect(loraBase('all')).toBe(ALL_BASES)
    const u = new URL(civitaiUrl(ALL_BASES, 'castle', undefined, true, 'model'))
    expect(u.searchParams.getAll('baseModels')).toEqual([])
    expect(u.searchParams.get('query')).toBe('castle')
    const h = new URL(hfUrl('', 'castle', undefined, 'model'))
    expect(h.searchParams.get('pipeline_tag')).toBe('text-to-image')
    expect(h.searchParams.getAll('filter')).toEqual([])
    expect(new URL(hfUrl('', undefined, undefined, 'lora')).searchParams.getAll('filter')).toEqual(['lora'])
    // the newest version whatever its base (here the Pony one, listed first)
    expect(parseCivitai({ items: [civitaiModel(1)] }, ALL_BASES, true, []).hits[0].baseModel).toBe('Pony')
    const named = parseHf([hfModel('a/b', { tags: ['lora', 'base_model:adapter:black-forest-labs/FLUX.1-dev'] })], ALL_BASES, true, [])
    expect(named[0].baseModel).toBe('FLUX.1 [dev]')
  })

  it('lists every base exactly once under a model group', () => {
    const grouped = BASE_GROUPS.flatMap((g) => g.bases.map((b) => b.id))
    expect(grouped.sort()).toEqual(LORA_BASES.map((b) => b.id).sort())
    expect(BASE_GROUPS.map((g) => g.label).slice(0, 3)).toEqual(['Stable Diffusion', 'SDXL', 'FLUX'])
  })
})

describe('searching', () => {
  beforeEach(clearSearchCache)

  it('asks Civitai once and keeps the answer for ten minutes', async () => {
    const asked: string[] = []
    const fetcher: FetchLike = async (url) => {
      asked.push(url)
      return response({ items: [civitaiModel(1)], metadata: { nextCursor: 'n' } }, { url })
    }
    const opts = { fetcher, safe: true, assets: [], now: 1000 }
    const first = await searchLoras({ base: 'sdxl', source: 'civitai' }, opts)
    await searchLoras({ base: 'sdxl', source: 'civitai' }, { ...opts, now: 1000 + 9 * 60_000 })
    expect(asked).toHaveLength(1)
    await searchLoras({ base: 'sdxl', source: 'civitai' }, { ...opts, now: 1000 + 11 * 60_000 })
    expect(asked).toHaveLength(2)
    // the next page goes with Civitai's cursor
    await searchLoras({ base: 'sdxl', source: 'civitai', cursor: first.cursor }, opts)
    expect(new URL(asked[2]).searchParams.get('cursor')).toBe('n')
  })

  it('goes through the base repositories of Hugging Face one after the other', async () => {
    const asked: string[] = []
    const fetcher: FetchLike = async (url) => {
      asked.push(url)
      const repo = new URL(url).searchParams.getAll('filter')[0].split(':').slice(2).join(':')
      const cursor = new URL(url).searchParams.get('cursor')
      const n = repo.endsWith('v1-5') && repo.startsWith('runwayml') ? (cursor ? 2 : 1) : 3
      const link = repo.startsWith('runwayml') && !cursor ? '<https://huggingface.co/api/models?cursor=p2>; rel="next"' : ''
      return response(Array.from({ length: 12 }, (_, k) => hfModel(`r${n}/m${k}`)), { url, headers: link ? { link } : {} })
    }
    const opts = { fetcher, safe: true, assets: [] }
    const one = await searchLoras({ base: 'sd15', source: 'hf' }, opts)
    expect(one.hits).toHaveLength(12)
    expect(decodeCursor(one.cursor)).toEqual({ i: 0, c: 'p2' })
    const two = await searchLoras({ base: 'sd15', source: 'hf', cursor: one.cursor }, opts)
    expect(decodeCursor(two.cursor)).toEqual({ i: 1, c: undefined })
    const three = await searchLoras({ base: 'sd15', source: 'hf', cursor: two.cursor }, opts)
    expect(three.cursor).toBeUndefined()
    expect(asked.map((u) => new URL(u).searchParams.getAll('filter')[0])).toEqual([
      'base_model:adapter:runwayml/stable-diffusion-v1-5', 'base_model:adapter:runwayml/stable-diffusion-v1-5',
      'base_model:adapter:stable-diffusion-v1-5/stable-diffusion-v1-5',
    ])
  })

  it('turns failures into messages', async () => {
    const opts = (fetcher: FetchLike) => ({ fetcher, safe: true, assets: [] })
    await expect(searchLoras({ base: 'nothing', source: 'civitai' }, opts(async () => response({})))).rejects.toThrow('Choose the model')
    await expect(searchLoras({ base: 'sdxl', source: 'civitai' }, opts(async () => response('busy', { status: 503 })))).rejects.toThrow('HTTP 503')
    await expect(searchLoras({ base: 'sdxl', source: 'civitai' }, opts(async () => response('slow', { status: 429 })))).rejects.toThrow('too many requests')
    await expect(searchLoras({ base: 'sdxl', source: 'civitai' }, opts(async () => { throw Object.assign(new Error('t'), { name: 'TimeoutError' }) }))).rejects.toThrow('in time')
    await expect(searchLoras({ base: 'sdxl', source: 'hf' }, opts(async () => response([], { url: 'https://evil.example/x' })))).rejects.toThrow('elsewhere')
  })
})

describe('preview pictures', () => {
  beforeEach(clearSearchCache)
  const png = new Uint8Array([137, 80, 78, 71, 1, 2, 3])

  it('fetches only pictures a search handed out, as data URLs, and no adult ones when they are not allowed', async () => {
    const asked: string[] = []
    const fetcher: FetchLike = async (url) => {
      asked.push(url)
      if (url.includes('/api/')) return response({ items: [civitaiModel(1, {}, { images: [{ url: IMG, type: 'image', nsfwLevel: 1 }] }), civitaiModel(3, { nsfwLevel: 31 }, { images: [{ url: 'https://image.civitai.com/k/i/original=true/x.jpeg', type: 'image', nsfwLevel: 16 }] })] }, { url })
      return response(png, { url, headers: { 'content-type': 'image/png' } })
    }
    expect(await previewPicture(IMG.replace('original=true', 'width=320'), { fetcher, safe: true })).toBeUndefined()
    const page = await searchLoras({ base: 'sdxl', source: 'civitai' }, { fetcher, safe: false, assets: [] })
    const [safeUrl, adultUrl] = page.hits.map((h) => h.previewUrl!)
    expect(await previewPicture(safeUrl, { fetcher, safe: true })).toBe('data:image/png;base64,' + Buffer.from(png).toString('base64'))
    expect(await previewPicture(adultUrl, { fetcher, safe: true })).toBeUndefined()
    expect(await previewPicture(adultUrl, { fetcher, safe: false })).toMatch(/^data:image\/png;base64,/)
    // kept: the first picture is not fetched twice
    await previewPicture(safeUrl, { fetcher, safe: true })
    expect(asked.filter((u) => u === safeUrl)).toHaveLength(1)
  })

  it('also fetches the pictures of the other Civitai versions of a hit', async () => {
    const pony = 'https://image.civitai.com/k/p/original=true/pony.jpeg'
    const item = civitaiModel(1)
    item.modelVersions[0].images = [{ url: pony, type: 'image', nsfwLevel: 1 }] as never
    const fetcher: FetchLike = async (url) => url.includes('/api/') ? response({ items: [item] }, { url }) : response(png, { url, headers: { 'content-type': 'image/png' } })
    const page = await searchLoras({ base: 'sdxl', source: 'civitai' }, { fetcher, safe: true, assets: [] })
    const other = page.hits[0].versions!.find((v) => v.name === 'v2 for Pony')!.previewUrl!
    expect(other).toContain('pony.jpeg')
    expect(await previewPicture(other, { fetcher, safe: true })).toMatch(/^data:image\/png;base64,/)
  })

  it('refuses what is not a picture or too large', async () => {
    const page = (type: string, body: Uint8Array, headers: Record<string, string> = {}): FetchLike => async (url) =>
      url.includes('/api/') ? response({ items: [civitaiModel(1)] }, { url }) : response(body, { url, headers: { 'content-type': type, ...headers } })
    for (const fetcher of [page('text/html', png), page('image/png', png, { 'content-length': String(10 * 1024 * 1024) })]) {
      clearSearchCache()
      const hits = (await searchLoras({ base: 'sdxl', source: 'civitai' }, { fetcher, safe: true, assets: [] })).hits
      expect(await previewPicture(hits[0].previewUrl!, { fetcher, safe: true })).toBeUndefined()
    }
    expect(await readLimited(response(new Uint8Array(100)), 50)).toBeUndefined()
    expect((await readLimited(response(new Uint8Array(40)), 50))?.length).toBe(40)
  })
})
