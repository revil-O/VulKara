<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Report a problem: pick one of the kept session logs, read it with personal data replaced by **** (the main process
// redacts it, log_redact.ts), then copy it or open a new GitHub issue and paste it there. Nothing is sent by the app.
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, Check, Copy, ExternalLink, TriangleAlert, X } from '@lucide/vue'
import HintBadge from './HintBadge.vue'
import { cleanError } from '../stores/runtimes'
import { dateTime, t } from '../i18n'
import { issueReport, reportText } from '@shared/report'
import type { LogReport, LogSession } from '@shared/api'

const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLDialogElement>()
const sessions = ref<LogSession[]>()
const chosen = ref('')
const report = ref<LogReport>()
// what was hidden, in the app's language (the report itself, report.header, stays English for the issue)
const CATEGORIES = ['paths', 'files', 'names', 'prompts', 'tokens', 'links', 'emails', 'addresses', 'ids'] as const
const summaryText = computed(() => {
  const counts = report.value?.counts ?? {}
  const parts = CATEGORIES.filter((c) => (counts[c] ?? 0) > 0).map((c) => t(`app.report.counts.${c}`, { n: counts[c] }))
  return parts.length ? t('app.report.hidden', { list: parts.join(', ') }) : t('app.report.nothingFound')
})
const loading = ref(false)
const error = ref('')
const done = ref<'' | 'copied' | 'issue'>('')

const two = (n: number): string => String(n).padStart(2, '0')
const day = (ts: number): string => dateTime(ts, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
const clock = (ts: number): string => { const d = new Date(ts); return `${two(d.getHours())}:${two(d.getMinutes())}` }
function span(s: LogSession): string {
  if (!s.end || s.end - s.start < 60_000) return clock(s.start)
  const min = Math.round((s.end - s.start) / 60_000)
  const length = min < 60 ? t('app.report.minutes', { min }) : t('app.report.hoursMinutes', { h: Math.floor(min / 60), min: two(min % 60) })
  return t('app.report.span', { start: clock(s.start), end: clock(s.end), length })
}

const forIssue = computed(() => (report.value ? issueReport(report.value.header, report.value.text) : undefined))

onMounted(async () => {
  dialog.value?.showModal()
  try {
    sessions.value = await window.vk.report.sessions()
    // the newest one with errors before this session (a problem made you restart), else this one
    chosen.value = (sessions.value.find((s) => !s.current && s.errors) ?? sessions.value[0])?.id ?? ''
  } catch (err) {
    error.value = cleanError(err)
  }
})

async function show(): Promise<void> {
  if (!chosen.value) return
  loading.value = true
  error.value = ''
  try {
    report.value = await window.vk.report.session(chosen.value)
  } catch (err) {
    error.value = cleanError(err)
  } finally {
    loading.value = false
  }
}

async function copy(): Promise<void> {
  if (!report.value) return
  await navigator.clipboard.writeText(reportText(report.value.header, report.value.text))
  done.value = 'copied'
}

async function openIssue(): Promise<void> {
  if (!forIssue.value) return
  try {
    await navigator.clipboard.writeText(forIssue.value.text)
    await window.vk.report.openIssue()
    done.value = 'issue'
  } catch (err) {
    error.value = cleanError(err)
  }
}

function back(): void {
  report.value = undefined
  done.value = ''
  error.value = ''
}

const close = (): void => emit('close')
</script>

<template>
  <!-- @close: Escape may close a modal dialog without a cancel event -->
  <dialog ref="dialog" class="report" @cancel.prevent="close" @close="close">
    <div class="inner">
      <header>
        <h2 class="grow">{{ t('app.report.title') }}</h2>
        <button class="btn small ghost" :aria-label="t('common.close')" @click="close"><X :size="14" /></button>
      </header>

      <template v-if="!report">
        <p class="dim">
          {{ t('app.report.choose') }}
          <HintBadge start :text="t('app.report.chooseHint')" />
        </p>
        <p v-if="sessions && !sessions.length" class="dim">{{ t('app.report.noSessions') }}</p>
        <div v-else-if="sessions" class="list" role="radiogroup" :aria-label="t('app.report.session')">
          <label v-for="s in sessions" :key="s.id" class="session" :class="{ on: chosen === s.id }">
            <input v-model="chosen" type="radio" name="session" :value="s.id" />
            <span class="when">
              <b>{{ day(s.start) }}</b>
              <span class="dim">{{ span(s) }} · {{ t('app.report.lines', { n: s.lines }) }}</span>
            </span>
            <span v-if="s.current" class="tag">{{ t('app.report.thisSession') }}</span>
            <span v-if="s.errors" class="tag warn"><TriangleAlert :size="12" /> {{ t('app.report.errorLines', { n: s.errors }) }}</span>
          </label>
        </div>
        <p v-if="error" class="error selectable">{{ error }}</p>
        <footer>
          <button class="btn" @click="close">{{ t('common.close') }}</button>
          <button class="btn primary" :disabled="!chosen || loading" @click="show">{{ loading ? t('app.report.preparing') : t('app.report.showLog') }}</button>
        </footer>
      </template>

      <template v-else>
        <p class="summary">
          <b>{{ summaryText }}</b>
          <HintBadge start :text="t('app.report.hiddenHint')" />
        </p>
        <p class="note">{{ t('app.report.readFirst') }}</p>
        <textarea class="entry log" readonly spellcheck="false" :value="`${report.header}\n\n${report.text}`" :aria-label="t('app.report.logLabel')" />
        <p v-if="forIssue?.dropped" class="dim">
          {{ t('app.report.dropped', { n: forIssue.dropped }) }}
        </p>
        <p v-if="done === 'copied'" class="ok"><Check :size="13" /> {{ t('app.report.copiedDone') }}</p>
        <p v-else-if="done === 'issue'" class="ok"><Check :size="13" /> {{ t('app.report.issueDone') }}</p>
        <p v-if="error" class="error selectable">{{ error }}</p>
        <footer>
          <button class="btn ghost" @click="back"><ArrowLeft :size="14" /> {{ t('app.report.otherSession') }}</button>
          <span class="grow" />
          <button class="btn" @click="copy"><Copy :size="14" /> {{ t('app.report.copy') }}</button>
          <button class="btn primary" @click="openIssue"><ExternalLink :size="14" /> {{ t('app.report.openIssue') }}</button>
          <button class="btn" @click="close">{{ t('common.close') }}</button>
        </footer>
      </template>
    </div>
  </dialog>
</template>

<style scoped>
.report {
  width: min(820px, calc(100vw - 80px));
  padding: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius-l);
  background: var(--bg);
  color: var(--text);
  box-shadow: var(--shadow);
}

.report::backdrop {
  background: rgba(0, 0, 0, 0.45);
}

.inner {
  display: grid;
  gap: 12px;
  padding: 18px 20px;
}

header,
footer {
  display: flex;
  align-items: center;
  gap: 10px;
}

footer {
  justify-content: flex-end;
}

h2 {
  margin: 0;
  font-size: 16px;
}

p {
  margin: 0;
}

.grow {
  flex: 1;
  min-width: 0;
}

.list {
  display: grid;
  gap: 4px;
  max-height: min(420px, 55vh);
  overflow: auto;
}

.session {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface);
  cursor: pointer;
}

.session.on {
  border-color: var(--accent);
}

.session input {
  accent-color: var(--accent);
}

.when {
  display: grid;
  flex: 1;
  min-width: 0;
}

.when .dim {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex: none;
  padding: 2px 7px;
  border-radius: 10px;
  background: var(--surface-3);
  font-size: 11.5px;
}

.tag.warn {
  color: var(--danger);
}

.summary {
  display: flex;
  align-items: center;
  gap: 8px;
}

.note {
  color: var(--text-dim);
}

.log {
  height: min(440px, 52vh);
  padding: 8px 10px;
  resize: none;
  font: 11.5px/1.5 var(--mono);
  white-space: pre;
  overflow: auto;
  user-select: text;
}

.ok {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--accent);
}
</style>
