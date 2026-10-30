<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Everything that was generated, newest first. The grid loads page by page while scrolling. Entries are
// selected like files in the Finder (click, ⌘-click, ⇧-click); the panel on the right always has the same
// width, so the grid does not move when the selection changes. As the Favorites page it shows only the pictures
// marked with the heart, in the same way.
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Check, Copy, Download, FolderSearch, Heart, ImageOff, Play, Repeat, Search, Share, Trash2, X } from 'lucide-vue-next'
import OpenHint from '../components/OpenHint.vue'
import PageFrame from '../components/PageFrame.vue'
import { useAssetsStore } from '../stores/assets'
import { useHandoffStore } from '../stores/handoff'
import { cleanError } from '../stores/runtimes'
import { formatDuration, pageName, perStep } from '../util/format'
import { formPage } from '../util/job_form'
import { dateLocale, t, type PlainKey } from '../i18n'
import { canCopyImage, canShare, copyPicture, sharePicture } from '../share'
import { styleLabel, jobLabel } from '../util/labels'
import type { HistoryEntry } from '@shared/types'

const props = defineProps<{ favorites?: boolean }>()

const PAGE_SIZE = 90
const entries = ref<HistoryEntry[]>([])
const total = ref(0)
const query = ref('')
const chosen = ref(new Set<string>())
const missing = ref(new Set<string>())
const sentinel = ref<HTMLElement>()
let anchor: string | undefined  // where a ⇧-click range starts
let loading = false
let generation = 0  // a newer search makes older answers obsolete

const url = (path: string): string => window.vk.files.url(path)
const selection = computed(() => entries.value.filter((e) => chosen.value.has(e.id)))
const selected = computed(() => (selection.value.length === 1 ? selection.value[0] : undefined))
/** the files of an entry this page shows: all of them, or on the Favorites page the marked ones */
const pictures = (e: HistoryEntry): string[] => (props.favorites ? e.favorites ?? [] : e.files)
/** the picture on the tile */
const cover = (e: HistoryEntry): string => pictures(e)[0] ?? e.files[0]
const isFavorite = (e: HistoryEntry, file: string): boolean => !!e.favorites?.includes(file)
const subtitle = computed(() => {
  if (!props.favorites) return t('library.entries', { n: total.value })
  // a job may have left several marked pictures: counted are those loaded so far
  const n = entries.value.reduce((sum, e) => sum + pictures(e).length, 0)
  return entries.value.length < total.value ? t('library.picturesMore', { n }) : t('library.pictures', { n })
})
const empty = computed(() => {
  if (query.value) return t('library.nothingFound')
  return props.favorites ? t('library.noFavorites') : t('library.nothingYet')
})

async function load(reset: boolean): Promise<void> {
  if (loading && !reset) return
  loading = true
  const mine = reset ? ++generation : generation
  try {
    const page = await window.vk.history.list({
      query: query.value, offset: reset ? 0 : entries.value.length, limit: PAGE_SIZE, favorites: props.favorites,
    })
    if (mine !== generation) return
    entries.value = reset ? page.entries : [...entries.value, ...page.entries]
    total.value = page.total
    if (reset) {
      const there = new Set(entries.value.map((e) => e.id))
      chosen.value = new Set([...chosen.value].filter((id) => there.has(id)))
    }
  } finally {
    // an answer to an older search must not let the next page load during the newer one
    if (mine === generation) loading = false
  }
}

let searchTimer: ReturnType<typeof setTimeout> | undefined
watch(query, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => void load(true), 200)
})

function pick(e: HistoryEntry, event: MouseEvent): void {
  const next = new Set(chosen.value)
  if (event.shiftKey && anchor) {
    const ids = entries.value.map((x) => x.id)
    const [a, b] = [ids.indexOf(anchor), ids.indexOf(e.id)].sort((x, y) => x - y)
    if (a >= 0) for (const id of ids.slice(a, b + 1)) next.add(id)
  } else if (event.metaKey || event.ctrlKey) {
    if (next.has(e.id)) next.delete(e.id)
    else next.add(e.id)
    anchor = e.id
  } else {
    next.clear()
    next.add(e.id)
    anchor = e.id
  }
  chosen.value = next
}

function key(event: KeyboardEvent): void {
  if ((event.target as HTMLElement).tagName === 'INPUT') return
  if (event.key === 'Escape') {
    chosen.value = new Set()
  } else if (event.key === 'a' && event.metaKey) {
    event.preventDefault()
    chosen.value = new Set(entries.value.map((e) => e.id))
  } else if ((event.key === 'Enter' || event.key === ' ') && selected.value) {
    event.preventDefault()
    view(selected.value)
  } else if ((event.key === 'Backspace' || event.key === 'Delete') && chosen.value.size) {
    void remove(true)
  }
}

let observer: IntersectionObserver | undefined
let stopListening: (() => void) | undefined
let stale = false
onMounted(() => {
  void load(true)
  observer = new IntersectionObserver((hits) => {
    if (hits.some((h) => h.isIntersecting) && entries.value.length < total.value) void load(false)
  }, { rootMargin: '600px' })
  if (sentinel.value) observer.observe(sentinel.value)
  // new results arrive while another page is shown: refresh when this one comes back
  stopListening = window.vk.history.onChange(() => { stale = true })
})
onActivated(() => {
  window.addEventListener('keydown', key)
  if (stale) {
    stale = false
    void load(true)
  }
})
onDeactivated(() => window.removeEventListener('keydown', key))
onBeforeUnmount(() => {
  clearTimeout(searchTimer)
  observer?.disconnect()
  stopListening?.()
  window.removeEventListener('keydown', key)
})

const assets = useAssetsStore()
/** the name the app shows for the job's model (its own name, if it was given one) */
const modelTitle = (e: HistoryEntry): string => (e.job.modelDir ? assets.titleOf(e.job.modelDir) : e.modelName)

const facts = computed(() => {
  const e = selected.value
  if (!e) return []
  const j = e.job
  const rows: [PlainKey, string][] = [
    ['library.facts.created', new Date(e.createdAt).toLocaleString(dateLocale())],
    ['library.facts.page', pageName(j.page)],
    ['library.facts.model', modelTitle(e) || '–'],
    ['library.facts.size', `${j.width} × ${j.height}`],
    ['library.facts.seed', String(j.seed)],
  ]
  if (j.style) rows.push(['library.facts.style', styleLabel(j.style)])
  if (j.steps) rows.push(['library.facts.steps', String(j.steps)])
  if (j.guidance !== undefined) rows.push(['library.facts.guidance', String(j.guidance)])
  if (j.sampler) rows.push(['library.facts.sampler', j.sigmaSchedule ? `${j.sampler} · ${j.sigmaSchedule}` : j.sampler])
  if (j.strength !== undefined) rows.push(['library.facts.strength', String(j.strength)])
  if (j.videoSeconds) rows.push(['library.facts.length', `${j.videoSeconds} s`])
  if (e.seconds !== undefined) {
    rows.push(['library.facts.duration', formatDuration(e.seconds) + (e.secondsPerStep ? ' · ' + perStep(e.secondsPerStep) : '')])
  }
  if (j.loras?.length) rows.push(['library.facts.loras', j.loras.map((l) => `${l.path.split('/').pop()} (${l.scale})`).join(', ')])
  if (j.controlnet) rows.push(['library.facts.controlnet', `${j.controlnet.type} (${j.controlnet.weight})`])
  if (j.label) rows.push(['library.facts.label', jobLabel(j.label)])
  if (j.note) rows.push(['library.facts.note', j.note])
  return rows
})

/** Removes the selected entries; with trashFiles their pictures go to the Trash. */
async function remove(trashFiles: boolean): Promise<void> {
  const ids = selection.value.map((e) => e.id)
  if (!ids.length) return
  if (trashFiles && !confirm(t('library.confirmTrash', { n: ids.length }))) return
  if (!trashFiles && ids.length > 1 && !confirm(t('library.confirmRemove', { n: ids.length }))) return
  try {
    await window.vk.history.remove(ids, trashFiles)
  } catch (err) {
    alert(cleanError(err))
    return
  }
  stale = false
  const gone = new Set(ids)
  entries.value = entries.value.filter((x) => !gone.has(x.id))
  total.value -= ids.length
  chosen.value = new Set()
  // the grid may have become shorter than the window
  if (entries.value.length < Math.min(total.value, PAGE_SIZE)) void load(false)
}

/** Marks or unmarks one file; on the Favorites page an entry without marked pictures leaves the grid. */
async function toggleFavorite(e: HistoryEntry, file: string): Promise<void> {
  const before = e.favorites
  const on = !isFavorite(e, file)
  const marked = new Set(before ?? [])
  if (on) marked.add(file)
  else marked.delete(file)
  e.favorites = e.files.filter((f) => marked.has(f))
  try {
    await window.vk.history.favorite(e.id, file, on)
  } catch (err) {
    e.favorites = before
    alert(cleanError(err))
    return
  }
  stale = false
  if (props.favorites && !e.favorites.length) {
    entries.value = entries.value.filter((x) => x.id !== e.id)
    total.value -= 1
    const next = new Set(chosen.value)
    next.delete(e.id)
    chosen.value = next
    if (entries.value.length < Math.min(total.value, PAGE_SIZE)) void load(false)
  }
}

const router = useRouter()
const handoff = useHandoffStore()

/** Prompt and settings of the entry go back into the form of its page. */
function reuse(e: HistoryEntry): void {
  const page = formPage(e.job.page)
  handoff.send(page, { job: e.job, inputImage: page === 'text' ? undefined : e.job.inputImage })
  void router.push('/' + page)
}

/** The large view opens in a window of its own, with the loaded history to step through. */
function view(e: HistoryEntry): void {
  const items = entries.value.map((x) => ({ job: JSON.parse(JSON.stringify(x.job)), file: cover(x), model: modelTitle(x) }))
  void window.vk.viewer.open(items, entries.value.findIndex((x) => x.id === e.id))
}

const reveal = (path: string): Promise<void> => window.vk.files.reveal(path)
const saveAs = (path: string): Promise<boolean> => window.vk.files.saveAs(path, path.split('/').pop() ?? 'picture.png')
// in the app: macOS's share menu and clipboard; in a browser only where the device offers them (HTTPS)
const shareable = canShare()
const copyable = canCopyImage()
const share = (path: string): Promise<void> => sharePicture(path)
/** the picture just copied (its button says so for a moment) */
const copiedFile = ref('')
// portrait pictures and videos: only as high as a square one is
const tall = ref(new Set<string>())
const measure = (f: string, w: number, h: number): void => { if (h > w) tall.value = new Set(tall.value).add(f) }
async function copyImage(path: string): Promise<void> {
  if (!(await copyPicture(path))) return
  copiedFile.value = path
  setTimeout(() => { if (copiedFile.value === path) copiedFile.value = '' }, 1500)
}
</script>

<template>
  <PageFrame :title="favorites ? t('library.favorites') : t('library.history')" :subtitle="subtitle" wide-panel>
    <template #actions>
      <label class="search">
        <Search :size="14" class="dim" />
        <input v-model="query" type="search" :placeholder="t('library.search')" spellcheck="false" />
      </label>
    </template>

    <p v-if="!total" class="dim">{{ empty }}</p>
    <div class="grid">
      <div v-for="e in entries" :key="e.id" class="cell">
        <button class="tile" :class="{ active: chosen.has(e.id) }" :title="e.job.prompt" @click="pick(e, $event)" @dblclick="view(e)">
          <div v-if="missing.has(e.id)" class="gone dim"><ImageOff :size="20" /></div>
          <video v-else-if="e.kind === 'video'" :src="url(cover(e))" preload="metadata" muted @error="missing.add(e.id)" />
          <img v-else :src="url(cover(e))" loading="lazy" decoding="async" draggable="false" @error="missing.add(e.id)" />
          <Play v-if="e.kind === 'video'" :size="16" class="badge" />
          <span v-if="pictures(e).length > 1" class="badge count">{{ pictures(e).length }}</span>
        </button>
        <!-- next to the tile, not in it: a button can not hold another one -->
        <button
          class="heart" :class="{ on: isFavorite(e, cover(e)) }"
          :title="isFavorite(e, cover(e)) ? t('library.removeFavorite') : t('library.addFavorite')"
          @click="toggleFavorite(e, cover(e))"
        >
          <Heart :size="13" :fill="isFavorite(e, cover(e)) ? 'currentColor' : 'none'" />
        </button>
      </div>
    </div>
    <div ref="sentinel" class="sentinel" />

    <template #panel>
      <div v-if="selected" class="detail">
        <template v-for="f in pictures(selected)" :key="f">
          <video v-if="selected.kind === 'video'" :src="url(f)" controls loop class="big" :class="{ tall: tall.has(f) }"
            @loadedmetadata="(ev) => measure(f, (ev.target as HTMLVideoElement).videoWidth, (ev.target as HTMLVideoElement).videoHeight)" />
          <span v-else class="frame" :class="{ tall: tall.has(f) }" @click="view(selected)">
            <img :src="url(f)" class="big zoom" :class="{ tall: tall.has(f) }" draggable="false"
              @load="(ev) => measure(f, (ev.target as HTMLImageElement).naturalWidth, (ev.target as HTMLImageElement).naturalHeight)" />
            <OpenHint />
          </span>
        </template>
        <!-- buttons in the left third, the settings and prompts beside them -->
        <div class="info">
          <div class="buttons">
            <div v-for="f in pictures(selected)" :key="f" class="buttons">
              <!-- several pictures: each group of buttons under a small copy of its picture -->
              <img v-if="pictures(selected).length > 1 && selected.kind !== 'video'" :src="url(f)" class="mark" draggable="false" />
              <button class="btn small" :class="{ marked: isFavorite(selected, f) }" @click="toggleFavorite(selected, f)">
                <Heart :size="12" :fill="isFavorite(selected, f) ? 'currentColor' : 'none'" /> {{ t('library.favourite') }}
              </button>
              <button class="btn small" @click="saveAs(f)"><Download :size="12" /> {{ t('library.saveAs') }}</button>
              <button class="btn small" @click="reveal(f)"><FolderSearch :size="12" /> {{ t('library.showInFinder') }}</button>
              <button v-if="shareable" class="btn small" @click="share(f)"><Share :size="12" /> {{ t('common.share') }}</button>
              <button v-if="copyable && selected.kind !== 'video'" class="btn small" @click="copyImage(f)">
                <component :is="copiedFile === f ? Check : Copy" :size="12" /> {{ copiedFile === f ? t('common.copied') : t('common.copyImage') }}
              </button>
            </div>
            <div class="buttons">
              <button class="btn small" :title="t('library.reuseHint')" @click="reuse(selected)"><Repeat :size="12" /> {{ t('library.reuse') }}</button>
              <button class="btn small" :title="t('library.filesStay')" @click="remove(false)"><X :size="12" /> {{ t('library.removeEntry') }}</button>
              <button class="btn small danger" @click="remove(true)"><Trash2 :size="12" /> {{ t('library.moveToTrash') }}</button>
            </div>
          </div>
          <div class="facts">
            <dl>
              <template v-for="[k, v] in facts" :key="k">
                <dt class="dim">{{ t(k) }}</dt>
                <dd class="selectable">{{ v }}</dd>
              </template>
            </dl>
            <hr />
            <h3>{{ t('library.facts.prompt') }}</h3>
            <p class="prompt selectable">{{ selected.job.prompt || t('library.noPrompt') }}</p>
            <template v-if="selected.job.negativePrompt">
              <hr />
              <h3>{{ t('library.facts.negative') }}</h3>
              <p class="prompt selectable">{{ selected.job.negativePrompt }}</p>
            </template>
          </div>
        </div>
      </div>
      <div v-else-if="selection.length" class="detail">
        <h2>{{ t('library.selected', { n: selection.length }) }}</h2>
        <div class="stack">
          <img v-for="e in selection.filter((x) => x.kind === 'image').slice(0, 9)" :key="e.id" :src="url(cover(e))" draggable="false" />
        </div>
        <div class="row">
          <button class="btn small" :title="t('library.filesStay')" @click="remove(false)"><X :size="12" /> {{ t('library.removeEntries') }}</button>
          <button class="btn small danger" @click="remove(true)"><Trash2 :size="12" /> {{ t('library.moveToTrash') }}</button>
        </div>
        <div class="row">
          <button class="btn small ghost" @click="chosen = new Set()">{{ t('library.clearSelection') }}</button>
        </div>
      </div>

      <div v-else class="hint dim">
        <p>{{ t('library.help.select') }}</p>
        <p>{{ t('library.help.heart') }}</p>
        <p>{{ t('library.help.open') }}</p>
        <p>{{ t('library.help.keys') }}</p>
      </div>
    </template>
  </PageFrame>
</template>

<style scoped>
.search input {
  width: 240px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: 8px;
}

.cell {
  position: relative;
}

.tile {
  position: relative;
  display: block;
  width: 100%;
  aspect-ratio: 1;
  padding: 0;
  border: 0;
  border-radius: var(--radius-m);
  background: var(--surface-2);
  overflow: hidden;
}

/* drawn over the picture, so selecting does not change any size */
.tile.active::after {
  content: '';
  position: absolute;
  inset: 0;
  border: 3px solid var(--accent);
  border-radius: inherit;
  background: var(--accent-soft);
}

.tile img,
.tile video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.gone {
  display: grid;
  place-items: center;
  height: 100%;
}

.badge {
  position: absolute;
  right: 6px;
  bottom: 6px;
  color: #fff;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.7));
}

.badge.count {
  padding: 0 6px;
  border-radius: 9px;
  background: rgba(0, 0, 0, 0.6);
  font-size: 11px;
}

.heart {
  position: absolute;
  top: 6px;
  left: 6px;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  opacity: 0;
  cursor: pointer;
}

/* shows on hover and stays when the picture is a favourite */
.cell:hover .heart,
.heart:focus-visible,
.heart.on {
  opacity: 1;
}

.heart:hover {
  background: rgba(0, 0, 0, 0.8);
}

.heart.on,
.btn.marked {
  color: var(--danger);
}

.sentinel {
  height: 1px;
}

.detail,
.hint {
  display: grid;
  gap: 12px;
}

.big {
  width: 100%;
  border-radius: var(--radius-m);
  background: var(--surface-2);
}

.detail {
  container-type: inline-size;
}

.big.tall {
  width: auto;
  max-width: 100%;
  height: 100cqw;
  justify-self: center;
}

.zoom {
  cursor: zoom-in;
}

/* the picture with its OpenHint band; a portrait picture keeps its own width */
.frame {
  position: relative;
  display: block;
  line-height: 0;
  border-radius: var(--radius-m);
  overflow: hidden;
}

.frame.tall {
  justify-self: center;
}

.stack {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
}

.stack img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: var(--radius-s);
}

/* under the picture: the buttons one under the other in the left third, the settings in the rest */
.info {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 16px;
  align-items: start;
}

.facts {
  display: grid;
  gap: 10px;
  min-width: 0;
  padding-left: 16px;
  border-left: 1px solid var(--line);
}

.facts .prompt,
.facts h3 {
  margin: 0;
}

.facts h3 {
  font-size: inherit;
  font-weight: 600;
}

.facts hr {
  width: 100%;
  margin: 0;
  border: 0;
  border-top: 1px solid var(--line);
}

.buttons {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.buttons > .buttons + .buttons {
  margin-top: 8px;
}

.mark {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: var(--radius-s);
}

.buttons .btn {
  justify-content: center;
}

.row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.prompt {
  white-space: pre-wrap;
  word-break: break-word;
}

dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 12px;
  margin: 0;
}

dd {
  margin: 0;
  word-break: break-word;
}
</style>
