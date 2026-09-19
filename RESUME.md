# RESUME

<!-- BEGIN GENERATED -- render_resume.py owns this block; edit state.yaml, not here -->

**dataRepo** &middot; phase **INCEPTION** (1/10) &middot; created 2026-09-19 &middot; rendered 2026-09-19

| | |
|---|---|
| Commits | 4 |
| Sync | not synced -- no remote recorded |
| Locked decisions | 7 |
| Open gaps | 7 |

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
- **`design/threads/aging/`:** 001 (scope correction, provenance axes, count mismatches) and 002 (a 78-question benchmark seed handed to aging). Both are pushed on aging's side up to 001; 002 is committed but not pushed.
- **`lit/`:** the research on platforms and proteomics resources.

**No code yet.** The GitHub remote is not created (G8): auto mode blocked `gh repo create --public`, so the user runs it themselves.

## Pick up at

1. **Read aging's replies** in `E:\CodeReview\aging\design\threads\dataRepo\` (003 and later). They answer our 001 (DATAREPO-1 scope, -2 provenance axes, -3 canonical counts) and 002 (DATAREPO-4, the benchmark seed). The user went to aging to get this feedback. Record each answer in `state.yaml` and move the matching rows in `design/OPEN_QUESTIONS.md` to Answered. aging's copy of 002 was committed but not pushed at close; aging's session may push it.
2. **Draft the generic core LinkML schema v0** (`schema/datarepo.yaml`) on U5's default: the core knows nothing about aging, and `age_effect`, `organelle_age_summary` and the sample age columns form aging's study layer. Keep the quant table long (run, channel, feature, value) for D5.
3. **When the user brings NCEMS answers** (N1–N9), record them as decisions.
4. **G8:** the user runs `! gh repo create trishorts/dataRepo --public --source . --remote origin --push` (auto mode won't). Then record `github.remote`.
