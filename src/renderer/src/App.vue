<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Menu } from '@lucide/vue'
import { useRoute, useRouter } from 'vue-router'
import NavRail from './components/NavRail.vue'
import JobBar from './components/JobBar.vue'
import ImagePicker from './components/ImagePicker.vue'
import UpdateBanner from './components/UpdateBanner.vue'
import { isRemote } from './remote_vk'
import ViewerPage from './pages/ViewerPage.vue'
import { useFavoritesStore } from './stores/favorites'
import { useHandoffStore } from './stores/handoff'
import { useQueueStore } from './stores/queue'
import { useRuntimesStore } from './stores/runtimes'
import { useSettingsStore } from './stores/settings'
import { formPage } from './util/job_form'
import { useAssetsStore } from './stores/assets'
import { locale, t } from './i18n'
import { hideViewer, viewerOverlay } from './viewer_overlay'
import type { ViewerAction } from '@shared/api'

const route = useRoute()
const router = useRouter()
const navOpen = ref(false)
watch(() => route.path, () => { navOpen.value = false })
// a viewer or splash window shows its page alone
// the remote web UI does not update the Mac's app
const remote = isRemote()
const bare = computed(() => route.meta.bare === true || /^#\/(viewer|splash|monitor)/.test(location.hash))

onMounted(() => {
  if (bare.value) return
  void useQueueStore().start()
  useFavoritesStore().start()
  void useRuntimesStore().refresh()
  void useSettingsStore().load()
  // the main process writes the runtimes' descriptions and the models' notes in the language of the moment
  watch(locale, () => {
    void useRuntimesStore().refresh()
    void useAssetsStore().refresh()
  })
  // a viewer window hands a picture or the settings of a job back
  window.vk.viewer.onAction(routeViewerAction)
  // the app menu and the menu bar open a page (Settings …)
  if (!remote) window.vk.app.onNavigate((to) => { if (router.resolve(to).matched.length) void router.push(to) })
})

const handoff = useHandoffStore()
/** A viewer action (a window's, or the overlay's): the settings of a job or the picture into the right page. */
function routeViewerAction(action: ViewerAction): void {
  if (action.page === 'upscale') {
    // enlarging has no settings to take over: the picture itself goes there
    handoff.send('upscale', { inputImage: action.type === 'reuse' ? action.job.inputImage ?? action.file : action.file })
    void router.push({ path: '/upscale', query: { t: String(Date.now()) } })
    return
  }
  const page = formPage(action.page)
  if (action.type === 'reuse') handoff.send(page, { job: action.job, inputImage: page === 'text' ? undefined : action.job.inputImage })
  else handoff.send(page, { inputImage: action.file })
  void router.push({ path: '/' + page, query: { t: String(Date.now()) } })
}
function onOverlayAct(action: ViewerAction): void {
  routeViewerAction(action)
  hideViewer()
}
</script>

<template>
  <RouterView v-if="bare" />
  <template v-else>
    <button class="nav-toggle" :aria-label="t('nav.menu')" @click="navOpen = !navOpen"><Menu :size="22" /></button>
    <div v-if="navOpen" class="nav-backdrop" @click="navOpen = false" />
    <div class="shell">
      <NavRail :class="{ open: navOpen }" />
    <main class="stage">
      <RouterView v-slot="{ Component, route: shown }">
        <KeepAlive>
          <component :is="Component" :key="shown.path" />
        </KeepAlive>
      </RouterView>
    </main>
      <JobBar />
      <ImagePicker />
      <UpdateBanner v-if="!remote" />
    </div>
  </template>
  <div v-if="viewerOverlay" class="viewer-overlay">
    <ViewerPage :inline="viewerOverlay" @close="hideViewer" @act="onOverlayAct" />
  </div>
</template>

<style scoped>
.viewer-overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: var(--bg);
}
.shell {
  display: grid;
  grid-template-columns: var(--rail) 1fr;
  grid-template-rows: 1fr minmax(var(--jobbar), auto);
  height: 100%;
}

.stage {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.nav-toggle,
.nav-backdrop {
  display: none;
}

/* phones and narrow tablets: the rail becomes a drawer behind a menu button */
@media (max-width: 860px) {
  .shell {
    grid-template-columns: 1fr;
  }
  .nav-toggle {
    display: grid;
    place-items: center;
    position: fixed;
    top: 8px;
    left: 8px;
    z-index: 40;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--text);
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.22);
  }
  .nav-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    z-index: 34;
    background: rgba(0, 0, 0, 0.45);
  }
}
</style>
