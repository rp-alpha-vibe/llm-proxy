"""Verify and print control-corpus span fragments (synthetic fixtures only)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tests" / "fixtures" / "control_corpus_v1.yaml"


def main() -> None:
    doc = yaml.safe_load(CORPUS.read_text(encoding="utf-8"))
    for case in doc["cases"]:
        text = case["text"]
        for exp in case.get("expected") or []:
            frag = text[exp["start"] : exp["end"]]
            print(f"{case['id']}|{exp['type']}|{exp['start']}:{exp['end']}|{frag!r}")


if __name__ == "__main__":
    main()
