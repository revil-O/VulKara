<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// The jobs of a page as tiles: a waiting or running job shows what it is and how far, a finished one its pictures.
import { jobLabel } from '../util/labels'
import { computed, ref } from 'vue'
import { CircleAlert, FileX, Heart, Info, Square, X } from 'lucide-vue-next'
import OpenHint from './OpenHint.vue'
import { useAssetsStore } from '../stores/assets'
import { useFavoritesStore } from '../stores/favorites'
import { useQueueStore } from '../stores/queue'
import { jobFacts, jobProgress } from '../util/format'
import { t } from '../i18n'
import type { QueuedJob } from '@shared/api'

defineProps<{ jobs: QueuedJob[] }>()
const emit = defineEmits<{ open: [job: QueuedJob, file: string] }>()
const queue = useQueueStore()
const url = (path: string): string => window.vk.files.url(path)
const isVideo = (path: string): boolean => /\.(mp4|webm)$/i.test(path)
const assets = useAssetsStore()
const modelName = (dir: string): string => assets.titleOf(dir)
/** job id -> place in the queue, from 1 */
const place = computed(() => new Map(queue.waiting.map((w, i) => [w.job.id, i + 1])))
const favorites = useFavoritesStore()
// a result whose file is gone (deleted, moved to the Trash, on a disk that is not there) is marked, not opened
const missing = ref(new Set<string>())
const gone = (file: string): void => {
  missing.value = new Set([...missing.value, file])
}
const fileName = (path: string): string => path.split('/').pop() ?? path
const openFile = (q: QueuedJob, file: string): void => {
  if (!missing.value.has(file)) emit('open', q, file)
}
// a job enters the history when it is over: only then can its pictures be marked
const over = (q: QueuedJob): boolean => q.state !== 'running' && q.state !== 'waiting'
/** everything about a job the tile has no room for: shown as the tooltip of its (i) */
const details = (q: QueuedJob): string => [
  q.job.label ? `${jobLabel(q.job.label)} · ${modelName(q.job.modelDir)}` : modelName(q.job.modelDir),
  q.job.prompt || t('library.noPrompt'),
  jobFacts(q),
  q.job.note,
  q.state === 'failed' ? q.error || t('library.gallery.failed') : undefined,
].filter(Boolean).join('\n\n')
</script>

<template>
  <div class="gallery">
    <template v-for="q in jobs" :key="q.job.id">
      <div
        v-for="file in queue.shown(q)" :key="file" class="tile picture" :class="{ missing: missing.has(file) }" role="button" tabindex="0"
        :title="q.job.prompt" @click="openFile(q, file)" @keydown.enter="openFile(q, file)"
      >
        <div v-if="missing.has(file)" class="gone">
          <FileX :size="26" :stroke-width="1.5" />
          <strong>{{ t('library.gallery.fileMissing') }}</strong>
          <small class="selectable">{{ fileName(file) }}</small>
          <small>{{ t('library.gallery.fileMissingHint') }}</small>
        </div>
        <span v-else class="frame">
          <video v-if="isVideo(file)" :src="url(file)" muted loop autoplay @error="gone(file)" />
          <img v-else :src="url(file)" draggable="false" @error="gone(file)" />
          <OpenHint>
            <template #start>
              <span v-if="q.job.label" class="label">{{ jobLabel(q.job.label) }}</span>
            </template>
            <template v-if="q.job.note">
              <span class="note" tabindex="0" :aria-label="t('library.gallery.note')" @click.stop @keydown.enter.stop><Info :size="12" /></span>
              <div class="details-panel note-panel selectable" @click.stop>{{ q.job.note }}</div>
            </template>
          </OpenHint>
        </span>
        <button
          v-if="over(q) && !missing.has(file)" class="heart" :class="{ on: favorites.has(file) }"
          :title="favorites.has(file) ? t('library.removeFavorite') : t('library.addFavorite')"
          @click.stop="favorites.toggle(q.job.id, file)" @keydown.enter.stop
        >
          <Heart :size="13" :fill="favorites.has(file) ? 'currentColor' : 'none'" />
        </button>
        <button class="close" :title="t('library.gallery.dismiss')" @click.stop="queue.dismiss(q, file)">
          <X :size="13" />
        </button>
      </div>
      <div v-if="!q.results.length || q.state === 'running'" class="tile job" :class="q.state">
        <!-- always in reach, also when the details are long (the button below can be cut off then) -->
        <button
          class="close" :title="q.state === 'running' ? t('common.cancel') : t('library.gallery.removeFromList')"
          @click="queue.cancel(q.job.id)"
        >
          <X :size="13" />
        </button>
        <!-- the native title tooltip does not show reliably in the app: the details open over the tile instead -->
        <span class="details" tabindex="0" :aria-label="t('library.gallery.details')"><Info :size="13" /></span>
        <div class="details-panel selectable">{{ details(q) }}</div>
        <div class="info">
          <strong>{{ q.job.label ? jobLabel(q.job.label) : modelName(q.job.modelDir) }}</strong>
          <p class="prompt dim">{{ q.job.prompt || t('library.noPrompt') }}</p>
          <p class="dim">{{ jobFacts(q) }}</p>
          <p v-if="q.job.note" class="note-text">{{ q.job.note.split(':')[0] }}</p>
          <template v-if="q.state === 'running'">
            <div class="bar" :class="{ unknown: q.progress <= 0 }">
              <i :style="q.progress > 0 ? { width: q.progress + '%' } : {}" />
            </div>
            <p class="state">{{ jobProgress(q) }}</p>
          </template>
          <p v-else-if="q.state === 'failed'" class="state error selectable"><CircleAlert :size="13" /> {{ q.error || t('library.gallery.failed') }}</p>
          <p v-else class="state">{{ q.state === 'waiting' ? t('library.gallery.waiting', { place: place.get(q.job.id) ?? '' }) : t('library.gallery.cancelled') }}</p>
          <button class="btn small" :class="{ danger: q.state === 'running' }" @click="queue.cancel(q.job.id)">
            <component :is="q.state === 'running' ? Square : X" :size="11" />
            {{ q.state === 'running' ? t('common.cancel') : t('common.remove') }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.tile {
  aspect-ratio: 1;
  border-radius: var(--radius-m);
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--line);
}

.picture {
  position: relative;
  padding: 0;
  cursor: pointer;
  display: grid;
  place-items: center;
  container-type: inline-size;
}

/* the picture's own outline, so that the band of OpenHint lies on the picture, not on the tile around it */
.frame {
  position: relative;
  display: block;
}

/* the tile is square: its width bounds both sides */
.picture img,
.picture video {
  max-width: 100cqw;
  max-height: 100cqw;
  display: block;
}

/* a result whose file is gone */
.picture.missing {
  cursor: default;
  border-style: dashed;
}

.gone {
  display: grid;
  justify-items: center;
  gap: 4px;
  padding: 12px;
  color: var(--text-dim);
  text-align: center;
  overflow-wrap: anywhere;
}

.gone strong {
  color: var(--text);
  font-size: 12px;
}

.gone small {
  font-size: 10.5px;
}

/* a cut-out (transparent background) shows on a checkerboard; opaque pictures cover it */
.picture img {
  background: repeating-conic-gradient(rgba(128, 128, 128, 0.22) 0% 25%, transparent 0% 50%) 50% / 16px 16px;
}

/* in the band of OpenHint, left of its text */
.label {
  flex-shrink: 0;
  max-width: 40%;
  padding: 2px 8px;
  border-radius: 9px;
  background: rgba(0, 0, 0, 0.65);
  color: #fff;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.picture:hover {
  border-color: var(--accent);
}

.picture:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

.close,
.heart {
  position: absolute;
  top: 8px;
  right: 8px;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  opacity: 0.7;
  cursor: pointer;
}

.picture:hover .close,
.close:focus-visible {
  opacity: 1;
}

.close:hover,
.heart:hover {
  background: rgba(0, 0, 0, 0.8);
}

/* the heart sits in the other corner; it shows on hover and stays when the picture is a favourite */
.heart {
  left: 8px;
  right: auto;
  opacity: 0;
}

.picture:hover .heart,
.heart:focus-visible,
.heart.on {
  opacity: 1;
}

.heart.on {
  color: var(--danger);
}

.job {
  position: relative;
  display: grid;
  place-items: center;
  padding: 16px;
}

.job .close {
  opacity: 0.85;
}

/* the job's full details, in the corner opposite the X: they open over the tile while the (i) is hovered or focused */
.details {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 2;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  color: var(--text-dim);
}

.details:hover,
.details:focus {
  background: var(--surface-2);
  color: var(--text);
  outline: none;
}

/* over the tile, below the (i) and the X */
.details-panel {
  display: none;
  position: absolute;
  z-index: 3;
  top: 36px;
  left: 8px;
  right: 8px;
  max-height: calc(100% - 44px);
  overflow-y: auto;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  background: var(--surface);
  box-shadow: var(--shadow);
  color: var(--text);
  font-size: 11.5px;
  line-height: 1.45;
  text-align: left;
  white-space: pre-line;
  overflow-wrap: anywhere;
}

/* a bridge over the gap between the (i) and the panel, so that the pointer can move into it */
.details::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 0;
  width: 24px;
  height: 6px;
}

.details:hover + .details-panel,
.details:focus + .details-panel,
.note:hover + .details-panel,
.note:focus + .details-panel,
.details-panel:hover {
  display: block;
}

/* a bridge over the gap to the panel above, so that the pointer can move into it */
.note::after {
  content: '';
  position: absolute;
  bottom: 100%;
  left: 0;
  width: 20px;
  height: 12px;
}

/* the note of a picture opens above the band, from its (i) */
.note-panel {
  top: auto;
  bottom: calc(100% + 6px);
  max-height: 60cqw;
  cursor: auto;
  pointer-events: auto;
}

.job.running {
  border-color: var(--accent);
}

.info {
  display: grid;
  justify-items: center;
  gap: 6px;
  width: 100%;
  max-height: 100%;
  overflow-y: auto;
  scrollbar-width: none;
  text-align: center;
  min-width: 0;
}

.prompt {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

.bar {
  width: 100%;
  margin-top: 4px;
}

.state {
  font-variant-numeric: tabular-nums;
}

.note {
  position: relative;
  z-index: 2;
  flex-shrink: 0;
  pointer-events: auto;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
}

.note-text {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 11px;
  color: var(--accent);
}

.error {
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
