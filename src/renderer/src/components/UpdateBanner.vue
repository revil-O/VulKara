<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// A newer VulKara on GitHub: update and restart, read what is new, or later (until the next version). Shows the
// download and the check of the update while they run.
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { Download, ExternalLink, RotateCw, X } from '@lucide/vue'
import { t } from '../i18n'
import { cleanError } from '../stores/runtimes'
import { useAppUpdateStore } from '../stores/appUpdate'
import type { UpdateWork } from '@shared/api'

const DISMISSED = 'vk.updateLater'
const updates = useAppUpdateStore()
const { state } = storeToRefs(updates)
const later = ref(readLater())
const failed = ref('')
// what ran when Update was clicked; asking: the stop is to be confirmed
const running = ref<UpdateWork[]>([])
const asking = ref(false)
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

async function install(mode?: 'after' | 'stop'): Promise<void> {
  failed.value = ''
  asking.value = false
  try {
    running.value = await window.vk.app.installUpdate(mode)
  } catch (err) {
    failed.value = cleanError(err)
  }
}
function noWait(): void {
  running.value = []
  void window.vk.app.cancelUpdateWait()
}
/** "2 pictures or videos, 1 download" */
function workList(work: UpdateWork[]): string {
  return work.map((w) => t(`app.update.work.${w.kind}`, { n: w.count })).join(', ')
}
// a runtime install is not stopped: the confirmation says so
// a started download shows its own progress
watch(() => state.value?.stage, (stage) => { if (stage !== 'idle') running.value = [] })
const onlyWaits = computed(() => (state.value?.work ?? running.value).some((w) => w.kind === 'runtime'))
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
    <template v-else-if="asking">
      <p>{{ t('app.update.stopAsk', { list: workList(state.work ?? running) }) }}<span v-if="onlyWaits" class="dim">{{ t('app.update.runtimeWaits') }}</span></p>
      <div class="actions">
        <button class="btn primary small" @click="install('stop')">{{ t('app.update.stopConfirm') }}</button>
        <button class="btn small" @click="asking = false">{{ t('app.update.back') }}</button>
      </div>
    </template>
    <template v-else-if="state.waiting">
      <p>
        <strong>{{ t('app.update.available', { version: state.available ?? '' }) }}</strong>
        <span>{{ t('app.update.waitingFor', { list: workList(state.work ?? []) }) }}</span>
      </p>
      <div class="actions">
        <button class="btn small" @click="asking = true">{{ t('app.update.stopNow') }}</button>
        <button class="btn small ghost" @click="noWait">{{ t('app.update.noWait') }}</button>
      </div>
    </template>
    <template v-else-if="running.length">
      <p>
        <strong>{{ t('app.update.available', { version: state.available ?? '' }) }}</strong>
        <span>{{ t('app.update.stillRunning', { list: workList(running) }) }}</span>
      </p>
      <div class="actions">
        <button ref="installButton" class="btn primary small" @click="install('after')">{{ t('app.update.after') }}</button>
        <button class="btn small" @click="asking = true">{{ t('app.update.stopNow') }}</button>
        <button class="btn small ghost" @click="running = []">{{ t('app.update.back') }}</button>
      </div>
    </template>
    <template v-else>
      <p>
        <strong>{{ t('app.update.available', { version: state.available ?? '' }) }}</strong>
        <span class="dim">{{ t('app.update.current', { version: state.current }) }}</span>
      </p>
      <p v-if="error" class="error selectable">{{ t('app.update.failed', { reason: error }) }}</p>
      <div class="actions">
        <button v-if="!stuck" ref="installButton" class="btn primary small" @click="install()">
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
