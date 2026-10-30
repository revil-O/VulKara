<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// A newer VulKara on GitHub: update and restart, read what is new, or later (until the next version). Shows the
// download and the check of the update while they run.
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { Download, ExternalLink, RotateCw, X } from 'lucide-vue-next'
import { t } from '../i18n'
import { cleanError } from '../stores/runtimes'
import { useAppUpdateStore } from '../stores/appUpdate'

const DISMISSED = 'vk.updateLater'
const updates = useAppUpdateStore()
const { state } = storeToRefs(updates)
const later = ref(readLater())
const failed = ref('')
const installButton = ref<HTMLButtonElement>()

function readLater(): string {
  try {
    return localStorage.getItem(DISMISSED) ?? ''
  } catch {
    return ''
  }
}

onMounted(() => updates.start())
// the page header's notice: the card comes back (also after Later) with its button focused
watch(() => updates.shown, async () => {
  later.value = ''
  await nextTick()
  installButton.value?.focus()
})

const shown = computed(() => {
  const s = state.value
  if (!s?.available) return false
  // running steps always show; an error (and the offer) only until Later
  return ['downloading', 'checking', 'restarting'].includes(s.stage) || later.value !== s.available
})
// the reasons the main process names with a key; anything else is its message
const REASONS = { notPackaged: 'app.update.notPackaged', notInstalled: 'app.update.notInstalled', readOnly: 'app.update.readOnly' } as const
const rawError = computed(() => failed.value || (state.value?.stage === 'error' ? state.value.error ?? '' : ''))
// a reason of the place the app runs from: trying again does not help
const stuck = computed(() => rawError.value in REASONS)
const error = computed(() => (stuck.value ? t(REASONS[rawError.value as keyof typeof REASONS]) : rawError.value))

async function install(): Promise<void> {
  failed.value = ''
  try {
    await window.vk.app.installUpdate()
  } catch (err) {
    failed.value = cleanError(err)
  }
}
function notes(): void {
  if (state.value?.notesUrl) void window.vk.app.openExternal(state.value.notesUrl)
}
function dismiss(): void {
  later.value = state.value?.available ?? ''
  failed.value = ''
  try {
    localStorage.setItem(DISMISSED, later.value)
  } catch {
    // remembered for this session only
  }
}
</script>

<template>
  <aside v-if="shown && state" class="update card" role="status" aria-live="polite">
    <template v-if="state.stage === 'downloading'">
      <p>{{ t('app.update.downloading', { version: state.available ?? '', percent: state.percent }) }}</p>
      <div class="bar"><span :style="{ width: state.percent + '%' }" /></div>
    </template>
    <p v-else-if="state.stage === 'checking'">{{ t('app.update.checking', { version: state.available ?? '' }) }}</p>
    <p v-else-if="state.stage === 'restarting'">{{ t('app.update.restarting', { version: state.available ?? '' }) }}</p>
    <template v-else>
      <p>
        <strong>{{ t('app.update.available', { version: state.available ?? '' }) }}</strong>
        <span class="dim">{{ t('app.update.current', { version: state.current }) }}</span>
      </p>
      <p v-if="error" class="error selectable">{{ t('app.update.failed', { reason: error }) }}</p>
      <div class="actions">
        <button v-if="!stuck" ref="installButton" class="btn primary small" @click="install">
          <component :is="error ? RotateCw : Download" :size="13" /> {{ error ? t('app.update.retry') : t('app.update.install') }}
        </button>
        <button class="btn small" @click="notes"><ExternalLink :size="13" /> {{ t('app.update.notes') }}</button>
        <button class="btn small ghost" :aria-label="t('app.update.later')" @click="dismiss"><X :size="13" /> {{ t('app.update.later') }}</button>
      </div>
    </template>
  </aside>
</template>

<style scoped>
.update {
  position: fixed;
  right: 16px;
  bottom: calc(var(--jobbar) + 12px);
  z-index: 45;
  width: min(380px, calc(100vw - 32px));
  padding: 14px 16px;
  display: grid;
  gap: 8px;
  box-shadow: var(--shadow);
}
.update p {
  margin: 0;
  display: grid;
  gap: 2px;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.bar {
  height: 6px;
  border-radius: 3px;
  background: var(--surface-3);
  overflow: hidden;
}
.bar span {
  display: block;
  height: 100%;
  background: var(--accent);
  transition: width 0.3s;
}
.error {
  color: var(--danger);
}
</style>
