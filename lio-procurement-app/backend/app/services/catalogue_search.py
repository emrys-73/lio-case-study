from __future__ import annotations

import logging
import math
import re
from collections import Counter

from app.core.config import settings
from app.services.keywords import words

log = logging.getLogger(__name__)

METHODS = ("words", "embeddings")
SHIPPED = "words"
SURE = {
    "words": {"threshold": 0.48, "margin": 0.05},
    "embeddings": {"threshold": 0.4, "margin": 0.17},
}
UNKNOWN_WEIGHT = 1.0

GERMAN = {
    "schwarz": "black", "weiss": "white", "gelb": "yellow", "blau": "blue", "rot": "red",
    "gruen": "green", "grau": "grey", "xl": "high yield", "hy": "high yield",
    "patrone": "cartridge", "kartusche": "cartridge", "tonerkartusche": "toner cartridge",
    "drucker": "printer", "kopierpapier": "copy paper", "druckerpapier": "copy paper",
    "papier": "paper", "recycling": "recycled", "recycelt": "recycled", "blatt": "sheet",
    "kugellager": "ball bearing", "rillenkugellager": "ball bearing", "lager": "bearing",
    "handschuh": "glove", "handschuhe": "glove", "sicherheit": "safety",
    "schutzhandschuhe": "safety glove", "arbeitshandschuhe": "safety glove",
    "nitril": "nitrile", "beschichtet": "coated", "schnittschutz": "cut resistant",
    "hitzebestaendig": "heat resistant", "edelstahl": "stainless steel", "stahl": "steel",
    "schraube": "bolt", "schrauben": "bolt", "bolzen": "bolt", "screw": "bolt",
    "europalette": "euro pallet", "palette": "pallet", "neu": "new", "gebraucht": "used",
    "kunststoff": "plastic", "stretchfolie": "stretch film", "folie": "film",
    "luftpolsterfolie": "bubble wrap", "luftpolster": "bubble", "my": "um", "mu": "um",
    "mikron": "um", "micron": "um", "dockingstation": "docking station",
    "feuerloescher": "fire extinguisher", "pulver": "powder", "schaum": "foam",
    "buerostuhl": "office chair", "stuhl": "chair", "buero": "office",
    "ergonomisch": "ergonomic", "netzruecken": "mesh", "netz": "mesh", "leder": "leather",
    "magnetisch": "magnetic", "kabel": "cable", "patchkabel": "patch cable",
    "netzwerk": "network", "tastatur": "keyboard", "maus": "mouse", "kabellos": "wireless",
    "funk": "wireless", "motoroel": "engine oil", "oel": "oil",
    "vollsynthetisch": "synthetic", "synthetisch": "synthetic",
    "teilsynthetisch": "semi synthetic", "winterreifen": "winter tyre",
    "sommerreifen": "summer tyre", "ganzjahresreifen": "all season tyre", "reifen": "tyre",
    "tire": "tyre", "ordner": "ring binder", "aktenordner": "ring binder",
    "hydraulikzylinder": "hydraulic cylinder", "hydraulik": "hydraulic",
    "zylinder": "cylinder", "bohrung": "bore", "hub": "stroke", "kabelbinder": "cable tie",
    "bildschirm": "monitor", "klebeband": "adhesive tape", "paketband": "adhesive tape",
    "karton": "box", "versandkarton": "corrugated box", "etikett": "label",
    "etiketten": "label", "versandetiketten": "shipping label", "haftnotizen": "sticky note",
    "postit": "sticky note", "akkuschrauber": "cordless drill", "bohrmaschine": "drill",
    "akku": "cordless", "werkstattwagen": "tool trolley", "arbeitsleuchte": "work light",
    "leuchte": "light", "lampe": "light", "verbandskasten": "first aid kit",
    "fussmatte": "floor mat", "matte": "mat", "notebook": "laptop",
    "uebersetzung": "translation", "wort": "word", "schulung": "training workshop",
    "beratung": "consulting", "reinigung": "cleaning", "kugelschreiber": "ballpoint pen",
    "stift": "pen", "kaffee": "coffee", "bohnen": "bean", "bleistift": "pencil",
    "bleistifte": "pencil", "gsm": "g", "liter": "litre", "ltr": "litre",
    "lieferung": "delivery", "versand": "shipping", "paket": "parcel",
    "lagerung": "storage", "solarmodul": "solar panel", "waermepumpe": "heat pump",
    "ladestation": "charging station", "wallbox": "wallbox", "zange": "plier",
    "werkzeug": "tool", "spruehdose": "spray", "schmiermittel": "lubricant",
    "klebstoff": "adhesive", "kleber": "adhesive", "loesungsmittel": "solvent",
    "aceton": "acetone", "verpackung": "packaging", "holzkiste": "wooden crate",
    "kiste": "crate", "umreifungsband": "strapping", "scheibenwischer": "windscreen wiper",
    "bremsbelaege": "brake pad", "bremsbelag": "brake pad", "vorne": "front",
    "hinten": "rear", "epoxid": "epoxy", "epoxidkleber": "epoxy adhesive",
    "upm": "rpm", "industrie": "industrial", "elektromotor": "motor", "lizenz": "licence", "license": "licence", "jaehrlich": "annual",
}
PHRASES = {
    "post it": "sticky note", "erste hilfe": "first aid", "pro wort": "per word",
    "u min": "rpm", "power delivery": "pd", "2 k": "2 component",
}
STOP = {
    "and", "und", "mit", "with", "for", "fuer", "the", "der", "die", "das", "ein", "eine",
    "x", "per", "pro", "stk", "stueck", "st", "pcs", "pc", "inch", "zoll", "gr", "groesse",
    "size", "of", "von", "fur", "stunden", "stunde", "std", "hour", "hours", "ca", "inkl", "kanister",
}


def _stem(token: str) -> str:
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _raw(text: str) -> list[str]:
    text = (text or "").replace("×", " x ").replace("µ", "u").replace("μ", "u")
    joined = " ".join(words(text))
    joined = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", joined)
    joined = f" {joined} "
    for phrase, english in PHRASES.items():
        joined = joined.replace(f" {phrase} ", f" {english} ")
    return joined.split()


def _split_compound(token: str, known: set[str], depth: int = 0) -> list[str] | None:
    if token in GERMAN:
        return GERMAN[token].split()
    if token in known:
        return [token]
    if depth >= 2:
        return None
    for cut in range(len(token) - 3, 2, -1):
        head, tail = token[:cut], token[cut:]
        for left in (head, head[:-1] if head.endswith("s") else None):
            if not left or len(left) < 3 or (left not in GERMAN and left not in known):
                continue
            rest = _split_compound(tail, known, depth + 1)
            if rest:
                return [*(GERMAN.get(left, left).split()), *rest]
    return None


def tokens(text: str, known: set[str] | None = None) -> list[str]:
    out: list[str] = []
    for raw in _raw(text):
        parts = GERMAN.get(raw, None)
        if parts is not None:
            pieces = parts.split()
        elif known is not None and raw.isalpha() and len(raw) > 7 and _stem(raw) not in known:
            pieces = _split_compound(raw, known) or [raw]
        else:
            pieces = [raw]
        out.extend(_stem(p) for p in pieces if p not in STOP)
    return [t for t in out if t not in STOP]


def _close(a: str, b: str) -> bool:
    if a == b:
        return True
    if not (a.isalpha() and b.isalpha()):
        return False
    short, long = sorted((a, b), key=len)
    if len(short) >= 4 and len(short) * 2 >= len(long) and long.startswith(short):
        return True
    if min(len(a), len(b)) >= 5 and abs(len(a) - len(b)) <= 1:
        return _one_edit(a, b)
    return False


def _one_edit(a: str, b: str) -> bool:
    if len(a) > len(b):
        a, b = b, a
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            edits += 1
            if edits > 1:
                return False
            if len(a) == len(b):
                i += 1
            j += 1
            continue
        i += 1
        j += 1
    return edits + (len(b) - j) + (len(a) - i) <= 1


class Catalogue:
    def __init__(self, descriptions: list[str]):
        self.descriptions = list(dict.fromkeys(descriptions))
        self.rows = [tokens(d) for d in self.descriptions]
        self.known = {t for row in self.rows for t in row}
        df = Counter(t for row in self.rows for t in set(row))
        n = max(len(self.rows), 1)
        self.idf = {t: math.log(1 + n / c) for t, c in df.items()}
        self.vectors: list[list[float]] | None = None

    def weight(self, token: str) -> float:
        return self.idf.get(token, UNKNOWN_WEIGHT)

    def score(self, query: list[str], row: list[str], partial: bool = False) -> float:
        free = list(row)
        matched = 0.0
        unmatched_query: list[str] = []
        named = False
        last = len(query) - 1
        for position, q in enumerate(query):
            hit = next((d for d in free if d == q), None)
            if hit is None:
                hit = next((d for d in free if _close(q, d)), None)
            if hit is None and partial and position == last and len(q) >= 2:
                hit = next((d for d in free if d.startswith(q)), None)
            if hit is None:
                unmatched_query.append(q)
                continue
            free.remove(hit)
            matched += self.weight(hit)
            named = named or (hit.isalpha() and len(hit) >= 3)
        if not named:
            return 0.0
        if any(t.isdigit() for t in unmatched_query) and any(t.isdigit() for t in free):
            return 0.0
        total = sum(self.weight(t) for t in row) + sum(self.weight(t) for t in unmatched_query)
        return matched / total if total else 0.0


def _rank_words(catalogue: Catalogue, text: str, partial: bool = False) -> list[tuple[str, float]]:
    query = tokens(text, catalogue.known)
    if not query or not catalogue.rows:
        return []
    scored = [
        (description, catalogue.score(query, row, partial))
        for description, row in zip(catalogue.descriptions, catalogue.rows)
    ]
    return sorted((s for s in scored if s[1] > 0), key=lambda s: -s[1])


def embedding_model() -> str:
    return settings.openai_embedding_model


def _embed(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key, timeout=5.0, max_retries=0)
    response = client.embeddings.create(model=embedding_model(), input=texts)
    return [item.embedding for item in response.data]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _rank_embeddings(catalogue: Catalogue, text: str) -> list[tuple[str, float]]:
    if not settings.openai_api_key:
        return _rank_words(catalogue, text)
    if not (text or "").strip() or not catalogue.descriptions:
        return []
    try:
        if catalogue.vectors is None:
            catalogue.vectors = _embed(catalogue.descriptions)
        query = _embed([text])[0]
    except Exception:
        log.warning("embedding search failed, using word match", exc_info=True)
        return _rank_words(catalogue, text)
    scored = [(d, _cosine(query, v)) for d, v in zip(catalogue.descriptions, catalogue.vectors)]
    return sorted(scored, key=lambda s: -s[1])


def rank(catalogue: Catalogue, text: str, method: str = SHIPPED) -> list[tuple[str, float]]:
    if method == "embeddings":
        return _rank_embeddings(catalogue, text)
    return _rank_words(catalogue, text)


def sure(
    ranked: list[tuple[str, float]],
    method: str = SHIPPED,
    threshold: float | None = None,
    margin: float | None = None,
) -> str | None:
    if not ranked:
        return None
    threshold = SURE[method]["threshold"] if threshold is None else threshold
    margin = SURE[method]["margin"] if margin is None else margin
    best, score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    if score >= threshold and score - runner_up >= margin:
        return best
    return None


def search(catalogue: Catalogue, text: str, limit: int = 5) -> list[str]:
    return [d for d, _ in _rank_words(catalogue, text, partial=True)[:limit]]


_LEGAL = {"gmbh", "ag", "co", "kg", "se", "ltd", "bv", "b", "v", "inc", "llc", "sa", "srl", "plc"}


def _company(name: str | None) -> set[str]:
    return {w for w in words(name or "") if w not in _LEGAL}


def _same_company(vendor: str | None, supplier: str | None) -> bool:
    a, b = _company(vendor), _company(supplier)
    return bool(a and b) and (a <= b or b <= a)


def pick_article(articles: list[dict], vendor: str | None = None, unit: str | None = None) -> dict | None:
    if not articles:
        return None
    if vendor:
        own = [a for a in articles if _same_company(vendor, a["supplier_name"])]
        if own:
            return min(own, key=lambda a: float(a["unit_price"]))
    wanted = (unit or "").strip().lower()
    units = Counter(a["unit"].lower() for a in articles)
    if wanted not in units:
        wanted = units.most_common(1)[0][0]
    same_unit = [a for a in articles if a["unit"].lower() == wanted]
    return min(same_unit, key=lambda a: float(a["unit_price"]))


_CACHE: dict[int, Catalogue] = {}


def catalogue_for(descriptions: list[str]) -> Catalogue:
    key = hash(tuple(sorted(descriptions)))
    if key not in _CACHE:
        if len(_CACHE) > 32:
            _CACHE.clear()
        _CACHE[key] = Catalogue(sorted(descriptions))
    return _CACHE[key]
