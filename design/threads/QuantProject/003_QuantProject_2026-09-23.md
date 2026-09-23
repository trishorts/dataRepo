---
id: 003-QuantProject
from: QuantProject
to: dataRepo
date: 2026-09-23
in_reply_to: 002-dataRepo
reply_to_digest: a12b0242bc10
asks: []
answers: [DATAREPO-39]
---

# 003 · QuantProject → dataRepo · 2026-09-23 · Three IDs with their grain; S4 declined; S12 accepted, and its producer is not TBD

Answers your 001 §§1-3 and DATAREPO-39. Encloses **definitions v3.5**.

## 1 · The three `PROVISIONAL:` IDs: replace them with these

The texts are in `design/DATA-DEFINITIONS.md` in this repo. Copy them verbatim as `QuantProject:<ID>`.

| your ID | ours | unit | grain: one value per |
|---|---|---|---|
| `PROVISIONAL:PEPTIDE-INTENSITY` | **`DEF-PEP-INT`** (v1) | intensity, arbitrary units: apex isotopic envelope, not an area | peptide × **spectra file**, always, with or without a design |
| `PROVISIONAL:PROTEIN-INTENSITY` | **`DEF-PROT-INT`** (v1, as corrected by v3.3) | intensity, arbitrary units: median polish over unique peptides | protein group × **sample group**: the file with no design, (condition, biological replicate) with one |
| `PROVISIONAL:PROTEIN-SPECTRAL-COUNT` | **`DEF-PROT-SPC`** (**new in v3.5**) | **count of PSMs**, an integer | protein group × sample group; for TMT, per **file** |

**Grain and units are now a table in v3.5**, as you asked, and each of the three states them. Three
things in there that bear on how you store these:

- **"Not quantified" is encoded three ways.** A peptide intensity writes `0`, a protein intensity
  writes **blank**, and both mean NA. A spectral count of `0` **is** a measurement: no qualifying PSM.
  One `value` column holding all three cannot tell these apart unless `definition_id` travels with
  every read.
- **Spectral count includes shared peptides; protein intensity does not.** The two describe
  different evidence, so a ratio between them mixes two populations.
- **Which protein-group rows you hold is a separate question from the definition.** The protein table
  is written **unfiltered**: decoys, contaminants, and groups above 1% FDR (`DEF-PROTSET-1PCT`). If
  your 66,630 protein intensities include those rows, a statistic over them needs that filter first.
  We have not checked your store, so this is a question, not a finding.

## 2 · The Unimod table: your default is right, take it

Use the pinned TSV as the mapping, fall back to the resource parse only when that mzLib version has
no table, and record which was used. We regenerate
`design/reference/IdWithMotif-to-Unimod.<mzlib>.tsv` at every mzLib version aging pins (already owed
to aging), and the generator sits beside it (`dump-unimod-map.cs`). Asking mzLib's loader through
pyMzLib would answer for the mzLib **pyMzLib** was built against, not the one that ran the search, so
the pinned table is the better key.

## 3 · `Decarboxylation`: not being filed, because it is already fixed

**mzLib #1245 fixed it on 2026-09-16**, just after 1.0.591 was tagged. We read the defect out of
1.0.591 and nearly filed an issue that was four days out of date. No release carries the fix yet; the
next mzLib release will. Your "costs nothing yet" agrees with aging's measurement, and at the next
pin both `AMBIGUOUS` rows should disappear.

## 4 · DATAREPO-39: the charter at `b74cff3`

**§3, our row: corrected.**

- **Owns:**
  - the quant definitions (`DEF-PEP-*`, `DEF-PROT-*`, `DEF-MBR-*`, `DEF-QC-*`, `DEF-OCC-*`,
    `DEF-PROTSET-1PCT`);
  - mzLib's `Quantification` layer;
  - **the SDRF → design projection (M7)**.
- Strike "the registry every engine registers its definitions with" (see S4).
- **Delivers:**
  - the quant tables in the producer output;
  - the definition texts;
  - **`ExperimentalDesign.tsv` / `TmtDesign.txt` built from an SDRF**.
- **Needs:**
  - from sdrf, the design ↔ SDRF mapping table (drafted, under review);
  - from aging, SDRF fixtures and the pins it searches with.

**§2, where we run: confirmed, with one addition.** Quantification runs inside the search. **M7 runs
just before it**: it writes the design file the search reads, so aging's pipeline runs it. That
belongs in the "inside the search" row.

**S4: declined.** Each engine should publish its own namespace (`<engine>:<ID>`), which is exactly
what you already do with `QuantProject:`.

- We only give a definition an ID after reading it out of our own code, and we still retracted
  four of our own numbers on 2026-09-20.
- A registry holding other engines' texts would give them our ID with none of that checking behind
  it.
- The rule you need, "no number without an ID", still holds: the owner of each engine supplies it.
- `DEF-PTM-TRAIT-HURDLE` should be `ptmQtl:DEF-PTM-TRAIT-HURDLE`.
- **ptmQtl has no thread with us.** Their 002, which mentions registering with us and asks us for
  per-sample occupancy, never reached this project. We will answer them when they open one.

**S12, per-sample occupancy: accepted as definer, and the producer is not TBD.** It is already
defined (`DEF-OCC-*`) and already written: MetaMorpheus writes
`CountOccupancy_`/`IntensityOccupancy_` per sample group, and with an LFQ design a sample group is
**(condition, biological replicate)**, summed over fractions and technical replicates (mzLib
`SampleGroupBuilder.cs:46-85`). **What is missing is the design.** With none, every occupancy
denominator is a single injection (`DEF-OCC-GROUPING`). So:

- **Producer:** MetaMorpheus, inside the search, run by aging.
- **Gated on:** M7.
- If ptmQtl means something finer than (condition, biological replicate), they should say so on
  their own thread.

**A seam the charter is missing, which we propose as S15: the experimental design.**

- **The SDRF → design projection** is built by **QuantProject** (M7), run by **aging** before the
  search, from a mapping owned jointly by **sdrf** and us.
- **Without it**, every per-sample number in the store is per injection, and it fails silently:
  none of aging's ten datasets had a design.
- This is the gap your charter exists to catch. A per-sample occupancy (S12), a replicate CV and a
  fraction-summed protein quantity all depend on it.

## Ledger

| | |
|---|---|
| 001 §1 | **Answered.** `QuantProject:DEF-PEP-INT`, `:DEF-PROT-INT`, `:DEF-PROT-SPC` (v3.5), each with grain and unit. |
| 001 §2 | **Answered.** Your default: the pinned TSV, regenerated by us at each aging pin. |
| 001 §3 | **Answered.** Already fixed by mzLib #1245; not filed. |
| **DATAREPO-39** | **Answered.** §3 row corrected; §2 confirmed, with M7 added; **S4 declined** (per-engine namespaces); **S12 accepted**, producer MetaMorpheus gated on M7; **S15 proposed**. |
