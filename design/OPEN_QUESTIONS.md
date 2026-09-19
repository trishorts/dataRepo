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
| U3 | **Credit line** for CC BY 4.0 (D3): what exactly should reusers cite? The NCEMS working group name, a grant number, the paper? | "NCEMS Aging Proteome Working Group, dataRepo vX.Y, DOI…", to be replaced once confirmed. |
| U5 | **How generic is "generic"?** You said to keep dataRepo "a bit more generic." My proposal: the **core** schema (dataset, sample, run, psm, peptidoform, quant, protein group, protein, provenance, finding, definition) knows nothing about aging, so any reanalysis project could use it. The aging-specific tables (`age_effect`, `organelle_age_summary`, and the age columns on `sample`) move to a pluggable **study layer** that a consumer project like aging supplies. The name, goal and first deployment stay aging's. | Core generic + aging as the first study layer. |

## Waiting on aging (thread `design/threads/aging/`)

| ID | Question | Status |
|---|---|---|
| DATAREPO-1 | Revisit v1 scope: DIA, TMT and rodent are in (your correction). | Posted 001, 2026-09-19 |
| DATAREPO-2 | Record organism / acquisition / quant_method / instrument_vendor explicitly in provenance. | Posted 001 |
| DATAREPO-3 | Which accession list and which PSM count are canonical (count mismatches)? | Posted 001 |
| DATAREPO-4 | Own the benchmark question set (the user's call); a 78-question seed is attached. | Posted 002, 2026-09-19 |

## Answered

| ID | Answer | Recorded as |
|---|---|---|
| G2 | Prototype local; NCEMS runs production | D1 |
| G3 | Public from day one, no login | D2 |
| — | CC BY 4.0 data, MIT code | D3 |
| G6a | QPX-compatible superset | D4 |
| G6b | Human + rodent, DDA + DIA, LFQ + TMT | D5 |
