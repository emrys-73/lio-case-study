from __future__ import annotations

import json
from datetime import datetime, timezone

from evals.cost.engine import HERE, PRICES, SCENARIOS, group_list_share, price_all


def _usd(value: float | None) -> str:
    if value is None:
        return "-"
    if value >= 0.1:
        return f"${value:,.2f}"
    return f"${value:.4f}"


def markdown(rows: list[dict]) -> str:
    volume = SCENARIOS["constants"]["quotesPerMonth"]
    lines = [
        f"| Scenario | Evidence | Model | Input tokens | Per quote | Per {volume:,} quotes | Per fully right | Fully right | Result |",
        "|" + "---|" * 9,
    ]
    for r in rows:
        lines.append(
            f"| {r['name']} | {r['evidence']} | {r['model']} | {r['inputTokens']:,} | {_usd(r['perQuote'])} | "
            f"{_usd(r['perMonth'])} | {_usd(r.get('perFullyRight'))} | {r.get('fullyRight', '-')} | {r['result']} |"
        )
    lines.append("")
    lines.append(f"Group list share of today's input tokens: {group_list_share():.0%}")
    return "\n".join(lines)


def main() -> None:
    rows = price_all()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / f"{stamp}_cost.json").write_text(json.dumps({
        "createdAt": stamp,
        "prices": PRICES,
        "constants": SCENARIOS["constants"],
        "runs": SCENARIOS["runs"],
        "groupListShare": group_list_share(),
        "scenarios": rows,
    }, indent=2))
    print(markdown(rows))


if __name__ == "__main__":
    main()
