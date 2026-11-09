<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Licences: of the app, of the software it contains or installs, and of every model it can download, with what
// each licence allows commercially. An installed model is matched to its entry by its source; one that is not in
// the list gets the licence its origin states (read once, kept in its folder) and that of its base model.
import { licenceListText } from '../util/data_texts'
import { computed, onActivated, reactive, ref, watch } from 'vue'
import { ExternalLink, RefreshCw, Search } from '@lucide/vue'
import PageFrame from '../components/PageFrame.vue'
import { useAssetsStore } from '../stores/assets'
import { cleanError } from '../stores/runtimes'
import { isWebLink, openLink as open } from '../util/links'
import { t, type PlainKey } from '../i18n'
import { baseLicence, licenceNoteKey, stricter, type Allowed } from '@shared/licence_terms'
import type { AssetLicence } from '@shared/api'
import type { Asset } from '@shared/types'
import licences from '@shared/data/licenses.json'
import curated from '@shared/data/curated_models.json'
import appLicence from '../../../../LICENSE?raw'
import notices from '../../../../THIRD_PARTY_NOTICES.txt?raw'

interface ModelLicence {
  group: string
  id: string | null
  title: string
  source: string
  license: string
  license_url: string
  model: 'yes' | 'limited' | 'no'
  outputs: 'yes' | 'limited' | 'no'
  note: string
}

const MODELS = licences.models as ModelLicence[]
const SOFTWARE = licences.software as { group: string; name: string; license: string; url: string }[]
const ANSWER: Record<string, PlainKey> = { yes: 'app.licenses.answer.yes', limited: 'app.licenses.answer.limited', no: 'app.licenses.answer.no', unknown: 'app.licenses.answer.unknown' }
/** a licence note in the app's language when it is one of the known ones (or of the list), else as it was read */
const noteText = (note: string): string => {
  const key = licenceNoteKey(note)
  return key ? t(key) : licenceListText(note)
}

const assets = useAssetsStore()
const tab = ref<'models' | 'installed' | 'software' | 'app'>('models')
const query = ref('')
const showNotices = ref(false)

const shown = computed(() => {
  const q = query.value.trim().toLowerCase()
  return MODELS.filter((m) => !q || [m.title, m.license, m.group, licenceListText(m.group), m.note, noteText(m.note ?? '')].join(' ').toLowerCase().includes(q))
})
const groups = computed(() => [...new Set(shown.value.map((m) => m.group))].map((g) => ({ title: g, models: shown.value.filter((m) => m.group === g) })))
const softwareGroups = [...new Set(SOFTWARE.map((s) => s.group))].map((g) => ({ title: g, items: SOFTWARE.filter((s) => s.group === g) }))

/** The entry of the licence list an installed model is, by its folder or its source. */
function listEntry(a: Asset): ModelLicence | undefined {
  const pick = curated.find((c) => c.id === a.folder.split('/').pop() || (c.ref === a.source?.ref && (c.file ?? null) === (a.source?.file ?? null)))
  const ref = a.source?.ref ?? ''
  return MODELS.find((m) => (pick && m.id === pick.id) || (ref && (m.source.endsWith('/' + ref) || (ref.includes('civitai.com') && m.source === ref.split('?')[0]))))
}

// licences read from the origins of the models that are not in the list
const looked = reactive<Record<string, AssetLicence | { error: string } | 'loading'>>({})
const checking = ref(false)

interface Row {
  asset: Asset
  licence?: string
  url?: string
  note?: string
  from?: string
  page?: string
  base?: { title: string; licence: string; url: string }
  /** the page was found by the folder's name */
  guessed?: boolean
  model: Allowed
  outputs: Allowed
  state: 'list' | 'page' | 'loading' | 'error' | 'none'
  error?: string
}

/** The installed models and LoRAs with the licence that applies: from the list, else from their origin and base model. */
const installed = computed<Row[]>(() => assets.all.map((a) => {
  const entry = listEntry(a)
  if (entry) {
    return { asset: a, licence: entry.license, url: entry.license_url, note: entry.note, model: entry.model, outputs: entry.outputs, state: 'list' }
  }
  const found = looked[a.id]
  const read = typeof found === 'object' && 'source' in found ? found : undefined
  const base = baseLicence(a.meta.family, a.meta.arch, read?.baseModel ?? '')
  let model: Allowed = read?.model ?? 'unknown'
  let outputs: Allowed = read?.outputs ?? 'unknown'
  if (base) {
    // a fine-tune or LoRA may not allow more than the model it builds on
    model = stricter(model, base.terms.model)
    outputs = stricter(outputs, base.terms.outputs)
  }
  const row: Row = {
    asset: a, model, outputs,
    base: base ? { title: base.title, licence: base.terms.name, url: base.terms.url } : undefined,
    state: found === 'loading' || found === undefined ? 'loading' : read ? (read.source === 'none' ? 'none' : 'page') : 'error',
  }
  if (read && read.source !== 'none') {
    Object.assign(row, { licence: read.licence, url: read.licenceUrl, note: read.note, page: read.page, from: read.source === 'civitai' ? 'Civitai' : 'Hugging Face', guessed: read.guessed })
  } else if (read) {
    row.note = read.note
  } else if (typeof found === 'object' && 'error' in found) {
    row.error = found.error
  }
  return row
}))

/** Reads the licences of the models not in the list from their origins, one after the other. */
async function lookUp(refresh = false): Promise<void> {
  if (checking.value) return
  checking.value = true
  try {
    for (const a of assets.all) {
      if (listEntry(a) || (!refresh && looked[a.id] && looked[a.id] !== 'loading')) continue
      looked[a.id] = 'loading'
      try {
        looked[a.id] = await window.vk.licences.get(a.id, refresh)
      } catch (err) {
        looked[a.id] = { error: cleanError(err) }
      }
    }
  } finally {
    checking.value = false
  }
}

watch([tab, () => assets.all], () => { if (tab.value === 'installed') void lookUp() })

// the page of a model whose origin is not known, as the user names it
const originFor = ref('')
const originLink = ref('')

async function saveOrigin(a: Asset): Promise<void> {
  looked[a.id] = 'loading'
  try {
    looked[a.id] = await window.vk.licences.setOrigin(a.id, originLink.value)
    originFor.value = ''
    originLink.value = ''
  } catch (err) {
    looked[a.id] = { error: cleanError(err) }
  }
}

onActivated(() => void assets.refresh())
</script>

<template>
  <PageFrame :title="t('app.licenses.title')" :subtitle="t('app.licenses.subtitle')">
    <template #actions>
      <div class="tabs">
        <button :class="{ on: tab === 'models' }" @click="tab = 'models'">{{ t('app.licenses.tabs.models') }}</button>
        <button :class="{ on: tab === 'installed' }" @click="tab = 'installed'">{{ t('app.licenses.tabs.installed') }}</button>
        <button :class="{ on: tab === 'software' }" @click="tab = 'software'">{{ t('app.licenses.tabs.software') }}</button>
        <button :class="{ on: tab === 'app' }" @click="tab = 'app'">VulKara</button>
      </div>
    </template>

    <div class="wrap">
      <template v-if="tab === 'models'">
        <p class="dim">{{ t('app.licenses.modelsIntro') }}</p>
        <label class="search"><Search :size="14" class="dim" /><input v-model="query" type="search" :placeholder="t('app.licenses.search')" spellcheck="false" /></label>
        <section v-for="g in groups" :key="g.title">
          <h2>{{ licenceListText(g.title) }}</h2>
          <div class="table card">
            <div class="row head"><span>{{ t('app.licenses.model') }}</span><span>{{ t('app.licenses.licence') }}</span><span>{{ t('app.licenses.model') }}</span><span>{{ t('app.licenses.pictures') }}</span></div>
            <div v-for="m in g.models" :key="m.source + m.title" class="row">
              <span><a href="#" @click.prevent="open(m.source)">{{ m.title }}</a></span>
              <span>
                <a href="#" @click.prevent="open(m.license_url)">{{ m.license }}</a>
                <small v-if="m.note" class="dim">{{ noteText(m.note) }}</small>
              </span>
              <span :class="m.model">{{ t(ANSWER[m.model]) }}</span>
              <span :class="m.outputs">{{ t(ANSWER[m.outputs]) }}</span>
            </div>
          </div>
        </section>
      </template>

      <template v-else-if="tab === 'installed'">
        <div class="intro">
          <p class="dim">{{ t('app.licenses.installedIntro') }}</p>
          <button class="btn small" :disabled="checking" :title="t('app.licenses.checkAgainHint')" @click="lookUp(true)">
            <RefreshCw :size="12" :class="{ spin: checking }" /> {{ t('app.licenses.checkAgain') }}
          </button>
        </div>
        <div class="table card">
          <div class="row head"><span>{{ t('app.licenses.installed') }}</span><span>{{ t('app.licenses.licence') }}</span><span>{{ t('app.licenses.model') }}</span><span>{{ t('app.licenses.pictures') }}</span></div>
          <div v-for="i in installed" :key="i.asset.id" class="row">
            <span>{{ i.asset.title }} <small class="dim">{{ i.asset.type === 'lora' ? 'LoRA' : i.asset.meta.label }}</small></span>
            <span>
              <template v-if="i.licence">
                <a v-if="isWebLink(i.url)" href="#" @click.prevent="open(i.url)">{{ i.licence }}</a><template v-else>{{ i.licence }}</template>
                <small v-if="i.from" class="dim">
                  {{ t('app.licenses.readFrom') }} <a v-if="isWebLink(i.page)" href="#" @click.prevent="open(i.page)">{{ t('app.licenses.pageOn', { from: i.from }) }}</a><template v-else>{{ i.from }}</template>
                  <template v-if="i.guessed"> {{ t('app.licenses.guessed') }}</template>
                </small>
              </template>
              <small v-else-if="i.state === 'loading'" class="dim">{{ t('app.licenses.reading') }}</small>
              <small v-else-if="i.state === 'error'" class="error">{{ i.error }}</small>
              <small v-if="i.note" class="dim">{{ noteText(i.note) }}</small>
              <span v-if="i.state === 'none' || i.state === 'error' || i.guessed" class="origin">
                <template v-if="originFor === i.asset.id">
                  <input v-model="originLink" type="text" :placeholder="t('app.licenses.originPlaceholder')" spellcheck="false" @keyup.enter="saveOrigin(i.asset)" @keyup.esc="originFor = ''" />
                  <button class="btn small" :disabled="!originLink.trim()" @click="saveOrigin(i.asset)">{{ t('app.licenses.save') }}</button>
                </template>
                <a v-else href="#" @click.prevent="(originFor = i.asset.id), (originLink = '')">{{ i.guessed ? t('app.licenses.wrongPage') : t('app.licenses.namePage') }}</a>
              </span>
              <small v-if="i.base" class="dim">
                {{ t('app.licenses.base', { title: i.base.title }) }} <a href="#" @click.prevent="open(i.base.url)">{{ i.base.licence }}</a>
              </small>
            </span>
            <span :class="i.model">{{ i.state === 'loading' && !i.base ? '…' : t(ANSWER[i.model]) }}</span>
            <span :class="i.outputs">{{ i.state === 'loading' && !i.base ? '…' : t(ANSWER[i.outputs]) }}</span>
          </div>
        </div>
      </template>

      <template v-else-if="tab === 'software'">
        <section v-for="g in softwareGroups" :key="g.title">
          <h2>{{ licenceListText(g.title) }}</h2>
          <div class="table card software">
            <div v-for="s in g.items" :key="s.name" class="row">
              <span>{{ s.name }}</span>
              <span><a href="#" @click.prevent="open(s.url)">{{ s.license }} <ExternalLink :size="11" /></a></span>
            </div>
          </div>
        </section>
        <p class="dim">{{ t('app.licenses.softwareNote') }}</p>
        <button class="btn" @click="showNotices = !showNotices">{{ showNotices ? t('app.licenses.hideNotices') : t('app.licenses.showNotices') }}</button>
        <pre v-if="showNotices" class="text selectable">{{ notices }}</pre>
      </template>

      <template v-else>
        <pre class="text selectable">{{ appLicence }}</pre>
      </template>
    </div>
  </PageFrame>
</template>

<style scoped>
.wrap {
  display: grid;
  gap: 16px;
  max-width: 1100px;
}

section {
  display: grid;
  gap: 8px;
}

.search {
  max-width: 360px;
}

.search input {
  flex: 1;
}

.table {
  overflow: hidden;
}

.row {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 2fr) 120px 120px;
  gap: 12px;
  padding: 9px 14px;
  align-items: start;
}

.software .row {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}

.row + .row {
  border-top: 1px solid var(--line);
}

.row.head {
  font-weight: 600;
  background: var(--surface-2);
}

.row span {
  display: grid;
  gap: 3px;
  min-width: 0;
  overflow-wrap: anywhere;
}

a {
  color: var(--accent);
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

.yes {
  color: var(--ok);
}

.limited {
  color: var(--accent);
}

.no {
  color: var(--danger);
}

.unknown {
  color: var(--text-dim);
}

.origin {
  display: flex !important;
  gap: 6px;
  align-items: center;
  font-size: 12px;
}

.origin input {
  flex: 1;
  min-width: 0;
  height: 26px;
}

.intro {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.intro .btn {
  flex: none;
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.text {
  margin: 0;
  padding: 14px 16px;
  max-height: 60vh;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  background: var(--surface);
  font: 11.5px/1.5 var(--mono);
  white-space: pre-wrap;
}
</style>
