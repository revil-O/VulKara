// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import type { ScanPhoto } from '@shared/api'
import { corners, moveCorner, moveEdge, readingOrder, rotateTo, turnRight } from './scan_frames'

const frame = (angle = 0, turn: ScanPhoto['turn'] = 0): ScanPhoto => ({ cx: 500, cy: 400, w: 300, h: 200, angle, turn })
const near = (a: [number, number], b: [number, number]): void => {
  expect(a[0]).toBeCloseTo(b[0], 2)
  expect(a[1]).toBeCloseTo(b[1], 2)
}

describe('the frames of the Scans page', () => {
  it('have their corners where the engine cuts (top left, top right, bottom right, bottom left)', () => {
    expect(corners(frame())).toEqual([[350, 300], [650, 300], [650, 500], [350, 500]])
    const [tl] = corners(frame(90 / 2))
    // turned clockwise on screen: the top left corner moves up and right of where it was
    near(tl, [500 - 150 * Math.SQRT1_2 + 100 * Math.SQRT1_2, 400 - 150 * Math.SQRT1_2 - 100 * Math.SQRT1_2])
  })

  it.each([0, 30])('keep the opposite corner when a corner is dragged (%s°)', (angle) => {
    const before = corners(frame(angle))
    const moved = moveCorner(frame(angle), 2, before[2][0] + 40, before[2][1] + 25)
    near(corners(moved)[0], before[0])
    expect(moved.angle).toBe(angle)
  })

  it('do not turn inside out when a corner is dragged past the opposite one', () => {
    const moved = moveCorner(frame(), 2, 100, 100)
    expect(moved.w).toBeGreaterThan(0)
    expect(moved.h).toBeGreaterThan(0)
    near(corners(moved)[0], [350, 300])
  })

  it('move only one side when an edge is dragged', () => {
    const moved = moveEdge(frame(), 1, 700, 999)
    expect(moved.w).toBeCloseTo(350)
    expect(moved.h).toBe(200)
    near(corners(moved)[0], [350, 300])
  })

  it('turn at most 45° each way and by quarter turns clockwise', () => {
    expect(rotateTo(frame(), 60).angle).toBe(45)
    expect(rotateTo(frame(), -50).angle).toBe(-45)
    expect(turnRight(frame(0, 270)).turn).toBe(0)
    expect(turnRight(frame(0, 90)).turn).toBe(180)
  })

  it('are numbered row by row from the top, then left to right (as the engine does)', () => {
    const a = { ...frame(), cx: 1800, cy: 700, w: 900, h: 700 }
    const b = { ...frame(), cx: 640, cy: 760, w: 900, h: 700 }
    const c = { ...frame(), cx: 700, cy: 2600, w: 900, h: 700 }
    expect(readingOrder([c, a, b])).toEqual([b, a, c])
  })
})
