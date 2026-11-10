import json
from pathlib import Path

from evals.extraction.score import score, unit_canon, vat_ok, vendor_ok

KEY = json.loads(
    (Path(__file__).parents[1] / "evals/extraction/cases/gaertner-gregg.json").read_text()
)

PERFECT = {
    "vendorName": "Gärtner Gregg",
    "vatId": "DE 198 570 491",
    "department": "",
    "orderLines": [
        {"positionDescription": "Moosbild", "unitPrice": 1438.0, "amount": 1, "unit": "pieces", "totalPrice": 1438.0},
        {"positionDescription": "Transport", "unitPrice": 320.0, "amount": 1, "unit": "flat", "totalPrice": 320.0},
    ],
    "totalCost": 1758.0,
}


def test_perfect_answer_is_fully_correct():
    s = score(PERFECT, KEY)
    assert s["fullyCorrect"]
    assert s["arithmetic"]["linesSumToTotal"]


def test_crash_scores_nothing():
    assert score(None, KEY) == {"crashed": True, "fullyCorrect": False}


def test_alternative_counted_as_purchase_is_flagged():
    data = {**PERFECT, "orderLines": PERFECT["orderLines"] + [
        {"positionDescription": "Alt 1.1a", "unitPrice": 1926.0, "amount": 1, "unit": "pieces", "totalPrice": 1926.0}
    ]}
    s = score(data, KEY)
    assert s["alternativesCounted"] == 1
    assert not s["fullyCorrect"]


def test_gross_total_is_wrong_but_named():
    s = score({**PERFECT, "totalCost": 2092.02}, KEY)
    assert s["totalKind"] == "gross"
    assert not s["fields"]["totalCost"]


def test_missing_shipping_line():
    data = {**PERFECT, "orderLines": PERFECT["orderLines"][:1]}
    s = score(data, KEY)
    assert s["chargesFound"] == 0 and s["chargesExpected"] == 1


def test_field_helpers():
    assert vat_ok(None, None) and vat_ok("N/A", None) and not vat_ok("DE1", None)
    assert vendor_ok("Hoffmann Nurnberg GmbH", ["Hoffmann Nürnberg GmbH"])
    assert unit_canon("Stk.") == "piece" and unit_canon("qm") == "sqm" and unit_canon("Lfm") == "m"


def test_every_key_adds_up():
    cases = Path(__file__).parents[1] / "evals/extraction/cases"
    for path in sorted(cases.glob("*.json")):
        key = json.loads(path.read_text())
        items = sum(l["totalPrice"] for l in key["lines"] if l["kind"] == "item")
        charges = sum(l["totalPrice"] for l in key["lines"] if l["kind"] == "charge")
        assert round(items, 2) == key["totals"]["positionsNet"], path.name
        assert round(items + charges, 2) == key["totals"]["net"], path.name
        for l in key["lines"]:
            assert abs(l["unitPrice"][0] * l["amount"] - l["totalPrice"]) < 0.01, (path.name, l["description"])
