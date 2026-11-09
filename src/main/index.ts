// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// VulKara, main process: one window, the engines and the job queue behind it; the app menu and the menu bar icon
// (closing the window leaves VulKara running there, with its jobs).

import { app, BrowserWindow, nativeTheme, screen, systemPreferences, session, shell, type Rectangle } from 'electron'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { bindWindow, fileAccess, navigate, queueStatus, registerIpc, repairRuntimes, sendToRemote, shutdown } from './ipc'
import { remoteRunning, startRemote, stopRemote } from './remote'
import { logTo } from './log'
import { PAGE_URL, PRELOAD, RENDERER_DIR } from './pages'
import { engineEnv, getSettings, onSettingChanged } from './settings'
import { mainLanguage, setMainLang, t } from './i18n'
import { setMenus } from './menus'
import { openMonitor } from './monitor_window'
import { formatDuration } from '@shared/duration'
import { LOCALES, resolveLang } from '@shared/i18n'
import { recheckLibrary } from './migrate'
import { engineCommand } from './runtimes'
import { handleSchemes, registerSchemes } from './protocols'
import { mainWindowReady, openSplash, splashWindow } from './splash'
import { warmMacModel } from './mac_model'

registerSchemes()

// copying text (logs, trigger words) and full-screen videos; no camera, microphone, location or notifications
const PERMISSIONS = ['clipboard-sanitized-write', 'fullscreen']

const boundsFile = (): string => join(app.getPath('userData'), 'window.json')

/** Where the window was when it was closed, if that place is still on a screen. */
function storedBounds(): Partial<Rectangle> {
  try {
    const b = JSON.parse(readFileSync(boundsFile(), 'utf8')) as Rectangle
    const area = screen.getDisplayMatching(b).workArea
    const visible = b.x < area.x + area.width - 100 && b.x + b.width > area.x + 100 && b.y >= area.y - 10 && b.y < area.y + area.height - 100
    return visible && b.width >= 980 && b.height >= 640 ? b : {}
  } catch {
    return {}
  }
}

const windowBackground = (): string => (nativeTheme.shouldUseDarkColors ? '#14161a' : '#f4f3f0')

/** Light, dark or as macOS: themeSource switches prefers-color-scheme in every window, the large views too. */
function applyTheme(): void {
  nativeTheme.themeSource = getSettings().theme
  for (const w of BrowserWindow.getAllWindows()) if (!w.isDestroyed()) w.setBackgroundColor(windowBackground())
}

/** The app's language from the settings (System: macOS's), for the main process and every window. */
function applyLanguage(): void {
  const setting = getSettings().language
  const lang = resolveLang(setting, app.getPreferredSystemLanguages())
  // dates and numbers: as macOS's region with System, else those of the chosen language
  const region = setting === 'system' ? Intl.DateTimeFormat.supportedLocalesOf([app.getSystemLocale() || LOCALES[lang]])[0] : undefined
  setMainLang(lang, region ?? LOCALES[lang])
  for (const w of BrowserWindow.getAllWindows()) if (!w.isDestroyed()) w.webContents.send('i18n:lang', mainLanguage())
  if (app.isReady()) applyMenus()
}

let main: BrowserWindow | undefined

/** The main window, made again if it was closed (VulKara keeps running in the menu bar), on a page of it. */
function showMain(route?: string): void {
  if (!main || main.isDestroyed()) {
    // the page loaded directly: a message sent after loading would come before the page listens
    main = createWindow(false, false, route)
    return
  }
  if (main.webContents.isLoading()) return  // it shows itself when it is ready
  if (main.isMinimized()) main.restore()
  main.show()
  main.focus()
  if (route) navigate(route)
}

/** The app menu (in the app's language) and the menu bar icon with what runs now. */
function applyMenus(): void {
  setMenus({
    name: 'VulKara',
    texts: () => ({
      about: t('app.menu.about'), settings: t('app.menu.settings'), monitor: t('app.menu.monitor'),
      services: t('app.menu.services'), hide: t('app.menu.hide'), hideOthers: t('app.menu.hideOthers'),
      showAll: t('app.menu.showAll'), quit: t('app.menu.quit'), open: t('app.menu.open'),
    }),
    showMain,
    openMonitor,
    status: () => {
      const q = queueStatus()
      const run = q.running
      const lines = [{
        label: !run ? t('app.menu.noJob')
          : run.eta !== undefined ? t('app.menu.runningEta', { model: run.model, progress: String(Math.max(0, run.progress)), eta: formatDuration(run.eta) })
          : t('app.menu.running', { model: run.model, progress: String(Math.max(0, run.progress)) }),
        enabled: false,
      }]
      if (q.waiting) lines.push({ label: t('app.menu.waiting', { n: String(q.waiting) }), enabled: false })
      // the remote web UI stays reachable with the window closed: said here, Quit ends it
      if (remoteRunning()) lines.push({ label: t('app.menu.remoteOn'), enabled: false })
      return lines
    },
  }, app.isPackaged ? join(process.resourcesPath, 'tray') : join(app.getAppPath(), 'build', 'tray'))
}

/** The main window. behindSplash: shown once the splash is confirmed; inactive: shown without coming to the front;
 *  route: the page it opens on. */
function createWindow(behindSplash: boolean, inactive = false, route?: string): BrowserWindow {
  const win = new BrowserWindow({
    width: 1360, height: 880, ...storedBounds(), minWidth: 980, minHeight: 640,
    show: false,
    titleBarStyle: 'hiddenInset',
    trafficLightPosition: { x: 18, y: 18 },
    backgroundColor: windowBackground(),
    webPreferences: {
      preload: PRELOAD,
      contextIsolation: true, sandbox: true, nodeIntegration: false, spellcheck: false, devTools: !app.isPackaged,
    },
  })
  bindWindow(win)
  win.once('ready-to-show', () => (behindSplash ? mainWindowReady() : inactive ? win.showInactive() : win.show()))
  win.on('close', () => {
    try {
      writeFileSync(boundsFile(), JSON.stringify(win.getNormalBounds()))
    } catch {
      // the window just opens at its standard place next time
    }
  })
  // the window shows the app and nothing else: links open in the browser
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) void shell.openExternal(url)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (event, url) => {
    const [to, own] = [new URL(url), new URL(PAGE_URL)]
    if (to.protocol !== own.protocol || to.host !== own.host) event.preventDefault()
  })
  void win.loadURL(route ? `${PAGE_URL}#${route}` : PAGE_URL)
  return win
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    const splash = splashWindow()
    if (splash) splash.focus()
    else showMain()
  })

  void app.whenReady().then(async () => {
    // with "prefer tabs: always" in macOS, the splash and the viewer would open as tabs of the main window (and take
    // its size): VulKara's windows are never put into tabs by the system
    if (process.platform === 'darwin') systemPreferences.setUserDefault('AppleWindowTabbingMode', 'string', 'manual')
    handleSchemes(RENDERER_DIR, fileAccess)
    session.defaultSession.setPermissionRequestHandler((_contents, permission, grant) => grant(PERMISSIONS.includes(permission)))
    session.defaultSession.setPermissionCheckHandler((_contents, permission) => PERMISSIONS.includes(permission))
    session.defaultSession.setDevicePermissionHandler(() => false)
    void warmMacModel()
    logTo(join(app.getPath('userData'), 'logs'))
    registerIpc()
    // runtimes from an earlier version (or broken by an untested package) are brought to this version's tested set
    const repaired = repairRuntimes()
    startRemote()
    applyTheme()
    onSettingChanged((key) => { if (key === 'theme') applyTheme() })
    applyLanguage()
    onSettingChanged((key) => { if (key === 'language') applyLanguage() })
    // the VulKara icon in the Dock also when started from the sources
    const icon = join(app.getAppPath(), 'build', 'icon.png')
    if (!app.isPackaged && existsSync(icon)) app.dock?.setIcon(icon)
    // --no-splash: straight to the main window (automated runs; it keeps them from coming to the front)
    if (process.argv.includes('--no-splash')) {
      main = createWindow(false, true)
    } else {
      openSplash(windowBackground(), () => { if (main && !main.isDestroyed()) main.show() })
      main = createWindow(true)
    }
    // the Dock icon: the main window again (the monitor window may still be open)
    app.on('activate', () => { if (!splashWindow()) showMain() })
    // once, in the background (after the runtimes are whole): installed LoRAs and models checked with the current
    // detection; the pages reload the list
    void repaired.then(() => recheckLibrary(engineCommand('diffusers', ['recheck_loras']), engineEnv(), app.getPath('userData'), () => {
      for (const w of BrowserWindow.getAllWindows()) if (!w.isDestroyed()) w.webContents.send('assets:change')
      sendToRemote('assets:change')
    }))
  })

  // closing the window leaves VulKara in the menu bar with its jobs and the remote web UI; Quit (⌘Q, the menu bar menu)
  // ends it. Without this listener Electron would quit when the last window closes.
  app.on('window-all-closed', () => {})
  // sent by macOS at log out or by `kill`: quit the usual way, so will-quit stops the engines
  // a second one ends at once, the engines stopped first (a hanging quit would leave only SIGKILL)
  let terms = 0
  process.on('SIGTERM', () => {
    if (terms++ === 0) return app.quit()
    shutdown()
    app.exit(0)
  })
  app.on('will-quit', () => {
    void stopRemote()
    shutdown()
  })
}
