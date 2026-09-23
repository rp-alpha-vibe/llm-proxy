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
import uuid
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
ALLOWED_SUFFIXES = frozenset(
    {
        ".py",
        ".yaml",
        ".yml",
        ".toml",
        ".txt",
        ".md",
        ".example",
        ".dockerignore",
    }
)
ALLOWED_NAMES = frozenset({"Dockerfile", "docker-compose.yml", ".dockerignore", ".env.example"})
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

SUBMISSION_README = """# llm-proxy — модуль защиты персональных данных

Проект хакатона «Альфавайб». Сервис обнаруживает в тексте персональные данные, заменяет их обозначениями и по повторному запросу восстанавливает известные значения. Сам llm-proxy **не вызывает языковую модель**: приложение отправляет очищенный текст модели и позже передаёт полученный ответ для восстановления данных.

## Как запустить

Понадобится Docker с Docker Compose; Python на компьютере не обязателен. В папке проекта скопируйте `.env.example` в `.env` (Linux/macOS: `cp .env.example .env`; PowerShell: `Copy-Item .env.example .env`). Задайте `LLM_PROXY_ENCRYPTION_KEY`: случайные 32 однобайтовых символа (ASCII); храните ключ только локально и не загружайте в репозиторий. Оставьте демонстрационные настройки `LLM_PROXY_DEFAULT_CONSUMER_ID=alfa_tester`.

```bash
docker compose up --build -d
curl http://localhost:8000/healthz
```

Проверка должна вернуть `{"status":"ok"}`. Эта проверка подтверждает ответ самого приложения, но не работу временного хранилища.

## Пример обращения

Запрос на маскирование **вымышленного** адреса:

```bash
curl -X POST "http://localhost:8000/process" \
  -H "Content-Type: application/json" \
  --data '{"payload":"Напишите на ivan@example.com.","payload_id":"archive-demo-001"}'
```

В ответ придёт JSON с полем `result`, например: `{"result":"Напишите на <EMAIL_1>."}`. Чтобы восстановить адрес, отправьте полученную строку из `result` в поле `payload` **с тем же** `payload_id`. Для восстановления данных в ответе языковой модели можно передать другой текст, содержащий уже известное обозначение, например `Ответьте сегодня на <EMAIL_1>.`. Изменённый текст сохранится, а обозначение будет заменено исходным адресом. Для новой независимой проверки используйте новый идентификатор.

`POST /process` принимает только два обязательных поля: `payload` (текст) и `payload_id` (идентификатор связанной последовательности запросов), а отвечает полем `result`. Запросы к языковой модели выполняет вызывающее приложение.

## Состав и настройка

Контейнер приложения использует FastAPI (обработка HTTP-запросов) и Redis (временное хранилище зашифрованных соответствий). В этой сборке Redis доступен только внутри сети Docker; данные удаляются автоматически по истечении срока. Система не записывает исходные персональные данные в технические журналы. Это исходный архив для проверки, поэтому внутренняя документация и сценарии испытаний в него не входят.

Для настройки другого приложения добавьте запись в раздел `systems` файла `config/systems.example.yaml`. Параметры `enabled`, `pii_types`, `allow_demask` и `mask_strategy` определяют доступ, категории поиска, разрешение восстановления и вид обозначений. Установите `LLM_PROXY_DEFAULT_CONSUMER_ID` равным идентификатору этой записи и перезапустите контейнеры. Выбор приложения происходит настройками развёртывания, а не дополнительным полем запроса.

Остановка: `docker compose down`.

**Термины:** персональные данные (PII) — сведения о человеке; языковая модель (LLM) — система искусственного интеллекта для обработки текста; маскирование — временная замена данных обозначениями; демаскирование — восстановление ранее заменённых данных.
"""


class PackageError(RuntimeError):
    """The archive contains a path the submission rules reject."""


def _suffix_allowed(relative: Path) -> bool:
    name = relative.name
    if name in ALLOWED_NAMES:
        return True
    if name.endswith(".example"):
        return True
    return relative.suffix.lower() in ALLOWED_SUFFIXES


def is_allowlisted(relative: Path) -> bool:
    posix = relative.as_posix()
    if posix in ALLOW_FILES:
        return True
    if not any(posix.startswith(f"{prefix}/") for prefix in ALLOW_DIRS):
        return False
    return _suffix_allowed(relative)


def is_blacklisted(relative: Path) -> bool:
    if set(relative.parts) & BLACKLIST_DIRS:
        return True
    name = relative.name
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return True
    return name.lower().endswith(BLACKLIST_SUFFIXES)


def _is_safe_source(root: Path, path: Path) -> bool:
    if path.is_symlink():
        return False
    if not path.is_file():
        return False
    try:
        resolved = path.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def iter_sources(root: Path) -> list[Path]:
    root = root.resolve()
    files: list[Path] = []
    for name in sorted(ALLOW_FILES):
        path = root / name
        if path.is_file() and not path.is_symlink() and _is_safe_source(root, path):
            files.append(path)
    for directory in ALLOW_DIRS:
        base = root / directory
        if not base.is_dir() or base.is_symlink():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            if not _is_safe_source(root, path):
                continue
            relative = path.relative_to(root)
            if is_blacklisted(relative) or not is_allowlisted(relative):
                continue
            files.append(path)
    return files


def inspect(archive_path: Path) -> list[str]:
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
    seen: set[str] = set()
    violations: list[str] = []
    for info in infos:
        name = info.filename
        relative = Path(name)
        is_symlink = bool(info.external_attr >> 16 & 0o170000 == 0o120000)
        if (
            name.endswith("/")
            or relative.is_absolute()
            or ".." in relative.parts
            or "\\" in name
            or name in seen
            or is_symlink
            or info.is_dir()
            or not is_allowlisted(relative)
            or is_blacklisted(relative)
            or not _suffix_allowed(relative)
        ):
            violations.append(name)
        seen.add(name)
    if violations:
        raise PackageError(f"archive rejected: {violations}")
    missing = REQUIRED - set(names)
    if missing:
        raise PackageError(f"archive missing: {sorted(missing)}")
    return names


def build(root: Path, output: Path) -> list[str]:
    root = root.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        written: set[str] = set()
        for path in iter_sources(root):
            relative = path.relative_to(root)
            if is_blacklisted(relative) or not is_allowlisted(relative):
                continue
            posix = relative.as_posix()
            if posix in written:
                raise PackageError(f"duplicate archive path: {posix}")
            if posix == "README.md":
                archive.writestr(posix, SUBMISSION_README)
            else:
                archive.write(path, posix)
            written.add(posix)
        if "README.md" not in written:
            archive.writestr("README.md", SUBMISSION_README)
            written.add("README.md")
    return inspect(output)


def _extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.namelist():
        target = (destination / member).resolve()
        if not target.is_relative_to(root):
            raise PackageError(f"unsafe archive path: {member}")
        archive.extract(member, destination)


def _post_process(base_url: str, payload: str, payload_id: str, timeout: float = 30.0) -> str:
    body = json.dumps({"payload": payload, "payload_id": payload_id}).encode()
    request = urllib.request.Request(
        f"{base_url}/process",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload_body = json.loads(response.read().decode())
    result = payload_body.get("result")
    if response.status != 200 or not isinstance(result, str):
        raise PackageError("unexpected process response")
    return result


def _wait_until_ready(base_url: str) -> None:
    last_error: Exception | None = None
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, TimeoutError, urllib.error.URLError, urllib.error.HTTPError) as error:
            last_error = error
            time.sleep(1)
    raise PackageError(f"packaged service did not answer /healthz: {last_error}")


def smoke(archive_path: Path) -> None:
    """Build and exercise mask, retry, and exact unmask from the ZIP only."""
    key = "0123456789abcdef" * 2
    project = f"llm-proxy-pkg-{uuid.uuid4().hex[:8]}"
    host_port = "18000"
    base_url = f"http://127.0.0.1:{host_port}"
    inspect(archive_path)
    with tempfile.TemporaryDirectory(prefix="llm-proxy-pkg-") as temporary:
        destination = Path(temporary)
        with zipfile.ZipFile(archive_path) as archive:
            _extract(archive, destination)
        compose_file = destination / "docker-compose.yml"
        compose_file.write_text(
            compose_file.read_text(encoding="utf-8").replace('"8000:8000"', f'"{host_port}:8000"'),
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["LLM_PROXY_ENCRYPTION_KEY"] = key
        env["LLM_PROXY_WEB_WORKERS"] = "1"
        compose = ["docker", "compose", "-p", project]
        try:
            subprocess.run([*compose, "up", "--build", "-d"], cwd=destination, check=True, env=env)
            _wait_until_ready(base_url)
            original = "contact user@example.com"
            payload_id = "pkg-smoke-1"
            masked = _post_process(base_url, original, payload_id)
            if "user@example.com" in masked:
                raise PackageError("mask left the original email visible")
            retry = _post_process(base_url, original, payload_id)
            if retry != masked:
                raise PackageError("retry did not return the same mask")
            restored = _post_process(base_url, masked, payload_id)
            if restored != original:
                raise PackageError("exact unmask did not restore the original text")
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
