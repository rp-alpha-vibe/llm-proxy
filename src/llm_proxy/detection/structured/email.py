import re
from collections.abc import Collection, Sequence

from llm_proxy.detection.models import Detection, PiiType
from llm_proxy.detection.structured.common import make_detection

_EMAIL = re.compile(
    r"(?<![\w.])"
    r"[A-Z0-9][A-Z0-9._%+-]{0,63}"
    r"@"
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)*"
    r"\.[A-Z]{2,24}"
    r"(?![\w])",
    re.IGNORECASE,
)


class EmailDetector:
    def detect(
        self,
        text: str,
        enabled_types: Collection[PiiType],
    ) -> Sequence[Detection]:
        if PiiType.EMAIL not in enabled_types:
            return ()
        found: list[Detection] = []
        for match in _EMAIL.finditer(text):
            value = match.group(0)
            local, domain = value.rsplit("@", 1)
            if _invalid_label(local) or _invalid_label(domain) or "." not in domain:
                continue
            found.append(
                make_detection(PiiType.EMAIL, match.start(), match.end(), "email", confidence=1.0)
            )
        return tuple(found)


def _invalid_label(value: str) -> bool:
    if value.startswith((".", "-")) or value.endswith((".", "-")) or ".." in value:
        return True
    return any(label.startswith("-") or label.endswith("-") for label in value.split("."))
