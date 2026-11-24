// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { resolve } from 'node:path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  resolve: {
    alias: {
      '@shared': resolve('src/shared'),
      '@': resolve('src/renderer/src'),
    },
  },
  define: { __VK_EDITION__: JSON.stringify('personal'), __VK_BUILD__: JSON.stringify('test'), __VK_ARCH__: JSON.stringify('arm64') },
  test: { include: ['src/**/*.test.ts'], environment: 'node' },
})
