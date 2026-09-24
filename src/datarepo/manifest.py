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

#: Manifest fields that shape what a bundle CONTAINS -- either because they are read into a row, or
#: because they choose which files are read. These go into the bundle's content hash, so changing
#: one of them changes the bundle id, which is exactly right: the bundle now holds something else.
CONTENT_FIELDS: tuple[str, ...] = (
    "accession",       # the dataset_id on every row
    "run",             # chooses the run folder, and so every file read
    "stages",          # chooses the stage folders
    "search_results",  # chooses the search results folder
    "title",           # Dataset.title
    "files",           # the expected file count a reconciliation check is made against
    "organism",        # Dataset.organisms, and the SDRF's default organism
    "acquisition",     # Dataset.acquisition (D5 axis)
    "quant_method",    # Dataset.quant_method (D5 axis)
    "labelling",       # Dataset.labelling (D5 axis)
    "labelling_plex",  # Dataset.labelling_plex (D5 axis)
    "enrichment",      # Dataset.enrichment (D5 axis), and every run's when the dataset is not mixed
    # Run.enrichment, per run (G63, aging DATAREPO-44). Adding it moves the bundle id, and must:
    # the run rows change (thread 054 section 2).
    "run_enrichment",
    # Lifted out of `flags`, which stays prose: this one flag decides whether a run with no per-run
    # value gets the dataset's enrichment or NULL, so it reaches Run.enrichment and
    # Dataset.enrichment_mixed. Only this flag -- rewording or adding any other must not re-id.
    "mixed_enrichment",
    "metamorpheus",    # chooses the modification registry, and is the engine_version fallback
    # Dataset.permitted_responses, and it is CONTENT rather than prose (aging 024 section 7).
    # Two bundles over the same rows, one of which may be used for site localization and one
    # of which may not, are NOT the same object: the rows mean different things. That is the
    # opposite of the `reason` case and the same test applied honestly -- does this change
    # what the rows MEAN. Changing a restriction must re-identify the bundle.
    "permitted_responses",
)

#: Fields that do NOT go into the content hash, each with the reason. A bundle id has to mean "these
#: are the same measurements" for an operator who re-runs the pipeline elsewhere (aging 019 section
#: 1), and hashing the producer's prose breaks that for no gain: rewording a `reason` moved the id
#: while every row stayed identical.
#:
#: Adding a field to `DatasetEntry` means classifying it here or in `CONTENT_FIELDS`; a test asserts
#: the two lists together cover the dataclass, so a new field cannot arrive unclassified. The rule
#: to apply is the one that has already bitten once: **anything that reaches a written row is an
#: input to the content hash.**
NON_CONTENT_FIELDS: dict[str, str] = {
    "status": "gates whether a bundle is written at all; every bundle that exists was 'include'",
    "reason": "the producer's prose for a status; never read into a row",
    "notes": "the producer's prose; never read into a row",
    "flags": "shown by `datarepo manifest`; the ingest reads none of them except `mixed_enrichment`, "
             "which is lifted into its own content field so the rest stay prose",
    "provenance_schema": "the producer's declared expectation; the ingest reads the schema from "
                         "provenance.json itself and refuses a version it cannot map",
    "sdrf": "declared but not read -- the SDRF is found under the run folder and hashed as a file",
    "raw": "the source row itself, which is the container for every field above",
}


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
    #: `(run base name, enrichment value)` pairs, sorted, from the manifest's
    #: `run_enrichment: {value: [run, ...]}`. Empty when the producer gave none.
    run_enrichment: tuple[tuple[str, str], ...] = ()
    mixed_enrichment: bool = False
    metamorpheus: str | None = None
    permitted_responses: tuple[str, ...] = ()
    provenance_schema: str | None = None
    flags: tuple[str, ...] = ()
    sdrf: str | None = None
    reason: str | None = None
    notes: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ingestable(self) -> bool:
        return self.status in INGESTABLE

    def content_declaration(self) -> dict[str, Any]:
        """The manifest's contribution to the bundle's content hash: `CONTENT_FIELDS` only.

        Not the raw row. A bundle id answers "are these the same measurements", so it covers what
        the manifest puts into the bundle and not what the producer wrote about the dataset.
        """
        return {name: getattr(self, name) for name in CONTENT_FIELDS}


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


def _run_enrichment(value: Any, where: str) -> tuple[tuple[str, str], ...]:
    """`{value: [run, ...]}` -> sorted `(run, value)` pairs, refusing a run named twice.

    Whether the names are real runs, whether they cover every run, and whether each value is one
    the dataset declares are checked at ingest, which is where the runs are known.

    Raises:
        ManifestError: not a mapping of value to a list of run names, or a run under two values.
    """
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise ManifestError(f"{where}: run_enrichment must map an enrichment value to a list of runs")
    seen: dict[str, str] = {}
    for enrichment, runs in value.items():
        if isinstance(runs, (str, int)) or not isinstance(runs, (list, tuple)):
            raise ManifestError(
                f"{where}: run_enrichment[{enrichment!r}] must be a list of run names, "
                f"found {type(runs).__name__}"
            )
        for run in runs:
            name = str(run)
            if name in seen:
                raise ManifestError(
                    f"{where}: run {name!r} appears twice in run_enrichment "
                    f"(under {seen[name]!r} and {str(enrichment)!r}). Each run has one entry."
                )
            seen[name] = str(enrichment)
    return tuple(sorted(seen.items()))


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
        flags = _as_tuple(row.get("flags"), ())
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
            run_enrichment=_run_enrichment(row.get("run_enrichment"), f"{path}: {accession}"),
            mixed_enrichment="mixed_enrichment" in flags,
            metamorpheus=row.get("metamorpheus"),
            permitted_responses=_as_tuple(row.get("permitted_responses"), ()),
            provenance_schema=row.get("provenance_schema"),
            flags=flags,
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
