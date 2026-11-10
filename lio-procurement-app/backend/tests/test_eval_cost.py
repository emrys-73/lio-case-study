import json

import pytest

from evals.cost.engine import (
    PRICES,
    SCENARIOS,
    apply_op,
    bill_cost,
    bill_from_run,
    call_cost,
    image_tokens,
    measured_run,
    price_scenario,
)

MINI = "gpt-4o-mini-2024-07-18"
A4_150DPI = (1240, 1754)
A4_TOKENS_MINI = 2833 + 6 * 5667


def test_a_million_input_tokens_cost_the_list_price():
    assert call_cost(MINI, 1_000_000, 0) == pytest.approx(0.15)


def test_output_tokens_use_the_output_price():
    assert call_cost(MINI, 0, 1_000_000) == pytest.approx(0.60)


def test_cached_tokens_are_billed_at_the_cached_price():
    assert call_cost(MINI, 1_000_000, 0, cached=1_000_000) == pytest.approx(0.075)


def test_an_a4_page_on_4o_mini_is_six_tiles():
    assert image_tokens(MINI, *A4_150DPI) == A4_TOKENS_MINI


def test_low_detail_costs_only_the_base_tokens():
    assert image_tokens(MINI, *A4_150DPI, detail="low") == 2833


def test_patch_models_count_32px_patches_times_the_multiplier():
    assert image_tokens("gpt-4.1-mini-2025-04-14", *A4_150DPI) == 3475


def test_a_big_page_is_scaled_into_the_patch_budget():
    tokens = image_tokens("gpt-5.4-mini", 2480, 3508)
    assert 2000 * 1.2 < tokens <= 2500 * 1.2


def _row(case, prompt, completion, vat="DE1", sums=True, calls=1, pictures=False, seconds=5.0, model_seconds=3.0):
    return {
        "case": case,
        "seconds": seconds,
        "model": {"promptTokens": prompt, "completionTokens": completion, "calls": calls, "seconds": model_seconds},
        "app": {"data": {"vatId": vat, "vendorName": "V"}, "reading": {"pageImagesSent": pictures}},
        "score": {"arithmetic": {"linesSumToTotal": sums}},
    }


def _write_run(tmp_path, rows, fully_correct=0, model=MINI):
    run = tmp_path / "20261110-000000_test"
    run.mkdir()
    (run / "runs.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    (run / "summary.json").write_text(json.dumps({
        "meta": {"model": model},
        "overall": {"runs": len(rows), "fullyCorrect": fully_correct, "crashes": 0},
    }))
    return run


def test_a_run_gives_average_tokens_calls_and_quality(tmp_path):
    run = _write_run(tmp_path, [_row("a", 100, 10), _row("b", 300, 30, calls=2, pictures=True)], fully_correct=1)
    m = measured_run(run)
    assert m["input"] == 200
    assert m["output"] == 20
    assert m["calls"] == 1.5
    assert m["pictureFires"] == 0.5
    assert m["fullyRight"] == 1
    assert m["runs"] == 2
    assert m["model"] == MINI


def test_time_outside_the_model_is_reading_time(tmp_path):
    m = measured_run(_write_run(tmp_path, [_row("a", 1, 1, seconds=9.0, model_seconds=3.0)]))
    assert m["seconds"] == 9.0
    assert m["readingSeconds"] == 6.0


def test_a_run_counts_how_often_the_code_checks_fail(tmp_path):
    rows = [_row("a", 1, 1), _row("b", 1, 1, vat=None), _row("c", 1, 1, sums=False), _row("d", 1, 1)]
    assert measured_run(_write_run(tmp_path, rows))["checksFail"] == 0.5


def test_picture_tokens_are_split_out_of_a_measured_run(tmp_path):
    pages = SCENARIOS["constants"]["pagesPerPictureCall"]
    rows = [_row("a", 1000, 0), _row("b", 2000 + pages * A4_TOKENS_MINI, 0, calls=2, pictures=True)]
    bill = bill_from_run(measured_run(_write_run(tmp_path, rows)))
    assert bill["pictures"] == pytest.approx(0.5 * pages)
    assert bill["text"] == pytest.approx(1500)


def _bill(**kw):
    bill = {"model": MINI, "text": 0, "cached": 0, "pictures": 0, "output": 0, "calls": 1, "extra": [],
            "readingSeconds": 0, "seconds": None}
    bill.update(kw)
    return bill


def test_a_bill_prices_text_pictures_and_output():
    bill = _bill(text=1_000_000, pictures=2, output=1_000_000)
    assert bill_cost(bill) == pytest.approx(0.15 + 0.60 + 2 * A4_TOKENS_MINI * 0.15 / 1_000_000)


def test_dropping_the_group_list_removes_it_from_every_call():
    group = SCENARIOS["constants"]["groupListTokens"]
    bill = apply_op(_bill(text=3 * group, calls=1.5), {"op": "dropGroupList"})
    assert bill["text"] == pytest.approx(1.5 * group)


def test_caching_the_group_list_bills_it_at_the_cached_price():
    group = SCENARIOS["constants"]["groupListTokens"]
    bill = apply_op(_bill(text=group), {"op": "cacheGroupList"})
    assert bill_cost(bill) == pytest.approx(group * 0.075 / 1_000_000)


def test_skipping_pictures_removes_the_picture_call():
    pages = SCENARIOS["constants"]["pagesPerPictureCall"]
    bill = apply_op(_bill(text=1200, pictures=0.2 * pages, calls=1.2, output=120), {"op": "skipPictures"})
    assert bill["pictures"] == 0
    assert bill["calls"] == pytest.approx(1.0)
    assert bill["text"] == pytest.approx(1000)
    assert bill["output"] == pytest.approx(100)


def test_pictures_can_go_to_another_model_in_a_small_call():
    pages = SCENARIOS["constants"]["pagesPerPictureCall"]
    op = {"op": "picturesTo", "model": "gpt-4.1-mini-2025-04-14", "input": 300, "output": 50}
    bill = apply_op(_bill(text=1200, pictures=0.2 * pages, calls=1.2, output=120), op)
    assert bill["pictures"] == 0
    [call] = bill["extra"]
    assert call["fires"] == pytest.approx(0.2)
    assert call["pages"] == pages


def test_a_model_swap_reprices_everything():
    bill = apply_op(_bill(text=1_000_000), {"op": "model", "to": "gpt-4.1"})
    assert bill_cost(bill) == pytest.approx(2.00)


def test_an_extra_call_that_fires_on_a_fifth_of_quotes_costs_a_fifth():
    call = {"model": MINI, "input": 1_000_000, "output": 0}
    always = apply_op(_bill(), {"op": "addCall", "call": call})
    sometimes = apply_op(_bill(), {"op": "addCall", "call": {**call, "fires": 0.2}})
    assert bill_cost(sometimes) == pytest.approx(bill_cost(always) * 0.2)


def test_every_price_names_its_source_and_the_day_it_was_checked():
    for model, p in PRICES["models"].items():
        assert p["source"] in PRICES["sources"], model
        assert p["checked"], model


def test_every_scenario_prices_without_error():
    for s in SCENARIOS["scenarios"]:
        priced = price_scenario(s)
        assert priced["perQuote"] >= 0, s["id"]
        assert s["evidence"] in {"measured", "estimated"}, s["id"]


def test_measured_scenarios_change_nothing():
    for s in SCENARIOS["scenarios"]:
        if s["evidence"] == "measured":
            assert not s.get("ops"), s["id"]
            assert "run" in s["from"], s["id"]
