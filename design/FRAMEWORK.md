# dataRepo — proposed framework (v0, 2026-09-19)

> **Status, 2026-09-21.** Steps 1 and 2 are built and their contracts locked as **D9** and **D10**.
> Steps 3–6 were grilled on 2026-09-21 and their choices locked as **D12–D18**; where this document
> and a decision disagree, **the decision wins** and the difference is called out below. What is
> still genuinely undecided: the REST API and the Docker Compose package (D16 defers both pending
> N1/G9 and evidence of a human who wants REST).

**What it's for:** hold every result the `aging` pipeline produces, across dozens to hundreds of PRIDE
reanalyses, in one place. People should be able to browse it and cite it. AI agents are the
**primary** users and should be able to query it well.

This rests on three research notes:
- `lit/research_ai_ready_platforms.md`: CELLxGENE, Open Targets, EBI, MCP practice, AI-ready standards.
- `lit/research_proteomics_resources.md`: QPX/quantms, PRIDE, USI, ProteomicsDB, organelle and aging atlases.
- `design/INPUT_INVENTORY.md`: what the pipeline actually writes.

---

## 1. The five lessons from the best projects

1. **Consistent metadata matters more than the database engine.**
   - CELLxGENE Census can answer one query across 900+ datasets because every dataset was curated to a single *required* metadata schema of ontology terms.
   - For us the scarce asset is the **age axis**. Only 160 of 1,236 curated SDRFs carry a real age (aging G12).
   - The harmonized sample table (age, sex, tissue, cell type, disease, all as ontology terms) is therefore the most valuable thing we build. The storage technology is not.
2. **Files are the product. APIs are views on top of them.**
   - Open Targets ships Parquet files on FTP, Google Cloud and BigQuery, and puts GraphQL on top.
   - The quantms portal treats per-dataset Parquet as the truth. It builds one DuckDB file from them offline and serves that.
3. **Agents do best with a few well-designed tools, not one tool per endpoint.**
   - Open Targets went from 45 thin tools to 5 schema-aware ones, and benchmarked the change with 140 questions.
   - quantms planned raw SQL but shipped task-level tools such as `search_protein` and `protein_profile`.
   - The pattern that keeps recurring:
     - *resolve an entity*
     - *show part of the schema*
     - *run a few curated task queries*
     - *run bounded read-only SQL*
     - *filter on the server side*
4. **Releases are versioned, immutable and citable.** Census keeps an LTS release every 6 months for 5 years. Open Targets and HPA number their releases. Snapshots get a DOI from Zenodo or Hugging Face.
5. **Every number can be traced back to its source.**
   - Provenance: the tool version, the parameters and a SHA-256 for every input.
   - The PSM → spectrum link is a **USI** (`mzspec:PXD…:run:scan:N:PEPTIDE/z`). PRIDE's PROXI server resolves these live today, so any agent or human can pull up the spectrum behind a claim. The aging pipeline already records everything needed to build them.

**The opening.** PRIDE has no official MCP server. No aging-proteomics resource has any agent-facing API, and quantms's MCP endpoint was broken when we tested it. A well-built, AI-first repository of reanalyzed aging proteomics would be a first of its kind. That makes it a publishable resource paper in its own right.

---

## 2. The architecture in one picture

```
 aging pipeline (F:\aging_data\<run>\<PXD>\)          ← produces; dataRepo never re-searches
        │  psmtsv / FlashLFQ tsv / provenance.json / SDRF / qc_report / flags
        ▼
 ┌─ INGEST (Python, glue only) ─────────────────────────────────────────────┐
 │ parse → validate against schema → melt wide→long → attach ontology IDs   │
 │ → mint USIs → write one immutable Parquet bundle per dataset-run         │
 └──────────────────────────────────────────────────────────────────────────┘
        ▼
 LAYER 1  CANONICAL FILES   store/<PXD>/<release-hash>/*.parquet  (+ sdrf.tsv, provenance.json)
          QPX-compatible superset · ZSTD Parquet · tidy/long · NA not 0
        ▼  (offline "build" job)
 LAYER 2  QUERY CATALOG     one prebuilt DuckDB file + cross-dataset indexes + precomputed stats
        ▼
 LAYER 3  INTERFACES (one code path, several doors)
   ├─ Python (+R) client   datarepo.protein_profile("P12345") → DataFrame
   ├─ REST API             FastAPI, auto OpenAPI docs, /health, cursor paging, fields=, TSV/JSON/Parquet
   ├─ MCP server           ~8 curated tools + sandboxed SQL (same functions as REST)
   ├─ Static site          dataset pages with Bioschemas JSON-LD, llms.txt, works if API is down
   └─ Bulk download        the Parquet itself (+ Zenodo/HF DOI snapshot per release)
```

**Why this stack.** It is DuckDB + Parquet + FastAPI + FastMCP, with LinkML for the schema.
- It runs the same way on your Windows box and on a Linux server.
- It needs no database administrator.
- It is what quantms, MotherDuck, Datasette and the Hugging Face datasets all converged on.
- We reject heavier options (Postgres, GraphQL, Kubernetes, Iceberg or Spark) until a measured need appears.

**This is not "big data".**
- Search output is about 3 MB of tables per raw file, once you exclude the GPTMD database.
- 300 datasets × ~20 files is ~6,000 files and ~15M PSM rows. That comes to **a few GB of Parquet**.
- One DuckDB file on one modest server, or even a laptop, will answer queries in milliseconds.

---

## 3. The data model: what goes in the files

The schema is written once in **LinkML** (`schema/datarepo.yaml`). Pydantic validators, JSON Schema, DuckDB DDL and the documentation served to agents are all generated from it. We stay compatible with **QPX** (the Parquet format from bigbio/quantms) where it has a matching view, and extend it where it doesn't. QPX has no proteoform view and no USI.

| Table | Grain | Key contents | Source |
|---|---|---|---|
| `dataset` | 1/PXD | accession, title, organism, instruments, informativeness verdict, pipeline commit, MM version, **flags**, release hash | discover + provenance |
| `sample` | 1/sample | **age (years, normalized) + age_raw + age_is_lower_bound**, sex, tissue (UBERON), cell type (CL), disease (MONDO/EFO), condition, bio-rep | SDRF + SdrfAge (mzLib #1326) |
| `run` | 1/raw file | file name, sample, sha256, PRIDE checksum, QC metrics, ID rate | fetch_manifest + qc_report |
| `psm` | 1/PSM | **usi**, peptidoform (ProForma 2), base seq, charge, score, q, PEP, mass error, accession(s), D/C/T | AllPSMs.psmtsv |
| `peptidoform` | 1/peptidoform/dataset | best q/PEP, protein group, mods, localization | AllPeptides.psmtsv |
| `peptidoform_quant` | 1/peptidoform/run | **apex intensity** (D13), detection type (MSMS / MBR), DEF-MBR-KEPT flag, PIP q | AllQuantifiedPeaks (long) |
| `protein_group` | 1/group/dataset | accessions, gene, q, coverage, unique/shared peptides | AllQuantifiedProteinGroups |
| `protein_group_quant` | 1/group/run | intensity, spectral count (melted from wide) | AllQuantifiedProteinGroups |
| `ptm_site` | 1/site | protein, position, modification (UNIMOD), localization score, evidence | derived from psm |
| `protein` | 1/accession | UniProt accession, gene, organism, length | UniProt XML |
| `localization` | 1/protein/compartment/source | compartment (GO-CC ID + organelle label), source (GO/UniProt/HPA/MitoCarta/LOPIT), evidence, **map version** | `go` project (REQ-GO-2..10) |
| `age_effect` | 1/feature/dataset/model | estimate, SE, p, q, n, model definition ID | aging stage 7 (R/msqrob2) |
| `organelle_age_summary` | 1/organelle/model | meta-analytic effect across datasets | precomputed from age_effect |
| `definition` | 1/DEF-ID | every metric's definition ID + text + owner (QuantProject DEF-*, etc.) | owning projects |
| `provenance` | 1/stage/dataset | flattened provenance.json (+ original kept) | provenance.json |
| `finding` | 1/flag | suspicious flags (low_id_rate, no_design_file, …) | provenance flags, SUSPICIOUS.md |

**Rules carried over from aging**
- Leave missing values as NA, not 0.
- Every number carries a **definition ID** from the project that produces it.
- MBR is only ever done within a dataset.
- Apex intensity is the quant value.
- Use one peptidoform notation everywhere: ProForma 2 with UNIMOD accessions. quantms mixes notations, and we shouldn't.

**Who owns what**
- aging (D1) and dataRepo own **storage and serving** only.
- The organelle map belongs to `go`.
- Metric definitions belong to QuantProject.
- The age normalizer belongs to sdrf/mzLib.
- Parsing should use pyMzLib's typed readers (REQ-BRIDGE-1) wherever they exist, so we don't hand-parse psmtsv.

---

## 4. The AI interface (MCP)

> **D12 narrows this.** Three tools ship first — `datarepo_describe`, `datarepo_search`,
> `datarepo_sql` — and a fourth is added only where aging's benchmark shows the agent getting a
> specific answer wrong. The eight below are a menu to draw from, not a build list: most are thin
> wrappers over SQL we would write anyway, and several answer questions no measurement has asked.
> The server is local stdio first, run as `datarepo mcp --catalog <path>`.
>
> **D14 stages the sandbox.** The sqlglot allow-list described in `datarepo_sql` below is deferred
> to when a public endpoint exists. What ships now is `enable_external_access=false` with a locked
> config, the row/character caps and a 30 s `con.interrupt()` watchdog — DuckDB 1.5 has no
> `statement_timeout`. This was measured, not assumed: `read_only=True` **alone is not a sandbox**,
> and a read-only connection will happily `read_csv_auto` a file anywhere on disk.
>
> **D15 replaces the acceptance bar.** "Agent answers ≥X% of the question set" is the wrong measure
> when `SCHEMA_COVERAGE.md` says 94 of 168 questions wait on a producer. The bar is **zero
> silently-wrong answers**: right when the data can answer, "no data" when it cannot, and either
> kind of wrong is a failure.

One FastMCP server calls the same Python functions as REST. It follows the stateless 2026-07-28 MCP spec, so it runs on any ordinary web host.

| Tool | Answers |
|---|---|
| `datarepo_search` | "What do you have on LMNA / mitochondria / PXD036557 / 'skeletal muscle'?" → IDs + names |
| `datarepo_describe` | Schema, one table or topic at a time: columns, units, ontology meaning, definition IDs |
| `datarepo_dataset` | One dataset's metadata, samples and age range, QC, flags and provenance summary |
| `datarepo_protein_profile` | One protein (or proteoform) across all datasets: detected where, abundance vs age, localization |
| `datarepo_organelle_summary` | Proteins in a compartment and their age effects across datasets |
| `datarepo_age_effects` | Ranked age-associated features, filtered by organelle, tissue, species or dataset |
| `datarepo_spectrum` | Given a PSM or USI, return the USI plus PROXI links so the spectrum can be viewed |
| `datarepo_sql` | Read-only SQL for anything else. DuckDB is locked down (no external access, locked config), queries pass a sqlglot AST allow-list, results are capped at 1,000 rows or 50k characters with a truncated flag, and a 30 s timeout applies. |

**Design rules.** These come from Anthropic's guidance and from Open Targets and quantms.
- Return compact tables with readable names alongside IDs.
- Offer a `concise` / `detailed` option.
- Filter, page and truncate by default.
- Return errors with a *hint* the agent can act on.
- Declare an `outputSchema` for typed results.
- Serve MCP *resources* for the schema documentation and example questions.

**How we'll know the tools are good.** We write an **evaluation set of 50–100 real aging questions** before building the tools, then iterate against it, as Open Targets did with its Karenina benchmark. Three examples:
- *"Which mitochondrial proteins decline with age in skeletal muscle in ≥3 datasets?"*
- *"Is the age effect for LMNA driven by one dataset?"*
- *"Show me the spectrum supporting the phospho-site claim for X."*

**The fastest win.** A local MCP server over stdio works in Claude Code on your own machine within about two weeks, before any web server exists.

---

## 5. Making it findable and citable

- **Landing pages.** Every dataset gets a static page with **Bioschemas/schema.org Dataset JSON-LD**. This puts it in Google Dataset Search.
- **`llms.txt`** at the site root, pointing to the docs, the MCP URL and the schema.
- **Per release:**
  - **Croissant 1.1** JSON-LD, the ML-dataset metadata format used by Hugging Face and Kaggle;
  - an **RO-Crate**, which packages the provenance;
  - a **Zenodo DOI**.
- **Optional:** a Hugging Face mirror. That gives anyone `hf://` access from DuckDB and a dataset viewer for free.
- **LLM-written summaries.** ~~Only ship after a human reviews them in a PR.~~ **Superseded by
  D17:** they auto-publish with a visible "generated" label, and are **grounded by construction** —
  the model may read only fields the catalog holds plus aging's own manifest `reason`/`notes`, never
  PRIDE's abstract, the paper, or what a model believes about the accession. So a summary can be
  clumsy and cannot be false about biology. The review rule is rejected as unrunnable: 300 datasets
  means 300 reviews with no owner, and the honest prediction is that it gets quietly dropped and
  they ship unreviewed anyway.
- **Back to the archives.** Deposit the reanalysis to PRIDE or MassIVE (aging G9, `massive-reanalysis-upload`) and cross-link it.

---

## 6. Roadmap: small, testable steps

| Step | Deliverable | Test that proves it |
|---|---|---|
| 0 | **Question set** (50–100 questions) + LinkML schema v0 | Every question maps to tables/columns |
| 1 | `datarepo ingest` for the 2 existing datasets → Parquet on F: | Counts reconcile with `results.txt`/provenance; round-trip tests; schema validation |
| 2 | `datarepo build` → DuckDB catalog + indexes | Question-set queries run in SQL |
| 3 | **Local MCP (stdio)**, three tools (D12) | Zero silently-wrong answers on aging's set (D15); every answer carries its `catalog_id` (D13) |
| 4a | Static site + `llms.txt` + Croissant + Zenodo DOI (D16) | Pages generated from a catalog, published by aging; site works with no API at all |
| 4b | ~~FastAPI REST + Docker Compose~~ **deferred (D16)** | Pending N1/G9, and evidence of a human who wants REST |
| 5 | Deploy to a Linux host (N1/G9); release v0.1 with DOI | External agent answers the question set |
| 6 | Auto-**ingest** as the pipeline finishes each PXD — never auto-**release** (D18) | Idempotent re-ingest; no release moves without a pin (D11) |

Steps 0–3 need **no server and no decisions from anyone else** — and step 4a turns out not to
either, which is why it comes before the server (D16). No Python or R client is in v1: the main
users are agents, and nobody has asked for either (D12).

---

## 7. Decisions needed from you (for `/grill-me`) — ALL ANSWERED

> All four were resolved on 2026-09-19. **Item 2 below is wrong and is kept only for the record:**
> it recommended private-until-publication, and D2 locked public-from-day-one, no login, on the same
> day. Read the decisions, not this list.


1. **Hosting (G2).** Options: a lab Linux box, UW (CHTC/DoIT), NCEMS cyberinfrastructure, or the cloud. My recommendation is to start on a lab box or NCEMS behind a public URL, because Docker Compose moves easily between them.
2. **Access (G3).** Public from day one, or private to the working group until publication? My recommendation: private until the first paper, with the design public-ready (auth only at the proxy).
3. **QPX compatibility.** My recommendation is a QPX-compatible superset. It interoperates with quantms/PRIDE and costs little.
4. **Scope of v0.** My recommendation is human, DDA, label-free only, matching aging v1.

## 8. Things spotted along the way (for aging, not fixed here)

- **The dataset counts disagree.** The discover output says 1,432 hits, 286 kept and 35 with an SDRF. The threads say 589 hits and 88 with an SDRF. PLAN.md says 407 kept. The "frozen accession list" has no single source of truth yet.
- **The PSM counts disagree.** `results.txt` reports 26,582 PSMs at 1% FDR, but provenance `psms_1pct` says 27,958. Contaminants may explain the difference.
- **Stage 7 needs the design file.** Without it (no_design_file), FlashLFQ treats each file as its own biological replicate. The `age_effect` table therefore can't be populated until QuantProject M7 lands. The repository can be built and tested before then.
