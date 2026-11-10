import inspect
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Organization
from app.seed import seed
from app.services import extraction

ELECTRICAL_ENGINEERING = 11
IT_HARDWARE = 29
SOFTWARE = 31
TONER_CARTRIDGES = 204

ACME_RULES = [
    {
        "keywords": ["cable tie", "kabelbinder"],
        "commodity_group_id": ELECTRICAL_ENGINEERING,
        "reason": "Acme books cable ties under Electrical Engineering",
    },
    {
        "keywords": ["toner"],
        "commodity_group_id": IT_HARDWARE,
        "reason": "Acme books printer toner under IT Hardware",
    },
]

SERVER_FIELDS = {"id", "max_amount", "updated_by", "updated_at"}


def _as_written(rules):
    return [{k: v for k, v in rule.items() if k not in SERVER_FIELDS} for rule in rules]


target = pytest.mark.xfail(strict=True, reason="Problem 3 target, not built yet")


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


def _request(title, group_id):
    return {
        "requestorName": "Rene Requester",
        "titleShortDescription": title,
        "vendorName": "Würth",
        "vatId": "DE123456789",
        "commodityGroupId": group_id,
        "totalCost": 40.0,
        "department": "Maintenance",
        "orderLines": [
            {
                "positionDescription": title,
                "unitPrice": 0.4,
                "amount": 100,
                "unit": "pieces",
                "totalPrice": 40.0,
            }
        ],
    }


def _org_id(db_session, slug):
    with db_session() as s:
        return s.scalar(select(Organization.id).where(Organization.slug == slug))


def test_today_groups_are_one_global_list(client):
    acme = client.get("/commodity-groups", headers=_token(client, "admin@acme.com")).json()
    walmart = client.get("/commodity-groups", headers=_token(client, "admin@walmart.com")).json()
    assert acme == walmart


def test_today_acme_names_sit_in_other_categories(client):
    groups = client.get("/commodity-groups", headers=_token(client, "admin@acme.com")).json()
    by_id = {g["id"]: g for g in groups}
    names = {g["name"] for g in groups}
    assert by_id[ELECTRICAL_ENGINEERING] == {
        "id": 11, "category": "Facility Management", "name": "Electrical Engineering"
    }
    assert by_id[IT_HARDWARE] == {"id": 29, "category": "Information Technology", "name": "Hardware"}
    assert by_id[TONER_CARTRIDGES]["category"] == "Office & Administration"
    assert "Office Supplies" not in names


def test_today_manual_request_keeps_any_group_the_user_picks(client):
    headers = _token(client, "requester@acme.com")
    r = client.post("/requests", json=_request("Cable ties 200mm", SOFTWARE), headers=headers)
    assert r.status_code == 201, r.text
    assert r.json()["commodity_groups"]["id"] == SOFTWARE


def test_settings_hold_required_fields_and_rules(client):
    headers = _token(client, "admin@acme.com")
    assert client.get("/organizations/me/settings", headers=headers).json() == {
        "required_fields": [],
        "commodity_rules": [],
    }


def test_guard_write_rejects_unknown_keys(client):
    headers = _token(client, "admin@acme.com")
    r = client.patch("/organizations/me/settings", json={"approval_limt": 2000}, headers=headers)
    assert r.status_code == 422
    sneaky = [dict(ACME_RULES[0], colour="red")]
    r = client.patch("/organizations/me/settings", json={"commodity_rules": sneaky}, headers=headers)
    assert r.status_code == 422
    r = client.patch(
        "/organizations/me/settings", json={"required_fields": ["shoe_size"]}, headers=headers
    )
    assert r.status_code == 422


def test_empty_patch_changes_nothing(client):
    headers = _token(client, "admin@acme.com")
    client.patch(
        "/organizations/me/settings", json={"required_fields": ["vat_id"]}, headers=headers
    )
    r = client.patch("/organizations/me/settings", json={}, headers=headers)
    assert r.status_code == 200, r.text
    assert client.get("/organizations/me/settings", headers=headers).json()["required_fields"] == [
        "vat_id"
    ]


def test_read_skips_unknown_keys_and_dead_rules_and_logs_them(client, db_session, caplog):
    live = dict(ACME_RULES[0], id="r_live")
    dead = dict(ACME_RULES[1], id="r_dead", commodity_group_id=999999)
    with db_session() as s:
        org = s.scalar(select(Organization).where(Organization.slug == "acme"))
        org.settings = {
            "required_fields": ["vat_id", "shoe_size"],
            "commodity_rules": [live, dead, {"keywords": []}, ACME_RULES[1]],
            "approval_limt": 2000,
        }
        s.commit()
    with caplog.at_level(logging.WARNING):
        r = client.get("/organizations/me/settings", headers=_token(client, "admin@acme.com"))
    assert r.status_code == 200, r.text
    assert r.json()["required_fields"] == ["vat_id"]
    assert [rule["commodity_group_id"] for rule in r.json()["commodity_rules"]] == [
        ELECTRICAL_ENGINEERING
    ]
    logged = caplog.text
    assert "approval_limt" in logged
    assert "shoe_size" in logged
    assert "999999" in logged


def test_requests_read_required_fields_through_the_same_reader(client, db_session):
    with db_session() as s:
        org = s.scalar(select(Organization).where(Organization.slug == "acme"))
        org.settings = {"required_fields": ["vat_id", "shoe_size"], "approval_limt": 2000}
        s.commit()
    headers = _token(client, "requester@acme.com")
    r = client.post("/requests", json=dict(_request("Desk", SOFTWARE), vatId=None), headers=headers)
    assert r.status_code == 422
    assert "vat_id" in r.text
    r = client.post("/requests", json=_request("Desk", SOFTWARE), headers=headers)
    assert r.status_code == 201, r.text


def test_one_settings_reader():
    from app.routers import organizations, requests

    for module in (organizations, requests):
        source = inspect.getsource(module)
        assert ".settings or" not in source
        assert "OrganizationSettings(**" not in source


def test_today_extraction_has_no_organization(client):
    params = inspect.signature(extraction.extract_vendor_data).parameters
    assert list(params) == ["pdf_text", "db", "buyer_name", "page_images"]


def test_admin_saves_rules_and_reads_them_back(client):
    headers = _token(client, "admin@acme.com")
    r = client.patch(
        "/organizations/me/settings", json={"commodity_rules": ACME_RULES}, headers=headers
    )
    assert r.status_code == 200, r.text
    saved = client.get("/organizations/me/settings", headers=headers).json()
    assert _as_written(saved["commodity_rules"]) == ACME_RULES


def test_rule_with_unknown_group_is_rejected(client):
    headers = _token(client, "admin@acme.com")
    good = client.patch(
        "/organizations/me/settings", json={"commodity_rules": ACME_RULES}, headers=headers
    )
    assert good.status_code == 200, good.text
    bad = [dict(ACME_RULES[0], commodity_group_id=999999)]
    r = client.patch("/organizations/me/settings", json={"commodity_rules": bad}, headers=headers)
    assert r.status_code == 422


def test_reason_is_optional_but_keywords_are_not(client):
    headers = _token(client, "admin@acme.com")
    bare = {"keywords": ["cable tie"], "commodity_group_id": ELECTRICAL_ENGINEERING}
    r = client.patch(
        "/organizations/me/settings", json={"commodity_rules": [bare]}, headers=headers
    )
    assert r.status_code == 200, r.text
    saved = client.get("/organizations/me/settings", headers=headers).json()
    assert _as_written(saved["commodity_rules"]) == [dict(bare, reason="")]

    for keywords in ([], [""], ["  "]):
        empty = dict(bare, keywords=keywords)
        r = client.patch(
            "/organizations/me/settings", json={"commodity_rules": [empty]}, headers=headers
        )
        assert r.status_code == 422, keywords


def test_saving_required_fields_keeps_rules(client):
    headers = _token(client, "admin@acme.com")
    client.patch(
        "/organizations/me/settings", json={"commodity_rules": ACME_RULES}, headers=headers
    )
    client.patch(
        "/organizations/me/settings", json={"required_fields": ["vat_id"]}, headers=headers
    )
    saved = client.get("/organizations/me/settings", headers=headers).json()
    assert saved["required_fields"] == ["vat_id"]
    assert _as_written(saved["commodity_rules"]) == ACME_RULES


def test_guard_buyer_cannot_change_settings(client):
    r = client.patch(
        "/organizations/me/settings",
        json={"commodity_rules": ACME_RULES},
        headers=_token(client, "buyer@acme.com"),
    )
    assert r.status_code == 403


def test_acme_rules_map_lines_to_acme_groups(client, db_session):
    from app.services.categorisation import categorise

    client.patch(
        "/organizations/me/settings",
        json={"commodity_rules": ACME_RULES},
        headers=_token(client, "admin@acme.com"),
    )
    acme = _org_id(db_session, "acme")
    with db_session() as s:
        assert categorise(s, acme, "Kabelbinder 200mm schwarz") == ELECTRICAL_ENGINEERING
        assert categorise(s, acme, "HP 305A toner black") == IT_HARDWARE
        assert categorise(s, acme, "Office chair") is None


def test_acme_rules_do_not_leak_to_another_company(client, db_session):
    from app.services.categorisation import categorise

    r = client.patch(
        "/organizations/me/settings",
        json={"commodity_rules": ACME_RULES},
        headers=_token(client, "admin@acme.com"),
    )
    assert r.status_code == 200, r.text

    walmart_headers = _token(client, "admin@walmart.com")
    walmart_settings = client.get("/organizations/me/settings", headers=walmart_headers).json()
    assert walmart_settings.get("commodity_rules", []) == []

    walmart = _org_id(db_session, "walmart")
    with db_session() as s:
        assert categorise(s, walmart, "Kabelbinder 200mm schwarz") is None
        assert categorise(s, walmart, "HP 305A toner black") is None

    r = client.patch(
        "/organizations/me/settings",
        json={"commodity_rules": [dict(ACME_RULES[1], commodity_group_id=TONER_CARTRIDGES)]},
        headers=walmart_headers,
    )
    assert r.status_code == 200, r.text
    acme = _org_id(db_session, "acme")
    with db_session() as s:
        assert categorise(s, acme, "HP 305A toner black") == IT_HARDWARE
        assert categorise(s, walmart, "HP 305A toner black") == TONER_CARTRIDGES


SOFTWARE_RULE = {
    "keywords": ["subscription", "abo", "abonnement"],
    "commodity_group_id": SOFTWARE,
    "reason": "Small software subscriptions, test data only",
    "max_amount": 50,
}


def _save_rules(client, rules, email="admin@acme.com"):
    r = client.patch(
        "/organizations/me/settings",
        json={"commodity_rules": rules},
        headers=_token(client, email),
    )
    assert r.status_code == 200, r.text
    return r.json()["commodity_rules"]


def test_server_sets_rule_id_and_who_and_when(client):
    saved = _save_rules(client, ACME_RULES)
    ids = [rule["id"] for rule in saved]
    assert all(ids) and len(set(ids)) == 2
    assert {rule["updated_by"] for rule in saved} == {"admin@acme.com"}
    assert all(rule["updated_at"] for rule in saved)
    assert [rule["max_amount"] for rule in saved] == [None, None]


def test_rule_id_never_changes_and_untouched_rules_keep_their_stamp(client):
    first = _save_rules(client, ACME_RULES)
    edited = [dict(first[0]), dict(first[1], keywords=["toner", "druckerpatrone"])]
    edited[0]["updated_by"] = "someone@else.com"
    second = _save_rules(client, list(reversed(edited)))
    by_id = {rule["id"]: rule for rule in second}
    assert set(by_id) == {first[0]["id"], first[1]["id"]}
    assert by_id[first[0]["id"]] == first[0]
    assert by_id[first[1]["id"]]["keywords"] == ["toner", "druckerpatrone"]
    assert by_id[first[1]["id"]]["updated_at"] >= first[1]["updated_at"]
    assert [rule["id"] for rule in second] == [first[1]["id"], first[0]["id"]]


def test_rule_id_from_nowhere_is_rejected(client):
    headers = _token(client, "admin@acme.com")
    for rules in (
        [dict(ACME_RULES[0], id="r_made_up")],
        [dict(ACME_RULES[0], id="r_same"), dict(ACME_RULES[1], id="r_same")],
    ):
        r = client.patch(
            "/organizations/me/settings", json={"commodity_rules": rules}, headers=headers
        )
        assert r.status_code == 422, rules
    first = _save_rules(client, ACME_RULES)
    twice = [dict(ACME_RULES[0], id=first[0]["id"]), dict(ACME_RULES[1], id=first[0]["id"])]
    r = client.patch("/organizations/me/settings", json={"commodity_rules": twice}, headers=headers)
    assert r.status_code == 422


def test_max_amount_must_be_positive_and_keywords_must_have_letters(client):
    headers = _token(client, "admin@acme.com")
    for rule in (
        dict(SOFTWARE_RULE, max_amount=0),
        dict(SOFTWARE_RULE, max_amount=-5),
        dict(SOFTWARE_RULE, keywords=["--"]),
    ):
        r = client.patch(
            "/organizations/me/settings", json={"commodity_rules": [rule]}, headers=headers
        )
        assert r.status_code == 422, rule
    saved = _save_rules(client, [SOFTWARE_RULE])
    assert saved[0]["max_amount"] == 50


MATCHING_CASES = [
    ("Kabelbinder 200mm schwarz", ELECTRICAL_ENGINEERING),
    ("KABELBINDER-SET 100 Stk.", ELECTRICAL_ENGINEERING),
    ("Nylonkabelbinder UV-beständig", ELECTRICAL_ENGINEERING),
    ("Cable ties, black, 200 mm", ELECTRICAL_ENGINEERING),
    ("cable-tie mounts", ELECTRICAL_ENGINEERING),
    ("Kabeltrommel 50m", None),
    ("cable drum 50m", None),
    ("tie for the cable", None),
    ("HP 305A toner black", IT_HARDWARE),
    ("Tonerkartusche HP 305A", IT_HARDWARE),
    ("Druckertoner schwarz", IT_HARDWARE),
    ("TONER", IT_HARDWARE),
    ("HP LaserJet printer", None),
    ("Drucker", None),
    ("Office chair", None),
    ("", None),
]


@pytest.mark.parametrize("text, expected", MATCHING_CASES)
def test_keywords_match_german_and_english(client, db_session, text, expected):
    from app.services.categorisation import categorise

    _save_rules(client, ACME_RULES)
    with db_session() as s:
        assert categorise(s, _org_id(db_session, "acme"), text) == expected


def test_umlauts_and_eszett_match_either_spelling(client, db_session):
    from app.services.categorisation import categorise

    _save_rules(
        client,
        [
            {"keywords": ["Drucker-Zubehör"], "commodity_group_id": IT_HARDWARE},
            {"keywords": ["Maßband"], "commodity_group_id": ELECTRICAL_ENGINEERING},
        ],
    )
    acme = _org_id(db_session, "acme")
    with db_session() as s:
        assert categorise(s, acme, "Drucker Zubehoer Set") == IT_HARDWARE
        assert categorise(s, acme, "DRUCKER-ZUBEHÖR") == IT_HARDWARE
        assert categorise(s, acme, "Zubehör für Drucker") is None
        assert categorise(s, acme, "MASSBAND 5m") == ELECTRICAL_ENGINEERING
        assert categorise(s, acme, "Maßbandhalter") == ELECTRICAL_ENGINEERING


def test_short_keywords_match_the_whole_word_only(client, db_session):
    from app.services.categorisation import categorise

    _save_rules(client, [dict(SOFTWARE_RULE, max_amount=None)])
    acme = _org_id(db_session, "acme")
    with db_session() as s:
        assert categorise(s, acme, "Software-Abo monatlich") == SOFTWARE
        assert categorise(s, acme, "Notion team plan, monthly subscription") == SOFTWARE
        assert categorise(s, acme, "Jahresabonnement Adobe") == SOFTWARE
        assert categorise(s, acme, "Kabo Schrank") is None
        assert categorise(s, acme, "Abort-Ventil") is None
        assert categorise(s, acme, "ERP licence 2026") is None


def test_max_amount_only_hits_lines_at_or_under_it(client, db_session):
    from app.services.categorisation import categorise

    _save_rules(client, [SOFTWARE_RULE])
    acme = _org_id(db_session, "acme")
    with db_session() as s:
        assert categorise(s, acme, "Notion subscription", 12.0) == SOFTWARE
        assert categorise(s, acme, "Notion subscription", 50.0) == SOFTWARE
        assert categorise(s, acme, "SAP subscription", 25000.0) is None
        assert categorise(s, acme, "Notion subscription") is None


def test_two_rules_on_one_line_first_in_the_list_wins(client, db_session):
    from app.services.categorisation import categorise

    acme = _org_id(db_session, "acme")
    line = "Kabelbinder und Toner Paket"
    _save_rules(client, ACME_RULES)
    with db_session() as s:
        assert categorise(s, acme, line) == ELECTRICAL_ENGINEERING
    _save_rules(client, list(reversed(ACME_RULES)))
    with db_session() as s:
        assert categorise(s, acme, line) == IT_HARDWARE


def test_seed_gives_acme_only_the_cable_tie_rule(client, db_session):
    from app.services.categorisation import categorise

    with db_session() as s:
        seed(s)
    acme = _org_id(db_session, "acme")
    walmart = _org_id(db_session, "walmart")
    rules = client.get(
        "/organizations/me/settings", headers=_token(client, "admin@acme.com")
    ).json()["commodity_rules"]
    assert [rule["commodity_group_id"] for rule in rules] == [ELECTRICAL_ENGINEERING]
    with db_session() as s:
        assert categorise(s, acme, "Kabelbinder 200mm") == ELECTRICAL_ENGINEERING
        assert categorise(s, acme, "HP 305A toner") is None
        assert categorise(s, walmart, "Kabelbinder 200mm") is None
        seed(s)
    again = client.get(
        "/organizations/me/settings", headers=_token(client, "admin@acme.com")
    ).json()["commodity_rules"]
    assert again == rules
