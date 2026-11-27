// SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
// Copyright (C) 2026 Oliver Schmidt
// English, the source of the texts. One file per part of the app; a new text goes into en first, then into de, es
// and pt (typecheck finds what is missing there).
import common from './common'
import nav from './nav'
import jobs from './jobs'
import generate from './generate'
import canvas from './canvas'
import edit from './edit'
import restore from './restore'
import scans from './scans'
import pose from './pose'
import lora from './lora'
import training from './training'
import models from './models'
import library from './library'
import viewer from './viewer'
import settings from './settings'
import hardware from './hardware'
import app from './app'
import tips from './tips'
import mainProcess from './main'
import engine from './engine'

export const en = { common, nav, jobs, generate, canvas, edit, restore, scans, pose, lora, training, models, library, viewer, settings, hardware, app, tips, main: mainProcess, engine } as const
