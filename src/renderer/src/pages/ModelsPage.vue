<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Models and LoRAs: what is installed, what is recommended, and adding more from Hugging Face, Civitai or disk.
// Nothing is part of the app; every model is downloaded or imported here.
import { computed, nextTick, onActivated, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { Boxes, Check, CircleAlert, Download, ExternalLink, FileDown, FolderOpen, FolderSearch, Layers, Pencil, Search, Square, Trash2, X } from '@lucide/vue'
import LoraFinder from '../components/LoraFinder.vue'
import HintBadge from '../components/HintBadge.vue'
import PageFrame from '../components/PageFrame.vue'
import { useAssetsStore } from '../stores/assets'
import { useImportsStore } from '../stores/imports'
import { cleanError, useRuntimesStore } from '../stores/runtimes'
import { useSettingsStore } from '../stores/settings'
import { CURATED, GROUPS, importRequest, installedAs, licencePage, memoryFit, type CuratedModel } from '../util/curated'
import { openLink } from '../util/links'
import { isRemote } from '../remote_vk'
import { num, t, type PlainKey } from '../i18n'
import type { HelperModel, ImportInfo, ImportJob, ImportRequest, PhotoTool, RecommendedTool } from '@shared/api'
import { baseOfAsset, type FindKind } from '@shared/lora_bases'
import { familyTitle } from '@shared/lora_fit'
import type { Asset } from '@shared/types'
import { curatedDescription, helperGroup } from '../util/data_texts'

const assets = useAssetsStore()
const imports = useImportsStore()
const runtimes = useRuntimesStore()
const settings = useSettingsStore()

// a browser (remote web UI) chooses, finds and installs models; what touches the Mac's files stays on the Mac
const remote = isRemote()
type Tab = 'installed' | 'recommended' | 'add'
const TABS: { id: Tab; title: PlainKey }[] = [
  { id: 'installed', title: 'models.tabs.installed' },
  { id: 'recommended', title: 'models.tabs.recommended' },
  ...(remote ? [] : [{ id: 'add' as Tab, title: 'models.tabs.add' as PlainKey }]),
]
const tab = ref<Tab>('installed')
const ramGb = ref(0)
// e.g. "MacBook Pro (13-inch, M2, 2022) · 24 GB"
const macName = ref('')
const tokens = reactive({ hf: false, civitai: false })
const diffusersInstalled = computed(() => runtimes.list.some((r) => r.id === 'diffusers' && r.installed))

async function refresh(): Promise<void> {
  const [hf, civitai, info] = await Promise.all([
    window.vk.tokens.has('huggingface'), window.vk.tokens.has('civitai'), window.vk.app.info(),
    assets.refresh(), imports.start(), runtimes.refresh(), settings.load(), loadHelpers(),
  ])
  Object.assign(tokens, { hf, civitai })
  ramGb.value = info.ramGb
  macName.value = info.mac
  if (!assets.all.length && tab.value === 'installed') tab.value = 'recommended'
}
onActivated(refresh)

const url = (path: string): string => window.vk.files.url(path)
const reveal = (path: string): Promise<void> => window.vk.files.reveal(path)

// ------------------------------------------------------------------ a model written as one checkpoint file
const exporting = ref<{ id: string; stage: string; percent: number } | undefined>()
const exported = ref<{ id: string; text: string; error?: boolean } | undefined>()
const stopExportProgress = window.vk.assets.onExportProgress((stage, percent) => { if (exporting.value) exporting.value = { ...exporting.value, stage, percent } })
onBeforeUnmount(stopExportProgress)
async function exportSingle(a: Asset): Promise<void> {
  exported.value = undefined
  exporting.value = { id: a.id, stage: t('models.installed.choosingWhere'), percent: -1 }
  try {
    const file = await window.vk.assets.exportSingle(a.id)
    if (file) exported.value = { id: a.id, text: t('models.installed.savedAs', { file: file.split('/').pop() ?? file }) }
  } catch (err) {
    exported.value = { id: a.id, text: cleanError(err), error: true }
  } finally {
    exporting.value = undefined
  }
}

// ------------------------------------------------------------------ installed
const kind = ref<'all' | 'model' | 'lora' | 'helper'>('all')
const query = ref('')
const shown = computed(() => {
  const words = query.value.toLowerCase().split(/\s+/).filter(Boolean)
  return assets.all.filter((a) => {
    if (kind.value !== 'all' && a.type !== kind.value) return false
    const text = `${a.title} ${a.name} ${a.meta.label} ${a.meta.family}`.toLowerCase()
    return words.every((w) => text.includes(w))
  })
})
// the installed ones by kind, each kind with its own tint
type Section = 'image' | 'video' | 'lora'
const SECTIONS: { id: Section; title: PlainKey }[] = [
  { id: 'image', title: 'models.installed.imageModels' },
  { id: 'video', title: 'models.installed.videoModels' },
  { id: 'lora', title: 'models.installed.loras' },
]
const sectionOf = (a: Asset): Section => (a.type === 'lora' ? 'lora' : a.meta.kind === 'video' ? 'video' : 'image')
const sections = computed(() => SECTIONS
  .map((sec) => ({ ...sec, assets: shown.value.filter((a) => sectionOf(a) === sec.id) }))
  .filter((sec) => sec.assets.length))
const removeError = ref('')

// ------------------------------------------------------------------ helper models
// content filter, Restore, pose and depth, ControlNets, upscaling and the photo tools: one kind with its own tint
const HELPER_PICTURES = import.meta.glob('../assets/helpers/*.jpg', { eager: true, query: '?url', import: 'default' }) as Record<string, string>
const helperPicture = (name: string): string => HELPER_PICTURES[`../assets/helpers/${name}.jpg`] ?? ''
// i18n-ok
const HELPER_GROUPS = ['Content filter', 'Restore', 'Pose and depth', 'ControlNet', 'Upscale', 'Photo tools']
const helpers = ref<HelperModel[]>([])
const tools = ref<{ installed: PhotoTool[]; recommended: RecommendedTool[] }>({ installed: [], recommended: [] })

async function loadHelpers(): Promise<void> {
  if (remote) return
  const [h, tl] = await Promise.all([window.vk.helpers.list(), window.vk.tools.list()])
  helpers.value = h
  tools.value = tl
}
// a helper that finished downloading shows as there
watch(() => imports.jobs.map((j) => j.state).join(), () => void loadHelpers())

interface HelperCard {
  key: string
  name: string
  group: string
  description: string
  installed: boolean
  required: boolean
  /** MB: on the disk when installed, else the download */
  mb: number
  picture: string
  source?: string
  folder?: string
  request: ImportRequest
  install: () => Promise<string>
  remove: () => Promise<void>
}

const helperCards = computed((): HelperCard[] => {
  const cards: HelperCard[] = helpers.value.map((h) => ({
    key: h.id, name: h.name, group: h.group, description: h.description, installed: h.installed, required: h.required,
    mb: h.installed ? h.diskMb : h.sizeMb, picture: helperPicture(h.preview), source: `https://huggingface.co/${h.repo}`,
    folder: h.installed ? h.folder : undefined, request: { source: 'helper', ref: h.id },
    install: () => window.vk.helpers.install(h.id), remove: () => window.vk.helpers.remove(h.id),
  }))
  for (const tl of tools.value.installed) {
    const r = tools.value.recommended.find((x) => x.id === tl.recommended)
    cards.push({
      // i18n-ok
      key: tl.folder, name: tl.name, group: 'Photo tools', description: tl.description, installed: true, required: false,
      mb: r?.sizeMb ?? 0, picture: helperPicture(`tool_${tl.task}`), source: tl.sourceUrl, folder: tl.folder,
      request: { source: 'tool', ref: tl.recommended ?? tl.folder },
      install: () => Promise.resolve(''), remove: () => window.vk.tools.remove(tl.folder),
    })
  }
  for (const r of tools.value.recommended.filter((x) => !x.installed)) {
    cards.push({
      // i18n-ok
      key: r.id, name: r.name, group: 'Photo tools', description: r.description, installed: false, required: false,
      mb: r.sizeMb, picture: helperPicture(`tool_${r.task}`), source: r.sourceUrl, request: { source: 'tool', ref: r.id },
      install: () => window.vk.tools.install(r.id), remove: () => Promise.resolve(),
    })
  }
  const words = query.value.toLowerCase().split(/\s+/).filter(Boolean)
  return cards
    .filter((c) => words.every((w) => `${c.name} ${c.group} ${helperGroup(c.group)} ${c.description}`.toLowerCase().includes(w)))
    .sort((a, b) => HELPER_GROUPS.indexOf(a.group) - HELPER_GROUPS.indexOf(b.group) || Number(b.installed) - Number(a.installed))
})
const helpersShown = computed(() => (kind.value === 'all' || kind.value === 'helper' ? helperCards.value : []))
const helpersInstalled = computed(() => helperCards.value.filter((c) => c.installed).length)
const helperJob = (c: HelperCard): ImportJob | undefined => {
  const job = imports.of(c.request)
  return job && (job.state === 'waiting' || job.state === 'running' || job.state === 'failed') ? job : undefined
}
const mbText = (mb: number): string => (mb >= 1024 ? `${num(mb / 1024, 1)} GB` : `${mb} MB`)

async function installHelper(c: HelperCard): Promise<void> {
  removeError.value = ''
  try {
    await c.install()
  } catch (err) {
    removeError.value = cleanError(err)
  }
}

async function removeHelper(c: HelperCard): Promise<void> {
  if (!confirm(t('models.helpers.confirmRemove', { name: c.name }))) return
  removeError.value = ''
  try {
    await c.remove()
  } catch (err) {
    removeError.value = cleanError(err)
  }
  await loadHelpers()
}

async function remove(a: Asset): Promise<void> {
  if (!confirm(t(a.type === 'model' ? 'models.installed.confirmRemoveModel' : 'models.installed.confirmRemoveLora', { name: a.title }))) return
  removeError.value = ''
  try {
    await window.vk.assets.remove(a.id)
  } catch (err) {
    removeError.value = cleanError(err)
  }
  await assets.refresh()
}

// a model imported on another Mac and copied here does not run: imported again from its source, or removed
function foreignText(a: Asset): string {
  const f = a.meta.foreignMac
  if (!f) return ''
  const why = f.ramGb ? t('models.installed.foreignWhyRam', { gb: f.ramGb }) : t('models.installed.foreignWhy')
  return `${why} ${f.canReimport ? t('models.installed.foreignReimport') : t('models.installed.foreignNoFileHint')}`
}
const reimportingId = ref('')
async function reimport(a: Asset): Promise<void> {
  if (!confirm(t('models.installed.confirmReimport', { name: a.title }))) return
  removeError.value = ''
  reimportingId.value = a.id
  try {
    await window.vk.assets.reimport(a.id)
  } catch (err) {
    removeError.value = cleanError(err)
  } finally {
    reimportingId.value = ''
  }
  await assets.refresh()
}

// a name for the app only: folder and files keep theirs
const renamingId = ref('')
const newTitle = ref('')
const titleInput = ref<HTMLInputElement[]>([])

function startRename(a: Asset): void {
  renamingId.value = a.id
  newTitle.value = a.title
  removeError.value = ''
  void nextTick(() => titleInput.value[0]?.select())
}

async function rename(a: Asset): Promise<void> {
  try {
    await window.vk.assets.rename(a.id, newTitle.value)
    await assets.refresh()
    renamingId.value = ''
  } catch (err) {
    removeError.value = cleanError(err)
  }
}

const sourcePage = (a: Asset): string | undefined => {
  if (a.source?.type === 'hf' && a.source.ref) return `https://huggingface.co/${a.source.ref}`
  if (a.source?.type === 'civitai' && /^https:\/\//.test(a.source.ref)) return a.source.ref
  return undefined
}

// LoRAs online that fit a model (or, without one, the base of the first installed model); models made from that base
const finder = ref<{ base: string; model?: string; kind: FindKind; key: number }>()
let finderKey = 0
const findLoras = (a?: Asset, kind: FindKind = 'lora'): void => {
  const base = a ? baseOfAsset(a) : assets.models.map(baseOfAsset).find(Boolean)
  // a new key each time: the finder opens afresh, for this model's base
  // models without a model of one's own: all of them, the search words narrow it
  finder.value = { base: kind === 'model' && !a ? 'all' : base?.id ?? 'sdxl', model: a?.title, kind, key: ++finderKey }
}

// ------------------------------------------------------------------ recommended
const groups = computed(() => GROUPS
  .filter((g) => g.id !== 'nsfw' || settings.values.allowExplicit)
  .map((g) => ({
    ...g,
    models: CURATED.filter((m) => m.group === g.id).map((m) => ({ m, installed: !!installedAs(m, assets.all), job: jobOf(m), tokenMissing: tokenMissing(m) })),
  })))

function tokenMissing(m: CuratedModel): string {
  if (m.needs_token === 'hf' && !tokens.hf) return t('models.recommended.needsHfToken')
  if (m.needs_token === 'civitai' && !tokens.civitai) return t('models.recommended.needsCivitaiToken')
  return ''
}

function jobOf(m: CuratedModel): ImportJob | undefined {
  const job = imports.of(importRequest(m))
  return job && job.state !== 'done' ? job : undefined
}

const installError = ref('')

async function install(m: CuratedModel): Promise<void> {
  installError.value = ''
  try {
    await imports.add(importRequest(m), m.title)
  } catch (err) {
    installError.value = cleanError(err)
  }
}

// ------------------------------------------------------------------ add
type Source = ImportRequest['source']
const SOURCES: { id: Source; title: () => string; hint: PlainKey; placeholder: PlainKey }[] = [
  { id: 'hf', title: () => 'Hugging Face', hint: 'models.add.hfHint', placeholder: 'models.add.hfPlaceholder' },
  { id: 'civitai', title: () => 'Civitai', hint: 'models.add.civitaiHint', placeholder: 'models.add.civitaiPlaceholder' },
  { id: 'file', title: () => t('models.add.file'), hint: 'models.add.fileHint', placeholder: 'models.add.filePlaceholder' },
  { id: 'dir', title: () => t('models.add.folder'), hint: 'models.add.dirHint', placeholder: 'models.add.dirPlaceholder' },
]
const add = reactive<{ source: Source; ref: string; file: string; name: string; quant: NonNullable<ImportRequest['quant']> }>(
  { source: 'hf', ref: '', file: '', name: '', quant: 'auto' })
const info = ref<ImportInfo>()
const addError = ref('')
const checking = ref(false)
const request = (): ImportRequest => ({
  source: add.source, ref: add.ref.trim(), file: add.source === 'hf' ? add.file.trim() || undefined : undefined,
  name: add.name.trim() || undefined, quant: add.quant,
})

function reset(): void {
  info.value = undefined
  addError.value = ''
}

// a repo without diffusers layout: the importer names its model files ("Pick one of its model files: a.gguf (4.3 GB), …")
const repoFiles = computed(() => {
  // i18n-ok
  const list = addError.value.split('Pick one of its model files: ')[1]
  return list ? list.replace(/ and \d+ more$/, '').split(', ').map((f) => f.replace(/ \([\d.]+ GB\)$/, '')) : []
})

function pickFile(file: string): void {
  add.file = file
  void check()
}

async function choose(): Promise<void> {
  const chosen = await window.vk.files.choose(add.source === 'dir' ? 'folder' : 'model')
  if (chosen) {
    add.ref = chosen
    reset()
  }
}

// only the answer to the latest check counts (an earlier one can arrive later)
let checkGen = 0
async function check(): Promise<void> {
  reset()
  const mine = ++checkGen
  checking.value = true
  try {
    const found = await window.vk.imports.inspect(request())
    if (mine === checkGen) info.value = found
  } catch (err) {
    if (mine === checkGen) addError.value = cleanError(err)
  } finally {
    if (mine === checkGen) checking.value = false
  }
}

async function startImport(force = false): Promise<void> {
  try {
    await imports.add({ ...request(), force }, add.name.trim() || add.file.trim().split('/').pop() || add.ref.trim().split('/').filter(Boolean).pop() || add.ref)
  } catch (err) {
    addError.value = cleanError(err)
    return
  }
  add.ref = add.file = add.name = ''
  reset()
}
</script>

<template>
  <PageFrame :title="t('models.title')" :subtitle="t('models.subtitle', { models: assets.models.length, loras: assets.loras.length })">
    <template #actions>
      <div class="tabs">
        <button v-for="tb in TABS" :key="tb.id" :class="{ on: tab === tb.id }" @click="tab = tb.id">{{ t(tb.title) }}</button>
      </div>
    </template>

    <div class="wrap" :class="{ wide: tab === 'installed' }">
      <p v-if="!diffusersInstalled" class="note dim">
        <CircleAlert :size="14" /> {{ t('models.diffusersMissing') }}
        <RouterLink to="/settings">{{ t('models.diffusersInstall') }}</RouterLink>
      </p>

      <section v-if="imports.jobs.length" class="card imports">
        <header>
          <h2>{{ t('models.imports.title') }}</h2>
          <button class="btn small ghost" :disabled="imports.jobs.length === imports.open.length" @click="imports.clearFinished()">{{ t('models.imports.clearFinished') }}</button>
        </header>
        <div v-for="j in imports.jobs" :key="j.id" class="import" :class="j.state">
          <div class="grow">
            <strong>{{ j.title }}</strong>
            <template v-if="j.state === 'running'">
              <div class="bar" :class="{ unknown: j.percent < 0 }"><i :style="j.percent >= 0 ? { width: j.percent + '%' } : {}" /></div>
              <p class="dim">{{ j.stage }}<template v-if="j.percent >= 0"> · {{ Math.round(j.percent) }} %</template></p>
            </template>
            <p v-else-if="j.state === 'failed'" class="error selectable">{{ j.error }}</p>
            <p v-else class="dim">{{ { waiting: t('models.imports.waiting'), done: t('models.imports.done'), cancelled: t('models.imports.cancelled') }[j.state] }}</p>
          </div>
          <button class="btn small" :class="{ danger: j.state === 'running' }" @click="imports.cancel(j.id)">
            <component :is="j.state === 'running' ? Square : X" :size="11" /> {{ j.state === 'running' ? t('common.cancel') : t('common.remove') }}
          </button>
        </div>
      </section>

      <!-- installed -->
      <template v-if="tab === 'installed'">
        <div class="filters">
          <div class="tabs">
            <button :class="{ on: kind === 'all' }" @click="kind = 'all'">{{ t('models.installed.all') }}</button>
            <button :class="{ on: kind === 'model' }" @click="kind = 'model'">{{ t('models.installed.models') }}</button>
            <button :class="{ on: kind === 'lora' }" @click="kind = 'lora'">{{ t('models.installed.loras') }}</button>
            <button v-if="!remote" :class="{ on: kind === 'helper' }" @click="kind = 'helper'">{{ t('models.installed.helpers') }}</button>
          </div>
          <span class="spacer" />
          <button class="btn" :title="t('models.installed.findModelsHint')" @click="findLoras(undefined, 'model')"><Boxes :size="14" /> {{ t('models.installed.findModels') }}</button>
          <button class="btn" :title="t('models.installed.findLorasHint')" @click="findLoras()"><Layers :size="14" /> {{ t('models.installed.findLoras') }}</button>
          <label class="search"><Search :size="14" class="dim" /><input v-model="query" type="search" :placeholder="t('models.installed.search')" spellcheck="false" /></label>
        </div>
        <p v-if="removeError" class="error">{{ removeError }}</p>
        <p v-if="!shown.length && kind !== 'helper' && !helpersShown.length" class="dim">{{ assets.all.length ? t('models.installed.nothingFound') : t('models.installed.nothingYet') }}</p>
        <section v-for="sec in kind === 'helper' ? [] : sections" :key="sec.id" class="kind">
          <h2>{{ t(sec.title) }} <span class="dim">{{ sec.assets.length }}</span></h2>
          <div class="cards">
            <article v-for="a in sec.assets" :key="a.id" class="card asset" :class="sec.id">
              <div class="picture">
                <img v-if="a.preview" :src="url(a.preview)" loading="lazy" draggable="false" />
                <span v-else class="dim">{{ a.type === 'lora' ? 'LoRA' : a.meta.family.toUpperCase() }}</span>
              </div>
              <div class="body">
                <div v-if="renamingId === a.id" class="rename">
                  <input
                    ref="titleInput" v-model="newTitle" type="text" spellcheck="false" :placeholder="a.name" maxlength="120"
                    @keyup.enter="rename(a)" @keyup.esc="renamingId = ''"
                  />
                  <button class="btn small" @click="rename(a)">{{ t('models.installed.save') }}</button>
                  <button class="btn small ghost" :title="t('common.cancel')" @click="renamingId = ''"><X :size="12" /></button>
                </div>
                <strong v-else class="selectable">{{ a.title }}</strong>
                <p v-if="a.title !== a.name && renamingId !== a.id" class="dim selectable">{{ t('models.installed.folder', { name: a.name }) }}</p>
                <p class="dim">
                  {{ a.type === 'lora' ? t('models.installed.loraFor', { family: familyTitle(a.meta.family, a.meta.variant) }) : a.meta.label }}<template v-if="a.type === 'model' && a.meta.minRamGb"> · {{ t('models.installed.ram', { gb: a.meta.minRamGb }) }}</template>
                </p>
                <p v-if="a.meta.unsupported" class="dim">{{ a.meta.unsupported }}</p>
                <p v-if="a.meta.foreignMac" class="intro-line">
                  {{ a.meta.foreignMac.canReimport ? t('models.installed.foreign') : t('models.installed.foreignNoFile') }}
                  <HintBadge notice start :text="foreignText(a)" />
                </p>
                <p v-if="a.meta.triggerWords?.length" class="dim selectable">{{ t('models.installed.trigger', { words: a.meta.triggerWords.join(', ') }) }}</p>
                <p v-if="exporting?.id === a.id" class="dim">{{ exporting.stage }}<template v-if="exporting.percent >= 0"> · {{ exporting.percent }} %</template></p>
                <p v-else-if="exported?.id === a.id" :class="exported.error ? 'error selectable' : 'dim selectable'">{{ exported.text }}</p>
                <div class="row">
                  <span v-if="a.meta.kind === 'video'" class="tag">{{ t('models.installed.video') }}</span>
                  <span v-if="a.meta.runtime === 'comfyui'" class="tag">ComfyUI</span>
                  <span class="spacer" />
                  <template v-if="a.meta.foreignMac && !remote">
                    <button v-if="a.meta.foreignMac.canReimport" class="btn small" :disabled="reimportingId === a.id" @click="reimport(a)">
                      <Download :size="12" /> {{ t('models.installed.importAgain') }}
                    </button>
                    <button class="btn small ghost danger" @click="remove(a)"><Trash2 :size="12" /> {{ t('common.remove') }}</button>
                  </template>
                  <!-- a model of another Mac gets only its two ways out: the rest does not fit the card and does not help -->
                  <template v-else>
                    <button v-if="a.type === 'model' && baseOfAsset(a)" class="btn small ghost" :title="t('models.installed.lorasHint')" @click="findLoras(a)">
                      <Layers :size="12" /> {{ t('models.installed.lorasButton') }}
                    </button>
                    <button v-if="sourcePage(a)" class="btn small ghost" :title="t('models.installed.sourceHint')" @click="openLink(sourcePage(a))"><ExternalLink :size="12" /></button>
                    <template v-if="!remote">
                      <button
                        v-if="a.type === 'model' && a.meta.exportable" class="btn small ghost" :disabled="!!exporting"
                        :aria-label="t('models.installed.exportHint')" @click="exportSingle(a)"
                      ><FileDown :size="12" /></button>
                      <button class="btn small ghost" :title="t('models.installed.renameHint')" @click="startRename(a)"><Pencil :size="12" /></button>
                      <button class="btn small ghost" :title="t('models.installed.showInFinder')" @click="reveal(a.folder)"><FolderSearch :size="12" /></button>
                      <button class="btn small ghost danger" :title="t('models.installed.moveToTrash')" @click="remove(a)"><Trash2 :size="12" /></button>
                    </template>
                  </template>
                </div>
              </div>
            </article>
          </div>
        </section>
        <section v-if="helpersShown.length" class="kind">
          <h2>
            {{ t('models.helpers.title') }} <span class="dim">{{ t('models.helpers.count', { installed: helpersInstalled, total: helperCards.length }) }}</span>
            <HintBadge start :text="t('models.helpers.hint')" />
          </h2>
          <div class="cards">
            <article v-for="c in helpersShown" :key="c.key" class="card asset helper" :class="{ missing: !c.installed }">
              <div class="picture">
                <img v-if="c.picture" :src="c.picture" loading="lazy" draggable="false" />
                <span v-else class="dim">{{ helperGroup(c.group).toUpperCase() }}</span>
              </div>
              <div class="body">
                <strong class="selectable">{{ c.name }}</strong>
                <p class="dim">{{ c.description }}</p>
                <p class="dim">{{ helperGroup(c.group) }} · {{ c.installed ? mbText(c.mb) : t('models.helpers.toDownload', { size: mbText(c.mb) }) }}</p>
                <p v-if="helperJob(c)?.state === 'failed'" class="error selectable">{{ helperJob(c)?.error }}</p>
                <div class="row">
                  <span v-if="c.required" class="tag">{{ t('models.helpers.required') }}</span>
                  <span class="spacer" />
                  <span v-if="helperJob(c) && helperJob(c)?.state !== 'failed'" class="dim">
                    {{ (helperJob(c)?.percent ?? -1) >= 0 ? `${Math.round(helperJob(c)!.percent)} %` : t('models.helpers.downloading') }}
                  </span>
                  <button v-else-if="!c.installed" class="btn small download" @click="installHelper(c)"><Download :size="12" /> {{ t('models.helpers.download') }}</button>
                  <button v-if="c.source" class="btn small ghost" :title="t('models.helpers.sourceHint')" @click="openLink(c.source)"><ExternalLink :size="12" /></button>
                  <button v-if="c.folder" class="btn small ghost" :title="t('models.installed.showInFinder')" @click="reveal(c.folder)"><FolderSearch :size="12" /></button>
                  <button v-if="c.installed && !c.required" class="btn small ghost danger" :title="t('models.installed.moveToTrash')" @click="removeHelper(c)"><Trash2 :size="12" /></button>
                </div>
              </div>
            </article>
          </div>
        </section>
      </template>

      <!-- recommended -->
      <template v-else-if="tab === 'recommended'">
        <p class="dim intro-line">
          {{ t('models.recommended.intro', { mac: macName || `${ramGb} GB` }) }}
          <HintBadge start :text="t('models.recommended.introHint')" />
        </p>
        <p v-if="installError" class="error selectable">{{ installError }}</p>
        <section v-for="g in groups" :key="g.id">
          <h2>{{ g.title }}</h2>
          <div class="list card">
            <div v-for="{ m, installed, job, tokenMissing: missing } in g.models" :key="m.id" class="curated">
              <div class="grow">
                <div class="name">
                  <strong>{{ m.title }}</strong>
                  <span class="tag">{{ m.family }}</span>
                  <span v-if="memoryFit(m, ramGb) === 'streamed'" class="tag">{{ t('models.recommended.streamedTag', { gb: m.min_ram_gb_streamed ?? '' }) }}</span>
                  <HintBadge v-if="memoryFit(m, ramGb) === 'streamed'" notice start :text="t('models.recommended.streamedHint')" />
                  <span v-else class="tag" :class="{ warn: memoryFit(m, ramGb) === 'none' }">{{ t('models.recommended.ramTag', { gb: m.min_ram_gb }) }}</span>
                  <span class="tag">{{ t('models.recommended.downloadTag', { gb: m.download_gb }) }}</span>
                </div>
                <p class="dim">{{ curatedDescription(m.id, m.description) }}</p>
                <p v-if="memoryFit(m, ramGb) === 'none'" class="warn-text">{{ t('models.recommended.tooLittleMemory') }}</p>
                <p v-if="!installed && missing" class="warn-text">{{ missing }}</p>
                <p v-if="!installed && m.gated" class="dim">
                  {{ t('models.recommended.gatedBefore') }}
                  <a href="#" @click.prevent="openLink(licencePage(m))">{{ t('models.recommended.gatedLink') }}</a> {{ t('models.recommended.gatedAfter') }}
                </p>
                <template v-if="job">
                  <template v-if="job.state === 'running'">
                    <div class="bar" :class="{ unknown: job.percent < 0 }"><i :style="job.percent >= 0 ? { width: job.percent + '%' } : {}" /></div>
                    <p class="dim">{{ job.stage }}</p>
                  </template>
                  <p v-else-if="job.state === 'failed'" class="error selectable">{{ job.error }}</p>
                  <p v-else-if="job.state === 'waiting'" class="dim">{{ t('models.recommended.waiting') }}</p>
                </template>
              </div>
              <span v-if="installed" class="installed"><Check :size="14" /> {{ t('models.recommended.installed') }}</span>
              <button v-else-if="job && (job.state === 'running' || job.state === 'waiting')" class="btn danger" @click="imports.cancel(job.id)">
                <Square :size="12" /> {{ t('common.cancel') }}
              </button>
              <button v-else class="btn primary" :disabled="!!missing" @click="install(m)">
                <Download :size="14" /> {{ t('models.recommended.install') }}
              </button>
            </div>
          </div>
        </section>
      </template>

      <!-- add -->
      <template v-else>
        <section class="card form">
          <div class="tabs">
            <button v-for="s in SOURCES" :key="s.id" :class="{ on: add.source === s.id }" @click="(add.source = s.id), (add.ref = ''), reset()">{{ s.title() }}</button>
          </div>
          <p class="dim intro-line">
            {{ SOURCES.find((s) => s.id === add.source)!.title() }}
            <HintBadge start :text="t(SOURCES.find((s) => s.id === add.source)!.hint)" />
          </p>
          <div class="line">
            <input v-model="add.ref" type="text" :placeholder="t(SOURCES.find((s) => s.id === add.source)!.placeholder)" spellcheck="false" @input="reset" />
            <button v-if="add.source === 'file' || add.source === 'dir'" class="btn" @click="choose"><FolderOpen :size="14" /> {{ t('models.add.choose') }}</button>
          </div>
          <input v-if="add.source === 'hf'" v-model="add.file" type="text" :placeholder="t('models.add.fileInRepo')" spellcheck="false" @input="reset" />
          <div class="line">
            <input v-model="add.name" type="text" :placeholder="t('models.add.name')" spellcheck="false" />
            <select v-model="add.quant" :title="t('models.add.quantHint')" @change="reset">
              <option value="auto">{{ t('models.add.compressWhenNeeded') }}</option>
              <option value="none">{{ t('models.add.doNotCompress') }}</option>
              <option value="q8">{{ t('models.add.bit8') }}</option>
              <option value="q4">{{ t('models.add.bit4') }}</option>
            </select>
          </div>
          <div class="line">
            <button class="btn" :disabled="!add.ref.trim() || checking" @click="check">{{ checking ? t('models.add.checking') : t('models.add.check') }}</button>
            <button class="btn primary" :disabled="!add.ref.trim() || checking || (info && info.fits === false)" @click="startImport()">
              <Download :size="14" /> {{ add.source === 'dir' || add.source === 'file' ? t('models.add.import') : t('models.add.download') }}
            </button>
          </div>
          <p v-if="addError" class="error selectable">{{ addError }}</p>
          <div v-if="repoFiles.length" class="picks">
            <button v-for="f in repoFiles" :key="f" class="btn small" @click="pickFile(f)">{{ f }}</button>
          </div>
          <div v-if="info" class="info">
            <p>
              <strong>{{ info.label }}</strong>
              <span class="tag">{{ info.kind === 'lora' ? 'LoRA' : t('models.add.model') }}</span>
              <span v-if="info.downloadGb" class="tag">{{ t('models.add.downloadTag', { gb: info.downloadGb }) }}</span>
              <template v-if="info.minRamGb && info.streamed">
                <span class="tag">{{ t('models.recommended.streamedTag', { gb: info.minRamGb }) }}</span>
                <HintBadge notice start :text="t('models.recommended.streamedHint')" />
              </template>
              <span v-else-if="info.minRamGb" class="tag" :class="{ warn: info.fits === false }">{{ t('models.add.ramTag', { gb: info.minRamGb }) }}</span>
              <span v-if="info.quant" class="tag">{{ t('models.add.compressed', { quant: info.quant }) }}</span>
              <span v-if="info.inPlace" class="tag">{{ t('models.add.inPlace') }}</span>
              <HintBadge v-if="info.inPlace" start :text="t('models.add.inPlaceHint')" />
              <span v-if="info.gated" class="tag warn">{{ t('models.add.gated') }}</span>
              <HintBadge v-if="info.gated" start :text="t('models.add.gatedHint')" />
            </p>
            <p v-if="info.triggerWords?.length" class="dim">{{ t('models.add.triggerWords', { words: info.triggerWords.join(', ') }) }}</p>
            <p v-if="info.note" class="dim intro-line">{{ t('models.add.note') }} <HintBadge notice start :text="info.note" /></p>
            <p v-if="info.fits === false" class="warn-text">
              {{ t('models.add.tooLarge') }}
              <button class="btn small" @click="startImport(true)">{{ t('models.add.importAnyway') }}</button>
            </p>
          </div>
        </section>
      </template>
    </div>
    <LoraFinder v-if="finder" :key="finder.key" :base="finder.base" :model="finder.model" :kind="finder.kind" @close="finder = undefined" />
  </PageFrame>
</template>

<style scoped>
.wrap {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 18px;
  max-width: 1200px;
}

/* the installed models, LoRAs and helpers: up to ten cards side by side on a wide window */
.wrap.wide {
  max-width: calc(10 * 230px + 9 * 12px);
}

section {
  display: grid;
  gap: 8px;
}

.note {
  display: flex;
  align-items: center;
  gap: 6px;
}

a {
  color: var(--accent);
}

.imports header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px 10px 16px;
}

.import,
.curated {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px 10px 16px;
  border-top: 1px solid var(--line);
}

.curated:first-child {
  border-top: 0;
}

.grow {
  flex: 1;
  min-width: 0;
}

.bar {
  margin: 6px 0 4px;
  max-width: 360px;
}

.warn-text {
  color: var(--accent);
}

/* the kind tabs, Find LoRAs and the search stay at the top while the cards scroll under them (-24px: the work
   area's own padding, so that nothing shows above the bar) */
.filters {
  display: flex;
  align-items: center;
  gap: 8px;
  position: sticky;
  top: -24px;
  z-index: 5;
  margin: -10px 0 0;
  padding: 10px 0;
  background: var(--bg);
}

.search input {
  width: 200px;
}

/* cards of one fixed size (230px, the smallest they had): a wider window shows more of them side by side, never
   larger ones */
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, 230px);
  gap: 12px;
}

.asset {
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.kind {
  display: grid;
  gap: 10px;
}

/* the kind's title and count stay right below the filter bar while its cards scroll (26px: the bar's 50px less the
   work area's 24px padding); the next kind's title pushes it away */
.kind h2 {
  position: sticky;
  top: 26px;
  z-index: 4;
  margin: 0;
  padding: 4px 0 6px;
  background: var(--bg);
}

.kind h2 .dim {
  font-weight: 400;
}

/* the badge after the count: some room between the text and it */
.kind h2 .hint {
  margin-left: 8px;
}

/* one tint per kind, mixed into the theme's surface so it works light and dark */
.asset.image {
  background: color-mix(in srgb, var(--surface) 88%, #4f8cff);
}

.asset.video {
  background: color-mix(in srgb, var(--surface) 88%, #a66bff);
}

.asset.lora {
  background: color-mix(in srgb, var(--surface) 88%, #3fbf8a);
}

.btn.download {
  border-color: var(--accent);
}

.asset.helper {
  background: color-mix(in srgb, var(--surface) 86%, #e8a33d);
}

/* not downloaded yet: shown, but quieter */
.asset.helper.missing .picture img {
  filter: grayscale(0.7);
  opacity: 0.7;
}

.picture {
  aspect-ratio: 4 / 3;
  background: var(--surface-2);
  display: grid;
  place-items: center;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.picture img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* the buttons always at the foot of the card, however much text is above them */
.body {
  padding: 10px 8px 6px 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1;
}

.body strong {
  word-break: break-word;
}

.row {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: auto;
  padding-top: 4px;
}

.spacer {
  flex: 1;
}

.name {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.tag {
  padding: 1px 7px;
  border-radius: 9px;
  background: var(--surface-2);
  font-size: 11px;
  white-space: nowrap;
}

.tag.warn {
  color: var(--accent);
}

.installed {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--ok);
  white-space: nowrap;
}

.form {
  padding: 16px;
  gap: 10px;
  max-width: 640px;
}

.line {
  display: flex;
  gap: 8px;
}

.picks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.info {
  display: grid;
  gap: 4px;
  padding-top: 8px;
  border-top: 1px solid var(--line);
}

.info p {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

input[type='text'],
select {
  flex: 1;
}

.rename {
  display: flex;
  gap: 6px;
  align-items: center;
}

.rename input {
  flex: 1;
  min-width: 0;
  height: 28px;
}

/* a short line with the details behind an (!) */
.intro-line {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* a phone (remote web UI): the filter bar wraps, two cards fill a row */
@media (max-width: 860px) {
  .filters {
    flex-wrap: wrap;
  }

  .cards {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  }

  .asset .row {
    flex-wrap: wrap;
  }
}
</style>
