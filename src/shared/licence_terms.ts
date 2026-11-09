// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The licences models come with, by the id Hugging Face uses for them, and what each allows commercially
// (model = commercial use of the model, outputs = of the pictures). The same terms as tools/gen_licenses.py.

import { translate, type PlainKey } from './i18n'

export type Allowed = 'yes' | 'limited' | 'no' | 'unknown'

export interface LicenceTerms {
  name: string
  url: string
  model: Allowed
  outputs: Allowed
  note: string
}

// the notes in English, as the main process keeps them with a model; the pages show them in the app's language
const NOTES = {
  openrail: 'app.licenses.terms.openrail',
  openrailPlain: 'app.licenses.terms.openrailPlain',
  credit: 'app.licenses.terms.credit',
  nonCommercial: 'app.licenses.terms.nonCommercial',
  modelNonCommercial: 'app.licenses.terms.modelNonCommercial',
  stability: 'app.licenses.terms.stability',
  circlestone: 'app.licenses.terms.circlestone',
  ideogram: 'app.licenses.terms.ideogram',
  qwen: 'app.licenses.terms.qwen',
  krea: 'app.licenses.terms.krea',
  fluxKommunity: 'app.licenses.terms.fluxKommunity',
  pony: 'app.licenses.terms.pony',
} as const satisfies Record<string, PlainKey>
const note = (name: keyof typeof NOTES): string => translate('en', NOTES[name])

/** The key of one of the notes, by its English text (as kept with a model), else undefined. */
export const licenceNoteKey = (text: string): PlainKey | undefined => Object.values(NOTES).find((k) => translate('en', k) === text)

export const TERMS: Record<string, LicenceTerms> = {
  'creativeml-openrail-m': { name: 'CreativeML Open RAIL-M', url: 'https://huggingface.co/spaces/CompVis/stable-diffusion-license', model: 'yes', outputs: 'yes', note: note('openrail') },
  'openrail++': { name: 'CreativeML Open RAIL++-M', url: 'https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/blob/main/LICENSE.md', model: 'yes', outputs: 'yes', note: note('openrail') },
  openrail: { name: 'OpenRAIL', url: 'https://huggingface.co/blog/open_rail', model: 'yes', outputs: 'yes', note: note('openrailPlain') },
  'bsd-3-clause': { name: 'BSD 3-Clause License', url: 'https://opensource.org/license/bsd-3-clause', model: 'yes', outputs: 'yes', note: '' },
  mit: { name: 'MIT License', url: 'https://opensource.org/license/mit', model: 'yes', outputs: 'yes', note: '' },
  'apache-2.0': { name: 'Apache License 2.0', url: 'https://www.apache.org/licenses/LICENSE-2.0', model: 'yes', outputs: 'yes', note: '' },
  'cc-by-4.0': { name: 'Creative Commons Attribution 4.0', url: 'https://creativecommons.org/licenses/by/4.0/', model: 'yes', outputs: 'yes', note: note('credit') },
  'cc-by-nc-4.0': { name: 'Creative Commons Attribution-NonCommercial 4.0', url: 'https://creativecommons.org/licenses/by-nc/4.0/', model: 'no', outputs: 'no', note: note('nonCommercial') },
  'cc-by-nc-sa-4.0': { name: 'Creative Commons Attribution-NonCommercial-ShareAlike 4.0', url: 'https://creativecommons.org/licenses/by-nc-sa/4.0/', model: 'no', outputs: 'no', note: note('nonCommercial') },
  'flux-1-dev-non-commercial-license': { name: 'FLUX.1 [dev] Non-Commercial License', url: 'https://github.com/black-forest-labs/flux/blob/main/model_licenses/LICENSE-FLUX1-dev', model: 'no', outputs: 'yes', note: note('modelNonCommercial') },
  'flux-non-commercial-license': { name: 'FLUX Non-Commercial License', url: 'https://github.com/black-forest-labs/flux2/blob/main/model_licenses/LICENSE-FLUX-NON-COMMERICAL', model: 'no', outputs: 'yes', note: note('modelNonCommercial') },
  'stabilityai-ai-community': { name: 'Stability AI Community License', url: 'https://stability.ai/community-license-agreement', model: 'limited', outputs: 'limited', note: note('stability') },
  'sai-nc-community': { name: 'Stability AI Community License', url: 'https://stability.ai/community-license-agreement', model: 'limited', outputs: 'limited', note: note('stability') },
  'circlestone-labs-non-commercial-license': { name: 'CircleStone Labs Non-Commercial License', url: 'https://huggingface.co/circlestone-labs/Anima/blob/main/LICENSE.md', model: 'no', outputs: 'yes', note: note('circlestone') },
  'ideogram-4-non-commercial': { name: 'Ideogram Non-Commercial Model Agreement', url: 'https://huggingface.co/ideogram-ai/ideogram-4-fp8/blob/main/LICENSE.md', model: 'no', outputs: 'no', note: note('ideogram') },
  'qwen-research': { name: 'Qwen Research License Agreement', url: 'https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE', model: 'no', outputs: 'no', note: note('qwen') },
  'flux-kommunity-license': { name: 'FLUX Kommunity License v1.0', url: 'https://huggingface.co/black-forest-labs/flux-3-image-klein/blob/main/LICENSE.md', model: 'no', outputs: 'limited', note: note('fluxKommunity') },
  'pony-license': { name: 'Pony License', url: 'https://huggingface.co/purplesmartai/pony-v7-base/blob/main/LICENSE', model: 'limited', outputs: 'limited', note: note('pony') },
  'krea-2-community-license': { name: 'Krea 2 Community License', url: 'https://www.krea.ai/krea-2-use-policy', model: 'limited', outputs: 'limited', note: note('krea') },
}

const RANK: Record<Allowed, number> = { no: 0, limited: 1, unknown: 2, yes: 3 }

/** The stricter of two answers: a fine-tune may not allow more than its base model. */
export function stricter(a: Allowed, b: Allowed): Allowed {
  return RANK[a] <= RANK[b] ? a : b
}

/**
 * The licence of the base model a model or LoRA builds on, from its family and architecture, or from the base
 * model its page names (Civitai: "Flux.1 D", "SDXL 1.0" …). Undefined when it can not be told.
 */
export function baseLicence(family: string, arch = '', pageBase = ''): { title: string; terms: LicenceTerms } | undefined {
  const base = pageBase.toLowerCase()
  const is = (...words: string[]): boolean => words.some((w) => base.includes(w))
  switch (family) {
    case 'sd1': return { title: 'Stable Diffusion 1.5', terms: TERMS['creativeml-openrail-m'] }
    case 'sd2': return { title: 'Stable Diffusion 2.x', terms: TERMS['openrail++'] }
    case 'sdxl': return { title: 'Stable Diffusion XL', terms: TERMS['openrail++'] }
    case 'sd3': return { title: 'Stable Diffusion 3.5', terms: TERMS['stabilityai-ai-community'] }
    case 'flux1':
      if (arch === 'flux1_schnell' || is('flux.1 s', 'schnell')) return { title: 'FLUX.1 [schnell]', terms: TERMS['apache-2.0'] }
      if (arch === 'flux1_dev' || is('flux.1 d', 'dev', 'krea')) return { title: 'FLUX.1 [dev]', terms: TERMS['flux-1-dev-non-commercial-license'] }
      return undefined
    case 'chroma': return { title: 'Chroma', terms: TERMS['apache-2.0'] }
    case 'flux2':
      if (is('9b') || arch === 'flux2_dev' || is('flux.2 d')) return { title: 'FLUX.2 [klein] 9B / [dev]', terms: TERMS['flux-non-commercial-license'] }
      if (is('4b')) return { title: 'FLUX.2 [klein] 4B', terms: TERMS['apache-2.0'] }
      return undefined
    case 'flux3': return { title: 'FLUX 3 Image Klein', terms: TERMS['flux-kommunity-license'] }
    case 'krea2': return { title: 'Krea 2', terms: TERMS['krea-2-community-license'] }
    case 'anima': return { title: 'Anima', terms: TERMS['circlestone-labs-non-commercial-license'] }
    case 'lumina': return { title: 'Lumina 2', terms: TERMS['apache-2.0'] }
    case 'ernie': return { title: 'ERNIE-Image', terms: TERMS['apache-2.0'] }
    case 'moss_image': return { title: 'MOSS-Image', terms: TERMS['apache-2.0'] }
    case 'fibo2': return { title: 'Fibo 2.0', terms: TERMS['cc-by-nc-4.0'] }
    case 'auraflow': return is('pony') ? { title: 'Pony V7', terms: TERMS['pony-license'] } : { title: 'AuraFlow', terms: TERMS['apache-2.0'] }
    case 'ideogram4': return { title: 'Ideogram 4', terms: TERMS['ideogram-4-non-commercial'] }
    case 'wan': return { title: 'Wan 2.2', terms: TERMS['apache-2.0'] }
    case 'qwen_image': return { title: 'Qwen-Image', terms: TERMS['apache-2.0'] }
    case 'qwen_image21': return { title: 'Qwen-Image 2.1', terms: TERMS['qwen-research'] }
    case 'z_image': return { title: 'Z-Image', terms: TERMS['apache-2.0'] }
    default: return undefined
  }
}
