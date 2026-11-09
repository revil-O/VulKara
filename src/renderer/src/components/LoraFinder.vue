<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// LoRAs that fit a model, or models made from a base, from Civitai or Hugging Face, installed through the import queue.
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Check, Download, ExternalLink, Search, Square, X } from '@lucide/vue'
import HintBadge from './HintBadge.vue'
import { useAssetsStore } from '../stores/assets'
import { useImportsStore } from '../stores/imports'
import { cleanError } from '../stores/runtimes'
import { useSettingsStore } from '../stores/settings'
import { openLink } from '../util/links'
import { BASE_GROUPS, isInstalled, loraBase, type FindKind, type LoraHit } from '@shared/lora_bases'
import type { ImportInfo, ImportJob, ImportRequest } from '@shared/api'
import { num, t } from '../i18n'

const props = withDefaults(defineProps<{ base: string; model?: string; kind?: FindKind }>(), { kind: 'lora' })
const emit = defineEmits<{ close: [] }>()

const assets = useAssetsStore()
const imports = useImportsStore()
const settings = useSettingsStore()

const dialog = ref<HTMLDialogElement>()
const base = ref(props.base)
const source = ref<'civitai' | 'hf'>('civitai')
const query = ref('')
const hits = ref<LoraHit[]>([])
const cursor = ref<string>()
const loading = ref(false)
const error = ref('')
const installError = ref('')
const tokens = reactive({ hf: false, civitai: false })
/** the file chosen for a Hugging Face repository with several */
const chosen = reactive<Record<string, string>>({})
/** preview pictures: data URL, '' when there is none */
const thumbs = reactive<Record<string, string>>({})
/** models: what the import's check says about the memory */
const plans = reactive<Record<string, ImportInfo>>({})
/** models: why the import's check refused one (a format this Mac can not compute, an unknown model type …) */
const refused = reactive<Record<string, string>>({})
/** adult previews the user chose to see */
const revealed = reactive(new Set<string>())

const title = computed(() => props.kind === 'model' ? t('lora.finder.modelsTitle')
  : props.model ? t('lora.finder.titleFor', { model: props.model }) : t('lora.finder.title'))
const baseLabel = computed(() => (base.value === 'all' ? t('lora.finder.allBases') : loraBase(base.value)?.label ?? base.value))
const intro = computed(() => base.value === 'all'
  ? t(props.kind === 'model' ? 'lora.finder.modelsIntroAll' : 'lora.finder.introAll')
  : t(props.kind === 'model' ? 'lora.finder.modelsIntro' : 'lora.finder.intro', { base: baseLabel.value }))
let run = 0

onMounted(async () => {
  dialog.value?.showModal()
  const [hf, civitai] = await Promise.all([window.vk.tokens.has('huggingface'), window.vk.tokens.has('civitai'), settings.load(), imports.start()])
  Object.assign(tokens, { hf, civitai })
  void search()
})

watch([base, source], () => void search())

async function search(more = false): Promise<void> {
  const id = ++run
  loading.value = true
  error.value = ''
  if (!more) {
    hits.value = []
    cursor.value = undefined
  }
  try {
    const page = await window.vk.loras.search({ base: base.value, source: source.value, kind: props.kind, query: query.value, cursor: more ? cursor.value : undefined })
    if (id !== run) return
    const known = new Set(hits.value.map(key))
    hits.value = [...hits.value, ...page.hits.filter((h) => !known.has(key(h)))]
    cursor.value = page.cursor
    for (const h of page.hits) if (h.file && !(h.ref in chosen)) chosen[h.ref] = h.file
    void loadThumbs(page.hits, id)
    if (props.kind === 'model') void loadPlans(page.hits, id)
  } catch (err) {
    if (id === run) error.value = cleanError(err)
  } finally {
    if (id === run) loading.value = false
  }
}

const key = (h: LoraHit): string => `${h.source}:${h.ref}`

// four at a time, so the first ones show soon
async function loadThumbs(list: LoraHit[], id: number): Promise<void> {
  const todo = list.filter((h) => h.previewUrl && !(h.previewUrl in thumbs))
  const worker = async (): Promise<void> => {
    for (let h = todo.shift(); h && id === run; h = todo.shift()) {
      const url = h.previewUrl!
      thumbs[url] = (await window.vk.loras.thumb(url).catch(() => undefined)) ?? ''
    }
  }
  await Promise.all([worker(), worker(), worker(), worker()])
}

// the import's dry run for each model, two at a time (well under a second for Civitai, a few for a repository), so the
// cards tell the memory a model needs and whether it runs streamed from the SSD.
// shortcut: checked for the file first offered; another file chosen on the card is not checked again
async function loadPlans(list: LoraHit[], id: number): Promise<void> {
  const todo = list.filter((h) => !(key(h) in plans) && !(key(h) in refused) && !tokenMissing(h))
  const worker = async (): Promise<void> => {
    for (let h = todo.shift(); h && id === run; h = todo.shift()) {
      try {
        plans[key(h)] = await window.vk.imports.inspect(requestOf(h))
      } catch (err) {
        refused[key(h)] = cleanError(err)
      }
    }
  }
  await Promise.all([worker(), worker()])
}

const fileOf = (h: LoraHit): string | undefined => chosen[h.ref] ?? h.file
const requestOf = (h: LoraHit): ImportRequest => h.source === 'hf' ? { source: 'hf', ref: h.ref, file: fileOf(h) } : { source: 'civitai', ref: h.ref }
const installed = (h: LoraHit): boolean => isInstalled({ source: h.source, ref: h.ref, file: fileOf(h) }, assets.all, props.kind)

function jobOf(h: LoraHit): ImportJob | undefined {
  const job = imports.of(requestOf(h))
  return job && job.state !== 'done' ? job : undefined
}

function tokenMissing(h: LoraHit): string {
  if (!h.needsToken) return ''
  if (h.source === 'civitai' && !tokens.civitai) return t('lora.finder.needsCivitaiToken')
  if (h.source === 'hf' && !tokens.hf) return t('lora.finder.needsHfToken')
  return ''
}

async function install(h: LoraHit): Promise<void> {
  installError.value = ''
  try {
    await imports.add(requestOf(h), h.title)
  } catch (err) {
    installError.value = cleanError(err)
  }
}

function count(n: number | undefined): string {
  if (n === undefined) return ''
  return n >= 1e6 ? `${num(n / 1e6, 1)}M` : n >= 1e3 ? `${num(n / 1e3, n >= 1e4 ? 0 : 1)}k` : String(n)
}

// the format names as the sites write them, with what they mean on a Mac
const FORMATS = [
  ['bf16 · fp16', 'lora.finder.formats.f16'], ['fp8 · fp8 scaled', 'lora.finder.formats.fp8'],
  ['GGUF (Q8_0, Q5, Q4 …)', 'lora.finder.formats.gguf'], ['fp32', 'lora.finder.formats.fp32'],
  // i18n-ok: format names
  ['NF4 · int8 · int4 · nvfp4 · AWQ', 'lora.finder.formats.nvidia'], ['pruned · full', 'lora.finder.formats.pruned'],
  ['.safetensors · .ckpt · .pt', 'lora.finder.formats.pickle'],
] as const

const size = (mb: number): string => mb >= 1024 ? `${num(mb / 1024, 1)} GB` : `${mb} MB`

function close(): void {
  run++
  emit('close')
}
</script>

<template>
  <!-- @close: the browser may close a modal dialog on Escape without a cancel event; the page has to hear of it, or
       the finder stays mounted but invisible and the next "LoRAs" click shows nothing -->
  <dialog ref="dialog" class="finder" @cancel.prevent="close" @close="close" @click.self="close">
    <div class="inner">
      <header>
        <div class="grow">
          <h2>{{ title }}</h2>
          <p class="dim">{{ intro }}</p>
        </div>
        <button class="btn small ghost" :title="t('lora.finder.close')" @click="close"><X :size="14" /></button>
      </header>

      <div class="controls">
        <div class="tabs">
          <button :class="{ on: source === 'civitai' }" @click="source = 'civitai'">Civitai</button>
          <button :class="{ on: source === 'hf' }" @click="source = 'hf'">Hugging Face</button>
        </div>
        <select v-model="base" :title="kind === 'model' ? t('lora.finder.modelsBaseHint') : t('lora.finder.baseHint')">
          <option value="all">{{ t('lora.finder.allBases') }}</option>
          <optgroup v-for="g in BASE_GROUPS" :key="g.label" :label="g.label">
            <option v-for="b in g.bases" :key="b.id" :value="b.id">{{ b.label }}</option>
          </optgroup>
        </select>
        <label class="search">
          <Search :size="14" class="dim" />
          <input v-model="query" type="search" :placeholder="t('lora.finder.searchPlaceholder')" spellcheck="false" @keyup.enter="search()" @search="search()" />
        </label>
      </div>
      <p v-if="!settings.values.allowExplicit" class="dim small">
        {{ kind === 'model' ? t('lora.finder.modelsAdultsLeftOut') : t('lora.finder.adultsLeftOut') }}
      </p>
      <details v-if="kind === 'model'" class="formats">
        <summary>{{ t('lora.finder.formats.title') }}</summary>
        <dl>
          <template v-for="[name, text] in FORMATS" :key="name"><dt>{{ name }}</dt><dd>{{ t(text) }}</dd></template>
        </dl>
      </details>
      <p v-if="installError" class="error selectable">{{ installError }}</p>

      <div class="results">
        <p v-if="error" class="error selectable">{{ error }}</p>
        <p v-else-if="!loading && !hits.length" class="dim">{{ query ? t('lora.finder.nothingFoundSearch') : t('lora.finder.nothingFound') }}</p>
        <div class="grid">
          <article v-for="h in hits" :key="key(h)" class="card hit">
            <div class="picture">
              <template v-if="h.previewUrl && thumbs[h.previewUrl]">
                <img :src="thumbs[h.previewUrl]" :class="{ blurred: h.previewExplicit && !revealed.has(h.previewUrl) }" draggable="false" />
                <button v-if="h.previewExplicit && !revealed.has(h.previewUrl)" class="reveal" @click="revealed.add(h.previewUrl)">
                  {{ t('lora.finder.adultShow') }}
                </button>
              </template>
              <span v-else class="dim">{{ h.previewUrl && !(h.previewUrl in thumbs) ? '…' : kind === 'model' ? baseLabel : 'LoRA' }}</span>
            </div>
            <div class="body">
              <strong class="selectable">{{ h.title }}</strong>
              <p class="dim">
                <template v-if="h.author">{{ t('lora.finder.by', { author: h.author }) }}</template><template v-if="h.version"> · {{ h.version }}</template>
              </p>
              <p class="tags">
                <span v-if="h.baseModel" class="tag">{{ h.baseModel }}</span>
                <span v-if="h.downloads !== undefined" class="tag" :title="t('lora.finder.downloadsHint')">{{ t('lora.finder.downloads', { count: count(h.downloads) }) }}</span>
                <span v-if="h.likes" class="tag" :title="t('lora.finder.likesHint')">{{ t('lora.finder.likes', { count: count(h.likes) }) }}</span>
                <span v-if="h.sizeMb" class="tag">{{ size(h.sizeMb) }}</span>
                <span v-else-if="plans[key(h)]?.downloadGb" class="tag">{{ size(plans[key(h)]!.downloadGb * 1024) }}</span>
                <template v-if="plans[key(h)]?.minRamGb">
                  <span v-if="plans[key(h)]!.streamed" class="tag stream">
                    {{ t('models.recommended.streamedTag', { gb: plans[key(h)]!.minRamGb! }) }}
                    <HintBadge notice start :text="t('models.recommended.streamedHint')" />
                  </span>
                  <span v-else class="tag" :class="{ warn: plans[key(h)]!.fits === false }">{{ t('models.recommended.ramTag', { gb: plans[key(h)]!.minRamGb! }) }}</span>
                </template>
                <span v-if="h.nsfw" class="tag warn">{{ t('lora.finder.adult') }}</span>
                <span v-if="h.gated" class="tag">{{ t('lora.finder.licenceToAccept') }}</span>
              </p>
              <p v-if="h.triggerWords.length" class="dim selectable small">{{ t('lora.finder.trigger', { words: h.triggerWords.join(', ') }) }}</p>
              <p v-if="h.licence" class="dim small">{{ h.licence }}</p>
              <select v-if="h.files && h.files.length > 1" v-model="chosen[h.ref]" class="file" :title="t('lora.finder.fileHint')">
                <option v-for="f in h.files" :key="f" :value="f">{{ f }}</option>
              </select>
              <p v-if="!installed(h) && plans[key(h)]?.fits === false" class="warn-text small">{{ t('models.recommended.tooLittleMemory') }}</p>
              <p v-if="!installed(h) && refused[key(h)]" class="warn-text small selectable clip">{{ refused[key(h)] }}</p>
              <p v-if="!installed(h) && tokenMissing(h)" class="warn-text small">{{ tokenMissing(h) }}</p>
              <p v-if="!installed(h) && h.gated" class="dim small">
                {{ t('lora.finder.gatedBefore') }} <a href="#" @click.prevent="openLink(h.page)">{{ t('lora.finder.gatedLink') }}</a> {{ t('lora.finder.gatedAfter') }}
              </p>
              <template v-if="jobOf(h)">
                <template v-if="jobOf(h)!.state === 'running'">
                  <div class="bar" :class="{ unknown: jobOf(h)!.percent < 0 }"><i :style="jobOf(h)!.percent >= 0 ? { width: jobOf(h)!.percent + '%' } : {}" /></div>
                  <p class="dim small">{{ jobOf(h)!.stage }}</p>
                </template>
                <p v-else-if="jobOf(h)!.state === 'failed'" class="error selectable small">{{ jobOf(h)!.error }}</p>
                <p v-else-if="jobOf(h)!.state === 'waiting'" class="dim small">{{ t('lora.finder.waiting') }}</p>
              </template>
              <div class="row">
                <span v-if="installed(h)" class="installed"><Check :size="14" /> {{ t('lora.finder.installed') }}</span>
                <button v-else-if="jobOf(h) && (jobOf(h)!.state === 'running' || jobOf(h)!.state === 'waiting')" class="btn small danger" @click="imports.cancel(jobOf(h)!.id)">
                  <Square :size="11" /> {{ t('lora.finder.cancel') }}
                </button>
                <button v-else class="btn small primary" :disabled="!!tokenMissing(h) || !!refused[key(h)]" @click="install(h)">
                  <Download :size="12" /> {{ t('lora.finder.install') }}
                </button>
                <span class="spacer" />
                <button class="btn small ghost" :title="t('lora.finder.openPage')" @click="openLink(h.page)"><ExternalLink :size="12" /></button>
              </div>
            </div>
          </article>
        </div>
        <div class="more">
          <span v-if="loading" class="dim">{{ t('lora.finder.loading') }}</span>
          <button v-else-if="cursor" class="btn" @click="search(true)">{{ t('lora.finder.loadMore') }}</button>
        </div>
      </div>
    </div>
  </dialog>
</template>

<style scoped>
.finder {
  width: min(1100px, calc(100vw - 80px));
  height: min(820px, calc(100vh - 80px));
  padding: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius-l);
  background: var(--bg);
  color: var(--text);
  box-shadow: var(--shadow);
}

.finder::backdrop {
  background: rgba(0, 0, 0, 0.45);
}

.inner {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  padding: 16px 18px;
  box-sizing: border-box;
}

header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.grow {
  flex: 1;
  min-width: 0;
}

.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.controls .search {
  flex: 1;
  min-width: 180px;
}

.controls .search input {
  flex: 1;
  min-width: 0;
}

.results {
  flex: 1;
  overflow-y: auto;
  display: grid;
  align-content: start;
  gap: 10px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.hit {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: color-mix(in srgb, var(--surface) 88%, #3fbf8a);
}

.picture {
  position: relative;
  aspect-ratio: 4 / 3;
  background: var(--surface-2);
  display: grid;
  place-items: center;
  overflow: hidden;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.picture img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.picture img.blurred {
  filter: blur(18px);
  transform: scale(1.1);
}

.reveal {
  position: absolute;
  padding: 4px 10px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
  color: var(--text);
  font-size: 12px;
}

/* the buttons always at the foot of the card */
.body {
  padding: 10px 8px 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.body strong {
  word-break: break-word;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.tag {
  padding: 1px 7px;
  border-radius: 9px;
  background: var(--surface-2);
  font-size: 11px;
  white-space: nowrap;
}

.formats {
  font-size: 12px;
}

.formats summary {
  cursor: pointer;
  color: var(--text-dim);
}

.formats dl {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 14px;
  margin: 8px 0 2px;
  max-height: 260px;
  overflow-y: auto;
}

.formats dt {
  font-weight: 600;
  white-space: nowrap;
}

.formats dd {
  margin: 0;
}

.clip {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.tag.stream {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: color-mix(in srgb, var(--surface-2) 70%, var(--accent));
}

.tag.warn,
.warn-text {
  color: var(--accent);
}

.small {
  font-size: 12px;
}

.file {
  height: 26px;
  font-size: 12px;
  max-width: 100%;
}

.bar {
  margin: 4px 0 2px;
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

.installed {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--ok);
  white-space: nowrap;
}

.more {
  display: flex;
  justify-content: center;
  padding: 6px 0 4px;
}

a {
  color: var(--accent);
}
</style>
