from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import ConsumerPolicy


class PolicyConfigurationError(ValueError):
    pass


class PolicyNotFoundError(LookupError):
    pass


class ConsumerNotAllowedError(PermissionError):
    pass


class YamlPolicyRegistry:
    def __init__(self, config_path: str | Path) -> None:
        self._path = Path(config_path)
        self._policies = self._load()

    def get(self, system_id: str) -> ConsumerPolicy | None:
        return self._policies.get(system_id)

    def require(self, system_id: str) -> ConsumerPolicy:
        policy = self.get(system_id)
        if policy is None:
            raise PolicyNotFoundError("consumer policy not found")
        return policy

    def _load(self) -> dict[str, ConsumerPolicy]:
        try:
            raw_document = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise PolicyConfigurationError("invalid policy configuration") from exc

        if not isinstance(raw_document, dict):
            raise PolicyConfigurationError("invalid policy configuration")
        systems = raw_document.get("systems")
        if not isinstance(systems, dict) or not systems:
            raise PolicyConfigurationError("invalid policy configuration")

        policies: dict[str, ConsumerPolicy] = {}
        for system_id, raw_policy in systems.items():
            if not isinstance(system_id, str) or not system_id.strip():
                raise PolicyConfigurationError("invalid policy configuration")
            if not isinstance(raw_policy, dict):
                raise PolicyConfigurationError("invalid policy configuration")

            policy_data = dict(raw_policy)
            policy_data["policy_id"] = f"policy-{system_id}"
            policy_data["system_id"] = system_id
            try:
                policy = ConsumerPolicy.model_validate(policy_data)
            except ValidationError as exc:
                raise PolicyConfigurationError("invalid policy configuration") from exc
            policies[system_id] = policy
        return policies
