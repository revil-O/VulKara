// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// "Use this model" on Hugging Face: /hf/?model_id=<owner>/<name> hands the repository to the app
// (vulkara://import/hf?repo=…); the same check as the app's (src/main/deeplink.ts), anything else opens nothing.
;(() => {
  const id = new URLSearchParams(location.search).get('model_id') || ''
  const ok = /^[\w.-]{1,96}\/[\w.-]{1,96}$/.test(id) && !id.includes('..')
  const open = document.getElementById('open')
  const what = document.getElementById('what')
  if (!ok) {
    what.textContent = 'This link names no Hugging Face model VulKara could open.'
    open.remove()
    return
  }
  const link = 'vulkara://import/hf?repo=' + encodeURIComponent(id)
  open.href = link
  open.textContent = 'Open ' + id + ' in VulKara'
  location.href = link
})()
