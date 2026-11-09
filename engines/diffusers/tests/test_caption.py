# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""Prompt from a picture: Qwen3-VL 2B is a pinned helper, its text ends on a whole sentence, and main.py caption_image
answers in one tagged line (MEASUREMENTS 7br)."""
import json

import caption
import helpers
import pinned


def test_qwen3_vl_is_a_pinned_helper():
    h = next(x for x in helpers.catalog() if x["id"] == caption.HELPER)
    revision, files = pinned.pins(h["repo"])
    assert h["group"] == "Prompt" and h["repo"] == "Qwen/Qwen3-VL-2B-Instruct" and len(revision) == 40
    assert len(files["model.safetensors"]) == 64 and "chat_template.json" in files and "preprocessor_config.json" in files


def test_a_text_cut_by_the_token_limit_ends_on_its_last_whole_sentence():
    assert caption.whole_sentences(" A fox. It sits on the lawn ", ended=False) == "A fox."
    assert caption.whole_sentences("A fox in 3.5 light. Soft", ended=False) == "A fox in 3.5 light."
    assert caption.whole_sentences("A fox. It sits", ended=True) == "A fox. It sits"
    assert caption.whole_sentences("no sentence end", ended=False) == "no sentence end"


def test_the_question_asks_for_one_prompt_paragraph_with_the_picture():
    [m] = caption.messages("picture")
    assert m["role"] == "user" and m["content"][0] == {"type": "image", "image": "picture"}
    assert "prompt" in m["content"][1]["text"] and "Only the paragraph" in m["content"][1]["text"]


def test_main_answers_with_the_caption_or_the_error(monkeypatch, capsys):
    monkeypatch.setattr(caption, "describe", lambda path, report: report("Describing the picture", -1) or "A fox.")
    assert caption.main(["/x.png"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == '__progress__ {"stage": "Describing the picture", "progress": -1}'
    assert json.loads(lines[1].split(" ", 1)[1]) == {"text": "A fox."}

    def broken(path, report):
        raise OSError("no picture")
    monkeypatch.setattr(caption, "describe", broken)
    assert caption.main(["/x.png"]) == 1
    assert json.loads(capsys.readouterr().out.split(" ", 1)[1]) == {"error": "no picture"}


def test_a_download_stopped_after_the_weights_is_finished_on_the_next_try(tmp_path, monkeypatch):
    import restore
    monkeypatch.setattr(restore, "helper_folder", lambda helper: str(tmp_path))
    installs = []
    monkeypatch.setattr(helpers, "install", lambda helper, report=None: installs.append(helper))
    (tmp_path / "model.safetensors").write_bytes(b"x")  # the weights came, the processor files did not
    caption.folder()
    assert installs == [caption.HELPER]
    h = next(x for x in helpers.catalog() if x["id"] == caption.HELPER)
    (tmp_path / pinned.MARK).write_text(json.dumps({"repo": h["repo"], "revision": pinned.pins(h["repo"])[0]}))
    caption.folder()  # complete: not fetched again
    assert installs == [caption.HELPER]
