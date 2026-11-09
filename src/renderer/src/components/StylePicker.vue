<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Choosing a style: the current one as a button, the styles by group with a preview picture each when opened.
import { computed, ref } from 'vue'
import { ChevronDown } from '@lucide/vue'
import { STYLES, STYLE_GROUPS, styleSlug } from '@shared/styles'
import { t } from '../i18n'
import { styleLabel } from '../util/labels'

/** the name of the style, '' for none */
const style = defineModel<string>({ required: true })
const open = ref(false)

const pictures = import.meta.glob<string>('../assets/styles/*.jpg', { eager: true, import: 'default' })
const picture = (name: string): string => pictures[`../assets/styles/${name ? styleSlug(name) : 'none'}.jpg`] ?? ''
const current = computed(() => STYLES.find((s) => s.name === style.value))
const groups = STYLE_GROUPS.map((g) => ({ ...g, styles: STYLES.filter((s) => s.group === g.id) }))

function choose(name: string): void {
  style.value = name
  open.value = false
}
</script>

<template>
  <div class="picker">
    <button class="current" :class="{ open }" @click="open = !open">
      <img :src="picture(current?.name ?? '')" draggable="false" />
      <span class="name">
        <strong>{{ current ? styleLabel(current.name) : t('generate.styles.none') }}</strong>
        <small class="dim">{{ t(current?.hint ?? 'generate.styles.noneHint') }}</small>
      </span>
      <ChevronDown :size="14" class="dim" :class="{ turned: open }" />
    </button>
    <div v-if="open" class="choices">
      <button class="style none" :class="{ on: !current }" @click="choose('')">
        <img :src="picture('')" draggable="false" />
        <span>{{ t('generate.styles.none') }}</span>
      </button>
      <template v-for="g in groups" :key="g.id">
        <p class="dim group">{{ t(g.title) }}</p>
        <button v-for="s in g.styles" :key="s.name" class="style" :class="{ on: s.name === style }" :title="t(s.hint)" @click="choose(s.name)">
          <img :src="picture(s.name)" loading="lazy" draggable="false" />
          <span>{{ styleLabel(s.name) }}</span>
        </button>
      </template>
    </div>
  </div>
</template>

<style scoped>
.current {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 5px 10px 5px 5px;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface-2);
  text-align: left;
}

.current.open {
  border-color: var(--accent);
}

.current img {
  width: 40px;
  height: 40px;
  border-radius: 4px;
  object-fit: cover;
}

.name {
  flex: 1;
  min-width: 0;
  display: grid;
}

.turned {
  transform: rotate(180deg);
}

.choices {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  margin-top: 8px;
}

.group {
  grid-column: 1 / -1;
  margin-top: 6px;
  padding: 3px 8px;
  border: 1px solid var(--accent);
  border-radius: var(--radius-s);
  color: var(--accent);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.style {
  display: grid;
  gap: 3px;
  padding: 3px 3px 4px;
  border: 1px solid transparent;
  border-radius: var(--radius-s);
  background: transparent;
  font-size: 11px;
  line-height: 1.2;
  min-width: 0;
}

.style:hover {
  background: var(--surface-2);
}

.style.on {
  border-color: var(--accent);
  color: var(--accent);
}

.style img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 4px;
}

.style span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
