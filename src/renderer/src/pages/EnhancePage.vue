<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Photo tools: sharpen, denoise, enlarge, remove JPEG artefacts, remove the background or select objects in a photo,
// with small models on this Mac (engines/diffusers/photo_tools.py): Denoise, Upscale and the JPEG tool as PyTorch
// weights on the GPU, Sharpen and the mask and selection tools as ONNX models on the CPU. The recommended tools are downloaded here at a fixed
// version; any other model that takes a picture and gives a picture or a mask can be imported (.pth, .safetensors,
// .onnx). Results go through the queue, the content filter and the history like every other result.
import { englishToolName } from '@shared/i18n/data'
import { jobLabel } from '../util/labels'
import { computed, onActivated, onMounted, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Download, Eraser, FileUp, Paintbrush, Play, Scissors, Trash2 } from '@lucide/vue'
import PageFrame from '../components/PageFrame.vue'
import ImageInput from '../components/ImageInput.vue'
import ZoomPan from '../components/ZoomPan.vue'
import JobGallery from '../components/JobGallery.vue'
import HintBadge from '../components/HintBadge.vue'
import FactorPicker from '../components/FactorPicker.vue'
import { useHandoffStore } from '../stores/handoff'
import { useImportsStore } from '../stores/imports'
import { useQueueStore } from '../stores/queue'
import { cleanError } from '../stores/runtimes'
import { t } from '../i18n'
import type { PhotoTool, QueuedJob, RecommendedTool, Selected } from '@shared/api'
import { nextRequest, type Click } from '../util/mask_ops'
import type { Job } from '@shared/types'

const queue = useQueueStore()
const imports = useImportsStore()
const handoff = useHandoffStore()
const route = useRoute()
const router = useRouter()

const installed = ref<PhotoTool[]>([])
const recommended = ref<RecommendedTool[]>([])
const chosen = ref('')  // folder of the chosen tool
const input = ref('')
const size = ref<[number, number]>()
const strength = ref(100)
// an enlarging tool: how many times larger the result is than the picture given (the model works at its own scale,
// its result is brought to this size)
const factor = ref(4)
// fine-tuning: another weights file of the tool (Denoise: natural or sharp), the JPEG quality to clean for (0 = auto)
const variant = ref('default')
const quality = ref(0)
// only the exact catalog entry (an older install under another id may work differently, e.g. ONNX)
const options = computed(() => recommended.value.find((r) => r.id === tool.value?.recommended))
const output = ref<'cutout' | 'mask'>('cutout')
const error = ref('')
const jobs = computed(() => queue.ofPage('enhance'))
const tool = computed(() => installed.value.find((tl) => tl.folder === chosen.value))

// selecting (SAM): clicks in picture pixels, the mask they give
// every click is a row of the clicks so far and SAM's candidate, with SAM's answer once it is there, so undo goes back
// exactly (also to a larger candidate) and the next click goes on from the answer of the row it follows
// (shallow: a row is known by itself, it is replaced, never changed)
const rows = shallowRef<{ clicks: Click[]; pick?: number; got?: Selected }[]>([])
const points = computed(() => rows.value[rows.value.length - 1]?.clicks ?? [])
const selection = computed(() => rows.value[rows.value.length - 1]?.got)
// over the picture the last answer stays while the next click is worked on
const shown = computed(() => rows.value.findLast((r) => r.got)?.got)
const selecting = ref(false)
let generation = 0  // an answer that comes back after the picture or the tool changed is dropped
let queued: Click | undefined  // the last click made while a selection ran

async function load(): Promise<void> {
  const list = await window.vk.tools.list()
  installed.value = list.installed
  recommended.value = list.recommended
  if (!tool.value) chosen.value = installed.value[0]?.folder ?? ''
}

async function refresh(): Promise<void> {
  await load()
  const given = handoff.take('enhance')
  if (given?.inputImage) input.value = given.inputImage
}
onMounted(() => void imports.start())
onActivated(refresh)
watch(() => route.query.t, () => { if (route.path === '/enhance') void refresh() })
// a tool that finished downloading shows up
watch(() => imports.jobs.map((j) => j.state).join(), () => void load())
// a new picture forgets the old one's size; another tool keeps it (the picture is still loaded, no new size comes)
watch(input, () => {
  size.value = undefined
})
watch(chosen, () => {
  factor.value = tool.value?.scale ?? 4
  variant.value = 'default'
  quality.value = 0
})
watch([input, chosen], () => {
  error.value = ''
  rows.value = []
  queued = undefined
  generation++
})

const downloading = (tl: RecommendedTool) => {
  const job = imports.of({ source: 'tool', ref: tl.id })
  return job && (job.state === 'waiting' || job.state === 'running') ? job : undefined
}
const failed = (tl: RecommendedTool) => {
  const job = imports.of({ source: 'tool', ref: tl.id })
  return job?.state === 'failed' ? job.error : undefined
}
const toInstall = computed(() => recommended.value.filter((tl) => !tl.installed))
// a tool installed before the catalog carried licence notes: the note comes from the catalog
const noteOf = (tl: PhotoTool): string | undefined => tl.licenceNote ?? recommended.value.find((r) => r.id === tl.recommended)?.licenceNote
const importing = computed(() => imports.jobs.findLast((j) => j.request.source === 'toolfile' || (j.request.source === 'file' && j.request.ref.toLowerCase().endsWith('.onnx'))))
const where = (tl: { runtime: 'torch' | 'onnx' }): string => (tl.runtime === 'torch' ? 'GPU' : 'CPU')

// The list shows a few words per tool; everything else is in its info badge. A tool installed before the catalog
// had summaries (or under an older id) takes the catalog's current one (the tool with the same task).
const catalogOf = (tl: PhotoTool): RecommendedTool | undefined =>
  recommended.value.find((r) => r.id === tl.recommended) ?? (tl.recommended ? recommended.value.find((r) => r.task === tl.task) : undefined)
const summaryOf = (tl: PhotoTool): string => catalogOf(tl)?.summary ?? tl.summary ?? tl.description

// "Remove background (BiRefNet)" -> "Remove background" in the list (one line); the model's name goes into the badge
// (a recommended tool takes the catalog's current name, so a tool installed under an older, longer name gets it too)
const fullName = (tl: PhotoTool | RecommendedTool): string => ('id' in tl ? tl : catalogOf(tl) ?? tl).name
const shortName = (tl: PhotoTool | RecommendedTool): string => fullName(tl).replace(/\s*\([^)]*\)\s*$/, '') || fullName(tl)

// the badge: what the tool does and where it runs; below a line, the licence with its note and the source
const variantInfo = computed(() => {
  const o = options.value
  if (!o?.variants) return ''
  const own = t('edit.enhance.variantOwn', { label: o.defaultLabel ?? t('edit.enhance.standard') })
  return [own, ...o.variants.map((v) => t('edit.enhance.variantOther', { label: v.label, description: v.description, size: v.sizeMb }))].join(' ')
})

function infoOf(tl: PhotoTool | RecommendedTool): string {
  const runs = tl.runtime === 'torch' ? t('edit.enhance.runsGpu') : t('edit.enhance.runsCpu')
  const side = tl.maxSide ? t('edit.enhance.madeSmaller', { side: tl.maxSide }) : ''
  const size = 'sizeMb' in tl ? t('edit.enhance.download', { size: tl.sizeMb }) : ''
  return [`${fullName(tl)}: ${tl.description}`, runs, side, size].filter(Boolean).join(' ')
}

function licenceOf(tl: PhotoTool | RecommendedTool): string | undefined {
  const note = 'id' in tl ? tl.licenceNote : noteOf(tl)
  const lines = [tl.licence ? t('edit.enhance.licence', { licence: tl.licence }) : '', note ?? '', tl.sourceUrl ? t('edit.enhance.source', { url: tl.sourceUrl }) : '']
  return lines.filter(Boolean).join('\n') || undefined
}

async function install(tl: RecommendedTool): Promise<void> {
  error.value = ''
  try {
    await window.vk.tools.install(tl.id)
  } catch (err) {
    error.value = cleanError(err)
  }
}

async function importFile(): Promise<void> {
  error.value = ''
  try {
    await window.vk.tools.importFile()
  } catch (err) {
    error.value = cleanError(err)
  }
}

async function remove(tl: PhotoTool): Promise<void> {
  error.value = ''
  try {
    await window.vk.tools.remove(tl.folder)
    await load()
  } catch (err) {
    error.value = cleanError(err)
  }
}

const target = computed((): [number, number] | undefined => {
  if (!size.value || !tool.value) return size.value
  const tl = tool.value
  if (tl.kind !== 'image' || tl.scale <= 1) return size.value
  // a picture over the tool's limit is made smaller to it first; the result then at most the tool's scale of that
  const k = tl.maxSide && Math.max(...size.value) > tl.maxSide ? tl.maxSide / Math.max(...size.value) : 1
  const most = (v: number): number => Math.round(v * k) * tl.scale
  const want = (v: number): number => Math.round(v * Math.min(factor.value, tl.scale))
  return [Math.min(want(size.value[0]), most(size.value[0])), Math.min(want(size.value[1]), most(size.value[1]))]
})
const result = computed(() => (target.value && tool.value ? `${target.value[0]} × ${target.value[1]}` : ''))

async function run(out: 'cutout' | 'mask' = output.value): Promise<void> {
  const tl = tool.value
  error.value = !input.value ? t('edit.enhance.choosePicture') : !tl ? t('edit.enhance.chooseTool') : ''
  if (tl?.kind === 'segment' && !selection.value) error.value = t('edit.enhance.clickToSelect')
  // an image tool takes a larger picture made smaller first (photo_tools.apply says so in the result's note)
  if (tl?.kind !== 'image' && tl?.maxSide && size.value && Math.max(...size.value) > tl.maxSide) error.value = t('edit.enhance.tooLarge', { name: fullName(tl), side: tl.maxSide })
  if (error.value || !tl) return
  try {
    await queue.add({
      page: 'enhance', prompt: '', modelId: '', modelDir: '', width: target.value?.[0] ?? 0, height: target.value?.[1] ?? 0, seed: 0,
      // the label in English, as every label a job keeps (labels.ts shows it in the app's language)
      inputImage: input.value, label: englishToolName(catalogOf(tl)?.id) ?? fullName(tl),
      photoTool: { folder: tl.folder, strength: strength.value / 100, factor: tl.scale > 1 ? factor.value : undefined,
        variant: variant.value !== 'default' ? variant.value : undefined, quality: options.value?.quality && quality.value ? quality.value : undefined, output: out, mask: selection.value?.mask },
    })
  } catch (err) {
    error.value = cleanError(err)
  }
}

// a click on the picture: left = belongs to it, with ⌥ = does not
async function click(event: MouseEvent): Promise<void> {
  const tl = tool.value
  if (!tl || tl.kind !== 'segment' || !size.value) return
  const img = event.currentTarget as HTMLElement
  const box = img.getBoundingClientRect()
  const x = Math.round(((event.clientX - box.left) / box.width) * size.value[0])
  const y = Math.round(((event.clientY - box.top) / box.height) * size.value[1])
  await select([x, y, event.altKey ? 0 : 1])
}

async function select(c: Click): Promise<void> {
  const tl = tool.value
  // a click while one is worked on: the last such click follows once it is done (as in the mask brush)
  if (selecting.value) {
    queued = c
    return
  }
  if (!tl || !size.value) return
  // the first click the whole thing, a click on the same spot again a smaller part of it (mask_ops.nextRequest)
  const last = rows.value[rows.value.length - 1]
  const prev = last ? { clicks: last.clicks, pick: last.got?.pick, candidates: last.got?.candidates } : undefined
  const row: { clicks: Click[]; pick?: number } = nextRequest(prev, c, Math.min(...size.value) * 0.02)
  rows.value = [...rows.value, row]
  const made = generation
  selecting.value = true
  error.value = ''
  try {
    const got = await window.vk.tools.select(tl.folder, input.value, row.clicks.map((p) => [p[0], p[1], p[2]] as Click), row.pick)
    // only for the row it was asked for, while that is still the last one
    if (made === generation && rows.value[rows.value.length - 1] === row) rows.value = [...rows.value.slice(0, -1), { ...row, got }]
  } catch (err) {
    // the click gave nothing: it goes, the selection before it stays
    if (made === generation) {
      error.value = cleanError(err)
      rows.value = rows.value.filter((r) => r !== row)
    }
  } finally {
    selecting.value = false
  }
  const next = queued
  queued = undefined
  if (next && made === generation) await select(next)
}

function undoClick(): void {
  rows.value = rows.value.slice(0, -1)
}

function toInpaint(): void {
  if (!selection.value) return
  handoff.send('inpaint', { inputImage: input.value, maskImage: selection.value.mask })
  void router.push({ path: '/inpaint', query: { t: Date.now() } })
}

const pct = (x: number, side: number): string => `${(x / side) * 100}%`
// the selection over the picture: tinted in the accent colour, and everything else dimmed (the mask turned round by
// excluding it from a full layer), so it shows also on warm or orange photos
const overlay = (mask: string, outside: boolean): Record<string, string> => {
  const url = `url("${window.vk.files.url(mask)}")`
  const image = outside ? `linear-gradient(#fff, #fff), ${url}` : url
  return {
    maskImage: image, webkitMaskImage: image, maskMode: 'luminance', maskSize: '100% 100%', webkitMaskSize: '100% 100%',
    ...(outside ? { maskComposite: 'exclude', webkitMaskComposite: 'xor' } : {}),
  }
}

function open(q: QueuedJob, file: string): void {
  const pictures = jobs.value.flatMap((x) => queue.shown(x).map((f) => ({ job: JSON.parse(JSON.stringify(x.job)) as Job, file: f, model: x.job.label ? jobLabel(x.job.label) : t('edit.enhance.photoTool') })))
  void window.vk.viewer.open(pictures, pictures.findIndex((p) => p.file === file && p.job.id === q.job.id))
}
</script>

<template>
  <PageFrame :title="t('edit.enhance.title')" :subtitle="t('edit.enhance.subtitle')">
    <div class="page-grid">
      <ImageInput v-model="input" @size="(w, h) => (size = [w, h])">
        <template v-if="tool?.kind === 'segment'" #default="{ src, loaded }">
          <ZoomPan><div class="pick" :class="{ busy: selecting }">
            <img :src="src" draggable="false" @load="loaded" @click="click" />
            <template v-if="shown">
              <div class="overlay outside" :style="overlay(shown.mask, true)" />
              <div class="overlay inside" :style="overlay(shown.mask, false)" />
            </template>
            <span
              v-for="(p, i) in size ? points : []" :key="i" class="dot" :class="{ no: !p[2] }"
              :style="{ left: pct(p[0], size![0]), top: pct(p[1], size![1]) }"
            />
          </div></ZoomPan>
        </template>
      </ImageInput>
      <div class="send">
        <span v-if="error" class="error selectable">{{ error }}</span>
        <span v-else-if="tool?.kind === 'segment'" class="dim">
          {{ points.length ? t('edit.enhance.clicks', { n: points.length }) : t('edit.enhance.selectHint') }}
        </span>
        <span v-else-if="size && result" class="dim">{{ t('edit.becomes', { size: `${size[0]} × ${size[1]}`, result }) }}</span>
        <span v-else />
        <div class="actions">
          <template v-if="tool?.kind === 'segment'">
            <button class="btn" :disabled="!points.length" @click="undoClick"><Eraser :size="14" /> {{ t('edit.enhance.undoClick') }}</button>
            <button class="btn" :disabled="!selection" @click="toInpaint"><Paintbrush :size="14" /> {{ t('edit.enhance.toInpaint') }}</button>
            <button class="btn" :disabled="!selection" @click="run('mask')">{{ t('edit.enhance.saveMask') }}</button>
            <button class="btn primary" :disabled="!selection" @click="run('cutout')"><Scissors :size="14" /> {{ t('edit.enhance.cutOut') }}</button>
          </template>
          <button v-else class="btn primary" :disabled="!input || !tool" @click="run()">
            <component :is="tool?.kind === 'mask' ? Scissors : Play" :size="14" /> {{ tool?.kind === 'mask' ? t('edit.enhance.cutOut') : t('edit.enhance.apply') }}
          </button>
        </div>
      </div>
      <JobGallery :jobs="jobs" @open="open" />
    </div>

    <template #panel>
      <div class="fields">
        <div class="field">
          <span>{{ t('edit.enhance.tool') }}</span>
          <p v-if="!installed.length" class="dim">{{ t('edit.enhance.noTool') }}</p>
          <label v-for="tl in installed" :key="tl.folder" class="tool" :class="{ on: chosen === tl.folder }">
            <input v-model="chosen" type="radio" :value="tl.folder" />
            <div class="grow">
              <strong>{{ shortName(tl) }}</strong>
              <small class="dim"><span class="where" :class="tl.runtime === 'torch' ? 'gpu' : 'cpu'">{{ where(tl) }}</span>{{ summaryOf(tl) }}</small>
            </div>
            <HintBadge :text="infoOf(tl)" :more="licenceOf(tl)" above />
            <button class="btn small ghost" :title="t('edit.enhance.trash')" @click.prevent="remove(tl)"><Trash2 :size="12" /></button>
          </label>
        </div>

        <div v-if="tool?.kind === 'image' && tool.scale > 1" class="field">
          <span class="title">{{ t('edit.enlargeBy', { factor }) }} <HintBadge start :text="t('edit.enhance.scaleHint', { scale: tool.scale })" /></span>
          <FactorPicker v-model="factor" :max="tool.scale" />
        </div>
        <div v-if="options?.variants?.length" class="field">
          <span class="title">{{ t('edit.enhance.character') }} <HintBadge start :text="variantInfo" /></span>
          <div class="presets wide">
            <button class="preset" :class="{ on: variant === 'default' }" @click="variant = 'default'">{{ options.defaultLabel ?? t('edit.enhance.standard') }}</button>
            <button v-for="v in options.variants" :key="v.id" class="preset" :class="{ on: variant === v.id }" @click="variant = v.id">{{ v.label }}</button>
          </div>
        </div>
        <div v-if="options?.quality" class="field">
          <span class="title">{{ t('edit.enhance.jpegQuality', { quality: quality ? quality : t('edit.enhance.auto') }) }} <HintBadge start :text="t('edit.enhance.jpegQualityHint')" /></span>
          <div class="presets">
            <button class="preset" :class="{ on: !quality }" @click="quality = 0">{{ t('edit.enhance.auto') }}</button>
            <button v-for="q in [10, 30, 50, 70, 90]" :key="q" class="preset" :class="{ on: quality === q }" @click="quality = q">{{ q }}</button>
          </div>
          <input v-model.number="quality" type="range" min="0" max="95" step="5" :aria-label="t('edit.enhance.jpegQualityLabel')" />
        </div>
        <div v-if="tool?.kind === 'image'" class="field">
          <span class="title">{{ t('edit.enhance.strength', { strength }) }} <HintBadge start :text="t('edit.enhance.strengthHint')" /></span>
          <input v-model.number="strength" type="range" min="10" max="100" step="5" />
        </div>
        <div v-if="tool?.kind === 'mask'" class="field">
          <span>{{ t('edit.enhance.result') }}</span>
          <div class="two">
            <button class="btn" :class="{ on: output === 'cutout' }" @click="output = 'cutout'">{{ t('edit.enhance.transparent') }}</button>
            <button class="btn" :class="{ on: output === 'mask' }" @click="output = 'mask'">{{ t('edit.enhance.mask') }}</button>
          </div>
        </div>

        <div v-if="toInstall.length" class="field">
          <span class="title">{{ t('edit.enhance.recommended') }} <HintBadge start :text="t('edit.enhance.recommendedHint')" /></span>
          <div v-for="tl in toInstall" :key="tl.id" class="tool">
            <div class="grow">
              <strong>{{ shortName(tl) }}</strong>
              <small class="dim"><span class="where" :class="tl.runtime === 'torch' ? 'gpu' : 'cpu'">{{ where(tl) }}</span>{{ tl.summary ?? tl.description }}</small>
              <small v-if="failed(tl)" class="error">{{ failed(tl) }}</small>
            </div>
            <HintBadge :text="infoOf(tl)" :more="licenceOf(tl)" above />
            <span v-if="downloading(tl)" class="dim">{{ downloading(tl)!.percent >= 0 ? `${Math.round(downloading(tl)!.percent)} %` : '…' }}</span>
            <button v-else class="btn small" @click="install(tl)"><Download :size="12" /> {{ t('edit.enhance.downloadButton') }}</button>
          </div>
        </div>

        <div class="field">
          <button class="btn" @click="importFile"><FileUp :size="14" /> {{ t('edit.enhance.importFile') }}</button>
          <small v-if="importing?.state === 'failed'" class="error selectable">{{ importing.error }}</small>
          <small v-else-if="importing && (importing.state === 'running' || importing.state === 'waiting')" class="dim">{{ t('edit.enhance.checking', { title: importing.title }) }}</small>
          <span class="dim small-row">
            {{ t('edit.enhance.fileTypes') }}
            <HintBadge above :text="t('edit.enhance.fileTypesHint')" />
          </span>
        </div>
      </div>
    </template>
  </PageFrame>
</template>

<style scoped>
.actions {
  display: flex;
  gap: 8px;
}

.pick {
  position: relative;
  display: inline-block;
  max-width: 100%;
  max-height: 100%;
  cursor: crosshair;
}

.pick img {
  display: block;
  max-width: 100%;
  max-height: 60vh;
}

.pick .overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.pick .overlay.inside {
  background: var(--accent);
  opacity: 0.35;
}

.pick .overlay.outside {
  background: #000;
  opacity: 0.5;
}

.pick.busy {
  cursor: progress;
}

.dot {
  position: absolute;
  width: 12px;
  height: 12px;
  margin: -6px 0 0 -6px;
  border-radius: 50%;
  background: var(--accent);
  border: 2px solid #fff;
  pointer-events: none;
}

.dot.no {
  background: #222;
}

.fields,
.field {
  display: grid;
  gap: 10px;
}


/* the panel's sections (tool, strength or result, recommended, import) set apart by a full line */
.fields > .field + .field {
  margin-top: 6px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.title {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tool {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: var(--radius-s);
}

.tool.on {
  background: color-mix(in srgb, var(--surface) 88%, var(--accent));
}

/* a line between two tools, starting at the name and ending short of the edge */
.tool + .tool::before {
  content: '';
  position: absolute;
  top: -5px;
  left: 34px;
  right: 14px;
  height: 1px;
  background: var(--line);
}

div.tool + div.tool::before {
  left: 10px;
}

.tool .grow {
  display: grid;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

/* the name on one line; one too long for the panel is cut, the badge has it in full */
.tool .grow strong {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

/* where the tool runs, under the name: GPU (PyTorch weights) or CPU (ONNX), tinted like the navigation's groups
   (mixed into the theme's surface, so it works light and dark) */
.tool .where {
  display: inline-block;
  margin-right: 6px;
  padding: 0 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.03em;
  color: var(--text);
  vertical-align: 1px;
}

.tool .where.gpu {
  background: color-mix(in srgb, var(--surface) 75%, #a66bff);
}

.tool .where.cpu {
  background: color-mix(in srgb, var(--surface) 75%, #2bb5a8);
}

/* choices of a tool (character, JPEG quality) as small tiles, like the enlargement presets */
.presets {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(48px, 1fr));
  gap: 6px;
}

.preset {
  padding: 7px 4px;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface);
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

/* words (Natural, Sharp) need more room than numbers */
.presets.wide {
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
}

.preset {
  white-space: nowrap;
}

.preset:hover {
  border-color: var(--text-dim);
}

.preset.on {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--surface) 88%, var(--accent));
  color: var(--accent);
}

.two {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.two .btn {
  justify-content: center;
}

.btn.on {
  border-color: var(--accent);
  color: var(--accent);
}

.small-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
</style>
