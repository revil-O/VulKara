<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// What the engines and installers report: the time on the left, the message, and on the right what a line
// measured (size and speed of a downloaded package). Report a problem opens one of the kept session logs, with
// personal data replaced, to post it on GitHub.
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Bug } from '@lucide/vue'
import PageFrame from '../components/PageFrame.vue'
import ReportDialog from '../components/ReportDialog.vue'
import { t } from '../i18n'
import type { LogLine } from '@shared/api'

const MAX_LINES = 4000
const lines = ref<LogLine[]>([])
const box = ref<HTMLElement>()
const copied = ref(false)
const reporting = ref(false)

const two = (n: number): string => String(n).padStart(2, '0')
function stamp(time: number): string {
  const d = new Date(time)
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`
}

// stays at the end while new lines arrive, unless the user scrolled up
function append(added: LogLine[]): void {
  const el = box.value
  const atEnd = !el || el.scrollHeight - el.scrollTop - el.clientHeight < 40
  lines.value = [...lines.value, ...added].slice(-MAX_LINES)
  if (atEnd) void nextTick(() => el?.scrollTo({ top: el.scrollHeight }))
}

let stopListening: (() => void) | undefined
onMounted(async () => {
  // lines logged while the earlier ones are on their way come after them
  const early: LogLine[] = []
  let ready = false
  stopListening = window.vk.app.onLog((line) => (ready ? append([line]) : early.push(line)))
  append(await window.vk.app.logs())
  ready = true
  const seen = new Set(lines.value.map((l) => `${l.time} ${l.text}`))
  append(early.filter((l) => !seen.has(`${l.time} ${l.text}`)))
})
onBeforeUnmount(() => stopListening?.())

async function copy(): Promise<void> {
  await navigator.clipboard.writeText(lines.value.map((l) => `${stamp(l.time)}  ${l.text}${l.note ? `  [${l.note}]` : ''}`).join('\n'))
  copied.value = true
  setTimeout(() => (copied.value = false), 1500)
}
</script>

<template>
  <PageFrame :title="t('app.logs.title')" :subtitle="t('app.logs.subtitle')">
    <template #actions>
      <button class="btn" :disabled="!lines.length" @click="copy">{{ copied ? t('app.logs.copied') : t('app.logs.copyAll') }}</button>
      <button class="btn primary" @click="reporting = true"><Bug :size="14" /> {{ t('app.logs.report') }}</button>
    </template>
    <ReportDialog v-if="reporting" @close="reporting = false" />
    <div ref="box" class="log selectable">
      <p v-if="!lines.length" class="dim">{{ t('app.logs.empty') }}</p>
      <div v-for="(l, i) in lines" :key="i" class="line">
        <time class="dim">{{ stamp(l.time) }}</time>
        <span class="text">{{ l.text }}</span>
        <span v-if="l.note" class="note">{{ l.note }}</span>
      </div>
    </div>
  </PageFrame>
</template>

<style scoped>
.log {
  height: 100%;
  overflow: auto;
  padding: 10px 14px;
  border-radius: var(--radius-m);
  background: var(--surface);
  border: 1px solid var(--line);
  font: 11.5px/1.5 var(--mono);
}

.line {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 14px;
  align-items: baseline;
}

time,
.note {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.text {
  white-space: pre-wrap;
  word-break: break-word;
  min-width: 0;
}

.note {
  color: var(--accent);
}
</style>
