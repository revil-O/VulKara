<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// The photos found on a scan, over the scan: one turned frame each, numbered in reading order. A frame is moved by
// dragging it, resized at its corners and edges, turned at the handle above it, turned by a quarter with ↻ (the arrow
// shows which side becomes the top), taken away with ×. With `drawing`, dragging over the scan draws a new frame.
// Positions are in the scan's pixels; the layer covers the scan as it is shown.
import { computed, ref } from 'vue'
import { ArrowUp, RotateCw, X } from '@lucide/vue'
import type { ScanPhoto } from '@shared/api'
import { t } from '../i18n'
import { corners, move, moveCorner, moveEdge, rotateTo, turnRight } from '../util/scan_frames'

const props = defineProps<{ photos: ScanPhoto[]; size: [number, number]; drawing?: boolean }>()
const emit = defineEmits<{ 'update:photos': [photos: ScanPhoto[]]; drawn: [] }>()

const layer = ref<HTMLElement>()
type Drag = { kind: 'move' | 'corner' | 'edge' | 'turn' | 'draw'; index: number; part: number; x: number; y: number; start: ScanPhoto }
let drag: Drag | undefined

const pct = (v: number, of: number): string => `${(v / of) * 100}%`
const at = (p: [number, number]): Record<string, string> => ({ left: pct(p[0], props.size[0]), top: pct(p[1], props.size[1]) })
const points = (p: ScanPhoto): string => corners(p).map(([x, y]) => `${x},${y}`).join(' ')
const middle = (a: [number, number], b: [number, number]): [number, number] => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]
const edges = (p: ScanPhoto): [number, number][] => { const c = corners(p); return [0, 1, 2, 3].map((i) => middle(c[i], c[(i + 1) % 4])) }
// the turning handle sits above the middle of the top edge, a tenth of the frame's height out
function turnHandle(p: ScanPhoto): [number, number] {
  const a = (p.angle * Math.PI) / 180
  const out = p.h / 2 + Math.max(p.h * 0.1, props.size[1] * 0.02)
  return [p.cx + out * Math.sin(a), p.cy - out * Math.cos(a)]
}
const frames = computed(() => props.photos.map((p) => ({ p, c: corners(p), e: edges(p), handle: turnHandle(p) })))

/** The pointer in the scan's pixels. */
function scanPoint(event: PointerEvent): [number, number] | undefined {
  const r = layer.value?.getBoundingClientRect()
  if (!r?.width) return undefined
  return [((event.clientX - r.left) / r.width) * props.size[0], ((event.clientY - r.top) / r.height) * props.size[1]]
}

function down(event: PointerEvent, kind: Drag['kind'], index = -1, part = 0): void {
  if (event.button !== 0) return
  const p = scanPoint(event)
  if (!p) return
  event.stopPropagation()
  event.preventDefault()
  try {
    ;(event.currentTarget as Element).setPointerCapture(event.pointerId)
  } catch {
    // the pointer is gone already: the drag then ends with it
  }
  if (kind === 'draw') {
    const start: ScanPhoto = { cx: p[0], cy: p[1], w: 1, h: 1, angle: 0, turn: 0 }
    emit('update:photos', [...props.photos, start])
    drag = { kind, index: props.photos.length, part: 0, x: p[0], y: p[1], start }
    return
  }
  drag = { kind, index, part, x: p[0], y: p[1], start: props.photos[index] }
}

function moved(event: PointerEvent): void {
  const p = scanPoint(event)
  if (!drag || !p) return
  const [x, y] = [Math.min(props.size[0], Math.max(0, p[0])), Math.min(props.size[1], Math.max(0, p[1]))]
  const s = drag.start
  let next: ScanPhoto
  if (drag.kind === 'move') next = move(s, x - drag.x, y - drag.y)
  else if (drag.kind === 'corner') next = moveCorner(s, drag.part, x, y)
  else if (drag.kind === 'edge') next = moveEdge(s, drag.part, x, y)
  else if (drag.kind === 'turn') next = rotateTo(s, (Math.atan2(y - s.cy, x - s.cx) * 180) / Math.PI + 90)
  else next = { ...s, cx: (drag.x + x) / 2, cy: (drag.y + y) / 2, w: Math.abs(x - drag.x), h: Math.abs(y - drag.y) }
  emit('update:photos', props.photos.map((q, i) => (i === drag!.index ? next : q)))
}

function up(): void {
  // a drawn frame too small to be a photo (a click) is dropped again
  if (drag?.kind === 'draw') {
    const drawn = props.photos[drag.index]
    if (drawn && (drawn.w < props.size[0] * 0.02 || drawn.h < props.size[1] * 0.02)) emit('update:photos', props.photos.filter((_, i) => i !== drag!.index))
    emit('drawn')
  }
  drag = undefined
}

const remove = (index: number): void => emit('update:photos', props.photos.filter((_, i) => i !== index))
const quarter = (index: number): void => emit('update:photos', props.photos.map((q, i) => (i === index ? turnRight(q) : q)))
</script>

<template>
  <div
    ref="layer" class="frames" :class="{ drawing }"
    @pointerdown="drawing && down($event, 'draw')" @pointermove="moved" @pointerup="up" @pointercancel="up"
  >
    <svg class="overlay" :viewBox="`0 0 ${size[0]} ${size[1]}`" preserveAspectRatio="none">
      <polygon
        v-for="(f, i) in frames" :key="i" :points="points(f.p)" class="frame"
        @pointerdown="down($event, 'move', i)"
      />
    </svg>
    <template v-for="(f, i) in frames" :key="i">
      <span v-for="(c, k) in f.c" :key="`c${k}`" class="grip corner" :style="at(c)" @pointerdown="down($event, 'corner', i, k)" />
      <span v-for="(e, k) in f.e" :key="`e${k}`" class="grip edge" :style="at(e)" @pointerdown="down($event, 'edge', i, k)" />
      <span class="grip turn" :style="at(f.handle)" :aria-label="t('scans.turnHandle')" @pointerdown="down($event, 'turn', i)" />
      <span class="up" :style="{ ...at([f.p.cx, f.p.cy]), transform: `translate(-50%, -50%) rotate(${f.p.angle - f.p.turn}deg)` }">
        <ArrowUp :size="22" />
      </span>
      <div class="tag" :style="at(f.c[0])">
        <span>{{ t('scans.photo', { n: i + 1 }) }}</span>
        <button :aria-label="t('scans.quarter')" @pointerdown.stop @click.stop="quarter(i)"><RotateCw :size="11" /></button>
        <button :aria-label="t('scans.remove')" @pointerdown.stop @click.stop="remove(i)"><X :size="11" /></button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.frames {
  position: absolute;
  inset: 0;
  touch-action: none;
}

.frames.drawing {
  cursor: crosshair;
}

svg.overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  overflow: visible;
}

.frame {
  fill: rgb(255 255 255 / 4%);
  stroke: var(--accent);
  stroke-width: 2px;
  vector-effect: non-scaling-stroke;
  cursor: move;
}

.frame:hover {
  fill: rgb(255 255 255 / 12%);
}

.grip {
  position: absolute;
  width: 11px;
  height: 11px;
  border: 2px solid var(--accent);
  border-radius: 3px;
  background: #fff;
  transform: translate(-50%, -50%);
  cursor: grab;
}

.grip.edge {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.grip.turn {
  border-radius: 50%;
  background: var(--accent);
  cursor: alias;
}

.up {
  position: absolute;
  color: #fff;
  filter: drop-shadow(0 0 2px rgb(0 0 0 / 70%));
  pointer-events: none;
}

.tag {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 1px 2px 1px 7px;
  border-radius: 999px;
  background: rgb(0 0 0 / 65%);
  color: #fff;
  font: 500 10px/1.4 var(--font);
  white-space: nowrap;
  /* inside the frame's top left corner: the turning handle has the space above the frame */
  transform: translate(6px, 6px);
}

.tag button {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: #fff;
  cursor: pointer;
}

.tag button:hover {
  background: rgb(255 255 255 / 20%);
}
</style>
