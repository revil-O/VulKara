// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The steps of the mask brush (MaskCanvas.vue), in order, so undo takes back exactly the last one: strokes painted or
// erased, and selections (a mask file: "Select subject" by Apple Vision, or "Select by click" by SAM). A selection
// by click is made again from all clicks with every click; a subject taken out or back in is a new step of the same
// selection. Of such a row only the last step shows.

export interface Stroke {
  kind: 'stroke'
  erase: boolean
  /** brush diameter in picture pixels */
  size: number
  points: [number, number][]
}

export type Click = [number, number, number]

export interface Selection {
  kind: 'selection'
  /** the mask's path (white = selected) */
  mask: string
  /** a selection by click: all clicks of its row so far, [x, y, 1 = adds | 0 = takes away] in picture pixels */
  clicks?: Click[]
  /** a selection by click: SAM's candidate by size (0 = the whole thing), and how many there are */
  pick?: number
  candidates?: number
  /** "Select subject" with several subjects: which pixel is which subject (grey 1..subjects), and the subjects taken
   *  out of the mask */
  labels?: string
  subjects?: number
  off?: number[]
}

export type MaskStep = Stroke | Selection

const isClick = (s: MaskStep | undefined): s is Selection => s?.kind === 'selection' && !!s.clicks
const isSubject = (s: MaskStep | undefined): s is Selection => s?.kind === 'selection' && !s.clicks

/** One row: clicks after clicks, or subjects taken out or back in after the same "Select subject". */
const sameRow = (a: MaskStep, b: MaskStep | undefined): boolean => (isClick(a) && isClick(b)) || (isSubject(a) && isSubject(b) && a.mask === b.mask)

/** The steps that make the mask: an earlier step of a row is replaced by the next one. */
export const shownSteps = (steps: MaskStep[]): MaskStep[] => steps.filter((s, i) => !sameRow(s, steps[i + 1]))

/** The next selection by click. A click that adds, on (nearly) the spot of the row's last such click, takes SAM's next
 *  smaller candidate for the same clicks (whole → part → detail → whole); any other click goes on with the row (SAM
 *  rates which candidate fits all clicks best), or starts one with the whole thing. near: how far counts as the same
 *  spot, in picture pixels. */
export function nextRequest(last: Pick<Selection, 'clicks' | 'pick' | 'candidates'> | undefined, click: Click, near: number): { clicks: Click[]; pick?: number } {
  if (!last?.clicks?.length) return { clicks: [click], pick: 0 }
  const [x, y, adds] = last.clicks[last.clicks.length - 1]
  const n = last.candidates ?? 1
  if (click[2] && adds && n > 1 && Math.hypot(click[0] - x, click[1] - y) <= near) return { clicks: last.clicks, pick: ((last.pick ?? 0) + 1) % n }
  return { clicks: [...last.clicks, click] }
}

/** The last step when it is a selection by click (its row goes on). */
export const lastClick = (steps: MaskStep[]): Selection | undefined => {
  const last = steps[steps.length - 1]
  return isClick(last) ? last : undefined
}

/** Does the mask hold anything to change (a selection with something in it, or a stroke that paints)? */
export const paints = (steps: MaskStep[]): boolean => shownSteps(steps).some((s) => s.kind === 'selection' ? (s.off?.length ?? 0) < (s.subjects ?? 1) : !s.erase)

/** A grey mask (white = selected) as white with that much opacity, in place (RGBA pixels as a canvas gives them). */
export function maskToAlpha(rgba: Uint8ClampedArray): Uint8ClampedArray {
  for (let i = 0; i < rgba.length; i += 4) {
    rgba[i + 3] = rgba[i]
    rgba[i] = rgba[i + 1] = rgba[i + 2] = 255
  }
  return rgba
}

/** The subjects' mask without those taken out (off), as white with the mask's grey as opacity, into rgba. alpha and
 *  labels: one byte per pixel (the mask's grey, the subject's number). */
export function composeSubjects(alpha: Uint8Array, labels: Uint8Array, off: number[], rgba: Uint8ClampedArray): Uint8ClampedArray {
  const keep = new Uint8Array(256).fill(1)
  for (const l of off) keep[l] = 0
  for (let p = 0, i = 0; p < alpha.length; p++, i += 4) {
    rgba[i] = rgba[i + 1] = rgba[i + 2] = 255
    rgba[i + 3] = keep[labels[p]] ? alpha[p] : 0
  }
  return rgba
}

/** The subjects' outlines in a w × h view of a W × H map of labels and the mask's grey (alpha): white, dotted for one
 *  taken out (off); RGBA. A pixel is on the line where its subject's neighbour belongs to another. */
export function subjectLines(labels: Uint8Array, alpha: Uint8Array, W: number, H: number, w: number, h: number, off: number[]): Uint8ClampedArray<ArrayBuffer> {
  const small = new Uint8Array(w * h)
  for (let y = 0; y < h; y++) {
    const fy = Math.min(H - 1, Math.max(0, ((y + 0.5) * H) / h - 0.5))
    const y0 = Math.floor(fy), y1 = Math.min(H - 1, y0 + 1), ty = fy - y0
    const row = Math.min(H - 1, Math.floor(((y + 0.5) * H) / h)) * W
    for (let x = 0; x < w; x++) {
      const fx = Math.min(W - 1, Math.max(0, ((x + 0.5) * W) / w - 0.5))
      const x0 = Math.floor(fx), x1 = Math.min(W - 1, x0 + 1), tx = fx - x0
      // like the mask's own line: a subject reaches as far as its soft edge counts (half and more), smooth when zoomed
      const top = alpha[y0 * W + x0] * (1 - tx) + alpha[y0 * W + x1] * tx
      const bottom = alpha[y1 * W + x0] * (1 - tx) + alpha[y1 * W + x1] * tx
      small[y * w + x] = top * (1 - ty) + bottom * ty >= 128 ? labels[row + Math.min(W - 1, Math.floor(((x + 0.5) * W) / w))] : 0
    }
  }
  const out = new Uint8ClampedArray(w * h * 4)
  const gone = new Uint8Array(256)
  for (const l of off) gone[l] = 1
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const p = y * w + x
      const l = small[p]
      if (!l) continue
      const edge = (x > 0 && small[p - 1] !== l) || (x < w - 1 && small[p + 1] !== l) || (y > 0 && small[p - w] !== l) || (y < h - 1 && small[p + w] !== l)
      if (!edge || (gone[l] && ((x + y) >> 2) & 1)) continue
      out.fill(255, p * 4, p * 4 + 4)
    }
  }
  return out
}
