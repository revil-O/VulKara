// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
import { describe, expect, it } from 'vitest'
import { ConsentRequired, JobQueue, type QueueEvent } from './queue'
import type { Job } from '@shared/types'

const JOB: Omit<Job, 'id'> = {
  page: 'text', prompt: 'a lighthouse at dusk', modelId: 'm', modelDir: '/models/m', width: 512, height: 512, seed: 7, steps: 10,
}

function setup(verdict: { ok: boolean; reason?: string } = { ok: true }) {
  const sent: { job: Record<string, unknown>; emit: (e: QueueEvent) => void }[] = []
  const stopped: string[] = []
  let time = 0
  let failDispatch = ''
  const queue = new JobQueue<string>({
    dispatch(job, listener) {
      if (failDispatch) throw new Error(failDispatch)
      sent.push({ job, emit: listener })
      return 'diffusers'
    },
    stop: (engine) => { stopped.push(engine) },
    check: async () => verdict,
    now: () => time,
    changed: () => {},
  })
  const settle = (): Promise<void> => new Promise((r) => setTimeout(r, 0))
  return { queue, sent, stopped, settle, tick: (ms: number) => { time += ms }, failNext: (m: string) => { failDispatch = m } }
}

describe('job queue', () => {
  it('runs the jobs one after the other with seeds counting up', async () => {
    const { queue, sent, settle } = setup()
    const ids = queue.add(JOB, 3)
    expect(ids).toHaveLength(3)
    expect(sent).toHaveLength(1)
    expect(queue.snapshot().map((j) => j.state)).toEqual(['running', 'waiting', 'waiting'])
    expect(queue.snapshot().map((j) => j.job.seed)).toEqual([7, 8, 9])
    sent[0].emit({ event: 'result', path: '/images/a.png' })
    sent[0].emit({ event: 'state', state: 'idle' })
    await settle()
    expect(queue.snapshot()[0]).toMatchObject({ state: 'done', results: ['/images/a.png'] })
    expect(sent).toHaveLength(2)
    expect(sent[1].job.seed).toBe(8)
  })

  it('keeps a note on how the job was made, and a new job starts without one', async () => {
    const { queue, sent, settle } = setup()
    queue.add(JOB)
    sent[0].emit({ event: 'note', message: 'Made with Diffusers instead of MLX' })
    sent[0].emit({ event: 'result', path: '/images/a.png' })
    sent[0].emit({ event: 'state', state: 'idle' })
    await settle()
    const done = queue.snapshot()[0]
    expect(done.job.note).toBe('Made with Diffusers instead of MLX')
    queue.add(done.job)  // "Use these settings" hands the old job back
    expect(queue.snapshot()[1].job.note).toBeUndefined()
  })

  it('sends the engine field names', () => {
    const { queue, sent } = setup()
    queue.add({ ...JOB, negativePrompt: 'blurry', guidance: 6 })
    expect(sent[0].job).toMatchObject({ model_dir: '/models/m', num_steps: 10, guidance_scale: 6, negative_prompt: 'blurry', count: 1 })
  })

  it('sends what extending a picture needs', () => {
    const { queue, sent } = setup()
    queue.add({ ...JOB, inputImage: '/in.png', maskImage: '/mask.png', strength: 1, exactSize: true, prefill: true })
    expect(sent[0].job).toMatchObject({ input_image: '/in.png', mask_image: '/mask.png', inpaint_strength: 1, exact_size: true, prefill: true })
  })

  it('refuses prohibited prompts and asks for consent', () => {
    const { queue, sent } = setup()
    expect(() => queue.add({ ...JOB, prompt: 'nude 12 year old girl' })).toThrow()
    expect(() => queue.add({ ...JOB, prompt: 'nude woman', inputImage: '/in.png' })).toThrow(ConsentRequired)
    expect(sent).toHaveLength(0)
    queue.add({ ...JOB, prompt: 'nude woman', inputImage: '/in.png', consent: true })
    expect(sent).toHaveLength(1)
  })

  it('does not ask for consent for a skeleton of the pose editor, but for a photo', () => {
    const sent: unknown[] = []
    const queue = new JobQueue<string>({
      dispatch: (job) => { sent.push(job); return 'diffusers' },
      stop: () => {},
      check: async () => ({ ok: true }),
      generated: (p) => p.startsWith('/data/inputs/poses/'),
      now: () => 0,
      changed: () => {},
    })
    queue.add({ ...JOB, prompt: 'nude woman on a beach', controlnet: { type: 'BodyPose', image: '/data/inputs/poses/a.png', weight: 1, preprocess: false } })
    expect(sent).toHaveLength(1)
    expect(() => queue.add({ ...JOB, prompt: 'nude woman', controlnet: { type: 'BodyPose', image: '/photos/me.jpg', weight: 1, preprocess: true } })).toThrow(ConsentRequired)
    expect(() => queue.add({ ...JOB, prompt: 'nude woman', inputImage: '/data/inputs/poses/a.png', restore: { correct: true, repair: false, colorize: false, colorStrength: 1, sharpen: false, sharpness: 0.25, lock: true, maxChange: 0.06, rules: [], checkFaces: true } })).toThrow(ConsentRequired)
  })

  it('does not show a result the content filter blocked', async () => {
    const { queue, sent, settle } = setup({ ok: false, reason: 'blocked' })
    queue.add(JOB)
    sent[0].emit({ event: 'result', path: '/images/a.png' })
    sent[0].emit({ event: 'state', state: 'idle' })
    await settle()
    expect(queue.snapshot()[0]).toMatchObject({ state: 'failed', results: [], error: 'blocked' })
  })

  it('removes a waiting job and stops the running one', async () => {
    const { queue, sent, stopped, settle } = setup()
    const [first, second] = queue.add(JOB, 2)
    queue.cancel(second)
    expect(queue.snapshot()).toHaveLength(1)
    queue.cancel(first)
    expect(stopped).toEqual(['diffusers'])
    sent[0].emit({ event: 'state', state: 'idle' })
    await settle()
    expect(queue.snapshot()[0].state).toBe('cancelled')
    queue.cancel(first)
    expect(queue.snapshot()).toHaveLength(0)
  })

  it('fails a job whose engine can not start or stops, and goes on', async () => {
    const { queue, sent, settle, failNext } = setup()
    failNext('not installed')
    queue.add(JOB)
    expect(queue.snapshot()[0]).toMatchObject({ state: 'failed', error: 'not installed' })
    failNext('')
    queue.add(JOB, 2)
    sent[0].emit({ event: 'exit', message: 'The engine stopped: out of memory' })
    await settle()
    expect(queue.snapshot()[1]).toMatchObject({ state: 'failed', error: 'The engine stopped: out of memory' })
    expect(queue.snapshot()[2].state).toBe('running')
  })

  it('estimates the time left from the progress', () => {
    const { queue, sent, tick } = setup()
    queue.add(JOB)
    sent[0].emit({ event: 'progress', value: 10 })
    tick(4000)
    sent[0].emit({ event: 'progress', value: 30 })
    expect(queue.snapshot()[0]).toMatchObject({ progress: 30, eta: 14, secondsPerStep: 2 })
  })

  it('ignores late events of a finished job', async () => {
    const { queue, sent, settle } = setup()
    queue.add(JOB, 2)
    sent[0].emit({ event: 'error', message: 'boom' })
    sent[0].emit({ event: 'state', state: 'idle' })
    await settle()
    sent[0].emit({ event: 'state', state: 'idle' })
    await settle()
    expect(queue.snapshot().map((j) => j.state)).toEqual(['failed', 'running'])
  })

  it('removes a result the content filter did not pass from the disk, also when the filter fails', async () => {
    const discarded: string[] = []
    for (const check of [async () => ({ ok: false, reason: 'blocked' }), async () => { throw new Error('no runtime') }]) {
      let emit: (e: QueueEvent) => void = () => {}
      const queue = new JobQueue<string>({
        dispatch: (_job, listener) => { emit = listener; return 'mlx' },
        stop: () => {}, check, now: () => 0, changed: () => {}, discard: (p) => discarded.push(p),
      })
      queue.add(JOB)
      emit({ event: 'result', path: '/images/x.png' })
      emit({ event: 'state', state: 'idle' })
      await new Promise((r) => setTimeout(r, 0))
      expect(queue.snapshot()[0]).toMatchObject({ state: 'failed', results: [] })
    }
    expect(discarded).toEqual(['/images/x.png', '/images/x.png'])
  })

  it('hands the run time and seconds per step of a finished job to the history', async () => {
    let time = 0
    const sent: ((e: QueueEvent) => void)[] = []
    const timings: unknown[] = []
    const queue = new JobQueue<string>({
      dispatch: (_job, listener) => { sent.push(listener); return 'diffusers' },
      stop: () => {}, check: async () => ({ ok: true }), now: () => time, changed: () => {},
      finished: (_job, _results, timing) => { timings.push(timing) },
    })
    queue.add(JOB)
    time = 3000
    sent[0]({ event: 'progress', value: 10 })
    time = 7000
    sent[0]({ event: 'progress', value: 30 })
    time = 12345
    sent[0]({ event: 'result', path: '/images/a.png' })
    sent[0]({ event: 'state', state: 'idle' })
    await new Promise((r) => setTimeout(r, 0))
    expect(timings).toEqual([{ seconds: 12.3, secondsPerStep: 2 }])
  })

  it('goes on with the next job when the finished one can not be saved', async () => {
    const sent: ((e: QueueEvent) => void)[] = []
    const logged: string[] = []
    const queue = new JobQueue<string>({
      dispatch: (_job, listener) => { sent.push(listener); return 'diffusers' },
      stop: () => {}, check: async () => ({ ok: true }), now: () => 0, changed: () => {},
      finished: () => { throw new Error('disk full') }, log: (l) => logged.push(l),
    })
    queue.add(JOB, 2)
    sent[0]({ event: 'result', path: '/images/a.png' })
    sent[0]({ event: 'state', state: 'idle' })
    await new Promise((r) => setTimeout(r, 0))
    expect(sent).toHaveLength(2)
    expect(logged[0]).toContain('disk full')
  })

  it('checks the restore rules with the prompt and asks for consent with a pose or restore picture', () => {
    const { queue } = setup()
    const restore = { correct: true, repair: true, colorize: false, colorStrength: 1, sharpen: false, sharpness: 0, lock: true, maxChange: 0.1, checkFaces: true }
    expect(() => queue.add({ ...JOB, prompt: '', restore: { ...restore, rules: ['a nude 12 year old'] } })).toThrow(/minor/)
    expect(() => queue.add({ ...JOB, prompt: '', restore: { ...restore, rules: ['make her nude'] } })).toThrow(ConsentRequired)
    expect(() => queue.add({ ...JOB, prompt: 'nude', controlnet: { type: 'pose', image: '/in/p.png', weight: 1, preprocess: true } })).toThrow(ConsentRequired)
  })

  it('turns a seed that is not a number into a random one and an empty LoRA weight into 0', () => {
    const { queue, sent } = setup()
    queue.add({ ...JOB, seed: Infinity, loras: [{ path: '/loras/a', scale: '' as unknown as number }] })
    expect(Number.isFinite(sent[0].job.seed)).toBe(true)
    expect(queue.snapshot()[0].job.loras?.[0].scale).toBe(0)
  })

  it('keeps every note of a job, each once', async () => {
    const { queue, sent, settle } = setup()
    queue.add(JOB)
    sent[0].emit({ event: 'note', message: 'Made with Diffusers instead of MLX' })
    sent[0].emit({ event: 'note', message: 'Step caching: 5 of 28 runs reused' })
    sent[0].emit({ event: 'note', message: 'Step caching: 5 of 28 runs reused' })
    sent[0].emit({ event: 'result', path: '/images/a.png' })
    sent[0].emit({ event: 'state', state: 'idle' })
    await settle()
    expect(queue.snapshot()[0].job.note).toBe('Made with Diffusers instead of MLX\nStep caching: 5 of 28 runs reused')
  })

  it('asks the content filter to write the AI label only for jobs that want it', async () => {
    const labels: unknown[] = []
    let emit: (e: QueueEvent) => void = () => {}
    const queue = new JobQueue<string>({
      dispatch: (_job, listener) => { emit = listener; return 'diffusers' },
      stop: () => {}, check: async (_p, _m, label) => { labels.push(label); return { ok: true } }, now: () => 0, changed: () => {},
    })
    queue.add({ ...JOB, aiLabel: { size: 'large', kind: 'generated', tone: 'auto' } })
    emit({ event: 'result', path: '/images/a.png' })
    emit({ event: 'state', state: 'idle' })
    await new Promise((r) => setTimeout(r, 0))
    queue.add(JOB)
    emit({ event: 'result', path: '/images/b.png' })
    emit({ event: 'state', state: 'idle' })
    await new Promise((r) => setTimeout(r, 0))
    expect(labels).toEqual([{ size: 'large', kind: 'generated', tone: 'auto' }, undefined])
  })
})
