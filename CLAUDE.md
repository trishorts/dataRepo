<!-- Auto-loaded when cwd is inside this project folder. Managed by the /project skill. -->

# Project: dataRepo

This folder is a `/project`-managed research project. **You are de facto working on it.**

- **Phase:** INCEPTION
- **Goal:** An AI-ready, API-accessible repository for the search + quant results of the many PRIDE datasets the `aging` pipeline reanalyzes. Humans can use it, but AI agents are the main users. The question it serves is how organelle proteomes change with age.
- **Pick up at:** code is datarepo **0.17.2** (`91fbdd9`), core schema **0.0.8**, aging study
  layer **0.3.0**, `bundle.INGESTER_VERSION` **0.11.0**, `study.STUDY_INGESTER_VERSION` **0.4.0**,
  `catalog.CATALOG_VERSION` **4**. The **public site is LIVE** as a preview at
  https://trishorts.github.io/aging-pipeline/ (D25): `datarepo site`, served from an orphan
  `gh-pages` branch of the public `aging-pipeline` repo (`aging` is private). 0.17.2 fixed
  DATAREPO-37: `.psmtsv` files over 512 MiB are read in windows (no INGESTER bump, D26). aging are
  **mid-re-ingest on `c619612`**. Their serving catalog is stale (G45).
  **First thing: run the thread checker.** Then: **G57**, the pyMzLib payload-limit report promised
  to aging in 052. After that, merge each **charter** reply into `design/CHARTER.md` (D24) and fill in
  §8 (G55). Also waiting on: aging (DATAREPO-38, the re-ingest), ptmQtl (P5/P6), logs (L1/L2),
  go (DATAREPO-35), pyMzLib (PR review; mzLib PRs **D #1346** and **E #1345**).
  **When the re-ingest lands:** run `python tools/verify_ptm_sites.py F:/aging_data/repo/store` (it
  should pass on **every** bundle), then regenerate the site **without** `--notice` (G58; the
  recipe is in thread 051). Ask the user whether `localization` joins the charter (G56) before
  writing to it.
  Next, in order:
  (1) **G52**: when `pro_forma` reaches pip, DIFF mzLib's string against `proforma.py` on the
  corpus before switching. They differ in 3 ways, and the string is the peptidoform id.
  (2) Build the **go reader** (G53) and the **logs gene table** (G54) only from a real delivered file.
  (3) **G48**: explain `ERVK-6` for `P63135` from logs 010 §3's hypothesis. **Never back-fill
  `Protein.gene`.**
  (4) G42 verbatim SDRF cells, stored as a pointer to aging's kept SDRF (sdrf 005 §2). (5) G35: do
  NOT claim D15's bar. (6) G32, G46, G33/G26/G36, QPX pin (G13). **N1/G9 goes to the next NCEMS
  meeting regardless.** Do NOT build `accession_is_leading` (G43, settled by go D25). **D1-D21
  locked.**
- **GitHub:** public at https://github.com/trishorts/dataRepo (`origin`, branch `master`). The user created it on 2026-09-19, which closed G8.
- **Every question for the user goes in `design/OPEN_QUESTIONS.md`** (D7), with a default. They take it to NCEMS and working-group meetings. Work proceeds on the defaults.
- **The benchmark questions belong to aging** (D6). Don't write domain questions here.

## Things that will bite you here

- **Validating is not loading.** Croissant's per-table FileSet form PASSED `mlcroissant validate` and
  then loaded **zero records** from an HTTP-served store, with no error: a loader cannot list a web
  directory. Test a published format by consuming it (`mlcroissant` `Dataset(...).records(...)`,
  with `mlcroissant[parquet]`, since without pyarrow it also fails), not by validating it. Same shape
  as "reviewing asks is it right, filling asks what goes here".
- **The public site lives in another repo.** `datarepo site` output is served from the orphan
  `gh-pages` branch of `trishorts/aging-pipeline` (D25). Regenerate by pointing `--out` at a clone of
  that branch: the generator deletes only files its `.datarepo-site.json` marker lists, so `.git` and
  `.nojekyll` survive. That clone is the ONE place `git add -A` is right. **Read the generated page
  before pushing**: that is how "11.8K" for 117,699 was caught.
- **The Bash tool eats backslashes in heredocs here.** `\\n` inside a `<<'EOF'` Python heredoc came
  out as a real newline three times in one session, breaking the files it patched. Write patch
  scripts with the Write tool and run them. Also: bash here cannot write to `C:/...` paths; use
  `/c/...`.
- **A windowed pyMzLib read re-parses the whole file per window** (~55 s for 1.8 GB). Windows are
  512 MiB of source (1.24 GB is known to read whole, 1.83 GB not). A proven-identical reader change
  does not bump `INGESTER_VERSION` (D26); a probably-identical one does.

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
- **ELEVEN thread peers now, not one** (D21): `aging`, `go`, `sdrf`, `pyMzLib`, `QuantProject`,
  `pride`, `qc`, `pep`, `phred`, `logs`, `ptmQtl` -- each under `design/threads/<peer>/` with a mirror in that
  project's `design/threads/dataRepo/`. Until 2026-09-22 everything routed through aging, and a
  proxy loses the reasoning. **Ask the owner directly and offer a measurement back** -- we ingest
  at corpus scale, so a count takes minutes and a producer guessing at a distribution we can query
  is waste on both sides. **Open a channel only where there is a concrete need or finding**;
  opening one with nothing to say is noise. And check the peer is `/project`-managed first --
  MetaMorpheus is a source clone and our convention does not belong in it.
- **To check whether a thread landed, run aging's checker** — don't guess and don't edit aging's
  tracking table yourself:
  `python "$env:USERPROFILE/.claude/skills/project/assets/threads.py" inbox`
  It prints who owes whom per peer and flags DUP-NUMBER / DIVERGED / ONE-SIDED / UNCOMMITTED /
  UNPUSHED. Both sides number from a shared sequence, so check `next=` before choosing a number:
  aging had planned their own 007 and ours took it, which the checker resolved to `next=008`.
  Its DIVERGED check normalizes line endings, so CRLF/LF differences between the two copies are fine.

- **`P12345_2` is NOT `P12345-2`, and they look alike.** From logs 002 section 4, off mzLib's
  source: `-2` is a real isoform suffix, while **`_2` is a FASTA load-collision counter**
  (`ProteinDbLoader.cs:333-343`) marking the second entry whose accession collided. They mean
  opposite things. Also: decoys are `DECOY_<acc>` with a *configurable* identifier that is
  nonetheless **hardcoded** as the literal `"DECOY_"` in three places in
  `PeptideWithSetModifications.cs`, entrapment adds `Random_<acc>`, and the two nest as
  `DECOY_Random_<acc>` -- so a single-strip is wrong. mzLib itself does **no** accession
  normalization at all (`IBioPolymer.Equals` keys on raw string equality), which is why our
  verbatim-storage rule (D9) is the only thing keeping any of this visible. Our
  `canonical_accession` does one `split('-')` and has never fired (0 of 110,910 rows) -- that is
  because this corpus is UniProt-XML-derived and canonical-only, **not** because isoforms are rare.
- **A contaminant-panel protein must never be mapped through orthology** (logs 002 section 0).
  Bovine albumin mapped to human ALB is *biologically correct and scientifically a lie* -- it is a
  reagent, not evidence about Bos taurus. The contaminant flag has to travel with the accession
  wherever it goes. Same family as the required-column falsehood below, reached through a door
  that looks like correctness.
- **Position in a producer's list is not rank unless the producer says so.** `go` asked us to store
  `accession_is_leading`. MetaMorpheus's `AllQuantifiedProteinGroups.tsv` has **26 columns and none
  names a razor, leading or principal protein**, and its `|`-joined `Protein Accession` list is
  **alphabetical** -- 159 of 159 multi-accession rows across two datasets, zero deviations. So
  element 0 is alphabetical rank. A cross-dataset "leads here, not there" count built on it
  (aging's 013: 2,608/2,427/131/50) is `min(group)` by string comparison, and **three projects
  passed that number around without anyone checking**, because sorted order and chosen order are
  indistinguishable from the data. Two of the four proteins named as examples do not reproduce.
  The check is one line (`a == sorted(a)`); the column would have been `Protein.organism` again,
  except undetectable -- a human accession on bovine albumin eventually looks odd, alphabetical
  order never does. G43, open as DATAREPO-28 to go and pyMzLib.
- **The `datarepo` MCP server in this folder reads aging's SERVING catalog, which can be stale.**
  At the 2026-09-22 close, `F:/aging_data/repo/catalog.duckdb` was still the 4-dataset 0.11.0 build
  while the store held 9 bundles on 0.13.0 (G45). So an answer from the MCP tools describes data
  that no longer exists. Check `catalog_id` and `built_by` in any `describe` answer. For
  measurements, build a scratch catalog from the store and **name the PXDs**, because a bare
  `datarepo build <manifest>` refuses on the first manifest dataset with no bundle:
  `datarepo build E:/CodeReview/aging/instance/manifest.yaml $(ls F:/aging_data/repo/store) --store F:/aging_data/repo/store --latest --out <scratch>/cat.duckdb`.
  Never overwrite aging's serving file yourself.
- **UniProt XML's Ensembl cross-references include ALT-haplotype and patch genes.** Counting
  distinct ENSG per accession in the search XML gives **87.59%** single-gene. The primary-assembly
  truth is ~99.6%: `P43628` (KIR) carries 24 ENSGs and 1 GeneID. NCBI `GeneID` gives 0.47%
  multi-gene and keeps the genuine cases (the histones). logs hit the same trap in Ensembl's own
  dumps (their 007). Any per-gene count over that field needs GeneID or a primary-assembly
  restriction.
- **Findings come from trying to FILL a thing, not from reviewing it.** Everything found on
  2026-09-22: the razor artifact came from going to write the column; G42 from checking a mapping we
  expected to survive; G44 and aging's stale catalog from building a catalog for an unrelated
  measurement. Two rounds of agent review had already missed the collapsed column for the same
  reason. **Reviewing asks "is this right?"; filling asks "what goes here?" -- and only the second
  one fails loudly.**
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
- **No two `|`-joined MetaMorpheus cells are aligned unless MetaMorpheus says so, and it does not.**
  Twice now. `Organism Name` collapses to one value when every protein shares it (0.13.0), and
  `Start and End Residues In Full Sequence` is de-duplicated *and* repeated per occurrence (aging
  043, 0.15.0), so gamma-actin carried POTE-E's numbering for 2,266 sites. The comment above the
  second bug said "one span per accession, paired by position" and **predicted the failure it was
  committing**. Equal lengths are not evidence either: two proteins, one sharing a span and one
  repeating the peptide, also give two spans. Where a fact per accession is needed, derive it from
  the thing itself (sites now come from the searched sequence) or return null. `_per_accession`'s
  broadcast/zip/null rule is safe only for a column that collapses and never repeats.
- **Commit with `git commit -F <file>` (or from Bash), never a PowerShell here-string that contains
  a double quote.** PowerShell 5.1 splits the message at each `"` into pathspecs, the commit fails,
  and a chained `git push` then pushes nothing while looking successful. It happened at 0.15.0.
- **Never `git add -A` in this repo.** It swept the unfinished DRAFT of thread 036 -- the one
  carrying the false MetaMorpheus claim -- into a release commit and pushed it. Threads are never
  edited after posting, and that one had not been posted (it was never in aging's repo, so no peer
  read it), but it sat in `design/threads/` looking posted and the checker counted it. Stage the
  paths you mean. This is the second convenience in two days that reached further than intended,
  the first being provenance inferred from a query's own output -- the same shape, a tool taking
  what is there rather than what was meant.
- **A consumer who does not state their requirements has delegated the design of their own inputs
  to someone with less information** -- and one who states them through an intermediary has
  delegated the reasoning too (D21). Opening four channels in an afternoon turned up two defects in
  our OWN schema (G39) that had sat unnoticed because aging wrote REQ-GO-2..10 on our behalf and
  nobody checked the contract against the table. Writing a first message forces you to state what
  you need, which forces you to check whether you know.
- **Re-test an upstream gap before reporting it again.** Already in this list for SDRF; it earned
  its keep again on 2026-09-22. All three pyMzLib gaps were re-run against 0.1.1 (confirmed latest
  via `pip index versions mzlib`) on real data before thread 001 went out. They still reproduce, so
  the report is dated and exact rather than inherited -- and if one had been fixed we would have
  reported a stale failure to the people who fixed it.
- **A requirement written on your behalf goes stale and you will not notice.** Our schema's own
  description cites `REQ-GO-2..10` -- which **aging** wrote for us, and which `go` had overruled in
  two later threads we were not party to. We built a table against the superseded version and only
  found out by opening the channel and being told *"trust D1-D22, not REQ-GO-2..10"*. If a
  contract in this schema names requirements somebody else authored, **check them against their
  owner's current rulings before building**, and prefer a flat current contract from the owner over
  a requirement list reconstructed from a thread.
- **FRAMEWORK.md is still partly a proposal.** Steps 1 (ingest) and 2 (build) are built and their contracts locked as D9 and D10; steps 3-6 (client/MCP, REST, deploy, auto-ingest) are not decided, so don't build on them as if they were.
- **The user is not a server or infrastructure person.** They said "out of my league" and rely on you to explain. Keep choices few and give a recommendation each time.
- **Don't re-own other projects' work.**
  - aging's rule (D1) applies here: the organelle map belongs to `go`, metric definitions (`DEF-*`) to QuantProject, and the age normalizer to sdrf/mzLib.
  - Parse with pyMzLib typed readers where they exist.
  - dataRepo **never defines**, but since D24 (2026-09-23) it **does run** the generic engines'
    released versions on stored data (logs, ptmQtl, maybe go). In-search engines (phred, quant,
    SDRF) run in aging's search. Who does what is in `design/CHARTER.md`, which is **not in force
    until all eight parties sign**.
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
