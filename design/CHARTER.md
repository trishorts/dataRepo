# Responsibilities charter: who defines, runs, stores and consumes what

**Status: DRAFT v0.2, 2026-09-23. Proposed by dataRepo. Not in force until every project in §8 has
signed its own rows.** Each project confirms or corrects its rows on its own thread with dataRepo.
Corrections are merged here, and the version goes up each time.

**v0.2 merges five replies:** aging 050, go 007 and 008, sdrf 008, logs 015, QuantProject 003.
ptmQtl, phred and pyMzLib have not replied, so their rows are unchanged from v0.1. §9 lists every
change. **A party that corrected its row should check the merged wording**: a merge is our reading
of your reply, not your text.

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

There are **three** places an engine's code can execute (v0.2 adds the first, from sdrf 008):

| where | who runs it | how it reaches dataRepo | engines |
|---|---|---|---|
| **before the search**: code whose output the search reads as input | **the fetcher**, today **aging**'s pipeline, calling released mzLib directly or through pyMzLib | the file the search consumes, kept beside the search output | **sdrf** (the SDRF drafter, sdrf D30); **QuantProject** (M7, the SDRF → `ExperimentalDesign.tsv`/`TmtDesign.txt` projection) |
| **inside the search**: code in mzLib/MetaMorpheus that executes while MetaMorpheus searches | **aging**, whose pipeline runs MetaMorpheus | a producer output file, which dataRepo ingests | **phred** (Q_loc, post-search beside localization; *unconfirmed*), **QuantProject** (FlashLFQ/TMT quant), **sdrf** (SDRF emitted by the search) |
| **on stored results**: code that reads search output after it exists, often across datasets | **dataRepo**, calling the engine's released mzLib code through pyMzLib | written directly as rows, with engine version, inputs and definition id recorded | **logs** (gene resolution per searched database, confirmed 015), **go** (GO annotation, confirmed 007), **ptmQtl** (trait effects, pairs; *unconfirmed*) |

**The MetaMorpheus version is the user's decision** (aging D12: 1.1.11 pinned). When an in-search
engine ships in a newer MetaMorpheus, enabling it is a **proposal aging takes to the user**, not
something aging does on release. No engine should read the middle row as "aging upgrades as soon
as it ships" (aging 050 §2).

**A consumer's own science on stored results stays the consumer's to run.** aging's abundance
age-effect fits (`DEF-AGE-EFFECT`, via mzLib `Statistics`) are code on stored results, so D24's
letter would make them dataRepo's. aging keeps them, because the trait and the refusals are its
science (aging 050 §2). D24 is about **generic engines**, which no consumer owns. *Proposed reading;
open as U11 in `OPEN_QUESTIONS.md`.*

**No engine is "run by nobody."** If an engine does not fit any row, it says so on its thread and
we add a row. We do not leave it blank.

## 3 · What each project owns

"Delivers" means to whom. "Needs" means from whom. Each project corrects its own row.

| project | DEFINES | RUNS | delivers | needs |
|---|---|---|---|---|
| **aging** (consumer) ✔ | the benchmark questions (D6); `DEF-AGE-EFFECT` (protein, peptide, isoform abundance) and its meta-analysis; its search-side definitions (`DEF-PSM-1PCT` and the register in `pipeline/docs/provenance.md`, including `DEF-*-1PCT-RUN` and `DEF-COMPOSITION-INSTABILITY`); **what each deposit IS** (the screen: labelled, DIA, enrichment and its kind, acquisition) and each dataset's enrichment annotation; which datasets are queued; the age trait; *proposed by go:* the organelle category map (S17) | an unattended batch runner that drives the pipeline's stages (the Nextflow pipeline wraps the same stages for operators): PRIDE fetch, the before-search engines, MetaMorpheus with in-search engines enabled, its own abundance age-effect fits, `datarepo ingest`/`build` on its instance, and site regeneration after every ingest. PTM responses (`pf_beyond_protein`, `modified_fraction`) are **ptmQtl's**, not aging's | search output + `provenance.json` + manifest to dataRepo; age-effect study bundles; the hosted instance, the public site and DOI releases (D8, D25); **the searched-database archive (S5)** | from dataRepo: correct ingest, a catalog, engine runs on stored data, **a reader that survives large result files (S16)**, **per-run enrichment (aging's DATAREPO-39)**. From sdrf: SDRF tooling. From each engine: a released version to run |
| **dataRepo** (framework) | nothing scientific. It defines only the schema, the ingest/catalog contracts and provenance | `ingest`, `build`, the MCP server, `datarepo site`; **and from D24, every generic on-stored-results engine** (§2), for whichever consumer asks | tables, catalogs and served answers, each carrying `catalog_id`; engine outputs stored with provenance | a released, callable version of each engine (via pyMzLib); a definition id for every number, from its owner (S4); producer files that follow their own contracts |
| **go** (engine) ✔ | GO parsed from UniProt XML (`Protein.GoTerms`, mzLib#1336); the go.obo DAG and ancestor propagation (is_a + part_of); per-member group evidence (`n_members`, `n_with`, `accession_used`, `propagated`, `inherited`); `annotation_status`; the **format** of a term-to-category map and how it is applied; the output contract (annotation file + one category file per map, D28; every non-decoy group with `q_value`, D29) and its header counts; go D1-D29. **Not** the organelle map: that is consumer science (S17) | **dataRepo** (on stored results, D24) | the mzLib API and TSV writer (PR B, stacked on #1347); the verb spec, sent to pyMzLib **through dataRepo** (S9); definition ids for its counts (S4) | stored protein-group files and the annotation XML (S5); a go.obo release pinned per run (S3, S18); the consumer's category map (S17); a pyMzLib verb |
| **logs** (engine) ✔ | gene resolution and orthology logic (`EnsemblGeneResolver`); gene-set files per (species, release); the output contract (`outcome`, key `(search_database_sha256, gene_set_release, accession, gene_id)`) | **dataRepo**, from D24 (confirmed, logs 015). One run per **target** database; none for the contaminant database, and decoys are never passed in | the gene-set tables it publishes, **and a manifest per (species, release) naming both reference files with sha256s**; the resolver in mzLib (#1338); the human reference output `search_db_human_e116.tsv.gz` | the searched databases (S5); **two reference inputs per (species, release): the gene-set table and Ensembl's UniProt xref dump** (without the dump, `ensembl_xref_agrees` is empty and aging's default gene view serves nothing); #1338 merged **and released**; a pyMzLib verb |
| **ptmQtl** (engine) | the hurdle model `ptmQtl:DEF-PTM-TRAIT-HURDLE`, pair statistics `ptmQtl:DEF-PTM-PAIR`, the default `mod_class`; PTM responses (`pf_beyond_protein`, `modified_fraction`, per aging 050) | **dataRepo, from D24**, on the stored catalog (*unconfirmed*) | code in `mzLib/Statistics`; the definitions, under its own namespace (S4) | per-run peptidoform + protein-group intensities (held); **per-site localization confidence (phred)**; **per-sample traits (aging via sdrf)**; per-sample occupancy (QuantProject, S12, gated on S19) |
| **phred** (engine) | Q, the calibrated posterior of misassignment. **For ptmQtl, Q_loc: per-site localization confidence** | **aging**: inside MetaMorpheus, post-search, beside localization, behind its own flag (*unconfirmed*) | a per-site Q_loc in MetaMorpheus output, and its definition | a released MetaMorpheus carrying it; ground truth for calibration; from dataRepo, a column with a stated grain (asked in our 001) |
| **sdrf** (tooling) ✔ | SDRF shape; the age normalizer (`SdrfAge`); provenance grain (SDRF-DR6 = option B, sdrf D31); **the SDRF drafter** (sdrf D30), which builds an SDRF for a deposit with none, every inferred cell marked; the PRIDE-record → column mapping (moved from aging's D27); jointly with QuantProject, the design ↔ SDRF mapping table | the drafter **before the search** (run by the fetcher); SDRF emitted by MetaMorpheus **inside the search** (run by aging); scripts from source, including **`SdrfAge` over its own 151-accession list** | SDRF files; **drafted SDRFs**; **per-cell provenance** (D31); age-bearing accession lists, **each with an age screen** (cells parsed, exact vs range/bound vs refused, the verbatim refusals) | from aging, curated values and which datasets; from dataRepo, storage per characteristic |
| **QuantProject** (definitions + quant) ✔ | the quant definitions (`DEF-PEP-*`, `DEF-PROT-*`, `DEF-MBR-*`, `DEF-QC-*`, `DEF-OCC-*`, `DEF-PROTSET-1PCT`); mzLib's `Quantification` layer; **the SDRF → design projection (M7)**. **Not** a registry of other engines' definitions (S4) | quantification **inside the search**; M7 **just before it** (both run by aging's pipeline) | the quant tables in the producer output; the definition texts; **`ExperimentalDesign.tsv` / `TmtDesign.txt` built from an SDRF** | from sdrf, the design ↔ SDRF mapping table (drafted, under review); from aging, SDRF fixtures and the pins it searches with |
| **pyMzLib** (bridge) | the Python projection of mzLib; its readers and verbs | nothing on data. It ships the library | typed readers (psmtsv etc.); **the verbs dataRepo needs to call each engine** | from each engine, a merged and released mzLib API; from dataRepo, the list of verbs (S9) |

✔ = the party has answered on this row; its corrections are merged. Unmarked rows are still v0.1's
proposal.

## 4 · The chain the core question depends on

"How do organelle proteomes change with age?", and ptmQtl's PTM version of it, need every link
below. **If one link is missing, the answer is empty, not wrong.** That is why a missing link
goes unnoticed.

```
PRIDE deposit
  -> aging: screen (what the deposit IS)                                                   [S15]
  -> aging: fetch, then sdrf drafter + QuantProject M7 (design)                             [before]
  -> aging: search (MetaMorpheus)          + phred Q_loc, QuantProject quant, sdrf SDRF    [in-search]
  -> dataRepo: ingest -> bundles -> catalog
  -> dataRepo: run on stored data          logs resolution, go annotation, ptmQtl fits      [on-stored]
  -> aging: age-effect fits (study layer)
  -> served: MCP / site / release (DOI)
```

| link | status 2026-09-23 | owner of the next move |
|---|---|---|
| sample ages in `samples` | **EMPTY: 0 samples carry an age** (G38). **Deferred by the user's decision, not by oversight:** the queue is not weighted toward age-bearing deposits until the SDRF → design path works (aging G48) | **sdrf** (age screen over the 151), then **aging** (queue preference, `SdrfAge` before any age-axis promise) |
| experimental design | **ABSENT: none of aging's datasets had one**, so every per-sample number is per injection (`DEF-OCC-GROUPING`) | **QuantProject** (M7) with **sdrf** (mapping table); then **aging** runs it (S19) |
| organelle categories | **EMPTY: go has no file yet** (G53). The map moves from go to aging | **go** (PR B, then a release; a pre-release file offered for the reader, GO-A1); **aging** (take the map, go's GO-A4) |
| per-site localization confidence | **EMPTY: `ptm_sites.localization_score` is NULL on every row** | **phred** (Q_loc grain + definition), then aging proposes the MetaMorpheus version to the user (§2) |
| whole proteomes vs enrichments | **labelled** (aging 050: the four enrichment kinds are in the manifest); one mixed deposit (PXD058611) needs per-run enrichment | **dataRepo** (aging's DATAREPO-39) |
| trait effects on PTMs | table shape exists, no producer | ptmQtl (engine in mzLib), then **dataRepo runs it** |
| gene identity | `Protein.gene` unvalidated (G48). logs' human reference output is delivered (015 §2) | logs (#1338 merged and released), pyMzLib (verb), then **dataRepo runs it** |

## 5 · Seams: tasks that sit between two projects

Each seam has one owner. **A seam with no owner is the failure this document exists to
prevent.** If you disagree with an owner, say so. Do not leave the row.

| # | task | owner | agreed by | notes |
|---|---|---|---|---|
| S1 | run every generic on-stored-results engine for a consumer | **dataRepo** | go, logs | D24. A consumer's own science stays the consumer's (§2, U11) |
| S2 | enable in-search engines (version, flag) for a consumer's run | **aging**, subject to the user's MetaMorpheus pin (aging D12) | aging | go: not go, nothing in the search |
| S3 | pin each engine's version for a run and record it in provenance | whoever RUNS it | aging, go | go: the go.obo release and the category-map version are *run inputs*; go's rows carry them |
| S4 | publish a definition id for every number an engine produces | **the engine, in its own namespace** (`<engine>:<ID>`). **No central registry** | QuantProject (declined the registry) | **Changed in v0.2.** go and logs had planned to register with QuantProject; they publish under `go:` and `logs:` instead. logs: not done yet |
| S5 | archive the searched databases (human, contaminant, later rodent) and the stored protein-group files | **aging** | aging, go | aging G49; F: copies with sha until the first DOI release. go depends on it. For a FASTA-searched run, who picks the annotation XML is GO-A2 (§7) |
| S6 | get sample ages into `samples` | **aging** chooses and curates; **sdrf** owns the tooling **and runs the age screen over the list it publishes**; **dataRepo** stores per characteristic | aging, sdrf | deferred by the user until the SDRF → design path works (§4) |
| S7 | classify modifications as artefact vs biological | **ptmQtl** default; **aging** overrides for its own questions | aging (deamidation first) | category-to-class is many-to-many (ptmQtl 003 §5) |
| S8 | per-site localization confidence | **phred** (Q_loc); FLR (set error rate) is the **localization** project's, which is not a party here yet (§7) | | phred D-log: FLR : Q_loc :: FDR : PEP |
| S9 | pyMzLib verbs so dataRepo can call logs, ptmQtl, go (and later phred reprocessing) | **pyMzLib**; **dataRepo** sends the verb list; each engine writes its verb's text and sends it through dataRepo | go, logs | logs: #1338 must merge and ship in an mzLib release first. go: after PR B's signatures settle |
| S10 | draft the mzLib PR for a change a project needs | **the project that needs it** | aging, go, logs | aging: #1341 and pyMzLib's A, B, C. go: #1336 (merged), PR B. logs: #1338 |
| S11 | keep the serving catalog **and the public site** in step with the store | **aging** rebuilds and regenerates after every ingest (aging D42, `instance/publish_catalog_and_site.ps1`); **dataRepo** makes staleness loud (a check that refuses or warns) | aging | the catalog has gone stale three times (G45). The warning check is still owed by dataRepo |
| S12 | per-sample occupancy | **QuantProject** defines (`DEF-OCC-*`); **MetaMorpheus** produces it inside the search, run by aging | QuantProject | **gated on S19**: without a design each denominator is one injection. If ptmQtl means finer than (condition, biological replicate), it says so on its own thread with QuantProject |
| S13 | benchmark questions and judging answers | **aging** (D6) | aging | |
| S14 | cross-dataset key for a feature (ProForma string) | **dataRepo** stores `peptidoform` + `engine_full_sequences` | | mzLib's string and ours differ in three ways today (G52) |
| **S15** | decide what a deposit IS before it is searched (labelled, DIA, enrichment kind, acquisition) | **aging** (the screen and `qc_spectra`) | aging (proposed it) | PXD027548 went through before the screen existed |
| **S16** | carry large result files through ingest | **dataRepo** (windowed reading, 0.17.2); **pyMzLib** if the bridge should refuse an unserialisable payload loudly | aging (proposed it) | reported to pyMzLib as our 008 (DATAREPO-42) |
| **S17** | the organelle category map: content and version | DEFINE **aging** (*proposed by go, pending aging's answer to GO-A4*); STORE **dataRepo**; APPLY go's code. go owns only the file format | go (proposed it) | until aging accepts, this map has **no owner** |
| **S18** | the go.obo release a consumer's run pins | *proposed by go:* **dataRepo**, one release per catalog build, recorded, so no catalog mixes ontologies | go (proposed it) | **open: GO-A3 is ours to answer** (§7) |
| **S19** | the experimental design a search quantifies with (SDRF → `ExperimentalDesign.tsv`/`TmtDesign.txt`) | built by **QuantProject** (M7); run by **aging** before the search; from a mapping owned jointly by **sdrf** and **QuantProject** | QuantProject, sdrf (both proposed it) | the SDRF is projected into the design and both files are kept (sdrf D32). Without it, every per-sample number is per injection, silently |

## 6 · What dataRepo commits to under D24

- Run each on-stored-results engine **only from a released, pinned version**, never a working tree.
  Record the engine, version, inputs (with sha256) and definition id with every row written.
- **Never alter an engine's logic or parameters beyond what the consumer asked.** A consumer choice,
  such as a trait or a `mod_class` override, is recorded as that consumer's.
- Re-run when the engine releases or the inputs move, and say what changed.
- **Refuse, don't guess:** an engine output that fails its own contract (for example go's header
  counts, recounted at `q_value <= 0.01` per go D29) is refused and reported to the engine.
- **Report the first run back to its engine.** logs asked for the row diff of our first pyMzLib run
  against their reference output (LOGS-DR1), including "identical". That is the first test of whether
  the definition travels.

## 7 · Open, and not ours to decide alone

- **The `localization` project** (site-level FLR for O-glycopeptides) is phred's declared boundary
  partner and is not a party to this charter. Should it be? Asked of the user (G56).
- **phred's and ptmQtl's run location** (§2) is still to be confirmed by each.
- **A consumer's own on-stored science** (§2): aging keeps its abundance fits. Proposed reading, U11.
- **Owed by dataRepo to go:** GO-A1 (is a pre-release file acceptable for building the reader, never
  for ingest?), GO-A2 (who picks the annotation XML for a FASTA-searched run; go proposes the
  consumer, recorded by us), GO-A3 (who pins the go.obo release; go proposes dataRepo, per catalog).
- **Owed by aging to go:** GO-A4 (take the organelle map, S17).
- **Owed by dataRepo to sdrf:** SDRF-DR7 (a fifth provenance value, `inferred`) and SDRF-DR8 (gate
  `trusted` on at least one data file existing in the deposit).
- **The live web service** still waits on NCEMS hosting (N1/G9).

## 8 · Sign-off

| project | thread | rows | date |
|---|---|---|---|
| aging | dataRepo 048 → aging 050 | **signed, with four corrections** (merged in v0.2); S15, S16 added | 2026-09-23 |
| go | dataRepo 006 → go 007, 008 | **row replaced by go's text; run location confirmed** (on stored results); S1/S3/S4/S5/S9/S10 confirmed, S2 not go; S17, S18 added | 2026-09-23 |
| logs | dataRepo 014 → logs 015 | **confirmed**, plus the xref input; S9, S10 confirmed; S4 open on logs' side | 2026-09-23 |
| sdrf | dataRepo 007 → sdrf 008 | **accepted, with two corrections** and a third run location; S6 amended | 2026-09-23 |
| QuantProject | dataRepo 002 → QuantProject 003 | **corrected**; run location confirmed + M7; **S4 declined** (merged as per-engine namespaces); S12 accepted; S19 added | 2026-09-23 |
| ptmQtl | dataRepo 004 | awaiting | |
| phred | dataRepo 002 | awaiting | |
| pyMzLib | dataRepo 006 | awaiting (DATAREPO-40) | |
| dataRepo | (author) | all | 2026-09-23 |

**The charter comes into force when all eight have signed their rows and the five who corrected
theirs accept the merged wording.** Acceptance is stated, not inferred from silence.

## 9 · Change log

**v0.2 (2026-09-23)**

- §2: a third run location, **before the search**, run by the fetcher (sdrf 008). go moves to *on
  stored results* (go 007). The MetaMorpheus version is the user's decision (aging 050). A consumer's
  own science stays the consumer's to run (aging 050; U11).
- §3: aging, go, logs, sdrf and QuantProject rows replaced with their corrections. The organelle
  map leaves go's DEFINES column (go 007). logs needs **two** reference inputs (015). QuantProject is
  **not** a registry (003), and ptmQtl's IDs are written `ptmQtl:` accordingly.
- §4: an experimental-design link added; sample ages marked as deferred by decision; enrichments
  marked as labelled.
- §5: **S4 changed** to per-engine namespaces. S6, S11, S12 amended. Five seams added, renumbered
  from the parties' proposals: aging's S15/S16 stay **S15/S16**; go's S15/S16 become **S17/S18**;
  QuantProject's S15 (with sdrf's §3) becomes **S19**.
- §6: go's recount rule (D29) and logs' first-run diff (LOGS-DR1).
- §7: the questions dataRepo now owes (GO-A1..A3, SDRF-DR7, SDRF-DR8).
- §8: five parties signed or corrected.

**v0.1 (2026-09-23, `b74cff3`)**: first draft, sent to all eight parties.
