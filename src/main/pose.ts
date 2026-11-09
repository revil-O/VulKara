// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Finding the people in a photo: body, hands and face of everyone for the pose editor ("main.py detect_pose"), and
// the faces Restore will restore ("main.py find_faces"), and a prompt for a picture ("main.py caption_image", Image to
// image), by the Diffusers engine (the models are downloaded on first use).

import type { ChildProcess } from 'node:child_process'
import type { Caption, DetectedPose, FoundFaces } from '@shared/api'
import type { Command } from './runtimes'
import { runTool } from './tool_process'
import { engineLine, t } from './i18n'

export function detectPose(command: Command | undefined, env: Record<string, string>, onProgress: (stage: string, percent: number) => void): Promise<DetectedPose> {
  return detect<DetectedPose>(command, env, '__pose__', () => t('main.pose.needsDiffusers'), onProgress)
}

export function findFaces(command: Command | undefined, env: Record<string, string>): Promise<FoundFaces> {
  return detect<FoundFaces>(command, env, '__faces__', () => t('main.pose.facesNeedDiffusers'), () => {})
}

export function captionImage(command: Command | undefined, env: Record<string, string>, onProgress: (stage: string, percent: number) => void, started: (proc: ChildProcess) => void): Promise<Caption> {
  return detect<Caption>(command, env, '__caption__', () => t('main.caption.needsDiffusers'), onProgress, started)
}

async function detect<T>(command: Command | undefined, env: Record<string, string>, tag: string, missing: () => string, onProgress: (stage: string, percent: number) => void, started?: (proc: ChildProcess) => void): Promise<T> {
  if (!command) throw new Error(missing())
  let result: T | undefined
  let error = ''
  const { code, stderr } = await runTool(command, env, (kind, payload) => {
    if (kind === '__progress__') onProgress(engineLine(String(payload.stage ?? '')), Number(payload.progress ?? -1))
    else if (kind === tag) result = payload as unknown as T
    else if (kind === '__error__') error = String(payload.error ?? '')
  }, started)
  if (result) return result
  throw new Error(error || stderr.trim().split('\n').pop() || `exit code ${code}`)
}
