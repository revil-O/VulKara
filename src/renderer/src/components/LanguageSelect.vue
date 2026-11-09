<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// The app's language: System (macOS's) or one of the four, each under its own name. Settings → Appearance and the
// Start page; icon: with the Languages icon in front (the Start page, where it stands alone).
import { computed, ref, watch } from 'vue'
import { Languages } from '@lucide/vue'
import { LANG_NAMES, LANGS, type LangSetting } from '@shared/i18n'
import { useSettingsStore } from '../stores/settings'
import { isRemote } from '../remote_vk'
import { setLang, storedLang, t } from '../i18n'

defineProps<{ icon?: boolean }>()
const settings = useSettingsStore()
const LANGUAGES: LangSetting[] = ['system', ...LANGS]
const langName = (l: LangSetting): string => (l === 'system' ? t('settings.appearance.system') : LANG_NAMES[l])

// a browser (remote web UI) switches its own language and cannot write the Mac's settings; the app writes them
const chosen = ref<LangSetting>(isRemote() ? storedLang() : settings.values.language)
watch(() => settings.values.language, (v) => { if (!isRemote()) chosen.value = v })
const current = computed(() => chosen.value)
function change(value: LangSetting): void {
  chosen.value = value
  if (isRemote()) void setLang(value)
  else void settings.set('language', value)
}
</script>

<template>
  <label class="language" :class="{ icon }">
    <Languages v-if="icon" :size="14" class="dim" />
    <select
      :value="current" :aria-label="t('settings.appearance.language')"
      @change="change(($event.target as HTMLSelectElement).value as LangSetting)"
    >
      <option v-for="l in LANGUAGES" :key="l" :value="l">{{ langName(l) }}</option>
    </select>
  </label>
</template>

<style scoped>
.language {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
</style>
