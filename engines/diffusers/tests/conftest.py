# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
import os
import sys

# optimum-quanto compiles its kernels with ninja from the venv on first use
os.environ["PATH"] = os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import compat  # noqa: E402

compat.install()

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _apple_chip_packages(request, monkeypatch):
    """The engine's logic is tested as the Apple-chip build has it (quanto plans, its own test pickles read) also on
    the Intel build's older packages; test_compat checks what compat.py changes there."""
    if request.module.__name__ != "test_compat":
        monkeypatch.setattr(compat, "QUANTO", True)
        monkeypatch.setattr(compat, "pickle_safe", lambda: True)
        monkeypatch.setattr(compat, "cpu_only", lambda: False)
        monkeypatch.setattr(compat, "old_torch", lambda: False)


@pytest.fixture(autouse=True)
def _install_room(monkeypatch):
    """The tests' imports do not depend on the free space of the disk they run on (test_importer checks the rule)."""
    import importer
    monkeypatch.setattr(importer, "MIN_INSTALL_FREE_GB", 0.0)


@pytest.fixture(autouse=True)
def _no_prompt_cache(monkeypatch):
    """Engine tests encode for real: their embeddings stay out of the user's data folder (test_prompt_cache sets it)."""
    monkeypatch.setenv("VK_PROMPT_CACHE_GB", "0")
