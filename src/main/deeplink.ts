// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Links that open VulKara from outside (vulkara://, e.g. "Use this model" on a Hugging Face model page). Only one
// kind is taken: vulkara://import/hf?repo=<owner>/<name> opens Models → Add with the repository filled in and checked;
// nothing is downloaded until the user clicks. Anything else is dropped.

/** A Hugging Face repository id: owner and name of letters, digits, "-", "_" and "." (no "..", no path beyond). */
const REPO = /^[\w.-]{1,96}\/[\w.-]{1,96}$/

/** The page a vulkara:// link opens, or undefined when the link is not one VulKara takes. */
export function linkRoute(link: string): string | undefined {
  let url: URL
  try {
    url = new URL(link)
  } catch {
    return undefined
  }
  if (url.protocol !== 'vulkara:' || url.hostname !== 'import' || url.pathname !== '/hf') return undefined
  const repo = url.searchParams.get('repo') ?? ''
  if (!REPO.test(repo) || repo.includes('..')) return undefined
  return `/models?hf=${encodeURIComponent(repo)}`
}
