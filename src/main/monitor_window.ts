// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The monitor window (app menu and menu bar → Monitor): one window with the running job against its plan and this
// Mac's figures. It keeps its place (monitor.json) if that is still on a screen, and asks only for the stats.

import { app, BrowserWindow, nativeTheme, screen, shell, type Rectangle, type WebContents } from 'electron'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { PAGE_URL, PRELOAD } from './pages'

let win: BrowserWindow | undefined
const boundsFile = (): string => join(app.getPath('userData'), 'monitor.json')
export const isMonitor = (sender: WebContents): boolean => !!win && !win.isDestroyed() && sender === win.webContents
export const monitorContents = (): WebContents | undefined => (win && !win.isDestroyed() ? win.webContents : undefined)

function storedBounds(): Partial<Rectangle> {
  try {
    const b = JSON.parse(readFileSync(boundsFile(), 'utf8')) as Rectangle
    const area = screen.getDisplayMatching(b).workArea
    const visible = b.x < area.x + area.width - 60 && b.x + b.width > area.x + 60 && b.y >= area.y - 10 && b.y < area.y + area.height - 60
    return visible ? b : {}
  } catch {
    return {}
  }
}

export function openMonitor(): void {
  if (win && !win.isDestroyed()) {
    if (win.isMinimized()) win.restore()
    win.show()
    win.focus()
    return
  }
  const w = new BrowserWindow({
    width: 520, height: 640, minWidth: 420, minHeight: 420, ...storedBounds(),
    show: false,
    title: 'VulKara Monitor',
    titleBarStyle: 'hiddenInset',
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#14161a' : '#f4f3f0',
    webPreferences: { preload: PRELOAD, contextIsolation: true, sandbox: true, nodeIntegration: false, spellcheck: false, devTools: !app.isPackaged },
  })
  win = w
  w.once('ready-to-show', () => w.show())
  w.on('close', () => {
    try {
      writeFileSync(boundsFile(), JSON.stringify(w.getNormalBounds()))
    } catch {
      // it opens at its standard place next time
    }
  })
  w.on('closed', () => { if (win === w) win = undefined })
  w.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) void shell.openExternal(url)
    return { action: 'deny' }
  })
  w.webContents.on('will-navigate', (event) => event.preventDefault())
  void w.loadURL(PAGE_URL + '#/monitor')
}
