import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from time import perf_counter

from llm_proxy.detection.models import Detector, PiiType
from llm_proxy.masking.base import MaskContext, MaskStrategy
from llm_proxy.policies.models import ConsumerContext, ConsumerPolicy
from llm_proxy.state.models import SessionRecord, StateStore, make_session_key


class ProcessOutcome(StrEnum):
    MASKED = "mask"
    EXACT_UNMASKED = "exact_unmask"
    PRODUCT_DEMASKED = "product_unmask"


class ProcessServiceError(RuntimeError):
    pass


class DemaskNotAllowedError(ProcessServiceError):
    pass


class SessionStateError(ProcessServiceError):
    pass


_PLACEHOLDER_RE = re.compile(r"\[\[[^\]]+\]\]")


def _type_counts(pii_types: Iterable[PiiType]) -> tuple[tuple[str, int], ...]:
    counts: Counter[str] = Counter(pii_type.value for pii_type in pii_types)
    return tuple(sorted(counts.items()))


@dataclass(frozen=True, slots=True)
class ProcessResult:
    result: str
    outcome: ProcessOutcome
    pii_type_counts: tuple[tuple[str, int], ...] = ()
    fresh_detection: bool = False
    detect_ms: float = 0.0

    @property
    def pii_count(self) -> int:
        return sum(count for _, count in self.pii_type_counts)

    @property
    def pii_types(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.pii_type_counts)


class ProcessService:
    def __init__(
        self,
        state_store: StateStore,
        detector: Detector,
        mask_strategy: MaskStrategy,
        *,
        session_ttl_seconds: int = 900,
        post_demask_ttl_seconds: int = 120,
    ) -> None:
        if session_ttl_seconds <= 0 or post_demask_ttl_seconds <= 0:
            raise ValueError("process TTL values must be positive")

        self._state_store = state_store
        self._detector = detector
        self._mask_strategy = mask_strategy
        self._session_ttl_seconds = session_ttl_seconds
        self._post_demask_ttl_seconds = post_demask_ttl_seconds

    async def process(
        self,
        context: ConsumerContext,
        payload_id: str,
        payload: str,
    ) -> ProcessResult:
        self._validate_context(context)
        if not isinstance(payload, str):
            raise TypeError("payload must be a string")

        redis_key = make_session_key(context.consumer_id, payload_id)
        record = await self._state_store.get(redis_key)
        if record is None:
            return await self._create_session(context, redis_key, payload)
        return await self._process_existing(context.policy, redis_key, record, payload)

    async def _create_session(
        self,
        context: ConsumerContext,
        redis_key: str,
        payload: str,
    ) -> ProcessResult:
        started = perf_counter()
        detections = self._detector.detect(payload, context.policy.pii_types)
        detect_ms = (perf_counter() - started) * 1000
        mask_result = self._mask_strategy.mask(
            payload,
            detections,
            MaskContext(
                policy_id=context.policy.policy_id,
                mask_strategy=context.policy.mask_strategy,
            ),
        )
        record = SessionRecord(
            original_text=payload,
            masked_text=mask_result.text,
            entities=mask_result.entities,
            offset_map=mask_result.offset_map,
            policy_id=context.policy.policy_id,
            mask_strategy=context.policy.mask_strategy,
        )

        created = await self._state_store.create_if_absent(
            redis_key,
            record,
            self._session_ttl_seconds,
        )
        if created:
            return ProcessResult(
                mask_result.text,
                ProcessOutcome.MASKED,
                _type_counts(item.type for item in detections),
                True,
                detect_ms,
            )

        winner = await self._state_store.get(redis_key)
        if winner is None:
            raise SessionStateError("session disappeared after concurrent create")
        self._validate_record_policy(winner, context.policy)
        return await self._process_existing(context.policy, redis_key, winner, payload)

    async def _process_existing(
        self,
        policy: ConsumerPolicy,
        redis_key: str,
        record: SessionRecord,
        payload: str,
    ) -> ProcessResult:
        self._validate_record_policy(record, policy)

        type_counts = _type_counts(entity.type for entity in record.entities)
        if payload == record.original_text:
            return ProcessResult(record.masked_text, ProcessOutcome.MASKED, type_counts)

        if payload == record.masked_text:
            if not policy.allow_demask:
                raise DemaskNotAllowedError()
            await self._shorten_ttl(redis_key)
            return ProcessResult(record.original_text, ProcessOutcome.EXACT_UNMASKED, type_counts)

        if not policy.allow_demask:
            raise DemaskNotAllowedError()

        result = self._demask_product(payload, record)
        await self._shorten_ttl(redis_key)
        return ProcessResult(result, ProcessOutcome.PRODUCT_DEMASKED, type_counts)

    async def _shorten_ttl(self, redis_key: str) -> None:
        updated = await self._state_store.update_ttl(redis_key, self._post_demask_ttl_seconds)
        if not updated:
            raise SessionStateError("session ttl update failed")

    @staticmethod
    def _demask_product(text: str, record: SessionRecord) -> str:
        values_by_mask: dict[str, set[str]] = {}
        for entity in record.entities:
            value = record.original_text[entity.original_start : entity.original_end]
            values_by_mask.setdefault(entity.rendered_mask, set()).add(value)
        mappings = {
            mask: next(iter(values)) for mask, values in values_by_mask.items() if len(values) == 1
        }
        placeholder_tokens = {match.group(0) for match in _PLACEHOLDER_RE.finditer(text)}
        tokens = sorted(set(mappings) | placeholder_tokens, key=len, reverse=True)
        if not tokens:
            return text

        token_pattern = re.compile("|".join(re.escape(token) for token in tokens))

        def replace_token(match: re.Match[str]) -> str:
            token = match.group(0)
            return mappings.get(token, token)

        return token_pattern.sub(replace_token, text)

    @staticmethod
    def _validate_context(context: ConsumerContext) -> None:
        if context.consumer_id != context.policy.system_id:
            raise ValueError("consumer policy mismatch")

    @staticmethod
    def _validate_record_policy(record: SessionRecord, policy: ConsumerPolicy) -> None:
        if record.policy_id != policy.policy_id:
            raise SessionStateError("session policy mismatch")
