// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { AppUpdateState } from '@shared/api'

/** The app's own update (main process, app_update.ts) for the banner, the page header and the Changelog page;
 *  not in the remote web UI. */
export const useAppUpdateStore = defineStore('appUpdate', () => {
  const state = ref<AppUpdateState>()
  /** bumped to bring the update card up again (also after Later) */
  const shown = ref(0)
  let started = false

  function start(): void {
    if (started) return
    started = true
    window.vk.app.onUpdate((s) => (state.value = s))
    void window.vk.app.update().then((s) => (state.value = s))
  }

  return { state, shown, start, show: () => shown.value++ }
})
