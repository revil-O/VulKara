<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
import { computed, onActivated } from 'vue'
import { Check, ChevronRight, Circle } from '@lucide/vue'
import PageFrame from '../components/PageFrame.vue'
import LanguageSelect from '../components/LanguageSelect.vue'
import { useAssetsStore } from '../stores/assets'
import { useRuntimesStore } from '../stores/runtimes'
import { useSettingsStore } from '../stores/settings'
import { t } from '../i18n'

const runtimes = useRuntimesStore()
const assets = useAssetsStore()
const settings = useSettingsStore()
onActivated(() => Promise.all([assets.refresh(), runtimes.refresh(), settings.load()]))

const steps = computed(() => [
  {
    done: runtimes.anyInstalled, title: t('common.start.runtime'), to: '/settings',
    text: t('common.start.runtimeText'),
  },
  {
    done: assets.models.length > 0, title: t('common.start.model'), to: '/models',
    text: t('common.start.modelText'),
  },
  {
    done: settings.values.firstPictureMade, title: t('common.start.picture'), to: '/text',
    text: t('common.start.pictureText'),
  },
])
</script>

<template>
  <PageFrame title="VulKara" :subtitle="t('common.start.subtitle')">
    <template #actions><LanguageSelect icon /></template>
    <div class="wrap">
      <div class="card setup">
        <h2>{{ t('common.start.gettingStarted') }}</h2>
        <RouterLink v-for="s in steps" :key="s.to" :to="s.to" class="step" :class="{ done: s.done }">
          <component :is="s.done ? Check : Circle" :size="18" class="mark" />
          <div>
            <strong>{{ s.title }}</strong>
            <p class="dim">{{ s.text }}</p>
          </div>
          <ChevronRight :size="16" class="dim" />
        </RouterLink>
      </div>
      <div class="card facts">
        <div><strong>{{ runtimes.list.filter((r) => r.installed).length }}</strong><span class="dim">{{ t('common.start.runtimesInstalled') }}</span></div>
        <div><strong>{{ assets.models.length }}</strong><span class="dim">{{ t('common.start.models') }}</span></div>
        <div><strong>{{ assets.loras.length }}</strong><span class="dim">LoRAs</span></div>
      </div>
    </div>
  </PageFrame>
</template>

<style scoped>
.wrap {
  max-width: 720px;
  display: grid;
  gap: 16px;
}

.setup h2 {
  padding: 16px 18px 8px;
}

.step {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 18px;
  color: inherit;
  text-decoration: none;
  border-top: 1px solid var(--line);
}

.step:hover {
  background: var(--surface-2);
}

.step > div {
  flex: 1;
}

.mark {
  color: var(--text-dim);
  flex: none;
}

.done .mark {
  color: var(--ok);
}

.facts {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
}

.facts > div {
  display: flex;
  flex-direction: column;
  padding: 14px 18px;
}

.facts > div + div {
  border-left: 1px solid var(--line);
}

.facts strong {
  font-size: 22px;
  font-weight: 650;
}
</style>
