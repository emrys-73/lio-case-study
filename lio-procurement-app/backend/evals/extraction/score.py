from __future__ import annotations

import re
import unicodedata
from typing import Any

CENT = 0.01

UNIT_ALIASES = {
    "piece": {"piece", "pieces", "pcs", "pc", "stk", "stk.", "stück", "stuck", "stueck",
              "item", "items", "unit", "units", "einheit", "x"},
    "sqm": {"sqm", "qm", "m2", "m²", "square meter", "square meters", "square metre",
            "square metres", "quadratmeter"},
    "m": {"m", "lfm", "linear meter", "linear meters", "linear metre", "linear metres",
          "running meter", "running meters", "running metre", "running metres", "meter",
          "meters", "metre", "metres", "laufmeter"},
    "lump_sum": {"lump sum", "lump_sum", "pauschale", "flat rate", "flat fee", "package", "flat"},
}
EMPTY = {"", "n/a", "na", "none", "null", "-", "not available", "not found", "unknown"}


def _fold(text: str) -> str:
    text = text.lower().replace("ß", "ss")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def num_eq(a: Any, b: float | None) -> bool:
    if b is None:
        return False
    try:
        return abs(float(a) - float(b)) <= CENT / 2 + 1e-9
    except (TypeError, ValueError):
        return False


def vat_ok(got: Any, want: str | None) -> bool:
    got_s = "" if got is None else str(got).strip().lower()
    if want is None:
        return got_s in EMPTY
    return re.sub(r"[^a-z0-9]", "", got_s) == want.lower()


def vendor_ok(got: Any, accepted: list[str]) -> bool:
    if not got:
        return False
    g = _fold(str(got))
    for name in accepted:
        n = _fold(name)
        if g == n or (len(g) >= 4 and (g in n or n in g)):
            return True
    return False


def unit_canon(unit: Any) -> str | None:
    if unit is None:
        return None
    u = str(unit).strip().lower()
    for canon, aliases in UNIT_ALIASES.items():
        if u in aliases:
            return canon
    return u or None


def total_kind(got: Any, totals: dict) -> str:
    if num_eq(got, totals["net"]):
        return "net"
    if num_eq(got, totals["gross"]):
        return "gross"
    if num_eq(got, totals["positionsNet"]):
        return "items_only_net"
    if got in (None, 0, 0.0, ""):
        return "missing"
    return "other"


def _line_val(line: dict, *keys: str) -> Any:
    for k in keys:
        if k in line:
            return line[k]
    return None


def score_lines(got_lines: list[dict], key: dict) -> dict:
    remaining = list(range(len(got_lines)))
    matched = []
    for kl in key["lines"]:
        hit = None
        for i in remaining:
            if num_eq(_line_val(got_lines[i], "totalPrice", "total_price"), kl["totalPrice"]):
                hit = i
                break
        if hit is None:
            matched.append({"key": kl["description"], "kind": kl["kind"], "found": False})
            continue
        remaining.remove(hit)
        gl = got_lines[hit]
        up = _line_val(gl, "unitPrice", "unit_price")
        amt = _line_val(gl, "amount")
        unit = _line_val(gl, "unit")
        checks = {
            "unitPrice": any(num_eq(up, v) for v in kl["unitPrice"]),
            "amount": num_eq(amt, kl["amount"]),
        }
        if kl["unit"] is not None:
            checks["unit"] = unit_canon(unit) == kl["unit"]
        matched.append({
            "key": kl["description"], "kind": kl["kind"], "found": True,
            "checks": checks, "got": {"unitPrice": up, "amount": amt, "unit": unit},
        })

    extras = []
    for i in remaining:
        gl = got_lines[i]
        tp = _line_val(gl, "totalPrice", "total_price")
        reason = "extra"
        for ex in key.get("excluded", []):
            if num_eq(tp, ex["totalPrice"]) or num_eq(_line_val(gl, "unitPrice", "unit_price"), ex["totalPrice"]):
                reason = ex["reason"]
        extras.append({"description": _line_val(gl, "positionDescription", "position_description"),
                       "totalPrice": tp, "reason": reason})
    return {"matched": matched, "extras": extras}


def arithmetic(got_lines: list[dict], total: Any) -> dict:
    bad_lines = 0
    line_sum = 0.0
    for gl in got_lines:
        try:
            up = float(_line_val(gl, "unitPrice", "unit_price"))
            amt = float(_line_val(gl, "amount"))
            tp = float(_line_val(gl, "totalPrice", "total_price"))
        except (TypeError, ValueError):
            bad_lines += 1
            continue
        line_sum += tp
        if abs(up * amt - tp) > max(0.02, abs(tp) * 0.005):
            bad_lines += 1
    try:
        sums_to_total = abs(line_sum - float(total)) <= 0.02
    except (TypeError, ValueError):
        sums_to_total = False
    return {"linesNotQtyTimesPrice": bad_lines, "lineSum": round(line_sum, 2),
            "linesSumToTotal": sums_to_total}


WARNING_FIELDS = {"Vendor Name", "VAT ID", "Order Lines", "Total Cost"}


def totals_warning(app: dict) -> bool:
    totals = app.get("totals") or {}
    if totals.get("grossMatch") is not None:
        return totals["grossMatch"] is False
    return totals.get("match") is False


def warned(app: dict) -> bool:
    return totals_warning(app) or bool(WARNING_FIELDS & set(app.get("missingFields") or []))


def lines_right(result: dict) -> bool:
    return (
        not result["crashed"]
        and result["fields"]["totalCost"]
        and result["itemsFound"] == result["itemsExpected"]
        and result["chargesFound"] == result["chargesExpected"]
        and result["extraLines"] == 0
    )


def false_alarm(result: dict, app: dict) -> bool:
    return lines_right(result) and totals_warning(app)


def score(data: dict | None, key: dict) -> dict:
    if data is None:
        return {"crashed": True, "fullyCorrect": False}
    lines = data.get("orderLines") or data.get("order_lines") or []
    total = data.get("totalCost", data.get("total_cost"))
    ls = score_lines(lines, key)
    items = [m for m in ls["matched"] if m["kind"] == "item"]
    charges = [m for m in ls["matched"] if m["kind"] == "charge"]
    line_fields = [ok for m in ls["matched"] if m["found"] for ok in m["checks"].values()]
    fields = {
        "vendorName": vendor_ok(data.get("vendorName", data.get("vendor_name")), key["vendorName"]),
        "vatId": vat_ok(data.get("vatId", data.get("vat_id")), key["vatId"]),
        "totalCost": total_kind(total, key["totals"]) == "net",
    }
    result = {
        "crashed": False,
        "fields": fields,
        "totalKind": total_kind(total, key["totals"]),
        "itemsFound": sum(m["found"] for m in items),
        "itemsExpected": len(items),
        "chargesFound": sum(m["found"] for m in charges),
        "chargesExpected": len(charges),
        "lineFieldsRight": sum(line_fields),
        "lineFieldsChecked": len(line_fields),
        "extraLines": len(ls["extras"]),
        "alternativesCounted": sum(e["reason"] == "alternative" for e in ls["extras"]),
        "lines": ls,
        "arithmetic": arithmetic(lines, total),
        "totalsBlock": {
            "vatAmount": num_eq(data.get("vatAmount"),
                                round(key["totals"]["gross"] - key["totals"]["net"], 2)),
            "grossTotal": num_eq(data.get("grossTotal"), key["totals"]["gross"]),
        },
        "recorded": {
            "title": data.get("title"),
            "department": data.get("department"),
            "vendorName": data.get("vendorName", data.get("vendor_name")),
            "vatId": data.get("vatId", data.get("vat_id")),
            "totalCost": total,
            "commodityGroupId": data.get("commodityGroupId", data.get("commodity_group_id")),
        },
    }
    result["fullyCorrect"] = (
        all(fields.values())
        and result["itemsFound"] == result["itemsExpected"]
        and result["chargesFound"] == result["chargesExpected"]
        and result["lineFieldsRight"] == result["lineFieldsChecked"]
        and result["extraLines"] == 0
    )
    return result
