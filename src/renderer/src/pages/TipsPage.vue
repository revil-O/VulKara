<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Tips & tricks: prompt help and guidelines, by topic and by model family; the family of the model chosen on the Text
// page comes first.
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue'
import { Check, ChevronLeft, ChevronRight, Copy, ExternalLink, Search, X } from '@lucide/vue'
import HintBadge from '../components/HintBadge.vue'
import PageFrame from '../components/PageFrame.vue'
import { useAssetsStore } from '../stores/assets'
import { openLink } from '../util/links'
import { t } from '../i18n'
import { TIP_SOURCES, TOPICS, groupForFamily, searchTips, tipGroups, tipPicture, type TipGroup, type TipImage } from '../util/tips'

const assets = useAssetsStore()
const query = ref('')
const selected = ref('general')
const copied = ref('')

// the model chosen on the Text page
const model = computed(() => {
  try {
    const id = JSON.parse(localStorage.getItem('vk.form.text') ?? '{}').modelId
    return assets.models.find((m) => m.id === id)
  } catch {
    return undefined
  }
})
const yours = computed(() => groupForFamily(model.value?.meta.family))

const topics = computed(() => tipGroups().filter((g) => TOPICS.includes(g.id)))
const families = computed(() => tipGroups().filter((g) => !TOPICS.includes(g.id)))

const SOURCES = 'sources'
const showSources = computed(() => !query.value.trim() && selected.value === SOURCES)

const shown = computed<TipGroup[]>(() => {
  if (query.value.trim()) return searchTips(tipGroups(), query.value)
  if (showSources.value) return []
  const g = tipGroups().find((x) => x.id === selected.value)
  return g ? [g] : []
})

async function copy(text: string): Promise<void> {
  await navigator.clipboard.writeText(text)
  copied.value = text
  setTimeout(() => { if (copied.value === text) copied.value = '' }, 1500)
}

// a picture of a tip, large, with the others of its row to step through
const preview = ref<{ images: TipImage[]; index: number }>()
const current = computed(() => preview.value?.images[preview.value.index])
function step(by: number): void {
  const p = preview.value
  if (p) p.index = (p.index + by + p.images.length) % p.images.length
}
const keys = (e: KeyboardEvent): void => {
  if (!preview.value) return
  if (e.key === 'Escape') preview.value = undefined
  else if (e.key === 'ArrowLeft') step(-1)
  else if (e.key === 'ArrowRight') step(1)
  else return
  e.preventDefault()
}

// the page stays alive while others are shown: the keys are only its own while it is visible
onActivated(() => window.addEventListener('keydown', keys))
onDeactivated(() => {
  window.removeEventListener('keydown', keys)
  preview.value = undefined
})
onMounted(async () => {
  const before = selected.value
  await assets.refresh()
  // a group the user picked meanwhile stays
  if (yours.value && selected.value === before) selected.value = yours.value.id
})
onBeforeUnmount(() => window.removeEventListener('keydown', keys))
</script>

<template>
  <PageFrame :title="t('tips.title')" :subtitle="t('tips.subtitle')">
    <div class="tips">
      <nav class="groups">
        <label class="search">
          <Search :size="14" />
          <input v-model="query" type="search" :placeholder="t('tips.search')" />
        </label>
        <template v-if="yours">
          <h3>{{ t('tips.forYourModel') }}</h3>
          <button class="group" :class="{ on: !query && selected === yours.id }" @click="selected = yours.id; query = ''">
            {{ yours.title }} <small class="dim">{{ model?.title }}</small>
          </button>
        </template>
        <h3>{{ t('tips.topics') }}</h3>
        <button v-for="g in topics" :key="g.id" class="group" :class="{ on: !query && selected === g.id }" @click="selected = g.id; query = ''">
          {{ g.title }}
        </button>
        <h3>{{ t('tips.modelTypes') }}</h3>
        <button v-for="g in families" :key="g.id" class="group" :class="{ on: !query && selected === g.id }" @click="selected = g.id; query = ''">
          {{ g.title }}
        </button>
        <h3>{{ t('tips.aboutTips') }}</h3>
        <button class="group" :class="{ on: showSources }" @click="selected = SOURCES; query = ''">{{ t('tips.sources') }}</button>
      </nav>

      <div class="content selectable">
        <p v-if="query && !shown.length" class="dim">{{ t('tips.noMatch') }}</p>
        <section v-for="g in shown" :key="g.id">
          <h2>{{ g.title }}</h2>
          <p class="dim intro">{{ g.intro }}</p>
          <article v-for="tip in g.tips" :key="tip.title" class="tip card">
            <h4>{{ tip.title }}</h4>
            <p>{{ tip.body }}</p>
            <div v-if="tip.images?.length" class="pictures">
              <figure v-for="(img, i) in tip.images" :key="img.file">
                <img
                  :src="tipPicture(img.file)" :alt="img.caption" draggable="false" role="button" tabindex="0" :title="t('tips.larger')"
                  @click="preview = { images: tip.images!, index: i }" @keydown.enter="preview = { images: tip.images!, index: i }"
                />
                <figcaption>
                  <strong>{{ img.caption }}</strong>
                  <template v-if="img.prompt">
                    <HintBadge :text="img.prompt" />
                    <button class="btn small ghost" :title="copied === img.prompt ? t('tips.copied') : t('tips.copyPrompt')" @click="copy(img.prompt)">
                      <component :is="copied === img.prompt ? Check : Copy" :size="12" />
                    </button>
                  </template>
                </figcaption>
              </figure>
            </div>
            <div v-if="tip.example" class="example">
              <code>{{ tip.example }}</code>
              <button class="btn small ghost" :title="copied === tip.example ? t('tips.copied') : t('tips.copyPrompt')" @click="copy(tip.example)">
                <component :is="copied === tip.example ? Check : Copy" :size="13" />
              </button>
            </div>
            <div v-if="tip.do?.length || tip.avoid?.length" class="lists">
              <ul v-if="tip.do?.length" class="do">
                <li v-for="d in tip.do" :key="d">{{ d }}</li>
              </ul>
              <ul v-if="tip.avoid?.length" class="avoid">
                <li v-for="a in tip.avoid" :key="a">{{ a }}</li>
              </ul>
            </div>
          </article>
        </section>

        <section v-if="showSources" class="sources">
          <h2>{{ t('tips.sources') }}</h2>
          <p class="dim intro">{{ t('tips.sourcesIntro') }}</p>
          <ul>
            <li v-for="s in TIP_SOURCES" :key="s.url">
              <a href="#" @click.prevent="openLink(s.url)">{{ s.title }} <ExternalLink :size="11" /></a>
            </li>
          </ul>
        </section>
      </div>
    </div>

    <div v-if="preview && current" class="preview" @click.self="preview = undefined">
      <div class="preview-box">
        <button class="btn small ghost close" :title="t('tips.close')" @click="preview = undefined"><X :size="16" /></button>
        <img :src="tipPicture(current.file)" :alt="current.caption" draggable="false" />
        <div class="preview-bar">
          <button v-if="preview.images.length > 1" class="btn small ghost" :title="t('tips.previous')" @click="step(-1)"><ChevronLeft :size="16" /></button>
          <strong>{{ current.caption }}</strong>
          <template v-if="current.prompt">
            <HintBadge :text="current.prompt" above />
            <button class="btn small ghost" :title="copied === current.prompt ? t('tips.copied') : t('tips.copyPrompt')" @click="copy(current.prompt)">
              <component :is="copied === current.prompt ? Check : Copy" :size="13" />
            </button>
          </template>
          <span v-if="preview.images.length > 1" class="dim">{{ preview.index + 1 }} / {{ preview.images.length }}</span>
          <button v-if="preview.images.length > 1" class="btn small ghost" :title="t('tips.next')" @click="step(1)"><ChevronRight :size="16" /></button>
        </div>
      </div>
    </div>
  </PageFrame>
</template>

<style scoped>
.tips {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

.groups {
  position: sticky;
  top: 0;
  display: grid;
  gap: 2px;
}

.groups h3 {
  margin: 14px 0 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-dim);
}

.search {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  background: var(--surface);
  color: var(--text-dim);
}

.search input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: none;
  color: var(--text);
  outline: none;
}

.group {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  padding: 6px 10px;
  border: 0;
  border-radius: var(--radius-s);
  background: none;
  color: var(--text);
  text-align: left;
  cursor: pointer;
}

.group:hover {
  background: var(--surface-2);
}

.group.on {
  background: var(--accent-soft);
  color: var(--accent);
}

.content {
  display: grid;
  gap: 12px;
  max-width: 860px;
  line-height: 1.55;
}

h2 {
  margin: 0;
  font-size: 18px;
}

.intro {
  margin: 0 0 4px;
}

.tip {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
}

.tip h4 {
  margin: 0;
  font-size: 13.5px;
}

.tip p {
  margin: 0;
}

/* small pictures, side by side: a pair or a row (e.g. LoRA weights 0 to 1.5) */
.pictures {
  display: grid;
  grid-template-columns: repeat(auto-fill, 150px);
  gap: 10px;
  margin: 4px 0;
  align-items: start;
}

.pictures figure {
  margin: 0;
  display: grid;
  align-content: start;
  gap: 4px;
  /* the picture takes the column's 150 px, not the width of a long caption (the figure's own column would grow
     with it, and the picture with the column) */
  grid-template-columns: minmax(0, 1fr);
}

.pictures img {
  cursor: zoom-in;
  width: 100%;
  height: auto;
  border-radius: var(--radius-s);
  border: 1px solid var(--line);
}

.pictures figcaption {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  white-space: nowrap;
  min-width: 0;
}

/* a long caption is cut with an ellipsis; the large view shows it whole */
.pictures figcaption strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* a tip picture, large, over the page */
.preview {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.6);
}

.preview-box {
  position: relative;
  display: grid;
  gap: 8px;
  max-width: calc(100vw - 80px);
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow);
}

.preview-box img {
  display: block;
  max-width: 100%;
  max-height: calc(100vh - 150px);
  margin: 0 auto;
  border-radius: var(--radius-m);
}

.preview-box .close {
  position: absolute;
  top: 18px;
  right: 18px;
  background: var(--surface);
}

.preview-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 12.5px;
}

.example {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--radius-s);
  background: var(--surface-2);
}

.example code {
  flex: 1;
  font: 12px/1.5 var(--mono);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.example .btn {
  flex: none;
}

.lists {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.lists ul {
  margin: 0;
  padding-left: 18px;
  font-size: 12.5px;
}

.do li::marker {
  content: '✓  ';
  color: var(--ok);
}

.avoid li::marker {
  content: '✕  ';
  color: var(--danger);
}

.sources ul {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 12.5px;
}

.sources a {
  color: var(--accent);
}
</style>
