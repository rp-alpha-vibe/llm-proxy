"""Build the submission source ZIP and reject anything outside the allowlist."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALLOW_FILES = frozenset(
    {
        "pyproject.toml",
        "Dockerfile",
        "docker-compose.yml",
        ".dockerignore",
        "README.md",
        ".env.example",
    }
)
ALLOW_DIRS = ("src", "config")
REQUIRED = frozenset(
    {
        "pyproject.toml",
        "Dockerfile",
        "docker-compose.yml",
        "README.md",
        "src/llm_proxy/main.py",
        "config/systems.example.yaml",
    }
)
BLACKLIST_DIRS = frozenset(
    {
        ".git",
        ".agents",
        ".kilo",
        ".idea",
        ".vscode",
        "docs",
        "tests",
        "scripts",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "target",
        "build",
        "dist",
        "out",
        "bin",
        "obj",
        "__pycache__",
        "coverage",
        "htmlcov",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".github",
    }
)
BLACKLIST_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dll",
    ".exe",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".mp4",
    ".mov",
    ".pdf",
    ".pptx",
    ".wav",
    ".mp3",
)


class PackageError(RuntimeError):
    """The archive contains a path the submission rules reject."""


def is_allowlisted(relative: Path) -> bool:
    posix = relative.as_posix()
    if posix in ALLOW_FILES:
        return True
    return any(posix.startswith(f"{prefix}/") for prefix in ALLOW_DIRS)


def is_blacklisted(relative: Path) -> bool:
    if set(relative.parts) & BLACKLIST_DIRS:
        return True
    name = relative.name
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return True
    return name.lower().endswith(BLACKLIST_SUFFIXES)


def iter_sources(root: Path) -> list[Path]:
    files: list[Path] = []
    for name in sorted(ALLOW_FILES):
        path = root / name
        if path.is_file():
            files.append(path)
    for directory in ALLOW_DIRS:
        base = root / directory
        if not base.is_dir():
            continue
        files.extend(path for path in sorted(base.rglob("*")) if path.is_file())
    return files


def inspect(archive_path: Path) -> list[str]:
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
    violations: list[str] = []
    for name in names:
        relative = Path(name)
        if (
            name.endswith("/")
            or relative.is_absolute()
            or ".." in relative.parts
            or "\\" in name
            or not is_allowlisted(relative)
            or is_blacklisted(relative)
        ):
            violations.append(name)
    if violations:
        raise PackageError(f"archive rejected: {violations}")
    missing = REQUIRED - set(names)
    if missing:
        raise PackageError(f"archive missing: {sorted(missing)}")
    return names


def build(root: Path, output: Path) -> list[str]:
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in iter_sources(root):
            relative = path.relative_to(root)
            if is_blacklisted(relative) or not is_allowlisted(relative):
                continue
            archive.write(path, relative.as_posix())
    return inspect(output)


def _extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.namelist():
        target = (destination / member).resolve()
        if not target.is_relative_to(root):
            raise PackageError(f"unsafe archive path: {member}")
        archive.extract(member, destination)


def smoke(archive_path: Path) -> None:
    """Build and start the stack from the ZIP, then call POST /process."""
    key = "0123456789abcdef" * 2
    with tempfile.TemporaryDirectory(prefix="llm-proxy-pkg-") as temporary:
        destination = Path(temporary)
        with zipfile.ZipFile(archive_path) as archive:
            _extract(archive, destination)
        compose_file = destination / "docker-compose.yml"
        compose_file.write_text(
            compose_file.read_text(encoding="utf-8").replace('"8000:8000"', '"18000:8000"'),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["LLM_PROXY_ENCRYPTION_KEY"] = key
        env["LLM_PROXY_WEB_WORKERS"] = "1"
        compose = ["docker", "compose", "-p", "llm-proxy-pkg-smoke"]
        try:
            subprocess.run([*compose, "up", "--build", "-d"], cwd=destination, check=True, env=env)
            _wait_until_ready()
        except PackageError as error:
            logs = subprocess.run(
                [*compose, "logs", "app"],
                cwd=destination,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )
            combined = f"{logs.stdout}\n{logs.stderr}".replace(key, "[redacted]")
            raise PackageError(f"{error}\n{combined[-2000:]}") from None
        finally:
            subprocess.run([*compose, "down", "-v"], cwd=destination, check=False, env=env)


def _wait_until_ready() -> None:
    payload = json.dumps(
        {"payload": "contact user@example.com", "payload_id": "pkg-smoke-1"}
    ).encode()
    request = urllib.request.Request(
        "http://127.0.0.1:18000/process",
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    last_error: Exception | None = None
    for _ in range(30):
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                body = json.loads(response.read().decode())
            result = body.get("result")
            if (
                response.status != 200
                or not isinstance(result, str)
                or "user@example.com" in result
            ):
                raise PackageError("unexpected process response")
            return
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:300]
            last_error = RuntimeError(f"HTTP {error.code} {detail}")
            time.sleep(1)
        except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(1)
    raise PackageError(f"packaged service did not answer /process: {last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the submission source ZIP")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "llm-proxy-src.zip")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    names = build(ROOT, args.output)
    print(f"wrote {args.output} ({len(names)} files)")
    if args.smoke:
        smoke(args.output)
        print("smoke passed")


if __name__ == "__main__":
    main()
