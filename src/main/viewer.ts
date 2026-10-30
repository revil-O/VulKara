// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The large view of pictures and videos: every view is a window of its own, so several can be open next to each
// other; back in the main window they all close (ipc.ts bindWindow). A viewer window gets the list it was opened from and may only ask for that
// list, save or reveal a file, and hand a picture back to the main window.

import { app, BrowserWindow, nativeTheme, shell, type WebContents } from 'electron'
import { PAGE_URL, PRELOAD } from './pages'
import type { ViewerPayload } from '@shared/api'

const payloads = new Map<number, ViewerPayload>()  // by the id of the window's page
const windows = new Set<BrowserWindow>()
export const isViewer = (sender: WebContents): boolean => payloads.has(sender.id)
export const viewerPayload = (sender: WebContents): ViewerPayload | undefined => payloads.get(sender.id)

export function openViewer(payload: ViewerPayload, opener?: BrowserWindow): void {
  const offset = (windows.size % 6) * 28
  // over an app in full screen a new window would take a full screen space of its own (without a title bar to
  // close it): it opens as a window over the app instead, in the same space
  const overFullScreen = !!opener && !opener.isDestroyed() && opener.isFullScreen()
  const win = new BrowserWindow({
    width: 1180, height: 820, minWidth: 640, minHeight: 420,
    ...(overFullScreen ? { parent: opener, fullscreenable: false } : {}),
    show: false,
    title: 'VulKara',
    titleBarStyle: 'hiddenInset',
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#0e0f12' : '#e9e7e2',
    webPreferences: { preload: PRELOAD, contextIsolation: true, sandbox: true, nodeIntegration: false, spellcheck: false, devTools: !app.isPackaged },
  })
  if (offset) {
    const [x, y] = win.getPosition()
    win.setPosition(x + offset, y + offset)
  }
  const id = win.webContents.id
  payloads.set(id, payload)
  windows.add(win)
  win.once('ready-to-show', () => win.show())
  win.on('closed', () => {
    payloads.delete(id)
    windows.delete(win)
  })
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) void shell.openExternal(url)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (event) => event.preventDefault())
  void win.loadURL(PAGE_URL + '#/viewer')
}

export function closeViewers(): void {
  for (const win of [...windows]) win.close()
}
