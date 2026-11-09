// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The runtimes install a locked, tested set of packages (tools/lock_runtimes.py). An unpinned requirement would let
// any new release reach users untested, as Pillow 13 did: caught here already, not only by the release gate.
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const ENGINES = fileURLToPath(new URL('../../engines/', import.meta.url))
const PIN = /^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?==([^\s;#]+)/
const norm = (name: string): string => name.replace(/[-_.]+/g, '-').toLowerCase()

function pins(file: string): Map<string, string> {
  const out = new Map<string, string>()
  for (const raw of readFileSync(file, 'utf8').split('\n')) {
    const line = raw.trim()
    if (!line || line.startsWith('#')) continue
    const m = PIN.exec(line)
    expect(m, `${file}: "${line}" is not pinned to one version`).not.toBeNull()
    out.set(norm(m![1]), m![3])
  }
  return out
}

describe('the runtime packages', () => {
  for (const engine of ['diffusers', 'mlx', 'comfy']) {
    it(`${engine}: every requirement pinned and equal to its lock`, () => {
      const direct = pins(`${ENGINES}${engine}/requirements.txt`)
      const locked = pins(`${ENGINES}${engine}/constraints.txt`)
      expect(direct.size).toBeGreaterThan(0)
      for (const [name, version] of direct) expect(locked.get(name), `${engine}: ${name}`).toBe(version)
    })
  }

  it('keeps the MLX runtime on Pillow 13 only with mflux 0.24 or newer', () => {
    // Pillow 13.0.0 broke an import in mflux 0.23 on Python 3.11; mflux 0.24 needs Pillow 13 (MEASUREMENTS 7aj).
    // Diffusers and ComfyUI moved to 13.0.0 for its security fixes after their tests and pictures (7bj).
    const mlx = pins(`${ENGINES}mlx/constraints.txt`)
    if (Number(mlx.get('pillow')?.split('.')[0]) >= 13) {
      const [major, minor] = (mlx.get('mflux') ?? '0.0').split('.').map(Number)
      expect(major > 0 || minor >= 24).toBe(true)
    }
  })
})
