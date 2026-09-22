<!-- Auto-loaded when cwd is inside this project folder. Managed by the /project skill. -->

# Project: dataRepo

This folder is a `/project`-managed research project. **You are de facto working on it.**

- **Phase:** INCEPTION
- **Goal:** An AI-ready, API-accessible repository for the search + quant results of the many PRIDE datasets the `aging` pipeline reanalyzes. Humans can use it, but AI agents are the main users. The question it serves is how organelle proteomes change with age.
- **Pick up at:** ingest, build, the study layer and **FRAMEWORK step 3, the MCP server**, are all
  done. Code is datarepo **0.13.0**, schema **0.0.7**, `bundle.INGESTER_VERSION` **0.9.0**,
  `study.STUDY_INGESTER_VERSION` **0.2.0**, `catalog.CATALOG_VERSION` **4**. **aging owe a
  re-ingest on `efd1a83`** (thread 036): 0.13.0 fixes a collapsed-column parse that cost ~7,200
  proteins their species, so `INGESTER_VERSION` moved and every bundle re-ids. Their catalog today
  is `71e48aa46a7c9900`, built on 0.11.0, and their unattended batch keeps adding to it.
  **First thing: run the thread checker** (command below).
  Next, in order:
  (1) **G35: do NOT claim D15's bar.** Measured twice; each round the benchmark improves while the
  red team breaks the previous round's fix (D20 is the worst instance). 0.12.0's fixes are
  unverified, and 0.13.0 proves the reviews have a blind spot: **both rounds missed the
  collapsed-column bug, because all four agents were reasoning about the catalog and the defect was
  upstream of it, in a producer file none of them could read.** A re-run should include at least
  one agent pointed at `F:/aging_data/<run>/<PXD>/04_search/` rather than at the catalog.
  (2) **G32**, `age_effect_meta.feature_id`, fully specified by aging's `DEF-AGE-EFFECT-META v1.1`
  (their 031): identity is the UniProt accession joined through MEMBERSHIP in `protein_accessions`,
  never the id string; for `ptm_site` it is (accession, residue, position, chemistry) off
  `ptm_sites_by_chemistry`, not the UNIMOD column. Land it with the membership-join view and the
  new **`n_source_groups`** column, whose description must carry the 1.02-1.05x inflation and the
  perfect-correlation-by-construction clause IN THE COLUMN'S OWN TEXT. A re-ingest is already owed,
  so this lands in the same pass instead of forcing a second.
  (3) **`ptm_stoichiometry` has the right shape (G17) and no producer.** Shape first, then a
  producer -- do not write one against a shape neither side has queried.
  (4) **The no-server half of FRAMEWORK 4-5 (D16)**: `datarepo site` with Bioschemas JSON-LD,
  `llms.txt` and Croissant, published by aging (D8). REST and Compose stay deferred. **N1/G9 --
  does NCEMS host web services at all -- goes to the next meeting regardless; it is the long pole
  for D1.**
  (5) **G33**, **G26** and **G36**, all the same `REQ-PYMZ` shape: ask mzLib's loader through
  pyMzLib rather than parsing its resource files. G36 (species to taxon) gets urgent when aging's
  queue reaches mouse or rat -- they are on 2 of 160 qualifying human datasets, so not soon.
  (6) QPX pin (G13). **D1-D20 locked.**
- **GitHub:** public at https://github.com/trishorts/dataRepo (`origin`, branch `master`). The user created it on 2026-09-19, which closed G8.
- **Every question for the user goes in `design/OPEN_QUESTIONS.md`** (D7), with a default. They take it to NCEMS and working-group meetings. Work proceeds on the defaults.
- **The benchmark questions belong to aging** (D6). Don't write domain questions here.

## Things that will bite you here

- **After editing `.project/state.yaml`, parse it:** `python -c "import yaml;yaml.safe_load(open('.project/state.yaml',encoding='utf-8'))"`. A broken file makes render_resume silently count 0 gaps. It happened on 2026-09-19.
- **Anything that reaches a written row is an input to the bundle hash — and nothing else is.** Both
  halves have now bitten. The manifest entry was not hashed for a day because it felt like a contract
  rather than an input, though it supplies the title and all five D5 axes. Then the fix over-corrected
  and hashed `entry.raw`, so aging rewording a dataset's `reason` moved the bundle id while every row
  stayed identical, and two sites ingesting byte-identical search output got different ids (their 019
  §1). `manifest.CONTENT_FIELDS` / `NON_CONTENT_FIELDS` now classify every field with its reason and a
  test fails on a `DatasetEntry` field in neither, so **adding a field means deciding which it is.**
- **A bundle's content hash covers inputs, schema version and `bundle.INGESTER_VERSION` — not the
  reader code, and NOT `__version__`.** Change how a file is parsed without bumping
  `INGESTER_VERSION` and you get the same bundle id from different code, so bump it in the same
  commit as any parsing or transform change. It is deliberately *not* the package version: 0.6.0 was
  entirely a `build` change, and hashing `__version__` would have re-identified every stored bundle
  for byte-identical rows. The catalog's equivalent is `catalog.CATALOG_VERSION`, which `catalog_id`
  carries along with `__version__` and every study layer's version.
- **Schema edits need TWO regenerations:** `python tools/build_docs.py` **and** `python tools/build_tables.py`
  (the ingester's Arrow schemas), or CI fails on drift. If the change affects what the ingester writes,
  also `python tools/build_example_bundle.py`. Lint with `--config .linkmllint.yaml`: enum values like
  DDA and TMT are kept on purpose. LinkML isn't installed globally; use `pip install -r requirements-dev.txt`
  in a venv.
- **pyMzLib is `mzlib` on PyPI**, and imports as `pymzlib`. Its wheels are per-platform and carry
  the mzLib bridge, so `pip install mzlib` is all it takes and **`PYMZLIB_BRIDGE` is not needed**.
  That variable is only for a source checkout, which ships no bridge — this machine ran an editable
  install of the `_wt_pymzlib_585` worktree for a while, which is where the old warning came from.
  `datarepo doctor` prints the version and the bridge path it resolved.
- **Reading mzLib's resource files is not the same as asking mzLib's loader.** `modlist.py` parses
  `Mods/*.txt` and `Data/ptmlist.txt` itself, never reads `Data/unimod.xml`, and prefers `Mods.txt`
  where the loader prefers Unimod. It agrees with the loader on all 100 modification names that have
  actually reached `ptm_sites`, and differs on two that have not (`Decarboxylation on D`/`on E`, a
  real mzLib defect). The authority is QuantProject's loader-generated
  `IdWithMotif-to-Unimod.<mzlib>.tsv`; replacing the registry with it is G26.
- **Parsing producer formats is pyMzLib's job.** Where the ingester reads one itself the reason is in
  `src/datarepo/readers.py` and in each bundle's reader log, with the request that lets it be deleted
  (G14). Don't add an in-house parser for a format pyMzLib covers, and **re-test the gaps against the
  current release before repeating them** — SDRF was fixed upstream while we were still reporting it.
  For an SDRF use `pymzlib.sdrf.read`, never the generic `read_records`, which is still lossy on one.
- **PowerShell `Set-Content -Encoding utf8` writes a BOM,** and linkml-validate then rejects the file (the first key reads as `ï»¿datasets`). Write YAML fixtures with the Write tool or `[IO.File]::WriteAllText` using UTF-8 without a BOM.
- **COMMIT, THEN ANNOUNCE. Never write "shipped" for code that is only in the working tree.**
  It happened twice on 2026-09-21 and aging caught it both times (their 029). Thread 028 said "we
  shipped 0.9.0" while twelve files sat uncommitted; earlier the same day they went to re-ingest on
  0.7.0 and found `study.py` uncommitted. Both times they refused to run, and they were right to:
  **a bundle id hashed on an `INGESTER_VERSION` and `SCHEMA_VERSION` that exist in no commit is
  reproducible by nobody**, which is precisely what `manifest.CONTENT_FIELDS` and the
  `INGESTER_VERSION`/`__version__` split were built to protect. Ingesting against a dirty tree
  would be them breaking our own rule on our behalf. They build from a read-only clone at our
  committed `HEAD`, so **our tip is the only thing they can see** -- if a release is announced and
  not pushed, they are blocked and the thread is a lie. Commit and push first, then say so, and
  quote the sha.
- **Thread messages are never edited after posting.** Put a message in both `aging/design/threads/dataRepo/` and `design/threads/aging/`, commit each copy alone in its own repo, and push aging.
- **To check whether a thread landed, run aging's checker** — don't guess and don't edit aging's
  tracking table yourself:
  `python "$env:USERPROFILE/.claude/skills/project/assets/threads.py" inbox`
  It prints who owes whom per peer and flags DUP-NUMBER / DIVERGED / ONE-SIDED / UNCOMMITTED /
  UNPUSHED. Both sides number from a shared sequence, so check `next=` before choosing a number:
  aging had planned their own 007 and ours took it, which the checker resolved to `next=008`.
  Its DIVERGED check normalizes line endings, so CRLF/LF differences between the two copies are fine.

- **A required column with no true value gets a false one.** `Protein.organism` was
  `required: true`, so all 339 contaminant entries read `NCBITaxon:9606` -- porcine trypsin, bovine
  albumin at q=0 in all three datasets, E. coli lacZ -- and "no non-human proteins were identified"
  became a falsehood the tools fully supported. We have now found this twice from opposite
  directions: `age_effect_refusals` exists because a refused fit had nowhere to write a null beta.
  **`required: true` is a claim that a true value always exists.** Ask it explicitly, because the
  failure is not a crash, it is a lie.
- **A measurement written into a comment must be re-run, or it becomes a belief.** Two on one day.
  `producer_counts` carried "it costs nothing on peptidoforms" -- true on the one dataset it was
  measured on, worth exactly 3 rows on each of the other two, which made a `count_mismatch` finding
  fire against a dataset that matched its producer perfectly. And D14's timeout probe,
  `SELECT count(*) FROM range(3e9)`, is answered from metadata in half a second by DuckDB 1.5 --
  the test still passed and had stopped testing anything. aging's qualifier (their 031) is the
  sharp form: **the re-labelling is silent because the number stays valid-looking.**
- **Put a guard on the path that cannot be avoided, not where it is easiest to write.** Every
  "this table is empty, do not answer from it" guard lived in `describe` and `search`; `datarepo_sql`
  had none, and `sql` answers everything else. That single placement error was six of seven
  near-misses in the first benchmark run. The rule it produced is D19: **a tool has to be chosen,
  an envelope field cannot be skipped.**
- **Commit-then-announce protects a claim of completion; it does not apply to a warning.** Thread
  033 went out with the defects undiagnosed-in-code and unfixed, because aging had started an
  unattended 60-dataset batch that morning and both fixes needed an `INGESTER_VERSION` bump. An
  hour of our tidiness would have cost them an hour of compute. Say what is wrong, hand them the
  decision, claim nothing fixed, and send the sha separately.
- **Hand the thing to someone who did not build it.** The cheapest instrument in this project is a
  subagent given the tools and denied the source (`scratchpad/ask.py` drives the real server over
  real stdio). Two of them found seven near-misses, two ingest defects nobody was looking at, and
  settled D12's fourth-tool question -- in about an hour. **Designing harder does not close the gap
  between "we built for X" and "X holds".**
- **A verification mechanism that can be steered by the thing it verifies is worse than none.**
  0.11.0 added `tables_touched` and a narrowed `provenance` so an answer could not be fabricated.
  A CTE named after a real table -- `WITH protein_groups_1pct AS (SELECT 99999)` -- read zero
  catalog bytes and came back stamped with that view's 8,055-row count and a real bundle id. Both
  new fields vouched for the fabrication. It converts a question the reader would have asked into
  an answer they accept. **Anything that certifies an answer must come from the engine, not from
  the query or its output** (D20).
- **Fixing the reproduction is not fixing the class, and you will not notice the difference.** The
  forgeable provenance was 'fixed' by rejecting bundle ids the catalog does not hold; a REAL id in
  a computed column narrows just as well. Both rounds of this happened on a day whose own journal
  entry already warned that a fix tested against the failure that prompted it is the weakest
  evidence there is. Write the test for the CLASS or say plainly that you did not.
- **Shipping a column is not delivering it.** Schema 0.0.7 added `Protein.organism_name` and the
  thread announcing the fix never named it, so aging queried `Protein.organism`, found NULL, and
  reported a working fix as broken (their 035 section 3). A consumer checks the obvious column. If
  a fix moves a fact to a new column, the thread must say the column's name.
- **`empty` and `unknown` are different answers and must not share a representation.**
  `referenced_tables` returned `[]` both for 'this query reads no tables' and for 'I cannot tell',
  and its own docstring warned about that while its only caller ignored the warning. It now
  returns `None` for unknown. The same split is why `describe` reports a 100%-NULL column
  separately from an absent one.
- **A claim about someone else's output is verified at the source, not from your own parse of it.**
  Thread 036's draft asserted that MetaMorpheus wrote no species for seven contaminants, and the
  user asked for a GitHub issue about it. Writing that issue meant reading their file for the first
  time -- and their file had the species. A public issue was one step from being filed, under the
  user's name, blaming an upstream project for a defect introduced here the day before. The bug was
  ours: MetaMorpheus **collapses a `|`-joined column to one entry when every protein on the row
  shares it**, and `protein_rows` zipped it positionally, costing ~7,200 proteins their species.
  **Neither round of agent review found it**, because all four agents were reasoning about the
  catalog and the defect lived upstream in a file they could not read.
- **Never `git add -A` in this repo.** It swept the unfinished DRAFT of thread 036 -- the one
  carrying the false MetaMorpheus claim -- into a release commit and pushed it. Threads are never
  edited after posting, and that one had not been posted (it was never in aging's repo, so no peer
  read it), but it sat in `design/threads/` looking posted and the checker counted it. Stage the
  paths you mean. This is the second convenience in two days that reached further than intended,
  the first being provenance inferred from a query's own output -- the same shape, a tool taking
  what is there rather than what was meant.
- **FRAMEWORK.md is still partly a proposal.** Steps 1 (ingest) and 2 (build) are built and their contracts locked as D9 and D10; steps 3-6 (client/MCP, REST, deploy, auto-ingest) are not decided, so don't build on them as if they were.
- **The user is not a server or infrastructure person.** They said "out of my league" and rely on you to explain. Keep choices few and give a recommendation each time.
- **Don't re-own other projects' work.**
  - aging's rule (D1) applies here: the organelle map belongs to `go`, metric definitions (`DEF-*`) to QuantProject, and the age normalizer to sdrf/mzLib.
  - Parse with pyMzLib typed readers where they exist.
  - dataRepo only stores and serves.
- **The .gitignore template ignores `bin/`.** Add a `!/<dir>/bin/` exception before putting code in any bin folder (G4).

**Sibling project: `E:\CodeReview\aging`** (the NCEMS pipeline). aging *produces* results under
`F:\aging_data\<run>\<PXD>\` with `provenance.json` (schema `aging-provenance/2`). dataRepo *ingests and serves*
them and never re-runs a search. Requests between the two go through aging's thread convention
(`aging/design/threads/`).

**Raw data never goes on E:** (aging D3). **D8: this repo is code only.** aging hosts the data instance (bundles, releases, DOIs, the deployed service); dataRepo ships the software.

**At the start of a session (your first response in this folder), render the standard `/project brief`
once.** Format and derivation are in the `project` skill's `references/session-brief.md`. State lives in
`.project/state.yaml`. `RESUME.md` is rendered fresh by `/project`, so do not hand-edit its generated block.

Layout: `design/` `lit/` `code/` (worktrees, gitignored) `data/` (+PROVENANCE) `results/`
`manuscript/` `submission/`. Conventions and dispatch live in the `project` skill.
