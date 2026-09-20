"""The ingest contract: the producing instance's `manifest.yaml`.

aging thread 006 settled this. `datarepo ingest` reads the manifest rather than scanning the work
root, so which run is canonical for a dataset, and whether it may be loaded at all, is the
producer's call and is recorded in their repository, not inferred from directory names here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import DatasetExcluded, ManifestError

SUPPORTED_MANIFEST_VERSIONS = {1}

#: Statuses that may be ingested. Everything else is a deliberate refusal.
INGESTABLE = {"include"}


@dataclass(frozen=True)
class DatasetEntry:
    """One dataset in the manifest, with the axes D5 makes real columns."""

    accession: str
    status: str
    run: str
    title: str | None = None
    stages: dict[str, str] = field(default_factory=dict)
    search_results: str | None = None
    files: int | None = None
    organism: str | None = None
    acquisition: str | None = None
    quant_method: str | None = None
    labelling: str = "none"
    labelling_plex: int | None = None
    enrichment: tuple[str, ...] = ("none",)
    metamorpheus: str | None = None
    provenance_schema: str | None = None
    flags: tuple[str, ...] = ()
    sdrf: str | None = None
    reason: str | None = None
    notes: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ingestable(self) -> bool:
        return self.status in INGESTABLE


@dataclass(frozen=True)
class Manifest:
    """A producing instance's whole manifest."""

    path: Path
    manifest_version: int
    instance: str
    work_root: Path
    store: Path
    licence: str | None
    credit: str | None
    datasets: dict[str, DatasetEntry]

    def dataset(self, accession: str) -> DatasetEntry:
        """Return one dataset, refusing the ones the producer marked unfit.

        Raises:
            ManifestError: the accession is not in the manifest.
            DatasetExcluded: it is there, but its status is not `include`.
        """
        try:
            entry = self.datasets[accession]
        except KeyError:
            known = ", ".join(sorted(self.datasets)) or "(none)"
            raise ManifestError(
                f"{accession} is not in {self.path}. Datasets listed: {known}"
            ) from None
        if not entry.ingestable:
            reason = (entry.reason or "no reason given").strip()
            raise DatasetExcluded(
                f"{accession} has status '{entry.status}' in {self.path} and will not be "
                f"loaded. The producer's reason: {reason}"
            )
        return entry

    def ingestable(self) -> list[DatasetEntry]:
        return [e for e in self.datasets.values() if e.ingestable]

    def run_dir(self, entry: DatasetEntry) -> Path:
        return self.work_root / entry.run

    def stage_dir(self, entry: DatasetEntry, stage: str) -> Path | None:
        """Absolute path of one pipeline stage folder, or None if the manifest omits it."""
        rel = entry.stages.get(stage)
        return None if rel is None else self.run_dir(entry) / rel

    def search_results_dir(self, entry: DatasetEntry) -> Path:
        rel = entry.search_results or f"{entry.stages.get('search', '')}/mm/Task3SearchTask"
        return self.run_dir(entry) / rel


def _as_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return (value,)
    return tuple(str(v) for v in value)


def _resolve(value: Any, manifest_path: Path) -> Path:
    """A manifest path, with relative ones taken against the manifest's own directory.

    Production manifests use absolute roots. Relative ones make a manifest movable, which is what
    lets a test or a copied instance carry its own tree beside it.
    """
    candidate = Path(str(value))
    return candidate if candidate.is_absolute() else (manifest_path.parent / candidate).resolve()


def load_manifest(path: str | Path) -> Manifest:
    """Read and check an instance manifest.

    Raises:
        ManifestError: the file is missing, is not a mapping, uses an unknown `manifest_version`,
            or has a dataset entry without the fields an ingest needs.
    """
    path = Path(path)
    if not path.is_file():
        raise ManifestError(f"no ingest manifest at {path}")
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as exc:
        raise ManifestError(f"{path} is not valid YAML: {exc}") from exc
    if not isinstance(doc, dict):
        raise ManifestError(f"{path} must contain a mapping, found {type(doc).__name__}")

    version = doc.get("manifest_version")
    if version not in SUPPORTED_MANIFEST_VERSIONS:
        supported = ", ".join(str(v) for v in sorted(SUPPORTED_MANIFEST_VERSIONS))
        raise ManifestError(
            f"{path} declares manifest_version {version!r}; this ingester reads {supported}"
        )

    for required in ("work_root", "store", "datasets"):
        if doc.get(required) is None:
            raise ManifestError(f"{path} is missing '{required}'")

    entries: dict[str, DatasetEntry] = {}
    for i, row in enumerate(doc["datasets"]):
        if not isinstance(row, dict):
            raise ManifestError(f"{path}: datasets[{i}] must be a mapping")
        accession = row.get("accession")
        if not accession:
            raise ManifestError(f"{path}: datasets[{i}] has no accession")
        status = str(row.get("status", "include"))
        if status in INGESTABLE and not row.get("run"):
            raise ManifestError(f"{path}: {accession} has status '{status}' but no 'run'")
        if accession in entries:
            raise ManifestError(f"{path}: {accession} appears twice")
        entries[accession] = DatasetEntry(
            accession=str(accession),
            status=status,
            run=str(row.get("run", "")),
            title=row.get("title"),
            stages={str(k): str(v) for k, v in (row.get("stages") or {}).items()},
            search_results=row.get("search_results"),
            files=row.get("files"),
            organism=row.get("organism"),
            acquisition=row.get("acquisition"),
            quant_method=row.get("quant_method"),
            labelling=str(row.get("labelling", "none")),
            labelling_plex=row.get("labelling_plex"),
            enrichment=_as_tuple(row.get("enrichment"), ("none",)),
            metamorpheus=row.get("metamorpheus"),
            provenance_schema=row.get("provenance_schema"),
            flags=_as_tuple(row.get("flags"), ()),
            sdrf=row.get("sdrf"),
            reason=row.get("reason"),
            notes=row.get("notes"),
            raw=row,
        )

    return Manifest(
        path=path,
        manifest_version=int(version),
        instance=str(doc.get("instance", "unknown")),
        work_root=_resolve(doc["work_root"], path),
        store=_resolve(doc["store"], path),
        licence=doc.get("licence"),
        credit=doc.get("credit"),
        datasets=entries,
    )
