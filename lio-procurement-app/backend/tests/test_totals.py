import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import RequestActivity
from app.schemas.extraction import OrderLineData
from app.seed import seed
from app.services.extraction import apply_totals, parse_reply
from app.services.totals import add_up, check_totals


def _lines(*totals):
    return [OrderLineData(totalPrice=t) for t in totals]


def test_lines_are_added_up_to_the_cent():
    assert add_up(_lines(1438.0, 320.0)) == 1758.0
    assert add_up(_lines(0.1, 0.2)) == 0.3


def test_a_line_with_no_total_counts_as_zero():
    assert add_up(_lines(1467.61, None)) == 1467.61


def test_lines_matching_the_printed_total():
    assert check_totals(_lines(1438.0, 320.0), 1758.0) == {
        "computed": 1758.0, "printed": 1758.0, "match": True,
        "vat": None, "gross": None, "grossMatch": None,
    }


def test_lines_not_matching_the_printed_total():
    assert check_totals(_lines(715.26, 622.0), 1847.19) == {
        "computed": 1337.26, "printed": 1847.19, "match": False,
        "vat": None, "gross": None, "grossMatch": None,
    }


def test_no_printed_total_means_nothing_to_compare():
    assert check_totals(_lines(100.0), None) == {
        "computed": 100.0, "printed": None, "match": None,
        "vat": None, "gross": None, "grossMatch": None,
    }


def test_lines_plus_vat_make_the_gross():
    totals = check_totals(_lines(1467.61, 10.55), 1478.16, vat=280.85, gross=1759.01)
    assert totals["match"] is True
    assert totals["grossMatch"] is True


def test_a_missing_line_shows_up_against_the_gross():
    totals = check_totals(_lines(1467.61), 1467.61, vat=280.85, gross=1759.01)
    assert totals["match"] is True
    assert totals["grossMatch"] is False


def test_extraction_total_is_the_sum_of_the_lines():
    data = parse_reply(json.dumps({
        "orderLines": [{"totalPrice": 15000.0}, {"totalPrice": 2000.0}],
        "totalCost": 17230.0,
    }))
    totals = apply_totals(data)
    assert data.total_cost == 17000.0
    assert {k: totals[k] for k in ("computed", "printed", "match")} == {
        "computed": 17000.0, "printed": 17230.0, "match": False,
    }


def test_extraction_with_no_lines_keeps_the_printed_total():
    data = parse_reply(json.dumps({"orderLines": [], "totalCost": 500.0}))
    totals = apply_totals(data)
    assert data.total_cost == 500.0
    assert {k: totals[k] for k in ("computed", "printed", "match")} == {
        "computed": 0.0, "printed": 500.0, "match": False,
    }


def test_extraction_checks_the_lines_against_the_gross():
    data = parse_reply(json.dumps({
        "orderLines": [{"totalPrice": 1467.61}],
        "totalCost": 1467.61, "vatAmount": 280.85, "grossTotal": 1759.01,
    }))
    totals = apply_totals(data)
    assert (totals["vat"], totals["gross"], totals["grossMatch"]) == (280.85, 1759.01, False)


@pytest.fixture(scope="module")
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _fks(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as s:
        seed(s)
    return Session


@pytest.fixture
def client(db_session):
    def _get_db():
        db = db_session()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app, raise_server_exceptions=False)
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def _token(client):
    r = client.post("/auth/signin", json={"email": "requester@acme.com", "password": "demo1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


GREGG_LINES = [
    {"positionDescription": "Moosbild 70:30", "unitPrice": 1438.0, "amount": 1,
     "unit": "pieces", "totalPrice": 1438.0},
    {"positionDescription": "Transport", "unitPrice": 320.0, "amount": 1,
     "unit": "lump sum", "totalPrice": 320.0},
]


def _create(title, total):
    return {
        "requestorName": "Rene Requester", "titleShortDescription": title,
        "vendorName": "Gärtner Gregg", "vatId": "DE198570491", "commodityGroupId": 15,
        "totalCost": total, "department": "Office", "orderLines": GREGG_LINES,
    }


def _activity(db_session, request_id, action):
    with db_session() as s:
        return s.scalars(
            select(RequestActivity)
            .where(RequestActivity.request_id == uuid.UUID(request_id),
                   RequestActivity.action == action)
        ).all()


def test_create_ignores_the_total_the_client_sent(client, db_session):
    r = client.post("/requests", json=_create("Moss wall", 1.0), headers=_token(client))
    assert r.status_code == 201, r.text
    assert float(r.json()["total_cost"]) == 1758.0
    [created] = _activity(db_session, r.json()["id"], "created")
    assert created.detail["totals"] == {
        "computed": 1758.0, "submitted": 1.0, "printed": None, "match": None,
        "linesOff": [],
    }


def test_create_with_the_right_total_logs_it_too(client, db_session):
    r = client.post("/requests", json=_create("Moss wall", 1758.0), headers=_token(client))
    [created] = _activity(db_session, r.json()["id"], "created")
    assert created.detail["totals"]["computed"] == 1758.0
    assert created.detail["totals"]["submitted"] == 1758.0


def test_edit_ignores_the_total_the_client_sent(client, db_session):
    headers = _token(client)
    rid = client.post("/requests", json=_create("Moss wall", 1758.0), headers=headers).json()["id"]
    edit = dict(_create("Moss wall", 99.0), title="Moss wall")
    edit["orderLines"] = GREGG_LINES[:1]
    r = client.put(f"/requests/{rid}", json=edit, headers=headers)
    assert r.status_code == 200, r.text
    assert float(r.json()["total_cost"]) == 1438.0
    [updated] = _activity(db_session, rid, "updated")
    assert updated.detail["totals"] == {
        "computed": 1438.0, "submitted": 99.0, "printed": None, "match": None,
        "linesOff": [],
    }


SNAPSHOT = {
    "success": True,
    "data": {"vendorName": "Gärtner Gregg", "vatId": "DE 198 570 491", "orderLines": GREGG_LINES,
             "totalCost": 1758.0},
    "totals": {"computed": 1758.0, "printed": 1758.0, "match": True},
}


def test_create_from_a_pdf_stores_what_the_extraction_returned(client, db_session):
    payload = dict(_create("Moss wall", 1758.0), extraction=SNAPSHOT)
    r = client.post("/requests", json=payload, headers=_token(client))
    assert r.status_code == 201, r.text
    [created] = _activity(db_session, r.json()["id"], "created")
    assert created.detail["source"] == "pdf"
    assert created.detail["extraction"] == SNAPSHOT
    assert created.detail["totals"] == {
        "computed": 1758.0, "submitted": 1758.0, "printed": 1758.0, "match": True,
        "linesOff": [],
    }


def test_lines_changed_after_extraction_no_longer_match_the_quote(client, db_session):
    payload = dict(_create("Moss wall", 1438.0), extraction=SNAPSHOT)
    payload["orderLines"] = GREGG_LINES[:1]
    r = client.post("/requests", json=payload, headers=_token(client))
    [created] = _activity(db_session, r.json()["id"], "created")
    assert created.detail["totals"]["match"] is False
    assert created.detail["totals"]["printed"] == 1758.0


def test_typed_request_has_no_snapshot(client, db_session):
    r = client.post("/requests", json=_create("Moss wall", 1758.0), headers=_token(client))
    [created] = _activity(db_session, r.json()["id"], "created")
    assert created.detail["source"] == "manual"
    assert "extraction" not in created.detail


def test_a_line_where_qty_times_price_is_not_the_total_is_flagged_not_changed(client, db_session):
    payload = _create("Moss wall", 1.0)
    payload["orderLines"] = [
        dict(GREGG_LINES[0]),
        {"positionDescription": "Schrauben", "unitPrice": 100.0, "amount": 10,
         "unit": "pieces", "totalPrice": 1.0},
    ]
    r = client.post("/requests", json=payload, headers=_token(client))
    assert float(r.json()["total_cost"]) == 1439.0
    [created] = _activity(db_session, r.json()["id"], "created")
    assert created.detail["totals"]["linesOff"] == [2]


def test_a_discounted_line_is_flagged_for_a_look(client, db_session):
    payload = _create("Moss picture", 715.26)
    payload["orderLines"] = [
        {"positionDescription": "Moosbild Mix-Moos", "unitPrice": 894.08, "amount": 1,
         "unit": "pieces", "totalPrice": 715.26},
    ]
    r = client.post("/requests", json=payload, headers=_token(client))
    [created] = _activity(db_session, r.json()["id"], "created")
    assert created.detail["totals"]["linesOff"] == [1]


def test_an_edit_with_no_lines_stores_a_total_of_zero(client, db_session):
    headers = _token(client)
    rid = client.post("/requests", json=_create("Moss wall", 1758.0), headers=headers).json()["id"]
    edit = dict(_create("Moss wall", 1758.0), title="Moss wall", orderLines=[])
    r = client.put(f"/requests/{rid}", json=edit, headers=headers)
    assert r.status_code == 200, r.text
    assert float(r.json()["total_cost"]) == 0.0


def test_vat_printed_in_two_places_is_no_false_alarm():
    totals = check_totals(_lines(715.52, 120.62, 350.0, 113.85), 1186.14, vat=225.37, gross=1546.99)
    assert totals["grossMatch"] is True


def test_vat_counted_as_a_line_does_not_fit_the_gross():
    totals = check_totals(_lines(1467.61, 280.85, 10.55), 1759.01, vat=280.85, gross=1759.01)
    assert totals["grossMatch"] is False


def test_an_alternative_counted_as_bought_does_not_fit_the_gross():
    totals = check_totals(_lines(715.26, 622.0, 430.0, 215.0), 1552.26, vat=254.08, gross=1847.19)
    assert totals["grossMatch"] is False


def test_reduced_rate_and_no_vat_fit_the_gross():
    assert check_totals(_lines(100.0), None, vat=7.0, gross=107.0)["grossMatch"] is True
    assert check_totals(_lines(100.0), None, vat=None, gross=107.0)["grossMatch"] is True
    assert check_totals(_lines(1000.0), None, vat=0.0, gross=1000.0)["grossMatch"] is True
    assert check_totals(_lines(1000.0), None, vat=None, gross=1000.0)["grossMatch"] is True


def test_the_gross_alone_is_enough_to_check():
    assert check_totals(_lines(1299.99), None, vat=None, gross=1546.99)["grossMatch"] is True
    assert check_totals(_lines(1186.14), None, vat=None, gross=1546.99)["grossMatch"] is False
