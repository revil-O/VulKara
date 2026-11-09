<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// The monitor window (app menu and menu bar → Monitor): the running job against what was expected (its memory plan
// on every Mac; on the Mac the measurements were made on, the measured time and memory of its model) and this Mac's
// figures with the last few minutes as small lines. It only reads: the stats every 2 s and the queue.
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { HardwareInfo, QueueSnapshot, SystemStats } from '@shared/api'
import { delta, expectationFor, type Tone } from '@shared/expectations'
import HintBadge from '../components/HintBadge.vue'
import Sparkline from '../components/Sparkline.vue'
import { gb } from '../stores/system'
import { num, t } from '../i18n'
import { formatDuration } from '../util/format'

const SAMPLES = 150  // 5 minutes of the 2 s samples
const stats = ref<SystemStats>()
const snap = ref<QueueSnapshot>({ jobs: [], engineReady: true })
const hw = ref<HardwareInfo>()
const history = ref<{ app: number[]; cpu: number[]; gpu: number[] }>({ app: [], cpu: [], gpu: [] })
// what VulKara and its engines hold with the GPU's share, sent while a job runs (the stats' appGb leaves it out)
const footprint = ref<number>()
// the running job's own figures: from its start (memory peak, swap at the start)
const since = ref<{ id: string; swapStart: number; peak: number }>()

const running = computed(() => snap.value.jobs.find((j) => j.state === 'running'))
const waiting = computed(() => snap.value.jobs.filter((j) => j.state === 'waiting').length)
const model = computed(() => running.value?.job.modelDir.replace(/\/+$/, '').split('/').pop() ?? '')
const expected = computed(() => {
  const j = running.value?.job
  return j ? expectationFor(j.modelDir, j.steps ?? 0, j.width, j.height, hw.value) : undefined
})
/** the whole picture as the queue estimates it now: time so far plus what it says is left */
const perPicture = computed(() => {
  const r = running.value
  return r?.startedAt && r.eta !== undefined ? (Date.now() - r.startedAt) / 1000 + r.eta : undefined
})
const swapAdded = computed(() => (stats.value && since.value ? Math.max(0, stats.value.swapGb - since.value.swapStart) : 0))

function push(list: number[], v: number): number[] {
  return [...list, v].slice(-SAMPLES)
}
function onStats(s: SystemStats): void {
  stats.value = s
  history.value = { ...history.value, cpu: push(history.value.cpu, s.cpuPercent), gpu: push(history.value.gpu, Math.max(0, s.gpuPercent)) }
  const r = running.value
  if (!r) {
    since.value = footprint.value = undefined
    history.value.app = []
  } else if (since.value?.id !== r.job.id) {
    since.value = { id: r.job.id, swapStart: s.swapGb, peak: 0 }
    history.value.app = []
  }
}
function onFootprint(gb: number): void {
  if (!since.value) return
  footprint.value = gb
  since.value.peak = Math.max(since.value.peak, gb)
  history.value = { ...history.value, app: push(history.value.app, gb) }
}

const offs: (() => void)[] = []
onMounted(async () => {
  offs.push(window.vk.system.onStats(onStats), window.vk.app.onFootprint(onFootprint), window.vk.queue.onChange((s) => { snap.value = s }))
  ;[snap.value, hw.value] = await Promise.all([window.vk.queue.snapshot(), window.vk.system.hardware()])
  onStats(await window.vk.system.stats())
})
onUnmounted(() => offs.forEach((off) => off()))

const TONE: Record<Tone, string> = { neutral: '', better: 'better', worse: 'worse', bad: 'bad' }
const sign = (pct: number): string => (pct > 0 ? `+${pct} %` : `${pct} %`)
const rated = (live: number, exp: number): { text: string; cls: string } => {
  const d = delta(live, exp)
  return { text: sign(d.pct), cls: TONE[d.tone] }
}
</script>

<template>
  <main class="monitor">
    <h1>{{ t('app.monitor.title') }} <HintBadge start :text="t('app.monitor.hint')" /></h1>

    <section class="card">
      <h2>{{ t('app.monitor.job') }}</h2>
      <p v-if="!running" class="dim">{{ t('app.monitor.idle') }}</p>
      <template v-else>
        <div class="model selectable">{{ model }} <span class="dim">{{ running.job.width }}×{{ running.job.height }} · {{ running.job.steps }}</span></div>
        <div class="pair"><span class="dim">{{ t('app.monitor.progress') }}</span><span>{{ Math.max(0, running.progress) }} %</span></div>
        <div v-if="running.secondsPerStep" class="pair"><span class="dim">{{ t('app.monitor.perStep') }}</span><span>{{ num(running.secondsPerStep, 2) }} s</span></div>
        <div v-if="running.eta !== undefined" class="pair"><span class="dim">{{ t('app.monitor.left') }}</span><span>{{ formatDuration(running.eta) }}</span></div>
        <div class="pair">
          <span class="dim">{{ t('app.monitor.memory') }}</span>
          <span>
            {{ footprint !== undefined ? gb(footprint) : '–' }}
            <template v-if="running.planGb">
              <span class="dim"> · {{ t('app.monitor.plan') }} {{ gb(running.planGb) }}</span>
              <b v-if="footprint !== undefined" :class="rated(footprint, running.planGb).cls"> {{ rated(footprint, running.planGb).text }}</b>
            </template>
          </span>
        </div>
        <div v-if="since?.peak" class="pair">
          <span class="dim">{{ t('app.monitor.peak') }}</span>
          <span>
            {{ gb(since.peak) }}
            <b v-if="running.planGb" :class="rated(since.peak, running.planGb).cls"> {{ rated(since.peak, running.planGb).text }}</b>
          </span>
        </div>
        <div class="pair"><span class="dim">{{ t('app.monitor.swapAdded') }}</span><b :class="{ bad: swapAdded > 2, worse: swapAdded >= 0.5 && swapAdded <= 2 }">{{ gb(swapAdded) }}</b></div>
        <Sparkline :values="history.app" :max="stats?.totalGb" :width="440" :height="36" />

        <h3>{{ expected ? t('app.monitor.measured', { ref: expected.ref }) : t('app.monitor.notMeasured') }}</h3>
        <template v-if="expected">
          <div class="pair">
            <span class="dim">{{ t('app.monitor.perPicture') }}</span>
            <span>
              {{ formatDuration(expected.secondsPerPicture) }}
              <b v-if="perPicture !== undefined" :class="rated(perPicture, expected.secondsPerPicture).cls"> {{ formatDuration(perPicture) }} ({{ rated(perPicture, expected.secondsPerPicture).text }})</b>
            </span>
          </div>
          <div v-if="since?.peak" class="pair">
            <span class="dim">{{ t('app.monitor.peak') }}</span>
            <span>{{ gb(expected.peakGb) }} <b :class="rated(since.peak, expected.peakGb).cls"> {{ rated(since.peak, expected.peakGb).text }}</b></span>
          </div>
        </template>
      </template>
      <p v-if="waiting" class="dim">{{ t('app.monitor.waiting', { n: waiting }) }}</p>
    </section>

    <section v-if="stats" class="card">
      <h2>{{ t('app.monitor.thisMac') }}<span v-if="hw" class="dim"> · {{ hw.chip }}, {{ Math.round(hw.ramGb) }} GB</span></h2>
      <div class="row"><span class="dim">{{ t('app.monitor.cpu') }}</span><span>{{ Math.round(stats.cpuPercent) || 0 }} %</span><Sparkline :values="history.cpu" :max="100" /></div>
      <div v-if="stats.gpuPercent >= 0" class="row"><span class="dim">{{ t('app.monitor.gpu') }}</span><span>{{ Math.round(stats.gpuPercent) || 0 }} %</span><Sparkline :values="history.gpu" :max="100" /></div>
      <div class="row"><span class="dim">{{ t('app.monitor.used') }}</span><span>{{ gb(stats.usedGb) }} / {{ gb(stats.totalGb) }}</span><span /></div>
      <div class="row"><span class="dim">{{ t('app.monitor.swap') }}</span><span>{{ gb(stats.swapGb) }}</span><span /></div>
      <div class="row"><span class="dim">{{ t('app.monitor.streamCache') }}</span><span>{{ gb(stats.streamCacheGb) }}</span><span /></div>
    </section>
  </main>
</template>

<style scoped>
.monitor {
  display: grid;
  gap: 12px;
  padding: 44px 16px 16px;  /* below the window's traffic lights */
  min-height: 100vh;
  max-width: 640px;
  align-content: start;
  -webkit-app-region: drag;
}

.monitor > * {
  -webkit-app-region: no-drag;
}

h1 {
  font-size: 15px;
  margin: 0;
}

h2,
h3 {
  font-size: 13px;
  margin: 0 0 6px;
}

h3 {
  margin-top: 8px;
}

.card {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
}

.model {
  font-weight: 600;
}

.pair {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.row {
  display: grid;
  grid-template-columns: 1fr auto 160px;
  gap: 12px;
  align-items: center;
}

.better {
  color: var(--ok);
}

.worse {
  color: var(--accent);
}

.bad {
  color: var(--danger);
}
</style>
