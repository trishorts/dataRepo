# AI-ready biology data platforms: research notes (2026-09-19)

A research subagent compiled these notes on 2026-09-19.

Status tags:
- **[shipped]**: released and live.
- **[announced]**: a preprint, a roadmap item, or a release candidate.
- **[unverified]**: could not be confirmed against a primary source.

## 1. CZ CELLxGENE Census

**What it is.** A standardized, cloud-native store read directly from public S3, using the SOMA spec and TileDB-SOMA. No query server sits in front of it.
- Sources: https://chanzuckerberg.github.io/cellxgene-census/ and https://registry.opendata.aws/biohub-cellxgene-census/
- Python and R clients return AnnData or Seurat objects.
- PyTorch loaders are included.

**Releases.** A long-term-support (LTS) release ships every 6 months and is kept for at least 5 years. Weekly builds carry no guarantee.

**Why it works.** Every dataset is curated to one required metadata schema before ingest. The schema has 10 required categories, mostly ontology terms. That is why a single query can span more than 900 datasets and over 65M cells.
- Source: https://academic.oup.com/nar/article/53/D1/D886/7912032
- **The lesson is standardization, not the storage engine.**

**Weaknesses.**
- The client library (tiledbsoma) is heavy.
- There is no official MCP server.

## 2. Open Targets Platform

**Access routes.** It offers every access route at once:
- a GraphQL API;
- Parquet-only bulk downloads (JSON was dropped around release 25.03), mirrored on the EBI FTP and on GCS;
- a BigQuery public dataset.

**Their MCP servers.**
- **July 2025 community prototype:** 45 tools, one per endpoint. The author said "the hardest part is deciding which query patterns to expose as tools." (https://blog.opentargets.org/case-study-mcp-server/)
- **Official server, 12 Jan 2026:** built with Anthropic. (https://blog.opentargets.org/official-open-targets-mcp/, https://github.com/opentargets/open-targets-platform-mcp)
  - It has **5 tools**:
    - `get_open_targets_graphql_schema` (returns subschemas by category)
    - `get_type_dependencies`
    - `query_open_targets_graphql`
    - `batch_query_open_targets_graphql`
    - `search_entities`
  - An optional jq filter runs server-side to cut the tokens returned.
  - It is stateless HTTP, rate-limited to 3 requests/s.
  - It is hosted at `https://mcp.platform.opentargets.org/mcp`. It also runs through uvx or Docker.

**Karenina benchmark.** 140 question-answer pairs. It showed that generic wrappers were inefficient, used too many tokens and made more errors. The fix was an interpretation layer that helps the agent paginate, judge relevance and choose its next step.

**Lesson: they went from 45 thin tools to 5 schema-aware ones, and chose between them by benchmarking.**

## 3. EBI, UniProt, NCBI, BioMCP and Anthropic's life-sciences connectors

**EMBL-EBI**
- On 2 Dec 2025 EBI said it is "exploring" MCP. It noted that these servers are mostly third-party. (https://www.embl.org/news/people-perspectives/connecting-ai-to-biology-model-context-protocol/)
- The BioContextAI registry lists 74 servers and about 3,145 tools. (https://biocontext.ai/, Nat Biotech https://www.nature.com/articles/s41587-025-02900-9)

**UniProt**
- No official MCP server was found [unverified absence].
- The REST API is a good pattern to copy:
  - `/search` returns cursor pages, 25 results by default and 500 at most, with a `Link` header for the next page.
  - `/stream` returns up to 10M results.
  - `fields=` selects columns.
- Sources: https://www.uniprot.org/help/api_queries and https://academic.oup.com/nar/article/53/W1/W547/8126256

**NCBI**
- NCBI Datasets offers REST v2 with an OpenAPI 3 spec, the `datasets` and `dataformat` CLIs, and zipped data packages in JSON Lines.
- Its MCP servers are community-built.

**PRIDE**
- There is no official MCP server. The Pipeworx wrapper is third-party.
- **This leaves room for a proteomics lab to be first.**

**BioMCP** (https://github.com/genomoncology/biomcp)
- One CLI and MCP server covering about 30 sources.
- It uses a single `search`/`get` grammar across entities.
- Named **sections** give progressive disclosure, e.g. `get gene BRAF pathways hpa`.
- It has batch operations and pivots across entities.

**Anthropic connectors**
- Oct 2025: Benchling, 10x, PubMed, BioRender, Synapse and Wiley.
- Jan 2026: ClinicalTrials.gov, bioRxiv, Open Targets, ChEMBL, ToolUniverse, Medidata and Owkin.
- Agent Skills were also added, including Nextflow and scVI-tools.
- Source: https://anthropic.com/news/healthcare-life-sciences

## 4. Standards for AI-ready data

**Bridge2AI criteria** (https://pmc.ncbi.nlm.nih.gov/articles/PMC11526931/; a bioRxiv preprint, v6 April 2026, so [announced])
- Seven dimensions: FAIRness, Provenance, Characterization, Ethics, Pre-model Explainability, Sustainability and Computability.
- They are put into practice as **RO-Crate** packages generated with FAIRSCAPE. Croissant and LinkML are also used.

**Croissant 1.1** (12 Feb 2026, https://mlcommons.org/2026/02/croissant-1-1-standard/)
- Based on schema.org JSON-LD.
- Adds PROV-O provenance, ontology links at the field and value level, and DUO/ODRL usage rules that agents can check.
- More than 700K datasets use it, including those on Hugging Face, Kaggle and OpenML.

**RO-Crate 1.2** (June 2025)
- Adds detached crates that can be embedded in APIs.
- Adds the Workflow Run Crate profile.
- Version 1.3 was announced in June 2026.

**Bioschemas / schema.org Dataset JSON-LD**
- Markup on landing pages that puts a dataset into Google Dataset Search.

**llms.txt** (proposed by Jeremy Howard in Sep 2024)
- A markdown index for agents to read.
- No major vendor had committed to reading it as of Q1 2026.
- It is cheap to add and useful for coding agents.

## 5. MCP best practices for data servers

**Anthropic, "Writing tools for agents"** (https://www.anthropic.com/engineering/writing-tools-for-agents)
- Build task-level tools rather than one tool per endpoint.
- Namespace tool names, e.g. `service_resource_verb`.
- Return readable names alongside IDs.
- Offer a `response_format` choice of concise or detailed.
- Paginate, filter and truncate by default. Claude Code caps a tool response at 25k tokens.
- Write errors that tell the agent what to do next.
- Measure the tools against a set of evaluation questions.

**Anthropic, "Code execution with MCP"** (https://www.anthropic.com/engineering/code-execution-with-mcp)
- The agent writes code that filters results before they reach its context. In their example this cut tokens by 98.7%.

**MCP spec**
- **2025-06-18 and 2025-11-25:** a tool can declare an `outputSchema` and return `structuredContent`.
- **2026-07-28 (final)** makes the protocol stateless:
  - no initialize handshake and no `Mcp-Session-Id`;
  - protocol version and capabilities are sent with every request;
  - list results can be cached;
  - so it runs fine behind a load balancer or on serverless.
  - Sources: https://blog.modelcontextprotocol.io/posts/2026-07-28/ and https://modelcontextprotocol.io/specification/2026-07-28/changelog

**Read-only SQL servers**

MotherDuck/DuckDB MCP (https://github.com/motherduckdb/mcp-server-motherduck)
- Tools: `execute_query`, `list_databases` and `list_tables`.
- Read-only by default.
- Results are capped at 1,024 rows and 50k characters.
- Its authors warn that **"read-only mode alone is not sufficient"**.

datasette-mcp (https://github.com/datasette/datasette-mcp)
- Serves an `/-/mcp` endpoint with `list_databases`, `get_database_schema` and `execute_sql`.
- Results carry a truncated flag.
- Datasette Agent (May 2026) keeps saved queries behind human approval.

**FastMCP `from_openapi()`**
- Fine for prototypes.
- The FastMCP docs say curated servers perform "significantly better" than ones auto-converted from OpenAPI (https://gofastmcp.com/integrations/openapi).
- The Open Targets benchmark agrees.

## 6. Lightweight stacks

**DuckDB**
- Reads Parquet over HTTP, S3 and `hf://` with no server.
- Hugging Face converts datasets to Parquet automatically.

**DuckLake 1.0** (April 2026, https://duckdb.org/2026/04/13/ducklake-10)
- Keeps a SQL catalog and adds snapshots and time travel.
- Version 1.1 is expected in September 2026.
- Simpler than Iceberg or Delta for a single team.

**API style**
- FastAPI generates OpenAPI docs automatically.
- GraphQL pushes the work of composing queries onto the agent. Open Targets needed extra tools to subset its schema.

**LinkML** (https://linkml.io/)
- One YAML file generates Pydantic models, JSON Schema, SQL DDL and OWL.
- Used by Monarch, Bridge2AI and INCLUDE.

**DOIs**
- Zenodo issues DOIs for GitHub releases.
- Hugging Face issues DataCite DOIs for datasets. After a DOI is issued, deleting the dataset requires a support request.

## 7. Other portals

**GTEx**
- REST v2 with OpenAPI docs (`/api/v2/docs`).
- The `gtexr` R client.

**Human Protein Atlas**
- One URL per entry in each format.
- `search_download.php` with column selection.
- Bulk TSV files.

**HuBMAP**
- Separate Search, Entity and Ontology APIs.
- Files are delivered through Globus.

**Human Cell Atlas**
- The Azul REST API.
- Data sits in a public S3 bucket.

## Patterns that recur

1. Standardize the metadata first. The choice of storage engine matters less.
2. Bulk columnar files are the product. APIs are views onto them.
3. Releases are versioned, immutable and come with a support window.
4. Several access routes lead to the same data: UI, REST, bulk download, SQL, R and Python clients, and MCP.
5. Agent interfaces settle on a handful of generic, schema-aware tools:
   - resolve an entity;
   - discover part of the schema;
   - run a bounded query;
   - batch requests;
   - filter or project on the server side.
6. The agent interface is benchmarked against a fixed set of questions.
7. Metadata is machine-readable: Bioschemas, Croissant, RO-Crate, and a DOI for each release.
8. Most AI access to the major databases is still community-built. An official, well-designed MCP server is still unusual.
