<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Restoring old photos: colour cast and contrast are corrected without a model; repairing (scratches, creases, spots,
// holes) is done by a FLUX.2 model, held to guard rails: fixed rules and the user's own for the model, the original kept
// outside the painted damage, a check of the change and the faces. Colouring is done by DDColor, which adds colour to the
// brightness of the photo and so can not change a shape; sharpening lessens grain and crisps details. Soft detail of the
// whole photo is rebuilt by Real-ESRGAN, faces by CodeFormer; a preview restores only a part of the photo, and the
// compare slider shows the change (left of the line) against the original (right).
import { computed, onActivated, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { BookmarkPlus, Eye, Plus, ShieldCheck, WandSparkles, X } from '@lucide/vue'
import PageFrame from '../components/PageFrame.vue'
import CompareSlider from '../components/CompareSlider.vue'
import FaceBoxes, { type Face } from '../components/FaceBoxes.vue'
import HintBadge from '../components/HintBadge.vue'
import ImageInput from '../components/ImageInput.vue'
import MaskCanvas from '../components/MaskCanvas.vue'
import SliderRow from '../components/SliderRow.vue'
import JobGallery from '../components/JobGallery.vue'
import { useAssetsStore } from '../stores/assets'
import { useHandoffStore } from '../stores/handoff'
import { useQueueStore } from '../stores/queue'
import { cleanError } from '../stores/runtimes'
import { useSettingsStore } from '../stores/settings'
import { num, t, type PlainKey } from '../i18n'
import { isMonochrome } from '../util/monochrome'
import { kleinTints, takesConsistency } from '@shared/hints'
import type { QueuedJob } from '@shared/api'
import type { RestoreTemplate } from '@shared/settings'
import type { Job, RestoreOptions } from '@shared/types'

// the rules the model always gets (engines/diffusers/restore.py BASE_RULES, shortened)
const FIXED_RULES: PlainKey[] = [
  'restore.fixedRules.onlyDamage',
  'restore.fixedRules.composition',
  'restore.fixedRules.people',
  'restore.fixedRules.objects',
  'restore.fixedRules.nothingNew',
]

// templates for the usual kinds of old photos; the user saves own ones
const GUARDS = { lock: true, maxChange: 0.06, checkFaces: true, colorStrength: 1, sharpen: false, sharpness: 0.25 }
// the AI steps for soft photos and faces, with the strengths that kept faces closest to themselves (MEASUREMENTS.md)
const AI_STEPS = { correctStrength: 0.8, dust: true, dustSensitivity: 0.5, details: true, detailLevel: 2, detailStrength: 1, faces: true, faceFidelity: 0.9, faceStrength: 0.6, scale: 1 as const }
const TEMPLATES: RestoreTemplate[] = [
  { name: 'Black and white, damaged', correct: true, repair: true, colorize: false, ...GUARDS, note: 'an old black-and-white photograph' }, // i18n-ok
  { name: 'Black and white to colour', correct: true, repair: true, colorize: true, ...GUARDS, note: 'an old black-and-white photograph' }, // i18n-ok
  { name: 'Colour cast (red or yellow)', correct: true, repair: false, colorize: false, ...GUARDS, sharpen: false, note: '' }, // i18n-ok
  { name: 'Faded colour photo', correct: true, repair: true, colorize: false, ...GUARDS, note: 'a faded colour photograph from the 1970s' }, // i18n-ok
  { name: 'Only colour it', correct: false, repair: false, colorize: true, ...GUARDS, sharpen: false, note: '' }, // i18n-ok
  { name: 'Heavy damage (creases, holes)', correct: true, repair: true, colorize: false, ...GUARDS, maxChange: 0.1, note: 'a heavily creased old photograph with torn and missing pieces' }, // i18n-ok
]
// the templates' names as shown (the English name above is what is stored as the chosen template)
const TEMPLATE_TITLES: Record<string, PlainKey> = {
  'Black and white, damaged': 'restore.templates.bwDamaged', // i18n-ok
  'Black and white to colour': 'restore.templates.bwToColour', // i18n-ok
  'Colour cast (red or yellow)': 'restore.templates.colourCast', // i18n-ok
  'Faded colour photo': 'restore.templates.faded', // i18n-ok
  'Only colour it': 'restore.templates.onlyColour', // i18n-ok
  'Heavy damage (creases, holes)': 'restore.templates.heavyDamage', // i18n-ok
}

const assets = useAssetsStore()
const queue = useQueueStore()
const settings = useSettingsStore()
const handoff = useHandoffStore()
const route = useRoute()

const input = ref('')
const size = ref<[number, number]>()
const mask = ref<InstanceType<typeof MaskCanvas>>()
const painted = ref(false)
const grayscale = ref(false)
const monochrome = ref(false)
const opts = ref<RestoreOptions>({ correct: true, repair: false, colorize: false, colorStrength: 1, sharpen: false, sharpness: 0.25, lock: true, maxChange: 0.06, rules: [], checkFaces: true, consistency: true, ...AI_STEPS })
const modelId = ref('')
const steps = ref(4)
const note = ref('')
const newRule = ref('')
const error = ref('')
const sending = ref(false)
const template = ref('')
const templateName = ref('')

// the AI edits the photo: only FLUX.2 models take a picture as a reference for editing
const models = computed(() => assets.models.filter((m) => m.meta.family === 'flux2' && m.meta.kind === 'image'))
const model = computed(() => models.value.find((m) => m.id === modelId.value))
// the first FLUX.2 model is chosen until the user picks another one
watch(models, (list) => { if (!list.some((m) => m.id === modelId.value)) modelId.value = list[0]?.id ?? '' }, { immediate: true })
const usesAi = computed(() => opts.value.repair)
const tints = computed(() => kleinTints(monochrome.value, model.value?.meta))
// previews are shown in the compare slider, not as results
const jobs = computed(() => queue.ofPage('restore').filter((q) => !q.job.restore?.preview))
const previewJob = computed(() => queue.ofPage('restore').find((q) => q.job.restore?.preview && q.job.inputImage === input.value))
const userRules = computed(() => settings.values.restoreRules ?? [])
const ownTemplates = computed(() => settings.values.restoreTemplates ?? [])

function useTemplate(tp: RestoreTemplate): void {
  const { name, note: text, ...steps } = tp
  template.value = name
  opts.value = { ...opts.value, colorStrength: 1, sharpen: false, sharpness: 0.25, ...AI_STEPS, ...steps }
  note.value = text
}

async function saveTemplate(): Promise<void> {
  const name = templateName.value.replace(/\s+/g, ' ').trim()
  if (!name) return
  const { rules: _rules, ...steps } = opts.value
  const own = ownTemplates.value.filter((tp) => tp.name !== name)
  await settings.set('restoreTemplates', [...own, { name, ...steps, note: note.value.trim() }])
  template.value = name
  templateName.value = ''
}

// the value of a strength slider as it is shown
const percent = (v: number): string => `${Math.round(v * 100)} %`

const removeTemplate = (name: string): Promise<void> => settings.set('restoreTemplates', ownTemplates.value.filter((tp) => tp.name !== name))

async function refresh(): Promise<void> {
  await Promise.all([assets.refresh(), settings.load()])
  const given = handoff.take('restore')
  if (given?.inputImage) input.value = given.inputImage
}
onActivated(refresh)
watch(() => route.query.t, () => { if (route.path === '/restore') void refresh() })

/** A black-and-white (or toned) photo hardly has any saturation: then colouring is offered right away. */
function measure(event: Event): void {
  const img = event.target as HTMLImageElement
  const c = document.createElement('canvas')
  c.width = c.height = 64
  const ctx = c.getContext('2d')!
  ctx.drawImage(img, 0, 0, 64, 64)
  const d = ctx.getImageData(0, 0, 64, 64).data
  let sat = 0
  for (let i = 0; i < d.length; i += 4) {
    const max = Math.max(d[i], d[i + 1], d[i + 2])
    sat += max ? (max - Math.min(d[i], d[i + 1], d[i + 2])) / max : 0
  }
  grayscale.value = sat / (d.length / 4) < 0.08
  monochrome.value = isMonochrome(d)
  opts.value.colorize = grayscale.value
}

watch(input, () => {
  size.value = undefined
  painted.value = false
  error.value = ''
  shownBefore.value = ''
})

// ------------------------------------------------------------------ the faces CodeFormer will restore, movable
const faces = ref<Face[]>([])
const facesSize = ref<[number, number]>()
const facesState = ref<'' | 'finding' | 'found' | 'failed'>('')
const facesError = ref('')

async function findFaces(): Promise<void> {
  const path = input.value
  if (!path || !opts.value.faces) return
  facesState.value = 'finding'
  try {
    const found = await window.vk.restore.faces(path)
    if (path !== input.value) return
    faces.value = found.faces
    facesSize.value = found.size
    facesState.value = 'found'
  } catch (err) {
    if (path !== input.value) return
    facesError.value = cleanError(err)
    facesState.value = 'failed'
  }
}

watch([input, () => opts.value.faces], ([path, on], [before]) => {
  if (path !== before) {
    faces.value = []
    facesSize.value = undefined
    facesState.value = ''
  }
  if (path && on && facesState.value === '') void findFaces()
})

// ------------------------------------------------------------------ compare: the newest preview or result of this photo
const shownBefore = ref('')
const compare = computed(() => {
  const done = queue.ofPage('restore').find((q) => q.job.inputImage === input.value && q.state === 'done' && queue.shown(q).length)
  if (!done) return undefined
  const file = queue.shown(done)[0]
  return { after: window.vk.files.url(file), file, preview: !!done.job.restore?.preview }
})

/** The part of the original a preview shows (its file name tells it: preview_x…_y…_w…_h…_id.png), as a picture. */
async function cropOf(file: string): Promise<string> {
  const m = /preview_x(\d+)_y(\d+)_w(\d+)_h(\d+)_/.exec(file)
  const src = window.vk.files.url(input.value)
  if (!m) return src
  const [x, y, w, h] = m.slice(1).map(Number)
  const img = new Image()
  img.crossOrigin = 'anonymous'
  img.src = src
  await img.decode()
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  c.getContext('2d')!.drawImage(img, x, y, w, h, 0, 0, w, h)
  return c.toDataURL('image/png')
}

watch(compare, async (c) => {
  shownBefore.value = c ? await cropOf(c.file).catch(() => '') : ''
}, { immediate: true })

function check(): string {
  return !input.value ? t('restore.choosePhoto')
    : !opts.value.correct && !opts.value.dust && !opts.value.repair && !opts.value.colorize && !opts.value.sharpen && !opts.value.details && !opts.value.faces ? t('restore.chooseStep')
      : usesAi.value && !model.value ? t('restore.needsModelError') : ''
}

/** A quick look at a part of the photo: what is zoomed in on, else the largest face or the middle (768 px). */
async function preview(): Promise<void> {
  error.value = check()
  if (error.value || !size.value) return
  const [w, h] = size.value
  const v = mask.value?.visible()
  const part = v ? { x: v.x * w, y: v.y * h, w: v.w * w, h: v.h * h } : { auto: true, x: 0, y: 0, w: Math.min(768, w), h: Math.min(768, h) }
  await send({ ...opts.value, preview: part }, 'Preview')
}

async function addRule(): Promise<void> {
  const rule = newRule.value.replace(/\s+/g, ' ').trim()
  if (!rule || userRules.value.includes(rule)) return
  await settings.set('restoreRules', [...userRules.value, rule])
  newRule.value = ''
}

const removeRule = (rule: string): Promise<void> => settings.set('restoreRules', userRules.value.filter((r) => r !== rule))

async function restore(): Promise<void> {
  error.value = check()
  if (!error.value) await send({ ...opts.value }, '')
}

async function send(o: RestoreOptions, kind: string): Promise<void> {
  if (!size.value) return
  sending.value = true
  try {
    const data = painted.value ? mask.value?.exportMask() : undefined
    const maskImage = data ? await window.vk.files.writeImage(data) : undefined
    const what = [o.correct && 'corrected', o.dust && 'dust removed', o.repair && 'repaired', o.details && 'details rebuilt', o.faces && 'faces restored',
      o.colorize && 'coloured', o.sharpen && 'sharpened', o.scale === 2 && 'twice the size'].filter(Boolean).join(', ')
    const scale = o.scale === 2 && !o.preview ? 2 : 1
    const job: Omit<Job, 'id'> = {
      page: 'restore', prompt: note.value.trim(), modelId: usesAi.value ? model.value!.id : '', modelDir: usesAi.value ? model.value!.folder : '',
      width: size.value[0] * scale, height: size.value[1] * scale, seed: -1, steps: usesAi.value ? steps.value : 0, guidance: 1, inputImage: input.value, maskImage,
      // the consistency LoRA only where it is made for (klein 4B); its switch is hidden for the others
      restore: { ...o, consistency: o.consistency && takesConsistency(model.value?.meta), scale, rules: [...userRules.value], facePoints: facesState.value === 'found' ? faces.value.map((f) => f.points.map(([x, y]) => [x, y] as [number, number])) : undefined },
      label: `${kind || 'Restored'}: ${what}`, // i18n-ok: stored in English, shown by jobLabel()
    }
    await queue.add(job)
  } catch (err) {
    error.value = cleanError(err)
  } finally {
    sending.value = false
  }
}

function open(q: QueuedJob, file: string): void {
  const pictures = jobs.value.flatMap((x) => queue.shown(x).map((f) => ({ job: JSON.parse(JSON.stringify(x.job)) as Job, file: f })))
  void window.vk.viewer.open(pictures, pictures.findIndex((p) => p.file === file && p.job.id === q.job.id))
}
</script>

<template>
  <PageFrame :title="t('restore.title')" :subtitle="t('restore.subtitle')">
    <div class="page-grid">
      <ImageInput v-model="input" @size="(w, h) => (size = [w, h])">
        <template #default="{ src, loaded }">
          <MaskCanvas ref="mask" :src="src" @loaded="(e) => (loaded(e), measure(e))" @change="painted = $event">
            <template #overlay>
              <FaceBoxes v-if="opts.faces && facesState === 'found' && facesSize" v-model:faces="faces" :size="facesSize" />
            </template>
          </MaskCanvas>
        </template>
      </ImageInput>
      <p v-if="input && opts.faces" class="dim hint faces-hint">
        <template v-if="facesState === 'finding'">{{ t('restore.findingFaces') }}</template>
        <template v-else-if="facesState === 'failed'"><span class="error selectable">{{ t('restore.facesError', { error: facesError }) }}</span></template>
        <template v-else-if="facesState === 'found'">
          {{ faces.length ? t('restore.facesFound', { n: faces.length }) : t('restore.noFace') }}
          <button class="btn small ghost" @click="findFaces">{{ t('restore.findAgain') }}</button>
        </template>
      </p>
      <p v-if="input" class="dim hint">
        {{ t('restore.paintHint') }}
      </p>
      <div v-if="compare && shownBefore" class="compare card">
        <CompareSlider :before="shownBefore" :after="compare.after" :after-label="compare.preview ? t('edit.compare.preview') : t('edit.compare.restored')" />
        <small class="dim">{{ compare.preview ? t('restore.compareHintPreview') : t('restore.compareHintResult') }}</small>
      </div>
      <p v-if="previewJob && (previewJob.state === 'running' || previewJob.state === 'waiting')" class="dim">
        {{ t('restore.previewStatus', { status: previewJob.status || t('restore.waiting') }) }}<template v-if="previewJob.progress > 0"> · {{ Math.round(previewJob.progress) }} %</template>
      </p>
      <p v-else-if="previewJob?.state === 'failed'" class="error selectable">{{ previewJob.error }}</p>
      <div class="prompt card">
        <textarea
          v-model="note" rows="3" :placeholder="t('restore.notePlaceholder')" spellcheck="false"
          @keydown.meta.enter.prevent="input && restore()"
        />
        <div class="send">
          <span v-if="error" class="error selectable">{{ error }}</span>
          <span v-else class="dim">{{ t('restore.shortcut') }}</span>
          <span class="buttons">
            <button class="btn" :disabled="sending || !input" @click="preview"><Eye :size="14" /> {{ t('restore.preview') }}</button>
            <HintBadge above :text="t('restore.previewHint')" />
            <button class="btn primary" :disabled="sending || !input" @click="restore"><WandSparkles :size="14" /> {{ t('restore.restore') }}</button>
          </span>
        </div>
      </div>
      <div class="add template">
        <input v-model="templateName" class="entry" type="text" :placeholder="t('restore.templateName')" maxlength="80" spellcheck="false" @keyup.enter="saveTemplate" />
        <button class="btn small" :title="t('restore.saveTemplateHint')" :disabled="!templateName.trim()" @click="saveTemplate">
          <BookmarkPlus :size="12" /> {{ t('restore.saveTemplate') }}
        </button>
      </div>
      <p v-if="settings.error" class="error selectable">{{ settings.error }}</p>
      <JobGallery :jobs="jobs" @open="open" />
    </div>

    <template #panel>
      <div class="fields">
        <div class="field">
          <span>{{ t('restore.template') }}</span>
          <div class="templates">
            <button v-for="tp in TEMPLATES" :key="tp.name" class="chip" :class="{ on: template === tp.name }" @click="useTemplate(tp)">{{ t(TEMPLATE_TITLES[tp.name]) }}</button>
            <span v-for="tp in ownTemplates" :key="'own:' + tp.name" class="chip own" :class="{ on: template === tp.name }">
              <button @click="useTemplate(tp)">{{ tp.name }}</button>
              <button :title="t('restore.deleteTemplate')" @click="removeTemplate(tp.name)"><X :size="11" /></button>
            </span>
          </div>
        </div>

        <div class="field">
          <span>{{ t('restore.steps') }}</span>
          <label class="check"><input v-model="opts.correct" type="checkbox" /> {{ t('restore.correct') }}</label>
          <SliderRow v-if="opts.correct" v-model="opts.correctStrength" class="indent" :label="t('restore.strength')" :min="0.2" :max="1" :step="0.05" :format="percent" :fallback="0.8" />
          <label class="check">
            <input v-model="opts.dust" type="checkbox" /> {{ t('restore.dust') }}
            <HintBadge :text="t('restore.dustHint')" />
          </label>
          <SliderRow v-if="opts.dust" v-model="opts.dustSensitivity" class="indent" :label="t('restore.sensitivity')" :min="0" :max="1" :step="0.05" :format="percent" :fallback="0.5" />
          <label class="check"><input v-model="opts.repair" type="checkbox" /> {{ t('restore.repair') }}</label>
          <label class="check">
            <input v-model="opts.details" type="checkbox" /> {{ t('restore.details') }}
            <HintBadge :text="t('restore.detailsHint')" />
          </label>
          <template v-if="opts.details">
            <SliderRow v-model="opts.detailLevel" class="indent" :label="t('restore.softness')" :min="1.25" :max="3" :step="0.25" :format="(v) => `× ${num(v, 2)}`" :fallback="2" />
            <SliderRow v-model="opts.detailStrength" class="indent" :label="t('restore.strength')" :min="0.2" :max="1" :step="0.05" :format="percent" :fallback="1" />
          </template>
          <label class="check">
            <input v-model="opts.faces" type="checkbox" /> {{ t('restore.faces') }}
            <HintBadge :text="t('restore.facesHint')" />
          </label>
          <template v-if="opts.faces">
            <SliderRow v-model="opts.faceFidelity" class="indent" :label="t('restore.faithful')" :min="0.5" :max="1" :step="0.05" :format="percent" :fallback="0.9" />
            <SliderRow v-model="opts.faceStrength" class="indent" :label="t('restore.strength')" :min="0.2" :max="1" :step="0.05" :format="percent" :fallback="0.6" />
          </template>
          <label class="check"><input v-model="opts.colorize" type="checkbox" /> {{ t('restore.colorize') }}</label>
          <SliderRow v-if="opts.colorize" v-model="opts.colorStrength" class="indent" :label="t('restore.colourStrength')" :min="0.5" :max="1.5" :step="0.05" :format="percent" />
          <small v-if="grayscale" class="dim">{{ t('restore.grayscale') }}</small>
          <label class="check"><input v-model="opts.sharpen" type="checkbox" /> {{ t('restore.sharpen') }}</label>
          <SliderRow v-if="opts.sharpen" v-model="opts.sharpness" class="indent" :label="t('restore.strength')" :min="0.1" :max="1" :step="0.05" :format="percent" />
          <small class="dim">
            {{ t('restore.colourAbout') }}
          </small>
        </div>

        <div class="field">
          <span>{{ t('restore.resultSize') }}</span>
          <div class="sizes">
            <label class="check"><input v-model.number="opts.scale" type="radio" :value="1" /> {{ t('restore.sizeSame') }}</label>
            <label class="check"><input v-model.number="opts.scale" type="radio" :value="2" /> {{ t('restore.sizeTwice') }}</label>
          </div>
          <small v-if="size" class="dim">{{ t('restore.pixels', { size: `${size[0] * (opts.scale ?? 1)} × ${size[1] * (opts.scale ?? 1)}` }) }}</small>
        </div>

        <template v-if="usesAi">
          <label class="field">
            <span>{{ t('restore.model') }}</span>
            <select v-model="modelId" class="entry">
              <option v-for="m in models" :key="m.id" :value="m.id">{{ m.title }}</option>
            </select>
            <small v-if="tints" class="dim">{{ t('restore.klein9bTint') }}</small>
            <small v-if="!models.length" class="dim">{{ t('restore.needsModel') }} <RouterLink to="/models">{{ t('restore.needsModelLink') }}</RouterLink>.</small>
          </label>
          <label class="field">
            <span>{{ t('restore.modelSteps') }} <b>{{ steps }}</b></span>
            <input v-model.number="steps" type="range" min="2" max="12" step="1" />
          </label>
          <label v-if="takesConsistency(model?.meta)" class="check">
            <input v-model="opts.consistency" type="checkbox" /> {{ t('restore.consistency') }}
            <HintBadge :text="t('restore.consistencyHint')" />
          </label>

          <div class="field guard">
            <span><ShieldCheck :size="14" /> {{ t('restore.guardRails') }}</span>
            <label class="check"><input v-model="opts.lock" type="checkbox" /> {{ t('restore.lock') }}</label>
            <label class="check"><input v-model="opts.checkFaces" type="checkbox" /> {{ t('restore.checkFaces') }}</label>
            <SliderRow v-model="opts.maxChange" :label="t('restore.maxChange')" :min="0.01" :max="0.3" :step="0.01" :format="percent" />
            <small class="dim">{{ t('restore.guardRailsHint') }}</small>
          </div>

          <div class="field">
            <span>{{ t('restore.rules') }}</span>
            <ul class="rules">
              <li v-for="r in FIXED_RULES" :key="r" class="dim">{{ t(r) }}</li>
              <li v-for="r in userRules" :key="r" class="own">
                <span class="selectable">{{ r }}</span>
                <button class="btn small ghost" :title="t('restore.removeRule')" @click="removeRule(r)"><X :size="12" /></button>
              </li>
            </ul>
            <div class="add">
              <input v-model="newRule" class="entry" type="text" :placeholder="t('restore.rulePlaceholder')" maxlength="300" spellcheck="false" @keyup.enter="addRule" />
              <button class="btn small" :disabled="!newRule.trim()" :title="t('restore.addRule')" @click="addRule"><Plus :size="12" /></button>
            </div>
            <small class="dim">{{ t('restore.rulesHint') }}</small>
          </div>
        </template>
      </div>
    </template>
  </PageFrame>
</template>

<style scoped>
.hint {
  margin-top: -6px;
}

.prompt {
  padding: 12px 12px 10px 14px;
}

.compare {
  display: grid;
  gap: 6px;
  padding: 8px;
  max-width: 900px;
}

.faces-hint {
  display: flex;
  align-items: center;
  gap: 8px;
}

.buttons {
  display: flex;
  align-items: center;
  gap: 8px;
}

.sizes {
  display: flex;
  gap: 16px;
}

.fields,
.field {
  display: grid;
  gap: 8px;
}

.fields {
  gap: 20px;
}

.field > span {
  display: flex;
  align-items: center;
  gap: 6px;
}

.field > span b {
  margin-left: auto;
  font-weight: 500;
  color: var(--text-dim);
}

.check {
  display: flex;
  gap: 8px;
  align-items: flex-start;
}

.indent {
  margin-left: 24px;
}

.guard {
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
}

.rules {
  display: grid;
  gap: 4px;
  margin: 0;
  padding-left: 16px;
}

.rules .own {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 6px;
}

.add {
  display: flex;
  gap: 6px;
}

.template {
  max-width: 520px;
}

.add input {
  flex: 1;
}

.templates {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  padding: 3px 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface-2);
  color: var(--text);
  font: inherit;
  font-size: 12px;
}

.chip.own {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding-right: 4px;
}

.chip.own button {
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
}
</style>
