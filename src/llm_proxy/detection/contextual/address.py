import re
from collections.abc import Collection, Sequence

from llm_proxy.detection.contextual.common import (
    CYR,
    CYR_LOWER,
    CYR_UPPER,
    G_DOT,
    confirmed,
    trim_span,
)
from llm_proxy.detection.models import Detection, PiiType

_PERSONAL = re.compile(
    r"адрес регистрации|адрес проживания|адрес клиента|адрес доставки|домашний адрес|"
    r"прожива(?:ет|ю)",
    re.IGNORECASE,
)
_GENERIC_ADDRESS = re.compile(
    rf"(?<![A-Za-z{CYR}])адрес(?:\u0430|\u0443|\u0435)?\s*:",
    re.IGNORECASE,
)
_DELIVERY = re.compile(r"достав|получател", re.IGNORECASE)
_ORG = re.compile(r"банк|отделен|филиал|офис", re.IGNORECASE)
_LABELED_COMPONENT = re.compile(
    r"(?:страна|индекс|город|улица|дом|квартира)\s*:",
    re.IGNORECASE,
)
_INDEX_LABELED = re.compile(
    rf"(?<![A-Za-z{CYR}])индекс\s*[:\s]\s*(?P<code>\d{{6}})(?!\d)",
    re.IGNORECASE,
)
_HOUSE_OR_UNIT = re.compile(
    rf"(?<![{CYR}])(?:\u0434\.|дом|кв\.|квартира)\b",
    re.IGNORECASE,
)
_ABBREV_DOT = frozenset({"\u0433", "\u0443\u043b", "\u0434", "\u043a\u0432"})
_BARE_LABEL_STOP = re.compile(
    rf"(?<![A-Za-z{CYR}])(?:индекс|получател|телефон|контактн|email|e-mail|фио)\b",
    re.IGNORECASE,
)
_BARE_NAME = rf"[{CYR_UPPER}][{CYR_LOWER}-]+(?:[ \t]+[{CYR_UPPER}][{CYR_LOWER}-]+)*"
_BARE_SEGMENT = re.compile(_BARE_NAME)
_SKIP_SEGMENT = re.compile(
    r"^(?:\u0434\.|дом|кв\.|квартира|индекс)\b",
    re.IGNORECASE,
)
_SKIP_BARE = frozenset(
    {
        "россия",
        "рф",
        "республика",
        "область",
        "край",
        "район",
        "город",
        "улица",
        "проспект",
        "переулок",
        "индекс",
        "адрес",
        "дом",
        "квартира",
        "получатель",
        "доставка",
        "служба",
    }
)
_CLAUSE_LIMIT = 160
_POSTAL_CITY = re.compile(rf"(?<!\d)\d{{6}}\s*,\s*(?P<city>[{CYR_UPPER}][{CYR_LOWER}-]+)(?=\s*,)")
_PARTS: tuple[tuple[PiiType, re.Pattern[str]], ...] = (
    (PiiType.ADDRESS_POSTAL_CODE, re.compile(r"(?<!\d)\d{6}(?!\d)")),
    (
        PiiType.ADDRESS_COUNTRY,
        re.compile(
            rf"(?<![0-9A-Za-z{CYR}])(?:Россия|РФ|"
            rf"[{CYR_UPPER}][{CYR_LOWER}-]+\s+Республика|"
            rf"Республика\s+[{CYR_UPPER}][{CYR_LOWER}-]+)(?![0-9A-Za-z{CYR}])"
        ),
    ),
    (
        PiiType.ADDRESS_REGION,
        re.compile(rf"(?<![{CYR}])[{CYR_UPPER}][{CYR_LOWER}]+\s+(?:область|край)(?![{CYR}])"),
    ),
    (
        PiiType.ADDRESS_DISTRICT,
        re.compile(
            rf"(?<![{CYR}])[{CYR_UPPER}][{CYR_LOWER}]+\s+(?:район|\u0440-\u043d)(?![{CYR}])"
        ),
    ),
    (
        PiiType.ADDRESS_CITY,
        re.compile(
            rf"(?<![{CYR}])(?:{G_DOT}|город)\s*{_BARE_NAME}",
            re.IGNORECASE,
        ),
    ),
    (
        PiiType.ADDRESS_STREET,
        re.compile(
            rf"(?<![{CYR}])(?:ул\.|улица)\s*{_BARE_NAME}",
            re.IGNORECASE,
        ),
    ),
    (
        PiiType.ADDRESS_BUILDING,
        re.compile(
            rf"(?<![{CYR}])(?:\u0434\.|дом)\s*(?P<value>\d+[0-9A-Za-z{CYR}]?)",
            re.IGNORECASE,
        ),
    ),
    (
        PiiType.ADDRESS_UNIT,
        re.compile(
            rf"(?<![{CYR}])(?:кв\.|квартира)\s*(?P<value>\d+)",
            re.IGNORECASE,
        ),
    ),
)


class AddressDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        enabled = frozenset(enabled_types)
        component_types = {pii_type for pii_type, _pattern in _PARTS}
        want_components = bool(enabled & component_types)
        want_address = PiiType.ADDRESS in enabled
        if not want_components and not want_address:
            return ()

        found: list[Detection] = []
        anchors = list(_PERSONAL.finditer(text))
        for anchor in _GENERIC_ADDRESS.finditer(text):
            prefix = text[max(0, anchor.start() - _CLAUSE_LIMIT) : anchor.start()]
            if _DELIVERY.search(prefix):
                anchors.append(anchor)

        for anchor in sorted(anchors, key=lambda item: item.start()):
            clause_start = anchor.end()
            while clause_start < len(text) and text[clause_start] in " \t:—-":
                clause_start += 1
            clause_end = min(len(text), clause_start + _CLAUSE_LIMIT)
            clause = text[clause_start:clause_end]
            if _ORG.search(clause):
                continue
            parts = _components(clause, clause_start)
            _extend_labeled_postal(text, anchor.start(), clause_end, parts)
            _extend_bare_city_street(clause, clause_start, parts)
            if want_components:
                found.extend(
                    confirmed(pii_type, start, end, "address")
                    for pii_type, start, end in parts
                    if pii_type in enabled
                )
            elif want_address and parts:
                start = min(item[1] for item in parts)
                end = max(item[2] for item in parts)
                start, end = trim_span(text, start, end)
                found.append(confirmed(PiiType.ADDRESS, start, end, "address", confidence=0.8))
        return tuple(found)


def _span_overlaps(start: int, end: int, found: list[tuple[PiiType, int, int]]) -> bool:
    return any(start < item_end and item_start < end for _type, item_start, item_end in found)


def _components(clause: str, offset: int) -> list[tuple[PiiType, int, int]]:
    found: list[tuple[PiiType, int, int]] = []
    for pii_type, pattern in _PARTS:
        for match in pattern.finditer(clause):
            if "value" in match.re.groupindex:
                raw_start, raw_end = match.start("value"), match.end("value")
            else:
                raw_start, raw_end = match.start(), match.end()
            start, end = trim_span(clause, raw_start, raw_end)
            if end > start and not _span_overlaps(offset + start, offset + end, found):
                found.append((pii_type, offset + start, offset + end))

    bare_city = _POSTAL_CITY.search(clause)
    if bare_city is not None:
        city_start = offset + bare_city.start("city")
        city_end = offset + bare_city.end("city")
        if not _span_overlaps(city_start, city_end, found):
            found.append((PiiType.ADDRESS_CITY, city_start, city_end))
    return found


def _extend_labeled_postal(
    text: str,
    anchor_start: int,
    clause_end: int,
    found: list[tuple[PiiType, int, int]],
) -> None:
    window_start = max(0, anchor_start - _CLAUSE_LIMIT)
    window_end = min(len(text), clause_end + _CLAUSE_LIMIT)
    window = text[window_start:window_end]
    if "индекс" not in window.casefold():
        return
    for match in _INDEX_LABELED.finditer(text, window_start, window_end):
        start, end = match.start("code"), match.end("code")
        if not _span_overlaps(start, end, found):
            found.append((PiiType.ADDRESS_POSTAL_CODE, start, end))


def _extend_bare_city_street(
    clause: str,
    offset: int,
    found: list[tuple[PiiType, int, int]],
) -> None:
    if _LABELED_COMPONENT.search(clause) is not None:
        return
    has_house_or_unit = any(
        pii_type in {PiiType.ADDRESS_BUILDING, PiiType.ADDRESS_UNIT} for pii_type, _s, _e in found
    )
    if not has_house_or_unit and _HOUSE_OR_UNIT.search(clause) is None:
        return

    has_city = any(pii_type == PiiType.ADDRESS_CITY for pii_type, _s, _e in found)
    has_street = any(pii_type == PiiType.ADDRESS_STREET for pii_type, _s, _e in found)
    if has_city and has_street:
        return

    region_end = _bare_region_end(clause)
    region = clause[:region_end]
    candidates: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(region):
        next_comma = region.find(",", cursor)
        seg_end = len(region) if next_comma < 0 else next_comma
        raw = region[cursor:seg_end]
        local_start = 0
        while local_start < len(raw) and raw[local_start] in " \t":
            local_start += 1
        local_end = len(raw)
        while local_end > local_start and raw[local_end - 1] in " \t":
            local_end -= 1
        segment = raw[local_start:local_end]
        abs_start = offset + cursor + local_start
        abs_end = offset + cursor + local_end
        cursor = seg_end + 1 if next_comma >= 0 else len(region)
        if not segment or _HOUSE_OR_UNIT.match(segment) is not None:
            continue
        if _SKIP_SEGMENT.match(segment) is not None:
            continue
        if _BARE_SEGMENT.fullmatch(segment) is None:
            continue
        if _span_overlaps(abs_start, abs_end, found):
            continue
        first = segment.split(None, 1)[0].casefold()
        if first in _SKIP_BARE:
            continue
        candidates.append((abs_start, abs_end))

    if not has_city and candidates:
        start, end = candidates.pop(0)
        found.append((PiiType.ADDRESS_CITY, start, end))
    if not has_street and candidates:
        start, end = candidates.pop(0)
        found.append((PiiType.ADDRESS_STREET, start, end))


def _bare_region_end(clause: str) -> int:
    """Stop bare city/street search at sentence end or the next field label."""
    candidates = [len(clause)]
    for match in re.finditer(rf"\.(?=\s+[{CYR_UPPER}A-Z]|\s*$)|;", clause):
        if match.group(0) == ";" or not _is_abbreviation_dot(clause, match.start()):
            candidates.append(match.start())
    for match in _BARE_LABEL_STOP.finditer(clause):
        candidates.append(match.start())
    return min(candidates)


def _is_abbreviation_dot(text: str, dot_pos: int) -> bool:
    """True for city/street/house abbreviations so dots are not sentence ends."""
    start = dot_pos
    while start > 0 and dot_pos - start < 3:
        ch = text[start - 1]
        if not (ch.isascii() and ch.isalpha()) and not ("\u0400" <= ch <= "\u04ff"):
            break
        start -= 1
    return text[start:dot_pos].casefold() in _ABBREV_DOT
