# RESUME

<!-- BEGIN GENERATED -- render_resume.py owns this block; edit state.yaml, not here -->

**dataRepo** &middot; phase **INCEPTION** (1/10) &middot; created 2026-09-19 &middot; rendered 2026-09-24

| | |
|---|---|
| Commits | 223 |
| Sync | [`trishorts/dataRepo`](https://github.com/trishorts/dataRepo) |
| Locked decisions | 27 |
| Open gaps | 65 |
| Gate items skipped | 4 |

**Worktrees** -- details in `code/PINNED.md`

| Worktree | Branch | HEAD | Pin | Status |
|---|---|---|---|---|
| `code/mzLib_prD_proforma` | fix/psmtsv-proforma-from-full-sequence | `ebdfa790` | `ebdfa790` | at pin |
| `code/mzLib_prE_peaks` | fix/quantified-peaks-optional-mbr-score | `88610382` | `88610382` | at pin |

<!-- END GENERATED -->


## Goal

Build an AI-ready, API-accessible repository for the results of the `aging` pipeline's PRIDE
reanalyses. The results cover search, quant, provenance, design and organelle annotation. Humans can
use it, but AI agents are the main users. The question it serves is how organelle proteomes change
with age.

## Latest (2026-09-23, eighteenth session): dataRepo operates nothing (D27), and mzLib merged our PRs

**No code changed; datarepo is still 0.17.2 (`91fbdd9`).** This session was threads, the charter and a
decision.

- **D27 (the user's): dataRepo SHIPS, the instance operator RUNS.** It supersedes D24's "dataRepo
  runs the engines". The dataRepo project operates nothing. It ships the software, including the
  runner an operator uses to execute a released engine on stored data. Today aging is the operator.
  aging was asked first and alone (thread 053, **DATAREPO-43**). No engine has been told yet.
- **Charter v0.2** (`design/CHARTER.md`, `6a4318e`) merges the replies from aging, go, sdrf, logs and
  QuantProject. S4 (definition ids) becomes per-engine namespaces, a before-the-search run location
  is added, and seams S15-S19 are new; **S19, the experimental design**, matters most. ptmQtl, phred
  and pyMzLib have not replied. v0.3 waits on DATAREPO-43 (G61).
- **Threads out:** pyMzLib 007 (PRs D/E changed) and 008 (the bridge payload limit, measured on
  0.1.1: G57); go 009 (GO-A1/A2 answered, A3 half); sdrf 010 (SDRF-DR7/DR8, plus a correction of
  our own 006); aging 054 (per-run enrichment, **DATAREPO-44**).
- **Found by filling:** a required column with no true value after go's D28 (G53); per-characteristic
  SDRF provenance that we had announced but never built, and an unmatched-SDRF path that refuses the
  whole bundle as an "ingester bug" (G62); and PXD058611's capture runs, visible only through
  streptavidin (G63).
- **At close:** mzLib **#1338, #1345 (PR E) and #1346 (PR D) all merged**, approved, around
  2026-09-24 00:00 UTC. No release yet. **aging accepted D27's operator role** (055, their D45).

## 2026-09-23 (sixteenth session): the public site is live, and large files read

**`datarepo` 0.17.2 (`91fbdd9`, pushed).** No bundle or catalog-format id moved since 0.16.0:
`INGESTER_VERSION` 0.11.0, schema 0.0.8 and `CATALOG_VERSION` 4 are unchanged.

- **Public site LIVE as a preview:** https://trishorts.github.io/aging-pipeline/ (D25). It is built
  by `datarepo site` (docs/site.md) and served from an orphan `gh-pages` branch of the public
  `trishorts/aging-pipeline`, because `aging` is private. It was built from the scratch catalog
  `f656bfc22cf1f675` (0.15.0 code, since the store is still schema 0.0.7) and carries a "Preview"
  banner on every page. Front page: aging's overview (`--about`), six figures of merit, colour.
  aging were asked to own the text and the regenerate step (thread 051, DATAREPO-38, G58).
- **DATAREPO-37 fixed (0.17.2):** `read_psmtsv` reads files over 512 MiB in windows. PXD032044 (1.83
  GB, 1,798,356 records) reads in 9 windows and 494 s. Windowed equals whole on PXD067622. No
  `INGESTER_VERSION` bump, on purpose (D26). Answered in thread 052.
- **Deck for biologists:** `presentations/dataRepo_overview_2026-09-23.pptx` (10 slides, validated,
  not rendered; its builder is `presentations/build_overview_deck.js`).

## 2026-09-23 (fifteenth session): 0.16.0, and a responsibilities charter for eight projects

**`datarepo` 0.16.0 (`c619612`, pushed), core schema 0.0.8, `INGESTER_VERSION` 0.11.0, aging study
layer 0.3.0, `STUDY_INGESTER_VERSION` 0.4.0, `CATALOG_VERSION` 4.** It re-ids every bundle, so aging
owe a re-ingest, timed with their own manifest correction.

- **0.16.0:** G51 closed as aging ruled (C-terminal site on the last residue, typed
  `protein_c_term`/`peptide_c_term` against the searched sequence). Checked on the real PXD050351
  file: `P60510:L307:...@protein_c_term`, 0 wrong sites. Four capture `Enrichment` values
  (DATAREPO-34); 7 of aging's first 10 datasets are enrichments, not proteomes.
  `peptidoforms.engine_full_sequences`, because UNIMOD ProForma erases the engine category.
  Shape-only `organelle_term_categories` (go) and `trait_effects`/`ptm_pairs` (ptmQtl).
- **mzLib PRs from the `trishorts` fork, after `/oracle mzLib`** (the user's standing instruction):
  **D #1346** (psmtsv ProForma) and **E #1345** (peaks reader without `MBR Score`). Worktrees under
  `code/`, recorded in `code/PINNED.md`.
- **CI is green again** (`6533d71`). It had failed since at least 09-22 because fixture files checked
  out CRLF on Windows, which changed the example bundle's source hashes. `tests/data/** -text` now.
- **D24 (user decision): dataRepo never DEFINES but does RUN.** Engines own logic and definitions.
  dataRepo runs the released versions of engines that work on stored results (logs, ptmQtl, maybe
  go). aging's search runs the in-search ones (phred Q_loc, QuantProject quant, sdrf SDRF).
  **`design/CHARTER.md`** sets out define/run/store/consume per project, the chain the core question
  needs, and 14 seams with one owner each. It went to all eight parties (aging 048, go 006, logs
  014, ptmQtl 004, phred 002, sdrf 007, QuantProject 002, pyMzLib 006). It is a DRAFT until each
  signs its rows. It reversed our logs 013 answer: we now take option (a).

## 2026-09-22 (fourteenth session): 0.15.0 places PTM sites by sequence

**`datarepo` 0.15.0 (`666b6fb`, pushed), `INGESTER_VERSION` 0.10.0, aging study layer 0.3.0,
`STUDY_INGESTER_VERSION` 0.4.0, core schema 0.0.7, `CATALOG_VERSION` 4.** aging owe a re-ingest.

aging 043 found that `ptm_sites` misplaced every shared peptide's sites. MetaMorpheus de-duplicates
`Start and End Residues In Full Sequence` and repeats it per occurrence, and we had paired it with
`Accession` by index, so gamma-actin carried POTE-E's numbering. Sites are now placed by finding
each peptide in the searched protein sequences (`src/datarepo/sources/protein_db.py`,
sha256-checked against the search provenance). On all ten datasets, wrong residues went from
**1,674 to 0** and positions beyond the protein from **344 to 1**. That one site is G51, the first
C-terminal modification, which predates this change.

**How the numbers are made reproducible:** every ingest checks its own site residues
(`bundle.json` → `protein_databases.site_residue_check`). `tools/verify_ptm_sites.py <store>
[--db ...]` re-checks any bundle independently. `docs/ingest.md` "Reproducing a bundle" lists the
byte-identical inputs, which now include **both** searched databases, one of them inside the
MetaMorpheus install. Detail is in the CHANGELOG 0.15.0 entry and the journal.

## Where it stands (2026-09-22, twelfth session)

**FRAMEWORK steps 1, 2 and 3 are built.** `datarepo` **0.13.0**, schema **0.0.7**,
`INGESTER_VERSION` **0.9.0**, `CATALOG_VERSION` **4**, `STUDY_INGESTER_VERSION` **0.2.0**. aging
re-ingested all four datasets on 0.11.0 (catalog `71e48aa46a7c9900`) and run an unattended batch
toward 160 qualifying human datasets. **0.13.0 moves `INGESTER_VERSION`, so a re-ingest on
`efd1a83` is owed** — it fixes a collapsed-column parse that cost ~7,200 proteins their species.

### Ten thread peers — and the ones that replied changed what we build

Until that day dataRepo had **one** peer, aging, while eight open gaps named an upstream we needed
something from. Every request went through aging as a proxy — and a proxy loses the reasoning: one
of our measurements reached `go` that way carrying a mechanism we had already disproved, and aging
had to retract it on our behalf.

`go`, `sdrf`, `pyMzLib` and `QuantProject` now have direct channels (001 on each), each stating
what we need **and offering measurement back**, since we ingest at corpus scale and a count takes
minutes.

Opening them paid for itself immediately. **`go`'s output contract cannot be stored by our table**
(G39): REQ-GO-7 emits `inherited` / `propagated` flags we have no column for, so ingesting their
file would promote an annotation they deliberately marked as *assumed* into one that reads as
*measured* — and `organelle_label` is `required: true` against a field they leave empty, the same
trap that made every contaminant human. Both are ours, found only by reading a contract aging wrote
on our behalf that nobody had checked against the table.

**And the largest hole in this repository is SDRF-shaped** (G38): 75 samples, **zero** carrying
sex, tissue, cell type, disease, condition, cell line, individual or timepoint. Three of four
datasets have no SDRF at all. Every age-stratified question in the benchmark dies there — in a
repository whose purpose is how organelle proteomes change with age. sdrf had never been told.

**Three replied the same day, and two changed what we build.**

- **`go` — we had been coding against a spec they overruled two threads ago.** REQ-GO-5's
  leading/union switch, which our 001 spent its longest section on, was rejected in their 008.
  Their rule instead (D7, hardened into D13 with aging): *emit the data and let the consumer
  filter; never a run-time switch that changes what a file contains.* Their instruction to us:
  **"trust D1–D22, not REQ-GO-2..10"** — the requirements aging wrote on our behalf and our schema
  cites. `inherited`/`propagated` confirmed; `organelle_category` turns out **set-valued**, a grain
  problem in a `string` column. **go v1 ships partly as a column in our schema** — we are a design
  stakeholder, not only a consumer.
- **`sdrf` — the repair path exists (their D27) and `SdrfAge` is merged**, which we had recorded as
  unbuilt. It now carries the raw cell, added at our request the same day. Their question back: is
  `sdrf_status` honest at *dataset* granularity when a dataset is partly repaired? No — that is the
  grain rule aimed at our own schema.
- **`aging` — re-ingested on 0.13.0: 0 speciesless proteins in 97,731.** Nothing owed to them.

`pride`, `qc`, `pep` and `phred` were opened the same afternoon (001 on each, no reply yet), which
makes **nine** channels, not five. The count is worth stating because a resume that reads *five*
will not go looking for the other four.

### We answered go and sdrf, and both replies cost us a column (G42, G43)

**`go` 002 asked us to commit to `accession_is_leading` as load-bearing, and we refused.**
MetaMorpheus's `AllQuantifiedProteinGroups.tsv` has 26 columns and **none of them names a razor or
leading protein**; the `|`-joined accession list is **alphabetical** (159 of 159 multi-accession
rows across two datasets, zero deviations). So position 1 is alphabetical rank, and the
2,608/2,427/131/50 measurement go quotes — which reached them from us via aging — is measuring
`min(group)` by string comparison. Our own 9-dataset reproduction (4,354/4,123/171/60) is the same
artifact, and **two of go's four named examples do not survive**: CALM1 and RAB6A are first in every
dataset they appear in.

Their conclusion survives on better evidence, which is the useful half: of 4,354 accessions
identified in ≥2 of 9 datasets, **354 change group composition across datasets and 316 are alone in
one dataset and grouped in another** — ARF1, RAB1A/B, SAR1A, H3C1. And the property needs no new
column: `protein_groups.protein_accessions` already preserves it. **G43**, open as DATAREPO-28 to
go and pyMzLib.

**`sdrf` 003 closed the age question and opened a worse one.** Their D27 repair path yields
**exactly zero ages, permanently** — an age is a donor property and the path fills only
deposit-single-valued cells — and the curated corpus tops out at **153 accessions of 1,203**. The
actionable half is that aging's batch is heading for ~160 datasets selected on search-side criteria
with **no reference to those 153**, and 0 of 9 searched so far carry any age. Two sets of almost the
same size, currently disjoint. DATAREPO-31 asks for the list as a queue filter.

SDRF-DR3 got worse rather than better: **8 of 9 datasets have no SDRF**, not 3 of 4, and all five
added by the batch arrived without one. Across 162 samples, sex / organism_part / cell_type /
disease / condition / material_type / cell_line / individual_id / timepoint are **all zero**.

And SDRF-DR1 found **G42** in our own schema: PXD036557's SDRF *has* `organism part` and `disease`
columns, both `not available` in all 18 rows, and our `samples.organism_part` is NULL for those 18
exactly as it is for the 144 samples whose deposits were never asked. **We cannot tell "answered
not available" from "never asked"** — the `empty` vs `unknown` rule this project has already written
down twice, shipped a third time. sdrf's argument for the upstream template is the same sentence
about our table.

### The column we nearly invented (G43), and a tenth peer

`go` asked us to commit to `accession_is_leading` as load-bearing. We went to fill it and could not:
MetaMorpheus's `AllQuantifiedProteinGroups.tsv` has **26 columns and none names a razor or leading
protein**, and its `|`-joined accession list is **alphabetical** — 159 of 159 multi-accession rows
across two datasets, zero deviations. So element 0 is alphabetical rank, and aging's 013 measurement
that `go` quotes (2,608/2,427/131/50) is `min(group)` by string comparison. **Three projects passed
that number around and none of us checked it.** Two of go's four named examples do not reproduce.

Their conclusion survives on better evidence: of 4,354 accessions in ≥2 of 9 datasets, **354 change
group composition and 316 are alone in one dataset and grouped in another** — ARF1, RAB1A/B, SAR1A,
H3C1. And `protein_groups.protein_accessions` already preserves it, so no new column is needed.

We also delivered the three counts `go` asked for and they argued against our own longest section:
**19,246 groups, 423 multi-member (2.2%)**, median size 1. 97.8% of identified groups hold exactly
one protein, so the leading-vs-member question matters less than any of us had been treating it.

**`logs` is the tenth peer** — generic cross-species orthology, created today. Their `OWNERSHIP.md`
flagged two capabilities as possibly colliding with us and **both are theirs** (D23): accession→gene
resolution is not something we do, and `canonical_accession` only strips an isoform suffix and has
never fired on 110,910 rows. We told them `protein_annotations` — key/value string, dataset-keyed —
is the wrong home for one-to-many output, and raised `feature_type='orthogroup'` as the
cross-species pooling key that would make `age_effect_meta` work across species **with no new
tables**. Taxa confirmed: human, mouse, rat.

### What `beta` means for a mouse (G40, G41)

`AgeEffect.beta` is the coefficient on `age_decades = (age_years − 50) / 10`. **50 is a human
lifespan constant** — a 24-month mouse gives −4.8 decades, a "change per decade" for an animal that
lives two years. And `AgeEffect` has 29 columns, `AgeEffectMeta` 22, and **organism is in neither**,
while `age_effect_meta` exists precisely to pool across datasets.

A human and a mouse effect for one feature would pool into a meta-estimate with nothing recording
the difference — the contaminant-organism defect again, except that one was caught in a day and
this one would reach a meta-analysis. Our half is ours to fix regardless of aging's answer (038);
the centring constant is their definition. And `age_mappings` already carries `organism`,
`age_unit`, `life_stage`, `human_equivalent_years` — exactly what is needed — holds zero rows and is
wired to nothing, while aging's benchmark B6 is one of only two questions our coverage map calls
*no home*. It has a home.

### The defect that four review agents missed

MetaMorpheus collapses a `|`-joined column to one entry when every protein on the row shares it;
`protein_rows` zipped it positionally, so every accession after the first got an empty string. It
was introduced in 0.11.0 — *the release whose purpose was handling species correctly* — and
survived two benchmark agents and two red teams, because all four reasoned about the catalog while
the defect lived upstream in a producer file none of them could read.

What found it was refusing to assert something about another project's output without reading their
file. A GitHub issue against MetaMorpheus was one step from being filed for it. **A claim about
someone else's output is verified at the source, not from your own parse of it.**

**Locked:** D1-D11 as before, **D12-D18** (the MCP server's shape), **D19** (no fourth tool -- a
guard belongs on the path that cannot be avoided) and **D20** (provenance is a fact about the
server and is inferred from nothing).

### The server is built; its done-bar is measured, improving, and not claimed

`datarepo mcp --catalog <path>` serves one catalog over stdio with three tools -- `describe`,
`search`, `sql` -- inside D14's measured sandbox, registered in both `E:/CodeReview/dataRepo` and
`E:/CodeReview/aging`. Reference: `docs/mcp.md`.

D15's bar was measured **twice** on 2026-09-22, by agents given the tools and denied the source:

| round | server | result |
|---|---|---|
| one | 0.10.0 | 5 answered, 5 correct 'no data', **7 near-misses**, 0 wrong |
| two | 0.11.0 | **0 wrong**, 9 answered, 9 correct 'no data' over 20 harder questions |

The guards work: the benchmark agent named `empty_tables` "the single most valuable thing in the
whole envelope" and the direct reason 9 of 20 were right. **But each round's red team broke the
previous round's fix**, and round two broke three of five claims -- two of them *through* fields
0.11.0 had added to prevent exactly that. 0.12.0's fixes are unverified. **Do not claim the bar on
a run we grade ourselves**; the one that counts is aging's (G35).

### The defect worth remembering, and the deletion that fixed it

`tables_touched` and a narrowed `provenance` were added so an answer could not be fabricated. A CTE
named after a real table -- `WITH protein_groups_1pct AS (SELECT 99999)` -- read **zero catalog
bytes** and came back stamped with that view's 8,055-row count and a real bundle id. The true
answer was 1,652. **Both verification fields vouched for the fabrication.**

The cause was a category error, not a coding one. *Which frozen data does this server hold?* is a
fact about the server that no question can change. *Which slice did this answer touch?* is a guess
read off the query's own output. The second was computed and labelled as the first.

0.12.0 **deletes** the narrowing. `catalog_id` is a hash of the exact (dataset, bundle) set, so
naming it already states which frozen copy of every dataset was available -- the whole citation in
one field, immune to the class. Provenance is now identical on every answer, inferred from nothing,
and says whether the catalog is a **release** (archived, cite this) or a **working build** (rebuilt
in place). The resolution came from the user's model of the domain, not from more engineering.

### Two ingest defects, found by agents pointed at the server, fixed and confirmed on real data

**The peptidoform count.** `producer_counts` applied aging's PSM notch clause to peptidoforms,
where MetaMorpheus does not -- a clause validated on the one dataset where it costs 0 and worth
exactly 3 on each of the others. PXD032202 carried a `count_mismatch` against a producer number it
matched perfectly. Confirmed gone on their re-ingest; PXD027318's now states the real 49,399 vs
49,394. DATAREPO-27 closed by aging 035: their own S22 had already bounded the clause to PSMs.

**Contaminant species.** All 339 contaminants read `NCBITaxon:9606` -- porcine trypsin, bovine
albumin at q = 0, E. coli lacZ. `Protein.organism` is now the taxon of the database an entry came
FROM (NULL for contaminants and decoys) and **`Protein.organism_name`** carries the producer's
species verbatim. The cause is the lesson: **`organism` was `required: true`, and a required column
with no true value gets a false one.**

**Open, and it is a communication defect rather than a code one:** aging's 035 reports this fix as
incomplete. It is not -- they queried `organism` and the species is in `organism_name`, which the
thread announcing the fix never named. Verified on their catalog: 433 of 442 contaminants carry a
name. Replying is the next action (G36).

## 2026-09-20: the site key, and the study layer

Two releases, both driven by aging's threads 019 and 020, and both measured on all three datasets.

**datarepo 0.5.0 - `ptm_site_id` keys on the engine's name, not the UNIMOD accession.** A key ending
in the accession cannot be formed for a modification that has none, so those sites were not written
as nulls - **they were not written at all**. Recovering them added **42 sites over 10 chemistries**
(195 PSMs), and only *one* of the ten had ever been reported: the other nine resolve to a *mass* but
not an accession, so they never entered the `unresolved_modifications` finding and vanished in
silence. PXD036557's bundle recorded `unresolved: {}` - a clean ingest - and was missing
`P16401:K37:N6-succinyllysine on K`, so **the released v0.1 catalog is missing a row and contains
nothing that says so**. The recovered list is succinyl-, glutaryl-, malonyl-, crotonyl- and
methacryl-lysine, nitrotyrosine and two hydroxylations: a lysine-acylation-shaped hole in an aging
repository. aging's 020 added the decisive case - `GG (Ubiquitination Site) on K`, the diGly remnant,
has no cross-reference in mzLib 1.0.591.

The cost is that the new key is **finer**: one chemistry can arrive under two names, and 5 sites in
35,615 split. That is recoverable and the deletion was not - `ptm_sites_by_chemistry` groups them
back and reproduces the accession-keyed table exactly on all 35,568 groups, zero mismatches. Store at
the grain measured, coarsen in a view.

**datarepo 0.6.0 - the study layer is real (G19).** `schema/study/aging.yaml` went from a stub to
eight tables, generated into `STUDY_TABLES` the same way the core's are and created by
`datarepo build`. `age_effects`, `age_effect_refusals` and `age_effect_meta` are transcribed
column-for-column from `aging:DEF-AGE-EFFECT v1`, with the definition's rules enforced by the shape:
`beta`, `se`, `age_span_years`, `covariates`, `normalization`, `method`, `method_version` are all NOT
NULL, and a refused fit has a table of its own so there is **nowhere to write a null beta**.

**Every study table is empty and will stay empty until aging answers DATAREPO-20(a).** That is the
deliverable, not a shortfall: their benchmark distinguishes `NO_TABLE` from `EMPTY_TABLE`, and the 46
age-effect questions scored the first. Section D's own query - do organelles age at different rates -
now parses, joins `protein_localizations` and returns nothing.

## 2026-09-21: the study tables can be filled

**datarepo 0.7.0 answers DATAREPO-20(a) with the default it recorded, and the default's virtue is
that it is cheap to be wrong about.** `datarepo study` reads a `study.yaml` -- one file per table,
`.tsv`/`.csv`/`.parquet`, columns named as the schema names them -- and writes a separately
content-addressed **study bundle** under `<store>/_study/<layer>/<id>/`. `datarepo build --study
aging=<id>` loads it beside the search bundles. End to end on the fixture dataset: two age effects
and two sample ages delivered, loaded, and queried back with their `study_bundle_id` attached.

**Writing one does not open a search bundle.** That is the whole reason the object is separate, it
is the first test in `tests/test_study_bundle.py`, and it is asserted byte for byte on the search
bundle's own `bundle.json`. `INGESTER_VERSION` stays 0.5.0 and no bundle id moved; `CATALOG_VERSION`
went 2 -> 3 because a catalog holding age effects and one without them answer 46 benchmark questions
differently and must not share an id. Third time the same sentence decided it -- *does this change
what the rows say* -- and the first time it was asked before rather than after.

**The rules in the definition are now write errors.** `bundle.table_from_rows` became a thin wrapper
over `rows_to_table`, so a delivery goes through exactly the core's coercion and its two refusals:
a `beta` with no `se` does not get written, a typo'd header stops the write instead of vanishing,
and a refused fit still has nowhere to put a null `beta` because it has a table of its own. Two rows
for one fit are refused on the keys declared in 0.6.0 -- which is the payoff for having declared
them while the tables were empty.

**What we deliberately did not check is the part worth remembering.** `feature_id` resolves against
nothing and `definition_id` is not checked against `definitions`. Both would have been easy, both
would have been guesses, and a foreign key is a guess with the authority of a constraint.
DATAREPO-20(c) is still the expensive open question and 023 says so in those words.

The file-level contract is ours and not aging's, and that is logged as **G30** rather than filed
under a closed 20(a). If stage 7 writes another shape, `study.read_table_file` changes and nothing
else does.

## 2026-09-21 (later): S39, and a commitment that had to be asked for twice

aging read 021, 022 and 023 all at once and replied with **024, 025 and 026**. Two of those changed
what shipped the same day.

**S39: 2,091 terminal PTM sites at q<=0.01 were never written, and nothing said so.** One `continue`
in `ptm_site_rows` skipped every modification placed at a peptide N-terminus, so `ptm_sites` held
**zero** rows for 3,085 peptidoforms and 18,566 PSMs that `peptidoforms` held in full. The 239
`UNIMOD:1` rows that *were* there are all `on K`, so a query for acetylation came back lysine-only
with nothing marking the absence. We had reported this as 13 sites; aging measured it and it was
thirty times larger. A projection gap, not a data-loss gap -- which is why it was a ruling and not
an incident.

Fixed in **0.8.0 / schema 0.0.5** with `site_type`, ruled by aging 024 §4. A column and not a
positional convention because **a protein N-terminal acetylation and an N6-acetyllysine on residue 1
are different chemistries at the same coordinate**. Their condition was that no existing id moves,
and it is met structurally -- the site type joins the key only when it is not `residue`. Verified by
diffing a re-ingest: **33 -> 36 sites, 0 ids lost, 0 carried-over rows changed any value.**

**The initiator methionine is the part worth remembering.** Co-translational N-terminal acetylation
follows Met excision, so the modified residue is **residue 2** and the previous residue is the
excised `M`. A rule of "peptide starts at residue 1" would have labelled the most abundant terminal
mark in the proteome `peptide_n_term`. Both fixture acetylations are of exactly that shape.

**And aging had to ask twice for something we had already agreed to.** Their 026: five
`ptm_stoichiometry` corrections accepted in our own thread 012, then missed by 0.5.0, 0.6.0 and
0.7.0. Their framing is the right one -- *a dropped commitment rather than a decision*. Worse, their
sharpest point was one we had not seen: 0.6.0 gave `age_effects` an `estimator` enum **because
count- and intensity-based occupancy differ threefold and must never be averaged**, while the core
table it draws from still had a single `modified_fraction` forcing exactly that average. The rule
was enforced one layer up and broken one layer down in the same week. All five are now in, corrected
while the table still held 0 rows, with four tests whose only job is to fail if the shape drifts
back. **The commitment now lives in the suite rather than in a thread**, which is the only place it
could have survived three releases.

Also in 0.8.0, both in aging's shapes rather than ours: `Dataset.permitted_responses` (an allow-list,
and in `CONTENT_FIELDS` -- two bundles over the same rows, one usable for site localization and one
not, are not the same object), and a study delivery declaring **its own** definition register, which
was their correction to a check we had offered against the wrong table.

## 2026-09-21 (later still): the declared/placed split, and shipping twice on purpose

aging's 027 answered all three questions our 025 and 027 asked, and one answer was actionable the
same hour. **0.9.0 shipped immediately after 0.8.0, deliberately**, because the rename it carries
moves the schema and nothing had re-ingested yet -- landing it now costs aging nothing and landing
it next week would have cost them a second pass over the whole corpus. That trade is the only
reason two releases went out in an hour, and 028 exists solely to say *re-ingest on 0.9.0*.

**G28 and G31 are closed. `search_modifications` is now `search_modifications_declared`**, and
`search_modifications_placed` derives from the **peptidoforms**, not from `ptm_sites`. We asked
rather than guessed, and aging's reason is better than the question: `ptm_sites` is per *resolved
protein position*, so a placed view built on it **would have reported that N-terminal acetylation
was never placed in any of the three datasets while 3,085 peptidoforms carried it.** S39 reproduced
in the one view whose entire job is to be trusted about absence. A view trusted about absence must
draw from the table that loses nothing -- that sentence is now in the code, not just here.

Grain is **accession-or-mass** and the two tables are **not comparable row for row**, stated in the
view's own description rather than left to be discovered: a ProForma tag carries an accession or a
mass, never an `IdWithMotif`. On the fixture: 4 declared, 5 placed, **2 placed that were never
declared** -- G28's whole point, now a query instead of a paragraph.

**DATAREPO-26 is answered and the answer is "not yet, and here is when".** aging measured three
ways: 0 C-terminal ProForma placements, 0 stored C-terminal sites, **0 C-terminal chemistries ever
declared to the engine**. The hole is *latent, not absent*, and it will be **worse than S39** --
S39 announced itself as `[mod]-PEPTIDE` and could be counted, whereas a C-terminal placement is
written identically to a last-residue one and gives no signal at all. Their safety net (raise a
`finding` when an ingest meets a declared C-terminal modification) is accepted and is **G33**, held
back because the `PP` lookup must come from mzLib's loader via pyMzLib: they tried three file-parsing
approaches and two were confidently wrong, one silently handing `Acetylation on K` the
protein-N-terminal rule of `Acetylation on X`. A safety net built on a 65% parse fails silently in
the other 35%, which is the failure it exists to prevent.

**And the hazard aging named applies to us.** They flagged themselves for moving a true sentence
into a context that falsifies it -- three times in one day. We did it in the same week: 022 §1
argued `age_effects.estimator` must exist *because the two occupancy estimators differ threefold and
must never be averaged*, while the core table it draws from still had one `modified_fraction`
forcing exactly that average. True where written, false one layer down, and it took their 026 to
see it. The practice that caught both was quoting a sentence back beside its own counter-example.

## 2026-09-21 (last): the corpus verdict, and a habit that cost aging two refusals

**S39 verified on real data, and it is bigger than either estimate.** aging re-ingested (their 028):
`ptm_sites` **35,615 -> 38,045**, **+2,430**, with `psms`, `peptidoforms`, `protein_groups` and
`quant_values` identical row-for-row -- which is exactly what an S39-only change must do, and is the
clause worth having asked for. Terminal sites at q<=0.01: **1,220 `protein_n_term` and 871
`peptide_n_term`**, 20,789 PSMs.

**The initiator-methionine refinement decides 79% of it: 958 of the 1,220 protein N-termini sit at
position 2.** That rule was added *against* aging's ruling on the strength of three fixture rows;
`N-acetylalanine on A` alone is 450 sites, `N-acetylserine on S` 187, against only 262 at position 1
where the initiator methionine is kept. A `start == 1` rule would have mislabelled 958 sites as
cleavage artefacts.

**aging retracted their own 1,367 rather than let us verify against it** (their 029). It counted
peptidoforms whose ProForma *begins* with a modification, so it conflated the two site types and
missed every first-residue placement written `C[UNIMOD:385]PEPTIDE` instead of as a prefix -- all 240
`Ammonia loss on C` sites. We had asked to be checked against that number and would have "passed"
while being wrong about which sites were which. **Every reference to 1,367 in this repo -- the schema
description, two code docstrings, `docs/ingest.md`, two changelog entries and this file -- is now the
corpus figure instead.** Prose only: `_tables.py` is byte-identical and the fixture bundle id is
`d13e382106002a1c` before and after, so nothing aging is about to ingest moved.

**The general form, now four instances between the two projects:** *a measurement is only true of the
grain it was taken at, and carrying it to a finer grain silently re-labels it.* 1,367 was true of
"peptidoforms with a leading mod tag" and false of "protein N-terminal sites".

**And a habit defect that is entirely ours.** aging refused to re-ingest **twice today** because the
release we announced existed only in our working tree -- 0.7.0 with an uncommitted `study.py`, then
0.9.0 with twelve uncommitted files. They were right both times: a bundle id hashed on an
`INGESTER_VERSION` and `SCHEMA_VERSION` that exist in no commit is reproducible by nobody, which is
the exact property `CONTENT_FIELDS` and the version split were built to protect. **They build from a
read-only clone at our committed `HEAD`, so our tip is the only thing they can see.** The rule --
*commit and push first, then announce, and quote the sha* -- is now a bullet in `CLAUDE.md`'s
bite-list, not a journal entry, because the journal is where the `__version__`-in-the-bundle-hash
lesson went to die three times.

## The ingester works

`datarepo ingest` turns one dataset's pipeline output into one immutable Parquet bundle. Run against
aging's real PXD036557: **16 tables, 4.1 MB, about ten seconds.** Reference: **`docs/ingest.md`**.

```
datarepo doctor                                        # can this machine ingest?
datarepo manifest E:/CodeReview/aging/instance/manifest.yaml
datarepo ingest   E:/CodeReview/aging/instance/manifest.yaml PXD036557 -v
```

- Reads aging's `instance/manifest.yaml` as the contract; refuses PXD048658 with aging's own reason.
- Every PSM carries a USI against the **deposited** file name, not the `-calib` copy the search reports.
- Peptidoforms are ProForma 2 with UNIMOD accessions, mapped from the searching MetaMorpheus build's
  own modification files. Anything unresolved becomes a finding, never a guess.
- Counts reconcile against aging's `results.txt`: peptides 5,541 ✓, protein groups 1,652 ✓, runs 18 ✓,
  MS2 266,402 ✓. PSMs come out 26,594 against 26,582 — 12 rows, carried as a `count_mismatch`
  finding and asked as DATAREPO-14.

**Environment:** pyMzLib is installed from `E:\GitClones\_wt_pymzlib_585` and ships no built bridge.
Set `PYMZLIB_BRIDGE` to `pkg/bridge/bin/Release/net10.0/win-x64/mzlib-bridge.exe` under that
worktree, or every `.psmtsv` read fails. `datarepo doctor` says so.

## The catalog works

`datarepo build` loads an instance's bundles into **one DuckDB file** that answers across datasets.
Reference: **`docs/build.md`**.

```
datarepo build   E:/CodeReview/aging/instance/manifest.yaml       # -> F:/aging_data/repo/catalog.duckdb
datarepo catalog F:/aging_data/repo/catalog.duckdb                # what went into it
datarepo query   F:/aging_data/repo/catalog.duckdb "SELECT * FROM dataset_overview"
```

- **The headline numbers are the bundle's numbers.** `psms_1pct`, `peptidoforms_1pct` and
  `protein_groups_1pct` are views applying MetaMorpheus's own acceptance rule, so the catalog reports
  **26,582 / 5,541 / 1,652** for PXD036557 — exactly what the bundle reconciled, and now exactly what
  aging's `results.txt` says. A test asserts the SQL and the ingester's Python agree, so the rule
  cannot drift into two answers.
- **Cross-dataset indexes are the point:** `protein_index`, `protein_datasets`, `peptide_index`,
  `dataset_overview`. `protein_index` carries `n_datasets` *and* `n_datasets_1pct`, because
  `proteins` is the search's protein list — decoys included — not its answer.
- **50 checks ran and passed:** every table's rows against its `bundle.json`, identifiers unique
  within a dataset, and every reference resolved, driven by `integrity.py`'s own lists.
- **A known mismatch would stay visible.** `catalog_bundles` flags any bundle whose own counts
  disagreed with its producer, so the catalog never looks cleaner than the data it was built from.
  PXD036557 was flagged that way until the notch clause closed it.
- Rebuilding from the same bundles is a no-op; a failed build leaves the previous catalog serving.

## The last count mismatch is closed, and the SDRF reader is gone

Two follow-ups landed in the same pass, both of them deletions of something we were carrying.

**The 12 PSMs.** aging's thread 008 named the missing clause of `DEF-PSM-1PCT v1`: a match whose
`Notch` cell holds several candidates separated by `|` never resolved, and the producer does not
count it even though both q-values pass. pyMzLib was already handing us that column — exactly 12 of
42,958 rows contain a `|` — we simply were not storing it. Now `Psm.notch` holds the text and
`Psm.notch_ambiguous` the conclusion, `producer_counts` and the catalog's `psms_1pct` view both
apply it, and **PXD036557 reconciles on all five checks**. The `count_mismatch` finding is gone.
Peptidoforms are untouched: no accepted peptide row is ambiguous, so 5,541 still holds.

```
$ datarepo ingest … PXD036557 -v
  ok  psms_target_1pct: 26582     ok  peptidoforms_target_1pct: 5541
  ok  protein_groups_1pct: 1652   ok  runs: 18     ok  ms2_spectra: 266402
```

**The SDRF reader.** `src/datarepo/readers.py` no longer parses SDRF; `pymzlib.sdrf.read` does. On
the real file the four SDRF-derived tables come out **byte-identical** to what the deleted code
produced. Characteristics are now copied by *position* rather than from a name-keyed map, because an
SDRF column name is a position — `comment[modification parameters]` appears twice in PXD036557's own
SDRF, and a map keeps only the last.

**What moved as a result.** datarepo **0.2.0**, schema **0.0.2**. PXD036557 is a new bundle,
`84ca279df425c0a2`; the old `6fea2187b2d9f737` is still on disk, still citable, and is refused by a
0.0.2 catalog with a message saying to re-ingest — which is right, because it cannot answer the notch
question. Nothing was written into aging's instance: **DATAREPO-16 asks them which bundle v0.1 pins,
and that is their call.**

One thing worth remembering: a bundle's content hash covers its inputs, the schema version and
`__version__` — *not* the reader code. Both of these changes would have produced the same bundle id
from different code if the version had not been bumped in the same commit.

## pyMzLib: the bridge problem was ours, not theirs

pyMzLib is **`mzlib` on PyPI** (it imports as `pymzlib`), and its wheels are per-platform with the
mzLib bridge inside — `pip install mzlib` and `PYMZLIB_BRIDGE` is never needed. This machine had an
*editable* install of the `_wt_pymzlib_585` worktree at **0.1.0.dev4**, which ships no bridge; that is
the whole of the "no built bridge here" warning. `pyproject.toml` also named a distribution
(`pymzlib`) that does not exist on PyPI. Both fixed. The full suite now runs the `.psmtsv` tests
instead of skipping them — **113 passed** — and CI installs `.[readers]` and runs ingest → build →
query end to end.

Re-tested against 0.1.1, the three gaps we reported in thread 007 resolve differently:

| Gap | At 0.1.1 |
|---|---|
| DATAREPO-13a, SDRF joined with `;` | **fixed** — `sdrf.read()` gives positional `columns` + `rows`; our in-house SDRF read is now **deleted** |
| DATAREPO-13b, FlashLFQ `MBR Score` | **still open** on MetaMorpheus 1.1.11 output |
| DATAREPO-12, `pro_forma` null | **still open** — the column is there, every value is `None` |
| matched-ion columns | **not a gap** — deliberately excluded, with the reason and a typed-view alternative in `excluded_fields` |

## v0.1 is RELEASED

`F:\aging_data\repo\releases\v0.1\` — catalog `08fb3a5e3078dce5`, pinned to bundle
`31fac552c5d748f0`, 50 checks passed, `id_rate` 0.0998, title filled, reconciliation green.

aging held it briefly over the `id_rate` number (their `provenance.json` used `DEF-PSM-FDRENGINE`
where the canonical `DEF-PSM-1PCT` was meant), fixed it, and re-cut. **They took the second fork of
DATAREPO-19**, so the release runs on datarepo **0.3.1** / schema **0.0.3** and carries the 1,997-row
`ptm_sites`. The earlier `84ca279df425c0a2` build is **superseded, not withdrawn** — both bundles stay
in the store and their `RELEASES.md` records what changed.

They fixed the id rate **without re-searching**, via a new `pipeline/bin/reprovenance.py`. The framing
is worth borrowing: a provenance record holds **history** (commands, tool versions, hashes, timings —
true forever) and **interpretations** (metrics computed under versioned definitions — these move).
Only the second kind goes stale, and only it is recomputed, through the same function the search stage
calls, with a `rederived` entry naming what changed from what to what.

## PTM sites: both filters were wrong, and the gap closed

aging 013 supplied QuantProject's actual `DEF-OCC-PSMS` text: the occupancy population is every PSM
passing the q-value threshold **at PSM level**, no ambiguity filter of any kind, on a protein group
whose definition **includes contaminants**. Both of our filters were wrong and between them they were
the whole gap.

```
                              before   after
ptm_sites rows                 1,370   1,997
occupancy sites uncovered        217      29     (93% of the gap)
  contaminant sites               —      113     (19 accessions, not just BSA + trypsin)
```

`PtmSite.best_ambiguity_level` and `PtmSite.target_decoy` keep the old derivation available as a
`WHERE` clause — which matters, because if QuantProject rules the other way the reversal is a query
rather than a re-ingest. `level = '1' AND target_decoy = 'target'` reproduces the old 1,370 ids
exactly, though 25 of them now carry a higher `n_psms`.

**Residual 29, and 13 have an exact cause:** they sit at position 0, `DEF-OCC-CELL`'s encoding of the
protein N-terminus, and all 13 are `N-acetylmethionine on M`. `ptm_site_rows` skips N-terminal
modifications entirely. DATAREPO-18 asks how to key one.

## The hash boundary, which has now failed three times in three directions

The most reusable thing this project has learned, and it took three failures in two days.

**Under-hashed (2026-09-19).** aging added `title:` to their manifest entry, we read it into the
`datasets` row, and the bundle id did not move - a bundle built from an edited manifest held
different content under the same id. Fixed by hashing the manifest **entry** as a declared input.
The manifest did not feel like an input because it is a contract.

**Over-hashed (2026-09-20, 0.5.0).** The fix hashed `entry.raw`, so `reason`, `notes` and `flags`
went into the id too. aging reworded a `reason` between their ingest and ours and got a different
bundle id from byte-identical search output - which destroys the one property they most want from an
id, that it means *these are the same measurements*. Fixed: `manifest.CONTENT_FIELDS` and
`NON_CONTENT_FIELDS` classify every field with its reason, and a test fails on a `DatasetEntry`
field in neither.

**Over-hashed again, one level up (2026-09-20, 0.6.0).** `__version__` was in the *bundle* hash, and
0.6.0 is entirely a `build` change - so releasing it would have re-identified every bundle in every
store for byte-identical rows. Fixed: `bundle.INGESTER_VERSION` is now the only version in a
bundle's hash, bumped with any change to what an ingest reads or writes, and it **lags
`__version__` on purpose**. `catalog_id` carries the package version, `CATALOG_VERSION` and every
study layer's version. Verified: adding the whole study layer moved every catalog id and **not one
bundle id**.

**The test is one sentence: *does this change what the rows say?*** It was available all three times
and nobody asked it. It is in `CLAUDE.md`'s bite-list now, which is the only place it can help.

## What the benchmark says

aging scored all 168 questions against the built catalog, 18 executed as SQL
(`results/BENCHMARK_v0.1.md` in their repo): **63 answerable**, 65 no-table, 25 empty-table, 10
no-metadata, 5 one-dataset. **`age_effect` alone blocks 46 and would unlock 42 by itself.** Section D
— whether organelles age at different rates, the proposal's own question — scores **1 of 19**.
Section B scores **0 of 11** because no table anywhere has an `age` column.

The line worth keeping: **no question failed because a table was shaped wrongly.** Every failure is
designed-but-unbuilt, built-but-unfilled, or metadata the deposit never carried. The schema is not
what needs revisiting.

The repository also produced its first real scientific answer: O1, progerin in PXD036557. Four
peptides, 18 PSMs, none spanning the 50-residue deletion — a qualified no with the evidence attached,
from a single query.

**Documents**
- **`design/OPEN_QUESTIONS.md`:** the list you take to NCEMS and working-group meetings. Each question has a default we build on until you bring an answer back.
- **`design/FRAMEWORK.md` (v0):** the architecture proposal (Parquet + DuckDB + REST/MCP over one code path, a LinkML schema, 8 MCP tools, roadmap).
- **`design/INPUT_INVENTORY.md`:** what aging writes on `F:\aging_data\`. The ingest spec starts here.
- **`design/threads/aging/`:** 001-014 set up scope, the benchmark, D8, the ingester, the catalog
  and v0.1. Since then: our **018** (AGING-Q2's duplicate collapse, per-run contamination, the grain
  rule), aging's **019** (PXD027318 ingested; the PSM gap has two mechanisms; `ptm_site_id` keys on
  UNIMOD and deletes sites; PXD060431 failed their acquisition gate) and their **020** (correcting
  the Unimod coverage figures and hardening the same ask), then our **021** (option (1) taken, the
  hole measured at 10 chemistries, the bundle-id question answered) and **022** (the study layer
  exists and is empty; DATAREPO-20's four shape questions).
  **The checker says AGING OWE, `next=023`.** They owe: DATAREPO-20 (how stage 7's rows arrive,
  `glycosite` vs `glycopeptide`, a feature's cross-dataset identity, whether `stratum` closes),
  G26's distribution question, the `search_modifications` meaning, how PXD060431's abundance-only
  restriction is enforced, and DATAREPO-18. **We owe nothing.** Re-check before writing anything -
  aging were working in parallel today and their 020 landed mid-session:
  `python "$env:USERPROFILE/.claude/skills/project/assets/threads.py" inbox`
  Confirm `next=` rather than assuming it; messages have crossed three times now.
- **`design/SCHEMA_COVERAGE.md`:** all 168 benchmark questions mapped onto schema v0: 70 answerable at ingest, 94 waiting on a producer, 2 with no home (J12, P2).
- **`design/SCHEMA_V0.md`:** what schema v0 contains and what's still open. The schema is in `schema/datarepo.yaml` (generic core, 27 tables) and `schema/study/aging.yaml` (the aging study layer, 8 tables, all empty). A study layer adds tables keyed on core identifiers and never alters a core table, so the core stays usable by a project that is not aging.
- **`docs/build.md`:** the catalog reference — choosing bundles, what the catalog holds, the acceptance views, the cross-dataset tables, the checks, and how to query it.
- **`docs/ingest.md`:** the ingester reference — the manifest contract, what it reads and who parses it, what it writes, the rules the writer enforces, reconciliation, USIs, ProForma, and the findings a bundle can carry.
- **Public repo docs:** `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `CITATION.cff`, `docs/architecture.md`, and `docs/schema/` (generated by `tools/build_docs.py`; never hand-edit). CI has two jobs: **schema** (lint, validate `examples/`, require `examples/invalid/` to fail, docs drift) and **ingester** (generated-tables drift, pytest with pyMzLib installed, a CLI smoke test, and a full ingest → build → query on the fixture instance).
- **`lit/`:** the research on platforms and proteomics resources.

**No server yet.** The code is the schema (YAML), the ingester and catalog builder (`src/datarepo/`), the generators (`tools/`) and the tests. The public GitHub repo is https://github.com/trishorts/dataRepo.
## Pick up at

**First, always:** run the thread checker (`CLAUDE.md`'s threads bullet). **aging accepted
DATAREPO-43 in 055** (their D45): aging operates the instance, engine runs included. DATAREPO-44
(the `run_enrichment` shape, 054) is still open.

### The next action

1. **Charter v0.3** (`design/CHARTER.md`): the RUN column and S1 become "the instance operator,
   today aging, via datarepo's runner". U11 closes. S17 loses "proposed", because aging owns the
   organelle map (their D46). Fold in aging's runner wish list from 055 §1: a bundle and a released
   engine version in, idempotent, output beside the bundle and never inside it. Then send **one**
   message each to go, logs, ptmQtl, sdrf and QuantProject covering v0.2 and v0.3 together, including
   GO-A3's held half (the operator picks the go.obo release) (G61).
2. **Tell pyMzLib, and logs for #1338, that the PRs merged** (G60). Retire
   `code/mzLib_prD_proforma` and `code/mzLib_prE_peaks` (`code/PINNED.md`).
3. **If 055 answers DATAREPO-44:** build **G63** (per-run enrichment) as specified there. It needs an
   `INGESTER_VERSION` bump, two schema regenerations, and aging told before it lands.
4. **Ask the user whether the `localization` project** joins the charter (G56). Do not write to it
   before they answer.

**In flight (re-check each):**
- **mzLib release** carrying #1338/#1345/#1346: `gh release list -R smith-chem-wisc/mzLib -L 2`
  (1.0.591 at close). Then pyMzLib: `pip index versions mzlib` (0.1.1 at close). **G52** (diff
  mzLib's ProForma against `proforma.py` on the corpus before switching) and logs' S9 both start
  there.
- **pyMzLib:** DATAREPO-40 (charter), -41 (`MBRScore` `double?` in the bridge), -42 (payload limit).
- **go:** the pre-release PXD036557 file for the reader (**G53**, which lists three schema fixes).
- **sdrf:** a reply to 010. **G62** (SDRF `source` column, data-file gate) builds from the first
  real SDRF that carries source columns.
- **ptmQtl, phred:** charter rows. **logs:** its S4 namespace, and LOGS-DR1 (our first run's diff).
- **PXD032044's first real ingest on 0.17.2** (G59).

**Standing:** G48 (explain `ERVK-6` for `P63135`; never back-fill `Protein.gene`), G42, G35 (do NOT
claim D15's bar), G32, G46, G33/G26/G36, G13. **N1/G9 goes to the next NCEMS meeting regardless.**
**`/project advance`**: the phase still says INCEPTION and the work is plainly BUILD. It is a gated
step, not a close-out edit.

**Do not trust a catalog number quoted anywhere in this file.** For a measurement, build a scratch
catalog from the store and name the PXDs. Name only PXDs that are in BOTH the manifest and the store
(the command below refuses on the first one that is not), and if the store's bundles are on an older
schema than the code, build with that release's code from a temporary worktree
(`git worktree add --detach <scratch>/wt <sha>`, then
`PYTHONPATH=<scratch>/wt/src python -m datarepo.cli build ...`):

```
datarepo build E:/CodeReview/aging/instance/manifest.yaml $(ls F:/aging_data/repo/store) --store F:/aging_data/repo/store --latest --out <scratch>/cat.duckdb
```

**After any schema edit:** `python tools/build_docs.py` **and** `python tools/build_tables.py`, or CI
fails on drift. If the ingester's output changes, also `python tools/build_example_bundle.py`.
