// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The frames of the Scans page: turned rectangles in the scan's pixels, as engines/diffusers/scans.py finds and cuts
// them (angle in degrees, positive turns clockwise on screen; turn = quarter turns clockwise after straightening).
import type { ScanPhoto } from '@shared/api'

type Point = [number, number]

const MIN_SIDE = 10
// each corner's side of the middle: top left, top right, bottom right, bottom left
const SIDES: Point[] = [[-1, -1], [1, -1], [1, 1], [-1, 1]]

/** The frame's own directions: along its width (u) and along its height (v). */
function axes(p: ScanPhoto): [Point, Point] {
  const a = (p.angle * Math.PI) / 180
  return [[Math.cos(a), Math.sin(a)], [-Math.sin(a), Math.cos(a)]]
}

const dot = (a: Point, b: Point): number => a[0] * b[0] + a[1] * b[1]

/** Top left, top right, bottom right, bottom left. */
export function corners(p: ScanPhoto): Point[] {
  const [u, v] = axes(p)
  return SIDES.map(([sx, sy]) => {
    const du = (sx * p.w) / 2, dv = (sy * p.h) / 2
    return [p.cx + du * u[0] + dv * v[0], p.cy + du * u[1] + dv * v[1]]
  })
}

/** The frame between a fixed corner and a dragged one, along the frame's axes, never inside out. */
function between(p: ScanPhoto, fixed: Point, du: number, dv: number): ScanPhoto {
  const [u, v] = axes(p)
  return { ...p, w: Math.abs(du), h: Math.abs(dv),
    cx: fixed[0] + (du * u[0] + dv * v[0]) / 2, cy: fixed[1] + (du * u[1] + dv * v[1]) / 2 }
}

/** Corner i dragged to (x, y): the opposite corner and the angle stay. */
export function moveCorner(p: ScanPhoto, i: number, x: number, y: number): ScanPhoto {
  const fixed = corners(p)[(i + 2) % 4]
  const [u, v] = axes(p)
  const [sx, sy] = SIDES[i]
  const d: Point = [x - fixed[0], y - fixed[1]]
  return between(p, fixed, sx * Math.max(MIN_SIDE, sx * dot(d, u)), sy * Math.max(MIN_SIDE, sy * dot(d, v)))
}

/** Edge i (0 top, 1 right, 2 bottom, 3 left) dragged towards (x, y): the opposite edge stays. */
export function moveEdge(p: ScanPhoto, i: number, x: number, y: number): ScanPhoto {
  // corner i lies on edge i (top left on the top, top right on the right …); it moves along one axis only
  const corner = i
  const fixed = corners(p)[(corner + 2) % 4]
  const [u, v] = axes(p)
  const [sx, sy] = SIDES[corner]
  const d: Point = [x - fixed[0], y - fixed[1]]
  const across = i % 2 === 1
  const du = across ? sx * Math.max(MIN_SIDE, sx * dot(d, u)) : sx * p.w
  const dv = across ? sy * p.h : sy * Math.max(MIN_SIDE, sy * dot(d, v))
  return between(p, fixed, du, dv)
}

export const move = (p: ScanPhoto, dx: number, dy: number): ScanPhoto => ({ ...p, cx: p.cx + dx, cy: p.cy + dy })

export const rotateTo = (p: ScanPhoto, angle: number): ScanPhoto => ({ ...p, angle: Math.max(-45, Math.min(45, angle)) })

export const turnRight = (p: ScanPhoto): ScanPhoto => ({ ...p, turn: ((p.turn + 90) % 360) as ScanPhoto['turn'] })

/** Top and bottom of the frame on screen. */
function extent(p: ScanPhoto): [number, number] {
  const a = (p.angle * Math.PI) / 180
  const half = (Math.abs(Math.sin(a)) * p.w + Math.abs(Math.cos(a)) * p.h) / 2
  return [p.cy - half, p.cy + half]
}

/** Row by row from the top (same row when the heights overlap by more than half the smaller one), then left to right. */
export function readingOrder(photos: ScanPhoto[]): ScanPhoto[] {
  const rows: { top: number; bottom: number; photos: ScanPhoto[] }[] = []
  for (const p of [...photos].sort((a, b) => extent(a)[0] - extent(b)[0])) {
    const [top, bottom] = extent(p)
    const row = rows.find((r) => Math.min(bottom, r.bottom) - Math.max(top, r.top) > 0.5 * Math.min(bottom - top, r.bottom - r.top))
    if (row) row.photos.push(p)
    else rows.push({ top, bottom, photos: [p] })
  }
  return rows.flatMap((r) => r.photos.sort((a, b) => a.cx - b.cx))
}
