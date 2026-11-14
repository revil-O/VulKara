// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { translate } from '.'
import { engineText, matchEngine } from './engine'

// status lines as the engines write them (engines/diffusers, mlx, comfy, the importer and the trainers)
const LINES = [
  'Loading model', 'Loading model (MLX)', 'Loading model (MLX, 4 bit)', 'Loading text_encoder', 'Loading LoRA',
  'Quantizing transformer (one-time)', 'Quantizing ControlNet (one-time)', 'Preparing SSD streaming (one-time) 42%',
  'Model larger than memory: streaming it from the SSD (slow)', 'Preparing canny control image', 'Encoding prompt',
  'Generating', 'Decoding', 'Restoring face 2 of 3', 'LaMa not available (no module), filling simply',
  'Downloading ControlNet (2.5 GB, one-time) 12%', 'Downloading depth preprocessor (0.40 GB, one-time)',
  'Downloading RealESRGAN (64 MB)', 'Downloading model.safetensors', 'Checking unet.bin (one-time)', 'Copying',
  'Copying a.bin', 'Reading LoRA Tattoo', 'Taking vae.safetensors from FLUX.1-dev', 'Version v2 · newest', 'Verifying 55%',
  'Encoding 1 picture', 'Encoding 12 pictures', 'Base model in 4 bit, 12 pictures', 'Loading SDXL and encoding the pictures',
  'Starting ComfyUI', 'Converting FP8 to GGUF 3%', 'Loading the model',
  'Extended with FLUX.2 [klein] 4B and its outpaint LoRA',
  'ObjectClear kept the object: filled again without it',
  'Faces not refined: no network',
  'Outpaint LoRA not available: extended with FLUX.2 [klein] 9B',
  'FLUX.2 [klein] 9B extends less well; without LoRAs of its own, an installed FLUX.2 [klein] 4B would extend',
]

describe('engine status lines', () => {
  it('every known line is matched and rebuilt word for word in English', () => {
    for (const line of LINES) {
      const hit = matchEngine(line)
      expect(hit, line).toBeDefined()
      expect(translate('en', hit!.key, hit!.params) + hit!.percent).toBe(line)
    }
  })
  it('unknown lines and English stay as they are', () => {
    expect(engineText('de', 'something new 12%')).toBe('something new 12%')
    expect(engineText('en', 'Decoding')).toBe('Decoding')
  })
})

describe('engine status lines in German', () => {
  it('are translated with the decimal mark of the language', () => {
    expect(engineText('de', 'Downloading ControlNet (2.5 GB, one-time) 12%')).toMatch(/2,5 GB.* 12%$/)
    expect(engineText('de', 'Decoding')).not.toBe('Decoding')
  })
})
