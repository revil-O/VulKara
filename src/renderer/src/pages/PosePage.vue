<!-- SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0 · Copyright (C) 2026 Oliver Schmidt -->
<script setup lang="ts">
// The pose editor: people as OpenPose skeletons (body, hands, face) on a black canvas. The points are dragged;
// the result is the control picture "Pose" of Text to image. A pose can also be read from a photo.
import { computed, nextTick, onActivated, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Check, Download, FlipHorizontal2, ImageUp, Minus, Plus, RotateCcw, RotateCw, Trash2, Type } from '@lucide/vue'
import PageFrame from '../components/PageFrame.vue'
import { useHandoffStore } from '../stores/handoff'
import { cleanError } from '../stores/runtimes'
import { pickImage } from '../util/pick_image'
import { t, type PlainKey } from '../i18n'
import {
  BODY_COLORS, BODY_MIRROR, BODY_NAMES, BODY_TEMPLATES, FACE_COLOR, FACE_EXPRESSIONS, FACE_MIRROR, fitInside, HAND_COLORS, HAND_EDGES,
  HAND_NAMES, HAND_POINT_COLOR, HAND_TEMPLATES, LIMBS, placeFace, placeHand, poseLabel, type Point, type Points,
} from '../util/openpose'

type Part = 'body' | 'rhand' | 'lhand' | 'face'
type Side = 'rhand' | 'lhand'
interface Person {
  body: Points
  rhand: Points | null
  lhand: Points | null
  face: Points | null
}

const PARTS: Part[] = ['body', 'rhand', 'lhand', 'face']
const SIDES: Side[] = ['rhand', 'lhand']
const WRIST: Record<Side, number> = { rhand: 4, lhand: 7 }
const ELBOW: Record<Side, number> = { rhand: 3, lhand: 6 }
const SIZES = [512, 576, 640, 704, 768, 832, 896, 960, 1024, 1152, 1280]
const PART_TITLE: Record<Part, PlainKey> = { body: 'pose.parts.body', rhand: 'pose.parts.rhand', lhand: 'pose.parts.lhand', face: 'pose.parts.face' }

const router = useRouter()
const handoff = useHandoffStore()

const width = ref(512)
const height = ref(768)
const people = ref<Person[]>([])
/** person index -> "part:index" -> where the hidden point was */
const hidden = ref<Record<number, Record<string, Point>>>({})
const selected = ref(0)
const part = ref<Part>('body')
const templateName = ref('Standing')
const handChoice = reactive<Record<Side, string>>({ rhand: 'Relaxed', lhand: 'Relaxed' })
const faceChoice = ref('Neutral')
const photo = ref('')
const showPhoto = ref(true)
const detecting = ref(false)
const status = ref('')
const error = ref('')
const displayScale = ref(1)
const wrap = ref<HTMLElement>()
const svg = ref<SVGSVGElement>()

const person = computed(() => people.value[selected.value] as Person | undefined)
const fullBody = Object.keys(BODY_TEMPLATES).filter((n) => !BODY_TEMPLATES[n].portrait)
const portraits = Object.keys(BODY_TEMPLATES).filter((n) => BODY_TEMPLATES[n].portrait)
// the drawing sizes of the control picture (given for 512 px), scaled to the canvas
const px = computed(() => {
  const s = Math.max(width.value, height.value) / 512
  return { stick: Math.max(3, 4 * s), joint: Math.max(3, 4 * s), handLine: Math.max(1.5, 2 * s), handPoint: Math.max(2, 4 * s), facePoint: Math.max(1.5, 3 * s) }
})

const rgb = (c: number[]): string => `rgb(${c.join(',')})`
const at = (k: Point | null | undefined): Point => k ?? [0, 0]
const present = (pts: Points | null | undefined): Point[] => (pts ?? []).filter((k): k is Point => !!k)
const url = (path: string): string => window.vk.files.url(path)

function fit(): void {
  const el = wrap.value
  if (el) displayScale.value = Math.min(1.5, (el.clientWidth - 24) / width.value, (el.clientHeight - 24) / height.value) || 1
}

function select(index: number, what: Part): void {
  selected.value = index
  part.value = what
}

// small hands and faces (full body shots) would be one blob with the sizes of a close-up
function partLimit(p: Person | undefined, what: Part, kind: 'line' | 'point'): number {
  const pts = present(p?.[what])
  if (what === 'body' || pts.length < 2) return Infinity
  const xs = pts.map((k) => k[0])
  const ys = pts.map((k) => k[1])
  const extent = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys))
  if (what === 'face') return Math.max(0.8, extent / 70)  // larger dots would be copied into the picture
  return Math.max(kind === 'line' ? 0.8 : 1, extent / (kind === 'line' ? 28 : 14))
}

function pointRadius(index: number, what: Part, r: number): number {
  const limited = Math.min(r, partLimit(people.value[index], what, 'point'))
  return index === selected.value && what === part.value ? limited * 1.4 : limited
}

// ------------------------------------------------------------------ building people

function headSize(p: Person): number | undefined {
  const [re, le] = [p.body[14], p.body[15]]
  return re && le ? Math.hypot(le[0] - re[0], le[1] - re[1]) * 2.6 : undefined
}

// the hand's size follows the forearm (a hand is about 75 % of it), limited by the size of the head
function handFor(p: Person, side: Side, name: string): Points {
  const b = p.body
  let wrist = b[WRIST[side]]
  const elbow = b[ELBOW[side]]
  if (!wrist) {
    // no wrist (a portrait crop): the hand goes below the shoulder
    const shoulder = b[side === 'rhand' ? 2 : 5] ?? b[1] ?? [width.value / 2, height.value / 2]
    wrist = [shoulder[0], Math.min(height.value * 0.95, shoulder[1] + height.value * 0.15)]
  }
  let dir = [0, -1]
  let size = height.value * 0.08
  if (elbow) {
    const [dx, dy] = [wrist[0] - elbow[0], wrist[1] - elbow[1]]
    const length = Math.hypot(dx, dy)
    if (length > 1) {
      dir = [dx / length, dy / length]
      size = length * 0.75
    }
  }
  const head = headSize(p)
  if (head) size = Math.min(size, head * 1.15)
  return placeHand(name, wrist, dir, size, side === 'rhand' ? 'right' : 'left')
}

function faceFor(p: Person, expression: string): Points {
  const b = p.body
  let [re, le] = [b[14], b[15]]
  if (!re || !le) {
    // eyes hidden: estimated from nose and neck
    const nose = b[0] ?? [width.value / 2, height.value * 0.2]
    const neck = b[1] ?? [nose[0], nose[1] + height.value * 0.1]
    const d = Math.hypot(neck[0] - nose[0], neck[1] - nose[1]) || height.value * 0.1
    re = [nose[0] - d * 0.18, nose[1] - d * 0.12]
    le = [nose[0] + d * 0.18, nose[1] - d * 0.12]
  }
  return placeFace(expression, re, le)
}

function makePerson(name: string, offsetX: number): Person {
  const tpl = BODY_TEMPLATES[name]
  let body: Points
  if (tpl.portrait) {
    body = tpl.body.map((k): Point | null => k && [k[0] * width.value + offsetX, k[1] * height.value])
  } else {
    // the template's box, as large as fits; lying poses are wider than tall
    const aspect = tpl.aspect ?? 0.55
    const h = Math.min(height.value * 0.85, (width.value * 0.9) / aspect)
    const w = h * aspect
    const [x0, y0] = [(width.value - w) / 2 + offsetX, (height.value - h) / 2]
    body = tpl.body.map((k): Point | null => k && [x0 + k[0] * w, y0 + k[1] * h])
  }
  const p: Person = { body, rhand: null, lhand: null, face: null }
  for (const side of SIDES) {
    const hand = tpl[side]
    if (hand) p[side] = handFor(p, side, hand)
  }
  if (tpl.face) p.face = faceFor(p, tpl.face)
  return p
}

function addPerson(): void {
  const n = people.value.length
  const offset = n ? (n % 2 ? 1 : -1) * width.value * 0.22 : 0
  people.value = [...people.value, fitted(makePerson(templateName.value, offset))]
  select(people.value.length - 1, 'body')
}

function replacePerson(p: Person): void {
  people.value = people.value.map((old, i) => (i === selected.value ? p : old))
}

/** the person moved (and only when larger than the canvas, shrunk) so that all its points are inside the canvas */
function fitted(p: Person): Person {
  const f = fitInside(PARTS.flatMap((what) => p[what] ?? []), width.value, height.value)
  if (f.scale === 1 && !f.dx && !f.dy) return p
  return mapPerson(p, PARTS, (k) => [f.cx + (k[0] - f.cx) * f.scale + f.dx, f.cy + (k[1] - f.cy) * f.scale + f.dy])
}

function applyTemplate(): void {
  const old = person.value
  if (!old) return
  const made = makePerson(templateName.value, 0)
  // the person stays where it was (by the neck), as far as it fits: a lying pose has its neck at one end
  const dx = old.body[1] && made.body[1] ? old.body[1][0] - made.body[1][0] : 0
  const p = mapPerson(made, PARTS, (k) => [k[0] + dx, k[1]])
  // hands and face the person has stay, at the new wrists: a template gives it another pose, not other hands
  for (const side of SIDES) if (old[side] && !p[side]) p[side] = handFor(p, side, handChoice[side])
  if (old.face && !p.face) p.face = faceFor(p, faceChoice.value)
  replacePerson(fitted(p))
  delete hidden.value[selected.value]
  part.value = 'body'
}

function removePerson(): void {
  people.value = people.value.filter((_p, i) => i !== selected.value)
  hidden.value = {}
  select(Math.max(0, selected.value - 1), 'body')
}

function clearHidden(index: number, what: Part): void {
  const h = { ...(hidden.value[index] ?? {}) }
  for (const key of Object.keys(h)) if (key.startsWith(what + ':')) delete h[key]
  hidden.value[index] = h
}

function setHand(side: Side): void {
  const p = person.value
  if (!p) return
  replacePerson({ ...p, [side]: handFor(p, side, handChoice[side]) })
  clearHidden(selected.value, side)
  part.value = side
}

function setFace(): void {
  const p = person.value
  if (!p) return
  replacePerson({ ...p, face: faceFor(p, faceChoice.value) })
  clearHidden(selected.value, 'face')
  part.value = 'face'
}

function removePart(what: Part): void {
  const p = person.value
  if (!p || what === 'body') return
  replacePerson({ ...p, [what]: null })
  clearHidden(selected.value, what)
  part.value = 'body'
}

// ------------------------------------------------------------------ transforms

/** The person with fn applied to every point of the given parts. */
function mapPerson(p: Person, parts: Part[], fn: (k: Point) => Point): Person {
  const out = { ...p }
  for (const what of parts) {
    const pts = p[what]
    if (pts) (out[what] as Points) = pts.map((k) => k && fn(k))
  }
  return out
}

const centre = (pts: Point[]): Point => [pts.reduce((a, k) => a + k[0], 0) / pts.length, pts.reduce((a, k) => a + k[1], 0) / pts.length]

// the parts a transform acts on and the point it turns around
function target(p: Person): { parts: Part[]; origin: Point } {
  if (part.value === 'body') return { parts: PARTS, origin: centre(present(p.body)) }
  const pts = present(p[part.value])
  if (part.value === 'face') return { parts: ['face'], origin: centre(pts) }
  return { parts: [part.value], origin: p[part.value]?.[0] ?? centre(pts) }  // a hand turns around its wrist
}

function scale(f: number): void {
  const p = person.value
  if (!p) return
  const { parts, origin: [cx, cy] } = target(p)
  const next = mapPerson(p, parts, (k) => [cx + (k[0] - cx) * f, cy + (k[1] - cy) * f])
  // the whole person stays inside the canvas: enlarging had pushed the head out of the picture
  replacePerson(part.value === 'body' ? fitted(next) : next)
}

function rotate(degrees: number): void {
  const p = person.value
  if (!p) return
  const { parts, origin: [cx, cy] } = target(p)
  const [cos, sin] = [Math.cos((degrees * Math.PI) / 180), Math.sin((degrees * Math.PI) / 180)]
  const next = mapPerson(p, parts, (k) => {
    const [u, v] = [k[0] - cx, k[1] - cy]
    return [cx + u * cos - v * sin, cy + u * sin + v * cos]
  })
  replacePerson(part.value === 'body' ? fitted(next) : next)
}

function mirror(): void {
  const p = person.value
  if (!p) return
  const [cx] = centre(PARTS.flatMap((what) => present(p[what])))
  const flip = (pts: Points | null): Points | null => pts && pts.map((k): Point | null => k && [2 * cx - k[0], k[1]])
  const swap = (pts: Points | null, pairs: Record<number, number>): Points | null => {
    if (!pts) return pts
    const out = pts.slice()
    for (const [a, b] of Object.entries(pairs)) out[Number(a)] = pts[b]
    return out
  }
  const bodyPairs: Record<number, number> = { ...BODY_MIRROR }
  for (const [a, b] of Object.entries(BODY_MIRROR)) bodyPairs[b] = Number(a)
  replacePerson({
    body: swap(flip(p.body), bodyPairs) as Points,
    rhand: flip(p.lhand),  // the left hand becomes the right one
    lhand: flip(p.rhand),
    face: swap(flip(p.face), FACE_MIRROR),
  })
  delete hidden.value[selected.value]
}

// ------------------------------------------------------------------ dragging

let drag: { index: number; part: Part; point: number; whole: boolean; last: Point } | undefined

function svgPoint(event: MouseEvent): Point {
  const box = (svg.value as SVGSVGElement).getBoundingClientRect()
  return [((event.clientX - box.left) * width.value) / box.width, ((event.clientY - box.top) * height.value) / box.height]
}

function startDrag(event: MouseEvent, index: number, what: Part, point: number): void {
  select(index, what)
  drag = { index, part: what, point, whole: event.shiftKey, last: svgPoint(event) }
}

function endDrag(): void {
  drag = undefined
}

function onMove(event: MouseEvent): void {
  if (!drag) return
  const pt = svgPoint(event)
  const p = people.value[drag.index]
  const [dx, dy] = [pt[0] - drag.last[0], pt[1] - drag.last[1]]
  const shift = (k: Point): Point => [k[0] + dx, k[1] + dy]
  const clamp = ([x, y]: Point): Point => [Math.min(width.value, Math.max(0, x)), Math.min(height.value, Math.max(0, y))]
  let next: Person
  if (drag.whole) {
    next = mapPerson(p, drag.part === 'body' ? PARTS : [drag.part], shift)
  } else {
    next = { ...p, [drag.part]: (p[drag.part] as Points).map((k, i) => (i === drag?.point ? clamp(pt) : k)) }
    if (drag.part === 'body') {
      // hands follow their wrist, the face follows the nose
      for (const side of SIDES) if (drag.point === WRIST[side]) next = mapPerson(next, [side], shift)
      if (drag.point === 0) next = mapPerson(next, ['face'], shift)
    } else if (drag.point === 0 && drag.part !== 'face' && next.body[WRIST[drag.part]]) {
      // the first point of a hand is the wrist of the body
      next = { ...next, body: next.body.map((k, i) => (i === WRIST[drag?.part as Side] ? clamp(pt) : k)) }
    }
  }
  people.value = people.value.map((old, i) => (i === drag?.index ? next : old))
  drag.last = pt
}

function hidePoint(index: number, what: Part, point: number): void {
  const p = people.value[index]
  const k = p[what]?.[point]
  if (!k) return
  hidden.value[index] = { ...(hidden.value[index] ?? {}), [`${what}:${point}`]: k }
  people.value = people.value.map((old, i) => (i === index ? { ...old, [what]: (old[what] as Points).map((q, j) => (j === point ? null : q)) } : old))
}

function showPoint(index: number, key: string): void {
  const [what, point] = key.split(':') as [Part, string]
  const h = { ...(hidden.value[index] ?? {}) }
  const k = h[key]
  delete h[key]
  hidden.value[index] = h
  people.value = people.value.map((old, i) => (i === index && old[what] ? { ...old, [what]: (old[what] as Points).map((q, j) => (j === Number(point) ? k : q)) } : old))
}

// ------------------------------------------------------------------ a pose from a photo

async function fromPhoto(): Promise<void> {
  const path = await pickImage()
  if (!path) return
  detecting.value = true
  error.value = ''
  status.value = t('pose.detect.looking')
  const stop = window.vk.pose.onProgress((stage, percent) => {
    status.value = stage + (percent >= 0 ? ` ${percent} %` : '')
  })
  try {
    const found = await window.vk.pose.detect(path)
    if (!found.people.length) {
      status.value = t('pose.detect.noPerson')
      return
    }
    // a canvas in the proportions of the photo (long side 1024), the people scaled onto it
    const snap = (v: number): number => SIZES.reduce((a, s) => (Math.abs(s - v) < Math.abs(a - v) ? s : a))
    if (found.width >= found.height) [width.value, height.value] = [1024, snap((1024 * found.height) / found.width)]
    else [width.value, height.value] = [snap((1024 * found.width) / found.height), 1024]
    const [sx, sy] = [width.value / found.width, height.value / found.height]
    const scaled = (pts: Points | null): Points | null => pts && pts.map((k): Point | null => k && [k[0] * sx, k[1] * sy])
    const all: Person[] = found.people.map((p) => ({ body: scaled(p.body) as Points, rhand: scaled(p.rhand), lhand: scaled(p.lhand), face: scaled(p.face) }))
    // people far in the background would only add noise to the control picture
    const size = (p: Person): number => {
      const pts = present(p.body)
      const [xs, ys] = [pts.map((k) => k[0]), pts.map((k) => k[1])]
      return Math.max(Math.max(...ys) - Math.min(...ys), Math.max(...xs) - Math.min(...xs))
    }
    const biggest = Math.max(...all.map(size))
    const kept = all.filter((p) => size(p) >= biggest * 0.4)
    people.value = kept
    hidden.value = {}
    photo.value = path
    showPhoto.value = true
    select(kept.indexOf(kept.reduce((a, p) => (size(p) > size(a) ? p : a))), 'body')
    const dropped = all.length - kept.length
    status.value = dropped ? t('pose.detect.foundDropped', { n: kept.length, dropped }) : t('pose.detect.found', { n: kept.length })
  } catch (err) {
    status.value = ''
    error.value = cleanError(err)
  } finally {
    stop()
    detecting.value = false
  }
}

// ------------------------------------------------------------------ the control picture

// drawn the way the pose ControlNets were trained: limbs as ellipses of 60 % opacity with joint circles,
// hands as coloured lines with blue points, faces as white points, on black
function renderPng(): string {
  const c = document.createElement('canvas')
  ;[c.width, c.height] = [width.value, height.value]
  const ctx = c.getContext('2d') as CanvasRenderingContext2D
  const sz = px.value
  ctx.fillStyle = '#000'
  ctx.fillRect(0, 0, c.width, c.height)
  const dot = (k: Point, r: number, color: number[]): void => {
    ctx.fillStyle = rgb(color)
    ctx.beginPath()
    ctx.arc(k[0], k[1], r, 0, 2 * Math.PI)
    ctx.fill()
  }
  for (const p of people.value) {
    LIMBS.forEach(([i, j], li) => {
      const [a, b] = [p.body[i], p.body[j]]
      if (!a || !b) return
      ctx.save()
      ctx.globalAlpha = 0.6
      ctx.fillStyle = rgb(BODY_COLORS[li])
      ctx.translate((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
      ctx.rotate(Math.atan2(b[1] - a[1], b[0] - a[0]))
      ctx.beginPath()
      ctx.ellipse(0, 0, Math.hypot(b[0] - a[0], b[1] - a[1]) / 2, sz.stick, 0, 0, 2 * Math.PI)
      ctx.fill()
      ctx.restore()
    })
    p.body.forEach((k, i) => k && dot(k, sz.joint, BODY_COLORS[i]))
  }
  for (const p of people.value) {
    for (const side of SIDES) {
      const hand = p[side]
      if (!hand) continue
      ctx.lineWidth = Math.min(sz.handLine, partLimit(p, side, 'line'))
      const r = Math.min(sz.handPoint, partLimit(p, side, 'point'))
      HAND_EDGES.forEach(([i, j], ei) => {
        const [a, b] = [hand[i], hand[j]]
        if (!a || !b) return
        ctx.strokeStyle = rgb(HAND_COLORS[ei])
        ctx.beginPath()
        ctx.moveTo(a[0], a[1])
        ctx.lineTo(b[0], b[1])
        ctx.stroke()
      })
      for (const k of present(hand)) dot(k, r, HAND_POINT_COLOR)
    }
  }
  for (const p of people.value) {
    const r = Math.min(sz.facePoint, partLimit(p, 'face', 'point'))
    for (const k of present(p.face)) dot(k, r, FACE_COLOR)
  }
  return c.toDataURL('image/png')
}

async function useInText(): Promise<void> {
  if (!people.value.length) return
  const image = await window.vk.files.writePose(renderPng())
  handoff.send('text', { control: { type: 'BodyPose', image, preprocess: false, size: [width.value, height.value] } })
  void router.push('/text')
}

async function savePng(): Promise<void> {
  if (!people.value.length) return
  const image = await window.vk.files.writePose(renderPng())
  await window.vk.files.saveAs(image, 'pose.png')
}

onMounted(() => {
  addPerson()
  void nextTick(fit)
  window.addEventListener('resize', fit)
})
onActivated(() => void nextTick(fit))
onBeforeUnmount(() => window.removeEventListener('resize', fit))
watch([width, height], () => {
  // a smaller or other-shaped canvas: the people come inside again
  people.value = people.value.map(fitted)
  void nextTick(fit)
})
</script>

<template>
  <PageFrame :title="t('pose.title')" :subtitle="t('pose.subtitle')">
    <template #actions>
      <button class="btn" :disabled="!people.length" @click="savePng"><Download :size="14" /> {{ t('pose.savePng') }}</button>
      <button class="btn primary" :disabled="!people.length" @click="useInText"><Type :size="14" /> {{ t('pose.useInText') }}</button>
    </template>

    <div ref="wrap" class="stage">
      <svg
        ref="svg" :viewBox="`0 0 ${width} ${height}`" :style="{ width: width * displayScale + 'px', height: height * displayScale + 'px' }"
        @mousemove="onMove" @mouseup="endDrag" @mouseleave="endDrag"
      >
        <rect x="0" y="0" :width="width" :height="height" fill="black" />
        <!-- the photo a pose was read from, as a guide; it is not part of the control picture -->
        <image v-if="photo && showPhoto" :href="url(photo)" x="0" y="0" :width="width" :height="height" preserveAspectRatio="none" opacity="0.4" pointer-events="none" />
        <g v-for="(p, pi) in people" :key="pi" :opacity="pi === selected ? 1 : 0.75">
          <line
            v-for="(limb, li) in LIMBS" v-show="p.body[limb[0]] && p.body[limb[1]]" :key="'l' + li"
            :x1="at(p.body[limb[0]])[0]" :y1="at(p.body[limb[0]])[1]" :x2="at(p.body[limb[1]])[0]" :y2="at(p.body[limb[1]])[1]"
            :stroke="rgb(BODY_COLORS[li])" :stroke-width="px.stick" stroke-opacity="0.6" stroke-linecap="round"
          />
          <circle
            v-for="(k, ki) in p.body" v-show="k" :key="'k' + ki" :cx="at(k)[0]" :cy="at(k)[1]" :r="pointRadius(pi, 'body', px.joint)"
            :fill="rgb(BODY_COLORS[ki])" class="joint" @mousedown.prevent="startDrag($event, pi, 'body', ki)" @dblclick="hidePoint(pi, 'body', ki)"
          >
            <title>{{ t(BODY_NAMES[ki]) }}</title>
          </circle>
          <template v-for="side in SIDES" :key="side">
            <g v-if="p[side]">
              <line
                v-for="(e, ei) in HAND_EDGES" v-show="p[side]![e[0]] && p[side]![e[1]]" :key="'e' + ei"
                :x1="at(p[side]![e[0]])[0]" :y1="at(p[side]![e[0]])[1]" :x2="at(p[side]![e[1]])[0]" :y2="at(p[side]![e[1]])[1]"
                :stroke="rgb(HAND_COLORS[ei])" :stroke-width="Math.min(px.handLine, partLimit(p, side, 'line'))"
              />
              <circle
                v-for="(k, ki) in p[side]!" v-show="k" :key="'h' + ki" :cx="at(k)[0]" :cy="at(k)[1]" :r="pointRadius(pi, side, px.handPoint)"
                :fill="rgb(HAND_POINT_COLOR)" class="joint" @mousedown.prevent="startDrag($event, pi, side, ki)" @dblclick="hidePoint(pi, side, ki)"
              >
                <title>{{ t(side === 'rhand' ? 'pose.rightPoint' : 'pose.leftPoint', { point: t(HAND_NAMES[ki]) }) }}</title>
              </circle>
            </g>
          </template>
          <g v-if="p.face">
            <circle
              v-for="(k, ki) in p.face" v-show="k" :key="'f' + ki" :cx="at(k)[0]" :cy="at(k)[1]" :r="pointRadius(pi, 'face', px.facePoint)"
              :fill="rgb(FACE_COLOR)" class="joint" @mousedown.prevent="startDrag($event, pi, 'face', ki)" @dblclick="hidePoint(pi, 'face', ki)"
            />
          </g>
          <!-- hidden points of the selected person stay reachable as outlines -->
          <template v-if="pi === selected">
            <circle
              v-for="(k, key) in hidden[pi] ?? {}" :key="'x' + key" :cx="k[0]" :cy="k[1]" :r="px.joint * 0.8"
              fill="none" stroke="#888" stroke-dasharray="2,2" class="joint" @dblclick="showPoint(pi, String(key))"
            >
              <title>{{ t('pose.hiddenPoint') }}</title>
            </circle>
          </template>
        </g>
      </svg>
    </div>

    <template #panel>
      <div class="fields">
        <p class="dim">{{ t('pose.intro') }}</p>

        <div class="field">
          <span>{{ t('pose.canvas') }}</span>
          <div class="pair">
            <select v-model.number="width" :title="t('pose.width')"><option v-for="s in SIZES" :key="s" :value="s">{{ s }}</option></select>
            <span class="dim">×</span>
            <select v-model.number="height" :title="t('pose.height')"><option v-for="s in SIZES" :key="s" :value="s">{{ s }}</option></select>
          </div>
        </div>

        <div class="field">
          <span>{{ t('pose.people') }}</span>
          <div class="chips">
            <button v-for="(_p, i) in people" :key="i" class="chip" :class="{ on: i === selected }" @click="select(i, 'body')">{{ t('pose.person', { n: i + 1 }) }}</button>
          </div>
          <select v-model="templateName">
            <optgroup :label="t('pose.fullBody')"><option v-for="n in fullBody" :key="n" :value="n">{{ poseLabel('templates', n) }}</option></optgroup>
            <optgroup :label="t('pose.portraitGroup')"><option v-for="n in portraits" :key="n" :value="n">{{ poseLabel('templates', n) }}</option></optgroup>
          </select>
          <div class="pair wrap">
            <button class="btn small" @click="addPerson"><Plus :size="12" /> {{ t('pose.add') }}</button>
            <button class="btn small" :disabled="!person" :title="t('pose.applyHint')" @click="applyTemplate">{{ t('pose.apply') }}</button>
            <button class="btn small" :disabled="!person" :title="t('pose.mirror')" @click="mirror"><FlipHorizontal2 :size="12" /></button>
            <button class="btn small danger" :disabled="!person" :title="t('pose.removePerson')" @click="removePerson"><Trash2 :size="12" /></button>
          </div>
          <div class="pair wrap">
            <button class="btn small" :disabled="detecting" @click="fromPhoto"><ImageUp :size="12" /> {{ t('pose.fromPhoto') }}</button>
            <label v-if="photo" class="check"><input v-model="showPhoto" type="checkbox" /> {{ t('pose.showPhoto') }}</label>
          </div>
          <small v-if="status" class="dim">{{ status }}</small>
          <small v-if="error" class="error selectable">{{ error }}</small>
        </div>

        <template v-if="person">
          <div class="field">
            <span>{{ t('pose.handsAndFace') }} <b>{{ t('pose.person', { n: selected + 1 }) }}</b></span>
            <div class="parts">
            <div v-for="side in SIDES" :key="side" class="part">
              <button class="chip" :class="{ on: part === side }" :disabled="!person[side]" @click="select(selected, side)">{{ side === 'rhand' ? t('pose.right') : t('pose.left') }}</button>
              <select v-model="handChoice[side]"><option v-for="(_h, n) in HAND_TEMPLATES" :key="n" :value="n">{{ poseLabel('hands', n) }}</option></select>
              <button class="btn small icon-only" :aria-label="person[side] ? t('pose.set') : t('pose.add')" @click="setHand(side)"><Check v-if="person[side]" :size="13" /><Plus v-else :size="13" /></button>
              <button class="btn small ghost" :disabled="!person[side]" :title="t('pose.remove')" @click="removePart(side)"><Trash2 :size="12" /></button>
            </div>
            <div class="part">
              <button class="chip" :class="{ on: part === 'face' }" :disabled="!person.face" @click="select(selected, 'face')">{{ t('pose.face') }}</button>
              <select v-model="faceChoice"><option v-for="(_f, n) in FACE_EXPRESSIONS" :key="n" :value="n">{{ poseLabel('faces', n) }}</option></select>
              <button class="btn small icon-only" :aria-label="person.face ? t('pose.set') : t('pose.add')" @click="setFace"><Check v-if="person.face" :size="13" /><Plus v-else :size="13" /></button>
              <button class="btn small ghost" :disabled="!person.face" :title="t('pose.remove')" @click="removePart('face')"><Trash2 :size="12" /></button>
            </div>
            </div>
          </div>

          <div class="field">
            <span>{{ t('pose.turnAndSize') }} <b>{{ t(PART_TITLE[part]) }}</b></span>
            <div class="pair wrap">
              <button class="btn small" :title="t('pose.turnLeft')" @click="rotate(-15)"><RotateCcw :size="12" /></button>
              <button class="btn small" :title="t('pose.turnRight')" @click="rotate(15)"><RotateCw :size="12" /></button>
              <button class="btn small" :title="t('pose.larger')" @click="scale(1.1)"><Plus :size="12" /></button>
              <button class="btn small" :title="t('pose.smaller')" @click="scale(1 / 1.1)"><Minus :size="12" /></button>
              <button v-if="part !== 'body'" class="btn small ghost" @click="part = 'body'">{{ t('pose.wholePerson') }}</button>
            </div>
          </div>
        </template>

        <p class="dim">{{ t('pose.outro') }}</p>
      </div>
    </template>
  </PageFrame>
</template>

<style scoped>
.stage {
  height: 100%;
  display: grid;
  place-items: center;
  overflow: hidden;
}

svg {
  border-radius: var(--radius-s);
  box-shadow: var(--shadow);
}

.joint {
  cursor: grab;
}

.fields {
  display: grid;
  gap: 18px;
}

.field > span {
  display: flex;
  justify-content: space-between;
}

.field {
  gap: 8px;
}

.field b {
  font-weight: 400;
  color: var(--text-dim);
}

select {
  width: 100%;
}

.pair {
  display: flex;
  align-items: center;
  gap: 6px;
}

.pair.wrap {
  flex-wrap: wrap;
}

.chip {
  padding: 3px 9px;
  white-space: nowrap;
}

.chip:disabled {
  opacity: 0.5;
}

/* the side's chip as wide as the longest of the three (Right, Left, Face) in the app's language */
.parts {
  display: grid;
  grid-template-columns: minmax(48px, max-content) minmax(0, 1fr) auto auto;
  gap: 4px;
}

.part .icon-only { padding-inline: 7px; }
.part .ghost { padding-inline: 4px; }
/* the longest shape names ("Flach, geschlossen") fit in the narrow panel */
.part select { font-size: 11.5px; padding-inline: 6px 0; min-width: 0; }
.part .chip { padding-inline: 8px; }

.part {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: subgrid;
  align-items: center;
}

.check {
  display: flex;
  gap: 6px;
  align-items: center;
}

.check input {
  accent-color: var(--accent);
}
</style>
