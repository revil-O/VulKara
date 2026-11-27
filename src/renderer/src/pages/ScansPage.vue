<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Scans: the photos on flatbed scans (PNG or JPEG) found, straightened and cut out into the export folder as
// "<scan> – Photo <n>.png", keeping the scan's bit depth, DPI and colour profile; nothing is overwritten. The engine
// finds the photos (engines/diffusers/scans.py); each frame can be corrected before the export. The cut-out photos
// can go on to Restore as a batch whose results land in the export folder too.
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { FolderOpen, Images, Plus, ScanLine, Trash2, WandSparkles } from '@lucide/vue'
import PageFrame from '../components/PageFrame.vue'
import PhotoFrames from '../components/PhotoFrames.vue'
import HintBadge from '../components/HintBadge.vue'
import { useHandoffStore } from '../stores/handoff'
import { useSettingsStore } from '../stores/settings'
import { cleanError } from '../stores/runtimes'
import { t } from '../i18n'
import { readingOrder } from '../util/scan_frames'
import type { ScanPhoto } from '@shared/api'

interface Scan {
  path: string
  size?: [number, number]
  photos: ScanPhoto[]
  state: 'waiting' | 'finding' | 'found' | 'none' | 'failed' | 'exported'
  error?: string
}

const SCAN = /\.(png|jpe?g)$/i
const MAX_SCANS = 100

const settings = useSettingsStore()
const handoff = useHandoffStore()
const router = useRouter()
const scans = ref<Scan[]>([])
const chosen = ref(0)
const drawing = ref(false)
const over = ref(false)
const exporting = ref(false)
const exported = ref<string[]>([])
const error = ref('')

const current = computed(() => scans.value[chosen.value])
const name = (p: string): string => p.split('/').pop() ?? p
const url = (p: string): string => window.vk.files.url(p)
const total = computed(() => scans.value.reduce((n, s) => n + s.photos.length, 0))
const folder = computed(() => settings.values.scanExportDir || '~/VulKara/scans')

/** Adds scans (no doubles) and finds the photos on each, one after another. */
async function add(paths: string[]): Promise<void> {
  const known = new Set(scans.value.map((s) => s.path))
  const fresh = paths.filter((p) => SCAN.test(p) && !known.has(p)).slice(0, MAX_SCANS - scans.value.length)
  scans.value.push(...fresh.map((path): Scan => ({ path, photos: [], state: 'waiting' })))
  for (const s of scans.value) {
    if (s.state !== 'waiting') continue
    s.state = 'finding'
    try {
      const found = await window.vk.scans.find(s.path)
      s.size = found.size
      s.photos = found.photos
      s.state = found.photos.length ? 'found' : 'none'
    } catch (err) {
      s.state = 'failed'
      s.error = cleanError(err)
    }
  }
}

async function choose(): Promise<void> {
  await add(await window.vk.files.chooseMany())
}

function drop(event: DragEvent): void {
  over.value = false
  void add([...(event.dataTransfer?.files ?? [])].map((f) => window.vk.files.pathOf(f)).filter(Boolean))
}

function removeScan(i: number): void {
  scans.value.splice(i, 1)
  chosen.value = Math.min(chosen.value, Math.max(0, scans.value.length - 1))
}

function setPhotos(photos: ScanPhoto[]): void {
  const s = current.value
  if (!s) return
  s.photos = photos
  if (s.state === 'none' || s.state === 'found' || s.state === 'exported') s.state = photos.length ? 'found' : 'none'
}

/** Every scan's photos cut out into the export folder, scan by scan; a scan that fails does not stop the others. */
async function exportAll(): Promise<void> {
  if (exporting.value) return
  exporting.value = true
  error.value = ''
  exported.value = []
  const errors: string[] = []
  try {
    for (const s of scans.value) {
      // a scan exported already goes again only after its frames changed (setPhotos makes it 'found' again)
      if (!s.photos.length || s.state === 'finding' || s.state === 'exported') continue
      try {
        s.photos = readingOrder(s.photos)
        exported.value.push(...await window.vk.scans.cut(s.path, JSON.parse(JSON.stringify(s.photos)), t('scans.word')))
        s.state = 'exported'
      } catch (err) {
        errors.push(`${name(s.path)}: ${cleanError(err)}`)
      }
    }
    error.value = errors.join(' · ')
  } finally {
    exporting.value = false
  }
}

const openFolder = (): Promise<void> => window.vk.scans.openFolder()

function toRestore(): void {
  handoff.send('restore', { batch: [...exported.value], exportBatch: true })
  void router.push({ path: '/restore', query: { t: Date.now() } })
}

onMounted(() => void settings.load())
</script>

<template>
  <PageFrame :title="t('scans.title')" :subtitle="t('scans.subtitle')">
    <div class="page-grid">
      <div
        v-if="!scans.length" class="empty card" :class="{ over }"
        @dragover.prevent="over = true" @dragleave="over = false" @drop.prevent="drop"
      >
        <ScanLine :size="28" />
        <p>{{ t('scans.empty') }}</p>
        <button class="btn primary" @click="choose"><Images :size="14" /> {{ t('scans.load') }}</button>
      </div>

      <div v-else class="work" @dragover.prevent @drop.prevent="drop">
        <ul class="list card">
          <li v-for="(s, i) in scans" :key="s.path" :class="{ on: i === chosen }" @click="chosen = i">
            <img :src="url(s.path)" alt="" />
            <span class="what">
              <span class="file">{{ name(s.path) }}</span>
              <small class="dim">
                <template v-if="s.state === 'waiting' || s.state === 'finding'">{{ t('scans.finding') }}</template>
                <template v-else-if="s.state === 'failed'"><span class="error">{{ t('scans.failed') }}</span></template>
                <template v-else-if="s.state === 'none'">{{ t('scans.none') }}</template>
                <template v-else>{{ t('scans.count', { n: s.photos.length }) }}<template v-if="s.state === 'exported'"> · {{ t('scans.exported') }}</template></template>
              </small>
            </span>
            <button class="btn small ghost" :aria-label="t('scans.removeScan')" :disabled="exporting" @click.stop="removeScan(i)"><Trash2 :size="12" /></button>
          </li>
          <li class="more"><button class="btn small" @click="choose"><Plus :size="12" /> {{ t('scans.more') }}</button></li>
        </ul>

        <div v-if="current" class="view">
          <div class="tools">
            <button class="btn small" :class="{ on: drawing }" :disabled="!current.size" @click="drawing = !drawing">
              <Plus :size="12" /> {{ t('scans.newFrame') }}
            </button>
            <span class="dim">{{ drawing ? t('scans.drawHint') : t('scans.editHint') }}</span>
          </div>
          <p v-if="current.state === 'failed'" class="error selectable">{{ current.error }}</p>
          <div class="stage">
            <div class="scan">
              <img :src="url(current.path)" alt="" draggable="false" />
              <PhotoFrames
                v-if="current.size" :photos="current.photos" :size="current.size" :drawing="drawing"
                @update:photos="setPhotos" @drawn="drawing = false"
              />
            </div>
          </div>
        </div>
      </div>

      <div v-if="scans.length" class="send">
        <span v-if="error" class="error selectable">{{ error }}</span>
        <span v-else-if="exported.length" class="dim">{{ t('scans.done', { n: exported.length }) }}</span>
        <span v-else class="dim">{{ t('scans.ready', { n: total }) }}</span>
        <span class="grow" />
        <template v-if="exported.length && !exporting">
          <button class="btn" @click="openFolder"><FolderOpen :size="14" /> {{ t('scans.openFolder') }}</button>
          <button class="btn" @click="toRestore"><WandSparkles :size="14" /> {{ t('scans.toRestore') }}</button>
        </template>
        <button class="btn primary" :disabled="!total || exporting" @click="exportAll">
          <ScanLine :size="14" /> {{ exporting ? t('scans.exporting') : t('scans.exportAll', { n: total }) }}
        </button>
      </div>
    </div>

    <template #panel>
      <div class="fields">
        <div class="field">
          <span>{{ t('scans.folder') }} <HintBadge :text="t('scans.folderHint')" /></span>
          <code class="selectable">{{ folder }}</code>
          <RouterLink to="/settings" class="dim">{{ t('scans.changeFolder') }}</RouterLink>
        </div>
        <small class="dim">{{ t('scans.about') }}</small>
        <small class="dim">{{ t('scans.restoreNote') }}</small>
      </div>
    </template>
  </PageFrame>
</template>

<style scoped>
.empty {
  display: grid;
  place-items: center;
  gap: 10px;
  min-height: 320px;
  border: 2px dashed var(--line);
  text-align: center;
}

.empty.over {
  border-color: var(--accent);
}

.work {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 12px;
  min-height: 0;
}

.list {
  display: grid;
  align-content: start;
  gap: 4px;
  max-height: 70vh;
  margin: 0;
  padding: 6px;
  overflow: auto;
  list-style: none;
}

.list li {
  display: grid;
  grid-template-columns: 40px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 4px;
  border-radius: var(--radius-s);
  cursor: pointer;
}

.list li.on {
  background: var(--accent-soft);
}

.list li.more {
  display: block;
  cursor: default;
}

.list img {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  object-fit: cover;
}

.what {
  display: grid;
  min-width: 0;
}

.file {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.view {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.tools {
  display: flex;
  gap: 10px;
  align-items: center;
}

.btn.on {
  border-color: var(--accent);
  color: var(--accent);
}

.stage {
  display: grid;
  place-items: center;
  padding: 18px;
  border-radius: var(--radius-m);
  background: var(--bg);
}

.scan {
  position: relative;
  line-height: 0;
}

.scan img {
  max-width: 100%;
  max-height: 68vh;
  user-select: none;
}

.send {
  display: flex;
  gap: 8px;
  align-items: center;
}

.grow {
  flex: 1;
}

.fields,
.field {
  display: grid;
  gap: 8px;
}

code {
  overflow-wrap: anywhere;
}
</style>
