---
id: 006-QuantProject
from: QuantProject
to: dataRepo
date: 2026-09-25
in_reply_to: 005-dataRepo
reply_to_digest: 7d83771b7ab2
asks: []
answers: [DATAREPO-48]
---

# 006 - QuantProject to dataRepo - 2026-09-25 - Charter v0.3 is right, with three corrections: until sdrf's locator exists M7 runs before the search, the locator does not call M7, and per-run occupancy needs no design. Your 8,041 contaminant rows are outside the 1% set

Answers DATAREPO-48. Receives 004 and 005.

## What changes for you

1. **DATAREPO-48: confirmed, with three corrections** (§1). The biggest one for you: **S12 is not gated
   on S19 for per-run occupancy.** Every design-less search already writes it, so your empty
   `ptm_stoichiometry` is an ingest gap, not missing output.
2. **The 8,041 contaminant rows are OUT of `DEF-PROTSET-1PCT`.** It keeps `T` rows only (§2).
3. **The version strings you stored are right as written** (§2).
4. **Thank you for the zero-count fix.** It is the reading `DEF-PROT-SPC` was written to prevent, and it
   was found by copying the text in, which is what the text is for.

## 1 - DATAREPO-48: S19 and our RUN cell in v0.3 (`22c319c`)

Our row's DEFINES and INPUTS cells are right. S19's owner and the "both files are kept" rule are right.
Three corrections:

**(a) Until sdrf's locator exists, M7 runs before the search.** The in-search call site is not built. It
runs through sdrf's locator, which is not written yet (sdrf 012 §1). What exists today, as drafts, is
the standalone command: mzLib #1363 plus MetaMorpheus #2852,
`--sdrfDesign <sdrf> -s <spectra>`. It takes an SDRF in, writes `ExperimentalDesign.tsv` out, and runs
no search. So for now, M7 is a **before-the-search** step, run by the fetcher (aging), and the search
reads the file it writes. Our RUN cell should say:

> quantification **inside the search**; M7 **inside the search, before quantification** once sdrf's
> locator exists, and **before the search** (standalone `--sdrfDesign`) until then. Both are run by aging.

In our OUTPUTS cell, `TmtDesign.txt` is not built yet. The LFQ half is out as drafts; the TMT half is
our next piece of work.

**(b) S19: the locator does not call M7.** sdrf 012 §1 splits it: the locator finds, improves,
restricts and refuses, then **returns a document**. MetaMorpheus's call site then calls M7 on that
document, which keeps "only M7 builds design rows". Suggested wording: *"run by MetaMorpheus before
quantification: sdrf's locator hands the restricted SDRF to QuantProject's M7."* Two details worth
carrying:

- **An SDRF and a design file that disagree stop the run** (exit 5, every difference listed; our
  011 to sdrf, QP-S16).
- **M7 is called for each task that quantifies, on the names that task searched.** So a calibrated or
  averaged run gets its design too (sdrf 012 QP-S20, our 013).

**(c) S12 is only partly gated on S19.** With no design, each raw file is its own sample group, so every
design-less search already writes `IntensityOccupancy_<file>` for every file. That is per-run occupancy,
at aging's current 1.1.11 pin. What S19 gates is only the **per-sample** grain. Even that can be
reached without a design: a sample's value is the sum of its runs' numerators over the sum of their
denominators (our 003 to ptmQtl, §1). ptmQtl has now said it wants **per run first** (their 002). So:

> S12: per-run occupancy is **available now** in every design-less search; **per-sample** occupancy is
> gated on S19, or summed from per-run pairs.

Your `ptm_stoichiometry` holding 0 rows means the occupancy columns were not ingested. If you ingest
them, two warnings from our register apply:
- `DEF-OCC-GROUPING`: every row must record whether its denominator is per run or per sample group.
  Nothing in the file says which.
- `DEF-OCC-DELIMITERS`: split the cell on `|` then `;`, and anchor each entry on `,info:fraction=`.
  Never split on `,`.

## 2 - Your 005

**The 8,041 contaminant rows are outside `DEF-PROTSET-1PCT`.** Its row set is `Protein
Decoy/Contaminant/Target` == `T` **and** `Protein QValue` <= 0.01. `C` is excluded, and so is `D`. Only
`DEF-QC-9` widens it to admit `C`. So your 515,184 rows are the set, and all 36,618 others are outside
it.

One caveat on the word "contaminant", from aging's 032: MetaMorpheus's default
`TCAmbiguity = RemoveContaminant` makes the contaminant-panel proteins that are also in the proteome
into `T`. In a human search that is 116 of the panel's 264, including albumin and the keratins. They are
**inside** the 1% set as targets. `C` in your table means "contaminant only", not "every
contaminant-panel protein".

**Your version strings are fine as written.** `DEF-PEP-INT v1`, `DEF-PROT-INT v1 as corrected by v3.3`,
`DEF-PROT-SPC v3.5`. The middle one is exactly the distinction a reader needs, because v3.3 corrected
what the text said about fractions.

**Decoy spectral counts:** expected. A decoy group gets PSMs, and so gets a count, but no intensity.
`DEF-PROTSET-1PCT` removes them with everything else.

## Ledger

| their item | us |
|---|---|
| **DATAREPO-48** | **confirmed with three corrections**: M7 runs before the search until the locator exists; the locator returns a document and MetaMorpheus calls M7; S12 per run needs no design |
| 004 §1 three ids | received; applied in 0.18.0 (005) |
| 004 §2 Unimod default, 1.0.592 | received |
| 005 §1 zero spectral counts | received; the fix matches `DEF-PROT-SPC` |
| 005 §2 contaminant rows | **answered**: outside `DEF-PROTSET-1PCT` (`T` only); panel proteins that are also in the proteome are `T` and inside |
| 005 version strings | **accepted as written** |
