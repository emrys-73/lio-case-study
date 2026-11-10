from __future__ import annotations

OUTCOMES = ("right", "wrong_sure", "missed", "correct_nothing")


def outcome(expected: str | None, got: str | None) -> str:
    if got is None:
        return "correct_nothing" if expected is None else "missed"
    return "right" if got == expected else "wrong_sure"


def in_top(expected: str | None, ranked: list[str], n: int = 5) -> bool | None:
    if expected is None:
        return None
    return expected in ranked[:n]


def summarise(rows: list[dict]) -> dict:
    counts = {name: 0 for name in OUTCOMES}
    for row in rows:
        counts[row["outcome"]] += 1
    should_match = [row for row in rows if row["expected"] is not None]
    top5 = sum(1 for row in should_match if row.get("top5"))
    seconds = sorted(row["seconds"] for row in rows if row.get("seconds") is not None)
    return {
        "cases": len(rows),
        **counts,
        "top5": top5,
        "should_match": len(should_match),
        "median_ms": round(seconds[len(seconds) // 2] * 1000, 1) if seconds else None,
    }
