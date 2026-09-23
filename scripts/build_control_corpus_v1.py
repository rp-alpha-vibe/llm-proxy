"""Rebuild control corpus offsets from hand-authored value substrings."""

# ruff: noqa: RUF001

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "control_corpus_v1.yaml"

# Hand-authored cases: text + ordered (type, exact_substring) expectations.
CASES: list[dict] = [
    {
        "id": "ctrl-fio-birth",
        "text": "Анкета. ФИО: Орлова Нина Марковна; дата рождения: 15.04.1988;",
        "values": [("person", "Орлова Нина Марковна"), ("birth_date", "15.04.1988")],
    },
    {
        "id": "ctrl-issuer-variants",
        "text": "кем выдан документ: МВД по г. Северску; паспорт выдан: ОУФМС района Тест;",
        "values": [
            ("passport_issuer", "МВД по г. Северску"),
            ("passport_issuer", "ОУФМС района Тест"),
        ],
    },
    {
        "id": "ctrl-address-block",
        "text": (
            "адрес — страна: Демонстрация, индекс: 111222, город: Примерск, "
            "улица: Садовая, дом: 10A, квартира: 12/1"
        ),
        "values": [
            ("address_country", "Демонстрация"),
            ("address_postal_code", "111222"),
            ("address_city", "Примерск"),
            ("address_street", "Садовая"),
            ("address_house", "10A"),
            ("address_apartment", "12/1"),
        ],
    },
    {
        "id": "ctrl-address-residence-label",
        "text": (
            "адрес проживания: страна: Мир, индекс: 222333, город: Восток, "
            "улица: Мира, дом: T-5, квартира: 3"
        ),
        "values": [
            ("address_country", "Мир"),
            ("address_postal_code", "222333"),
            ("address_city", "Восток"),
            ("address_street", "Мира"),
            ("address_house", "T-5"),
            ("address_apartment", "3"),
        ],
    },
    {
        "id": "ctrl-inn-invalid-labeled",
        "text": "ИНН: 1234567890 (проверка);",
        "values": [("inn", "1234567890")],
    },
    {
        "id": "ctrl-card-invalid-labeled",
        "text": "номер платёжной банковской карты: 4111 1111 1111 1112 (тест);",
        "values": [("card", "4111 1111 1111 1112")],
    },
    {
        "id": "ctrl-cardholder-latin",
        "text": "имя держателя карты: DEMOHOLD99 CARDNAME",
        "values": [("cardholder", "DEMOHOLD99 CARDNAME")],
    },
    {
        "id": "ctrl-dates-formats",
        "text": "дата рождения: 2001/07/09; дата выдачи паспорта: 09-07-2021;",
        "values": [("birth_date", "2001/07/09"), ("passport_issue_date", "09-07-2021")],
    },
    {
        "id": "ctrl-dates-textual",
        "text": "дата рождения: 3 марта 1999 года; дата выдачи паспорта: 12 мая 2018 г;",
        "values": [("birth_date", "3 марта 1999 года"), ("passport_issue_date", "12 мая 2018 г")],
    },
    {
        "id": "ctrl-verbal-birth",
        "text": "дата рождения: первого мая тысяча девятьсот девяносто года;",
        "values": [("birth_date", "первого мая тысяча девятьсот девяносто года")],
    },
    {
        "id": "ctrl-birth-place-comma",
        "text": "место рождения: посёлок Северный, Образцовая область;",
        "values": [("birth_place", "посёлок Северный, Образцовая область")],
    },
    {
        "id": "ctrl-citizenship-free",
        "text": "гражданство: Образцовая республика (фиктивное);",
        "values": [("citizenship", "Образцовая республика")],
    },
    {
        "id": "ctrl-passport-issuer-labeled",
        "text": "орган, выдавший паспорт: Тестовый отдел №7 города Пример;",
        "values": [("passport_issuer", "Тестовый отдел №7 города Пример")],
    },
    {
        "id": "ctrl-field-order-swapped",
        "text": (
            "ИНН: 000000000012; ФИО: Смирнов Олег Петрович; гражданство: РФ; "
            "дата рождения: 01.01.1980;"
        ),
        "values": [
            ("inn", "000000000012"),
            ("person", "Смирнов Олег Петрович"),
            ("citizenship", "РФ"),
            ("birth_date", "01.01.1980"),
        ],
    },
    {
        "id": "ctrl-mixed-case-labels",
        "text": "ФИО: Ким Аида; ДАТА РОЖДЕНИЯ: 1990-12-01; ГРАЖДАНСТВО: рф;",
        "values": [
            ("person", "Ким Аида"),
            ("birth_date", "1990-12-01"),
            ("citizenship", "рф"),
        ],
    },
    {
        "id": "ctrl-two-persons-free",
        "text": "клиента зовут Иван Тестов и Мария Примерова.",
        "values": [("person", "Иван Тестов"), ("person", "Мария Примерова")],
    },
    {
        "id": "ctrl-contact-person",
        "text": "контактное лицо Пётр Демонстрационный, телефон +7 900 000-11-22",
        "values": [("person", "Пётр Демонстрационный")],
    },
    {
        "id": "ctrl-overlap-dates",
        "text": "дата рождения: 10.10.1990; дата выдачи паспорта: 10.10.2010;",
        "values": [("birth_date", "10.10.1990"), ("passport_issue_date", "10.10.2010")],
    },
    {
        "id": "ctrl-overlap-docs",
        "text": (
            "серия и номер паспорта: 4510 123456; "
            "серия и номер водительского удостоверения: 7711 654321;"
        ),
        "values": [("passport", "4510 123456"), ("driver_license", "7711 654321")],
    },
    {
        "id": "ctrl-fio-cardholder-pair",
        "text": "ФИО: Белова Анна Сергеевна; имя держателя карты: BELOVA ANNA;",
        "values": [("person", "Белова Анна Сергеевна"), ("cardholder", "BELOVA ANNA")],
    },
    {
        "id": "ctrl-short-partial",
        "text": "email: sample.user@example.test; номер телефона: +7 911 222-33-44",
        "values": [("email", "sample.user@example.test"), ("phone", "+7 911 222-33-44")],
    },
    {
        "id": "ctrl-cvv-pin",
        "text": "CVV-код: 321; PIN-код карты: 9988;",
        "values": [("cvv", "321"), ("pin", "9988")],
    },
    {
        "id": "ctrl-full-form-a",
        "text": (
            "ФИО: Козлова Елена Викторовна; дата рождения: 22.11.1985; "
            "место рождения: г. Пример, Крайний край; серия и номер паспорта: 5011 778899; "
            "гражданство: Примерляндия (фиктивное); орган, выдавший паспорт: УВД г. Примера; "
            "код подразделения: 500-111; дата выдачи паспорта: 22.11.2005; "
            "серия и номер водительского удостоверения: 9910 112233; "
            "адрес — страна: Примерляндия, индекс: 500111, город: Пример, улица: Лесная, "
            "дом: 7Б, квартира: 15; email: elena.koz@example.test; "
            "номер телефона: +7 900 111-22-33; ИНН: 500111223344 (фиктивный); "
            "номер платёжной банковской карты: 4000 0000 0000 0002 (невалидный); "
            "CVV-код: 111; PIN-код карты: 2222; имя держателя карты: KOZLOVA ELENA."
        ),
        "values": [
            ("person", "Козлова Елена Викторовна"),
            ("birth_date", "22.11.1985"),
            ("birth_place", "г. Пример, Крайний край"),
            ("passport", "5011 778899"),
            ("citizenship", "Примерляндия"),
            ("passport_issuer", "УВД г. Примера"),
            ("passport_division_code", "500-111"),
            ("passport_issue_date", "22.11.2005"),
            ("driver_license", "9910 112233"),
            ("address_country", "Примерляндия"),
            ("address_postal_code", "500111"),
            ("address_city", "Пример"),
            ("address_street", "Лесная"),
            ("address_house", "7Б"),
            ("address_apartment", "15"),
            ("email", "elena.koz@example.test"),
            ("phone", "+7 900 111-22-33"),
            ("inn", "500111223344"),
            ("card", "4000 0000 0000 0002"),
            ("cvv", "111"),
            ("pin", "2222"),
            ("cardholder", "KOZLOVA ELENA"),
        ],
    },
    {
        "id": "neg-bare-long-number",
        "text": "код заказа 123456789012 и номер 4111222233334444 без меток",
        "values": [],
    },
    {"id": "neg-ordinary-date", "text": "встреча назначена на 12.03.2024 в офисе", "values": []},
    {
        "id": "neg-bank-address",
        "text": "адрес отделения Банка: г. Москва, ул. Тверская, д. 1",
        "values": [],
    },
    {"id": "neg-public-person", "text": "Александр Пушкин написал стихотворение", "values": []},
    {
        "id": "neg-editorial-contacts",
        "text": "Контакты редакции: Российский Красный Крест",
        "values": [],
    },
    {
        "id": "neg-fio-does-not-span-next",
        "text": "ФИО: Иванов Иван; гражданство: Россия;",
        "values": [("person", "Иванов Иван"), ("citizenship", "Россия")],
    },
    {
        "id": "neg-unknown-label",
        "text": "любимый цвет: синий; код склада: 9988776655",
        "values": [],
    },
    {
        "id": "free-client-name",
        "text": "клиента зовут Сергей Примерный.",
        "values": [("person", "Сергей Примерный")],
    },
    {
        "id": "free-birth-context",
        "text": "родился 6 июня 1990 года в семье",
        "values": [("birth_date", "6 июня 1990")],
    },
    {
        "id": "free-issuer",
        "text": "паспорт выдан 01.02.2015 ОВД Тестового района.",
        "values": [
            ("passport_issue_date", "01.02.2015"),
            ("passport_issuer", "ОВД Тестового района"),
        ],
    },
]


def _locate(text: str, value: str, cursor: int) -> tuple[int, int]:
    index = text.find(value, cursor)
    if index < 0:
        raise ValueError(f"value not found after {cursor}: {value!r}")
    return index, index + len(value)


def main() -> None:
    cases = []
    for raw in CASES:
        text = raw["text"]
        cursor = 0
        expected = []
        for pii_type, value in raw["values"]:
            start, end = _locate(text, value, cursor)
            expected.append({"type": pii_type, "start": start, "end": end})
            cursor = end
        cases.append({"id": raw["id"], "text": text, "expected": expected})

    doc = {
        "version": 1,
        "note": (
            "Prepared before detector changes for TASK_IMPROVE_PII_DETECTION. "
            "Expected spans are hand-authored synthetic values; offsets resolved from those values."
        ),
        "cases": cases,
    }
    OUT.write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    print(f"wrote {len(cases)} cases to {OUT}")


if __name__ == "__main__":
    main()
