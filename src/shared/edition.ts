// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// What a build of the app offers. VulKara is published free of charge, so there is one edition with everything;
// the switches stay so that a restricted build (no ComfyUI, nudity always filtered, only commercially usable models
// recommended) remains possible without touching the pages.

export interface Edition {
  id: 'full'
  /** the processor the build is for: x64 is the Intel-Mac build (plans/INTEL_MACHBARKEIT.md) */
  arch: 'arm64' | 'x64'
  /** downloaded: the app installs the runtimes; bundled: they ship inside the app (no such build exists) */
  runtimes: 'downloaded' | 'bundled'
  comfyui: boolean
  /** the MLX runtime: Apple's library exists for Apple chips only */
  mlx: boolean
  /** choice: a setting decides whether nudity is shown; filtered: never shown */
  explicitContent: 'choice' | 'filtered'
  /** recommend only models that may be used commercially, with pictures that may be */
  commercialModelsOnly: boolean
}

// set by the build (electron.vite.config.ts) from VK_ARCH
declare const __VK_ARCH__: Edition['arch']

/** What a build for this processor offers. Intel Macs get PyTorch up to 2.2 only: no MLX, no ComfyUI, and of the
 *  recommended models only the families diffusers 0.35 runs on it. */
export function editionFor(arch: Edition['arch']): Edition {
  const intel = arch === 'x64'
  return { id: 'full', arch, runtimes: 'downloaded', comfyui: !intel, mlx: !intel, explicitContent: 'choice', commercialModelsOnly: false }
}

/** The edition of this build. */
export const EDITION: Edition = editionFor(__VK_ARCH__)

/** An engine's pin file for this build: the Intel build has its own set (engines/diffusers/*-x64.txt). */
export const pinFile = (name: 'requirements' | 'constraints'): string => `${name}${EDITION.arch === 'x64' ? '-x64' : ''}.txt`

/** The model families the Intel build recommends (FLUX and newer need torch.nn.RMSNorm, PyTorch 2.4+). */
export const INTEL_FAMILIES = ['SD 1.x', 'SD 2.x', 'SDXL']

/** May a build with commercialModelsOnly recommend a model with these licence answers (licenses.json: yes, limited, no)? */
export function commerciallyUsable(licence: { model: string; outputs: string } | undefined): boolean {
  return !!licence && licence.model !== 'no' && licence.outputs !== 'no'
}
