"""Write an immutable Parquet bundle for one dataset.

Layer 1 of the architecture: the files are the product (FRAMEWORK section 2). One directory per
dataset-run, one Parquet file per table, the producer's own metadata files copied in beside them,
and a `bundle.json` that says exactly which inputs produced it and what came out.

The directory name is a content hash, so re-ingesting unchanged inputs with an unchanged ingester
lands on the same path and re-ingesting changed ones cannot quietly overwrite a bundle somebody
already cited.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from . import __version__
from ._tables import SCHEMA_VERSION, TABLES
from .errors import IngestError
from .integrity import check as check_integrity

#: QPX release these column names are written against (D4). Provisional until the mapping is
#: checked against a pinned QPX release; tracked as gap G13.
QPX_VERSION = "unpinned"

#: The version of the INGEST PATH, and the only version in a bundle's content hash.
#:
#: Deliberately not `__version__`. A bundle id has to mean "these are the same measurements" (aging
#: 019 section 1), so it must move when this ingester reads a file differently or writes a different
#: row -- and must NOT move because something elsewhere in the package changed. 0.6.0 added the
#: study layer, which `build` creates and `ingest` never writes; bumping the package version would
#: have re-identified every bundle in every store for rows that are byte-identical.
#:
#: **Bump this in the same commit as any change to what an ingest reads, parses, derives or
#: writes.** It lags `__version__` on purpose; they are not meant to agree. The catalog's equivalent
#: is `catalog.CATALOG_VERSION`, and `catalog_id` carries `__version__` as well because a catalog is
#: rebuilt cheaply and a bundle is not.
INGESTER_VERSION = "0.14.0"

BUNDLE_MANIFEST = "bundle.json"
SOURCES_DIR = "sources"


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file, streamed."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def _to_date(value: Any) -> dt.date | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value)[:10])


def _to_timestamp(value: Any) -> dt.datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, dt.datetime):
        stamp = value
    else:
        stamp = dt.datetime.fromisoformat(str(value))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return stamp.astimezone(dt.timezone.utc)


def _coerce(value: Any, field_type: pa.DataType) -> Any:
    """Bend one Python value into the column's declared type, or leave it null.

    Empty strings become nulls on purpose: a missing measurement is NA, never 0 and never "".
    """
    if value is None:
        return None
    if pa.types.is_list(field_type):
        if isinstance(value, str):
            value = [value] if value else []
        return [_coerce(v, field_type.value_type) for v in value] or None
    if isinstance(value, str) and not value.strip():
        return None
    if pa.types.is_date(field_type):
        return _to_date(value)
    if pa.types.is_timestamp(field_type):
        return _to_timestamp(value)
    if pa.types.is_boolean(field_type):
        if isinstance(value, str):
            return value.strip().lower() in {"true", "yes", "1", "y", "t"}
        return bool(value)
    if pa.types.is_integer(field_type):
        return int(float(value))
    if pa.types.is_floating(field_type):
        number = float(value)
        return None if number != number else number  # NaN is absence, so store it as null
    return str(value)


def rows_to_table(label: str, schema: pa.Schema, rows: Sequence[dict[str, Any]]) -> pa.Table:
    """Build an Arrow table from row dicts against any schema, in the schema's column order.

    Split out from `table_from_rows` so a study layer's tables are written through exactly the same
    coercion and the same two refusals as the core's. A study layer that validated its own rows
    more loosely would be the interesting failure: `aging:DEF-AGE-EFFECT v1` puts its rules in the
    shape -- a `beta` without an `se` is not an age effect -- and the shape only enforces them if
    the writer refuses the null.

    Args:
        label: what to call the table in an error, e.g. `age_effects` or `aging.age_effects`.
        schema: the Arrow schema to write against.
        rows: row dicts keyed on column names.

    Raises:
        IngestError: a row carries a key the table has no column for, or a required column is null.
    """
    columns: dict[str, list[Any]] = {f.name: [] for f in schema}
    known = set(columns)
    for index, row in enumerate(rows):
        extra = set(row) - known
        if extra:
            raise IngestError(f"table {label}: row {index} has unknown columns {sorted(extra)}")
        for f in schema:
            value = _coerce(row.get(f.name), f.type)
            if value is None and not f.nullable:
                raise IngestError(
                    f"table {label}: row {index} has no value for required '{f.name}'"
                )
            columns[f.name].append(value)
    return pa.table({f.name: pa.array(columns[f.name], type=f.type) for f in schema}, schema=schema)


def table_from_rows(name: str, rows: Sequence[dict[str, Any]]) -> pa.Table:
    """Build an Arrow table for the core schema table `name` from row dicts."""
    return rows_to_table(name, TABLES[name], rows)


@dataclass
class BundleWriter:
    """Collect tables and source files, then write them under a content-addressed directory.

    Args:
        store: the instance's bundle store, e.g. `F:/aging_data/repo/store`.
        dataset_id: ProteomeXchange accession.
    """

    store: Path
    dataset_id: str
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    sources: list[dict[str, Any]] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)
    _copied: list[tuple[Path, str]] = field(default_factory=list)

    def add(self, table: str, rows: Iterable[dict[str, Any]]) -> None:
        """Append rows to a table. Unknown table names fail loudly, not silently."""
        if table not in TABLES:
            raise IngestError(f"no table named '{table}' in schema {SCHEMA_VERSION}")
        self.tables.setdefault(table, []).extend(rows)

    def add_source(self, path: Path, role: str, copy_as: str | None = None) -> dict[str, Any]:
        """Record an input file by hash, and optionally copy it into the bundle.

        Args:
            path: the producer's file.
            role: what it was read for, e.g. `provenance:search`.
            copy_as: name inside the bundle's `sources/` directory; None to record without copying.

        Returns:
            The recorded entry, whose `sha256` and `bundle_path` the tables can point at.
        """
        entry = {
            "role": role,
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        if copy_as:
            entry["bundle_path"] = f"{SOURCES_DIR}/{copy_as}"
            self._copied.append((path, copy_as))
        self.sources.append(entry)
        return entry

    def add_hashed_source(self, path: Path, role: str, sha256: str) -> dict[str, Any]:
        """Record an input file whose sha256 the caller has already computed, without copying it.

        For a protein database: 1 GB, hashed once to check it against the search provenance, and
        never copied into a bundle -- it is the producer's input, archived with their release (D8).
        """
        entry = {"role": role, "path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256}
        self.sources.append(entry)
        return entry

    def add_declaration(self, role: str, payload: Any) -> dict[str, Any]:
        """Record a non-file input that shapes the bundle, so it lands in the content hash.

        Not every input is a file on disk. The producer's manifest entry supplies the dataset's
        title and its organism, acquisition, quant_method, labelling and enrichment axes, and those
        go straight into the `datasets` row -- so a bundle built from an edited manifest holds
        different content. Hashing only the files would leave that change invisible, which is the
        one thing content addressing exists to prevent.

        The entry is hashed rather than the manifest file: the file describes every dataset, and an
        unrelated entry's edit must not churn this bundle's id.
        """
        canonical = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
        entry = {
            "role": role,
            "path": f"<{role}>",
            "kind": "declaration",
            "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        }
        self.sources.append(entry)
        return entry

    @property
    def bundle_id(self) -> str:
        """Content hash of the inputs, the schema and the ingest path.

        Same inputs and same ingest path give the same bundle directory; any change to either gives
        a new one. That is what makes a released bundle safe to cite -- and why the version here is
        `INGESTER_VERSION` rather than the package's, which moves for reasons a bundle cannot see.
        """
        digest = hashlib.sha256()
        digest.update(f"datarepo/{INGESTER_VERSION}\nschema/{SCHEMA_VERSION}\n{self.dataset_id}\n".encode())
        for entry in sorted(self.sources, key=lambda e: (e["role"], e["path"])):
            digest.update(f"{entry['role']}\t{entry['sha256']}\n".encode())
        return digest.hexdigest()[:16]

    def path(self) -> Path:
        return self.store / self.dataset_id / self.bundle_id

    def write(self, *, overwrite: bool = False) -> Path:
        """Write every table, copy the recorded sources, and emit `bundle.json`.

        Raises:
            IngestError: the bundle directory already holds a manifest and `overwrite` is False,
                or a reference between the tables does not resolve.
        """
        out = self.path()
        manifest_path = out / BUNDLE_MANIFEST
        if manifest_path.exists() and not overwrite:
            raise IngestError(
                f"{out} already exists. The inputs and the ingester are unchanged, so this bundle "
                f"is already written; pass --overwrite to rebuild it in place."
            )
        problems = check_integrity(self.tables)
        if problems:
            raise IngestError(
                "the bundle's own tables do not hold together, so nothing was written:\n  - "
                + "\n  - ".join(problems)
            )

        (out / SOURCES_DIR).mkdir(parents=True, exist_ok=True)

        row_counts: dict[str, int] = {}
        for name in TABLES:
            rows = self.tables.get(name)
            if not rows:
                continue
            table = table_from_rows(name, rows)
            pq.write_table(table, out / f"{name}.parquet", compression="zstd")
            row_counts[name] = table.num_rows

        for src, copy_as in self._copied:
            shutil.copy2(src, out / SOURCES_DIR / copy_as)

        manifest = {
            "bundle_id": self.bundle_id,
            "dataset_id": self.dataset_id,
            "schema_version": SCHEMA_VERSION,
            "qpx_version": QPX_VERSION,
            # Both versions, because they answer different questions: `version` is what an
            # operator installed, `ingest_path` is what the bundle id was computed from.
            "ingester": {
                "name": "datarepo",
                "version": __version__,
                "ingest_path": INGESTER_VERSION,
            },
            "written_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "tables": row_counts,
            "sources": self.sources,
            **self.notes,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        return out
