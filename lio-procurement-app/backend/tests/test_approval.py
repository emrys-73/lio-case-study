import inspect
import logging
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Organization, RequestActivity
from app.seed import seed

LIMIT = 2000
OFFICE_EQUIPMENT = 15
SETTINGS = "/organizations/me/settings"
AUTO = "auto_approved"
RESET = "approval_reset"


@pytest.mark.parametrize(
    "total, expected",
    [
        (1999.99, "approved"),
        (2000.00, "pending"),
        (2000.01, "pending"),
        (0.01, "approved"),
        (Decimal("1999.99"), "approved"),
        (Decimal("2000.00"), "pending"),
    ],
)
def test_only_a_total_strictly_below_the_limit_is_approved(total, expected):
    from app.services.approval import approval_for

    assert approval_for(total, 2000.0) == expected


@pytest.mark.parametrize("total", [None, 0, 0.0, Decimal("0.00")])
def test_no_total_or_zero_stays_pending(total):
    from app.services.approval import approval_for

    assert approval_for(total, 2000.0) == "pending"


def test_a_total_that_does_not_add_up_stays_pending():
    from app.services.approval import approval_for

    assert approval_for(1999.99, 2000.0, adds_up=False) == "pending"
    assert approval_for(1999.99, 2000.0, adds_up=True) == "approved"
    assert approval_for(1999.99, 2000.0, adds_up=None) == "approved"


@pytest.mark.parametrize("total", [0.01, 1999.99, 2000.00, 50000.0])
def test_no_limit_keeps_todays_behaviour(total):
    from app.services.approval import approval_for

    assert approval_for(total, None) == "pending"


def test_the_decision_knows_nothing_about_the_db_or_the_api():
    from app.services import approval

    source = inspect.getsource(approval)
    for name in ("sqlalchemy", "fastapi", "Session", "app.models"):
        assert name not in source


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
    with db_session() as s:
        for org in s.scalars(select(Organization)):
            org.settings = {}
        s.commit()
    yield TestClient(app, raise_server_exceptions=False)
    if previous is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous


def _token(client, email):
    r = client.post("/auth/signin", json={"email": email, "password": "demo1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _set_limit(client, limit, email="admin@acme.com"):
    r = client.patch(SETTINGS, json={"approval_limit": limit}, headers=_token(client, email))
    assert r.status_code == 200, r.text
    return r.json()


def _read_settings(client, email="admin@acme.com"):
    r = client.get(SETTINGS, headers=_token(client, email))
    assert r.status_code == 200, r.text
    return r.json()


def _acme(db_session):
    with db_session() as s:
        return s.scalar(select(Organization).where(Organization.slug == "acme"))


def _store_raw(db_session, settings):
    with db_session() as s:
        org = s.scalar(select(Organization).where(Organization.slug == "acme"))
        org.settings = settings
        s.commit()


def test_admin_saves_the_limit_and_reads_it_back(client):
    assert _set_limit(client, LIMIT)["approval_limit"] == LIMIT
    assert _read_settings(client)["approval_limit"] == LIMIT
    assert _set_limit(client, 2500.5)["approval_limit"] == 2500.5
    assert _read_settings(client)["approval_limit"] == 2500.5


@pytest.mark.parametrize("bad", [-1, -0.01, 0, 0.0, "2000", "abc", True, [2000], {"eur": 2000}])
def test_the_limit_must_be_a_positive_number(client, bad):
    _set_limit(client, LIMIT)
    r = client.patch(
        SETTINGS, json={"approval_limit": bad}, headers=_token(client, "admin@acme.com")
    )
    assert r.status_code == 422, bad
    assert _read_settings(client)["approval_limit"] == LIMIT


def test_saving_required_fields_keeps_the_limit(client):
    _set_limit(client, LIMIT)
    headers = _token(client, "admin@acme.com")
    r = client.patch(SETTINGS, json={"required_fields": ["vat_id"]}, headers=headers)
    assert r.status_code == 200, r.text
    saved = _read_settings(client)
    assert saved["required_fields"] == ["vat_id"]
    assert saved["approval_limit"] == LIMIT


def test_saving_the_limit_keeps_required_fields(client):
    headers = _token(client, "admin@acme.com")
    client.patch(SETTINGS, json={"required_fields": ["vat_id"]}, headers=headers)
    _set_limit(client, LIMIT)
    assert _read_settings(client)["required_fields"] == ["vat_id"]


def test_an_org_without_the_key_reads_as_no_limit(client, db_session):
    from app.services.organization_settings import load_settings

    assert _read_settings(client).get("approval_limit") is None
    assert load_settings(_acme(db_session)).approval_limit is None


def test_patching_null_removes_the_limit(client, db_session):
    from app.services.organization_settings import load_settings

    _set_limit(client, LIMIT)
    assert _set_limit(client, None).get("approval_limit") is None
    assert _read_settings(client).get("approval_limit") is None
    assert load_settings(_acme(db_session)).approval_limit is None


def test_the_limit_is_per_company(client):
    _set_limit(client, LIMIT)
    assert _read_settings(client, "admin@walmart.com").get("approval_limit") is None


@pytest.mark.parametrize("email", ["buyer@acme.com", "requester@acme.com"])
def test_only_an_admin_can_set_the_limit(client, email):
    r = client.patch(SETTINGS, json={"approval_limit": LIMIT}, headers=_token(client, email))
    assert r.status_code == 403
    assert _read_settings(client).get("approval_limit") is None


@pytest.mark.parametrize("stored", [-5, 0, "2000", "abc", True, [2000]])
def test_a_bad_stored_limit_reads_as_no_limit_and_is_logged(client, db_session, caplog, stored):
    from app.services.organization_settings import load_settings

    _store_raw(db_session, {"approval_limit": stored, "required_fields": ["vat_id"]})
    with caplog.at_level(logging.WARNING):
        saved = _read_settings(client)
    assert saved.get("approval_limit") is None
    assert saved["required_fields"] == ["vat_id"]
    assert "skipped approval_limit" in caplog.text
    assert load_settings(_acme(db_session)).approval_limit is None


def test_a_good_stored_limit_reads_back(client, db_session):
    from app.services.organization_settings import load_settings

    _store_raw(db_session, {"approval_limit": 2000})
    assert _read_settings(client)["approval_limit"] == LIMIT
    assert load_settings(_acme(db_session)).approval_limit == LIMIT


def _line(text, total):
    return {
        "positionDescription": text,
        "unitPrice": total,
        "amount": 1,
        "unit": "pieces",
        "totalPrice": total,
    }


def _create(client, lines, total_cost=None, email="requester@acme.com"):
    body = {
        "requestorName": "Rene Requester",
        "titleShortDescription": "Workshop order",
        "vendorName": "Würth",
        "vatId": "DE123456789",
        "commodityGroupId": OFFICE_EQUIPMENT,
        "totalCost": sum(line["totalPrice"] for line in lines) if total_cost is None else total_cost,
        "department": "Maintenance",
        "orderLines": lines,
    }
    r = client.post("/requests", json=body, headers=_token(client, email))
    assert r.status_code == 201, r.text
    return r.json()


def _edit(client, created, lines, email="requester@acme.com"):
    body = {
        "requestorName": created["requestor_name"],
        "title": created["title"],
        "vendorName": created["vendor_name"],
        "vatId": created["vat_id"],
        "commodityGroupId": created["commodity_group_id"],
        "totalCost": sum(line["totalPrice"] for line in lines),
        "department": created["department"],
        "orderLines": lines,
    }
    r = client.put(f"/requests/{created['id']}", json=body, headers=_token(client, email))
    assert r.status_code == 200, r.text
    return r.json()


def _activity(db_session, request_id, action):
    with db_session() as s:
        rows = s.scalars(
            select(RequestActivity)
            .where(
                RequestActivity.request_id == uuid.UUID(request_id),
                RequestActivity.action == action,
            )
            .order_by(RequestActivity.created_at)
        ).all()
        return [row.detail for row in rows]


def test_create_below_the_limit_is_auto_approved_and_logged(client, db_session):
    _set_limit(client, LIMIT)
    created = _create(client, [_line("Office chair", 1999.99)])
    assert created["approval_status"] == "approved"
    assert created["approved_by"] is None
    assert created["approved_at"] is not None
    assert _activity(db_session, created["id"], "auto_approved") == [
        {"limit": LIMIT, "computed_total": 1999.99}
    ]


def test_create_at_the_limit_stays_pending(client, db_session):
    _set_limit(client, LIMIT)
    created = _create(client, [_line("Schleifmaschine", 2000.00)])
    assert created["approval_status"] == "pending"
    assert created["approved_by"] is None
    assert _activity(db_session, created["id"], "auto_approved") == []


def test_the_form_total_is_ignored_and_the_lines_decide(client, db_session):
    _set_limit(client, LIMIT)
    lines = [_line("Schleifmaschine", 2500.0), _line("Montage", 2500.0)]
    created = _create(client, lines, total_cost=10.0)
    assert created["total_cost"] == 5000.0
    assert created["approval_status"] == "pending"
    assert _activity(db_session, created["id"], "auto_approved") == []


def test_an_org_without_a_limit_stays_pending(client, db_session):
    created = _create(client, [_line("Office chair", 1999.99)])
    assert created["approval_status"] == "pending"
    assert _activity(db_session, created["id"], "auto_approved") == []


def test_editing_an_auto_approved_request_to_the_limit_sends_it_back_to_pending(
    client, db_session
):
    _set_limit(client, LIMIT)
    created = _create(client, [_line("Office chair", 1999.99)])
    assert created["approval_status"] == "approved"
    lines = [_line("Office chair", 1999.99), _line("Versand", 0.01)]
    edited = _edit(client, created, lines)
    assert edited["total_cost"] == 2000.0
    assert edited["approval_status"] == "pending"
    assert edited["approved_by"] is None
    assert edited["approved_at"] is None
    assert _activity(db_session, created["id"], RESET) == [
        {"from_total": 1999.99, "to_total": 2000.0, "limit": LIMIT}
    ]


def _decide(client, created, decision, email="buyer@acme.com"):
    r = client.patch(
        f"/requests/{created['id']}/approval",
        json={"decision": decision},
        headers=_token(client, email),
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_a_pending_request_edited_under_the_limit_is_auto_approved(client, db_session):
    _set_limit(client, LIMIT)
    created = _create(client, [_line("Schleifmaschine", 2500.0)])
    assert created["approval_status"] == "pending"
    edited = _edit(client, created, [_line("Schleifmaschine", 1500.0)])
    assert edited["approval_status"] == "approved"
    assert edited["approved_by"] is None
    assert edited["approved_at"] is not None
    assert _activity(db_session, created["id"], AUTO) == [
        {"limit": LIMIT, "computed_total": 1500.0}
    ]


def test_a_rejected_request_stays_rejected_after_an_edit_under_the_limit(client, db_session):
    _set_limit(client, LIMIT)
    created = _create(client, [_line("Schleifmaschine", 2500.0)])
    rejected = _decide(client, created, "rejected")
    edited = _edit(client, created, [_line("Schleifmaschine", 100.0)])
    assert edited["approval_status"] == "rejected"
    assert edited["approved_by"] == rejected["approved_by"]
    assert _activity(db_session, created["id"], AUTO) == []
    assert _activity(db_session, created["id"], RESET) == []


def test_a_buyer_approval_holds_on_a_lower_total_and_resets_on_a_higher_one(client, db_session):
    _set_limit(client, LIMIT)
    created = _create(client, [_line("Schleifmaschine", 2500.0)])
    approved = _decide(client, created, "approved")
    lower = _edit(client, created, [_line("Schleifmaschine", 2400.0)])
    assert lower["approval_status"] == "approved"
    assert lower["approved_by"] == approved["approved_by"]
    higher = _edit(client, created, [_line("Schleifmaschine", 2600.0)])
    assert higher["approval_status"] == "pending"
    assert higher["approved_by"] is None
    assert higher["approved_at"] is None
    assert _activity(db_session, created["id"], RESET) == [
        {"from_total": 2400.0, "to_total": 2600.0, "limit": LIMIT}
    ]


SWITCHED = {
    "status": "switched",
    "article_number": "LIN-00862",
    "offer_price": 240.0,
    "catalog_price": 186.0,
}


def test_the_catalog_choices_still_reach_the_created_and_updated_detail(client, db_session):
    _set_limit(client, LIMIT)
    created = _create(client, [dict(_line("Toner schwarz XL", 186.0), catalog=SWITCHED)])
    [detail] = _activity(db_session, created["id"], "created")
    assert detail["catalog"] == [{"line": 1, **SWITCHED}]
    lines = [_line("Office chair", 10.0), dict(_line("Toner schwarz XL", 186.0), catalog=SWITCHED)]
    _edit(client, created, lines)
    [detail] = _activity(db_session, created["id"], "updated")
    assert detail["catalog"] == [{"line": 2, **SWITCHED}]


def test_the_seed_sets_acme_limit_once_and_keeps_an_admin_value(client, db_session):
    with db_session() as s:
        assert seed(s)["approval_limit"] == 1
    assert _read_settings(client)["approval_limit"] == LIMIT
    assert _read_settings(client, "admin@walmart.com").get("approval_limit") is None
    _set_limit(client, 5000)
    with db_session() as s:
        assert seed(s)["approval_limit"] == 0
    assert _read_settings(client)["approval_limit"] == 5000
