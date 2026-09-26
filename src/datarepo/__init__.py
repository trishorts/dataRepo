"""dataRepo: ingest and serve reanalyzed public proteomics results.

dataRepo stores and serves; it never re-runs a search (D8). The producing pipeline (`aging`) writes
its results under a work root and describes them in an ingest manifest; `datarepo ingest` turns one
dataset's results into an immutable Parquet bundle that conforms to `schema/datarepo.yaml`.
"""

from __future__ import annotations

__version__ = "0.22.0"

from ._tables import SCHEMA_VERSION, TABLE_CLASS, TABLES
from .errors import (
    DataRepoError,
    DatasetExcluded,
    IngestError,
    ManifestError,
    ReaderUnavailable,
    UnsupportedProvenance,
)

__all__ = [
    "__version__",
    "SCHEMA_VERSION",
    "TABLES",
    "TABLE_CLASS",
    "DataRepoError",
    "DatasetExcluded",
    "IngestError",
    "ManifestError",
    "ReaderUnavailable",
    "UnsupportedProvenance",
]
