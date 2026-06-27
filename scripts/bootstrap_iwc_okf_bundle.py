#!/usr/bin/env python3
"""Regenerate mechanical OKF files for the IWC sample bundle.

Hand-authored concepts and root claude.md must exist first. This script runs:
  - regenerate_indexes
  - record_conversion_log (Initialization) or skip if log exists
  - append_log_entries (sample review transitions)
  - write_agent_instructions (subdir claude.md only; root claude.md preserved)
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_REL = Path("data") / "iwc" / "okf-bundle"
BUNDLE = REPO_ROOT / BUNDLE_REL

try:
    from okf_toolkit.bundle.agent_instructions import write_agent_instructions
    from okf_toolkit.bundle.index import regenerate_indexes
    from okf_toolkit.bundle.log import (
        LogEntry,
        append_log_entries,
        list_concept_ids,
        read_log,
        record_conversion_log,
    )
    from okf_toolkit.bundle.validate import validate_bundle
except ImportError as exc:
    print(
        "okf_toolkit is not importable; run with .venv-okf/bin/python or set "
        "PYTHONPATH to the OpenKnowledgeFormat src directory.",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc


def _write_agent_instructions() -> None:
    """Regenerate folder claude.md files while preserving the hand-authored root."""
    root_claude = BUNDLE / "claude.md"
    root_text = (
        root_claude.read_text(encoding="utf-8") if root_claude.exists() else None
    )

    write_agent_instructions(BUNDLE, force=True)

    if root_text is not None:
        root_claude.write_text(root_text, encoding="utf-8")

    absolute_bundle = BUNDLE.as_posix()
    portable_bundle = BUNDLE_REL.as_posix()
    for claude_path in BUNDLE.rglob("claude.md"):
        text = claude_path.read_text(encoding="utf-8")
        text = text.replace(absolute_bundle, portable_bundle)
        claude_path.write_text(text, encoding="utf-8")


def main() -> int:
    if not BUNDLE.is_dir():
        print(f"Bundle not found: {BUNDLE}", file=sys.stderr)
        return 1

    regenerate_indexes(BUNDLE)

    if not read_log(BUNDLE).strip():
        concept_paths = sorted(f"{cid}.md" for cid in list_concept_ids(BUNDLE))
        record_conversion_log(
            BUNDLE,
            source_label="findingnemo IWC OKF bootstrap (illustrative samples)",
            converted=concept_paths,
        )

    existing_log = read_log(BUNDLE)
    if "Illustrative batch queued for human review" not in existing_log:
        append_log_entries(
            BUNDLE,
            [
                LogEntry(
                    kind="Update",
                    message="Illustrative batch queued for human review",
                    links=[("pending-batch-042", "/review/pending-batch-042.md")],
                ),
                LogEntry(
                    kind="Update",
                    message="Sample validation report linked to strike case",
                    links=[
                        ("db-match batch7", "/validation/db-match-2026-06-batch7.md"),
                        ("strike case", "/cases/strike-2024-gulf-maine-001.md"),
                    ],
                ),
            ],
        )

    _write_agent_instructions()

    report = validate_bundle(BUNDLE)
    print(report.summary())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
