// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The engines write their status lines in English (engines/*: protocol.status, import and training progress). Known
// lines are shown in the app's language; a line not in this table, and every error message, stays as it is.
import { LOCALES, translate, type Key, type Lang } from '.'

type Rule = [RegExp, Key, string[]?]

const RULES: Rule[] = [
  [/^Loading model$/, 'engine.loadingModel'],
  [/^Loading model \(MLX\)$/, 'engine.loadingModelMlx'],
  [/^Loading model \(MLX, (\d+) bit\)$/, 'engine.loadingModelMlxBits', ['bits']],
  [/^Loading LoRA$/, 'engine.loadingLora'],
  [/^Loading ControlNet$/, 'engine.loadingControlnet'],
  [/^Loading the kept part of the model$/, 'engine.loadingKept'],
  [/^Loading the face model$/, 'engine.loadingFaceModel'],
  [/^Loading the filling model \(0\.2 GB, downloaded once\)$/, 'engine.loadingFillModel'],
  [/^Loading the colouring model \(0\.9 GB, downloaded once\)$/, 'engine.loadingColourModel'],
  [/^Loading the model$/, 'engine.trainLoading'],
  [/^Loading (.+) and encoding the pictures$/, 'engine.trainLoadingArch', ['name']],
  [/^Loading (.+)$/, 'engine.loading', ['what']],
  [/^Quantizing ControlNet \(one-time\)$/, 'engine.quantizingControlnet'],
  [/^Quantizing (.+) \(one-time\)$/, 'engine.quantizing', ['what']],
  [/^Saving the quantized model for faster loading \(one-time\)$/, 'engine.savingQuantized'],
  [/^Streaming the model from the SSD \(slow\)$/, 'engine.streaming'],
  [/^Model larger than memory: streaming it from the SSD \(slow\)$/, 'engine.streamingLarger'],
  [/^Preparing SSD streaming \(one-time\)$/, 'engine.preparingStreaming'],
  [/^Unpacking the GGUF file for SSD streaming \(one-time\)$/, 'engine.unpackingGguf'],
  [/^Converting FP8 model to GGUF \(one-time\)$/, 'engine.convertingFp8'],
  [/^Converting FP8 to GGUF$/, 'engine.convertingFp8Import'],
  [/^Preparing (.+) control image$/, 'engine.preparingControl', ['type']],
  [/^Encoding prompt$/, 'engine.encodingPrompt'],
  [/^Generating$/, 'engine.generating'],
  [/^Describing the picture$/, 'engine.describingPicture'],
  [/^Decoding$/, 'engine.decoding'],
  [/^Working on the picture$/, 'engine.workingOnPicture'],
  [/^Correcting colours and contrast$/, 'engine.correcting'],
  [/^Removing dust and scratches$/, 'engine.removingDust'],
  [/^Filling the damage$/, 'engine.filling'],
  [/^Checking the guard rails$/, 'engine.checkingGuardRails'],
  [/^Removing the object$/, 'engine.removingObject'],
  [/^Matching the colours$/, 'engine.matchingColours'],
  [/^Colouring$/, 'engine.colouring'],
  [/^Sharpening$/, 'engine.sharpening'],
  [/^Rebuilding details$/, 'engine.rebuilding'],
  [/^Finding faces$/, 'engine.findingFaces'],
  [/^Restoring face (\d+) of (\d+)$/, 'engine.restoringFace', ['i', 'n']],
  [/^Refining face (\d+) of (\d+)$/, 'engine.refiningFace', ['i', 'n']],
  [/^Faces refined: (\d+)$/, 'engine.facesRefined', ['n']],
  [/^Extended with FLUX\.2 \[klein\] 4B and its outpaint LoRA/, 'engine.extendedWithKlein4'],
  [/^Faces not refined: (.*)$/, 'engine.facesNotRefined', ['reason']],
  [/^Outpaint LoRA not available: extended with FLUX\.2 \[klein\] 9B$/, 'engine.outpaintLoraMissing'],
  [/^ObjectClear kept the object: filled again without it$/, 'engine.objectclearKept'],
  // notes of older jobs in the history (since 7ch klein 9B extends cleanly itself)
  [/^FLUX\.2 \[klein\] 9B extends less well/, 'engine.klein9ExtendsLess'],
  [/^LaMa not available \((.*)\), filling simply$/, 'engine.lamaMissing', ['reason']],
  [/^Downloading the upscaling model \(64 MB\)$/, 'engine.downloadingUpscaler'],
  [/^Enlarging$/, 'engine.enlarging'],
  [/^Starting ComfyUI$/, 'engine.startingComfy'],
  [/^Downloading ControlNet \(([\d.]+) GB, one-time\)$/, 'engine.downloadingControlnet', ['size']],
  [/^Downloading (.+) preprocessor \(([\d.]+) GB, one-time\)$/, 'engine.downloadingPreprocessor', ['name', 'size']],
  [/^Downloading LoRA$/, 'engine.downloadingLora'],
  [/^Downloading from Civitai$/, 'engine.downloadingCivitai'],
  [/^Downloading (.+) \((\d+) MB\)$/, 'engine.downloadingSized', ['name', 'size']],
  [/^Downloading (.+)$/, 'engine.downloading', ['name']],
  [/^Checking (.+) \(one-time\)$/, 'engine.checkingOnce', ['name']],
  [/^Copying$/, 'engine.copying'],
  [/^Copying (.+)$/, 'engine.copyingFile', ['name']],
  [/^Completing the base parts \((.*)\)$/, 'engine.completingBase', ['problem']],
  [/^Baking in$/, 'engine.baking'],
  [/^Reading LoRA (.+)$/, 'engine.readingLora', ['name']],
  [/^Saving the new model$/, 'engine.savingModel'],
  [/^Asking Civitai$/, 'engine.askingCivitai'],
  [/^Fetching preview picture$/, 'engine.fetchingPreview'],
  [/^Inspecting$/, 'engine.inspecting'],
  [/^Looking up the file on Civitai$/, 'engine.lookingUpCivitai'],
  [/^Reading the \.ckpt file$/, 'engine.readingCkpt'],
  [/^Taking (.+) from (.+)$/, 'engine.takingFrom', ['file', 'folder']],
  [/^Verifying$/, 'engine.verifying'],
  [/^Version (.+?) · (.*)$/, 'engine.version', ['name', 'note']],
  [/^Encoding (\d+) pictures?$/, 'engine.trainEncoding', ['n']],
  [/^Base model in (\d+) bit, (\d+) pictures$/, 'engine.trainBaseBits', ['bits', 'n']],
]

/** The key and values of a known status line; a trailing " 42%" is kept apart. */
export function matchEngine(line: string): { key: Key; params: Record<string, string | number>; percent: string } | undefined {
  // a status line is one short line: anything else is not looked at (the rules' groups would take long on it)
  if (line.length > 400 || line.includes('\n')) return undefined
  const m = /^(.*?)( \d+%)?$/.exec(line)
  const [text, percent] = [m?.[1] ?? line, m?.[2] ?? '']
  for (const [re, key, names] of RULES) {
    const hit = re.exec(text)
    if (!hit) continue
    const params: Record<string, string | number> = {}
    names?.forEach((name, i) => { params[name] = name === 'n' ? Number(hit[i + 1]) : hit[i + 1] })
    return { key, params, percent }
  }
  return undefined
}

/** An engine's status line in lang. Unknown lines come back unchanged. */
export function engineText(lang: Lang, line: string): string {
  if (lang === 'en' || !line) return line
  const hit = matchEngine(line)
  if (!hit) return line
  // a size like "0.40" keeps its digits, with the language's decimal mark
  for (const [k, v] of Object.entries(hit.params)) {
    const d = typeof v === 'string' ? /^\d+\.(\d+)$/.exec(v) : null
    if (d) hit.params[k] = Number(v).toLocaleString(LOCALES[lang], { minimumFractionDigits: d[1].length, maximumFractionDigits: d[1].length, useGrouping: false })
  }
  return translate(lang, hit.key, hit.params) + hit.percent
}
