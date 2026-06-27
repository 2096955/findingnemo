---
type: Validation Report
title: Sample DB match report — batch 7 (illustrative)
description: Synthetic validation report comparing extracted cases to sample DB export.
tags: [iwc, illustrative, validation]
timestamp: '2026-06-27T12:00:00Z'
---

Illustrative validation output from `IWC_Validator`-style CSV matching. Not based on Alice's real database.

# Schema

| Metric | Value |
|--------|-------|
| database | sample_database.csv (illustrative) |
| candidates | 1 |
| matched | 1 |
| unmatched | 0 |
| match_threshold | 0.55 |

# Matches

- [Sample humpback strike — Gulf of Maine](/cases/strike-2024-gulf-maine-001.md): matched
  SAMPLE-IWC-2024-001 (score 0.92, illustrative)

# Gaps

- None in this illustrative batch.

# Suggested corrections

- Human reviewer must confirm species and date before any database import.

# Citations

- Sample DB: `data/iwc/sample_database.csv` (findingnemo repo, illustrative)
