// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// "Select subject" in the mask brush: Apple Vision finds the subject of a picture (native/subject_mask.swift, built
// into Resources/native with the app). Runs on this Mac in about a second, nothing to download.

import { execFile } from 'node:child_process'
import { existsSync, rmSync } from 'node:fs'
import { lstat, readdir, unlink } from 'node:fs/promises'
import { join } from 'node:path'
import type { SubjectMask } from '@shared/api'
import { t } from './i18n'

/** Where the selections are kept (the subject's masks and SAM's, photo_tools.segment_serve), in the data folder. */
export const selectionsDir = (data: string): string => join(data, 'inputs', 'selections')

/** Deletes the selections older than maxAgeMs that no history entry uses (at app start: the folder would grow with
 *  every click; a job of Enhance keeps its selection to be run again); the number. */
export async function pruneSelections(dir: string, keep: (path: string) => boolean = () => false, maxAgeMs = 7 * 86_400_000, now = Date.now()): Promise<number> {
  const names = await readdir(dir).catch(() => [] as string[])
  let removed = 0
  for (const name of names) {
    const path = join(dir, name)
    try {
      const st = await lstat(path)
      if (st.isFile() && now - st.mtimeMs > maxAgeMs && !keep(path)) {
        await unlink(path)
        removed++
      }
    } catch {
      // gone meanwhile or not deletable: the next start tries again
    }
  }
  return removed
}

/** The helper in the app bundle; in development the one `npm run native` built. */
export function subjectMaskHelper(packaged: boolean, resourcesPath: string, appPath: string): string {
  return packaged ? join(resourcesPath, 'native', 'subject-mask') : join(appPath, 'out', 'native', 'subject-mask')
}

/** Writes the mask of the picture's subjects (white = subject) to out, with more than one subject also which pixel
 *  belongs to which (out_labels.png); rejects with a text for the user. */
export function subjectMask(helper: string, image: string, out: string, log: (line: string) => void, timeoutMs = 60_000): Promise<SubjectMask> {
  if (!existsSync(helper)) return Promise.reject(new Error(t('main.subject.missing')))
  const labels = out.replace(/\.png$/, '') + '_labels.png'
  return new Promise((resolve, reject) => {
    execFile(helper, [image, out, labels], { timeout: timeoutMs }, (err, stdout, stderr) => {
      if (stderr.trim()) log(`subject mask: ${stderr.trim()}`)
      if (!err) {
        const subjects = Number(/subjects (\d+)/.exec(stdout)?.[1] ?? 1)
        return resolve(subjects > 1 && existsSync(labels) ? { mask: out, labels, subjects } : { mask: out, subjects })
      }
      // a helper stopped while writing leaves half a file
      for (const f of [out, labels]) rmSync(f, { force: true })
      const code = typeof err.code === 'number' ? err.code : undefined
      reject(new Error(
        code === 4 ? t('main.subject.none')
          : code === 3 ? t('main.files.choosePicture')
            : err.killed ? t('main.subject.timeout') : t('main.subject.failed'),
      ))
    })
  })
}
