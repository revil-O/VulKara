// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// A release build: checks, builds, packages, signs and (when possible) notarizes the app and its DMG.
//
//   node tools/release.mjs [--skip-checks]
//
// 0. the runtimes' Python packages are locked and the lock is the set tested on this Mac (tools/check_pins.py);
//    runs also with --skip-checks
// 1. type check, unit tests and the check that nothing of the earlier app is contained (tools/check_clean.py)
// 2. the app (electron-vite), the notices of the bundled packages, the Swift helper (swiftc), the app bundle
//    (electron-builder)
// 3. signed with the "Developer ID Application" certificate (hardened runtime, build/entitlements.mac.plist)
// 4. notarized and stapled, if the notarytool profile APPLE_KEYCHAIN_PROFILE (default "VulKara") exists;
//    create it once with: xcrun notarytool store-credentials VulKara --apple-id <Apple ID> --team-id <Team ID>
// 5. the DMG around the signed app, signed, notarized and stapled as well
//
// VK_SIGN_IDENTITY: the SHA-1 of the certificate; without it the first Developer ID Application certificate
// of the keychain is used (by its SHA-1, so several certificates of the same name do not get in the way).

import { execFileSync } from 'node:child_process'
import { existsSync, readdirSync, rmSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { signAsync } from '@electron/osx-sign'
import { notarize } from '@electron/notarize'

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)))
const DIST = join(ROOT, 'dist')
const APP = join(DIST, 'mac-arm64', 'VulKara.app')
const ENTITLEMENTS = join(ROOT, 'build', 'entitlements.mac.plist')
const PROFILE = process.env.APPLE_KEYCHAIN_PROFILE || 'VulKara'
const skipChecks = process.argv.includes('--skip-checks')
const bin = (name) => join(ROOT, 'node_modules', '.bin', name)

function step(text, cmd, args, env = {}) {
  console.log(`\n▸ ${text}`)
  execFileSync(cmd, args, { cwd: ROOT, stdio: 'inherit', env: { ...process.env, ...env } })
}

function identity() {
  if (process.env.VK_SIGN_IDENTITY) return process.env.VK_SIGN_IDENTITY
  const list = execFileSync('security', ['find-identity', '-v', '-p', 'codesigning']).toString()
  const found = /^\s*\d+\)\s+([0-9A-F]{40})\s+"Developer ID Application:/m.exec(list)
  if (!found) throw new Error('No "Developer ID Application" certificate in the keychain.')
  return found[1]
}

function hasProfile() {
  try {
    execFileSync('xcrun', ['notarytool', 'history', '--keychain-profile', PROFILE], { stdio: 'ignore' })
    return true
  } catch {
    return false
  }
}

// not skippable: no runtime package reaches a user before its version was accepted (docs/DEVELOPMENT.md)
step('runtime packages locked and accepted', 'python3', ['tools/check_pins.py'])
if (!skipChecks) {
  step('type check', 'npm', ['run', 'typecheck'])
  step('unit tests', 'npm', ['test'])
  step('nothing of the earlier app', 'python3', ['tools/check_clean.py'])
}
step('notices of the bundled packages', 'node', ['tools/gen_notices.mjs'])
step('build', bin('electron-vite'), ['build'])
step('Apple Vision helper (Select subject)', 'npm', ['run', 'native'])
// only what a release made: dist/dev holds the bundle that `npm run start:app` runs from
for (const f of existsSync(DIST) ? readdirSync(DIST) : []) if (f !== 'dev') rmSync(join(DIST, f), { recursive: true, force: true })
step('app bundle', bin('electron-builder'), ['--config', 'electron-builder.config.cjs', '--mac', 'dir', '--arm64', '--publish', 'never'])

const id = identity()
console.log(`\n▸ signing with ${id}`)
await signAsync({
  app: APP, platform: 'darwin', type: 'distribution', identity: id, identityValidation: false,
  // the Apple Vision helper runs no JavaScript: hardened runtime without the JIT exception (entitlements: [] signs with
  // an empty set; left out, osx-sign would give it its own defaults with camera, microphone and more); timestamped
  // like every file (osx-sign adds --timestamp)
  optionsForFile: (file) => file.endsWith(join('Resources', 'native', 'subject-mask'))
    ? { hardenedRuntime: true, entitlements: [] }
    : { hardenedRuntime: true, entitlements: ENTITLEMENTS },
})
step('verify the signature', 'codesign', ['--verify', '--deep', '--strict', APP])

const notarizing = hasProfile()
if (notarizing) {
  console.log('\n▸ notarizing the app (takes a few minutes)')
  await notarize({ appPath: APP, keychainProfile: PROFILE })  // staples as well
}

step('DMG', bin('electron-builder'), ['--config', 'electron-builder.config.cjs', '--mac', 'dmg', '--arm64', '--prepackaged', APP, '--publish', 'never'])
const dmg = readdirSync(DIST).filter((f) => f.endsWith('.dmg')).map((f) => join(DIST, f)).sort().pop()
step('sign the DMG', 'codesign', ['--sign', id, '--timestamp', dmg])
if (notarizing) {
  step('notarize the DMG', 'xcrun', ['notarytool', 'submit', dmg, '--keychain-profile', PROFILE, '--wait'])
  step('staple', 'xcrun', ['stapler', 'staple', dmg])
}
console.log(`\nDone: ${dmg} (${notarizing ? 'signed, notarized' : `signed, not notarized: there is no notarytool profile "${PROFILE}"`})`)
