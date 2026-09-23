"""Tests for labeled questionnaire detection and control corpus."""

# Mixed Cyrillic labels with numeric dates/IDs are intentional fixtures.
# ruff: noqa: RUF001

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from llm_proxy.application.process_service import ProcessService
from llm_proxy.detection.contextual import register_contextual_detectors
from llm_proxy.detection.engine import PiiEngine
from llm_proxy.detection.models import MANDATORY_PII_TYPES, PiiType
from llm_proxy.detection.registry import DetectorRegistry
from llm_proxy.detection.structured import register_structured_detectors
from llm_proxy.masking.competition import CompetitionMaskStrategy
from llm_proxy.policies.models import ConsumerContext, ConsumerPolicy
from llm_proxy.state.models import SessionRecord, StateStore

CONTROL = Path(__file__).resolve().parent / "fixtures" / "control_corpus_v1.yaml"


class MemoryStateStore(StateStore):
    def __init__(self) -> None:
        self.records: dict[str, SessionRecord] = {}

    async def get(self, key: str) -> SessionRecord | None:
        return self.records.get(key)

    async def create_if_absent(self, key: str, record: SessionRecord, ttl_seconds: int) -> bool:
        if key in self.records:
            return False
        self.records[key] = record
        return True

    async def update_ttl(self, key: str, ttl_seconds: int) -> bool:
        return key in self.records

    async def delete(self, key: str) -> bool:
        return self.records.pop(key, None) is not None


def _engine() -> PiiEngine:
    registry = DetectorRegistry()
    register_structured_detectors(registry)
    register_contextual_detectors(registry)
    return PiiEngine(registry)


def _found(text: str) -> list[tuple[PiiType, str]]:
    return [
        (item.type, text[item.start : item.end])
        for item in _engine().detect(text, MANDATORY_PII_TYPES)
    ]


def test_labeled_fields_from_section_4_1() -> None:
    assert _found("ФИО: Орлова Нина Марковна;") == [
        (PiiType.PERSON, "Орлова Нина Марковна"),
    ]
    assert _found("дата рождения: 15.04.1988;") == [(PiiType.BIRTH_DATE, "15.04.1988")]
    assert _found("место рождения: посёлок Северный, Образцовая область;") == [
        (PiiType.BIRTH_PLACE, "посёлок Северный, Образцовая область"),
    ]
    assert _found("гражданство: Образцовая республика (фиктивное);") == [
        (PiiType.CITIZENSHIP, "Образцовая республика"),
    ]
    assert _found("орган, выдавший паспорт: Тестовый отдел №7;") == [
        (PiiType.PASSPORT_ISSUER, "Тестовый отдел №7"),
    ]
    assert _found("дата выдачи паспорта: 09-07-2021;") == [
        (PiiType.PASSPORT_ISSUE_DATE, "09-07-2021"),
    ]
    assert _found("ИНН: 1234567890 (проверка);") == [(PiiType.INN, "1234567890")]
    assert _found("номер платёжной банковской карты: 4111 1111 1111 1112 (тест);") == [
        (PiiType.PAYMENT_CARD, "4111 1111 1111 1112"),
    ]
    assert _found("имя держателя карты: DEMOHOLD99 CARDNAME;") == [
        (PiiType.CARDHOLDER, "DEMOHOLD99 CARDNAME"),
    ]


def test_address_block_and_alphanumeric_house() -> None:
    text = (
        "адрес — страна: Демонстрация, индекс: 111222, город: Примерск, "
        "улица: Садовая, дом: 10A, квартира: 12/1;"
    )
    assert _found(text) == [
        (PiiType.ADDRESS_COUNTRY, "Демонстрация"),
        (PiiType.ADDRESS_POSTAL_CODE, "111222"),
        (PiiType.ADDRESS_CITY, "Примерск"),
        (PiiType.ADDRESS_STREET, "Садовая"),
        (PiiType.ADDRESS_BUILDING, "10A"),
        (PiiType.ADDRESS_UNIT, "12/1"),
    ]


def test_date_formats_and_verbal_labeled() -> None:
    assert _found("дата рождения: 2001/07/09;") == [(PiiType.BIRTH_DATE, "2001/07/09")]
    assert _found("дата рождения: 3 марта 1999 года;") == [
        (PiiType.BIRTH_DATE, "3 марта 1999 года"),
    ]
    assert _found("дата рождения: первого мая тысяча девятьсот девяносто года;") == [
        (PiiType.BIRTH_DATE, "первого мая тысяча девятьсот девяносто года"),
    ]
    assert _found("дата выдачи паспорта: восьмого января две тысячи шестнадцать года;") == [
        (PiiType.PASSPORT_ISSUE_DATE, "восьмого января две тысячи шестнадцать года"),
    ]


def test_negatives_for_labeled_rules() -> None:
    assert _found("код заказа 123456789012 и номер 4111222233334444 без меток") == []
    assert _found("встреча назначена на 12.03.2024 в офисе") == []
    assert _found("адрес отделения Банка: \u0433. Москва, ул. Тверская, д. 1") == []
    assert _found("Александр Пушкин написал стихотворение") == []
    assert _found("Контакты редакции: Российский Красный Крест") == []
    assert _found("любимый цвет: синий; код склада: 9988776655") == []
    assert _found("ФИО: Иванов Иван; гражданство: Россия;") == [
        (PiiType.PERSON, "Иванов Иван"),
        (PiiType.CITIZENSHIP, "Россия"),
    ]


def test_issuer_label_variants() -> None:
    assert _found("кем выдан документ: МВД по \u0433. Северску;") == [
        (PiiType.PASSPORT_ISSUER, "МВД по \u0433. Северску"),
    ]
    assert _found("паспорт выдан: ОУФМС района Тест;") == [
        (PiiType.PASSPORT_ISSUER, "ОУФМС района Тест"),
    ]


def test_control_corpus_v1_expected_spans() -> None:
    doc = yaml.safe_load(CONTROL.read_text(encoding="utf-8"))
    engine = _engine()
    for case in doc["cases"]:
        text = case["text"]
        detections = engine.detect(text, MANDATORY_PII_TYPES)
        actual = {(item.type.value, item.start, item.end) for item in detections}
        expected = {(item["type"], item["start"], item["end"]) for item in case["expected"]}
        missing = expected - actual
        # Extra detections that do not overlap any expected span.
        extras = {
            (item.type.value, item.start, item.end)
            for item in detections
            if not any(
                item.start < exp["end"] and exp["start"] < item.end for exp in case["expected"]
            )
        }
        assert not missing, f"{case['id']} missing {missing}"
        if case["id"].startswith("neg-"):
            assert not extras, f"{case['id']} extras {extras}"


_FULL_FORMS = (
    (
        "ФИО: Козлова Елена Викторовна; дата рождения: 22.11.1985; "
        "место рождения: \u0433. Пример, Крайний край; серия и номер паспорта: 5011 778899; "
        "гражданство: Примерляндия (фиктивное); орган, выдавший паспорт: УВД \u0433. Примера; "
        "код подразделения: 500-111; дата выдачи паспорта: 22.11.2005; "
        "серия и номер водительского удостоверения: 9910 112233; "
        "адрес — страна: Примерляндия, индекс: 500111, город: Пример, улица: Лесная, "
        "дом: 7B, квартира: 15; email: elena.koz@example.test; "
        "номер телефона: +7 900 111-22-33; ИНН: 500111223344 (фиктивный); "
        "номер платёжной банковской карты: 4000 0000 0000 0002 (невалидный); "
        "CVV-код: 111; PIN-код карты: 2222; имя держателя карты: KOZLOVA ELENA."
    ),
    (
        "ИНН: 111222333444; имя держателя карты: IVAN TESTOV; "
        "номер платёжной банковской карты: 5000 0000 0000 0001; "
        "CVV-код: 222; PIN-код карты: 3333; email: ivan.t@example.test; "
        "номер телефона: +7 900 222-33-44; "
        "адрес проживания: страна: Тестландия, индекс: 111111, город: Север, "
        "улица: Речная, дом: T-101, квартира: 9; "
        "серия и номер водительского удостоверения: 1122 334455; "
        "дата выдачи паспорта: 2001/07/09; код подразделения: 111-222; "
        "орган, выдавший паспорт: ОВД Тест; гражданство: РФ; "
        "серия и номер паспорта: 4010 112233; место рождения: \u0433. Север, Край; "
        "дата рождения: 01.02.1980; ФИО: Тестов Иван Петрович;"
    ),
    (
        "ФИО: Мирова Анна; дата рождения: 05-06-1991; место рождения: \u0433. Восток, Область; "
        "серия и номер паспорта: 1212 343456; гражданство: Мир; "
        "орган, выдавший паспорт: УФМС Мира; код подразделения: 222-333; "
        "дата выдачи паспорта: 05/06/2011; серия и номер водительского удостоверения: 5555 666677; "
        "адрес — страна: Мир, индекс: 222333, город: Восток, улица: Полевая, "
        "дом: 2/1, квартира: 4; "
        "email: anna.m@example.test; номер телефона: +7 900 333-44-55; ИНН: 222333444555; "
        "номер платёжной банковской карты: 4111 1111 1111 1111; CVV-код: 333; "
        "PIN-код карты: 4444; имя держателя карты: MIROVA ANNA;"
    ),
    (
        "дата рождения: 1992-08-08; ФИО: Гусев Пётр; гражданство: РФ; "
        "место рождения: пос. Лесной, Район; серия и номер паспорта: 9090 808070; "
        "кем выдан документ: МВД Лесного; код подразделения: 909-808; "
        "дата выдачи паспорта: 08.08.2012; серия и номер водительского удостоверения: 8080 707060; "
        "адрес — страна: РФ, индекс: 909808, город: Лесной, улица: Сосновая, "
        "дом: 8A, квартира: 80; "
        "номер телефона: +7 900 444-55-66; email: gusev@example.test; ИНН: 909808707060; "
        "номер платёжной банковской карты: 4222 2222 2222 2222; CVV-код: 444; "
        "PIN-код карты: 5555; имя держателя карты: GUSEV PETR;"
    ),
    (
        "ФИО: Савина Ольга Игоревна; дата рождения: 3 марта 1993 года; "
        "место рождения: \u0433. Южный, Край; серия и номер паспорта: 3030 404050; "
        "гражданство: Савиния (фиктивное); орган, выдавший паспорт: ОВД Южного; "
        "код подразделения: 303-404; дата выдачи паспорта: 12 мая 2013 г; "
        "серия и номер водительского удостоверения: 3030 505060; "
        "адрес — страна: Савиния, индекс: 303404, город: Южный, улица: Южная, "
        "дом: 30, квартира: 3; "
        "email: savina@example.test; номер телефона: +7 900 555-66-77; ИНН: 303404505060; "
        "номер платёжной банковской карты: 4333 3333 3333 3333; CVV-код: 555; "
        "PIN-код карты: 6666; имя держателя карты: SAVINA OLGA;"
    ),
    (
        "ФИО: Орлов Кирилл; дата рождения: первого мая тысяча девятьсот девяносто года; "
        "место рождения: \u0433. Орск, Область; серия и номер паспорта: 6060 707080; "
        "гражданство: Орляндия; паспорт выдан: УВД Орска; код подразделения: 606-707; "
        "дата выдачи паспорта: восьмого января две тысячи шестнадцать года; "
        "серия и номер водительского удостоверения: 6060 808090; "
        "адрес — страна: Орляндия, индекс: 606707, город: Орск, улица: Орская, "
        "дом: T-6, квартира: 60; "
        "email: orlov@example.test; номер телефона: +7 900 666-77-88; ИНН: 606707808090; "
        "номер платёжной банковской карты: 4444 4444 4444 4444; CVV-код: 666; "
        "PIN-код карты: 7777; имя держателя карты: ORLOV KIRILL;"
    ),
    (
        "email: a1@example.test; номер телефона: +7 900 777-88-99; "
        "ФИО: Белова Дарья; дата рождения: 11.11.1994; место рождения: \u0433. Бел, Край; "
        "серия и номер паспорта: 1111 222233; гражданство: Белландия; "
        "орган, выдавший паспорт: УФМС Бел; код подразделения: 111-222; "
        "дата выдачи паспорта: 11.11.2014; серия и номер водительского удостоверения: 1111 333344; "
        "адрес — страна: Белландия, индекс: 111222, город: Бел, улица: Белая, "
        "дом: 11, квартира: 1; "
        "ИНН: 111222333344; номер платёжной банковской карты: 4555 5555 5555 5555; "
        "CVV-код: 777; PIN-код карты: 8888; имя держателя карты: BELOVA DARYA;"
    ),
    (
        "ФИО: Новиков Илья; гражданство: РФ; дата рождения: 12/12/1988; "
        "место рождения: \u0433. Нов, Область; серия и номер паспорта: 1212 131415; "
        "орган, выдавший паспорт: МВД Нова; код подразделения: 121-131; "
        "дата выдачи паспорта: 2010-12-12; серия и номер водительского удостоверения: 1212 161718; "
        "адрес — страна: РФ, индекс: 121131, город: Нов, улица: Новая, дом: 12/2, квартира: 12; "
        "email: nov@example.test; номер телефона: +7 900 888-99-00; ИНН: 121131141516; "
        "номер платёжной банковской карты: 4666 6666 6666 6666; CVV-код: 888; "
        "PIN-код карты: 9999; имя держателя карты: NOVIKOV ILYA;"
    ),
    (
        "ФИО: Крылова Вера; дата рождения: 09.09.1989; место рождения: \u0433. Крымск, Край; "
        "серия и номер паспорта: 0909 101112; гражданство: Крыландия; "
        "орган, выдавший паспорт: ОВД Крымска; код подразделения: 090-101; "
        "дата выдачи паспорта: 09.09.2009; серия и номер водительского удостоверения: 0909 131415; "
        "адрес — страна: Крыландия, индекс: 090101, город: Крымск, улица: Крымская, "
        "дом: 9B, квартира: 19; "
        "email: krylova@example.test; номер телефона: +7 900 999-00-11; ИНН: 090101121314; "
        "номер платёжной банковской карты: 4777 7777 7777 7777; CVV-код: 999; "
        "PIN-код карты: 1010; имя держателя карты: KRYLOVA VERA;"
    ),
    (
        "ФИО: Павлов Сергей; дата рождения: 07.07.1987; место рождения: \u0433. Павл, Область; "
        "серия и номер паспорта: 0707 080910; гражданство: Павландия; "
        "орган, выдавший паспорт: УВД Павла; код подразделения: 070-080; "
        "дата выдачи паспорта: 07.07.2007; серия и номер водительского удостоверения: 0707 111213; "
        "адрес — страна: Павландия, индекс: 070080, город: Павл, улица: Павлова, "
        "дом: 7, квартира: 17; "
        "email: pavlov@example.test; номер телефона: +7 900 101-11-12; ИНН: 070080091011; "
        "номер платёжной банковской карты: 4888 8888 8888 8888; CVV-код: 101; "
        "PIN-код карты: 1212; имя держателя карты: PAVLOV SERGEY;"
    ),
)


@pytest.mark.parametrize("text", _FULL_FORMS)
def test_full_questionnaire_covers_twenty_two_fields(text: str) -> None:
    found = _found(text)
    types = {item[0] for item in found}
    required = {
        PiiType.PERSON,
        PiiType.BIRTH_DATE,
        PiiType.BIRTH_PLACE,
        PiiType.PASSPORT,
        PiiType.CITIZENSHIP,
        PiiType.PASSPORT_ISSUER,
        PiiType.PASSPORT_DIVISION_CODE,
        PiiType.PASSPORT_ISSUE_DATE,
        PiiType.DRIVER_LICENSE,
        PiiType.ADDRESS_COUNTRY,
        PiiType.ADDRESS_POSTAL_CODE,
        PiiType.ADDRESS_CITY,
        PiiType.ADDRESS_STREET,
        PiiType.ADDRESS_BUILDING,
        PiiType.ADDRESS_UNIT,
        PiiType.EMAIL,
        PiiType.PHONE,
        PiiType.INN,
        PiiType.PAYMENT_CARD,
        PiiType.CVV,
        PiiType.PIN,
        PiiType.CARDHOLDER,
    }
    assert required <= types
    # Annotations and separators stay outside spans.
    assert "(фиктив" not in "".join(value for _type, value in found)
    assert all(";" not in value for _type, value in found)


@pytest.mark.asyncio
@pytest.mark.parametrize("index,text", list(enumerate(_FULL_FORMS)))
async def test_full_questionnaire_mask_unmask_and_llm_reply(index: int, text: str) -> None:
    service = ProcessService(
        state_store=MemoryStateStore(),
        detector=_engine(),
        mask_strategy=CompetitionMaskStrategy(),
    )
    policy = ConsumerPolicy(
        policy_id="policy-alfa_tester",
        system_id="alfa_tester",
        enabled=True,
        pii_types="all",
        allow_demask=True,
        mask_strategy="competition",
    )
    context = ConsumerContext(consumer_id="alfa_tester", policy=policy)
    payload_id = f"full-form-{index}"
    masked = await service.process(context, payload_id, text)
    restored = await service.process(context, payload_id, masked.result)
    assert restored.result == text

    # Product demask: reorder known masks inside a new reply.
    import re

    tokens = re.findall(r"<[A-Z_]+_\d+>", masked.result)
    assert tokens
    reply = f"Ответ: {tokens[-1]} затем {tokens[0]} повтор {tokens[-1]}."
    demasked = await service.process(context, payload_id, reply)
    assert demasked.result.startswith("Ответ:")
    assert tokens[-1] not in demasked.result
    assert "Ответ:" in demasked.result
