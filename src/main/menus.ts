// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The app menu beside the Apple menu (About, Settings…, Monitor) and the icon in the menu bar with its own menu. Edit,
// View and Window come from Electron's roles: without the Edit menu ⌘C and ⌘V stop working in every field.
// Shared with okAI-helper (LmAI-Studio src/main/menus.ts): the app's own parts come in through MenuHooks; keep both
// copies of this file the same.
import { app, Menu, nativeImage, Tray, type MenuItemConstructorOptions } from 'electron'
import { join } from 'node:path'

/** The menu texts, already in the app's language. */
export interface MenuTexts {
  about: string
  settings: string
  monitor: string
  services: string
  hide: string
  hideOthers: string
  showAll: string
  quit: string
  open: string
}

export interface MenuHooks {
  name: string
  texts: () => MenuTexts
  /** the main window (made again if it was closed), on a page of it */
  showMain: (route?: string) => void
  openMonitor: () => void
  /** the app's own lines of the menu bar menu (what runs now), built anew at each click */
  status: () => MenuItemConstructorOptions[]
}

export function appMenuTemplate(h: MenuHooks): MenuItemConstructorOptions[] {
  const t = h.texts()
  return [
    {
      label: h.name,
      submenu: [
        { label: t.about, role: 'about' },
        { type: 'separator' },
        { label: t.settings, accelerator: 'CommandOrControl+,', click: () => h.showMain('/settings') },
        { label: t.monitor, click: () => h.openMonitor() },
        { type: 'separator' },
        { label: t.services, role: 'services' },
        { type: 'separator' },
        { label: t.hide, role: 'hide' },
        { label: t.hideOthers, role: 'hideOthers' },
        { label: t.showAll, role: 'unhide' },
        { type: 'separator' },
        { label: t.quit, role: 'quit' },
      ],
    },
    { role: 'editMenu' },
    { role: 'viewMenu' },
    { role: 'windowMenu' },
  ]
}

export function trayMenuTemplate(h: MenuHooks): MenuItemConstructorOptions[] {
  const t = h.texts()
  return [
    { label: t.open, click: () => h.showMain() },
    { label: t.monitor, click: () => h.openMonitor() },
    { type: 'separator' },
    ...h.status(),
    { type: 'separator' },
    { label: t.settings, click: () => h.showMain('/settings') },
    { label: t.quit, click: () => app.quit() },
  ]
}

let tray: Tray | undefined
let hooks: MenuHooks | undefined
let shown = ''
let open = false  // a menu set while it is open would close it under the pointer

/** The menu bar menu, set on the icon (macOS opens it itself; popping one up from a click showed nothing while the
 *  app was not in front) and built anew when its texts changed. */
function refreshTray(force = false): void {
  if (!tray || !hooks || open) return
  const template = trayMenuTemplate(hooks)
  const texts = JSON.stringify(template.map((i) => i.label ?? '-'))
  if (!force && texts === shown) return
  shown = texts
  const menu = Menu.buildFromTemplate(template)
  menu.on('menu-will-show', () => { open = true })
  menu.on('menu-will-close', () => { open = false })
  tray.setContextMenu(menu)
}

/** Sets the app menu (again when the language changes) and, once, the menu bar icon from iconDir/trayTemplate.png. */
export function setMenus(h: MenuHooks, iconDir: string): void {
  hooks = h
  Menu.setApplicationMenu(Menu.buildFromTemplate(appMenuTemplate(h)))
  if (!tray) {
    // "Template" in the name: macOS colours the icon for a light or dark menu bar; @2x is taken on Retina screens
    tray = new Tray(nativeImage.createFromPath(join(iconDir, 'trayTemplate.png')))
    tray.setToolTip(h.name)
    // what runs changes while the app runs: the texts are compared every 2 s, the menu set again when they changed
    setInterval(() => refreshTray(), 2000).unref()
  }
  refreshTray(true)
}
