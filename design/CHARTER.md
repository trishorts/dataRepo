# Responsibilities charter: who defines, runs, stores and consumes what

**Status: DRAFT v0.1, 2026-09-23. Proposed by dataRepo. Not in force until every project in §8 has
signed its own rows.** Each project confirms or corrects its rows on its own thread with dataRepo.
Corrections are merged here, and the version goes up each time.

**Why this exists.** The user, 2026-09-23: *"I don't want critical tasks to slip through the cracks
between projects with each one thinking it is the others responsibility."* The engines (go, logs,
ptmQtl, phred) are generic by design. They must work for any consumer, and aging is only the
first. Being generic has a cost: **no engine knows which consumer it is running for, so none of
them runs itself.** Until today dataRepo's rule was "store and serve, never compute", so dataRepo
did not run them either. The result was a gap in the middle that nobody owned.

---

## 1 · The rule (user decision, 2026-09-23; dataRepo D24)

**dataRepo never DEFINES. It does RUN.**

Every task has four verbs, and each verb has exactly one owner:

| verb | meaning | owner |
|---|---|---|
| **DEFINE** | the logic, the model, the definition text, the version | the **engine** that owns the science |
| **RUN** | execute a released version of that logic on a consumer's data, with the version pinned and recorded | **where the code executes** (§2) |
| **STORE / SERVE** | keep the output with provenance and a definition id, and serve it to people and agents | **dataRepo** |
| **CONSUME** | say what is needed, own the consumer's own science, and ask the questions | the **consumer** (today: aging) |

A project that owns DEFINE never has to know which consumer it is serving. dataRepo does, because
every stored row carries its dataset, bundle and consumer.

## 2 · Where code runs decides who runs it

There are two places an engine's code can execute. Each is run by a different project:

| where | who runs it | how it reaches dataRepo | engines (proposed; each engine confirms its own) |
|---|---|---|---|
| **inside the search**: code in mzLib/MetaMorpheus that executes while MetaMorpheus searches | **aging**, whose pipeline runs MetaMorpheus. aging picks the version and turns on the flag. | a producer output file, which dataRepo ingests | **phred** (Q_loc, in the post-search step beside localization), **QuantProject** (FlashLFQ/TMT quant), **sdrf** (SDRF emitted by the search), **go**? |
| **on stored results**: code that reads search output after it exists, often across datasets | **dataRepo**, calling the engine's released mzLib code through pyMzLib | written directly as rows, with engine version, inputs and definition id recorded | **logs** (gene resolution per searched database), **ptmQtl** (trait effects, pairs), **go**? |

**No engine is "run by nobody."** If an engine does not fit either row, it says so on its thread and
we add a row. We do not leave it blank.

## 3 · What each project owns

"Delivers" means to whom. "Needs" means from whom. Each project corrects its own row.

| project | DEFINES | RUNS | delivers | needs |
|---|---|---|---|---|
| **aging** (consumer) | the benchmark questions (D6); `DEF-AGE-EFFECT` and its meta-analysis; which datasets are queued; the age trait | the Nextflow pipeline: PRIDE fetch, MetaMorpheus search with in-search engines enabled, its own age-effect fits, `datarepo ingest`/`build` on its instance | search output + `provenance.json` + manifest to dataRepo; age-effect study bundles; the hosted instance and DOI releases (D8) | from dataRepo: correct ingest, a catalog, engine runs on stored data. From sdrf: SDRF tooling. From each engine: a released version to run |
| **dataRepo** (framework) | nothing scientific. It defines only the schema, the ingest/catalog contracts and provenance | `ingest`, `build`, the MCP server; **and from D24, every on-stored-results engine** (§2), for whichever consumer asks | tables, catalogs and served answers, each carrying `catalog_id`; engine outputs stored with provenance | a released, callable version of each engine (via pyMzLib); a definition id for every number; producer files that follow their own contracts |
| **go** (engine) | the organelle map (anchors), term to category, `organelle_map_version`; go D1-D26 | **to confirm:** inside the search or on stored results | term categories + protein to term rows (`organelle_term_categories`, `protein_localizations`) | the searched UniProt XML; a GO release pin; from dataRepo, a place to land (built in schema 0.0.8) |
| **logs** (engine) | gene resolution and orthology logic (`EnsemblGeneResolver`), gene-set files per (species, release) | **dataRepo, from D24.** This reverses our 013 answer; see the thread | the gene-set tables it publishes; the resolver in mzLib (#1338) | the searched databases (aging archives them, 045 §4); a pyMzLib verb |
| **ptmQtl** (engine) | the hurdle model `DEF-PTM-TRAIT-HURDLE`, pair statistics `DEF-PTM-PAIR`, the default `mod_class` | **dataRepo, from D24**, on the stored catalog | code in `mzLib/Statistics`; the definitions, registered with QuantProject | per-run peptidoform + protein-group intensities (held); **per-site localization confidence (phred)**; **per-sample traits (aging via sdrf)**; per-sample occupancy (QuantProject) |
| **phred** (engine) | Q, the calibrated posterior of misassignment. **For ptmQtl, Q_loc: per-site localization confidence** | **aging**: inside MetaMorpheus, post-search, beside localization, behind its own flag | a per-site Q_loc in MetaMorpheus output, and its definition | a released MetaMorpheus carrying it; ground truth for calibration; from dataRepo, a column with a stated grain (asked in our 001) |
| **sdrf** (tooling) | SDRF shape, the age normalizer (`SdrfAge`), provenance grain (SDRF-DR6 = option B) | inside the search (SDRF emitted by MetaMorpheus), plus scripts like the 151-accession list | SDRF files; age-bearing accession lists | from aging, curated values and which datasets; from dataRepo, storage per characteristic |
| **QuantProject** (definitions + quant) | `DEF-OCC-*`, `DEF-QC-*`, the quant definitions; the registry every engine registers its definitions with | inside the search (FlashLFQ/TMT) | quant tables in the producer output; definition texts | engine definitions registered with it; from ptmQtl, the per-sample occupancy request |
| **pyMzLib** (bridge) | the Python projection of mzLib; its readers and verbs | nothing on data. It ships the library | typed readers (psmtsv etc.); **the verbs dataRepo needs to call each engine** | from each engine, a merged mzLib API; from dataRepo, the list of verbs (§5) |

## 4 · The chain the core question depends on

"How do organelle proteomes change with age?", and ptmQtl's PTM version of it, need every link
below. **If one link is missing, the answer is empty, not wrong.** That is why a missing link
goes unnoticed.

```
PRIDE deposit
  -> aging: search (MetaMorpheus)          + phred Q_loc, QuantProject quant, sdrf SDRF   [in-search]
  -> dataRepo: ingest -> bundles -> catalog
  -> dataRepo: run on stored data          logs resolution, ptmQtl fits, go mapping?      [on-stored]
  -> aging: age-effect fits (study layer)
  -> served: MCP / site / release (DOI)
```

| link | status 2026-09-23 | owner of the next move |
|---|---|---|
| sample ages in `samples` | **EMPTY: 0 samples carry an age** (G38) | **aging** (queue the 151 age-bearing accessions from sdrf 005); sdrf (tooling) |
| organelle categories | **EMPTY: go has no file yet** (G53) | **go** (first real file, DATAREPO-35) |
| per-site localization confidence | **EMPTY: `ptm_sites.localization_score` is NULL on every row** | **phred** (Q_loc grain + definition) and aging (enable it in the search) |
| whole proteomes vs enrichments | labelled from 0.16.0; 7 of the first 10 are enrichments | aging (manifest correction) |
| trait effects on PTMs | table shape exists, no producer | ptmQtl (engine in mzLib) then **dataRepo runs it** |
| gene identity | `Protein.gene` unvalidated (G48) | logs (resolver release) then **dataRepo runs it** |

## 5 · Seams: tasks that sit between two projects

Each seam has one proposed owner. **A seam with no owner is the failure this document exists to
prevent.** If you disagree with an owner, say so. Do not leave the row.

| # | task | proposed owner | why that one |
|---|---|---|---|
| S1 | run every on-stored-results engine for a consumer | **dataRepo** | D24 |
| S2 | enable in-search engines (version, flag) for a consumer's run | **aging** | they run MetaMorpheus |
| S3 | pin each engine's version for a run and record it in provenance | whoever RUNS it (S1/S2) | provenance is written where execution happens |
| S4 | publish a definition id for every number an engine produces | the **engine**, registered with **QuantProject** | owner defines; one registry |
| S5 | archive the searched databases (human, contaminant, later rodent) | **aging** | agreed, their 045 §4 |
| S6 | get sample ages into `samples` | **aging** chooses and curates; **sdrf** tooling; **dataRepo** stores per characteristic | nobody else can choose datasets |
| S7 | classify modifications as artefact vs biological | **ptmQtl** default; **aging** overrides for its own questions | it is a model input. Note: category-to-class is many-to-many (ptmQtl 003 §5) |
| S8 | per-site localization confidence | **phred** (Q_loc); FLR (set error rate) is the **localization** project's, which is not a party here yet (§7) | phred D-log: FLR : Q_loc :: FDR : PEP |
| S9 | pyMzLib verbs so dataRepo can call logs, ptmQtl, go (and later phred reprocessing) | **pyMzLib**, with dataRepo writing the verb list | the bridge owns projection; the caller states the need |
| S10 | draft the mzLib PR for a change a project needs | **the project that needs it** | pyMzLib 004 house rule |
| S11 | keep the serving catalog in step with the store | **aging** rebuilds (they host); **dataRepo** makes staleness loud (a check that refuses or warns) | it has gone stale three times (G45) |
| S12 | per-sample occupancy | **QuantProject** defines; producer TBD | ptmQtl 002 §1 asked QuantProject |
| S13 | benchmark questions and judging answers | **aging** (D6) | consumer owns its questions |
| S14 | cross-dataset key for a feature (ProForma string) | **dataRepo** stores `peptidoform` + `engine_full_sequences`; mzLib and ours differ today (G52) | the key is a stored thing |

## 6 · What dataRepo commits to under D24

- Run each on-stored-results engine **only from a released, pinned version**, never a working tree.
  Record the engine, version, inputs (with sha256) and definition id with every row written.
- **Never alter an engine's logic or parameters beyond what the consumer asked.** A consumer choice,
  such as a trait or a `mod_class` override, is recorded as that consumer's.
- Re-run when the engine releases or the inputs move, and say what changed.
- **Refuse, don't guess:** an engine output that fails its own contract (for example go's header
  counts) is refused and reported to the engine.

## 7 · Open, and not ours to decide

- **The `localization` project** (site-level FLR for O-glycopeptides) is phred's declared boundary
  partner and is not a party to this charter. Should it be? Asked of the user.
- **go's and phred's run location** (§2) is to be confirmed by each.
- **The live web service** still waits on NCEMS hosting (N1/G9).

## 8 · Sign-off

| project | thread | rows confirmed | date |
|---|---|---|---|
| aging | dataRepo 048 | | |
| go | dataRepo 006 | | |
| logs | dataRepo 014 | | |
| ptmQtl | dataRepo 004 | | |
| phred | dataRepo 002 | | |
| sdrf | dataRepo 007 | | |
| QuantProject | dataRepo 002 | | |
| pyMzLib | dataRepo 006 | | |
| dataRepo | (author) | all | 2026-09-23 |
