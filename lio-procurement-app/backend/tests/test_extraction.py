import json

from app.services.extraction import find_missing_fields, parse_reply

HOFFMANN_REPLY = {
    "title": "Industrial Grinding Machine Purchase",
    "vendorName": "Hoffmann Nurnberg GmbH Qualitatswerkzeuge",
    "vatId": None,
    "department": "Einkauf / Technik",
    "orderLines": [
        {"positionDescription": "Schleifmaschine HN-GS 450", "unitPrice": 15000.0,
         "amount": 1, "unit": "pieces", "totalPrice": 15000.0},
        {"positionDescription": "Lieferung und Montage", "unitPrice": 2000.0,
         "amount": 1, "unit": "lump sum", "totalPrice": 2000.0},
    ],
    "totalCost": 17000.0,
    "commodityGroupId": 45,
    "commodityGroupName": "Production Machinery",
}


def test_null_vat_id_is_kept_not_a_crash():
    data = parse_reply(json.dumps(HOFFMANN_REPLY))
    assert data.vat_id is None
    assert data.vendor_name == "Hoffmann Nurnberg GmbH Qualitatswerkzeuge"
    assert len(data.order_lines) == 2


def test_null_vat_id_is_listed_as_missing():
    data = parse_reply(json.dumps(HOFFMANN_REPLY))
    assert find_missing_fields(data) == ["VAT ID"]


def test_every_field_can_be_null():
    reply = {k: None for k in HOFFMANN_REPLY}
    data = parse_reply(json.dumps(reply))
    assert data.order_lines == []
    assert find_missing_fields(data) == [
        "Title/Short Description", "Vendor Name", "VAT ID", "Department",
        "Order Lines", "Total Cost", "Commodity Group",
    ]


def test_fields_left_out_are_missing_not_a_crash():
    data = parse_reply(json.dumps({"vendorName": "styleGREEN"}))
    assert data.vendor_name == "styleGREEN"
    assert "VAT ID" in find_missing_fields(data)


def test_line_with_null_values_is_kept():
    reply = dict(HOFFMANN_REPLY, orderLines=[
        {"positionDescription": "Versandkosten", "unitPrice": None,
         "amount": None, "unit": None, "totalPrice": 113.85},
    ])
    line = parse_reply(json.dumps(reply)).order_lines[0]
    assert line.total_price == 113.85
    assert line.unit_price is None and line.amount is None and line.unit is None


def test_blank_strings_still_count_as_missing():
    reply = dict(HOFFMANN_REPLY, vatId="  ", department="")
    assert find_missing_fields(parse_reply(json.dumps(reply))) == ["VAT ID", "Department"]


def test_reply_in_code_fences_still_parses():
    data = parse_reply("```json\n" + json.dumps(HOFFMANN_REPLY) + "\n```")
    assert data.total_cost == 17000.0
