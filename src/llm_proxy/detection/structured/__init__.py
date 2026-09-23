from llm_proxy.detection.models import PiiType
from llm_proxy.detection.registry import DetectorPriority, DetectorRegistry
from llm_proxy.detection.structured.division_code import DivisionCodeDetector
from llm_proxy.detection.structured.driver_license import DriverLicenseDetector
from llm_proxy.detection.structured.email import EmailDetector
from llm_proxy.detection.structured.inn import InnDetector
from llm_proxy.detection.structured.pan import PanDetector
from llm_proxy.detection.structured.passport import PassportDetector
from llm_proxy.detection.structured.phone import PhoneDetector


def register_structured_detectors(registry: DetectorRegistry) -> None:
    registrations = (
        (EmailDetector(), (PiiType.EMAIL,)),
        (PhoneDetector(), (PiiType.PHONE,)),
        (InnDetector(), (PiiType.INN,)),
        (PanDetector(), (PiiType.PAYMENT_CARD,)),
        (PassportDetector(), (PiiType.PASSPORT,)),
        (DivisionCodeDetector(), (PiiType.PASSPORT_DIVISION_CODE,)),
        (DriverLicenseDetector(), (PiiType.DRIVER_LICENSE,)),
    )
    for detector, types in registrations:
        registry.register(detector, types=types, priority=DetectorPriority.STRUCTURED)
