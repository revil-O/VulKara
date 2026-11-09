<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// A small line of the last samples, the newest at the right edge; max: the top of the scale (else the highest
// sample). Shared with okAI-helper (LmAI-Studio MonitorWindow's sparkline): keep both the same.
import { computed } from 'vue'

const props = withDefaults(defineProps<{ values: number[]; max?: number; width?: number; height?: number }>(), { width: 160, height: 32 })

const points = computed(() => {
  const v = props.values
  if (v.length < 2) return ''
  const top = Math.max(props.max ?? 0, ...v, 1e-9)
  const step = props.width / (v.length - 1)
  return v.map((y, i) => `${(i * step).toFixed(1)},${(props.height - 1 - (Math.max(0, y) / top) * (props.height - 2)).toFixed(1)}`).join(' ')
})
</script>

<template>
  <svg class="spark" :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" aria-hidden="true">
    <polyline v-if="points" :points="points" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
  </svg>
</template>

<style scoped>
.spark {
  display: block;
  color: var(--accent);
}
</style>
