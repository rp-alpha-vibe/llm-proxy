from pathlib import Path

import pytest

from llm_proxy.policies.consumer_resolver import ConfigConsumerResolver
from llm_proxy.policies.loader import (
    ConsumerNotAllowedError,
    PolicyConfigurationError,
    PolicyNotFoundError,
    YamlPolicyRegistry,
)


def write_config(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_yaml_policy_registry_loads_and_normalizes_policies(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: competition
  disabled:
    enabled: false
    pii_types:
      - email
    allow_demask: false
    mask_strategy: placeholder
""",
    )

    registry = YamlPolicyRegistry(config_path)
    policy = registry.require("alfa_tester")

    assert policy.policy_id == "policy-alfa_tester"
    assert policy.system_id == "alfa_tester"
    assert policy.enabled is True
    assert policy.allow_demask is True
    assert policy.mask_strategy == "competition"
    assert registry.get("missing") is None
    with pytest.raises(PolicyNotFoundError):
        registry.require("missing")


def test_consumer_resolver_rejects_unknown_and_disabled_consumers(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(
        config_path,
        """systems:
  alfa_tester:
    enabled: true
    pii_types: all
    allow_demask: true
    mask_strategy: competition
  disabled:
    enabled: false
    pii_types:
      - email
    allow_demask: false
    mask_strategy: placeholder
""",
    )
    registry = YamlPolicyRegistry(config_path)
    resolver = ConfigConsumerResolver(registry, "alfa_tester")

    assert resolver.resolve("alfa_tester").consumer_id == "alfa_tester"
    with pytest.raises(ConsumerNotAllowedError):
        resolver.resolve("disabled")
    with pytest.raises(ConsumerNotAllowedError):
        resolver.resolve("missing")


def test_yaml_policy_registry_rejects_invalid_documents(tmp_path: Path) -> None:
    config_path = tmp_path / "systems.yaml"
    write_config(config_path, "systems: []\n")

    with pytest.raises(PolicyConfigurationError):
        YamlPolicyRegistry(config_path)

    write_config(config_path, "not-systems: {}\n")
    with pytest.raises(PolicyConfigurationError):
        YamlPolicyRegistry(config_path)
