// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { createRouter, createWebHashHistory, type RouteRecordRaw } from 'vue-router'
import { isRemote } from './remote_vk'
import type { Component } from 'vue'
import { EDITION } from '@shared/edition'
import type { PlainKey } from './i18n'
import {
  Aperture, Boxes, Clapperboard, Cpu, Eraser, FileClock, Lightbulb, Frame, GraduationCap, Heart, History, House, Images, Info, Layers, Maximize2,
  PersonStanding, Scale, ScrollText, Settings, Sparkles, Type, WandSparkles,
} from '@lucide/vue'

export interface PageEntry {
  path: string
  /** the key of the page's name in the texts (nav.*) */
  title: PlainKey
  icon: Component
  group: 'start' | 'create' | 'edit' | 'tools' | 'library' | 'app'
  /** the page component; pages without one are announced as coming */
  page?: () => Promise<Component>
  props?: Record<string, unknown>
  /** shown and reachable in the remote web UI (Generate + monitor); the rest stay on the Mac */
  remote?: boolean
}

const generate = (): Promise<Component> => import('./pages/GeneratePage.vue')

export const PAGES: PageEntry[] = [
  { path: '/', title: 'nav.start', icon: House, group: 'start', remote: true, page: () => import('./pages/StartPage.vue') },
  { path: '/text', title: 'nav.text', icon: Type, group: 'create', remote: true, page: generate, props: { mode: 'text' } },
  { path: '/image', title: 'nav.image', icon: Images, group: 'create', remote: true, page: generate, props: { mode: 'image' } },
  { path: '/canvas', title: 'nav.canvas', icon: Frame, group: 'create', page: () => import('./pages/CanvasPage.vue') },
  { path: '/video', title: 'nav.video', icon: Clapperboard, group: 'create', remote: true, page: generate, props: { mode: 'video' } },
  { path: '/illusion', title: 'nav.illusion', icon: Sparkles, group: 'create', remote: true, page: generate, props: { mode: 'illusion' } },
  { path: '/inpaint', title: 'nav.inpaint', icon: Eraser, group: 'edit', remote: true, page: generate, props: { mode: 'inpaint' } },
  { path: '/enhance', title: 'nav.enhance', icon: Aperture, group: 'edit', page: () => import('./pages/EnhancePage.vue') },
  { path: '/upscale', title: 'nav.upscale', icon: Maximize2, group: 'edit', page: () => import('./pages/UpscalePage.vue') },
  { path: '/restore', title: 'nav.restore', icon: WandSparkles, group: 'edit', page: () => import('./pages/RestorePage.vue') },
  { path: '/pose', title: 'nav.pose', icon: PersonStanding, group: 'tools', remote: true, page: () => import('./pages/PosePage.vue') },
  { path: '/lora', title: 'nav.lora', icon: Layers, group: 'tools', remote: true, page: () => import('./pages/LoraPage.vue') },
  { path: '/training', title: 'nav.training', icon: GraduationCap, group: 'tools', page: () => import('./pages/TrainingPage.vue') },
  { path: '/models', title: 'nav.models', icon: Boxes, group: 'library', remote: true, page: () => import('./pages/ModelsPage.vue') },
  { path: '/history', title: 'nav.history', icon: History, group: 'library', remote: true, page: () => import('./pages/HistoryPage.vue') },
  {
    path: '/favorites', title: 'nav.favorites', icon: Heart, group: 'library', remote: true,
    page: () => import('./pages/HistoryPage.vue'), props: { favorites: true },
  },
  { path: '/tips', title: 'nav.tips', icon: Lightbulb, group: 'library', remote: true, page: () => import('./pages/TipsPage.vue') },
  { path: '/settings', title: 'nav.settings', icon: Settings, group: 'app', page: () => import('./pages/SettingsPage.vue') },
  { path: '/hardware', title: 'nav.hardware', icon: Cpu, group: 'app', page: () => import('./pages/HardwarePage.vue') },
  { path: '/logs', title: 'nav.logs', icon: ScrollText, group: 'app', page: () => import('./pages/LogsPage.vue') },
  { path: '/changelog', title: 'nav.changelog', icon: FileClock, group: 'app', remote: true, page: () => import('./pages/ChangelogPage.vue') },
  { path: '/licenses', title: 'nav.licenses', icon: Scale, group: 'app', page: () => import('./pages/LicensesPage.vue') },
  { path: '/about', title: 'nav.about', icon: Info, group: 'app', page: () => import('./pages/AboutPage.vue') },
]

// pages that need ComfyUI are left out of an edition without it
const NEEDS_COMFY = ['/video', '/upscale']
export const SHOWN = PAGES.filter((p) => EDITION.comfyui || !NEEDS_COMFY.includes(p.path))

/** The pages a browser (the remote web UI) shows and may open; the app itself shows them all. */
export const shownPages = (remote: boolean): PageEntry[] => (remote ? SHOWN.filter((p) => p.remote) : SHOWN)

const pages: RouteRecordRaw[] = SHOWN.map((p) => ({
  path: p.path,
  component: p.page ?? (() => import('./pages/ComingPage.vue')),
  props: p.props,
  meta: { title: p.title },
}))

// the large view and the splash are windows of their own: their pages come without the frame of the app
const routes: RouteRecordRaw[] = [
  ...pages,
  { path: '/viewer', component: () => import('./pages/ViewerPage.vue'), meta: { bare: true } },
  { path: '/splash', component: () => import('./pages/SplashPage.vue'), meta: { bare: true } },
  { path: '/monitor', component: () => import('./pages/MonitorPage.vue'), meta: { bare: true } },
]

export const router = createRouter({ history: createWebHashHistory(), routes })

// a browser (the remote web UI) may not open a page that stays on the Mac: send it to the start page
const remotePaths = new Set(SHOWN.filter((p) => p.remote).map((p) => p.path))
router.beforeEach((to) => {
  if (isRemote() && ((to.meta.title !== undefined && !remotePaths.has(to.path)) || to.path === '/monitor')) return '/'
  return true
})
