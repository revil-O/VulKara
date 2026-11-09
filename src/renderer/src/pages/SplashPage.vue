<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// The splash window at start: the forge picture with the name. The main window loads behind it; the splash closes by
// itself once that is ready (a click or Return closes it earlier).
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { LoaderCircle } from '@lucide/vue'
import picture from '../assets/splash/splash.jpg?url'
import { t } from '../i18n'

const COPYRIGHT = '© 2026 Oliver Schmidt'

const ready = ref(false)
const version = ref('')
let stopListening: (() => void) | undefined

function confirm(): void {
  if (ready.value) void window.vk.splash.confirm()
}

const key = (e: KeyboardEvent): void => {
  if (e.key === 'Enter' || e.key === ' ') confirm()
}

onMounted(async () => {
  stopListening = window.vk.splash.onReady(() => (ready.value = true))
  window.addEventListener('keydown', key)
  const [state, info] = await Promise.all([window.vk.splash.state(), window.vk.app.info()])
  ready.value ||= state.ready
  version.value = info.version
})

onBeforeUnmount(() => {
  stopListening?.()
  window.removeEventListener('keydown', key)
})
</script>

<template>
  <div class="splash" @click="confirm">
    <img :src="picture" class="picture" alt="" draggable="false" />
    <div class="handle" />
    <div class="caption">
      <div class="name">
        <h1>VulKara</h1>
        <p>{{ t('common.splash.tagline') }}</p>
        <p class="origin">{{ t('common.splash.origin') }}</p>
      </div>
      <span class="status"><LoaderCircle :size="13" class="spin" /> {{ ready ? t('common.splash.starting') : t('common.splash.gettingReady') }}</span>
    </div>
    <footer>
      <span v-if="version">{{ t('common.splash.version', { version }) }}</span>
      <span>{{ COPYRIGHT }}</span>
    </footer>
  </div>
</template>

<style scoped>
/* the forge picture is dark in light mode too: the text on it stays light */
.splash {
  position: relative;
  height: 100vh;
  overflow: hidden;
  background: #0d0c0e;
  color: #f1ece4;
}

.picture {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* the frameless window is moved by dragging the picture above the band; the band with the button is no drag region
   at all, or macOS takes a click on the button for moving the window */
.handle {
  position: absolute;
  inset: 0 0 120px;
  -webkit-app-region: drag;
}

/* a dark band at the bottom so the name stays readable on the picture */
.splash::after {
  content: '';
  position: absolute;
  inset: auto 0 0;
  height: 46%;
  background: linear-gradient(transparent, rgba(8, 7, 9, 0.88) 62%);
  pointer-events: none;
}

.caption {
  position: absolute;
  z-index: 1;
  left: 0;
  right: 0;
  bottom: 34px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 0 24px;
  animation: rise 0.7s ease both;
}

h1 {
  font-size: 28px;
  letter-spacing: -0.02em;
  background: linear-gradient(90deg, #ffd9a8, #ff8a3d);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.name p {
  color: rgba(241, 236, 228, 0.82);
}

.name .origin {
  margin-top: 4px;
  font-size: 10.5px;
  font-style: italic;
  color: rgba(241, 236, 228, 0.6);
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  font-size: 12px;
  color: rgba(241, 236, 228, 0.7);
}

footer {
  position: absolute;
  z-index: 1;
  left: 24px;
  bottom: 10px;
  display: flex;
  gap: 14px;
  font-size: 11px;
  color: rgba(241, 236, 228, 0.5);
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes rise {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
}
</style>
