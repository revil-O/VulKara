// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt

/** 75 -> "1:15 min", 40 -> "40 s", 3700 -> "1:01 h" (the pages and the menu bar menu) */
export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s} s`
  const pad = (n: number): string => String(n).padStart(2, '0')
  if (s < 3600) return `${Math.floor(s / 60)}:${pad(s % 60)} min`
  return `${Math.floor(s / 3600)}:${pad(Math.floor((s % 3600) / 60))} h`
}
