<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// A batch: many pictures with the page's settings, one job each through the queue (one after another, never at once).
// The page gives the job of one picture (make); a picture's size comes from the picture itself.
import { computed, onMounted, ref } from 'vue'
import { Play, Plus, X } from '@lucide/vue'
import { useQueueStore } from '../stores/queue'
import { cleanError } from '../stores/runtimes'
import { t } from '../i18n'
import { MAX_BATCH, mergeBatch, sendEach } from '../util/batch'
import type { Job } from '@shared/types'

const paths = defineModel<string[]>({ required: true })
const props = defineProps<{ make: (path: string, size: [number, number]) => Omit<Job, 'id'>; blocked?: string }>()
const queue = useQueueStore()
const ids = ref<string[]>([])
const sending = ref(false)
const error = ref('')
const capped = ref(0)

const url = (p: string): string => window.vk.files.url(p)
const name = (p: string): string => p.split('/').pop() ?? p
const mine = computed(() => queue.jobs.filter((q) => ids.value.includes(q.job.id)))
const waiting = computed(() => mine.value.filter((q) => q.state === 'waiting'))
const done = computed(() => mine.value.filter((q) => q.state === 'done').length)
const failed = computed(() => mine.value.filter((q) => q.state === 'failed').length)

/** Adds pictures (no doubles), the first MAX_BATCH. */
function add(more: string[]): void {
  const got = mergeBatch(paths.value, more)
  capped.value = got.capped
  paths.value = got.paths
}

async function choose(): Promise<void> {
  add(await window.vk.files.chooseMany())
}

function sizeOf(path: string): Promise<[number, number]> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve([img.naturalWidth, img.naturalHeight])
    img.onerror = () => reject(new Error(t('edit.batch.unreadable', { name: name(path) })))
    img.src = url(path)
  })
}

async function run(): Promise<void> {
  error.value = props.blocked ?? ''
  if (error.value || sending.value) return
  sending.value = true
  ids.value = []
  try {
    const errors = await sendEach(paths.value, async (p) => queue.add(props.make(p, await sizeOf(p))),
      (got) => { ids.value = [...ids.value, ...got] })
    error.value = [...new Set(errors.map((e) => cleanError(e)))].join(' · ')
  } finally {
    sending.value = false
  }
}

async function cancelRest(): Promise<void> {
  for (const q of waiting.value) await queue.cancel(q.job.id)
}

// pictures handed over at once (a dialog, a drop) are capped like added ones
onMounted(() => add([]))
</script>

<template>
  <div class="batch card">
    <div class="head">
      <strong>{{ t('edit.batch.count', { n: paths.length }) }}</strong>
      <span class="grow" />
      <button class="btn small" @click="choose"><Plus :size="12" /> {{ t('edit.batch.more') }}</button>
      <button class="btn small ghost" @click="paths = []">{{ t('edit.batch.clear') }}</button>
    </div>
    <p v-if="capped" class="dim">{{ t('edit.batch.capped', { max: MAX_BATCH, n: capped }) }}</p>
    <div class="thumbs">
      <figure v-for="p in paths" :key="p" :title="name(p)">
        <img :src="url(p)" loading="lazy" draggable="false" />
        <button class="btn small clear" :title="t('edit.batch.remove')" @click="paths = paths.filter((x) => x !== p)"><X :size="10" /></button>
      </figure>
    </div>
    <div class="send">
      <span v-if="error" class="error selectable">{{ error }}</span>
      <span v-if="ids.length" class="dim">
        {{ t('edit.batch.status', { done, n: ids.length }) }}<template v-if="failed"> · {{ t('edit.batch.failed', { n: failed }) }}</template>
      </span>
      <span v-else-if="!error" class="dim">{{ t('edit.batch.hint') }}</span>
      <span class="buttons">
        <button v-if="waiting.length" class="btn" @click="cancelRest">{{ t('edit.batch.cancelRest', { n: waiting.length }) }}</button>
        <button class="btn primary" :disabled="sending || !paths.length || !!blocked" :title="blocked" @click="run">
          <Play :size="14" /> {{ t('edit.batch.run', { n: paths.length }) }}
        </button>
      </span>
    </div>
  </div>
</template>

<style scoped>
.batch {
  display: grid;
  gap: 10px;
  padding: 12px;
}

.head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.grow {
  flex: 1;
}

.thumbs {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
  gap: 6px;
  max-height: 46vh;
  overflow: auto;
}

figure {
  position: relative;
  margin: 0;
  aspect-ratio: 1;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  overflow: hidden;
  background: var(--surface);
}

figure img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.clear {
  position: absolute;
  top: 3px;
  right: 3px;
  padding: 2px;
}

.send {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.buttons {
  display: flex;
  gap: 8px;
}
</style>
