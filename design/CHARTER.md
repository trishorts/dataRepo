# Responsibilities charter: who defines, runs, stores and consumes what

**Status: DRAFT v0.4, 2026-09-25. Proposed by dataRepo. Not in force until every project in §8 has
signed its own rows.** Each project confirms or corrects its rows on its own thread with dataRepo.
Corrections are merged here, and the version goes up each time.

**v0.3 changes who RUNS.** The user decided on 2026-09-23 that **dataRepo ships software and operates
nothing** (dataRepo D27). Every run on stored data belongs to whoever **operates an instance**,
today **aging**, which accepted the role for engine runs too (aging 055, their D45). dataRepo ships
the runner that operator uses. v0.3 also merges pyMzLib 009, go 010, logs 016/017, sdrf 011 and
aging 055. ptmQtl and phred have not replied. §9 lists every change. **A party that corrected its
row should check the merged wording**: a merge is our reading of your reply, not your text.

**v0.4 merges three replies to v0.3**: go 012 (four cells, in go's words), QuantProject 006 (three
corrections: M7 runs before the search until sdrf's locator exists; the locator does not call M7;
per-run occupancy needs no design) and ptmQtl 006 (row accepted, with three conditions). It also
brings statuses up to date: **the runner is built** (datarepo 0.20.0) and **per-run occupancy is
stored** (datarepo 0.21.0).

**Why this exists.** The user, 2026-09-23: *"I don't want critical tasks to slip through the cracks
between projects with each one thinking it is the others responsibility."* The engines (go, logs,
ptmQtl, phred) are generic by design. They must work for any consumer, and aging is only the
first. Being generic has a cost: **no engine knows which consumer it is running for, so none of
them runs itself.** Before this charter nobody ran them, and the gap in the middle had no owner.

---

## 1 · The rule (user decisions, 2026-09-23; dataRepo D24, revised by D27)

**dataRepo never DEFINES, and it operates nothing. It SHIPS the software an operator runs.**

Every task has four verbs, and each verb has exactly one owner:

| verb | meaning | owner |
|---|---|---|
| **DEFINE** | the logic, the model, the definition text, the version | the **engine** that owns the science |
| **RUN** | execute a released version of that logic on a consumer's data, with the version pinned and recorded | **where the code executes** (§2); on stored data, the **instance operator** |
| **STORE / SERVE** | keep the output with provenance and a definition id, and serve it to people and agents | **dataRepo's software** (schema, ingest, catalog, MCP server, site), run on an instance by its operator |
| **CONSUME** | say what is needed, own the consumer's own science, and ask the questions | the **consumer** (today: aging) |

**The instance operator** is whoever runs a dataRepo instance: ingest, build, the catalog, the site,
and every engine run on that instance's stored data. **Today it is aging**, which already ran
ingest, build and the site (dataRepo D8, D25; aging D42) and took engine runs on in 055. A second
consumer would operate its own instance with the same software. The dataRepo project makes scratch
runs on real data only to **test** its software, and never serves or publishes them.

A project that owns DEFINE never has to know which consumer it is serving. The operator does, because
every stored row carries its dataset, bundle and consumer.

## 2 · Where code runs decides who runs it

There are three places an engine's code can execute:

| where | who runs it | how it reaches the store | engines |
|---|---|---|---|
| **before the search**: code whose output the search reads as input | **the fetcher**, today **aging**'s pipeline, calling released mzLib directly or through pyMzLib | the file the search consumes, kept beside the search output | **sdrf** (the SDRF drafter, sdrf D30); **QuantProject M7, until sdrf's locator exists** (the standalone `--sdrfDesign <sdrf> -s <spectra>`, mzLib #1363 + MetaMorpheus #2852, drafts), writing the `ExperimentalDesign.tsv` the search reads |
| **inside the search**: code in mzLib/MetaMorpheus that executes while MetaMorpheus searches | **aging**, whose pipeline runs MetaMorpheus | a producer output file, which `datarepo ingest` reads | **phred** (Q_loc, post-search beside localization; *unconfirmed*), **QuantProject** (FlashLFQ/TMT quant; and **M7**, called before quantification, **once sdrf's locator exists**; see S19), **sdrf** (the locator that hands M7 its SDRF; SDRF emitted by the search) |
| **on stored results**: code that reads search output after it exists, often across datasets | **the instance operator, today aging**, through **datarepo's runner** calling the engine's released mzLib code through pyMzLib | a new artefact beside the bundle, never a write into it, with engine version, inputs (sha256) and definition id recorded | **logs** (gene resolution per searched database), **go** (GO annotation), **ptmQtl** (trait effects, pairs; accepted, ptmQtl 006); and the consumer's own science, such as aging's abundance age-effect fits |

**The MetaMorpheus version is the user's decision** (aging D12: 1.1.11 pinned). When an in-search
engine ships in a newer MetaMorpheus, enabling it is a **proposal aging takes to the user**, not
something aging does on release (aging 050 §2).

**v0.3 moves M7 into the search, and v0.4 says when.** QuantProject and sdrf settled (QuantProject
011 to sdrf, sdrf 011 §3) that M7 is called **inside MetaMorpheus, before quantification**. That call
site runs through sdrf's locator, which is **not written yet** (sdrf 012 §1). **Until it exists, M7
runs before the search**, as a standalone command the fetcher (aging) runs, and the search reads the
file it writes (QuantProject 006 §1a). The SDRF drafter stays before the search, with the fetcher,
because it needs PRIDE.

**A consumer's own science on stored results** runs the same way as a generic engine, by the same
operator. U11 is closed: it asked whether dataRepo should run aging's fits, and under D27 dataRepo
runs nothing.

**No engine is "run by nobody."** If an engine does not fit any row, it says so on its thread and
we add a row. We do not leave it blank.

### The runner (dataRepo ships it; built in datarepo 0.20.0)

`datarepo run <engine> <PXD...> --store <store> --input ROLE=PATH ...` runs a released engine on stored
data. It was built to aging's wish list (055 §1) and review (063), and it:

- runs only a **released engine** (pyMzLib from PyPI), and refuses an editable or dirty-clone
  datarepo; every artefact records the datarepo install's commit or wheel sha256 (aging 063);
- keys each artefact on the engine, its release, every input's role and sha256, and the definition
  id, so a repeat is refused as "already done" (dataRepo D28). It is **not** keyed on a bundle: one
  logs run per searched database serves every dataset that searched it;
- writes a **new artefact beside the bundles**, never into one (`<store>/_engine/<engine>/<id>/`);
- refuses an input that does not hash to its record, and engine output that fails its own contract.

The first engine is logs' gene resolution. go and ptmQtl join it when their code is released. The
runner's record is the record the operator keeps.

## 3 · What each project owns

"Delivers" means to whom. "Needs" means from whom. Each project corrects its own row.

| project | DEFINES | RUNS | delivers | needs |
|---|---|---|---|---|
| **aging** (consumer, instance operator) ✔ | the benchmark questions (D6); `DEF-AGE-EFFECT` (protein, peptide, isoform abundance) and its meta-analysis; its search-side definitions (`DEF-PSM-1PCT` and the register in `pipeline/docs/provenance.md`, including `DEF-*-1PCT-RUN` and `DEF-COMPOSITION-INSTABILITY`); **what each deposit IS** (the screen: labelled, DIA, enrichment and its kind, acquisition) and each dataset's enrichment annotation; which datasets are queued; the age trait; **the organelle category map, its content and version (S17, aging D46)** | an unattended batch runner that drives the pipeline's stages (the Nextflow pipeline wraps the same stages for operators): PRIDE fetch, the before-search engines, MetaMorpheus with in-search engines enabled; **and as instance operator (aging D45)**: `datarepo ingest`/`build`, site regeneration after every ingest, **every engine run on stored data through datarepo's runner**, and its own abundance age-effect fits. PTM responses (`pf_beyond_protein`, `modified_fraction`) are **ptmQtl's**, not aging's | search output + `provenance.json` + manifest; age-effect study bundles; the hosted instance, the public site and DOI releases (D8, D25); **the searched-database archive (S5)**; engine outputs on its instance, each with its runner record | from dataRepo: correct ingest, a catalog, **the runner**, **a reader that survives large result files (S16)**, **per-run enrichment (aging's DATAREPO-39)**. From sdrf: SDRF tooling. From each engine: a released version to run |
| **dataRepo** (framework) | nothing scientific. It defines only the schema, the ingest/catalog contracts, provenance, and **how an engine run is recorded** | **nothing on any instance** (D27). Scratch runs on real data to test its own software, never served | the software: `ingest`, `build`, the MCP server, `datarepo site`, **the runner** (§2); each release committed and pushed before it is announced | a released, callable version of each engine (via pyMzLib); a definition id for every number, from its owner (S4); producer files that follow their own contracts |
| **go** (engine) ✔ | GO parsed from UniProt XML (`Protein.GoTerms`, mzLib#1336); the go.obo DAG and ancestor propagation (is_a + part_of); per-member group evidence (`n_members`, `n_with`, `accession_used`, `propagated`, `inherited`); `annotation_status`; the **format** of a term-to-category map and how it is applied; the output contract (annotation file + one category file per map, D28; every non-decoy group with `q_value`, D29), its header counts, and the `mzlib_version` / `mzlib_release` header lines; go D1-D32 (D31: the `mzlib_version` / `mzlib_release` lines; D32: entrapment is its own class, neither decoy nor target, with a D18 amendment to follow). **Not** the organelle map: that is aging's (S17) | **the instance operator, today aging**, via datarepo's runner (on stored results) | the mzLib API and TSV writer (**PR B**, mzLib#1353, **ready for review** since 2026-09-25) and the Readers adapter (**PR C**, draft mzLib#1366, stacked on PR B; stays a draft until D32 lands) and FileReader recognising `AllProteinGroups.tsv` / `<file>_ProteinGroups.tsv` (mzLib#1365, ready for review); the verb spec, sent to pyMzLib **through dataRepo** (S9); definition ids for its counts (S4); a pre-release file for building the reader (delivered, go 010) | stored protein-group files and the annotation XML (S5); **one go.obo release per catalog**, chosen by the operator (S18); aging's category map (S17); a pyMzLib verb |
| **logs** (engine) ✔ | gene resolution and orthology logic (`EnsemblGeneResolver`); gene-set files per (species, release); the output contract (`outcome`, key `(search_database_sha256, gene_set_release, accession, gene_id)`); **`logs:DEF-GENE-RESOLUTION v1`** (a run is v1 only with the xref given); the proteoform-to-entry accession rule, if the join is entry-level (LOGS-D2) | **the instance operator, today aging**, via datarepo's runner. One run per **target** database; none for the contaminant database, and decoys are never passed in | the gene-set tables it publishes, **and a manifest per (species, release) naming both reference files with sha256s** (delivered: `results/resolver_inputs_e116.{json,md}`); the resolver in mzLib (#1338, **released in 1.0.592**); the human reference output `search_db_human_e116.tsv.gz` | the searched databases (S5); **two reference inputs per (species, release): the gene-set table and Ensembl's UniProt xref dump**; the first run's row diff against its reference (LOGS-D1) |
| **ptmQtl** (engine) ✔ | the hurdle model `ptmQtl:DEF-PTM-TRAIT-HURDLE`, pair statistics `ptmQtl:DEF-PTM-PAIR`, the default `mod_class` as a versioned rule per (UNIMOD accession, residue) (ptmQtl D11); PTM responses (`pf_beyond_protein`, `modified_fraction`, per aging 050) | **the instance operator, today aging**, via datarepo's runner, on the stored catalog. Accepted on three conditions (ptmQtl 006 §3): the runner calls the **released** mzLib entry point with plain tables and holds no statistics of its own; every row carries the engine version and a `ptmQtl:` `definition_id`; the runner **never pre-filters on `mod_class`** | code in mzLib (#1341 and the engine, #1369, drafts); the definitions, under its own namespace (S4) | per-run peptidoform + protein-group intensities (held); **per-run site occupancy** (stored since datarepo 0.21.0, S12); **per-site localization confidence (phred)**; **per-sample traits (aging via sdrf)** |
| **phred** (engine) | Q, the calibrated posterior of misassignment. **For ptmQtl, Q_loc: per-site localization confidence** | **aging**: inside MetaMorpheus, post-search, beside localization, behind its own flag (*unconfirmed*) | a per-site Q_loc in MetaMorpheus output, and its definition | a released MetaMorpheus carrying it; ground truth for calibration; from dataRepo, a column with a stated grain (asked in our 001) |
| **sdrf** (tooling) ✔ | SDRF shape; the age normalizer (`SdrfAge`); provenance grain (SDRF-DR6 = option B, sdrf D31) and the five `source` values; **the SDRF drafter** (sdrf D30), which builds an SDRF for a deposit with none, every inferred cell marked; **the locator** that finds, improves and restricts an SDRF and hands it to M7; the PRIDE-record → column mapping (moved from aging's D27); jointly with QuantProject, the design ↔ SDRF mapping table | the drafter **before the search** (run by the fetcher); the locator and SDRF emitted by MetaMorpheus **inside the search** (run by aging); scripts from source, including **`SdrfAge` over its own 151-accession list** | SDRF files; **drafted SDRFs**, with per-cell `source` (D31); age-bearing accession lists, **each with an age screen** (cells parsed, exact vs range/bound vs refused, the verbatim refusals); a drafted SDRF for dataRepo to build `source` against (owed, sdrf 011) | from aging, curated values and which datasets; from dataRepo, a `source` column per characteristic (**to be built**, G62) and a data-file gate at ingest (SDRF-DR8) |
| **QuantProject** (definitions + quant) ✔ | the quant definitions (`DEF-PEP-*`, `DEF-PROT-*`, `DEF-MBR-*`, `DEF-QC-*`, `DEF-OCC-*`, `DEF-PROTSET-1PCT`); mzLib's `Quantification` layer; **the SDRF → design projection (M7)**. **Not** a registry of other engines' definitions (S4) | quantification **inside the search**; M7 **inside the search, before quantification** once sdrf's locator exists, and **before the search** (standalone `--sdrfDesign`) until then. Both are run by aging | the quant tables in the producer output; the definition texts; **`ExperimentalDesign.tsv` built from an SDRF** (the LFQ half, out as drafts: mzLib #1363, MetaMorpheus #2852); **`TmtDesign.txt`, not built yet** (QuantProject's next piece of work) | from sdrf, the design ↔ SDRF mapping table (drafted, under review) and the locator; from aging, SDRF fixtures and the pins it searches with |
| **pyMzLib** (bridge) ✔ | the Python projection of mzLib; its readers and verbs; the Python names and prose of each verb. The verb's wire contract is **bridge**'s (`bridge/design/verbs/<module>.<verb>.yaml`) | nothing on data. It ships the library | typed readers (psmtsv etc.); **the verbs the operator needs to call each engine** (S9); loud refusal of an unserialisable payload, routed to bridge (PYMZ-B4, S16) | from each engine, a merged and released mzLib API; from dataRepo, **each verb request as a draft bridge verb spec** (S9) |

✔ = the party has answered on this row; its corrections are merged. Unmarked rows are still v0.1's
proposal, with v0.3's RUN change applied.

## 4 · The chain the core question depends on

"How do organelle proteomes change with age?", and ptmQtl's PTM version of it, need every link
below. **If one link is missing, the answer is empty, not wrong.** That is why a missing link
goes unnoticed.

```
PRIDE deposit
  -> aging: screen (what the deposit IS)                                                   [S15]
  -> aging: fetch, then the sdrf drafter                                                    [before]
  -> aging: search (MetaMorpheus)   + sdrf locator -> QuantProject M7, quant, phred Q_loc    [in-search]
  -> operator (aging): datarepo ingest -> bundles -> catalog
  -> operator (aging): datarepo runner   logs resolution, go annotation, ptmQtl fits,        [on-stored]
                                         aging's age-effect fits
  -> served: MCP / site / release (DOI)
```

| link | status 2026-09-24 | owner of the next move |
|---|---|---|
| sample ages in `samples` | **EMPTY: 0 samples carry an age** (G38). **Deferred by the user's decision, not by oversight:** the queue is not weighted toward age-bearing deposits until the SDRF → design path works (aging G48) | **sdrf** (age screen over the 151, now on released `SdrfAge`), then **aging** (queue preference, `SdrfAge` before any age-axis promise) |
| experimental design | **ABSENT: none of aging's datasets had one**, so every per-sample number is per injection (`DEF-OCC-GROUPING`) | **QuantProject** (M7) with **sdrf** (mapping table, locator); then **aging** runs MetaMorpheus with it (S19) |
| organelle categories | **EMPTY in the store.** The reader is built against go's pre-release file (datarepo 0.18.1; go's per-row evidence columns in schema 0.0.10); aging owns the map (D46) | **go** (PR B merged and released); then **the operator** runs go through the runner; **aging** (the map, `aging-organelle-map` v1) |
| per-site localization confidence | **EMPTY: `ptm_sites.localization_score` is NULL on every row** | **phred** (Q_loc grain + definition), then aging proposes the MetaMorpheus version to the user (§2) |
| whole proteomes vs enrichments | **labelled** (aging 050: the four enrichment kinds are in the manifest); one mixed deposit (PXD058611) needs per-run enrichment | **dataRepo** (aging's DATAREPO-39; shape asked as DATAREPO-44) |
| per-run PTM site occupancy | **stored** from MetaMorpheus's own cells since datarepo 0.21.0 (QuantProject `DEF-OCC-CELL v3.2`); every denominator is one injection | **the operator** re-ingests on 0.21.0 |
| trait effects on PTMs | table shapes exist (`ptm_pairs` at site grain since schema 0.0.11); ptmQtl's first bundle is test data, not served (dataRepo D30) | ptmQtl (#1341, #1369, then a release), pyMzLib (verb), then **the operator** runs it |
| gene identity | `Protein.gene` unvalidated (G48). The resolver is released, **the runner is built** (datarepo 0.20.0, `gene_resolutions`), LOGS-D1 reproduced on all three species, LOGS-D2 answered (entry-level) | **the operator** (aging) runs it after re-ingesting on 0.21.0 |

## 5 · Seams: tasks that sit between two projects

Each seam has one owner. **A seam with no owner is the failure this document exists to
prevent.** If you disagree with an owner, say so. Do not leave the row.

| # | task | owner | agreed by | notes |
|---|---|---|---|---|
| S1 | run every on-stored-results engine, and the consumer's own on-stored science, for a consumer | **the instance operator, today aging**, via datarepo's runner | aging (D45), go, logs | **Changed in v0.3** (D27). dataRepo ships the runner and runs nothing. U11 closed |
| S2 | enable in-search engines (version, flag) for a consumer's run | **aging**, subject to the user's MetaMorpheus pin (aging D12) | aging | go: not go, nothing in the search |
| S3 | pin each engine's version for a run and record it in provenance | whoever RUNS it; on stored data the runner records it | aging, go | go: the go.obo release and the category-map version are *run inputs*. `go_release` is a column on every annotation row and a header line; the category map's name, version and sha256 are in the category table's `#!category_map` header line, not on annotation rows |
| S4 | publish a definition id for every number an engine produces | **the engine, in its own namespace** (`<engine>:<ID>`). **No central registry** | QuantProject (declined the registry), logs | logs: **done**, `logs:DEF-GENE-RESOLUTION v1` (`logs/design/DEFINITIONS.md`) |
| S5 | archive the searched databases (human, contaminant, later rodent) and the stored protein-group files | **aging** | aging, go | aging G49; F: copies with sha until the first DOI release. go depends on it. For a FASTA-searched run the consumer names the annotation XML, and a run with none named is refused (GO-A2) |
| S6 | get sample ages into `samples` | **aging** chooses and curates; **sdrf** owns the tooling **and runs the age screen over the list it publishes**; **dataRepo**'s schema stores them per characteristic | aging, sdrf | deferred by the user until the SDRF → design path works (§4) |
| S7 | classify modifications as artefact vs biological | **ptmQtl** default; **aging** overrides for its own questions | aging (deamidation first) | category-to-class is many-to-many (ptmQtl 003 §5) |
| S8 | per-site localization confidence | **phred** (Q_loc); FLR (set error rate) is the **localization** project's, which is not a party here yet (§7) | | phred D-log: FLR : Q_loc :: FDR : PEP |
| S9 | pyMzLib verbs so the runner can call logs, ptmQtl, go (and later phred reprocessing) | **pyMzLib**; **dataRepo** sends each request **as a draft bridge verb spec**; each engine writes its verb's text and sends it through dataRepo | pyMzLib, go, logs | **Today:** gene resolution and protein databases (accession, organism, taxon, GO terms) **ship in pyMzLib 0.2.0**; go's PR B writer waits on PR B's merge and release; trait effects wait on #1341; modification lookup is queued with bridge (PYMZ-B3) |
| S10 | draft the mzLib PR for a change a project needs | **the project that needs it** | aging, go, logs | aging: #1341 and pyMzLib's A, B, C. go: #1336 (merged), PR B (mzLib#1353, ready for review since 2026-09-25). logs: #1338 (merged, released) |
| S11 | keep the serving catalog **and the public site** in step with the store | **aging** rebuilds and regenerates after every ingest (aging D42, `instance/publish_catalog_and_site.ps1`); **dataRepo**'s software makes staleness loud (a check that refuses or warns) | aging | the catalog has gone stale three times (G45). The warning check is still owed by dataRepo |
| S12 | PTM site occupancy | **QuantProject** defines (`DEF-OCC-*`); **MetaMorpheus** produces it inside the search, run by aging; **dataRepo**'s ingest stores it | QuantProject, ptmQtl | **Per-run occupancy is available now** in every design-less search, and stored since datarepo 0.21.0 (dataRepo D29). **Per-sample** occupancy is gated on S19, or summed from per-run pairs (QuantProject 006 §1c). ptmQtl wants per run first (ptmQtl 002) |
| S13 | benchmark questions and judging answers | **aging** (D6) | aging | |
| S14 | cross-dataset key for a feature (ProForma string) | **dataRepo** stores `peptidoform` + `engine_full_sequences` | | mzLib's string and ours differ in three ways (G52); mzLib's now ships (1.0.592), so the corpus diff comes before any switch |
| **S15** | decide what a deposit IS before it is searched (labelled, DIA, enrichment kind, acquisition) | **aging** (the screen and `qc_spectra`) | aging (proposed it) | PXD027548 went through before the screen existed |
| **S16** | carry large result files through ingest | **dataRepo** (windowed reading, 0.17.2); **pyMzLib** routes a loud refusal of an unserialisable payload to bridge as one error kind (PYMZ-B4) | aging (proposed it), pyMzLib | reported as our 008 (DATAREPO-42); we re-run the probe on 0.2.0 with `out=` |
| **S17** | the organelle category map: content and version | DEFINE **aging** (aging D46); STORE dataRepo's schema; APPLY go's code. go owns only the file format | go (proposed it), aging | **Changed in v0.3:** aging accepted go's GO-A4 |
| **S18** | the go.obo release a consumer's run pins | **the instance operator** chooses it, **one release per catalog**, recorded on every row; `datarepo build` refuses a catalog that mixes releases | go (proposed it) | **Changed in v0.3:** GO-A3 fully answered. Under D27 the chooser is the operator, not dataRepo |
| **S19** | the experimental design a search quantifies with (SDRF → `ExperimentalDesign.tsv`/`TmtDesign.txt`) | built by **QuantProject** (M7); run by MetaMorpheus before quantification: **sdrf's locator hands the restricted SDRF to QuantProject's M7** (the locator returns a document and never calls M7 itself, sdrf 012 §1); **before the search**, by the fetcher, until the locator exists; **aging** runs both; from a mapping owned jointly by **sdrf** and **QuantProject** | QuantProject, sdrf | **Changed in v0.3 and v0.4** (sdrf 011 §3; QuantProject 006 §1a-b). Both files are kept (sdrf D32). **An SDRF and a design file that disagree stop the run** (exit 5, every difference listed; QP-S16). **M7 is called for each task that quantifies, on the names that task searched**, so a calibrated or averaged run gets its design too (QP-S20). Without a design, every per-sample number is per injection, silently |

## 6 · What dataRepo's software guarantees, and what the operator does

**The runner enforces** (built in datarepo 0.20.0, so no operator has to remember them):

- It runs an on-stored-results engine **only from a released, pinned version**, never a working tree.
  It records the engine, version, inputs (with sha256) and definition id with every artefact.
- It never writes into a bundle, and it refuses a repeat run with identical inputs.
- **Refuse, don't guess:** an engine output that fails its own contract is refused and reported.
  Examples: go's header counts, recounted at `q_value <= 0.01` (go D29); a go file whose
  `#!mzlib_release` is `none` (go 010); a logs run with no xref, which is not v1 (logs 017).

**The operator does:**

- **Never alter an engine's logic or parameters beyond what the consumer asked.** A consumer choice,
  such as a trait or a `mod_class` override, is recorded as that consumer's.
- Re-run when the engine releases or the inputs move, and say what changed.
- Choose the go.obo release for each catalog (S18).

**dataRepo does, as the software's author:**

- **Reports the first run of each engine back to it.** logs asked for the row diff of the first run
  against their reference output (LOGS-D1), including "identical". dataRepo makes that run as a
  scratch test of its runner, because it is a test of whether the definition travels, not a
  served result.

## 7 · Open, and not ours to decide alone

- **The `localization` project** (site-level FLR for O-glycopeptides) is phred's declared boundary
  partner and is not a party to this charter. Should it be? Asked of the user (G56).
- **phred's run location** (§2) is still to be confirmed by phred. ptmQtl confirmed its own (006).
- **Owed by sdrf to dataRepo:** a drafted SDRF to build `source` against. How a drafter's default
  cell is labelled is settled: `default`, the sixth `source` value (sdrf 013, our 014), once aging
  also agrees (their SDRF-A14).
- **go's D32 (entrapment):** go will amend D18 in one thread; the go row and D18 stay as they are
  until then (go 012).
- **The live web service** still waits on NCEMS hosting (N1/G9).

## 8 · Sign-off

| project | thread | rows | date |
|---|---|---|---|
| aging | dataRepo 048 → aging 050, 053 → 055 | **signed**; four corrections (v0.2); **operator role accepted** (D45), S17 edit (v0.3) | 2026-09-23 |
| go | dataRepo 006 → go 007, 008, 010, 012 | **row replaced by go's text**; 010's corrections merged in v0.3; **RUN cell, S17, S18 confirmed and four cells fixed in 012** (merged in v0.4) | 2026-09-25 |
| logs | dataRepo 014 → logs 015, 016, 017 | **confirmed**, plus the xref input; S4 done (017) | 2026-09-24 |
| sdrf | dataRepo 007 → sdrf 008, 011, 013 | **accepted, with two corrections** (v0.2); row confirmed and S19 reworded (011); **v0.3 row and S19 confirmed as merged** (013) | 2026-09-24 |
| QuantProject | dataRepo 002 → QuantProject 003, 006 | **corrected**; run location confirmed + M7; **S4 declined** (merged as per-engine namespaces); S12 accepted; S19 added; **v0.3 confirmed with three corrections** (006, merged in v0.4) | 2026-09-25 |
| pyMzLib | dataRepo 006 → pyMzLib 009 | **signed**: row and S9 accepted, S9's verb list corrected, the verb-spec convention and S16 added | 2026-09-24 |
| ptmQtl | dataRepo 004 → ptmQtl 006 | **accepted, with three conditions** (006 §3, merged in v0.4) | 2026-09-24 |
| phred | dataRepo 002 | awaiting | |
| dataRepo | (author) | all | 2026-09-25 |

**The charter comes into force when all eight have signed their rows and every party whose row was
merged accepts the merged wording.** Acceptance is stated, not inferred from silence. **v0.3 changes
the RUN column of go, logs and ptmQtl and seams S1, S17, S18 and S19**, so those parties are asked
to confirm again. go, sdrf, QuantProject and ptmQtl have; **logs (DATAREPO-46) and phred have not**.
**v0.4 merges go's, QuantProject's and ptmQtl's wording**, and each is asked to check it.

## 9 · Change log

**v0.4 (2026-09-25)**

- §2: M7 runs **before the search** until sdrf's locator exists, as a standalone command the fetcher
  runs (QuantProject 006 §1a). The runner is described as built (datarepo 0.20.0), with aging's two
  operator notes (063).
- §3: **go**: D1-D32 in OWNS; PR B ready for review; PR C draft #1366 and #1365 in DELIVERS (go 012).
  **QuantProject**: the RUN cell in their words; `TmtDesign.txt` not built yet (006 §1a). **ptmQtl**:
  accepted with three conditions (006 §3); `mod_class` rule per (UNIMOD, residue) (their D11); needs
  per-run occupancy, now stored.
- §4: statuses at 2026-09-25: the runner is built, occupancy is stored, the go reader is built, and
  LOGS-D2 is answered.
- §5: **S3** (go 012: where `go_release` and the map's identity live), **S10** (PR B ready for review),
  **S12** (per-run occupancy needs no design and is stored; QuantProject 006 §1c), **S19** (the locator
  returns a document and never calls M7; disagreement stops the run; M7 per quantifying task;
  QuantProject 006 §1b).
- §7: LOGS-D2 closed (entry-level, our logs 018); sdrf's default-cell label settled (`default`, sdrf
  013); go's D32 noted.
- §8: go, sdrf, QuantProject and ptmQtl updated.

**v0.3 (2026-09-24)**

- §1, §2: **D27.** dataRepo ships and operates nothing; the instance operator, today aging (aging
  D45), runs everything on stored data through datarepo's runner. The runner is described and is
  not built yet. M7 moves inside the search (sdrf 011, QuantProject 011 to sdrf). U11 closed as
  dissolved.
- §3: RUN column for go, logs, ptmQtl moves to the operator. aging's row takes the operator role and
  the organelle map (D46). dataRepo's row runs nothing. go: PR B sits on master, PR C stacks on
  #1347 (go 010); header lines named. logs: #1338 released, manifest delivered, definition id (017).
  sdrf: the locator. pyMzLib: signed (009), verb specs go to bridge.
- §4: statuses at 2026-09-24; the chain shows the operator.
- §5: **S1, S17, S18, S19 changed**; S4, S9, S16 updated from logs 017, pyMzLib 009; S10, S14 updated
  for the mzLib 1.0.592 release.
- §6: split into what the runner enforces, what the operator does, and what dataRepo does.
- §7: GO-A1..A4, SDRF-DR7/DR8 answered and removed; LOGS-D2 and sdrf's owed file added.
- §8: pyMzLib signed; go, logs, sdrf, aging updated.

**v0.2 (2026-09-23, `6a4318e`)**

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
- §6: go's recount rule (D29) and logs' first-run diff (LOGS-DR1, now LOGS-D1).
- §7: the questions dataRepo then owed (GO-A1..A3, SDRF-DR7, SDRF-DR8).
- §8: five parties signed or corrected.

**v0.1 (2026-09-23, `b74cff3`)**: first draft, sent to all eight parties.
