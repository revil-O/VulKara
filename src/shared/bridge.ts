// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The bridge between the pages and the main process (window.vk), once: the preload builds it on Electron's IPC, the
// remote web UI on HTTP (remote_vk.ts). Only the transport differs, plus two things a browser does differently: where
// a local picture is loaded from, and the path of a dropped file (a browser never knows it).

import type { VulkaraApi } from './api'

export type Call = <T>(channel: string, ...args: unknown[]) => Promise<T>
export type On = <A extends unknown[]>(channel: string, fn: (...args: A) => void) => () => void
export interface BridgeExtra {
  /** the address a page loads a local picture or video from */
  fileUrl(path: string): string
  /** the path of a file dropped onto the page ('' where it can not be known) */
  pathOf(file: File): string
}

export function makeApi(call: Call, on: On, extra: BridgeExtra): VulkaraApi {
  return {
    settings: {
      get: () => call('settings:get'),
      set: (key, value) => call('settings:set', key, value),
      chooseFolder: (key) => call('settings:chooseFolder', key),
    },
    i18n: {
      lang: () => call('i18n:lang'),
      onLang: (fn) => on('i18n:lang', fn),
    },
    tokens: {
      set: (service, token) => call('tokens:set', service, token),
      has: (service) => call('tokens:has', service),
    },
    runtimes: {
      list: () => call('runtimes:list'),
      install: (id) => call('runtimes:install', id),
      remove: (id) => call('runtimes:remove', id),
      onProgress: (fn) => on('runtimes:progress', fn),
      updates: () => call('runtimes:updates'),
      checkUpdates: (force) => call('runtimes:checkUpdates', force === true),
      onUpdates: (fn) => on('runtimes:updatesChanged', fn),
    },
    queue: {
      add: (job, count) => call('queue:add', job, count),
      cancel: (jobId) => call('queue:cancel', jobId),
      clearFinished: () => call('queue:clearFinished'),
      snapshot: () => call('queue:snapshot'),
      onChange: (fn) => on('queue:change', fn),
    },
    assets: {
      list: () => call('assets:list'),
      remove: (id) => call('assets:remove', id),
      reimport: (id) => call('assets:reimport', id),
      rename: (id, title) => call('assets:rename', id, title),
      bake: (modelId, loras, name) => call('assets:bake', modelId, loras, name),
      exportSingle: (modelId) => call('assets:exportSingle', modelId),
      onExportProgress: (fn) => on('assets:exportProgress', fn),
      onChange: (fn) => on('assets:change', fn),
    },
    benchmark: {
      start: (job, count, model) => call('benchmark:start', job, count, model),
      list: () => call('benchmark:list'),
      clear: () => call('benchmark:clear'),
      onChange: (fn) => on('benchmark:change', fn),
    },
    system: {
      stats: () => call('system:stats'),
      hardware: () => call('system:hardware'),
      onStats: (fn) => on('system:stats', fn),
    },
    helpers: {
      list: () => call('helpers:list'),
      install: (id) => call('helpers:install', id),
      remove: (id) => call('helpers:remove', id),
    },
    tools: {
      list: () => call('tools:list'),
      install: (id) => call('tools:install', id),
      importFile: () => call('tools:importFile'),
      remove: (folder) => call('tools:remove', folder),
      select: (tool, image, points) => call('tools:select', tool, image, points),
    },
    imports: {
      inspect: (request) => call('imports:inspect', request),
      add: (request, title) => call('imports:add', request, title),
      cancel: (id) => call('imports:cancel', id),
      clearFinished: () => call('imports:clearFinished'),
      list: () => call('imports:list'),
      onChange: (fn) => on('imports:change', fn),
    },
    history: {
      list: (opts) => call('history:list', opts),
      remove: (ids, trashFiles) => call('history:remove', ids, trashFiles),
      favorite: (id, file, on) => call('history:favorite', id, file, on),
      favorites: () => call('history:favorites'),
      onChange: (fn) => on('history:change', fn),
    },
    splash: {
      state: () => call('splash:state'),
      confirm: () => call('splash:confirm'),
      onReady: (fn) => on('splash:ready', fn),
    },
    viewer: {
      open: (items, index) => call('viewer:open', items, index),
      payload: () => call('viewer:payload'),
      act: (action) => call('viewer:act', action),
      onAction: (fn) => on('viewer:action', fn),
    },
    licences: {
      get: (id, refresh) => call('licences:get', id, refresh),
      setOrigin: (id, link) => call('licences:setOrigin', id, link),
    },
    loras: {
      details: (id) => call('loras:details', id),
      info: (id, refresh) => call('loras:info', id, refresh),
      setTriggerWords: (id, words) => call('loras:setTriggerWords', id, words),
      setCategory: (id, category) => call('loras:setCategory', id, category),
      search: (request) => call('loras:search', request),
      thumb: (url) => call('loras:thumb', url),
    },
    training: {
      state: () => call('training:state'),
      start: (request) => call('training:start', request),
      stop: () => call('training:stop'),
      choosePictures: () => call('training:choosePictures'),
      chooseFolder: () => call('training:chooseFolder'),
      onChange: (fn) => on('training:change', fn),
    },
    restore: {
      faces: (path) => call('restore:faces', path),
    },
    pose: {
      detect: (path) => call('pose:detect', path),
      onProgress: (fn) => on('pose:progress', fn),
    },
    dialog: {
      ask: (message, yes, no, detail) => call('dialog:ask', message, yes, no, detail),
    },
    files: {
      url: (path) => extra.fileUrl(path),
      choose: (kind) => call('files:choose', kind),
      saveAs: (path, suggestedName) => call('files:saveAs', path, suggestedName),
      reveal: (path) => call('files:reveal', path),
      share: (path) => call('files:share', path),
      copyImage: (path) => call('files:copyImage', path),
      pathOf: (file) => extra.pathOf(file),
      writeImage: (dataUrl) => call('files:writeImage', dataUrl),
      writePose: (dataUrl) => call('files:writePose', dataUrl),
    },
    app: {
      info: () => call('app:info'),
      openExternal: (url) => call('app:openExternal', url),
      logs: () => call('app:logs'),
      onLog: (fn) => on('app:log', fn),
      update: () => call('app:update'),
      checkUpdate: () => call('app:checkUpdate'),
      promptCache: () => call('app:promptCache'),
      clearPromptCache: () => call('app:clearPromptCache'),
      installUpdate: () => call('app:installUpdate'),
      onUpdate: (fn) => on('app:updateChanged', fn),
    },
    remote: {
      info: () => call('remote:info'),
    },
    report: {
      sessions: () => call('logs:sessions'),
      session: (id) => call('logs:report', id),
      openIssue: () => call('logs:openIssue'),
    },
  }
}
