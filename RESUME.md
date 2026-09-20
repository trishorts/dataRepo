# RESUME

<!-- BEGIN GENERATED -- render_resume.py owns this block; edit state.yaml, not here -->

**dataRepo** &middot; phase **INCEPTION** (1/10) &middot; created 2026-09-19 &middot; rendered 2026-09-19

| | |
|---|---|
| Commits | 18 |
| Sync | [`trishorts/dataRepo`](https://github.com/trishorts/dataRepo) |
| Locked decisions | 10 |
| Open gaps | 11 |

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
  26,594 / 5,541 / 1,652 for PXD036557 — exactly what the bundle reconciled. A test asserts the SQL
  and the ingester's Python agree, so the rule cannot drift into two answers.
- **Cross-dataset indexes are the point:** `protein_index`, `protein_datasets`, `peptide_index`,
  `dataset_overview`. `protein_index` carries `n_datasets` *and* `n_datasets_1pct`, because
  `proteins` is the search's protein list — decoys included — not its answer.
- **50 checks ran and passed:** every table's rows against its `bundle.json`, identifiers unique
  within a dataset, and every reference resolved, driven by `integrity.py`'s own lists.
- **A known mismatch stays visible.** `catalog_bundles` flags PXD036557 for its 12-PSM difference, so
  the catalog never looks cleaner than the data it was built from.
- Rebuilding from the same bundles is a no-op; a failed build leaves the previous catalog serving.

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
| DATAREPO-13a, SDRF joined with `;` | **fixed** — `sdrf.read()` gives positional `columns` + `rows`; our in-house SDRF read is now deletable |
| DATAREPO-13b, FlashLFQ `MBR Score` | **still open** on MetaMorpheus 1.1.11 output |
| DATAREPO-12, `pro_forma` null | **still open** — the column is there, every value is `None` |
| matched-ion columns | **not a gap** — deliberately excluded, with the reason and a typed-view alternative in `excluded_fields` |

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

1. **Reply to the open threads.** aging is waiting on us (`next=010`): thread 008 answered
   DATAREPO-14 and 009 said `datarepo build` was the only blocker for their v0.1 — it exists now, so
   tell them, and say the catalog is what their release checklist step 3 asks for. Separately, tell
   pyMzLib the 0.1.1 re-test result: SDRF fixed, `MBR Score` and `pro_forma` still open.
2. **Delete the in-house SDRF reader** (G14). pyMzLib 0.1.1 parses the real PXD036557 SDRF correctly
   through `pymzlib.sdrf.read()`; keeping our own is exactly what the project forbids.
3. **Store notch ambiguity, then close the 12-PSM difference** (G7). aging's canonical
   `DEF-PSM-1PCT` excludes PSMs whose `Notch` cell contains `|`, and we do not record that at all.
   Add it in `sources/identifications.py` first, then `producer_counts`, then the catalog's
   `psms_1pct` view — in that order, so the bundle and the catalog never disagree.
4. **Pin the QPX version** (G13). Bundles and catalogs record `qpx_version: "unpinned"`. Pin a
   release of github.com/bigbio/qpx, map our column names onto its views, set `QPX_VERSION` in
   `src/datarepo/bundle.py` (D4), and only then add QPX-compatible views to the catalog.
5. **Re-map the benchmark** (`design/SCHEMA_COVERAGE.md`) against what the ingester actually fills —
   the 70 "answerable at ingest" questions can now be *run* against the catalog rather than asserted.
6. **`/grill-me` on FRAMEWORK steps 3-6** (G1) before building the client, MCP server or REST.
7. **When the user brings NCEMS answers** (N1-N9), record them as decisions.

**After any schema edit:** `python tools/build_docs.py` **and** `python tools/build_tables.py`, or CI
fails on drift. If the ingester's output changes, also `python tools/build_example_bundle.py`.
