import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.data.articles import ARTICLES
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import RequestActivity
from app.seed import seed
from app.services import catalogue_search as cs
from evals.search.score import outcome, summarise

DESCRIPTIONS = sorted({a["description"] for a in ARTICLES})


@pytest.fixture(scope="module")
def catalogue():
    return cs.Catalogue(DESCRIPTIONS)


def _suggest(catalogue, text):
    return cs.sure(cs.rank(catalogue, text, method="words"), method="words")


def test_words_fold_case_umlauts_and_symbols():
    assert cs.tokens("Feuerlöscher 5 kg CO₂") == ["fire", "extinguisher", "5", "kg", "co", "2"]
    assert cs.tokens("Stainless steel bolt M8×30 A2") == cs.tokens("stainless steel bolt m8x30 a2")


def test_german_words_and_compounds_map_to_english(catalogue):
    assert cs.tokens("Toner schwarz") == ["toner", "black"]
    assert cs.tokens("Sicherheitshandschuhe", catalogue.known) == ["safety", "glove"]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Toner schwarz XL", "Toner cartridge black, high-yield"),
        ("Kugellager 6205 2RS", "Ball bearing 6205-2RS"),
        ("Edelstahlschrauben M8x30 A2", "Stainless steel bolt M8×30 A2"),
    ],
)
def test_a_clear_request_gets_one_sure_match(catalogue, text, expected):
    assert _suggest(catalogue, text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Kugellager 6204-2RS",
        "Fire extinguisher 2 kg CO2",
        "Toner cartridge green",
        "Kabelbinder 200mm schwarz",
        "Bürostuhl",
        "Laptop",
        "",
        "   ",
    ],
)
def test_near_misses_off_catalogue_and_ambiguous_get_nothing(catalogue, text):
    assert _suggest(catalogue, text) is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Handschuhe Nitril", "Safety gloves nitrile-coated"),
        ("Kopierpapier A4", "Copy paper A4 recycled 80 g"),
        ("monitor 1440p", "24-inch monitor 1440p IPS"),
    ],
)
def test_a_likely_match_is_suggested_because_switching_is_by_hand(catalogue, text, expected):
    assert _suggest(catalogue, text) == expected


def test_an_empty_catalogue_never_suggests():
    empty = cs.Catalogue([])
    assert cs.rank(empty, "Toner schwarz XL") == []
    assert cs.sure([], method="words") is None


def test_search_ranks_best_first_and_respects_the_limit(catalogue):
    found = cs.search(catalogue, "toner", limit=3)
    assert len(found) == 3
    assert all(d.startswith("Toner cartridge") for d in found)
    assert cs.search(catalogue, "", limit=5) == []


def test_embeddings_fall_back_to_words_without_a_key(catalogue, monkeypatch):
    monkeypatch.setattr(cs.settings, "openai_api_key", None)
    assert cs.rank(catalogue, "Toner schwarz XL", method="embeddings") == cs.rank(
        catalogue, "Toner schwarz XL", method="words"
    )


def _offer(number, supplier, price, unit="piece"):
    return {
        "article_number": number,
        "description": "Ball bearing 6202-2RS",
        "supplier_name": supplier,
        "unit": unit,
        "unit_price": price,
        "currency": "EUR",
    }


OFFERS = [
    _offer("A-1", "Osterhaus Technik GmbH & Co. KG", 56.70),
    _offer("B-1", "Lindqvist Technik Ltd", 6.78),
    _offer("C-1", "Kranz Labs AG", 9.10),
]


def test_without_a_vendor_the_cheapest_article_wins():
    assert cs.pick_article(OFFERS)["article_number"] == "B-1"


def test_the_requests_vendor_wins_when_it_sells_the_article():
    assert cs.pick_article(OFFERS, vendor="Osterhaus Technik")["article_number"] == "A-1"
    assert cs.pick_article(OFFERS, vendor="osterhaus technik gmbh & co kg")["article_number"] == "A-1"


def test_an_unknown_vendor_falls_back_to_the_cheapest():
    assert cs.pick_article(OFFERS, vendor="Somebody Else GmbH")["article_number"] == "B-1"


def test_the_cheapest_is_taken_within_one_unit():
    offers = [*OFFERS, _offer("D-1", "Cheap Box GmbH", 1.00, unit="pack")]
    assert cs.pick_article(offers, unit="piece")["article_number"] == "B-1"
    assert cs.pick_article(offers)["article_number"] == "B-1"
    assert cs.pick_article(offers, unit="pack")["article_number"] == "D-1"


def test_no_articles_picks_nothing():
    assert cs.pick_article([]) is None


def test_eval_outcomes():
    assert outcome("A", "A") == "right"
    assert outcome("A", "B") == "wrong_sure"
    assert outcome(None, "B") == "wrong_sure"
    assert outcome("A", None) == "missed"
    assert outcome(None, None) == "correct_nothing"
    summary = summarise([
        {"expected": "A", "outcome": "right", "top5": True, "seconds": 0.001},
        {"expected": None, "outcome": "wrong_sure", "top5": None, "seconds": 0.003},
    ])
    assert summary["right"] == 1 and summary["wrong_sure"] == 1 and summary["top5"] == 1


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
def client(db_session, monkeypatch):
    monkeypatch.setattr(cs.settings, "openai_api_key", None)

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


def _token(client, email):
    r = client.post("/auth/signin", json={"email": email, "password": "demo1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


SHAPE = {"article_number", "description", "supplier_name", "unit", "unit_price", "currency"}


def _toner_offers():
    return [a for a in ARTICLES if a["description"] == "Toner cartridge black, high-yield"]


def test_suggest_returns_the_cheapest_sure_article(client):
    r = client.get(
        "/articles/suggest", params={"q": "Toner schwarz XL"},
        headers=_token(client, "requester@acme.com"),
    )
    assert r.status_code == 200, r.text
    match = r.json()["match"]
    assert set(match) == SHAPE
    cheapest = min(_toner_offers(), key=lambda a: a["unit_price"])
    assert match["article_number"] == cheapest["article_number"]
    assert match["description"] == "Toner cartridge black, high-yield"
    assert isinstance(match["unit_price"], float)
    assert match["unit_price"] == cheapest["unit_price"]


def test_suggest_prefers_the_requests_vendor(client):
    offers = sorted(_toner_offers(), key=lambda a: a["unit_price"])
    priciest = offers[-1]
    r = client.get(
        "/articles/suggest",
        params={"q": "Toner schwarz XL", "vendor": priciest["supplier_name"]},
        headers=_token(client, "buyer@acme.com"),
    )
    assert r.json()["match"]["article_number"] == priciest["article_number"]


def test_suggest_off_catalogue_is_null(client):
    r = client.get(
        "/articles/suggest", params={"q": "Kabelbinder 200mm"},
        headers=_token(client, "requester@acme.com"),
    )
    assert r.status_code == 200
    assert r.json() == {"match": None}


def test_another_company_never_sees_acme_articles(client):
    headers = _token(client, "admin@walmart.com")
    r = client.get("/articles/suggest", params={"q": "Toner schwarz XL"}, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"match": None}
    r = client.get("/articles/search", params={"q": "toner"}, headers=headers)
    assert r.json() == {"items": []}


def test_search_dedupes_by_description_and_ranks_best_first(client):
    r = client.get(
        "/articles/search", params={"q": "Toner schwarz", "limit": 5},
        headers=_token(client, "requester@acme.com"),
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert 1 <= len(items) <= 5
    assert items[0]["description"] == "Toner cartridge black, high-yield"
    assert len({i["description"] for i in items}) == len(items)
    assert all(set(i) == SHAPE for i in items)


def test_suggest_and_search_need_a_sign_in(client):
    assert client.get("/articles/suggest", params={"q": "toner"}).status_code == 401
    assert client.get("/articles/search", params={"q": "toner"}).status_code == 401


def test_existing_article_routes_still_work(client):
    headers = _token(client, "requester@acme.com")
    assert client.get("/articles/count", headers=headers).json() == {"count": len(ARTICLES)}
    r = client.get("/articles", params={"search": "toner"}, headers=headers)
    assert r.status_code == 200 and r.json()["total"] > 0


def _payload(lines):
    return {
        "requestorName": "Rene Requester",
        "titleShortDescription": "Toner",
        "vendorName": "Lindqvist Supply B.V.",
        "commodityGroupId": 15,
        "totalCost": sum(line["totalPrice"] for line in lines),
        "department": "IT",
        "orderLines": lines,
    }


def _line(text, price, catalog=None):
    line = {
        "positionDescription": text,
        "unitPrice": price,
        "amount": 1,
        "unit": "piece",
        "totalPrice": price,
    }
    if catalog is not None:
        line["catalog"] = catalog
    return line


def _created_detail(db_session, request_id):
    with db_session() as s:
        row = s.scalar(
            select(RequestActivity).where(
                RequestActivity.request_id == uuid.UUID(request_id),
                RequestActivity.action == "created"
            )
        )
        return row.detail


def test_catalog_choices_are_logged_per_line_on_create(client, db_session):
    switched = {
        "status": "switched", "article_number": "LIN-00862",
        "offer_price": 240.0, "catalog_price": 186.0,
    }
    no_match = {"status": "no_match", "article_number": None,
                "offer_price": None, "catalog_price": None}
    r = client.post(
        "/requests",
        json=_payload([
            _line("Toner schwarz XL", 186.0, switched),
            _line("Kabelbinder", 5.0),
            _line("Something odd", 7.0, no_match),
        ]),
        headers=_token(client, "requester@acme.com"),
    )
    assert r.status_code == 201, r.text
    assert all("catalog" not in line for line in r.json()["order_lines"])
    detail = _created_detail(db_session, r.json()["id"])
    assert detail["catalog"] == [
        {"line": 1, **switched},
        {"line": 3, **no_match},
    ]


def test_a_payload_without_catalog_still_works(client, db_session):
    r = client.post(
        "/requests",
        json=_payload([_line("Toner schwarz XL", 240.0)]),
        headers=_token(client, "requester@acme.com"),
    )
    assert r.status_code == 201, r.text
    assert "catalog" not in _created_detail(db_session, r.json()["id"])


def test_an_unknown_catalog_status_is_rejected(client):
    r = client.post(
        "/requests",
        json=_payload([_line("Toner", 1.0, {"status": "maybe", "article_number": None,
                                            "offer_price": None, "catalog_price": None})]),
        headers=_token(client, "requester@acme.com"),
    )
    assert r.status_code == 422
