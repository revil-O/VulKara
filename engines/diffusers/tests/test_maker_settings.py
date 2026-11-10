# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Oliver Schmidt
"""The settings a model's maker recommends, read from the model card."""
import json

import maker_settings as ms
import recheck

REALVIS = """<b>Recommended Negative Prompt:</b><br>
(octane render, render, drawing, anime, bad photo, bad photography:1.3), (worst quality, low quality, blurry:1.2), (bad teeth, deformed teeth, deformed lips), morbid<br>
<b>or another negative prompt</b><br>

<b>Recommended Generation Parameters:</b><br>
Sampling Steps: 5<br>
Sampling Method: DPM++ SDE Karras / DPM++ SDE<br>
CFG Scale: 1.0-2.0

<b>Recommended Hires Fix Parameters:</b><br>
Hires steps: 3<br>
Denoising strength: 0.5<br>"""


def test_realvisxl_lightning_card():
    s = ms.parse(REALVIS)
    assert s["num_steps"] == 5
    assert s["guidance_scale"] == 1.5
    assert s["sampler"] == "DPM++ SDE"
    assert s["sigma_schedule"] == "Karras"
    assert s["samplers"] == ["DPM++ SDE"]  # named twice, once each
    assert s["negative_prompt"].startswith("octane render, render, drawing, anime, bad photo, bad photography, worst quality")
    assert ":1.3" not in s["negative_prompt"] and "(" not in s["negative_prompt"]


def test_civitai_style_texts():
    s = ms.parse("<p>Steps: 4 (min) 6 (recommended), CFG 1.1, sampler: Euler a</p>")
    assert s == {"num_steps": 6, "guidance_scale": 1.1, "sampler": "Euler a", "samplers": ["Euler a"]}
    s = ms.parse("Use 4-8 steps with CFG scale 2 and DPM++ 2M SDE Karras as the sampler")
    assert s["num_steps"] == 6 and s["guidance_scale"] == 2.0
    s = ms.parse("Sampler: DPM++ 2M SDE Karras\nSteps: 30\nCFG: 5-7")
    assert s == {"num_steps": 30, "guidance_scale": 6.0, "sampler": "DPM++ 2M SDE", "sigma_schedule": "Karras", "samplers": ["DPM++ 2M SDE"]}


def test_nothing_clear_nothing_taken():
    assert ms.parse("A great model for portraits. Have fun!") == {}
    assert ms.parse("") == {}
    assert ms.parse("Steps: 900") == {}


def test_the_hires_part_does_not_count():
    s = ms.parse("Hires fix: steps 15, CFG 9")
    assert "num_steps" not in s and "guidance_scale" not in s


def test_apply_puts_them_over_the_guessed_defaults():
    m = {"defaults": {"num_steps": 4, "guidance_scale": 0, "width": 1024, "height": 1024}}
    ms.apply(m, {"num_steps": 5, "guidance_scale": 1.5, "sampler": "DPM++ SDE"}, "hf model card")
    assert m["defaults"] == {"num_steps": 5, "guidance_scale": 1.5, "width": 1024, "height": 1024, "sampler": "DPM++ SDE"}
    assert m["maker"]["source"] == "hf model card"
    assert ms.apply({"defaults": {"num_steps": 4}}, {}, "x") == {"defaults": {"num_steps": 4}}


def test_the_makers_own_choice_among_several():
    card = "Recommended Settings Steps: 25-30 (I use 30 normally)\nCFG: 3-5 ( I use 5 normally )\nSampler: Euler / Euler A (my go-to)\nScheduler: Normal or Simple"
    assert ms.parse(card) == {"num_steps": 30, "guidance_scale": 5.0, "sampler": "Euler a", "samplers": ["Euler", "Euler a"]}


def test_the_first_sampler_named_and_a_scheduler_line():
    assert ms.parse("Sampler: Euler a / DPM++ 2M + Karras\nSampling Steps: 25–45")["sampler"] == "Euler a"
    got = ms.parse("Sampler: dpmpp2msde\nScheduler: karras, exponential or beta\nSteps: 25-40\nCFG: 3.5-5.5")
    assert got == {"sampler": "DPM++ 2M SDE", "sigma_schedule": "Karras", "num_steps": 33, "guidance_scale": 4.5, "samplers": ["DPM++ 2M SDE"]}


def test_code_example_and_quoted_negative():
    card = 'Negative prompt: "worst quality, low quality"\n```py\nimage = pipe(prompt, num_inference_steps=50, guidance_scale=3.5).images[0]\n```'
    assert ms.parse(card) == {"negative_prompt": "worst quality, low quality", "num_steps": 50, "guidance_scale": 3.5}


def test_advice_after_negative_is_no_prompt():
    # Juggernaut XL's card (Civitai 133005), word for word: the maker says to start without one
    card = "Sampler: DPM++ 2M SDE\nSteps: 30-40\nNegative: Start with no negative, and add afterwards the Stuff you don´t wanna see in that image."
    assert "negative_prompt" not in ms.parse(card)
    assert "negative_prompt" not in ms.parse("Negative prompt: none")
    assert ms.parse("Negative: blurry, lowres, watermark")["negative_prompt"] == "blurry, lowres, watermark"
    # words of a real negative prompt are no advice
    for neg in ("bad hands, dont-care", "ugly, your face", "blurry, start with a frame", "none of the above, lowres"):
        assert not ms.is_advice(neg), neg
    assert ms.is_advice("None.") and ms.is_advice("Not needed") and ms.is_advice("I don't use one")


def test_recheck_waits_for_a_drive_that_is_not_connected(tmp_path):
    assert recheck.main(["--models", "/Volumes/vk-not-connected-drive/models", "--loras", str(tmp_path)]) == 3
    # a folder that is simply not there (no models yet) is nothing to wait for
    assert recheck.main(["--models", str(tmp_path / "none"), "--loras", str(tmp_path)]) == 0


def test_recheck_takes_advice_read_before_out_of_an_installed_model(tmp_path):
    advice = "Start with no negative, and add afterwards the Stuff you don\u00b4t wanna see in that image."
    folder = tmp_path / "models" / "juggernaut"
    folder.mkdir(parents=True)
    (folder / "model.json").write_text(json.dumps({
        "name": "Juggernaut-XL-v7", "maker": {"num_steps": 35, "negative_prompt": advice, "source": "civitai description"},
        "defaults": {"num_steps": 35, "guidance_scale": 4.5, "negative_prompt": advice}}))
    report = recheck.recheck(str(tmp_path / "models"), None, apply=True)
    assert [r["name"] for r in report] == ["Juggernaut-XL-v7"]
    m = json.loads((folder / "model.json").read_text())
    assert m["maker"] == {"num_steps": 35, "source": "civitai description"}
    assert m["defaults"] == {"num_steps": 35, "guidance_scale": 4.5}
    assert (folder / "model.json.bak").exists()
    assert recheck.recheck(str(tmp_path / "models"), None) == []  # once only
    # a real negative prompt stays
    assert recheck.model_changes(str(folder), {"maker": {"negative_prompt": "blurry, lowres"}}) == {}


def test_the_samplers_the_maker_names_become_the_allow_list():
    # the whole line the maker names, so the picker can be held to them; the preferred one stays the default
    assert ms.parse("Sampler: DPM++ 2M, DPM++ 2M SDE or UniPC")["samplers"] == ["DPM++ 2M", "DPM++ 2M SDE", "UniPC"]
    assert "samplers" not in ms.parse("Steps: 20, CFG 7")  # no sampler named, no restriction


def test_apply_keeps_the_allow_list_out_of_the_scalar_defaults():
    m = {"defaults": {"num_steps": 4}}
    ms.apply(m, {"num_steps": 5, "sampler": "DPM++ 2M", "samplers": ["DPM++ 2M", "UniPC"]}, "card")
    assert m["samplers"] == ["DPM++ 2M", "UniPC"]
    assert "samplers" not in m["defaults"] and "samplers" not in m["maker"]
    assert m["defaults"] == {"num_steps": 5, "sampler": "DPM++ 2M"}


def test_no_schedule_for_samplers_that_take_none_and_the_sweet_spot():
    assert ms.parse("Sampler: LCM\nScheduler: karras, exponential or beta") == {"sampler": "LCM", "samplers": ["LCM"]}
    assert ms.parse("Works best at minimum at 20 steps, the sweet spot is between 25-50.")["num_steps"] == 38


def test_a_number_no_card_means_is_left_out_and_the_sane_one_kept():
    # a card may hold anything; each pattern that finds an impossible value falls through to the next
    assert ms.parse("Steps: 20 (I use 99999999)") == {"num_steps": 20}
    assert ms.parse("CFG scale: 7 (I use 1000000)") == {"guidance_scale": 7.0}
    assert ms.parse("the sweet spot is between 100000-200000 steps") == {}
    assert ms.parse("Steps: " + "9" * 400) == {}  # had crashed the import with NaN


def test_a_card_longer_than_a_card_is_cut():
    assert ms.parse("x" * 300_000 + "\nSteps: 28") == {}


def test_the_hires_part_is_cut_only_where_it_begins_a_line():
    card = "Great for upscaling portraits.\nSteps: 28, CFG 4\nHires fix\nSteps: 60"
    assert ms.parse(card) == {"num_steps": 28, "guidance_scale": 4.0}
