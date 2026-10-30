// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// The interface between the pages and the main process (preload: window.vk).

import type { Asset, HistoryEntry, Job } from './types'
import type { FolderKey, Settings } from './settings'
import type { Language } from './i18n'
import type { Allowed } from './licence_terms'
import type { LoraSearchPage, LoraSearchRequest } from './lora_bases'

export interface RuntimeInfo {
  id: 'diffusers' | 'mlx' | 'comfyui'
  name: string
  description: string
  details: string[]
  installed: boolean
  /** the stage of its running installation */
  installing?: string
  /** why the last installation failed */
  error?: string
  version?: string
  path: string
  sizeGb: number
}

/** One version source of a runtime in the update check (a package such as diffusers, or ComfyUI itself). */
export interface RuntimeComponentUpdate {
  name: string
  installed?: string
  /** the newest version an Update installs (inside the range the app allows) */
  latest?: string
  /** a newer release that the app does not allow yet: it comes with an app update */
  newest?: string
  updateAvailable: boolean
  /** "could not check (…)" or "not checked yet" */
  error?: string
}

export interface RuntimeUpdate {
  id: RuntimeInfo['id']
  /** the first component's versions */
  installed?: string
  latest?: string
  updateAvailable: boolean
  checkedAt?: number
  error?: string
  components: RuntimeComponentUpdate[]
}

/** The update check of the installed runtimes. */
export interface RuntimeUpdates {
  checkedAt?: number
  checking: boolean
  runtimes: RuntimeUpdate[]
}

/** The app's own update: the newest release on GitHub against this version, and how far its installation is. */
export interface AppUpdateState {
  current: string
  checking?: boolean
  checkedAt?: number
  checkError?: string
  /** a newer released version, with its release notes */
  available?: string
  notesUrl?: string
  /** downloading (percent), checking the DMG, restarting into it, or error (a reason key or message) */
  stage: 'idle' | 'downloading' | 'checking' | 'restarting' | 'error'
  percent: number
  error?: string
}

/** Time the steps of a job waited for parts of the model to be read again, and how much was read. */
export interface Waited {
  /** ssd_stream: blocks of a model streamed from the SSD */
  what: string
  seconds: number
  gb: number
}

export type QueuedJobState = 'waiting' | 'running' | 'done' | 'failed' | 'cancelled'

export interface QueuedJob {
  job: Job
  state: QueuedJobState
  /** 0..100, -1 while it can not be told */
  progress: number
  status: string
  /** seconds left, undefined while unknown */
  eta?: number
  /** seconds per step of the running job */
  secondsPerStep?: number
  /** the bit size each part of the model runs in, as the engine reported it */
  precision?: string
  /** time the steps waited for parts of the model read again, summed per kind */
  waited?: Waited[]
  /** the engine's own peak footprint and disk reads over the job, and what its memory plan expected */
  footprint?: { peakGb: number; readGb: number; planGb?: number }
  results: string[]
  error?: string
  addedAt: number
  startedAt?: number
  finishedAt?: number
}

export interface QueueSnapshot {
  jobs: QueuedJob[]
  engineReady: boolean
}

/** A picture or video in the large view, with the job it came from. */
export interface ViewerItem {
  job: Job
  file: string
  /** name of the model, when the job's folder does not tell it any more */
  model?: string
}

export interface ViewerPayload {
  items: ViewerItem[]
  index: number
}

/** What a viewer window hands back to the main window. */
export interface ViewerAction {
  /** reuse: the job's settings into the form of page; continue: the file as input of page */
  type: 'reuse' | 'continue'
  page: string
  job: Job
  file: string
}

type PosePoints = ([number, number] | null)[]

/** The faces of a photo Restore would restore: 5 landmarks (eyes, nose tip, mouth corners) and the restored square
 *  [x, y, w, h], in the photo's pixels. */
export interface FoundFaces {
  size: [number, number]
  faces: { points: [number, number][]; box: [number, number, number, number] }[]
}

/** The people found in a photo: points in the photo's pixels, null where a point was not found. */
export interface DetectedPose {
  width: number
  height: number
  people: { body: PosePoints; rhand: PosePoints | null; lhand: PosePoints | null; face: PosePoints | null }[]
}

/** What a LoRA was trained with, as far as its file tells. */
export interface LoraTraining {
  title?: string
  base?: string
  network?: string
  resolution?: string
  images?: number
  epochs?: number
  steps?: number
  learningRate?: number
  trained?: string
  software?: string
  /** the most used tags of the training pictures with their counts */
  topTags: [string, number][]
}

export interface LoraDetails {
  sizeMb: number
  /** millions of parameters */
  paramsM?: number
  /** where the trigger words come from */
  triggerSource: 'user' | 'civitai' | 'training'
  /** the page the LoRA was downloaded from */
  page?: string
  pageName?: string
  training?: LoraTraining
}

/** A prompt the makers of a LoRA showed it with, and the settings of that picture. */
export interface LoraExample {
  prompt: string
  negative?: string
  steps?: number
  guidance?: number
  sampler?: string
  seed?: number
  /** the strength the LoRA had in this picture */
  strength?: number
  clipSkip?: number
}

/** The licence of an installed model or LoRA, as its origin states it (licence.json in its folder). */
export interface AssetLicence {
  /** where it was read; none: the origin is not known */
  source: 'civitai' | 'huggingface' | 'none'
  page?: string
  /** its name on that page */
  name?: string
  licence?: string
  licenceUrl?: string
  /** commercial use of the model / of the pictures */
  model: Allowed
  outputs: Allowed
  note?: string
  /** the base model its page names */
  baseModel?: string
  /** the page was found by the folder's name, not by a known origin */
  guessed?: boolean
  fetchedAt: number
}

/** What the page of a LoRA (Civitai, Hugging Face) says about it. */
export interface LoraInfo {
  source: 'civitai' | 'huggingface'
  page: string
  name?: string
  version?: string
  creator?: string
  /** what the LoRA teaches, as its makers classified it */
  kind?: 'style' | 'person' | 'object' | 'concept'
  tags: string[]
  baseModel?: string
  description: string[]
  /** what the makers wrote about this version */
  versionNotes: string[]
  trainedWords: string[]
  recommended: {
    strength?: number
    minStrength?: number
    maxStrength?: number
    /** the makers set the strength themselves; otherwise it is taken from their example pictures */
    fromMakers: boolean
    steps?: number
    guidance?: number
    sampler?: string
    clipSkip?: number
    /** how many example pictures the numbers come from */
    examples: number
  }
  examples: LoraExample[]
  /** what the makers allow commercially, in the words of Civitai */
  commercialUse?: string[]
  licence?: string
  fetchedAt: number
}

export interface TrainingImage {
  path: string
  caption: string
}

export interface TrainingRequest {
  name: string
  trigger: string
  /** folder of the model to train on */
  baseModel: string
  images: TrainingImage[]
  resolution: number
  steps: number
  rank: number
  learningRate: number
}

export interface TrainingState {
  running: boolean
  name?: string
  /** loading, preparing, training */
  phase?: string
  message?: string
  step?: number
  total?: number
  loss?: number
  /** seconds left */
  eta?: number
  losses: number[]
  result?: { folder: string; name: string; trigger: string }
  error?: string
  stopped?: boolean
}

export interface LogLine {
  /** milliseconds since 1970 */
  time: number
  text: string
  /** what the line measured, e.g. size and speed of a download */
  note?: string
}

/** One start of the app in the log files (logs/session-….log), for the problem report. */
export interface LogSession {
  /** the file name, the only way a page names a session */
  id: string
  /** when it started and when its last line was written (ms) */
  start: number
  end?: number
  lines: number
  /** lines with error, failed or Traceback */
  errors: number
  bytes: number
  /** the session running now */
  current: boolean
}

/** A session log made fit to be posted: personal data replaced by ****. */
export interface LogReport {
  id: string
  /** app version, macOS, Mac model with chip and memory; no names */
  header: string
  text: string
  /** "Hidden: 41 paths, 2 tokens, 3 prompts and texts" */
  summary: string
  counts: Record<string, number>
}

/** What the Mac is doing right now (status bar, Hardware page); every 2 s. */
export interface SystemStats {
  /** all cores, 0..100 */
  cpuPercent: number
  /** the GPU as its driver reports it, 0..100; -1 when it does not */
  gpuPercent: number
  /** memory VulKara and its engines hold */
  appGb: number
  /** memory the system has in use (active, wired, compressed) */
  usedGb: number
  totalGb: number
  /** the SSD streaming caches on the disk, and the room left there */
  streamCacheGb: number
  streamFreeGb: number
  streamWhere: string
  /** read since the Mac started (vm_stat page-ins and swap-ins): the difference over a job is what it read back */
  pageinsGb: number
  swapinsGb: number
  /** swap in use on the SSD (when memory runs short, macOS moves pages there and everything slows down) */
  swapGb: number
}

/** A phase of a benchmark run: the engine's status line and how long it lasted (still counting while it runs). */
export interface BenchmarkPhase {
  text: string
  /** milliseconds since 1970 */
  at: number
  seconds: number
}

/** One picture of a benchmark (Hardware page): a model's job through the queue, with its times and the memory the Mac
 *  used meanwhile (the peaks of the 2 s samples). */
export interface BenchmarkRun {
  /** the queue job's id */
  id: string
  /** milliseconds since 1970 */
  at: number
  model: string
  /** the app's version and the code state it was built from ("0.7.1 7370989+ 2026-10-26 15:42"); missing on older runs */
  build?: string
  width: number
  height: number
  steps?: number
  state: QueuedJobState
  error?: string
  secondsPerStep?: number
  /** the whole job, with loading the model and saving the picture */
  seconds?: number
  /** the footprint of the app and its engines, with what the GPU holds */
  peakAppGb: number
  peakUsedGb: number
  totalGb: number
  /** swap in use when the job started, and its highest value while it ran */
  swapStartGb?: number
  peakSwapGb: number
  /** read back while the job ran, Mac-wide: from the disks (model files, mapped or streamed) and from the swap */
  diskReadGb?: number
  swapReadGb?: number
  /** time the steps waited for parts of the model read again, as the engine measured it */
  waited?: Waited[]
  /** the engine's own processes: peak footprint and disk reads over the job, and the peak its memory plan expected */
  footprint?: { peakGb: number; readGb: number; planGb?: number }
  /** the bit size each part of the model ran in ("transformer 8 bit, text encoder 4 bit") */
  precision?: string
  /** what the engine did one after the other (handing over to Diffusers, preparing SSD streaming, quantizing, loading,
   *  generating), each with how long it took; a figure that counts up stays one phase */
  phases: BenchmarkPhase[]
  /** how the job was made where that differs from the usual */
  note?: string
  /** the picture, to look at what was measured */
  result?: string
}

/** This Mac (Hardware page); asked once. */
export interface HardwareInfo {
  chip: string
  arch: string
  performanceCores: number
  efficiencyCores: number
  totalCores: number
  ramGb: number
  gpuCores?: number
  /** about how much of the unified memory Metal lets one process use */
  metalBudgetGb: number
  metal: boolean
}

/** A helper model (engines/diffusers/helpers.json): content filter, Restore, pose and depth, ControlNet, upscaling. */
export interface HelperModel {
  id: string
  name: string
  /** Content filter, Restore, Pose and depth, ControlNet, Upscale */
  group: string
  description: string
  repo: string
  folder: string
  /** download size */
  sizeMb: number
  installed: boolean
  /** what is on the disk */
  diskMb: number
  /** needed for every result (the content filter): it can not be removed */
  required: boolean
  /** name of its preview picture (assets/helpers) */
  preview: string
}

/** An installed photo tool (Enhance page). */
export interface PhotoTool {
  folder: string
  name: string
  /** sharpen, denoise, upscale, dejpeg, cutout, select, custom */
  task: string
  kind: 'image' | 'mask' | 'segment'
  /** torch: PyTorch weights on the GPU (spandrel); onnx: onnxruntime on the CPU */
  runtime: 'torch' | 'onnx'
  /** a few words for the list; the description goes into the info badge */
  summary?: string
  description: string
  /** how many times an image tool enlarges */
  scale: number
  /** the longest side it takes, where limited */
  maxSide?: number
  licence?: string
  licenceUrl?: string
  /** where the source's own licence statement is incomplete or inconsistent */
  licenceNote?: string
  sourceUrl?: string
  /** the catalog id of a recommended tool */
  recommended?: string
}

/** A tool of the catalog (engines/diffusers/photo_tools.json). */
export interface RecommendedTool {
  id: string
  name: string
  task: string
  kind: 'image' | 'mask' | 'segment'
  runtime: 'torch' | 'onnx'
  summary?: string
  description: string
  /** other weights the tool offers, downloaded when first chosen; defaultLabel names its own */
  variants?: { id: string; label: string; description: string; sizeMb: number }[]
  defaultLabel?: string
  /** JPEG cleanup: the JPEG quality can be set */
  quality?: boolean
  /** how many times it enlarges, the longest side it takes (image tools) */
  scale?: number
  maxSide?: number
  sizeMb: number
  licence: string
  licenceUrl: string
  licenceNote?: string
  sourceUrl: string
  installed: boolean
}

export interface ImportRequest {
  /** hf: repository id, civitai: page URL, file / dir / toolfile (a photo model file): path, tool / helper: catalog id */
  source: 'hf' | 'civitai' | 'file' | 'dir' | 'tool' | 'toolfile' | 'helper' | 'merge'
  ref: string
  /** one file of a Hugging Face repository */
  file?: string
  name?: string
  quant?: 'auto' | 'none' | 'q8' | 'q4'
  /** import although the model needs more memory than this Mac has */
  force?: boolean
}

/** What an import would bring, found out without downloading it. */
export interface ImportInfo {
  kind: 'model' | 'lora'
  label: string
  downloadGb: number
  gated: boolean
  fits?: boolean
  minRamGb?: number
  /** too large for the memory: it runs streamed from the SSD (minRamGb is then what that needs) */
  streamed?: boolean
  /** how the model would be compressed to fit */
  quant?: string
  inPlace: boolean
  note?: string
  triggerWords?: string[]
}

export interface ImportJob {
  id: string
  title: string
  request: ImportRequest
  state: QueuedJobState
  stage: string
  /** 0..100, -1 while it can not be told */
  percent: number
  error?: string
}

export interface HistoryPage {
  /** entries matching the search, before paging */
  total: number
  entries: HistoryEntry[]
}

export interface VulkaraApi {
  settings: {
    get(): Promise<Settings>
    set<K extends keyof Settings>(key: K, value: Settings[K]): Promise<void>
    /** the main process asks for the folder; undefined when cancelled */
    chooseFolder(key: FolderKey): Promise<string | undefined>
  }
  i18n: {
    /** the app's language (System already resolved) and the locale for dates and numbers */
    lang(): Promise<Language>
    onLang(fn: (language: Language) => void): () => void
  }
  tokens: {
    set(service: 'huggingface' | 'civitai', token: string): Promise<'stored' | 'session' | 'removed'>
    has(service: 'huggingface' | 'civitai'): Promise<boolean>
  }
  runtimes: {
    list(): Promise<RuntimeInfo[]>
    install(id: RuntimeInfo['id']): Promise<{ version: string }>
    remove(id: RuntimeInfo['id']): Promise<void>
    onProgress(fn: (id: string, stage: string, percent: number) => void): () => void
    /** the last update check, against what is installed now (no network) */
    updates(): Promise<RuntimeUpdates>
    /** asks PyPI and GitHub; force: also when the last check is younger than 12 hours */
    checkUpdates(force?: boolean): Promise<RuntimeUpdates>
    onUpdates(fn: (updates: RuntimeUpdates) => void): () => void
  }
  queue: {
    add(job: Omit<Job, 'id'>, count?: number): Promise<string[]>
    cancel(jobId: string): Promise<void>
    clearFinished(): Promise<void>
    snapshot(): Promise<QueueSnapshot>
    onChange(fn: (snapshot: QueueSnapshot) => void): () => void
  }
  assets: {
    list(): Promise<Asset[]>
    /** moves the folder of a model or LoRA to the Trash */
    remove(id: string): Promise<void>
    /** a model imported on another Mac: its folder to the Trash, then imported again from its source under its name;
     * returns the import's id */
    reimport(id: string): Promise<string>
    /** the name the app shows for it; folder and files keep theirs. An empty title brings back the folder's name */
    rename(id: string, title: string): Promise<void>
    /** LoRAs baked into a new model of its own (a job of the import queue); returns the import's id */
    bake(modelId: string, loras: { id: string; scale: number }[], name: string): Promise<string>
    /** the model written as one .safetensors checkpoint where the user chooses; resolves with the file, or '' when cancelled */
    exportSingle(modelId: string): Promise<string>
    onExportProgress(fn: (stage: string, percent: number) => void): () => void
    onChange(fn: () => void): () => void
  }
  benchmark: {
    /** the job count times (the first picture loads the model, the next ones show the speed with it loaded) */
    start(job: Omit<Job, 'id'>, count: number, model: string): Promise<string[]>
    list(): Promise<BenchmarkRun[]>
    clear(): Promise<void>
    onChange(fn: (runs: BenchmarkRun[]) => void): () => void
  }
  system: {
    stats(): Promise<SystemStats>
    hardware(): Promise<HardwareInfo>
    onStats(fn: (stats: SystemStats) => void): () => void
  }
  helpers: {
    list(): Promise<HelperModel[]>
    /** downloads one ahead of its first use (through the import queue); returns the import's id */
    install(id: string): Promise<string>
    /** moves it to the Trash; it is downloaded again when needed */
    remove(id: string): Promise<void>
  }
  tools: {
    list(): Promise<{ installed: PhotoTool[]; recommended: RecommendedTool[] }>
    /** downloads a recommended tool (through the import queue); returns the import's id */
    install(id: string): Promise<string>
    /** asks for a model file (.pth, .safetensors, .onnx) and imports it; undefined when cancelled */
    importFile(): Promise<string | undefined>
    remove(folder: string): Promise<void>
    /** selection tools: the mask of what the clicks mean ([x, y, 1 | 0] in picture pixels) */
    select(tool: string, image: string, points: [number, number, number][]): Promise<{ mask: string; score: number }>
  }
  imports: {
    inspect(request: ImportRequest): Promise<ImportInfo>
    add(request: ImportRequest, title: string): Promise<string>
    cancel(id: string): Promise<void>
    clearFinished(): Promise<void>
    list(): Promise<ImportJob[]>
    onChange(fn: (jobs: ImportJob[]) => void): () => void
  }
  history: {
    /**
     * newest first; query searches prompt, model name (also the one shown in the app) and label. With favorites
     * only the entries with at least one favourite file
     */
    list(opts: { query?: string; offset?: number; limit?: number; favorites?: boolean }): Promise<HistoryPage>
    /** marks one file of an entry as a favourite (on) or takes the mark away */
    favorite(id: string, file: string, on: boolean): Promise<void>
    /** the files marked as favourites, newest first */
    favorites(): Promise<string[]>
    /** removes entries; with trashFiles their pictures go to the macOS trash */
    remove(ids: string[], trashFiles: boolean): Promise<void>
    onChange(fn: () => void): () => void
  }
  splash: {
    /** in the splash window: whether the main window has loaded */
    state(): Promise<{ ready: boolean }>
    /** in the splash window: close it and show the main window */
    confirm(): Promise<void>
    onReady(fn: () => void): () => void
  }
  viewer: {
    /** opens the large view in a window of its own */
    open(items: ViewerItem[], index: number): Promise<void>
    /** in a viewer window: what it was opened with */
    payload(): Promise<ViewerPayload | undefined>
    /** in a viewer window: hand something back to the main window */
    act(action: ViewerAction): Promise<void>
    onAction(fn: (action: ViewerAction) => void): () => void
  }
  licences: {
    /** the licence of an installed model or LoRA: read once from its origin and kept in its folder */
    get(id: string, refresh?: boolean): Promise<AssetLicence>
    /** names the page of a model whose origin is not known (Civitai or Hugging Face) and reads its licence there */
    setOrigin(id: string, link: string): Promise<AssetLicence>
  }
  loras: {
    details(id: string): Promise<LoraDetails>
    /** what the page of the LoRA says; read once and kept, refresh reads it again. undefined: its origin is not known */
    info(id: string, refresh?: boolean): Promise<LoraInfo | undefined>
    setTriggerWords(id: string, words: string[]): Promise<string[]>
    setCategory(id: string, category: string): Promise<void>
    /** LoRAs on Civitai or Hugging Face made for a base model; one page, the cursor asks for the next */
    search(request: LoraSearchRequest): Promise<LoraSearchPage>
    /** the preview picture of a search result as a data URL; undefined when it can not be shown */
    thumb(url: string): Promise<string | undefined>
  }
  training: {
    state(): Promise<TrainingState>
    start(request: TrainingRequest): Promise<void>
    stop(): Promise<void>
    choosePictures(): Promise<string[]>
    /** the pictures of a folder with the captions of .txt files next to them */
    chooseFolder(): Promise<TrainingImage[]>
    onChange(fn: (state: TrainingState) => void): () => void
  }
  restore: {
    /** the faces of a photo (Diffusers engine, the detector downloaded on first use) */
    faces(path: string): Promise<FoundFaces>
  }
  pose: {
    detect(path: string): Promise<DetectedPose>
    onProgress(fn: (stage: string, percent: number) => void): () => void
  }
  dialog: {
    /** a question with two answers on the window; true when the first (yes) was chosen */
    ask(message: string, yes: string, no: string, detail?: string): Promise<boolean>
  }
  files: {
    /** vk-file:// URL of a local file for <img> / <video> */
    url(path: string): string
    choose(kind: 'image' | 'folder' | 'model'): Promise<string | undefined>
    saveAs(path: string, suggestedName: string): Promise<boolean>
    reveal(path: string): Promise<void>
    /** macOS's share menu for a result (Mail, Messages, AirDrop, apps that offer themselves); false: not allowed */
    share(path: string): Promise<boolean>
    /** the picture on the clipboard; false for a video or a file the app may not hand out */
    copyImage(path: string): Promise<boolean>
    /** the path of a file dropped onto the page */
    pathOf(file: File): string
    /** stores a picture the page made (a mask, a drawing) as PNG and returns its path */
    writeImage(dataUrl: string): Promise<string>
    /** stores a skeleton of the pose editor as PNG (it counts as showing no person) and returns its path */
    writePose(dataUrl: string): Promise<string>
  }
  app: {
    /** mac: model, chip (where the name does not say it) and memory; os: e.g. "macOS 26.0" */
    info(): Promise<{ name: string; version: string; electron: string; platform: string; ramGb: number; mac: string; os: string }>
    openExternal(url: string): Promise<void>
    logs(): Promise<LogLine[]>
    onLog(fn: (line: LogLine) => void): () => void
    /** bytes of encoded prompts the engines keep on disk */
    promptCache(): Promise<number>
    clearPromptCache(): Promise<void>
    /** the app's update: last check and installation (no network) */
    update(): Promise<AppUpdateState>
    /** asks GitHub for the newest release */
    checkUpdate(): Promise<AppUpdateState>
    /** downloads and checks the newest release, then restarts into it */
    installUpdate(): Promise<void>
    onUpdate(fn: (s: AppUpdateState) => void): () => void
  }
  remote: {
    /** whether the remote web UI is serving, the addresses it can be reached at on this Mac, and whether over HTTPS */
    info(): Promise<{ running: boolean; addresses: string[]; https: boolean }>
  }
  report: {
    /** the kept session logs, newest first */
    sessions(): Promise<LogSession[]>
    /** one of them (by its id from sessions()), redacted */
    session(id: string): Promise<LogReport>
    /** opens the new-issue page of the app's GitHub repository in the browser */
    openIssue(): Promise<void>
  }
}
