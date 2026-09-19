# Data provenance â€” dataRepo

Every data input is recorded here so the repo is **reproducible-by-reference** even though large raw
files are gitignored. One row per dataset/file (or logical group).

| Dataset | Local path | Source / origin | Repository accession | Acquired | Checksum (SHA-256) | Notes |
|---|---|---|---|---|---|---|
| _example_ | `data/raw/run1.raw` | Smith lab, Velos | MassIVE MSV000000000 | YYYY-MM-DD | `â€¦` | top-down Jurkat |

Rules:
- Raw spectra / databases are **gitignored** â€” this table is their record. Do not commit the bytes.
- Public re-analyses: cite the original accession; deposit new results (see `massive-reanalysis-upload`).
- Fill the checksum at acquisition: `Get-FileHash -Algorithm SHA256 <path>`.

