// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { linkRoute } from './deeplink'

describe('vulkara:// links', () => {
  it('opens Models → Add for a Hugging Face repository', () => {
    expect(linkRoute('vulkara://import/hf?repo=stable-diffusion-v1-5/stable-diffusion-v1-5')).toBe('/models?hf=stable-diffusion-v1-5%2Fstable-diffusion-v1-5')
    expect(linkRoute('vulkara://import/hf?repo=black-forest-labs/FLUX.2-klein-4B')).toBe('/models?hf=black-forest-labs%2FFLUX.2-klein-4B')
    // as the website hands it over (site/hf/hf.js encodes the slash)
    expect(linkRoute('vulkara://import/hf?repo=black-forest-labs%2FFLUX.2-klein-4B')).toBe('/models?hf=black-forest-labs%2FFLUX.2-klein-4B')
  })

  it('drops every other link', () => {
    for (const link of [
      'vulkara://import/hf', 'vulkara://import/hf?repo=', 'vulkara://import/hf?repo=onlyname', 'vulkara://import/hf?repo=a/b/c',
      'vulkara://import/hf?repo=../etc', 'vulkara://import/hf?repo=a/..', 'vulkara://import/hf?repo=a/b%0Ac', 'vulkara://import/hf?repo=a/<b>',
      'vulkara://import/civitai?repo=a/b', 'vulkara://run/hf?repo=a/b', 'https://import/hf?repo=a/b', 'file:///etc/passwd', 'not a link',
      `vulkara://import/hf?repo=a/${'b'.repeat(200)}`,
    ]) expect(linkRoute(link), link).toBeUndefined()
  })
})
