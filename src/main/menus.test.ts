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
