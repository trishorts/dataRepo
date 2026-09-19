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


def load_fetch_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_qc_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


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
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build Run rows and their Metric rows.

    Args:
        dataset_id: ProteomeXchange accession.
        fetch: parsed `fetch_manifest.json`, or None when the stage was not kept.
        qc: parsed `qc_report.json`, keyed by raw file name, or None.
        run_facts: per-run instrument/fraction facts from the SDRF.

    Returns:
        `(runs, metrics)`. Runs are ordered by file name so a bundle is byte-stable.
    """
    qc = qc or {}
    files: list[dict[str, Any]] = []
    if fetch:
        files = [f for f in fetch.get("files", []) if str(f.get("category", "RAW")).upper() == "RAW"]

    names = {Path(str(f.get("name", ""))).name for f in files} | set(qc)
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
