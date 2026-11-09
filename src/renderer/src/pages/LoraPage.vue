<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// LoRAs: an overview of all of them (trigger words, category, what they were trained with, renaming) and a
// comparison of strengths: the same prompt and seed, one picture per strength and LoRA.
import { computed, nextTick, onActivated, reactive, ref, watch } from 'vue'
import { ExternalLink, Flame, Pencil, RefreshCw, Scale, Search, Sparkles, X } from '@lucide/vue'
import PageFrame from '../components/PageFrame.vue'
import JobGallery from '../components/JobGallery.vue'
import BakeDialog from '../components/BakeDialog.vue'
import { useAssetsStore } from '../stores/assets'
import { useHandoffStore } from '../stores/handoff'
import { useQueueStore } from '../stores/queue'
import { cleanError } from '../stores/runtimes'
import { openLink } from '../util/links'
import { comparisonJobs, parseStrengths } from '../util/lora_compare'
import { loraGuide } from '../util/lora_guide'
import { CONSENT_QUESTION } from '@shared/content_policy'
import { askConsent } from '../util/consent'
import { FAMILY_TITLES, familyTitle as subBaseTitle, loraFits } from '@shared/lora_fit'
import type { LoraDetails, LoraExample, LoraInfo, QueuedJob } from '@shared/api'
import type { Asset, Job } from '@shared/types'
import { seedOf } from '@/util/seed'
import { dateLocale, t } from '../i18n'

const familyTitle = (f: string): string => FAMILY_TITLES[f] ?? (f || t('lora.other'))

const assets = useAssetsStore()
const baking = ref(false)
const bakingCompare = ref(false)
const queue = useQueueStore()
const handoff = useHandoffStore()
const tab = ref<'overview' | 'compare'>('overview')
const url = (path: string): string => window.vk.files.url(path)

// ------------------------------------------------------------------ overview
const search = ref('')
const family = ref('all')
const selectedId = ref('')
const details = ref<LoraDetails>()
/** what the page of the LoRA says: description, recommended settings, example prompts */
const info = ref<LoraInfo>()
const infoState = ref<'' | 'loading' | 'unknown'>('')
const infoError = ref('')
const wholeDescription = ref(false)
const words = ref<string[]>([])
const wordInput = ref('')
const copied = ref('')
const renaming = ref(false)
const newName = ref('')
const problem = ref('')
const renameInput = ref<HTMLInputElement>()

const loras = computed(() => assets.loras)
const families = computed(() => {
  const ids = [...new Set(loras.value.map((l) => l.meta.family))].sort()
  return [{ id: 'all', title: t('lora.all'), count: loras.value.length }, ...ids.map((id) => ({ id, title: familyTitle(id), count: loras.value.filter((l) => l.meta.family === id).length }))]
})
const shown = computed(() => {
  const q = search.value.trim().toLowerCase()
  return loras.value.filter((l) => (family.value === 'all' || l.meta.family === family.value)
    && (!q || [l.title, l.name, (l.meta.triggerWords ?? []).join(' '), l.category ?? '', familyTitle(l.meta.family)].join(' ').toLowerCase().includes(q)))
})
const categories = computed(() => [...new Set(loras.value.map((l) => l.category).filter((c): c is string => !!c))])
const current = computed(() => loras.value.find((l) => l.id === selectedId.value))
const wordsChanged = computed(() => !!current.value && JSON.stringify(words.value) !== JSON.stringify(current.value.meta.triggerWords ?? []))
const triggerSource = computed(() => (!current.value?.meta.triggerWords?.length ? ''
  : t(({ user: 'lora.details.triggerEdited', civitai: 'lora.details.triggerCivitai', training: 'lora.details.triggerTraining' } as const)[details.value?.triggerSource ?? 'training'])))
/** how this LoRA is used and what makes its pictures good, in plain words */
const guide = computed(() => (current.value ? loraGuide(current.value, details.value, assets.models, info.value) : []))
const recommended = computed(() => {
  const r = info.value?.recommended
  if (!r) return []
  const ranged = r.minStrength !== undefined && r.maxStrength !== undefined && r.minStrength !== r.maxStrength
  const strength = r.strength === undefined ? undefined
    : ranged ? t('lora.recommended.range', { value: r.strength, min: r.minStrength ?? '', max: r.maxStrength ?? '' }) : String(r.strength)
  const rows: [string, string | undefined][] = [
    [t('lora.recommended.strength'), strength], [t('lora.recommended.steps'), r.steps?.toString()], [t('lora.recommended.guidance'), r.guidance?.toString()],
    [t('lora.recommended.sampler'), r.sampler], [t('lora.recommended.clipSkip'), r.clipSkip?.toString()], [t('lora.recommended.madeFor'), info.value?.baseModel],
  ]
  return rows.filter((row): row is [string, string] => !!row[1])
})

/** The info of the selected LoRA: what is kept from an earlier look, else read from its page now. */
async function loadInfo(refresh = false): Promise<void> {
  const lora = current.value
  if (!refresh) info.value = undefined
  infoError.value = ''
  wholeDescription.value = false
  if (!lora) return
  infoState.value = 'loading'
  try {
    const found = await window.vk.loras.info(lora.id, refresh)
    if (current.value?.id !== lora.id) return  // another LoRA was selected meanwhile
    info.value = found
    infoState.value = found ? '' : 'unknown'
  } catch (err) {
    if (current.value?.id !== lora.id) return
    infoError.value = cleanError(err)
    infoState.value = ''
  }
}

/** Tries a prompt of the makers in the comparison, with the strength they used. */
function tryExample(example: LoraExample): void {
  if (!current.value) return
  compareThis(current.value)
  compare.prompt = example.prompt
  compare.seed = example.seed ?? null
  compare.strengths = example.strength !== undefined && example.strength !== 0 ? `0, ${example.strength}` : '0, 1'
}
const trainingRows = computed(() => {
  const tr = details.value?.training
  if (!tr) return []
  const rows: [string, unknown][] = [[t('lora.training.trainedFor'), tr.base], [t('lora.training.trainingTitle'), tr.title], [t('lora.training.network'), tr.network],
    [t('lora.training.resolution'), tr.resolution], [t('lora.training.pictures'), tr.images], [t('lora.training.epochs'), tr.epochs], [t('lora.training.steps'), tr.steps],
    [t('lora.training.learningRate'), tr.learningRate], [t('lora.training.trainedOn'), tr.trained], [t('lora.training.software'), tr.software]]
  return rows.filter((r) => r[1] !== undefined && r[1] !== '')
})

async function loadDetails(): Promise<void> {
  details.value = undefined
  if (!current.value) return
  try {
    details.value = await window.vk.loras.details(current.value.id)
  } catch {
    details.value = undefined
  }
}

watch(current, (l, old) => {
  if (!l) return
  if (old?.id !== l.id) {
    renaming.value = false
    problem.value = ''
    void loadDetails()
    void loadInfo()
  }
  words.value = [...(l.meta.triggerWords ?? [])]
})

async function copy(word: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(word)
  } catch {
    return
  }
  copied.value = word
  setTimeout(() => { if (copied.value === word) copied.value = '' }, 1500)
}

function addWord(word = wordInput.value): void {
  const w = word.trim()
  if (w && !words.value.includes(w)) words.value = [...words.value, w]
  wordInput.value = ''
}

async function saveWords(): Promise<void> {
  if (!current.value) return
  problem.value = ''
  try {
    await window.vk.loras.setTriggerWords(current.value.id, [...words.value])
    await assets.refresh()
    await loadDetails()
  } catch (err) {
    problem.value = cleanError(err)
  }
}

async function setCategory(value: string): Promise<void> {
  if (!current.value) return
  problem.value = ''
  try {
    await window.vk.loras.setCategory(current.value.id, value)
    await assets.refresh()
  } catch (err) {
    problem.value = cleanError(err)
  }
}

function startRename(): void {
  if (!current.value) return
  newName.value = current.value.title
  problem.value = ''
  renaming.value = true
  void nextTick(() => renameInput.value?.select())
}

async function rename(): Promise<void> {
  if (!current.value) return
  try {
    await window.vk.assets.rename(current.value.id, newName.value)
    await assets.refresh()
    renaming.value = false
  } catch (err) {
    problem.value = cleanError(err)
  }
}

// ------------------------------------------------------------------ comparison
const compare = reactive({ modelId: '', loraA: '', loraB: '', strengths: '0, 0.5, 1', prompt: '', seed: null as number | null })
const compareError = ref('')
const loraA = computed(() => loras.value.find((l) => l.id === compare.loraA))
const loraB = computed(() => loras.value.find((l) => l.id === compare.loraB && l.id !== compare.loraA))
const compareModels = computed(() => assets.models.filter((m) => m.meta.kind === 'image' && !m.meta.inpaintOnly && !m.meta.unsupported && (!loraA.value || loraFits(loraA.value, m))))
const compareModel = computed(() => compareModels.value.find((m) => m.id === compare.modelId))
// LoRAs of the same family and size (a [klein] 4B and a [klein] 9B LoRA never share a model)
const partners = computed(() => loras.value.filter((l) => l.id !== compare.loraA && l.meta.family === loraA.value?.meta.family
  && (!l.meta.variant || !loraA.value.meta.variant || l.meta.variant === loraA.value.meta.variant)))
const compareWords = computed(() => [...new Set([loraA.value, loraB.value].flatMap((l) => l?.meta.triggerWords ?? []))])
const strengths = computed(() => parseStrengths(compare.strengths))
const plan = computed(() => {
  if (!loraA.value) return t('lora.compare.chooseToCompare')
  const picked = [loraA.value, loraB.value].filter((l): l is Asset => !!l)
  const n = (strengths.value.includes(0) ? 1 : 0) + strengths.value.filter((s) => s !== 0).length * picked.length
  const list = strengths.value.map((s) => (s === 0 ? t('lora.compare.withoutLoraLower') : s)).join(', ')
  return t(picked.length > 1 ? 'lora.compare.planEach' : 'lora.compare.plan', { n, list })
})
const jobs = computed(() => queue.ofPage('lora'))

watch([compareModels, loraA], () => {
  if (!compareModel.value && compareModels.value.length) compare.modelId = compareModels.value[0].id
  if (compare.loraB && !partners.value.some((l) => l.id === compare.loraB)) compare.loraB = ''
})

function compareThis(l: Asset): void {
  compare.loraA = l.id
  compare.loraB = ''
  tab.value = 'compare'
}

function insertWords(): void {
  const missing = compareWords.value.filter((w) => !compare.prompt.toLowerCase().includes(w.toLowerCase()))
  if (missing.length) compare.prompt = [missing.join(', '), compare.prompt.trim()].filter(Boolean).join(', ')
}

async function runComparison(): Promise<void> {
  compareError.value = ''
  const model = compareModel.value
  if (!loraA.value || !model) return void (compareError.value = !loraA.value ? t('lora.compare.chooseLora') : t('lora.compare.installModel'))
  if (!compare.prompt.trim()) return void (compareError.value = t('lora.compare.describe'))
  if (!strengths.value.length) return void (compareError.value = t('lora.compare.badStrengths'))
  const list = comparisonJobs(model, [loraA.value, loraB.value].filter((l): l is Asset => !!l), strengths.value, compare.prompt, compare.seed ?? Math.floor(Math.random() * 2 ** 31))
  try {
    for (const job of list) {
      try {
        await queue.add(job)
      } catch (err) {
        if (cleanError(err) !== CONSENT_QUESTION) throw err
        if (!(await askConsent())) return
        await queue.add({ ...job, consent: true })
      }
    }
  } catch (err) {
    compareError.value = cleanError(err)
  }
}

function open(q: QueuedJob, file: string): void {
  const pictures = jobs.value.flatMap((x) => queue.shown(x).map((f) => ({ job: JSON.parse(JSON.stringify(x.job)) as Job, file: f })))
  void window.vk.viewer.open(pictures, pictures.findIndex((p) => p.file === file && p.job.id === q.job.id))
}

async function refresh(): Promise<void> {
  await assets.refresh()
  const given = handoff.take('lora')
  const sent = given?.loraFolder ? loras.value.find((l) => l.folder === given.loraFolder) : undefined
  if (sent) {
    selectedId.value = sent.id
    compareThis(sent)
  }
}
onActivated(refresh)
</script>

<template>
  <PageFrame :title="t('lora.title')" :subtitle="t('lora.installed', { n: loras.length })">
    <template #actions>
      <div class="tabs">
        <button :class="{ on: tab === 'overview' }" @click="tab = 'overview'">{{ t('lora.overview') }}</button>
        <button :class="{ on: tab === 'compare' }" @click="tab = 'compare'">{{ t('lora.compareStrengths') }}</button>
      </div>
    </template>

    <!-- overview -->
    <template v-if="tab === 'overview'">
      <div class="filters">
        <div class="chips">
          <button v-for="f in families" :key="f.id" class="chip" :class="{ on: family === f.id }" @click="family = f.id">{{ f.title }} <small class="dim">{{ f.count }}</small></button>
        </div>
        <label class="search"><Search :size="14" class="dim" /><input v-model="search" type="search" :placeholder="t('lora.searchPlaceholder')" spellcheck="false" /></label>
      </div>
      <p v-if="!loras.length" class="dim">{{ t('lora.none') }}</p>
      <div class="cards">
        <button v-for="l in shown" :key="l.id" class="card lora" :class="{ on: l.id === selectedId }" @click="selectedId = l.id">
          <div class="picture">
            <img v-if="l.preview" :src="url(l.preview)" loading="lazy" draggable="false" />
            <span v-else class="dim">{{ l.title.slice(0, 2).toUpperCase() }}</span>
          </div>
          <div class="body">
            <strong>{{ l.title }}</strong>
            <small class="dim">{{ familyTitle(l.meta.family) }}<template v-if="l.category"> · #{{ l.category }}</template></small>
            <div class="words">
              <span v-for="w in (l.meta.triggerWords ?? []).slice(0, 3)" :key="w" class="word">{{ w }}</span>
              <small v-if="(l.meta.triggerWords?.length ?? 0) > 3" class="dim">+{{ (l.meta.triggerWords?.length ?? 0) - 3 }}</small>
              <small v-if="!l.meta.triggerWords?.length" class="dim">{{ t('lora.noTriggerWord') }}</small>
            </div>
          </div>
        </button>
      </div>
    </template>

    <!-- comparison -->
    <template v-else>
      <div class="compare">
        <div class="card prompt">
          <textarea v-model="compare.prompt" rows="5" :placeholder="t('lora.compare.promptPlaceholder')" spellcheck="false" @keydown.meta.enter.prevent="runComparison" />
          <div class="send">
            <span v-if="compareError" class="error selectable">{{ compareError }}</span>
            <span v-else class="dim">{{ plan }}</span>
            <button class="btn primary" @click="runComparison"><Sparkles :size="14" /> {{ t('lora.compare.compare') }}</button>
          </div>
        </div>
        <JobGallery :jobs="jobs" @open="open" />
      </div>
    </template>

    <template #panel>
      <!-- details of the selected LoRA -->
      <div v-if="tab === 'overview' && current" class="fields">
        <img v-if="current.preview" :src="url(current.preview)" class="preview" draggable="false" />
        <div v-if="!renaming" class="title">
          <h2 class="selectable">{{ current.title }}</h2>
          <button class="btn small ghost" :title="t('lora.details.renameHint')" @click="startRename"><Pencil :size="12" /></button>
        </div>
        <div v-else class="line">
          <input
            ref="renameInput" v-model="newName" type="text" spellcheck="false" :placeholder="current.name" maxlength="120"
            @keyup.enter="rename" @keyup.esc="renaming = false"
          />
          <button class="btn small" @click="rename">{{ t('lora.details.save') }}</button>
          <button class="btn small ghost" @click="renaming = false"><X :size="12" /></button>
        </div>
        <p v-if="!renaming && current.title !== current.name" class="dim selectable">{{ t('lora.details.folder', { name: current.name }) }}</p>
        <p class="dim">
          {{ t('lora.details.loraFor', { base: subBaseTitle(current.meta.family, current.meta.variant) }) }}<template v-if="details?.sizeMb"> · {{ details.sizeMb }} MB</template>
          <template v-if="details?.paramsM"> · {{ t('lora.details.params', { n: details.paramsM }) }}</template>
        </p>
        <button v-if="details?.page" class="btn small link" :title="details.page" @click="openLink(details.page)">
          <ExternalLink :size="12" /> <span>{{ details.pageName || t('lora.details.itsPage') }}</span>
        </button>
        <p v-if="problem" class="error selectable">{{ problem }}</p>
        <button class="btn small" @click="baking = true"><Flame :size="12" /> {{ t('lora.details.bake') }}</button>
        <BakeDialog v-if="baking" :lora-ids="[current.id]" @close="baking = false" />

        <div class="field">
          <span>{{ t('lora.details.triggerWords') }} <b>{{ triggerSource }}</b></span>
          <div class="words">
            <span v-for="(w, i) in words" :key="w" class="word big" :title="t('lora.details.clickToCopy')" @click="copy(w)">
              {{ w }}<button :title="t('lora.details.remove')" @click.stop="words = words.filter((_x, j) => j !== i)"><X :size="10" /></button>
            </span>
            <input v-model="wordInput" type="text" class="add" :placeholder="t('lora.details.addWord')" spellcheck="false" @keyup.enter="addWord()" />
          </div>
          <div class="line">
            <button v-if="wordsChanged" class="btn small primary" @click="saveWords">{{ t('lora.details.saveWords') }}</button>
            <small v-if="copied" class="dim">{{ t('lora.details.copied', { word: copied }) }}</small>
          </div>
        </div>

        <label class="field">
          <span>{{ t('lora.details.category') }}</span>
          <input type="text" list="vk-lora-categories" :value="current.category ?? ''" :placeholder="t('lora.details.categoryPlaceholder')" spellcheck="false" @change="setCategory(($event.target as HTMLInputElement).value)" />
          <datalist id="vk-lora-categories"><option v-for="c in categories" :key="c" :value="c" /></datalist>
        </label>

        <button class="btn" @click="compareThis(current)"><Scale :size="14" /> {{ t('lora.compareStrengths') }}</button>

        <div class="field">
          <span>{{ t('lora.info.fromPage') }}
            <button class="btn small ghost" :disabled="infoState === 'loading'" :title="t('lora.info.readAgain')" @click="loadInfo(true)"><RefreshCw :size="12" /></button>
          </span>
          <small v-if="infoState === 'loading' && !info" class="dim">{{ t('lora.info.reading') }}</small>
          <small v-else-if="infoState === 'unknown'" class="dim">{{ t('lora.info.unknown') }}</small>
          <small v-if="infoError" class="error selectable">{{ infoError }}</small>
          <template v-if="info">
            <small class="dim">
              {{ info.source === 'civitai' ? 'Civitai' : 'Hugging Face' }}<template v-if="info.creator"> · {{ t('lora.info.by', { creator: info.creator }) }}</template><template v-if="info.version"> · {{ info.version }}</template>
              · {{ t('lora.info.readOn', { date: new Date(info.fetchedAt).toLocaleDateString(dateLocale()) }) }}
            </small>
            <div v-if="info.tags.length" class="words"><span v-for="tag in info.tags" :key="tag" class="word tag">{{ tag }}</span></div>
            <div v-if="info.description.length" class="text selectable" :class="{ clamped: !wholeDescription }">
              <p v-for="(para, i) in info.description" :key="i">{{ para }}</p>
            </div>
            <button v-if="info.description.length > 3" class="btn small ghost" @click="wholeDescription = !wholeDescription">{{ wholeDescription ? t('lora.info.showLess') : t('lora.info.showAll') }}</button>
            <small v-if="!info.description.length" class="dim">{{ t('lora.info.noDescription') }}</small>
            <template v-if="info.versionNotes.length">
              <small class="dim">{{ t('lora.info.aboutVersion') }}</small>
              <div class="text selectable"><p v-for="(para, i) in info.versionNotes" :key="i">{{ para }}</p></div>
            </template>
            <small v-if="info.commercialUse?.length" class="dim">{{ t('lora.info.commercialUse', { uses: info.commercialUse.join(', ') }) }}</small>
            <small v-if="info.licence" class="dim">{{ t('lora.info.licence', { licence: info.licence }) }}</small>
          </template>
        </div>

        <div v-if="info && recommended.length" class="field">
          <span>{{ t('lora.recommended.title') }}</span>
          <dl><template v-for="[k, v] in recommended" :key="k"><dt class="dim">{{ k }}</dt><dd class="selectable">{{ v }}</dd></template></dl>
          <small class="dim">
            {{ info.recommended.fromMakers ? t('lora.recommended.fromMakers') : info.recommended.examples ? t('lora.recommended.fromExamples', { n: info.recommended.examples }) : '' }}
          </small>
        </div>

        <div v-if="info?.examples.length" class="field">
          <span>{{ t('lora.examples.title') }}</span>
          <div v-for="(e, i) in info.examples" :key="i" class="example">
            <p class="selectable">{{ e.prompt }}</p>
            <div class="line">
              <small class="dim">{{ [e.strength !== undefined && t('lora.examples.strength', { value: e.strength }), e.steps && t('lora.examples.steps', { n: e.steps }), e.guidance !== undefined && t('lora.examples.guidance', { value: e.guidance }), e.sampler].filter(Boolean).join(' · ') }}</small>
              <button class="btn small" :title="t('lora.examples.tryHint')" @click="tryExample(e)">{{ t('lora.examples.tryIt') }}</button>
            </div>
          </div>
        </div>

        <details class="guide" open>
          <summary>{{ t('lora.howToUse') }}</summary>
          <section v-for="s in guide" :key="s.title">
            <h3>{{ s.title }}</h3>
            <p v-for="para in s.text" :key="para" class="selectable">{{ para }}</p>
          </section>
        </details>

        <div class="field">
          <span>{{ t('lora.training.title') }}</span>
          <p v-if="!trainingRows.length" class="dim">{{ t('lora.training.nothing') }}</p>
          <dl v-else>
            <template v-for="[k, v] in trainingRows" :key="k"><dt class="dim">{{ k }}</dt><dd class="selectable">{{ v }}</dd></template>
          </dl>
        </div>
        <div v-if="details?.training?.topTags.length" class="field">
          <span>{{ t('lora.training.topTags') }}</span>
          <small class="dim">{{ t('lora.training.topTagsHint') }}</small>
          <div class="words">
            <button v-for="[tag, n] in details.training.topTags" :key="tag" class="word tag" @click="addWord(tag)">{{ tag }} <small class="dim">{{ n }}</small></button>
          </div>
        </div>
      </div>
      <p v-else-if="tab === 'overview'" class="dim">{{ t('lora.selectHint') }}</p>

      <!-- settings of the comparison -->
      <div v-else class="fields">
        <label class="field">
          <span>{{ t('lora.compare.lora') }}</span>
          <select v-model="compare.loraA">
            <option value="" disabled>{{ t('lora.compare.choose') }}</option>
            <option v-for="l in loras" :key="l.id" :value="l.id">{{ l.title }} ({{ familyTitle(l.meta.family) }})</option>
          </select>
        </label>
        <label class="field">
          <span>{{ t('lora.compare.second') }} <b>{{ t('lora.compare.optional') }}</b></span>
          <select v-model="compare.loraB" :disabled="!partners.length">
            <option value="">{{ t('lora.compare.noneOption') }}</option>
            <option v-for="l in partners" :key="l.id" :value="l.id">{{ l.title }}</option>
          </select>
        </label>
        <label class="field">
          <span>{{ t('lora.compare.model') }}</span>
          <select v-model="compare.modelId">
            <option v-for="m in compareModels" :key="m.id" :value="m.id">{{ m.title }}</option>
          </select>
          <small v-if="loraA && !compareModels.length" class="error">{{ t('lora.compare.noModel', { family: familyTitle(loraA.meta.family) }) }}</small>
        </label>
        <label class="field">
          <span>{{ t('lora.compare.strengths') }}</span>
          <input v-model="compare.strengths" type="text" placeholder="0, 0.5, 1" spellcheck="false" />
          <small class="dim">{{ t('lora.compare.strengthsHint') }}</small>
        </label>
        <div v-if="compareWords.length" class="field">
          <span>{{ t('lora.compare.triggerWords') }}</span>
          <div class="words"><span v-for="w in compareWords" :key="w" class="word">{{ w }}</span></div>
          <button class="btn small" @click="insertWords">{{ t('lora.compare.insertWords') }}</button>
        </div>
        <label class="field">
          <span>{{ t('lora.compare.seed') }}</span>
          <input type="number" min="0" :value="compare.seed ?? ''" :placeholder="t('lora.compare.seedPlaceholder')"
            @input="compare.seed = ($event.target as HTMLInputElement).value === '' ? null : seedOf(($event.target as HTMLInputElement).value)" />
        </label>
        <small class="dim">{{ t('lora.compare.modelOwn') }}</small>
        <button class="btn" :disabled="!loraA" @click="bakingCompare = true"><Flame :size="13" /> {{ t('lora.details.bake') }}</button>
        <BakeDialog
          v-if="bakingCompare && loraA" :lora-ids="[loraA.id, ...(loraB ? [loraB.id] : [])]" :model-id="compare.modelId"
          @close="bakingCompare = false"
        />
      </div>
    </template>
  </PageFrame>
</template>

<style scoped>
/* the family chips and the search stay at the top while the cards scroll under them, as on the Models page (-24px:
   the work area's own padding, so that nothing shows above the bar) */
.filters {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  position: sticky;
  top: -24px;
  z-index: 5;
  margin: -10px 0 4px;
  padding: 10px 0;
  background: var(--bg);
}

.chips,
.words,
.line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.search input {
  width: 260px;
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 12px;
}

.lora {
  width: 100%;
  padding: 0;
  overflow: hidden;
  text-align: left;
  display: flex;
  flex-direction: column;
}

.lora.on {
  border-color: var(--accent);
}

.picture {
  aspect-ratio: 1;
  background: var(--surface-2);
  display: grid;
  place-items: center;
  font-weight: 600;
  font-size: 20px;
}

.picture img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.body {
  display: grid;
  gap: 3px;
  padding: 8px 10px 10px;
}

.body strong {
  overflow-wrap: anywhere;
}

.word {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 7px;
  border: 0;
  border-radius: 9px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 11px;
}

.word.big {
  font-size: 12px;
  padding: 2px 4px 2px 9px;
  cursor: copy;
}

.word.big button {
  display: grid;
  border: 0;
  background: transparent;
  color: inherit;
  padding: 2px;
}

.word.tag {
  background: var(--surface-2);
  color: inherit;
}

.compare {
  display: grid;
  gap: 16px;
}

.prompt {
  padding: 12px 12px 10px 14px;
}

.fields {
  display: grid;
  gap: 16px;
}

.field > span {
  display: flex;
  justify-content: space-between;
}

.field b {
  font-weight: 400;
  color: var(--text-dim);
}

.preview {
  width: 100%;
  border-radius: var(--radius-m);
}

.title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.title h2 {
  word-break: break-word;
}

input[type='text'],
input[type='number'],
select {
  width: 100%;
}

.add {
  width: 90px !important;
  height: 24px !important;
  font-size: 12px !important;
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

/* the name of a page can be long: it wraps instead of widening the panel */
.link {
  height: auto;
  min-height: 24px;
  padding: 4px 8px;
  white-space: normal;
  text-align: left;
  align-items: flex-start;
}

.link svg {
  flex: none;
  margin-top: 3px;
}

.text {
  display: grid;
  gap: 6px;
  line-height: 1.5;
}

/* the beginning of a long description; "Show all" opens it */
.text.clamped {
  max-height: 7.5em;
  overflow: hidden;
  mask-image: linear-gradient(#000 60%, transparent);
}

.example {
  display: grid;
  gap: 4px;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
}

.example p {
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.example .line {
  justify-content: space-between;
}

.guide {
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  background: var(--surface-2);
}

.guide summary {
  padding: 8px 12px;
  font-weight: 600;
  cursor: default;
}

.guide section {
  display: grid;
  gap: 5px;
  padding: 8px 12px 10px;
  border-top: 1px solid var(--line);
}

.guide h3 {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
}

.guide p {
  line-height: 1.5;
}
</style>
