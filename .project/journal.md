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

Later that session: I mapped all 168 benchmark questions onto the schema (design/SCHEMA_COVERAGE.md). 70 are answerable at ingest, 94 wait on a producer (mostly stage 7, go, MetaMorpheus R7/R16, and aging's census and panels), 2 have no home (J12 literature claims, P2 mass-shift histogram) and 2 are out of v1. The mapping forced real fixes. Top-10 questions K1 and O1 would have failed without AgeEffect.response (abundance vs modified fraction) and Protein.source_db (custom entries such as progerin). It also added a long Metric table (so S21's two PSM counts can coexist), SearchModification, run date and instrument, donor ID, and material type. Thread 004 to aging is drafted as the coverage doc's last section and not yet posted.

Later still: the user created the public GitHub repo (G8 closed) and then set D8: dataRepo is code only, and aging hosts the data instance (bundles, releases, DOIs, the deployed service). U6 asks how much of running the service aging takes on. The user then asked for gold-standard repo docs. I added a README (code-vs-data split, schema at a glance, quick start, ownership, roadmap, ID glossary), LICENSE (MIT), CITATION.cff (U3 placeholder credit), CONTRIBUTING, CHANGELOG, docs/architecture.md (decided vs proposed), a generated schema reference (tools/build_docs.py → docs/schema/), examples with a must-fail case, and CI (lint, generators, validation, negative test, docs drift). Every schema element now has a description. The negative test exposed missing 0–1 bounds on the probability columns, which are fixed now.

Close-out (same day): thread 005 went to aging with D8 (DATAREPO-9 accept the instance role; DATAREPO-10 = U6, does aging also run the service). It is committed and pushed in both repos. The user accepted the placeholder credit line, which closes U3. GitHub CI passed on its first run. During close-out I found that the D8 edit had merged `gaps:` onto the line of the first gap, which made state.yaml invalid YAML. RESUME rendering didn't fail; it silently counted 0 gaps. That was fixed and parsing verified. Lesson: after any hand edit to state.yaml, parse it.

## 2026-09-19 - Fourth session: the ingester is built and has run on real data

aging replied (thread 006) and said yes to everything in 005: they populate and host the instance,
including the running service (their D18). The instance exists now — `aging/instance/manifest.yaml`
with `F:\aging_data\repo\` underneath — and our ingester's input is that manifest, not a folder scan.
S21 closed with two definitions (DEF-PSM-1PCT canonical, DEF-PSM-FDRENGINE the engine's log line,
which is what provenance /2 stores under the misleading name `psms_1pct`). They asked for an ETA on
step 1. The user asked for the ingester so aging could start using it, so that was the session.

`datarepo ingest` is written, tested and run against PXD036557: 16 Parquet tables, 4.1 MB, about ten
seconds. `src/datarepo/` is the package; `docs/ingest.md` is the reference; D9 records the contract.

**What the build actually settled.** The manifest gate works as aging intended — PXD048658 is refused
with their own reason printed. Bundle directories are a content hash of (inputs, schema version,
ingester version), so re-ingest is a no-op and a changed input can never overwrite a cited bundle.
The Parquet column list is generated from the LinkML schema (`tools/build_tables.py`, CI drift check),
so there is no second list to drift. Definition IDs needed namespacing, because QuantProject's
`DEF-QC-9` and aging's `DEF-CONTAM-PSM` are both "contaminant share": bundles write `<owner>:<ID>`,
and numbers nobody has defined get `PROVISIONAL:<NAME>` whose own text says so (U7, G15).

**Reconciliation was worth building first.** It caught three real bugs that would have shipped a
plausible-looking bundle. A zero-is-missing helper was being used for q-values as well as
intensities, so every protein group with q=0 lost its q — the protein-group count came out 1,195
against 1,652. Peptidoform counts included decoys. And `peptidoform.protein_group_id` was being
synthesized from the peptide's accessions rather than looked up in the producer's parsimony result,
which dangled for 2,925 of 12,653 rows. The referential-integrity check, added after that, then
caught a fourth: protein groups can name accessions that never appear in the PSM table at all.

The counting predicate is MetaMorpheus's own: target, and **both** `QValue` and `QValueNotch` at or
below 1%. That reproduces aging's peptide (5,541) and protein-group (1,652) totals exactly — and the
protein-group headline turns out to include contaminants while the PSM headline does not. PSMs come
out 12 too many (26,594 vs 26,582, 0.05%); nothing tried explains the 12, so it went to aging as
DATAREPO-14 and is carried as a `count_mismatch` finding. Also noticed: aging's own per-file PSM
lines sum to 26,746, not to their 26,582 total.

**pyMzLib did the hard part and has three gaps.** 42,958 typed `.psmtsv` records in under three
seconds. But `pro_forma` is null, so `src/datarepo/proforma.py` translates MetaMorpheus notation
itself, reading the UNIMOD mapping out of the searching build's own `Mods/*.txt` and
`Data/ptmlist.txt` rather than inventing it — that file is a stop-gap to delete (DATAREPO-12). The
FlashLFQ peak reader fails on MetaMorpheus 1.1.11 output (`Header with name 'MBR Score' was not
found`), and the SDRF projection joins header and cells with `;`, which SDRF values contain, so
columns cannot be recovered (DATAREPO-13). Every in-house read is recorded with its reason in the
bundle's reader log, so the code is deletable rather than permanent.

**Schema changes, all additive:** `Psm.q_value_notch`, `Peptidoform.best_q_value_notch`,
`Peptidoform.target_decoy`, `ProteinGroup.target_decoy` (without the last two a caller cannot exclude
decoys from those tables at all), and `SearchModification.modification` is no longer required, since
metal adducts have no UNIMOD accession.

CI gained an `ingester` job: the generated-tables drift check, pytest (the `.psmtsv` tests skip
without a built mzLib bridge, which CI has no way to build), and a CLI smoke test. Real ingester
output is checked in as `examples/ingested_bundle.yaml` and validated by `linkml-validate`, which is
what proves the writer emits rows the published schema accepts, not merely columns it recognizes.

Thread 007 went to aging with all of it, including the ETA they asked for: step 1 is available now.

One environment note for next time: pyMzLib is installed from the worktree at
`E:\GitClones\_wt_pymzlib_585` and ships no built bridge, so `PYMZLIB_BRIDGE` has to point at
`pkg\bridge\bin\Release\net10.0\win-x64\mzlib-bridge.exe` or every `.psmtsv` read fails.
`datarepo doctor` reports this.

## 2026-09-19 - Fifth session: the catalog is built, and the bridge problem was ours

`datarepo build` exists and has run on the real store: PXD036557's bundle into one DuckDB file, 50
checks, all passed. Contract locked as **D10**. Reference: `docs/build.md`.

**The design question that mattered was what the catalog is *for*.** A bundle already answers
"what is in this dataset", and materialising it into DuckDB would add nothing. What only the catalog
can do is answer across datasets, so the derived tables are the deliverable, not a side effect:
`protein_index`, `protein_datasets`, `peptide_index`, `dataset_overview`. Two consequences fell out
of writing them. Every table needed `dataset_id` and `bundle_id` prepended, taken from the bundle
rather than the row, because `proteins` and `definitions` have no dataset of their own and without
one the same UniProt accession from two datasets is indistinguishable. And `protein_index` needed
**two** counts: `proteins` is the search's protein list, decoys and sub-threshold matches included,
not its answer, so `n_datasets` and `n_datasets_1pct` are both there with names that say which is
which. 3,670 of PXD036557's 5,500 protein rows have no accepted evidence behind them.

**The acceptance rule is the thing that would have drifted.** The first `dataset_overview` counted
`target_decoy = 'target'` and reported 10,729 peptidoforms where the bundle had reconciled 5,541.
A catalog whose front page disagrees with the bundle it was built from is worse than no front page.
So the rule is applied once, as the views `psms_1pct` / `peptidoforms_1pct` / `protein_groups_1pct`,
and everything counts through them — 26,594 / 5,541 / 1,652, exactly the bundle's numbers. It is
MetaMorpheus's rule and it is not guessable: target, **both** q-values at or below 1%, except for
protein groups where anything not a decoy counts, contaminants included. There are now two
implementations of it, Python in the ingester and SQL in the catalog, so a test asserts they agree.

**Checks are re-run rather than trusted.** Row counts against each `bundle.json` catch the one thing
a content hash cannot — Parquet truncated or edited after the manifest was written. Uniqueness and
references are re-checked from `integrity.py`'s own lists, so there is one statement of what points
at what. A failure stops the build: a Finding is for something true about the dataset, and this
would be something false about the catalog. The build stages to a temporary file beside the target,
so a failed rebuild leaves the previous catalog serving.

**The user was right about pyMzLib, and it was a bigger correction than it looked.** The standing
warning was that "pyMzLib ships no built bridge here". It does. The distribution is **`mzlib`** on
PyPI, imports as `pymzlib`, and its wheels are per-platform with the bridge inside. This machine had
an *editable* install of the `_wt_pymzlib_585` worktree at 0.1.0.dev4, which is a source checkout and
ships no bridge — that was the whole of it. `pyproject.toml` named `pymzlib`, a distribution that
does not exist on PyPI, so the optional dependency could never have resolved. Both fixed. The full
suite now runs the `.psmtsv` tests instead of skipping: **113 passed**, and CI installs `.[readers]`
and runs ingest → build → query end to end on the fixture instance.

Re-testing thread 007's reader gaps against 0.1.1 changed two of the four answers. **SDRF is fixed
upstream** — `pymzlib.sdrf.read()` returns positional `columns` + `rows` and parses the real
PXD036557 file, 19 columns by 18 rows — so our in-house SDRF read is deletable, which is the next
thing to do. `pro_forma` is still null on every `.psmtsv` record and `AllQuantifiedPeaks.tsv` still
fails on the missing `MBR Score` header, so DATAREPO-12 and 13b stand. The matched-ion columns turn
out not to be a gap at all: they are deliberately excluded, listed in `NativeRecords.excluded_fields`
with the reason and a typed-view alternative.

**aging answered DATAREPO-14 and we have not acted on it yet.** The 12 extra PSMs are exactly the
rows whose `Notch` cell contains a `|`. We do not store notch ambiguity at all — `q_value_notch` and
`ambiguity_level` are both something else — so neither the bundle nor the catalog can apply the
refined predicate, and both still report 26,594 with a `count_mismatch` finding. The column goes in
the ingester first, then `producer_counts`, then the catalog view, in that order, so the two never
disagree.
