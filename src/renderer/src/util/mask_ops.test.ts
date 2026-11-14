// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { composeSubjects, lastClick, maskToAlpha, nextRequest, paints, shownSteps, subjectLines, type MaskStep, type Selection } from './mask_ops'

const stroke = (erase = false): MaskStep => ({ kind: 'stroke', erase, size: 10, points: [[1, 1]] })
const click = (mask: string, clicks: [number, number, number][]): MaskStep => ({ kind: 'selection', mask, clicks })
const subject: MaskStep = { kind: 'selection', mask: 'subject.png' }

describe('mask brush steps', () => {
  it('shows only the last selection of a row of clicks, strokes and subjects all', () => {
    const a = click('a.png', [[1, 2, 1]])
    const b = click('b.png', [[1, 2, 1], [5, 5, 0]])
    const c = click('c.png', [[9, 9, 1]])
    expect(shownSteps([subject, a, b])).toEqual([subject, b])
    // a stroke ends the row: the clicks after it are a new selection, the one before stays
    expect(shownSteps([a, stroke(), c])).toEqual([a, stroke(), c])
    // undo of the last click brings the one before back
    expect(shownSteps([subject, a, b].slice(0, -1))).toEqual([subject, a])
  })

  it('goes on with the clicks of the row, or starts a new one with the whole thing', () => {
    const next = (steps: MaskStep[], c: [number, number, number]) => nextRequest(lastClick(steps), c, 10)
    expect(next([], [3, 4, 1])).toEqual({ clicks: [[3, 4, 1]], pick: 0 })
    expect(next([click('a.png', [[1, 2, 1]])], [30, 40, 0])).toEqual({ clicks: [[1, 2, 1], [30, 40, 0]] })
    expect(next([click('a.png', [[1, 2, 1]]), stroke()], [3, 4, 1])).toEqual({ clicks: [[3, 4, 1]], pick: 0 })
    expect(next([subject], [3, 4, 1])).toEqual({ clicks: [[3, 4, 1]], pick: 0 })
  })

  it('takes the next smaller candidate on a click on the same spot, round again after the smallest', () => {
    const at = (pick: number): Selection => ({ kind: 'selection', mask: 'a.png', clicks: [[100, 100, 1]], pick, candidates: 3 })
    expect(nextRequest(at(0), [105, 104, 1], 10)).toEqual({ clicks: [[100, 100, 1]], pick: 1 })
    expect(nextRequest(at(1), [100, 100, 1], 10)).toEqual({ clicks: [[100, 100, 1]], pick: 2 })
    expect(nextRequest(at(2), [100, 100, 1], 10)).toEqual({ clicks: [[100, 100, 1]], pick: 0 })
    // further away, or ⌥ (takes away): one more click of the row
    expect(nextRequest(at(0), [120, 100, 1], 10)).toEqual({ clicks: [[100, 100, 1], [120, 100, 1]] })
    expect(nextRequest(at(0), [100, 100, 0], 10)).toEqual({ clicks: [[100, 100, 1], [100, 100, 0]] })
    // after a ⌥-click the same spot is a new click, and one candidate only has nothing to go round
    expect(nextRequest({ ...at(0), clicks: [[100, 100, 0]] }, [100, 100, 1], 10).clicks).toHaveLength(2)
    expect(nextRequest({ ...at(0), candidates: 1 }, [100, 100, 1], 10).clicks).toHaveLength(2)
  })

  it('shows only the last state of a subject selection, until another selection follows', () => {
    const all: Selection = { kind: 'selection', mask: 's.png', labels: 'l.png', subjects: 3 }
    const one = { ...all, off: [2] }
    const two = { ...all, off: [2, 3] }
    expect(shownSteps([all, one, two])).toEqual([two])
    expect(shownSteps([all, one, two].slice(0, -1))).toEqual([one])
    // another "Select subject" (new mask) is its own step
    const again: Selection = { kind: 'selection', mask: 't.png' }
    expect(shownSteps([all, again])).toEqual([all, again])
    // all subjects taken out: nothing to change
    expect(paints([all, one, { ...all, off: [1, 2, 3] }])).toBe(false)
    expect(paints([all, { ...all, off: [1, 2, 3] }, stroke()])).toBe(true)
  })

  it('leaves the subjects taken out out of the mask', () => {
    const alpha = new Uint8Array([200, 255, 128, 0])
    const labels = new Uint8Array([1, 2, 2, 0])
    expect([...composeSubjects(alpha, labels, [2], new Uint8ClampedArray(16))]).toEqual([255, 255, 255, 200, 255, 255, 255, 0, 255, 255, 255, 0, 255, 255, 255, 0])
    expect([...composeSubjects(alpha, labels, [], new Uint8ClampedArray(16))].filter((_, i) => i % 4 === 3)).toEqual([200, 255, 128, 0])
  })

  it('draws a line where one subject meets another or the background', () => {
    // 8 × 4: subject 1 left, subject 2 right, touching in the middle
    const labels = new Uint8Array(32).map((_, i) => (i % 8 < 4 ? 1 : 2))
    const full = new Uint8Array(32).fill(255)
    const line = (off: number[]) => [...subjectLines(labels, full, 8, 4, 8, 4, off)].filter((_, i) => i % 4 === 3).map((a) => (a ? 1 : 0))
    const on = line([])
    // the touching columns 3 and 4 are lines, inside not
    expect([0, 1, 2, 3].map((y) => on.slice(y * 8, y * 8 + 8).join(''))).toEqual(['00011000', '00011000', '00011000', '00011000'])
    // subject 2 taken out: its line is dotted
    const dotted = line([2])
    expect(dotted.filter((_, i) => i % 8 === 3).join('')).toBe('1111')
    expect(dotted.filter((_, i) => i % 8 === 4).join('')).toBe('0000')  // (x + y) / 4 odd here: a gap of the dots
    // a smaller view samples the map
    expect(subjectLines(labels, full, 8, 4, 4, 2, []).length).toBe(4 * 2 * 4)
  })

  it('puts a subject line where its soft edge reaches half, not at the faint end', () => {
    // 8 × 1: one subject over the whole row, its edge fading out to the right
    const labels = new Uint8Array(8).fill(1)
    const alpha = new Uint8Array([255, 255, 255, 255, 200, 100, 30, 5])
    const on = [...subjectLines(labels, alpha, 8, 1, 8, 1, [])].filter((_, i) => i % 4 === 3).map((a) => (a ? 1 : 0))
    expect(on.join('')).toBe('00001000')
    // zoomed ×4: still one line, at the same place (between 200 and 100 the half lies at 4.72 → pixel 20 of 32)
    const big = [...subjectLines(labels, alpha, 8, 1, 32, 1, [])].filter((_, i) => i % 4 === 3).map((a) => (a ? 1 : 0))
    expect(big.indexOf(1)).toBe(big.lastIndexOf(1))
    expect(big.indexOf(1)).toBe(20)
  })

  it('counts a selection or a painting stroke as a mask, erasing alone not', () => {
    expect(paints([])).toBe(false)
    expect(paints([stroke(true)])).toBe(false)
    expect(paints([stroke(true), subject])).toBe(true)
    expect(paints([stroke()])).toBe(true)
  })

  it('turns a grey mask into white with its grey as opacity', () => {
    const px = new Uint8ClampedArray([0, 0, 0, 255, 128, 128, 128, 255, 255, 255, 255, 255])
    expect([...maskToAlpha(px)]).toEqual([255, 255, 255, 0, 255, 255, 255, 128, 255, 255, 255, 255])
  })
})
