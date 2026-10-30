<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// The band along the bottom of a picture that opens the large view on a click: a window of its own in the app, an
// overlay over the page in the remote web UI. The parent is the picture's frame (position: relative); the slots put
// small marks of the picture into the band, left and right of the text, so that they never cover it.
import { t } from '../i18n'
import { isRemote } from '../remote_vk'
</script>

<template>
  <span class="open-hint">
    <slot name="start" />
    <span class="text">{{ isRemote() ? t('library.openHintRemote') : t('library.openHint') }}</span>
    <slot />
  </span>
</template>

<style scoped>
.open-hint {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  background: var(--scrim);
  color: var(--scrim-text);
  font-size: 11px;
  line-height: 1.3;
  text-align: center;
  pointer-events: none;
  -webkit-backdrop-filter: blur(4px);
  backdrop-filter: blur(4px);
}

.text {
  flex: 1;
  min-width: 0;
}
</style>
