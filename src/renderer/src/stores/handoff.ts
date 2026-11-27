// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Passing things from one page to another: a picture to continue with, the settings of an earlier job.

import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Job } from '@shared/types'

export interface Handoff {
  inputImage?: string
  /** take over prompt and settings of this job */
  job?: Job
  /** use this picture as control picture; size: the size it was made for */
  control?: { type: string; image: string; preprocess: boolean; size?: [number, number] }
  /** LoRA page: compare the strengths of this LoRA */
  loraFolder?: string
  /** Inpaint page: start from this mask (white = changes), e.g. an object selected on the Enhance page */
  maskImage?: string
  /** Restore page: these pictures as a batch, their results also into the scans' export folder */
  batch?: string[]
  exportBatch?: boolean
}

export const useHandoffStore = defineStore('handoff', () => {
  const pending = ref<Record<string, Handoff>>({})

  function send(page: string, what: Handoff): void {
    pending.value[page] = what
  }

  function take(page: string): Handoff | undefined {
    const what = pending.value[page]
    delete pending.value[page]
    return what
  }

  return { pending, send, take }
})
