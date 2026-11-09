<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Painting the part of a picture that is to change. The strokes are kept as a list, so undo is exact and the
// mask can be exported in the picture's own resolution: white where it changes, black elsewhere. A mask made
// elsewhere (an object selected on the Enhance page) can be the start; the strokes add to it or erase from it.
import { computed, ref, watch } from 'vue'
import ZoomPan from './ZoomPan.vue'
import { Brush, Eraser, RotateCcw, Trash2 } from '@lucide/vue'
import { t } from '../i18n'

interface Stroke {
  erase: boolean
  /** brush diameter in picture pixels */
  size: number
  points: [number, number][]
}

/** base: a mask to start from (PNG, white = changes), applied once the picture is loaded */
const props = defineProps<{ src: string; base?: string }>()
const emit = defineEmits<{ loaded: [event: Event]; change: [painted: boolean] }>()

const canvas = ref<HTMLCanvasElement>()
const strokes = ref<Stroke[]>([])
/** the starting mask (white = changes), in the picture's size; and the one to load once the picture is there */
const base = ref<HTMLCanvasElement>()
const erase = ref(false)
const brush = ref(8)  // percent of the picture's shorter side
const natural = ref<[number, number]>([0, 0])
const cursor = ref<{ x: number; y: number; d: number }>()
let current: Stroke | undefined

const painted = computed(() => !!base.value || strokes.value.some((s) => !s.erase))
watch(painted, (p) => emit('change', p))
watch(() => props.src, () => {
  strokes.value = []
  base.value = undefined
  redraw()
})

/** The starting mask's white parts in one colour, transparent elsewhere. */
function tinted(color: string): HTMLCanvasElement | undefined {
  const b = base.value
  if (!b) return undefined
  const out = document.createElement('canvas')
  ;[out.width, out.height] = [b.width, b.height]
  const ctx = out.getContext('2d') as CanvasRenderingContext2D
  const data = (b.getContext('2d') as CanvasRenderingContext2D).getImageData(0, 0, b.width, b.height)
  const [r, g, bl] = color === '#fff' ? [255, 255, 255] : [255, 138, 61]
  for (let i = 0; i < data.data.length; i += 4) {
    const v = data.data[i]
    ;[data.data[i], data.data[i + 1], data.data[i + 2], data.data[i + 3]] = [r, g, bl, v]
  }
  ctx.putImageData(data, 0, 0)
  return out
}

function loadBase(path: string): void {
  const img = new Image()
  img.onload = () => {
    const [w, h] = natural.value
    if (!w || props.base !== path) return
    const c = document.createElement('canvas')
    ;[c.width, c.height] = [w, h]
    ;(c.getContext('2d') as CanvasRenderingContext2D).drawImage(img, 0, 0, w, h)
    base.value = c
    redraw()
  }
  // vk-file is another origin: without CORS the canvas could not read the mask's pixels
  img.crossOrigin = 'anonymous'
  img.src = window.vk.files.url(path)
}

// a new starting mask for the picture that is already there
watch(() => props.base, (path) => {
  base.value = undefined
  if (path && natural.value[0]) loadBase(path)
  else redraw()
})

function onLoad(event: Event): void {
  const img = event.target as HTMLImageElement
  natural.value = [img.naturalWidth, img.naturalHeight]
  const c = canvas.value
  if (c) [c.width, c.height] = natural.value
  redraw()
  if (props.base) loadBase(props.base)
  emit('loaded', event)
}

function draw(ctx: CanvasRenderingContext2D, list: Stroke[], color: string): void {
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  for (const s of list) {
    ctx.globalCompositeOperation = s.erase ? 'destination-out' : 'source-over'
    ctx.strokeStyle = ctx.fillStyle = s.erase ? '#000' : color
    ctx.lineWidth = s.size
    ctx.beginPath()
    const [x0, y0] = s.points[0]
    if (s.points.length === 1) {
      ctx.arc(x0, y0, s.size / 2, 0, Math.PI * 2)
      ctx.fill()
      continue
    }
    ctx.moveTo(x0, y0)
    for (const [x, y] of s.points.slice(1)) ctx.lineTo(x, y)
    ctx.stroke()
  }
  ctx.globalCompositeOperation = 'source-over'
}

function redraw(): void {
  const c = canvas.value
  const ctx = c?.getContext('2d')
  if (!c || !ctx) return
  ctx.clearRect(0, 0, c.width, c.height)
  const start = tinted('#ff8a3d')
  if (start) ctx.drawImage(start, 0, 0)
  draw(ctx, strokes.value, '#ff8a3d')
}

const brushPixels = (): number => Math.max(4, (Math.min(...natural.value) * brush.value) / 100)

function position(event: PointerEvent): [number, number] {
  const c = canvas.value as HTMLCanvasElement
  const box = c.getBoundingClientRect()
  return [((event.clientX - box.left) / box.width) * c.width, ((event.clientY - box.top) / box.height) * c.height]
}

function down(event: PointerEvent): void {
  if (event.button !== 0 || !natural.value[0]) return
  ;(event.target as HTMLElement).setPointerCapture(event.pointerId)
  current = { erase: erase.value, size: brushPixels(), points: [position(event)] }
  strokes.value.push(current)
  redraw()
}

function move(event: PointerEvent): void {
  const c = canvas.value as HTMLCanvasElement
  const box = c.getBoundingClientRect()
  // in the surface's own pixels: the surface may be zoomed (ZoomPan), the cursor is drawn inside it
  const k = c.offsetWidth / box.width
  cursor.value = { x: (event.clientX - box.left) * k, y: (event.clientY - box.top) * k, d: (brushPixels() / natural.value[0]) * c.offsetWidth }
  if (!current) return
  current.points.push(position(event))
  redraw()
}

function up(): void {
  current = undefined
}

function undo(): void {
  strokes.value.pop()
  redraw()
}

function clear(): void {
  strokes.value = []
  base.value = undefined
  redraw()
}

/** The mask as PNG data URL in the picture's resolution, undefined when nothing is painted. */
function exportMask(): string | undefined {
  if (!painted.value) return undefined
  const [w, h] = natural.value
  const layer = document.createElement('canvas')
  ;[layer.width, layer.height] = [w, h]
  const layerCtx = layer.getContext('2d') as CanvasRenderingContext2D
  const start = tinted('#fff')
  if (start) layerCtx.drawImage(start, 0, 0)
  draw(layerCtx, strokes.value, '#fff')
  const out = document.createElement('canvas')
  ;[out.width, out.height] = [w, h]
  const ctx = out.getContext('2d') as CanvasRenderingContext2D
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, w, h)
  ctx.drawImage(layer, 0, 0)
  return out.toDataURL('image/png')
}

const zoom = ref<InstanceType<typeof ZoomPan>>()
/** The part of the photo in view when zoomed in (shares 0..1), for a preview of just that part. */
const visible = () => zoom.value?.visible()

defineExpose({ exportMask, clear, visible })
</script>

<template>
  <div class="mask">
    <ZoomPan ref="zoom">
      <div class="surface" @pointerleave="cursor = undefined">
        <!-- crossorigin: the pages read the picture's pixels (Restore tells a black-and-white photo); vk-file sends CORS -->
        <img :src="src" crossorigin="anonymous" draggable="false" @load="onLoad" />
        <canvas ref="canvas" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" />
        <i v-if="cursor" class="cursor" :style="{ left: cursor.x + 'px', top: cursor.y + 'px', width: cursor.d + 'px', height: cursor.d + 'px' }" />
        <!-- marks over the photo that zoom with it (Restore: the faces) -->
        <slot name="overlay" />
      </div>
    </ZoomPan>
    <div class="tools">
      <button class="btn small" :class="{ on: !erase }" :title="t('edit.mask.paintHint')" @click="erase = false"><Brush :size="13" /> {{ t('edit.mask.paint') }}</button>
      <button class="btn small" :class="{ on: erase }" :title="t('edit.mask.eraseHint')" @click="erase = true"><Eraser :size="13" /> {{ t('edit.mask.erase') }}</button>
      <label class="size">{{ t('edit.mask.size') }} <input v-model.number="brush" type="range" min="1" max="30" /></label>
      <button class="btn small" :disabled="!strokes.length" :title="t('edit.mask.undo')" @click="undo"><RotateCcw :size="13" /></button>
      <button class="btn small" :disabled="!strokes.length" :title="t('edit.mask.clear')" @click="clear"><Trash2 :size="13" /></button>
    </div>
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
