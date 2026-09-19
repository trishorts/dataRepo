# How proteomics resources serve (re)analysis results — research notes (2026-09-19)

Written by a research subagent on 2026-09-19. **Verified** means the subagent read the primary doc or source, or called the live endpoint itself. Anything the subagent could not verify is flagged.

## 1. QPX (formerly quantms.io) + portal.quantms.org — the closest precedent

**The format**
- Repo: https://github.com/bigbio/qpx. Docs and spec: https://qpx.quantms.org and https://qpx.quantms.org/spec/.
- Current release: PyPI `qpx` 1.1.4, spec 1.1. The spec is pre-2.0, so breaking changes are allowed. Every file carries `qpx_version`.
- A dataset is a set of files named `{PREFIX}.<view>.parquet`:
  - **Data views:**
    - `psm`: psm_id, peptidoform (ProForma), charge, run_file_name, scan (an int32 array), optional feature_id
    - `feature`: feature_id, peptidoform, charge, run_file_name, rt, intensities (a list of {label, intensity}), anchor_protein
    - `pg`: pg_id, pg_accessions, anchor_protein, label, intensity. Since 1.1 there is one row per label.
    - `mz` and `pepmap`
  - **Metadata views:** `dataset`, `sample`, `run`, `provenance` and `ontology`. `ontology` maps each field to an ontology term, so the dataset describes itself. The raw `sdrf.tsv` is kept too.
  - **Expression views:** `ae.h5ad` (iBAQ) and `de.h5ad` (differential expression). These are AnnData files, not Parquet.
- Files are compressed with ZSTD. They can use Hive partitions (usually by `run_file_name`) and carry key-value metadata in the file footer. They are meant to be read straight from S3 by DuckDB's httpfs extension.
- Converters exist for MaxQuant, DIA-NN, Spectronaut, FragPipe, OpenMS/quantms, CPTAC and **mzIdentML**. MetaMorpheus writes mzIdentML, so it can already be converted.
- **What QPX lacks:**
  - no proteoform or top-down view
  - no stored USI column
  - inconsistent peptidoform notation in live data: `C(UNIMOD:4)` appears alongside `C(Carbamidomethyl)`

**The reanalysis:** quantms (Nature Methods 2024) reanalyzed 83 ProteomeXchange datasets: 29,354 raw files and 13,132 samples (https://www.nature.com/articles/s41592-024-02343-1). The ProteomeXchange 2026 paper says ">103 large-scale human studies".

**The portal** (https://github.com/bigbio/quantms-portal). Its design spec, dated 2026-04-09, ranks its users "AI agents > bioinformaticians > biologists".

- **Two tiers.**
  - A static Vue site on GitHub Pages, built from pre-baked JSON. It must keep working when the backend is down.
  - A FastAPI + DuckDB layer over Parquet on S3.
- **Collections.**
  - Any folder containing `*.dataset.parquet` counts as a dataset, so there is no manifest.
  - `_index/` holds prebuilt indexes:
    - peptides, partitioned by their first two amino acids
    - proteins, partitioned by the first two characters of the accession
  - A new index is swapped in blue/green style: `_metadata.parquet` is written last, then an atomic rename.
- **Hardening for the planned raw-SQL MCP.**
  - DuckDB is locked down with `enable_external_access=false` and `lock_configuration=true`.
  - Queries are filtered with a sqlglot AST blocklist.
  - Every query gets a forced LIMIT of 1000 rows and a 30 s timeout, plus memory and thread caps.
  - Errors come back as structured JSON with a "hint" field.
- **What shipped instead of raw SQL: task-level tools.**
  - The REST API lives at https://api.quantms.org/peptide-search. Its routes are `/search/peptide|protein|gene`, `/peptide/profile`, `/protein/profile`, `/protein/coverage-map`, `/peptidoforms`, `/stats`, `/facets`, `/modifications`, `/health` and `/ready`.
  - MCP tools of the same names are documented. **The handshake was not verified:** the endpoint answers with a 307 redirect to the wrong path. The `quantms-mcp` package returns 404 on PyPI.
  - Scale according to `/stats`: 240 datasets, 4.73M peptides, 9.13M peptidoforms, 27.6M rows.
- **Infrastructure.**
  - A weekly Kubernetes CronJob builds immutable, content-addressed artifacts: one Parquet file per dataset, then **one prebuilt DuckDB file**.
  - Serving pods open that file in seconds, where rebuilding took 10–15 minutes. A version check forces a rebuild from Parquet if the file is stale.
  - Hot columns have ART indexes. A `prot_tokens` inverted side-table serves lookups on list columns.
  - An exact peptide lookup takes about 55 ms.
  - Dataset IDs look like `PXD030304/fa0e1399f581`.
  - The site publishes `llms.txt` (verified live).
- **Dataset descriptions.** An LLM (the Claude API) writes them, and they ship only through a **human-reviewed PR**.
- **Related bigbio work.**
  - `sdrf-skills`: agent skills plus a local stdio MCP over PRIDE v2, OLS, Europe PMC and MassIVE PROXI.
  - `mokume`: a local MCP server.

## 2. PRIDE Archive
- **REST API v3** (https://www.ebi.ac.uk/pride/ws/archive/v3/v3/api-docs) is read-only, returns JSON and has OpenAPI docs. v2 still runs. Endpoints:
  - `/search/projects`, `/facet/projects` and `/search/autocomplete`
  - `/projects/{acc}` and `/projects/{acc}/files`
  - `/projects/reanalysis/{acc}`
  - `/files/sdrf/{acc}` and `/files/checksum/{acc}`
  - `/proteins/{acc}`
  - `/stats/*`
- The **2025 NAR update** (https://pmc.ncbi.nlm.nih.gov/articles/PMC11701690/) reported:
  - USI and file-streaming APIs, plus the `pridepy` client
  - downloads over FTP, Aspera and Globus
  - 42,036 datasets totalling 285 PB
  - a documentation chatbot based on Gemini
- **Expression Atlas** holds 123 proteomics studies. It calls "AI-ready formats" planned, not done.
- **MCP:**
  - On 2025-12-02 EBI said it was only "exploring" MCP.
  - The "official" PRIDE and Expression Atlas MCP servers listed on PulseMCP are third-party wrappers by Pipeworx that only search metadata (https://github.com/pipeworx-io/mcp-pride).
  - **No MCP server hosted by EBI for PRIDE was found.**

## 3. Other resources
- **USI / PROXI.**
  - The USI format is `mzspec:PXD:run:scan:N:PEPTIDOFORM/charge`. HUPO-PSI ratified it in 2021 (https://www.nature.com/articles/s41592-021-01184-6).
  - The PROXI spec is at https://github.com/HUPO-PSI/proxi-schemas.
  - **Verified live:** the USI `mzspec:PXD000561:Adult_Frontalcortex_bRP_Elite_85_f09:scan:17555:VLHPLEGAVVIIFK/2` returned peaks from both:
    - https://www.ebi.ac.uk/pride/proxi/archive/v0.1/spectra?resultType=full&usi=…
    - https://massive.ucsd.edu/ProteoSAFe/proxi/v0.1/spectra?…
  - So if each of our PSMs stores the PXD, the raw file stem and the scan, a reader can pull up the spectrum behind it for free.
- **ProteomicsDB:** API v2 is OData v2 over SAP HANA, with 93 entities (https://www.proteomicsdb.org/vue/apiv2/). Only the paper was verified, not the live API.
- **MassIVE-KB:** spectral libraries of 5.9M precursors. MassIVE.quant holds 209 reanalyses of 105 datasets.
- **jPOST:** jPOSTdb reanalyzed 600+ datasets with UniScore. Its data is in RDF, but a SPARQL endpoint was not verified.
- **PaxDb 5.0:** 831 datasets, uniformly reprocessed, with abundance in ppm and a quality score per dataset.

## 4. Standards
- **mzTab 1.0:** proteomics work on it has stalled since 2014. mzTab-M covers metabolomics only.
- **mzIdentML 1.3.0** (2024) is still the archive format that ProteomeXchange accepts for "complete" submissions.
- **mzPeak:** a PSI working draft for Parquet-based raw spectra, with a Rust reference implementation (https://github.com/HUPO-PSI/mzPeak).
- **mzSpecLib and mzPAF** (Anal. Chem. 2024): a spectral-library standard and a peak-annotation notation.
- **SDRF-Proteomics:**
  - spec: https://github.com/bigbio/proteomics-sample-metadata
  - validator: `sdrf-pipelines`
  - annotated reanalysis SDRFs: `sdrf-annotated-datasets`
  - QPX splits SDRF into `sample` and `run` Parquet files and keeps the raw TSV too.

## 5. Aging and organelle resources: how you get the data
- **HPA:**
  - Every entry is a URL in several formats (`/ENSG….json|tsv|xml`).
  - `api/search_download.php?search=&columns=&format=` selects from 200+ column codes, and the response carries an `X-Total-Results` header.
  - Bulk TSVs come with each release.
  - **This is the best simple API in this set.**
- **OpenCell:** bulk downloads, with raw images on AWS Open Data (`czb-opencell`).
- **Organelle IP map (Hein 2024):** a portal plus the analysis code on GitHub.
- **LOPIT:** distributed as Bioconductor `pRolocdata` MSnSet objects.
- **MitoCarta 3.0:** static Excel and FASTA downloads.
- **Tabula Muris Senis:** h5ad files on public S3, plus access through the Census API.
- **Mouse aging proteomic atlas** (aging-proteomics.info): a search page and downloads, with **no API**.
- **No aging-proteomics resource with an agent-facing API was found.**
