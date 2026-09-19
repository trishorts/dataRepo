# RESUME

<!-- BEGIN GENERATED -- render_resume.py owns this block; edit state.yaml, not here -->

**dataRepo** &middot; phase **INCEPTION** (1/10) &middot; created 2026-09-19 &middot; rendered 2026-09-19

| | |
|---|---|
| Commits | 7 |
| Sync | not synced -- no remote recorded |
| Locked decisions | 7 |
| Open gaps | 8 |

<!-- END GENERATED -->


## Goal

Build an AI-ready, API-accessible repository for the results of the `aging` pipeline's PRIDE
reanalyses. The results cover search, quant, provenance, design and organelle annotation. Humans can
use it, but AI agents are the main users. The question it serves is how organelle proteomes change
with age.

## Where it stands (2026-09-19, second session)

The framework's section 7 decisions are **locked** (grill-me). Everything else in `design/FRAMEWORK.md` v0 is still a proposal.

**Locked:** D1 hosting (prototype local; NCEMS runs production) · D2 public from day one, no login · D3 CC BY 4.0 data, MIT code · D4 QPX-compatible superset · D5 human and rodent, DDA and DIA, LFQ and TMT (the table shape now, the ingesters when aging produces the data) · D6 aging owns the benchmark questions; dataRepo stays generic · D7 every open question goes in `design/OPEN_QUESTIONS.md`.

**Documents**
- **`design/OPEN_QUESTIONS.md`:** the list you take to NCEMS and working-group meetings. Each question has a default we build on until you bring an answer back.
- **`design/FRAMEWORK.md` (v0):** the architecture proposal (Parquet + DuckDB + REST/MCP over one code path, a LinkML schema, 8 MCP tools, roadmap).
- **`design/INPUT_INVENTORY.md`:** what aging writes on `F:\aging_data\`. The ingest spec starts here.
- **`design/threads/aging/`:** 001 (scope, provenance axes, count mismatches), 002 (the benchmark seed) and aging's reply 003 (QUESTIONS.md v0.3 is ready; tables routed to us: R1–R3, R7, R7b, R8, R9, R16).
- **`design/SCHEMA_V0.md`:** what schema v0 contains and what's still open. The schema is in `schema/datarepo.yaml` (generic core) and `schema/study/aging.yaml` (a stub for aging to own).
- **`lit/`:** the research on platforms and proteomics resources.

**No code yet** (the schema is YAML only). The GitHub remote is not created (G8): auto mode blocked `gh repo create --public`, so the user runs it themselves.

## Pick up at

1. **Map the benchmark onto schema v0.** Put every question in `aging/design/QUESTIONS.md` v0.3 (read it from aging; don't copy it), top 10 first, into `design/SCHEMA_COVERAGE.md`. Record the table and columns each needs, or mark it as a gap. Fix the schema where a question fails.
2. **Post thread 004 to aging.** Ask them to confirm the study-layer columns (`schema/study/aging.yaml`) and to give the R7 and R16 producer column names. Include the coverage result.
3. **When the user brings NCEMS answers** (N1–N9), record them as decisions.
4. **G8:** the user runs `! gh repo create trishorts/dataRepo --public --source . --remote origin --push` (auto mode won't). Then record `github.remote`.
