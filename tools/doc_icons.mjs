// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The icons of the documents (README, user guide): the same Lucide icons the app shows, written as SVG files into
// docs/icons from the app's own @lucide/vue, in the app's accent colour (readable on light and dark pages).
// The documents use them instead of emoji:  node tools/doc_icons.mjs
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const ICONS = join(ROOT, 'node_modules', '@lucide', 'vue', 'dist', 'esm', 'icons')
const OUT = join(ROOT, 'docs', 'icons')
const COLOUR = '#d65a12'  // --accent of the light theme

// file name in lucide -> what it stands for in the documents (the app's page or control with this icon)
export const DOC_ICONS = {
  'sun': 'website: light appearance',
  'messages-square': 'website: the Discord community',
  'moon': 'website: dark appearance',
  'sun-moon': 'website: appearance like the system',
  'copy': 'website: copy a command',
  'gauge': 'website: the benchmark',
  'monitor': 'everything on the Mac',
  'tablet-smartphone': 'website: remote access from a phone or tablet',
  'boxes': 'Models',
  'cpu': 'engines, Hardware',
  'paintbrush': 'tools',
  'layers': 'LoRA',
  'scale': 'Licenses, responsibility',
  'hard-drive': 'SSD streaming',
  'loader-circle': 'a job in the queue',
  'memory-stick': 'memory',
  'type': 'Text',
  'images': 'Image',
  'eraser': 'Inpaint',
  'frame': 'Canvas',
  'person-standing': 'Pose',
  'sparkles': 'Illusion',
  'clapperboard': 'Video',
  'maximize-2': 'Upscale',
  'wand-sparkles': 'Restore',
  'download': 'import',
  'shield-check': 'privacy, guard rails',
  'check': 'supported',
  'x': 'remove, close',
  'aperture': 'Enhance',
  'graduation-cap': 'Training',
  'lightbulb': 'Tips',
  'file-clock': 'Changelog',
  'languages': 'language menu',
  'menu': 'the website menu on narrow screens',
  'heart': 'Favorites',
  'coffee': 'support the project',
  'scroll-text': 'Logs, wiki',
  'rotate-3d': 'website: turn a pose in 3D',
  'bone': 'website: joints of a pose',
  'bookmark': 'website: saved poses',
  'users': 'website: characters',
}

const attrs = (o) => Object.entries(o).filter(([k]) => k !== 'key').map(([k, v]) => `${k}="${v}"`).join(' ')

mkdirSync(OUT, { recursive: true })
for (const name of Object.keys(DOC_ICONS)) {
  // the icon's nodes: [["rect", { width: "20", … }], …] as lucide exports them
  const { node: nodes } = (await import(pathToFileURL(join(ICONS, `${name}.mjs`)).href)).__iconData
  const inner = nodes.map(([tag, a]) => `<${tag} ${attrs(a)}/>`).join('')
  writeFileSync(join(OUT, `${name}.svg`),
    `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="${COLOUR}" ` +
    `stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${inner}</svg>\n`)
}
console.log(`${Object.keys(DOC_ICONS).length} icons in docs/icons`)
