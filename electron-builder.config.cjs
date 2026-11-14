// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// Packaging for macOS: the built app (out/), the engine scripts next to it (Resources/engines), a DMG.
// electron-builder only packages: tools/release.mjs signs (by the certificate's SHA-1, which stays unambiguous
// when the keychain holds several certificates of the same name), notarizes and builds the DMG around the
// signed app.

module.exports = {
  appId: 'de.netfx2.vulkara',
  productName: 'VulKara',
  copyright: 'Copyright © 2026 Oliver Schmidt',
  directories: { output: 'dist', buildResources: 'build' },
  files: ['out/**', 'package.json', '!**/*.map', '!out/native/**'],
  extraResources: [
    {
      from: 'engines',
      to: 'engines',
      // the tests, tools and caches of the engines are not part of the app
      filter: ['**/*', '!**/tests/**', '!**/tools/**', '!**/__pycache__/**', '!**/.pytest_cache/**', '!**/*.pyc'],
    },
    // the Apple Vision helper for "Select subject" (native/subject_mask.swift, built by `npm run native`)
    { from: 'out/native', to: 'native' },
    // the menu bar icon (index.ts: process.resourcesPath/tray)
    { from: 'build/tray', to: 'tray' },
    { from: 'LICENSE', to: 'LICENSE.txt' },
    { from: 'THIRD_PARTY_NOTICES.txt', to: 'THIRD_PARTY_NOTICES.txt' },
  ],
  asar: true,
  // the signed app runs only its own code: not as plain Node, without NODE_OPTIONS or a debugger port, only from
  // its checked app.asar
  electronFuses: {
    runAsNode: false,
    enableNodeOptionsEnvironmentVariable: false,
    enableNodeCliInspectArguments: false,
    enableEmbeddedAsarIntegrityValidation: true,
    onlyLoadAppFromAsar: true,
    grantFileProtocolExtraPrivileges: false,
  },
  mac: {
    target: [{ target: 'dmg', arch: ['arm64'] }],
    category: 'public.app-category.graphics-design',
    icon: 'build/icon.icns',
    minimumSystemVersion: '14.0',  // torch, mlx and onnxruntime of the runtimes have wheels from macOS 14 on
    identity: null,
    notarize: false,
  },
  dmg: {
    artifactName: 'VulKara-${version}-${arch}.${ext}',
    title: 'VulKara ${version}',
    sign: false,
  },
}
