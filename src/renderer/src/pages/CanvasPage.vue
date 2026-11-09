<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// The AI Canvas: an endless surface with pictures as layers and a frame in which the model paints. An empty
// frame gives a new picture; a frame over the edge of a picture extends it; a painted mask repaints a part;
// a covered frame without a mask gives a variation. The jobs run through the queue like all others.
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from 'vue'
import { Brush, Download, ImagePlus, Layers, Maximize, Move, Scaling, Sparkles, Square, Trash2, Undo2 } from '@lucide/vue'
import PageFrame from '../components/PageFrame.vue'
import JobGallery from '../components/JobGallery.vue'
import HintBadge from '../components/HintBadge.vue'
import { stepsHint } from '../util/model_fit'
import { useAssetsStore } from '../stores/assets'
import { useQueueStore } from '../stores/queue'
import { cleanError } from '../stores/runtimes'
import { PLAN_TEXT, coverage, fitView, frameFor, planFor, resizeFrame, type Corner, type Layer, type Rect } from '../util/canvas_plan'
import { formatDuration } from '../util/format'
import { CONSENT_QUESTION } from '@shared/content_policy'
import type { Job } from '@shared/types'
import type { QueuedJob } from '@shared/api'
import { seedOf } from '@/util/seed'
import { pickImage } from '../util/pick_image'
import { askConsent } from '../util/consent'
import { t } from '../i18n'

const RATIOS = [{ id: '1:1', w: 1, h: 1 }, { id: '3:4', w: 3, h: 4 }, { id: '4:3', w: 4, h: 3 }, { id: '16:9', w: 16, h: 9 }, { id: '9:16', w: 9, h: 16 }]
// model families that can fill a masked part
const FILL_FAMILIES = ['sdxl', 'sd3', 'flux1', 'chroma', 'z_image']
const STORE_KEY = 'vk.canvas'

const assets = useAssetsStore()
const queue = useQueueStore()

const prompt = ref('')
const negative = ref('')
const modelId = ref('')
const ratio = ref('1:1')
const steps = ref(25)
const seed = ref<number | null>(null)
const variation = ref(0.5)
const layers = ref<Layer[]>([])
const selected = ref('')
const undoStack: string[] = []
const canUndo = ref(false)
const frame = ref<Rect>({ x: 0, y: 0, w: 1024, h: 1024 })
const view = reactive({ ox: 200, oy: 60, scale: 0.5 })
const tool = ref<'move' | 'mask'>('move')
const brush = ref(60)
const hasMask = ref(false)
const error = ref('')
/** the job that paints into the frame, and where the frame was when it was sent */
const pending = ref<{ id: string; frame: Rect }>()
const stage = ref<HTMLElement>()
const mask = ref<HTMLCanvasElement>()

const models = computed(() => assets.models
  .filter((m) => m.meta.kind === 'image' && m.meta.runtime !== 'comfyui' && !m.meta.inpaintOnly)
  .map((m) => ({ asset: m, canFill: m.meta.inpaint === true || FILL_FAMILIES.includes(m.meta.family) })))
const model = computed(() => models.value.find((m) => m.asset.id === modelId.value))
const native = computed(() => Number(model.value?.asset.meta.defaults?.width) || 1024)
// steps far above what a distilled model is made for (typed in; a new model brings its own)
const stepsFit = computed(() => stepsHint(model.value?.asset.meta, steps.value))
const covered = computed(() => coverage(frame.value, layers.value))
const plan = computed(() => planFor(covered.value, hasMask.value))
const running = computed(() => queue.jobs.find((j) => j.job.id === pending.value?.id))
// the queue and the recent results of this page, in a row below the surface
const jobs = computed(() => queue.ofPage('canvas'))

function open(q: QueuedJob, file: string): void {
  const pictures = jobs.value.flatMap((x) => queue.shown(x).map((f) => ({ job: JSON.parse(JSON.stringify(x.job)) as Job, file: f, model: assets.titleOf(x.job.modelDir) })))
  void window.vk.viewer.open(pictures, pictures.findIndex((p) => p.file === file && p.job.id === q.job.id))
}
const busy = computed(() => !!pending.value)
const blocked = computed(() => {
  if (!model.value) return t('canvas.noModel')
  if (!prompt.value.trim()) return t('canvas.noPrompt')
  if (plan.value !== 'new' && !model.value.canFill && !(plan.value === 'variation' && model.value.asset.meta.img2img)) return t('canvas.newOnly')
  return ''
})
const url = (path: string): string => window.vk.files.url(path)

// ------------------------------------------------------------------ state that survives restarts
function save(): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({ layers: layers.value, frame: frame.value, view: { ...view }, ratio: ratio.value, model: modelId.value, prompt: prompt.value, negative: negative.value }))
  } catch {
    // not remembered then
  }
}
let saveTimer: ReturnType<typeof setTimeout> | undefined
const saveSoon = (): void => {
  clearTimeout(saveTimer)
  saveTimer = setTimeout(save, 500)
}

function restore(): boolean {
  try {
    const st = JSON.parse(localStorage.getItem(STORE_KEY) ?? 'null')
    if (!st) return false
    layers.value = Array.isArray(st.layers) ? st.layers : []
    ratio.value = st.ratio ?? '1:1'
    if (st.frame) frame.value = st.frame
    if (st.view) Object.assign(view, st.view)
    modelId.value = st.model ?? ''
    prompt.value = st.prompt ?? ''
    negative.value = st.negative ?? ''
    return true
  } catch {
    return false
  }
}

function snapshot(): void {
  undoStack.push(JSON.stringify(layers.value))
  if (undoStack.length > 50) undoStack.shift()
  canUndo.value = true
}

function undo(): void {
  const last = undoStack.pop()
  if (last) layers.value = JSON.parse(last)
  canUndo.value = undoStack.length > 0
}

// ------------------------------------------------------------------ frame, layers, view
function setRatio(id: string): void {
  ratio.value = id
  // a frame resized by hand keeps its size (also for another model)
  if (id === 'free') {
    void nextTick(clearMask)
    return
  }
  const r = RATIOS.find((x) => x.id === id) ?? RATIOS[0]
  frame.value = frameFor(r, native.value, frame.value)
  void nextTick(clearMask)
}

function toWorld(event: MouseEvent): { x: number; y: number } {
  const box = (stage.value as HTMLElement).getBoundingClientRect()
  return { x: (event.clientX - box.left - view.ox) / view.scale, y: (event.clientY - box.top - view.oy) / view.scale }
}

const inRect = (p: { x: number; y: number }, r: Rect): boolean => p.x >= r.x && p.x < r.x + r.w && p.y >= r.y && p.y < r.y + r.h

function onFrameBorder(p: { x: number; y: number }): boolean {
  const f = frame.value
  const m = 12 / view.scale
  const outer = p.x >= f.x - m && p.x <= f.x + f.w + m && p.y >= f.y - m && p.y <= f.y + f.h + m
  const inner = p.x > f.x + m && p.x < f.x + f.w - m && p.y > f.y + m && p.y < f.y + f.h - m
  return outer && !inner
}

const CORNERS: Corner[] = ['nw', 'ne', 'sw', 'se']
const cornerPoint = (l: Rect, c: Corner): { x: number; y: number } => ({ x: c[1] === 'w' ? l.x : l.x + l.w, y: c[0] === 'n' ? l.y : l.y + l.h })

/** The corner handle of the selected picture under a point (they take precedence over the frame's border). */
function handleAt(p: { x: number; y: number }): Corner | undefined {
  const layer = layers.value.find((l) => l.id === selected.value)
  if (!layer) return undefined
  const m = 10 / view.scale
  return CORNERS.find((c) => {
    const q = cornerPoint(layer, c)
    return Math.abs(p.x - q.x) <= m && Math.abs(p.y - q.y) <= m
  })
}

/** Resizes a picture from a corner: the opposite corner stays, the proportions too unless Shift is held. */
function resizeMove(layer: Layer, corner: Corner, start: { x: number; y: number }, ev: MouseEvent): Layer {
  const dx = (ev.clientX - start.x) / view.scale
  const dy = (ev.clientY - start.y) / view.scale
  const left = corner[1] === 'w'
  const top = corner[0] === 'n'
  let w = Math.max(32, layer.w + (left ? -dx : dx))
  let h = Math.max(32, layer.h + (top ? -dy : dy))
  if (!ev.shiftKey) {
    const k = Math.max(w / layer.w, h / layer.h)
    w = Math.max(32, layer.w * k)
    h = Math.max(32, layer.h * k)
  }
  w = Math.round(w)
  h = Math.round(h)
  return { ...layer, w, h, x: left ? layer.x + layer.w - w : layer.x, y: top ? layer.y + layer.h - h : layer.y }
}

/** The selected picture as large as fits into the frame, centred, proportions kept. */
function fitToFrame(): void {
  const layer = layers.value.find((l) => l.id === selected.value)
  if (!layer) return
  snapshot()
  const f = frame.value
  const k = Math.min(f.w / layer.w, f.h / layer.h)
  const [w, h] = [Math.round(layer.w * k), Math.round(layer.h * k)]
  const fitted = { ...layer, w, h, x: f.x + Math.round((f.w - w) / 2), y: f.y + Math.round((f.h - h) / 2) }
  layers.value = layers.value.map((l) => (l.id === layer.id ? fitted : l))
}

/** The corner handle of the frame under a point. */
function frameHandleAt(p: { x: number; y: number }): Corner | undefined {
  const m = 10 / view.scale
  return CORNERS.find((c) => {
    const q = cornerPoint(frame.value, c)
    return Math.abs(p.x - q.x) <= m && Math.abs(p.y - q.y) <= m
  })
}

const selectedLayer = computed(() => layers.value.find((l) => l.id === selected.value))

function layerAt(p: { x: number; y: number }): Layer | undefined {
  for (let i = layers.value.length - 1; i >= 0; i--) if (inRect(p, layers.value[i])) return layers.value[i]
  return undefined
}

function onWheel(event: WheelEvent): void {
  if (event.ctrlKey || event.metaKey) {
    const box = (stage.value as HTMLElement).getBoundingClientRect()
    const [mx, my] = [event.clientX - box.left, event.clientY - box.top]
    const scale = Math.min(4, Math.max(0.05, view.scale * Math.exp(-event.deltaY * 0.01)))
    view.ox = mx - ((mx - view.ox) * scale) / view.scale
    view.oy = my - ((my - view.oy) * scale) / view.scale
    view.scale = scale
  } else {
    view.ox -= event.deltaX
    view.oy -= event.deltaY
  }
  saveSoon()
}

function onDown(event: MouseEvent): void {
  if (event.button !== 0) return
  const p = toWorld(event)
  const start = { x: event.clientX, y: event.clientY }
  let move: (ev: MouseEvent) => void
  const corner = tool.value === 'move' ? handleAt(p) : undefined
  const frameCorner = tool.value === 'move' && !corner ? frameHandleAt(p) : undefined
  if (frameCorner) {
    clearMask()  // a mask belongs to the frame's old size
    const from = { ...frame.value }
    move = (ev) => {
      frame.value = resizeFrame(from, frameCorner, (ev.clientX - start.x) / view.scale, (ev.clientY - start.y) / view.scale, native.value)
      ratio.value = 'free'
    }
  } else if (corner) {
    const layer = layers.value.find((l) => l.id === selected.value) as Layer
    snapshot()
    move = (ev) => {
      const resized = resizeMove(layer, corner, start, ev)
      layers.value = layers.value.map((l) => (l.id === layer.id ? resized : l))
    }
  } else if (tool.value === 'mask' && inRect(p, frame.value)) {
    paintMask(p)
    move = (ev) => paintMask(toWorld(ev))
  } else if (onFrameBorder(p) || (tool.value === 'move' && inRect(p, frame.value) && !layerAt(p))) {
    const from = { ...frame.value }
    // the frame moves in steps of 8, so it lines up with what is there
    move = (ev) => {
      frame.value = { ...frame.value, x: Math.round((from.x + (ev.clientX - start.x) / view.scale) / 8) * 8, y: Math.round((from.y + (ev.clientY - start.y) / view.scale) / 8) * 8 }
    }
  } else if (tool.value === 'move' && layerAt(p)) {
    const layer = layerAt(p) as Layer
    selected.value = layer.id
    snapshot()
    const from = { x: layer.x, y: layer.y }
    move = (ev) => {
      layers.value = layers.value.map((l) => (l.id === layer.id ? { ...l, x: Math.round(from.x + (ev.clientX - start.x) / view.scale), y: Math.round(from.y + (ev.clientY - start.y) / view.scale) } : l))
    }
  } else {
    selected.value = ''
    const from = { ox: view.ox, oy: view.oy }
    move = (ev) => {
      view.ox = from.ox + ev.clientX - start.x
      view.oy = from.oy + ev.clientY - start.y
    }
  }
  const up = (): void => {
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
    saveSoon()
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}

function paintMask(p: { x: number; y: number }): void {
  const ctx = mask.value?.getContext('2d')
  if (!ctx) return
  ctx.fillStyle = '#ff8a3d'
  ctx.beginPath()
  ctx.arc(p.x - frame.value.x, p.y - frame.value.y, brush.value / 2, 0, 2 * Math.PI)
  ctx.fill()
  hasMask.value = true
}

function clearMask(): void {
  const c = mask.value
  c?.getContext('2d')?.clearRect(0, 0, c.width, c.height)
  hasMask.value = false
}

function removeSelected(): void {
  if (!selected.value) return
  snapshot()
  layers.value = layers.value.filter((l) => l.id !== selected.value)
  selected.value = ''
}

function toFront(): void {
  const layer = layers.value.find((l) => l.id === selected.value)
  if (!layer) return
  snapshot()
  layers.value = [...layers.value.filter((l) => l.id !== layer.id), layer]
}

function addLayer(src: string, rect: Rect): void {
  snapshot()
  const layer: Layer = { id: Math.random().toString(36).slice(2), src, ...rect }
  layers.value = [...layers.value, layer]
  selected.value = layer.id
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'  // keeps canvases readable that it is drawn into
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('a picture of the canvas could not be loaded'))
    img.src = src
  })
}

async function addPicture(): Promise<void> {
  const path = await pickImage()
  if (!path) return
  try {
    const img = await loadImage(url(path))
    const s = Math.min(1, native.value / Math.max(img.width, img.height))
    addLayer(path, { x: frame.value.x, y: frame.value.y, w: Math.round(img.width * s), h: Math.round(img.height * s) })
  } catch (err) {
    error.value = cleanError(err)
  }
}

function fit(): void {
  const box = (stage.value as HTMLElement).getBoundingClientRect()
  Object.assign(view, fitView([...layers.value, frame.value], box.width, box.height))
  saveSoon()
}

// ------------------------------------------------------------------ painting into the frame

/** The layers under a rectangle drawn into a canvas; what no picture covers stays transparent. */
async function renderArea(r: Rect): Promise<HTMLCanvasElement> {
  const c = document.createElement('canvas')
  ;[c.width, c.height] = [r.w, r.h]
  const ctx = c.getContext('2d') as CanvasRenderingContext2D
  for (const l of layers.value) {
    if (l.x >= r.x + r.w || l.x + l.w <= r.x || l.y >= r.y + r.h || l.y + l.h <= r.y) continue
    ctx.drawImage(await loadImage(url(l.src)), l.x - r.x, l.y - r.y, l.w, l.h)
  }
  return c
}

async function buildJob(): Promise<Omit<Job, 'id'>> {
  const f = frame.value
  const m = (model.value as NonNullable<typeof model.value>).asset
  const job: Omit<Job, 'id'> = {
    page: 'canvas', prompt: prompt.value.trim(), modelId: m.id, modelDir: m.folder, width: f.w, height: f.h, steps: steps.value,
    guidance: typeof m.meta.defaults?.guidance_scale === 'number' ? m.meta.defaults.guidance_scale : undefined,
    seed: seed.value ?? -1, exactSize: true,
  }
  if (m.meta.negativePrompt && negative.value.trim()) job.negativePrompt = negative.value.trim()
  if (plan.value === 'new') return job
  const area = await renderArea(f)
  // the start picture: what is there, empty parts in neutral grey
  const init = document.createElement('canvas')
  ;[init.width, init.height] = [f.w, f.h]
  const ictx = init.getContext('2d') as CanvasRenderingContext2D
  ictx.fillStyle = '#808080'
  ictx.fillRect(0, 0, f.w, f.h)
  ictx.drawImage(area, 0, 0)
  job.inputImage = await window.vk.files.writeImage(init.toDataURL('image/png'))
  if (plan.value === 'variation') {
    job.strength = variation.value
    return job
  }
  // the mask: the empty parts and the brush strokes, white where the model paints
  const data = (area.getContext('2d') as CanvasRenderingContext2D).getImageData(0, 0, f.w, f.h).data
  const strokes = hasMask.value ? mask.value?.getContext('2d')?.getImageData(0, 0, f.w, f.h).data : undefined
  const out = document.createElement('canvas')
  ;[out.width, out.height] = [f.w, f.h]
  const octx = out.getContext('2d') as CanvasRenderingContext2D
  const pixels = octx.createImageData(f.w, f.h)
  for (let i = 0; i < f.w * f.h; i++) {
    const paint = data[i * 4 + 3] < 250 || (strokes !== undefined && strokes[i * 4 + 3] > 0)
    pixels.data[i * 4] = pixels.data[i * 4 + 1] = pixels.data[i * 4 + 2] = paint ? 255 : 0
    pixels.data[i * 4 + 3] = 255
  }
  octx.putImageData(pixels, 0, 0)
  job.maskImage = await window.vk.files.writeImage(out.toDataURL('image/png'))
  // extending: the strip along the edge starts from the colours there, so light and colours go on. The empty
  // part itself is painted from scratch: anything less than full strength keeps the smeared colours, and fast
  // models with few steps then leave a flat area
  job.prefill = plan.value === 'extend'
  job.strength = 1
  return job
}

async function generate(): Promise<void> {
  error.value = blocked.value
  if (error.value || busy.value) return
  const at = { ...frame.value }
  try {
    const job = await buildJob()
    let ids: string[]
    try {
      ids = await queue.add(job)
    } catch (err) {
      if (cleanError(err) !== CONSENT_QUESTION) throw err
      if (!(await askConsent())) return
      ids = await queue.add({ ...job, consent: true })
    }
    pending.value = { id: ids[0], frame: at }
  } catch (err) {
    error.value = cleanError(err)
  }
}

// the finished picture becomes a layer where the frame was
watch(running, (job) => {
  const waiting = pending.value
  if (!waiting) return
  if (!job) {
    pending.value = undefined  // removed from the queue
    return
  }
  if (job.state === 'done' && job.results[0]) {
    addLayer(job.results[0], waiting.frame)
    clearMask()
    pending.value = undefined
  } else if (job.state === 'failed' || job.state === 'cancelled') {
    if (job.state === 'failed') error.value = job.error ?? t('canvas.failed')
    pending.value = undefined
  }
})

async function exportPng(): Promise<void> {
  if (!layers.value.length) return
  const x0 = Math.min(...layers.value.map((l) => l.x))
  const y0 = Math.min(...layers.value.map((l) => l.y))
  const x1 = Math.max(...layers.value.map((l) => l.x + l.w))
  const y1 = Math.max(...layers.value.map((l) => l.y + l.h))
  try {
    const all = await renderArea({ x: x0, y: y0, w: x1 - x0, h: y1 - y0 })
    await window.vk.files.saveAs(await window.vk.files.writeImage(all.toDataURL('image/png')), 'canvas.png')
  } catch (err) {
    error.value = cleanError(err)
  }
}

function onKey(event: KeyboardEvent): void {
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes((event.target as HTMLElement).tagName)) return
  if ((event.key === 'Delete' || event.key === 'Backspace') && selected.value) removeSelected()
  else if (event.key === 'z' && (event.metaKey || event.ctrlKey)) undo()
  else if (event.key === 'v') tool.value = 'move'
  else if (event.key === 'b') tool.value = 'mask'
}

async function refresh(): Promise<void> {
  await assets.refresh()
  if (!model.value && models.value.length) {
    // a fast SDXL model first, else one that can fill, else any
    modelId.value = (models.value.find((m) => m.asset.meta.family === 'sdxl') ?? models.value.find((m) => m.canFill) ?? models.value[0]).asset.id
  }
}

watch(modelId, () => {
  setRatio(ratio.value)
  const d = model.value?.asset.meta.defaults
  if (typeof d?.num_steps === 'number') steps.value = d.num_steps
  saveSoon()
})
watch([layers, frame, prompt, negative], saveSoon, { deep: true })

// a model chosen by refresh() sizes the frame for itself (watch on modelId)
/** Restored pictures the app can no longer open (moved, deleted, or chosen before 0.4.14 outside the app's folders,
 * which needs choosing again) are taken off the canvas, so it can still paint. */
async function dropUnreadable(): Promise<void> {
  const gone = new Set<string>()
  await Promise.all([...new Set(layers.value.map((l) => l.src))].map((src) =>
    loadImage(url(src)).catch(() => { gone.add(src) })))
  if (!gone.size) return
  layers.value = layers.value.filter((l) => !gone.has(l.src))
  saveSoon()
  error.value = t('canvas.gone', { n: gone.size })
}

onMounted(() => {
  if (!restore()) setRatio('1:1')
  else void dropUnreadable()
})
onActivated(() => {
  window.addEventListener('keydown', onKey)
  void refresh()
})
onDeactivated(() => window.removeEventListener('keydown', onKey))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  clearTimeout(saveTimer)
  save()
})
</script>

<template>
  <PageFrame :title="t('canvas.title')" :subtitle="t('canvas.subtitle')">
    <template #actions>
      <button class="btn" @click="addPicture"><ImagePlus :size="14" /> {{ t('canvas.addPicture') }}</button>
      <button class="btn" :disabled="!layers.length" @click="exportPng"><Download :size="14" /> {{ t('canvas.exportPng') }}</button>
    </template>

    <div class="canvas-work">
    <div ref="stage" class="stage" :class="tool" @wheel.prevent="onWheel" @mousedown="onDown">
      <div class="world" :style="{ transform: `translate(${view.ox}px, ${view.oy}px) scale(${view.scale})` }">
        <img
          v-for="l in layers" :key="l.id" :src="url(l.src)" class="layer" :class="{ selected: l.id === selected }" draggable="false"
          :style="{ left: l.x + 'px', top: l.y + 'px', width: l.w + 'px', height: l.h + 'px', outlineWidth: 2 / view.scale + 'px' }"
        />
        <template v-if="selectedLayer && tool === 'move'">
          <span
            v-for="c in CORNERS" :key="c" class="handle" :class="c"
            :style="{ left: cornerPoint(selectedLayer, c).x + 'px', top: cornerPoint(selectedLayer, c).y + 'px', width: 12 / view.scale + 'px', height: 12 / view.scale + 'px', borderWidth: 2 / view.scale + 'px' }"
          />
          <span
            class="layer-size"
            :style="{ left: selectedLayer.x + 'px', top: selectedLayer.y + selectedLayer.h + 6 / view.scale + 'px', fontSize: 12 / view.scale + 'px' }"
          >{{ selectedLayer.w }} × {{ selectedLayer.h }}</span>
        </template>
        <template v-if="tool === 'move'">
          <span
            v-for="c in CORNERS" :key="'f' + c" class="handle frame-handle" :class="c"
            :style="{ left: cornerPoint(frame, c).x + 'px', top: cornerPoint(frame, c).y + 'px', width: 14 / view.scale + 'px', height: 14 / view.scale + 'px', borderWidth: 2 / view.scale + 'px' }"
          />
        </template>
        <div class="frame" :style="{ left: frame.x + 'px', top: frame.y + 'px', width: frame.w + 'px', height: frame.h + 'px', borderWidth: 2 / view.scale + 'px' }">
          <span class="size" :style="{ fontSize: 12 / view.scale + 'px', top: -20 / view.scale + 'px' }">{{ frame.w }} × {{ frame.h }}</span>
          <canvas v-show="hasMask || tool === 'mask'" ref="mask" :width="frame.w" :height="frame.h" />
        </div>
      </div>
      <div class="toolbar" @mousedown.stop>
        <button class="btn small" :class="{ on: tool === 'move' }" :title="t('canvas.toolMove')" @click="tool = 'move'"><Move :size="13" /></button>
        <button class="btn small" :class="{ on: tool === 'mask' }" :title="t('canvas.toolMask')" @click="tool = 'mask'"><Brush :size="13" /></button>
        <template v-if="tool === 'mask'">
          <input v-model.number="brush" type="range" min="8" max="200" :title="t('canvas.brushSize')" />
          <button class="btn small" :disabled="!hasMask" @click="clearMask">{{ t('canvas.clearMask') }}</button>
        </template>
        <i />
        <button class="btn small" :disabled="!selected" :title="t('canvas.fitToFrame')" @click="fitToFrame"><Scaling :size="13" /></button>
        <button class="btn small" :disabled="!selected" :title="t('canvas.toFront')" @click="toFront"><Layers :size="13" /></button>
        <button class="btn small" :disabled="!selected" :title="t('canvas.removeSelected')" @click="removeSelected"><Trash2 :size="13" /></button>
        <button class="btn small" :disabled="!canUndo" :title="t('canvas.undo')" @click="undo"><Undo2 :size="13" /></button>
        <button class="btn small" :title="t('canvas.showAll')" @click="fit"><Maximize :size="13" /></button>
        <span class="dim zoom">{{ Math.round(view.scale * 100) }} %</span>
      </div>
    </div>
    <div v-if="jobs.length" class="results">
      <JobGallery :jobs="jobs" @open="open" />
    </div>
    </div>

    <template #panel>
      <div class="fields">
        <label class="field">
          <span>Prompt</span>
          <textarea v-model="prompt" rows="6" :placeholder="t('canvas.promptPlaceholder')" spellcheck="false" @keydown.meta.enter.prevent="generate" />
        </label>
        <label v-if="model?.asset.meta.negativePrompt" class="field">
          <span>{{ t('canvas.negative') }}</span>
          <textarea v-model="negative" rows="3" spellcheck="false" />
        </label>
        <label class="field">
          <span>{{ t('canvas.model') }}</span>
          <select v-model="modelId">
            <option v-for="m in models" :key="m.asset.id" :value="m.asset.id">{{ m.canFill ? m.asset.title : t('canvas.newPicturesOnly', { model: m.asset.title }) }}</option>
          </select>
        </label>
        <div class="field">
          <span>{{ t('canvas.frame') }} <b>{{ frame.w }} × {{ frame.h }}{{ ratio === 'free' ? ` · ${t('canvas.free')}` : '' }}</b></span>
          <div class="chips"><button v-for="r in RATIOS" :key="r.id" class="chip" :class="{ on: ratio === r.id }" @click="setRatio(r.id)">{{ r.id }}</button></div>
        </div>
        <div class="two">
          <label class="field">
            <span class="label-row">{{ t('canvas.steps') }} <HintBadge v-if="stepsFit" notice start :text="stepsFit.text" /></span>
            <input v-model.number="steps" type="number" min="1" max="100" />
          </label>
          <label class="field"><span>Seed</span>
            <input type="number" min="0" :value="seed ?? ''" :placeholder="t('canvas.random')" @input="seed = ($event.target as HTMLInputElement).value === '' ? null : seedOf(($event.target as HTMLInputElement).value)" />
          </label>
        </div>
        <label v-if="plan === 'variation'" class="field">
          <span>{{ t('canvas.change') }} <b>{{ Math.round(variation * 100) }} %</b></span>
          <input v-model.number="variation" type="range" min="0.1" max="0.9" step="0.05" />
        </label>

        <p class="plan">{{ t(PLAN_TEXT[plan]) }}</p>
        <button v-if="!busy" class="btn primary" @click="generate"><Sparkles :size="14" /> {{ t('canvas.generate') }}</button>
        <button v-else class="btn danger" @click="queue.cancel(pending!.id)"><Square :size="12" /> {{ t('common.cancel') }}</button>
        <template v-if="running && busy">
          <div class="bar" :class="{ unknown: running.progress <= 0 }"><i :style="running.progress > 0 ? { width: running.progress + '%' } : {}" /></div>
          <small class="dim">
            {{ running.state === 'waiting' ? t('canvas.waiting') : running.progress > 0 ? `${Math.round(running.progress)} %` : running.status || t('common.starting') }}
            <template v-if="running.eta !== undefined"> · {{ t('canvas.left', { time: formatDuration(running.eta) }) }}</template>
          </small>
        </template>
        <p v-if="error" class="error selectable">{{ error }}</p>
        <small class="dim">
          {{ t('canvas.help') }}
        </small>
      </div>
    </template>
  </PageFrame>
</template>

<style scoped>
/* the surface fills the work area; the results of this page in a row below it */
.canvas-work {
  display: grid;
  grid-template-rows: minmax(300px, 1fr) auto;
  gap: 12px;
  height: 100%;
}

.results {
  min-width: 0;
  overflow-x: auto;
  padding-bottom: 4px;
}

.results :deep(.gallery) {
  grid-template-columns: none;
  grid-auto-flow: column;
  grid-auto-columns: 168px;
}

.stage {
  position: relative;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  border-radius: var(--radius-m);
  border: 1px solid var(--line);
  background-color: var(--surface);
  background-image: radial-gradient(var(--line) 1px, transparent 1px);
  background-size: 24px 24px;
  cursor: grab;
}

.stage.mask {
  cursor: crosshair;
}

.world {
  position: absolute;
  left: 0;
  top: 0;
  transform-origin: 0 0;
}

.layer {
  position: absolute;
  max-width: none;
  outline: 0 solid var(--accent);
  user-select: none;
}

.layer.selected {
  outline-style: solid;
}

/* the corner handles of the selected picture: drag to resize */
.handle {
  position: absolute;
  z-index: 2;
  box-sizing: border-box;
  border: 2px solid var(--accent);
  border-radius: 2px;
  background: var(--surface);
  transform: translate(-50%, -50%);
}

.handle.nw,
.handle.se {
  cursor: nwse-resize;
}

.handle.ne,
.handle.sw {
  cursor: nesw-resize;
}

/* the frame's handles: round and filled, so they differ from a picture's */
.frame-handle {
  z-index: 3;
  border-radius: 50%;
  background: var(--accent);
  border-color: var(--surface);
}

.layer-size {
  position: absolute;
  z-index: 2;
  white-space: nowrap;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
  pointer-events: none;
}

.frame {
  position: absolute;
  box-sizing: content-box;
  border: 2px dashed var(--accent);
  margin: 0;
  pointer-events: none;
}

.frame .size {
  position: absolute;
  left: 0;
  white-space: nowrap;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
}

.frame canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0.5;
}

.toolbar {
  position: absolute;
  left: 12px;
  bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px;
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  background: var(--surface);
  box-shadow: var(--shadow);
  cursor: default;
}

.toolbar i {
  width: 1px;
  height: 18px;
  background: var(--line);
}

.toolbar input[type='range'] {
  width: 110px;
  accent-color: var(--accent);
}

.zoom {
  min-width: 44px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.btn.on,
.chip.on {
  border-color: var(--accent);
  color: var(--accent);
}

.fields {
  display: grid;
  gap: 14px;
}

/* a notice next to the name of a field */
.field > .label-row {
  justify-content: flex-start;
  align-items: center;
  gap: 6px;
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

.two {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

textarea {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface-2);
  color: inherit;
  font: inherit;
  user-select: text;
  resize: vertical;
}

select,
input[type='number'] {
  width: 100%;
}

input[type='range'] {
  width: 100%;
  accent-color: var(--accent);
}

.plan {
  padding: 8px 10px;
  border-radius: var(--radius-s);
  background: var(--accent-soft);
}
</style>
