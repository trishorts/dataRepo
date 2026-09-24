# Code pins — dataRepo

Worktrees under `code/` are **gitignored**; this file is their record. Pin repo · branch · commit
whenever a worktree is created or advanced.

| repo | worktree | branch | base clone | pinned commit |
|---|---|---|---|---|
| mzLib | `code/mzLib_prE_peaks` | `fix/quantified-peaks-optional-mbr-score` (pushed to `origin` = trishorts/mzLib) | `E:\GitClones\mzLib`, off `upstream/master` 588c2249 | `88610382` — PR E (review fixes on 2026-09-23; first push `ce7578c9`), [smith-chem-wisc/mzLib#1345](https://github.com/smith-chem-wisc/mzLib/pull/1345) |
| mzLib | `code/mzLib_prD_proforma` | `fix/psmtsv-proforma-from-full-sequence` (pushed to `origin` = trishorts/mzLib) | `E:\GitClones\mzLib`, off `upstream/master` 588c2249 | `ebdfa790` — PR D (review fixes on 2026-09-23; first push `7562d4bc`), [smith-chem-wisc/mzLib#1346](https://github.com/smith-chem-wisc/mzLib/pull/1346) |

**Both PRs MERGED into smith-chem-wisc/mzLib master on 2026-09-24 (~00:11 UTC for E, ~00:22 UTC for D),
approved.** The maintainer merged master into each branch first (E head `149c5173`, D head
`163925fd`), so each worktree shows "behind" its remote; nothing of ours is unpushed. Both worktrees
can be retired. No mzLib release carries either yet (1.0.591 is latest).
