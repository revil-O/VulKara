// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { cachedInfo, fetchInfo, fromCivitai, fromModelCard, htmlToParagraphs, infoSource, markdownToParagraphs, newerVersions, strengthInPrompt } from './lora_info'

const MODEL = {
  id: 637096, name: 'Tattoo Maker XL', creator: { username: 'maker' }, tags: ['style', 'tattoo'], allowCommercialUse: ['Image', 'Rent'],
  description: '<p>Based on my <a href="https://x">original</a> model.</p><ul><li>Use &quot;monochrome&quot;</li><li>Weight 0.8&nbsp;&amp; up</li></ul><script>alert(1)</script>',
}
const VERSION = {
  id: 712356, modelId: 637096, name: 'V1', baseModel: 'SDXL 1.0', trainedWords: ['proto_tat', ' tattoo_style '],
  description: '<p>Add the term monochrome.</p>', trainingDetails: { type: 'Style', params: { clipSkip: 1 } },
  images: [
    { nsfwLevel: 1, meta: { prompt: 'a swallow <lora:tattoo:0.8>, ink', negativePrompt: 'blurry', steps: 30, cfgScale: 6, sampler: 'DPM++ 2M', seed: 5 } },
    { nsfwLevel: 2, meta: { prompt: 'a rose <lora:tattoo:1>', steps: 20, cfgScale: 7, sampler: 'DPM++ 2M' } },
    { nsfwLevel: 8, meta: { prompt: 'adult <lora:tattoo:1.2>', steps: 40, cfgScale: 9, sampler: 'Euler' } },
    { nsfwLevel: 1, meta: null },
  ],
}

describe('lora info', () => {
  it('turns HTML and Markdown into plain paragraphs', () => {
    expect(htmlToParagraphs(MODEL.description)).toEqual(['Based on my original model.', '• Use "monochrome"', '• Weight 0.8 & up'])
    expect(htmlToParagraphs('a&#39;b &#x41; &unknown;<br/>c')).toEqual(["a'b A &unknown;", 'c'])
    expect(markdownToParagraphs('---\nlicense: mit\n---\n# Title\n![x](y.png)\nSome **bold** [link](http://x).\n- item\n| a | b |\n```\ncode\n```')).toEqual(['Title', 'Some bold link.', '• item'])
  })

  it('reads description, words and recommended settings from Civitai', () => {
    const info = fromCivitai(MODEL, VERSION, false)
    expect(info).toMatchObject({
      source: 'civitai', page: 'https://civitai.com/models/637096?modelVersionId=712356', name: 'Tattoo Maker XL', version: 'V1', creator: 'maker',
      kind: 'style', baseModel: 'SDXL 1.0', trainedWords: ['proto_tat', 'tattoo_style'], versionNotes: ['Add the term monochrome.'], commercialUse: ['Image', 'Rent'],
    })
    expect(info.recommended).toMatchObject({ strength: 1, minStrength: 0.8, maxStrength: 1.2, fromMakers: false, steps: 30, guidance: 7, sampler: 'DPM++ 2M', clipSkip: 1, examples: 3 })
    expect(info.examples[0]).toMatchObject({ prompt: 'a swallow, ink', negative: 'blurry', strength: 0.8, seed: 5 })
    expect(strengthInPrompt('x <lora:a:0.65> y')).toBe(0.65)
  })

  it('leaves adult examples out in safe mode and prefers what the makers set', () => {
    const info = fromCivitai(MODEL, { ...VERSION, settings: { strength: 0.7, minStrength: 0.5, maxStrength: 0.9 } }, true)
    expect(info.examples.map((e) => e.prompt)).toEqual(['a swallow, ink', 'a rose'])
    expect(info.recommended).toMatchObject({ strength: 0.7, minStrength: 0.5, maxStrength: 0.9, fromMakers: true, examples: 2 })
  })

  it('reads a Hugging Face model card', () => {
    const card = '---\nlicense: apache-2.0\nbase_model: black-forest-labs/FLUX.1-dev\ntags:\n- lora\n- style\ninstance_prompt: zqx style\nwidget:\n- text: "a castle in zqx style"\n---\n# Zqx\nA style LoRA.'
    expect(fromModelCard('someone/zqx-lora', card)).toMatchObject({
      source: 'huggingface', page: 'https://huggingface.co/someone/zqx-lora', creator: 'someone', kind: 'style', baseModel: 'black-forest-labs/FLUX.1-dev',
      trainedWords: ['zqx style'], description: ['Zqx', 'A style LoRA.'], licence: 'apache-2.0', examples: [{ prompt: 'a castle in zqx style' }],
    })
  })

  it('knows where to look and keeps what it found', async () => {
    expect(infoSource({ source: { type: 'file' }, civitai: { model_id: 1, version_id: 2 } })).toEqual({ civitai: { modelId: 1, versionId: 2 } })
    expect(infoSource({ source: { type: 'hf', ref: 'a/b' } })).toEqual({ huggingface: 'a/b' })
    expect(infoSource({ source: { type: 'file', ref: '/x.safetensors' } })).toEqual({})

    const folder = mkdtempSync(join(tmpdir(), 'vk-info-'))
    writeFileSync(join(folder, 'lora.json'), JSON.stringify({ source: { type: 'civitai', model_id: 637096, version_id: 712356 } }))
    const asked: [string, Record<string, string>][] = []
    const info = await fetchInfo(folder, async (url, headers) => {
      asked.push([url, headers])
      return JSON.stringify(url.includes('model-versions') ? VERSION : MODEL)
    }, { civitai: 'secret' }, false)
    expect(asked.map((a) => a[0])).toEqual(['https://civitai.com/api/v1/model-versions/712356', 'https://civitai.com/api/v1/models/637096'])
    expect(asked[0][1]).toEqual({ Authorization: 'Bearer secret' })
    expect(info?.name).toBe('Tattoo Maker XL')
    expect(cachedInfo(folder)?.name).toBe('Tattoo Maker XL')

    const unknown = mkdtempSync(join(tmpdir(), 'vk-info-'))
    writeFileSync(join(unknown, 'lora.json'), JSON.stringify({ source: { type: 'file' } }))
    expect(await fetchInfo(unknown, async () => '{}', {}, false)).toBeUndefined()
    expect(cachedInfo(unknown)).toBeUndefined()
  })
})

describe('newer versions on Civitai', () => {
  const file = (name: string) => ({ name, metadata: { format: name.endsWith('.safetensors') ? 'SafeTensor' : 'PickleTensor' } })
  const model = { modelVersions: [
    { id: 4, name: 'v4', baseModel: 'SDXL 1.0', publishedAt: '2026-11-20T10:00:00Z', files: [file('a.safetensors')] },
    { id: 3, name: 'v3 Pony', baseModel: 'Pony', files: [file('b.safetensors')] },
    { id: 2, name: 'v2 pickle', baseModel: 'SDXL 1.0', files: [file('c.pt')] },
    { id: 1, name: 'v1', baseModel: 'SDXL 1.0', files: [file('d.safetensors')] },
  ] }
  it('lists the newer ones for the same base with a SafeTensor file, and none for the newest', () => {
    expect(newerVersions(model, { id: 1, baseModel: 'SDXL 1.0' }, 9)).toEqual([
      { name: 'v4', ref: 'https://civitai.com/models/9?modelVersionId=4', baseModel: 'SDXL 1.0', date: '2026-11-20' },
    ])
    expect(newerVersions(model, { id: 4, baseModel: 'SDXL 1.0' }, 9)).toEqual([])
    expect(newerVersions(model, { id: 99 }, 9)).toEqual([])
  })
})
