<!-- Auto-loaded when cwd is inside this project folder. Managed by the /project skill. -->

# Project: dataRepo

This folder is a `/project`-managed research project. **You are de facto working on it.**

- **Phase:** INCEPTION
- **Goal:** An AI-ready, API-accessible repository for the search + quant results of the many PRIDE datasets the `aging` pipeline reanalyzes. Humans can use it, but AI agents are the main users. The question it serves is how organelle proteomes change with age.
- **Pick up at:** Schema v0 is drafted (`schema/datarepo.yaml` core + `schema/study/aging.yaml` stub; see `design/SCHEMA_V0.md`). The benchmark is mapped: `design/SCHEMA_COVERAGE.md` (168 questions: 70 ✓, 94 waiting on a producer, 2 with no home: J12, P2). Thread 004 (DATAREPO-5..8) is posted; read aging's reply (005+) when it lands. Meanwhile fill in the field descriptions and check the QPX column mapping. Validate with LinkML (`pip install linkml`; `linkml-lint`, `linkml-validate -C Bundle`). D1–D7 are locked.
- **Auto mode blocks `gh repo create --public`.** The user must run it themselves (G8 has the command). Don't retry it.
- **Every question for the user goes in `design/OPEN_QUESTIONS.md`** (D7), with a default. They take it to NCEMS and working-group meetings. Work proceeds on the defaults.
- **The benchmark questions belong to aging** (D6). Don't write domain questions here.

## Things that will bite you here

- **FRAMEWORK.md is a proposal.** Nothing in it is locked (`decisions: []`), so don't build on it as if it were decided.
- **The user is not a server or infrastructure person.** They said "out of my league" and rely on you to explain. Keep choices few and give a recommendation each time.
- **Don't re-own other projects' work.**
  - aging's rule (D1) applies here: the organelle map belongs to `go`, metric definitions (`DEF-*`) to QuantProject, and the age normalizer to sdrf/mzLib.
  - Parse with pyMzLib typed readers where they exist.
  - dataRepo only stores and serves.
- **The .gitignore template ignores `bin/`.** Add a `!/<dir>/bin/` exception before putting code in any bin folder (G4).
- **No GitHub remote exists.** Ask before creating one (G8).

**Sibling project: `E:\CodeReview\aging`** (the NCEMS pipeline). aging *produces* results under
`F:\aging_data\<run>\<PXD>\` with `provenance.json` (schema `aging-provenance/2`). dataRepo *ingests and serves*
them and never re-runs a search. Requests between the two go through aging's thread convention
(`aging/design/threads/`).

**Raw data never goes on E:** (aging D3). The repository's data store lives on F: or on the server.

**At the start of a session (your first response in this folder), render the standard `/project brief`
once.** Format and derivation are in the `project` skill's `references/session-brief.md`. State lives in
`.project/state.yaml`. `RESUME.md` is rendered fresh by `/project`, so do not hand-edit its generated block.

Layout: `design/` `lit/` `code/` (worktrees, gitignored) `data/` (+PROVENANCE) `results/`
`manuscript/` `submission/`. Conventions and dispatch live in the `project` skill.
