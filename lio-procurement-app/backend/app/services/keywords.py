import re
import unicodedata

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_SHORT = 4


def words(text: str) -> list[str]:
    folded = (text or "").lower().translate(_UMLAUTS)
    ascii_only = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_only).split()


def keyword_hits(keyword: str, text_words: list[str]) -> bool:
    wanted = words(keyword)
    if not wanted:
        return False
    if len(wanted) == 1:
        single = wanted[0]
        if len(single) < _SHORT:
            return single in text_words
        return any(word.startswith(single) or word.endswith(single) for word in text_words)
    span = len(wanted)
    return any(
        all(text_words[start + offset].startswith(part) for offset, part in enumerate(wanted))
        for start in range(len(text_words) - span + 1)
    )
