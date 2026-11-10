from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

import app.services.extraction as extraction
from app.core.config import settings
from app.db.session import SessionLocal
from app.services.pdf import extract_text
from evals.extraction.score import score, warned

HERE = Path(__file__).parent
CASES = HERE / "cases"
LAYOUT = HERE / "inputs" / "layout"
RESULTS = HERE / "results"
QUOTES = Path("/quotes")

log = logging.getLogger("eval.extraction")


class RecordingOpenAI(OpenAI):

    last: dict = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        create = self.chat.completions.create

        def recorded_create(**params):
            started = time.monotonic()
            RecordingOpenAI.last = {"model": params.get("model")}
            try:
                resp = create(**params)
            except Exception as exc:
                RecordingOpenAI.last.update(apiError=repr(exc),
                                            seconds=round(time.monotonic() - started, 2))
                raise
            choice = resp.choices[0]
            RecordingOpenAI.last.update(
                seconds=round(time.monotonic() - started, 2),
                responseModel=resp.model,
                systemFingerprint=resp.system_fingerprint,
                finishReason=choice.finish_reason,
                content=choice.message.content,
                promptTokens=resp.usage.prompt_tokens if resp.usage else None,
                completionTokens=resp.usage.completion_tokens if resp.usage else None,
            )
            return resp

        self.chat.completions.create = recorded_create


def _raw_json(content: str | None) -> dict | None:
    if not content:
        return None
    try:
        parsed = json.loads(extraction._strip_markdown_fences(content))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def run_case(key: dict, source: str, db) -> dict:
    pdf_bytes = (QUOTES / key["pdf"]).read_bytes()
    text = (LAYOUT / f"{key['pdf']}.txt").read_text() if source == "layout" else extract_text(pdf_bytes)

    RecordingOpenAI.last = {}
    started = time.monotonic()
    resp = extraction.extract_vendor_data(text, db, key.get("customer"))
    seconds = round(time.monotonic() - started, 2)
    raw = dict(RecordingOpenAI.last)
    app_data = resp.data.model_dump(by_alias=True) if resp.success and resp.data else None
    raw_parsed = _raw_json(raw.get("content"))

    return {
        "case": key["id"],
        "inputChars": len(text),
        "seconds": seconds,
        "model": raw,
        "app": {"success": resp.success, "error": resp.error,
                "missingFields": resp.missing_fields, "data": app_data,
                "totals": resp.totals.model_dump(by_alias=True) if resp.totals else None},
        "score": score(app_data, key),
        "modelOnlyScore": score(raw_parsed, key) if raw_parsed else None,
    }


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({round(100 * n / d) if d else 0}%)"


def summarise(rows: list[dict], meta: dict) -> tuple[dict, str]:
    ok = [r["score"] for r in rows if not r["score"]["crashed"]]
    n = len(rows)
    crashes = n - len(ok)

    def fsum(name):
        return sum(s["fields"][name] for s in ok)

    model_ok = [r["modelOnlyScore"] for r in rows
                if r["score"]["crashed"] and r["modelOnlyScore"]]
    totals = {}
    for s in ok:
        totals[s["totalKind"]] = totals.get(s["totalKind"], 0) + 1

    overall = {
        "runs": n,
        "crashes": crashes,
        "crashesWhereModelReplyWasUsable": len(model_ok),
        "fullyCorrect": sum(r["score"]["fullyCorrect"] for r in rows),
        "vendorName": fsum("vendorName"),
        "vatId": fsum("vatId"),
        "totalCostNet": fsum("totalCost"),
        "totalKinds": totals,
        "itemsFound": sum(s["itemsFound"] for s in ok),
        "itemsExpected": sum(r["score"].get("itemsExpected", 0) or 0 for r in rows) or None,
        "chargesFound": sum(s["chargesFound"] for s in ok),
        "lineFieldsRight": sum(s["lineFieldsRight"] for s in ok),
        "lineFieldsChecked": sum(s["lineFieldsChecked"] for s in ok),
        "alternativesCounted": sum(s["alternativesCounted"] for s in ok),
        "extraLines": sum(s["extraLines"] for s in ok),
        "linesSumToTotal": sum(s["arithmetic"]["linesSumToTotal"] for s in ok),
        "vatAmount": sum(s.get("totalsBlock", {}).get("vatAmount", False) for s in ok),
        "grossTotal": sum(s.get("totalsBlock", {}).get("grossTotal", False) for s in ok),
        "wrong": sum(not r["score"]["fullyCorrect"] for r in rows),
        "wrongAndSilent": sum(not r["score"]["fullyCorrect"] and not warned(r["app"]) for r in rows),
        "avgSeconds": round(sum(r["seconds"] for r in rows) / n, 1) if n else 0,
        "promptTokens": sum(r["model"].get("promptTokens") or 0 for r in rows),
        "completionTokens": sum(r["model"].get("completionTokens") or 0 for r in rows),
    }

    keys = {r["case"]: r for r in rows}
    exp_items = exp_charges = 0
    for r in rows:
        key = json.loads((CASES / f"{r['case']}.json").read_text())
        exp_items += sum(l["kind"] == "item" for l in key["lines"])
        exp_charges += sum(l["kind"] == "charge" for l in key["lines"])
    overall["itemsExpected"] = exp_items
    overall["chargesExpected"] = exp_charges

    per_case = {}
    for case in keys:
        rs = [r for r in rows if r["case"] == case]
        per_case[case] = {
            "runs": len(rs),
            "crashes": sum(r["score"]["crashed"] for r in rs),
            "fullyCorrect": sum(r["score"]["fullyCorrect"] for r in rs),
            "errors": sorted({(r["app"]["error"] or "")[:160] for r in rs if not r["app"]["success"]}),
            "totalKinds": [r["score"].get("totalKind", "crash") for r in rs],
            "alternativesCounted": [r["score"].get("alternativesCounted") for r in rs],
            "missingCharges": [
                (r["score"]["chargesExpected"] - r["score"]["chargesFound"]) if not r["score"]["crashed"] else None
                for r in rs
            ],
            "departments": sorted({str(r["score"].get("recorded", {}).get("department")) for r in rs
                                   if not r["score"]["crashed"]}),
        }

    summary = {"meta": meta, "overall": overall, "perCase": per_case}

    o = overall
    md = [
        f"# Extraction eval: {meta['label']}",
        "",
        f"- Model: `{meta['model']}`, text from `{meta['textSource']}`, {meta['runsPerCase']} runs per case",
        f"- Started {meta['startedAt']}",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Crashes (user gets nothing) | {_pct(o['crashes'], n)} |",
        f"| ... of which the model reply was usable | {o['crashesWhereModelReplyWasUsable']} |",
        f"| Fully correct quotes | {_pct(o['fullyCorrect'], n)} |",
        f"| Vendor name right | {_pct(o['vendorName'], n)} |",
        f"| VAT ID right | {_pct(o['vatId'], n)} |",
        f"| Total = net cost | {_pct(o['totalCostNet'], n)} |",
        f"| Total kinds | {o['totalKinds']} |",
        f"| Item lines found | {_pct(o['itemsFound'], o['itemsExpected'])} |",
        f"| Charge lines found (shipping, levy) | {_pct(o['chargesFound'], o['chargesExpected'])} |",
        f"| Line fields right (of found lines) | {_pct(o['lineFieldsRight'], o['lineFieldsChecked'])} |",
        f"| Alternatives counted as purchases | {o['alternativesCounted']} |",
        f"| Extra lines | {o['extraLines']} |",
        f"| Lines sum to total | {_pct(o['linesSumToTotal'], n)} |",
        f"| VAT amount right | {_pct(o['vatAmount'], n)} |",
        f"| Gross total right | {_pct(o['grossTotal'], n)} |",
        f"| Wrong with no warning in the form | {_pct(o['wrongAndSilent'], o['wrong'])} |",
        f"| Avg seconds per quote | {o['avgSeconds']} |",
        f"| Tokens in / out | {o['promptTokens']:,} / {o['completionTokens']:,} |",
        "",
        "| Case | Crashes | Fully correct | Total kind | Alternatives | Missing charges |",
        "|---|---|---|---|---|---|",
    ]
    for case, c in per_case.items():
        md.append(f"| {case} | {c['crashes']}/{c['runs']} | {c['fullyCorrect']}/{c['runs']} | "
                  f"{', '.join(c['totalKinds'])} | {c['alternativesCounted']} | {c['missingCharges']} |")
    errs = {e for c in per_case.values() for e in c["errors"]}
    if errs:
        md += ["", "Errors:", *[f"- `{e}`" for e in sorted(errs)]]
    return summary, "\n".join(md) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--model", default=None)
    parser.add_argument("--text-source", choices=["pypdf", "layout"], default="pypdf")
    parser.add_argument("--case", action="append")
    parser.add_argument("--label", default="run")
    parser.add_argument("--without-group-list", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.model:
        settings.openai_model = args.model
    extraction.OpenAI = RecordingOpenAI
    if args.without_group_list:
        build = extraction._build_prompt
        extraction._build_prompt = lambda text, groups, *rest: build(
            text, "(left out for this run)", *rest)

    keys = [json.loads(p.read_text()) for p in sorted(CASES.glob("*.json"))]
    if args.case:
        keys = [k for k in keys if k["id"] in args.case]

    started = datetime.now(timezone.utc)
    meta = {"label": args.label, "model": settings.openai_model, "textSource": args.text_source,
            "runsPerCase": args.runs, "startedAt": started.isoformat(timespec="seconds"),
            "withoutGroupList": args.without_group_list}
    out = RESULTS / f"{started.strftime('%Y%m%d-%H%M%S')}_{args.label}"
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    with SessionLocal() as db, (out / "runs.jsonl").open("w") as fh:
        for key in keys:
            for i in range(args.runs):
                row = run_case(key, args.text_source, db)
                row["run"] = i + 1
                rows.append(row)
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                fh.flush()
                s = row["score"]
                log.info("%s run %d: %s in %.1fs%s", key["id"], i + 1,
                         "CRASH" if s["crashed"] else ("OK" if s["fullyCorrect"] else "wrong"),
                         row["seconds"],
                         f" ({' '.join(row['app']['error'].split())[:140]})" if s["crashed"] else
                         f" total={s['totalKind']} items={s['itemsFound']}/{s['itemsExpected']}"
                         f" charges={s['chargesFound']}/{s['chargesExpected']} extras={s['extraLines']}")

    summary, md = summarise(rows, meta)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    (out / "summary.md").write_text(md)
    print(md)
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
