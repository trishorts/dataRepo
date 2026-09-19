# What dataRepo must ingest: an inventory of aging pipeline outputs (2026-09-19)

Source: a read-only survey of `F:\aging_data\run_2026-09-18\` and `E:\CodeReview\aging\`.

## Shared across the run

**Discovery output**
- `01_discover\candidates_2026-09-18.tsv` has 1,434 rows. Columns:
  - accession, keep, drop_reason, keywords_hit
  - has_sdrf_file, n_raw_listed, ms2_class
  - instruments, organism_parts, experiment_types, submission_type, title
- `discover_summary.json` counts 1,432 hits, 286 kept and 35 with an SDRF.
- **Mismatch:** these numbers don't agree with the aging threads (589 hits and 88 with SDRF) or with PLAN.md (407 kept).

**Other shared folders**
- `db\`: UniProt human reviewed XML, 1.0 GB, stage `db_prepare`.
- `mm_settings\{1.1.9,1.1.10,1.1.11}\`.

## Per dataset (e.g. `PXD036557_n18`, 18 Thermo QE+ files, label-free)

| Stage | What it produces |
|---|---|
| `02_fetch` | `fetch_manifest.json`: a `files[]` list with pride_size, local_size, pride_checksum (SHA-1), sha256 and category. Also `metadata\<PXD>_community_annotated.sdrf.tsv` and `spectra\*.raw`, which are disposable. |
| `02b_qc` | `qc_report.json`, one entry per raw file: pass, scans, ms2, fraction_orbitrap_hcd, run_minutes, charge_states |
| `04_search_mm1111` | `provenance.json`, the log, `tasks\*.toml`, and `mm\Task1Calibration` (calib mzML, disposable), `Task2Gptmd` (GPTMD database XML, 435 MB) and `Task3SearchTask` |
| `09_cleanup` | `provenance.json` |

## MetaMorpheus files in Task3SearchTask

The row counts below are for the 18-file run.

| File | Rows | Shape |
|---|---|---|
| `AllPSMs.psmtsv` | 42,959 | long, 57 columns (the full list is below the table) |
| `AllPeptides.psmtsv` | 12,654 | the same 57 columns |
| `AllQuantifiedPeaks.tsv` | 74,894 | long, one row per FlashLFQ peak |
| `AllQuantifiedPeptides.tsv` | 5,814 | **wide**: `Intensity_<file>-calib` and `Detection Type_<file>-calib` for each file |
| `AllQuantifiedProteinGroups.tsv` | 2,230 | **wide**: SpectralCount, Intensity, CountOccupancy and IntensityOccupancy for each file. **There is no separate AllProteinGroups.tsv.** |
| `AllPSMs_FormattedForPercolator.tab` | 55,190 | Percolator features |
| `results.txt` | | free text: totals and per-file counts. It reports 26,582 PSMs at 1% FDR, but provenance says 27,958. The gap is unexplained and may be contaminants. |
| `Individual File Results\` | | 6 files per raw file, including `-calib.mzID` |

**The 57 psmtsv columns, in groups**
- **Spectrum:** File Name, Scan Number, Scan Retention Time, Precursor Scan Number, Precursor Charge, Precursor Intensity, Precursor MZ, Precursor Mass
- **Score:** Score, Delta Score, Notch
- **Sequence:** Base Sequence, Full Sequence, Essential Sequence, Ambiguity Level
- **Modifications:** Mods, Mods Chemical Formulas, Missed Cleavages, Monoisotopic Mass, Mass Diff (Da/ppm)
- **Protein:** Accession, Name, Gene Name, Organism Name, Identified Sequence Variations, Splice Sites, Start and End Residues
- **Target/decoy:** Decoy/Contaminant/Target
- **Fragments:** Matched Ion Series, Matched Ion Mass-To-Charge Ratios, Matched Ion Intensities, Matched Ion Counts
- **Localization:** Normalized Spectral Angle, Localization Score
- **FDR:** Cumulative Target, Cumulative Decoy, QValue, QValue Notch, PEP, PEP_QValue

**AllQuantifiedPeaks columns:** File Name, Base Sequence, Full Sequence, Protein Group, Peptide Monoisotopic Mass, MS2 Retention Time, Precursor Charge, Theoretical MZ, Peak intensity, Peak RT Start, Peak RT Apex, Peak RT End, Peak FWHM, Peak Charge, Num Charge States Observed, Peak Detection Type, PIP Q-Value, PIP PEP, PSMs Mapped, Peak Apex Mass Error (ppm), Decoy Peptide, Random RT.

**AllQuantifiedProteinGroups tail columns:** Protein QValue, Best Peptide Score, Best Peptide Notch QValue, Best Peptide PEP, Sequence Coverage (and the variant "with Mods"), Unique Peptides and Shared Peptides.

## provenance.json

Discover and db_prepare still write `aging-provenance/1`. The later stages write `aging-provenance/2`.

**Keys in every stage**
- schema, stage, started_utc/finished_utc
- host, pipeline{repo, commit}
- params_file{path, sha256}, params
- tools
- commands
- upstream[{stage, path, sha256}]
- inputs[] and outputs[], each with {path, root, size_bytes, sha256}
- notes
- roots{work_root}
- resources, with these fields:
  - wall_s, cpu_user_s, cpu_system_s
  - avg_cores_used
  - peak_rss_gib, peak_threads, peak_processes
  - disk I/O, host details
  - timeseries_file, output_bytes

**Keys only in the search stage**
- exit_code, success
- per_task_resources
- id_rate{psms_1pct, ms2, rate}
- mbr{definition: "QuantProject DEF-QC-MBR v1", mbr_rows, mbr_kept, msms_peaks, kept_over_msms}
- **flags[]**: low_id_rate, no_design_file, no_output_sdrf

## What is not produced yet (per the aging plan)

- **Experimental design file:** stage 3 is blocked on QuantProject M7. Every run is flagged `no_design_file`.
- **Output SDRF:** waiting on MetaMorpheus #2816.
- **GO/organelle annotation:** the `go` project owns it (REQ-GO-2..10) and it is still in INCEPTION.
- **Stage-7 statistics:** in R using msqrob2. Per OWNERSHIP, it takes a peptide table with NA rather than 0 and normalizes within each dataset. aging owns it.

## Volumes (from aging `results/SCALING.md`)

- Each ~1.3 GB raw file yields about **27 MB of search output**.
- An 18-file dataset yields about 491 MB, of which about 435 MB is the GPTMD database.
- Only 71–76 of about 2,200 protein groups are quantified in all 18 files, so missingness is severe.
