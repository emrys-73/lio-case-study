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
    }


def test_lines_not_matching_the_printed_total():
    assert check_totals(_lines(715.26, 622.0), 1847.19) == {
        "computed": 1337.26, "printed": 1847.19, "match": False,
    }


def test_no_printed_total_means_nothing_to_compare():
    assert check_totals(_lines(100.0), None) == {
        "computed": 100.0, "printed": None, "match": None,
    }


def test_extraction_total_is_the_sum_of_the_lines():
    data = parse_reply(json.dumps({
        "orderLines": [{"totalPrice": 15000.0}, {"totalPrice": 2000.0}],
        "totalCost": 17230.0,
    }))
    totals = apply_totals(data)
    assert data.total_cost == 17000.0
    assert totals == {"computed": 17000.0, "printed": 17230.0, "match": False}


def test_extraction_with_no_lines_keeps_the_printed_total():
    data = parse_reply(json.dumps({"orderLines": [], "totalCost": 500.0}))
    totals = apply_totals(data)
    assert data.total_cost == 500.0
    assert totals == {"computed": 0.0, "printed": 500.0, "match": False}


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
    }

