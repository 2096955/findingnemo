# Agent Instructions — IWC Strike Knowledge Bundle

> **IWC agent operating system.** All agents working on whale-vessel strike data for the
> International Whaling Commission must follow this bundle before reading concepts.

## Read order (mandatory)

1. **`log.md`** — recent pipeline runs and review state changes
2. **`claude.md`** — this file (rules and gates)
3. **`index.md`** — bundle table of contents; pick concepts by title/description only
4. **Concept frontmatter** — `type`, `title`, `description`, `tags` before loading body
5. **Concept body** — only when frontmatter matches your task
6. **Cross-links** — follow `/cases/…`, `/literature/…` links; do not filesystem-search

## Hard rules

- **Never auto-import** strike records into the IWC production database. Human validation
  is mandatory before any DB import.
- Treat concepts tagged **`pending_human_review`** as unapproved. Do not treat them as
  confirmed cases.
- All committed sample concepts in this bundle are **synthetic/illustrative** unless
  explicitly marked otherwise. Do not present them as real IWC records.
- Cite external sources under `# Citations`. Do not invent incidents or URLs.

## Forbidden

- Do **not** glob, ripgrep, or keyword-scan all `.md` files to find information.
- Do **not** open every concept file to "see what's inside" — use index entries first.
- Do **not** add, rename, or remove concepts without regenerating indices and appending
  to `log.md`.

## After changes

```bash
okf index data/iwc/okf-bundle
okf log append data/iwc/okf-bundle --kind Update --message "Describe change" --link /cases/example.md
okf validate data/iwc/okf-bundle
okf evals run data/iwc/okf-bundle
```

## Bundle layout

```
index.md          ← START HERE (root listing)
├── claude.md     ← you are here (IWC agent OS)
├── log.md        ← audit trail
├── cases/        ← Strike Case concepts
├── literature/   ← Literature Source concepts
├── validation/   ← Validation Report concepts
├── alerts/       ← Alert Batch concepts
└── review/       ← Review Note concepts (human checklist)
```
