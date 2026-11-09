// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Writes THIRD_PARTY_NOTICES.txt: the licence texts of every package that is part of the app (the libraries
// bundled into its pages and Electron), and a note on what the app downloads later and does not ship.
//
//   node tools/gen_notices.mjs

import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)))
// what ends up in the app: the libraries bundled into the pages and Electron itself
const START = ['vue', 'pinia', 'vue-router', '@lucide/vue', 'electron']

function packageDir(name, from = ROOT) {
  for (let dir = from; ; dir = dirname(dir)) {
    const candidate = join(dir, 'node_modules', name)
    if (existsSync(join(candidate, 'package.json'))) return candidate
    if (dirname(dir) === dir) return undefined
  }
}

const seen = new Map()
function visit(name, from) {
  const dir = packageDir(name, from)
  if (!dir) return
  const meta = JSON.parse(readFileSync(join(dir, 'package.json'), 'utf8'))
  const key = `${meta.name}@${meta.version}`
  if (seen.has(key)) return
  seen.set(key, { meta, dir })
  // Electron's own dependencies only download it while building; they are not part of the app
  if (meta.name === 'electron') return
  for (const dep of Object.keys(meta.dependencies ?? {})) visit(dep, dir)
}
for (const name of START) visit(name, ROOT)

function licenceText(dir) {
  const file = readdirSync(dir).find((f) => /^(licen[cs]e|copying)(\.(md|txt))?$/i.test(f))
  return file ? readFileSync(join(dir, file), 'utf8').trim() : ''
}

const parts = [
  'VulKara – third-party notices',
  '',
  'VulKara contains the following third-party packages. Their licences are reproduced below.',
  'Electron includes Chromium and Node.js; their notices are in the file LICENSES.chromium.html inside the app.',
  '',
  'Not part of the app: the Python runtimes (PyTorch, diffusers, MLX, ComfyUI and their dependencies) and all',
  'models, including the upscaling model Real-ESRGAN (BSD-3-Clause) and the face model CodeFormer (NTU S-Lab',
  'License 1.0, non-commercial use only), are downloaded by the user from their',
  'publishers when they are needed, under the licences those publishers give them. The Licenses page of the app',
  'lists the licences of the models.',
  '',
  'engines/diffusers/export_single.py follows the key maps of diffusers\' conversion scripts',
  '(convert_diffusers_to_original_stable_diffusion.py, convert_diffusers_to_original_sdxl.py), Copyright The HuggingFace',
  'Team, licensed under the Apache License 2.0: https://www.apache.org/licenses/LICENSE-2.0',
  '',
  'The icons of the EU AI label (AI GENERATED, AI MODIFIED, AI) are the European Commission\'s icons for labelling',
  'AI-generated content, made publicly available for everyone to use freely, without attribution:',
  'https://digital-strategy.ec.europa.eu/en/policies/eu-icons-labelling-ai-generated-content',
]
for (const [key, { meta, dir }] of [...seen.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
  const text = licenceText(dir)
  parts.push('', '='.repeat(78), `${key} – ${typeof meta.license === 'string' ? meta.license : 'see below'}`,
    meta.homepage ? meta.homepage : '', '-'.repeat(78), text || `Licence: ${meta.license ?? 'unknown'} (no licence file in the package)`)
}
writeFileSync(join(ROOT, 'THIRD_PARTY_NOTICES.txt'), parts.join('\n') + '\n')
console.log(`${seen.size} packages`)
