import zipfile
from pathlib import Path

import pytest
from scripts.package import (
    SUBMISSION_README,
    PackageError,
    build,
    inspect,
    is_allowlisted,
)

ROOT = Path(__file__).resolve().parents[1]


def test_submission_zip_keeps_runtime_sources_and_drops_internal_files(tmp_path: Path) -> None:
    archive = tmp_path / "llm-proxy-src.zip"

    names = set(build(ROOT, archive))

    assert "src/llm_proxy/main.py" in names
    assert "config/systems.example.yaml" in names
    assert "Dockerfile" in names
    assert "README.md" in names
    assert ".env.example" in names
    forbidden = ("docs/", "tests/", "scripts/", ".agents/", ".git/")
    assert not any(name.startswith(forbidden) for name in names)
    assert not any(
        name.endswith((".pyc", ".png", ".zip")) or "__pycache__" in name for name in names
    )
    with zipfile.ZipFile(archive) as handle:
        readme = handle.read("README.md").decode("utf-8")
    assert readme == SUBMISSION_README
    assert "scripts/verify.py" not in readme
    assert "AGENTS.md" not in readme
    assert "docs/" not in readme
    inspect(archive)


def test_inspect_rejects_a_blacklisted_member(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("pyproject.toml", "")
        handle.writestr("docs/REQUIREMENTS.md", "secret")

    with pytest.raises(PackageError, match="archive rejected"):
        inspect(archive)


def test_inspect_rejects_duplicate_paths(tmp_path: Path) -> None:
    archive = tmp_path / "dup.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("pyproject.toml", "a")
        handle.writestr("pyproject.toml", "b")

    with pytest.raises(PackageError, match="archive rejected"):
        inspect(archive)


def test_build_skips_foreign_config_and_source_files(tmp_path: Path) -> None:
    project = tmp_path / "project"
    (project / "src" / "llm_proxy").mkdir(parents=True)
    (project / "config").mkdir()
    (project / "src" / "llm_proxy" / "main.py").write_text("x = 1\n", encoding="utf-8")
    (project / "config" / "systems.example.yaml").write_text("systems: {}\n", encoding="utf-8")
    (project / "config" / "secrets.env").write_text("SECRET=1\n", encoding="utf-8")
    (project / "src" / "llm_proxy" / "notes.bin").write_bytes(b"\x00\x01")
    for name in (
        "pyproject.toml",
        "Dockerfile",
        "docker-compose.yml",
        ".dockerignore",
        "README.md",
        ".env.example",
    ):
        (project / name).write_text(name, encoding="utf-8")

    names = set(build(project, tmp_path / "out.zip"))

    assert "config/secrets.env" not in names
    assert "src/llm_proxy/notes.bin" not in names
    assert "src/llm_proxy/main.py" in names
    assert not is_allowlisted(Path("config/secrets.env"))
    assert not is_allowlisted(Path("src/llm_proxy/notes.bin"))


def test_build_skips_symlink_outside_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside.txt"
    outside.write_text("leaked\n", encoding="utf-8")
    (project / "src" / "llm_proxy").mkdir(parents=True)
    (project / "config").mkdir()
    (project / "src" / "llm_proxy" / "main.py").write_text("x = 1\n", encoding="utf-8")
    (project / "config" / "systems.example.yaml").write_text("systems: {}\n", encoding="utf-8")
    for name in (
        "pyproject.toml",
        "Dockerfile",
        "docker-compose.yml",
        ".dockerignore",
        "README.md",
        ".env.example",
    ):
        (project / name).write_text(name, encoding="utf-8")
    link = project / "src" / "llm_proxy" / "leaked.py"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks are not available in this environment")

    names = set(build(project, tmp_path / "out.zip"))

    assert "src/llm_proxy/leaked.py" not in names
    with zipfile.ZipFile(tmp_path / "out.zip") as handle:
        assert b"leaked" not in handle.read("src/llm_proxy/main.py")


def test_inspect_rejects_symlink_zip_entry(tmp_path: Path) -> None:
    archive = tmp_path / "symlink.zip"
    info = zipfile.ZipInfo("src/llm_proxy/evil.py")
    info.create_system = 3
    info.external_attr = 0o120777 << 16
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("pyproject.toml", "")
        handle.writestr(info, b"")

    with pytest.raises(PackageError, match="archive rejected"):
        inspect(archive)
