<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Painting the part of a picture that is to change. The steps are kept as a list (util/mask_ops.ts), so undo is
// exact and the mask can be exported in the picture's own resolution: white where it changes, black elsewhere. A
// mask made elsewhere (an object selected on the Enhance page) can be the start; the strokes add to it or erase from
// it. With the picture's path (image) the subject can be selected (Apple Vision) or parts of it by click (SAM 2.1,
// the selection tool of the Enhance page); a selection is added to the mask and painted on like the rest. Several
// subjects are outlined each and can be taken out of the selection or back in by a click; a click selects the whole
// thing first, a click on the same spot again a smaller part of it.
import { computed, markRaw, onBeforeUnmount, ref, watch } from 'vue'
import ZoomPan from './ZoomPan.vue'
import HintBadge from './HintBadge.vue'
import { Brush, Eraser, MousePointerClick, RotateCcw, ScanSearch, Trash2 } from '@lucide/vue'
import { t } from '../i18n'
import { cleanError } from '../stores/runtimes'
import { composeSubjects, lastClick, maskToAlpha, nextRequest, paints, shownSteps, subjectLines, type MaskStep, type Selection, type Stroke } from '../util/mask_ops'

/** base: a mask to start from (PNG, white = changes), applied once the picture is loaded; image: the picture's path,
 *  for selecting (left out where selecting does not apply: Restore, the remote web UI) */
const props = defineProps<{ src: string; base?: string; image?: string }>()
const emit = defineEmits<{ loaded: [event: Event]; change: [painted: boolean] }>()

const canvas = ref<HTMLCanvasElement>()
/** the outline around the mask, white inside black, in screen pixels (visible on any picture) */
const edge = ref<HTMLCanvasElement>()
const steps = ref<MaskStep[]>([])
/** the starting mask as white with its grey as opacity, in the picture's size */
const base = ref<ImageBitmap>()
// the shown selections' masks in that form; one hidden by a later click of its row is let go (memory: full size each)
// and loaded again from its file when undo shows it again
const layers = new WeakMap<Selection, ImageBitmap>()
// all steps but the stroke being painted, in white: while painting only that stroke is drawn on top of it
const done = document.createElement('canvas')
const erase = ref(false)
const picking = ref(false)  // clicks select (SAM) instead of painting
const choosing = ref(false)  // clicks take subjects out of the subject selection or back in
// of the last subject selection with several subjects: its mask's grey and which pixel is which subject, one byte
// per pixel each (48 MB at 24 MP instead of a full-size picture per subject); every state of it is made from these
let subjectData: { mask: string; alpha: Uint8Array; labels: Uint8Array } | undefined
const busy = ref(false)
const error = ref('')
const brush = ref(8)  // percent of the picture's shorter side
const natural = ref<[number, number]>([0, 0])
const cursor = ref<{ x: number; y: number; d: number }>()
let current: Stroke | undefined
let generation = 0  // a selection that comes back after the picture changed or the mask was cleared is dropped
let queued: [number, number, number] | undefined  // the last click made while a selection by click ran

const painted = computed(() => !!base.value || paints(steps.value))
// "Select subject" again would add the same mask once more
const subjectLast = computed(() => {
  const last = steps.value[steps.value.length - 1]
  return last?.kind === 'selection' && !last.clicks
})
// the last step as a subject selection with several subjects: then they can be taken out and back in
const subjects = computed(() => {
  const last = steps.value[steps.value.length - 1]
  return last?.kind === 'selection' && !last.clicks && last.labels && (last.subjects ?? 1) > 1 ? last : undefined
})
watch(subjects, (s) => {
  if (!s) choosing.value = false
})
watch(painted, (p) => emit('change', p))
watch(() => props.src, () => {
  // the old picture's size no longer holds: nothing loads or selects in it until the new one is there
  natural.value = [0, 0]
  dropAll()
  error.value = ''
  queued = undefined
  generation++
  refresh()
})

/** Lets go of every step and the starting mask, with their bitmaps (96 MB each at 24 MP). */
function dropAll(): void {
  for (const s of steps.value) if (s.kind === 'selection') forget(s)
  steps.value = []
  subjectData = composed = undefined
  setBase(undefined)
}

function setBase(bitmap: ImageBitmap | undefined): void {
  base.value?.close()
  base.value = bitmap
}

/** The pixels of a grey picture file in the picture's size; undefined when they are no longer wanted. exact: no
 *  smoothing should the sizes differ (numbers, not shades). */
function readGrey(path: string, wanted: () => boolean, exact = false): Promise<ImageData | undefined> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      const [w, h] = natural.value
      if (!w || !wanted()) return resolve(undefined)
      // a canvas only for reading the pixels, let go afterwards
      const tmp = document.createElement('canvas')
      ;[tmp.width, tmp.height] = [w, h]
      const ctx = tmp.getContext('2d', { willReadFrequently: true }) as CanvasRenderingContext2D
      ctx.imageSmoothingEnabled = !exact
      ctx.drawImage(img, 0, 0, w, h)
      const data = ctx.getImageData(0, 0, w, h)
      // its pixels (96 MB at 24 MP) go now, not whenever the canvas is collected
      tmp.width = 0
      resolve(data)
    }
    img.onerror = () => reject(new Error(path))
    // vk-file is another origin: without CORS the canvas could not read the mask's pixels
    img.crossOrigin = 'anonymous'
    img.src = window.vk.files.url(path)
  })
}

/** RGBA pixels as a bitmap; undefined when no longer wanted. */
async function bitmap(data: ImageData | undefined, wanted: () => boolean): Promise<ImageBitmap | undefined> {
  if (!data || !wanted()) return undefined
  const b = await createImageBitmap(data)
  if (wanted()) return b
  b.close()
  return undefined
}

/** A mask file in the picture's size as white with its grey as opacity; undefined when it is no longer wanted. */
async function loadMask(path: string, wanted: () => boolean): Promise<ImageBitmap | undefined> {
  const data = await readGrey(path, wanted)
  if (data) maskToAlpha(data.data)
  return bitmap(data, wanted)
}

/** One byte per pixel: the first channel of grey pixels. */
function channel(data: ImageData): Uint8Array {
  const out = new Uint8Array(data.width * data.height)
  for (let p = 0, i = 0; p < out.length; p++, i += 4) out[p] = data.data[i]
  return out
}

/** The grey and the subjects' map of a subject selection, read when another selection's are held (undo can bring an
 *  older one back). One file after the other: each read holds a full-size canvas and its pixels for a moment. */
async function subjectsOf(s: Selection, wanted: () => boolean): Promise<typeof subjectData> {
  if (subjectData?.mask === s.mask) return subjectData
  const grey = await readGrey(s.mask, wanted)
  if (!grey) return undefined
  const alpha = channel(grey)
  const map = await readGrey(s.labels as string, wanted, true)
  if (!map) return undefined
  subjectData = { mask: s.mask, alpha, labels: channel(map) }
  return subjectData
}

// the pixels a subject selection is put together in, kept for the next one (96 MB at 24 MP); createImageBitmap
// copies them before it returns
let composed: ImageData | undefined

/** A subject selection with several subjects as it shows, without the subjects taken out. */
async function subjectLayer(s: Selection, wanted: () => boolean): Promise<ImageBitmap | undefined> {
  const data = await subjectsOf(s, wanted)
  if (!data || !wanted()) return undefined
  const [w, h] = natural.value
  if (composed?.width !== w || composed.height !== h) composed = new ImageData(w, h)
  composeSubjects(data.alpha, data.labels, s.off ?? [], composed.data)
  return bitmap(composed, wanted)
}

/** A selection's mask as it shows. */
const layerOf = (s: Selection, wanted: () => boolean): Promise<ImageBitmap | undefined> => s.labels ? subjectLayer(s, wanted) : loadMask(s.mask, wanted)

function loadBase(path: string): void {
  void loadMask(path, () => props.base === path).then((b) => {
    if (!b) return
    setBase(b)
    refresh()
  }, () => {})
}

// a new starting mask for the picture that is already there
watch(() => props.base, (path) => {
  setBase(undefined)
  if (path && natural.value[0]) loadBase(path)
  else refresh()
})

function onLoad(event: Event): void {
  const img = event.target as HTMLImageElement
  natural.value = [img.naturalWidth, img.naturalHeight]
  for (const c of [canvas.value, done]) if (c) [c.width, c.height] = natural.value
  refresh()
  if (props.base) loadBase(props.base)
  emit('loaded', event)
}

/** One step in white onto ctx (a stroke that erases takes away). */
function drawStep(ctx: CanvasRenderingContext2D, s: MaskStep): void {
  if (s.kind === 'selection') {
    const layer = layers.get(s)
    ctx.globalCompositeOperation = 'source-over'
    if (layer) ctx.drawImage(layer, 0, 0)
    return
  }
  ctx.globalCompositeOperation = s.erase ? 'destination-out' : 'source-over'
  ctx.strokeStyle = ctx.fillStyle = '#fff'
  ctx.lineWidth = s.size
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.beginPath()
  const [x0, y0] = s.points[0]
  if (s.points.length === 1) {
    ctx.arc(x0, y0, s.size / 2, 0, Math.PI * 2)
    ctx.fill()
    return
  }
  ctx.moveTo(x0, y0)
  for (const [x, y] of s.points.slice(1)) ctx.lineTo(x, y)
  ctx.stroke()
}

/** After any change but a stroke growing: the finished steps drawn again, then shown. */
function refresh(): void {
  const ctx = done.getContext('2d') as CanvasRenderingContext2D
  ctx.clearRect(0, 0, done.width, done.height)
  if (base.value) ctx.drawImage(base.value, 0, 0)
  for (const s of shownSteps(steps.value)) if (s !== current) drawStep(ctx, s)
  ctx.globalCompositeOperation = 'source-over'
  redraw()
}

function redraw(): void {
  const c = canvas.value
  const ctx = c?.getContext('2d')
  if (!c || !ctx) return
  ctx.clearRect(0, 0, c.width, c.height)
  if (done.width) ctx.drawImage(done, 0, 0)
  if (current) drawStep(ctx, current)
  // all of it in the accent colour, at the opacity drawn
  ctx.globalCompositeOperation = 'source-in'
  ctx.fillStyle = '#ff8a3d'
  ctx.fillRect(0, 0, c.width, c.height)
  ctx.globalCompositeOperation = 'source-over'
  // while a stroke is painted, the outline waits for its end: zoomed in it is up to 16 M pixels per pointer move
  if (!current) outline()
}

// the outline is worked out at the size shown, zoom included (a few draws of a small canvas), not in the picture's
// resolution; zoomed far in, at most OUTLINE_PIXELS (the line gets wider there instead of the canvas huge)
const OUTLINE_PIXELS = 16e6
const zoom = ref<InstanceType<typeof ZoomPan>>()
const small = document.createElement('canvas')  // the mask
const wider = document.createElement('canvas')  // the mask one pixel wider, white
const lines = document.createElement('canvas')  // the subjects' outlines

/** src drawn d pixels further out in every direction onto ctx. */
function around(ctx: CanvasRenderingContext2D, src: HTMLCanvasElement, d: number): void {
  for (const dx of [-d, 0, d]) for (const dy of [-d, 0, d]) ctx.drawImage(src, dx, dy)
}

function tint(ctx: CanvasRenderingContext2D, colour: string): void {
  ctx.globalCompositeOperation = 'source-in'
  ctx.fillStyle = colour
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height)
  ctx.globalCompositeOperation = 'source-over'
}

function outline(): void {
  const c = canvas.value
  const e = edge.value
  if (!c || !e) return
  const shown = c.offsetWidth * c.offsetHeight * devicePixelRatio ** 2
  const k = Math.min(zoom.value?.scale ?? 1, Math.sqrt(OUTLINE_PIXELS / Math.max(1, shown)))
  const w = Math.round(c.offsetWidth * devicePixelRatio * Math.max(1, k))
  const h = Math.round(c.offsetHeight * devicePixelRatio * Math.max(1, k))
  if (!w || !h) return
  for (const x of [e, small, wider]) if (x.width !== w || x.height !== h) [x.width, x.height] = [w, h]
  const d = Math.max(1, Math.round(devicePixelRatio))  // one point wide
  const sm = small.getContext('2d', { willReadFrequently: true }) as CanvasRenderingContext2D
  sm.clearRect(0, 0, w, h)
  sm.drawImage(c, 0, 0, w, h)
  // a soft brush fades out: the line goes where the mask counts for the model (half and more), not where it starts
  const px = sm.getImageData(0, 0, w, h)
  for (let i = 3; i < px.data.length; i += 4) px.data[i] = px.data[i] >= 128 ? 255 : 0
  sm.putImageData(px, 0, 0)
  const wi = wider.getContext('2d') as CanvasRenderingContext2D
  wi.clearRect(0, 0, w, h)
  around(wi, small, d)
  tint(wi, '#fff')
  const ctx = e.getContext('2d') as CanvasRenderingContext2D
  ctx.clearRect(0, 0, w, h)
  around(ctx, wider, d)
  tint(ctx, '#000')
  ctx.drawImage(wider, 0, 0)
  // only the line outside the mask stays
  ctx.globalCompositeOperation = 'destination-out'
  ctx.drawImage(small, 0, 0)
  ctx.globalCompositeOperation = 'source-over'
  // while subjects are taken out and back in: each one's own outline, white on black, dotted for one taken out
  const s = subjects.value
  if (!choosing.value || !s || subjectData?.mask !== s.mask) return
  ;[lines.width, lines.height] = [w, h]
  const lc = lines.getContext('2d') as CanvasRenderingContext2D
  lc.putImageData(new ImageData(subjectLines(subjectData.labels, subjectData.alpha, natural.value[0], natural.value[1], w, h, s.off ?? []), w, h), 0, 0)
  wi.clearRect(0, 0, w, h)
  around(wi, lines, d)
  tint(wi, '#000')
  wi.drawImage(lines, 0, 0)
  ctx.drawImage(wider, 0, 0)
}

// the picture shown larger or smaller (window, panel, zoom): the outline drawn again at the new size, once a frame
let pending = 0
const reoutline = (): void => {
  if (!pending) pending = requestAnimationFrame(() => { pending = 0; outline() })
}
const resized = new ResizeObserver(reoutline)
watch(() => zoom.value?.scale, reoutline)
watch(canvas, (c, old) => {
  if (old) resized.unobserve(old)
  if (c) resized.observe(c)
})
onBeforeUnmount(() => {
  resized.disconnect()
  dropAll()
})

const brushPixels = (): number => Math.max(4, (Math.min(...natural.value) * brush.value) / 100)

function position(event: PointerEvent): [number, number] {
  const c = canvas.value as HTMLCanvasElement
  const box = c.getBoundingClientRect()
  return [((event.clientX - box.left) / box.width) * c.width, ((event.clientY - box.top) / box.height) * c.height]
}

function down(event: PointerEvent): void {
  if (event.button !== 0 || !natural.value[0]) return
  if (picking.value) {
    const [x, y] = position(event)
    void selectByClick([Math.round(x), Math.round(y), event.altKey ? 0 : 1])
    return
  }
  if (choosing.value) {
    void toggleSubject(position(event))
    return
  }
  ;(event.target as HTMLElement).setPointerCapture(event.pointerId)
  // raw: the list hands out the object itself, so it is known as the stroke being painted
  current = markRaw<Stroke>({ kind: 'stroke', erase: erase.value, size: brushPixels(), points: [position(event)] })
  steps.value.push(current)
  redraw()
}

function move(event: PointerEvent): void {
  const c = canvas.value as HTMLCanvasElement
  const box = c.getBoundingClientRect()
  // in the surface's own pixels: the surface may be zoomed (ZoomPan), the cursor is drawn inside it
  const k = c.offsetWidth / box.width
  cursor.value = picking.value || choosing.value || !natural.value[0] ? undefined : { x: (event.clientX - box.left) * k, y: (event.clientY - box.top) * k, d: (brushPixels() / natural.value[0]) * c.offsetWidth }
  if (!current) return
  current.points.push(position(event))
  redraw()
}

function up(): void {
  if (!current) return
  current = undefined
  refresh()
}

function forget(s: Selection): void {
  layers.get(s)?.close()
  layers.delete(s)
}

/** Adds a selection (its mask file) as a step; keeps only the shown selections' masks in memory. */
async function addSelection(step: Selection, made: number): Promise<void> {
  const layer = await layerOf(step, () => made === generation)
  if (!layer) return
  if (made !== generation) return layer.close()
  // raw: the list would hand out a proxy of it, which the map does not know
  markRaw(step)
  layers.set(step, layer)
  steps.value.push(step)
  const shown = new Set(shownSteps(steps.value))
  for (const s of steps.value) if (s.kind === 'selection' && !shown.has(s)) forget(s)
  refresh()
}

async function selecting(work: (made: number) => Promise<void>): Promise<void> {
  if (busy.value || !props.image) return
  busy.value = true
  error.value = ''
  try {
    await work(generation)
  } catch (err) {
    error.value = cleanError(err)
  } finally {
    busy.value = false
  }
}

const selectSubject = (): Promise<void> => selecting(async (made) => {
  picking.value = false
  if (subjects.value) {
    // undo may have brought back an older subject selection than the one whose subjects are held
    const s = subjects.value
    if (!choosing.value && !await subjectsOf(s, () => made === generation && subjects.value === s)) return
    choosing.value = !choosing.value
    cursor.value = undefined
    return outline()
  }
  if (subjectLast.value) return
  const found = await window.vk.tools.subject(props.image as string)
  await addSelection({ kind: 'selection', ...found }, made)
  // several subjects: a click on one takes it out or back in, right away
  choosing.value = !!subjects.value
  outline()
})

/** The subject under the click (picture pixels) taken out of the selection or back in, as a new step. */
const toggleSubject = ([x, y]: [number, number]): Promise<void> => selecting(async (made) => {
  const s = subjects.value
  const data = s && await subjectsOf(s, () => made === generation && subjects.value === s)
  const [w, h] = natural.value
  const label = data ? data.labels[Math.min(h - 1, Math.floor(y)) * w + Math.min(w - 1, Math.floor(x))] : 0
  if (!s || !label) return
  const off = s.off?.includes(label) ? s.off.filter((l) => l !== label) : [...(s.off ?? []), label]
  await addSelection({ ...s, off }, made)
})

// the selection tool of the Enhance page (SAM 2.1), looked up when selecting by click is turned on
let samTool = ''
async function togglePicking(): Promise<void> {
  error.value = ''
  choosing.value = false
  if (picking.value) {
    picking.value = false
    return outline()
  }
  const tool = await window.vk.tools.list().then((l) => l.installed.find((tl) => tl.kind === 'segment'), () => undefined)
  if (!tool) {
    error.value = t('edit.mask.clickTool')
    return
  }
  samTool = tool.folder
  picking.value = true
  cursor.value = undefined
}

async function selectByClick(click: [number, number, number]): Promise<void> {
  // a click while one is worked on: the last such click follows once it is done
  if (busy.value) {
    queued = click
    return
  }
  await selecting(async (made) => {
    // the same spot again: within 2 % of the picture's shorter side
    const { clicks, pick } = nextRequest(lastClick(steps.value), click, Math.min(...natural.value) * 0.02)
    if (!clicks.some((c) => c[2])) return  // ⌥-click takes away from a selection: alone there is nothing to take from
    const got = await window.vk.tools.select(samTool, props.image as string, clicks, pick)
    await addSelection({ kind: 'selection', mask: got.mask, clicks, pick: got.pick, candidates: got.candidates }, made)
  })
  const next = queued
  queued = undefined
  if (next && picking.value) await selectByClick(next)
}

function paintMode(rubber: boolean): void {
  erase.value = rubber
  picking.value = false
  if (choosing.value) {
    choosing.value = false
    outline()
  }
}

// a mask let go that undo brings back is read again; exportMask waits for it
let reloading: Promise<void> = Promise.resolve()

function undo(): void {
  const gone = steps.value.pop()
  if (gone?.kind === 'selection') forget(gone)
  // no step of that subject selection left: its grey and map go (48 MB at 24 MP), and the pixels put together from them
  if (subjectData && !steps.value.some((s) => s.kind === 'selection' && s.mask === subjectData?.mask)) subjectData = composed = undefined
  refresh()
  // a click of a row shows again: its mask was let go
  const missing = shownSteps(steps.value).filter((s): s is Selection => s.kind === 'selection' && !layers.has(s))
  if (!missing.length) return
  const made = generation
  busy.value = true
  reloading = Promise.all(missing.map((s) => layerOf(s, () => made === generation && steps.value.includes(s)).then((b) => {
    if (b) layers.set(s, b)
  }, (err) => {
    // its file is gone: the step can show nothing, so it goes
    steps.value = steps.value.filter((x) => x !== s)
    error.value = cleanError(err)
  }))).then(() => {
    busy.value = false
    refresh()
  })
}

function clear(): void {
  dropAll()
  queued = undefined
  generation++
  refresh()
}

/** The mask as PNG data URL in the picture's resolution, undefined when nothing is painted. */
async function exportMask(): Promise<string | undefined> {
  await reloading
  if (!painted.value || !natural.value[0]) return undefined
  const [w, h] = natural.value
  const out = document.createElement('canvas')
  ;[out.width, out.height] = [w, h]
  const ctx = out.getContext('2d') as CanvasRenderingContext2D
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, w, h)
  // the finished steps (no stroke is being painted while the mask is asked for)
  ctx.drawImage(done, 0, 0)
  return out.toDataURL('image/png')
}

/** The part of the photo in view when zoomed in (shares 0..1), for a preview of just that part. */
const visible = () => zoom.value?.visible()

defineExpose({ exportMask, clear, visible })
</script>

<template>
  <div class="mask">
    <ZoomPan ref="zoom">
      <div class="surface" :class="{ picking, choosing, busy }" @pointerleave="cursor = undefined">
        <!-- crossorigin: the pages read the picture's pixels (Restore tells a black-and-white photo); vk-file sends CORS -->
        <img :src="src" crossorigin="anonymous" draggable="false" @load="onLoad" />
        <canvas ref="canvas" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" />
        <canvas ref="edge" class="edge" />
        <i v-if="cursor" class="cursor" :style="{ left: cursor.x + 'px', top: cursor.y + 'px', width: cursor.d + 'px', height: cursor.d + 'px' }" />
        <!-- marks over the photo that zoom with it (Restore: the faces) -->
        <slot name="overlay" />
      </div>
    </ZoomPan>
    <div v-if="image" class="tools">
      <button class="btn small" :class="{ on: choosing }" :disabled="busy || !natural[0] || (subjectLast && !subjects)" @click="selectSubject"><ScanSearch :size="13" /> {{ t('edit.mask.subject') }}</button>
      <HintBadge above :text="t('edit.mask.subjectHint')" />
      <button class="btn small" :class="{ on: picking }" :disabled="busy" @click="togglePicking"><MousePointerClick :size="13" /> {{ t('edit.mask.click') }}</button>
      <HintBadge above :text="t('edit.mask.clickHint')" />
    </div>
    <div class="tools">
      <button class="btn small" :class="{ on: !erase && !picking && !choosing }" :title="t('edit.mask.paintHint')" @click="paintMode(false)"><Brush :size="13" /> {{ t('edit.mask.paint') }}</button>
      <button class="btn small" :class="{ on: erase && !picking && !choosing }" :title="t('edit.mask.eraseHint')" @click="paintMode(true)"><Eraser :size="13" /> {{ t('edit.mask.erase') }}</button>
      <label class="size">{{ t('edit.mask.size') }} <input v-model.number="brush" type="range" min="1" max="30" /></label>
      <button class="btn small" :disabled="!steps.length || busy" :title="t('edit.mask.undo')" @click="undo"><RotateCcw :size="13" /></button>
      <button class="btn small" :disabled="(!steps.length && !base) || busy" :title="t('edit.mask.clear')" @click="clear"><Trash2 :size="13" /></button>
    </div>
    <small v-if="choosing && subjects" class="dim">{{ t('edit.mask.subjects', { n: subjects.subjects ?? 2 }) }}</small>
    <small v-if="error" class="error selectable">{{ error }}</small>
  </div>
</template>

<style scoped>
.mask {
  display: grid;
  justify-items: center;
  gap: 8px;
  padding: 10px;
  width: 100%;
}

.surface {
  position: relative;
  line-height: 0;
  cursor: none;
  touch-action: none;
}

img {
  max-width: 100%;
  max-height: 52vh;
  border-radius: var(--radius-s);
}

canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  opacity: 0.55;
}

canvas.edge {
  opacity: 1;
  pointer-events: none;
}

.surface.picking {
  cursor: crosshair;
}

.surface.choosing {
  cursor: pointer;
}

.surface.busy {
  cursor: progress;
}

.cursor {
  position: absolute;
  border: 1.5px solid #fff;
  border-radius: 50%;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.6);
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.tools {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: center;
}

.btn.on {
  border-color: var(--accent);
  color: var(--accent);
}

.size {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 6px;
  color: var(--text-dim);
}

input[type='range'] {
  width: 110px;
  accent-color: var(--accent);
}
</style>
