<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Text to image, Image to image, Inpainting, Image to video and Illusion: one page in five modes. The prompt and
// the results are in the work area, the settings of the job in the panel on the right.
import { computed, onActivated, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Dices, Eraser, Minus, Plus, RotateCw, ScanText, Sparkles, X } from '@lucide/vue'
import PageFrame from '../components/PageFrame.vue'
import ImageInput from '../components/ImageInput.vue'
import HintBadge from '../components/HintBadge.vue'
import MaskCanvas from '../components/MaskCanvas.vue'
import PatternEditor from '../components/PatternEditor.vue'
import JobGallery from '../components/JobGallery.vue'
import StylePicker from '../components/StylePicker.vue'
import { useAssetsStore } from '../stores/assets'
import { useHandoffStore } from '../stores/handoff'
import { useQueueStore } from '../stores/queue'
import { useImportsStore } from '../stores/imports'
import { cleanError } from '../stores/runtimes'
import { guidanceHint, stepsHint } from '../util/model_fit'
import { MAX_LORAS, MODES, aiLabelOf, applyDefaults, applyJob, applyModel, buildJob, buildRemoveJob, modelDefaults, emptyForm, formProblem, lorasFor, modelsFor, keepsPicture, takesFaceDetail, takesReferences, takesTurbo, takesUpsampler, turboLora, upsamplerHelper, removes, removeHelper, removeMethods, TURBO, type GenerateForm, type Mode } from '../util/job_form'
import { MAX_REFERENCES } from '@shared/engine_job'
import { DEFAULT_SIZES, RATIOS, ratioOf, sizeForRatio } from '../util/sizes'
import { CONSENT_QUESTION } from '@shared/content_policy'
import { askConsent } from '../util/consent'
import { controlTypesFor } from '@shared/controlnet'
import { flux1Outline } from '@shared/hints'
import { SIGMA_SCHEDULES, samplersFor } from '@shared/samplers'
import type { HelperModel, QueuedJob } from '@shared/api'
import type { Job } from '@shared/types'
import { seedOf } from '@/util/seed'
import { samplerLabel } from '../util/labels'
import { dec, num, t, type PlainKey } from '../i18n'
import { isRemote } from '../remote_vk'

const props = defineProps<{ mode: Mode }>()
const TEXTS: Record<Mode, { title: PlainKey; subtitle: PlainKey; prompt: PlainKey }> = {
  text: { title: 'generate.modes.text.title', subtitle: 'generate.modes.text.subtitle', prompt: 'generate.modes.text.prompt' },
  image: { title: 'generate.modes.image.title', subtitle: 'generate.modes.image.subtitle', prompt: 'generate.modes.image.prompt' },
  inpaint: { title: 'generate.modes.inpaint.title', subtitle: 'generate.modes.inpaint.subtitle', prompt: 'generate.modes.inpaint.prompt' },
  video: { title: 'generate.modes.video.title', subtitle: 'generate.modes.video.subtitle', prompt: 'generate.modes.video.prompt' },
  illusion: { title: 'generate.modes.illusion.title', subtitle: 'generate.modes.illusion.subtitle', prompt: 'generate.modes.illusion.prompt' },
}

const does = MODES[props.mode]
const assets = useAssetsStore()
const queue = useQueueStore()
const handoff = useHandoffStore()

const STORE_KEY = 'vk.form.' + props.mode
function stored(): GenerateForm {
  const form = emptyForm(props.mode)
  try {
    Object.assign(form, JSON.parse(localStorage.getItem(STORE_KEY) ?? '{}'))
  } catch {
    // unreadable: start fresh
  }
  return form
}
const form = reactive<GenerateForm>(stored())
watch(form, () => {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(form))
  } catch {
    // no storage: the form just is not remembered
  }
})

// Inpainting → Remove: the painted object filled from its surroundings, no model and no prompt
const removing = computed(() => removes(props.mode, form))
const REMOVE_METHODS = removeMethods()
const models = computed(() => modelsFor(props.mode, assets.models))
const model = computed(() => models.value.find((m) => m.id === form.modelId))
const loras = computed(() => lorasFor(model.value, assets.loras))
const samplers = computed(() => samplersFor(model.value?.meta))
// the chosen sampler stays in the form across models; one a model lacks shows (and runs) as its default
const samplerShown = computed({
  get: () => (samplers.value?.includes(form.sampler) ? form.sampler : 'Default'),
  set: (v: string) => { form.sampler = v },
})
const controlTypes = computed(() => (does.control ? controlTypesFor(model.value?.meta) : []))
const controlType = computed(() => controlTypes.value.find((ct) => ct.id === form.controlType))
const sizes = computed(() => model.value?.meta.resolutions?.length ? model.value.meta.resolutions : DEFAULT_SIZES)
const native = computed<[number, number]>(() => {
  const d = model.value?.meta.defaults ?? {}
  return [Number(d.width) || 1024, Number(d.height) || 1024]
})
const ratio = computed(() => ratioOf(form.width, form.height, native.value[0], native.value[1], sizes.value))
const showSize = computed(() => does.size || (props.mode === 'image' && form.customSize))
const controlNote = ref<PlainKey | ''>('')
// FLUX.2 takes the input picture as a reference, there is no strength to set; Fibo 2.0 repaints a mask's part whole
const showStrength = computed(() => (props.mode === 'inpaint' || props.mode === 'image') && model.value?.meta.family !== 'fibo2'
  && !(props.mode === 'image' && ['flux2', 'flux3', 'qwen_image21'].includes(model.value?.meta.family ?? '')))

// Fibo 2.0: further pictures beside the input picture, one empty field after the chosen ones
const showReferences = computed(() => props.mode === 'image' && takesReferences(model.value?.meta))
const referenceSlots = computed(() => Math.min(MAX_REFERENCES, form.references.filter(Boolean).length + 1))
function setReference(i: number, path: string): void {
  const refs = [...form.references]
  refs[i] = path
  form.references = refs.filter(Boolean)
}

// the model's own suggestions, offered while the form differs from them
const suggested = computed(() => (model.value ? modelDefaults(model.value) : undefined))
const offDefaults = computed(() => {
  const s = suggested.value
  if (!s || fastOn.value) return false  // the fast option sets steps and guidance itself
  return s.steps !== form.steps || s.guidance !== form.guidance || (showSize.value && (s.width !== form.width || s.height !== form.height))
    || (does.sampler && s.sampler !== 'Default' && (s.sampler !== form.sampler || s.sigmaSchedule !== form.sigmaSchedule))
})

const suggestText = computed(() => {
  const s = suggested.value
  if (!s) return ''
  const base = showSize.value ? t('generate.panel.suggestsSizeHint', { steps: s.steps, guidance: s.guidance, width: s.width, height: s.height }) : t('generate.panel.suggestsHint', { steps: s.steps, guidance: s.guidance })
  const sampler = s.sigmaSchedule !== 'Default' ? `${s.sampler} ${s.sigmaSchedule}` : s.sampler
  return does.sampler && s.sampler !== 'Default' ? `${base} ${t('generate.panel.makerSampler', { sampler })}` : base
})

// steps and guidance the chosen model is not made for (kept from another model)
// the fast option (FLUX.1 [dev]): the Turbo-Alpha LoRA sets steps and guidance itself
const fastOffered = computed(() => does.loras && !removing.value && takesTurbo(model.value?.meta))
const fastOn = computed(() => fastOffered.value && form.fast)
const turbo = computed(() => turboLora(assets.loras))
const stepsFit = computed(() => (fastOn.value ? null : stepsHint(model.value?.meta, form.steps)))
const guidanceFit = computed(() => (fastOn.value ? null : guidanceHint(model.value?.meta, form.guidance, form.steps)))

function chooseModel(id: string): void {
  const next = models.value.find((m) => m.id === id)
  if (next) applyModel(form, next, assets.loras, model.value)
}

/** A rectangle in the proportions of a ratio; its longer side is 46 px. */
function shape(r: { w: number; h: number }): Record<string, string> {
  const long = Math.max(r.w, r.h)
  return { width: `${(r.w / long) * 46}px`, height: `${(r.h / long) * 46}px` }
}

function setRatio(r: { w: number; h: number }): void {
  ;[form.width, form.height] = sizeForRatio(r, native.value[0], native.value[1], sizes.value)
}

async function refresh(): Promise<void> {
  await assets.refresh()
  if (!model.value && models.value.length) applyModel(form, models.value[0], assets.loras)
  const given = handoff.take(props.mode)
  if (given?.job) applyJob(form, given.job, models.value, assets.loras)
  if (given?.inputImage) form.inputImage = given.inputImage
  // a mask from elsewhere (an object selected on the Enhance page) belongs to the picture it came with
  if (given?.maskImage && given.inputImage) baseMask.value = { image: given.inputImage, mask: given.maskImage }
  if (given?.control) {
    form.controlImage = given.control.image
    form.controlPreprocess = given.control.preprocess
    if (controlTypes.value.some((ct) => ct.id === given.control?.type)) form.controlType = given.control.type
    else controlNote.value = 'generate.panel.controlNoPose'
    const size = given.control.size
    if (size && sizes.value.includes(size[0]) && sizes.value.includes(size[1])) [form.width, form.height] = size
  }
}
onActivated(refresh)
// a viewer window sends something to the page that is already shown
const route = useRoute()
watch(() => route.query.t, () => { if (route.path === '/' + props.mode) void refresh() })

const mask = ref<InstanceType<typeof MaskCanvas>>()
/** the mask to start from, for the picture it was made for */
const baseMask = ref<{ image: string; mask: string }>()
const startMask = computed(() => (baseMask.value && baseMask.value.image === form.inputImage ? baseMask.value.mask : undefined))
const pattern = ref<InstanceType<typeof PatternEditor>>()
const hasMask = ref(false)
const inputSize = ref<[number, number]>()
const error = ref('')
const sending = ref(false)

// Prompt from picture (Image to image): Qwen3-VL describes the picture on this Mac, not in the remote web UI
const remote = isRemote()
const describing = ref('')  // its stage while it describes
async function promptFromPicture(): Promise<void> {
  if (!form.inputImage || describing.value) return
  if (form.prompt.trim() && !(await window.vk.dialog.ask(t('generate.caption.replace'), t('generate.caption.replaceYes'), t('common.cancel')))) return
  error.value = ''
  describing.value = t('generate.caption.starting')
  const off = window.vk.caption.onProgress((stage) => { describing.value = stage })
  try {
    const { text } = await window.vk.caption.image(form.inputImage)
    if (text) form.prompt = text
  } catch (err) {
    error.value = cleanError(err)
  } finally {
    off()
    describing.value = ''
  }
}
const stopDescribing = (): void => { void window.vk.caption.stop() }
const problem = computed(() => formProblem(props.mode, form, model.value, hasMask.value))

// FLUX 3's prompt upsampler and ERNIE-Image's prompt enhancer are helper models: downloaded here or on the Models page
// (the MLX engine never downloads)
const PUP = computed(() => upsamplerHelper(model.value?.meta))
// the texts of the option: ERNIE's enhancer has its own
const up = (key: string): string => t(`generate.upsample.${key}${model.value?.meta.arch === 'ernie_image' ? 'Ernie' : ''}` as PlainKey)
const imports = useImportsStore()
const pupInstalled = ref<boolean | null>(null)
async function checkPup(): Promise<void> {
  try {
    pupInstalled.value = takesUpsampler(model.value?.meta)
      ? (await window.vk.helpers.list()).find((h) => h.id === PUP.value)?.installed ?? false
      : null
  } catch {
    pupInstalled.value = null  // the remote web UI may not list helper models: the engine says when it is missing
  }
}
watch(() => model.value?.id, () => void checkPup(), { immediate: true })
const pupDownload = computed(() => imports.of({ source: 'helper', ref: PUP.value }))
const pupDownloading = computed(() => pupDownload.value?.state === 'waiting' || pupDownload.value?.state === 'running')
watch(() => pupDownload.value?.state, (state) => { if (state === 'done') void checkPup() })
async function downloadPup(): Promise<void> {
  error.value = ''
  try {
    void imports.start()
    await window.vk.helpers.install(PUP.value)
  } catch (err) {
    error.value = cleanError(err)
  }
}

// RORem fills large areas when removing (Auto, Thorough), ObjectClear takes shadows along (With shadows): helper
// models, downloaded here or on the Models page; the remote web UI can not install helpers, so it only says so
const shadows = computed(() => form.removeMethod === 'objectclear')
const helperId = computed(() => removeHelper(form.removeMethod))
const removeHelpers = ref<HelperModel[] | null>(null)
async function checkRemoveHelpers(): Promise<void> {
  try {
    removeHelpers.value = await window.vk.helpers.list()
  } catch {
    removeHelpers.value = null  // the engine says when it is missing
  }
}
watch(removing, (on) => { if (on) void checkRemoveHelpers() }, { immediate: true })
const helper = computed(() => removeHelpers.value?.find((h) => h.id === helperId.value))
const helperInstalled = computed<boolean | null>(() => (removeHelpers.value ? helper.value?.installed ?? false : null))
const helperGb = computed(() => num((helper.value?.sizeMb ?? 0) / 1024, 1))
const helperDownload = computed(() => imports.of({ source: 'helper', ref: helperId.value }))
const helperDownloading = computed(() => helperDownload.value?.state === 'waiting' || helperDownload.value?.state === 'running')
watch(() => ['rorem', 'objectclear'].map((id) => imports.of({ source: 'helper', ref: id })?.state).join(), (states) => {
  if (states.includes('done')) void checkRemoveHelpers()
})
async function downloadHelper(): Promise<void> {
  const id = helperId.value
  const gb = helperGb.value
  const asked = shadows.value
    ? window.vk.dialog.ask(t('generate.remove.shadowsDownloadAsk', { gb }), t('generate.remove.downloadYes'), t('common.cancel'), t('generate.remove.shadowsDownloadDetail', { gb }))
    : window.vk.dialog.ask(t('generate.remove.downloadAsk', { gb }), t('generate.remove.downloadYes'), t('common.cancel'), t('generate.remove.downloadDetail', { gb }))
  if (!(await asked)) return
  error.value = ''
  try {
    void imports.start()
    await window.vk.helpers.install(id)
  } catch (err) {
    error.value = cleanError(err)
  }
}

const turboRequest = { source: 'hf' as const, ref: TURBO.ref, file: TURBO.file, name: TURBO.name }
const turboDownload = computed(() => imports.of(turboRequest))
const turboDownloading = computed(() => turboDownload.value?.state === 'waiting' || turboDownload.value?.state === 'running')
async function downloadTurbo(): Promise<void> {
  error.value = ''
  try {
    void imports.start()
    await imports.add(turboRequest, TURBO.name)
  } catch (err) {
    error.value = cleanError(err)
  }
}

async function generate(): Promise<void> {
  error.value = problem.value
  if (!error.value && fastOn.value && !turbo.value) error.value = t('generate.fast.missing')
  if (!error.value && props.mode === 'text' && form.upsample && pupInstalled.value === false) error.value = up('missing')
  if (!error.value && removing.value && (form.removeMethod === 'rorem' || shadows.value) && helperInstalled.value === false) {
    error.value = shadows.value ? t('generate.remove.shadowsMissing') : t('generate.remove.missing')
  }
  if (error.value || (!model.value && !removing.value) || sending.value) return
  sending.value = true
  try {
    let maskImage: string | undefined
    if (props.mode === 'inpaint') {
      const data = await mask.value?.exportMask()
      if (!data) return
      maskImage = await window.vk.files.writeImage(data)
    }
    let patternImage: string | undefined
    if (props.mode === 'illusion') {
      const data = pattern.value?.exportPattern()
      if (!data) return
      patternImage = await window.vk.files.writeImage(data)
    }
    const extras = { maskImage, patternImage, inputSize: inputSize.value }
    await send(removing.value ? buildRemoveJob(form, extras) : buildJob(props.mode, form, model.value!, assets.loras, extras),
      does.count && !removing.value ? form.count : 1)
  } catch (err) {
    error.value = cleanError(err)
  } finally {
    sending.value = false
  }
}

async function send(job: Omit<Job, 'id'>, count: number): Promise<void> {
  try {
    await queue.add(job, count)
  } catch (err) {
    const message = cleanError(err)
    if (message !== CONSENT_QUESTION) throw err
    if (await askConsent()) await queue.add({ ...job, consent: true }, count)
  }
}

// the newest finished removal of this page: Remove again takes its result with the same mask (leftovers, shadows)
// (not after Compare: which of its pictures to go on with is the user's pick, from the gallery)
const lastRemoval = computed(() => {
  const q = jobs.value.filter((q) => q.state === 'done' && q.job.removeObject && q.job.maskImage && q.results.length).at(-1)
  return q?.job.removeObject?.method === 'compare' ? undefined : q
})
async function removeAgain(): Promise<void> {
  const q = lastRemoval.value
  if (!q || sending.value) return
  error.value = ''
  sending.value = true
  try {
    const picture = q.results[0]
    form.inputImage = picture
    baseMask.value = { image: picture, mask: q.job.maskImage! }
    await send(buildRemoveJob(form, { maskImage: q.job.maskImage, inputSize: [q.job.width, q.job.height] }), 1)
  } catch (err) {
    error.value = cleanError(err)
  } finally {
    sending.value = false
  }
}


function addLora(): void {
  const free = loras.value.find((l) => !form.loras.some((x) => x.id === l.id))
  if (free) form.loras.push({ id: free.id, scale: 1 })
}

/** the weight a tenth up or down, within the field's range, without float dust (0.55 + 0.1 = 0.65, not 0.6500000001) */
const stepWeight = (scale: number, by: number): number => Math.round(Math.min(2, Math.max(-2, (Number(scale) || 0) + by)) * 100) / 100

// ------------------------------------------------------------------ results
const jobs = computed(() => queue.ofPage(props.mode))
const pictures = computed(() => jobs.value.flatMap((q) => queue.shown(q).map((file) => ({ q, file }))))

function open(q: QueuedJob, file: string): void {
  const items = pictures.value.map((p) => ({ job: JSON.parse(JSON.stringify(p.q.job)) as Job, file: p.file }))
  void window.vk.viewer.open(items, pictures.value.findIndex((p) => p.q === q && p.file === file))
}

const EU_ICONS = import.meta.glob('../assets/eu_ai_label/*.png', { eager: true, import: 'default' }) as Record<string, string>
const labelPreview = computed(() => {
  const label = aiLabelOf(form, props.mode)
  const tone = label.tone === 'white' ? 'white' : 'black'
  return { tone, src: EU_ICONS[`../assets/eu_ai_label/${label.kind}_${tone}${label.subtle ? '_50' : ''}.png`] ?? '' }
})
</script>

<template>
  <PageFrame :title="t(TEXTS[mode].title)" :subtitle="t(TEXTS[mode].subtitle)">
    <div class="page-grid">
      <PatternEditor v-if="mode === 'illusion'" ref="pattern" :width="form.width" :height="form.height" />
      <ImageInput v-if="does.input" v-model="form.inputImage" @size="(w, h) => (inputSize = [w, h])">
        <template v-if="mode === 'inpaint'" #default="{ src, loaded }">
          <MaskCanvas ref="mask" :src="src" :base="startMask" :image="remote ? undefined : form.inputImage" @loaded="loaded" @change="hasMask = $event" />
        </template>
      </ImageInput>

      <div class="prompt card">
        <p v-if="removing" class="dim">{{ t('generate.remove.intro') }}</p>
        <textarea
          v-else v-model="form.prompt" :placeholder="t(TEXTS[mode].prompt)" :rows="mode === 'video' || mode === 'illusion' ? 5 : 14" spellcheck="false"
          @keydown.meta.enter.prevent="generate"
        />
        <div class="send">
          <span v-if="error" class="error selectable">{{ error }}</span>
          <span v-else class="dim">{{ t('generate.send.shortcut') }}</span>
          <span class="spacer" />
          <label v-if="mode === 'text' && takesUpsampler(model?.meta)" class="check">
            <input v-model="form.upsample" type="checkbox" /> {{ up('label') }}
            <HintBadge above :text="up('hint')" />
          </label>
          <button
            v-if="mode === 'text' && form.upsample && pupInstalled === false" class="btn small" :disabled="pupDownloading"
            @click="downloadPup"
          >
            {{ pupDownloading ? t('generate.upsample.downloading') : up('download') }}
          </button>
          <template v-if="mode === 'image' && !remote">
            <button v-if="!describing" class="btn small" :disabled="!form.inputImage || queue.open.length > 0 || sending" @click="promptFromPicture">
              <ScanText :size="14" /> {{ t('generate.caption.button') }}
            </button>
            <template v-else>
              <span class="dim">{{ describing }}</span>
              <button class="btn small" @click="stopDescribing">{{ t('common.cancel') }}</button>
            </template>
            <HintBadge above :text="t('generate.caption.hint')" />
          </template>
          <!-- the EU's icon for AI content in the corner of the pictures -->
          <div v-if="mode !== 'video'" class="ai-label">
            <label class="check">
              <input v-model="form.aiLabel" type="checkbox" /> {{ t('generate.aiLabel.label') }}
              <HintBadge above :text="t('generate.aiLabel.hint')" />
            </label>
            <template v-if="form.aiLabel">
              <img class="eu-icon" :class="labelPreview.tone" :src="labelPreview.src" alt="" />
              <select v-model="form.aiLabelIcon" :aria-label="t('generate.aiLabel.icon')">
                <!-- i18n-ok: the words on the EU's icon -->
                <option value="auto">{{ mode === 'image' || mode === 'inpaint' ? 'AI MODIFIED' : 'AI GENERATED' }}</option>
                <option value="ai">{{ t('generate.aiLabel.round') }}</option>
              </select>
              <select v-model="form.aiLabelTone" :aria-label="t('generate.aiLabel.tone')">
                <option value="auto">{{ t('generate.aiLabel.autoTone') }}</option>
                <option value="black">{{ t('generate.aiLabel.dark') }}</option>
                <option value="white">{{ t('generate.aiLabel.light') }}</option>
              </select>
              <select v-model="form.aiLabelSize" :aria-label="t('generate.aiLabel.size')">
                <option value="small">{{ t('generate.aiLabel.small') }}</option>
                <option value="medium">{{ t('generate.aiLabel.medium') }}</option>
                <option value="large">{{ t('generate.aiLabel.large') }}</option>
              </select>
              <label class="check"><input v-model="form.aiLabelSubtle" type="checkbox" /> {{ t('generate.aiLabel.subtle') }}</label>
            </template>
          </div>
          <button v-if="removing && lastRemoval" class="btn" :disabled="sending" :title="t('generate.remove.againHint')" @click="removeAgain">
            <RotateCw :size="14" /> {{ t('generate.remove.again') }}
          </button>
          <button class="btn primary" :disabled="sending || !!describing" @click="generate">
            <template v-if="removing"><Eraser :size="14" /> {{ t('generate.remove.send') }}</template>
            <template v-else><Sparkles :size="14" /> {{ does.count && form.count > 1 ? t('generate.send.generateCount', { n: form.count }) : t('generate.send.generate') }}</template>
          </button>
        </div>
      </div>

      <p v-if="!models.length && !removing" class="dim">
        {{ t('generate.send.noModel') }} <RouterLink to="/models">{{ t('generate.send.noModelLink') }}</RouterLink>
      </p>
      <JobGallery :jobs="jobs" @open="open" />
    </div>

    <template #panel>
      <div class="fields">
        <div v-if="mode === 'inpaint'" class="tabs segmented" role="radiogroup" :aria-label="t('generate.remove.action')">
          <button role="radio" :aria-checked="!removing" :class="{ on: !removing }" @click="form.inpaintAction = 'repaint'">{{ t('generate.remove.repaint') }}</button>
          <button role="radio" :aria-checked="removing" :class="{ on: removing }" @click="form.inpaintAction = 'remove'">{{ t('generate.remove.remove') }}</button>
        </div>
        <div v-if="removing" class="field">
          <span class="label-row">{{ t('generate.remove.method') }} <HintBadge :text="t('generate.remove.methodHint')" /></span>
          <div class="tabs segmented methods" role="radiogroup" :aria-label="t('generate.remove.method')">
            <button
              v-for="m in REMOVE_METHODS" :key="m.id" role="radio" :aria-checked="form.removeMethod === m.id"
              :class="{ on: form.removeMethod === m.id }" @click="form.removeMethod = m.id"
            >
              {{ t(m.title) }}
            </button>
          </div>
          <template v-if="helperId">
            <small v-if="remote" class="dim">{{ shadows ? t('generate.remove.shadowsOnTheMac') : t('generate.remove.onTheMac') }}</small>
            <template v-else-if="helperInstalled === false">
              <small class="dim">
                {{ shadows ? t('generate.remove.shadowsMissing') : form.removeMethod === 'auto' ? t('generate.remove.missingAuto') : t('generate.remove.missing') }}
              </small>
              <button class="btn small" :disabled="helperDownloading" @click="downloadHelper">
                {{ helperDownloading ? t('generate.upsample.downloading')
                  : shadows ? t('generate.remove.shadowsDownload', { gb: helperGb }) : t('generate.remove.download', { gb: helperGb }) }}
              </button>
            </template>
          </template>
        </div>
        <template v-if="!removing">
          <label class="field">
            <span>{{ t('generate.panel.model') }}</span>
            <select :value="form.modelId" @change="chooseModel(($event.target as HTMLSelectElement).value)">
              <option v-if="!model" value="" disabled>{{ t('generate.panel.chooseModel') }}</option>
              <option v-for="m in models" :key="m.id" :value="m.id">{{ m.title }}</option>
            </select>
            <small v-if="model" class="dim">{{ model.meta.label }}</small>
            <small v-if="flux1Outline(mode, model?.meta)" class="dim">{{ t('generate.panel.flux1MaskHint') }}</small>
          </label>

          <div v-if="does.styles" class="field">
            <span>{{ t('generate.panel.style') }}</span>
            <StylePicker v-model="form.style" />
          </div>

          <template v-if="mode === 'video'">
            <label class="field">
              <span>{{ t('generate.panel.length') }} <b>{{ form.videoSeconds }} s</b></span>
              <input v-model.number="form.videoSeconds" type="range" min="1" max="5" />
              <small class="dim">{{ t('generate.panel.lengthHint') }}</small>
            </label>
            <label class="field">
              <span>{{ t('generate.panel.resolution') }}</span>
              <select v-model="form.videoResolution">
                <option value="480p">480p</option>
                <option value="720p">720p</option>
              </select>
              <small class="dim">{{ t('generate.panel.resolutionHint') }}</small>
            </label>
          </template>

          <label v-if="mode === 'illusion'" class="field">
            <span>{{ t('generate.panel.patternStrength') }} <b>{{ dec(form.patternStrength) }}</b></span>
            <input v-model.number="form.patternStrength" type="range" min="0.5" max="2" step="0.05" />
            <small class="dim">{{ t('generate.panel.patternStrengthHint') }}</small>
          </label>

          <label v-if="mode === 'image'" class="check">
            <input v-model="form.customSize" type="checkbox" /> {{ t('generate.panel.customSize') }}
          </label>
          <div v-if="showSize" class="field">
            <span>{{ t('generate.panel.size') }}</span>
            <div class="ratios">
              <button v-for="r in RATIOS" :key="r.label" class="ratio" :class="{ on: ratio === r.label }" :title="r.label" @click="setRatio(r)">
                <i :style="shape(r)">{{ r.label }}</i>
              </button>
            </div>
            <div class="pair">
              <select v-model.number="form.width" :title="t('generate.panel.width')"><option v-for="s in sizes" :key="s" :value="s">{{ s }}</option></select>
              <span class="dim">×</span>
              <select v-model.number="form.height" :title="t('generate.panel.height')"><option v-for="s in sizes" :key="s" :value="s">{{ s }}</option></select>
            </div>
          </div>

          <label v-if="showStrength" class="field">
            <span>{{ t('generate.panel.change') }} <b>{{ Math.round(form.strength * 100) }} %</b></span>
            <input v-model.number="form.strength" type="range" min="0.05" max="1" step="0.05" />
            <small class="dim">{{ mode === 'inpaint' ? t('generate.panel.changeInpaintHint') : t('generate.panel.changeHint') }}</small>
          </label>
          <label v-if="mode === 'image' && keepsPicture(model?.meta)" class="check">
            <input v-model="form.keepPicture" type="checkbox" /> {{ t('generate.keepPicture.label') }}
            <HintBadge :text="t('generate.keepPicture.hint')" />
          </label>
          <template v-if="(mode === 'text' || mode === 'image') && takesFaceDetail(model?.meta)">
            <label class="check">
              <input v-model="form.faceDetail" type="checkbox" /> {{ t('generate.faceDetail.label') }}
              <HintBadge :text="t('generate.faceDetail.hint')" />
            </label>
            <label v-if="form.faceDetail" class="field">
              <span>{{ t('generate.faceDetail.strength', { pct: Math.round(form.faceDetailStrength * 100) }) }} <HintBadge :text="t('generate.faceDetail.strengthHint')" /></span>
              <input v-model.number="form.faceDetailStrength" type="range" min="0.2" max="0.6" step="0.05" />
            </label>
          </template>

          <div v-if="showReferences" class="field">
            <span>{{ t('generate.panel.references') }} <HintBadge :text="t('generate.panel.referencesHint')" /></span>
            <ImageInput
              v-for="i in referenceSlots" :key="i" class="control" :model-value="form.references[i - 1] ?? ''"
              @update:model-value="(p: string) => setReference(i - 1, p)"
            />
          </div>

          <div v-if="offDefaults && suggested" class="defaults">
            <button class="btn small" @click="model && applyDefaults(form, model)">{{ t('generate.panel.modelDefaults') }}</button>
            <HintBadge notice :text="suggestText" />
          </div>
          <label class="field">
            <span>
              <span class="label-row">{{ t('generate.panel.steps') }}
                <template v-if="stepsFit">
                  <HintBadge notice start :text="stepsFit.text" />
                  <button class="btn small fix" @click.prevent="form.steps = stepsFit.fix.value">{{ stepsFit.fix.label }}</button>
                </template>
              </span>
              <b>{{ fastOn ? TURBO.steps : form.steps }}</b>
            </span>
            <input v-if="fastOn" :value="TURBO.steps" type="range" min="1" max="80" disabled />
            <input v-else v-model.number="form.steps" type="range" min="1" max="80" />
          </label>
          <div v-if="fastOffered" class="field fast">
            <label class="check">
              <input v-model="form.fast" type="checkbox" /> {{ t('generate.fast.label') }}
              <HintBadge :text="t('generate.fast.hint')" />
            </label>
            <button v-if="fastOn && !turbo" class="btn small" :disabled="turboDownloading" @click="downloadTurbo">
              {{ turboDownloading ? t('generate.upsample.downloading') : t('generate.fast.download') }}
            </button>
          </div>
          <label class="field">
            <span>
              <span class="label-row">{{ t('generate.panel.guidance') }}
                <template v-if="guidanceFit">
                  <HintBadge notice start :text="guidanceFit.text" />
                  <button class="btn small fix" @click.prevent="form.guidance = guidanceFit.fix.value">{{ guidanceFit.fix.label }}</button>
                </template>
              </span>
              <b>{{ num(fastOn ? TURBO.guidance : form.guidance, 1) }}</b>
            </span>
            <div class="ruler" aria-hidden="true">
              <i v-for="n in 21" :key="n" :class="{ major: (n - 1) % 5 === 0 }"><em v-if="(n - 1) % 5 === 0">{{ n - 1 }}</em></i>
            </div>
            <input v-if="fastOn" :value="TURBO.guidance" type="range" min="0" max="20" step="0.1" disabled />
            <input v-else v-model.number="form.guidance" type="range" min="0" max="20" step="0.1" />
            <small class="dim">{{ t('generate.panel.guidanceHint') }}</small>
          </label>

          <div v-if="controlTypes.length" class="field">
            <span>{{ t('generate.panel.control') }}</span>
            <select v-model="form.controlType" @change="controlNote = ''">
              <option value="">{{ t('generate.panel.none') }}</option>
              <option v-for="ct in controlTypes" :key="ct.id" :value="ct.id">{{ t(ct.title) }}</option>
            </select>
            <template v-if="controlType">
              <small class="dim">{{ t('generate.panel.controlHint', { hint: t(controlType.hint) }) }}</small>
              <ImageInput v-model="form.controlImage" class="control" />
              <label class="check"><input v-model="form.controlPreprocess" type="checkbox" /> {{ t('generate.panel.controlPhoto') }}</label>
              <span>{{ t('generate.panel.weight') }} <b>{{ dec(form.controlWeight) }}</b></span>
              <input v-model.number="form.controlWeight" type="range" min="0" max="2" step="0.05" />
            </template>
          </div>
          <p v-if="controlNote" class="error">{{ t(controlNote) }}</p>

          <div v-if="samplers && does.sampler" class="field">
            <span class="label-row">{{ t('generate.panel.sampler') }} <HintBadge v-if="model?.meta.samplers?.length" :text="t('generate.panel.samplerMakerOnly')" /><HintBadge notice v-if="form.sampler !== samplerShown" :text="t('generate.panel.samplerMissingHint', { name: samplerLabel(form.sampler) })" /></span>
            <div class="pair">
              <select v-model="samplerShown"><option v-for="s in samplers" :key="s" :value="s">{{ samplerLabel(s) }}</option></select>
              <!-- i18n-ok: the sampler's value -->
              <select v-model="form.sigmaSchedule" :disabled="samplerShown === 'Default'" :title="t('generate.panel.noiseSchedule')">
                <option v-for="s in SIGMA_SCHEDULES" :key="s" :value="s">{{ samplerLabel(s) }}</option>
              </select>
            </div>
          </div>
        </template>

        <div class="field">
          <span>{{ t('generate.panel.seed') }}</span>
          <div class="pair">
            <input
              type="number" min="0" :value="form.seed ?? ''" :placeholder="t('generate.panel.random')"
              @input="form.seed = ($event.target as HTMLInputElement).value === '' ? null : seedOf(($event.target as HTMLInputElement).value)"
            />
            <button class="btn" :class="{ on: form.seed === null }" :title="t('generate.panel.randomHint')" @click="form.seed = null"><Dices :size="14" /></button>
          </div>
        </div>
        <template v-if="!removing">
          <label v-if="does.count" class="field">
            <span>{{ t('generate.panel.pictures') }} <b>{{ form.count }}</b></span>
            <input v-model.number="form.count" type="range" min="1" max="20" />
          </label>

          <div v-if="loras.length && does.loras" class="field">
            <span>{{ t('generate.panel.loras') }}</span>
            <div v-for="(l, i) in form.loras" :key="i" class="lora">
              <select v-model="l.id"><option v-for="a in loras" :key="a.id" :value="a.id">{{ a.title }}</option></select>
              <!-- a phone's keyboard offers no stepping on a number field: the buttons step the weight by a tenth -->
              <span class="weight">
                <button class="btn small ghost" :aria-label="t('generate.panel.weight') + ' −'" @click="l.scale = stepWeight(l.scale, -0.1)"><Minus :size="12" /></button>
                <input v-model.number="l.scale" type="number" min="-2" max="2" step="0.05" :title="t('generate.panel.weight')" />
                <button class="btn small ghost" :aria-label="t('generate.panel.weight') + ' +'" @click="l.scale = stepWeight(l.scale, 0.1)"><Plus :size="12" /></button>
              </span>
              <button class="btn small ghost" :title="t('generate.panel.remove')" @click="form.loras.splice(i, 1)"><X :size="12" /></button>
            </div>
            <button v-if="form.loras.length < Math.min(MAX_LORAS, loras.length)" class="btn small" @click="addLora"><Plus :size="12" /> {{ t('generate.panel.addLora') }}</button>
          </div>

          <label v-if="model?.meta.negativePrompt" class="field">
            <span>{{ t('generate.panel.negative') }}</span>
            <textarea v-model="form.negativePrompt" rows="10" spellcheck="false" :placeholder="t('generate.panel.negativePlaceholder')" />
          </label>
        </template>
      </div>
    </template>
  </PageFrame>
</template>

<style scoped>
.prompt {
  padding: 12px 12px 10px 14px;
}

/* four remove methods do not fit the panel in one row in the longer languages: two by two */
.methods {
  display: grid;
  grid-template-columns: 1fr 1fr;
  width: 100%;
}
.methods button:last-child:nth-child(odd) {
  grid-column: 1 / -1;
}

.send {
  flex-wrap: wrap;
}

/* longer languages: the parts go to a second line instead of out of the box */
.send > .dim,
.ai-label .check {
  white-space: nowrap;
}

.fields {
  display: grid;
  gap: 18px;
}

.field > span {
  display: flex;
  justify-content: space-between;
}

.field b {
  font-weight: 400;
  color: var(--text-dim);
  font-variant-numeric: tabular-nums;
}

.field textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface-2);
  color: inherit;
  font: 13px/1.5 var(--font);
  outline: 0;
  resize: vertical;
  user-select: text;
}

select,
input[type='number'] {
  width: 100%;
}

input[type='range'] {
  width: 100%;
  accent-color: var(--accent);
}

/* a scale above a slider: a tick per unit, a number every five; inset by half the slider's knob */
.ruler {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  height: 20px;
  margin: 0 8px -4px;
}

.ruler i {
  position: relative;
  width: 1px;
  height: 4px;
  background: var(--text-dim);
  opacity: 0.6;
}

.ruler i.major {
  height: 7px;
  opacity: 1;
}

.ruler em {
  position: absolute;
  bottom: 8px;
  left: 50%;
  transform: translateX(-50%);
  font-style: normal;
  font-size: 10px;
  line-height: 1;
  white-space: nowrap; /* the tick it sits on is 1px wide: "10" would break into two lines */
  color: var(--text-dim);
  font-variant-numeric: tabular-nums;
}

/* the model's own suggestions, while the form differs from them */
.defaults {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.defaults .btn {
  flex: none;
}

/* a value the model is not made for: next to the notice, the button that sets the model's own */
.label-row .fix {
  font-weight: 400;
}

.label-row {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.pair {
  display: flex;
  align-items: center;
  gap: 6px;
}

.ratios {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 4px;
}

/* a tile per ratio: a rectangle in its proportions with the ratio written inside */
.ratio {
  display: grid;
  place-items: center;
  height: 54px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--radius-s);
  background: transparent;
}

.ratio i {
  display: grid;
  place-items: center;
  /* the longer side of the rectangle: shape() gives the sides in percent of it */
  max-width: 46px;
  max-height: 46px;
  box-sizing: border-box;
  border: 1.5px solid var(--text-dim);
  border-radius: 3px;
  font-style: normal;
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  color: var(--text-dim);
}

.ratio:hover {
  background: var(--surface-2);
}

.ratio.on i {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}

.btn.on {
  border-color: var(--accent);
  color: var(--accent);
}

.check {
  display: flex;
  gap: 8px;
  align-items: center;
}

.send .spacer {
  flex: 1;
}

/* wrapped onto a line of its own (longer languages), the button still stands on the right */
.send > .btn.primary {
  margin-left: auto;
}

.ai-label {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-right: 8px;
  font-size: 13px;
}

.ai-label select {
  width: auto;
}

/* the chosen icon as it will look (black on light, white on dark; auto shows the black one) */
.eu-icon {
  height: 22px;
  padding: 4px 6px;
  border-radius: 6px;
  background: #ececec;
  box-sizing: content-box;
}

.eu-icon.white {
  background: #2a2a2a;
}

.check input {
  accent-color: var(--accent);
}

.control {
  min-height: 120px;
}

.control :deep(.empty) {
  min-height: 120px;
}

.control :deep(img) {
  max-height: 220px;
}

.lora {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 6px;
  align-items: center;
}

.weight {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.weight input {
  width: 56px;
  text-align: center;
}
</style>
