// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The pictures of the landing page (site/, published with GitHub Pages): copies every file the pages reference under
// assets/ from build/ and docs/ into site/assets/, plus the social preview to site/social_preview.png (the absolute
// URL in the pages' Open Graph tags). The pages stay plain HTML and CSS; site/ is then complete on its own.
// Run before publishing (the Pages workflow does):  node tools/build_site.mjs
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const SITE = join(ROOT, 'site')
const ASSETS = join(SITE, 'assets')
const LANGS = ['de', 'es', 'pt-BR', 'pt-PT']

// published path below assets/ -> source file in the repository
function source(path) {
  if (path === 'icon.svg' || path === 'icon.png') return join(ROOT, 'build', path)
  if (path === 'banner.jpg') return join(ROOT, 'docs', 'images', path)
  let m = path.match(/^gallery\/([a-z0-9_]+\.jpg)$/)
  if (m) return join(ROOT, 'docs', 'images', 'gallery', m[1])
  m = path.match(/^characters\/([a-z0-9_]+\.jpg)$/)
  if (m) return join(ROOT, 'docs', 'images', 'characters', m[1])
  m = path.match(/^models\/([a-z0-9_]+\.jpg)$/)
  if (m) return join(ROOT, 'docs', 'images', 'models', m[1])
  m = path.match(/^results\/([a-z0-9_]+\.(?:jpg|mp4))$/)
  if (m) return join(ROOT, 'docs', 'images', 'results', m[1])
  m = path.match(/^pose3d\/([a-z0-9_]+\.svg)$/)
  if (m) return join(ROOT, 'docs', 'images', 'pose3d', m[1])
  m = path.match(/^icons\/([a-z0-9-]+\.svg)$/)
  if (m) return join(ROOT, 'docs', 'icons', m[1])
  m = path.match(/^screenshots\/([A-Za-z-]+)\/([a-z0-9_]+\.(?:jpg|png))$/)
  if (m && m[1] === 'en') return join(ROOT, 'docs', 'screenshots', m[2])
  if (m && LANGS.includes(m[1])) return join(ROOT, 'docs', 'screenshots', m[1], m[2])
  return null
}

function htmlFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    if (p === ASSETS) return []
    if (statSync(p).isDirectory()) return htmlFiles(p)
    return name.endsWith('.html') ? [p] : []
  })
}

const wanted = new Set()
for (const file of htmlFiles(SITE)) {
  for (const [, path] of readFileSync(file, 'utf8').matchAll(/(?:\.\.\/)?assets\/([^"'()\s?#]+)/g)) wanted.add(path)
}

const missing = []
rmSync(ASSETS, { recursive: true, force: true })
for (const path of [...wanted].sort()) {
  const from = source(path)
  if (!from || !existsSync(from)) { missing.push(path); continue }
  mkdirSync(dirname(join(ASSETS, path)), { recursive: true })
  copyFileSync(from, join(ASSETS, path))
}
copyFileSync(join(ROOT, 'docs', 'images', 'social_preview.png'), join(SITE, 'social_preview.png'))

if (missing.length) {
  console.error(`No source for: ${missing.map((p) => `assets/${p}`).join(', ')}`)
  process.exit(1)
}
console.log(`${wanted.size} files in ${relative(ROOT, ASSETS)}/, social_preview.png in site/`)
