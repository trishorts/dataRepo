<!-- Auto-loaded when cwd is inside this project folder. Managed by the /project skill. -->

# Project: dataRepo

This folder is a `/project`-managed research project. **You are de facto working on it.**

- **Phase:** INCEPTION
- **Goal:** An AI-ready, API-accessible repository for the search + quant results of the many PRIDE datasets the `aging` pipeline reanalyzes. Humans can use it, but AI agents are the main users. The question it serves is how organelle proteomes change with age.
- **Pick up at:** `datarepo ingest` is **built and run against real data** (PXD036557 → 16 Parquet
  tables, 4.1 MB, ~10 s). Reference: `docs/ingest.md`; contract locked as D9. Thread 007 is posted to
  aging with DATAREPO-11..14 and is awaiting reply — nothing is blocked, every one has a default in
  the code. Next: **`datarepo build`** (FRAMEWORK step 2, the DuckDB catalog). Then pin the QPX
  version (G13), and re-map `design/SCHEMA_COVERAGE.md` against what the ingester actually fills.
  D1–D9 are locked.
- **GitHub:** public at https://github.com/trishorts/dataRepo (`origin`, branch `master`). The user created it on 2026-09-19, which closed G8.
- **Every question for the user goes in `design/OPEN_QUESTIONS.md`** (D7), with a default. They take it to NCEMS and working-group meetings. Work proceeds on the defaults.
- **The benchmark questions belong to aging** (D6). Don't write domain questions here.

## Things that will bite you here

- **After editing `.project/state.yaml`, parse it:** `python -c "import yaml;yaml.safe_load(open('.project/state.yaml',encoding='utf-8'))"`. A broken file makes render_resume silently count 0 gaps. It happened on 2026-09-19.
- **Schema edits need TWO regenerations:** `python tools/build_docs.py` **and** `python tools/build_tables.py`
  (the ingester's Arrow schemas), or CI fails on drift. If the change affects what the ingester writes,
  also `python tools/build_example_bundle.py`. Lint with `--config .linkmllint.yaml`: enum values like
  DDA and TMT are kept on purpose. LinkML isn't installed globally; use `pip install -r requirements-dev.txt`
  in a venv.
- **pyMzLib ships no built bridge here.** It is installed from the worktree
  `E:\GitClones\_wt_pymzlib_585`, so set `PYMZLIB_BRIDGE` to
  `pkg/bridge/bin/Release/net10.0/win-x64/mzlib-bridge.exe` under it, or every `.psmtsv` read
  fails. `datarepo doctor` reports this, and the `.psmtsv` tests skip rather than fail without it.
- **Parsing producer formats is pyMzLib's job.** Where the ingester reads one itself the reason is in
  `src/datarepo/readers.py` and in each bundle's reader log, with the request that lets it be deleted
  (G14). Don't add an in-house parser for a format pyMzLib covers.
- **PowerShell `Set-Content -Encoding utf8` writes a BOM,** and linkml-validate then rejects the file (the first key reads as `ï»¿datasets`). Write YAML fixtures with the Write tool or `[IO.File]::WriteAllText` using UTF-8 without a BOM.
- **Thread messages are never edited after posting.** Put a message in both `aging/design/threads/dataRepo/` and `design/threads/aging/`, commit each copy alone in its own repo, and push aging.

- **FRAMEWORK.md is still mostly a proposal.** Its step 1 (ingest) is built and its contract is locked as D9; steps 2-6 (DuckDB catalog, client/MCP, REST, deploy, auto-ingest) are not decided, so don't build on them as if they were.
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
