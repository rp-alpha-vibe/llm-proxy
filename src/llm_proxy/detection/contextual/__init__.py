from llm_proxy.detection.contextual.address import AddressDetector
from llm_proxy.detection.contextual.dates import BirthDateDetector, PassportIssueDateDetector
from llm_proxy.detection.contextual.person import CardholderDetector, PersonDetector
from llm_proxy.detection.contextual.questionnaire import QuestionnaireDetector
from llm_proxy.detection.contextual.records import (
    BirthPlaceDetector,
    CitizenshipDetector,
    PassportIssuerDetector,
)
from llm_proxy.detection.contextual.secrets import CvvDetector, PinDetector
from llm_proxy.detection.models import PiiType
from llm_proxy.detection.registry import DetectorPriority, DetectorRegistry


def register_contextual_detectors(registry: DetectorRegistry) -> None:
    registrations = (
        (
            QuestionnaireDetector(),
            (
                PiiType.PERSON,
                PiiType.BIRTH_DATE,
                PiiType.BIRTH_PLACE,
                PiiType.CITIZENSHIP,
                PiiType.PASSPORT_ISSUER,
                PiiType.PASSPORT_ISSUE_DATE,
                PiiType.INN,
                PiiType.PAYMENT_CARD,
                PiiType.CARDHOLDER,
                PiiType.ADDRESS_COUNTRY,
                PiiType.ADDRESS_CITY,
                PiiType.ADDRESS_STREET,
                PiiType.ADDRESS_BUILDING,
                PiiType.ADDRESS_UNIT,
                PiiType.ADDRESS_POSTAL_CODE,
            ),
        ),
        (BirthDateDetector(), (PiiType.BIRTH_DATE,)),
        (PassportIssueDateDetector(), (PiiType.PASSPORT_ISSUE_DATE,)),
        (CvvDetector(), (PiiType.CVV,)),
        (PinDetector(), (PiiType.PIN,)),
        (CitizenshipDetector(), (PiiType.CITIZENSHIP,)),
        (BirthPlaceDetector(), (PiiType.BIRTH_PLACE,)),
        (PassportIssuerDetector(), (PiiType.PASSPORT_ISSUER,)),
        (
            AddressDetector(),
            (
                PiiType.ADDRESS,
                PiiType.ADDRESS_COUNTRY,
                PiiType.ADDRESS_REGION,
                PiiType.ADDRESS_DISTRICT,
                PiiType.ADDRESS_CITY,
                PiiType.ADDRESS_STREET,
                PiiType.ADDRESS_BUILDING,
                PiiType.ADDRESS_UNIT,
                PiiType.ADDRESS_POSTAL_CODE,
            ),
        ),
        (PersonDetector(), (PiiType.PERSON,)),
        (CardholderDetector(), (PiiType.CARDHOLDER,)),
    )
    for detector, types in registrations:
        registry.register(detector, types=types, priority=DetectorPriority.CONTEXT)
