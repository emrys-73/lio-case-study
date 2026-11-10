from __future__ import annotations

import copy
import json
import math
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).parent
RESULTS = HERE.parent / "extraction" / "results"
PRICES = json.loads((HERE / "prices.json").read_text())
SCENARIOS = json.loads((HERE / "scenarios.json").read_text())
MILLION = 1_000_000


def _const(name: str):
    return SCENARIOS["constants"][name]


def call_cost(model: str, input_tokens: float, output_tokens: float, cached: float = 0) -> float:
    p = PRICES["models"][model]
    cached = min(cached, input_tokens)
    return (
        (input_tokens - cached) * p["input"]
        + cached * p["cachedInput"]
        + output_tokens * p["output"]
    ) / MILLION


def _fit(width: float, height: float, max_dim: float) -> tuple[float, float]:
    scale = min(1.0, max_dim / max(width, height))
    return width * scale, height * scale


def _patches(width: float, height: float) -> int:
    return math.ceil(width / 32) * math.ceil(height / 32)


def image_tokens(model: str, width: int, height: int, detail: str = "high") -> int:
    rule = PRICES["models"][model]["image"]
    if rule["method"] == "tile":
        if detail == "low":
            return rule["base"]
        w, h = _fit(width, height, 2048)
        short = min(w, h)
        if short > 768:
            w, h = w * 768 / short, h * 768 / short
        return rule["base"] + rule["tile"] * math.ceil(w / 512) * math.ceil(h / 512)
    w, h = _fit(width, height, rule["maxDim"])
    while _patches(w, h) > rule["patchBudget"]:
        shrink = math.sqrt(rule["patchBudget"] / _patches(w, h)) * 0.999
        w, h = math.floor(w * shrink), math.floor(h * shrink)
    return math.ceil(_patches(w, h) * rule["multiplier"])


def page_tokens(model: str) -> int:
    return image_tokens(model, *_const("pagePixels"))


def _checks_fail(row: dict) -> bool:
    data = (row.get("app") or {}).get("data") or {}
    sums = ((row.get("score") or {}).get("arithmetic") or {}).get("linesSumToTotal")
    return not data.get("vatId") or not data.get("vendorName") or not sums


def _mean(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


@lru_cache(maxsize=None)
def _measured(path: str) -> dict:
    run = Path(path)
    rows = [json.loads(line) for line in (run / "runs.jsonl").read_text().splitlines() if line.strip()]
    summary = json.loads((run / "summary.json").read_text())
    n = len(rows)
    total = _mean([r.get("seconds") for r in rows])
    model_s = _mean([r["model"].get("seconds") for r in rows])
    return {
        "label": run.name,
        "model": summary.get("meta", {}).get("model"),
        "runs": n,
        "input": sum(r["model"]["promptTokens"] for r in rows) / n,
        "output": sum(r["model"]["completionTokens"] for r in rows) / n,
        "calls": sum(r["model"].get("calls", 1) for r in rows) / n,
        "pictureFires": sum(bool(((r.get("app") or {}).get("reading") or {}).get("pageImagesSent")) for r in rows) / n,
        "seconds": total,
        "readingSeconds": max(0.0, total - model_s) if total is not None and model_s is not None else 0.0,
        "fullyRight": summary["overall"]["fullyCorrect"],
        "crashes": summary["overall"].get("crashes", 0),
        "checksFail": sum(_checks_fail(r) for r in rows) / n,
    }


def measured_run(path: Path | str) -> dict:
    return _measured(str(path))


def _run(key: str) -> dict:
    return measured_run(RESULTS / SCENARIOS["runs"][key])


def bill_from_run(m: dict) -> dict:
    pictures = m["pictureFires"] * _const("pagesPerPictureCall")
    return {
        "model": m["model"],
        "text": m["input"] - pictures * page_tokens(m["model"]),
        "cached": 0,
        "pictures": pictures,
        "output": m["output"],
        "calls": m["calls"],
        "extra": [],
        "readingSeconds": m["readingSeconds"],
        "seconds": m["seconds"],
    }


def _value(spec) -> float:
    if isinstance(spec, (int, float)):
        return spec
    if "const" in spec:
        return _const(spec["const"])
    return _run(spec["run"])[spec["metric"]]


def _picture_calls(bill: dict) -> float:
    return bill["pictures"] / _const("pagesPerPictureCall")


def _drop_picture_call(bill: dict) -> float:
    fires = _picture_calls(bill)
    if fires:
        share = fires / bill["calls"]
        bill["text"] -= bill["text"] * share
        bill["output"] -= bill["output"] * share
        bill["calls"] -= fires
        bill["pictures"] = 0
    return fires


def apply_op(bill: dict, op: dict) -> dict:
    bill = copy.deepcopy(bill)
    kind = op["op"]
    if kind == "dropGroupList":
        bill["text"] -= _const("groupListTokens") * bill["calls"]
    elif kind == "cacheGroupList":
        bill["cached"] = _const("groupListTokens") * bill["calls"]
    elif kind == "skipPictures":
        _drop_picture_call(bill)
    elif kind == "picturesTo":
        fires = _drop_picture_call(bill)
        bill["extra"].append({"model": op["model"], "input": op["input"], "output": op["output"],
                              "pages": _const("pagesPerPictureCall"), "fires": fires,
                              "label": "picture call"})
    elif kind == "picturesEveryPage":
        _drop_picture_call(bill)
        bill["pictures"] = _const("pagesPerQuote")
    elif kind == "model":
        bill["model"] = op["to"]
    elif kind == "escalate":
        bill["extra"].append({"model": op["model"], "input": bill["text"] / bill["calls"],
                              "output": bill["output"] / bill["calls"], "fires": _value(op["fires"]),
                              "label": "second try when checks fail"})
    elif kind == "addCall":
        call = dict(op["call"])
        call["fires"] = _value(call.get("fires", 1.0))
        bill["extra"].append(call)
    else:
        raise ValueError(f"unknown op {kind}")
    return bill


def _extra_cost(call: dict) -> float:
    pictures = call.get("pages", 0) * page_tokens(call["model"]) if call.get("pages") else 0
    return call.get("fires", 1.0) * call_cost(call["model"], call["input"] + pictures, call["output"])


def bill_cost(bill: dict) -> float:
    pictures = bill["pictures"] * page_tokens(bill["model"]) if bill["pictures"] else 0
    main = call_cost(bill["model"], bill["text"] + pictures, bill["output"], bill["cached"])
    return main + sum(_extra_cost(c) for c in bill["extra"])


def bill_tokens(bill: dict) -> float:
    pictures = bill["pictures"] * page_tokens(bill["model"]) if bill["pictures"] else 0
    extra = 0.0
    for c in bill["extra"]:
        pages = c.get("pages", 0) * page_tokens(c["model"]) if c.get("pages") else 0
        extra += c.get("fires", 1.0) * (c["input"] + pages)
    return bill["text"] + pictures + extra


def _by_id(scenario_id: str) -> dict:
    return next(s for s in SCENARIOS["scenarios"] if s["id"] == scenario_id)


def scenario_bill(scenario: dict) -> dict:
    source = scenario["from"]
    bill = bill_from_run(_run(source["run"])) if "run" in source else scenario_bill(_by_id(source["scenario"]))
    for op in scenario.get("ops", []):
        bill = apply_op(bill, op)
    return bill


def price_scenario(scenario: dict) -> dict:
    bill = scenario_bill(scenario)
    per_quote = bill_cost(bill)
    out = {
        "id": scenario["id"],
        "name": scenario["name"],
        "group": scenario["group"],
        "status": scenario.get("status"),
        "evidence": scenario["evidence"],
        "from": scenario["from"],
        "ops": [o["op"] for o in scenario.get("ops", [])],
        "result": scenario.get("result"),
        "proveWith": scenario.get("proveWith"),
        "perQuote": per_quote,
        "perMonth": per_quote * _const("quotesPerMonth"),
        "inputTokens": round(bill_tokens(bill)),
        "model": bill["model"],
        "pictureCalls": round(_picture_calls(bill), 2),
        "readingSeconds": round(bill["readingSeconds"], 1),
        "bill": bill,
    }
    if "run" in scenario["from"] and not scenario.get("ops"):
        m = _run(scenario["from"]["run"])
        out.update(
            run=m["label"],
            fullyRight=f"{m['fullyRight']}/{m['runs']}",
            crashes=f"{m['crashes']}/{m['runs']}",
            seconds=round(m["seconds"], 1) if m["seconds"] else None,
            perFullyRight=per_quote * m["runs"] / m["fullyRight"] if m["fullyRight"] else None,
        )
    return out


def price_all() -> list[dict]:
    return [price_scenario(s) for s in SCENARIOS["scenarios"]]


def group_list_share() -> float:
    now = _run("now")
    return _const("groupListTokens") * now["calls"] / now["input"]
