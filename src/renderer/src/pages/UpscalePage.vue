<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// Enlarging a picture to twice or four times its size with an upscaling model. It needs no model of the user:
// the ComfyUI runtime does it with Real-ESRGAN, which is downloaded on first use.
import { computed, onActivated, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Maximize2 } from '@lucide/vue'
import PageFrame from '../components/PageFrame.vue'
import ImageInput from '../components/ImageInput.vue'
import FactorPicker from '../components/FactorPicker.vue'
import JobGallery from '../components/JobGallery.vue'
import { useHandoffStore } from '../stores/handoff'
import { useQueueStore } from '../stores/queue'
import { cleanError, useRuntimesStore } from '../stores/runtimes'
import { t } from '../i18n'
import type { QueuedJob } from '@shared/api'
import type { Job } from '@shared/types'

const MAX_SIDE = 2048
const queue = useQueueStore()
const runtimes = useRuntimesStore()
const handoff = useHandoffStore()
const route = useRoute()

const input = ref('')
const size = ref<[number, number]>()
const factor = ref(4)
const error = ref('')
const comfyInstalled = computed(() => runtimes.list.some((r) => r.id === 'comfyui' && r.installed))
// a picture over MAX_SIDE is made smaller to it first; the result is factor times the picture, at most four times that
const target = computed((): [number, number] | undefined => {
  if (!size.value) return undefined
  const k = Math.min(1, MAX_SIDE / Math.max(...size.value))
  const side = (v: number): number => Math.min(Math.round(v * factor.value), Math.round(v * k) * 4)
  return [side(size.value[0]), side(size.value[1])]
})
const result = computed(() => (target.value ? `${target.value[0]} × ${target.value[1]}` : ''))
const jobs = computed(() => queue.ofPage('upscale'))

async function refresh(): Promise<void> {
  await runtimes.refresh()
  const given = handoff.take('upscale')
  if (given?.inputImage) input.value = given.inputImage
}
onActivated(refresh)
watch(() => route.query.t, () => { if (route.path === '/upscale') void refresh() })
watch(input, () => {
  size.value = undefined
  error.value = ''
})

async function enlarge(): Promise<void> {
  error.value = !input.value ? t('edit.upscale.choosePicture') : ''
  if (error.value || !size.value) return
  try {
    await queue.add({ page: 'upscale', prompt: '', modelId: '', modelDir: '', width: target.value![0], height: target.value![1], seed: 0, inputImage: input.value, upscale: factor.value, label: `Upscale ×${factor.value}` }) // i18n-ok
  } catch (err) {
    error.value = cleanError(err)
  }
}

function open(q: QueuedJob, file: string): void {
  const pictures = jobs.value.flatMap((x) => queue.shown(x).map((f) => ({ job: JSON.parse(JSON.stringify(x.job)) as Job, file: f, model: 'Real-ESRGAN' })))
  void window.vk.viewer.open(pictures, pictures.findIndex((p) => p.file === file && p.job.id === q.job.id))
}
</script>

<template>
  <PageFrame :title="t('edit.upscale.title')" :subtitle="t('edit.upscale.subtitle')">
    <div class="page-grid">
      <ImageInput v-model="input" @size="(w, h) => (size = [w, h])" />
      <div class="send">
        <span v-if="error" class="error selectable">{{ error }}</span>
        <span v-else-if="size" class="dim">{{ t('edit.becomes', { size: `${size[0]} × ${size[1]}`, result }) }}</span>
        <span v-else />
        <button class="btn primary" :disabled="!input" @click="enlarge"><Maximize2 :size="14" /> {{ t('edit.upscale.enlarge') }}</button>
      </div>
      <JobGallery :jobs="jobs" @open="open" />
    </div>

    <template #panel>
      <div class="fields">
        <div class="field">
          <span>{{ t('edit.enlargeBy', { factor }) }}</span>
          <FactorPicker v-model="factor" :max="4" />
          <small class="dim">{{ t('edit.upscale.factorHint') }}</small>
        </div>
        <p v-if="!comfyInstalled" class="note">
          {{ t('edit.upscale.needsComfy') }} <RouterLink to="/settings">{{ t('edit.upscale.needsComfyLink') }}</RouterLink>
        </p>
        <small class="dim">
          {{ t('edit.upscale.about', { max: MAX_SIDE }) }}
        </small>
      </div>
    </template>
  </PageFrame>
</template>

<style scoped>
.fields,
.field {
  display: grid;
  gap: 10px;
}


.two {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.two .btn {
  justify-content: center;
}

.btn.on {
  border-color: var(--accent);
  color: var(--accent);
}

.note {
  padding: 8px 10px;
  border-radius: var(--radius-s);
  background: var(--accent-soft);
}

.note a {
  color: var(--accent);
}
</style>
