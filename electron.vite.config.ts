// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { execSync } from 'node:child_process'
import { resolve } from 'node:path'
import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import vue from '@vitejs/plugin-vue'

/** The code state a build was made from, for telling benchmarks apart: the commit, + with changes to tracked files
 *  (not new files: the build writes a temporary copy of this config next to it), and the time of the build. */
function buildLabel(): string {
  const git = (args: string): string => {
    try {
      return execSync(`git ${args}`, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
    } catch {
      return ''  // no git (a source archive)
    }
  }
  const hash = git('rev-parse --short HEAD')
  const at = new Date().toLocaleString('sv-SE').slice(0, 16)  // "2026-10-26 15:42", local time
  return hash ? `${hash}${git('status --porcelain --untracked-files=no -- .') ? '+' : ''} ${at}` : at
}

// the processor the app is built for: VK_ARCH=x64 makes the Intel-Mac build (src/shared/edition.ts)
const ARCH = { __VK_ARCH__: JSON.stringify(process.env.VK_ARCH === 'x64' ? 'x64' : 'arm64') }

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    define: { __VK_BUILD__: JSON.stringify(buildLabel()), ...ARCH },
    resolve: { alias: { '@shared': resolve('src/shared') } },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    define: ARCH,
    resolve: { alias: { '@shared': resolve('src/shared') } },
    // a sandboxed preload script has to be CommonJS
    build: { rollupOptions: { output: { format: 'cjs', entryFileNames: '[name].cjs' } } },
  },
  renderer: {
    define: ARCH,
    plugins: [
      vue(),
      // the development server's live reload needs a websocket; the built pages connect to nothing of the kind
      { name: 'vk-csp', apply: 'build', transformIndexHtml: (html: string) => html.replace(' ws://localhost:*', '') },
    ],
    resolve: {
      alias: {
        '@': resolve('src/renderer/src'),
        '@shared': resolve('src/shared'),
      },
    },
  },
})
