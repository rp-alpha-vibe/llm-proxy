from .loader import ConsumerNotAllowedError, PolicyNotFoundError, YamlPolicyRegistry
from .models import ConsumerContext, ConsumerResolver


class ConfigConsumerResolver(ConsumerResolver):
    def __init__(self, registry: YamlPolicyRegistry, default_consumer_id: str) -> None:
        if not default_consumer_id.strip():
            raise ValueError("default_consumer_id must not be blank")
        self._registry = registry
        self._default_consumer_id = default_consumer_id

    def resolve(self, consumer_id: str) -> ConsumerContext:
        selected_consumer_id = consumer_id or self._default_consumer_id
        try:
            policy = self._registry.require(selected_consumer_id)
        except PolicyNotFoundError as exc:
            raise ConsumerNotAllowedError("consumer not allowed") from exc
        if not policy.enabled:
            raise ConsumerNotAllowedError("consumer not allowed")
        return ConsumerContext(
            consumer_id=selected_consumer_id,
            policy=policy,
        )
