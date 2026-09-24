# The runner: how an instance operator runs a released engine on stored data (G64)

**Status: PROPOSAL, 2026-09-24. Not built.** D27 decided that dataRepo ships a runner and the instance
operator (today aging) runs it; charter v0.3 §2 lists what it must do. This page proposes how. Every
open choice has a default in `OPEN_QUESTIONS.md` (U12-U15), and aging, as the operator, is asked to
check it before a line is written.

## What it is for

Engines that work on **stored results** (charter §2: logs' gene resolution, go's annotation, ptmQtl's
trait fits, a consumer's own model fits) never learn which consumer they serve, so none runs itself.
The runner is the one command that runs a **released** engine on an instance's stored data and keeps
its output with a record a stranger can reproduce.

## The four rules it inherits (charter §2, aging 055 §1)

1. **Released inputs only.** An engine version is a released package (pyMzLib from PyPI, which pins a
   released mzLib), never a working tree, exactly as `ingest` refuses an unannounced ingester.
2. **Idempotent.** The same (engine, engine version, inputs) is refused as "already done", with the
   existing artefact's id.
3. **Beside the bundle, never inside it.** A search bundle is immutable and cited by id. An engine
   output is a separate, separately content-addressed **artefact**; writing one never reads, rewrites
   or re-identifies a search bundle. This is the study layer's rule (U5, `study.py`) applied again.
4. **The record is the output's provenance.** Engine, version, every input with its sha256, the
   definition id, and the runner's own version.

## Proposed shape

### Command

```
datarepo run <engine> --store <store> [--bundle <accession>=<bundle id> ...] [--input <role>=<path> ...]
```

- `<engine>` is one of a fixed list the runner knows (`logs.resolve_genes` first). Each is a small
  adapter in `datarepo/engines/<engine>.py` that names the pyMzLib verb, the inputs it needs by role,
  which stored table(s) it writes, and the engine's own acceptance checks (below).
- **Inputs by role, never by guess.** For logs: `gene_set`, `xref` (both from logs' manifest) and the
  searched database, which the runner takes **from the bundle's own record** (`search_database`,
  `search_database_sha256`) and refuses if the file on disk does not hash to it.

### Artefact

```
<store>/_engine/<engine>/<artefact id>/
    run.json              the record (below)
    <table>.parquet       one file per schema table the engine fills
```

- The leading underscore keeps it out of the dataset namespace, as `_study/` does.
- **Artefact id** = sha256 over: engine name, engine release (pyMzLib version and the mzLib version it
  reports), each input's role and sha256, the definition id, `RUNNER_VERSION`, and the schema version.
  Not the bundle id: logs resolves a **searched database**, which fifteen human datasets share, so the
  one artefact serves all of them, and re-ingesting a dataset does not re-run an unchanged resolution.
- `run.json`: the fields hashed above, plus `written_utc`, the runner's `__version__`, the bundles it
  was asked on behalf of, the verb's own summary (outcome counts, caveats), and the engine's
  acceptance result.

### Acceptance, per engine (refuse, don't guess)

| engine | checked before anything is written |
|---|---|
| logs `resolve_genes` | `xref` given (else not `logs:DEF-GENE-RESOLUTION v1`, logs 017); every row's `gene_set_sha256` and `ensembl_xref_sha256` equal logs' manifest `row_values`; zero caveats or they are recorded |
| go (after its release) | `sources/go.py`: released writer, header recount, coverage (0.18.1) |
| ptmQtl (after #1341) | defined with ptmQtl when its verb exists |

### Where the rows go

This is the one piece that needs a **schema change**, so it is taken once, with the first engine:

- **logs** has no table. Proposed: `gene_resolutions`, keyed as logs keys it: `(search_database_sha256,
  gene_set_release, accession, gene_id)`, with logs' columns as they write them and
  `definition_id`. The join to `proteins` is entry-level (LOGS-D2, our 018), and on today's corpus it
  needs no mapping (logs 019).
- **go** fills the existing `protein_localizations` / `organelle_term_categories` /
  `annotation_sources`, plus go's per-row evidence columns (n_members, n_with, propagated, inherited,
  annotation_status, q_value, protein_group), which 0.0.9 lacks.

### Catalog

`datarepo build` loads every artefact under `_engine/` whose inputs match the catalog: for logs,
whose `search_database_sha256` is the database of a bundle in the catalog. `catalog_id` then hashes
the artefact ids too, so a catalog cites exactly which resolution it serves. A catalog that would
need an artefact that does not exist builds without it and says so in `catalog_checks`, the way an
empty study layer does today.

## What it will not do

- Fetch anything. The operator supplies every input file; the runner hashes and checks it.
- Pick an engine version. It records the one installed and refuses an unreleased one.
- Run on a search bundle's behalf without the operator asking.
