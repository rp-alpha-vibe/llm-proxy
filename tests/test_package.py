import zipfile
from pathlib import Path

import pytest
from scripts.package import PackageError, build, inspect

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
    inspect(archive)


def test_inspect_rejects_a_blacklisted_member(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("pyproject.toml", "")
        handle.writestr("docs/REQUIREMENTS.md", "secret")

    with pytest.raises(PackageError, match="archive rejected"):
        inspect(archive)
