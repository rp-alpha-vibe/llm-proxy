import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = (
    [sys.executable, "-m", "ruff", "format", "--check", "src", "tests", "scripts"],
    [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"],
    [sys.executable, "-m", "mypy", "src", "tests", "scripts"],
    [sys.executable, "-m", "pytest"],
)


def main() -> None:
    for command in COMMANDS:
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
