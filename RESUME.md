# RESUME

<!-- BEGIN GENERATED -- render_resume.py owns this block; edit state.yaml, not here -->

**dataRepo** &middot; phase **INCEPTION** (1/10) &middot; created 2026-09-19 &middot; rendered 2026-09-19

| | |
|---|---|
| Commits | 31 |
| Sync | [`trishorts/dataRepo`](https://github.com/trishorts/dataRepo) |
| Locked decisions | 11 |
| Open gaps | 17 |

<!-- END GENERATED -->


## Goal

Build an AI-ready, API-accessible repository for the results of the `aging` pipeline's PRIDE
reanalyses. The results cover search, quant, provenance, design and organelle annotation. Humans can
use it, but AI agents are the main users. The question it serves is how organelle proteomes change
with age.

## Where it stands (2026-09-19, fifth session)

The framework's section 7 decisions are **locked** (grill-me). Everything else in `design/FRAMEWORK.md` v0 is still a proposal.

**Locked:** D1 hosting (prototype local; NCEMS runs production) · D2 public from day one, no login · D3 CC BY 4.0 data, MIT code · D4 QPX-compatible superset · D5 human and rodent, DDA and DIA, LFQ and TMT (the table shape now, the ingesters when aging produces the data) · D6 aging owns the benchmark questions; dataRepo stays generic · D7 every open question goes in `design/OPEN_QUESTIONS.md` · **D8 this repo is code only; aging hosts the data instance** (bundles, releases, DOIs, the deployed service) · **D9 the ingest contract** (manifest-driven, content-addressed bundles, schema-generated columns, pyMzLib for producer formats, mandatory reconciliation and integrity checks) · **D10 the catalog contract** (manifest-driven again, derived and content-addressed, materialised tables, the producer's acceptance rule applied once as views, checks re-run before anything is served).

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

## Where v0.1 stands: built, pinned, and HELD by aging

`F:\aging_data\repo\releases\v0.1\catalog.duckdb` — catalog `d8b3e1cd055c56a9`, pinned to bundle
`84ca279df425c0a2`, 50 checks green, `dataset_overview` reading 26,582 / 5,541 / 1,652. aging froze
their `manifest.yaml` beside it and filled `instance/RELEASES.md`.

**They then held it from citation, and they were right to.** The bundle's `id_rate` metric and
`low_id_rate` finding report 10.5% — `DEF-PSM-FDRENGINE` as the numerator instead of the canonical
`DEF-PSM-1PCT`, which gives 9.98%. It is their number out of their `provenance.json` and their fix.

**Do not re-ingest their store until DATAREPO-19 is answered.** Their corrected provenance moves the
bundle hash anyway, so the open question is which ingester writes the replacement: pin 0.2.0 / schema
0.0.2 and keep v0.1 exactly as scoped, or take 0.3.1 / 0.0.3 with the 1,997-row `ptm_sites`. We
recommended the second **conditional on QuantProject confirming** the no-ambiguity-filter reading,
because aging flagged that reading as theirs rather than QuantProject's ruling.

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

## A content-hash defect that was live all day

aging added `title:` to their manifest entry, we read it into the `datasets` row, and **the bundle id
did not move**. The manifest entry supplies the title and all five D5 axes; we hashed only the
producer's files. A bundle built from an edited manifest held different content under the same id —
the exact failure content addressing exists to prevent, on the artifact a release pins.

Fixed: the manifest **entry** is hashed as a declared input (`BundleWriter.add_declaration`), the
entry rather than the file so an unrelated dataset's edit cannot churn this bundle. The lesson is
narrower than "hash more things" — the manifest did not feel like an input because it is a contract.
**Anything that reaches a written row is an input.**

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
- **`design/threads/aging/`:** 001 (scope, provenance axes, count mismatches), 002 (the benchmark seed), aging's 003 (QUESTIONS.md v0.3; tables routed to us), our 004 (the benchmark scored against schema v0; DATAREPO-5..8) and 005 (D8; DATAREPO-9/10), aging's **006** (yes to everything: they populate and host the instance including the service; S21 closed; the manifest is our input) and our **007** (the ingester works; DATAREPO-11..14).
- **`design/SCHEMA_COVERAGE.md`:** all 168 benchmark questions mapped onto schema v0: 70 answerable at ingest, 94 waiting on a producer, 2 with no home (J12, P2).
- **`design/SCHEMA_V0.md`:** what schema v0 contains and what's still open. The schema is in `schema/datarepo.yaml` (generic core) and `schema/study/aging.yaml` (a stub for aging to own).
- **`docs/build.md`:** the catalog reference — choosing bundles, what the catalog holds, the acceptance views, the cross-dataset tables, the checks, and how to query it.
- **`docs/ingest.md`:** the ingester reference — the manifest contract, what it reads and who parses it, what it writes, the rules the writer enforces, reconciliation, USIs, ProForma, and the findings a bundle can carry.
- **Public repo docs:** `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `CITATION.cff`, `docs/architecture.md`, and `docs/schema/` (generated by `tools/build_docs.py`; never hand-edit). CI has two jobs: **schema** (lint, validate `examples/`, require `examples/invalid/` to fail, docs drift) and **ingester** (generated-tables drift, pytest with pyMzLib installed, a CLI smoke test, and a full ingest → build → query on the fixture instance).
- **`lit/`:** the research on platforms and proteomics resources.

**No server yet.** The code is the schema (YAML), the ingester and catalog builder (`src/datarepo/`), the generators (`tools/`) and the tests. The public GitHub repo is https://github.com/trishorts/dataRepo.

## Pick up at

1. **Swap the five definition IDs** (G20). `MS2-COUNT`, `PEPTIDE-COUNT-1PCT`, `PRECURSOR-COUNT`,
   `PROTEIN-GROUP-COUNT-1PCT` and `RUN-MINUTES` have real `aging:DEF-*` IDs under aging's D20; edit
   `src/datarepo/definitions.py`. `PROTEIN-INTENSITY` and `PROTEIN-SPECTRAL-COUNT` stay
   `PROVISIONAL:` — QuantProject has not ruled. Mechanical, needs no reply, do it first.
2. **Instantiate the study layer** (G19). `SampleAge`, `ClockModel`, `ClockFeature` and `AgeMapping`
   from `schema/study/aging.yaml`, plus the `age_effect` table **shape**. Do **not** write the
   definition of an age effect — model, covariates, normalization is aging's G6, and a shape built
   around a guess at it is worse than no table. This is the largest lever in the project: 46 of 168
   benchmark questions.
3. **Wait on aging for DATAREPO-19 before touching their store** (G21) — which ingester re-cuts
   v0.1. `F:/aging_data/repo/store/PXD036557/84ca279df425c0a2` is what v0.1 pins and what they
   verified. Re-check with
   `powershell -NoProfile -File E:\CodeReview\aging\design\threads\check_threads.ps1`.
4. **DATAREPO-18** (G16): how a protein-terminal modification is keyed. Default is `position = 0`,
   `residue = 'N-term'`. It is a join key, so do not implement it ahead of their answer unless they
   go quiet.
5. **G17 / G18** — the `ptm_stoichiometry` corrections and the `ptm_sites` hygiene items. Still free
   while both tables are 0 rows. The count/intensity split is the one that must not be got wrong:
   the two estimators differ 3x overall and 7x at 21-50 PSM sites, and must never be averaged.
6. **Pin the QPX version** (G13), then re-map `design/SCHEMA_COVERAGE.md`.
7. **`/project advance`** — the phase field still says INCEPTION and the work is plainly BUILD. It
   was left alone deliberately; advancing is a gated step, not a close-out edit.

**After any schema edit:** `python tools/build_docs.py` **and** `python tools/build_tables.py`, or CI
fails on drift. If the ingester's output changes, also `python tools/build_example_bundle.py`.
