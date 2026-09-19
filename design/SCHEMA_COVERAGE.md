# Schema coverage: aging's benchmark against schema v0 (2026-09-19)

**What this checks.** For every question in `aging/design/QUESTIONS.md` **v0.3** (aging owns it, D6; not copied here), it asks whether schema v0 has somewhere to put the answer. This is FRAMEWORK roadmap step 0: "every question maps to tables/columns". It is **not** a test of the agent tools. That comes at step 3.

**Status**
- **✓** The schema holds it, and aging's current output (human DDA label-free) fills it at ingest.
- **◐** The schema holds it, but a producer hasn't made the data yet. The producer is named in the row.
- **✗** Nothing in the schema holds it. The owner is named in the row.
- **—** Out of v1.

**Table names:** `core` means `schema/datarepo.yaml`. *Italic* tables are in the aging study layer (`schema/study/aging.yaml`).

## Result

| | ✓ | ◐ | ✗ | — | Total |
|---|---|---|---|---|---|
| All 168 | 70 | 94 | 2 | 2 | 168 |
| Top 10 | 4 | 6 | 0 | 0 | 10 |

**Only two questions have no home in the schema:**
- **J12** needs a literature-claim table. Nobody owns it yet; it goes to aging.
- **P2** needs aging's mass-shift histogram (R12). It isn't a table, so the proposal is to store it as a file in the release bundle.

**Mapping the questions changed schema v0.** The fixes are listed at the end. Without them, 2 of the top 10 (K1, O1) and 12 other questions would have failed.

**Why ◐ dominates:** most of the ◐ rows wait on the same four producers.
- **aging stage 7** (*AgeEffect*, *OrganelleAgeSummary*): blocked on the design file (QuantProject M7).
- **go's organelle map and annotations**: `ProteinLocalization` and `ProteinAnnotation` (R5, R6).
- **MetaMorpheus stoichiometry and glyco output**: R7 and R16.
- **aging's census and reference panels**: R1 and R8.

## Top 10

| # | Tables · columns | St | Waiting on |
|---|---|---|---|
| K1 | PtmStoichiometry · *AgeEffect* (feature_type=ptm_site, **response**=modified_fraction) next to *AgeEffect* (protein_group, response=abundance) | ◐ | R7 MetaMorpheus; aging stage 7 |
| D2 | *OrganelleAgeSummary* (compartment, estimate, response) | ◐ | aging stage 7; go |
| O1 | Protein (**source_db**=progerin DB) · Peptidoform (protein_accessions, is_isoform_specific) · Sample (condition) | ✓ | |
| D1 | *AgeEffect* · ProteinLocalization · Sample (organism_part) · Dataset | ◐ | aging stage 7; go |
| T2 | Glycopeptide (glycan_composition) · QuantValue (glycopeptide) · *AgeEffect* · Sample | ◐ | R16 glyco search; stage 7 |
| N1 | *ClockModel* (feature_level, cv/held-out MAE) · *ClockFeature* | ◐ | R9 aging |
| M1 | PtmSite · ProteinAnnotation (key=ELLP / half_life) | ◐ | R6 go |
| C1 | Protein · ProteinGroup · QuantValue (protein_group) · Assay → Sample · *SampleAge* | ✓ | |
| G1 | Finding (code, severity, status, source) · Definition | ✓ | |
| J16 | ProteoformInference (**sites_on_one_peptide**, inference_confidence) · Peptidoform · PtmSite | ✓ | (ProteoformInference rows wait on R7b; the Peptidoform check works today) |

## All questions

| # | Tables · columns | St | Waiting on / note |
|---|---|---|---|
| A1 | Dataset · Sample · *SampleAge* | ✓ | |
| A2 | Sample (organism_part) | ✓ | |
| A3 | *SampleAge* · Sample | ✓ | |
| A4 | *SampleAge* (NA) · Finding | ✓ | |
| A5 | Metric (scope=dataset, definition_id) · Psm · Peptidoform · ProteinGroup | ✓ | |
| A6 | DatasetCandidate | ◐ | R1 aging census |
| A7 | Release · ReleaseChange | ◐ | dataRepo's own first release |
| A8 | Dataset (acquisition, quant_method, organisms, axis_source) | ✓ | axis_source=discover until DATAREPO-2 |
| A9 | Dataset (enrichment) | ◐ | aging provenance axes (DATAREPO-2); discover fallback |
| A10 | Dataset (labelling) | ◐ | same |
| A11 | Dataset · DatasetCandidate | ◐ | R1 |
| B1 | *SampleAge* · Sample | ✓ | |
| B2 | *SampleAge* (age_raw, age_years, normalizer_version) | ✓ | |
| B3 | *SampleAge* (age_is_lower_bound) | ✓ | |
| B4 | Sample (sex) · *SampleAge* | ✓ | |
| B5 | Sample (disease) | ✓ | |
| B6 | *AgeMapping* | ◐ | R4 aging stage 7 |
| B7 | Sample (condition) | ✓ | |
| B8 | Sample (**material_type**, **cell_line**, cell_type) | ✓ | |
| B9 | *SampleAge* | ✓ | |
| B10 | *SampleAge* | ✓ | |
| B11 | Sample (**individual_id**, timepoint) | ◐ | R10 sdrf curation |
| C1 | see top 10 | ✓ | |
| C2 | *AgeEffect* (per dataset) | ◐ | stage 7 |
| C3 | *AgeEffect* · Sample | ◐ | stage 7 |
| C4 | Peptidoform (protein_accessions, is_unique) · QuantValue | ✓ | |
| C5 | QuantValue (detection_type, **mbr_kept**, pip_q_value) | ✓ | |
| C6 | QuantValue (absent row = missing) · Assay | ✓ | |
| C7 | Peptidoform (is_isoform_specific) · Protein (canonical_accession) | ◐ | R11 mzLib uniqueness; isoform DB (aging D8, G13) |
| C8 | Protein (**is_contaminant**) · Psm (target_decoy) · Finding | ✓ | |
| C9 | ProteinLocalization (source_id) | ◐ | go |
| C10 | QuantValue · Assay → Sample · *SampleAge* | ✓ | |
| C11 | *AgeEffect* · Sample | ◐ | stage 7 |
| C12 | FeatureSet (ProtAge) · FeatureSetMember | ◐ | R8 aging panels |
| C13 | FeatureSet · *AgeEffect* | ◐ | R8; stage 7 |
| C14 | FeatureSet (SASP) · *AgeEffect* | ◐ | R8; stage 7 |
| D1 | see top 10 | ◐ | |
| D2 | see top 10 | ◐ | |
| D3 | *AgeEffect* · ProteinLocalization (GO-CC sub-terms) | ◐ | stage 7; go |
| D4 | *AgeEffect* · ProteinLocalization · Sample | ◐ | stage 7; go |
| D5 | *OrganelleAgeSummary* (organism_part) | ◐ | stage 7; go |
| D6 | ProteinLocalization · ProteinGroup | ◐ | go |
| D7 | ProteinLocalization (source_id) · *AgeEffect* | ◐ | go; stage 7 |
| D8 | *OrganelleAgeSummary* (model_definition_id) · Definition | ◐ | stage 7 |
| D9 | *AgeEffect* (model_definition_id = organelle-normalized) | ◐ | QuantProject definition (R7b) |
| D10 | *AgeEffect* · ProteinLocalization · ProteinAnnotation (half_life) | ◐ | R6 go |
| D11 | AnnotationSource (version) · Definition | ◐ | go |
| D12 | ProteinAnnotation (genome_of_origin) · *AgeEffect* | ◐ | R6 go |
| D13 | *AgeEffect* (a model with sex) · Sample (sex) | ◐ | stage 7 |
| D14 | *OrganelleAgeSummary* (**organism**) · ProteinAnnotation (ortholog) | ◐ | R5 go; stage 7 |
| D15 | *AgeEffect* · ProteinLocalization · ProteinAnnotation (GO-BP) | ◐ | go; stage 7 |
| D16 | *AgeEffect* · ProteinAnnotation (complex) | ◐ | R6 go |
| D17 | ProteinLocalization · ProteinGroup · Dataset | ◐ | go |
| D18 | *AgeEffect* · Sample (condition) · ProteinLocalization | ◐ | stage 7; go |
| D19 | *AgeEffect* · ProteinLocalization | ◐ | stage 7; go |
| E1 | PtmStoichiometry · *AgeEffect* (response) | ◐ | R7 |
| E2 | Psm · PtmSite · Sample · Run (**acquisition_datetime**) | ✓ | |
| E3 | Psm · PtmSite · SearchModification | ✓ | |
| E4 | Peptidoform · PtmSite · ProteoformInference | ✓ | inferred forms wait on R7b |
| E5 | PtmSite (localization_score) · Psm | ✓ | |
| E6 | PtmSite · *AgeEffect* | ◐ | stage 7 |
| E7 | Definition (TMT quant model) · Dataset (labelling) | ◐ | QuantProject TMT model; TMT data |
| E8 | Peptidoform · Dataset | ✓ | |
| F1 | Psm (usi) → PROXI | ✓ | |
| F2 | Psm (usi, q_value, score) | ✓ | |
| F3 | Psm | ✓ | |
| F4 | QuantValue → Assay → Run · Psm (scan) | ✓ | |
| F5 | Psm (bulk Parquet) | ✓ | |
| F6 | Run (sha256, pride_checksum_sha1) | ✓ | |
| F7 | Psm (**matched_ion_series**, **matched_ion_count**, localization_score) | ✓ | partial: full evidence is R14 (pyMetaMorpheus) |
| G1 | see top 10 | ✓ | |
| G2 | ProvenanceRecord (tools_json, **params_json**) · Dataset (search_engine_version, **search_database**) | ✓ | |
| G3 | Metric (scope=run, name=id_rate) · Run | ✓ | |
| G4 | Metric (both counts side by side, each with definition_id and source) | ✓ | the *answer* waits on S21 |
| G5 | Finding | ✓ | |
| G6 | Definition (via *AgeEffect*.model_definition_id) | ◐ | stage 7 |
| G7 | ProvenanceRecord (pipeline_commit, params_json, original_path) | ✓ | |
| G8 | Metric (contaminant share, DEF-QC-9 / DEF-CONTAM-PSM) | ✓ | if aging emits the metric |
| G9 | ProvenanceRecord (**wall_seconds**, **peak_rss_gib**, **resources_json**) | ✓ | |
| G10 | Dataset (**search_database**, **search_database_sha256**, organisms) | ✓ | |
| H1 | *AgeEffect* (per dataset; I² computed at query time) | ◐ | stage 7 |
| H2 | *AgeEffect* (recompute) | ◐ | stage 7 |
| H3 | *AgeEffect* (q_value) | ◐ | stage 7 |
| H4 | Run (**instrument_model**, **acquisition_datetime**) · SampleCharacteristic (batch) | ✓ | |
| H5 | Sample · *SampleAge* | ✓ | |
| H6 | *AgeEffect* · Dataset (quant_method) | ◐ | stage 7; TMT data |
| H7 | *AgeEffect* (non-linear model_definition_id) | ◐ | stage 7 |
| H8 | QuantValue (mbr_kept) · *AgeEffect* (two models) | ◐ | stage 7 |
| I1 | ProteinAnnotation (ortholog) · *AgeEffect* | ◐ | R5 go |
| I2 | QuantValue · Dataset (acquisition) | ◐ | DIA data from aging |
| I3 | *AgeEffect* · Definition | ◐ | DIA data; stage 7 |
| I4 | Sample (condition) · Dataset (organisms) | ◐ | rodent data from aging |
| I5 | Dataset (instrument_vendor, acquisition) | ✓ | |
| I6 | ProteinAnnotation (complex, ortholog) · *AgeEffect* | ◐ | R5, R6 go |
| J1 | Definition | ✓ | |
| J2 | Definition (quant value meaning) | ✓ | |
| J3 | Definition | ✓ | |
| J4 | QuantValue (absent = missing) · Definition | ✓ | |
| J5 | *SampleAge* (age_is_lower_bound) | ✓ | |
| J6 | Sample · *AgeEffect* | ◐ | stage 7 |
| J7 | Definition · *ClockModel* (absence) | ✓ | |
| J8 | SearchModification · Definition | ✓ | |
| J9 | Glycopeptide (glycan_composition, never structure) | ◐ | R16 |
| J10 | Dataset (labelling) · Definition | ✓ | |
| J11 | Dataset | ✓ | |
| J12 | none | ✗ | literature-claim table; no owner (aging to route) |
| J13 | Dataset (enrichment) · PtmStoichiometry | ◐ | DATAREPO-2; R7 |
| J14 | Psm · Run (acquisition_datetime) · Sample | ✓ | |
| J15 | Peptidoform (is_isoform_specific) · ProteinGroup | ✓ | |
| J16 | see top 10 | ✓ | |
| J17 | PtmSite · SearchModification (fixed carbamidomethyl) · ProvenanceRecord (params_json) | ✓ | |
| K1 | see top 10 | ◐ | |
| K2 | PtmStoichiometry · ProteinLocalization | ◐ | R7; go |
| K3 | Psm · PtmSite · SearchModification | ✓ | |
| K4 | FeatureSet (sirtuin substrates) · PtmSite | ◐ | R8 |
| K5 | ProteoformInference · QuantValue (proteoform) · *SampleAge* | ◐ | R7b MetaMorpheus/mzLib |
| K6 | Peptidoform · ProteinLocalization · Sample | ◐ | go |
| K7 | *AgeEffect* (feature_type) | ◐ | stage 7 |
| K8 | PtmSite · *AgeEffect* | ◐ | stage 7 |
| K9 | PtmSite · *AgeEffect* | ◐ | stage 7 |
| K10 | PtmSite · *AgeEffect* | ◐ | stage 7 |
| K11 | PtmSite · FeatureSet (PRMT1 substrates) | ◐ | R8 |
| K12 | ProteinGroup (sequence_coverage) · PtmSite · Psm | ✓ | |
| K13 | *AgeEffect* × 2 per site (response=modified_fraction and =abundance) | ◐ | R7; stage 7 |
| K14 | PtmStoichiometry · ProteinLocalization · *AgeEffect* | ◐ | R7; go |
| K15 | PtmStoichiometry (n_modified/n_unmodified, uncertainty, definition_id) | ◐ | R7 |
| K16 | PtmStoichiometry · Dataset (enrichment) | ◐ | R7; DATAREPO-2 |
| K17 | PtmSite (UNIMOD GG) · PtmStoichiometry · FeatureSet | ◐ | R7; R8 |
| L1 | PtmSite · ProteinAnnotation (half_life) · *AgeEffect* | ◐ | R6 |
| L2 | ProteinAnnotation (**position**, key=predicted_deamidation_rate) | ◐ | R13, owner open |
| L3 | Psm (**nonspecific_termini**, start/end_residue) · Sample | ✓ | |
| L4 | PtmSite · *AgeEffect* | ◐ | stage 7 |
| L5 | PtmSite · SearchModification | ✓ | |
| L6 | PtmSite · Run (fraction) · SampleCharacteristic | ✓ | |
| L7 | PtmSite · *AgeEffect* · *ClockModel* | ◐ | stage 7; R9 |
| M1 | see top 10 | ◐ | |
| M2 | ProteinAnnotation (half_life, qualifier) · AnnotationSource | ◐ | R6 |
| M3 | QuantValue · ProteinAnnotation (complex) | ◐ | R6 |
| M4 | *AgeEffect* · ProteinAnnotation (half_life) | ◐ | R6; stage 7 |
| M5 | Dataset (labelling) · Finding | ✓ | axis via discover until DATAREPO-2 |
| N1 | see top 10 | ◐ | |
| N2 | *ClockModel* · ProteinLocalization | ◐ | R9; go |
| N3 | FeatureSet (organ-enriched) · *AgeEffect* | ◐ | R8; stage 7 |
| N4 | *ClockModel* (heldout_datasets) · *AgeEffect* | ◐ | R9 |
| N5 | Sample · *SampleAge* | ✓ | |
| N6 | Sample (condition) · *AgeEffect* | ◐ | stage 7 |
| O1 | see top 10 | ✓ | |
| O2 | Peptidoform · Protein (targeted isoforms) | ◐ | isoform DB selection (aging G13) |
| O3 | Peptidoform (is_unique) · Psm (ambiguity_level) · ProteinGroup | ◐ | R11 mzLib |
| O4 | QuantValue · *AgeEffect* (response=isoform_ratio) | ◐ | stage 7 |
| O5 | PtmSite · Peptidoform (ProForma C-term mod) | ✓ | |
| O6 | FeatureSet (isoform target list) · Dataset (search_database) | ◐ | aging G13 |
| P1 | SearchModification (usage) | ✓ | |
| P2 | none | ✗ | R12 aging mass-shift histogram: propose storing it as a bundle file |
| P3 | DatasetCandidate (exclusion_reason) | ◐ | R1 |
| P4 | Dataset (**sdrf_status**) · ProvenanceRecord | ✓ | |
| Q1 | none | — | out of v1 |
| Q2 | none | — | out of v1 |
| T1 | Glycopeptide | ◐ | R16 |
| T2 | see top 10 | ◐ | |
| T3 | Glycopeptide · PtmStoichiometry · *AgeEffect* (response=glycoform_fraction) | ◐ | R16; R7 |
| T4 | Glycopeptide · *AgeEffect* | ◐ | R16; stage 7 |
| T5 | Glycopeptide (localization_level) | ◐ | R16 |
| T6 | Glycopeptide · PtmSite · ProteinLocalization | ◐ | R16; go |
| T7 | Glycopeptide · *AgeEffect* | ◐ | R16; stage 7 |
| T8 | Glycopeptide (glycan_type=N_and_O) | ◐ | R16 |
| T9 | Glycopeptide · ProteinLocalization · *OrganelleAgeSummary* | ◐ | R16; go; stage 7 |
| T10 | Run (fragmentation) · Dataset (searches) | ✓ | |

## Schema changes this mapping forced (in v0 now; new names in **bold** above)

| Change | Questions it fixed |
|---|---|
| *AgeEffect* and *OrganelleAgeSummary* get `response` (abundance / modified_fraction / isoform_ratio / glycoform_fraction) | **K1**, K13, E1, O4, T3 |
| Protein `source_db` (custom-database entries, e.g. progerin) | **O1** |
| Psm `missed_cleavages`, `nonspecific_termini`, `start_residue`, `end_residue` | L3 |
| Psm `matched_ion_series`, `matched_ion_count` | F7 (in part) |
| New **Metric** table (dataset/run, name, value, definition_id, source) replaces Run's single-definition count columns | A5, G3, G4 (S21), G8 |
| New **SearchModification** table | P1, J8, J17, E3, K3, L5 |
| Dataset `search_database`, `search_database_sha256`, `sdrf_status` | G2, G10, P4 |
| Sample `material_type`, `cell_line`, `individual_id` | B8, B11 |
| Run `instrument_model`, `acquisition_datetime` | H4, J14, E2 |
| Protein `is_contaminant`; QuantValue `mbr_kept` | C8; C5, H8 |
| ProteinAnnotation `position` (residue-level facts) | L2 |
| ProvenanceRecord `params_json`, `wall_seconds`, `peak_rss_gib`, `resources_json` | G2, G7, G9, J17 |
| *OrganelleAgeSummary* `organism`; new *AgeMapping* | D14; B6 |

## For thread 004 to aging

1. **Confirm or replace the study-layer columns.** In particular the `response` vocabulary, and whether stage 7 fits K1/K13 as two *AgeEffect* rows per site.
2. **J12 and P2** have no home. J12 needs a literature-claim table with no owner. P2 needs the R12 histogram; we propose storing it as a file.
3. **Metrics aging should emit, named with definition IDs:** contaminant share (G8) and both PSM counts (S21).
4. **Producer column names for R7 and R16.** They're proposed in the schema from aging 003's list.
