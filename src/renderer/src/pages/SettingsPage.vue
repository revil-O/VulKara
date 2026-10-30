<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
import { computed, onActivated, reactive, ref } from 'vue'
import { ArrowUpCircle, Check, Copy, Download, FolderOpen, Info, Monitor, Moon, RefreshCw, Sun, Trash2 } from 'lucide-vue-next'
import PageFrame from '../components/PageFrame.vue'
import LanguageSelect from '../components/LanguageSelect.vue'
import HintBadge from '../components/HintBadge.vue'
import { useRuntimesStore } from '../stores/runtimes'
import { useSettingsStore } from '../stores/settings'
import { useQueueStore } from '../stores/queue'
import type { RuntimeInfo } from '@shared/api'
import type { FolderKey, Settings } from '@shared/settings'
import { EDITION } from '@shared/edition'
import { qrSvg } from '../qr'
import { dateTime, dec, t, type PlainKey } from '../i18n'

const runtimes = useRuntimesStore()
const settings = useSettingsStore()
const queue = useQueueStore()

type Service = 'huggingface' | 'civitai'
const SERVICES: { id: Service; name: string; hint: PlainKey }[] = [
  { id: 'huggingface', name: 'Hugging Face', hint: 'settings.tokens.huggingfaceHint' },
  { id: 'civitai', name: 'Civitai', hint: 'settings.tokens.civitaiHint' },
]
const tokenInput = reactive<Record<Service, string>>({ huggingface: '', civitai: '' })
const tokenStored = reactive<Record<Service, boolean>>({ huggingface: false, civitai: false })
const about = ref<RuntimeInfo>()

/** bytes of encoded prompts on disk (Privacy) */
const promptCacheBytes = ref(0)

const remote = ref<{ running: boolean; addresses: string[]; https: boolean }>({ running: false, addresses: [], https: false })
/** the address whose link was just copied (its icon shows a tick for a moment) */
const copied = ref('')

async function refresh(): Promise<void> {
  await Promise.all([runtimes.refresh(), settings.load()])
  for (const s of SERVICES) tokenStored[s.id] = await window.vk.tokens.has(s.id)
  remote.value = await window.vk.remote.info()
  promptCacheBytes.value = await window.vk.app.promptCache()
}

async function clearPromptCache(): Promise<void> {
  await window.vk.app.clearPromptCache()
  promptCacheBytes.value = await window.vk.app.promptCache()
}

/** the address a device opens: one on the network, with the token in it */
const remoteLink = (address: string): string => address + '?t=' + encodeURIComponent(settings.values.remoteToken)

/** a scannable QR of the first link, so a phone or tablet can open the web UI without typing it */
const remoteQr = computed(() => {
  const a = remote.value.addresses[0]
  return a ? qrSvg(remoteLink(a)) : null
})

async function setRemote<K extends 'remoteAccess' | 'remotePort' | 'remoteHttps'>(key: K, value: Settings[K]): Promise<void> {
  await settings.set(key, value)
  remote.value = await window.vk.remote.info()
}

async function renewToken(): Promise<void> {
  if (!confirm(t('settings.remote.renewHint'))) return
  await settings.set('remoteToken', '')
  remote.value = await window.vk.remote.info()
}

/** text on the clipboard; key: which copy icon shows the tick for a moment */
async function copyText(key: string, text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    copied.value = key
    setTimeout(() => { copied.value = '' }, 1500)
  } catch {
    // no clipboard permission: the field is there to copy by hand
  }
}
const copyLink = (address: string): Promise<void> => copyText(address, remoteLink(address))
/** where a device installs the Mac's certificate authority (served by the web UI itself) */
const certLink = computed(() => (remote.value.https && remote.value.addresses[0] ? remote.value.addresses[0] + 'vulkara-ca.crt' : ''))
onActivated(refresh)

async function saveToken(service: Service, value: string): Promise<void> {
  await window.vk.tokens.set(service, value)
  tokenInput[service] = ''
  tokenStored[service] = await window.vk.tokens.has(service)
}

async function chooseFolder(key: FolderKey): Promise<void> {
  await settings.chooseFolder(key)
  if (key === 'runtimesDir') await runtimes.refresh()
}

async function defaultFolder(key: FolderKey): Promise<void> {
  await settings.set(key, '')
  if (key === 'runtimesDir') await runtimes.refresh()
}

// standard: a key (a text) or a path (shown as it is)
const FOLDERS: { key: FolderKey; title: PlainKey; standard: PlainKey | `~${string}`; hint?: PlainKey }[] = [
  { key: 'modelsDir', title: 'settings.folders.models', standard: '~/VulKara/models' },
  { key: 'lorasDir', title: 'settings.folders.loras', standard: '~/VulKara/loras' },
  { key: 'imagesDir', title: 'settings.folders.images', standard: '~/VulKara/images', hint: 'settings.folders.imagesHint' },
  { key: 'historyDir', title: 'settings.folders.history', standard: 'settings.folders.inAppData', hint: 'settings.folders.historyHint' },
  { key: 'helpersDir', title: 'settings.folders.helpers', standard: '~/VulKara', hint: 'settings.folders.helpersHint' },
  { key: 'runtimesDir', title: 'settings.folders.runtimes', standard: 'settings.folders.inAppData', hint: 'settings.folders.runtimesHint' },
  { key: 'streamCacheDir', title: 'settings.folders.streamCache', standard: 'settings.folders.streamCacheDefault', hint: 'settings.folders.streamCacheHint' },
]
const standard = (s: PlainKey | `~${string}`): string => (s.startsWith('~') ? s : t(s as PlainKey))

const when = (ts?: number): string => (ts ? dateTime(ts) : t('settings.runtimes.never'))

function updateTitle(rt: RuntimeInfo): string {
  const u = runtimes.updateOf(rt.id)
  const next = u?.components.filter((c) => c.updateAvailable).map((c) => `${c.name} ${c.latest}`).join(', ')
  return next ? t('settings.runtimes.updateTo', { next }) : t('settings.runtimes.installAgain')
}

function remove(rt: RuntimeInfo): void {
  if (confirm(t('settings.runtimes.confirmRemove', { name: rt.name, size: rt.sizeGb }))) void runtimes.remove(rt.id)
}

const THEMES: { id: 'system' | 'light' | 'dark'; title: PlainKey; icon: typeof Monitor }[] = [
  { id: 'system', title: 'settings.appearance.system', icon: Monitor },
  { id: 'light', title: 'settings.appearance.light', icon: Sun },
  { id: 'dark', title: 'settings.appearance.dark', icon: Moon },
]
</script>

<template>
  <PageFrame :title="t('settings.title')">
    <div class="wrap">
      <section>
        <h2>{{ t('settings.runtimes.title') }}</h2>
        <p class="dim">{{ t('settings.runtimes.intro') }}</p>
        <div v-if="runtimes.anyInstalled" class="checked">
          <span class="dim">
            {{ runtimes.updates.checking ? t('settings.runtimes.checking') : t('settings.runtimes.lastChecked', { when: when(runtimes.updates.checkedAt) }) }}
          </span>
          <button class="btn small" :disabled="runtimes.updates.checking" :title="t('settings.runtimes.checkNowHint')" @click="runtimes.checkUpdates()">
            <RefreshCw :size="12" :class="{ spin: runtimes.updates.checking }" /> {{ t('settings.runtimes.checkNow') }}
          </button>
          <span v-if="runtimes.checkError" class="error">{{ runtimes.checkError }}</span>
        </div>
        <div class="card list">
          <div v-for="rt in runtimes.list" :key="rt.id" class="row">
            <div class="grow">
              <div class="name">
                <strong>{{ rt.name }}</strong>
                <span v-if="rt.installed" class="tag ok">{{ rt.version || t('settings.runtimes.installed') }} · {{ dec(rt.sizeGb) }} GB</span>
                <button v-if="rt.details.length" class="btn small ghost" :title="t('settings.runtimes.howItWorks')" @click="about = about?.id === rt.id ? undefined : rt">
                  <Info :size="13" />
                </button>
              </div>
              <p class="dim">{{ rt.description }}</p>
              <ul v-if="about?.id === rt.id" class="details dim">
                <li v-for="d in rt.details" :key="d">{{ d }}</li>
              </ul>
              <template v-if="rt.installed && !(rt.id in runtimes.installing)">
                <div v-for="c in runtimes.updateOf(rt.id)?.components ?? []" :key="c.name" class="update">
                  <p v-if="c.updateAvailable" class="available">
                    <ArrowUpCircle :size="13" /> {{ t('settings.runtimes.updateAvailable', { name: c.name, installed: c.installed ?? '' }) }} <strong>{{ c.latest }}</strong>
                  </p>
                  <p v-else-if="c.installed && c.latest" class="dim">{{ t('settings.runtimes.upToDate', { name: c.name, installed: c.installed }) }}</p>
                  <p v-else-if="c.error" class="dim">{{ c.name }} {{ c.installed }}: {{ c.error }}</p>
                  <p v-else-if="!c.installed" class="dim">{{ t('settings.runtimes.versionUnknown', { name: c.name }) }}</p>
                  <p v-if="c.newest" class="dim">
                    {{ t('settings.runtimes.newerReleased', { name: c.name, newest: c.newest, latest: c.latest ?? '' }) }}
                  </p>
                  <p v-if="c.error && c.latest" class="dim">{{ t('settings.runtimes.lastCheck', { error: c.error }) }}</p>
                </div>
              </template>
              <template v-if="rt.id in runtimes.installing">
                <div class="bar unknown"><i /></div>
                <p class="dim">{{ runtimes.installing[rt.id] }}</p>
              </template>
              <p v-if="runtimes.errors[rt.id]" class="error selectable">{{ runtimes.errors[rt.id] }}</p>
            </div>
            <button v-if="!rt.installed" class="btn primary" :disabled="rt.id in runtimes.installing || !!queue.running" @click="runtimes.install(rt.id)">
              <Download :size="14" /> {{ t('settings.runtimes.install') }}
            </button>
            <template v-else>
              <button
                class="btn" :class="{ primary: runtimes.updateOf(rt.id)?.updateAvailable }"
                :disabled="rt.id in runtimes.installing || !!queue.running" :title="updateTitle(rt)" @click="runtimes.install(rt.id)"
              >
                {{ t('settings.runtimes.update') }}
              </button>
              <button class="btn danger" :disabled="rt.id in runtimes.installing || !!queue.running" :title="t('settings.runtimes.remove')" @click="remove(rt)">
                <Trash2 :size="14" />
              </button>
            </template>
          </div>
        </div>
      </section>

      <section>
        <h2>{{ t('settings.folders.title') }}</h2>
        <p v-if="settings.error" class="error">{{ settings.error }}</p>
        <div class="card list">
          <div v-for="f in FOLDERS" :key="f.key" class="row">
            <div class="grow">
              <strong>{{ t(f.title) }}</strong>
              <p class="dim selectable">{{ settings.values[f.key] || standard(f.standard) }}</p>
              <p v-if="f.hint" class="dim">{{ t(f.hint) }}</p>
            </div>
            <button v-if="settings.values[f.key]" class="btn" @click="defaultFolder(f.key)">{{ t('settings.folders.default') }}</button>
            <button class="btn" @click="chooseFolder(f.key)"><FolderOpen :size="14" /> {{ t('settings.folders.choose') }}</button>
          </div>
        </div>
      </section>

      <section>
        <h2>{{ t('settings.engine.title') }}</h2>
        <div class="card list">
          <label class="row">
            <div class="grow">
              <strong>{{ t('settings.engine.runtime') }}</strong>
              <p class="dim">{{ t('settings.engine.runtimeHint') }}</p>
            </div>
            <select :value="settings.values.runtime" @change="settings.set('runtime', ($event.target as HTMLSelectElement).value as 'auto')">
              <option value="auto">{{ t('settings.engine.automatic') }}</option>
              <option value="diffusers">Diffusers</option>
              <option value="mlx">MLX</option>
            </select>
          </label>
          <label class="row">
            <div class="grow">
              <strong>{{ t('settings.engine.quant') }}</strong>
              <p class="dim">{{ t('settings.engine.quantHint') }}</p>
            </div>
            <select :value="settings.values.defaultQuant" @change="settings.set('defaultQuant', ($event.target as HTMLSelectElement).value as 'auto')">
              <option value="auto">{{ t('settings.engine.whenNeeded') }}</option>
              <option value="none">{{ t('settings.engine.never') }}</option>
              <option value="q8">{{ t('settings.engine.bit8') }}</option>
              <option value="q4">{{ t('settings.engine.bit4') }}</option>
            </select>
          </label>
          <label class="row">
            <div class="grow">
              <strong>{{ t('settings.engine.reserve') }}</strong>
              <p class="dim">{{ t('settings.engine.reserveHint') }}</p>
            </div>
            <input
              type="number" min="0" max="256" :value="settings.values.memoryReserveGb"
              @change="settings.set('memoryReserveGb', Number(($event.target as HTMLInputElement).value) || 0)"
            />
            <span class="dim">GB</span>
          </label>
          <label class="row">
            <div class="grow">
              <strong>{{ t('settings.engine.streaming') }}</strong>
              <p class="dim">{{ t('settings.engine.streamingHint') }}</p>
            </div>
            <select :value="settings.values.ssdStreaming" @change="settings.set('ssdStreaming', ($event.target as HTMLSelectElement).value as 'auto')">
              <option value="auto">{{ t('settings.engine.whenNeeded') }}</option>
              <option value="always">{{ t('settings.engine.always') }}</option>
              <option value="off">{{ t('settings.engine.never') }}</option>
            </select>
          </label>
          <label class="row">
            <div class="grow">
              <strong>{{ t('settings.engine.comfyStreaming') }} <HintBadge start :text="t('settings.engine.comfyStreamingDetails')" /></strong>
              <p class="dim">{{ t('settings.engine.comfyStreamingHint') }}</p>
            </div>
            <input type="checkbox" :checked="settings.values.comfyStreaming" @change="settings.set('comfyStreaming', ($event.target as HTMLInputElement).checked)" />
          </label>
          <label class="row">
            <div class="grow">
              <strong>{{ t('settings.engine.idleUnload') }}</strong>
              <p class="dim">{{ t('settings.engine.idleUnloadHint') }}</p>
            </div>
            <select :value="settings.values.idleUnloadMinutes" @change="settings.set('idleUnloadMinutes', Number(($event.target as HTMLSelectElement).value))">
              <option v-for="n in [5, 10, 30, 60]" :key="n" :value="n">{{ t('settings.engine.afterMinutes', { n }) }}</option>
              <option :value="0">{{ t('settings.engine.never') }}</option>
            </select>
          </label>
          <label class="row">
            <div class="grow">
              <strong>{{ t('settings.engine.stepCache') }}</strong>
              <p class="dim">{{ t('settings.engine.stepCacheHint') }}</p>
            </div>
            <select :value="settings.values.stepCache" @change="settings.set('stepCache', ($event.target as HTMLSelectElement).value as 'off')">
              <option value="off">{{ t('settings.engine.off') }}</option>
              <option value="light">{{ t('settings.engine.light') }}</option>
              <option value="strong">{{ t('settings.engine.strong') }}</option>
            </select>
          </label>
        </div>
      </section>

      <section>
        <h2>{{ t('settings.appearance.title') }}</h2>
        <div class="card list">
          <div class="row">
            <div class="grow">
              <strong>{{ t('settings.appearance.theme') }}</strong>
              <p class="dim">{{ t('settings.appearance.themeHint') }}</p>
            </div>
            <div class="tabs segmented" role="radiogroup" :aria-label="t('settings.appearance.title')">
              <button
                v-for="th in THEMES" :key="th.id" role="radio" :aria-checked="settings.values.theme === th.id"
                :class="{ on: settings.values.theme === th.id }" @click="settings.set('theme', th.id)"
              >
                <component :is="th.icon" :size="13" /> {{ t(th.title) }}
              </button>
            </div>
          </div>
          <div class="row">
            <div class="grow">
              <strong>{{ t('settings.appearance.language') }}</strong>
              <p class="dim">{{ t('settings.appearance.languageHint') }}</p>
            </div>
            <LanguageSelect />
          </div>
        </div>
      </section>

      <section>
        <h2>{{ t('settings.content.title') }}</h2>
        <div class="card list">
          <label v-if="EDITION.explicitContent === 'choice'" class="row">
            <div class="grow">
              <strong>{{ t('settings.content.nudity') }}</strong>
              <p class="dim">{{ t('settings.content.nudityHint') }}</p>
            </div>
            <input type="checkbox" :checked="settings.values.allowExplicit" @change="settings.set('allowExplicit', ($event.target as HTMLInputElement).checked)" />
          </label>
          <label class="row">
            <div class="grow"><strong>{{ t('settings.content.sound') }}</strong></div>
            <input type="checkbox" :checked="settings.values.notifySound" @change="settings.set('notifySound', ($event.target as HTMLInputElement).checked)" />
          </label>
        </div>
      </section>

      <section>
        <h2>{{ t('settings.remote.title') }}</h2>
        <p class="dim">{{ t('settings.remote.intro') }}</p>
        <div class="card list">
          <label class="row">
            <div class="grow">
              <strong>{{ t('settings.remote.enable') }}</strong>
              <p class="dim">{{ remote.running ? t('settings.remote.running') : t('settings.remote.offline') }}</p>
            </div>
            <input type="checkbox" :checked="settings.values.remoteAccess" @change="setRemote('remoteAccess', ($event.target as HTMLInputElement).checked)" />
          </label>
          <template v-if="settings.values.remoteAccess">
            <div class="row">
              <div class="grow"><strong>{{ t('settings.remote.port') }}</strong></div>
              <input
                class="port" type="number" min="1024" max="65535" :value="settings.values.remotePort"
                @change="setRemote('remotePort', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <label class="row">
              <div class="grow">
                <strong>{{ t('settings.remote.https') }}</strong>
                <p class="dim">{{ t('settings.remote.httpsHint') }}</p>
              </div>
              <input type="checkbox" :checked="settings.values.remoteHttps" @change="setRemote('remoteHttps', ($event.target as HTMLInputElement).checked)" />
            </label>
            <div class="row">
              <div class="grow">
                <strong>{{ t('settings.remote.reach') }}</strong>
                <p v-for="a in remote.addresses" :key="a" class="link-line">
                  <span class="dim selectable link">{{ remoteLink(a) }}</span>
                  <!-- the label is a panel of its own: the system tooltip (title) does not show reliably in the app -->
                  <span class="icon-tip">
                    <button class="btn small icon" :aria-label="t('settings.remote.copyLink')" @click="copyLink(a)">
                      <Check v-if="copied === a" :size="13" /><Copy v-else :size="13" />
                    </button>
                    <span class="tip" role="tooltip">{{ copied === a ? t('settings.remote.copied') : t('settings.remote.copyLink') }}</span>
                  </span>
                </p>
                <p v-if="!remote.addresses.length" class="dim">—</p>
                <p class="dim">{{ t('settings.remote.reachHint') }}</p>
                <p class="dim">{{ t('settings.remote.firewall') }}</p>
              </div>
            </div>
            <div v-if="remoteQr" class="row qr">
              <!-- eslint-disable-next-line vue/no-v-html -- our own QR, no user input -->
              <div class="qr-box" v-html="remoteQr"></div>
              <p class="dim grow">{{ t('settings.remote.scan') }}</p>
            </div>
            <div v-if="certLink" class="row">
              <div class="grow">
                <strong>{{ t('settings.remote.certificate') }}</strong>
                <p class="link-line">
                  <span class="dim selectable link">{{ certLink }}</span>
                  <span class="icon-tip">
                    <button class="btn small icon" :aria-label="t('settings.remote.copyLink')" @click="copyText('ca', certLink)">
                      <Check v-if="copied === 'ca'" :size="13" /><Copy v-else :size="13" />
                    </button>
                    <span class="tip" role="tooltip">{{ copied === 'ca' ? t('settings.remote.copied') : t('settings.remote.copyLink') }}</span>
                  </span>
                </p>
                <p class="dim">{{ t('settings.remote.certificateHint') }}</p>
              </div>
            </div>
            <div class="row">
              <div class="grow">
                <strong>{{ t('settings.remote.token') }}</strong>
                <p class="dim selectable">{{ settings.values.remoteToken }}</p>
              </div>
              <button class="btn" @click="renewToken"><RefreshCw :size="14" /> {{ t('settings.remote.renew') }}</button>
            </div>
          </template>
        </div>
      </section>

      <section>
        <h2>{{ t('settings.privacy.title') }}</h2>
        <p class="dim">{{ t('settings.privacy.intro') }}</p>
        <div class="card list">
          <label class="row">
            <div class="grow">
              <strong>{{ t('settings.privacy.hashLookups') }}</strong>
              <p class="dim">{{ t('settings.privacy.hashLookupsHint') }}</p>
            </div>
            <input type="checkbox" :checked="settings.values.hashLookups" @change="settings.set('hashLookups', ($event.target as HTMLInputElement).checked)" />
          </label>
          <label class="row">
            <div class="grow">
              <strong>{{ t('settings.privacy.updateChecks') }}</strong>
              <p class="dim">{{ t('settings.privacy.updateChecksHint') }}</p>
            </div>
            <input type="checkbox" :checked="settings.values.updateChecks" @change="settings.set('updateChecks', ($event.target as HTMLInputElement).checked)" />
          </label>
          <div class="row">
            <div class="grow">
              <strong>{{ t('settings.privacy.promptCache') }}</strong>
              <p class="dim">{{ t('settings.privacy.promptCacheHint', { mb: dec(Math.round(promptCacheBytes / 1e5) / 10) }) }}</p>
            </div>
            <button class="btn small" :disabled="!promptCacheBytes" @click="clearPromptCache"><Trash2 :size="13" /> {{ t('settings.privacy.promptCacheClear') }}</button>
          </div>
        </div>
      </section>

      <section>
        <h2>{{ t('settings.tokens.title') }}</h2>
        <p class="dim">{{ t('settings.tokens.intro') }}</p>
        <div class="card list">
          <div v-for="s in SERVICES" :key="s.id" class="row">
            <div class="grow">
              <div class="name">
                <strong>{{ s.name }}</strong>
                <span v-if="tokenStored[s.id]" class="tag ok">{{ t('settings.tokens.stored') }}</span>
              </div>
              <p class="dim">{{ t(s.hint) }}</p>
            </div>
            <input v-model="tokenInput[s.id]" type="password" :placeholder="t('settings.tokens.paste')" autocomplete="off" class="token" />
            <button class="btn" :disabled="!tokenInput[s.id].trim()" @click="saveToken(s.id, tokenInput[s.id])">{{ t('settings.tokens.save') }}</button>
            <button v-if="tokenStored[s.id]" class="btn danger" :title="t('settings.tokens.remove')" @click="saveToken(s.id, '')"><Trash2 :size="14" /></button>
          </div>
        </div>
      </section>
    </div>
  </PageFrame>
</template>

<style scoped>
.wrap {
  max-width: 760px;
  display: grid;
  gap: 28px;
}

section {
  display: grid;
  gap: 8px;
}

.row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
}

.row + .row {
  border-top: 1px solid var(--line);
}

.grow {
  flex: 1;
  min-width: 0;
}

.name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tag {
  padding: 1px 7px;
  border-radius: 9px;
  background: var(--surface-2);
  font-size: 11px;
}

.tag.ok {
  color: var(--ok);
}

.checked {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.update p {
  margin: 4px 0 0;
}

.available {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--accent);
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.details {
  margin: 8px 0 0;
  padding-left: 18px;
  display: grid;
  gap: 4px;
}

.bar {
  margin: 10px 0 4px;
  max-width: 320px;
}

input[type='number'] {
  width: 72px;
}

.token {
  width: 190px;
}

input[type='checkbox'] {
  width: 16px;
  height: 16px;
  accent-color: var(--accent);
}

.segmented {
  flex: none;
}

.segmented button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
}

.port {
  width: 92px;
}

.link {
  overflow-wrap: anywhere;
}

/* a link on the left, its copy icon on the right edge like the other controls of the card */
.link-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 0;
}

.link-line .link {
  min-width: 0;  /* a long link wraps instead of pushing the icon out */
}

/* an empty line between the links and the hints below them */
.link-line + p:not(.link-line) {
  margin-top: 1.45em;
}

.btn.icon {
  width: 24px;
  padding: 0;
  justify-content: center;
}

/* the icon's label: a small panel below it while the pointer is on it (or it has the focus) */
.icon-tip {
  position: relative;
  display: inline-flex;
  flex: none;
}

.tip {
  display: none;
  position: absolute;
  z-index: 20;
  top: calc(100% + 6px);
  right: 0;
  padding: 5px 9px;
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  background: var(--surface);
  box-shadow: var(--shadow);
  color: var(--text);
  font-size: 11.5px;
  white-space: nowrap;
}

.icon-tip:hover .tip,
.icon-tip:focus-within .tip {
  display: block;
}

.row.qr {
  align-items: center;
}
.qr-box {
  width: 132px;
  flex: none;
  padding: 8px;
  background: #fff;
  border-radius: 8px;
}
.qr-box :deep(svg) {
  display: block;
  width: 100%;
  height: auto;
}
</style>