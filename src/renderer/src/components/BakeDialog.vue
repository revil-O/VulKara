<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// LoRAs baked into a new model of its own (engines/diffusers/merge.py): a base model, one or more LoRAs with their
// strength, a name. The new model needs no LoRA any more and shows up under Models; the work runs in the import
// queue, its progress shows here.
import { computed, onMounted, ref, watch } from 'vue'
import { Flame, Plus, X } from '@lucide/vue'
import HintBadge from './HintBadge.vue'
import { useAssetsStore } from '../stores/assets'
import { useImportsStore } from '../stores/imports'
import { cleanError } from '../stores/runtimes'
import { num, t } from '../i18n'
import { loraFits } from '@shared/lora_fit'
import type { Asset } from '@shared/types'

const props = defineProps<{ loraIds: string[]; modelId?: string }>()
const emit = defineEmits<{ close: [] }>()
const assets = useAssetsStore()
const imports = useImportsStore()

const dialog = ref<HTMLDialogElement>()
const modelId = ref(props.modelId ?? '')
const chosen = ref<{ id: string; scale: number }[]>(props.loraIds.map((id) => ({ id, scale: 1 })))
const name = ref('')
const nameEdited = ref(false)
const error = ref('')
const importId = ref('')

const loraOf = (id: string): Asset | undefined => assets.loras.find((l) => l.id === id)
const model = computed(() => assets.models.find((m) => m.id === modelId.value))
// the models every chosen LoRA fits; those that can not take a LoRA baked in say why
const candidates = computed(() => assets.models.filter((m) => m.meta.kind === 'image'
  && chosen.value.every((c) => { const l = loraOf(c.id); return l ? loraFits(l, m) : true })))
const addable = computed(() => assets.loras.filter((l) => !chosen.value.some((c) => c.id === l.id)
  && (!model.value || loraFits(l, model.value))))
const job = computed(() => imports.jobs.find((j) => j.id === importId.value))
const working = computed(() => job.value?.state === 'waiting' || job.value?.state === 'running')
const blocked = computed(() => {
  if (!model.value) return t('models.bake.chooseModel')
  if (model.value.meta.bakeBlocked) return model.value.meta.bakeBlocked
  if (!chosen.value.length) return t('models.bake.chooseLora')
  return ''
})

watch([model, chosen], () => {
  if (nameEdited.value || !model.value) return
  name.value = [model.value.title, ...chosen.value.map((c) => loraOf(c.id)?.title ?? '')].filter(Boolean).join(' + ')
}, { deep: true, immediate: true })

onMounted(() => {
  void imports.start()
  if (!modelId.value) modelId.value = candidates.value.find((m) => !m.meta.bakeBlocked)?.id ?? candidates.value[0]?.id ?? ''
  dialog.value?.showModal()
})

function add(id: string): void {
  if (id) chosen.value = [...chosen.value, { id, scale: 1 }]
}

async function bake(): Promise<void> {
  error.value = blocked.value
  if (error.value) return
  try {
    importId.value = await window.vk.assets.bake(modelId.value, chosen.value.map((c) => ({ ...c })), name.value.trim())
  } catch (err) {
    error.value = cleanError(err)
  }
}

const close = (): void => emit('close')
</script>

<template>
  <!-- @close: Escape may close a modal dialog without a cancel event -->
  <dialog ref="dialog" class="bake" @cancel.prevent="close" @close="close">
    <div class="inner">
      <header>
        <h2 class="grow">{{ t('models.bake.title') }}</h2>
        <button class="btn small ghost" :aria-label="t('common.close')" @click="close"><X :size="14" /></button>
      </header>
      <p class="dim">
        {{ t('models.bake.intro') }}
        <HintBadge start :text="t('models.bake.introHint')" />
      </p>

      <label class="field">
        <span>{{ t('models.bake.baseModel') }}</span>
        <select v-model="modelId" class="entry" :disabled="working">
          <option v-for="m in candidates" :key="m.id" :value="m.id" :disabled="!!m.meta.bakeBlocked">
            {{ m.meta.bakeBlocked ? t('models.bake.notPossible', { name: m.title }) : m.title }}
          </option>
        </select>
        <small v-if="model?.meta.bakeBlocked" class="error">{{ model.meta.bakeBlocked }}</small>
      </label>

      <div class="field">
        <span>{{ t('models.bake.loras') }}</span>
        <div v-for="(c, i) in chosen" :key="c.id" class="lora">
          <span class="grow">{{ loraOf(c.id)?.title ?? c.id }}</span>
          <input v-model.number="c.scale" type="range" min="0.1" max="1.5" step="0.05" :disabled="working" :aria-label="t('models.bake.strength')" />
          <b class="num">{{ num(c.scale, 2) }}</b>
          <button class="btn small ghost" :aria-label="t('common.remove')" :disabled="working" @click="chosen = chosen.filter((_x, j) => j !== i)"><X :size="12" /></button>
        </div>
        <label v-if="addable.length && !working" class="add">
          <Plus :size="13" />
          <select class="entry" :value="''" @change="add(($event.target as HTMLSelectElement).value)">
            <option value="">{{ t('models.bake.addLora') }}</option>
            <option v-for="l in addable" :key="l.id" :value="l.id">{{ l.title }}</option>
          </select>
        </label>
      </div>

      <label class="field">
        <span>{{ t('models.bake.name') }}</span>
        <input v-model="name" class="entry" type="text" maxlength="120" spellcheck="false" :disabled="working" @input="nameEdited = true" />
      </label>

      <p v-if="error" class="error selectable">{{ error }}</p>
      <template v-if="job">
        <div class="bar" :class="{ unknown: job.percent < 0 }"><i :style="job.percent >= 0 ? { width: job.percent + '%' } : {}" /></div>
        <p class="dim">
          <template v-if="working">{{ job.stage || t('models.bake.waiting') }}</template>
          <template v-else-if="job.state === 'done'">{{ t('models.bake.done', { name }) }}</template>
          <span v-else class="error selectable">{{ job.error || t('models.bake.stopped') }}</span>
        </p>
      </template>

      <footer>
        <button class="btn" @click="close">{{ job?.state === 'done' ? t('common.close') : t('common.cancel') }}</button>
        <button v-if="job?.state !== 'done'" class="btn primary" :disabled="working || !!blocked" @click="bake"><Flame :size="14" /> {{ t('models.bake.bake') }}</button>
      </footer>
    </div>
  </dialog>
</template>

<style scoped>
.bake {
  width: min(560px, calc(100vw - 80px));
  padding: 0;
  border: 1px solid var(--line);
  border-radius: var(--radius-l);
  background: var(--bg);
  color: var(--text);
  box-shadow: var(--shadow);
}

.bake::backdrop {
  background: rgba(0, 0, 0, 0.45);
}

.inner {
  display: grid;
  gap: 14px;
  padding: 18px 20px;
}

header,
footer {
  display: flex;
  align-items: center;
  gap: 10px;
}

footer {
  justify-content: flex-end;
}

h2 {
  margin: 0;
  font-size: 16px;
}

.grow {
  flex: 1;
  min-width: 0;
}


.lora {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lora input[type='range'] {
  width: 150px;
  accent-color: var(--accent);
}

.num {
  min-width: 36px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.add {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-dim);
}

.bar {
  height: 4px;
  border-radius: 2px;
  background: var(--line);
  overflow: hidden;
}

.bar i {
  display: block;
  height: 100%;
  background: var(--accent);
}

.bar.unknown i {
  width: 30%;
  animation: slide 1.2s ease-in-out infinite;
}

@keyframes slide {
  from {
    transform: translateX(-100%);
  }

  to {
    transform: translateX(340%);
  }
}
</style>
