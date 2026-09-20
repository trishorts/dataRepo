<!-- Auto-loaded when cwd is inside this project folder. Managed by the /project skill. -->

# Project: dataRepo

This folder is a `/project`-managed research project. **You are de facto working on it.**

- **Phase:** INCEPTION
- **Goal:** An AI-ready, API-accessible repository for the search + quant results of the many PRIDE datasets the `aging` pipeline reanalyzes. Humans can use it, but AI agents are the main users. The question it serves is how organelle proteomes change with age.
- **Pick up at:** ingest and build are done, aging's v0.1 is RELEASED (bundle `31fac552c5d748f0`
  / catalog `08fb3a5e3078dce5`) and **aging is not re-cutting it** (their 019 §6). Code is now
  datarepo **0.5.0**, schema **0.0.4**. Nothing is blocking us and nothing of ours is blocking them.
  Next, in order: (1) **G19**, instantiate the study layer — the largest lever at 46 of 168 benchmark
  questions, unblocked by `aging:DEF-AGE-EFFECT v1` (three tables: `age_effect`, `age_effect_meta`,
  `age_effect_refusals`), but **the definition of an age effect is aging's and must not be invented
  here**; build the SHAPE only and ask if a benchmark question needs a column the definition does not
  name. Know before starting that PXD060431 — the only dataset carrying donor ages — is admitted for
  **abundance only** under a scoped acquisition exception, so the tables may ship empty; (2) **G26**,
  replace the in-house modification registry with QuantProject's loader-generated
  `IdWithMotif-to-Unimod.<mzlib>.tsv` once aging and QuantProject answer the distribution question in
  thread 021 §5; (3) **G28**, `search_modifications` says "every modification the search considered"
  and means "declared"; (4) G17/G18, still free at 0 rows; (5) QPX pin (G13). D1–D11 locked.
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
- **Thread messages are never edited after posting.** Put a message in both `aging/design/threads/dataRepo/` and `design/threads/aging/`, commit each copy alone in its own repo, and push aging.
- **To check whether a thread landed, run aging's checker** — don't guess and don't edit aging's
  tracking table yourself:
  `powershell -NoProfile -File E:\CodeReview\aging\design\threads\check_threads.ps1`
  It prints who owes whom per peer and flags DUP-NUMBER / DIVERGED / ONE-SIDED / UNCOMMITTED /
  UNPUSHED. Both sides number from a shared sequence, so check `next=` before choosing a number:
  aging had planned their own 007 and ours took it, which the checker resolved to `next=008`.
  Its DIVERGED check normalizes line endings, so CRLF/LF differences between the two copies are fine.

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
