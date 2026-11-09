// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Renders build/icon.svg into the macOS icon set (build/icon.icns) and a 1024 px PNG (build/icon.png), and
// build/trayTemplate.svg into the menu bar icon (build/tray/trayTemplate.png, 18 px, and @2x, 36 px).
// The SVG is drawn into a canvas of a hidden page in every size the icon set needs.
//
//   npx electron tools/make_icon.mjs

import { app, BrowserWindow } from 'electron'
import { execFileSync } from 'node:child_process'
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)))
const BUILD = join(ROOT, 'build')
const SIZES = [16, 32, 64, 128, 256, 512, 1024]

/** The SVG file drawn at a size, as PNG bytes. */
async function draw(win, file, size) {
  const svg = readFileSync(join(BUILD, file), 'base64')
  const dataUrl = await win.webContents.executeJavaScript(`new Promise((resolve, reject) => {
      const img = new Image()
      img.onload = () => {
        const c = document.createElement('canvas')
        c.width = c.height = ${size}
        const ctx = c.getContext('2d')
        ctx.imageSmoothingQuality = 'high'
        ctx.drawImage(img, 0, 0, ${size}, ${size})
        resolve(c.toDataURL('image/png'))
      }
      img.onerror = () => reject(new Error('the icon could not be drawn'))
      img.src = 'data:image/svg+xml;base64,${svg}'
    })`)
  return Buffer.from(dataUrl.split(',')[1], 'base64')
}

// the work runs after the ready event: awaiting it at the top of an ES module would hold that event back
async function render() {
  const win = new BrowserWindow({ show: false })
  await win.loadURL('data:text/html,<html><body></body></html>')
  const pngs = {}
  for (const size of SIZES) pngs[size] = await draw(win, 'icon.svg', size)
  const set = join(BUILD, 'icon.iconset')
  rmSync(set, { recursive: true, force: true })
  mkdirSync(set)
  for (const size of [16, 32, 128, 256, 512]) {
    writeFileSync(join(set, `icon_${size}x${size}.png`), pngs[size])
    writeFileSync(join(set, `icon_${size}x${size}@2x.png`), pngs[size * 2])
  }
  execFileSync('iconutil', ['-c', 'icns', set, '-o', join(BUILD, 'icon.icns')])
  rmSync(set, { recursive: true, force: true })
  writeFileSync(join(BUILD, 'icon.png'), pngs[1024])
  mkdirSync(join(BUILD, 'tray'), { recursive: true })
  writeFileSync(join(BUILD, 'tray', 'trayTemplate.png'), await draw(win, 'trayTemplate.svg', 18))
  writeFileSync(join(BUILD, 'tray', 'trayTemplate@2x.png'), await draw(win, 'trayTemplate.svg', 36))
  console.log('build/icon.icns, build/icon.png and build/tray/ written')
  app.exit(0)
}

void app.whenReady().then(render)
