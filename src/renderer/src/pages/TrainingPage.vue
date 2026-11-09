<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Training a LoRA on own pictures: a name, a trigger word, the model to train on, the pictures with captions
// and a few numbers. The training itself runs in the main process; this page shows how far it is.
import { computed, onActivated, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Flame, FolderOpen, ImagePlus, Play, Square, X } from '@lucide/vue'
import PageFrame from '../components/PageFrame.vue'
import BakeDialog from '../components/BakeDialog.vue'
import { useAssetsStore } from '../stores/assets'
import { useHandoffStore } from '../stores/handoff'
import { useQueueStore } from '../stores/queue'
import { cleanError } from '../stores/runtimes'
import { formatDuration } from '../util/format'
import type { TrainingImage, TrainingState } from '@shared/api'
import { t, type PlainKey } from '../i18n'

const TRAINABLE = ['sdxl', 'flux2_klein', 'krea2']
const PRESETS: { id: string; title: PlainKey; steps: number }[] = [
  { id: 'quick', title: 'training.presets.quick', steps: 100 }, { id: 'standard', title: 'training.presets.standard', steps: 500 },
  { id: 'thorough', title: 'training.presets.thorough', steps: 1200 },
]
// seconds per training step on an M2 with 10 GPU cores at 512 px (it grows with the number of pixels)
const SECONDS_PER_STEP: Record<string, number> = { sdxl: 2.5, flux2_klein_4b: 15, flux2_klein_9b: 30, krea2: 45 }

const assets = useAssetsStore()
const queue = useQueueStore()
const handoff = useHandoffStore()
const router = useRouter()

const name = ref('')
const trigger = ref('')
let triggerEdited = false
const baseId = ref('')
const images = ref<TrainingImage[]>([])
const preset = ref('standard')
const steps = ref(500)
const resolution = ref(512)
const rank = ref(16)
const learningRate = ref(0.0001)
const state = ref<TrainingState>({ running: false, losses: [] })
const error = ref('')

const baseModels = computed(() => assets.models.filter((m) => TRAINABLE.includes(m.meta.arch)))
const base = computed(() => baseModels.value.find((m) => m.id === baseId.value))
const autoTrigger = (n: string): string => (n ? n.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '') + '_zqx' : '')
const blocked = computed(() => (queue.running ? t('training.blocked') : ''))
const canStart = computed(() => !state.value.running && !blocked.value && !!base.value && images.value.length > 0 && !!name.value.trim())
const percent = computed(() => (state.value.total ? Math.round((100 * (state.value.step ?? 0)) / state.value.total) : 0))
const PHASES: Record<string, PlainKey> = { loading: 'training.phases.loading', preparing: 'training.phases.preparing', training: 'training.phases.training' }
const phaseText = computed(() => state.value.message
  ?? (PHASES[state.value.phase ?? ''] ? t(PHASES[state.value.phase ?? '']) : ''))

const estimate = computed(() => {
  const b = base.value
  if (!b) return ''
  const key = b.meta.arch === 'sdxl' ? 'sdxl' : b.meta.arch === 'krea2' ? 'krea2' : /9b/i.test(b.id) ? 'flux2_klein_9b' : 'flux2_klein_4b'
  const seconds = SECONDS_PER_STEP[key] * (resolution.value / 512) ** 2 * steps.value
  return t('training.estimate', { duration: formatDuration(seconds) })
})

// the loss of every step as a line; lower is better, but it jumps a lot from step to step
const lossLine = computed(() => {
  const l = state.value.losses
  if (l.length < 3) return ''
  const [max, min] = [Math.max(...l), Math.min(...l)]
  return l.map((v, i) => `${((i * 300) / (l.length - 1)).toFixed(1)},${(75 - (70 * (v - min)) / (max - min || 1)).toFixed(1)}`).join(' ')
})

watch(name, (n) => {
  if (!triggerEdited) trigger.value = autoTrigger(n)
})
watch(trigger, (word) => {
  triggerEdited = !!word && word !== autoTrigger(name.value)
})
watch(base, (b) => {
  // FLUX.2 and Krea 2 learn well at 512 px; SDXL is made for 1024, 768 is a good middle
  if (b && !state.value.running) resolution.value = b.meta.arch === 'sdxl' ? 768 : 512
})

async function refresh(): Promise<void> {
  await assets.refresh()
  if (!base.value && baseModels.value.length) baseId.value = baseModels.value[0].id
  state.value = await window.vk.training.state()
}
const stopListening = window.vk.training.onChange((s) => { state.value = s })
onBeforeUnmount(stopListening)
onActivated(refresh)

function setPreset(id: string): void {
  preset.value = id
  steps.value = PRESETS.find((p) => p.id === id)?.steps ?? steps.value
}

function addImages(items: TrainingImage[]): void {
  const known = new Set(images.value.map((i) => i.path))
  images.value = [...images.value, ...items.filter((i) => !known.has(i.path))]
}

const addPictures = async (): Promise<void> => addImages((await window.vk.training.choosePictures()).map((path) => ({ path, caption: '' })))
const addFolder = async (): Promise<void> => addImages(await window.vk.training.chooseFolder())

async function start(): Promise<void> {
  if (!canStart.value || !base.value) return
  error.value = ''
  try {
    await window.vk.training.start({
      name: name.value.trim(), trigger: trigger.value.trim(), baseModel: base.value.folder,
      images: images.value.map((i) => ({ path: i.path, caption: i.caption })),
      resolution: resolution.value, steps: steps.value, rank: rank.value, learningRate: learningRate.value,
    })
  } catch (err) {
    error.value = cleanError(err)
  }
}

/** The new LoRA in the strength comparison of the LoRA page. */
// the LoRA just trained, as an asset (for baking it into a model)
const baking = ref(false)
const trainedLoraId = computed(() => assets.loras.find((l) => l.folder === state.value.result?.folder)?.id)

function compare(): void {
  const folder = state.value.result?.folder
  if (!folder) return
  handoff.send('lora', { loraFolder: folder })
  void router.push('/lora')
}

const stop = (): Promise<void> => window.vk.training.stop()
const url = (path: string): string => window.vk.files.url(path)
</script>

<template>
  <PageFrame :title="t('training.title')" :subtitle="t('training.subtitle')">
    <div class="form">
      <p class="dim">
        {{ t('training.intro') }}
        {{ t('training.captionsBefore') }} <em>{{ t('training.captionsNot') }}</em> {{ t('training.captionsAfter') }}
      </p>

      <div class="two">
        <label class="field"><span>{{ t('training.name') }}</span><input v-model="name" type="text" :placeholder="t('training.namePlaceholder')" :disabled="state.running" spellcheck="false" /></label>
        <label class="field"><span>{{ t('training.trigger') }}</span><input v-model="trigger" type="text" :placeholder="t('training.triggerPlaceholder')" :disabled="state.running" spellcheck="false" /></label>
      </div>

      <label class="field">
        <span>{{ t('training.model') }}</span>
        <select v-model="baseId" :disabled="state.running">
          <option v-for="m in baseModels" :key="m.id" :value="m.id">{{ m.title }} ({{ m.meta.label }} · {{ m.meta.arch === 'sdxl' ? 'Diffusers' : 'MLX' }})</option>
        </select>
        <small v-if="!baseModels.length" class="warn">{{ t('training.noModel') }}</small>
      </label>

      <div class="field">
        <span>{{ t('training.pictures') }} <b>{{ images.length }}</b></span>
        <div class="line">
          <button class="btn small" :disabled="state.running" @click="addPictures"><ImagePlus :size="12" /> {{ t('training.addPictures') }}</button>
          <button class="btn small" :disabled="state.running" :title="t('training.addFolderHint')" @click="addFolder"><FolderOpen :size="12" /> {{ t('training.addFolder') }}</button>
          <button v-if="images.length" class="btn small ghost" :disabled="state.running" @click="images = []">{{ t('training.removeAll') }}</button>
        </div>
        <div v-if="images.length" class="pictures">
          <div v-for="(im, i) in images" :key="im.path" class="picture">
            <img :src="url(im.path)" loading="lazy" draggable="false" />
            <textarea v-model="im.caption" rows="2" :disabled="state.running" :placeholder="t('training.captionPlaceholder')" spellcheck="false" />
            <button class="btn small remove" :title="t('training.remove')" :disabled="state.running" @click="images.splice(i, 1)"><X :size="11" /></button>
          </div>
        </div>
        <small v-if="images.length && trigger" class="dim">{{ t('training.captionStart', { trigger }) }}</small>
      </div>

      <div class="field">
        <span>{{ t('training.training') }}</span>
        <div class="line">
          <button v-for="p in PRESETS" :key="p.id" class="chip" :class="{ on: preset === p.id && steps === p.steps }" :disabled="state.running" @click="setPreset(p.id)">
            {{ t(p.title) }} <small class="dim">{{ t('training.stepsCount', { n: p.steps }) }}</small>
          </button>
        </div>
        <div class="four">
          <label class="field"><small>{{ t('training.steps') }}</small><input v-model.number="steps" type="number" min="10" max="5000" :disabled="state.running" /></label>
          <label class="field"><small>{{ t('training.resolution') }}</small>
            <select v-model.number="resolution" :disabled="state.running"><option :value="512">512 px</option><option :value="768">768 px</option><option :value="1024">1024 px</option></select>
          </label>
          <label class="field"><small>{{ t('training.rank') }}</small>
            <select v-model.number="rank" :disabled="state.running"><option :value="8">8</option><option :value="16">16</option><option :value="32">32</option></select>
          </label>
          <label class="field"><small>{{ t('training.learningRate') }}</small><input v-model.number="learningRate" type="number" step="0.00001" :disabled="state.running" /></label>
        </div>
        <small class="dim">{{ estimate }}</small>
      </div>

      <div class="line">
        <button v-if="!state.running" class="btn primary" :disabled="!canStart" @click="start"><Play :size="14" /> {{ t('training.start') }}</button>
        <button v-else class="btn danger" @click="stop"><Square :size="12" /> {{ t('training.stop') }}</button>
        <span v-if="blocked && !state.running" class="warn">{{ blocked }}</span>
        <span v-if="error" class="error selectable">{{ error }}</span>
      </div>
    </div>

    <template #panel>
      <div class="status">
        <template v-if="state.running || state.phase">
          <h2>{{ state.running ? t('training.trainingName', { name: state.name ?? '' }) : t('training.lastTraining') }}</h2>
          <p>{{ phaseText }}</p>
          <template v-if="state.total">
            <div class="bar"><i :style="{ width: percent + '%' }" /></div>
            <p class="dim numbers">
              {{ t('training.stepOf', { step: state.step ?? '', total: state.total }) }}<template v-if="state.loss !== undefined"> · {{ t('training.loss', { loss: state.loss }) }}</template>
              <template v-if="state.eta !== undefined && state.running"> · {{ t('training.left', { duration: formatDuration(state.eta) }) }}</template>
            </p>
          </template>
          <svg v-if="lossLine" class="chart" viewBox="0 0 300 80" preserveAspectRatio="none"><polyline :points="lossLine" fill="none" stroke="var(--accent)" stroke-width="1.5" /></svg>
        </template>
        <div v-if="state.result" class="card done">
          <h2>{{ t('training.ready') }}</h2>
          <p><strong>{{ state.result.name }}</strong> · {{ t('training.triggerWord', { word: state.result.trigger || '–' }) }}</p>
          <p class="dim">{{ t('training.readyHint') }}</p>
          <div class="line">
            <button class="btn primary" @click="compare">{{ t('training.compare') }}</button>
            <button class="btn" :disabled="!trainedLoraId" @click="baking = true"><Flame :size="14" /> {{ t('training.bake') }}</button>
          </div>
          <BakeDialog v-if="baking && trainedLoraId" :lora-ids="[trainedLoraId]" :model-id="baseId" @close="baking = false" />
        </div>
        <p v-if="state.stopped" class="dim">{{ t('training.stopped') }}</p>
        <p v-if="state.error" class="error selectable">{{ state.error }}</p>
        <div v-if="!state.running && !state.phase" class="dim hint">
          <p>{{ t('training.hintStart') }}</p>
          <p>{{ t('training.hintSpeed') }}</p>
        </div>
      </div>
    </template>
  </PageFrame>
</template>

<style scoped>
.form {
  display: grid;
  gap: 18px;
  max-width: 900px;
}

.field > span {
  display: flex;
  gap: 8px;
}

.field b {
  font-weight: 400;
  color: var(--text-dim);
}

.two {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.four {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
}

.line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

input[type='text'],
input[type='number'],
select,
textarea {
  width: 100%;
}

textarea {
  min-width: 0;
  padding: 6px 8px;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface-2);
  color: inherit;
  font: inherit;
  font-size: 12px;
  user-select: text;
  resize: vertical;
}

.pictures {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}

.picture {
  position: relative;
  display: grid;
  gap: 4px;
}

.picture img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: var(--radius-s);
}

.remove {
  position: absolute;
  top: 4px;
  right: 4px;
  padding: 0 5px;
}

.chip {
  padding: 4px 10px;
}

.warn {
  color: var(--accent);
}

.status {
  display: grid;
  gap: 10px;
}

.numbers {
  font-variant-numeric: tabular-nums;
}

.chart {
  width: 100%;
  height: 80px;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
}

.done {
  display: grid;
  gap: 8px;
  padding: 12px;
}

.hint {
  display: grid;
  gap: 8px;
}
</style>
