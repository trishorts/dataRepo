"""Write a study bundle: the rows a study layer contributes, delivered separately from a search.

This is DATAREPO-20(a). `age_effects` is the output of a modelling stage that runs long after a
search — aging's stage 7 — and it is not in the folder `datarepo ingest` reads, so an age effect
cannot arrive the way a PSM does. It needed its own path, and the path had to satisfy three things
at once:

* **Delivering a model result must never force a re-ingest.** A study bundle is a separate,
  separately content-addressed object. Writing one does not read, touch or re-identify a single
  search bundle, so a re-fit cannot move the id of a bundle somebody has already cited.
* **A study layer adds tables and never alters a core one** (U5). That is true of the file layout
  here as well: the bundle holds only its layer's tables and `build` unions it in beside the core
  rather than into it.
* **The producer declares what they are handing over**, exactly as D9 makes them declare a search.
  The contract is `study.yaml`, and it is deliberately the dumbest one that works: a table per file,
  columns named as the schema names them. dataRepo does not know what shape aging's modelling stage
  writes internally and is not going to guess -- the one thing it insists on is that the rows land
  in the schema the definition was transcribed into, with the definition's rules enforced on the
  way in.

**The default is running ahead of the answer, and that is on purpose (D7).** aging has not yet
replied to thread 022, so this is the default recorded there, built so the tables can stop being
empty. Two things it deliberately does NOT decide, because they are aging's to decide and a check
here would freeze a guess into the data:

* `feature_id` at meta grain is not resolved against anything. DATAREPO-20(c) asks what a feature's
  cross-dataset identity even is, and a foreign key written before that answer would be a guess with
  the authority of a constraint.
* `definition_id` WAS unresolved against anything, and aging asked for the check with a correction
  to its target (their 024 section 2a). Their definitions are not produced by a search and have no
  business in a search bundle, so the core `definitions` table is the wrong register. A delivery
  therefore declares **its own** definitions, and a `definition_id` that is not among them refuses
  the write: a number whose definition id is unresolvable is the exact failure the register exists
  to prevent, and they would rather the write failed than the row landed.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

import yaml

from . import __version__
from ._tables import SCHEMA_VERSION, STUDY_TABLES, STUDY_VERSIONS
from .bundle import rows_to_table, sha256_file
from .errors import IngestError, ManifestError
from .integrity import STUDY_COMPOSITE_IDENTIFIERS

SUPPORTED_STUDY_MANIFEST_VERSIONS = {1}

#: The version of the STUDY INGEST PATH, and the only version in a study bundle's content hash.
#:
#: Same rule as `bundle.INGESTER_VERSION` and for the same reason: a study bundle id has to mean
#: "these are the same model results". Bump it in the same commit as any change to what this module
#: reads, parses, coerces or writes. It is separate from the ingester's because the two paths move
#: independently -- a change to how a `.psmtsv` is parsed says nothing about a delivered age effect.
STUDY_INGESTER_VERSION = "0.5.0"

STUDY_BUNDLE_MANIFEST = "study.json"

#: Where study bundles live inside the instance's store: `<store>/_study/<layer>/<bundle id>/`.
#:
#: The leading underscore is what keeps it out of the dataset namespace -- a ProteomeXchange or
#: MassIVE accession never starts with one -- and `write_study_bundle` refuses a layer name that
#: would collide anyway, rather than trusting the convention to hold forever.
STUDY_DIR = "_study"

#: In a delimited file, a list-valued column's cell is split on this. Parquet carries real lists and
#: is not touched. `age_effect_meta.dataset_ids` is the column that makes this necessary: C3 and D1
#: need *which* datasets a pooled estimate came from, not how many.
LIST_SEPARATOR = ";"

#: Manifest fields that shape what a study bundle CONTAINS. Same discipline as
#: `manifest.CONTENT_FIELDS`, and it exists here for the same reason it had to be written down
#: there: the half of the rule that bites is "anything that reaches a written row is an input to the
#: content hash -- and nothing else is".
#:
#: `tables` covers both halves of a delivery at once, because each entry is hashed as
#: `table:<name>` against the file's own SHA-256: change which file fills `age_effects`, or change a
#: byte inside it, and the id moves.
STUDY_CONTENT_FIELDS: tuple[str, ...] = (
    "layer",   # which study layer's schema the rows are written against, and the bundle's namespace
    "tables",  # which table each delivered file fills, and (by hash) what is in it
    # The definition register every definition_id in the delivery must resolve against. Content,
    # not prose: it decides whether a row may be written at all, and two deliveries declaring
    # different registers are not interchangeable even over identical numbers.
    "definitions",
    # How the manifest itself is read. In the hash rather than out of it because a version exists
    # only when the interpretation changed: a v2 that read `tables` differently would turn the same
    # files into different rows, and a bump is by definition never a no-op.
    "study_manifest_version",
)

#: Fields that do NOT go into the content hash, each with the reason.
STUDY_NON_CONTENT_FIELDS: dict[str, str] = {
    "path": "where the manifest file happens to sit; a moved manifest delivers the same rows",
    "store": "where the bundle is written, which is an operator's choice and not its content",
    "instance": "who produced it; recorded in study.json, never read into a row",
    "delivery": "the producer's label for this hand-over; prose, like a manifest `reason`",
    "notes": "the producer's prose; never read into a row",
    "layer_version": "checked against STUDY_VERSIONS and recorded, but the layer's version is "
                     "already hashed from STUDY_VERSIONS rather than from what a manifest claims",
    "raw": "the parsed document itself, which is the container for every field above",
}


@dataclass(frozen=True)
class StudyManifest:
    """One study layer's delivery: which tables are being handed over, and in which files."""

    path: Path
    study_manifest_version: int
    layer: str
    store: Path
    tables: dict[str, Path]
    definitions: tuple[str, ...] = ()
    instance: str | None = None
    delivery: str | None = None
    layer_version: str | None = None
    notes: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def content_declaration(self) -> dict[str, Any]:
        """The manifest's contribution to the bundle's content hash: `STUDY_CONTENT_FIELDS` only."""
        return {
            "layer": self.layer,
            "tables": {name: path.name for name, path in sorted(self.tables.items())},
            "definitions": sorted(self.definitions),
            "study_manifest_version": self.study_manifest_version,
        }


def _resolve(value: Any, manifest_path: Path) -> Path:
    """A manifest path, with relative ones taken against the manifest's own directory."""
    candidate = Path(str(value))
    return candidate if candidate.is_absolute() else (manifest_path.parent / candidate).resolve()


def load_study_manifest(path: str | Path) -> StudyManifest:
    """Read and check a study delivery manifest.

    Raises:
        ManifestError: the file is missing or malformed, declares an unknown `study_manifest_version`
            or an unknown layer, names a table the layer does not have, or points at a file that is
            not there.
    """
    path = Path(path)
    if not path.is_file():
        raise ManifestError(f"no study manifest at {path}")
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as exc:
        raise ManifestError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise ManifestError(f"{path} must contain a mapping, found {type(doc).__name__}")

    version = doc.get("study_manifest_version")
    if version not in SUPPORTED_STUDY_MANIFEST_VERSIONS:
        supported = ", ".join(str(v) for v in sorted(SUPPORTED_STUDY_MANIFEST_VERSIONS))
        raise ManifestError(
            f"{path} declares study_manifest_version {version!r}; this build reads {supported}"
        )

    layer = doc.get("layer")
    if not layer:
        raise ManifestError(f"{path} does not say which study 'layer' it delivers")
    layer = str(layer)
    if layer not in STUDY_TABLES:
        known = ", ".join(sorted(STUDY_TABLES)) or "(none)"
        raise ManifestError(
            f"{path} delivers study layer '{layer}', which this build does not carry. "
            f"Layers available: {known}"
        )

    declared = doc.get("layer_version")
    if declared is not None and str(declared) != STUDY_VERSIONS[layer]:
        raise ManifestError(
            f"{path} declares layer_version {declared!r} for '{layer}', and this build carries "
            f"{STUDY_VERSIONS[layer]}. Deliver against the layer this build has, or build with the "
            f"version the rows were written for -- a column added between the two would land "
            f"silently null."
        )

    if doc.get("store") is None:
        raise ManifestError(f"{path} is missing 'store'")

    raw_tables = doc.get("tables")
    if not isinstance(raw_tables, dict) or not raw_tables:
        raise ManifestError(
            f"{path} must declare a non-empty 'tables' mapping of <table>: <file>. A delivery that "
            f"names no table is not a delivery."
        )
    tables: dict[str, Path] = {}
    for name, rel in raw_tables.items():
        name = str(name)
        if name not in STUDY_TABLES[layer]:
            known = ", ".join(sorted(STUDY_TABLES[layer]))
            raise ManifestError(
                f"{path}: study layer '{layer}' has no table '{name}'. Tables: {known}"
            )
        table_path = _resolve(rel, path)
        if not table_path.is_file():
            raise ManifestError(f"{path}: {name} points at {table_path}, which is not a file")
        tables[name] = table_path

    raw_definitions = doc.get("definitions") or []
    if isinstance(raw_definitions, str):
        raw_definitions = [raw_definitions]
    definitions = tuple(str(d) for d in raw_definitions)

    return StudyManifest(
        path=path,
        study_manifest_version=int(version),
        layer=layer,
        store=_resolve(doc["store"], path),
        tables=tables,
        definitions=definitions,
        instance=doc.get("instance"),
        delivery=doc.get("delivery"),
        layer_version=None if declared is None else str(declared),
        notes=doc.get("notes"),
        raw=doc,
    )


def _split_lists(row: dict[str, Any], schema: pa.Schema) -> dict[str, Any]:
    """Turn a delimited file's list columns into real lists, splitting on `LIST_SEPARATOR`."""
    out = dict(row)
    for f in schema:
        if pa.types.is_list(f.type) and isinstance(out.get(f.name), str):
            cell = out[f.name].strip()
            out[f.name] = [part.strip() for part in cell.split(LIST_SEPARATOR) if part.strip()]
    return out


def read_table_file(path: Path, schema: pa.Schema, label: str) -> list[dict[str, Any]]:
    """Read one delivered table file into row dicts.

    Three formats, chosen by extension, and no sniffing: `.parquet`, `.tsv` and `.csv`. Guessing a
    delimiter is how a column full of `A;B` becomes two columns on somebody else's machine.

    Args:
        path: the producer's file.
        schema: the study table's schema, used to split list columns in text formats.
        label: what to call the table in an error.

    Raises:
        IngestError: the extension is not one of the three, or the file cannot be read.
    """
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pq.read_table(path).to_pylist()
    if suffix not in (".tsv", ".csv"):
        raise IngestError(
            f"{label}: {path.name} has extension '{suffix or '(none)'}'. A delivered table is "
            f".parquet, .tsv or .csv -- the delimiter is taken from the extension rather than "
            f"sniffed, because a guess turns one column of 'A;B' into two."
        )
    delimiter = "\t" if suffix == ".tsv" else ","
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if reader.fieldnames is None:
                raise IngestError(f"{label}: {path.name} is empty, so it has no header row")
            return [_split_lists(row, schema) for row in reader]
    except OSError as exc:
        raise IngestError(f"{label}: cannot read {path}: {exc}") from exc


def _duplicate_keys(layer: str, table: str, rows: Sequence[dict[str, Any]]) -> list[str]:
    """Key values that appear more than once, using the layer's declared natural key.

    The keys were declared while the tables were empty precisely so this check could exist the
    moment something filled them (`integrity.STUDY_COMPOSITE_IDENTIFIERS`). `quant_values` shipped
    with no key at all and a duplicated source row wrote one measurement three times.

    A key with a null component is skipped, matching `integrity.check`: `age_effect_refusals` keys
    on `feature_id` and a dataset-level refusal has none.
    """
    key = STUDY_COMPOSITE_IDENTIFIERS.get(layer, {}).get(table)
    if not key:
        return []
    seen: set[tuple] = set()
    duplicates: set[tuple] = set()
    for row in rows:
        value = tuple(str(row.get(column)) for column in key)
        if any(row.get(column) in (None, "") for column in key):
            continue
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return [":".join(v) for v in sorted(duplicates)]


def _unknown_definitions(
    declared: Sequence[str], schema: pa.Schema, rows: Sequence[dict[str, Any]]
) -> set[str]:
    """Definition ids a table's rows carry that the delivery did not declare.

    Checked against the delivery's OWN register rather than the core `definitions` table, which is
    aging's correction to our offer (their 024 section 2a): their definitions are not produced by a
    search and have no business in a search bundle.

    A delivery that declares nothing is not checked. That is deliberate rather than lax -- a
    producer who has not adopted the register yet is not silently handed a stricter contract than
    the one they agreed to, and a delivery that declares even one definition opts fully in.
    """
    if not declared or "definition_id" not in schema.names:
        return set()
    known = set(declared)
    return {
        str(value)
        for row in rows
        if (value := row.get("definition_id")) not in (None, "") and str(value) not in known
    }


@dataclass
class StudyResult:
    """What writing a study bundle did, in the terms an operator needs."""

    bundle_path: Path
    bundle_id: str
    layer: str
    row_counts: dict[str, int] = field(default_factory=dict)
    skipped: bool = False


def study_bundle_id(manifest: StudyManifest, sources: Sequence[dict[str, Any]]) -> str:
    """Content hash of the delivered files, the layer, the schema and the study ingest path.

    The layer's version comes from `STUDY_VERSIONS` rather than from what the manifest claims, so a
    bundle written against a layer that has since gained a column cannot share an id with one
    written after.
    """
    digest = hashlib.sha256()
    digest.update(
        f"datarepo-study/{STUDY_INGESTER_VERSION}\nschema/{SCHEMA_VERSION}\n"
        f"study/{manifest.layer}/{STUDY_VERSIONS[manifest.layer]}\n".encode()
    )
    for entry in sorted(sources, key=lambda e: (e["role"], e["path"])):
        digest.update(f"{entry['role']}\t{entry['sha256']}\n".encode())
    return digest.hexdigest()[:16]


def write_study_bundle(
    manifest: StudyManifest,
    *,
    store: Path | None = None,
    overwrite: bool = False,
) -> StudyResult:
    """Read a delivery and write it as one content-addressed study bundle.

    Every table goes through `bundle.rows_to_table` against the study schema, so the definition's
    rules are enforced here and not merely documented: a `beta` with no `se` is a write error, and a
    refused fit has nowhere to put a null `beta` because it has a table of its own.

    Args:
        manifest: a loaded `study.yaml`.
        store: override the manifest's store.
        overwrite: rewrite a bundle that is already there. Without it, an unchanged delivery is a
            no-op and says so, exactly as `ingest` does.

    Returns:
        A `StudyResult`. `skipped` is True when the bundle was already written.

    Raises:
        IngestError: a delivered file cannot be read, a row has an unknown column or a null in a
            required one, or a table repeats its own key.
    """
    root = Path(store) if store else manifest.store
    layer = manifest.layer
    if layer.startswith(".") or "/" in layer or "\\" in layer:
        raise IngestError(f"study layer '{layer}' is not usable as a directory name")

    sources: list[dict[str, Any]] = []
    for name, path in sorted(manifest.tables.items()):
        sources.append({
            "role": f"table:{name}",
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    canonical = json.dumps(manifest.content_declaration(), sort_keys=True, ensure_ascii=False)
    sources.append({
        "role": "declaration:study",
        "path": "<declaration:study>",
        "kind": "declaration",
        "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    })

    bundle_id = study_bundle_id(manifest, sources)
    out = root / STUDY_DIR / layer / bundle_id
    manifest_path = out / STUDY_BUNDLE_MANIFEST
    if manifest_path.exists() and not overwrite:
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        return StudyResult(
            bundle_path=out,
            bundle_id=bundle_id,
            layer=layer,
            row_counts={str(k): int(v) for k, v in (doc.get("tables") or {}).items()},
            skipped=True,
        )

    prepared: dict[str, pa.Table] = {}
    for name, path in sorted(manifest.tables.items()):
        schema = STUDY_TABLES[layer][name]
        label = f"{layer}.{name}"
        rows = read_table_file(path, schema, label)
        duplicates = _duplicate_keys(layer, name, rows)
        if duplicates:
            key = ", ".join(STUDY_COMPOSITE_IDENTIFIERS[layer][name])
            sample = ", ".join(duplicates[:3])
            raise IngestError(
                f"table {label}: {len(duplicates)} duplicate key(s) on ({key}), e.g. {sample}. "
                f"Two rows for one fit are two different answers to one question, and which is "
                f"right is the producer's call, not this ingester's."
            )
        unknown = _unknown_definitions(manifest.definitions, schema, rows)
        if unknown:
            declared = ", ".join(sorted(manifest.definitions)) or "(none declared)"
            raise IngestError(
                f"table {label}: {len(unknown)} definition_id(s) the delivery does not declare, "
                f"e.g. {', '.join(sorted(unknown)[:3])}. Declared: {declared}. A number whose "
                f"definition id does not resolve is the failure a definition register exists to "
                f"prevent, so the write fails rather than the row landing (aging 024 section 2a). "
                f"Add it to `definitions:` in the study manifest, or correct the column."
            )
        prepared[name] = rows_to_table(label, schema, rows)

    out.mkdir(parents=True, exist_ok=True)
    row_counts: dict[str, int] = {}
    for name, table in prepared.items():
        pq.write_table(table, out / f"{name}.parquet", compression="zstd")
        row_counts[name] = table.num_rows

    doc = {
        "bundle_id": bundle_id,
        "kind": "study",
        "layer": layer,
        "layer_version": STUDY_VERSIONS[layer],
        "schema_version": SCHEMA_VERSION,
        "instance": manifest.instance,
        "delivery": manifest.delivery,
        # Both versions, for the same reason the search bundle records both: `version` is what an
        # operator installed, `study_ingest_path` is what the id was computed from.
        "ingester": {
            "name": "datarepo",
            "version": __version__,
            "study_ingest_path": STUDY_INGESTER_VERSION,
        },
        "written_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "tables": row_counts,
        "sources": sources,
        "notes": manifest.notes,
    }
    manifest_path.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return StudyResult(bundle_path=out, bundle_id=bundle_id, layer=layer, row_counts=row_counts)
