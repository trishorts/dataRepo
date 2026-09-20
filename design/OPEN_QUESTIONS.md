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

## Answered

| ID | Answer | Recorded as |
|---|---|---|
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
