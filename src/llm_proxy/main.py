from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response

from llm_proxy.api.process import (
    APIError,
    api_error_handler,
    create_process_router,
    internal_error_handler,
    validation_error_handler,
)
from llm_proxy.application.overload import ConcurrencyGate
from llm_proxy.application.process_service import ProcessService
from llm_proxy.detection.contextual import register_contextual_detectors
from llm_proxy.detection.engine import PiiEngine
from llm_proxy.detection.registry import DetectorRegistry
from llm_proxy.detection.structured import register_structured_detectors
from llm_proxy.masking.base import MaskStrategyName
from llm_proxy.masking.competition import CompetitionMaskStrategy
from llm_proxy.masking.placeholder import PlaceholderMaskStrategy
from llm_proxy.masking.routing import RoutingMaskStrategy
from llm_proxy.observability.metrics import render_metrics
from llm_proxy.observability.middleware import observe_process
from llm_proxy.policies.consumer_resolver import ConfigConsumerResolver
from llm_proxy.policies.loader import YamlPolicyRegistry
from llm_proxy.policies.models import ConsumerResolver
from llm_proxy.settings import require_encryption_key
from llm_proxy.state.crypto import SessionRecordCodec
from llm_proxy.state.redis_store import RedisStateStore

from .settings import Settings, get_settings


def _build_consumer_resolver(settings: Settings) -> ConsumerResolver:
    registry = YamlPolicyRegistry(settings.config_path)
    return ConfigConsumerResolver(registry, settings.default_consumer_id)


def _build_detector() -> PiiEngine:
    registry = DetectorRegistry()
    register_structured_detectors(registry)
    register_contextual_detectors(registry)
    return PiiEngine(registry)


def _build_mask_strategy() -> RoutingMaskStrategy:
    return RoutingMaskStrategy(
        {
            MaskStrategyName.PLACEHOLDER.value: PlaceholderMaskStrategy(),
            MaskStrategyName.COMPETITION.value: CompetitionMaskStrategy(),
        }
    )


def _build_process_service(settings: Settings) -> ProcessService | None:
    if settings.encryption_key is None:
        return None

    encryption_key = require_encryption_key(settings)
    codec = SessionRecordCodec(encryption_key)
    state_store = RedisStateStore(settings.redis_url, codec)
    return ProcessService(
        state_store=state_store,
        detector=_build_detector(),
        mask_strategy=_build_mask_strategy(),
        session_ttl_seconds=settings.session_ttl_seconds,
        post_demask_ttl_seconds=settings.post_demask_ttl_seconds,
    )


def create_app(
    settings: Settings | None = None,
    *,
    process_service: ProcessService | None = None,
    consumer_resolver: ConsumerResolver | None = None,
    concurrency_gate: ConcurrencyGate | None = None,
) -> FastAPI:
    resolved_settings = (
        get_settings() if settings is None else Settings.model_validate(settings.model_dump())
    )
    application = FastAPI(title="llm-proxy", version="0.1.0")
    application.state.settings = resolved_settings
    application.state.consumer_resolver = consumer_resolver or _build_consumer_resolver(
        resolved_settings
    )
    application.state.concurrency_gate = concurrency_gate or ConcurrencyGate(
        resolved_settings.max_concurrency,
        retry_after_seconds=resolved_settings.overload_retry_after_seconds,
    )
    application.state.process_service = (
        process_service
        if process_service is not None
        else _build_process_service(resolved_settings)
    )
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(APIError, api_error_handler)
    application.add_exception_handler(Exception, internal_error_handler)
    application.middleware("http")(observe_process)
    application.include_router(create_process_router())

    @application.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(
            content=render_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @application.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()


def main() -> None:
    import os
    import tempfile
    from pathlib import Path

    import uvicorn

    settings = get_settings()
    if settings.web_workers > 1:
        directory = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
        if not directory:
            directory = str(Path(tempfile.gettempdir()) / "llm-proxy-prometheus")
            os.environ["PROMETHEUS_MULTIPROC_DIR"] = directory
        Path(directory).mkdir(parents=True, exist_ok=True)
        uvicorn.run(
            "llm_proxy.main:app",
            host=settings.app_host,
            port=settings.app_port,
            workers=settings.web_workers,
        )
        return

    uvicorn.run(
        app,
        host=settings.app_host,
        port=settings.app_port,
    )


if __name__ == "__main__":
    main()
