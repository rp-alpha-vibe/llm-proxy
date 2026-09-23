import sys

from llm_proxy.quality.runner import evaluate, render_report


def main() -> int:
    report = evaluate()
    print(render_report(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
