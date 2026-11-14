// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it, vi } from 'vitest'

const quit = vi.fn()
vi.mock('electron', () => ({ app: { quit }, Menu: {}, nativeImage: {}, Tray: class {} }))

const { appMenuTemplate, trayMenuTemplate } = await import('./menus')

const texts = {
  about: 'Über VulKara', settings: 'Einstellungen …', monitor: 'Monitor', services: 'Dienste', hide: 'VulKara ausblenden',
  hideOthers: 'Andere ausblenden', showAll: 'Alle einblenden', quit: 'VulKara beenden', open: 'VulKara öffnen',
}

function hooks() {
  return {
    name: 'VulKara', texts: () => texts, showMain: vi.fn(), openMonitor: vi.fn(),
    status: () => [{ label: 'FLUX.2-klein-4B · 40 %', enabled: false }, { label: '2 waiting', enabled: false }],
  }
}

describe('menus', () => {
  it('keeps Edit, View and Window, so ⌘C and ⌘V work in every field', () => {
    const menu = appMenuTemplate(hooks())
    expect(menu.slice(1).map((m) => m.role)).toEqual(['editMenu', 'viewMenu', 'windowMenu'])
  })

  type Item = { label?: string; role?: string; submenu?: Item[] }
  const all = (items: Item[]): Item[] => items.flatMap((i) => [i, ...all(i.submenu ?? [])])

  it('labels Edit, View and Window in the app language and keeps their roles (copy and paste stay macOS\'s)', () => {
    const h = { ...hooks(), texts: () => ({ ...texts, edit: 'Bearbeiten', window: 'Fenster', roles: { copy: 'Kopieren', paste: 'Einsetzen' } }) }
    const [, edit, , win] = appMenuTemplate(h) as Item[]
    expect(edit.label).toBe('Bearbeiten')
    expect(win).toMatchObject({ role: 'windowMenu', label: 'Fenster' })
    expect(edit.submenu!.find((i) => i.role === 'copy')!.label).toBe('Kopieren')
    expect(edit.submenu!.find((i) => i.role === 'paste')!.label).toBe('Einsetzen')
    // a role without a text keeps Electron's own label
    expect(edit.submenu!.find((i) => i.role === 'undo')!.label).toBeUndefined()
  })

  it('shows reload and the developer tools only in development', () => {
    const roles = (devTools: boolean): string[] => all(appMenuTemplate({ ...hooks(), devTools }) as Item[]).map((i) => i.role ?? '')
    expect(roles(false)).not.toContain('reload')
    expect(roles(false)).not.toContain('toggleDevTools')
    expect(roles(false)).toContain('zoomIn')
    expect(roles(true)).toEqual(expect.arrayContaining(['reload', 'forceReload', 'toggleDevTools']))
  })

  it('checks for updates from the app menu and the menu bar menu, not while one installs', () => {
    type Entry = { label?: string; enabled?: boolean; click?: () => void }
    const checkUpdate = vi.fn()
    let busy = false
    const h = { ...hooks(), texts: () => ({ ...texts, checkUpdate: 'Auf Update prüfen …' }), checkUpdate, updateBusy: () => busy }
    const find = (items: Entry[]): Entry => items.find((i) => i.label === 'Auf Update prüfen …')!
    const inApp = find(appMenuTemplate(h)[0].submenu as Entry[])
    const inTray = find(trayMenuTemplate(h) as Entry[])
    inApp.click!()
    inTray.click!()
    expect(checkUpdate).toHaveBeenCalledTimes(2)
    expect([inApp.enabled, inTray.enabled]).toEqual([true, true])
    busy = true
    expect(find(trayMenuTemplate(h) as Entry[]).enabled).toBe(false)
    // without the hook (okAI-helper's menus, tests) no entry
    expect((trayMenuTemplate(hooks()) as Entry[]).some((i) => i.label === 'Auf Update prüfen …')).toBe(false)
  })

  it('opens the settings with ⌘, and the monitor from the app menu, in the app language', () => {
    const h = hooks()
    const items = appMenuTemplate(h)[0].submenu as { label?: string; accelerator?: string; click?: () => void; role?: string }[]
    const settings = items.find((i) => i.label === 'Einstellungen …')!
    expect(settings.accelerator).toBe('CommandOrControl+,')
    settings.click!()
    expect(h.showMain).toHaveBeenCalledWith('/settings')
    items.find((i) => i.label === 'Monitor')!.click!()
    expect(h.openMonitor).toHaveBeenCalled()
    expect(items.find((i) => i.role === 'quit')!.label).toBe('VulKara beenden')
  })

  it('puts what runs into the menu bar menu, built from the hooks (no click on the icon needed)', () => {
    const h = hooks()
    const items = trayMenuTemplate(h) as { label?: string; click?: () => void }[]
    expect(items.map((i) => i.label).filter(Boolean)).toEqual(
      ['VulKara öffnen', 'Monitor', 'FLUX.2-klein-4B · 40 %', '2 waiting', 'Einstellungen …', 'VulKara beenden'])
    items[0].click!()
    expect(h.showMain).toHaveBeenCalledWith()
    items.at(-1)!.click!()
    expect(quit).toHaveBeenCalled()
  })
})
