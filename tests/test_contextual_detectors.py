import time
from collections.abc import Sequence

import pytest

from llm_proxy.application.process_service import ProcessService
from llm_proxy.application.stubs import SimplePlaceholderMaskStrategy
from llm_proxy.detection.contextual import register_contextual_detectors
from llm_proxy.detection.engine import PiiEngine
from llm_proxy.detection.models import MANDATORY_PII_TYPES, PiiType
from llm_proxy.detection.registry import DetectorRegistry
from llm_proxy.policies.models import ConsumerContext, ConsumerPolicy
from llm_proxy.state.models import SessionRecord, StateStore

_TYPES = (
    PiiType.BIRTH_DATE,
    PiiType.PASSPORT_ISSUE_DATE,
    PiiType.CVV,
    PiiType.PIN,
    PiiType.CITIZENSHIP,
    PiiType.BIRTH_PLACE,
    PiiType.PASSPORT_ISSUER,
    PiiType.ADDRESS,
    PiiType.ADDRESS_COUNTRY,
    PiiType.ADDRESS_REGION,
    PiiType.ADDRESS_DISTRICT,
    PiiType.ADDRESS_CITY,
    PiiType.ADDRESS_STREET,
    PiiType.ADDRESS_BUILDING,
    PiiType.ADDRESS_UNIT,
    PiiType.ADDRESS_POSTAL_CODE,
    PiiType.PERSON,
    PiiType.CARDHOLDER,
)


class MemoryStateStore(StateStore):
    def __init__(self) -> None:
        self.records: dict[str, SessionRecord] = {}

    async def get(self, key: str) -> SessionRecord | None:
        return self.records.get(key)

    async def create_if_absent(
        self,
        key: str,
        record: SessionRecord,
        ttl_seconds: int,
    ) -> bool:
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
    register_contextual_detectors(registry)
    return PiiEngine(registry)


def _found(text: str, enabled: Sequence[PiiType] = _TYPES) -> list[tuple[PiiType, str]]:
    return [(item.type, text[item.start : item.end]) for item in _engine().detect(text, enabled)]


def test_birth_and_issue_dates_need_their_own_context() -> None:
    assert _found("дата рождения 01.02.1990.") == [(PiiType.BIRTH_DATE, "01.02.1990")]
    assert _found("родился 6 июня 1990 года") == [(PiiType.BIRTH_DATE, "6 июня 1990")]
    assert _found("ДАТА РОЖДЕНИЯ: 1.2.1991,") == [(PiiType.BIRTH_DATE, "1.2.1991")]
    assert _found("родился 01.02.1990 и родилась 03.04.1992") == [
        (PiiType.BIRTH_DATE, "01.02.1990"),
        (PiiType.BIRTH_DATE, "03.04.1992"),
    ]
    assert _found("паспорт выдан 12.03.2010.") == [(PiiType.PASSPORT_ISSUE_DATE, "12.03.2010")]
    assert _found("дата выдачи 2010-03-12") == [(PiiType.PASSPORT_ISSUE_DATE, "2010-03-12")]
    assert _found("встреча назначена на 12.03.2024") == []
    assert _found("дата рождения 31.02.1990") == []
    assert _found("дата рождения 01.02.1990, паспорт выдан 12.03.2010") == [
        (PiiType.BIRTH_DATE, "01.02.1990"),
        (PiiType.PASSPORT_ISSUE_DATE, "12.03.2010"),
    ]


def test_cvv_and_pin_require_labels() -> None:
    assert _found("CVV: 123.") == [(PiiType.CVV, "123")]
    assert _found("cvc 482, код безопасности 907") == [
        (PiiType.CVV, "482"),
        (PiiType.CVV, "907"),
    ]
    assert _found("заказ 482") == []
    assert _found("код 123") == []
    assert _found("пин-код карты 4321.") == [(PiiType.PIN, "4321")]
    assert _found("PIN карты 123456") == [(PiiType.PIN, "123456")]
    assert _found("пин 4321") == []
    assert _found("код домофона 4321") == []


def test_citizenship_birth_place_and_issuer() -> None:
    assert _found("гражданство: Россия.") == [(PiiType.CITIZENSHIP, "Россия")]
    assert _found("гражданин РФ") == [(PiiType.CITIZENSHIP, "РФ")]
    assert _found("ГРАЖДАНСТВО: РОССИИ") == [(PiiType.CITIZENSHIP, "РОССИИ")]
    assert _found("Гражданский кодекс") == []
    assert _found("РФ") == []
    assert _found("место рождения: \u0433. Казань.") == [(PiiType.BIRTH_PLACE, "\u0433. Казань")]
    assert _found("клиент родился в Казани.") == [(PiiType.BIRTH_PLACE, "Казани")]
    assert _found("Александр Пушкин родился в Москве.") == []
    assert _found("паспорт выдан 12.03.2010 ОВД \u0433. Казани.") == [
        (PiiType.PASSPORT_ISSUE_DATE, "12.03.2010"),
        (PiiType.PASSPORT_ISSUER, "ОВД \u0433. Казани"),
    ]
    assert _found("выдан кредит банком") == []


def test_address_components_and_organization_negative() -> None:
    text = (
        "адрес регистрации: 123456, Россия, Московская область, Ленинский район, "
        "\u0433. Казань, ул. Баумана, д. 10, кв. 5."
    )
    assert _found(text) == [
        (PiiType.ADDRESS_POSTAL_CODE, "123456"),
        (PiiType.ADDRESS_COUNTRY, "Россия"),
        (PiiType.ADDRESS_REGION, "Московская область"),
        (PiiType.ADDRESS_DISTRICT, "Ленинский район"),
        (PiiType.ADDRESS_CITY, "\u0433. Казань"),
        (PiiType.ADDRESS_STREET, "ул. Баумана"),
        (PiiType.ADDRESS_BUILDING, "10"),
        (PiiType.ADDRESS_UNIT, "5"),
    ]
    assert _found("АДРЕС ПРОЖИВАНИЯ: \u0433. Самара, улица Ленина, дом 4, квартира 2.") == [
        (PiiType.ADDRESS_CITY, "\u0433. Самара"),
        (PiiType.ADDRESS_STREET, "улица Ленина"),
        (PiiType.ADDRESS_BUILDING, "4"),
        (PiiType.ADDRESS_UNIT, "2"),
    ]
    assert _found("адрес отделения банка: \u0433. Москва, ул. Тверская, д. 1") == []
    assert _found("\u0433. Москва, ул. Тверская, д. 1") == []
    only_address = _found(text, (PiiType.ADDRESS,))
    assert only_address == [
        (
            PiiType.ADDRESS,
            "123456, Россия, Московская область, Ленинский район, "
            "\u0433. Казань, ул. Баумана, д. 10, кв. 5",
        )
    ]


def test_person_and_cardholder_context() -> None:
    assert _found("ФИО: Иван Петров.") == [(PiiType.PERSON, "Иван Петров")]
    assert _found("клиента зовут Иван Иванович Сидоров.") == [
        (PiiType.PERSON, "Иван Иванович Сидоров")
    ]
    assert _found("ФИО: ИВАН ПЕТРОВ") == [(PiiType.PERSON, "ИВАН ПЕТРОВ")]
    assert _found("ФИО: Иван Петров и Петр Сидоров") == [
        (PiiType.PERSON, "Иван Петров"),
        (PiiType.PERSON, "Петр Сидоров"),
    ]
    assert _found("Александр Пушкин написал стихи") == []
    assert _found("Иван Петров") == []
    assert _found("держатель карты Иван Петров.") == [(PiiType.CARDHOLDER, "Иван Петров")]
    assert _found("cardholder: IVAN PETROV") == [(PiiType.CARDHOLDER, "IVAN PETROV")]


def test_delivery_contacts_confirm_person_and_address_components() -> None:
    text = (
        "Оставляю контакты для доставки макета: Новиков Ирина Примеровна, "
        "+7 000 555-00-10. Адрес: Тестовая Республика, 990010, Демонстрационск, "
        "улица Макетная, д. 10, кв. 20. Лучше звонить после обеда."
    )

    assert _found(text) == [
        (PiiType.PERSON, "Новиков Ирина Примеровна"),
        (PiiType.ADDRESS_COUNTRY, "Тестовая Республика"),
        (PiiType.ADDRESS_POSTAL_CODE, "990010"),
        (PiiType.ADDRESS_CITY, "Демонстрационск"),
        (PiiType.ADDRESS_STREET, "улица Макетная"),
        (PiiType.ADDRESS_BUILDING, "10"),
        (PiiType.ADDRESS_UNIT, "20"),
    ]


def test_generic_contacts_and_address_stay_unconfirmed_without_personal_context() -> None:
    assert _found("Контакты редакции: Российский Красный Крест.") == []
    assert _found("Адрес: \u0433. Москва, улица Тверская, дом 4.") == []
    assert _found("Контакты редакции. Адрес: \u0433. Москва, улица Тверская, дом 4.") == []


@pytest.mark.asyncio
async def test_delivery_contacts_mask_and_exact_unmask() -> None:
    from llm_proxy.main import _build_detector
    from llm_proxy.masking.competition import CompetitionMaskStrategy

    text = (
        "Оставляю контакты для доставки макета: Новиков Ирина Примеровна, "
        "+7 000 555-00-10. Адрес: Тестовая Республика, 990010, Демонстрационск, "
        "улица Макетная, д. 10, кв. 20. Лучше звонить после обеда."
    )
    expected = (
        "Оставляю контакты для доставки макета: <PERSON_1>, <PHONE_2>. "
        "Адрес: <ADDRESS_COUNTRY_3>, <ADDRESS_POSTAL_CODE_4>, <ADDRESS_CITY_5>, "
        "<ADDRESS_STREET_6>, д. <ADDRESS_HOUSE_7>, кв. <ADDRESS_APARTMENT_8>. "
        "Лучше звонить после обеда."
    )
    service = ProcessService(
        state_store=MemoryStateStore(),
        detector=_build_detector(),
        mask_strategy=CompetitionMaskStrategy(),
    )
    policy = ConsumerPolicy(
        policy_id="policy-alfa_tester",
        system_id="alfa_tester",
        enabled=True,
        pii_types=MANDATORY_PII_TYPES,
        allow_demask=True,
        mask_strategy="competition",
    )
    context = ConsumerContext(consumer_id="alfa_tester", policy=policy)

    masked = await service.process(context, "payload-delivery", text)
    restored = await service.process(context, "payload-delivery", masked.result)

    assert masked.result == expected
    assert restored.result == text


def test_app_wires_contextual_detectors() -> None:
    from llm_proxy.main import _build_detector

    text = "дата рождения 01.02.1990"
    found = [
        (item.type, text[item.start : item.end])
        for item in _build_detector().detect(text, (PiiType.BIRTH_DATE,))
    ]
    assert found == [(PiiType.BIRTH_DATE, "01.02.1990")]


@pytest.mark.asyncio
async def test_contextual_mask_exact_unmask_preserves_neighbors() -> None:
    text = (
        "ФИО: Иван Петров, дата рождения 01.02.1990, место рождения: \u0433. Казань, "
        "гражданство: Россия, паспорт выдан 12.03.2010 ОВД \u0433. Казани, "
        "адрес регистрации: \u0433. Казань, ул. Баумана, д. 10, кв. 5, "
        "CVV 123, пин-код карты 4321, держатель карты Петр Сидоров."
    )
    service = ProcessService(
        state_store=MemoryStateStore(),
        detector=_engine(),
        mask_strategy=SimplePlaceholderMaskStrategy(),
    )
    policy = ConsumerPolicy(
        policy_id="policy-alfa_tester",
        system_id="alfa_tester",
        enabled=True,
        pii_types=_TYPES,
        allow_demask=True,
        mask_strategy="placeholder",
    )
    context = ConsumerContext(consumer_id="alfa_tester", policy=policy)
    masked = await service.process(context, "payload-context", text)
    restored = await service.process(context, "payload-context", masked.result)

    assert "Иван Петров" not in masked.result
    assert "01.02.1990" not in masked.result
    assert "4321" not in masked.result
    assert "ФИО: " in masked.result
    assert restored.result == text


def test_contextual_patterns_stay_bounded() -> None:
    engine = _engine()
    samples = (
        "дата рождения 01.02.1990 " * 30,
        "Абв " * 20_000,
        "1" * 100_000,
        "серия " * 5_000,
    )
    started = time.perf_counter()
    for sample in samples:
        engine.detect(sample, _TYPES)
    assert time.perf_counter() - started < 2.0


_FREE_TEXT_EXAMPLE = (
    "Служба доставки просила уточнить индекс и телефон. Индекс 990020, адрес: "
    "Демонстрационск, Учебная, дом 20, квартира 30; контактный номер +7 000 555-00-20. "
    "Получатель Новиков Алексей Примеровна"
)


def _full_engine() -> PiiEngine:
    from llm_proxy.detection.structured import register_structured_detectors

    registry = DetectorRegistry()
    register_structured_detectors(registry)
    register_contextual_detectors(registry)
    return PiiEngine(registry)


def _full_found(text: str) -> list[tuple[PiiType, str]]:
    return [
        (item.type, text[item.start : item.end])
        for item in _full_engine().detect(text, MANDATORY_PII_TYPES)
    ]


def test_free_text_delivery_example_detections() -> None:
    assert _full_found(_FREE_TEXT_EXAMPLE) == [
        (PiiType.ADDRESS_POSTAL_CODE, "990020"),
        (PiiType.ADDRESS_CITY, "Демонстрационск"),
        (PiiType.ADDRESS_STREET, "Учебная"),
        (PiiType.ADDRESS_BUILDING, "20"),
        (PiiType.ADDRESS_UNIT, "30"),
        (PiiType.PHONE, "+7 000 555-00-20"),
        (PiiType.PERSON, "Новиков Алексей Примеровна"),
    ]


@pytest.mark.asyncio
async def test_free_text_delivery_example_mask_and_exact_unmask() -> None:
    from llm_proxy.main import _build_detector
    from llm_proxy.masking.competition import CompetitionMaskStrategy

    expected = (
        "Служба доставки просила уточнить индекс и телефон. Индекс <ADDRESS_POSTAL_CODE_1>, "
        "адрес: <ADDRESS_CITY_2>, <ADDRESS_STREET_3>, дом <ADDRESS_HOUSE_4>, "
        "квартира <ADDRESS_APARTMENT_5>; контактный номер <PHONE_6>. Получатель <PERSON_7>"
    )
    service = ProcessService(
        state_store=MemoryStateStore(),
        detector=_build_detector(),
        mask_strategy=CompetitionMaskStrategy(),
    )
    policy = ConsumerPolicy(
        policy_id="policy-alfa_tester",
        system_id="alfa_tester",
        enabled=True,
        pii_types=MANDATORY_PII_TYPES,
        allow_demask=True,
        mask_strategy="competition",
    )
    context = ConsumerContext(consumer_id="alfa_tester", policy=policy)

    masked = await service.process(context, "payload-free-text", _FREE_TEXT_EXAMPLE)
    restored = await service.process(context, "payload-free-text", masked.result)

    assert masked.result == expected
    assert restored.result == _FREE_TEXT_EXAMPLE


def test_free_text_address_variants() -> None:
    # Bare city/street without city/street prefixes; index after address.
    assert _found(
        "Доставьте заказ по адресу: Примерск, Центральная, дом 10, квартира 5. Индекс 123456."
    ) == [
        (PiiType.ADDRESS_CITY, "Примерск"),
        (PiiType.ADDRESS_STREET, "Центральная"),
        (PiiType.ADDRESS_BUILDING, "10"),
        (PiiType.ADDRESS_UNIT, "5"),
        (PiiType.ADDRESS_POSTAL_CODE, "123456"),
    ]
    # Index before address.
    assert _found("Для доставки индекс 654321, адрес: Озёрск, Набережная, дом 3, квартира 8.") == [
        (PiiType.ADDRESS_POSTAL_CODE, "654321"),
        (PiiType.ADDRESS_CITY, "Озёрск"),
        (PiiType.ADDRESS_STREET, "Набережная"),
        (PiiType.ADDRESS_BUILDING, "3"),
        (PiiType.ADDRESS_UNIT, "8"),
    ]
    # Reordered components: house/unit before bare city/street.
    assert _found("Курьерская доставка, адрес: дом 7, кв. 12, Зеленоградск, Парковая.") == [
        (PiiType.ADDRESS_BUILDING, "7"),
        (PiiType.ADDRESS_UNIT, "12"),
        (PiiType.ADDRESS_CITY, "Зеленоградск"),
        (PiiType.ADDRESS_STREET, "Парковая"),
    ]


def test_free_text_multiword_city_and_street() -> None:
    assert _found("Адрес доставки: Москва, Большая Никитская, дом 10, квартира 2.") == [
        (PiiType.ADDRESS_CITY, "Москва"),
        (PiiType.ADDRESS_STREET, "Большая Никитская"),
        (PiiType.ADDRESS_BUILDING, "10"),
        (PiiType.ADDRESS_UNIT, "2"),
    ]
    assert _found("Адрес доставки: Нижний Новгород, Большая Покровская, дом 8, квартира 4.") == [
        (PiiType.ADDRESS_CITY, "Нижний Новгород"),
        (PiiType.ADDRESS_STREET, "Большая Покровская"),
        (PiiType.ADDRESS_BUILDING, "8"),
        (PiiType.ADDRESS_UNIT, "4"),
    ]
    assert _found(
        "адрес проживания: \u0433. Нижний Новгород, ул. Большая Никитская, дом 1, квартира 2."
    ) == [
        (PiiType.ADDRESS_CITY, "\u0433. Нижний Новгород"),
        (PiiType.ADDRESS_STREET, "ул. Большая Никитская"),
        (PiiType.ADDRESS_BUILDING, "1"),
        (PiiType.ADDRESS_UNIT, "2"),
    ]


def test_free_text_address_stops_at_sentence_boundary() -> None:
    found = _found("Адрес доставки: дом 10, квартира 5. Получатель Иван Иванов.")
    assert (PiiType.ADDRESS_BUILDING, "10") in found
    assert (PiiType.ADDRESS_UNIT, "5") in found
    assert (PiiType.ADDRESS_CITY, "Иван") not in found
    assert (PiiType.ADDRESS_STREET, "Иванов") not in found
    assert (PiiType.ADDRESS_CITY, "Получатель") not in found
    # Recipient with delivery context still finds the person.
    assert (PiiType.PERSON, "Иван Иванов") in found


def test_free_text_person_recipient_variants() -> None:
    assert _found("Для доставки. Получатель Сидоров Пётр Иванович") == [
        (PiiType.PERSON, "Сидоров Пётр Иванович")
    ]
    assert _found("получатель: Козлова Мария") == [(PiiType.PERSON, "Козлова Мария")]
    assert _found("Получатель заказа Белова Анна Сергеевна") == [
        (PiiType.PERSON, "Белова Анна Сергеевна")
    ]
    assert _found("Контактное лицо Орлов Дмитрий") == [(PiiType.PERSON, "Орлов Дмитрий")]
    # Non-standard gender combination of name parts must still be detected.
    assert _found("Курьерская доставка, получатель Новикова Алексей Примеровна") == [
        (PiiType.PERSON, "Новикова Алексей Примеровна")
    ]
    # Получатель immediately before a name acts as a label (no delivery required).
    assert _found("Получатель Сидоров Пётр Иванович") == [(PiiType.PERSON, "Сидоров Пётр Иванович")]


def test_free_text_recipient_award_is_not_person_context() -> None:
    assert _found("Получатель премии Александр Пушкин выступил на сцене.") == []
    assert _found("Получатель награды Мария Тестова получила диплом.") == []
    assert _found("Получатель ордена Пётр Примерский присутствовал на церемонии.") == []
    assert (
        _found(
            "Доставка книг обсуждалась отдельно. "
            "Получатель гранта Александр Пушкин выступил на сцене."
        )
        == []
    )
    assert _full_found("Сегодня обсуждали роман Александра Пушкина.") == []


def test_free_text_phone_context_phrases() -> None:
    assert _full_found("контактный номер +7 900 111-22-33") == [(PiiType.PHONE, "+7 900 111-22-33")]
    assert _full_found("номер телефона 8 (900) 222-33-44 для связи") == [
        (PiiType.PHONE, "8 (900) 222-33-44")
    ]
    assert _full_found("телефон для связи +7-900-333-44-55") == [
        (PiiType.PHONE, "+7-900-333-44-55")
    ]
    assert _full_found("позвонить по номеру +7 900 444 55 66") == [
        (PiiType.PHONE, "+7 900 444 55 66")
    ]


def test_free_text_multiple_people_and_addresses() -> None:
    text = (
        "Первая доставка: адрес: Северск, Лесная, дом 1, квартира 2, получатель Иванов Иван. "
        "Вторая доставка: адрес: Южск, Степная, дом 3, квартира 4, получатель Петрова Анна."
    )
    found = _found(text)
    assert found.count((PiiType.ADDRESS_CITY, "Северск")) == 1
    assert found.count((PiiType.ADDRESS_CITY, "Южск")) == 1
    assert (PiiType.PERSON, "Иванов Иван") in found
    assert (PiiType.PERSON, "Петрова Анна") in found
    assert (PiiType.ADDRESS_BUILDING, "1") in found
    assert (PiiType.ADDRESS_BUILDING, "3") in found


def test_free_text_pii_inside_long_prose() -> None:
    padding = "Фрагмент текста без ПДн. " * 40
    text = (
        f"{padding}Курьер спросил адрес доставки: Мирный, Школьная, дом 9, квартира 11. "
        f"Индекс 111222. Получатель Смирнов Олег.{padding}"
    )
    found = _found(text)
    assert (PiiType.ADDRESS_POSTAL_CODE, "111222") in found
    assert (PiiType.ADDRESS_CITY, "Мирный") in found
    assert (PiiType.ADDRESS_STREET, "Школьная") in found
    assert (PiiType.ADDRESS_BUILDING, "9") in found
    assert (PiiType.ADDRESS_UNIT, "11") in found
    assert (PiiType.PERSON, "Смирнов Олег") in found


def test_free_text_numbers_near_non_address_context() -> None:
    text = (
        "Склад № 42 принял паллету 990020. Для доставки адрес: Факел, Заводская, дом 15, "
        "квартира 6. Индекс 424242. Код ячейки 15 не является домом."
    )
    found = _found(text)
    assert (PiiType.ADDRESS_POSTAL_CODE, "424242") in found
    assert (PiiType.ADDRESS_POSTAL_CODE, "990020") not in found
    assert (PiiType.ADDRESS_BUILDING, "15") in found
    assert found.count((PiiType.ADDRESS_BUILDING, "15")) == 1


def test_free_text_negatives_avoid_overmasking() -> None:
    assert _full_found("Служба доставки работает ежедневно.") == []
    assert _full_found("Встреча состоится в центральном офисе банка.") == []
    assert _full_found("Номер заказа 990020 передан на склад.") == []
    assert _full_found("Сегодня обсуждали роман Александра Пушкина.") == []
    assert _full_found("Доставка временно недоступна в некоторых городах.") == []
