<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Zoom into a picture (and what is painted or clicked on it) without changing how it is laid out: the content is
// scaled with a transform inside a frame of its own size. ⌘-scroll or a pinch zooms towards the pointer; scrolling
// moves a zoomed picture; Space-drag or the middle button drags it. Painting and clicking keep working, because
// they measure the picture as it is shown (getBoundingClientRect).
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Maximize, Minus, Plus } from '@lucide/vue'
import { t } from '../i18n'

const MAX = 8
const frame = ref<HTMLElement>()
const view = reactive({ scale: 1, x: 0, y: 0 })
const space = ref(false)
const dragging = ref(false)
const zoomed = computed(() => view.scale > 1.001)

/** Keeps the scaled content covering the frame (no empty edge inside it). */
function clamp(): void {
  const el = frame.value
  if (!el) return
  const w = el.clientWidth
  const h = el.clientHeight
  view.scale = Math.min(MAX, Math.max(1, view.scale))
  view.x = Math.min(0, Math.max(w - w * view.scale, view.x))
  view.y = Math.min(0, Math.max(h - h * view.scale, view.y))
}

/** Zooms by factor k towards a point (px, py) of the frame (its centre when not given). */
function zoomBy(k: number, px?: number, py?: number): void {
  const el = frame.value
  if (!el) return
  const cx = px ?? el.clientWidth / 2
  const cy = py ?? el.clientHeight / 2
  const scale = Math.min(MAX, Math.max(1, view.scale * k))
  view.x = cx - ((cx - view.x) * scale) / view.scale
  view.y = cy - ((cy - view.y) * scale) / view.scale
  view.scale = scale
  clamp()
}

function fit(): void {
  Object.assign(view, { scale: 1, x: 0, y: 0 })
}

function onWheel(event: WheelEvent): void {
  const el = frame.value
  if (!el) return
  if (event.ctrlKey || event.metaKey) {
    // a pinch arrives as a wheel with ctrlKey
    event.preventDefault()
    const box = el.getBoundingClientRect()
    // one wheel notch can bring a large delta: at most ×1.4 per event, so a mouse zooms in steps like a pinch
    zoomBy(Math.exp(Math.max(-0.35, Math.min(0.35, -event.deltaY * 0.01))), event.clientX - box.left, event.clientY - box.top)
  } else if (zoomed.value) {
    event.preventDefault()
    view.x -= event.deltaX
    view.y -= event.deltaY
    clamp()
  }
}

// Space-drag or the middle button moves the picture; it is taken before painting or clicking sees it
function onPointerDown(event: PointerEvent): void {
  if (!zoomed.value || !(space.value || event.button === 1)) return
  event.preventDefault()
  event.stopPropagation()
  const start = { x: event.clientX, y: event.clientY, vx: view.x, vy: view.y }
  dragging.value = true
  const move = (ev: PointerEvent): void => {
    view.x = start.vx + ev.clientX - start.x
    view.y = start.vy + ev.clientY - start.y
    clamp()
  }
  const up = (): void => {
    dragging.value = false
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}

// a click that ends a Space-drag must not count as a click on the picture
function onClick(event: MouseEvent): void {
  if (space.value) {
    event.preventDefault()
    event.stopPropagation()
  }
}

const typing = (target: EventTarget | null): boolean =>
  target instanceof HTMLElement && (['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable)
function keyDown(event: KeyboardEvent): void {
  if (event.code === 'Space' && !typing(event.target) && frame.value?.matches(':hover')) {
    space.value = true
    event.preventDefault()
  }
}
function keyUp(event: KeyboardEvent): void {
  if (event.code === 'Space') space.value = false
}
onMounted(() => {
  window.addEventListener('keydown', keyDown)
  window.addEventListener('keyup', keyUp)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', keyDown)
  window.removeEventListener('keyup', keyUp)
})

/** The part of the content in view, as shares of it (0..1); undefined when not zoomed in (all of it shows). */
function visible(): { x: number; y: number; w: number; h: number } | undefined {
  const el = frame.value
  if (!el || !zoomed.value) return undefined
  return { x: -view.x / (el.clientWidth * view.scale), y: -view.y / (el.clientHeight * view.scale), w: 1 / view.scale, h: 1 / view.scale }
}

/** the zoom factor (1 = fitted), for content drawn at the size it is shown (MaskCanvas's outline) */
const scale = computed(() => view.scale)

defineExpose({ fit, visible, scale })
</script>

<template>
  <div
    ref="frame" class="zoom" :class="{ panning: zoomed && space, dragging }"
    @wheel="onWheel" @pointerdown.capture="onPointerDown" @click.capture="onClick" @auxclick.prevent
  >
    <div class="content" :style="{ transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})` }">
      <slot />
    </div>
    <div class="controls" @pointerdown.stop @click.stop>
      <button class="ctl" :disabled="!zoomed" :aria-label="t('edit.zoom.out')" @click="zoomBy(1 / 1.5)"><Minus :size="12" /></button>
      <span class="pct">{{ Math.round(view.scale * 100) }} %</span>
      <button class="ctl" :disabled="view.scale >= MAX" :aria-label="t('edit.zoom.in')" @click="zoomBy(1.5)"><Plus :size="12" /></button>
      <button class="ctl" :disabled="!zoomed" :aria-label="t('edit.zoom.fit')" @click="fit"><Maximize :size="12" /></button>
    </div>
  </div>
</template>

<style scoped>
.zoom {
  position: relative;
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  line-height: 0;
  vertical-align: top;
}

.content {
  transform-origin: 0 0;
}

.zoom.panning,
.zoom.panning :deep(*) {
  cursor: grab !important;
}

.zoom.dragging,
.zoom.dragging :deep(*) {
  cursor: grabbing !important;
}

/* small controls in the lower right corner; they show when the pointer is over the picture or it is zoomed */
.controls {
  position: absolute;
  right: 8px;
  bottom: 8px;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: color-mix(in srgb, var(--surface) 88%, transparent);
  box-shadow: var(--shadow);
  line-height: 1;
  opacity: 0;
  transition: opacity 0.12s;
}

.zoom:hover .controls,
.zoom:focus-within .controls {
  opacity: 1;
}

.ctl {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--text);
  cursor: pointer;
}

.ctl:hover:not(:disabled) {
  background: color-mix(in srgb, var(--text) 10%, transparent);
}

.ctl:disabled {
  opacity: 0.35;
  cursor: default;
}

.pct {
  min-width: 40px;
  font-size: 11px;
  text-align: center;
  color: var(--text-dim);
  font-variant-numeric: tabular-nums;
}
</style>
