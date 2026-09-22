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

## 2026-09-19 - Fifth session, continued: two things we were carrying, both deleted

**The 12 PSMs are gone, and the answer was already in the file.** aging 008 named the missing clause
of `DEF-PSM-1PCT v1`: a match whose `Notch` cell holds several candidates separated by `|` never
resolved, and the producer does not count it even though both q-values pass. The thing worth
recording is that pyMzLib had been handing us that column all along — `notch`, right next to
`q_value_notch`, with exactly 12 of 42,958 rows containing a `|`. We had written `ambiguity_level`
and `q_value_notch` into the schema and assumed between them they covered it. They do not:
`ambiguity_level` is MetaMorpheus's 1/2A/2D/3/4/5 and `q_value_notch` is a q-value. Checking the
reader's actual columns before declaring something unrepresentable would have found it in a minute.

`Psm.notch` now holds the cell verbatim and `Psm.notch_ambiguous` the conclusion. Storing both was
the right call and not only because the thread's default said so: the first implementation passed the
raw cell through `_first()`, which splits on `|` and takes the first candidate, so the flag came out
correct while the evidence behind it read `0.00000` — a column that asserts an exclusion without
showing why. `_verbatim()` fixed it, and the rows now read `0.00000|1.00290`: the search could not
decide between notch 0 and a +1.003 Da offset.

The clause applies to peptidoforms too and costs nothing there — no accepted peptide row is
ambiguous — so `producer_counts` applies it unconditionally and both counts reconcile. **All five
checks pass on PXD036557 for the first time.**

**The SDRF reader is deleted.** `pymzlib.sdrf.read` produces the four SDRF-derived tables
byte-identical to what our in-house TSV read produced on the real file. Reading pyMzLib's own
caveats while swapping it found a latent bug in our code: an SDRF column name is a *position*, not a
key, and `comment[modification parameters]` appears twice in PXD036557's own SDRF. We were building a
name-keyed dict per row, so a repeated `characteristics[...]` column would have been silently
overwritten. Characteristics are now copied by walking the pairs. Nothing in PXD036557 was lost,
because the repeat happened to be a `comment[...]` column we skip — a near miss, not a save.

**Versions moved and that mattered.** datarepo 0.1.0 → 0.2.0, schema 0.0.1 → 0.0.2. Both changes
altered how a file is parsed without altering the file, and a bundle's content hash covers inputs,
schema version and `__version__` but *not* the reader code — so without the bump, both would have
produced the same bundle id from different code. That is now written into CLAUDE.md as a hazard.
PXD036557 is a new bundle, `84ca279df425c0a2`; the old one stays on disk, stays citable, and a 0.0.2
catalog refuses it with a message saying to re-ingest, which is right: it cannot answer the notch
question.

**Nothing was written into aging's instance.** Their store still holds the 0.0.1 bundle and the
catalog built from it. Thread 010 asks them which bundle v0.1 pins (DATAREPO-16), and replacing what
their release candidate points at while that question is open would be answering it for them.

Also: `linkml` is now installed in the working environment, so `tools/build_docs.py --check` and the
example-bundle validation run locally instead of only on CI. 122 tests pass.

## 2026-09-19 - aging 011 answered both questions, and v0.1 is pinned

Thread 011 arrived while the notch work was in flight and confirmed both defaults, so nothing built
on them had to be undone. Three refinements came with it, all now implemented.

**`aging DEF-PSM-NOTCH-AMBIGUOUS v1` exists.** aging published the definition rather than leaving the
boolean as a habit, and the mechanism is worth knowing: `ResolveAllAmbiguities` leaves the in-memory
`QValueNotch` unresolved at > 1 while `PsmTsvWriter` writes the **minimum** across hypotheses, so the
written `QValue Notch` can pass a threshold the counted one fails. That is why the file alone cannot
give you the count. `aging:DEF-PSM-1PCT` now carries all four conditions in its own text, and the
notch definition travels in every bundle that has PSMs -- a stored conclusion has to carry the text
behind it, not point at a thread.

**`Psm.notch` stays a string, `'0'` and not NULL**, which was their one request on it. Already true:
41,269 rows read `0` and none are null. A nullable column would have made "no notch" and "notch 0"
the same thing, and notch 0 is the commonest value in the file.

**Releases now enforce pinning rather than defaulting to it**, which they asked for explicitly:
`--release` refuses `--latest` outright and requires a `--bundle` pin per dataset. The reason it is
worth a guard is that the failure is invisible -- a release that quietly picks up a later re-ingest
still builds cleanly and still answers questions, just not the ones that were cited. D11.

**v0.1 is built.** They chose "fix the notch, re-ingest, pin the new hash" over cutting on the old
bundle, on the grounds that the first release sets the precedent and they would rather demonstrate
that a finding can be *closed* than carried. So: re-ingested into their store (20 s, all five checks
green), and `releases/v0.1/catalog.duckdb` is pinned to `84ca279df425c0a2`. The working catalog at
`repo/catalog.duckdb` was rebuilt onto the same bundle. Both bundles remain in the store; the 0.0.1
one is still citable and a 0.0.2 catalog refuses it by design.

`Dataset.title` can now come from the manifest (`title:` on a dataset entry). aging offered to supply
it from PRIDE's `GetProjectAsync` and asked where it should live; the manifest is the answer, because
dataRepo does not call PRIDE. Their manifest has no `title:` yet, so it is still null -- theirs to add.

**Queued from 011, none of it release-blocking** (both tables are 0 rows, which is why it arrives
cheaply): five `ptm_stoichiometry` column corrections from QuantProject, including splitting
`modified_fraction` into count- and intensity-based columns that must never be averaged (they differ
by 3-7x), adding `intensity_is_floor`, and dropping `uncertainty`; `proteoform_inferences.
inference_confidence` becoming an enum of evidence classes or being dropped; and four findings about
`ptm_sites` -- 81% of it is carbamidomethyl, which `DEF-OCC-PSMS` excludes from occupancy by
construction, and the occupancy site population overlaps ours by only 212 of 433, most likely because
the occupancy writer emits one entry per protein in an ambiguous group while we key on the leading
one. That last one decides whether R7 can key to `ptm_sites` at all, so it is the first to look at.

## 2026-09-19 - §4.2 investigated: aging's diagnosis was wrong, and a latent bug was hiding behind it

aging asked us to check whether the 221 occupancy sites missing from `ptm_sites` are an
ambiguous-protein-group problem, because it decides whether R7 can key to `ptm_sites` at all. It is
not. Measuring which accepted PSMs actually cover each missing residue:

- **0** of 217 are covered by an accepted level-1 PSM;
- **181** (83%) exist only in accepted PSMs at ambiguity level >= 2;
- **36** are covered by no accepted PSM at all.

The cause is a rule of ours that had never been stated outside the code: `ptm_site_rows` emits a
site only from a level-1 PSM, on the reasoning that anything else is "a site the evidence does not
place". On the 18-file run that keeps 22,730 accepted PSMs and drops 4,027, of which level 2D alone
is 3,651. So R7 *can* key to `ptm_sites`, but only once `ptm_sites` stops being level-1-only —
keying to it today would silently drop 83% of the sites occupancy can be computed for.

**The methodological lesson.** aging's hypothesis was plausible, specific, and came with a number
(46 accessions) that looked like support. Taking it at face value and "fixing" the protein-group
keying would have produced a change that measured as an improvement on that number and left the real
cause untouched. Asking the more basic question — which PSMs actually cover this residue — took one
query and inverted the answer.

**A latent bug surfaced on the way, and the two compound.** A peptide shared between proteins starts
at a different residue in each; MetaMorpheus writes one span per protein, `|`-separated and aligned
with the accession column. `ptm_site_rows` took the *first* span and applied it to every accession —
right for the leading protein, wrong for the rest. PXD036557 has 3,154 accepted PSMs with differing
spans and **none at level 1**, so only the filter we are about to relax has kept it from firing.
Fixed by pairing each accession with its own span; verified byte-identical on real data (1,370 rows
in, 1,370 identical out), so aging's v0.1 pin is unaffected. Patch bump to 0.2.1 because the hash
covers `__version__` and not the reader code.

Thread 012 carries all of it, plus DATAREPO-17: which PSM population `DEF-OCC-PSMS` counts over, and
a worked example of one of the 36. Our default if they do not answer is to emit a site from any
accepted PSM whose modification position is determinate and add a column recording the best
ambiguity level that placed it, so today's table stays reproducible as a filter.

## 2026-09-19 - DATAREPO-17 answered, and both of our ptm_sites filters were wrong

aging 013 came back with QuantProject's actual `DEF-OCC-PSMS` text rather than a paraphrase, and it
settled the question in one sentence: the occupancy population is every PSM passing the q-value
threshold **at PSM level**, with no ambiguity-level filter of any kind, on a protein group whose
definition includes contaminants. So `ptm_site_rows` had two filters and both were wrong, and
between them they were the whole of the gap.

Removing them: **1,370 -> 1,997 sites, and uncovered occupancy sites 217 -> 29.** 93% of the gap,
from deleting two conditions. 113 of the new rows are contaminant sites, all BSA and trypsin — the
half of the answer we would never have guessed, because a contaminant group has occupancy and by
construction no "target" PSM.

**Neither filter was replaced with nothing.** `best_ambiguity_level` and `target_decoy` make the old
derivation a `WHERE` clause instead of a lost option, which matters because aging flagged that the
no-level-filter reading is *their* interpretation of QuantProject's text and not QuantProject's
ruling. If it reverses, the reversal is a query.

**One honesty correction I had to make to myself mid-flight.** I told aging the relaxation would
"reproduce today's table exactly". The site *set* does — 1,370 ids, verified identical — but 25 of
those rows now carry a higher `n_psms`, because `n_psms` aggregates every accepted PSM that placed
the site rather than only the level-1 target ones. That is the right measure (it is what the
occupancy denominator is built from), but "exactly" was wrong and the schema now spells out which
reading applies rather than leaving "number of PSMs supporting this row" ambiguous.

**The residual is 29 and 13 of them have a clean cause:** they sit at **position 0**, which is
`DEF-OCC-CELL`'s encoding of the protein N-terminus, and `ptm_site_rows` skips N-terminal
modifications entirely. Representing them means deciding how a terminal modification is keyed —
`residue` is currently a one-letter code. The other 16 are scattered internal positions and have no
explanation yet.

**What aging's benchmark says, and what it does not.** 63 of 168 answerable; `age_effect` alone
blocks 46 and would unlock 42 by itself; section D — the proposal's own question, whether organelles
age at different rates — scores 1 of 19. Section B scores 0 of 11 because there is no `age` column
anywhere. But the line worth keeping is theirs: **no question failed because a table was shaped
wrongly.** Every failure is designed-but-unbuilt, built-but-unfilled, or metadata the deposit never
carried. The schema is not what needs revisiting.

Two questions from them are unanswered and are the next thing to send: whether the study layer is
what we instantiate next (our view: yes, and it is one piece of work with section B, not two), and
whether contaminant sites stay — already implemented their way, kept and marked.

## 2026-09-19 - Session close: v0.1 is held by its producer, and a hash defect that was live all day

The last stretch of the session, after the `ptm_sites` relaxation.

**aging held v0.1 from citation, and they were right.** Their own check found the bundle's `id_rate`
metric and `low_id_rate` finding reporting 10.5% — `DEF-PSM-FDRENGINE` as the numerator instead of
the canonical `DEF-PSM-1PCT`, which gives 9.98%. It is their number, out of their `provenance.json`,
and they chose to hold rather than release a headline quality figure a reader will not re-derive.
That is the right instinct and it is worth remembering as the precedent for later releases.

**The hold turns into a fork that is genuinely theirs.** Their corrected provenance moves the bundle
hash anyway, so the only real question is which ingester writes the replacement: pin 0.2.0 and keep
v0.1 exactly as scoped and verified, or take 0.3.1 and get the 1,997-row `ptm_sites` for free. We
recommended the second **conditional on QuantProject confirming the no-ambiguity-filter reading**,
because aging themselves flagged that reading as their interpretation of QuantProject's text rather
than QuantProject's ruling. Recommending it unconditionally would have been recommending they build
a release on our joint guess. DATAREPO-19.

**A content-hash defect was live the entire time v0.1 was being built, and an unrelated change found
it.** aging added `title:` to their manifest entry (answering our §4.5 ask), we read it into the
`datasets` row — and the bundle id did not move. The manifest entry supplies the title and all five
D5 axes, and we were hashing only the producer's files. So a bundle built from an edited manifest
held different content under the same id, which is precisely the failure content addressing exists
to prevent, on the artifact a release pins.

Fixed by hashing the manifest **entry** as a declared input — the entry rather than the file, so an
unrelated dataset's edit cannot churn this bundle's id. The lesson is narrower than "hash more
things": the hash covered the inputs we thought of as inputs, and the manifest did not feel like one
because it is a contract. Anything that reaches a written row is an input.

**Two corrections carried rather than left to be found.** Ours: we told aging in 012 that the
relaxation would "reproduce today's table exactly", and the site set does — 1,370 ids, verified —
but 25 rows now carry a higher `n_psms`. Theirs: their 013 said the contaminant sites are "all BSA
and trypsin"; there are 113 across 19 accessions, several of them keratins, which understates what
their own S17 contaminant-share metric is measuring. Neither changed a decision. Both would have
been found later by someone with less context.

**The benchmark is the thing to hold on to.** 63 of 168 answerable; `age_effect` alone blocks 46 and
would unlock 42 by itself; section D — whether organelles age at different rates, the proposal's own
question — scores 1 of 19; section B scores 0 of 11 because there is no `age` column anywhere. And
the line that matters most: **no question failed because a table was shaped wrongly.** Every failure
is designed-but-unbuilt, built-but-unfilled, or metadata the deposit never carried.

One pattern from the day worth naming. Three of the four substantive findings came from checking a
claim rather than building on it — aging's ambiguous-group hypothesis, our own "reproduces exactly",
their "all BSA and trypsin". The fourth, the hash defect, is the counter-example: nobody checked it,
and it surfaced only because an unrelated change happened to expose it.

## 2026-09-19 - Postscript: v0.1 released while the close-out was being written

aging's own 014 crossed with ours — the second crossing today — and it changed the headline the
close-out had just recorded. **v0.1 is RELEASED**, not held: catalog `08fb3a5e3078dce5` on bundle
`31fac552c5d748f0`, `id_rate` 0.0998, title filled. They took the second fork of DATAREPO-19, so the
release runs on datarepo 0.3.1 / schema 0.0.3 and carries the 1,997-row `ptm_sites`. The earlier
`84ca279df425c0a2` is superseded, not withdrawn, and their `RELEASES.md` records what changed.

Worth noticing that the close-out's verification step is what caught it. The survey listed a commit
that was not there when the session's summary was written, and every file I had just finished writing
said "HELD". Had the close-out ended one command earlier, the next session would have opened on a
confident, wrong statement about the most important fact in the project.

**A framing of theirs worth stealing.** They corrected the id rate without re-running MetaMorpheus,
via a new `reprovenance.py`, on the argument that a provenance record holds two different kinds of
thing: **history** — commands, tool versions, hashes, timings, true forever and never rewritten — and
**interpretations** — metrics computed under versioned definitions, which move when a definition is
corrected. Only the second kind goes stale, and only it is recomputed, through the same function the
search stage calls, with a `rederived` entry naming what changed from what to what. Our bundles have
the same shape of problem and no such distinction.

**And a schema argument that is better than the request attached to it.** They want contamination as
metrics rather than only a finding, which is easy. The reason is the interesting part: the
dataset-level contaminant share is 7.0%, the per-file values run **2.6% to 18.9%**, and they are
structured by cell line — fetal bovine serum carryover differing sevenfold inside one experiment,
on the same axis along which their S31 says the identification rate is structured. A single
dataset-level number hid all of it and would have been believed. They raise per-run grain as a
general schema preference rather than a one-off, and that question deserves a real answer rather than
just shipping the two metrics.

## 2026-09-20 - Option (1), and the deletion was ten chemistries deep

aging's 019 asked two things and their 020 arrived mid-session correcting the evidence under one of
them. Both are answered, implemented and posted as 021, on datarepo **0.5.0** / schema **0.0.4**.

**`ptm_site_id` keys on the engine's `IdWithMotif`, not the UNIMOD accession.** The decision was
straightforward — a derived view cannot be a key, because a key has to be formable for every row —
and their corrected coverage figure (93.2%, not 33.6%) did not change it. What changed was the size
of the thing being fixed. aging measured one modification on one dataset. Re-ingesting all three and
diffing against 0.4.0 recovered **42 sites over 10 chemistries, 195 PSMs**, and only **one** of the
ten had ever been reported: the other nine resolve to a *mass* but not an accession, so they never
entered `proforma.unresolved`, never produced the finding, and were deleted in complete silence.

The one that stings: PXD036557's 0.4.0 bundle records `unresolved: {}` — a clean ingest, no finding,
nothing to look at — and was missing `PXD036557:P16401:K37:N6-succinyllysine on K`. **The released
v0.1 catalog is missing a row and contains nothing that could tell you so.** The recovered list is
succinyl-, glutaryl-, malonyl-, crotonyl- and methacryl-lysine, nitrotyrosine, two hydroxylations and
a palmitoleoylation. That is a lysine-acylation-shaped hole in an aging proteome repository, and it
was invisible because the loss happened at exactly the level with the strongest constraint.

**The new key costs something, and finding that out was the useful part of the day.** One chemistry
can reach a dataset under two names — `Phosphorylation on S` from the variable-mod list,
`Phosphoserine on S` from a UniProt annotation — so the name key is *finer* than the accession key
and 5 sites in 35,615 split. The temptation was to not mention it. What settled it instead was
noticing the shape: the split is recoverable and the deletion was not. `ptm_sites_by_chemistry`
groups them back and **reproduces the accession-keyed table exactly on all 35,568 groups, zero
mismatches**, `n_psms` summing and `best_q_value` taking the minimum. Which is U8's own grain rule —
store at the grain measured, coarsen in a view — deciding a case where the coarser table was the one
we already had and the finer one cost work. A rule earns its keep the first time it rules against
you.

**The bundle-id question answered itself into a defect.** aging asked whether a bundle id identifies
the data or the data plus the ingest configuration. It identified both *plus their prose*:
`add_declaration` hashed `entry.raw`, so rewording a `reason` moved the id with every row identical.
Fixed, with the field list classified in code and a test that fails on an unclassified field. Worth
recording that this is the *second* failure of the same boundary in two days, in opposite directions
— under-hashing on Friday, over-hashing today — and that only the second one had a caller who could
notice, because aging was the one holding two ids for one measurement.

**And their postscript was about us.** They warned that a consumer parsing mzLib's resource files
rather than asking its loader gets `Decarboxylation on D` wrong. We do parse them, we never read
`unimod.xml`, and our precedence is backwards. Measured against QuantProject's loader-generated
table: agrees on all 100 names that have reached `ptm_sites`, no entry at all for 2,445, differs on
exactly two — the two they named, neither of which has fired. Nothing shipped is wrong; the registry
is right by luck on a narrow corpus and blind on a wide one. Deliberately **not** fixed in the same
change: it would wire a third repository's file into the bundle content hash on our own authority and
confound two movements in one id. Logged as G26/U9 with the distribution question asked rather than
guessed.

The pattern from Friday held again, three for three: the three real findings today all came from
checking a claim rather than building on it — aging's "the only trace is a WARN", our own assumption
that the rekey was purely additive, and their warning about the loader. The claim that turned out
true (their bundle-id hypothesis) was the one they had already checked themselves.

## 2026-09-20 - The study layer, and a version doing two jobs

G19 is built. `schema/study/aging.yaml` went from a stub to eight tables generated the same way the
core's are, and `age_effects` / `age_effect_refusals` / `age_effect_meta` are transcribed
column-for-column from `aging:DEF-AGE-EFFECT v1`. The thing worth recording is *how* the definition
got into the schema: wherever it says something must be true, the shape refuses a null rather than a
comment discouraging one. "A `beta` without an `se` is not an age effect" is a write error. §5's "no
row, not a row with a null" is enforced by a refused fit having a different table, so there is
nowhere to write the null. Five enums carry, in their own descriptions, the benchmark question that
forces them to exist — the `ptm_site_id` residue lesson, applied ahead of time.

Every table is empty and will stay empty. That was the deliverable, not a shortfall: aging's own
benchmark distinguishes `NO_TABLE` from `EMPTY_TABLE`, and the 46 blocked questions scored the first.
Section D's query now parses, joins `protein_localizations`, and returns nothing — which is the
honest answer and was previously not even expressible.

**Four decisions turned out to be ours and not aging's**, which is the part a schema always forces
out of a definition. How the rows arrive at all (stage 7 runs long after a search, so `ingest` cannot
carry them). `glycosite`, which their §4 names and our core enum does not have. Whether `stratum`
closes, when their own §5 uses a value their §2 does not list. And the one that is a real gap rather
than a preference: **`feature_id` at meta grain cannot mean what it means at dataset grain** — a
`protein_group_id` here is scoped to its dataset, so it cannot be a cross-dataset key, and §6 does
not say what replaces it. All four asked as DATAREPO-20, none guessed silently.

**And the same boundary failed a third time.** 0.6.0 is entirely a `build` change, but `__version__`
was in the *bundle* hash, so releasing it would have re-identified every bundle in every store for
byte-identical rows — the over-hashing of 021 §4, one level up and one release later. Now
`bundle.INGESTER_VERSION` is the only version in a bundle's hash and lags `__version__` on purpose;
`catalog_id` carries the package version, the catalog version and every study layer's version.
Verified: adding the entire study layer moved every catalog id and not one bundle id.

Three times in two days: manifest entry under-hashed, manifest prose over-hashed, package version
over-hashed. Each time the test is one sentence — *does this change what the rows say* — and each
time it was available and nobody asked it. That sentence is now in CLAUDE.md's bite-list rather than
in a journal entry, which is the only place it can do any good.

## 2026-09-21 - Three releases, seven decisions, and two lessons that were ours

The longest session so far, and the shape of it is worth recording as much as the content: almost
everything that shipped today was **in reply to something aging said**, and the two most valuable
things learned were **defects in how we work**, not in the code.

**0.7.0 built DATAREPO-20(a) on its own default.** aging had owed us an answer for a day, so D7
applied: build on the recorded default and mark it. `datarepo study` writes a separately
content-addressed study bundle under `<store>/_study/<layer>/`, and `build --study` loads it opt-in.
The property that made it safe to build ahead of an answer is the same one that made it worth
building: a study bundle is a **separate object**, so the blast radius of being wrong about aging's
hand-over is one reader function. Their 024 came back "you built ahead of us and the shape is right;
the delay was ours", with two changes, one of which (`delivery` being advisory rather than
identifying) was already true and already had a test proving it. That is the first time a
pre-emptive default has come back accepted unchanged, and the reason is that we asked in 022 §2
before building rather than after.

**Steps 3-6 of FRAMEWORK are decided as D12-D18**, after a `/grill-me`. Three of the seven changed
the plan rather than ratifying it, and all three changes came from checking a number rather than
accepting a framing:
- **Three MCP tools, not eight.** Most of the eight were thin wrappers over SQL we would write
  anyway, and several answered questions no measurement has asked.
- **The acceptance bar was the wrong shape.** "Agent answers >=X% of the question set" mostly
  measures *aging's data*: `SCHEMA_COVERAGE.md` says 94 of 168 questions wait on a producer, so the
  number would jump when they deliver age effects with nothing here having changed. The bar is now
  zero silently-wrong answers, either direction.
- **Steps 4-5 conflated "a server" with "on the web".** The static site, `llms.txt`, Croissant and a
  Zenodo DOI need no host and no answer to N1/G9, so they come *before* the server. REST and Docker
  Compose are deferred until someone actually wants REST.

**And `read_only=True` is not a sandbox.** Measured rather than assumed, which is the only reason it
was found: a read-only DuckDB connection read a file outside the store via `read_csv_auto` and ran a
three-billion-row scan to completion. DuckDB 1.5 has no `statement_timeout` either. The sandbox
therefore splits in two -- cheap lockdown now, sqlglot allow-list when a public endpoint exists --
because locally it bounds blast radius and publicly it bounds an attacker. Different job, different
time.

**S39 was the biggest thing in the code, and it was one line.** `ptm_site_rows` had
`if mod.position == N_TERMINUS: continue`. We had reported it to aging as 13 missing sites; they
measured the corpus and it was **2,091 terminal sites at q<=0.01** -- 1,220 protein N-terminal, 871
peptide N-terminal, 20,789 PSMs, `ptm_sites` 35,615 -> 38,045 with every other table identical
row-for-row. `peptidoforms` held every one of them, so it was a projection gap rather than data
loss, which is why it was a ruling and not an incident. A reader querying `ptm_sites` for
acetylation got a lysine-only answer, because the 239 `UNIMOD:1` rows that existed were all `on K`.

**The part of that fix worth keeping is the bit we added against their ruling.** aging's rule implied
a protein N-terminus is where the peptide starts at residue 1. Co-translational N-terminal
acetylation follows **initiator-methionine excision**, so it sits on residue 2 with the excised `M`
as the previous residue -- and on their corpus **958 of the 1,220 protein N-termini are at position
2**. A `start == 1` rule would have mislabelled 79% of them as cleavage artefacts. We had three
fixture rows and an argument; they had the number. Arguing from a mechanism against a stated rule
paid, and it paid because the mechanism was checkable.

**We also refused to guess twice, and both refusals were right.** C-terminal placements are
indistinguishable from last-residue ones in what MetaMorpheus writes, so they stay `residue` -- aging
then measured and found **0 C-terminal chemistries have ever been declared to the engine**, so the
hole is latent rather than absent, and will be *worse* than S39 when it appears because it produces
no signal at all. And we asked which table `search_modifications_placed` should derive from rather
than picking: the answer was **peptidoforms, not `ptm_sites`**, because a placed view built on
`ptm_sites` would have reported N-terminal acetylation as never placed while 3,085 peptidoforms
carried it. S39 reproduced in the one view whose whole job is to be trusted about absence. Asking
cost a day; guessing would have cost a table.

### The two lessons that were ours

**We announced releases that existed only in the working tree -- twice in one day.** aging went to
re-ingest 0.7.0 and found `study.py` uncommitted; thread 028 said "we shipped 0.9.0" with twelve
files uncommitted. They refused both times and were right to: a bundle id hashed on an
`INGESTER_VERSION` and `SCHEMA_VERSION` that exist in no commit is reproducible by nobody, which is
exactly the property `manifest.CONTENT_FIELDS` and the version split were built to protect. The
thing we had not considered at all: **they build from a read-only clone at our committed `HEAD`, so
our tip is the only thing they can see** -- an announced-but-unpushed release does not inconvenience
them, it makes the thread message false. The rule went into `CLAUDE.md`'s bite-list rather than here,
because the journal is where the `__version__`-in-the-bundle-hash lesson went to die three times.

**A measurement is only true of the grain it was taken at.** aging retracted their own 1,367 rather
than let us verify against it: it counted peptidoforms whose ProForma *begins* with a modification,
so it conflated the two site types and missed every first-residue placement written
`C[UNIMOD:385]PEPTIDE` instead of as a prefix -- all 240 `Ammonia loss on C` sites. We had asked to
be checked against that number and would have "passed" while being wrong about which sites were
which. It had already reached six places including the schema description, where the next session
would have read it as measured fact; all six now carry the corpus figures, verified prose-only
(`_tables.py` byte-identical, fixture bundle id `d13e382106002a1c` on both sides). This is now four
instances between the two projects, counting aging's own three, and the general form is worth more
than any of them: **carrying a number to a finer grain silently re-labels it.**

And the same hazard caught us one layer up. Our 022 §1 argued that `age_effects.estimator` must exist
*because count- and intensity-based occupancy differ threefold and must never be averaged*, while
the core `ptm_stoichiometry` it draws from still had a single `modified_fraction` forcing precisely
that average. True where written, false one layer down. It took aging's 026 to see it -- and 026 was
also a **dropped commitment**: five corrections we accepted in our own thread 012 and then shipped
0.5.0, 0.6.0 and 0.7.0 without. Their framing ("worth a message rather than a shrug") was correct.
All five are now in, corrected while the table still held 0 rows, with four tests whose only job is
to fail if the shape drifts back. The commitment lives in the suite now rather than in a thread,
which is the only place it could have survived three releases.

### Two smaller things, both found by reading rather than running

`pyproject.toml` restated `version = "0.3.1"` while the package said 0.7.0 and the **installed**
distribution reported `0.1.0` -- three answers to one question, for four releases, with nothing to
catch it. `__version__` is in every `catalog_id`, so an operator reconciling "what did I install"
against a catalog was reading two different numbers. Now `dynamic`, with a test.

And a stale claim repeated in four files: that pyMzLib's mzLib bridge "is not built" in CI. The user
corrected it, and the pyMzLib project confirms wheels for win-x64, linux-x64, osx-x64 and osx-arm64
that carry the bridge -- `pip install mzlib` works anywhere, and our own CI already installed it and
ran the parser tests rather than skipping them. **The comment had outlived the condition it
described**, which is the documentation version of the grain lesson.

## 2026-09-22 - Eighth session: the MCP server shipped, and two agents took it apart

Three releases. **0.10.0** built FRAMEWORK step 3 -- `datarepo mcp`, three tools, D14's sandbox.
**0.11.0** fixed what two agents found when we pointed them at it. In between, the most useful
hour of the day: not writing the server, but **handing it to somebody who had not written it.**

### The thing worth remembering about the whole day

We shipped 0.10.0 with a paragraph in thread 032 saying D15's bar was "a design property we built
for, not a measurement we have". That hedge was written to be honest about an absence. Six hours
later it was a measurement, and **it said no**: 7 of 17 benchmark questions had a live path to a
confident falsehood. The hedge was right and it was also not enough -- we had built every guard we
could think of and still shipped something that would have lied to a careful reader about seven
questions. **The gap between "we designed for X" and "X holds" is not closed by designing harder.**
It is closed by giving the thing to someone who will use it wrong.

The cheapest instrument we have found for that is a subagent with the source code taken away. It
cost two tool calls to set up.

### The guard was on the wrong tools, and that is a shape, not a bug

Six of the seven near-misses were one thing. Every "this table is empty, do not answer from it"
guard lived in `describe` and `search`. **`datarepo_sql` had none of them** -- and `sql` is the tool
that answers everything else, the one `describe`'s own "what to do next" block points at. A join
over two empty tables returned `rows: []` and an envelope that said nothing, and "organelles do not
age at measurably different rates" was one careless step away.

We had written the guards. We had written good ones -- the agent called the text "genuinely the best
I have seen in a data-access layer". We had put them where they were easy to write instead of where
they could not be avoided. The benchmark agent's own sentence is the rule worth keeping:
**a fourth tool would have to be chosen, and an envelope field cannot be skipped.** That settled
D12's open question in the direction of not building anything, which is the best kind of answer.

### Two ingest defects, and both were a measurement that stopped being true

The agents were pointed at the server and found the **ingester**, which nobody was looking at.

**The notch clause.** aging's 008 gave us a rule scoped to PSMs. We applied it to peptidoforms too,
and wrote in the docstring that it "costs nothing on peptidoforms, where no accepted row is
ambiguous". That was measured on PXD036557, where it is 0, and never re-run. On both larger
datasets it costs exactly 3 -- so PXD032202 carried a `count_mismatch` finding against a producer
number **it matched perfectly**, and PXD027318's finding stated a difference of 2 where the real one
is 5, in the wrong direction. The SQL view never had the clause, so the two implementations of one
rule disagreed for three releases, which D10 says is impossible. The test asserting it checked PSMs
only.

This is the same hazard as the `range(3e9)` probe we found the same day: **a measurement embedded in
a comment, generalised past its evidence, with nothing that re-runs it.** aging's qualifier from
their 031 is the sharp version -- the re-labelling is silent *because the number stays
valid-looking*. 21,768 is not an implausible peptide count. Nothing about it invites a second look.

**The contaminant species.** All 339 contaminant proteins read `NCBITaxon:9606` -- porcine trypsin,
bovine albumin at q = 0 in all three datasets, horse cytochrome c, E. coli lacZ. MetaMorpheus had
been handing us the right species per accession the whole time and we overwrote it with the
dataset's organism, consulting the truth only as a fallback that could never fire. "No non-human
proteins were identified" was a falsehood the tools fully supported.

The cause is worth more than the fix. **`Protein.organism` was `required: true`.** A required column
with no true value gets a false one -- there is nowhere else for it to go. We have now made the
same discovery twice from opposite directions: `age_effect_refusals` exists because we gave a
refused fit nowhere to write a null beta, and this exists because we gave a contaminant nowhere to
write an unknown taxon. **Requiredness is a claim that a true value always exists.** It is worth
asking that question explicitly every time, because the failure is not a crash, it is a lie.

### What the sandbox taught, which is the opposite lesson

It held under everything: ATTACH, `read_csv_auto`, `glob`, multi-statement, CREATE, COPY TO,
INSTALL, the watchdog, both caps. Not one row of non-catalog data reached a result. The red team's
summary is the useful part -- **"the remaining risk concentrates not in SQL and not in the sandbox,
but in the derived layer"**: `protein_index`, `proteins`, the `_1pct` views. The tables `search`
answers from, the ones an agent is steered to first, and the only ones with no column documentation
at all, because they exist in no LinkML file and the generator could not see them.

We built a generator specifically to stop descriptions drifting from columns, and then left the
three most-used tables outside it. The fix was to put their prose beside the SQL that builds them
with a test that fails on an undocumented one -- the `manifest.CONTENT_FIELDS` shape again, which
is now the third place that pattern has earned its keep.

### Told to aging while it was still broken

Thread 033 went out **before** the fix was committed, which is the opposite of the rule we adopted
the day before. It was right: they had started an unattended 60-dataset batch that morning, both
defects needed an `INGESTER_VERSION` bump, and every dataset finished on 0.7.0 would need doing
again. An hour of our tidiness would have cost them an hour of compute. **The commit-then-announce
rule protects a claim of completion; it does not apply to a warning.** 033 said what was wrong, gave
them the pause-or-continue decision explicitly, and made no claim to have fixed anything. 034
carried the sha.

### What is not done, and is not being claimed

D15's bar is still unverified. Every near-miss has a test named for the wrong answer it prevents,
and **a fix tested against the failure that prompted it is the weakest evidence there is.** A second
pair of agents is running against 0.11.0 as this is written -- fresh, no knowledge that anything was
fixed, and explicitly asked whether the added envelope fields helped or are ballast an agent will
learn to skip. The measurement that actually counts is aging's, and 032 asked them for wrong
answers rather than a score.


## 2026-09-22 - Same day, later: the fix that certified the forgery, and a deletion

0.10.0 shipped the MCP server. 0.11.0 fixed what two agents found in it. Then a **second** pair of
agents ran against 0.11.0 -- and the part worth recording is what they found in the fixes.

The benchmark improved, and honestly: **0 wrong, 9 answered, 9 correct 'no data'** over 20
questions, against 5/5 over 17 the round before. The `empty_tables` guard was called "the single
most valuable thing in the whole envelope" and named as the direct reason 9 of 20 were answered
correctly. The column-level NULL counts prevented two specific wrong answers.

**And the red team broke three of five claims, two of them through the fields added to prevent
exactly that.**

### The shape of the failure, which is the thing to remember

`tables_touched` and the narrowed `provenance` were added in 0.11.0 so an answer could not be
fabricated. A CTE named after a real table -- `WITH protein_groups_1pct AS (SELECT 99999)` -- read
**zero catalog bytes** and came back stamped `tables_touched: [{protein_groups_1pct, rows: 8055}]`
with a real bundle id. The true answer was 1,652. Both verification fields vouched for the
fabrication, and the provenance text pointed the reader at `tables_touched` as the backstop.

Naming a working table after the thing it relates to needs no adversary. **A verification mechanism
that can be steered by the thing it verifies is worse than none**, because it converts a question
the reader would have asked into an answer they accept.

Worse, the 0.11.0 provenance patch had *already* been this mistake once. The first red-team round
showed a fake bundle id echoed as the provenance of 8,055 real rows; the patch rejected ids the
catalog does not hold. That closed the reproduction. A **real** id in a computed column --
`SELECT max(dataset_id) AS dataset_id, count(*) FROM ptm_sites` -- narrows just as effectively, and
nobody has to be trying. **I fixed the reproduction and called it the class, having written a
warning about exactly that into this file the same morning.**

### What resolved it was a question, not a patch

The user asked: releases are versioned, so an old dataset sits in several versions -- does "I got
this data from this version" help? It does more than help. **`catalog_id` is a hash of the exact
(dataset, bundle) set**, so naming it already states precisely which frozen copy of every dataset
was available. The narrowing was never adding provenance; it was adding a convenience, and
labelling a convenience as provenance is what made it forgeable.

Two questions had been answered as one:

* **Which frozen data does this server hold?** A fact about the server, fixed when it opened the
  file. No question can change it.
* **Which slice did this answer touch?** A guess, read off the query's own output.

0.12.0 deletes the second. Provenance is identical on every answer and inferred from nothing. The
fix is a **deletion**, which is the right shape for a defect caused by a mechanism that should not
have existed -- and it came from the user's model of the domain, not from more engineering.

### aging re-ingested mid-session, and their 035 is half right

They did **not** pause the batch, and their reasoning is better than our question was: the expensive
lanes are fetch and search, the defects were wrong metadata over correct rows, an ingest is minutes.
Four datasets on 0.11.0, 95 checks passed, catalog `71e48aa46a7c9900`. Both count fixes confirmed on
real data -- PXD032202's spurious `count_mismatch` is gone, PXD027318's now states the real 49,399
vs 49,394 instead of a number that was neither side's.

**DATAREPO-27 closed, and they gave the better argument.** Our default was right on PXD032202's
arithmetic; their reason is structural and was already in their own ledger: S22 established that the
peptide-level collapse removes ambiguous rows *before* the count is taken, so the notch clause was
never a property of `DEF-PEPTIDE-1PCT` at all. Their framing of their half: **they handed us a
clause without handing us its scope**, and their ledger already held the sentence that bounded it.

**Their section 3 says the contaminant organism fix is incomplete. It is not, and the reason
matters.** They queried `organism`, found NULL on every contaminant, and hypothesised a
name-to-taxon resolver that knows only `Homo sapiens`. There is no resolver -- deliberately (D1,
G36). The species is in **`organism_name`**, the column schema 0.0.7 added for it: 433 of 442
contaminants carry one, P02769 reads `Bos taurus`, P00761 reads `Sus scrofa`. Their unexplained
41,510 NULL non-contaminant rows are **decoys**, NULL by design because a reversed sequence is no
organism's protein.

So there IS a defect and it is **ours and it is a communication one**: we added a column, described
it in the schema, and said nothing about it in the thread that announced the fix. A consumer who
checks the obvious column concludes the fix failed. **Shipping a column is not delivering it.**

Their section 4 is the best news in the message: our reconciliation caught *their* bug on their
first unattended dataset. A manifest `files: 0` -- the runner counted raw files after cleanup had
deleted them -- surfaced as `MISMATCH runs: bundle 18 vs producer 0`. Because `files` is in the
content hash it would have fixed a wrong bundle id permanently. Their words: "that check earned
its keep."

## 2026-09-22 - Ninth: the bug that two rounds of agent review missed, and nearly blamed on somebody else

aging's 035 said the contaminant organism fix was incomplete. The close-out had recorded that they
were **wrong** -- the species was in `organism_name` and they had queried `organism`. Verified, and
true as far as it went. A draft of thread 036 went out on that basis, with a §3 saying seven
contaminant accessions carry no species **because MetaMorpheus wrote none for them**.

The user then asked for a GitHub issue against MetaMorpheus about those seven.

**Writing that issue meant asserting something about another project's output**, so their file got
read for the first time in the whole exchange. `A2I7N2` = `Bos taurus`, plainly, in the column we
were about to report as empty.

### The actual defect

MetaMorpheus **collapses a column to one entry when every protein on the row shares it**, while
`Accession` keeps all of them:

    Accession     = P60709|P63261         (2 entries)
    Organism Name = Homo sapiens          (1 entry -- collapsed, not missing)

`protein_rows` zipped the two positionally, so every accession after the first indexed past the end
and got `''`. 2,062 rows in a 60,000-row sample; on aging's catalog **2,678 uniprot proteins, 4,523
decoys and 9 contaminants** lost their species -- introduced in 0.11.0, *the release whose entire
purpose was handling species correctly*. `Gene Name` collapses the same way, and
`add_group_proteins` had the same assumption.

The `ptm_sites` path did NOT have it: there is an explicit comment there about pairing residue
starts with accessions and what happens if you do not. Somebody thought about that one. Nobody
thought about this one, on the same day, in the same file.

### What found it, since nothing else did

Not a test. **Not either round of agent review** -- two benchmark agents and two red teams, none of
them saw it, because all four were reasoning about the catalog and the defect was upstream of the
catalog in a file none of them could read.

What found it was the discomfort of making a public claim about somebody else's work. The rule is
now in the bite-list and it generalises past GitHub issues:

> **A claim about someone else's output is verified at the source, not from your own parse of it.**

That is the same failure as 034 (a column shipped without its name) and as aging's own 008 (a
clause handed over without its scope), rotated once more: **a parse trusted without its source.**
Three shapes of the same thing inside a week, two of them ours.

### And a process slip worth recording because it was the second of its kind

`git add -A` on the release commit swept in the **draft** of thread 036 -- the one containing the
false claim about MetaMorpheus -- and pushed it. It was never *posted*: it existed only in our
repo, never in aging's, so no peer read it. But it sat in the thread directory looking posted and
the checker counted it. Rewritten, and the commit message says so rather than replacing it
quietly.

Twice in two days a convenience reached further than intended: inferring provenance from a query's
own output, and `git add -A` on a tree with an unfinished message in it. Same shape -- a tool that
takes what is there rather than what was meant.

## 2026-09-22 - Tenth: we had one thread peer, and eight gaps that needed five

The user's challenge, after watching a thread to `go` get drafted: *"are you waiting on specific
things from project go? why don't you ask for what you need?"* Then, a step further: **thirty-odd
projects, and a producer left to guess is in a weak position.**

Checked rather than agreed, and the answer was worse than "not yet". **dataRepo had exactly one
thread peer: aging.** Eight open gaps name an upstream we need something from -- QuantProject,
pyMzLib, mzLib, MetaMorpheus, go -- and every single request had been routed through aging.

### Why a proxy is not merely indirect

The evidence was already in the record and we had not read it as evidence. Our 012 section 2
measurement reached `go` **through aging**, carrying a mechanism we had already disproved, and
aging had to apologise to `go` on our behalf. Their words to go: the sentence *"transplanted a
number out of a comparison it was measured in, into a claim it does not support."*

**The number survives the hop. The reason does not.** That is the same hazard as every other one
this week -- a clause without its scope, a column without its name, a parse without its source --
and here it is again as a claim without its measurement context, one project removed.

### What opening the channels actually found

Writing a first message forces you to state what you need, which forces you to check whether you
know. Three of four threads turned up something we did not know we knew:

**`go` is designing their output format right now, and two of our columns cannot hold it.**
REQ-GO-7 emits `inherited` and `propagated` flags; `ProteinLocalization` has neither. Ingesting
their file as specified would **promote** an isoform annotation go deliberately marked as assumed
into one that reads as measured. And `organelle_label` is `required: true` against a field they
describe as "CC only; empty otherwise" -- the identical required-column trap that made every
contaminant human two days ago. Both are our bugs, found by reading a contract aging wrote on our
behalf and nobody had checked against the table.

**sdrf is the largest hole in this repository and had never been told it existed.** 75 samples in
the live catalog; **zero** carrying sex, organism_part, cell_type, disease, condition, cell_line,
individual_id or timepoint. Three of four datasets carry `no_sdrf`, the fourth `sdrf_skeleton`.
Every age-stratified question in aging's benchmark dies there. A repository whose stated purpose
is *how organelle proteomes change with age* **cannot stratify a single dataset by age today**, and
the project that owns the repair path had heard nothing from us.

**pyMzLib's gaps were re-tested before being reported**, because the bite-list says SDRF was fixed
upstream while we were still reporting it. All three reproduce on 0.1.1, confirmed latest:
`pro_forma` present and 0-populated with an empty `failed_fields`, `AllQuantifiedPeaks.tsv` failing
on a missing optional `MBR Score` header, two FlashLFQ tables unsupported. Worth the ten minutes:
the report is now dated and exact rather than inherited.

### The rule

> **A consumer who does not state their requirements has delegated the design of their own inputs
> to someone with less information.** And one who states them through an intermediary has delegated
> the reasoning as well.

Each thread offers measurement back, which is what makes it a channel rather than a request queue:
we ingest at corpus scale, and a count that would settle a design argument takes minutes. If any
of these projects is guessing at a distribution we can simply query, that is waste on both sides.

### Left alone deliberately

dataRepo will have a second consumer -- a project still in the user's head. We are not building for
it. *"We will communicate those at that time"* is the correct order, and it is the same discipline
as G17: do not write a producer against a shape neither side has queried. What it does do is
validate U5/G10's default, the generic core plus pluggable study layer, which is about to be tested
by something other than aging for the first time.

## 2026-09-22 - Eleventh: three replies in an hour, and two of them changed what we build

Having opened four channels, we wrote the message that should have come first -- and then the
replies arrived faster than we could act on them.

### The fan-out, and the question we were about to ask the wrong project

Thread 036 to aging ended *"nothing else"*. False: `age_effect` is required by **46 of aging's 168
benchmark questions, 42 blocked by nothing else**, and the delivery path has been built and empty
since 0.7.0 while we never once said it was the priority. Every thread we write asks a project for
what that project owes us, and **none of them says where it sits against everything else.** A
producer who knows they hold the number-one blocker behaves differently from one handed a list.

The user's steer -- *"maybe fan out your aging question, it might be an sdrf thing"* -- was right,
and checking it before asking is what made 037 a correction rather than a wrong request. An age
effect needs a donor age. **There is no age anywhere in the corpus.** The only SDRF in four datasets
is a generated skeleton (`sdrf-skeleton-gen v2.0.0`, 19 columns) and `characteristics[age]` is not
among them -- not empty, *absent*. The other three carry `no_sdrf`. So 037 corrected the omission
and then **withdrew the request**, asking instead whether aging hold ages outside the SDRF path.

### What came back, and it is humbling in the right way

**`go`: we were coding against a contract they overruled two threads ago.** REQ-GO-5's
leading-vs-union default -- which our 001 spent its longest section worrying about -- they rejected
in their 008. Their actual ruling is better than anything we would have asked for: one row per term
carried by *any* member, plus `n_members` / `n_with` / `on_leading` so the consumer reconstructs any
rule at query time. Their D13, now a standing rule with aging: **emit the data and let the consumer
filter; never a run-time switch that changes what a file contains.** Their sentence to us:
*"Trust D1-D22, not REQ-GO-2..10."*

We had read a spec **aging wrote on our behalf**, cited it in our own schema description, and built
against it -- while three threads of rulings moved out from under it. That is the proxy problem with
a number on it, and it is exactly what D21 was written about earlier the same day.

They also confirmed `inherited`/`propagated` and then sharpened our own argument past where we had
it: inherited **CC** is specifically the dangerous case, because alternative isoforms differ
precisely in cellular component -- so the column we were about to not have guards the only aspect
our table stores. And `organelle_category` is **set-valued**, which is a grain problem in a `string`
column, plus a subcategory column we had never heard of.

The part worth remembering for its own sake: **go now ships v1 in three layers, and the third is one
column in our schema.** We hold a third of their design and did not know we were a stakeholder.

**`sdrf`: the repair path exists and the normaliser is merged.** Their D27 -- mzLib never invents
sample metadata; *aging* builds sample blocks for deposits with no usable SDRF and fills
organism/part/disease from PRIDE's project record **only where exactly one value exists**. Every
block carries provenance. They proposed `comment[characteristics source]` mapping onto our
`sdrf_status`, and asked the question we should have asked ourselves: **is `repaired` honest at
DATASET granularity when a dataset is partly repaired?** That is the grain rule aimed at our own
schema.

And `SdrfAge` was merged yesterday, which we had recorded as unbuilt. It carries `Cell` -- the raw
text -- **added at our request in mzLib #1333**, because a number you cannot audit is one you cannot
publish. A thread opened in the morning had changed an upstream API by the afternoon.

**`aging`: re-ingested on 0.13.0, 0 speciesless proteins in 97,731**, and they say they made our own
verify-at-the-source mistake twice on the way there.

### The user's question that found a defect in both schemas

*"I think you asked for ages in years but that might not be good for mouse/rats."*

The units were fine -- `age_raw` is verbatim and required. One layer down was not. `AgeEffect.beta`
is the coefficient on `age_decades = (age_years - 50) / 10`, and **50 is a human lifespan
constant**: a 24-month mouse gives -4.8 decades, a "change per decade" for an animal that lives two
years. And `AgeEffect` has 29 columns, `AgeEffectMeta` has 22, and **organism is in neither**, while
`age_effect_meta` exists precisely to pool across datasets. A human and a mouse effect for one
feature would pool into a meta-estimate with nothing recording the difference.

**Same shape as the contaminant-organism defect from the same morning** -- a column that permits
something wrong with nothing saying so -- except that one put bovine albumin in a human column and
was caught in a day, and this one would reach a meta-analysis. Logged as G40, our half fixed
regardless of aging's answer, asked as 038.

And `age_mappings` already carries `organism`, `age_unit`, `life_stage`, `human_equivalent_years` --
exactly what the problem needs -- holds 0 rows, is referenced by nothing, while aging's benchmark B6
is one of only two questions our coverage map calls NO HOME. **It has a home. The wire was never
connected.** G41.

### What the day actually demonstrated

Four channels opened in an afternoon produced, within the hour: two defects in our own schema, one
superseded spec we had been building against, one upstream API change made at our request, and a
repair path we had recorded as non-existent. **None of it came from more analysis.**

The user's framing, which is the better version of D21: *each project becomes better as the
consumers of those projects define what they need. Otherwise the project is left to guess, which is
a weak position.* Stating a requirement is not a courtesy -- it is a **verification step**, and it
is the cheapest one available.

Process note: both 037 and sdrf 002 **crossed** -- we and they picked the same number
simultaneously. The checker handles it (`BOTH OWE (crossed)`) and threads are never edited after
posting, so both stand. Expect more of this now that five channels are live.

## 2026-09-22 - Twelfth: we went to fill a column and found it was sorting

The session had one job -- answer `go` 002 and `sdrf` 003, the two threads we owed -- and both
replies turned into measurements that changed what somebody builds.

### The column we nearly invented

`go` 002 asked us to commit to `accession_is_leading` as load-bearing: layer 3 of their D21, the
part of their v1 that ships as a column in **our** schema. Their argument was good. Group
composition varies across datasets because it is a function of which peptides were observed, so a
protein's compartment annotation can appear and disappear for reasons that are not biology, and
only a cross-dataset table can ever see that. That table is ours. They were explicit that it was
the section they most wanted answered.

So we went to fill it, and could not.

`AllQuantifiedProteinGroups.tsv` has **26 columns and not one of them names a razor, leading,
representative or principal protein.** And the `|`-joined accession list is **alphabetical** --
checked rather than assumed, 159 of 159 multi-accession rows across two datasets from different
runs, zero deviations. Our ingester preserves producer order faithfully, which means position 1 in
`protein_accessions` is the alphabetically first accession and **nothing else**.

A column called `accession_is_leading` filled from it would report alphabetical rank under a name
promising razor rank. That is `Protein.organism` again -- the value was never missing, the *name
asserted something the data never said* -- and it would be worse in one specific way: **a reader
cannot detect it.** A human accession on bovine albumin eventually looks odd. Alphabetical order
looks exactly like a razor choice, forever.

### And the measurement behind their argument was the same artifact

aging's 013 gave `go` 2,608 / 2,427 / 131 / 50 -- accessions that "always lead", "sometimes lead",
"never lead" across datasets. We reproduced the shape on nine datasets, 4,354 / 4,123 / 171 / 60,
and it is `min(group)` by string comparison in both cases. **171 accessions do not switch razor
status; their alphabetical rank moves because their group gained or lost a member.**

Two of the four proteins `go` named as examples do not survive. `P0DP23` (CALM1) was their
headline -- *"a member in PXD036557, the lead in PXD027318, a member again in PXD032202"* -- and it
is the first accession in all three. It is alone in PXD027318 and sits in
`[P0DP23, P0DP24, P0DP25]` elsewhere; the three calmodulin genes encode an identical protein and
P0DP23 sorts first every time.

That number reached `go` from us, through `aging`. It is the **second** time a mechanism of ours has
arrived at their project with the wrong cause attached -- the first was 46-of-208, which they
struck from their design notes after our 012 disproved it. Three projects have now handled this
number and none of us noticed what it was measuring.

### The honest version is better than the thing they asked for

Their conclusion survives; only the evidence was wrong. Measured directly: of 4,354 accessions
identified in at least two of nine datasets, 4,000 sit in an identical group everywhere, **354
change composition, and 316 are alone in one dataset and grouped in another** -- ARF1 (alone in
PXD027318, with ARF3 in the other eight, both Golgi), RAB1A/RAB1B, SAR1A, H3C1, RAC1.

And it needs no new column at all: `protein_groups.protein_accessions` already holds full
membership per dataset, so the cross-dataset query is reproducible from what we ship today. We gave
them the query. **The property survives the hop and nobody has to trust a column whose meaning
depends on a sort order** -- which is a better outcome than the one they asked for.

Logged as **G43**, open as **DATAREPO-28** to `go` and, in a new thread 002, to `pyMzLib`: does any
MetaMorpheus output expose a razor assignment we are not reading? If both say no we want it recorded
jointly that leading-protein identity is unrecoverable, so none of us reconstructs it from a sort
again.

### Delivering a number that argued against our own section

`go` asked for three counts to price their layer 2. Over nine datasets: **19,246 identified groups,
423 multi-member (2.2%)**, median size 1, p90 1, p99 2, max 15; 402 of the 423 have at least two
members known in UniProt. So at most 2.2% of groups can ever produce an `on_leading = false` pair,
and a per-run counter would read ~0 on eight of nine datasets. We recommended they not build it.

Worth writing down because it cost something to say: **97.8% of identified groups hold exactly one
protein**, which means the whole leading-vs-member question -- the longest section in our 001 and in
their 002 and in our 003 -- matters less than either project has been treating it. The grain
argument still earned its keep, because it is what surfaced their D22 and removed our broadcast. But
the risk we were all defending against is small, and saying so in the same message that refuses
their column is the only way the refusal reads as measurement rather than position.

### sdrf: the answer was no, and the useful part was the number attached to it

`sdrf` 003 closed the age question properly. Their D27 repair path fills a cell only where PRIDE's
project record single-values it for the whole deposit -- which is what makes it safe and what makes
it **useless for age**, since an age is a donor property. It yields **exactly zero ages, today and
after every improvement they have planned.** The curated corpus tops out at **153 accessions of
1,203** carrying a real age, and PXD036557 is not in it.

They corrected their own six-hour-old number on the way (521 was files; 496 is accessions; 153 have
a real value) in the same message that told us the thing we were waiting for was never coming.

The actionable half is one we nearly missed. `aging`'s unattended batch is heading for ~160 datasets
selected on human/DDA/instrument criteria, **with no reference to those 153**, and 0 of the 9
searched so far carry any age. Two sets of almost the same size, currently disjoint, for a
repository whose founding question is how organelle proteomes change with age. **DATAREPO-31** asks
`sdrf` for the list as a queue filter, and it is worth more than anything else queued here.

**SDRF-DR3 got worse rather than better:** 8 of 9 datasets have no SDRF at all, against the 3 of 4
our 001 reported -- all five datasets the batch added since arrived without one. Across 162 samples:
sex, organism part, cell type, disease, condition, material type, cell line, individual and
timepoint are **all zero**. `organism` reads 162/162 only because aging supply it from the manifest,
so even that column is not evidence of sample metadata.

### G42: we shipped the empty-vs-unknown bug a third time

Checking SDRF-DR1 properly -- does their provenance vocabulary survive contact with our schema --
found something one column over. **PXD036557's SDRF *has* an `organism part` column and a `disease`
column**, both carrying `not available` in all 18 rows. Our `samples.organism_part` is NULL for
those 18 samples, and NULL for the 144 samples in the eight datasets that were never asked at all.

We cannot tell them apart. That is the rule this project has already written down twice --
`referenced_tables` returning `[]` for both "reads no tables" and "cannot tell", and `describe`
separating a 100%-NULL column from an absent one -- and `sdrf`'s own section 2 argues the identical
point upstream: *a column that is missing has no fill rate to report, so it is invisible to every
quality instrument we have built.* **Their argument for the SDRF template is an argument about our
table.**

So our answer to their question back is no: `sdrf_status` is **not** honest at dataset granularity.
The grain is wrong, not the vocabulary. Proposal sent: provenance lands per sample and per
characteristic where the fact lands, `sdrf_status` survives as a derived summary with an explicit
`mixed`, and `absent` stays dataset-level because a deposit with no SDRF has no row to carry a
comment -- their framing of why, which is better than ours.

### G44, and a catalog nobody rebuilt

Measuring for `go` meant building a fresh catalog, which surfaced two things the conversation was
not looking for.

**aging's serving catalog is stale.** `F:/aging_data/repo/catalog.duckdb` holds 4 datasets on
builder 0.11.0, built 07:20; the store holds **9 bundles ingested 09:12-09:21** on 0.13.0 with
entirely different ids. Everything they serve or benchmark against right now is pre-fix data. We
built to a scratch path rather than overwrite a serving file mid-batch -- the thread-033 rule, that
an hour of our tidiness can cost them an hour of compute -- so they still have to be told. **G45.**

**G44:** `Protein.organism_name` is populated for decoys, inconsistently -- 149 of 7,157 missing in
PXD023381 but 11,804 of 11,804 in PXD024803. We correctly NULL `organism` for a decoy because a
reversed sequence is no organism's protein; `organism_name` never got the same treatment. Same
defect class as the contaminant-organism falsehood, one column over, caught before it reached an
answer.

The collapsed-column fix does hold on the new batch: **0 non-decoy proteins missing `organism_name`
in 8 of 9 datasets**, PXD032040 the exception at 770 of 13,179. The scary-looking 64,856 total is
decoys.

### A tenth peer, and the first empty inbox this project has had

`logs` was created today -- a generic cross-species orthology layer, homologs/orthologs/paralogs,
`aging` as first consumer rather than design driver. Their `OWNERSHIP.md` already flagged two
capabilities as *"UNCLAIMED -- possible collision with `dataRepo`"*, so 001 answered both unasked.

**Both are theirs.** Accession-to-gene resolution is not something we do: `Protein.gene` is
MetaMorpheus's column stored verbatim, and on real data 20,022 distinct accessions carry 19,743
distinct gene strings, 721 rows have no gene, and **5 accessions disagree with themselves across
datasets** -- gene is not even a function of accession here. Identifier storage splits: verbatim
storage stays ours under D9, because normalising on the way in would stop the thing we are a
repository *of* being reproducible, while normalization is theirs -- our `canonical_accession` only
strips an isoform suffix and has **never fired**, 0 of 110,910 non-decoy rows.

The substantive half was telling them our own schema is wrong for them. `protein_annotations` names
R5 orthologs in its description with `key='ortholog'` in a **string** -- one-to-many in a key/value
string, which is the `organelle_category` grain error with a different name, on a domain whose first
sentence is *"without collapsing one-to-many orthology"*. And it is **dataset-keyed for a fact that
is not a property of a dataset**.

The design point worth keeping: `age_effects` (31 columns) and `age_effect_meta` (24 columns) have
**no organism column**, and `age_effect_meta` stratifies on tissue, acquisition and quant method but
not species. Adding organism (G40) only lets us *refuse* to pool. Pooling across species on purpose
needs a key -- and `feature_type` is already an open vocabulary, so `feature_type='orthogroup'`
makes cross-species meta-analysis expressible **with no new tables**. Asked as REQ-LOGS-4. We also
offered them G36, name-to-taxon, open with no owner since the schema was written.

Taxa confirmed by the user: human, mouse, rat -- matching their MVP 9606/10090/10116 and our D5.

**After posting go 003, sdrf 004, pyMzLib 002 and logs 001, the inbox is empty on our side for the
first time.** Ten peers, all of them owing us.

### What the day demonstrated, again

Every finding here came from trying to *fill* something rather than from reviewing it. The razor
column was found by going to write it. G42 was found by checking a mapping we expected to survive.
G44 and the stale catalog were found by building a catalog for an unrelated measurement. The
previous session's lesson was that stating a requirement is a verification step; this one's is
narrower and sharper:

**Position in a producer's list is not rank unless the producer says so.** Three projects inherited
a number built on that assumption and none of us checked it, because sorted order and chosen order
are indistinguishable from the data -- and the check is one line.

## 2026-09-22 - Twelfth, continued: logs replied during the close-out, and the docs were lying on the front page

The close-out ran and then three more things happened, which is why this entry exists after one that
reads like an ending.

### logs replied within the hour, and asking us a question found a defect in us

Their 002 landed while the close-out was still running, committed from their own session. The
pick-up line we had just written -- *"the inbox is empty on our side, for the first time"* -- was
false before it was pushed. The cold-start check caught it, which is the only reason it did not
survive into the next session.

Their three questions were all measurable and the answers were unusually clean. **REQ-DATAREPO-1:
the corpus is 100% UniProt XML** -- `uniprotkb_proteome_UP000005640_AND_revi_2026_09_18.xml`, sha256
`760984e8d402ade6`, **identical across all nine datasets**, MetaMorpheus 1.1.11 throughout. So the
gene cross-references (Ensembl, GeneID, RefSeq, HGNC) were on `Protein.DatabaseReferences` at search
time and their v1 needs no ID-mapping service on the critical path. **REQ-DATAREPO-2: 100% UniProt
accessions, zero RefSeq** over 20,022 distinct non-decoy accessions, so RefSeq support is their v3
rather than v1; also zero isoform suffixes, zero `_N` collision counters, zero entrapment prefixes.
**REQ-DATAREPO-3: yes** -- name and sha256 per dataset, and because the checksum is identical we can
say the same *bytes*, not merely the same name.

Which is what made the fourth thing possible. They had offered a hypothesis about our five
self-disagreeing gene names: *"we would expect those to be the ones searched against different
databases."* **Identical sha256 disproves it outright**, and chasing the real cause found ours.

All five are HERV-K Gag/Pol proteins in large shared groups, and five undercounts it: **60 of 20,022
accessions are named in one dataset and NULL in another.** MetaMorpheus `|`-joins `Gene Name`
alongside `Accession`, and of 23,284 multi-accession non-decoy peptide rows, 188 collapse the gene
to one shared value (correct, broadcast) and **182 are ragged** -- typically `n_gene = n_acc - 1`,
because a protein with no symbol leaves no hole in the join. Our `_per_accession` refuses to guess
on those and writes None, which is right. But `add_psm_proteins` does `if acc in out: continue`, so
**an accession's value is set by whichever row claims it first**, and a ragged row claims it as
firmly as a clean one.

**And one thing would not reconcile.** Tracing `P63135` by hand gives None for PXD032040; the
catalog stores `ERVK-6`. We could not reproduce the stored value from the source. It went into the
thread as G48 with the column marked unvalidated, rather than being sat on, because **logs are
claiming accession-to-gene and that is the column they are claiming**. The instruction attached to
the gap is not to write the fix until the discrepancy is explained -- first-non-null-wins is the
obvious shape, and a fix built on a mechanism we could not reproduce is the weakest evidence there
is, which this project has already written down twice.

`PXD036557` has **zero** ragged rows. That is the third time this session that a defect survived
because the dataset used to investigate its family happened not to exhibit it.

Their reply also cost us two more gaps and rewrote a third. **G47**: `protein_annotations` is the
wrong home for orthology on grain *and* on keying -- an ortholog relationship is not a property of a
dataset and not a property of a protein either, it is a property of a pair of genes under a stated
source release. Owed edit: drop `ortholog` from the `key` column's examples, because *an example in
a description is a specification to whoever reads it next*, which is exactly how we came to hold
that contract. **G46**: our own `feature_type='orthogroup'` proposal would let a pool span a release
boundary and combine estimates computed against two different memberships -- G40 again with release
as the discriminating column. **G36 rewritten**: they declined the general name-to-taxon map and
were right to. mzLib already carries `Protein.NcbiTaxonomyId` and captures `OX=` from FASTA headers,
and its own comment says an organism id *"comes from the search database that was already loaded, so
it never has to be looked up"*. Our §1 proves that is true of 100% of our corpus: the taxon was in
memory at search time and the producer wrote free text. A downstream map would let the producer keep
discarding it. Owner is now logs, narrowed to the no-`OX=` residue; the upstream ask is ours to make.

### The front page was three releases out of date

Asked to set the repo description and improve the documentation, the first thing the survey found
was that `README.md` said:

> *"The schema is drafted and validated but not locked, and `datarepo ingest` is the only working
> command. There is no query catalog and no server yet."*

**Contradicted by the roadmap table further down the same file**, which correctly showed ingest,
study, build and mcp all Done. Anyone landing on the public repo was told the project does far less
than it does, in the paragraph most likely to be read and least likely to be re-read. Same shape as
the RESUME "Pick up at" that was three sessions stale earlier the same day: **the countable,
generated parts stayed correct while the hand-written headline rotted, and nothing checks prose.**

Three pages added. `docs/README.md` routes by intent and states the five rules that explain the
design. `docs/querying.md` is a cookbook in which every query was run against catalog
`f8fc910cce116fbe` and every result is verbatim -- and it ends with *queries that look right and are
wrong*, which is where the ACTB case lives: `unique_peptides` is 0 in seven of eight datasets
because beta-actin shares nearly all its tryptic peptides, so `WHERE unique_peptides > 0` silently
deletes one of the most abundant proteins in the sample. `docs/limitations.md` is the one worth
keeping: every place the catalog would return a confident wrong answer, each with the measurement
behind it and a gap id.

Writing that third page was itself an audit. Laid out in one list, the limitations are not a
scattering of small gaps -- **no ages at all, 8 of 9 datasets with no sample metadata, seven
annotation tables at zero rows, a gene column we cannot validate, no leading protein, and a corpus
of one organism, one acquisition, one search engine and one database**. The last of those is the one
we had never said out loud: cross-dataset agreement in this catalog is not evidence of method
robustness, because the methods are identical.

Two numbers in the cookbook were transcribed wrong and caught by re-running the queries before the
commit -- an ACTB `unique_peptides` value, and a species count written as "30+" that is 25. On a page
whose entire premise is that the outputs are verbatim, those were the two worst errors available,
and they were found by the cheapest possible check: run it again and read it.

### Recorded

`logs` now has a remote (private, matching its own `state.yaml` and every peer repo except this one,
which is public under D2). Repo description set. G46, G47, G48 logged; G36 rewritten. Ten peers,
`logs` owing us 004.

## 2026-09-22 - Thirteenth: an eleventh peer, G40 shipped, and the XML had logs' trap

The user started a new project, `ptmQtl` (PTM-trait association and PTM co-occurrence), and asked
us to open it the way we opened `logs`. Doing that properly meant measuring the corpus against
their goal before writing a word, and the first measurement came from the wrong place: **the
`datarepo` MCP server reads aging's serving catalog, which is still the 4-dataset 0.11.0 build**
(G45). A scratch rebuild of the store reproduced `f8fc910cce116fbe` exactly, and every number went
out on that. The bare `datarepo build <manifest>` now refuses, because the manifest lists PXD067622
with no bundle, so the PXDs have to be named.

Two findings led 001, and both came from asking what would go in a column for ptmQtl rather than
from reviewing the tables. **No sample carries a trait**: 0 of 162, so PTM -> trait cannot be asked
of this corpus at all. And **`ptm_stoichiometry` pools occupancy per sample group**, which is right
for MetaMorpheus and fatal for a regression on a continuous trait. It is the G17 shape we had
declared correct, and no consumer had ever queried it. Two figures were wrong in the draft and
fixed before posting: a null-UNIMOD count of 46 read off the stale catalog (135 on the current
one), and an artefact share stated against the level-1 sites when the query had counted all target
sites. Re-running before sending caught both. The user asked mid-draft when the message had gone
out, and the honest answer was "not yet".

Then the inbox. aging 039/040 ruled on G40 and corrected their own unit (beta is per decade, not
per year), and writing their definition had exposed `age_centre_years = 50` as a human constant in
the model. We built it as **0.14.0** (`4a108d6`): organism and age_centre_years required on
`age_effects`, organism first in the `age_effect_meta` key, and a test pinning the class (the meta key
begins with organism). It is a study-layer-only change, so no search bundle re-ids and aging owe no
re-ingest. We committed and pushed it before announcing, and 041 names the three columns.

logs had sent five messages (004-008) while we were away, three of them correcting their own
numbers. REQ-DATAREPO-7 asked for the distinct-ENSG distribution in the search XML, and they
predicted ~99%, adding that anything less would mean we had their ALT-haplotype trap. **87.59%.** We
have the trap. `P43628` (KIR) carries 24 ENSGs and one GeneID. NCBI GeneID gives 0.47% multi-gene,
close to their 0.36% primary-assembly figure, and the histones hold up under both. The search
database turned out to be retained on one machine only, in two copies, with neither in any archive;
we routed that decision to aging. We declined to relay the `go` introduction and told logs to go
direct. Relaying it would have been a proxy, the same thing all three projects have been warning
about.

Eleven peers now, and every one of them owes us.
