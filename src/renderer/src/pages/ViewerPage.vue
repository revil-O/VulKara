<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// The large view, alone in its window: the picture, what it was made from and what can be done with it.
// ← and → go through the list the view was opened from.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { canCopyImage, canShare, copyPicture, sharePicture } from '../share'
import { Check, ChevronLeft, ChevronRight, Clapperboard, Copy, Download, Eraser, FolderSearch, Images, Maximize2, Repeat, Share, X } from '@lucide/vue'
import { EDITION } from '@shared/edition'
import type { ViewerAction, ViewerItem } from '@shared/api'
import { t } from '../i18n'

// inline: over the page in the remote web UI (no window). Given the items, it closes and acts by events, not natively.
const props = defineProps<{ inline?: { items: ViewerItem[]; index: number } }>()
const emit = defineEmits<{ close: []; act: [ViewerAction] }>()
const items = ref<ViewerItem[]>(props.inline?.items ?? [])
const index = ref(props.inline?.index ?? 0)
const item = computed(() => items.value[index.value])
const url = (path: string): string => window.vk.files.url(path)
const isVideo = computed(() => /\.(mp4|webm)$/i.test(item.value?.file ?? ''))

function step(by: number): void {
  const next = index.value + by
  if (next >= 0 && next < items.value.length) index.value = next
}

const close = (): void => { if (props.inline) emit('close'); else window.close() }

function key(event: KeyboardEvent): void {
  if (event.key === 'Escape') close()
  else if (event.key === 'ArrowLeft') step(-1)
  else if (event.key === 'ArrowRight') step(1)
}

onMounted(async () => {
  if (!props.inline) {
    const payload = await window.vk.viewer.payload()
    if (payload) {
      items.value = payload.items
      index.value = payload.index
    }
  }
  window.addEventListener('keydown', key)
})
// the overlay is reopened with another picture without unmounting
watch(() => props.inline, (p) => { if (p) { items.value = p.items; index.value = p.index } })
onBeforeUnmount(() => window.removeEventListener('keydown', key))
watch(item, (i) => {
  document.title = i ? (i.job.prompt || i.file.split('/').pop() || 'VulKara').slice(0, 80) : 'VulKara'
})

function saveAs(): void {
  const name = item.value.file.split('/').pop() ?? 'picture.png'
  if (props.inline) {
    // a browser saves by itself: the file's own address with a name to suggest
    const a = document.createElement('a')
    a.href = window.vk.files.url(item.value.file)
    a.download = name
    a.click()
  } else {
    void window.vk.files.saveAs(item.value.file, name)
  }
}
const reveal = (): Promise<void> => window.vk.files.reveal(item.value.file)
// in the app's window: macOS's share menu and clipboard; over the page in a browser only where the device offers them
const shareable = canShare()
const copyable = canCopyImage()
const share = (): Promise<void> => sharePicture(item.value.file)
/** the picture just copied (the button says so for a moment) */
const copied = ref('')
async function copyImage(): Promise<void> {
  const file = item.value.file
  if (!(await copyPicture(file))) return
  copied.value = file
  setTimeout(() => { if (copied.value === file) copied.value = '' }, 1500)
}
/** The settings into the form, or the picture into another page. In a window: back to the main one. Over the page:
 *  App.vue routes it and closes the overlay. */
function act(type: 'reuse' | 'continue', page: string): void {
  const action: ViewerAction = { type, page, job: JSON.parse(JSON.stringify(item.value.job)), file: item.value.file }
  if (props.inline) emit('act', action)
  else void window.vk.viewer.act(action)
}
</script>

<template>
  <div class="viewer">
    <div class="stage">
      <div v-if="!props.inline" class="drag" />
      <template v-if="item">
        <video v-if="isVideo" :key="item.file" :src="url(item.file)" controls loop autoplay />
        <img v-else :src="url(item.file)" draggable="false" />
      </template>
      <button v-if="index > 0" class="nav left" :title="t('viewer.previous')" @click="step(-1)"><ChevronLeft :size="22" /></button>
      <button v-if="index < items.length - 1" class="nav right" :title="t('viewer.next')" @click="step(1)"><ChevronRight :size="22" /></button>
      <button class="close" :title="t('viewer.close')" @click="close"><X :size="16" /></button>
    </div>
    <aside v-if="item" class="side">
      <div class="actions">
        <button class="btn" @click="saveAs"><Download :size="14" /> {{ t('viewer.saveAs') }}</button>
        <button v-if="!props.inline" class="btn" @click="reveal"><FolderSearch :size="14" /> {{ t('viewer.showInFinder') }}</button>
        <button v-if="shareable" class="btn" @click="share"><Share :size="14" /> {{ t('common.share') }}</button>
        <button v-if="copyable && !isVideo" class="btn" @click="copyImage">
          <component :is="copied === item.file ? Check : Copy" :size="14" /> {{ copied === item.file ? t('common.copied') : t('common.copyImage') }}
        </button>
        <button class="btn" :title="t('viewer.reuseHint')" @click="act('reuse', item.job.page)"><Repeat :size="14" /> {{ t('viewer.reuse') }}</button>
        <template v-if="!isVideo">
          <button class="btn" @click="act('continue', 'image')"><Images :size="14" /> {{ t('viewer.imageToImage') }}</button>
          <button class="btn" @click="act('continue', 'inpaint')"><Eraser :size="14" /> {{ t('viewer.inpaint') }}</button>
          <!-- video and upscaling are pages of the editions with ComfyUI only -->
          <template v-if="EDITION.comfyui">
            <button class="btn" @click="act('continue', 'video')"><Clapperboard :size="14" /> {{ t('viewer.imageToVideo') }}</button>
            <button class="btn" @click="act('continue', 'upscale')"><Maximize2 :size="14" /> {{ t('viewer.upscale') }}</button>
          </template>
        </template>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.viewer {
  display: flex;
  height: 100%;
}

.stage {
  position: relative;
  flex: 1;
  min-width: 0;
  display: grid;
  place-items: center;
  padding: 36px 16px 16px;
  background: #0e0f12;
}

@media (prefers-color-scheme: light) {
  .stage {
    background: #e9e7e2;
  }
}

/* the window is moved at its upper edge */
.drag {
  position: absolute;
  inset: 0 0 auto 0;
  height: 36px;
  -webkit-app-region: drag;
}

.stage img,
.stage video {
  max-width: 100%;
  max-height: 100%;
  min-height: 0;
  object-fit: contain;
  border-radius: var(--radius-s);
}

/* a cut-out (transparent background) shows on a checkerboard; opaque pictures cover it */
.stage img {
  background: repeating-conic-gradient(rgba(128, 128, 128, 0.25) 0% 25%, transparent 0% 50%) 50% / 20px 20px;
}

.nav {
  position: absolute;
  top: 50%;
  width: 38px;
  height: 38px;
  margin-top: -19px;
  border: 0;
  border-radius: 50%;
  background: rgba(127, 127, 127, 0.35);
  color: #fff;
  display: grid;
  place-items: center;
}

.nav:hover,
.close:hover {
  background: rgba(127, 127, 127, 0.6);
}

/* its own close button: a viewer over an app in full screen has no title bar */
.close {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 50%;
  background: rgba(127, 127, 127, 0.35);
  color: #fff;
  display: grid;
  place-items: center;
  -webkit-app-region: no-drag;
  z-index: 2;
}

.left {
  left: 14px;
}

.right {
  right: 14px;
}

.side {
  flex: none;
  width: 280px;
  overflow: auto;
  padding: 40px 16px 16px;
  display: grid;
  gap: 10px;
  align-content: start;
  background: var(--surface);
  border-left: 1px solid var(--line);
}

.actions {
  display: grid;
  gap: 6px;
}

.actions .btn {
  justify-content: flex-start;
}

@media (max-width: 860px) {
  .viewer {
    flex-direction: column;
  }
  .stage {
    padding: 44px 8px 8px;
    min-height: 55%;
  }
  .side {
    width: auto;
    max-height: 45%;
  }
}
</style>