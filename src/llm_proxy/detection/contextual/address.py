# Cyrillic address markers; RUF001/RUF003 suppressed for marker literals.
# ruff: noqa: RUF001

import re
from collections.abc import Collection, Sequence

from llm_proxy.detection.contextual.common import (
    CYR,
    CYR_LOWER,
    CYR_UPPER,
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
# Organizational address is decided by the anchor phrase, not by later words like «банком».
_ORG_ANCHOR = re.compile(
    r"адрес\s+(?:банка|отделения|офиса|филиала)|"
    r"адрес\s+отделения\s+банка",
    re.IGNORECASE,
)
_LABELED_COMPONENT = re.compile(
    r"(?:страна|индекс|город|улица|дом|квартира)\s*:",
    re.IGNORECASE,
)
_INDEX_LABELED = re.compile(
    rf"(?<![A-Za-z{CYR}])индекс\s*[:\s]\s*(?P<code>\d{{6}})(?!\d)",
    re.IGNORECASE,
)
# Markers: case-insensitive via (?i:...), values stay case-flexible without IGNORECASE.
_CITY_MARK = r"(?i:г\.|город)"
_STREET_MARK = r"(?i:ул\.|улица|пр-т|проспект|пер\.|переулок|бул\.|бульвар|шоссе)"
_HOUSE_MARK = r"(?i:д\.|дом|корп\.|корпус|стр\.|строение)"
_UNIT_MARK = r"(?i:кв\.|квартира)"
_MARKER_TOKEN = (
    r"(?i:г|город|ул|улица|пр-т|проспект|пер|переулок|бул|бульвар|шоссе|"
    r"д|дом|корп|корпус|стр|строение|кв|квартира|индекс)"
)
_HOUSE_OR_UNIT = re.compile(
    rf"(?<![{CYR}])(?:{_HOUSE_MARK}|{_UNIT_MARK})\b",
)
_ABBREV_DOT = frozenset(
    {
        "\u0433",
        "\u0443\u043b",
        "\u0434",
        "\u043a\u0432",
        "\u043f\u0440",
        "\u043f\u0435\u0440",
        "\u0431\u0443\u043b",
        "\u043a\u043e\u0440\u043f",
        "\u0441\u0442\u0440",
    }
)
_BARE_LABEL_STOP = re.compile(
    rf"(?<![A-Za-z{CYR}])(?:индекс|получател|телефон|контактн|email|e-mail|фио)\b",
    re.IGNORECASE,
)
# Title / UPPER / lower values; never consume the next component marker as a name word.
_NAME_WORD = rf"(?!{_MARKER_TOKEN}\b)[{CYR}]{{2,}}(?:-[{CYR}]+)*"
_BARE_NAME = rf"{_NAME_WORD}(?:[ \t]+{_NAME_WORD})*"
_VALUE_STOP = (
    r"(?=,|;|\.|$|"
    rf"\s+(?:{_STREET_MARK}|{_HOUSE_MARK}|{_UNIT_MARK}|(?i:индекс)|{_CITY_MARK}))"
)
_BARE_SEGMENT = re.compile(
    rf"(?:[{CYR_UPPER}][{CYR_LOWER}-]+|[{CYR_UPPER}]{{2,}}|[{CYR_LOWER}]{{2,}})"
    rf"(?:[ \t]+(?:[{CYR_UPPER}][{CYR_LOWER}-]+|[{CYR_UPPER}]{{2,}}|[{CYR_LOWER}]{{2,}}))*"
)
_SKIP_SEGMENT = re.compile(
    rf"^(?:{_HOUSE_MARK}|{_UNIT_MARK}|(?i:индекс))\b",
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
        "бульвар",
        "шоссе",
        "индекс",
        "адрес",
        "дом",
        "квартира",
        "корпус",
        "строение",
        "получатель",
        "доставка",
        "служба",
    }
)
_CLAUSE_LIMIT = 160
_POSTAL_CITY = re.compile(rf"(?<!\d)\d{{6}}\s*,\s*(?P<city>{_BARE_NAME})(?=\s*,)")
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
        re.compile(rf"(?<![{CYR}]){_CITY_MARK}\s*{_BARE_NAME}{_VALUE_STOP}"),
    ),
    (
        PiiType.ADDRESS_STREET,
        re.compile(rf"(?<![{CYR}]){_STREET_MARK}\s*{_BARE_NAME}{_VALUE_STOP}"),
    ),
    (
        PiiType.ADDRESS_BUILDING,
        re.compile(
            rf"(?<![{CYR}]){_HOUSE_MARK}\s*(?P<value>\d+[0-9A-Za-z{CYR}]?)",
        ),
    ),
    (
        PiiType.ADDRESS_UNIT,
        re.compile(
            rf"(?<![{CYR}]){_UNIT_MARK}\s*(?P<value>\d+)",
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
            if _ORG_ANCHOR.search(
                text, max(0, anchor.start() - 8), min(len(text), anchor.end() + 48)
            ):
                continue
            clause_start = anchor.end()
            while clause_start < len(text) and text[clause_start] in " \t:—-":
                clause_start += 1
            clause_end = min(len(text), clause_start + _CLAUSE_LIMIT)
            clause_end = min(clause_end, _sentence_end(text, clause_start))
            clause = text[clause_start:clause_end]
            parts = _components(clause, clause_start)
            _extend_labeled_postal(text, anchor.start(), clause_end, parts)
            _extend_bare_city_street(clause, clause_start, parts)
            parts.sort(key=lambda item: (item[1], item[2], item[0].value))
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
    """Allow explicit «Индекс NNNNNN» in a neighboring sentence around the address."""
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
    has_city = any(pii_type == PiiType.ADDRESS_CITY for pii_type, _s, _e in found)
    has_street = any(pii_type == PiiType.ADDRESS_STREET for pii_type, _s, _e in found)
    if has_city and has_street:
        return
    # Bare city is allowed when a marked street is already present (no house yet).
    if not has_house_or_unit and not has_street and _HOUSE_OR_UNIT.search(clause) is None:
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


def _sentence_end(text: str, start: int) -> int:
    """End of the sentence/field starting at start (abbreviation dots excluded)."""
    limit = min(len(text), start + _CLAUSE_LIMIT)
    region = text[start:limit]
    for match in re.finditer(rf"\.(?=\s+[{CYR_UPPER}A-Z]|\s*$)|;", region):
        if match.group(0) == ";" or not _is_abbreviation_dot(region, match.start()):
            return start + match.start()
    return limit


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
    while start > 0 and dot_pos - start < 4:
        ch = text[start - 1]
        if not (ch.isascii() and ch.isalpha()) and not ("\u0400" <= ch <= "\u04ff"):
            break
        start -= 1
    return text[start:dot_pos].casefold() in _ABBREV_DOT
