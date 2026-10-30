<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// What changed from version to version: the changelog shipped with the app, newest first.
import { onMounted, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { RefreshCw } from 'lucide-vue-next'
import PageFrame from '../components/PageFrame.vue'
import { isRemote } from '../remote_vk'
import { parseChangelog } from '../util/changelog'
import { useAppUpdateStore } from '../stores/appUpdate'
import { t } from '../i18n'
import text from '../../../../CHANGELOG.md?raw'
import type { AppUpdateState } from '@shared/api'

const versions = parseChangelog(text)
const installed = ref('')
// the app's update check (the banner offers the update itself); not in the remote web UI
const remote = isRemote()
const updates = useAppUpdateStore()
const { state: update } = storeToRefs(updates)
onMounted(async () => {
  installed.value = (await window.vk.app.info()).version
  if (!remote) updates.start()
})
function check(): void {
  void window.vk.app.checkUpdate()
}
function updateLine(u: AppUpdateState): string {
  if (u.checking) return t('app.changelog.checking')
  if (u.available) return t('app.changelog.newer', { version: u.available })
  if (u.checkError) return t('app.changelog.checkFailed', { reason: u.checkError })
  return u.checkedAt ? t('app.changelog.upToDate', { when: new Date(u.checkedAt).toLocaleString() }) : t('app.changelog.notChecked')
}
</script>

<template>
  <PageFrame :title="t('app.changelog.title')" :subtitle="installed ? t('app.changelog.subtitleVersion', { version: installed }) : t('app.changelog.subtitle')">
    <article class="changelog selectable">
      <div v-if="update" class="check">
        <span class="dim">{{ updateLine(update) }}</span>
        <button class="btn small" :disabled="update.checking" @click="check">
          <RefreshCw :size="12" /> {{ t('app.changelog.checkNow') }}
        </button>
      </div>
      <section v-for="v in versions" :key="v.version">
        <h2>
          <!-- i18n-ok -->
          {{ v.version === 'Unreleased' ? t('app.changelog.unreleased') : t('app.changelog.version', { version: v.version }) }}
          <span v-if="v.version === installed" class="installed">{{ t('app.changelog.installed') }}</span>
        </h2>
        <!-- eslint-disable-next-line vue/no-v-html -- escaped by parseChangelog -->
        <p v-for="(p, i) in v.intro" :key="'p' + i" v-html="p" />
        <ul>
          <!-- eslint-disable-next-line vue/no-v-html -- escaped by parseChangelog -->
          <li v-for="(item, i) in v.items" :key="i" v-html="item" />
        </ul>
      </section>
    </article>
  </PageFrame>
</template>

<style scoped>
.check {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.changelog {
  display: grid;
  gap: 18px;
  max-width: 900px;
  line-height: 1.55;
}

h2 {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 0 0 6px;
  font-size: 16px;
}

.installed {
  padding: 1px 8px;
  border-radius: 9px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 11px;
  font-weight: 500;
}

p {
  margin: 0 0 6px;
}

ul {
  margin: 0;
  padding-left: 20px;
  display: grid;
  gap: 5px;
}

:deep(code) {
  font: 12px var(--mono);
}
</style>
