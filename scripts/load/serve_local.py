"""Start the app for a local load profile.

Uses the same synthetic encryption key as the test suite. Redis must already
be listening on LLM_PROXY_REDIS_URL or redis://127.0.0.1:6379/0.
"""

import os

os.environ.setdefault("LLM_PROXY_REDIS_URL", "redis://127.0.0.1:6379/0")
os.environ.setdefault("LLM_PROXY_ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("LLM_PROXY_WEB_WORKERS", "8")
os.environ.setdefault("LLM_PROXY_MAX_CONCURRENCY", "1000")
os.environ.setdefault("LLM_PROXY_CONFIG_PATH", "config/systems.example.yaml")


def main() -> None:
    from llm_proxy.main import main as serve

    serve()


if __name__ == "__main__":
    main()
