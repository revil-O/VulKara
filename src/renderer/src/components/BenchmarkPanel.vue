<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Benchmark of one model (Hardware page): a few pictures with the model's own settings through the queue, then the
// time to the first step, seconds per step, the whole time and the memory and swap the Mac used meanwhile.
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { Check, Copy, Gauge, Square, Trash2 } from '@lucide/vue'
import type { BenchmarkRun, Waited } from '@shared/api'
import HintBadge from './HintBadge.vue'
import { useAssetsStore } from '../stores/assets'
import { gb, useSystemStore } from '../stores/system'
import { dateLocale, num, t } from '../i18n'
import { modelsFor } from '../util/job_form'
import { benchmarkJob, benchmarkTable, swapGrowth } from '../util/benchmark'
import { formatDuration } from '../util/format'

const assets = useAssetsStore()
const system = useSystemStore()
const runs = ref<BenchmarkRun[]>([])
const modelId = ref('')
const size = ref(0)
const count = ref(2)
const freshPrompt = ref(false)
const error = ref('')
const copied = ref(false)

const models = computed(() => modelsFor('text', assets.models))
const model = computed(() => models.value.find((m) => m.id === modelId.value) ?? models.value[0])
const busy = computed(() => runs.value.some((r) => r.state === 'waiting' || r.state === 'running'))
let off: (() => void) | undefined

onMounted(async () => {
  off = window.vk.benchmark.onChange((list) => { runs.value = list })
  runs.value = await window.vk.benchmark.list()
  if (!assets.all.length) await assets.refresh()
})
onUnmounted(() => off?.())

async function start(): Promise<void> {
  const m = model.value
  if (!m) return
  error.value = ''
  try {
    await window.vk.benchmark.start(benchmarkJob(m, size.value), count.value, m.title, freshPrompt.value)
  } catch (err) {
    error.value = (err as Error).message.replace(/^Error invoking remote method '[^']+': (Error: )?/, '')
  }
}

async function copyTable(): Promise<void> {
  await navigator.clipboard.writeText(benchmarkTable(runs.value, system.hardware))
  copied.value = true
  setTimeout(() => (copied.value = false), 1500)
}

const clear = (): Promise<void> => window.vk.benchmark.clear()
/** stops the benchmark: the main process stops all its pictures together */
async function stop(): Promise<void> {
  const r = runs.value.find((x) => x.state === 'running') ?? runs.value.find((x) => x.state === 'waiting')
  if (r) await window.vk.queue.cancel(r.id)
}
/** what the steps waited for, in the app's language */
const waitedText = (w: Waited): string => (w.what === 'ssd_stream' ? t('hardware.bench.waitedSsd', { gb: gb(w.gb) }) : w.what)

const seconds = (n?: number, digits = 1): string => (n === undefined ? '–' : `${num(n, digits)} s`)
const when = (at: number): string => new Date(at).toLocaleString(dateLocale(), { dateStyle: 'short', timeStyle: 'short' })
const STATES = { waiting: 'jobs.waiting', running: 'hardware.bench.running', done: 'jobs.done', failed: 'hardware.bench.failed', cancelled: 'jobs.cancelled' } as const
</script>

<template>
  <section>
    <h2>{{ t('hardware.bench.title') }} <HintBadge start :text="t('hardware.bench.hint')" /></h2>
    <div class="card rows">
      <div class="controls">
        <label class="field">
          <span>{{ t('hardware.bench.model') }}</span>
          <select :value="model?.id" @change="modelId = ($event.target as HTMLSelectElement).value">
            <option v-for="m in models" :key="m.id" :value="m.id">{{ m.title }}</option>
          </select>
        </label>
        <label class="field">
          <span>{{ t('hardware.bench.size') }}</span>
          <select v-model.number="size">
            <option :value="0">{{ t('hardware.bench.ownSize') }}</option>
            <option v-for="s in [512, 768, 1024]" :key="s" :value="s">{{ s }} × {{ s }}</option>
          </select>
        </label>
        <label class="field">
          <span>{{ t('hardware.bench.pictures') }}</span>
          <select v-model.number="count">
            <option v-for="n in [1, 2, 3]" :key="n" :value="n">{{ n }}</option>
          </select>
        </label>
        <label class="check">
          <input v-model="freshPrompt" type="checkbox" /> {{ t('hardware.bench.freshPrompt') }}
          <HintBadge :text="t('hardware.bench.freshPromptHint')" />
        </label>
        <button v-if="busy" class="btn" @click="stop"><Square :size="13" /> {{ t('hardware.bench.stop') }}</button>
        <button v-else class="btn primary" :disabled="!model" @click="start"><Gauge :size="14" /> {{ t('hardware.bench.start') }}</button>
      </div>
      <small v-if="error" class="error">{{ error }}</small>
      <small class="dim">{{ t('hardware.bench.how') }}</small>

      <!-- one block per run: what ran, then its size, time, memory and phases in areas of their own -->
      <div v-if="runs.length" class="runs">
        <article v-for="r in runs" :key="r.id" class="run" :class="r.state">
          <header>
            <strong>{{ r.model }}</strong>
            <span class="dim small">{{ when(r.at) }} · {{ t(STATES[r.state]) }}</span>
            <span v-if="r.build" class="dim build selectable">{{ r.build }}</span>
          </header>
          <div class="areas">
            <section class="area">
              <h3>{{ t('hardware.bench.sizeBits') }} <HintBadge :text="t('hardware.bench.bitsHint')" /></h3>
              <div>{{ r.width }}×{{ r.height }}<span v-if="r.steps" class="dim"> · {{ t('jobs.steps', { n: r.steps }) }}</span></div>
              <div v-if="r.precision" class="dim small">
                {{ r.precision }}
                <HintBadge v-if="!r.precision.includes('text encoder')" :text="t('hardware.bench.bitsPartial')" />
              </div>
            </section>
            <section class="area">
              <h3>{{ t('hardware.bench.time') }}</h3>
              <div class="pair"><span class="dim">{{ t('hardware.bench.perStep') }}</span><strong>{{ seconds(r.secondsPerStep, 2) }}</strong></div>
              <div class="pair"><span class="dim">{{ t('hardware.bench.total') }}</span><span>{{ seconds(r.seconds) }}</span></div>
            </section>
            <section class="area">
              <h3>{{ t('hardware.bench.memory') }} <HintBadge :text="t('hardware.bench.memoryHint')" /></h3>
              <div v-if="r.footprint" class="pair">
                <span class="dim">{{ t('hardware.bench.enginePeak') }}</span>
                <span :class="{ accent: r.footprint.planGb !== undefined && r.footprint.peakGb > r.footprint.planGb + 0.5 }">
                  {{ gb(r.footprint.peakGb) }}<span v-if="r.footprint.planGb !== undefined" class="dim"> · {{ t('hardware.bench.planned', { gb: gb(r.footprint.planGb) }) }}</span>
                </span>
              </div>
              <div class="pair"><span class="dim">{{ t('hardware.bench.peakApp') }}</span><span>{{ gb(r.peakAppGb) }}</span></div>
              <div class="pair"><span class="dim">{{ t('hardware.bench.peakSystem') }}</span><span>{{ gb(r.peakUsedGb) }} / {{ gb(r.totalGb) }}</span></div>
              <div class="pair">
                <span class="dim">{{ t('hardware.bench.swap') }}</span>
                <span :class="{ accent: (swapGrowth(r) ?? 0) >= 0.5 }">{{ swapGrowth(r) === undefined ? '–' : `+${gb(swapGrowth(r)!)}` }}</span>
              </div>
              <div v-if="r.diskReadGb !== undefined" class="pair"><span class="dim">{{ t('hardware.bench.diskRead') }}</span><span>{{ gb(r.diskReadGb) }}</span></div>
              <div v-if="r.swapReadGb !== undefined" class="pair">
                <span class="dim">{{ t('hardware.bench.swapRead') }}</span>
                <span :class="{ accent: r.swapReadGb >= 0.5 }">{{ gb(r.swapReadGb) }}</span>
              </div>
            </section>
            <section class="area phases selectable">
              <h3>{{ t('hardware.bench.phases') }} <HintBadge :text="t('hardware.bench.phasesHint')" /></h3>
              <div v-for="(p, i) in r.phases" :key="i" class="phase small">
                <span class="time">{{ p.seconds >= 0 ? formatDuration(p.seconds) : '' }}</span>
                <span>{{ p.text }} <HintBadge v-if="p.text.includes('(MLX')" :text="t('hardware.bench.mlxLoading')" /></span>
              </div>
              <div v-for="w in r.waited ?? []" :key="w.what" class="phase small waited">
                <span class="time">{{ formatDuration(w.seconds) }}</span>
                <span>{{ waitedText(w) }} <HintBadge :text="t('hardware.bench.waitedHint')" /></span>
              </div>
            </section>
          </div>
          <p v-if="r.note || r.error" class="dim small selectable note">
            <span v-if="r.error" class="error">{{ r.error }}</span><span v-if="r.error && r.note"> · </span>{{ r.note }}
          </p>
        </article>
      </div>
      <div v-if="runs.length" class="row end">
        <button class="btn small" @click="copyTable"><component :is="copied ? Check : Copy" :size="13" /> {{ copied ? t('hardware.copied') : t('hardware.bench.copy') }}</button>
        <button class="btn small" :disabled="busy" @click="clear"><Trash2 :size="13" /> {{ t('hardware.bench.clear') }}</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
section {
  display: grid;
  gap: 8px;
}

h2 {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  margin: 0;
}

.rows {
  display: grid;
  gap: 10px;
  padding: 12px 16px;
}

.controls {
  display: grid;
  grid-template-columns: minmax(200px, 2fr) minmax(140px, 1fr) minmax(80px, 0.5fr) auto auto;
  gap: 12px;
  align-items: end;
}

.runs {
  display: grid;
  gap: 10px;
}

.run {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
}

.run.failed {
  border-color: var(--accent);
}

.run header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
}

.areas {
  display: grid;
  grid-template-columns: minmax(150px, 1fr) minmax(170px, 1fr) minmax(210px, 1.2fr) minmax(240px, 1.6fr);
  gap: 8px;
}

@media (max-width: 1100px) {
  .areas {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

.area {
  display: grid;
  align-content: start;
  gap: 3px;
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--surface-2);
  font-size: 13px;
}

.area h3 {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 0 0 2px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-dim);
}

.note {
  margin: 0;
}

.small {
  font-size: 12px;
}

/* a label and its figure in one line of a cell */
.pair {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

/* the time first, so that it stays in view however long the text is */
.phase {
  display: grid;
  grid-template-columns: 4.5em 1fr;
  gap: 8px;
}

.waited {
  font-style: italic;
}

.phase .time {
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  color: var(--text-dim);
}

.build {
  font-family: var(--mono, ui-monospace, monospace);
  font-size: 11px;
  word-break: break-word;
}

.accent {
  color: var(--accent);
}

.row {
  display: flex;
  gap: 8px;
}

.row.end {
  justify-content: flex-end;
}
.check {
  display: flex;
  gap: 6px;
  align-items: center;
}

.check input {
  accent-color: var(--accent);
}
</style>
