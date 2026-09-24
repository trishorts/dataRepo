# Open questions — take these to meetings

The running list of everything dataRepo needs a human answer to. I add a question the moment it
comes up. When you bring back an answer, I record it as a decision in `.project/state.yaml` and move
the row to **Answered** at the bottom.

Each question has a default. If no answer comes back, we build on the default, and any work that
depends on it is marked as such.

## For NCEMS (the operators who will run production — D1)

| ID | Question | Why it matters | Our default until answered |
|---|---|---|---|
| N1 | Do you host **public web services** (a website/API up all the time), or only compute jobs? | D1 hands production to you. If you only run batch jobs, we need a different host. | Assume yes; keep the package portable to any Linux host. |
| N2 | Can your servers run **Docker / Docker Compose**? Or only Apptainer/Singularity, as many HPC centres do? | Decides what we package. | Docker Compose; we would also test that it converts to Apptainer. |
| N3 | Will it get a **public URL with HTTPS** (a domain name, e.g. `aging.ncems.org`)? Who owns the name? | Citations, DOIs and the agents' MCP endpoint all point at this URL, so it must not change. | Placeholder URL; the address is configurable. |
| N4 | How much **disk** can the service have, and where? | We estimate a few GB of tables at ~300 datasets. Raw files are *not* hosted (PRIDE keeps them). | 50 GB, with room to grow. |
| N5 | Who runs **ingest** when aging finishes new datasets: you on a schedule, or we hand you a release? | Decides whether the server needs access to aging's output. | We build versioned releases; you deploy a release. |
| N6 | Who handles **rate limiting / abuse protection** in front of a public API (D2)? | Public and login-free means one runaway agent could swamp it. | Your reverse proxy does it; our code sets per-query limits (30 s, 1,000 rows). |
| N7 | **Backups and uptime.** What do you promise, and who do we call when it's down? | Agents and people will depend on it. | Best effort; every release can be rebuilt from its files. |
| N8 | **DOIs.** Does NCEMS mint them, or do we use Zenodo? | D2 says every release is citable. | Zenodo (free, GitHub-integrated, CC BY friendly). |
| N9 | Who is the **named operator contact** for the handover doc? | aging's D5 handover pattern needs a person. | Blank. |

## For you / the working group

| ID | Question | Our default until answered |
|---|---|---|
| U1 | D5 build order: build the table shape for DIA/TMT/rodent now, and the ingesters only when aging produces that data (**A**)? Or write the ingesters now against public example files (**B**)? | **A** (taken by default in the grill). |
| U2 | Does the working group agree to **public from day one** (D2), including age-effect results before the first paper? You decided this; this is only a check that co-leads (Schilling, Gladyshev, Mohanty) aren't surprised. | Public. |
| U5 | **How generic is "generic"?** You said to keep dataRepo "a bit more generic." My proposal: the **core** schema (dataset, sample, run, psm, peptidoform, quant, protein group, protein, provenance, finding, definition) knows nothing about aging, so any reanalysis project could use it. The aging-specific tables (`age_effect`, `organelle_age_summary`, and the age columns on `sample`) move to a pluggable **study layer** that a consumer project like aging supplies. The name, goal and first deployment stay aging's. | Core generic + aging as the first study layer. |
| U7 | **Namespacing definition IDs.** The schema's example is a bare ID (`DEF-QC-MBR`), but two registers already use overlapping codes (aging's `DEF-CONTAM-PSM` and QuantProject's `DEF-QC-9` both describe a contaminant share). The ingester writes `<owner>:<ID>`, e.g. `aging:DEF-PSM-1PCT`, `QuantProject:DEF-QC-MBR`. Is that the form the registers want to be cited by? | `<owner>:<ID>`. Numbers with no published definition use `PROVISIONAL:<NAME>` and say so in their own text. |
| U6 | D8 makes dataRepo code-only, with aging hosting the data. Does aging also **run the service** (the API/MCP server over its data, deployed by NCEMS as aging's), or does it only publish the data files and someone else runs the server? | aging owns the whole instance: the data, the releases/DOIs, and the deployed service. dataRepo ships a package that aging runs. |
| U8 | **What grain does a stored number have?** aging asked (their 014) whether per-run should be the default, after their dataset-level contaminant share of 7.0% hid a per-file spread of 2.6-18.9% structured by cell line. Our answer, now implemented and told to them in thread 018: **a number is stored at the grain at which it was measured, never coarser and never finer.** Never coarser, so a per-file measurement gets one row per file and the producer's own summaries are carried named as summaries. Never finer, because aging's per-file FDR numbers are a different calculation and must never be summed, so `psms_1pct` stays dataset-scope. And two grains of one quantity are two definitions, not one metric queried differently. Worth locking as a decision rather than leaving as a habit. | The rule above. It needs no schema change, and it only works where the producer's definition states a grain -- which is a small standing request on aging's and QuantProject's registers. |
| U9 | **Where does the modification-name → UNIMOD mapping come from?** The ingester parses mzLib's own resource files (`Mods/*.txt`, `Data/ptmlist.txt`) out of the searching MetaMorpheus install and reads the `DR Unimod;` lines itself. That is not the same as asking mzLib's loader: it never reads `Data/unimod.xml`, and it prefers `Mods.txt` where the loader prefers Unimod. Against QuantProject's `IdWithMotif-to-Unimod.1.0.591.tsv` (3,139 names, generated by running mzLib's own loader) it agrees on all 100 names that have reached `ptm_sites`, returns null for 57 more, has no entry for 2,445, and resolves **two** differently -- `Decarboxylation on D`/`on E`, a defect QuantProject is filing against mzLib. Neither has fired, so nothing shipped is wrong. The question is not which is correct -- the loader is -- but how a generated table from a third repository reaches an operator's machine and is pinned to the mzLib version that did the search. | Consume the pinned TSV as the mapping, fall back to the resource parse only when the instance's mzLib version has no table, and record in the bundle's reader log which was used. Asked of aging and QuantProject as thread 021 §5; tracked as G26. |
| U10 | **Does `catalog_id` promise more than it delivers?** It hashes `datarepo.__version__` alongside `CATALOG_VERSION`, so **0.10.0 -- which adds an MCP server and changes nothing `build` writes -- gives every catalog a new id from the same bundles.** That is the mirror of the decision that deliberately kept `__version__` OUT of the bundle hash (G29). It is not obviously wrong: a catalog is derived and disposable (D10), so the cost is a rebuild rather than a broken citation, and over-hashing can only be wrong in the safe direction. But aging is the one citing catalog ids, so whether a catalog id should move for a change that cannot reach a catalog is theirs to say. Option (b) is to drop `__version__` and make `CATALOG_VERSION` carry the builder, which would make every future `build` change a deliberate bump exactly as `INGESTER_VERSION` does. | **(a)** leave it, and document what the id does and does not promise. Tracked as G34; not changed without a thread. |
| U11 | **Does D24 cover a consumer's own science?** D24 says dataRepo RUNS every engine that works on stored results. aging's abundance age-effect fits (`DEF-AGE-EFFECT`, mzLib `Statistics`) are code on stored results, so D24's letter would make them ours. aging would rather keep them, because the trait and the refusals are their science (aging 050 §2). | aging keeps them. D24 covers **generic engines** that no consumer owns; a consumer's own science stays the consumer's to run. Written into charter v0.2 §2 as a proposed reading. **CLOSED, dissolved by D27** (2026-09-24): aging accepted the operator role (aging 055, their D45) and runs its own fits and the generic engines alike. Charter v0.3 §2. |

### The runner (G64, `design/RUNNER.md`) -- ANSWERED 2026-09-24: all four defaults accepted by the user (D28)

| ID | Question | Our default until answered |
|---|---|---|
| U12 | Where does an engine's output live in an instance's store? | `<store>/_engine/<engine>/<artefact id>/`, beside the bundles and never inside one, the way `_study/` works. A search bundle is never rewritten |
| U13 | What identifies one engine run, for "already done"? | sha256 over the engine, its released version, every input's role and sha256, the definition id, `RUNNER_VERSION` and the schema version. **Not** the bundle id: logs resolves a searched database that fifteen datasets share, so one run serves all of them |
| U14 | Does the runner fetch reference inputs (Ensembl's xref dump, go.obo), or does the operator supply them? | The operator supplies every file; the runner hashes each and checks it against the engine's published manifest. Fetching would make the runner a second, unrecorded source of inputs |
| U15 | Where do logs' rows go? | A new core table `gene_resolutions`, keyed as logs keys it (`search_database_sha256, gene_set_release, accession, gene_id`), with `definition_id`. That is a schema change, taken once, together with go's per-row evidence columns |

## Waiting on aging (thread `design/threads/aging/`)

| ID | Question | Status |
|---|---|---|
| DATAREPO-2 | Record organism / acquisition / quant_method / instrument_vendor, **plus enrichment and labelling** (aging's addition), explicitly in provenance. | Accepted (aging 003). aging will say in the thread when `provenance.json` carries them. Until then the ingester reads them from discover/SDRF and marks them `inferred`. |
| DATAREPO-3 | Which accession list and which PSM count are canonical? | Open on aging's side: SUSPICIOUS.md S20 (datasets; the frozen census, R1, will be canonical) and S21 (PSMs; aging will answer with a definition ID). Until then the ingester stores both PSM numbers with their source. |
| DATAREPO-5 | Confirm or replace the aging study layer (`schema/study/aging.yaml`), incl. the AgeEffect `response` vocabulary. | Posted 004, 2026-09-19. Default: build on the stub. |
| DATAREPO-6 | Route J12 (literature-claim table) and P2 (mass-shift histogram as a bundle file). | Posted 004. Default: P2 as a file; J12 treated as a definition-only trap. |
| DATAREPO-7 | Emit both PSM counts, contaminant share, and run date + instrument as definition-backed metrics. | Posted 004. Default: read what exists; run date from raw header. |
| DATAREPO-8 | Relay R7 / R16 / R7b column names to MetaMorpheus and QuantProject. | Posted 004. Default: schema's proposed names. |
| DATAREPO-9 | D8: accept the data-instance role (bundle location, releases/DOIs, CC BY 4.0, handover doc). | Posted 005, 2026-09-19. Default: accepted; bundles on `F:\aging_data\repo\<release>\`. |
| DATAREPO-10 | = U6: does aging also run the service? | Answered (aging 006): yes. aging populates and hosts the instance, including the service. |
| DATAREPO-11 | Definition IDs for the numbers the ingester now stores with `PROVISIONAL:` placeholders: FlashLFQ peptide and protein intensity, protein spectral count, peptide and protein-group counts at 1% FDR, MS2 count, run minutes, precursor count. | Posted 007, 2026-09-19. Default: keep the `PROVISIONAL:` IDs, whose text says they are not an owner's definition, and swap them when the owners publish. |
| DATAREPO-12 | pyMzLib: populate `pro_forma` on `.psmtsv` records. It is null in 0.1.x, so dataRepo translates MetaMorpheus notation itself, which is peptidoform semantics it should not own. | Posted 007. Default: keep `src/datarepo/proforma.py` and delete it when the field arrives. |
| DATAREPO-13 | pyMzLib: two readers dataRepo had to work around. `AllQuantifiedPeaks.tsv` fails with "Header with name 'MBR Score' was not found" on MetaMorpheus 1.1.11 output, and the SDRF projection joins header and cells with `;`, which SDRF values also contain, so columns cannot be recovered. The `.psmtsv` projection also omits the matched-ion summary columns and the localization score. | Posted 007. Default: dataRepo reads those three files as plain TSV, with the reason recorded in its reader log. |
| DATAREPO-14 | The exact predicate behind `aging DEF-PSM-1PCT v1`. Target plus `QValue <= 0.01` and `QValueNotch <= 0.01` reproduces the peptide (5,541) and protein-group (1,652) totals of PXD036557 exactly, but gives 26,594 PSMs against the reported 26,582. | Posted 007. Default: use that predicate, store both numbers, and raise a `count_mismatch` finding for the 12. |
| DATAREPO-20 | **The study layer is instantiated and four things about its shape are ours, not aging's.** (a) How do `age_effect` rows reach the repository at all? They are the output of a modelling stage that runs long after a search, so they cannot come from `datarepo ingest`. (b) `aging:DEF-AGE-EFFECT v1` §4 writes `feature_type = glycosite`; the core `FeatureType` enum has `glycopeptide` and no `glycosite`. (c) §6's meta key omits `feature_type`, and a dataset-scoped identifier such as a `protein_group_id` cannot be a cross-dataset key at all - so what IS a feature's cross-dataset identity? (d) `stratum` is left an open string because §5 adds `incl_censored`, which §2's table does not list. | Posted as thread 022. (a) **BUILT on the default in datarepo 0.7.0** (2026-09-21): `datarepo study` writes a separately content-addressed study bundle under `<store>/_study/<layer>/`, `build --study` loads it, and no search bundle id moves. Still reversible -- if aging wants another hand-over, only the reader changes. Defaults: (a) a separate study bundle written by a new command and loaded by `build`, so a study layer never forces a re-ingest; (b) use the core `glycopeptide` rather than forking the enum; (c) include `feature_type` and treat `feature_id` at meta grain as a protein accession for protein features; (d) leave it a string. |
| DATAREPO-27 | **Does `aging:DEF-PEPTIDE-1PCT` carry a notch condition?** We applied the PSM notch-resolution clause from their 008 to the peptidoform count as well. PXD032202 settles it against us: the producer reports 21,771 and the un-clause count is 21,771 exactly, while ours said 21,768 -- so we raised a `count_mismatch` against a dataset that matched perfectly. | Implemented on our default (no notch condition) in 0.11.0, thread 033 section 1. aging says so before re-ingesting if the definition means something else. |

## Answered

| ID | Answer | Recorded as |
|---|---|---|
| U12-U15 | The runner's shape as proposed: output beside the bundle under `_engine/`; id from engine, version and input sha256s; operator supplies inputs; one schema change adds `gene_resolutions` with go's columns | D28 (2026-09-24) |
| G2 | Prototype local; NCEMS runs production | D1 |
| G3 | Public from day one, no login | D2 |
| — | CC BY 4.0 data, MIT code | D3 |
| G6a | QPX-compatible superset | D4 |
| G6b | Human + rodent, DDA + DIA, LFQ + TMT | D5 |
| DATAREPO-1 | aging accepts DIA/TMT/rodent; build order stays human DDA LFQ first (aging 003) | D5 (unchanged) |
| DATAREPO-4 | aging owns the benchmark: `aging/design/QUESTIONS.md` v0.3, 168 questions, read from trishorts/aging master, not copied (aging 003) | G5 |
| U3 | Credit line: "NCEMS Aging Proteome Working Group" (user: "citation is fine", 2026-09-19) | CITATION.cff |
| G8 | Public GitHub repo created by the user | state.yaml github.remote |
| — | dataRepo is code only; aging hosts the data (user) | D8 |
