# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Folders of the engines. The app passes them in the environment (VK_*); the defaults below apply when an
engine runs on its own (development, tests)."""
import os
from pathlib import Path

HOME = Path.home()
DATA_DIR = Path(os.environ.get("VK_DATA_DIR") or HOME / "Library" / "Application Support" / "VulKara")


def models_dir():
    return Path(os.environ.get("VK_MODELS_DIR") or HOME / "VulKara" / "models")


def images_dir():
    return Path(os.environ.get("VK_IMAGES_DIR") or HOME / "VulKara" / "images")


def loras_dir():
    return Path(os.environ.get("VK_LORAS_DIR") or models_dir().parent / "loras")


def helpers_dir(name):
    """Helper models (ControlNets, annotators, content filter): next to the models, they are large too."""
    d = Path(os.environ.get("VK_HELPERS_DIR") or models_dir().parent) / name
    if d.is_symlink() and not d.exists():  # mkdir would only say "File exists"
        raise FileNotFoundError("%s is a link to %s, which does not exist: remove the link or bring the folder back"
                                % (d, os.readlink(d)))
    d.mkdir(parents=True, exist_ok=True)
    return d
