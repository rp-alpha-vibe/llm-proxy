from dataclasses import dataclass
from itertools import pairwise

_INVISIBLE = frozenset("\u00ad\u200b\u200c\u200d\ufeff")


@dataclass(frozen=True, slots=True)
class TextView:
    original: str
    normalized: str
    normalized_to_original: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        mapping = self.normalized_to_original
        if mapping is None:
            if self.original != self.normalized:
                raise ValueError("length-preserving view requires identical text")
            return
        if len(mapping) != len(self.normalized):
            raise ValueError("offset map must cover the normalized text")
        if any(current <= previous for previous, current in pairwise(mapping)):
            raise ValueError("offset map must increase")
        if mapping and (mapping[0] < 0 or mapping[-1] >= len(self.original)):
            raise ValueError("offset map points outside the original text")

    @staticmethod
    def from_text(text: str) -> "TextView":
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if not any(char in _INVISIBLE for char in text):
            return TextView(text, text, None)

        characters: list[str] = []
        indexes: list[int] = []
        for index, char in enumerate(text):
            if char in _INVISIBLE:
                continue
            characters.append(char)
            indexes.append(index)
        return TextView(text, "".join(characters), tuple(indexes))

    def to_original_span(self, start: int, end: int) -> tuple[int, int]:
        if start < 0 or end <= start or end > len(self.normalized):
            raise ValueError("span is outside the normalized text")
        mapping = self.normalized_to_original
        if mapping is None:
            return start, end
        return mapping[start], mapping[end - 1] + 1
