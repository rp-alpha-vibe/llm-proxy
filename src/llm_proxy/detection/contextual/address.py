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
    r"адрес регистрации|адрес проживания|адрес клиента|домашний адрес|прожива(?:ет|ю)",
    re.IGNORECASE,
)
_GENERIC_ADDRESS = re.compile(rf"(?<![A-Za-z{CYR}])адрес\s*:", re.IGNORECASE)
_DELIVERY = re.compile(r"доставк|получател", re.IGNORECASE)
_ORG = re.compile(r"банк|отделен|филиал|офис", re.IGNORECASE)
_CLAUSE_LIMIT = 160
_POSTAL_CITY = re.compile(
    rf"(?<!\d)\d{{6}}\s*,\s*(?P<city>[{CYR_UPPER}][{CYR_LOWER}-]+)(?=\s*,)"
)
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
            rf"(?<![{CYR}])(?:{G_DOT}|город)\s*[{CYR_UPPER}][{CYR_LOWER}-]+",
            re.IGNORECASE,
        ),
    ),
    (
        PiiType.ADDRESS_STREET,
        re.compile(
            rf"(?<![{CYR}])(?:ул\.|улица)\s*[{CYR_UPPER}][{CYR_LOWER}-]+",
            re.IGNORECASE,
        ),
    ),
    (
        PiiType.ADDRESS_BUILDING,
        re.compile(
            rf"(?<![{CYR}])(?:\u0434\.|дом)\s*\d+[0-9A-Za-z{CYR}]?",
            re.IGNORECASE,
        ),
    ),
    (
        PiiType.ADDRESS_UNIT,
        re.compile(rf"(?<![{CYR}])(?:кв\.|квартира)\s*\d+", re.IGNORECASE),
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
            clause_end = min(len(text), clause_start + _CLAUSE_LIMIT)
            clause = text[clause_start:clause_end]
            if _ORG.search(clause):
                continue
            parts = _components(clause, clause_start)
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


def _components(clause: str, offset: int) -> list[tuple[PiiType, int, int]]:
    found: list[tuple[PiiType, int, int]] = []
    for pii_type, pattern in _PARTS:
        for match in pattern.finditer(clause):
            start, end = trim_span(clause, match.start(), match.end())
            if end > start:
                found.append((pii_type, offset + start, offset + end))

    bare_city = _POSTAL_CITY.search(clause)
    if bare_city is not None:
        city_start = offset + bare_city.start("city")
        city_end = offset + bare_city.end("city")
        if not any(start < city_end and city_start < end for _type, start, end in found):
            found.append((PiiType.ADDRESS_CITY, city_start, city_end))
    return found
