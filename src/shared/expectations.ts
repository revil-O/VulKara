// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// What the monitor window compares a running job with: the memory plan of the job itself (on every Mac), and on the
// Mac the measurements were made on, the measured seconds per picture and memory of the recommended models.

export type Tone = 'neutral' | 'better' | 'worse' | 'bad'

/** One measured model: its standard settings (the figures hold only for them) and what pictures 2–5 took. */
export interface Expectation {
  /** the model's folder name */
  model: string
  steps: number
  /** square size in pixels */
  size: number
  secondsPerPicture: number
  peakGb: number
  /** the section of docs/MEASUREMENTS.md */
  ref: string
}

/** Where they were measured: Hardware → Benchmark, five pictures each, the same prompt (its encoding cached). */
export const MEASURED_ON = { chip: 'Apple M4', ramGb: 16 }

export const EXPECTED: Expectation[] = [
  { model: 'DreamShaper-8', steps: 25, size: 512, secondsPerPicture: 14, peakGb: 3.79, ref: '7bs' },
  { model: 'Juggernaut-XL-v7', steps: 35, size: 1024, secondsPerPicture: 140, peakGb: 8.76, ref: '7bs' },
  { model: 'FLUX.2-klein-4B', steps: 4, size: 1024, secondsPerPicture: 51, peakGb: 6.91, ref: '7bt' },
  { model: 'Z-Image-Turbo', steps: 9, size: 1024, secondsPerPicture: 165, peakGb: 8.97, ref: '7bu' },
  { model: 'Anima-Turbo', steps: 10, size: 1024, secondsPerPicture: 64, peakGb: 10.02, ref: '7bt' },
  { model: 'SD3.5-Medium-repaired', steps: 40, size: 1024, secondsPerPicture: 327, peakGb: 5.94, ref: '7bs' },
  { model: 'FLUX-3-Image-Klein-MLX-8bit', steps: 16, size: 1024, secondsPerPicture: 217, peakGb: 10.63, ref: '7bs' },
  { model: 'Fibo-2.0-Edit-Turbo-MLX', steps: 4, size: 1024, secondsPerPicture: 128, peakGb: 11.02, ref: '7bs' },
  { model: 'ERNIE-Image-Turbo', steps: 8, size: 1024, secondsPerPicture: 238, peakGb: 8.98, ref: '7bt' },
  { model: 'FLUX.2-klein-9B', steps: 4, size: 1024, secondsPerPicture: 116, peakGb: 9.04, ref: '7bt' },
  { model: 'FLUX.1-schnell-Q8', steps: 4, size: 1024, secondsPerPicture: 122, peakGb: 8.93, ref: '7bs' },
  { model: 'NetaYume-Lumina-v4', steps: 45, size: 1024, secondsPerPicture: 683, peakGb: 9.22, ref: '7bt' },
  { model: 'GonzaLomo-Chroma', steps: 30, size: 1024, secondsPerPicture: 1617, peakGb: 9.32, ref: '7bs' },
]

/** The measurement of a job's model, only on the Mac it was made on and only at the settings it was made with. */
export function expectationFor(modelDir: string, steps: number, width: number, height: number,
  mac: { chip: string; ramGb: number } | undefined): Expectation | undefined {
  if (!mac || mac.chip !== MEASURED_ON.chip || Math.round(mac.ramGb) !== MEASURED_ON.ramGb) return undefined
  const folder = modelDir.replace(/\/+$/, '').split('/').pop() ?? ''
  return EXPECTED.find((e) => e.model === folder && e.steps === steps && e.size === width && e.size === height)
}

/**
 * How far a live figure is from what was expected, in percent of it (rounded; never "-0"). Within 10 % it is neutral
 * (the target of the measurements: memory at most 10 % over the plan); lower is better for time and memory, beyond
 * 10 % under it; over it 10-25 % is worse, more is bad. Shared with okAI-helper (LmAI-Studio src/shared/expectations.ts
 * delta) apart from these limits.
 */
export function delta(live: number, expected: number): { pct: number; tone: Tone } {
  const pct = expected > 0 ? Math.round(((live - expected) / expected) * 100) || 0 : 0
  if (Math.abs(pct) <= 10) return { pct, tone: 'neutral' }
  if (pct < 0) return { pct, tone: 'better' }
  return { pct, tone: pct > 25 ? 'bad' : 'worse' }
}
