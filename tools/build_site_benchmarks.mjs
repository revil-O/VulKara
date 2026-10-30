// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The benchmarks page of the website (site/benchmarks/, written by tools/build_site_pages.mjs): the measurements of
// docs/MEASUREMENTS.md as charts. The figures below are copied from there by hand (section in `ref`); a new
// measurement goes into MEASUREMENTS.md first, then here. The charts are plain HTML and CSS (no script needed), a
// tooltip comes from site/bench.js, and every chart has its table.

import { createHash } from 'node:crypto'

const MEASURED = 'Apple M2, 24 GB'

// before → after, per step and the engine's peak (MEASUREMENTS 7m, 7n, 7o, 7ab, 7ac, 7ad, 7ae; gb left out where not measured)
const CHANGES = [
  { ref: '7n', model: 'SD 1.5 (epiCPhotoGasm), 512 px', runtime: 'Diffusers', step: [1.55, 0.72], gb: [7.3, 3.7], why: 'attention heads padded to a size the fused kernel takes' },
  { ref: '7n', model: 'SD 1.5 (epiCPhotoGasm), 1024 px', runtime: 'Diffusers', step: [9.4, 4.8], gb: [9.8, 5.0], why: 'padded heads, no attention slicing' },
  { ref: '7n', model: 'SDXL (JuggernautXL), 2048 px', runtime: 'Diffusers', step: [111, 28], gb: [17.4, 12.1], why: 'no attention slicing on MPS' },
  { ref: '7n', model: 'SDXL (JuggernautXL), 1024 px', runtime: 'Diffusers', step: [4.9, 5.0], gb: [9.0, 8.8], why: 'unchanged: its heads were fused already' },
  { ref: '7m', model: 'FLUX.1 dev, 1024 px', runtime: 'MLX, 4 bit', step: [175, 46], gb: [18.1, 13.0], why: 'decoded in tiles when the free memory is short' },
  { ref: '7m', model: 'Krea 2 Turbo, 1024 px', runtime: 'MLX, 4 bit', step: [212.5, 81.5], gb: [18.2, 16.1], range: ['211–214', '78–85', '18.2', '15.6–16.6'], why: 'decoded in tiles when the free memory is short' },
  { ref: '7o', model: 'Wan 2.2 I2V 14B, 832×480, 1 s', runtime: 'ComfyUI, Q4_K', step: [210.5, 148.3], gb: [12.7, 12.9], why: 'PyTorch attention instead of sub-quadratic' },
  { ref: '7o', model: 'NetaYume v4 (Lumina 2), 1024 px', runtime: 'ComfyUI', step: [32.45, 28.7], gb: [15.85, 14.7], range: ['31.9–33.0', '28.7', '15.5–16.2', '14.1–15.3'], why: 'PyTorch attention instead of sub-quadratic' },
  { ref: '7o', model: 'Pony V7 Q8_0 (AuraFlow), 1024 px', runtime: 'ComfyUI, GGUF', step: [46.05, 46.7], gb: [15.35, 13.0], range: ['46.0–46.1', '46.7', '14.8–15.9', '12.3–13.7'], why: 'PyTorch attention instead of sub-quadratic' },
  { ref: '7o', model: 'Anima-Turbo, 1024 px', runtime: 'ComfyUI', step: [12.1, 11.8], gb: [10.0, 10.0], why: 'PyTorch attention instead of sub-quadratic' },
  { ref: '7ae', model: 'NetaYume v4 (Lumina 2), 16 GB (8 GB wired)', runtime: 'ComfyUI', step: [30.6, 28.3], gb: [10.6, 8.7], why: 'the text encoder dropped after encoding' },
  { ref: '7ae', model: 'Pony V7 Q8_0, 16 GB (8 GB wired)', runtime: 'ComfyUI, GGUF', step: [64.7, 46.9], gb: [6.6, 9.7], why: 'whole in memory without its text encoder instead of LOW_VRAM' },
  { ref: '7ad', model: 'FLUX.2 [klein] 9B streamed, 16 GB plan, the plan counts its blocks', runtime: 'Diffusers', step: [50.4, 54.3], gb: [14.3, 10.6], why: 'blocks in flight counted at their size: 2 instead of 9 blocks kept' },
  { ref: '7ac', model: 'FLUX.2 [klein] 9B streamed, 16 GB plan, busy GPU', runtime: 'Diffusers', step: [67.0, 50.4], gb: [19.6, 14.3], why: 'at most two streamed blocks wait on the GPU' },
  { ref: '7ab', model: 'MiaoMiao RealSkin (Anima), 1024×1536, CFG 5', runtime: 'ComfyUI', step: [123.5, 92.3], range: ['117–130', '92.3'], why: 'float16 instead of bfloat16, which MPS computes at half the speed' },
  { ref: '7ab', model: 'MiaoMiao RealSkin (Anima), 512×768, CFG 5', runtime: 'ComfyUI', step: [21.2, 18.1], why: 'float16 instead of bfloat16' },
]

// the memory plan against the engine's measured peak, 1024 px (MEASUREMENTS 7m): [model, runtime, used, planned]
const PLAN = [
  ['Z-Image Turbo', 'MLX, 8 bit', 16.8, 14.9],
  ['FLUX.2 [klein] 4B', 'MLX, 8 bit', 13.3, 12.5],
  ['FLUX.2 [klein] 9B', 'MLX, 4 bit', 14.3, 14.5],
  ['Krea 2 Turbo', 'MLX, 4 bit', 18.2, 14.7],
  ['ERNIE-Image Turbo', 'MLX, 4 bit', 13.7, 11.2],
  ['FLUX 3 Image Klein', 'MLX, 6 bit', 13.1, 12.5],
  ['FLUX.1 dev', 'MLX, 4 bit', 18.1, 13.9],
  ['JuggernautXL v7', 'Diffusers, 16 bit', 8.8, 9.4],
  ['epiCPhotoGasm (SD 1.5)', 'Diffusers, 16 bit', 8.8, 3.9],
  ['SD3.5 Medium', 'Diffusers', 14.0, 14.7],
  ['Chroma1 Flash', 'Diffusers, 8 bit', 11.9, 15.5],
  ['Qwen-Image 2.1', 'Diffusers, streamed', 15.7, 13.0],
  ['AuraFlow v0.3', 'Diffusers, 8 bit', 14.6, 13.3],
]

// the plans brought to the measurements (MEASUREMENTS 7p; used = 7n for SD 1.5, the middle of 7o's range for ComfyUI)
const PLAN_AFTER = [
  ['epiCPhotoGasm (SD 1.5), 512 px', 'Diffusers, 16 bit', 3.7, 3.6],
  ['epiCPhotoGasm (SD 1.5), 1024 px', 'Diffusers, 16 bit', 5.0, 5.0],
  ['Anima-Turbo', 'ComfyUI', 10.0, 9.1],
  ['NetaYume v4 (Lumina 2)', 'ComfyUI', 14.7, 14.1],
  ['Pony V7 Q8_0 (AuraFlow)', 'ComfyUI, GGUF', 13.0, 13.9],
  ['Qwen-Image 2.1, streamed (16 GB plan)', 'Diffusers, kept blocks counted (7w)', 12.1, 11.8],
]

// work done once and kept, and a stop that waited (MEASUREMENTS 7r, 7s, 7t, 7u, 7x, 7y, 7z): before, after, unit
const ONCE = [
  { ref: '7s', what: 'Qwen-Image 2.1, whole picture', sub: '16 GB plan: text encoder quantized to 4 bit, then from the quantized cache', a: 10971, b: 221, unit: 's' },
  { ref: '7s', what: 'Qwen-Image 2.1, memory at most', sub: 'the same two pictures', a: 14.5, b: 11.8, unit: 'GB' },
  { ref: '7t', what: 'Qwen-Image 2.1, prompt from the prompt cache', sub: 'memory at most; the text encoder is not loaded, same picture to the pixel', a: 14.5, b: 12.1, unit: 'GB' },
  { ref: '7t', what: 'Qwen-Image 2.1, a prompt used before, after a restart', sub: 'whole picture: text encoder from its 4 bit copy, then the prompt from the prompt cache', a: 4264, b: 1711, unit: 's' },
  { ref: '7u', what: 'Qwen-Image 2.1, text encoder for a new prompt', sub: 'its 4 bit copy moved to the GPU and the prompt encoded: TinyGemm repacked per layer, then the plain packing', a: 2586, b: 28.9, unit: 's' },
  { ref: '7z', what: 'Qwen-Image 2.1, read from the SSD per picture', sub: 'transformer streamed in 16 bit, then in stages: text encoder alone, then the transformer whole in 8 bit (about as fast)', a: 382, b: 20, unit: 'GB' },
  { ref: '7z', what: 'Qwen-Image 2.1 in stages, memory at most', sub: 'prompt from the prompt cache: streamed (16 bit) against the transformer whole in 8 bit', a: 12.1, b: 9.9, unit: 'GB' },
  { ref: '7x', what: 'Z-Image Turbo (MLX), a prompt used before', sub: '16 GB plan, 512 px, after another prompt: the model loaded again, then its encodings from the prompt cache', a: 98.7, b: 64.4, unit: 's' },
  { ref: '7y', what: 'Engines without a job', sub: 'Z-Image Turbo (MLX) loaded: memory held after the picture, then freed after the idle time', a: 7.5, b: 1.1, unit: 'GB' },
  { ref: '7r', what: 'Stop while SSD streaming is prepared', sub: 'Chroma1 Flash, stopped at 21 %: seconds until the job ended', a: 84.9, b: 0, unit: 's' },
]

// attention alone on MPS, ComfyUI's functions, 5 runs (MEASUREMENTS 7o): [case, sub-quadratic ms, PyTorch ms, note]
const ATTENTION = [
  ['SD 1.5 at 512 px', '2 × 8 heads × 40, 4096 tokens', 108, 32, 'padded to 64'],
  ['SD 1.5 at 1024 px', '2 × 8 × 40, 16384', 2337, 494, 'padded to 64'],
  ['SDXL at 1024 px', '2 × 10 × 64, 4096', 118, 39, ''],
  ['SDXL at 2048 px', '2 × 10 × 64, 16384', 2396, 624, ''],
  ['FLUX at 1024 px', '1 × 24 × 128, 4608', 239, 122, ''],
  ['AuraFlow at 1024 px', '2 × 12 × 256, 4352', 283, 344, 'slower: head size 256'],
]

// the fused kernel by head size, 2 × 8 heads, 4096 tokens (MEASUREMENTS 7n): [label, ms, extra GB]
const HEADS = [
  ['head size 64 (fused)', 31, 0],
  ['head size 40 (not fused)', 193, 3.0],
  ['head size 40 padded to 64', 31, 0.03],
]

// seams between the VAE tiles of Qwen-Image, one latent decoded in tiles against whole (MEASUREMENTS 7v):
// [tiles, when, strongest column 0–255, mean, GB, s]
const SEAMS = [
  ['256 px, 64 px overlap', 'before', 4.4, 1.19, 1.1, 20],
  ['256 px, 128 px overlap, new blend', '16 GB plans', 2.0, 0.79, 1.15, 40],
  ['512 px, 128 px overlap, new blend', 'where the plan has room', 0.96, 0.42, 3.3, 18],
]

// the site's Content-Security-Policy allows no inline styles: every position becomes a class in charts.css
let RULES = []
const at = (css) => { RULES.push(css); return 'p' + (RULES.length - 1) }

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
const cap = (s) => s[0].toUpperCase() + s.slice(1)
const fmt = (v, d = 1) => (Math.round(v * 10 ** d) / 10 ** d).toString()
const pct = (v, max) => (Math.max(0, Math.min(1, v / max)) * 100).toFixed(2)

/** A clean axis maximum and its ticks. */
function axis(max, count = 4) {
  const raw = max / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw)
  const top = Math.ceil(max / step) * step
  return { top, ticks: Array.from({ length: Math.round(top / step) + 1 }, (_, i) => +(i * step).toFixed(6)) }
}

const legend = (a, b) => `<p class="legend"><span><i class="k a"></i>${a}</span><span><i class="k b"></i>${b}</span></p>`
const ticksRow = (ax, unit, label = 'dot-label') => `
        <div class="bx-row bx-axis" aria-hidden="true"><span class="${label}"></span><span class="bx-track">${ax.ticks.map((t) => `<span class="tick ${at(`left:${pct(t, ax.top)}%`)}">${t}${unit}</span>`).join('')}</span><span></span></div>`
const grid = (ax) => ax.ticks.map((t) => `<span class="grid ${at(`left:${pct(t, ax.top)}%`)}"></span>`).join('')

/** A dumbbell row: two values on one axis, a line between them; the tooltip carries both. */
function dumbbell({ label, sub, a, b, ax, tip, value }) {
  const [lo, hi] = a < b ? [a, b] : [b, a]
  return `
        <div class="bx-row" data-tip="${esc(tip)}" tabindex="0">
          <span class="dot-label">${esc(label)}${sub ? `<small>${esc(sub)}</small>` : ''}</span>
          <span class="bx-track">${grid(ax)}<span class="bar-link ${at(`left:${pct(lo, ax.top)}%;width:${(pct(hi, ax.top) - pct(lo, ax.top)).toFixed(2)}%`)}"></span><span class="bd a ${at(`left:${pct(a, ax.top)}%`)}"></span><span class="bd b ${at(`left:${pct(b, ax.top)}%`)}"></span></span>
          <span class="bx-value">${value}</span>
        </div>`
}

/** Two thin bars, before and after, scaled to the larger one (the tiles' microspark). */
function spark(a, b) {
  const max = Math.max(a, b)
  const w = (v) => (4 + (v / max) * 96).toFixed(1)
  return `<svg class="spark" viewBox="0 0 104 22" aria-hidden="true" focusable="false"><rect class="a" x="0" y="2" height="7" rx="3.5" width="${w(a)}"/><rect class="b" x="0" y="13" height="7" rx="3.5" width="${w(b)}"/></svg>`
}

const table = (head, rows) => `
      <details class="bx-table"><summary>Table</summary>
        <table><thead><tr>${head.map((h) => `<th>${h}</th>`).join('')}</tr></thead><tbody>
${rows.map((r) => `          <tr>${r.map((c, i) => `<td${i ? ' class="num"' : ''}>${c}</td>`).join('')}</tr>`).join('\n')}
        </tbody></table>
      </details>`

function tiles() {
  const pick = (model) => CHANGES.find((c) => c.model.startsWith(model))
  const items = [
    [pick('SD 1.5 (epiCPhotoGasm), 512'), 'step', '× faster', 'SD 1.5 at 512 px', 's per step'],
    [pick('SDXL (JuggernautXL), 2048'), 'step', '× faster', 'SDXL at 2048 px', 's per step'],
    [pick('SD 1.5 (epiCPhotoGasm), 512'), 'gb', '% less memory', 'SD 1.5 at 512 px', 'GB'],
    [pick('Wan 2.2'), 'step', '% less per step', 'Wan 2.2 video', 's per step'],
  ]
  return items.map(([c, k, unit, label, u]) => {
    const [a, b] = c[k]
    const big = unit.startsWith('×') ? fmt(a / b, 1) : Math.round((1 - b / a) * 100)
    return `
      <div class="tile" data-tip="${esc(`${label}: ${fmt(a, 2)} → ${fmt(b, 2)} ${u} (${c.runtime})`)}" tabindex="0">
        <p class="big">${big}<span>${unit}</span></p>
        <p class="what">${esc(label)}</p>
        ${spark(a, b)}
        <p class="vals"><span>${fmt(a, 2)}</span> → <span>${fmt(b, 2)}</span> ${u}</p>
      </div>`
  }).join('')
}

function speedChart() {
  // seconds per step as a share of before: one axis for models from 0.7 to 200 s
  const ax = { top: 110, ticks: [0, 25, 50, 75, 100] }
  const rows = CHANGES.map((c) => {
    const [a, b] = c.step
    const r = c.range
    const v = `${r ? r[0] : fmt(a, 2)} → ${r ? r[1] : fmt(b, 2)} s`
    return dumbbell({ label: c.model, sub: c.runtime, a: 100, b: (b / a) * 100, ax, value: v,
      tip: `${c.model} (${c.runtime}): ${v} per step, ${Math.round((b / a) * 100)} % of before. ${cap(c.why)}. MEASUREMENTS ${c.ref}` })
  }).join('')
  return `
    <section class="chart" id="speed">
      <h2>Time per step, before and after</h2>
      <p class="sub">Seconds per step as a share of before (before = 100 %), so models from under a second to minutes share one axis. The seconds are on the right.</p>
      ${legend('before', 'after')}
      <div class="bx">${ticksRow(ax, ' %')}${rows}
      </div>${table(['Model', 'Runtime', 'Before s/step', 'After s/step', 'After / before', 'Why'], CHANGES.map((c) => [esc(c.model), esc(c.runtime), c.range?.[0] ?? fmt(c.step[0], 2), c.range?.[1] ?? fmt(c.step[1], 2), Math.round((c.step[1] / c.step[0]) * 100) + ' %', esc(c.why)]))}
    </section>`
}

function memoryChart() {
  const measured = CHANGES.filter((c) => c.gb)
  const ax = axis(Math.max(...measured.flatMap((c) => c.gb)), 4)
  const rows = measured.map((c) => {
    const [a, b] = c.gb
    const r = c.range
    const v = `${r ? r[2] : fmt(a)} → ${r ? r[3] : fmt(b)} GB`
    return dumbbell({ label: c.model, sub: c.runtime, a, b, ax, value: v, tip: `${c.model} (${c.runtime}): engine at most ${v}. ${cap(c.why)}. MEASUREMENTS ${c.ref}` })
  }).join('')
  return `
    <section class="chart" id="memory">
      <h2>Memory at most, before and after</h2>
      <p class="sub">The engine's peak footprint during the picture (macOS, with what the GPU holds), in GB.</p>
      ${legend('before', 'after')}
      <div class="bx">${ticksRow(ax, '')}${rows}
      </div>${table(['Model', 'Runtime', 'Before GB', 'After GB'], measured.map((c) => [esc(c.model), esc(c.runtime), c.range?.[2] ?? fmt(c.gb[0]), c.range?.[3] ?? fmt(c.gb[1])]))}
    </section>`
}

function planChart(id, title, sub, data, ref) {
  const ax = axis(Math.max(...data.flatMap((p) => [p[2], p[3]])), 4)
  const rows = data.map(([model, rt, used, plan]) => {
    const d = used - plan
    const v = `${d >= 0 ? '+' : '−'}${fmt(Math.abs(d))} GB`
    return dumbbell({ label: model, sub: rt, a: plan, b: used, ax, value: v, tip: `${model} (${rt}): planned ${fmt(plan)} GB, used ${fmt(used)} GB (${v}). MEASUREMENTS ${ref}` })
  }).join('')
  return `
    <section class="chart" id="${id}">
      <h2>${title}</h2>
      <p class="sub">${sub}</p>
      ${legend('planned', 'measured')}
      <div class="bx">${ticksRow(ax, '')}${rows}
      </div>${table(['Model', 'Runtime', 'Planned GB', 'Measured GB', 'Difference'], data.map(([m, rt, u, p]) => [esc(m), esc(rt), fmt(p), fmt(u), (u - p >= 0 ? '+' : '−') + fmt(Math.abs(u - p))]))}
    </section>`
}

function onceTable() {
  const rows = ONCE.map((o) => {
    const max = Math.max(o.a, o.b)
    const bar = (v, cls) => `<span class="mbar ${cls} ${at(`width:${pct(v, max)}%`)}"></span>`
    const less = o.a ? Math.round((1 - o.b / o.a) * 100) : 0
    return `
          <tr data-tip="${esc(`${o.what}: ${fmt(o.a)} → ${fmt(o.b)} ${o.unit}. MEASUREMENTS ${o.ref}`)}" tabindex="0">
            <td>${esc(o.what)}<small>${esc(o.sub)}</small></td>
            <td class="bars">${bar(o.a, 'a')}${bar(o.b, 'b')}</td>
            <td class="num">${fmt(o.a)} ${o.unit}</td><td class="num">${fmt(o.b)} ${o.unit}</td>
            <td class="num">−${less} %</td>
          </tr>`
  }).join('')
  return `
    <section class="chart" id="once">
      <h2>Done once, then kept</h2>
      <p class="sub">What a cache or a fix saves on a 16 GB plan (memory kept free 12 GB on the 24 GB Mac). Each row's bars share its own scale. Also measured: an FP8 model on a Mac short of memory stopped at its first step (MPS cannot compute FP8); it now runs in 16 bit (Anima-Turbo, 4.9 GB, MEASUREMENTS 7q). Not built in: MLX's wired limit (68 % of the RAM or its recommended working set) was not faster in all three MLX models tried (MEASUREMENTS 7aa).</p>
      ${legend('before', 'after')}
      <table class="micro">
        <thead><tr><th>Case</th><th>per row</th><th class="num">before</th><th class="num">after</th><th class="num">less</th></tr></thead>
        <tbody>${rows}
        </tbody>
      </table>
    </section>`
}

function attentionTable() {
  const rows = ATTENTION.map(([name, shape, sub, sdpa, note]) => {
    const max = Math.max(sub, sdpa)
    const bar = (v, cls) => `<span class="mbar ${cls} ${at(`width:${pct(v, max)}%`)}"></span>`
    const ratio = sub / sdpa
    return `
          <tr data-tip="${esc(`${name}: sub-quadratic ${sub} ms, PyTorch ${sdpa} ms${note ? ' (' + note + ')' : ''}`)}" tabindex="0">
            <td>${esc(name)}<small>${esc(shape)}</small></td>
            <td class="bars">${bar(sub, 'a')}${bar(sdpa, 'b')}</td>
            <td class="num">${sub} ms</td><td class="num">${sdpa} ms</td>
            <td class="num ${ratio < 1 ? 'worse' : ''}">${ratio >= 1 ? fmt(ratio, 1) + '×' : '−' + Math.round((1 - ratio) * 100) + ' %'}</td>
          </tr>`
  }).join('')
  return `
    <section class="chart" id="attention">
      <h2>Attention alone: ComfyUI's two functions</h2>
      <p class="sub">One attention call per case on the GPU (MPS), 5 runs. Each row's bars share its own scale. Sub-quadratic was ComfyUI's choice on the Mac; PyTorch's fused attention is used now.</p>
      ${legend('sub-quadratic', 'PyTorch (SDPA)')}
      <table class="micro">
        <thead><tr><th>Case</th><th>per row</th><th class="num">sub-quad.</th><th class="num">PyTorch</th><th class="num">faster</th></tr></thead>
        <tbody>${rows}
        </tbody>
      </table>
    </section>`
}

function headsChart() {
  const ax = axis(Math.max(...HEADS.map((h) => h[1])), 4)
  const rows = HEADS.map(([label, ms, gb]) => `
        <div class="bx-row" data-tip="${esc(`${label}: ${ms} ms, ${gb} GB extra`)}" tabindex="0">
          <span class="dot-label">${esc(label)}</span>
          <span class="bx-track">${grid(ax)}<span class="hbar ${at(`width:${pct(ms, ax.top)}%`)}"></span></span>
          <span class="bx-value">${ms} ms · +${gb} GB</span>
        </div>`).join('')
  return `
    <section class="chart" id="heads">
      <h2>Why SD 1.5 was slow: head sizes on MPS</h2>
      <p class="sub">PyTorch's attention on Apple GPUs runs fused only for some head sizes; for the others it holds the whole attention matrix (extra GB). SD 1.5 has heads of 40. Padded with zeros to 64 it gives the same result.</p>
      <div class="bx">${ticksRow(ax, ' ms')}${rows}
      </div>${table(['Case', 'ms', 'extra GB'], HEADS.map(([l, ms, gb]) => [esc(l), ms, gb]))}
    </section>`
}

function seamsChart() {
  const ax = axis(Math.max(...SEAMS.map((r) => r[2])), 4)
  const rows = SEAMS.map(([tiles, when, col, mean, gb, sec]) => `
        <div class="bx-row" data-tip="${esc(`${tiles} (${when}): strongest column ${fmt(col, 2)}, mean ${fmt(mean, 2)}, ${fmt(gb)} GB, ${sec} s. MEASUREMENTS 7v`)}" tabindex="0">
          <span class="dot-label">${esc(tiles)}<small>${esc(when)}</small></span>
          <span class="bx-track">${grid(ax)}<span class="hbar ${at(`width:${pct(col, ax.top)}%`)}"></span></span>
          <span class="bx-value">${fmt(col, 2)} · ${fmt(gb)} GB</span>
        </div>`).join('')
  return `
    <section class="chart" id="seams">
      <h2>Seams between VAE tiles (Qwen-Image)</h2>
      <p class="sub">Qwen-Image's VAE decodes 1024 px in tiles; where they meet, plain areas showed faint streaks. The bar is the strongest column's difference to decoding whole (0–255); decoding whole needs 13.2 GB. In the real 16 GB run: 0.3 GB and 33 s more per picture, the streaks gone. Decoding is not the peak there (MEASUREMENTS 7w): sampled 9.7 GB at its start, then 7.6 GB, against up to 11.6 GB in the steps.</p>
      <div class="bx">${ticksRow(ax, '')}${rows}
      </div>${table(['Tiles', 'Used', 'Strongest column', 'Mean', 'GB', 's'], SEAMS.map(([t, w, c, m, gb, sec]) => [esc(t), esc(w), fmt(c, 2), fmt(m, 2), fmt(gb, 2), sec]))}
    </section>`
}

/** The page and its charts.css (the positions of the marks). */
export function benchmarksPage({ BASE, GH, BLOB, VERSION, CSS_V, JS_V, BENCH_V }) {
  RULES = []
  const body = [speedChart(), memoryChart(),
    planChart('plan', 'The memory plan against the measurement', 'Before every picture VulKara plans the memory a model needs and picks bit size, staging or streaming from it. Here the plan against what the engine used, 1024 px; the right column is the difference. Before the fixes of the same day (decoding in tiles, padded attention).', PLAN, '7m'),
    planChart('plan-after', 'Plans brought to the measurements', 'SD 1.5 planned at its own size with fused attention, ComfyUI models with the plan of a model held whole (shown in the benchmark since 0.7.5). The ComfyUI figures are the middle of two runs. Qwen-Image 2.1 streamed: the blocks kept in memory were not counted while denoising (planned 9.1 GB before).', PLAN_AFTER, '7p'),
    onceTable(), seamsChart(), headsChart(), attentionTable()].join('\n')
  const tileHtml = tiles()
  const css = RULES.map((r, i) => `.bench-page .p${i}{${r}}`).join('\n') + '\n'
  const cssV = createHash('sha256').update(css).digest('hex').slice(0, 10)
  const html = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; base-uri 'none'; form-action 'none'">
  <meta name="referrer" content="strict-origin-when-cross-origin">
  <title>Benchmarks – VulKara</title>
  <meta name="description" content="Measured speed and memory of VulKara's runtimes on Apple Silicon: before and after, and the memory plan against the measurement.">
  <link rel="canonical" href="${BASE}benchmarks/">
  <meta name="color-scheme" content="light dark">
  <link rel="icon" href="../assets/icon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="../style.css?v=${CSS_V}">
  <link rel="stylesheet" href="charts.css?v=${cssV}">
  <script src="../theme.js?v=${JS_V}"></script>
  <script src="../bench.js?v=${BENCH_V}" defer></script>
</head>
<body class="changes-page bench-page">
  <header class="cl-top">
    <div class="wrap">
      <a class="brand" href="../"><img src="../assets/icon.svg" width="26" height="26" alt="">VulKara<span class="ver">v${VERSION}</span></a>
      <span class="path">~/vulkara <b>$</b> benchmark --report</span>
      <span class="spacer"></span>
      <a class="gh" href="../changes/">changes</a>
      <a class="gh" href="${BLOB}/docs/MEASUREMENTS.md" rel="noopener">MEASUREMENTS.md ↗</a>
    </div>
  </header>
  <main id="main" class="wrap">
    <div class="intro">
      <h1>Benchmarks</h1>
      <p>Speed and memory of VulKara's three runtimes (Diffusers, MLX, ComfyUI), measured with the app's own benchmark
      (Hardware → Benchmark) and engine probes. Every figure is in the measurement log with how it was taken.
      <span class="stat">${MEASURED} · seconds per step of the second picture · peaks = the engine's footprint · the Mac swapped other programs throughout, so seconds compare within a row, not across rows</span></p>
    </div>
    <div class="tiles">${tileHtml}
    </div>
${body}
  </main>
  <footer>
    <div class="wrap">
      <p class="legal"><a href="../">VulKara</a> · <a href="../changes/">Changes</a> · <a href="../impressum/">Impressum</a> · <a href="../datenschutz/">Datenschutz</a> · <a href="${GH}" rel="noopener">GitHub</a></p>
    </div>
  </footer>
</body>
</html>
`
  return { html, css }
}
