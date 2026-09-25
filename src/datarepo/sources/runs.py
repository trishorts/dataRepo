"""`fetch_manifest.json` + `qc_report.json` (+ the SDRF) -> Run rows and run-level Metrics.

A run is one deposited raw file. Which files exist, and what the archive said about them, comes
from the fetch manifest; what is in them comes from the spectra QC stage.

Two fields the schema wants are not available yet and are left null rather than derived here:
`instrument_model` at run level and `acquisition_datetime`. aging 006 is explicit that neither is
in `qc_report.json` yet, that pyMzLib has been asked for run-level metadata (REQ-PYMZ-2), and that
dataRepo should **not** parse raw file headers itself in the meantime. The instrument therefore
comes from the archive's own record via the SDRF, which is project-level, and the date stays NA.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import definitions as defs
from .._schema_docs import ENUMS
from ..errors import IngestError

#: Where a run's enrichment came from (the schema's `RunEnrichmentSource`).
FROM_DATASET = "dataset_declaration"
FROM_MANIFEST = "manifest_run_enrichment"


def load_fetch_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_qc_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def excluded_files(search_provenance: dict[str, Any]) -> tuple[frozenset[str], str | None]:
    """The raw files the search left out, and the producer's reason (DATAREPO-51, aging D52).

    aging excludes a file that fails QC only on `too_few_ms2` (a blank or failed injection) and
    records it in the search's `excluded_files`. The QC report still lists it, truthfully, so a run
    built from the QC report would describe a measurement that is not in the data.

    Returns:
        `(file names, reason)`. Names are bare file names; empty when nothing was excluded.
    """
    block = search_provenance.get("excluded_files") or {}
    names = frozenset(Path(str(f)).name for f in (block.get("files") or []) if str(f).strip())
    reason = block.get("reason")
    return names, (str(reason) if reason else None)


def _dissociation(qc: dict[str, Any]) -> list[str]:
    """`{"Orbitrap/HCD": 16197}` -> `["HCD"]`."""
    modes = []
    for key in (qc.get("ms2_analyzer_dissociation") or {}):
        _, _, dissociation = str(key).rpartition("/")
        value = (dissociation or key).strip()
        if value and value not in modes:
            modes.append(value)
    return modes


def build(
    dataset_id: str,
    *,
    fetch: dict[str, Any] | None,
    qc: dict[str, Any] | None,
    run_facts: dict[str, dict[str, Any]],
    excluded: frozenset[str] = frozenset(),
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build Run rows and their Metric rows.

    Args:
        dataset_id: ProteomeXchange accession.
        fetch: parsed `fetch_manifest.json`, or None when the stage was not kept.
        qc: parsed `qc_report.json`, keyed by raw file name, or None.
        run_facts: per-run instrument/fraction facts from the SDRF.
        excluded: file names the search left out (`excluded_files`). They are deposited and QC'd
            but not searched, so they are not runs of this dataset's results.

    Returns:
        `(runs, metrics)`. Runs are ordered by file name so a bundle is byte-stable.
    """
    qc = qc or {}
    files: list[dict[str, Any]] = []
    if fetch:
        files = [f for f in fetch.get("files", []) if str(f.get("category", "RAW")).upper() == "RAW"]

    names = {Path(str(f.get("name", ""))).name for f in files} | set(qc)
    excluded_stems = {Path(n).stem for n in excluded}
    names = {n for n in names if n not in excluded and Path(n).stem not in excluded_stems}
    by_name = {Path(str(f.get("name", ""))).name: f for f in files}

    runs: list[dict[str, Any]] = []
    metrics: list[dict[str, Any]] = []
    for file_name in sorted(n for n in names if n):
        base = Path(file_name).stem
        run_id = f"{dataset_id}:{base}"
        entry = by_name.get(file_name, {})
        qc_entry = qc.get(file_name) or qc.get(base) or {}
        facts = run_facts.get(base, {})
        runs.append(
            {
                "run_id": run_id,
                "dataset_id": dataset_id,
                "file_name": file_name,
                "sha256": entry.get("sha256"),
                "pride_checksum_sha1": entry.get("pride_checksum"),
                "fraction": facts.get("fraction"),
                "technical_replicate": facts.get("technical_replicate"),
                "fragmentation": _dissociation(qc_entry),
                "ms2_spectra": qc_entry.get("ms2"),
                "run_minutes": qc_entry.get("run_minutes"),
                "qc_pass": qc_entry.get("pass"),
                "instrument_model": facts.get("instrument_model"),
                "acquisition_datetime": None,
                # Filled by `assign_enrichment`, which needs every run at once to check coverage.
                "enrichment": None,
                "enrichment_source": None,
            }
        )
        for name, value, definition in (
            ("ms2", qc_entry.get("ms2"), defs.MS2_COUNT.definition_id),
            ("run_minutes", qc_entry.get("run_minutes"), defs.RUN_MINUTES.definition_id),
        ):
            if value is not None:
                metrics.append(
                    {
                        "scope": "run",
                        "scope_id": run_id,
                        "name": name,
                        "value": value,
                        "definition_id": definition,
                        "source": "qc_report.json",
                    }
                )
    return runs, metrics


def _examples(names: list[str], n: int = 5) -> str:
    shown = ", ".join(names[:n])
    return shown + (f" and {len(names) - n} more" if len(names) > n else "")


def assign_enrichment(
    runs: list[dict[str, Any]],
    dataset_id: str,
    *,
    declared: tuple[str, ...],
    mixed: bool,
    run_enrichment: tuple[tuple[str, str], ...],
) -> bool:
    """Fill each run's `enrichment` and `enrichment_source`, and say whether the runs differ (G63).

    The rules are the ones agreed with aging (thread 054 section 2, their 058), and each failure
    refuses the ingest rather than writing a guess:

    - **A per-run map must cover every run.** A partial map would leave some runs NULL beside some
      filled, and NULL would come to mean "probably the other one".
    - **A name that is not a run is refused**, and so is an enrichment value outside the schema's
      vocabulary. (A run named twice is refused when the manifest is read.)
    - **Every run value other than `none` must be in the dataset's declaration.** A run that says
      `chemical_probe` in a dataset declared `[immunoprecipitation]` is a curation error.
    - **A map with one value on a dataset flagged mixed** contradicts the flag, and is refused.
    - **No map:** a dataset not flagged mixed gives its declaration to every run, because it is true
      of every run. A mixed dataset gives NULL to every run, never its declaration, which is true of
      only some of them.

    Args:
        runs: Run rows from `build`, modified in place.
        dataset_id: for messages.
        declared: the dataset's `enrichment` from the manifest.
        mixed: the producer's `mixed_enrichment` flag.
        run_enrichment: the manifest's sorted `(run base name, value)` pairs.

    Returns:
        `Dataset.enrichment_mixed`: the flag, or more than one distinct per-run value.

    Raises:
        IngestError: any rule above.
    """
    if not run_enrichment:
        for run in runs:
            run["enrichment"] = None if mixed else list(declared)
            run["enrichment_source"] = None if mixed else FROM_DATASET
        return mixed

    vocabulary = set(ENUMS["Enrichment"]["values"])
    given = dict(run_enrichment)
    bad_values = sorted({v for v in given.values() if v not in vocabulary})
    if bad_values:
        raise IngestError(
            f"{dataset_id}: run_enrichment uses {', '.join(bad_values)}, which the schema's Enrichment "
            f"vocabulary does not have ({', '.join(sorted(vocabulary))})."
        )
    base_names = {Path(str(run["file_name"])).stem: run for run in runs}
    unknown = sorted(set(given) - set(base_names))
    if unknown:
        raise IngestError(
            f"{dataset_id}: run_enrichment names {len(unknown)} run(s) that are not runs of this "
            f"dataset: {_examples(unknown)}. Runs are the deposited raw file names without their "
            f"extension, e.g. {_examples(sorted(base_names), 3)}."
        )
    missing = sorted(set(base_names) - set(given))
    if missing:
        raise IngestError(
            f"{dataset_id}: run_enrichment covers {len(given)} of {len(base_names)} runs and must cover "
            f"every one. Missing: {_examples(missing)}. A partial map would leave NULL meaning "
            f"'probably the other one'."
        )
    undeclared = sorted({v for v in given.values() if v != "none" and v not in declared})
    if undeclared:
        raise IngestError(
            f"{dataset_id}: run_enrichment assigns {', '.join(undeclared)}, which the dataset's "
            f"enrichment declaration ({', '.join(declared)}) does not include. Either the run map or "
            f"the declaration is wrong, and the producer has to say which."
        )
    distinct = set(given.values())
    if mixed and len(distinct) == 1:
        raise IngestError(
            f"{dataset_id}: flagged mixed_enrichment, but run_enrichment gives every run "
            f"{next(iter(distinct))!r}. The flag and the map contradict each other."
        )
    for base, run in base_names.items():
        run["enrichment"] = [given[base]]
        run["enrichment_source"] = FROM_MANIFEST
    return mixed or len(distinct) > 1
