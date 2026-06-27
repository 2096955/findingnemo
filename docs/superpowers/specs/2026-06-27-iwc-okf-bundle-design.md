# IWC OKF Bundle — Design Spec

**Date:** 2026-06-27
**Status:** Approved (design)
**Scope:** Track A (findingnemo) — stand up the IWC knowledge bundle as OKF v0.1
**Related:** [`docs/superpowers/plans/2026-06-24-iwc-whale-agent-platform.md`](../plans/2026-06-24-iwc-whale-agent-platform.md) §3 (Knowledge structure layer)

## 1. Goal

Make findingnemo "adhere to OKF" in the sense the master plan defines: create a
git-tracked, **OKF v0.1-conformant** IWC knowledge bundle at
`data/iwc/okf-bundle/` that passes `okf validate` (zero errors) and
`okf evals run` (automated evals pass), with the layout and concept vocabulary
specified in the plan.

This is the **Task 2 "OKF bootstrap"** from the master plan — standing up the
bundle and its scaffolding, with illustrative sample concepts.

## 2. Non-goals (explicit)

- **Not** converting findingnemo's Python source or general docs into OKF. Code
  is not "knowledge"; OKF applies to IWC knowledge artefacts only.
- **Not** rewiring the writer tools (`iwc_note_writer.py`, `literature_extractor.py`,
  `iwc_validator.py`, `review_exporter.py`, `graph_ingest.py`) to *write* OKF
  concepts. That is Task 2b / Tracks B–C in NeuroSAN and is out of scope here.
- **Not** importing any of Alice's real strike data. All committed sample
  concepts are synthetic and clearly marked as illustrative.

## 3. Bundle structure

Mirrors master plan §3 ("IWC bundle layout (target)"). Bundle root:
`data/iwc/okf-bundle/`.

```
data/iwc/okf-bundle/
├── index.md            # frontmatter: okf_version: "0.1"; root TOC (generated)
├── claude.md           # Agent OS: read order, never auto-import, human-review gate
├── log.md              # dated entries; Initialization + sample transitions
├── cases/
│   ├── index.md        # generated
│   └── strike-2024-gulf-maine-001.md      # type: Strike Case
├── literature/
│   ├── index.md        # generated
│   └── paper-smith-2022.md                # type: Literature Source
├── validation/
│   ├── index.md        # generated
│   └── db-match-2026-06-batch7.md         # type: Validation Report
├── alerts/
│   ├── index.md        # generated
│   └── news-sweep-2026-06.md              # type: Alert Batch
└── review/
    ├── index.md        # generated
    └── pending-batch-042.md               # type: Review Note
```

### 3.1 Concept vocabulary (frontmatter `type` values)

Per master plan §3 "OKF concept types". One sample concept per type:

| `type`              | File                                     | Conventional sections          |
|---------------------|------------------------------------------|--------------------------------|
| `Strike Case`       | `cases/strike-2024-gulf-maine-001.md`    | `# Schema`, `# Citations`      |
| `Literature Source` | `literature/paper-smith-2022.md`         | summary, `# Schema`, `# Citations` |
| `Validation Report` | `validation/db-match-2026-06-batch7.md`  | matches/gaps, links to `cases/` |
| `Alert Batch`       | `alerts/news-sweep-2026-06.md`           | queries, candidate events, links |
| `Review Note`       | `review/pending-batch-042.md`            | human checklist; `tags: [pending_human_review]` |

### 3.2 Cross-links (per SPEC §5, bundle-relative `/…` form)

- `validation/db-match-2026-06-batch7.md` → `/cases/strike-2024-gulf-maine-001.md`
- `review/pending-batch-042.md` → the pending case under `/cases/…`
- `alerts/news-sweep-2026-06.md` → candidate `/cases/…`
- `cases/strike-2024-gulf-maine-001.md` → its `/literature/paper-smith-2022.md` source

## 4. Generation approach (script-first)

OKF principle #1 is "script-first — bulk work in code; agent for judgment only."

1. **Hand-author** the 5 concept `.md` files (domain judgment; synthetic data).
2. **Generate mechanical files via `okf_toolkit`** so they are conformant by
   construction:
   - `okf_toolkit.bundle.index.regenerate_indexes(bundle)` → all `index.md`
     (root index keeps `okf_version: "0.1"` frontmatter).
   - `okf log init` (CLI) or `okf_toolkit.bundle.log.append_log_entries(...)`
     → `log.md` with an Initialization entry + sample review-transition entries.
   - `okf agent-instructions` (CLI) generates per-folder `claude.md`; the
     **root `claude.md`** is hand-authored to encode the IWC agent OS:
     read order `log.md → claude.md → index.md → concept frontmatter → body →
     cross-links`, and the hard rule **never auto-import; human review gate**.

## 5. Config wiring

- Add `IWC_OKF_BUNDLE` to `.env.example`, default `data/iwc/okf-bundle/`.
- Add a single constant in `src/whale_common/constants.py` (matching the file's
  existing pattern) resolving the bundle path from env with that default, so code
  has one canonical reference. No behavior change to existing tools.

## 6. Gitignore — track samples, ignore real data

Add `data/iwc/.gitignore`:
- **Track** `okf-bundle/` (the sample bundle is committed).
- **Ignore** real-data locations: `raw/`, `private/`, and `*.real.md`.

Rationale: human validation is mandatory before any DB import (memory:
`human-validation-before-iwc-import`); Alice's data must never enter git.

## 7. Validation gate

Toolkit has no heavy deps (only `pyyaml`). Install into a local venv:

```bash
python3 -m venv .venv-okf && source .venv-okf/bin/activate
pip install -e /Users/anthonylui/OpenKnowledgeFormat
okf validate data/iwc/okf-bundle      # MUST be PASS / 0 errors
okf evals run data/iwc/okf-bundle     # automated evals MUST pass; agent evals reported
```

Acceptance: `okf validate` reports **0 errors**; `okf evals run` reports all
**automated** evals passing. Agent-prompt evals are surfaced for manual review,
not auto-graded. Raw output is reported back, not just a pass/fail claim.

## 8. Conformance test

Add `tests/unit/test_iwc_okf_bundle.py`:
- Import `validate_bundle` from `okf_toolkit.bundle.validate`.
- Assert the committed bundle validates with **zero errors** (warnings allowed).
- Skip cleanly (pytest skip) if `okf_toolkit` is not importable, so the suite
  doesn't hard-fail in environments without the toolkit installed.

This prevents the committed bundle from silently rotting out of conformance.

## 9. Acceptance criteria

1. `data/iwc/okf-bundle/` exists with the §3 layout and 5 cross-linked concepts.
2. `okf validate data/iwc/okf-bundle` → PASS, 0 errors.
3. `okf evals run data/iwc/okf-bundle` → automated evals pass.
4. `IWC_OKF_BUNDLE` present in `.env.example` and resolvable via a constant in
   `src/whale_common/constants.py`.
5. `data/iwc/.gitignore` tracks the sample bundle, ignores real-data paths.
6. `tests/unit/test_iwc_okf_bundle.py` passes.
7. All sample data is synthetic/illustrative — no real strike records committed.
