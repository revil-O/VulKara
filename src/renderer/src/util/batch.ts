// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The pictures of a batch (BatchPanel.vue): no picture twice, at most MAX_BATCH (as a benchmark's count).

export const MAX_BATCH = 100

/** current and more as one list in their order without doubles, the first max; capped: how many there were when
 *  there were more than max, else 0. */
export function mergeBatch(current: string[], more: string[], max = MAX_BATCH): { paths: string[]; capped: number } {
  const all = [...new Set([...current, ...more])]
  return { paths: all.slice(0, max), capped: all.length > max ? all.length : 0 }
}

/** Sends each picture on its own: one that fails (unreadable, refused) is noted and the rest still goes. */
export async function sendEach(paths: string[], send: (path: string) => Promise<string[]>,
  onSent: (ids: string[]) => void): Promise<string[]> {
  const errors: string[] = []
  for (const p of paths) {
    try {
      onSent(await send(p))
    } catch (err) {
      errors.push(err instanceof Error ? err.message : String(err))
    }
  }
  return errors
}
