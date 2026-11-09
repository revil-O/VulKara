// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The results page of the website (site/results/, written by tools/build_site_pages.mjs) and the same page as
// docs/RESULTS.md for the wikis: pictures made with VulKara at full size, with the model, the prompt, the settings
// and the time of the run. The pictures live in docs/images/results/ (the EU icon AI GENERATED put in with
// tools/example_picture.py); the prompts and settings are also in marketing/PICTURE_PROMPTS.md (Gitea only).
// A measurement behind a figure is named by its section of docs/MEASUREMENTS.md.

const MAC = 'MacBook Pro M2, 24 GB'

// pictures: [file in docs/images/results (without .jpg), caption, width, height]
export const RESULTS = [
  {
    id: 'edits', title: 'Image to image: Fibo 2.0 Edit Turbo',
    intro: 'Bria AI\'s Fibo 2.0 Edit Turbo edits a picture by instruction, repaints a masked part, or combines several pictures. The start picture was made with Z-Image Turbo. Both runtimes with the same seed: ComfyUI (int8 files, float16) for Macs with 20 GB and more, MLX (8 bit) for 16 GB Macs. 1024 × 1024, 4 steps, no guidance, seed 12.',
    items: [
      {
        title: 'An edit by instruction', prompt: 'Make it a snowy winter night with a full moon',
        runs: [['ComfyUI', '353 s, 74.9 s per step, 14.8 GB (7ai)'], ['MLX, 8 bit', '396 s, 96.3 s per step, 11.1 GB (7aj)']],
        pics: [['lighthouse', 'Start picture', 1024, 968], ['edit_snow_comfy', 'ComfyUI', 1024, 968], ['edit_snow_mlx', 'MLX, 8 bit', 1024, 968]],
      },
      {
        title: 'A masked edit (Inpainting)', prompt: 'the white base of the lighthouse tower with a small red wooden cabin beside it',
        note: 'An oval mask over the base of the tower; the rest of the picture stays pixel for pixel.',
        runs: [['ComfyUI', '352 s, 75.1 s per step, 14.8 GB (7ai)'], ['MLX, 8 bit', '397 s, 96.5 s per step, 11.0 GB (7aj)']],
        pics: [['inpaint_comfy', 'ComfyUI', 1024, 968], ['inpaint_mlx', 'MLX, 8 bit', 1024, 968]],
      },
      {
        title: 'Four pictures in one edit', prompt: 'Put the lighthouse from <image_1> as a small framed painting in the shop window of <image_2>, hang the wooden sign from <image_3> above the door and put the books from <image_4> on the window sill',
        note: 'image_1 is the lighthouse above, image_2 the bookshop below, image_3 the MOSS-Image 8-step sign further down, image_4 a 512 px shop window from Z-Image Turbo. ComfyUI kept the sign of image_2 (its lettering is wrong, a 4-step picture of Fibo 2.0 Dev); MLX hung the sign of image_3 as asked.',
        runs: [['ComfyUI', '1179 s, 276 s per step (7al: 16.2 GB with two pictures)'], ['MLX, 8 bit', '1355 s, 337 s per step (7al: 11.6 GB with two pictures)']],
        pics: [['bookshop_ref', 'image_2: the bookshop (Fibo 2.0 Dev, 4 steps)', 1024, 1024], ['two_pictures_comfy', 'ComfyUI', 1024, 1024], ['two_pictures_mlx', 'MLX, 8 bit', 1024, 1024]],
      },
    ],
  },
  {
    id: 'more-edits', title: 'Image to image: MOSS-Image and upscaling',
    intro: 'Other ways from one picture to another: MOSS-Image repaints a picture with a strength (how far it may go from the start picture), Real-ESRGAN doubles the size.',
    items: [
      {
        title: 'MOSS-Image 8-step (DMD), image to image, strength 0.6', prompt: 'a cozy bookshop window at dusk, snow falling, the hand-painted wooden sign above the door reading “VulKara Books”, photo',
        note: 'The start picture is the Fibo 2.0 Dev bookshop below (50 steps).',
        runs: [['ComfyUI', '274 s, 25.4 s per step, 8.6 GB (planned 9.2)']],
        pics: [['moss_img2img', 'MOSS-Image 8-step, 1024 × 1024, 8 steps, no guidance, seed 3', 1024, 1024]],
      },
      {
        title: 'Upscale × 2 (Real-ESRGAN)', prompt: '',
        note: 'The lighthouse above at 2048 × 2048 (the page shows it smaller; open the picture for the full size).',
        runs: [['ComfyUI', '21 s']],
        pics: [['upscale_x2', 'Real-ESRGAN × 2', 2048, 2048]],
      },
    ],
  },
  {
    id: 'text', title: 'Text to image: the bookshop sign',
    intro: 'The same prompt on the models that paint lettering, each at the maker\'s settings. The sign reads "VulKara Books" where the model got it right; the first word is not an English word, which makes it a fair test.',
    prompt: 'A cozy bookshop window at dusk, a hand-painted wooden sign above the door reading “VulKara Books”, warm light, rain on the glass, photograph',
    items: [
      { title: 'MOSS-Image, 50 steps, guidance 3', runs: [['ComfyUI', '2454 s (41 min), 47.7 s per step, 9.9 GB (7ag)']], pics: [['moss_50', 'MOSS-Image, 1024 × 1024, seed 12', 1024, 1024]] },
      { title: 'MOSS-Image 8-step (DMD), 8 steps, no guidance', runs: [['ComfyUI', '283 s, 24.6 s per step, 10.0 GB (7ag)']], pics: [['moss_dmd', 'MOSS-Image 8-step, 1024 × 1024, seed 12', 1024, 1024]] },
      { title: 'Fibo 2.0 Dev, 50 steps, guidance 5', runs: [['ComfyUI', '3643 s (61 min), 72.0 s per step, 13.4 GB (7an)']], pics: [['fibo_dev_50', 'Fibo 2.0 Dev, 1024 × 1024, seed 12', 1024, 1024]] },
      {
        title: 'Fibo 2.0 Edit Turbo, 4 steps, no guidance',
        runs: [['ComfyUI', '181 s, 35.4 s per step, 13.4 GB (7ai)'], ['MLX, 8 bit', '181 s, 42.1 s per step, 10.9 GB (7aj)']],
        pics: [['fibo_turbo_comfy', 'ComfyUI, seed 12', 1024, 1024], ['fibo_turbo_mlx', 'MLX, 8 bit, seed 12', 1024, 1024]],
      },
    ],
  },
  {
    id: 'pictures', title: 'Text to image: more models',
    intro: 'The benchmark prompt and other pictures from the measurements, each at the maker\'s settings.',
    items: [
      { title: 'FLUX.2 [klein] 9B, 4 steps', prompt: 'a lighthouse on a rocky coast at dusk, photo', runs: [['Diffusers, streamed from the SSD on a 16 GB plan', '224 s, 51.0 s per step, 10.6 GB (7ad)']], pics: [['klein9b', 'FLUX.2 [klein] 9B, 1024 × 1024, seed 12', 1024, 1024]] },
      { title: 'FLUX.2 [klein] 4B, 4 steps', prompt: 'a lighthouse on a rocky coast at dusk, photo', runs: [['Diffusers, 8 bit on a 16 GB plan', '136 s, 24.1 s per step, 9.4 GB (7aq)']], pics: [['klein4b', 'FLUX.2 [klein] 4B, 1024 × 1024, seed 12', 1024, 1024]] },
      { title: 'ERNIE-Image Turbo, 8 steps', prompt: 'a lighthouse on a rocky coast at dusk', runs: [['MLX, 4 bit', '332 s, 40.1 s per step, 9.0 GB (7aw)']], pics: [['ernie', 'ERNIE-Image Turbo, 1024 × 1024, seed 11', 1024, 1024]] },
      { title: 'Chroma1 Flash, 12 steps', prompt: 'a cozy bookshop window at dusk, photo', runs: [['Diffusers, 16 bit streamed from the SSD', '739 s, 63.3 s per step, 8.0 GB (7au)']], pics: [['chroma_flash', 'Chroma1 Flash, 1024 × 1024, seed 7', 1024, 1024]] },
      {
        title: 'Juggernaut XL (SDXL) with ControlNet Canny, 30 steps, guidance 6', prompt: 'a cozy bookshop window at dusk, photo',
        note: 'ControlNet Union ProMax, Canny at weight 0.7 from a 512 px picture made with Z-Image Turbo: the picture follows the edges, down to the shapes of the letters, which SDXL cannot spell.',
        runs: [['Diffusers', '244 s, 7.0 s per step, 12.2 GB (planned 12.7, 7as)']],
        pics: [['canny_source', 'The ControlNet picture (512 px)', 512, 512], ['sdxl_controlnet', 'Juggernaut XL + ControlNet, 1024 × 1024, seed 12', 1024, 1024]],
      },
      { title: 'NetaYume v4 (Lumina 2), 45 steps, guidance 5.5', prompt: 'a girl with silver hair reading in a library, warm light', runs: [['ComfyUI', '1349 s, 29.1 s per step, 10.6 GB (7ae)']], pics: [['netayume', 'NetaYume v4, 1024 × 1024, seed 12', 1024, 1024]] },
    ],
  },
  {
    id: 'layouts', title: 'Layouts and LoRAs',
    intro: 'MOSS-Image takes a layout as the prompt (the JSON of ComfyUI\'s layout node: where the text and the objects go) and LoRAs; Fibo 2.0 takes LoRAs on both runtimes.',
    items: [
      {
        title: 'MOSS-Image 8-step (DMD) with a layout', prompt: '{"summary":{"caption":"A poster for a bakery, warm morning light, a round loaf of bread on a wooden board, clean typography"},"items":[{"label":"text","caption":"headline in bold serif letters","text":"FRESH BREAD","bbox":[-340,-300,-220,300]},{"label":"object","caption":"a round loaf of sourdough bread on a wooden board","bbox":[-150,-250,250,250]},{"label":"text","caption":"small caption line","text":"baked every morning","bbox":[300,-200,360,200]}],"bbox_coord_space":"abs_centralized","bbox_format":"yxyx"}',
        runs: [['ComfyUI', '222 s, 15.0 s per step (7av)']],
        pics: [['moss_layout', 'MOSS-Image 8-step, 768 × 768, 8 steps, seed 3', 768, 768]],
      },
      {
        title: 'MOSS-Image 8-step (DMD) with the Destripe LoRA', prompt: 'a vintage travel poster of a lighthouse at dawn, flat colours, large sky, the words “LIGHTHOUSE POINT” in bold letters at the bottom',
        note: 'nynxz\'s Destripe LoRA (strength 1) against the fine stripes of MOSS-Image\'s flat colours.',
        runs: [['ComfyUI', '260 s, 24.7 s per step, 8.7 GB (planned 9.2)']],
        pics: [['moss_poster', 'MOSS-Image 8-step + Destripe LoRA, 1024 × 1024, 8 steps, seed 5', 1024, 1024]],
      },
      {
        title: 'Fibo 2.0 with the anime LoRA', prompt: 'fibo_seinen_style, a young woman with short dark hair reading a book at a cafe window, soft morning light',
        note: 'axiomofmind\'s Fibo-2.0-anime-lora at strength 0.9 (a 400-step pilot: the style shows little); its ComfyUI file split by VulKara for MLX, its diffusers file fused for ComfyUI.',
        runs: [['MLX, Fibo 2.0 Edit Turbo 8 bit, 4 steps', '123 s, 25.7 s per step, 11.3 GB (7ax)'], ['ComfyUI, Fibo 2.0 Dev int8, 10 steps, guidance 5', '522 s, 45.1 s per step, 13.0 GB (7ax)']],
        pics: [['fibo_anime_mlx', 'MLX, Fibo 2.0 Edit Turbo, 768 × 768, seed 5', 768, 768], ['fibo_anime_dev', 'ComfyUI, Fibo 2.0 Dev, 768 × 768, seed 5', 768, 768]],
      },
    ],
  },
  {
    id: 'video', title: 'Image to video: Wan 2.2 I2V 14B',
    intro: 'A five-second clip (77 frames at 16 fps) from the ERNIE-Image lighthouse above, Wan 2.2 I2V 14B as the app installs it (Q4_K GGUF, both experts read from the SSD per step), 832 × 480, 4 steps, seed 3; 110 minutes on the M2 (7ay: 1 s takes 8 minutes, 2 s 16, 3 s 52). The clip carries the EU icon AI GENERATED in its lower right corner.',
    items: [
      {
        title: 'Five seconds', prompt: 'the lighthouse beam sweeps slowly across the dusk sky, waves roll onto the rocks, slow push-in',
        runs: [['ComfyUI', '6601 s (110 min), 2155 s per step, 10.0 GB (7ay)']],
        video: ['wan_5s', 832, 480], pics: [['wan_5s', 'The last frame of the clip', 832, 480]],
      },
    ],
  },
]

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

function itemHtml(item) {
  const prompt = item.prompt  // a section's prompt is shown once, above its items
  const pics = item.pics.map(([f, cap, w, h]) => `
          <figure${w > h ? ' class="wide"' : ''}><a href="../assets/results/${f}.jpg"><img src="../assets/results/${f}.jpg" width="${w}" height="${h}" alt="${esc(`${item.title}: ${cap}`)}" loading="lazy" decoding="async"></a><figcaption>${esc(cap)}</figcaption></figure>`).join('')
  const video = item.video ? `
          <figure class="wide"><video src="../assets/results/${item.video[0]}.mp4" width="${item.video[1]}" height="${item.video[2]}" controls muted playsinline preload="metadata" poster="../assets/results/${item.video[0]}.jpg"></video><figcaption>The clip (MP4, 1.5 MB)</figcaption></figure>` : ''
  return `
      <article class="item">
        <h3>${esc(item.title)}</h3>${prompt ? `
        <p class="prompt">${esc(prompt)}</p>` : ''}${item.note ? `
        <p class="note">${esc(item.note)}</p>` : ''}
        <ul class="runs">${item.runs.map(([r, t]) => `<li><b>${esc(r)}</b> ${esc(t)}</li>`).join('')}</ul>
        <div class="pics">${video}${pics}
        </div>
      </article>`
}

/** The page: the same frame as the benchmarks page. */
export function resultsPage({ BASE, BLOB, VERSION, CSS_V, JS_V }) {
  const sections = RESULTS.map((s) => `
    <section class="chart" id="${s.id}">
      <h2>${esc(s.title)}</h2>
      <p class="sub">${esc(s.intro)}</p>${s.prompt ? `
      <p class="prompt">${esc(s.prompt)}</p>` : ''}${s.items.map(itemHtml).join('')}
    </section>`).join('\n')
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; media-src 'self'; style-src 'self'; script-src 'self'; base-uri 'none'; form-action 'none'">
  <meta name="referrer" content="strict-origin-when-cross-origin">
  <title>Results – VulKara</title>
  <meta name="description" content="Pictures and a video made with VulKara on a Mac, at full size: edits, masked edits, lettering, LoRAs and layouts, with the model, the prompt, the settings and the time.">
  <link rel="canonical" href="${BASE}results/">
  <meta name="color-scheme" content="light dark">
  <link rel="icon" href="../assets/icon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="../style.css?v=${CSS_V}">
  <script src="../theme.js?v=${JS_V}"></script>
</head>
<body class="changes-page bench-page results-page">
  <header class="cl-top">
    <div class="wrap">
      <a class="brand" href="../"><img src="../assets/icon.svg" width="26" height="26" alt="">VulKara<span class="ver">v${VERSION}</span></a>
      <span class="path">~/vulkara <b>$</b> results --full-size</span>
      <span class="spacer"></span>
      <a class="gh" href="../benchmarks/">benchmarks</a>
      <a class="gh" href="../changes/">changes</a>
      <a class="gh" href="${BLOB}/docs/RESULTS.md" rel="noopener">RESULTS.md ↗</a>
    </div>
  </header>
  <main id="main" class="wrap">
    <div class="intro">
      <h1>Results</h1>
      <p>Pictures made with VulKara, at full size: click a picture to open it. Every one with the model, the runtime, the prompt, the settings and the time of its run on a ${MAC}; the figures in brackets name the section of the measurement log. All of them carry the EU icon <em>AI GENERATED</em>.</p>
      <span class="stat">${RESULTS.reduce((n, s) => n + s.items.reduce((m, i) => m + i.pics.length, 0), 0)} pictures · ${RESULTS.length} sections</span>
    </div>
${sections}
  </main>
  <footer>
    <div class="wrap">
      <p class="legal"><a href="../">VulKara</a> · <a href="../impressum/">Impressum</a> · <a href="../datenschutz/">Datenschutz</a> · <a href="../benchmarks/">Benchmarks</a> · <a href="../changes/">Changes</a></p>
    </div>
  </footer>
</body>
</html>
`
}

/** docs/RESULTS.md: the same content for the wikis (the pictures from docs/images/results, the clip linked). */
export function resultsMarkdown({ BASE }) {
  const out = ['# Results', '', '[README](../README.md) · [User guide](USER_GUIDE.md) · [Measurements](MEASUREMENTS.md)', '',
    `Pictures made with VulKara, at full size, each with the model, the runtime, the prompt, the settings and the time of its run on a ${MAC}; a figure in brackets names the section of [MEASUREMENTS.md](MEASUREMENTS.md). All of them carry the EU icon *AI GENERATED*. The same page with the video: ${BASE}results/`,
    '', 'Generated by tools/build_site_results.mjs; edit the data there.', '']
  for (const s of RESULTS) {
    out.push(`## ${s.title}`, '', s.intro, '')
    if (s.prompt) out.push(`> ${s.prompt}`, '')
    for (const i of s.items) {
      out.push(`### ${i.title}`, '')
      if (i.prompt) out.push(`> ${i.prompt}`, '')
      if (i.note) out.push(i.note, '')
      for (const [r, t] of i.runs) out.push(`- **${r}**: ${t}`)
      out.push('')
      if (i.video) out.push(`The clip as MP4: ${BASE}assets/results/${i.video[0]}.mp4`, '')
      for (const [f, cap] of i.pics) out.push(`![${i.title}: ${cap}](images/results/${f}.jpg)`, '', `*${cap}*`, '')
    }
  }
  return out.join('\n')
}
