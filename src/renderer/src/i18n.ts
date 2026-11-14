// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The pages' texts in the app's language (src/shared/i18n). The language is a reactive value: everything that calls
// t() while rendering (a template, a computed) follows a change at once, without a restart.
//   <script setup> import { t } from '../i18n'      <template> {{ t('settings.title') }}
// Never call t() once at module level or into a plain constant of a component's setup: that keeps the text of the
// language at that moment. Keep the key instead (title: 'settings.folders.models' as Key) and call t() in the template.

import { ref } from 'vue'
import { LOCALES, translate, value, type Args, type Key, type Lang, type LangSetting, type Language } from '@shared/i18n'
import { engineText } from '@shared/i18n/engine'

export type { Key, PlainKey } from '@shared/i18n'

/** the app's current language (System resolved by the main process) */
export const locale = ref<Lang>('en')
/** the locale for dates: macOS's region with the setting System, else the chosen language's */
const region = ref('en-US')

export function t<K extends Key>(key: K, ...args: Args<K>): string {
  return translate(locale.value, key, args[0] as Record<string, string | number> | undefined)
}

/** an engine's note on a job (one line per way it was made differently) in the app's language; unknown lines stay */
export const engineNote = (note: string): string => note.split('\n').map((line) => engineText(locale.value, line)).join('\n')

/** A key built at run time (from an id) as a text, or fallback when there is no such key. */
export function tMaybe(key: string, fallback: string): string {
  const text = translate(locale.value, key)
  return text === key ? fallback : text
}

/** The locale for numbers: the app's language, so a decimal mark matches the words around it. */
export const numLocale = (): string => LOCALES[locale.value]
/** The locale for dates: macOS's region with the language setting System, else the chosen language's. */
export const dateLocale = (): string => region.value

/** A number with a fixed count of decimals in the app's language: 2.5 -> "2.5", in German "2,5"; no grouping. */
export function num(value: number, digits = 0): string {
  return value.toLocaleString(numLocale(), { minimumFractionDigits: digits, maximumFractionDigits: digits, useGrouping: false })
}

/** A number as it comes (0.85, 12), with the language's decimal mark: in German 0,85. */
export const dec = (n: number): string => value(locale.value, n)

/** A date and time in the app's language. */
export const dateTime = (ts: number | Date, options: Intl.DateTimeFormatOptions = { dateStyle: 'medium', timeStyle: 'short' }): string =>
  new Date(ts).toLocaleString(dateLocale(), options)

function apply(language: Language): void {
  locale.value = language.lang
  region.value = language.locale
  document.documentElement.lang = language.lang
}
const localeOf = (lang: Lang): Language => ({ lang, locale: LOCALES[lang] ?? 'en-US' })

// the remote web UI cannot (and must not) change the Mac's language, so a browser keeps its own choice here and
// follows the Mac's language only while that choice is "System". The app itself always follows the Mac.
const LANG_KEY = 'vk.lang'
let followSystem = true

/** The language this browser chose (remote web UI), or "system". */
export function storedLang(): LangSetting {
  try {
    return (localStorage.getItem(LANG_KEY) as LangSetting) || 'system'
  } catch {
    return 'system'
  }
}

/** Remote web UI: switch this browser's language (kept in this browser). "system" follows the Mac again. */
export async function setLang(setting: LangSetting): Promise<void> {
  try {
    localStorage.setItem(LANG_KEY, setting)
  } catch {
    // private window: the choice lives as long as the page
  }
  followSystem = setting === 'system'
  if (followSystem) {
    try {
      apply(await window.vk.i18n.lang())
    } catch {
      // no main process
    }
  } else {
    apply(localeOf(setting))
  }
}

/** Asks the main process for the language and follows its changes (every window does this before it mounts).
 *  In a browser (remote web UI) the device's own stored choice wins over the Mac's. */
export async function startI18n(remote = false): Promise<void> {
  const pref = remote ? storedLang() : 'system'
  followSystem = pref === 'system'
  try {
    apply(await window.vk.i18n.lang())
  } catch {
    // no main process (a test page): English
  }
  if (!followSystem) apply(localeOf(pref))
  window.vk?.i18n.onLang((l) => { if (followSystem) apply(l) })
}
