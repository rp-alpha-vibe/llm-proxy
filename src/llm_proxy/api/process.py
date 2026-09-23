from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis.exceptions import RedisError

from llm_proxy.application.overload import ConcurrencyLimitExceeded
from llm_proxy.application.process_service import (
    DemaskNotAllowedError,
    ProcessServiceError,
    SessionStateError,
)
from llm_proxy.observability.logging import ProcessObservation
from llm_proxy.observability.timing import redis_seconds, start_redis_timing
from llm_proxy.observability.tokens import count_tokens
from llm_proxy.policies.loader import (
    ConsumerNotAllowedError,
    PolicyConfigurationError,
    PolicyNotFoundError,
)
from llm_proxy.state.crypto import StateEncryptionError


class APIError(Exception):
    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers


class ProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # Bound memory while accepting a 100_000-token profile (§7). Whitespace
    # tokens can exceed 1_000_000 characters for longer words.
    payload: str = Field(min_length=1, max_length=8_000_000)
    payload_id: str = Field(min_length=1, max_length=256)

    @field_validator("payload")
    @classmethod
    def payload_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("payload must not be blank")
        return value

    @field_validator("payload_id")
    @classmethod
    def payload_id_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("payload_id must not be blank")
        return value


class ProcessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    result: str


def create_process_router() -> APIRouter:
    router = APIRouter()

    @router.post("/process", response_model=ProcessResponse)
    async def process(payload: ProcessRequest, request: Request) -> ProcessResponse:
        observation = ProcessObservation(
            payload_chars=len(payload.payload),
            token_count=count_tokens(payload.payload),
        )
        request.state.process_observation = observation
        start_redis_timing()
        try:
            settings = request.app.state.settings
            context = request.app.state.consumer_resolver.resolve(settings.default_consumer_id)
            observation.consumer = context.consumer_id
            async with request.app.state.concurrency_gate.slot():
                service = request.app.state.process_service
                if service is None:
                    raise APIError(503, "state unavailable")
                result = await service.process(
                    context,
                    payload.payload_id,
                    payload.payload,
                )
            observation.operation = result.outcome.value
            observation.pii_types = result.pii_types
            observation.pii_count = result.pii_count
            observation.pii_type_counts = result.pii_type_counts
            observation.fresh_detection = result.fresh_detection
            observation.detect_ms = result.detect_ms
            return ProcessResponse(result=result.result)
        except APIError:
            observation.operation = "rejected"
            raise
        except ConcurrencyLimitExceeded as exc:
            retry_after = str(request.app.state.concurrency_gate.retry_after_seconds)
            raise APIError(
                429,
                "overloaded",
                headers={"Retry-After": retry_after},
            ) from exc
        except (ConsumerNotAllowedError, PolicyNotFoundError):
            raise APIError(403, "consumer not allowed") from None
        except PolicyConfigurationError:
            raise APIError(503, "policy unavailable") from None
        except DemaskNotAllowedError:
            raise APIError(403, "demask not allowed") from None
        except (
            SessionStateError,
            ProcessServiceError,
            StateEncryptionError,
            RedisError,
            ConnectionError,
            TimeoutError,
        ):
            raise APIError(503, "state unavailable") from None
        except Exception:
            observation.operation = "rejected"
            raise APIError(500, "internal error") from None
        finally:
            observation.redis_ms = redis_seconds() * 1000

    return router


def validation_error_handler(_: Request, __: Any) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "invalid request"})


def api_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, APIError):
        return internal_error_handler(_, exc)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


def internal_error_handler(_: Request, __: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": "internal error"})
