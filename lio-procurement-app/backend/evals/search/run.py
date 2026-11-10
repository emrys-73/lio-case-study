from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.data.articles import ARTICLES
from app.services import catalogue_search as cs
from evals.search.score import in_top, outcome, summarise

HERE = Path(__file__).parent
CASES = HERE / "cases"
RESULTS = HERE / "results"


def load_cases(only: str | None = None) -> list[dict]:
    rows = []
    for path in sorted(CASES.glob("*.jsonl")):
        for line in path.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    for path in sorted(CASES.glob("*.json")):
        rows.append(json.loads(path.read_text()))
    if only:
        rows = [row for row in rows if only in row["id"]]
    return rows


def run_method(method: str, catalogue: cs.Catalogue, cases: list[dict],
               threshold: float | None, margin: float | None) -> list[dict]:
    rows = []
    for case in cases:
        started = time.monotonic()
        ranked = cs.rank(catalogue, case["query"], method=method)
        got = cs.sure(ranked, method=method, threshold=threshold, margin=margin)
        seconds = time.monotonic() - started
        top = [description for description, _ in ranked[:5]]
        rows.append({
            "id": case["id"],
            "kind": case["kind"],
            "query": case["query"],
            "expected": case["expected"],
            "got": got,
            "outcome": outcome(case["expected"], got),
            "top5": in_top(case["expected"], top),
            "ranked": [[description, round(score, 4)] for description, score in ranked[:5]],
            "seconds": round(seconds, 4),
        })
    return rows


def table(summaries: dict[str, dict]) -> str:
    head = "| method | right | wrong sure | missed | correct nothing | top-5 hit | median ms |"
    lines = [head, "|---|---|---|---|---|---|---|"]
    for method, s in summaries.items():
        lines.append(
            f"| {method} | {s['right']}/{s['should_match']} | {s['wrong_sure']} | {s['missed']} "
            f"| {s['correct_nothing']}/{s['cases'] - s['should_match']} "
            f"| {s['top5']}/{s['should_match']} | {s['median_ms']} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", action="append", choices=list(cs.METHODS))
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--margin", type=float)
    parser.add_argument("--case")
    parser.add_argument("--label", default="run")
    args = parser.parse_args()

    methods = args.method or ["words"]
    cases = load_cases(args.case)
    catalogue = cs.Catalogue(sorted({a["description"] for a in ARTICLES}))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = RESULTS / f"{stamp}_{args.label}"
    out.mkdir(parents=True, exist_ok=True)

    summaries = {}
    with (out / "runs.jsonl").open("w") as runs:
        for method in methods:
            rows = run_method(method, catalogue, cases, args.threshold, args.margin)
            for row in rows:
                runs.write(json.dumps({"method": method, **row}, ensure_ascii=False) + "\n")
            summaries[method] = summarise(rows)
            for row in rows:
                if row["outcome"] in ("wrong_sure", "missed"):
                    print(method, row["outcome"], row["id"], "->", row["got"], row["ranked"][:2])

    settings = {
        "methods": methods,
        "threshold": args.threshold,
        "margin": args.margin,
        "defaults": cs.SURE,
        "embedding_model": cs.embedding_model(),
        "cases": len(cases),
        "answer_key": "drafted, not yet checked by Adrian",
    }
    (out / "summary.json").write_text(
        json.dumps({"settings": settings, "summary": summaries}, indent=2, ensure_ascii=False)
    )
    md = f"# Search eval {stamp} ({args.label})\n\n{table(summaries)}\n\nSettings: `{json.dumps(settings, ensure_ascii=False)}`\n"
    (out / "summary.md").write_text(md)
    print(table(summaries))
    print(out)


if __name__ == "__main__":
    main()
