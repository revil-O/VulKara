<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// The faces Restore will restore, over the photo: one rounded frame each (the square CodeFormer restores). A frame
// is dragged to where the face really is, or taken away with its ×. Positions are in the photo's pixels; the
// frames lie in the zoomed surface, so they follow zooming, and they measure the surface as it is shown.
import { ref } from 'vue'
import { X } from '@lucide/vue'
import { t } from '../i18n'

export interface Face {
  points: [number, number][]
  box: [number, number, number, number]
}

const props = defineProps<{ faces: Face[]; size: [number, number] }>()
const emit = defineEmits<{ (e: 'update:faces', faces: Face[]): void }>()

const layer = ref<HTMLElement>()
let drag: { index: number; x: number; y: number; start: Face } | undefined

const pct = (v: number, of: number): string => `${(v / of) * 100}%`

function down(event: PointerEvent, index: number): void {
  if (event.button !== 0) return
  event.stopPropagation()
  event.preventDefault()
  try {
    ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  } catch {
    // the pointer is gone already: the drag then ends with it
  }
  drag = { index, x: event.clientX, y: event.clientY, start: props.faces[index] }
}

function move(event: PointerEvent): void {
  const r = layer.value?.getBoundingClientRect()
  if (!drag || !r?.width) return
  const dx = ((event.clientX - drag.x) / r.width) * props.size[0]
  const dy = ((event.clientY - drag.y) / r.height) * props.size[1]
  const [x, y, w, h] = drag.start.box
  // the frame stays on the photo with at least its middle
  const mx = Math.min(props.size[0] - w / 2, Math.max(-w / 2, x + dx)) - x
  const my = Math.min(props.size[1] - h / 2, Math.max(-h / 2, y + dy)) - y
  const moved: Face = {
    box: [x + mx, y + my, w, h],
    points: drag.start.points.map(([px, py]) => [px + mx, py + my] as [number, number]),
  }
  emit('update:faces', props.faces.map((f, i) => (i === drag!.index ? moved : f)))
}

function up(): void {
  drag = undefined
}

function remove(index: number): void {
  emit('update:faces', props.faces.filter((_, i) => i !== index))
}
</script>

<template>
  <div ref="layer" class="faces">
    <div
      v-for="(f, i) in faces" :key="i" class="face"
      :style="{ left: pct(f.box[0], size[0]), top: pct(f.box[1], size[1]), width: pct(f.box[2], size[0]), height: pct(f.box[3], size[1]) }"
      @pointerdown="down($event, i)" @pointermove="move" @pointerup="up" @pointercancel="up"
    >
      <span class="label">{{ t('edit.faces.face', { n: i + 1 }) }}</span>
      <button class="remove" :aria-label="t('edit.faces.remove')" @pointerdown.stop @click.stop="remove(i)"><X :size="10" /></button>
    </div>
  </div>
</template>

<style scoped>
.faces {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.face {
  position: absolute;
  border: 2px solid #fff;
  border-radius: 14%;
  box-shadow: 0 0 0 1px rgb(0 0 0 / 45%), inset 0 0 0 1px rgb(0 0 0 / 30%);
  cursor: move;
  pointer-events: auto;
  touch-action: none;
}

.face:hover {
  border-color: var(--accent);
}

.label {
  position: absolute;
  bottom: 100%;
  left: 0;
  margin-bottom: 3px;
  padding: 1px 6px;
  border-radius: 999px;
  background: rgb(0 0 0 / 60%);
  color: #fff;
  font: 500 10px/1.4 var(--font);
  white-space: nowrap;
}

.remove {
  position: absolute;
  top: -8px;
  right: -8px;
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: 1px solid #fff;
  border-radius: 50%;
  background: rgb(0 0 0 / 65%);
  color: #fff;
  cursor: pointer;
  line-height: 0;
}
</style>
