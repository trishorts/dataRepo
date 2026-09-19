# Schema v0: what it is and what's still open (2026-09-19)

**Files**
- `schema/datarepo.yaml` is the **core**. It's generic: any bottom-up reanalysis project can use it.
- `schema/study/aging.yaml` is the **aging study layer**. It's a stub: dataRepo proposes it, and aging owns what goes in it.

**Status:** draft. It lints clean (errors: 0) and a small example bundle validates. Nothing is locked, because FRAMEWORK.md (G1) is still a proposal.

## The one rule that keeps the core generic (U5 default)

A study layer **adds tables keyed on core IDs** (`sample_id`, `dataset_id`, `feature_type` + `feature_id`). It never adds columns to a core table. That's why age lives in `SampleAge`, not on `Sample`.

## Core tables (25 classes)

| Group | Tables |
|---|---|
| Releases & catalog | Release, ReleaseChange (R2), DatasetCandidate (census, R1), Dataset |
| Design | Sample, SampleCharacteristic (every SDRF column, verbatim), Run, Assay (run × channel → sample) |
| Identifications | Psm (with USI), Peptidoform, ProteinGroup, Protein |
| PTM / glyco / proteoform | PtmSite, PtmStoichiometry (R7), Glycopeptide (R16), ProteoformInference (R7b) |
| Quant | QuantValue: long, one row per (assay, feature), with a definition_id on every value |
| Stored from owners | AnnotationSource, ProteinLocalization (go), ProteinAnnotation (R5/R6), FeatureSet + FeatureSetMember (R8 panels) |
| Trust | Definition, ProvenanceRecord, Finding |

**The six dataset axes** are real columns on Dataset: organisms, acquisition, quant_method, labelling (+ plex), enrichment and instrument_vendor. `axis_source` records where each value came from. It stays `discover`/`sdrf` until aging's provenance carries the axes (DATAREPO-2).

**Built in for the traps**
- Glycans are stored as **compositions** (J9).
- A proteoform inference carries `sites_on_one_peptide` + `inference_confidence` (J16).
- MBR rows are marked with detection_type.
- There's no 0-for-missing.

## Open (not blocking v0)

1. **QPX column mapping.** The `qpx_view` annotations are at table level only. Next: check the column names against a pinned QPX release and record `qpx_version` (D4).
2. **Producers' column names** for R7 stoichiometry and R16 glycopeptides. MetaMorpheus hasn't published those outputs yet, so the columns here are the ones aging 003 listed.
3. **Study-layer columns.** aging to confirm or replace (SampleAge, AgeEffect, OrganelleAgeSummary, ClockModel/Feature).
4. **PSM count (S21).** `Run.psms_at_1pct` carries a definition_id, so both of aging's numbers can be stored until aging names the canonical one.
5. **Descriptions.** 153 lint warnings are style only, mostly missing field descriptions. Fill them in before the schema docs are served to agents (FRAMEWORK §4 `datarepo_describe`).

## Next step

Map every question in `aging/design/QUESTIONS.md` v0.3 onto these tables (`design/SCHEMA_COVERAGE.md`), starting with the top 10. That is the FRAMEWORK roadmap's step-0 test: "every question maps to tables/columns".
