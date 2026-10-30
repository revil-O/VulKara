// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The bridge in a browser (remote web UI): the same window.vk as in the app, over the Mac's remote server. A call is
// a POST to /ipc, the events come as one Server-Sent-Events stream, local pictures from /file. Everything carries
// the access token, which comes with the link once and is kept in this browser.

import { makeApi } from '@shared/bridge'
import { showViewer } from './viewer_overlay'
import type { VulkaraApi } from '@shared/api'

const KEY = 'vk.remoteToken'

/** The token: from the link (?t=, then taken out of the address bar), else the one this browser kept. */
export function remoteToken(): string | null {
  const url = new URL(location.href)
  const fromLink = url.searchParams.get('t')
  if (fromLink) {
    try {
      localStorage.setItem(KEY, fromLink)
    } catch {
      // private window: the token lives as long as the page
    }
    url.searchParams.delete('t')
    history.replaceState(null, '', url.pathname + url.search + url.hash)
    return fromLink
  }
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function keepToken(token: string): void {
  try {
    localStorage.setItem(KEY, token)
  } catch {
    // private window
  }
}

export function forgetToken(): void {
  try {
    localStorage.removeItem(KEY)
  } catch {
    // private window
  }
}

// captured at module load, before installRemoteVk sets window.vk: the app's preload has set it by now, a browser has not
const remote = !(window as { vk?: VulkaraApi }).vk
/** True in a browser (the remote web UI), false in the app's own window. */
export const isRemote = (): boolean => remote

/** Builds window.vk on HTTP. unauthorized: the Mac refused the token (renewed, or remote access switched off). */
export function installRemoteVk(token: string, unauthorized: () => void): void {
  const auth = encodeURIComponent(token)
  const listeners = new Map<string, Set<(...args: unknown[]) => void>>()
  let events: EventSource | undefined

  const call = async <T>(channel: string, ...args: unknown[]): Promise<T> => {
    const res = await fetch('/ipc', {
      method: 'POST',
      headers: { authorization: `Bearer ${token}`, 'content-type': 'application/json' }, // i18n-ok: an HTTP header
      body: JSON.stringify({ channel, args }),
    })
    if (res.status === 401) {
      unauthorized()
      throw new Error('token')
    }
    const body = (await res.json()) as { result?: T; error?: string }
    if (!res.ok) throw new Error(body.error ?? String(res.status))
    return body.result as T
  }

  const on = <A extends unknown[]>(channel: string, fn: (...args: A) => void): (() => void) => {
    // one stream for every channel, opened by the first page that listens; the browser reconnects it by itself
    if (!events) {
      events = new EventSource(`/events?t=${auth}`)
      events.onmessage = (e: MessageEvent<string>) => {
        const { channel: c, args } = JSON.parse(e.data) as { channel: string; args: unknown[] }
        listeners.get(c)?.forEach((f) => f(...args))
      }
    }
    let set = listeners.get(channel)
    if (!set) listeners.set(channel, (set = new Set()))
    const f = fn as (...args: unknown[]) => void
    set.add(f)
    return () => set.delete(f)
  }

  const api = makeApi(call, on, {
    fileUrl: (path) => `/file?t=${auth}&path=${encodeURIComponent(path)}`,
    // a browser never learns where a dropped file lies; the remote UI does not take pictures from this side
    pathOf: () => '',
  })
  // a browser has no second window: the large view opens over the page (App.vue), the rest of viewer stays unused
  api.viewer.open = (items, index) => { showViewer(items, index); return Promise.resolve() }
  // a model's or licence's page opens in this browser, not on the Mac (links.ts lets only https:// through)
  api.app.openExternal = (link) => { window.open(link, '_blank', 'noopener'); return Promise.resolve() }
  ;(window as { vk?: VulkaraApi }).vk = api
}
