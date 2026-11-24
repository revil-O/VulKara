<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// The picture a job starts from: chosen from the history or from disk (pickImage), or dropped onto the field. With many,
// several pictures (a dialog for pictures and folders, or more than one dropped) go to the page as a batch.
import { ref } from 'vue'
import { Images, ImagePlus, X } from '@lucide/vue'
import ZoomPan from './ZoomPan.vue'
import { pickImage } from '../util/pick_image'
import { t } from '../i18n'

const path = defineModel<string>({ required: true })
const props = defineProps<{ many?: boolean }>()
const emit = defineEmits<{ size: [width: number, height: number]; many: [paths: string[]] }>()
const over = ref(false)
const IMAGE = /\.(png|jpe?g|webp|bmp)$/i
const url = (p: string): string => window.vk.files.url(p)

async function choose(): Promise<void> {
  const chosen = await pickImage()
  if (chosen) path.value = chosen
}

function drop(event: DragEvent): void {
  over.value = false
  const dropped = [...(event.dataTransfer?.files ?? [])].map((f) => window.vk.files.pathOf(f)).filter((p) => p && IMAGE.test(p))
  if (props.many && dropped.length > 1) emit('many', dropped)
  else if (dropped[0]) path.value = dropped[0]
}

async function chooseMany(): Promise<void> {
  const chosen = await window.vk.files.chooseMany()
  if (chosen.length) emit('many', chosen)
}

function loaded(event: Event): void {
  const img = event.target as HTMLImageElement
  emit('size', img.naturalWidth, img.naturalHeight)
}
</script>

<template>
  <div class="input" :class="{ over, filled: !!path }" @dragover.prevent="over = true" @dragleave="over = false" @drop.prevent="drop">
    <template v-if="path">
      <slot :src="url(path)" :loaded="loaded">
        <ZoomPan><img :src="url(path)" draggable="false" @load="loaded" /></ZoomPan>
      </slot>
      <button class="btn small clear" :title="t('generate.imageInput.remove')" @click="path = ''"><X :size="12" /></button>
    </template>
    <template v-else>
      <button class="empty" @click="choose">
        <ImagePlus :size="26" :stroke-width="1.4" />
        <span>{{ t('generate.imageInput.choose') }}</span>
      </button>
      <button v-if="many" class="btn small many" @click="chooseMany"><Images :size="12" /> {{ t('edit.batch.many') }}</button>
    </template>
  </div>
</template>

<style scoped>
.input {
  position: relative;
  display: grid;
  place-items: center;
  min-height: 180px;
  border: 1px dashed var(--line);
  border-radius: var(--radius-m);
  background: var(--surface);
  overflow: hidden;
}

.input.filled {
  border-style: solid;
}

.input.over {
  border-color: var(--accent);
  background: var(--accent-soft);
}

img {
  display: block;
  max-width: 100%;
  max-height: 46vh;
}

.empty {
  display: grid;
  justify-items: center;
  gap: 8px;
  width: 100%;
  height: 100%;
  min-height: 180px;
  align-content: center;
  border: 0;
  background: transparent;
  color: var(--text-dim);
}

.empty:hover {
  color: var(--text);
}

.many {
  position: absolute;
  bottom: 10px;
  left: 50%;
  transform: translateX(-50%);
}

.clear {
  position: absolute;
  top: 8px;
  right: 8px;
}
</style>
