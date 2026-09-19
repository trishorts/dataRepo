# Journal — dataRepo

- 2026-09-19 · INIT · phase INCEPTION · Sibling of `aging`. Its first task is researching how leading bio resources make data AI-ready, then proposing a framework.
- 2026-09-19 · RESEARCH · Three research passes (AI-ready platforms, proteomics resources, aging output inventory) are saved to lit/ and design/. FRAMEWORK.md v0 is proposed. It covers Parquet+DuckDB, FastAPI+MCP, LinkML, QPX superset and USI. Decisions G2/G3 are open.

## 2026-09-19 - First session: from "where do I begin" to a proposed framework

The user runs a strong search-and-quant pipeline (aging) but has no way to organize its results for
humans or AI. They asked me to study how the best bio projects make data AI-ready and to propose a
framework, and said they would rely on me for the server side. Three parallel research passes ran: AI-ready
platforms (CELLxGENE Census, Open Targets, EBI/UniProt/NCBI, MCP practice, Croissant/RO-Crate/Bioschemas),
proteomics resources (QPX/quantms portal, PRIDE v3, USI/PROXI, ProteomicsDB, jPOST, organelle and aging
atlases), and an inventory of what the aging pipeline actually writes on F:.

The conclusions that shaped FRAMEWORK.md v0:
- **Standardized metadata beats the choice of engine.** CELLxGENE's required schema is what makes
  its cross-dataset queries possible. For us, the age axis is the scarce asset.
- **Files are the product.** bigbio's quantms portal has already built almost exactly this. It uses
  Parquet, a prebuilt DuckDB file, and FastAPI plus task-level MCP tools. It is the precedent to copy,
  but it lacks proteoforms and USIs, and its MCP endpoint redirected to the wrong path when tested.
- **Agents do best with a few curated tools benchmarked against a question set.** Open Targets went
  from 45 tools to 5.
- **The data is small.** It comes to about 3 MB of tables per raw file, or a few GB at 300 datasets.
  There is no case for clusters or Postgres.

Nothing is locked yet. The user asked to close before reviewing the framework, so every
recommendation is still a proposal.

## 2026-09-19 - Second session: section 7 locked, questions handed to aging

A grill-me on FRAMEWORK section 7 locked five decisions quickly. D1: aging's D5 applies, so we prototype locally and NCEMS operators run production from a portable Docker Compose package. D2: public from day one with no login. The user is "about all open all the time", which overturned my recommendation of private-until-publication. D3: CC BY 4.0 for the data (credit for the working group) and MIT for the code. D4: a QPX-compatible superset. D5: the scope is wider than aging v1. The user said "aging is wrong about DIA. definitely DIA and TMT and rodent". So organism, acquisition, quant_method and instrument_vendor are real columns and the quant table is long (run, channel, feature, value). The user never picked between building DIA/TMT ingesters now or later; I defaulted to later (U1).

Thread dataRepo/001 went to aging, carrying the scope correction, a request for explicit scope axes in provenance, and the count mismatches (G7). It is committed and pushed on aging's side.

I drafted a 78-question benchmark, then the user redirected: aging should generate all the questions, and dataRepo stays "a bit more generic" (D6). The draft moved to aging as thread 002, a seed for aging to adopt. It is committed in aging but NOT pushed. The draft also surfaced six kinds of question the proposed schema can't answer (excluded datasets, release changelog, ortholog and cross-species age maps, PTM occupancy, organelle-mass normalization, TMT quant model); aging will route them. "Generic" raised its own open question, U5: my default is a generic core schema with aging as a pluggable study layer.

The user can't answer the NCEMS questions yet and will ask at an upcoming meeting. So every open question now lives in design/OPEN_QUESTIONS.md with a default, and work proceeds on the defaults (D7).

Auto mode blocked `gh repo create trishorts/dataRepo --public` as a possible data leak, so there is still no remote. The user has to run it themselves.

## 2026-09-19 - Third session: aging answered; schema v0 drafted

aging's reply (thread 003) handed back the benchmark: `aging/design/QUESTIONS.md` v0.3 has 168 questions, and its top 10 are K1 D2 O1 D1 T2 N1 M1 C1 G1 J16. It also routed new tables to us. We own the release changelog (R2). We store the census (R1), the dataset axes (R3, now including enrichment and labelling), the reference panels (R8) and the clock model (R9). From MetaMorpheus we store PTM stoichiometry (R7), glycopeptides (R16) and inferred proteoforms (R7b). The count mismatches are now aging's S20 and S21, both still open. I recorded all of this as G5, G7 and G11 and in OPEN_QUESTIONS.

I drafted the LinkML schema v0 on U5's default. The core (`schema/datarepo.yaml`, 25 classes) is generic. The aging study layer (`schema/study/aging.yaml`) is a stub that adds tables keyed on core IDs and never alters a core table, which is why age sits in SampleAge and not on Sample. The schema lints with 0 errors, a minimal bundle validates, and a bad enum value is rejected. Still open: the QPX column mapping, the producers' R7/R16 column names, aging's confirmation of the study layer, and field descriptions (design/SCHEMA_V0.md).
