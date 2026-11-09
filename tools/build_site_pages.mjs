// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The landing page (GitHub Pages) in every language: writes site/index.html and site/<lang>/index.html from the texts
// below; tools/build_site.mjs then copies the pictures they use into site/assets.
//   node tools/build_site_pages.mjs && node tools/build_site.mjs
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { benchmarksPage } from './build_site_benchmarks.mjs'
import { resultsPage, resultsMarkdown } from './build_site_results.mjs'
import { join } from 'node:path'
import { createHash } from 'node:crypto'

const ROOT = join(import.meta.dirname, '..')
const SITE = join(ROOT, 'site')
// the stylesheet's address changes with its content: browsers keep CSS for a week (.htaccess), a new one loads at once
const BREW = 'brew install --cask revil-O/tap/vulkara'
// theme.js too: it changes rarely, but a browser keeps it like the stylesheet
const JS_V = createHash('sha256').update(readFileSync(join(SITE, 'theme.js'))).digest('hex').slice(0, 10)
const CSS_V = createHash('sha256').update(readFileSync(join(SITE, 'style.css'))).digest('hex').slice(0, 10)
// the released version beside the name: a release raises it in package.json, which also starts the deploy (site.yml)
const VERSION = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8')).version
const BASE = 'https://www.vulkara.net/'
const GH = 'https://github.com/revil-O/VulKara'
const BLOB = `${GH}/blob/main`
const DISCORD = 'https://discord.gg/SDnSHZfQY'

const LANGS = [
  { code: 'en', dir: '', name: 'English', og: 'en_US' },
  { code: 'de', dir: 'de/', name: 'Deutsch', og: 'de_DE' },
  { code: 'es', dir: 'es/', name: 'Español', og: 'es_ES' },
  { code: 'pt-BR', dir: 'pt-BR/', name: 'Português (Brasil)', og: 'pt_BR' },
  { code: 'pt-PT', dir: 'pt-PT/', name: 'Português (Portugal)', og: 'pt_PT' },
]

// screenshot, icon, height (all 1600 wide)
// the gallery: pictures made with VulKara (docs/images/gallery, with the EU icon AI GENERATED), file, width, height
const GALLERY = [
  ['greenhouse', 1200, 686], ['cat_astronaut', 1024, 1024], ['silver_gown', 1024, 1024],
  ['snow_leopard', 1024, 1024], ['hummingbird', 1024, 1024], ['sky_koi', 1200, 686],
  ['crystal_cat', 1024, 1024], ['gold_freckles', 1024, 1024], ['fox_mushroom', 1024, 1024], ['kitten_cloud', 1024, 1024],
]

// the model families: key (notes in T.*.models), name, runtimes, what they do (keys of T.*.models.caps), new
const MODELS = [
  ['flux3', 'FLUX 3 Image Klein', ['MLX'], ['pic', 'edit', 'lora', 'pup'], true],
  ['flux2', 'FLUX.2 [klein] 4B / 9B, [dev]', ['Diffusers', 'MLX'], ['pic', 'edit', 'lora', 'train']],
  ['flux1', 'FLUX.1 [schnell] / [dev]', ['Diffusers', 'MLX'], ['pic', 'inpaint', 'cn', 'lora']],
  ['zimage', 'Z-Image Turbo / Base', ['Diffusers', 'MLX'], ['pic', 'inpaint', 'lora']],
  ['krea2', 'Krea 2', ['MLX'], ['pic', 'lora', 'train']],
  ['qwen', 'Qwen-Image, Qwen-Image 2.1', ['Diffusers'], ['pic', 'edit', 'inpaint', 'lora']],
  ['ideogram4', 'Ideogram 4', ['MLX'], ['pic', 'lora']],
  ['chroma', 'Chroma', ['Diffusers'], ['pic', 'inpaint', 'lora']],
  ['sdxl', 'SDXL (Turbo, Pony, Illustrious, NoobAI)', ['Diffusers'], ['pic', 'inpaint', 'cn', 'lora', 'train']],
  ['sd35', 'Stable Diffusion 3.5', ['Diffusers'], ['pic', 'inpaint', 'cn', 'lora']],
  ['sd15', 'Stable Diffusion 1.x / 2.x', ['Diffusers'], ['pic', 'inpaint', 'cn', 'lora']],
  ['anima', 'Anima', ['ComfyUI'], ['pic', 'lora']],
  ['wan', 'Wan 2.2 5B / 14B', ['ComfyUI'], ['video']],
]

const SHOTS = [
  ['text', 1100], ['canvas', 1100], ['inpaint', 1100], ['restore', 1500],
  ['video', 1100], ['pose', 1100], ['training', 1100], ['models_recommended', 1100],
]

const T = {
  en: {
    title: 'VulKara – local AI image generator for your Mac',
    desc: 'Free AI image app with public source code for Apple-silicon Macs: text to image, inpainting, AI canvas, video, photo restoration and LoRA training. Everything runs on your Mac.',
    ogAlt: 'VulKara, your local AI image generator with high privacy',
    skip: 'Skip to content',
    nav: ['Features', 'Why VulKara', 'Screenshots', 'Get started'],
    changesNav: 'Changes',
    language: 'Language',
    menu: 'Menu',
    theme: 'Appearance',
    themes: ["Like the system", "Light", "Dark"],
    copy: 'Copy the command',
    copied: 'Copied',
    brewLabel: 'Or with Homebrew',
    download: 'Download',
    kicker: 'Free · source code open · for Macs with Apple silicon',
    tagline: 'Your local AI image generator with high privacy',
    lead: 'Turn ideas into pictures, sketches into scenes and old photos into keepers – right on your Mac. No cloud, no credits, no subscription.',
    chips: ['Creators', 'Students', 'Anime &amp; comic artists', 'Digital artists', 'Photo fans'],
    dlBig: 'Download for Mac',
    github: 'Source on GitHub',
    note: 'Free · macOS 14+ on Apple silicon · signed and notarized by Apple',
    brew: 'Or with Homebrew: <code>brew install --cask revil-O/tap/vulkara</code>',
    inspired: 'Inspired by DiffusionBee &amp; ComfyUI',
    stream: {"eyebrow": "Model streaming", "title": "Big models. Small Mac.", "lead": "VulKara streams a model from the SSD – internal or external – block by block while the picture is computed. Only the part that is working sits in memory, so models that need 24 GB run on a Mac with 16 GB, at full 16-bit quality.", "points": [["hard-drive", "Internal or external SSD", "Keep models and the streaming cache on the Mac’s SSD or on an external drive over USB or Thunderbolt. The faster the drive, the faster the picture."], ["sparkles", "Full quality", "No squeezing into 4 bits: the model keeps its 16-bit weights. As much as fits stays in memory, the rest is read ahead while the GPU works."], ["memory-stick", "Automatic", "The memory plan decides for each model: it runs in RAM when it fits, and is streamed from the SSD (internal/external) when it does not. SSD streaming can also be switched off by hand!"]], "fine": "Tested on a Mac mini M4 with 16 GB: FLUX.1 [dev], Krea 2 and Qwen-Image 2.1 run. Streaming trades speed for size – big models take minutes per picture."},
    bannerAlt: 'Five pictures made with VulKara: a lighthouse on a rocky coast, a fox in a snowy forest, a neon city street at night, an astronaut in a greenhouse dome and a cabin by a lake in autumn',
    bannerCap: 'Made with VulKara on an M2: Juggernaut XL v7, styles Cinematic, Digital Art, Neon Punk, Fantasy Art and Analog Film.',
    galEyebrow: "Gallery",
    galTitle: "Made on a Mac. Not in the cloud.",
    galLead: "Every picture here was made with VulKara on a MacBook Pro M2 with Z-Image Turbo, from one sentence each, in about five minutes per picture.",
    galCaps: {"greenhouse": "A glass greenhouse floating above a misty forest", "silver_gown": "A gown of liquid silver", "snow_leopard": "Snow leopard with morpho butterflies", "cat_astronaut": "Orange cat among glowing jellyfish", "crystal_cat": "Black cat on crystal books", "sky_koi": "Koi swimming through a neon city", "gold_freckles": "Freckles, gold leaf and white flowers", "fox_mushroom": "A fox asleep under a glowing mushroom", "hummingbird": "A hummingbird of stained glass", "kitten_cloud": "A white kitten asleep in a teacup on a cloud"},
    models: {"nav": "Models", "eyebrow": "Supported models", "title": "Every big model family, one app", "lead": "Install them from a list of tested models or import them from Hugging Face, Civitai or a file. VulKara picks the right runtime for each one and plans the memory for your Mac.", "fine": "Models are never part of the app: they are downloaded when you choose them. Each one has its own licence, and the Licenses page in the app tells whether it and its pictures may be used commercially.", "new": "New", "made": "Picture made with", "caps": {"pic": "Pictures", "edit": "Edit with a reference", "inpaint": "Inpainting", "cn": "ControlNet", "lora": "LoRAs", "train": "Training", "video": "Video", "pup": "Prompt upsampler"}, "notes": {"sd15": "The classic with thousands of fine-tunes; runs with 8 GB.", "sdxl": "The largest choice of fine-tunes and LoRAs: photo, anime, illustration.", "sd35": "Stability AI's third generation.", "flux1": "Detailed and photoreal; [schnell] needs only 4 steps.", "chroma": "An open model built on FLUX.1, under Apache 2.0.", "flux2": "Takes your picture as a reference; [klein] also learns your own LoRAs.", "flux3": "Black Forest Labs' newest. The 6 and 8 bit versions run on a Mac with 16 GB.", "qwen": "Strong at lettering inside the picture; 2.1 as GGUF.", "zimage": "Fast and photoreal – the gallery above was made with Z-Image Turbo.", "krea2": "Aesthetic photos; runs on 16 GB with SSD streaming.", "ideogram4": "Ideogram's model on the MLX runtime.", "anima": "Anime and illustration.", "wan": "Image to video: 1–5 seconds at 480p or 720p."}},
    featEyebrow: 'Features',
    featTitle: 'One app, a whole studio',
    bench: ['Benchmark: measure your Mac', 'Pick a model and measure it on your own Mac: seconds per step, the whole picture, the most memory VulKara and the system used, swap, what was read from the SSD, and every phase from loading to generating. Copy the runs as a table and compare Macs, sizes and bit sizes. The same measurements made VulKara faster: SD 1.5 twice as fast with half the memory, large SDXL pictures four times as fast.', 'See the measurements'],
    news: [['scan-text', "Prompt from picture", "Choose a picture in Image to image and press <b>Prompt from picture</b>: Qwen3-VL 2B describes subject, setting, light, colours, style and camera in one paragraph, on the Mac, in about 15 seconds on a Mac mini M4 with 16 GB. Change it, then generate."], ['activity', "Menu bar and Monitor", "Close the window and VulKara keeps running with its icon in the menu bar: the running job, its progress, what waits. <b>Monitor</b> shows the job against its memory plan and, on the measured Mac, against the measurements of its model."]],
    featLead: 'Pictures, edits, video and your own LoRAs – for creators, students, comic and anime fans and digital artists.',
    feats: [
      ['type', 'Text to image', 'Describe it, pick a style, press ⌘↩. Twenty styles from photo to illustration and 3D, and up to three LoRAs, each with its own weight.'],
      ['eraser', 'Image to image and inpainting', 'Keep the motif, change the scene. Or paint over just the part that should change – the rest stays untouched.'],
      ['frame', 'AI Canvas', 'An endless surface: move the frame over the edge and Generate continues the picture. Paint a mask to redo a part.'],
      ['clapperboard', 'Image to video', 'Bring a picture to life with Wan 2.2: describe the movement and get 1–5 seconds at 480p or 720p.'],
      ['maximize-2', 'Upscale and photo tools', '2× or 4× with Real-ESRGAN, plus sharpen, denoise, remove JPEG artefacts, remove the background and select objects with a click.'],
      ['wand-sparkles', 'Restore old photos', 'Colour casts, dust and scratches fixed, blurred faces restored, black-and-white photos coloured.'],
      ['person-standing', 'Pose editor', 'OpenPose skeletons with hands and faces, templates, or a pose detected from a photo – then use it in Text to image.'],
      ['sparkles', 'Illusions', 'Hide a spiral, a pattern, a word or a logo inside a picture.'],
      ['graduation-cap', 'LoRA training', 'Teach a model your art style or character from 10–30 of your own pictures, on SDXL, FLUX.2 [klein] or Krea 2, with a live loss curve.'],
      ['boxes', 'Many models', 'SD 1.5, SDXL (also Pony, Illustrious, NoobAI), SD 3.5, FLUX.1, FLUX.2, FLUX 3, Chroma, Qwen-Image, Z-Image, Krea 2, Ideogram 4, Anima and Wan 2.2 video. Download straight from a list of tested models, import from Hugging Face or Civitai (an API token may be needed) by link (URL or creator/model name), or from a model file you already downloaded.'],
    ],
    whyEyebrow: 'Why VulKara',
    whyTitle: 'Your ideas stay yours',
    why: [
      ['monitor', 'Everything on your Mac', ['Pictures, videos, restorations and training run on the Apple GPU. Your prompts and pictures never leave the Mac – the internet is only used to download runtimes, models and LoRA descriptions and to look for updates. Disconnect your Mac from the network and try it – it also works completely offline (once every package it depends on has been downloaded!)']],
      ['tablet-smartphone', 'From your phone, on your own network', ['Open VulKara in a browser on your phone, tablet or another computer, on your home network or over a VPN connection. See the current status of your pictures, type in and start new ideas while you are out, and look through, download or share finished pictures in the history. Only your Mac computes. Access is secured by an access token and encrypted over HTTPS, to keep your privacy here too.'], 'Switch it on once, scan the QR code, done. Nothing goes to the internet.'],
      ['heart', 'Free, no strings', ['No account, no subscription, no credits. The source code is open: read it, change it, share it for any noncommercial use.'], 'Some models ask for a free Hugging Face or Civitai token before they download.'],
      ['hard-drive', 'Runs on small Macs too', ['A model too big for the memory streams from the SSD block by block, at full quality. On a Mac mini M4 with 16 GB, FLUX.1 [dev], Krea 2 and Qwen-Image 2.1 run.'], 'Streaming trades speed for size: big models take minutes per picture. Stable Diffusion 1.5 runs with 8 GB.'],
      ['languages', 'Speaks your language', ['English, Deutsch, Español, Português (Brasil) and Português (Portugal) – the app and the user guide. Yours is missing? A new language is a folder of text files.']],
    ],
    stepsEyebrow: 'Get started',
    stepsTitle: 'Your first picture in 3 steps',
    steps: [
      ['Install', 'Download the DMG, open it and drag VulKara into <b>Applications</b>.'],
      ['Runtime and model', '<b>Settings → Runtimes</b>: install <b>Diffusers (Apple GPU)</b>. Then <b>Models → Recommended</b>: <i>SDXL 1.0</i> with 16 GB, <i>Stable Diffusion 1.5</i> with 8 GB.'],
      ['Create', 'Open <b>Text</b>, describe your picture and press <b>⌘↩</b>. The Start page ticks off each step.'],
    ],
    shotsEyebrow: 'Screenshots',
    shotsTitle: 'Take a look inside',
    shotsOpen: 'opens the full-size screenshot',
    shots: {
      text: ['Text to image', 'prompt, model, style, size and LoRAs on one page'],
      canvas: ['AI Canvas', 'continue a picture beyond its edges'],
      inpaint: ['Inpainting', 'repaint only what you mark'],
      restore: ['Restore', 'old photos with a before-and-after slider'],
      video: ['Image to video', 'a start picture and a description of the movement'],
      pose: ['Pose editor', 'skeletons with hands and faces'],
      training: ['Training', 'a LoRA from your own pictures'],
      models_recommended: ['Recommended models', 'with the memory and download size for your Mac'],
    },
    respTitle: 'Developed responsibly',
    resp: [
      'every prompt and every result is checked before it is shown',
      'the protection of minors is always on',
      'before real photos are edited, we ask for consent',
      'every picture gets an AI note in its metadata',
      'the visible “AI GENERATED” label can be switched on with one click',
    ],
    linksEyebrow: 'Learn more',
    linksTitle: 'Guides, news and code',
    links: [
      ['lightbulb', 'User guide', 'every page and setting', `${BLOB}/docs/USER_GUIDE.md`],
      ['scroll-text', 'Wiki', 'guides and help', `${GH}/wiki`],
      ['messages-square', 'Discord', 'community and help', DISCORD],
      ['file-clock', 'Changelog', 'what is new?', `${BLOB}/CHANGELOG.md`],
      ['languages', 'Translate VulKara', 'add your language (if it is missing)', `${BLOB}/docs/TRANSLATING.md`],
      ['scale', 'Licence', 'PolyForm Noncommercial 1.0.0', `${BLOB}/LICENSE`],
    ],
    supportTitle: 'Made in spare time. Kept going by coffee.',
    support: 'VulKara is free for everyone. If it is useful to you, buy me a coffee for further development: adding new models, fixes and more.',
    coffee: 'Buy me a coffee',
    pose3d: {"title": "Pose editor in 3D", "alt": "An OpenPose skeleton turning in space: the camera walks around the pose", "cap": "Animated sketch of the idea, not the finished editor.", "lead": "Turn a pose freely in space and look at your figure from any angle: from the front, the side, above or a worm’s-eye view. The result goes into Text to image as a pose, as before.", "points": [["rotate-3d", "Turn freely", "Drag the figure to move the camera around it, up and down. Fixed views with one click: from the front, from the side, from behind, from above."], ["bone", "Joints like a body", "Dragging a point turns its joint, and the bones keep their length. Head, shoulders, hips, knees and fingers stay within natural limits – switch them off for acrobatics."], ["bookmark", "Save your poses", "Keep a pose and its viewpoint as a template, load it again, rename it or pass it on as a file."], ["users", "For your characters", "A saved pose goes straight into a character scene, together with its viewpoint."]]},
    next: ["Next planned features", "Your own characters", "Create a character once – face, hair, outfit, style – and put them into any scene as a reference: comic panels, anime shots, a whole story. The same character in every picture. Made and kept on your Mac, like everything else.", "Planned, but no date yet. That takes a lot of coffee ;)"],
    nextPill: 'Planned new features',
    nextCap: "One character, seven pictures: the reference and six scenes, made with VulKara today (FLUX.2 klein with the reference picture on the Image page). The feature will make it a few clicks.",
    nextAlts: {"mira": "Mira, the reference", "cafe": "Sketching in a café", "rooftop": "On a rooftop at sunset", "neon": "Neon street in the rain", "mountain": "Hiking at dawn", "anime": "As an anime character", "comic": "As a comic panel"},
    footAi: 'The pictures made with VulKara on this page carry the EU icon AI GENERATED.',
    foot: '© 2026 Oliver Schmidt<br>VulKara is free for noncommercial use under the PolyForm Noncommercial License 1.0.0. This page sets no cookies and loads nothing from other servers.',
    legal: ['Legal notice (Impressum)', 'Privacy'],
    footPrivate: 'VulKara is a purely private project and is not associated or affiliated with any outside company.',
    footTm: 'Apple, Mac and macOS are trademarks of Apple Inc. VulKara is not affiliated with Apple.',
  },

  de: {
    title: 'VulKara – lokaler KI-Bildgenerator für deinen Mac',
    desc: 'Kostenlose App mit offenem Quellcode für KI-Bilder auf Macs mit Apple-Chip: Text zu Bild, Inpainting, KI-Leinwand, Video, Fotos restaurieren und LoRA-Training. Alles läuft auf deinem Mac.',
    ogAlt: 'VulKara, dein lokaler KI-Bildgenerator mit hohem Datenschutz',
    skip: 'Zum Inhalt springen',
    nav: ['Funktionen', 'Warum VulKara', 'Screenshots', 'Loslegen'],
    changesNav: 'Änderungen',
    language: 'Sprache',
    menu: 'Menü',
    theme: 'Darstellung',
    themes: ["Wie das System", "Hell", "Dunkel"],
    copy: 'Befehl kopieren',
    copied: 'Kopiert',
    brewLabel: 'Oder mit Homebrew',
    download: 'Download',
    kicker: 'Kostenlos · Quellcode offen · für Macs mit Apple-Chip',
    tagline: 'Dein lokaler KI-Bildgenerator mit hohem Datenschutz',
    lead: 'Mach aus Ideen Bilder, aus Skizzen Szenen und aus alten Fotos wieder Lieblingsstücke – direkt auf deinem Mac. Keine Cloud, keine Credits, kein Abo.',
    chips: ['Creator', 'Studierende', 'Anime- und Comic-Zeichner', 'Digital Artists', 'Foto-Fans'],
    dlBig: 'Download für Mac',
    github: 'Quellcode auf GitHub',
    note: 'Kostenlos · macOS 14+ auf Apple-Chip · signiert und von Apple notarisiert',
    brew: 'Oder mit Homebrew: <code>brew install --cask revil-O/tap/vulkara</code>',
    inspired: 'Inspiriert von DiffusionBee &amp; ComfyUI',
    stream: {"eyebrow": "Modell-Streaming", "title": "Große Modelle. Kleiner Mac.", "lead": "VulKara streamt ein Modell von der SSD – intern oder extern – Block für Block, während das Bild entsteht. Nur der Teil, der gerade rechnet, liegt im Arbeitsspeicher. So laufen Modelle, die 24 GB brauchen, auf einem Mac mit 16 GB, in voller 16-Bit-Qualität.", "points": [["hard-drive", "Interne oder externe SSD", "Leg Modelle und den Streaming-Cache auf die SSD des Macs oder auf ein externes Laufwerk an USB oder Thunderbolt. Je schneller das Laufwerk, desto schneller das Bild."], ["sparkles", "Volle Qualität", "Kein Zusammenquetschen auf 4 Bit: Das Modell behält seine 16-Bit-Gewichte. Was passt, bleibt im Speicher, der Rest wird vorausgelesen, während die GPU rechnet."], ["memory-stick", "Automatisch", "Der Speicherplan entscheidet für jedes Modell: läuft im RAM, wenn es hineinpasst, wird von SSD (intern/extern) gestreamt, wenn nicht. SSD-Streaming kann auch manuell abgeschaltet werden!"]], "fine": "Getestet auf einem Mac mini M4 mit 16 GB: FLUX.1 [dev], Krea 2 und Qwen-Image 2.1 laufen. Streaming tauscht Tempo gegen Größe – große Modelle brauchen Minuten pro Bild."},
    bannerAlt: 'Fünf mit VulKara erstellte Bilder: ein Leuchtturm an einer Felsküste, ein Fuchs im verschneiten Wald, eine Neon-Straße bei Nacht, ein Astronaut in einer Gewächshauskuppel und eine Hütte am See im Herbst',
    bannerCap: 'Mit VulKara auf einem M2 erstellt: Juggernaut XL v7, Stile Cinematic, Digital Art, Neon Punk, Fantasy Art und Analog Film.',
    galEyebrow: "Galerie",
    galTitle: "Auf dem Mac gemacht. Nicht in der Cloud.",
    galLead: "Jedes Bild hier ist mit VulKara auf einem MacBook Pro M2 mit Z-Image Turbo entstanden, aus jeweils einem Satz, in etwa fünf Minuten pro Bild.",
    galCaps: {"greenhouse": "Ein Glas-Gewächshaus schwebt über dem Nebelwald", "silver_gown": "Ein Kleid aus flüssigem Silber", "snow_leopard": "Schneeleopard mit Morphofaltern", "cat_astronaut": "Rote Katze zwischen leuchtenden Quallen", "crystal_cat": "Schwarze Katze auf Kristallbüchern", "sky_koi": "Kois schwimmen durch eine Neonstadt", "gold_freckles": "Sommersprossen, Blattgold und weiße Blüten", "fox_mushroom": "Ein Fuchs schläft unter einem leuchtenden Pilz", "hummingbird": "Ein Kolibri aus Buntglas", "kitten_cloud": "Ein weißes Kätzchen schläft in einer Teetasse auf einer Wolke"},
    models: {"nav": "Modelle", "eyebrow": "Unterstützte Modelle", "title": "Alle großen Modellfamilien, eine App", "lead": "Installiere sie aus einer Liste getesteter Modelle oder importiere sie von Hugging Face, Civitai oder aus einer Datei. VulKara wählt für jedes die passende Runtime und plant den Speicher für deinen Mac.", "fine": "Modelle sind nie Teil der App: Sie werden geladen, wenn du sie auswählst. Jedes hat seine eigene Lizenz, und die Seite Lizenzen in der App sagt, ob es und seine Bilder kommerziell genutzt werden dürfen.", "new": "Neu", "made": "Bild erstellt mit", "caps": {"pic": "Bilder", "edit": "Bearbeiten mit Referenz", "inpaint": "Inpainting", "cn": "ControlNet", "lora": "LoRAs", "train": "Training", "video": "Video", "pup": "Prompt-Upsampler"}, "notes": {"sd15": "Der Klassiker mit Tausenden Fine-Tunes; läuft mit 8 GB.", "sdxl": "Die größte Auswahl an Fine-Tunes und LoRAs: Foto, Anime, Illustration.", "sd35": "Die dritte Generation von Stability AI.", "flux1": "Detailreich und fotorealistisch; [schnell] braucht nur 4 Schritte.", "chroma": "Ein offenes Modell auf Basis von FLUX.1, unter Apache 2.0.", "flux2": "Nimmt dein Bild als Referenz; [klein] lernt auch deine eigenen LoRAs.", "flux3": "Das neueste von Black Forest Labs. Die 6- und 8-Bit-Fassungen laufen auf einem Mac mit 16 GB.", "qwen": "Stark bei Schrift im Bild; 2.1 als GGUF.", "zimage": "Schnell und fotorealistisch – die Galerie oben ist mit Z-Image Turbo entstanden.", "krea2": "Ästhetische Fotos; läuft mit SSD-Streaming auf 16 GB.", "ideogram4": "Das Modell von Ideogram auf der MLX-Runtime.", "anima": "Anime und Illustration.", "wan": "Bild zu Video: 1–5 Sekunden in 480p oder 720p."}},
    featEyebrow: 'Funktionen',
    featTitle: 'Eine App, ein ganzes Studio',
    bench: ['Benchmark: miss deinen Mac', 'Wähle ein Modell und miss es auf deinem eigenen Mac: Sekunden pro Schritt, das ganze Bild, den meisten Speicher von VulKara und vom System, Swap, was von der SSD gelesen wurde, und jede Phase vom Laden bis zum Erzeugen. Kopiere die Läufe als Tabelle und vergleiche Macs, Größen und Bit-Größen. Dieselben Messungen haben VulKara schneller gemacht: SD 1.5 doppelt so schnell mit halbem Speicher, große SDXL-Bilder viermal so schnell.', 'Zu den Messungen'],
    news: [['scan-text', "Prompt aus Bild", "Wähle in „Bild zu Bild“ ein Bild und drücke <b>Prompt aus Bild</b>: Qwen3-VL 2B beschreibt Motiv, Umgebung, Licht, Farben, Stil und Kamera in einem Absatz, auf dem Mac, in etwa 15 Sekunden auf einem Mac mini M4 mit 16 GB. Ändere ihn, dann erstelle."], ['activity', "Menüleiste und Monitor", "Schließ das Fenster, und VulKara läuft mit seinem Symbol in der Menüleiste weiter: der laufende Auftrag, sein Fortschritt, was wartet. <b>Monitor</b> zeigt den Auftrag gegen seinen Speicherplan und auf dem gemessenen Mac gegen die Messwerte seines Modells."]],
    featLead: 'Bilder, Bearbeitung, Video und eigene LoRAs – für Creator, Studierende, Comic- und Anime-Fans und Digital Artists.',
    feats: [
      ['type', 'Text zu Bild', 'Beschreib es, wähl einen Stil, drück ⌘↩. Zwanzig Stile von Foto bis Illustration und 3D, dazu bis zu drei LoRAs, jede mit eigenem Gewicht.'],
      ['eraser', 'Bild zu Bild und Inpainting', 'Motiv behalten, Szene wechseln. Oder nur den Teil übermalen, der sich ändern soll – der Rest bleibt unberührt.'],
      ['frame', 'KI-Leinwand', 'Eine endlose Fläche: Schieb den Rahmen über den Rand, und Erstellen setzt das Bild fort. Mit einer Maske malst du einen Teil neu.'],
      ['clapperboard', 'Bild zu Video', 'Erweck ein Bild mit Wan 2.2 zum Leben: Beschreib die Bewegung und bekomm 1–5 Sekunden in 480p oder 720p.'],
      ['maximize-2', 'Vergrößern und Fotowerkzeuge', '2× oder 4× mit Real-ESRGAN, dazu schärfen, entrauschen, JPEG-Artefakte entfernen, Hintergrund entfernen und Objekte per Klick auswählen.'],
      ['wand-sparkles', 'Alte Fotos restaurieren', 'Farbstiche, Staub und Kratzer behoben, unscharfe Gesichter wiederhergestellt, Schwarzweißfotos eingefärbt.'],
      ['person-standing', 'Pose-Editor', 'OpenPose-Skelette mit Händen und Gesichtern, Vorlagen oder eine Pose aus einem Foto erkannt – dann ab damit in Text zu Bild.'],
      ['sparkles', 'Illusionen', 'Versteck eine Spirale, ein Muster, ein Wort oder ein Logo in einem Bild.'],
      ['graduation-cap', 'LoRA-Training', 'Bring einem Modell deinen Zeichenstil oder deinen Charakter bei, mit 10–30 eigenen Bildern, auf SDXL, FLUX.2 [klein] oder Krea 2, mit Live-Verlustkurve.'],
      ['boxes', 'Viele Modelle', 'SD 1.5, SDXL (auch Pony, Illustrious, NoobAI), SD 3.5, FLUX.1, FLUX.2, FLUX 3, Chroma, Qwen-Image, Z-Image, Krea 2, Ideogram 4, Anima und Wan 2.2 für Video. Aus einer Liste getesteter Modelle direkt herunterladbar, importieren von Hugging Face oder Civitai (ggf. API-Token benötigt) per Link (URL oder Creator/ModellName) oder aus einer bereits heruntergeladenen Modell-Datei.'],
    ],
    whyEyebrow: 'Warum VulKara',
    whyTitle: 'Deine Ideen bleiben deine',
    why: [
      ['monitor', 'Alles auf deinem Mac', ['Bilder, Videos, Restaurierungen und Training laufen auf der Apple-GPU. Deine Prompts und Bilder verlassen den Mac nie – das Internet dient nur zum Herunterladen von Runtimes, Modellen und LoRA-Beschreibungen und zur Suche nach Updates. Trenne deinen Mac vom Netzwerk und probier es aus – es funktioniert auch komplett offline (wenn alle abhängigen Software-Pakete vorher geladen wurden!)']],
      ['tablet-smartphone', 'Vom Handy aus, im eigenen Netz', ['Öffne VulKara im Browser auf Handy, Tablet oder einem anderen Rechner, im Heimnetzwerk oder via VPN-Verbindung. Sieh den aktuellen Bildstatus, gib neue Ideen schon unterwegs ein und starte sie, und sieh dir fertige Bilder im Verlauf an, lade sie herunter oder teile sie. Gerechnet wird nur auf deinem Mac. Der Zugang ist mit einem Zugangstoken gesichert und über HTTPS verschlüsselt, um auch hier Privatsphäre zu garantieren.'], 'Einmal einschalten, den QR-Code scannen, fertig. Nichts geht dabei ins Internet.'],
      ['heart', 'Kostenlos, ohne Haken', ['Kein Konto, kein Abo, keine Credits. Der Quellcode ist offen: Lies ihn, änder ihn, gib ihn weiter, für jede nicht kommerzielle Nutzung.'], 'Manche Modelle verlangen vor dem Download einen kostenlosen Token von Hugging Face oder Civitai.'],
      ['hard-drive', 'Läuft auch auf kleinen Macs', ['Ein Modell, das nicht in den Arbeitsspeicher passt, wird Block für Block von der SSD gestreamt, in voller Qualität. Auf einem Mac mini M4 mit 16 GB laufen FLUX.1 [dev], Krea 2 und Qwen-Image 2.1.'], 'Streaming tauscht Tempo gegen Größe: Große Modelle brauchen Minuten pro Bild. Stable Diffusion 1.5 läuft mit 8 GB.'],
      ['languages', 'Spricht deine Sprache', ['English, Deutsch, Español, Português (Brasil) und Português (Portugal) – die App und das Handbuch. Deine fehlt? Eine neue Sprache ist ein Ordner mit Textdateien.']],
    ],
    stepsEyebrow: 'Loslegen',
    stepsTitle: 'Dein erstes Bild in 3 Schritten',
    steps: [
      ['Installieren', 'Lad das DMG, öffne es und zieh VulKara in <b>Programme</b>.'],
      ['Runtime und Modell', '<b>Einstellungen → Runtimes</b>: <b>Diffusers (Apple GPU)</b> installieren. Dann <b>Modelle → Empfohlen</b>: <i>SDXL 1.0</i> mit 16 GB, <i>Stable Diffusion 1.5</i> mit 8 GB.'],
      ['Erstellen', 'Öffne <b>Text</b>, beschreib dein Bild und drück <b>⌘↩</b>. Die Start-Seite hakt jeden Schritt ab.'],
    ],
    shotsEyebrow: 'Screenshots',
    shotsTitle: 'Ein Blick hinein',
    shotsOpen: 'öffnet den Screenshot in voller Größe',
    shots: {
      text: ['Text zu Bild', 'Prompt, Modell, Stil, Format und LoRAs auf einer Seite'],
      canvas: ['KI-Leinwand', 'ein Bild über seine Ränder hinaus fortsetzen'],
      inpaint: ['Inpainting', 'nur neu malen, was du markierst'],
      restore: ['Restaurieren', 'alte Fotos mit Vorher-nachher-Regler'],
      video: ['Bild zu Video', 'ein Startbild und eine Beschreibung der Bewegung'],
      pose: ['Pose-Editor', 'Skelette mit Händen und Gesichtern'],
      training: ['Training', 'eine LoRA aus deinen eigenen Bildern'],
      models_recommended: ['Empfohlene Modelle', 'mit Speicherbedarf und Downloadgröße für deinen Mac'],
    },
    respTitle: 'Verantwortungsvoll entwickelt',
    resp: [
      'jeder Prompt und jedes Ergebnis wird geprüft, bevor es angezeigt wird',
      'der Schutz Minderjähriger ist immer aktiv',
      'bevor echte Fotos bearbeitet werden, fragen wir nach der Einwilligung',
      'jedes Bild erhält einen KI-Hinweis in seinen Metadaten',
      'das sichtbare Kennzeichen „AI GENERATED“ lässt sich mit einem Klick zuschalten',
    ],
    linksEyebrow: 'Mehr erfahren',
    linksTitle: 'Handbuch, Neuigkeiten und Code',
    links: [
      ['lightbulb', 'Benutzerhandbuch', 'jede Seite, jede Einstellung', `${BLOB}/docs/de/USER_GUIDE.md`],
      ['scroll-text', 'Wiki', 'Anleitungen und Hilfe', `${GH}/wiki`],
      ['messages-square', 'Discord', 'Community und Hilfe', DISCORD],
      ['file-clock', 'Änderungen', 'was ist neu?', `${BLOB}/CHANGELOG.md`],
      ['languages', 'VulKara übersetzen', 'deine Sprache hinzufügen (wenn nicht vorhanden)', `${BLOB}/docs/TRANSLATING.md`],
      ['scale', 'Lizenz', 'PolyForm Noncommercial 1.0.0', `${BLOB}/LICENSE`],
    ],
    supportTitle: 'In der Freizeit gebaut. Mit Kaffee am Laufen gehalten.',
    support: 'VulKara ist für alle kostenlos. Wenn es dir nützt, spendier ’nen Kaffee für die Weiterentwicklung, für Einbindung neuer Modelle, Fehlerbehebungen etc.',
    coffee: 'Spendier mir einen Kaffee',
    pose3d: {"title": "Pose-Editor in 3D", "alt": "Ein OpenPose-Skelett dreht sich im Raum: die Kamera geht um die Pose herum", "cap": "Animierte Skizze der Idee, nicht der fertige Editor.", "lead": "Dreh eine Pose frei im Raum und schau aus jedem Winkel auf deine Figur: von vorn, von der Seite, von oben oder aus der Froschperspektive. Das Ergebnis geht wie gewohnt als Pose in Text zu Bild.", "points": [["rotate-3d", "Frei drehen", "An der Figur ziehen dreht die Kamera rundherum, nach oben und unten. Feste Ansichten mit einem Klick: von vorn, von der Seite, von hinten, von oben."], ["bone", "Gelenke wie beim Menschen", "Ein gezogener Punkt dreht sein Gelenk, die Knochen behalten ihre Länge. Kopf, Schultern, Hüfte, Knie und Finger bleiben in natürlichen Grenzen – für Akrobatik abschaltbar."], ["bookmark", "Eigene Posen speichern", "Pose und Blickwinkel als Vorlage sichern, wieder laden, umbenennen oder als Datei weitergeben."], ["users", "Für deine Charaktere", "Eine gespeicherte Pose geht samt Blickwinkel direkt in eine Charakter-Szene."]]},
    next: ["Nächste geplante Features", "Deine eigenen Charaktere", "Erschaffe einen Charakter einmal – Gesicht, Haare, Outfit, Stil – und setze ihn als Referenz in jede Szene: Comic-Panels, Anime-Shots, eine ganze Geschichte. Derselbe Charakter auf jedem Bild. Erstellt und gespeichert auf deinem Mac, wie alles andere.", "Geplant, aber noch ohne Termin. Dafür braucht’s ’ne Menge Kaffee ;)"],
    nextPill: 'Geplante neue Features',
    nextCap: "Ein Charakter, sieben Bilder: die Vorlage und sechs Szenen, heute schon mit VulKara gemacht (FLUX.2 klein mit dem Vorlagebild auf der Seite Bild). Das Feature macht daraus ein paar Klicks.",
    nextAlts: {"mira": "Mira, die Vorlage", "cafe": "Zeichnen im Café", "rooftop": "Auf dem Dach bei Sonnenuntergang", "neon": "Neon-Straße im Regen", "mountain": "Wandern im Morgenlicht", "anime": "Als Anime-Figur", "comic": "Als Comic-Panel"},
    footAi: 'Die mit VulKara erstellten Bilder auf dieser Seite tragen das EU-Symbol AI GENERATED.',
    foot: '© 2026 Oliver Schmidt<br>VulKara ist für nicht kommerzielle Nutzung frei, unter der PolyForm Noncommercial License 1.0.0. Diese Seite setzt keine Cookies und lädt nichts von anderen Servern.',
    legal: ['Impressum', 'Datenschutz'],
    footPrivate: 'VulKara ist ein rein privates Projekt und mit keiner außenstehenden Firma verbunden oder assoziiert.',
    footTm: 'Apple, Mac und macOS sind Marken der Apple Inc. VulKara steht in keiner Verbindung zu Apple.',
  },

  es: {
    title: 'VulKara – generador local de imágenes con IA para tu Mac',
    desc: 'App gratuita con código fuente público para imágenes con IA en Macs con Apple silicon: texto a imagen, inpainting, lienzo IA, vídeo, restauración de fotos y entrenamiento de LoRAs. Todo se ejecuta en tu Mac.',
    ogAlt: 'VulKara, tu generador local de imágenes con IA, con alta privacidad',
    skip: 'Saltar al contenido',
    nav: ['Funciones', 'Por qué VulKara', 'Capturas', 'Empezar'],
    changesNav: 'Cambios',
    language: 'Idioma',
    theme: 'Apariencia',
    menu: 'Menú',
    themes: ["Como el sistema", "Claro", "Oscuro"],
    copy: 'Copiar el comando',
    copied: 'Copiado',
    brewLabel: 'O con Homebrew',
    download: 'Descargar',
    kicker: 'Gratis · código fuente público · para Macs con Apple silicon',
    tagline: 'Tu generador local de imágenes con IA, con alta privacidad',
    lead: 'Convierte ideas en imágenes, bocetos en escenas y fotos antiguas en recuerdos que vuelven a brillar, directamente en tu Mac. Sin nube, sin créditos, sin suscripción.',
    chips: ['Creadores', 'Estudiantes', 'Artistas de anime y cómic', 'Artistas digitales', 'Fans de la fotografía'],
    dlBig: 'Descargar para Mac',
    github: 'Código en GitHub',
    note: 'Gratis · macOS 14+ en Apple silicon · firmada y notarizada por Apple',
    brew: 'O con Homebrew: <code>brew install --cask revil-O/tap/vulkara</code>',
    inspired: 'Inspirada en DiffusionBee y ComfyUI',
    stream: {"eyebrow": "Streaming de modelos", "title": "Modelos grandes. Mac pequeño.", "lead": "VulKara transmite el modelo desde el SSD – interno o externo – bloque a bloque mientras se calcula la imagen. Solo la parte que está trabajando ocupa la memoria, así que modelos que necesitan 24 GB funcionan en un Mac con 16 GB, con toda su calidad de 16 bits.", "points": [["hard-drive", "SSD interno o externo", "Guarda los modelos y la caché de streaming en el SSD del Mac o en un disco externo por USB o Thunderbolt. Cuanto más rápido el disco, más rápida la imagen."], ["sparkles", "Calidad completa", "Nada de comprimir a 4 bits: el modelo conserva sus pesos de 16 bits. Lo que cabe se queda en memoria; el resto se lee por adelantado mientras trabaja la GPU."], ["memory-stick", "Automático", "El plan de memoria decide para cada modelo: se ejecuta en la RAM si cabe y se transmite desde el SSD (interno/externo) si no. ¡El streaming desde el SSD también se puede desactivar a mano!"]], "fine": "Probado en un Mac mini M4 con 16 GB: funcionan FLUX.1 [dev], Krea 2 y Qwen-Image 2.1. El streaming cambia velocidad por tamaño: los modelos grandes tardan minutos por imagen."},
    bannerAlt: 'Cinco imágenes creadas con VulKara: un faro en una costa rocosa, un zorro en un bosque nevado, una calle de neón de noche, un astronauta en una cúpula invernadero y una cabaña junto a un lago en otoño',
    bannerCap: 'Creadas con VulKara en un M2: Juggernaut XL v7, estilos Cinematic, Digital Art, Neon Punk, Fantasy Art y Analog Film.',
    galEyebrow: "Galería",
    galTitle: "Hecho en un Mac. No en la nube.",
    galLead: "Cada imagen se creó con VulKara en un MacBook Pro M2 con Z-Image Turbo, a partir de una sola frase, en unos cinco minutos por imagen.",
    galCaps: {"greenhouse": "Un invernadero de cristal flota sobre un bosque con niebla", "silver_gown": "Un vestido de plata líquida", "snow_leopard": "Leopardo de las nieves con mariposas morfo", "cat_astronaut": "Gato naranja entre medusas luminosas", "crystal_cat": "Gato negro sobre libros de cristal", "sky_koi": "Kois nadando por una ciudad de neón", "gold_freckles": "Pecas, pan de oro y flores blancas", "fox_mushroom": "Un zorro dormido bajo una seta luminosa", "hummingbird": "Un colibrí de vidriera", "kitten_cloud": "Un gatito blanco dormido en una taza sobre una nube"},
    models: {"nav": "Modelos", "eyebrow": "Modelos compatibles", "title": "Todas las grandes familias de modelos, una sola app", "lead": "Instálalos desde una lista de modelos probados o impórtalos de Hugging Face, Civitai o un archivo. VulKara elige el runtime adecuado para cada uno y planifica la memoria de tu Mac.", "fine": "Los modelos nunca forman parte de la app: se descargan cuando los eliges. Cada uno tiene su propia licencia, y la página Licencias de la app indica si el modelo y sus imágenes pueden usarse comercialmente.", "new": "Nuevo", "made": "Imagen hecha con", "caps": {"pic": "Imágenes", "edit": "Edición con referencia", "inpaint": "Inpainting", "cn": "ControlNet", "lora": "LoRAs", "train": "Entrenamiento", "video": "Vídeo", "pup": "Ampliador de prompts"}, "notes": {"sd15": "El clásico con miles de fine-tunes; funciona con 8 GB.", "sdxl": "La mayor selección de fine-tunes y LoRAs: foto, anime, ilustración.", "sd35": "La tercera generación de Stability AI.", "flux1": "Detallado y fotorrealista; [schnell] solo necesita 4 pasos.", "chroma": "Un modelo abierto basado en FLUX.1, bajo Apache 2.0.", "flux2": "Toma tu imagen como referencia; [klein] también aprende tus propios LoRAs.", "flux3": "Lo más nuevo de Black Forest Labs. Las versiones de 6 y 8 bits funcionan en un Mac con 16 GB.", "qwen": "Destaca con el texto dentro de la imagen; 2.1 en GGUF.", "zimage": "Rápido y fotorrealista: la galería de arriba se hizo con Z-Image Turbo.", "krea2": "Fotos estéticas; funciona con 16 GB gracias al streaming desde el SSD.", "ideogram4": "El modelo de Ideogram en el runtime MLX.", "anima": "Anime e ilustración.", "wan": "Imagen a vídeo: 1–5 segundos en 480p o 720p."}},
    featEyebrow: 'Funciones',
    featTitle: 'Una app, todo un estudio',
    bench: ['Benchmark: mide tu Mac', 'Elige un modelo y mídelo en tu propio Mac: segundos por paso, la imagen entera, la memoria máxima de VulKara y del sistema, el swap, lo que se leyó del SSD y cada fase, de la carga a la generación. Copia las mediciones como tabla y compara Macs, tamaños y bits. Las mismas mediciones hicieron VulKara más rápido: SD 1.5 el doble de rápido con la mitad de memoria, las imágenes SDXL grandes cuatro veces más rápidas.', 'Ver las mediciones'],
    news: [['scan-text', "Prompt desde imagen", "Elige una imagen en Imagen a imagen y pulsa <b>Prompt desde imagen</b>: Qwen3-VL 2B describe motivo, entorno, luz, colores, estilo y cámara en un párrafo, en el Mac, en unos 15 segundos en un Mac mini M4 con 16 GB. Cámbialo y genera."], ['activity', "Barra de menús y Monitor", "Cierra la ventana y VulKara sigue en marcha con su icono en la barra de menús: la tarea en curso, su progreso, lo que espera. <b>Monitor</b> muestra la tarea frente a su plan de memoria y, en el Mac medido, frente a las mediciones de su modelo."]],
    featLead: 'Imágenes, edición, vídeo y tus propias LoRAs, para creadores, estudiantes, fans del cómic y del anime y artistas digitales.',
    feats: [
      ['type', 'Texto a imagen', 'Descríbelo, elige un estilo y pulsa ⌘↩. Veinte estilos, de foto a ilustración y 3D, y hasta tres LoRAs, cada una con su propio peso.'],
      ['eraser', 'Imagen a imagen e inpainting', 'Mantén el motivo y cambia la escena. O pinta solo la parte que debe cambiar: el resto queda intacto.'],
      ['frame', 'Lienzo IA', 'Una superficie sin fin: mueve el marco más allá del borde y Generar continúa la imagen. Pinta una máscara para rehacer una parte.'],
      ['clapperboard', 'Imagen a vídeo', 'Da vida a una imagen con Wan 2.2: describe el movimiento y obtén de 1 a 5 segundos en 480p o 720p.'],
      ['maximize-2', 'Ampliar y herramientas de fotos', '2× o 4× con Real-ESRGAN, además de enfocar, quitar ruido, eliminar artefactos JPEG, quitar el fondo y seleccionar objetos con un clic.'],
      ['wand-sparkles', 'Restaurar fotos antiguas', 'Dominantes de color, polvo y arañazos corregidos, caras borrosas restauradas y fotos en blanco y negro coloreadas.'],
      ['person-standing', 'Editor de poses', 'Esqueletos OpenPose con manos y caras, plantillas o una pose detectada en una foto; luego, a Texto a imagen.'],
      ['sparkles', 'Ilusiones', 'Esconde una espiral, un patrón, una palabra o un logo dentro de una imagen.'],
      ['graduation-cap', 'Entrenamiento de LoRAs', 'Enseña a un modelo tu estilo de dibujo o tu personaje con 10–30 imágenes propias, en SDXL, FLUX.2 [klein] o Krea 2, con la curva de pérdida en directo.'],
      ['boxes', 'Muchos modelos', 'SD 1.5, SDXL (también Pony, Illustrious, NoobAI), SD 3.5, FLUX.1, FLUX.2, FLUX 3, Chroma, Qwen-Image, Z-Image, Krea 2, Ideogram 4, Anima y Wan 2.2 para vídeo. Descarga directa desde una lista de modelos probados, importación desde Hugging Face o Civitai (puede hacer falta un token de API) por enlace (URL o creador/nombre del modelo) o desde un archivo de modelo ya descargado.'],
    ],
    whyEyebrow: 'Por qué VulKara',
    whyTitle: 'Tus ideas siguen siendo tuyas',
    why: [
      ['monitor', 'Todo en tu Mac', ['Imágenes, vídeos, restauraciones y entrenamiento se ejecutan en la GPU de Apple. Tus prompts e imágenes nunca salen del Mac: internet solo se usa para descargar runtimes, modelos y descripciones de LoRAs, y para buscar actualizaciones. Desconecta tu Mac de la red y pruébalo: también funciona completamente sin conexión (¡si antes se descargaron todos los paquetes de los que depende!)']],
      ['tablet-smartphone', 'Desde el móvil, en tu propia red', ['Abre VulKara en un navegador del móvil, la tableta u otro ordenador, en tu red doméstica o a través de una conexión VPN. Mira el estado actual de tus imágenes, introduce e inicia nuevas ideas cuando estás fuera, y mira, descarga o comparte las imágenes terminadas en el historial. Solo calcula tu Mac. El acceso está protegido con un token de acceso y cifrado por HTTPS, para garantizar también aquí tu privacidad.'], 'Actívalo una vez, escanea el código QR y listo. Nada sale a internet.'],
      ['heart', 'Gratis, sin trampa', ['Sin cuenta, sin suscripción, sin créditos. El código fuente es público: léelo, cámbialo, compártelo para cualquier uso no comercial.'], 'Algunos modelos piden un token gratuito de Hugging Face o Civitai antes de descargarse.'],
      ['hard-drive', 'Funciona también en Macs pequeños', ['Un modelo demasiado grande para la memoria se transmite desde el SSD bloque a bloque, con toda su calidad. En un Mac mini M4 con 16 GB funcionan FLUX.1 [dev], Krea 2 y Qwen-Image 2.1.'], 'El streaming cambia velocidad por tamaño: los modelos grandes tardan minutos por imagen. Stable Diffusion 1.5 funciona con 8 GB.'],
      ['languages', 'Habla tu idioma', ['English, Deutsch, Español, Português (Brasil) y Português (Portugal): la app y la guía de usuario. ¿Falta el tuyo? Un idioma nuevo es una carpeta de archivos de texto.']],
    ],
    stepsEyebrow: 'Empezar',
    stepsTitle: 'Tu primera imagen en 3 pasos',
    steps: [
      ['Instala', 'Descarga el DMG, ábrelo y arrastra VulKara a <b>Aplicaciones</b>.'],
      ['Runtime y modelo', '<b>Ajustes → Runtimes</b>: instala <b>Diffusers (Apple GPU)</b>. Luego <b>Modelos → Recomendados</b>: <i>SDXL 1.0</i> con 16 GB, <i>Stable Diffusion 1.5</i> con 8 GB.'],
      ['Crea', 'Abre <b>Texto</b>, describe tu imagen y pulsa <b>⌘↩</b>. La página de Inicio marca cada paso.'],
    ],
    shotsEyebrow: 'Capturas',
    shotsTitle: 'Echa un vistazo dentro',
    shotsOpen: 'abre la captura a tamaño completo',
    shots: {
      text: ['Texto a imagen', 'prompt, modelo, estilo, tamaño y LoRAs en una página'],
      canvas: ['Lienzo IA', 'continúa una imagen más allá de sus bordes'],
      inpaint: ['Inpainting', 'vuelve a pintar solo lo que marques'],
      restore: ['Restaurar', 'fotos antiguas con un control de antes y después'],
      video: ['Imagen a vídeo', 'una imagen inicial y una descripción del movimiento'],
      pose: ['Editor de poses', 'esqueletos con manos y caras'],
      training: ['Entrenamiento', 'una LoRA a partir de tus propias imágenes'],
      models_recommended: ['Modelos recomendados', 'con la memoria y el tamaño de descarga para tu Mac'],
    },
    respTitle: 'Desarrollado con responsabilidad',
    resp: [
      'cada prompt y cada resultado se comprueban antes de mostrarse',
      'la protección de menores está siempre activa',
      'antes de editar fotos reales, pedimos el consentimiento',
      'cada imagen recibe una nota de IA en sus metadatos',
      'la etiqueta visible «AI GENERATED» se activa con un clic',
    ],
    linksEyebrow: 'Más información',
    linksTitle: 'Guía, novedades y código',
    links: [
      ['lightbulb', 'Guía de usuario', 'cada página y cada ajuste', `${BLOB}/docs/es/USER_GUIDE.md`],
      ['scroll-text', 'Wiki', 'guías y ayuda', `${GH}/wiki`],
      ['messages-square', 'Discord', 'comunidad y ayuda', DISCORD],
      ['file-clock', 'Cambios', '¿qué hay de nuevo?', `${BLOB}/CHANGELOG.md`],
      ['languages', 'Traduce VulKara', 'añade tu idioma (si aún no está)', `${BLOB}/docs/TRANSLATING.md`],
      ['scale', 'Licencia', 'PolyForm Noncommercial 1.0.0', `${BLOB}/LICENSE`],
    ],
    supportTitle: 'Hecha en el tiempo libre. Impulsada por café.',
    support: 'VulKara es gratis para todos. Si te resulta útil, invítame a un café para seguir desarrollándola: integrar nuevos modelos, correcciones, etc.',
    coffee: 'Invítame a un café',
    pose3d: {"title": "Editor de poses en 3D", "alt": "Un esqueleto OpenPose girando en el espacio: la cámara rodea la pose", "cap": "Boceto animado de la idea, no el editor terminado.", "lead": "Gira una pose libremente en el espacio y mira tu figura desde cualquier ángulo: de frente, de lado, desde arriba o en contrapicado. El resultado va como siempre a Texto a imagen como pose.", "points": [["rotate-3d", "Gira libremente", "Arrastra la figura para mover la cámara a su alrededor, arriba y abajo. Vistas fijas con un clic: de frente, de lado, de espaldas, desde arriba."], ["bone", "Articulaciones como un cuerpo", "Al arrastrar un punto gira su articulación y los huesos conservan su longitud. Cabeza, hombros, caderas, rodillas y dedos se quedan en límites naturales; se pueden desactivar para acrobacias."], ["bookmark", "Guarda tus poses", "Guarda una pose con su punto de vista como plantilla, vuelve a cargarla, cámbiale el nombre o compártela como archivo."], ["users", "Para tus personajes", "Una pose guardada pasa directamente a una escena de personaje, junto con su punto de vista."]]},
    next: ["Próximas funciones planeadas", "Tus propios personajes", "Crea un personaje una vez – cara, pelo, ropa, estilo – y ponlo como referencia en cualquier escena: viñetas de cómic, planos de anime, una historia entera. El mismo personaje en cada imagen. Creado y guardado en tu Mac, como todo lo demás.", "Planeado, pero todavía sin fecha. Para eso hace falta mucho café ;)"],
    nextPill: 'Nuevas funciones planeadas',
    nextCap: "Un personaje, siete imágenes: la referencia y seis escenas, hechas hoy ya con VulKara (FLUX.2 klein con la imagen de referencia en la página Imagen). La función lo convertirá en unos pocos clics.",
    nextAlts: {"mira": "Mira, la referencia", "cafe": "Dibujando en un café", "rooftop": "En una azotea al atardecer", "neon": "Calle de neón bajo la lluvia", "mountain": "De excursión al amanecer", "anime": "Como personaje de anime", "comic": "Como viñeta de cómic"},
    footAi: 'Las imágenes creadas con VulKara en esta página llevan el icono de la UE AI GENERATED.',
    foot: '© 2026 Oliver Schmidt<br>VulKara es libre para uso no comercial bajo la PolyForm Noncommercial License 1.0.0. Esta página no usa cookies y no carga nada de otros servidores.',
    legal: ['Aviso legal (Impressum)', 'Privacidad'],
    footPrivate: 'VulKara es un proyecto puramente privado y no está asociado ni vinculado a ninguna empresa externa.',
    footTm: 'Apple, Mac y macOS son marcas comerciales de Apple Inc. VulKara no está afiliada a Apple.',
  },

  'pt-BR': {
    title: 'VulKara – gerador local de imagens com IA para o seu Mac',
    desc: 'App gratuito com código-fonte público para imagens com IA em Macs com Apple silicon: texto para imagem, inpainting, tela de IA, vídeo, restauração de fotos e treinamento de LoRAs. Tudo roda no seu Mac.',
    ogAlt: 'VulKara, seu gerador local de imagens com IA, com alta privacidade',
    skip: 'Pular para o conteúdo',
    nav: ['Recursos', 'Por que o VulKara', 'Capturas', 'Começar'],
    changesNav: 'Novidades',
    language: 'Idioma',
    theme: 'Aparência',
    menu: 'Menu',
    themes: ["Como o sistema", "Claro", "Escuro"],
    copy: 'Copiar o comando',
    copied: 'Copiado',
    brewLabel: 'Ou com Homebrew',
    download: 'Baixar',
    kicker: 'Grátis · código-fonte público · para Macs com Apple silicon',
    tagline: 'Seu gerador local de imagens com IA, com alta privacidade',
    lead: 'Transforme ideias em imagens, rascunhos em cenas e fotos antigas em lembranças que brilham de novo – direto no seu Mac. Sem nuvem, sem créditos, sem assinatura.',
    chips: ['Criadores', 'Estudantes', 'Artistas de anime e HQ', 'Artistas digitais', 'Fãs de fotografia'],
    dlBig: 'Baixar para Mac',
    github: 'Código no GitHub',
    note: 'Grátis · macOS 14+ em Apple silicon · assinado e notarizado pela Apple',
    brew: 'Ou com Homebrew: <code>brew install --cask revil-O/tap/vulkara</code>',
    inspired: 'Inspirado no DiffusionBee e no ComfyUI',
    stream: {"eyebrow": "Streaming de modelos", "title": "Modelos grandes. Mac pequeno.", "lead": "O VulKara transmite o modelo do SSD – interno ou externo – bloco a bloco enquanto a imagem é calculada. Só a parte que está trabalhando ocupa a memória, então modelos que precisam de 24 GB rodam num Mac com 16 GB, com qualidade total de 16 bits.", "points": [["hard-drive", "SSD interno ou externo", "Guarde os modelos e o cache de streaming no SSD do Mac ou num disco externo via USB ou Thunderbolt. Quanto mais rápido o disco, mais rápida a imagem."], ["sparkles", "Qualidade total", "Nada de espremer em 4 bits: o modelo mantém os pesos de 16 bits. O que cabe fica na memória, o resto é lido antes enquanto a GPU trabalha."], ["memory-stick", "Automático", "O plano de memória decide para cada modelo: roda na RAM se couber e é transmitido do SSD (interno/externo) se não couber. O streaming do SSD também pode ser desligado manualmente!"]], "fine": "Testado num Mac mini M4 com 16 GB: rodam o FLUX.1 [dev], o Krea 2 e o Qwen-Image 2.1. O streaming troca velocidade por tamanho: modelos grandes levam minutos por imagem."},
    bannerAlt: 'Cinco imagens criadas com o VulKara: um farol numa costa rochosa, uma raposa numa floresta com neve, uma rua neon à noite, um astronauta numa estufa em cúpula e uma cabana à beira de um lago no outono',
    bannerCap: 'Criadas com o VulKara num M2: Juggernaut XL v7, estilos Cinematic, Digital Art, Neon Punk, Fantasy Art e Analog Film.',
    galEyebrow: "Galeria",
    galTitle: "Feito num Mac. Não na nuvem.",
    galLead: "Cada imagem foi criada com o VulKara num MacBook Pro M2 com Z-Image Turbo, a partir de uma única frase, em cerca de cinco minutos por imagem.",
    galCaps: {"greenhouse": "Uma estufa de vidro flutua sobre uma floresta enevoada", "silver_gown": "Um vestido de prata líquida", "snow_leopard": "Leopardo-das-neves com borboletas morfo", "cat_astronaut": "Gato laranja entre águas-vivas luminosas", "crystal_cat": "Gato preto sobre livros de cristal", "sky_koi": "Carpas nadando por uma cidade neon", "gold_freckles": "Sardas, folha de ouro e flores brancas", "fox_mushroom": "Uma raposa dorme sob um cogumelo luminoso", "hummingbird": "Um beija-flor de vitral", "kitten_cloud": "Um gatinho branco dormindo numa xícara sobre uma nuvem"},
    models: {"nav": "Modelos", "eyebrow": "Modelos compatíveis", "title": "Todas as grandes famílias de modelos, um só app", "lead": "Instale a partir de uma lista de modelos testados ou importe do Hugging Face, do Civitai ou de um arquivo. O VulKara escolhe o runtime certo para cada um e planeja a memória do seu Mac.", "fine": "Os modelos nunca fazem parte do app: são baixados quando você os escolhe. Cada um tem a sua licença, e a página Licenças do app diz se o modelo e as suas imagens podem ser usados comercialmente.", "new": "Novo", "made": "Imagem feita com", "caps": {"pic": "Imagens", "edit": "Edição com referência", "inpaint": "Inpainting", "cn": "ControlNet", "lora": "LoRAs", "train": "Treinamento", "video": "Vídeo", "pup": "Ampliador de prompt"}, "notes": {"sd15": "O clássico com milhares de fine-tunes; roda com 8 GB.", "sdxl": "A maior escolha de fine-tunes e LoRAs: foto, anime, ilustração.", "sd35": "A terceira geração da Stability AI.", "flux1": "Detalhado e fotorrealista; o [schnell] precisa de só 4 passos.", "chroma": "Um modelo aberto baseado no FLUX.1, sob Apache 2.0.", "flux2": "Usa a sua imagem como referência; o [klein] também aprende os seus próprios LoRAs.", "flux3": "O mais novo da Black Forest Labs. As versões de 6 e 8 bits rodam num Mac com 16 GB.", "qwen": "Forte em texto dentro da imagem; 2.1 em GGUF.", "zimage": "Rápido e fotorrealista: a galeria acima foi feita com o Z-Image Turbo.", "krea2": "Fotos estéticas; roda com 16 GB graças ao streaming do SSD.", "ideogram4": "O modelo da Ideogram no runtime MLX.", "anima": "Anime e ilustração.", "wan": "Imagem para vídeo: 1–5 segundos em 480p ou 720p."}},
    featEyebrow: 'Recursos',
    featTitle: 'Um app, um estúdio inteiro',
    bench: ['Benchmark: meça o seu Mac', 'Escolha um modelo e meça-o no seu próprio Mac: segundos por passo, a imagem inteira, a memória máxima do VulKara e do sistema, o swap, o que foi lido do SSD e cada fase, do carregamento à geração. Copie as medições como tabela e compare Macs, tamanhos e bits. As mesmas medições deixaram o VulKara mais rápido: SD 1.5 duas vezes mais rápido com metade da memória, imagens SDXL grandes quatro vezes mais rápidas.', 'Ver as medições'],
    news: [['scan-text', "Prompt a partir da imagem", "Escolha uma imagem em Imagem para imagem e clique em <b>Prompt a partir da imagem</b>: o Qwen3-VL 2B descreve motivo, ambiente, luz, cores, estilo e câmera em um parágrafo, no Mac, em cerca de 15 segundos num Mac mini M4 com 16 GB. Mude-o e gere."], ['activity', "Barra de menus e Monitor", "Feche a janela e o VulKara continua rodando com seu ícone na barra de menus: a tarefa em andamento, o progresso, o que aguarda. O <b>Monitor</b> mostra a tarefa comparada com seu plano de memória e, no Mac medido, com as medições do seu modelo."]],
    featLead: 'Imagens, edição, vídeo e suas próprias LoRAs – para criadores, estudantes, fãs de HQ e anime e artistas digitais.',
    feats: [
      ['type', 'Texto para imagem', 'Descreva, escolha um estilo e pressione ⌘↩. Vinte estilos, de foto a ilustração e 3D, e até três LoRAs, cada uma com seu próprio peso.'],
      ['eraser', 'Imagem para imagem e inpainting', 'Mantenha o motivo e mude a cena. Ou pinte só a parte que deve mudar – o resto fica intacto.'],
      ['frame', 'Tela de IA', 'Uma superfície sem fim: leve a moldura além da borda e Gerar continua a imagem. Pinte uma máscara para refazer uma parte.'],
      ['clapperboard', 'Imagem para vídeo', 'Dê vida a uma imagem com o Wan 2.2: descreva o movimento e receba de 1 a 5 segundos em 480p ou 720p.'],
      ['maximize-2', 'Ampliar e ferramentas de foto', '2× ou 4× com Real-ESRGAN, além de nitidez, redução de ruído, remoção de artefatos JPEG, remoção do fundo e seleção de objetos com um clique.'],
      ['wand-sparkles', 'Restaurar fotos antigas', 'Dominantes de cor, poeira e arranhões corrigidos, rostos borrados restaurados e fotos em preto e branco coloridas.'],
      ['person-standing', 'Editor de pose', 'Esqueletos OpenPose com mãos e rostos, modelos prontos ou uma pose detectada numa foto – depois é só usar em Texto para imagem.'],
      ['sparkles', 'Ilusões', 'Esconda uma espiral, um padrão, uma palavra ou um logo dentro de uma imagem.'],
      ['graduation-cap', 'Treinamento de LoRAs', 'Ensine a um modelo seu estilo de desenho ou seu personagem com 10–30 imagens suas, em SDXL, FLUX.2 [klein] ou Krea 2, com a curva de perda ao vivo.'],
      ['boxes', 'Muitos modelos', 'SD 1.5, SDXL (também Pony, Illustrious, NoobAI), SD 3.5, FLUX.1, FLUX.2, FLUX 3, Chroma, Qwen-Image, Z-Image, Krea 2, Ideogram 4, Anima e Wan 2.2 para vídeo. Download direto de uma lista de modelos testados, importação do Hugging Face ou do Civitai (pode ser preciso um token de API) por link (URL ou criador/nome do modelo) ou de um arquivo de modelo já baixado.'],
    ],
    whyEyebrow: 'Por que o VulKara',
    whyTitle: 'Suas ideias continuam suas',
    why: [
      ['monitor', 'Tudo no seu Mac', ['Imagens, vídeos, restaurações e treinamento rodam na GPU da Apple. Seus prompts e imagens nunca saem do Mac – a internet só é usada para baixar runtimes, modelos e descrições de LoRAs, e para procurar atualizações. Desconecte o seu Mac da rede e experimente – funciona também totalmente offline (se todos os pacotes de que depende tiverem sido baixados antes!)']],
      ['tablet-smartphone', 'Pelo celular, na sua própria rede', ['Abra o VulKara em um navegador no celular, tablet ou outro computador, na sua rede doméstica ou por uma conexão VPN. Veja o status atual das suas imagens, digite e inicie novas ideias quando estiver fora, e veja, baixe ou compartilhe imagens prontas no histórico. Só o seu Mac calcula. O acesso é protegido por um token de acesso e criptografado por HTTPS, para garantir a sua privacidade também aqui.'], 'Ative uma vez, escaneie o código QR, pronto. Nada vai para a internet.'],
      ['heart', 'Grátis, sem pegadinha', ['Sem conta, sem assinatura, sem créditos. O código-fonte é público: leia, mude, compartilhe para qualquer uso não comercial.'], 'Alguns modelos pedem um token gratuito do Hugging Face ou do Civitai antes do download.'],
      ['hard-drive', 'Roda também em Macs pequenos', ['Um modelo grande demais para a memória é transmitido do SSD bloco a bloco, com qualidade total. Num Mac mini M4 com 16 GB rodam o FLUX.1 [dev], o Krea 2 e o Qwen-Image 2.1.'], 'O streaming troca velocidade por tamanho: modelos grandes levam minutos por imagem. O Stable Diffusion 1.5 roda com 8 GB.'],
      ['languages', 'Fala o seu idioma', ['English, Deutsch, Español, Português (Brasil) e Português (Portugal) – o app e o guia do usuário. Falta o seu? Um idioma novo é uma pasta de arquivos de texto.']],
    ],
    stepsEyebrow: 'Começar',
    stepsTitle: 'Sua primeira imagem em 3 passos',
    steps: [
      ['Instale', 'Baixe o DMG, abra e arraste o VulKara para <b>Aplicativos</b>.'],
      ['Runtime e modelo', '<b>Ajustes → Runtimes</b>: instale o <b>Diffusers (Apple GPU)</b>. Depois, <b>Modelos → Recomendados</b>: <i>SDXL 1.0</i> com 16 GB, <i>Stable Diffusion 1.5</i> com 8 GB.'],
      ['Crie', 'Abra <b>Texto</b>, descreva sua imagem e pressione <b>⌘↩</b>. A página Início marca cada passo.'],
    ],
    shotsEyebrow: 'Capturas',
    shotsTitle: 'Dê uma olhada por dentro',
    shotsOpen: 'abre a captura em tamanho real',
    shots: {
      text: ['Texto para imagem', 'prompt, modelo, estilo, tamanho e LoRAs numa página'],
      canvas: ['Tela de IA', 'continue uma imagem além das bordas'],
      inpaint: ['Inpainting', 'repinte só o que você marcar'],
      restore: ['Restaurar', 'fotos antigas com um controle de antes e depois'],
      video: ['Imagem para vídeo', 'uma imagem inicial e uma descrição do movimento'],
      pose: ['Editor de pose', 'esqueletos com mãos e rostos'],
      training: ['Treino', 'uma LoRA a partir das suas próprias imagens'],
      models_recommended: ['Modelos recomendados', 'com a memória e o tamanho do download para o seu Mac'],
    },
    respTitle: 'Desenvolvido com responsabilidade',
    resp: [
      'cada prompt e cada resultado são verificados antes de serem exibidos',
      'a proteção de menores está sempre ativa',
      'antes de editar fotos reais, pedimos o consentimento',
      'cada imagem recebe uma nota de IA nos metadados',
      'o selo visível “AI GENERATED” pode ser ativado com um clique',
    ],
    linksEyebrow: 'Saiba mais',
    linksTitle: 'Guia, novidades e código',
    links: [
      ['lightbulb', 'Guia do usuário', 'cada página e cada ajuste', `${BLOB}/docs/pt-BR/USER_GUIDE.md`],
      ['scroll-text', 'Wiki', 'guias e ajuda', `${GH}/wiki`],
      ['messages-square', 'Discord', 'comunidade e ajuda', DISCORD],
      ['file-clock', 'Novidades', 'o que há de novo?', `${BLOB}/CHANGELOG.md`],
      ['languages', 'Traduza o VulKara', 'adicione o seu idioma (se ainda não existir)', `${BLOB}/docs/TRANSLATING.md`],
      ['scale', 'Licença', 'PolyForm Noncommercial 1.0.0', `${BLOB}/LICENSE`],
    ],
    supportTitle: 'Feito no tempo livre. Movido a café.',
    support: 'O VulKara é grátis para todos. Se ele for útil para você, me pague um café para o desenvolvimento continuar: integração de novos modelos, correções etc.',
    coffee: 'Me pague um café',
    pose3d: {"title": "Editor de pose em 3D", "alt": "Um esqueleto OpenPose girando no espaço: a câmera dá a volta na pose", "cap": "Esboço animado da ideia, não o editor pronto.", "lead": "Gire uma pose livremente no espaço e veja a sua figura de qualquer ângulo: de frente, de lado, de cima ou de baixo para cima. O resultado vai, como sempre, para Texto para imagem como pose.", "points": [["rotate-3d", "Gire livremente", "Arraste a figura para mover a câmera ao redor dela, para cima e para baixo. Vistas fixas com um clique: de frente, de lado, de costas, de cima."], ["bone", "Articulações como um corpo", "Arrastar um ponto gira a articulação, e os ossos mantêm o comprimento. Cabeça, ombros, quadris, joelhos e dedos ficam dentro de limites naturais – dá para desligar para acrobacias."], ["bookmark", "Salve suas poses", "Guarde uma pose com o ponto de vista como modelo, carregue de novo, renomeie ou compartilhe como arquivo."], ["users", "Para seus personagens", "Uma pose salva vai direto para uma cena de personagem, junto com o ponto de vista."]]},
    next: ["Próximos recursos planejados", "Seus próprios personagens", "Crie um personagem uma vez – rosto, cabelo, roupa, estilo – e coloque-o como referência em qualquer cena: quadrinhos, cenas de anime, uma história inteira. O mesmo personagem em todas as imagens. Criado e guardado no seu Mac, como todo o resto.", "Planejado, mas ainda sem data. Para isso, é preciso muito café ;)"],
    nextPill: 'Novos recursos planejados',
    nextCap: "Um personagem, sete imagens: a referência e seis cenas, feitas hoje mesmo com o VulKara (FLUX.2 klein com a imagem de referência na página Imagem). O recurso vai transformar isso em poucos cliques.",
    nextAlts: {"mira": "Mira, a referência", "cafe": "Desenhando num café", "rooftop": "Num terraço ao pôr do sol", "neon": "Rua de neon na chuva", "mountain": "Trilha ao amanhecer", "anime": "Como personagem de anime", "comic": "Como quadrinho"},
    footAi: 'As imagens criadas com o VulKara nesta página levam o ícone da UE AI GENERATED.',
    foot: '© 2026 Oliver Schmidt<br>O VulKara é livre para uso não comercial sob a PolyForm Noncommercial License 1.0.0. Esta página não usa cookies e não carrega nada de outros servidores.',
    legal: ['Aviso legal (Impressum)', 'Privacidade'],
    footPrivate: 'O VulKara é um projeto puramente pessoal e não está associado nem vinculado a nenhuma empresa externa.',
    footTm: 'Apple, Mac e macOS são marcas registradas da Apple Inc. O VulKara não tem vínculo com a Apple.',
  },

  'pt-PT': {
    title: 'VulKara – gerador local de imagens com IA para Mac',
    desc: 'App gratuita com código-fonte público para imagens com IA em Mac com Apple silicon: texto para imagem, inpainting, tela de IA, vídeo, restauro de fotografias e treino de LoRAs. Tudo é executado no Mac.',
    ogAlt: 'VulKara, o seu gerador local de imagens com IA, com elevada privacidade',
    skip: 'Avançar para o conteúdo',
    nav: ['Funcionalidades', 'Porquê o VulKara', 'Capturas', 'Começar'],
    changesNav: 'Novidades',
    language: 'Idioma',
    theme: 'Aspeto',
    menu: 'Menu',
    themes: ["Como o sistema", "Claro", "Escuro"],
    copy: 'Copiar o comando',
    copied: 'Copiado',
    brewLabel: 'Ou com o Homebrew',
    download: 'Transferir',
    kicker: 'Gratuito · código-fonte público · para Mac com Apple silicon',
    tagline: 'O seu gerador local de imagens com IA, com elevada privacidade',
    lead: 'Ideias que se tornam imagens, esboços que se tornam cenas e fotografias antigas que voltam a brilhar – diretamente no Mac. Sem nuvem, sem créditos, sem subscrição.',
    chips: ['Criadores', 'Estudantes', 'Artistas de anime e BD', 'Artistas digitais', 'Fãs de fotografia'],
    dlBig: 'Transferir para Mac',
    github: 'Código no GitHub',
    note: 'Gratuito · macOS 14+ em Apple silicon · assinado e notarizado pela Apple',
    brew: 'Ou com o Homebrew: <code>brew install --cask revil-O/tap/vulkara</code>',
    inspired: 'Inspirada no DiffusionBee e no ComfyUI',
    stream: {"eyebrow": "Streaming de modelos", "title": "Modelos grandes. Mac pequeno.", "lead": "O VulKara transmite o modelo a partir do SSD – interno ou externo – bloco a bloco enquanto a imagem é calculada. Só a parte que está a trabalhar ocupa a memória, pelo que modelos que precisam de 24 GB funcionam num Mac com 16 GB, com a qualidade total de 16 bits.", "points": [["hard-drive", "SSD interno ou externo", "Guarde os modelos e a cache de streaming no SSD do Mac ou num disco externo por USB ou Thunderbolt. Quanto mais rápido o disco, mais rápida a imagem."], ["sparkles", "Qualidade total", "Nada de comprimir para 4 bits: o modelo mantém os pesos de 16 bits. O que cabe fica na memória; o resto é lido antecipadamente enquanto a GPU trabalha."], ["memory-stick", "Automático", "O plano de memória decide para cada modelo: corre na RAM se couber e é transmitido a partir do SSD (interno/externo) se não couber. O streaming do SSD também pode ser desligado manualmente!"]], "fine": "Testado num Mac mini M4 com 16 GB: o FLUX.1 [dev], o Krea 2 e o Qwen-Image 2.1 funcionam. O streaming troca velocidade por tamanho: os modelos grandes demoram minutos por imagem."},
    bannerAlt: 'Cinco imagens criadas com o VulKara: um farol numa costa rochosa, uma raposa numa floresta com neve, uma rua em néon à noite, um astronauta numa estufa em cúpula e uma cabana junto a um lago no outono',
    bannerCap: 'Criadas com o VulKara num M2: Juggernaut XL v7, estilos Cinematic, Digital Art, Neon Punk, Fantasy Art e Analog Film.',
    galEyebrow: "Galeria",
    galTitle: "Feito num Mac. Não na nuvem.",
    galLead: "Cada imagem foi criada com o VulKara num MacBook Pro M2 com o Z-Image Turbo, a partir de uma única frase, em cerca de cinco minutos por imagem.",
    galCaps: {"greenhouse": "Uma estufa de vidro flutua sobre uma floresta com nevoeiro", "silver_gown": "Um vestido de prata líquida", "snow_leopard": "Leopardo-das-neves com borboletas morfo", "cat_astronaut": "Gato laranja entre medusas luminosas", "crystal_cat": "Gato preto sobre livros de cristal", "sky_koi": "Carpas a nadar por uma cidade de néon", "gold_freckles": "Sardas, folha de ouro e flores brancas", "fox_mushroom": "Uma raposa a dormir sob um cogumelo luminoso", "hummingbird": "Um colibri de vitral", "kitten_cloud": "Um gatinho branco a dormir numa chávena sobre uma nuvem"},
    models: {"nav": "Modelos", "eyebrow": "Modelos suportados", "title": "Todas as grandes famílias de modelos, uma só app", "lead": "Instala-os a partir de uma lista de modelos testados ou importa-os do Hugging Face, do Civitai ou de um ficheiro. O VulKara escolhe o runtime certo para cada um e planeia a memória do teu Mac.", "fine": "Os modelos nunca fazem parte da app: são descarregados quando os escolhes. Cada um tem a sua licença, e a página Licenças da app indica se o modelo e as suas imagens podem ser usados comercialmente.", "new": "Novo", "made": "Imagem feita com", "caps": {"pic": "Imagens", "edit": "Edição com referência", "inpaint": "Inpainting", "cn": "ControlNet", "lora": "LoRAs", "train": "Treino", "video": "Vídeo", "pup": "Ampliador de prompt"}, "notes": {"sd15": "O clássico com milhares de fine-tunes; funciona com 8 GB.", "sdxl": "A maior escolha de fine-tunes e LoRAs: fotografia, anime, ilustração.", "sd35": "A terceira geração da Stability AI.", "flux1": "Detalhado e fotorrealista; o [schnell] precisa de apenas 4 passos.", "chroma": "Um modelo aberto baseado no FLUX.1, sob Apache 2.0.", "flux2": "Usa a tua imagem como referência; o [klein] também aprende os teus próprios LoRAs.", "flux3": "O mais recente da Black Forest Labs. As versões de 6 e 8 bits funcionam num Mac com 16 GB.", "qwen": "Forte em texto dentro da imagem; 2.1 em GGUF.", "zimage": "Rápido e fotorrealista: a galeria acima foi feita com o Z-Image Turbo.", "krea2": "Fotografias estéticas; funciona com 16 GB graças ao streaming do SSD.", "ideogram4": "O modelo da Ideogram no runtime MLX.", "anima": "Anime e ilustração.", "wan": "Imagem para vídeo: 1–5 segundos em 480p ou 720p."}},
    featEyebrow: 'Funcionalidades',
    featTitle: 'Uma app, um estúdio completo',
    bench: ['Benchmark: mede o teu Mac', 'Escolhe um modelo e mede-o no teu próprio Mac: segundos por passo, a imagem inteira, a memória máxima do VulKara e do sistema, o swap, o que foi lido do SSD e cada fase, do carregamento à geração. Copia as medições como tabela e compara Macs, tamanhos e bits. As mesmas medições tornaram o VulKara mais rápido: SD 1.5 duas vezes mais rápido com metade da memória, imagens SDXL grandes quatro vezes mais rápidas.', 'Ver as medições'],
    news: [['scan-text', "Prompt a partir da imagem", "Escolhe uma imagem em Imagem para imagem e carrega em <b>Prompt a partir da imagem</b>: o Qwen3-VL 2B descreve motivo, ambiente, luz, cores, estilo e câmara num parágrafo, no Mac, em cerca de 15 segundos num Mac mini M4 com 16 GB. Altera-o e gera."], ['activity', "Barra de menus e Monitor", "Fecha a janela e o VulKara continua a correr com o seu ícone na barra de menus: a tarefa em curso, o progresso, o que espera. O <b>Monitor</b> mostra a tarefa comparada com o seu plano de memória e, no Mac medido, com as medições do seu modelo."]],
    featLead: 'Imagens, edição, vídeo e LoRAs próprias – para criadores, estudantes, fãs de BD e anime e artistas digitais.',
    feats: [
      ['type', 'Texto para imagem', 'Descreva a imagem, escolha um estilo e prima ⌘↩. Vinte estilos, da fotografia à ilustração e ao 3D, e até três LoRAs, cada uma com o seu peso.'],
      ['eraser', 'Imagem para imagem e inpainting', 'Mantenha o motivo e mude a cena. Ou pinte apenas a parte que deve mudar – o resto fica intacto.'],
      ['frame', 'Tela de IA', 'Uma superfície infinita: leve a moldura para lá do limite e Gerar continua a imagem. Pinte uma máscara para refazer uma parte.'],
      ['clapperboard', 'Imagem para vídeo', 'Dê vida a uma imagem com o Wan 2.2: descreva o movimento e obtenha 1 a 5 segundos em 480p ou 720p.'],
      ['maximize-2', 'Ampliar e ferramentas de foto', '2× ou 4× com Real-ESRGAN, além de nitidez, redução de ruído, remoção de artefactos JPEG, remoção do fundo e seleção de objetos com um clique.'],
      ['wand-sparkles', 'Restaurar fotografias antigas', 'Dominantes de cor, pó e riscos corrigidos, rostos desfocados restaurados e fotografias a preto e branco coloridas.'],
      ['person-standing', 'Editor de pose', 'Esqueletos OpenPose com mãos e rostos, modelos ou uma pose detetada numa fotografia – depois, basta utilizá-la em Texto para imagem.'],
      ['sparkles', 'Ilusões', 'Esconda uma espiral, um padrão, uma palavra ou um logótipo numa imagem.'],
      ['graduation-cap', 'Treino de LoRAs', 'Ensine a um modelo o seu estilo de desenho ou a sua personagem com 10 a 30 imagens próprias, em SDXL, FLUX.2 [klein] ou Krea 2, com a curva de perda em direto.'],
      ['boxes', 'Muitos modelos', 'SD 1.5, SDXL (também Pony, Illustrious, NoobAI), SD 3.5, FLUX.1, FLUX.2, FLUX 3, Chroma, Qwen-Image, Z-Image, Krea 2, Ideogram 4, Anima e Wan 2.2 para vídeo. Transferência direta a partir de uma lista de modelos testados, importação do Hugging Face ou do Civitai (pode ser necessário um token de API) por ligação (URL ou criador/nome do modelo) ou a partir de um ficheiro de modelo já transferido.'],
    ],
    whyEyebrow: 'Porquê o VulKara',
    whyTitle: 'As suas ideias continuam suas',
    why: [
      ['monitor', 'Tudo no Mac', ['Imagens, vídeos, restauros e treino são executados na GPU da Apple. Os prompts e as imagens nunca saem do Mac – a internet só é utilizada para transferir runtimes, modelos e descrições de LoRAs, e para procurar atualizações. Desligue o Mac da rede e experimente – funciona também totalmente offline (se todos os pacotes de que depende tiverem sido transferidos antes!)']],
      ['tablet-smartphone', 'Pelo telemóvel, na sua própria rede', ['Abra o VulKara num navegador no telemóvel, tablet ou outro computador, na sua rede doméstica ou através de uma ligação VPN. Veja o estado atual das suas imagens, introduza e inicie novas ideias quando estiver fora, e veja, transfira ou partilhe imagens prontas no histórico. Só o seu Mac calcula. O acesso é protegido por um token de acesso e encriptado por HTTPS, para garantir também aqui a sua privacidade.'], 'Ative uma vez, leia o código QR, pronto. Nada vai para a internet.'],
      ['heart', 'Gratuito, sem letras pequenas', ['Sem conta, sem subscrição, sem créditos. O código-fonte é público: leia-o, altere-o, partilhe-o para qualquer utilização não comercial.'], 'Alguns modelos pedem um token gratuito do Hugging Face ou do Civitai antes da transferência.'],
      ['hard-drive', 'Também em Mac mais pequenos', ['Um modelo demasiado grande para a memória é transmitido do SSD bloco a bloco, com qualidade total. Num Mac mini M4 com 16 GB, o FLUX.1 [dev], o Krea 2 e o Qwen-Image 2.1 funcionam.'], 'O streaming troca velocidade por tamanho: os modelos grandes demoram minutos por imagem. O Stable Diffusion 1.5 funciona com 8 GB.'],
      ['languages', 'No seu idioma', ['English, Deutsch, Español, Português (Brasil) e Português (Portugal) – a app e o guia do utilizador. Falta o seu? Um novo idioma é uma pasta de ficheiros de texto.']],
    ],
    stepsEyebrow: 'Começar',
    stepsTitle: 'A primeira imagem em 3 passos',
    steps: [
      ['Instalar', 'Transfira o DMG, abra-o e arraste o VulKara para <b>Aplicações</b>.'],
      ['Runtime e modelo', '<b>Definições → Runtimes</b>: instale o <b>Diffusers (Apple GPU)</b>. Depois, <b>Modelos → Recomendados</b>: <i>SDXL 1.0</i> com 16 GB, <i>Stable Diffusion 1.5</i> com 8 GB.'],
      ['Criar', 'Abra <b>Texto</b>, descreva a imagem e prima <b>⌘↩</b>. A página Início assinala cada passo.'],
    ],
    shotsEyebrow: 'Capturas',
    shotsTitle: 'Um olhar por dentro',
    shotsOpen: 'abre a captura em tamanho real',
    shots: {
      text: ['Texto para imagem', 'prompt, modelo, estilo, tamanho e LoRAs numa página'],
      canvas: ['Tela de IA', 'continuar uma imagem para lá dos limites'],
      inpaint: ['Inpainting', 'voltar a pintar apenas o que marcar'],
      restore: ['Restaurar', 'fotografias antigas com um controlo de antes e depois'],
      video: ['Imagem para vídeo', 'uma imagem inicial e uma descrição do movimento'],
      pose: ['Editor de pose', 'esqueletos com mãos e rostos'],
      training: ['Treino', 'uma LoRA a partir das suas imagens'],
      models_recommended: ['Modelos recomendados', 'com a memória e o tamanho da transferência para o Mac'],
    },
    respTitle: 'Desenvolvido com responsabilidade',
    resp: [
      'cada prompt e cada resultado são verificados antes de serem apresentados',
      'a proteção de menores está sempre ativa',
      'antes de editar fotografias reais, pedimos o consentimento',
      'cada imagem recebe uma nota de IA nos metadados',
      'o selo visível «AI GENERATED» pode ser ativado com um clique',
    ],
    linksEyebrow: 'Saber mais',
    linksTitle: 'Guia, novidades e código',
    links: [
      ['lightbulb', 'Guia do utilizador', 'cada página e cada definição', `${BLOB}/docs/pt-PT/USER_GUIDE.md`],
      ['scroll-text', 'Wiki', 'guias e ajuda', `${GH}/wiki`],
      ['messages-square', 'Discord', 'comunidade e ajuda', DISCORD],
      ['file-clock', 'Novidades', 'o que há de novo?', `${BLOB}/CHANGELOG.md`],
      ['languages', 'Traduzir o VulKara', 'adicione o seu idioma (se ainda não existir)', `${BLOB}/docs/TRANSLATING.md`],
      ['scale', 'Licença', 'PolyForm Noncommercial 1.0.0', `${BLOB}/LICENSE`],
    ],
    supportTitle: 'Feito nos tempos livres. Alimentado a café.',
    support: 'O VulKara é gratuito para todos. Se lhe for útil, ofereça-me um café para o desenvolvimento continuar: integração de novos modelos, correções, etc.',
    coffee: 'Ofereça-me um café',
    pose3d: {"title": "Editor de pose em 3D", "alt": "Um esqueleto OpenPose a rodar no espaço: a câmara dá a volta à pose", "cap": "Esboço animado da ideia, não o editor acabado.", "lead": "Rode uma pose livremente no espaço e veja a sua figura de qualquer ângulo: de frente, de lado, de cima ou de baixo para cima. O resultado vai, como sempre, para Texto para imagem como pose.", "points": [["rotate-3d", "Rodar livremente", "Arraste a figura para mover a câmara à volta dela, para cima e para baixo. Vistas fixas com um clique: de frente, de lado, de costas, de cima."], ["bone", "Articulações como um corpo", "Arrastar um ponto roda a articulação, e os ossos mantêm o comprimento. Cabeça, ombros, ancas, joelhos e dedos ficam dentro de limites naturais – pode desligá-los para acrobacias."], ["bookmark", "Guarde as suas poses", "Guarde uma pose com o ponto de vista como modelo, volte a carregá-la, mude-lhe o nome ou partilhe-a como ficheiro."], ["users", "Para as suas personagens", "Uma pose guardada vai diretamente para uma cena de personagem, juntamente com o ponto de vista."]]},
    next: ["Próximas funcionalidades planeadas", "As suas próprias personagens", "Crie uma personagem uma vez – rosto, cabelo, roupa, estilo – e coloque-a como referência em qualquer cena: banda desenhada, cenas de anime, uma história inteira. A mesma personagem em todas as imagens. Criada e guardada no seu Mac, como tudo o resto.", "Planeado, mas ainda sem data. Para isso, é preciso muito café ;)"],
    nextPill: 'Novas funcionalidades planeadas',
    nextCap: "Uma personagem, sete imagens: a referência e seis cenas, feitas hoje mesmo com o VulKara (FLUX.2 klein com a imagem de referência na página Imagem). A funcionalidade vai transformar isto em poucos cliques.",
    nextAlts: {"mira": "Mira, a referência", "cafe": "A desenhar num café", "rooftop": "Num terraço ao pôr do sol", "neon": "Rua de néon à chuva", "mountain": "A caminhar ao amanhecer", "anime": "Como personagem de anime", "comic": "Como banda desenhada"},
    footAi: 'As imagens criadas com o VulKara nesta página têm o ícone da UE AI GENERATED.',
    foot: '© 2026 Oliver Schmidt<br>O VulKara é livre para utilização não comercial ao abrigo da PolyForm Noncommercial License 1.0.0. Esta página não utiliza cookies e não carrega nada de outros servidores.',
    legal: ['Aviso legal (Impressum)', 'Privacidade'],
    footPrivate: 'O VulKara é um projeto puramente pessoal e não está associado nem ligado a nenhuma empresa externa.',
    footTm: 'Apple, Mac e macOS são marcas comerciais da Apple Inc. O VulKara não está associado à Apple.',
  },
}

const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
// the icons inline (docs/icons, Lucide from the app): no request each, the colour from the text around them
// (currentColor), and they can move with CSS. Decorative: hidden from screen readers, the text next to them says it
const ICON_SVG = {}
const icon = (up, name, cls = 'ico') => {
  if (!ICON_SVG[name]) {
    const raw = readFileSync(join(ROOT, 'docs', 'icons', `${name}.svg`), 'utf8')
    ICON_SVG[name] = raw.replace(/^<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '')
  }
  return `<svg class="${cls}" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${ICON_SVG[name]}</svg>`
}

function page(lang) {
  const t = T[lang.code]
  const up = lang.dir ? '../' : ''
  const url = BASE + lang.dir
  const shotDir = lang.code === 'en' ? 'en' : lang.code
  const ext = (href, body, cls = '') => `<a${cls ? ` class="${cls}"` : ''} href="${href}" rel="noopener">${body}</a>`
  const alternates = LANGS.map((l) => `  <link rel="alternate" hreflang="${l.code}" href="${BASE}${l.dir}">`).join('\n')
  const ogAlts = LANGS.filter((l) => l !== lang).map((l) => `  <meta property="og:locale:alternate" content="${l.og}">`).join('\n')
  const langItems = LANGS.map((l) => {
    const href = up + (l.dir || './')
    const cur = l === lang ? ' aria-current="page"' : ''
    return `          <li><a href="${href}" hreflang="${l.code}" lang="${l.code}"${cur}>${l.name}</a></li>`
  }).join('\n')

  return `<!doctype html>
<html lang="${lang.code}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; base-uri 'none'; form-action 'none'">
  <meta name="referrer" content="strict-origin-when-cross-origin">
  <title>${esc(t.title)}</title>
  <meta name="description" content="${esc(t.desc)}">
  <link rel="canonical" href="${url}">
${alternates}
  <link rel="alternate" hreflang="x-default" href="${BASE}">
  <meta name="color-scheme" content="light dark">
  <meta name="theme-color" content="#fbfaf8" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#0e1014" media="(prefers-color-scheme: dark)">
  <link rel="icon" href="${up}assets/icon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="${up}assets/icon.png">
  <link rel="stylesheet" href="${up}style.css?v=${CSS_V}">
  <script src="${up}theme.js?v=${JS_V}"></script>
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="VulKara">
  <meta property="og:title" content="${esc(t.title)}">
  <meta property="og:description" content="${esc(t.desc)}">
  <meta property="og:url" content="${url}">
  <meta property="og:image" content="${BASE}social_preview.png">
  <meta property="og:image:width" content="1280">
  <meta property="og:image:height" content="640">
  <meta property="og:image:alt" content="${esc(t.ogAlt)}">
  <meta property="og:locale" content="${lang.og}">
${ogAlts}
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${esc(t.title)}">
  <meta name="twitter:description" content="${esc(t.desc)}">
  <meta name="twitter:image" content="${BASE}social_preview.png">
  <meta name="twitter:image:alt" content="${esc(t.ogAlt)}">
</head>
<body>
  <a class="skip" href="#main">${t.skip}</a>

  <header class="top">
    <div class="wrap">
      <span class="brandbox"><a class="brand" href="${up}${lang.dir || './'}"><img src="${up}assets/icon.svg" width="30" height="30" alt="">VulKara</a><a class="ver" href="${up}changes/" title="${t.changesNav}" aria-label="${t.changesNav}: v${VERSION}">v${VERSION}</a></span>
      <nav aria-label="VulKara">
        <a href="#features">${t.nav[0]}</a>
        <a href="#models">${t.models.nav}</a>
        <a href="#why">${t.nav[1]}</a>
        <a href="#screenshots">${t.nav[2]}</a>
        <a href="#start">${t.nav[3]}</a>
      </nav>
      <span class="spacer"></span>
      <details class="menu">
        <summary aria-label="${t.menu}">${icon(up, 'menu')}${icon(up, 'x', 'ico close')}</summary>
        <div class="panel">
          <a href="#features">${t.nav[0]}</a>
          <a href="#models">${t.models.nav}</a>
          <a href="#why">${t.nav[1]}</a>
          <a href="#screenshots">${t.nav[2]}</a>
          <a href="#start">${t.nav[3]}</a>
          <a class="phone" href="${DISCORD}" rel="noopener">${icon(up, 'messages-square')}Discord</a>
          <div class="theme phone" role="group" aria-label="${t.theme}">
${[['system', 'sun-moon'], ['light', 'sun'], ['dark', 'moon']].map(([v, ic], i) => `            <button type="button" data-set-theme="${v}" aria-pressed="${v === 'system'}" aria-label="${t.theme}: ${t.themes[i]}">${icon(up, ic)}</button>`).join('\n')}
          </div>
        </div>
      </details>
      <details class="lang">
        <summary aria-label="${t.language}: ${lang.name}">${icon(up, 'languages')}<span>${lang.name}</span></summary>
        <ul>
${langItems}
        </ul>
      </details>
      <a class="community" href="${DISCORD}" rel="noopener" aria-label="Discord">${icon(up, 'messages-square')}<span>Discord</span></a>
      <div class="theme" role="group" aria-label="${t.theme}">
${[['system', 'sun-moon'], ['light', 'sun'], ['dark', 'moon']].map(([v, ic], i) => `        <button type="button" data-set-theme="${v}" aria-pressed="${v === 'system'}" aria-label="${t.theme}: ${t.themes[i]}">${icon(up, ic)}</button>`).join('\n')}
      </div>
      ${ext('https://github.com/revil-O/VulKara/releases/latest', t.download, 'btn primary small')}
    </div>
  </header>

  <main id="main">
    <div class="hero">
      <div class="wrap">
        <img class="appicon" src="${up}assets/icon.svg" width="128" height="128" alt="">
        <p class="kicker">${t.kicker}</p>
        <h1>VulKara</h1>
        <p class="tagline">${t.tagline}</p>
        <p class="lead">${t.lead}</p>
        <ul class="chips">
${t.chips.map((c) => `          <li>${c}</li>`).join('\n')}
        </ul>
        <div class="cta">
          ${ext('https://github.com/revil-O/VulKara/releases/latest', `${icon(up, 'download')}${t.dlBig}`, 'btn primary big')}
          ${ext(GH, t.github, 'btn big ghost')}
        </div>
        <p class="note">${t.note}</p>
        <div class="cmd">
          <span class="cmd-label">${t.brewLabel}</span>
          <code><span class="prompt" aria-hidden="true">$</span> ${BREW}</code>
          <button type="button" class="copy" data-copy="${BREW}" data-done="${t.copied}" aria-label="${t.copy}">${icon(up, 'copy')}${icon(up, 'check', 'ico done')}</button>
        </div>
        <p class="note inspired">${t.inspired}</p>
        <a class="pill-next" href="#next"><span class="dot"></span>${t.nextPill}<span aria-hidden="true">→</span></a>
        <figure class="banner">
          <img src="${up}assets/banner.jpg" width="1712" height="420" alt="${esc(t.bannerAlt)}" fetchpriority="high">
          <figcaption>${t.bannerCap}</figcaption>
        </figure>
      </div>
    </div>

    <section id="streaming" aria-labelledby="streaming-title">
      <div class="wrap">
        <div class="stream">
          <div class="head">
            <span class="eyebrow">${icon(up, 'hard-drive')}${t.stream.eyebrow}</span>
            <h2 id="streaming-title">${t.stream.title}</h2>
            <p>${t.stream.lead}</p>
          </div>
          <div class="points">
${t.stream.points.map(([ic, h, p]) => `            <article>
              <div class="tile">${icon(up, ic)}</div>
              <h3>${h}</h3>
              <p>${p}</p>
            </article>`).join('\n')}
          </div>
          <p class="fine">${t.stream.fine}</p>
        </div>
      </div>
    </section>

    <section id="next" class="spotlight" aria-labelledby="next-title">
      <div class="wrap">
        <div class="spot-head">
          <span class="badge"><span class="dot"></span>${t.next[0]}</span>
          <h2 id="next-title">${t.next[1]}</h2>
          <p class="spot-lead">${t.next[2]}</p>
        </div>
        <div class="mosaic">
${['mira', 'cafe', 'rooftop', 'neon', 'mountain', 'anime', 'comic'].map((f) => `          <figure${f === 'mira' ? ' class="ref"' : ''}>
            <img src="${up}assets/characters/${f}.jpg" width="832" height="1216" alt="${esc(t.nextAlts[f])}" loading="lazy" decoding="async">
            <figcaption>${t.nextAlts[f]}</figcaption>
          </figure>`).join('\n')}
        </div>
        <p class="spot-cap">${t.nextCap}</p>
        <div class="spot-head spot-second">
          <h2 id="pose3d-title">${t.pose3d.title}</h2>
          <p class="spot-lead">${t.pose3d.lead}</p>
        </div>
        <figure class="pose-teaser">
          <picture>
            <source media="(prefers-reduced-motion: reduce)" srcset="${up}assets/pose3d/teaser_still.svg">
            <img src="${up}assets/pose3d/teaser.svg" width="640" height="400" alt="${esc(t.pose3d.alt)}" loading="lazy" decoding="async">
          </picture>
          <figcaption>${t.pose3d.cap}</figcaption>
        </figure>
        <div class="spot-points">
${t.pose3d.points.map(([ic, h, p]) => `          <article>
            <div class="tile">${icon(up, ic)}</div>
            <h3>${h}</h3>
            <p>${p}</p>
          </article>`).join('\n')}
        </div>
        <p class="spot-fine">${icon(up, 'coffee')}${t.next[3]}</p>
      </div>
    </section>

    <section id="gallery" aria-labelledby="gallery-title">
      <div class="wrap">
        <div class="head">
          <span class="eyebrow">${t.galEyebrow}</span>
          <h2 id="gallery-title">${t.galTitle}</h2>
          <p>${t.galLead}</p>
        </div>
        <div class="gallery">
${GALLERY.map(([file, w, h]) => `          <figure class="${w > h ? 'wide' : ''}">
            <img src="${up}assets/gallery/${file}.jpg" width="${w}" height="${h}" alt="${esc(t.galCaps[file])}" loading="lazy" decoding="async">
            <figcaption>${t.galCaps[file]}</figcaption>
          </figure>`).join('\n')}
        </div>
      </div>
    </section>

    <section id="features" aria-labelledby="features-title">
      <div class="wrap">
        <div class="head">
          <span class="eyebrow">${t.featEyebrow}</span>
          <h2 id="features-title">${t.featTitle}</h2>
          <p>${t.featLead}</p>
        </div>
        <div class="grid">
${t.feats.map(([ic, h, p], i) => `          <article class="card${i >= 8 ? ' wide' : ''}">
            <div class="tile">${icon(up, ic)}</div>
            <h3>${h}</h3>
            <p>${p}</p>
          </article>`).join('\n')}
${t.news.map(([ic, h, p]) => `          <article class="card">
            <div class="tile">${icon(up, ic)}</div>
            <h3>${h} <span class="new">${t.models.new}</span></h3>
            <p>${p}</p>
          </article>`).join('\n')}
          <article class="card full">
            <div class="tile">${icon(up, 'gauge')}</div>
            <h3>${t.bench[0]} <span class="new">${t.models.new}</span></h3>
            <p>${t.bench[1]}</p>
            <p><a href="${up}benchmarks/">${t.bench[2]} →</a></p>
          </article>
        </div>
      </div>
    </section>

    <section id="models" aria-labelledby="models-title">
      <div class="wrap">
        <div class="head">
          <span class="eyebrow">${t.models.eyebrow}</span>
          <h2 id="models-title">${t.models.title}</h2>
          <p>${t.models.lead}</p>
        </div>
        <ul class="models">
${MODELS.map(([key, name, runtimes, caps, isNew]) => `          <li class="card">${existsSync(join(ROOT, 'docs', 'images', 'models', `${key}.jpg`)) ? `
            <a class="pic" href="${up}assets/models/${key}.jpg"><img src="${up}assets/models/${key}.jpg" width="720" height="480" alt="${esc(`${t.models.made} ${name}`)}" loading="lazy" decoding="async"></a>` : ''}
            <div class="body">
              <h3>${name}${isNew ? ` <span class="new">${t.models.new}</span>` : ''}</h3>
              <p>${t.models.notes[key]}</p>
              <p class="tags">${runtimes.map((r) => `<span class="rt">${r}</span>`).join('')}${caps.map((c) => `<span>${t.models.caps[c]}</span>`).join('')}</p>
            </div>
          </li>`).join('\n')}
        </ul>
        <p class="models-fine">${t.models.fine}</p>
      </div>
    </section>

    <section id="why" aria-labelledby="why-title">
      <div class="wrap">
        <div class="head">
          <span class="eyebrow">${t.whyEyebrow}</span>
          <h2 id="why-title">${t.whyTitle}</h2>
        </div>
        <div class="why">
${t.why.map(([ic, h, ps, fine]) => `          <article class="card">
            <div class="tile">${icon(up, ic)}</div>
            <h3>${h}</h3>
${ps.map((p) => `            <p>${p}</p>`).join('\n')}${fine ? `\n            <p class="fine">${fine}</p>` : ''}
          </article>`).join('\n')}
        </div>
      </div>
    </section>

    <section id="start" aria-labelledby="start-title">
      <div class="wrap">
        <div class="head">
          <span class="eyebrow">${t.stepsEyebrow}</span>
          <h2 id="start-title">${t.stepsTitle}</h2>
        </div>
        <ol class="steps">
${t.steps.map(([h, p]) => `          <li class="card">
            <h3>${h}</h3>
            <p>${p}</p>
          </li>`).join('\n')}
        </ol>
      </div>
    </section>

    <section id="screenshots" aria-labelledby="screenshots-title">
      <div class="wrap">
        <div class="head">
          <span class="eyebrow">${t.shotsEyebrow}</span>
          <h2 id="screenshots-title">${t.shotsTitle}</h2>
        </div>
        <div class="shots">
${SHOTS.map(([name, h]) => {
    const [title, cap] = t.shots[name]
    const src = `${up}assets/screenshots/${shotDir}/${name}.jpg`
    return `          <figure>
            <a href="${src}" aria-label="${esc(`${title}: ${t.shotsOpen}`)}"><img src="${src}" width="1600" height="${h}" alt="${esc(`VulKara, ${title}: ${cap}`)}" loading="lazy" decoding="async"></a>
            <figcaption><b>${title}</b> – ${cap}</figcaption>
          </figure>`
  }).join('\n')}
        </div>
      </div>
    </section>

    <section aria-labelledby="responsible-title">
      <div class="wrap">
        <div class="responsible">
          ${icon(up, 'shield-check')}
          <div>
            <h2 id="responsible-title">${t.respTitle}</h2>
            <ul class="resp-list">${t.resp.map((x) => `<li>${x}</li>`).join('')}</ul>
          </div>
        </div>
      </div>
    </section>

    <section id="more" aria-labelledby="more-title">
      <div class="wrap">
        <div class="head">
          <span class="eyebrow">${t.linksEyebrow}</span>
          <h2 id="more-title">${t.linksTitle}</h2>
        </div>
        <ul class="links">
${t.links.map(([ic, h, s, href]) => `          <li>${ext(href, `${icon(up, ic)}<span>${h}<small>${s}</small></span>`)}</li>`).join('\n')}
        </ul>
        <div class="support">
          <h2>${t.supportTitle}</h2>
          <p>${t.support}</p>
          ${ext('https://buymeacoffee.com/revil.0', `${icon(up, 'coffee')}${t.coffee}`, 'btn primary big')}
        </div>
      </div>
    </section>
  </main>

  <footer>
    <div class="wrap">
      <p class="ai">${t.footAi}</p>
      <p>${t.foot}</p>
      <p>${t.footPrivate}</p>
      <p>${t.footTm}</p>
      <p class="legal"><a href="${up}impressum/">${t.legal[0]}</a> · <a href="${up}datenschutz/">${t.legal[1]}</a> · <a href="${up}changes/">${t.changesNav}</a> · <a href="${up}benchmarks/">Benchmarks</a> · <a href="${up}results/">Results</a> · <a href="${DISCORD}" rel="noopener">Discord</a></p>
    </div>
  </footer>
</body>
</html>
`
}

for (const lang of LANGS) {
  const dir = join(SITE, lang.dir)
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, 'index.html'), page(lang))
}
console.log('pages written')

// ---------------------------------------------------------------- legal notice and privacy (German law), with English
// The operator's name, address and e-mail are not in the repository: site/legal.local.json (git-ignored) or the
// environment variable VK_LEGAL (the same JSON, a secret in CI): { "name", "street", "city", "email" }. Without them the
// pages keep {{…}} placeholders, and tools/deploy_site.sh refuses to upload.
const legalFile = join(SITE, 'legal.local.json')
const L = process.env.VK_LEGAL ? JSON.parse(process.env.VK_LEGAL)
  : existsSync(legalFile) ? JSON.parse(readFileSync(legalFile, 'utf8')) : {}
const v = (k) => L[k] || `{{${k}}}`
const operator = `${v('name')}<br>${v('street')}<br>${v('city')}<br>Deutschland`
const mail = L.email ? `<a href="mailto:${L.email}">${L.email}</a>` : '{{email}}'

const LEGAL = {
  impressum: {
    title: 'Impressum · Legal notice',
    body: `
      <h1>Impressum</h1>
      <h2>Angaben gemäß § 5 DDG</h2>
      <p>${operator}</p>
      <h2>Kontakt</h2>
      <p>E-Mail: ${mail}</p>
      <h2>Verantwortlich für den Inhalt nach § 18 Abs. 2 MStV</h2>
      <p>${v('name')}, Anschrift wie oben</p>
      <h2>Haftung für Links</h2>
      <p>Diese Seite verlinkt auf Angebote Dritter (GitHub, Buy Me a Coffee). Für deren Inhalte sind allein deren
      Anbieter verantwortlich. Bei Bekanntwerden von Rechtsverletzungen werden solche Links umgehend entfernt.</p>
      <h2>Verbraucherstreitbeilegung</h2>
      <p>Ich bin nicht bereit und nicht verpflichtet, an Streitbeilegungsverfahren vor einer
      Verbraucherschlichtungsstelle teilzunehmen.</p>
      <hr>
      <h1 lang="en">Legal notice</h1>
      <p lang="en">VulKara is made by ${v('name')}, ${v('street')}, ${v('city')}, Germany. Contact: ${mail}.
      The German text above is the binding one.</p>`,
  },
  datenschutz: {
    title: 'Datenschutz · Privacy',
    body: `
      <h1>Datenschutzerklärung</h1>
      <h2>Verantwortlicher</h2>
      <p>${operator}<br>E-Mail: ${mail}</p>
      <h2>Kurz gesagt</h2>
      <p>Diese Website setzt keine Cookies, nutzt keine Analyse- oder Tracking-Werkzeuge und lädt keine Inhalte von
      anderen Servern (keine Schriften, Skripte oder eingebetteten Medien Dritter).</p>
      <h2>Hosting und Server-Logdateien</h2>
      <p>Die Website liegt bei ALL-INKL.COM – Neue Medien Münnich, Hauptstraße 68, 02742 Friedersdorf, Deutschland,
      mit dem ein Vertrag zur Auftragsverarbeitung besteht. Beim Aufruf einer Seite verarbeitet der Server technisch
      notwendige Daten: IP-Adresse, Datum und Uhrzeit, aufgerufene Seite, übertragene Datenmenge, Referrer und
      Browser-Kennung. Das dient dem sicheren und stabilen Betrieb (Art. 6 Abs. 1 lit. f DSGVO). Die Logdateien werden
      nach {{log_days}} Tagen gelöscht; eine Zusammenführung mit anderen Daten findet nicht statt.</p>
      <h2>Links zu anderen Anbietern</h2>
      <p>Die Links zu GitHub (Download, Quellcode, Wiki) und zu Buy Me a Coffee führen auf deren Seiten; dort gelten
      deren Datenschutzerklärungen. Erst mit dem Klick werden Daten an diese Anbieter übertragen.</p>
      <h2>Die App</h2>
      <p>VulKara selbst rechnet auf deinem Mac. Prompts, Bilder und Pfade verlassen den Mac nicht; das Netz wird nur
      zum Herunterladen von Runtimes, Modellen und Beschreibungen von LoRAs genutzt.</p>
      <h2>Deine Rechte</h2>
      <p>Du hast das Recht auf Auskunft, Berichtigung, Löschung und Einschränkung der Verarbeitung, auf
      Datenübertragbarkeit und auf Widerspruch gegen die Verarbeitung (Art. 15–21 DSGVO), sowie das Recht auf
      Beschwerde bei einer Datenschutz-Aufsichtsbehörde (Art. 77 DSGVO). Eine E-Mail an ${mail} genügt.</p>
      <hr>
      <h1 lang="en">Privacy</h1>
      <p lang="en">This website sets no cookies, uses no analytics or tracking and loads nothing from other servers. The
      host (ALL-INKL.COM, Germany) keeps technically necessary server logs (IP address, time, page, referrer, browser)
      for {{log_days}} days for a secure operation. Links to GitHub and Buy Me a Coffee lead to their sites and their
      privacy policies. The app itself computes on your Mac; prompts, pictures and paths never leave it. Your rights
      under the GDPR (access, correction, deletion, objection, complaint to a supervisory authority): write to
      ${mail}. The German text above is the binding one.</p>`,
  },
}

for (const [slug, p] of Object.entries(LEGAL)) {
  const dir = join(SITE, slug)
  mkdirSync(dir, { recursive: true })
  const body = p.body.replace(/\{\{log_days\}\}/g, L.log_days ? String(L.log_days) : '{{log_days}}')
  writeFileSync(join(dir, 'index.html'), `<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; base-uri 'none'; form-action 'none'">
  <title>${p.title} – VulKara</title>
  <link rel="canonical" href="${BASE}${slug}/">
  <link rel="stylesheet" href="../style.css?v=${CSS_V}">
  <script src="../theme.js?v=${JS_V}"></script>
</head>
<body>
  <main class="legal-page">
    <div class="wrap">
      <p><a href="../">← VulKara</a></p>${body}
    </div>
  </main>
</body>
</html>
`)
}
console.log(L.name ? 'legal pages written' : 'legal pages written with placeholders (site/legal.local.json missing)')

// ---------------------------------------------------------------- changes: every release's new features and changes
// site/changes/index.html from CHANGELOG.md (English, as the changelog), in a technical look. A release raises the
// version in package.json, which deploys the site (site.yml), so the page follows every release by itself. Only
// released versions: an "Unreleased" section of the development line stays out.
const inline = (s) => esc(s)
  .replace(/`([^`]+)`/g, '<code>$1</code>')
  .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  .replace(/(^|[^*\w])\*([^*\s][^*]*)\*(?!\w)/g, '$1<em>$2</em>')
  .replace(/\[([^\]]+)\]\((https:\/\/[^)\s]+)\)/g, '<a href="$2" rel="noopener">$1</a>')

/** The released versions of the changelog: [{ version, date, blocks: [{ kind: 'item' | 'text', text, subs }] }] */
function releases(markdown) {
  const out = []
  let cur, last
  for (const line of markdown.split('\n')) {
    const head = /^## (\d+\.\d+\.\d+\S*) – (\d{4}-\d{2}-\d{2})/.exec(line)
    if (head) { out.push(cur = { version: head[1], date: head[2], blocks: [] }); last = undefined; continue }
    if (line.startsWith('## ') || line.startsWith('# ')) { cur = undefined; continue }
    if (!cur || !line.trim()) { if (!line.trim()) last = last?.kind === 'text' ? undefined : last; continue }
    const sub = /^ {2}- (.*)$/.exec(line)
    if (line.startsWith('- ')) cur.blocks.push(last = { kind: 'item', text: line.slice(2), subs: [] })
    else if (sub && last?.kind === 'item') last.subs.push(sub[1])
    else if (line.startsWith(' ') && last?.kind === 'item') {
      if (last.subs.length && /^ {4}/.test(line)) last.subs[last.subs.length - 1] += ' ' + line.trim()
      else last.text += ' ' + line.trim()
    } else if (last?.kind === 'text') last.text += ' ' + line.trim()
    else cur.blocks.push(last = { kind: 'text', text: line.trim(), subs: [] })
  }
  return out
}

function changesPage(list) {
  const total = list.reduce((n, r) => n + r.blocks.filter((b) => b.kind === 'item').length, 0)
  const entry = (b) => {
    const m = /^\*\*(.+?)\*\*\s*(.*)$/.exec(b.text)
    const subs = b.subs.length ? `\n          <ul>${b.subs.map((s) => `<li>${inline(s)}</li>`).join('')}</ul>` : ''
    return b.kind === 'text' ? `        <p class="note">${inline(b.text)}</p>`
      : m ? `        <li><span class="title">${inline(m[1])}</span> ${inline(m[2])}${subs}</li>`
        : `        <li>${inline(b.text)}${subs}</li>`
  }
  const section = (r, i) => {
    const items = r.blocks.filter((b) => b.kind === 'item')
    const notes = r.blocks.filter((b) => b.kind === 'text').map(entry).join('\n')
    return `    <section class="release" id="v${esc(r.version)}">
      <header>
        <a class="tag" href="#v${esc(r.version)}">v${esc(r.version)}</a>
        <time datetime="${r.date}">${r.date}</time>
        <span class="count">${items.length} ${items.length === 1 ? 'change' : 'changes'}</span>${i === 0 ? '\n        <span class="latest">latest</span>' : ''}
        <a class="gh" href="${GH}/releases/tag/v${esc(r.version)}" rel="noopener">release ↗</a>
      </header>${notes ? '\n' + notes : ''}
      <ul class="entries">
${items.map(entry).join('\n')}
      </ul>
    </section>`
  }
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'self'; script-src 'self'; base-uri 'none'; form-action 'none'">
  <meta name="referrer" content="strict-origin-when-cross-origin">
  <title>Changes – VulKara</title>
  <meta name="description" content="New features and changes of every VulKara release, from the changelog.">
  <link rel="canonical" href="${BASE}changes/">
  <meta name="color-scheme" content="light dark">
  <link rel="icon" href="../assets/icon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="../style.css?v=${CSS_V}">
  <script src="../theme.js?v=${JS_V}"></script>
</head>
<body class="changes-page">
  <header class="cl-top">
    <div class="wrap">
      <a class="brand" href="../"><img src="../assets/icon.svg" width="26" height="26" alt="">VulKara<span class="ver">v${VERSION}</span></a>
      <span class="path">~/vulkara <b>$</b> changelog --releases</span>
      <span class="spacer"></span>
      <a class="gh" href="../benchmarks/">benchmarks</a>
      <a class="gh" href="../results/">results</a>
      <a class="gh" href="${BLOB}/CHANGELOG.md" rel="noopener">CHANGELOG.md ↗</a>
    </div>
  </header>
  <main id="main" class="wrap">
    <div class="intro">
      <h1>Changes</h1>
      <p>New features, fixes and measurements of every release, taken from the changelog.
      <span class="stat">${list.length} releases · ${total} entries · latest v${esc(list[0]?.version ?? VERSION)} (${list[0]?.date ?? ''})</span></p>
    </div>
    <div class="cl-grid">
    <nav class="index" aria-label="Releases">
      <ol>
${list.map((r) => `        <li><a href="#v${esc(r.version)}"><span>v${esc(r.version)}</span><time datetime="${r.date}">${r.date}</time></a></li>`).join('\n')}
      </ol>
    </nav>
    <div class="releases">
${list.map(section).join('\n')}
    </div>
    </div>
  </main>
  <footer>
    <div class="wrap">
      <p class="legal"><a href="../">VulKara</a> · <a href="../impressum/">Impressum</a> · <a href="../datenschutz/">Datenschutz</a> · <a href="../benchmarks/">Benchmarks</a> · <a href="../results/">Results</a> · <a href="${GH}" rel="noopener">GitHub</a></p>
    </div>
  </footer>
</body>
</html>
`
}

{
  const list = releases(readFileSync(join(ROOT, 'CHANGELOG.md'), 'utf8'))
  // a release without entries means the changelog's layout changed and the parser no longer follows it
  const empty = list.filter((r) => !r.blocks.length).map((r) => r.version)
  if (!list.length || empty.length) throw new Error(`changes page: no entries read for ${empty.join(', ') || 'any release'}`)
  mkdirSync(join(SITE, 'changes'), { recursive: true })
  writeFileSync(join(SITE, 'changes', 'index.html'), changesPage(list))
  console.log(`changes page written (${list.length} releases)`)
}

// ---------------------------------------------------------------- benchmarks: the measurements as charts
{
  const BENCH_V = createHash('sha256').update(readFileSync(join(SITE, 'bench.js'))).digest('hex').slice(0, 10)
  const { html, css } = benchmarksPage({ BASE, GH, BLOB, VERSION, CSS_V, JS_V, BENCH_V })
  mkdirSync(join(SITE, 'benchmarks'), { recursive: true })
  writeFileSync(join(SITE, 'benchmarks', 'index.html'), html)
  writeFileSync(join(SITE, 'benchmarks', 'charts.css'), css)
  console.log('benchmarks page written')
}

// ---------------------------------------------------------------- results: pictures at full size, also docs/RESULTS.md
{
  mkdirSync(join(SITE, 'results'), { recursive: true })
  writeFileSync(join(SITE, 'results', 'index.html'), resultsPage({ BASE, BLOB, VERSION, CSS_V, JS_V }))
  writeFileSync(join(ROOT, 'docs', 'RESULTS.md'), resultsMarkdown({ BASE }))
  console.log('results page written')
}
