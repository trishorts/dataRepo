# RESUME

<!-- BEGIN GENERATED -- render_resume.py owns this block; edit state.yaml, not here -->

**dataRepo** &middot; phase **INCEPTION** (1/10) &middot; created 2026-09-19 &middot; rendered 2026-09-19

| | |
|---|---|
| Commits | 2 |
| Sync | not synced -- no remote recorded |
| Locked decisions | 0 |
| Open gaps | 8 |

<!-- END GENERATED -->


## Goal

Build an AI-ready, API-accessible repository for the results of the `aging` pipeline's PRIDE
reanalyses. The results cover search, quant, provenance, design and organelle annotation. Humans can
use it, but AI agents are the main users. The question it serves is how organelle proteomes change
with age.

## Where it stands (2026-09-19 close)

The research is done and the framework is **proposed, not agreed**. The user has not reviewed it yet.

**Documents**
- **`design/FRAMEWORK.md` (v0):** the proposal. Its sections:
  - five lessons from the best projects;
  - a three-layer architecture:
    - per-dataset Parquet as the product;
    - a prebuilt DuckDB catalog;
    - Python, REST, MCP and static-site access over one code path;
  - a 16-table LinkML data model that is a QPX superset with a USI per PSM;
  - 8 MCP tools, including sandboxed SQL;
  - a 6-step roadmap;
  - the decisions it needs;
  - aging count mismatches.
- **`design/INPUT_INVENTORY.md`:** what the aging pipeline writes on `F:\aging_data\`. It lists the files, columns, row counts, provenance keys and volumes. It is the ingest spec's starting point.
- **`lit/research_ai_ready_platforms.md` and `lit/research_proteomics_resources.md`:** the research with URLs. The closest precedent is bigbio's quantms portal (github.com/bigbio/quantms-portal).

**No code yet. No GitHub remote yet** (G8; the user hasn't answered the offer).

## Pick up at

1. Run `/grill-me` on `design/FRAMEWORK.md` section 7. Lock hosting (G2), access (G3), and QPX compatibility plus v0 scope (G6), and record them as decisions in `state.yaml`.
2. **Step 0 (G5):** write `design/QUESTIONS.md`, 50–100 real aging/organelle questions. This is the benchmark. Then write the LinkML schema v0.
3. Tell aging about the count mismatches (G7), through its `design/threads/` or `results/SUSPICIOUS.md`.
