"""Render a generated canonical golden view without changing its source JSONL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from golden_schema import load_golden_jsonl, mapping_summary


def main() -> None:
    """Print adapter results and optionally write a clearly generated JSONL view."""
    parser = argparse.ArgumentParser(description="Inspect golden schema mappings")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("experiments/datasets/golden_v0/data/annotations.jsonl"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = load_golden_jsonl(args.dataset)
    summary = mapping_summary(records)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.output is not None:
        if not args.output.name.endswith(".generated.jsonl"):
            raise ValueError("generated output must end in .generated.jsonl")
        args.output.write_text(
            "".join(json.dumps(record.as_dict(), ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
