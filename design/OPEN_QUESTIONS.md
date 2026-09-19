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
| U6 | D8 makes dataRepo code-only, with aging hosting the data. Does aging also **run the service** (the API/MCP server over its data, deployed by NCEMS as aging's), or does it only publish the data files and someone else runs the server? | aging owns the whole instance: the data, the releases/DOIs, and the deployed service. dataRepo ships a package that aging runs. |

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
| DATAREPO-10 | = U6: does aging also run the service? | Posted 005. Default: yes, aging owns the whole instance. |

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
