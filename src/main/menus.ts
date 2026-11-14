// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The app menu beside the Apple menu (About, Settings…, Monitor) and the icon in the menu bar with its own menu. Edit,
// View and Window are Electron's role menus written out: without the Edit menu ⌘C and ⌘V stop working in every field.
// Electron's labels for them are English only; on macOS a role item takes only label and accelerator from us
// (electronjs.org/docs/latest/tutorial/menus), so the roles keep working under translated labels.
// Shared byte for byte by VulKara (vulkara/src/main/menus.ts) and okAI-helper (LmAI-Studio src/main/menus.ts): change
// both alike. Each app passes its texts through texts() and its own menu bar lines through status().
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
  /** "Check for Update…": app menu and menu bar menu, when the hook is there */
  checkUpdate?: string
  /** Edit, View and Window and their entries by role (undo, copy, zoomIn …); missing ones keep Electron's English */
  edit?: string
  view?: string
  window?: string
  substitutions?: string
  speech?: string
  roles?: Partial<Record<string, string>>
}

export interface MenuHooks {
  name: string
  texts: () => MenuTexts
  /** the main window (made again if it was closed), on a page of it */
  showMain: (route?: string) => void
  openMonitor: () => void
  /** the app's own lines of the menu bar menu (what runs now), built anew at each click */
  status: () => MenuItemConstructorOptions[]
  /** looks for a newer VulKara now and shows the answer (Changelog page); updateBusy: while one installs */
  checkUpdate?: () => void
  updateBusy?: () => boolean
  /** Reload and the developer tools in the View menu (development only: a reload drops what is typed or painted) */
  devTools?: boolean
}

export function appMenuTemplate(h: MenuHooks): MenuItemConstructorOptions[] {
  const t = h.texts()
  type Role = NonNullable<MenuItemConstructorOptions['role']>
  const r = (role: Role): MenuItemConstructorOptions => (t.roles?.[role] ? { role, label: t.roles[role] } : { role })
  const sep: MenuItemConstructorOptions = { type: 'separator' }
  return [
    {
      label: h.name,
      submenu: [
        { label: t.about, role: 'about' },
        ...updateItem(h, t),
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
    // the same entries as Electron's editMenu, viewMenu and windowMenu (lib/browser/api/menu-item-roles.ts, macOS)
    {
      role: 'editMenu', label: t.edit ?? 'Edit', submenu: [
        r('undo'), r('redo'), sep, r('cut'), r('copy'), r('paste'), r('pasteAndMatchStyle'), r('delete'), r('selectAll'), sep,
        { label: t.substitutions ?? 'Substitutions', submenu: [r('showSubstitutions'), sep, r('toggleSmartQuotes'), r('toggleSmartDashes'), r('toggleTextReplacement')] },
        { label: t.speech ?? 'Speech', submenu: [r('startSpeaking'), r('stopSpeaking')] },
      ],
    },
    {
      role: 'viewMenu', label: t.view ?? 'View', submenu: [
        ...(h.devTools ? [r('reload'), r('forceReload'), r('toggleDevTools'), sep] : []),
        r('resetZoom'), r('zoomIn'), r('zoomOut'), sep, r('togglefullscreen'),
      ],
    },
    // the role keeps it the Window menu macOS lists the open windows in
    { role: 'windowMenu', label: t.window ?? 'Window', submenu: [r('minimize'), r('zoom'), sep, r('front')] },
  ]
}

function updateItem(h: MenuHooks, t: MenuTexts): MenuItemConstructorOptions[] {
  const check = h.checkUpdate
  return check && t.checkUpdate ? [{ label: t.checkUpdate, enabled: !h.updateBusy?.(), click: () => check() }] : []
}

export function trayMenuTemplate(h: MenuHooks): MenuItemConstructorOptions[] {
  const t = h.texts()
  return [
    { label: t.open, click: () => h.showMain() },
    { label: t.monitor, click: () => h.openMonitor() },
    ...updateItem(h, t),
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
let appBusy = false  // the update state the app menu was built with

/** The menu bar menu, set on the icon (macOS opens it itself; popping one up from a click showed nothing while the
 *  app was not in front) and built anew when its texts changed. */
function refreshTray(force = false): void {
  if (!tray || !hooks || open) return
  const template = trayMenuTemplate(hooks)
  const texts = JSON.stringify(template.map((i) => [i.label ?? '-', i.enabled !== false]))
  if (!force && texts === shown) return
  shown = texts
  const menu = Menu.buildFromTemplate(template)
  menu.on('menu-will-show', () => { open = true })
  menu.on('menu-will-close', () => { open = false })
  tray.setContextMenu(menu)
}

/** Closes the menu bar menu if it is open: while it is, AppKit's menu loop holds the main process (timers, child
 *  process exits) and a quit waits for it (seen with the same menu in okAI-helper on the Mac mini). */
export function closeTrayMenu(): void {
  if (open) tray?.closeContextMenu()
}

function setAppMenu(): void {
  if (!hooks) return
  appBusy = !!hooks.updateBusy?.()
  Menu.setApplicationMenu(Menu.buildFromTemplate(appMenuTemplate(hooks)))
}

/** Sets the app menu (again when the language changes) and, once, the menu bar icon from iconDir/trayTemplate.png. */
export function setMenus(h: MenuHooks, iconDir: string): void {
  hooks = h
  setAppMenu()
  if (!tray) {
    // "Template" in the name: macOS colours the icon for a light or dark menu bar; @2x is taken on Retina screens
    tray = new Tray(nativeImage.createFromPath(join(iconDir, 'trayTemplate.png')))
    tray.setToolTip(h.name)
    // what runs changes while the app runs: the texts are compared every 2 s, the menu set again when they changed
    setInterval(() => {
      refreshTray()
      // "Check for Update…" off while one installs: the app menu is built anew when that changes
      if (!!hooks?.updateBusy?.() !== appBusy) setAppMenu()
    }, 2000).unref()
  }
  refreshTray(true)
}
