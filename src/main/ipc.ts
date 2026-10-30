// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// What the pages can ask of the main process (src/shared/api.ts, exposed by the preload script as window.vk).

import { app, BrowserWindow, clipboard, ClipboardItem, dialog, ipcMain, nativeImage, net, powerSaveBlocker, ShareMenu, shell, type IpcMainInvokeEvent } from 'electron'
import { type ChildProcess, execFile } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { copyFileSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { basename, dirname, extname, isAbsolute, join } from 'node:path'
import { totalmem } from 'node:os'
import { describeMac, macModel } from './mac_model'
import { dataDir, enginesDir, isInside } from './paths'
import { isMedia } from './protocols'
import { REMOTE_CHANNELS, REMOTE_EVENTS } from './remote_channels'
import { adoptFolder, listAssets, removeAsset, setDisplayName, titleOfFolder } from './assets'
import { foreignRefusalOf, reimportRequest } from './foreign_mac'
import { anyEngineInstalled, dispatch, forgetMlxRefusals, guard, stopEngines, stopJob, unloadEngines } from './engines'
import { History } from './history'
import { FileAccess } from './file_access'
import { unlabelledOf } from './unlabelled'
import { ImportQueue, processRunner, publicRef } from './imports'
import { PhotoSelector, installedTools, recommendedTools } from './photo_tools'
import { listHelpers } from './helpers'
import { SystemMonitor, hardwareInfo, treeFootprintGb } from './system_stats'
import { Benchmarks } from './benchmark'
import { currentSession, log, logFolder, logLines, logOutput, onLog } from './log'
import { hiddenSummary, redact } from './log_redact'
import { listSessions, machineContext, readSession, sessionStart, stamp } from './log_sessions'
import { issueUrl } from '@shared/report'
import { cachedLicence, fetchLicence, setOrigin } from './licence_info'
import { cachedInfo, fetchInfo } from './lora_info'
import { loraDetails, setCategory, setTriggerWords } from './loras'
import { previewPicture, searchLoras, type FetchLike } from './lora_search'
import { detectPose, findFaces } from './pose'
import { Trainer, folderImages } from './training'
import { JobQueue } from './queue'
import { runTool } from './tool_process'
import { dirSize, engineCommand, installRuntime, listRuntimes, removeRuntime, staleRuntimes, updateTargets, type RuntimeId } from './runtimes'
import { AUTO_INTERVAL, UpdateChecker } from './runtime_updates'
import { AppUpdater } from './app_update'
import { getToken, hasToken, setToken, type TokenService } from './secrets'
import { closeViewers, isViewer, openViewer, viewerPayload } from './viewer'
import { confirmSplash, isSplash, splashState } from './splash'
import { engineLine, mainLanguage, t } from './i18n'
import { engineEnv, getSettings, helpersDir, historyDir, imagesDir, isValidSetting, modelsDir, settableByPage, lorasDir, onSettingChanged, setSetting } from './settings'
import type { LoraSearchRequest } from '@shared/lora_bases'
import type { ImportJob, ImportRequest, QueueSnapshot, TrainingRequest, ViewerAction, ViewerItem } from '@shared/api'
import { FOLDER_KEYS, type FolderKey, type Settings } from '@shared/settings'
import type { Job } from '@shared/types'

let win: BrowserWindow | undefined

/** where the pose editor's skeletons go (files:writePose): pictures that show no person */
const posesDir = (): string => join(dataDir(), 'inputs', 'poses')

function send(channel: string, ...args: unknown[]): void {
  if (win && !win.isDestroyed()) win.webContents.send(channel, ...args)
  if (REMOTE_EVENTS.has(channel)) for (const fn of remoteListeners) fn(channel, args)
}

/** An event that main's own code sends to every window by itself: the browsers of the remote web UI hear it too. */
export function sendToRemote(channel: string, ...args: unknown[]): void {
  if (REMOTE_EVENTS.has(channel)) for (const fn of remoteListeners) fn(channel, args)
}

// the remote web UI (remote.ts): the handlers it may call by channel, and who hears what the pages hear
const remoteHandlers = new Map<string, (...args: unknown[]) => unknown>()
const remoteListeners = new Set<(channel: string, args: unknown[]) => void>()

/** The bridge as the remote web UI sees it: only the channels of remote.ts's list, the same events as the pages. */
export const remoteBridge = {
  call(channel: string, args: unknown[]): Promise<unknown> {
    const fn = remoteHandlers.get(channel)
    if (!fn) return Promise.reject(new Error('not allowed'))
    return Promise.resolve().then(() => fn(...args))
  },
  subscribe(fn: (channel: string, args: unknown[]) => void): () => void {
    remoteListeners.add(fn)
    return () => remoteListeners.delete(fn)
  },
}

// snapshots at most every 100 ms: an engine reports progress far more often than a page needs it
let snapshotTimer: NodeJS.Timeout | undefined
const snapshot = (): QueueSnapshot => ({ jobs: queue.snapshot(), engineReady: anyEngineInstalled() })

const queue: JobQueue<RuntimeId> = new JobQueue<RuntimeId>({
  dispatch: (job, listener) => dispatch('generate', job, listener),
  stop: stopJob,
  check: (path, model, label) => guard.check(path, { safeMode: !getSettings().allowExplicit, model, label }),
  // skeletons of the pose editor (written by files:writePose only) show no person
  generated: (path) => isInside(path, posesDir()),
  // a fresh result the filter did not pass leaves the pictures folder too (also when the filter could not run)
  discard: (path) => { if (isInside(path, imagesDir())) rmSync(path, { force: true }) },
  log,
  now: Date.now,
  finished: (job, results, timing) => {
    // a preview of Restore (a part of the photo) is shown on its page only
    if (job.restore?.preview) return
    history.add(job, results, Date.now(), timing)
    if (results.length && !getSettings().firstPictureMade) setSetting('firstPictureMade', true)
    if (getSettings().notifySound && !queue.snapshot().some((j) => j.state === 'waiting')) doneSound()
  },
  changed: () => {
    watchIdle()
    snapshotTimer ??= setTimeout(() => {
      snapshotTimer = undefined
      benchmarks.observe(queue.snapshot(), Date.now())
      send('queue:change', snapshot())
    }, 100)
  },
})

// benchmarks of single models (Hardware page): measured from the queue's snapshots and the monitor's samples
const benchmarks = new Benchmarks(() => join(dataDir(), 'benchmarks.json'), (runs) => send('benchmark:change', runs),
  `${app.getVersion()} ${__VK_BUILD__}`, () => t('main.status.starting'))

// the engines free their models after a while without a job (Settings → Engine): the memory goes back to the other
// programs; the next job loads its model again
let idleTimer: NodeJS.Timeout | undefined
function watchIdle(restart = false): void {
  const minutes = getSettings().idleUnloadMinutes
  if (restart || busy() || !minutes) {
    clearTimeout(idleTimer)
    idleTimer = undefined
  }
  // restart: armed also while busy, it looks again when it fires
  if (!minutes || (busy() && !restart)) return
  idleTimer ??= setTimeout(() => {
    idleTimer = undefined
    // an import or training is not a queue change that would arm the timer again when it ends: wait another round
    if (busy()) return watchIdle(true)
    log(`[app] ${minutes} min without a job: the engines free their models`)
    unloadEngines()
  }, minutes * 60_000)
}
onSettingChanged((key) => { if (key === 'idleUnloadMinutes') watchIdle(true) })

// one sound when the last waiting job is done, not one for every picture of a series
function doneSound(): void {
  execFile('/usr/bin/afplay', ['/System/Library/Sounds/Glass.aiff'], () => {})
}

const TOKEN_HOSTS = ['civitai.com', 'huggingface.co']

/** The text of a page on Civitai or Hugging Face, undefined when it does not exist. lora: the page of a LoRA (else a
 * model's licence page), for errors. */
async function fetchPage(url: string, headers: Record<string, string>, lora: boolean): Promise<string | undefined> {
  // an access token goes to the sites it belongs to and nowhere else, not along a redirect either
  const withToken = TOKEN_HOSTS.includes(new URL(url).hostname)
  let res = await net.fetch(url, { headers: withToken ? headers : {}, redirect: withToken ? 'manual' : 'follow' })
  const to = res.status >= 300 && res.status < 400 ? res.headers.get('location') : null
  if (to) {
    const next = new URL(to, url)
    if (next.protocol !== 'https:') throw new Error(t(lora ? 'main.fetch.loraMoved' : 'main.fetch.licenceMoved'))
    res = await net.fetch(next.toString(), { headers: next.hostname === new URL(url).hostname ? headers : {} })
  }
  if (res.status === 404) return undefined
  if (res.status === 401 || res.status === 403) throw new Error(t(lora ? 'main.fetch.loraToken' : 'main.fetch.licenceToken'))
  if (!res.ok) throw new Error(t(lora ? 'main.fetch.loraHttp' : 'main.fetch.licenceHttp', { status: res.status }))
  return res.text()
}

const history = new History(historyDir, () => send('history:change'))

// which pictures the pages may see (vk-file://) or hand to a job: the app's folders, the history's files and what
// the user chose or dropped (file_access.ts)
export const fileAccess = new FileAccess(
  () => [imagesDir(), modelsDir(), lorasDir(), helpersDir(), dataDir()],
  () => join(dataDir(), 'granted-files.json'),
  (path) => history.hasFile(path),
)

// CPU, memory and the streaming caches for the status bar and the Hardware page
const monitor = new SystemMonitor({
  modelsDir, streamCacheDir: () => getSettings().streamCacheDir,
  send: (stats) => {
    send('system:stats', stats)
    if (benchmarks.running) void treeFootprintGb(process.pid).then((gb) => benchmarks.sample(stats, gb || undefined))
    else benchmarks.sample(stats)
  },
})
onSettingChanged((key) => { if (key === 'modelsDir' || key === 'streamCacheDir') monitor.refreshStorage() })

// selecting objects with a photo tool: one process, kept while the page is used
const selector = new PhotoSelector(() => engineCommand('diffusers', ['photo_select']), engineEnv, (chunk) => logOutput('photo select', chunk))

// what a browser (remote web UI) imports and sees of the imports: downloads only, no file or folder of the Mac
const WEB_SOURCES = ['hf', 'civitai']
const isWeb = (job: ImportJob): boolean => WEB_SOURCES.includes(job.request.source)
const webJobs = (jobs: ImportJob[]): ImportJob[] => jobs.filter(isWeb)

const imports = new ImportQueue(
  processRunner(
    (args) => engineCommand('diffusers', args),
    () => {
      // the tokens go to the importer only, in its environment
      const env: Record<string, string> = { ...engineEnv() }
      const hf = getToken('huggingface')
      const civitai = getToken('civitai')
      if (hf) env.HF_TOKEN = hf
      if (civitai) env.CIVITAI_TOKEN = civitai
      return env
    },
    (chunk) => logOutput('import', chunk),
  ),
  () => {
    const jobs = imports.list()
    if (win && !win.isDestroyed()) win.webContents.send('imports:change', jobs)
    sendToRemote('imports:change', webJobs(jobs))
  },
  (result) => {
    try {
      if (typeof result.model_path === 'string') adoptFolder(result.model_path)
    } catch (err) {
      log(`[import] the model could not be linked into the models folder: ${(err as Error).message}`)
    }
    send('assets:change')
    // the preview picture from the source passes the content filter like a result (safe mode included)
    const preview = typeof result.model_path === 'string' ? join(result.model_path, 'preview.jpg') : ''
    if (preview && existsSync(preview)) {
      void guard.check(preview, { safeMode: !getSettings().allowExplicit, model: '', preview: true }).then((v) => {
        if (v.ok) return
        rmSync(preview, { force: true })
        log(`[import] the preview picture was removed: ${v.reason ?? 'the content filter did not pass it'}`)
        send('assets:change')
      })
    }
  },
)

// the Mac must not go to sleep in the middle of a training
let awake: number | undefined

const trainer = new Trainer({
  command: (arch, jobFile) => engineCommand(arch === 'sdxl' ? 'diffusers' : 'mlx', ['train', jobFile]),
  env: engineEnv,
  workDir: () => join(dataDir(), 'training'),
  lorasDir,
  prepare: unloadEngines,
  changed: (state) => {
    if (state.running && awake === undefined) awake = powerSaveBlocker.start('prevent-app-suspension')
    if (!state.running && awake !== undefined) {
      powerSaveBlocker.stop(awake)
      awake = undefined
    }
    send('training:change', state)
  },
  installed: () => send('assets:change'),
  // the pictures a LoRA learns from pass the content filter like results (they are only read, never removed)
  check: (path) => guard.check(path, { safeMode: !getSettings().allowExplicit, model: '', keep: true }),
  checked: () => guard.stop(),
  log: (chunk) => logOutput('training', chunk),
})

// generating, importing and training all run on the runtimes' Python
const busy = (): boolean => queue.busy || imports.busy || trainer.running

const installing = new Set<RuntimeId>()
const lastStage: Partial<Record<RuntimeId, string>> = {}
const installError: Partial<Record<RuntimeId, string>> = {}

/** Install or update a runtime (Settings → Runtimes, and the repair at the start), with its progress on the pages. */
async function runInstall(id: RuntimeId): Promise<{ version: string }> {
  if (installing.has(id)) throw new Error(t('main.runtimes.installingAlready'))
  installing.add(id)
  delete installError[id]
  delete lastStage[id]
  try {
    if (busy()) throw new Error(t('main.runtimes.busyInstall'))
    stopEngines()
    selector.stop()
    forgetMlxRefusals()
    const res = await installRuntime(id, (stage, percent) => {
      if (stage !== lastStage[id]) log(`[runtime ${id}] ${stage}`)
      lastStage[id] = stage
      send('runtimes:progress', id, stage, percent)
    })
    send('queue:change', snapshot())
    return res
  } catch (err) {
    installError[id] = (err as Error).message
    throw err
  } finally {
    installing.delete(id)
    send('runtimes:progress', id, '', 100)  // over: the pages read the list again
    send('runtimes:updatesChanged', runtimeUpdates().status())
  }
}

/** At the start: every installed runtime that is not the tested set of this app version (installed by an earlier one,
 *  or broken by an untested package release) is brought to it, before a job can use it. Usually seconds (cache). */
export async function repairRuntimes(): Promise<void> {
  for (const id of staleRuntimes()) {
    log(`[runtime ${id}] not the tested package set of this version: brought to it`)
    try {
      await runInstall(id)
    } catch (err) {
      log(`[runtime ${id}] repair failed: ${(err as Error).message}`)  // shown in Settings → Runtimes; Update tries again
    }
  }
}
// a model being written as one file (assets:exportSingle): it holds the memory, so no job starts meanwhile
let exporting: ChildProcess | undefined

// newer versions of the runtimes' key packages: public PyPI and GitHub lists, no token is sent
let updateChecker: UpdateChecker | undefined
const runtimeUpdates = (): UpdateChecker => (updateChecker ??= new UpdateChecker({
  fetcher: (url, init) => net.fetch(url, { ...init, headers: { ...(init?.headers as Record<string, string>), 'User-Agent': 'VulKara' } }),
  targets: updateTargets,
  file: join(dataDir(), 'runtime-updates.json'),
  log,
}))

// the app's own update: the newest release on GitHub (app_update.ts)
let appUpdater: AppUpdater | undefined
const appUpdate = (): AppUpdater => (appUpdater ??= new AppUpdater({
  fetcher: (url, init) => net.fetch(url, { ...init, headers: { ...(init?.headers as Record<string, string>), 'User-Agent': 'VulKara' } }),
  current: app.getVersion(),
  exe: app.getPath('exe'),
  packaged: app.isPackaged,
  pid: process.pid,
  args: process.argv.slice(1),
  changed: (s) => send('app:updateChanged', s),
  log,
}))

/** Once a day, a few seconds after the start and then on the hour, while nothing is generated or installed (the
 *  runtimes); the app's own release list once a day too, whenever. */
function scheduleUpdateChecks(): void {
  const tick = (): void => {
    const own = appUpdate().status()
    // a failed look (offline at the start) is tried again within the hour
    const again = own.checkError ? 55 * 60 * 1000 : AUTO_INTERVAL
    if (getSettings().updateChecks && (!own.checkedAt || Date.now() - own.checkedAt >= again)) void appUpdate().check()
    const checker = runtimeUpdates()
    if (!getSettings().updateChecks || !checker.olderThan(AUTO_INTERVAL) || busy() || installing.size) return
    checker.check(true).then((u) => send('runtimes:updatesChanged', u), () => undefined)
  }
  setTimeout(tick, 8000).unref()
  setInterval(tick, 60 * 60 * 1000).unref()
}

// what a viewer window may ask for; everything else is for the main window only
// every window asks for the app's language (i18n:lang) before it shows its page
const VIEWER_CHANNELS = new Set(['viewer:payload', 'viewer:act', 'files:saveAs', 'files:reveal', 'files:share', 'files:copyImage', 'i18n:lang'])
const SPLASH_CHANNELS = new Set(['splash:state', 'splash:confirm', 'app:info', 'i18n:lang'])

type Handler = (...args: never[]) => unknown
/** A handler that wants to know which window asked. */
type SenderHandler = (event: IpcMainInvokeEvent, ...args: never[]) => unknown

function handleFrom(channel: string, fn: SenderHandler): void {
  ipcMain.handle(channel, (event: IpcMainInvokeEvent, ...args: unknown[]) => {
    // only the app's own pages, not a frame something loaded into them
    const fromMain = !!win && event.sender === win.webContents
    const fromViewer = VIEWER_CHANNELS.has(channel) && isViewer(event.sender)
    const fromSplash = SPLASH_CHANNELS.has(channel) && isSplash(event.sender)
    if (!(fromMain || fromViewer || fromSplash) || event.senderFrame !== event.sender.mainFrame) throw new Error('not allowed')
    return (fn as (e: IpcMainInvokeEvent, ...a: unknown[]) => unknown)(event, ...args)
  })
}

function handle(channel: string, fn: Handler): void {
  handleFrom(channel, (_event, ...args) => (fn as (...a: unknown[]) => unknown)(...args))
  if (REMOTE_CHANNELS.has(channel)) remoteHandlers.set(channel, fn as (...a: unknown[]) => unknown)
}

export function registerIpc(): void {
  ipcMain.on('files:dropped', (event, path: unknown) => {
    // synchronous, so the picture can be shown right after; only the main window's own page
    if (win && event.sender === win.webContents && event.senderFrame === event.sender.mainFrame && typeof path === 'string' && isMedia(path)) {
      fileAccess.grantFile(path)
    }
    event.returnValue = true
  })
  // pictures made before the flag existed count as well
  if (!getSettings().firstPictureMade && history.list({ limit: 1 }).total > 0) setSetting('firstPictureMade', true)
  handle('settings:get', () => getSettings())
  handle('i18n:lang', () => mainLanguage())
  const applySetting = (key: keyof Settings, value: Settings[keyof Settings]): void => {
    if (!isValidSetting(key, value)) throw new Error(t('main.settings.invalidValue', { key: String(key) }))
    if (key === 'runtimesDir' && (installing.size || busy())) throw new Error(t('main.settings.runtimesFolderBusy'))
    // the history moves along to a new folder that has none yet
    if (key === 'historyDir') history.relocate(String(value) || join(dataDir(), 'history'))
    setSetting(key, value)
  }
  handle('settings:set', (key: keyof Settings, value: Settings[keyof Settings]) => {
    // a folder decides where Python runs from and what is loaded: a page may only return it to the default,
    // a new one is chosen by the user in the dialog of settings:chooseFolder
    if (!settableByPage(key, value)) throw new Error(t('main.settings.chooseFolders'))
    applySetting(key, value)
  })
  handle('settings:chooseFolder', async (key: FolderKey) => {
    if (!win || !(FOLDER_KEYS as readonly string[]).includes(key)) return undefined
    if (key === 'runtimesDir' && (installing.size || busy())) throw new Error(t('main.settings.runtimesFolderBusy'))
    const current = getSettings()[key]
    const res = await dialog.showOpenDialog(win, {
      properties: ['openDirectory', 'createDirectory'], ...(current ? { defaultPath: current } : {}),
    })
    if (res.canceled || !res.filePaths[0]) return undefined
    applySetting(key, res.filePaths[0])
    return res.filePaths[0]
  })
  onSettingChanged((key) => {
    if (key === 'historyDir') history.reload()
  })

  handle('tokens:set', (service: TokenService, token: string) => setToken(service, String(token)))
  handle('tokens:has', (service: TokenService) => hasToken(service))

  handle('runtimes:list', () => listRuntimes().map((r) => ({
    ...r, installing: installing.has(r.id) ? lastStage[r.id] ?? t('main.status.starting') : undefined, error: installError[r.id],
  })))
  handle('runtimes:install', (id: RuntimeId) => runInstall(id))
  handle('runtimes:remove', (id: RuntimeId) => {
    if (installing.has(id)) throw new Error(t('main.runtimes.beingInstalled'))
    if (busy()) throw new Error(t('main.runtimes.busyRemove'))
    stopEngines()
    selector.stop()
    forgetMlxRefusals()
    removeRuntime(id)
    send('queue:change', snapshot())
    send('runtimes:updatesChanged', runtimeUpdates().status())
  })
  handle('runtimes:updates', () => runtimeUpdates().status())
  // the engines' prompt cache (prompt_cache.py): its size, and emptied on request
  const promptCache = (): string => join(dataDir(), 'prompt_cache')
  handle('app:promptCache', () => dirSize(promptCache()))
  handle('app:clearPromptCache', () => rmSync(promptCache(), { recursive: true, force: true }))
  handle('app:update', () => appUpdate().status())
  handle('app:checkUpdate', () => appUpdate().check())
  handle('app:installUpdate', () => {
    if (busy() || installing.size) throw new Error(t('main.appUpdate.busy'))
    // a job queued while the update downloaded finishes first; the new version starts after the quit
    const quitWhenIdle = (): void => { if (busy() || installing.size) setTimeout(quitWhenIdle, 2000); else app.quit() }
    void appUpdate().install(quitWhenIdle)
  })
  handle('runtimes:checkUpdates', async (force: boolean) => {
    const checker = runtimeUpdates()
    const pending = checker.check(force === true)
    send('runtimes:updatesChanged', checker.status())  // checking
    const result = await pending
    send('runtimes:updatesChanged', result)
    return result
  })
  scheduleUpdateChecks()

  const addJob = (job: Omit<Job, 'id'>, count?: number): string[] => {
    if (trainer.running) throw new Error(t('main.queue.training'))
    if (installing.size) throw new Error(t('main.queue.installing'))
    if (exporting) throw new Error(t('main.queue.exporting'))
    if (!job || typeof job !== 'object' || typeof job.modelDir !== 'string' || (job.prompt !== undefined && typeof job.prompt !== 'string'))
      throw new Error(t('main.queue.incomplete'))
    // without the content filter no result could be shown: the job does not start
    if (!engineCommand('diffusers', ['content_check']))
      throw new Error(t('main.queue.needsFilter'))
    // a model copied from another Mac: what its import decided there does not hold here (foreign_mac.ts)
    const foreign = foreignRefusalOf(job.modelDir)
    if (foreign) throw new Error(foreign)
    fileAccess.check(job.inputImage)
    // a labelled result used as an input again: its picture without the label (unlabelled.ts)
    const clean = job.inputImage ? unlabelledOf(job.inputImage) : undefined
    if (clean && fileAccess.allows(clean)) job = { ...job, inputImage: clean }
    fileAccess.check(job.maskImage, 'mask')
    fileAccess.check(job.controlnet?.image, 'control')
    fileAccess.check(job.photoTool?.mask, 'selection')
    return queue.add(job, count)
  }
  handle('queue:add', (job: Omit<Job, 'id'>, count?: number) => {
    // the app quits for its update as soon as the queue is empty
    if (appUpdater?.status().stage === 'restarting') throw new Error(t('main.appUpdate.restarting'))
    return addJob(job, count)
  })
  handle('benchmark:start', (job: Omit<Job, 'id'>, count: number, model: string) => {
    const run = { ...job, page: 'benchmark' }
    const ids = addJob(run, count)
    benchmarks.track(ids, run, String(model ?? '').slice(0, 200), Date.now())
    return ids
  })
  handle('benchmark:list', () => benchmarks.list())
  handle('benchmark:clear', () => benchmarks.clear())
  handle('queue:cancel', (id: string) => {
    // stopping a picture of a benchmark stops the whole benchmark (the pictures waiting after it first)
    for (const other of benchmarks.together(String(id))) queue.cancel(other)
    queue.cancel(String(id))
  })
  handle('queue:clearFinished', () => queue.clearFinished())
  handle('queue:snapshot', () => snapshot())

  handle('assets:list', () => listAssets())
  handle('assets:rename', (id: string, title: string) => {
    setDisplayName(String(id), String(title ?? ''))
    send('assets:change')
  })
  // a model in folder layout written as one original-layout checkpoint (engines/diffusers/export_single.py)
  handle('assets:exportSingle', async (modelId: string) => {
    if (exporting) throw new Error(t('main.assets.exportingAlready'))
    if (installing.size) throw new Error(t('main.assets.exportInstalling'))
    if (busy()) throw new Error(t('main.assets.exportBusy'))
    const model = listAssets().find((a) => a.type === 'model' && a.id === String(modelId))
    if (!model?.meta.exportable) throw new Error(t('main.assets.notExportable'))
    const owner = BrowserWindow.getFocusedWindow() ?? win
    const res = owner
      ? await dialog.showSaveDialog(owner, { defaultPath: `${model.title.replace(/[/\\:]/g, '_')}.safetensors`, filters: [{ name: t('main.dialogs.checkpoint'), extensions: ['safetensors'] }] })
      : { canceled: true, filePath: '' }
    if (res.canceled || !res.filePath) return ''
    if (exporting || installing.size || busy()) throw new Error(t('main.assets.exportStarted'))
    const out = res.filePath
    const command = engineCommand('diffusers', ['export_single', model.folder, out])
    if (!command) throw new Error(t('main.assets.exportNeedsDiffusers'))
    let error = ''
    const end = await runTool(command, engineEnv(), (tag, payload) => {
      if (tag === '__progress__') send('assets:exportProgress', engineLine(String(payload.stage ?? '')), Number(payload.progress ?? -1))
      else if (tag === '__error__') error = String(payload.error ?? '')
    }, (proc) => { exporting = proc }).finally(() => { exporting = undefined })
    if (end.code !== 0) throw new Error(error || end.stderr.trim().split('\n').slice(-3).join('\n') || `exit code ${end.code}`)
    log(`exported ${model.title} as one file: ${out}`)
    return out
  })

  // LoRAs baked into a new model (engines/diffusers/merge.py), run by the import queue like an import
  handle('assets:bake', (modelId: string, loras: { id: string; scale: number }[], name: string) => {
    if (installing.size) throw new Error(t('main.assets.bakeInstalling'))
    if (queue.busy) throw new Error(t('main.assets.bakeBusy'))
    const all = listAssets()
    const model = all.find((a) => a.type === 'model' && a.id === String(modelId))
    if (!model) throw new Error(t('main.assets.bakeChooseModel'))
    const foreign = foreignRefusalOf(model.folder)
    if (foreign) throw new Error(foreign)
    const chosen = (Array.isArray(loras) ? loras : []).map((l) => ({ asset: all.find((a) => a.type === 'lora' && a.id === String(l?.id)), scale: Number(l?.scale) }))
      .filter((l) => l.asset && Number.isFinite(l.scale) && l.scale !== 0)
    if (!chosen.length) throw new Error(t('main.assets.bakeChooseLora'))
    const title = String(name ?? '').trim() || `${model.title} + ${chosen.map((l) => l.asset!.title).join(' + ')}`
    const dir = join(dataDir(), 'merges')
    mkdirSync(dir, { recursive: true })
    const spec = join(dir, `${randomUUID()}.json`)
    writeFileSync(spec, JSON.stringify({ model: model.folder, name: title, loras: chosen.map((l) => ({ path: l.asset!.folder, scale: l.scale })) }))
    unloadEngines()  // the merge holds the whole model in memory
    return imports.add({ source: 'merge', ref: spec, name: title, quant: 'auto' }, t('main.assets.baking', { title }))
  })
  handle('assets:remove', async (id: string) => {
    if (queue.busy) throw new Error(t('main.assets.removeBusy'))
    stopEngines()  // an engine may hold files of the model open
    await removeAsset(String(id), (path) => shell.trashItem(path))
    send('assets:change')
  })
  // a model imported on another Mac and copied here (foreign_mac.ts): checked first (a dry run), then its folder goes
  // to the Trash and it is imported again from its source under the same name (removed first: the names would collide)
  const reimporting = new Set<string>()
  handle('assets:reimport', async (id: string) => {
    if (queue.busy) throw new Error(t('main.assets.reimportBusy'))
    if (installing.size) throw new Error(t('main.assets.importInstalling'))
    const model = listAssets().find((a) => a.type === 'model' && a.id === String(id))
    if (!model) throw new Error(t('main.assets.notInstalled'))
    if (!model.meta.foreignMac) throw new Error(t('main.assets.importedHere', { title: model.title }))
    if (reimporting.has(model.id) || imports.list().some((j) => ['waiting', 'running'].includes(j.state) && [model.name, basename(model.folder)].includes(j.request.name ?? '')))
      throw new Error(t('main.assets.importingAlready', { title: model.title }))
    let manifest: Record<string, unknown>
    try {
      manifest = JSON.parse(readFileSync(join(model.folder, 'model.json'), 'utf8')) as Record<string, unknown>
    } catch {
      throw new Error(t('main.assets.modelJsonUnreadable'))
    }
    const source = reimportRequest(manifest, model.folder)
    if (!source) throw new Error(t('main.assets.originalGone', { title: model.title }))
    // imported under the name of the folder that goes to the Trash, so the new folder takes its place (the importer
    // names it as importer.safe_name does); a folder of that name that is another model's is refused before anything goes
    const name = basename(model.folder)
    const target = join(dirname(model.folder), name.replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^[._]+|[._]+$/g, ''))
    if (target !== model.folder && existsSync(target))
      throw new Error(t('main.assets.folderTaken', { folder: basename(target), title: model.title }))
    const req = { ...source, name }
    reimporting.add(model.id)
    try {
      const info = await imports.inspect(req)  // a dry run: nothing is removed for an import that could not be made
      if (info.fits === false) {
        throw new Error(t('main.assets.tooLittleRam', { title: model.title, need: info.minRamGb ?? '?', have: macModel().ramGb }))
      }
      if (queue.busy || installing.size) throw new Error(t('main.assets.reimportStarted'))
      stopEngines()  // an engine may hold files of the model open
      await removeAsset(model.id, (path) => shell.trashItem(path))
      send('assets:change')
      log(`[import] ${model.title} was imported on another Mac: moved to the Trash, imported again from its source (${req.source})`)
      return imports.add(req, t('main.assets.importedAgain', { title: model.title }))
    } finally {
      reimporting.delete(model.id)
    }
  })

  // not 'toolfile' or 'merge': the app starts those itself (its file dialog, assets:bake with its checks)
  const SOURCES = ['hf', 'civitai', 'file', 'dir', 'tool', 'helper']
  const QUANTS = ['auto', 'none', 'q8', 'q4']
  const text = (v: unknown): string | undefined => (typeof v === 'string' && v.trim()) || undefined
  const checked = (req: ImportRequest): ImportRequest => {
    const ref = publicRef(text(req?.ref) ?? '')
    if (!ref || !SOURCES.includes(req.source)) throw new Error(t('main.imports.sayWhat'))
    return {
      source: req.source, ref, file: text(req.file), name: text(req.name),
      quant: req.quant && QUANTS.includes(req.quant) ? req.quant : getSettings().defaultQuant, force: req.force === true,
    }
  }
  handle('imports:inspect', (req: ImportRequest) => imports.inspect(checked(req)))
  handle('imports:add', (req: ImportRequest, title: string) => {
    if (installing.size) throw new Error(t('main.assets.importInstalling'))
    const clean = checked(req)
    return imports.add(clean, publicRef(String(title || clean.ref)))
  })
  handle('imports:cancel', (id: string) => imports.cancel(String(id)))

  // what the Mac is doing
  monitor.start()
  handle('system:stats', () => monitor.current)
  handle('system:hardware', () => hardwareInfo())

  // helper models (Models → Installed → Helper models)
  handle('helpers:list', () => listHelpers(enginesDir(), helpersDir()))
  handle('helpers:install', (id: string) => {
    if (installing.size) throw new Error(t('main.helpers.installing'))
    const h = listHelpers(enginesDir(), helpersDir()).find((x) => x.id === id)
    if (!h) throw new Error(t('main.helpers.unknown'))
    return imports.add({ source: 'helper', ref: h.id, quant: 'auto' }, h.name)
  })
  handle('helpers:remove', async (id: string) => {
    const h = listHelpers(enginesDir(), helpersDir()).find((x) => x.id === id)
    if (!h) throw new Error(t('main.helpers.unknown'))
    if (h.required) throw new Error(t('main.helpers.required'))
    if (busy() || installing.size) throw new Error(t('main.helpers.busy'))
    if (!isInside(h.folder, helpersDir()) || !existsSync(h.folder)) return
    // an engine may hold it: they start again with the next job
    stopEngines()
    selector.stop()
    await shell.trashItem(h.folder)
  })

  // photo tools (Enhance page)
  const toolsDir = (): string => join(helpersDir(), 'photo_tools')
  handle('tools:list', () => ({ installed: installedTools(toolsDir()), recommended: recommendedTools(enginesDir(), toolsDir()) }))
  handle('tools:install', (id: string) => {
    if (installing.size) throw new Error(t('main.tools.installing'))
    const tool = recommendedTools(enginesDir(), toolsDir()).find((r) => r.id === id)
    if (!tool) throw new Error(t('main.tools.unknown'))
    return imports.add({ source: 'tool', ref: tool.id, quant: 'auto' }, tool.name)
  })
  handle('tools:importFile', async () => {
    if (!win) return undefined
    if (installing.size) throw new Error(t('main.assets.importInstalling'))
    const res = await dialog.showOpenDialog(win, {
      properties: ['openFile'], filters: [{ name: t('main.dialogs.photoModels'), extensions: ['pth', 'pt', 'safetensors', 'onnx'] }],
    })
    if (res.canceled || !res.filePaths[0]) return undefined
    return imports.add({ source: 'toolfile', ref: res.filePaths[0], quant: 'auto' }, basename(res.filePaths[0]))
  })
  handle('tools:remove', async (folder: string) => {
    if (queue.busy) throw new Error(t('main.tools.removeBusy'))
    if (!isInside(String(folder), toolsDir()) || !existsSync(join(String(folder), 'tool.json'))) throw new Error(t('main.tools.notATool'))
    selector.stop()
    await shell.trashItem(String(folder))
  })
  handle('tools:select', (tool: string, image: string, points: [number, number, number][]) => {
    if (!isInside(String(tool), toolsDir())) throw new Error(t('main.tools.notATool'))
    if (typeof image !== 'string' || !isAbsolute(image) || !isMedia(image)) throw new Error(t('main.files.choosePicture'))
    fileAccess.check(image)
    const clicks = (Array.isArray(points) ? points : []).slice(0, 64)
      .filter((p) => Array.isArray(p) && p.length === 3 && p.every((v) => Number.isFinite(Number(v))))
      .map((p) => [Number(p[0]), Number(p[1]), Number(p[2]) ? 1 : 0] as [number, number, number])
    return selector.select(String(tool), image, clicks)
  })
  handle('imports:clearFinished', () => imports.clearFinished())
  handle('imports:list', () => imports.list())
  // a browser imports from the web only: a file or folder named by it would be one of the Mac's
  remoteHandlers.set('imports:list', () => webJobs(imports.list()))
  for (const channel of ['imports:inspect', 'imports:add']) {
    const local = remoteHandlers.get(channel)!
    remoteHandlers.set(channel, (req, ...rest) => {
      if (!WEB_SOURCES.includes((req as ImportRequest | undefined)?.source ?? '')) throw new Error('not allowed')
      return local(req, ...rest)
    })
  }
  remoteHandlers.set('imports:cancel', (id) => {
    if (imports.list().some((j) => j.id === String(id) && isWeb(j))) imports.cancel(String(id))
  })
  remoteHandlers.set('imports:clearFinished', () => imports.clearFinished(isWeb))

  handle('history:list', (opts: { query?: string; offset?: number; limit?: number; favorites?: boolean }) => {
    if (!opts?.query?.trim()) return history.list(opts ?? {})
    const assets = listAssets()
    return history.list(opts, (folder) => titleOfFolder(folder, assets))
  })
  handle('history:remove', async (ids: string[], trashFiles: boolean) => {
    const files = history.remove(Array.isArray(ids) ? ids.map(String) : [])
    if (trashFiles) {
      for (const f of files) {
        if (!isMedia(f) || !existsSync(f)) continue
        await shell.trashItem(f).catch(() => undefined)
        const clean = unlabelledOf(f)  // its copy without the label goes too
        if (clean) await shell.trashItem(clean).catch(() => undefined)
      }
    }
  })
  handle('history:favorite', (id: string, file: string, on: boolean) => {
    if (typeof id !== 'string' || typeof file !== 'string' || typeof on !== 'boolean') throw new Error('not a favourite')
    if (!history.favorite(id, file, on)) throw new Error(t('main.files.notInHistory'))
  })
  handle('history:favorites', () => history.favorites())

  // a question with two answers as a macOS sheet on the window: true for the first (yes), false for the second
  handle('dialog:ask', async (message: string, yes: string, no: string, detail?: string) => {
    if (!win) return false
    const res = await dialog.showMessageBox(win, {
      type: 'question', message: String(message), detail: detail ? String(detail) : undefined,
      buttons: [String(yes), String(no)], defaultId: 1, cancelId: 1, noLink: true,
    })
    return res.response === 0
  })
  handle('files:choose', async (kind: 'image' | 'folder' | 'model') => {
    if (!win) return undefined
    const filter = kind === 'model'
      ? { name: t('main.dialogs.models'), extensions: ['safetensors', 'gguf', 'ckpt'] }
      : { name: t('main.dialogs.pictures'), extensions: ['png', 'jpg', 'jpeg', 'webp', 'bmp'] }
    const res = await dialog.showOpenDialog(win, kind === 'folder'
      ? { properties: ['openDirectory', 'createDirectory'] }
      : { properties: ['openFile'], filters: [filter] })
    if (res.canceled || !res.filePaths[0]) return undefined
    // what the user chose here, the pages may show and use (file_access.ts)
    if (kind === 'folder') fileAccess.grantFolder(res.filePaths[0])
    else if (kind === 'image') fileAccess.grantFile(res.filePaths[0])
    return res.filePaths[0]
  })
  handleFrom('files:saveAs', async (event, path: string, suggestedName: string) => {
    const owner = BrowserWindow.fromWebContents(event.sender)
    if (!owner || typeof path !== 'string' || !isMedia(path) || !existsSync(path) || !fileAccess.allows(path)) return false
    const ext = extname(path).slice(1)
    const res = await dialog.showSaveDialog(owner, { defaultPath: String(suggestedName ?? ''), filters: [{ name: ext.toUpperCase(), extensions: [ext] }] })
    if (res.canceled || !res.filePath) return false
    copyFileSync(path, res.filePath)
    return true
  })
  // a picture a page made (a mask, a drawing) as PNG; the pose editor's skeletons go into a folder of their own, so
  // that the consent question knows they show no person
  const writePng = (dataUrl: string, folder: string): string => {
    // a canvas of 8192 × 8192 is far below this
    if (typeof dataUrl !== 'string' || dataUrl.length > 300 * 1024 ** 2) throw new Error(t('main.files.tooLarge'))
    const m = /^data:image\/png;base64,([A-Za-z0-9+/=]+)$/.exec(dataUrl)
    if (!m) throw new Error('not a PNG picture')
    mkdirSync(folder, { recursive: true })
    const path = join(folder, randomUUID() + '.png')
    writeFileSync(path, Buffer.from(m[1], 'base64'))
    return path
  }
  handle('files:writeImage', (dataUrl: string) => writePng(dataUrl, join(dataDir(), 'inputs')))
  handle('files:writePose', (dataUrl: string) => writePng(dataUrl, posesDir()))
  handle('files:reveal', (path: string) => {
    if (typeof path === 'string' && isAbsolute(path) && existsSync(path) && fileAccess.allows(path)) shell.showItemInFolder(path)
  })
  // a result to Mail, Messages, AirDrop and every app that offers itself in macOS's share menu (WhatsApp, Telegram, …)
  handleFrom('files:share', (event, path: string) => {
    const owner = BrowserWindow.fromWebContents(event.sender)
    if (!owner || typeof path !== 'string' || !isMedia(path) || !existsSync(path) || !fileAccess.allows(path)) return false
    new ShareMenu({ filePaths: [path] }).popup({ window: owner })
    return true
  })
  // the picture itself on the clipboard, to paste into any app (Signal, Threema, a mail being written, …)
  handle('files:copyImage', async (path: string) => {
    if (typeof path !== 'string' || !isMedia(path) || !existsSync(path) || !fileAccess.allows(path)) return false
    const image = nativeImage.createFromPath(path)
    if (image.isEmpty()) return false  // a video: the share menu takes it, the clipboard does not
    await clipboard.write([new ClipboardItem({ 'image/png': new Blob([image.toPNG()], { type: 'image/png' }) })])
    return true
  })

  handle('viewer:open', (items: ViewerItem[], index: number) => {
    if (!Array.isArray(items) || !items.length) return
    // the index is the shown picture's place in the list as the page sent it
    const wanted = items[Math.floor(Number(index) || 0)]
    const valid = items.filter((i) => i && typeof i.file === 'string' && i.job)
    let at = Math.max(0, valid.indexOf(wanted))
    // at most 5000 pictures, around the shown one
    const from = Math.max(0, Math.min(at - 2500, valid.length - 5000))
    at -= from
    const list = valid.slice(from, from + 5000)
    if (!list.length) return
    openViewer({ items: list, index: at }, win)
  })
  handleFrom('viewer:payload', (event) => viewerPayload(event.sender))
  handle('viewer:act', (action: ViewerAction) => {
    if (!win || win.isDestroyed() || !['reuse', 'continue'].includes(action?.type)) return
    send('viewer:action', action)
    if (win.isMinimized()) win.restore()
    win.focus()
  })

  const installedAsset = (id: string) => {
    const asset = listAssets().find((a) => a.id === id)
    if (!asset) throw new Error(t('main.assets.notInstalled'))
    return { folder: asset.folder, manifest: asset.type === 'model' ? 'model.json' : 'lora.json' }
  }
  const loraFolder = (id: string): string => {
    const asset = listAssets().find((a) => a.id === id && a.type === 'lora')
    if (!asset) throw new Error(t('main.assets.loraNotInstalled'))
    return asset.folder
  }
  const tokens = () => ({ civitai: getToken('civitai'), huggingface: getToken('huggingface') })
  handle('licences:get', async (id: string, refresh?: boolean) => {
    const { folder, manifest } = installedAsset(String(id))
    const cached = cachedLicence(folder)
    if (cached && !refresh) return cached
    return readLicence(folder, manifest)
  })
  handle('licences:setOrigin', async (id: string, link: string) => {
    const { folder, manifest } = installedAsset(String(id))
    if (!setOrigin(folder, manifest, String(link ?? ''))) throw new Error(t('main.fetch.enterLink'))
    return readLicence(folder, manifest)
  })
  const readLicence = (folder: string, manifest: string) =>
    fetchLicence(folder, manifest, (url, headers) => fetchPage(url, headers, false), tokens(), getSettings().hashLookups)
  handle('loras:details', (id: string) => loraDetails(loraFolder(String(id))))
  handle('loras:info', async (id: string, refresh?: boolean) => {
    const folder = loraFolder(String(id))
    const cached = cachedInfo(folder)
    if (cached && !refresh) return cached
    return fetchInfo(folder, async (url, headers) => {
      const text = await fetchPage(url, headers, true)
      if (text === undefined) throw new Error(t('main.fetch.loraGone'))
      return text
    }, tokens(), !getSettings().allowExplicit)
  })
  handle('loras:setTriggerWords', (id: string, words: string[]) => {
    const saved = setTriggerWords(loraFolder(String(id)), Array.isArray(words) ? words : [])
    send('assets:change')
    return saved
  })
  handle('loras:setCategory', (id: string, category: string) => {
    setCategory(loraFolder(String(id)), String(category ?? ''))
    send('assets:change')
  })
  // LoRAs on Civitai and Hugging Face that fit a model: public lists, no token is sent
  const publicFetch: FetchLike = (url, init) => net.fetch(url, { ...init, headers: { ...(init?.headers as Record<string, string>), 'User-Agent': 'VulKara' } })
  handle('loras:search', (req: LoraSearchRequest) => {
    if (!req || typeof req !== 'object') throw new Error(t('main.loras.sayWhat'))
    return searchLoras(req, { fetcher: publicFetch, safe: !getSettings().allowExplicit, assets: listAssets() })
  })
  handle('loras:thumb', (url: string) => previewPicture(String(url ?? ''), { fetcher: publicFetch, safe: !getSettings().allowExplicit }))
  handle('training:state', () => trainer.state())
  handle('training:start', (request: TrainingRequest) => {
    if (queue.busy) throw new Error(t('main.training.queueBusy'))
    const foreign = typeof request?.baseModel === 'string' ? foreignRefusalOf(request.baseModel) : undefined
    if (foreign) throw new Error(foreign)
    for (const img of Array.isArray(request?.images) ? request.images : []) fileAccess.check(img?.path, 'training')
    return trainer.start(request)
  })
  handle('training:stop', () => trainer.stop())
  handle('training:choosePictures', async () => {
    if (!win) return []
    const res = await dialog.showOpenDialog(win, { properties: ['openFile', 'multiSelections'], filters: [{ name: t('main.dialogs.pictures'), extensions: ['png', 'jpg', 'jpeg', 'webp', 'bmp'] }] })
    if (res.canceled) return []
    fileAccess.grantFiles(res.filePaths)
    return res.filePaths
  })
  handle('training:chooseFolder', async () => {
    if (!win) return []
    const res = await dialog.showOpenDialog(win, { title: t('main.dialogs.trainingFolder'), properties: ['openDirectory'] })
    if (res.canceled || !res.filePaths.length) return []
    fileAccess.grantFolder(res.filePaths[0])
    return folderImages(res.filePaths[0])
  })

  handle('pose:detect', (path: string) => {
    // an absolute path can not be taken for an option of the detector
    if (typeof path !== 'string' || !isAbsolute(path) || !/\.(png|jpe?g|webp|bmp)$/i.test(path) || !existsSync(path)) throw new Error(t('main.files.choosePicture'))
    fileAccess.check(path)
    return detectPose(engineCommand('diffusers', ['detect_pose', path]), engineEnv(), (stage, percent) => send('pose:progress', stage, percent))
  })

  handle('restore:faces', (path: string) => {
    if (typeof path !== 'string' || !isAbsolute(path) || !/\.(png|jpe?g|webp|bmp|tiff?|heic)$/i.test(path) || !existsSync(path)) throw new Error(t('main.files.choosePicture'))
    fileAccess.check(path)
    return findFaces(engineCommand('diffusers', ['find_faces', path]), engineEnv())
  })

  handle('splash:state', () => splashState())
  handle('splash:confirm', () => confirmSplash())
  handle('app:info', () => ({
    name: app.getName(), version: app.getVersion(), electron: process.versions.electron, platform: `${process.platform} ${process.arch}`,
    ramGb: Math.round(totalmem() / 1024 ** 3),
    // "MacBook Pro (13-inch, M2, 2022) · 24 GB", "Mac mini (2024) · Apple M4 · 16 GB"
    mac: describeMac(macModel()),
    os: process.platform === 'darwin' ? `macOS ${process.getSystemVersion()}` : `${process.platform} ${process.getSystemVersion()}`,
  }))
  handle('app:openExternal', (url: string) => {
    if (typeof url === 'string' && url.startsWith('https://')) return shell.openExternal(url)
    throw new Error('only https links are opened')
  })
  handle('app:logs', () => logLines())
  // the problem report: the kept sessions, one of them redacted (only names of the list are read), the issue page
  handle('logs:sessions', () => {
    const folder = logFolder()
    return folder ? listSessions(folder, currentSession()) : []
  })
  handle('logs:report', async (id: string) => {
    const folder = logFolder()
    if (!folder) throw new Error(t('main.logs.noLogFile'))
    const raw = await readSession(folder, id)
    const { text, counts } = redact(raw, machineContext())
    const summary = hiddenSummary(counts)
    const lines = text.split('\n').filter(Boolean).length
    const os = process.platform === 'darwin' ? `macOS ${process.getSystemVersion()}` : `${process.platform} ${process.getSystemVersion()}`
    const header = [
      `${app.getName()} ${app.getVersion()} · ${os} · ${describeMac(macModel())}`,
      `Log of the session started ${stamp(sessionStart(id) ?? 0)}, ${lines} lines. ${summary} (replaced by ****).`,
    ].join('\n')
    return { id, header, text, summary, counts }
  })
  // the one page of GitHub this call opens, built here: a page can not choose the address
  handle('logs:openIssue', () => shell.openExternal(issueUrl()))
  handle('remote:info', async () => {
    const r = await import('./remote')
    return { running: r.remoteRunning(), addresses: r.remoteAddresses(), https: r.remoteHttps() }
  })
  onLog((line) => send('app:log', line))
}

export function bindWindow(w: BrowserWindow): void {
  win = w
  // the viewer windows belong to the main window: back in it, they close
  w.on('closed', closeViewers)
  w.on('focus', closeViewers)
}

export function shutdown(): void {
  exporting?.kill()
  monitor.stop()
  trainer.stop()
  imports.cancelAll()
  stopEngines()
  selector.stop()
}
