<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// The picture picker (util/pick_image.ts): the pictures of the history, newest first, searchable and filtered to the
// favourites on request; one click takes a picture. "From disk" opens the file dialog instead.
import { jobLabel } from '../util/labels'
import { computed, nextTick, ref, watch } from 'vue'
import { FolderOpen, Heart, Search, X } from '@lucide/vue'
import { finishPick, picker } from '../util/pick_image'
import type { HistoryEntry } from '@shared/types'
import { t } from '../i18n'
import { isRemote } from '../remote_vk'

const PAGE_SIZE = 40
// a browser of the remote web UI cannot open the Mac's file dialog: there the history is the source
const diskChoice = !isRemote()
const dialog = ref<HTMLDialogElement>()
const query = ref('')
const favorites = ref(false)
const entries = ref<HistoryEntry[]>([])
const total = ref(0)
const loading = ref(false)
const broken = ref(new Set<string>())
let generation = 0

// every picture of the loaded entries (a job can have several), with what made it
const pictures = computed(() => entries.value
  .filter((e) => e.kind === 'image')
  .flatMap((e) => (favorites.value && e.favorites ? e.favorites : e.files).map((file) => ({ file, entry: e })))
  .filter((p) => !broken.value.has(p.file)))
const url = (p: string): string => window.vk.files.url(p)

async function load(reset: boolean): Promise<void> {
  const mine = reset ? ++generation : generation
  loading.value = true
  try {
    const page = await window.vk.history.list({
      query: query.value, offset: reset ? 0 : entries.value.length, limit: PAGE_SIZE, favorites: favorites.value,
    })
    if (mine !== generation) return
    entries.value = reset ? page.entries : [...entries.value, ...page.entries]
    total.value = page.total
  } finally {
    if (mine === generation) loading.value = false
  }
}

watch(() => picker.open, async (open) => {
  if (!open) {
    if (dialog.value?.open) dialog.value.close()
    return
  }
  broken.value = new Set()
  await load(true)
  await nextTick()
  if (!dialog.value?.open) dialog.value?.showModal()
})

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(query, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => void load(true), 200)
})
watch(favorites, () => void load(true))

function onScroll(event: Event): void {
  const el = event.target as HTMLElement
  if (!loading.value && entries.value.length < total.value && el.scrollTop + el.clientHeight > el.scrollHeight - 300) void load(false)
}

async function fromDisk(): Promise<void> {
  const chosen = await window.vk.files.choose('image')
  if (chosen) finishPick(chosen)
}

// a file the history still lists but that is gone (moved, in the Trash) is left out
function gone(file: string): void {
  broken.value = new Set([...broken.value, file])
}

const close = (): void => finishPick(undefined)
</script>

<template>
  <!-- @close: Escape may close a modal dialog without a cancel event -->
  <dialog ref="dialog" class="picker" @cancel.prevent="close" @close="picker.open && close()" @click.self="close">
    <div class="inner">
      <header>
        <h2 class="grow">{{ t('common.picker.title') }}</h2>
        <button v-if="diskChoice" class="btn primary" @click="fromDisk"><FolderOpen :size="14" /> {{ t('common.picker.fromDisk') }}</button>
        <button class="btn small ghost" :aria-label="t('common.close')" @click="close"><X :size="14" /></button>
      </header>
      <div class="controls">
        <label class="search">
          <Search :size="14" />
          <input v-model="query" type="search" :placeholder="t('common.picker.search')" spellcheck="false" />
        </label>
        <button class="btn" :class="{ on: favorites }" @click="favorites = !favorites"><Heart :size="13" /> {{ t('common.picker.favorites') }}</button>
      </div>
      <div class="grid" @scroll="onScroll">
        <button v-for="p in pictures" :key="p.file" class="pic" @click="finishPick(p.file)">
          <img :src="url(p.file)" loading="lazy" draggable="false" @error="gone(p.file)" />
          <span class="caption">{{ p.entry.job.prompt || (p.entry.job.label ? jobLabel(p.entry.job.label) : p.entry.modelName) }}</span>
        </button>
        <p v-if="!pictures.length && !loading" class="dim empty">
          {{ query || favorites ? t('common.picker.nothingFound') : t('common.picker.empty') }}
        </p>
      </div>
    </div>
  </dialog>
</template>

<style scoped>
.picker {
  width: min(1100px, calc(100vw - 80px));
  height: min(820px, calc(100vh - 80px));
  padding: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius-l);
  background: var(--bg);
  color: var(--text);
  box-shadow: var(--shadow);
}

.picker::backdrop {
  background: rgba(0, 0, 0, 0.45);
}

.inner {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  padding: 16px 18px;
  box-sizing: border-box;
}

header {
  display: flex;
  align-items: center;
  gap: 10px;
}

h2 {
  margin: 0;
  font-size: 16px;
}

.grow {
  flex: 1;
}

.controls {
  display: flex;
  gap: 10px;
}

.search {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 8px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface);
  color: var(--text-dim);
}

.search input {
  flex: 1;
  border: 0;
  background: transparent;
  outline: none;
}

.btn.on {
  border-color: var(--accent);
  color: var(--accent);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  grid-auto-rows: 160px;
  align-content: start;
  gap: 10px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.pic {
  position: relative;
  min-height: 0;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  background: var(--surface);
  overflow: hidden;
  cursor: pointer;
}

.pic:hover {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}

.pic img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.caption {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 14px 8px 6px;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.65));
  color: #fff;
  font-size: 11px;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  opacity: 0;
  transition: opacity 0.12s;
}

.pic:hover .caption {
  opacity: 1;
}

.empty {
  grid-column: 1 / -1;
  padding: 40px 0;
  text-align: center;
}
</style>
