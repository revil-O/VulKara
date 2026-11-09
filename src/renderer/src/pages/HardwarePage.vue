<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// This Mac: chip, cores, memory and the GPU, what VulKara is using right now, the room on the SSD for streaming, and
// the settings that keep the Mac responsive (the guard rails), each with a way to Settings.
import { computed, onActivated, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Check, Copy } from '@lucide/vue'
import PageFrame from '../components/PageFrame.vue'
import HintBadge from '../components/HintBadge.vue'
import LevelMeter from '../components/LevelMeter.vue'
import BenchmarkPanel from '../components/BenchmarkPanel.vue'
import { useSettingsStore } from '../stores/settings'
import { gb, useSystemStore } from '../stores/system'
import { num, t, type PlainKey } from '../i18n'
import { translate } from '@shared/i18n'

const system = useSystemStore()
const router = useRouter()
const settings = useSettingsStore()
const info = ref<{ mac: string; os: string }>()
const copied = ref(false)

onActivated(async () => {
  await Promise.all([system.start(), system.loadHardware(), settings.load()])
  info.value ??= await window.vk.app.info()
})

const hw = computed(() => system.hardware)
const st = computed(() => system.stats)
/** the memory kept free, in the app's language or in English (en) */
function reserveText(en = false): string {
  const set = settings.values.memoryReserveGb
  if (set > 0) return `${set} GB`
  const auto = { gb: Math.max(4, Math.round((hw.value?.ramGb ?? 0) * 0.2)) }
  return en ? translate('en', 'hardware.guard.reserveAuto', auto) : t('hardware.guard.reserveAuto', auto)
}
const reserve = computed(() => reserveText())
const budget = computed(() => {
  const ram = hw.value?.ramGb ?? 0
  const set = settings.values.memoryReserveGb
  return ram - (set > 0 ? set : Math.max(4, Math.round(ram * 0.2)))
})
const STREAMING: Record<string, PlainKey> = { auto: 'hardware.streaming.auto', always: 'hardware.streaming.always', off: 'hardware.streaming.off' }
const CACHE: Record<string, PlainKey> = { off: 'hardware.cache.off', light: 'hardware.cache.light', strong: 'hardware.cache.strong' }
const pct = (part: number, whole: number): number => (whole ? Math.min(100, (100 * part) / whole) : 0)

async function copyInfo(): Promise<void> {
  const h = hw.value
  const s = st.value
  if (!h) return
  // English, like the problem report: for pasting into an issue
  const en = (key: PlainKey): string => translate('en', key)
  const lines = [
    `VulKara on ${info.value?.mac ?? ''} · ${info.value?.os ?? ''}`, // i18n-ok
    `Chip: ${h.chip} (${h.arch}), ${h.performanceCores} performance + ${h.efficiencyCores} efficiency cores, ${h.gpuCores ?? '?'} GPU cores`, // i18n-ok
    `Memory: ${h.ramGb} GB unified, Metal budget about ${h.metalBudgetGb} GB, kept free ${reserveText(true)}`, // i18n-ok
    s ? `Now: VulKara ${gb(s.appGb)}, system ${gb(s.usedGb)} of ${gb(s.totalGb)}, swap ${gb(s.swapGb)}, CPU ${s.cpuPercent.toFixed(1)} %${s.gpuPercent >= 0 ? `, GPU ${s.gpuPercent} %` : ''}` : '', // i18n-ok
    s ? `Streaming caches: ${gb(s.streamCacheGb)} in ${s.streamWhere}, ${gb(s.streamFreeGb)} free` : '', // i18n-ok
    `Settings: SSD streaming ${en(STREAMING[settings.values.ssdStreaming])}, step caching ${en(CACHE[settings.values.stepCache])}, runtime ${settings.values.runtime}`, // i18n-ok
  ].filter(Boolean)
  await navigator.clipboard.writeText(lines.join('\n'))
  copied.value = true
  setTimeout(() => (copied.value = false), 1500)
}
</script>

<template>
  <PageFrame :title="t('hardware.title')" :subtitle="info ? `${info.mac} · ${info.os}` : t('hardware.thisMac')">
    <div v-if="hw" class="hardware">
      <div class="grid">
        <section>
          <!-- i18n-ok -->
          <h2>CPU <HintBadge start :text="t('hardware.cpu.hint')" /></h2>
          <div class="card rows">
            <div class="row"><span>{{ t('hardware.cpu.name') }}</span><strong>{{ hw.chip }}</strong></div>
            <!-- i18n-ok -->
            <div class="row"><span>{{ t('hardware.cpu.architecture') }}</span><span class="tags"><span class="tag">{{ hw.arch.toUpperCase() }}</span><span v-if="hw.metal" class="tag">Metal</span></span></div>
            <div class="row"><span>{{ t('hardware.cpu.cores') }}</span><strong>{{ hw.totalCores }}<span class="dim"> · {{ t('hardware.cpu.coreSplit', { performance: hw.performanceCores, efficiency: hw.efficiencyCores }) }}</span></strong></div>
          </div>
        </section>
        <section>
          <h2>{{ t('hardware.memory.title') }} <HintBadge start :text="t('hardware.memory.hint')" /></h2>
          <div class="card rows">
            <div class="row"><span>{{ t('hardware.memory.unified') }}</span><strong>{{ hw.ramGb }} GB</strong></div>
            <div class="row"><span>{{ t('hardware.memory.gpuBudget') }}</span><strong>{{ t('hardware.memory.about', { gb: hw.metalBudgetGb }) }}</strong></div>
            <div class="row"><span>{{ t('hardware.memory.forModels') }}</span><strong>{{ budget }} GB</strong></div>
          </div>
        </section>
      </div>

      <section>
        <!-- i18n-ok -->
        <h2>GPU</h2>
        <div class="card rows">
          <div class="row"><span>{{ hw.chip }}</span><strong>{{ hw.gpuCores ? t('hardware.gpu.cores', { n: hw.gpuCores }) : '' }}<span class="dim"> · {{ t('hardware.gpu.metalUnified') }}</span></strong></div>
          <div class="row"><span>{{ t('hardware.gpu.enginesOn') }}</span><span class="dim">{{ t('hardware.gpu.engines') }}</span></div>
        </div>
      </section>

      <section>
        <h2>{{ t('hardware.monitor.title') }} <HintBadge start :text="t('hardware.monitor.hint')" /></h2>
        <div v-if="st" class="grid">
          <div class="card rows">
            <div class="row"><span>{{ t('hardware.monitor.app') }}</span><strong>{{ gb(st.appGb) }}</strong></div>
            <div class="meter"><i :style="{ width: pct(st.appGb, st.totalGb) + '%' }" /></div>
            <div class="row"><span>{{ t('hardware.monitor.system') }}</span><strong>{{ gb(st.usedGb) }} <span class="dim">{{ t('hardware.monitor.of', { total: gb(st.totalGb) }) }}</span></strong></div>
            <div class="meter"><i class="soft" :style="{ width: pct(st.usedGb, st.totalGb) + '%' }" /></div>
            <div class="row"><span>{{ t('hardware.monitor.swap') }}</span><strong>{{ gb(st.swapGb) }}</strong></div>
          </div>
          <div class="card rows">
            <!-- i18n-ok -->
            <div class="row"><span>CPU</span><strong class="accent">{{ num(st.cpuPercent, 1) }} %</strong></div>
            <LevelMeter class="cpu" :value="st.cpuPercent" :segments="80" :height="14" :width="3" :gap="1" />
            <template v-if="st.gpuPercent >= 0">
              <!-- i18n-ok -->
              <div class="row"><span>GPU</span><strong class="accent">{{ st.gpuPercent }} %</strong></div>
              <LevelMeter class="cpu" :value="st.gpuPercent" :segments="80" :height="14" :width="3" :gap="1" />
            </template>
            <div class="row"><span>{{ t('hardware.monitor.streamCaches') }}</span><strong>{{ gb(st.streamCacheGb) }}</strong></div>
            <div class="row">
              <span>{{ t('hardware.monitor.freeThere') }}</span>
              <strong :class="{ accent: st.streamFreeGb < 20 }">{{ gb(st.streamFreeGb) }}</strong>
            </div>
            <p class="dim path selectable">{{ st.streamWhere }}</p>
          </div>
        </div>
      </section>

      <section>
        <h2>{{ t('hardware.guard.title') }} <HintBadge start :text="t('hardware.guard.hint')" /></h2>
        <div class="card rows">
          <div class="row"><span>{{ t('hardware.guard.reserve') }}</span><strong>{{ reserve }}</strong></div>
          <div class="row"><span>{{ t('hardware.guard.larger') }}</span><strong>{{ t('hardware.guard.ssdStreaming', { mode: t(STREAMING[settings.values.ssdStreaming]) }) }}</strong></div>
          <div class="row"><span>{{ t('hardware.guard.stepCaching') }}</span><strong>{{ t(CACHE[settings.values.stepCache]) }}</strong></div>
          <div class="row"><span>{{ t('hardware.guard.runtime') }}</span><strong>{{ settings.values.runtime === 'auto' ? t('hardware.guard.automatic') : settings.values.runtime === 'mlx' ? 'MLX' : 'Diffusers' }}</strong></div>
          <div class="row end"><button class="btn small" @click="router.push('/settings')">{{ t('hardware.guard.change') }}</button></div>
        </div>
      </section>

      <BenchmarkPanel />

      <div class="actions">
        <button class="btn" @click="copyInfo"><component :is="copied ? Check : Copy" :size="14" /> {{ copied ? t('hardware.copied') : t('hardware.copyInfo') }}</button>
      </div>
    </div>
  </PageFrame>
</template>

<style scoped>
.hardware {
  display: grid;
  gap: 20px;
  max-width: 1100px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(380px, 1fr));
  gap: 16px;
}

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
  gap: 8px;
  padding: 12px 16px;
}

.row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 16px;
}

.row.end {
  justify-content: flex-end;
}

.row > span:first-child {
  color: var(--text-dim);
}

.tags {
  display: flex;
  gap: 6px;
}

.accent {
  color: var(--accent);
}

.meter {
  height: 6px;
  border-radius: 3px;
  background: var(--surface-2);
  overflow: hidden;
}

.meter i {
  display: block;
  height: 100%;
  background: var(--accent);
  transition: width 0.6s;
}

.meter i.soft {
  opacity: 0.45;
}

.cpu {
  justify-content: space-between;
}

.path {
  margin: 0;
  font-size: 12px;
  word-break: break-all;
}

.actions {
  display: flex;
  justify-content: flex-end;
}
</style>
