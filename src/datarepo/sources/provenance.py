"""`provenance.json` -> ProvenanceRecord, Metric and Finding rows.

The provenance schema version is not decoration. aging thread 006: in `aging-provenance/2` and
earlier, `id_rate.psms_1pct` holds the FDR engine's count, not the canonical target-PSM count that
its name suggests; `/3` splits them into two named fields, each with its own definition. So the
version is read first and the fields are mapped accordingly, and a version older than `/2` is
refused rather than read under the wrong meaning.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .. import definitions as defs
from ..errors import UnsupportedProvenance

#: Provenance schema versions this ingester knows how to map.
SUPPORTED = {2, 3}

_SCHEMA_RE = re.compile(r"^aging-provenance/(\d+)$")

#: How much each pipeline flag should change trust in the data.
FLAG_SEVERITY = {
    "low_id_rate": "warning",
    "no_design_file": "warning",
    "no_output_sdrf": "info",
    "old_provenance_schema": "error",
}

FLAG_MESSAGE = {
    "low_id_rate": (
        "The search identified an unusually small fraction of the MS2 spectra. Treat absence of a "
        "protein in this dataset as weak evidence."
    ),
    "no_design_file": (
        "No experimental design file, so quantification treated every raw file as its own "
        "condition. Between-group comparisons are not available for this dataset."
    ),
    "no_output_sdrf": (
        "The search did not write an SDRF back out, so sample metadata comes from the deposited "
        "SDRF only."
    ),
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def schema_version(doc: dict[str, Any]) -> int:
    """Major version of the provenance schema.

    Raises:
        UnsupportedProvenance: the value is missing, unparseable, or a version whose field meanings
            this ingester has not been taught.
    """
    raw = str(doc.get("schema", ""))
    m = _SCHEMA_RE.match(raw)
    if not m:
        raise UnsupportedProvenance(
            f"provenance schema {raw!r} is not an aging-provenance version this ingester reads"
        )
    version = int(m.group(1))
    if version not in SUPPORTED:
        supported = ", ".join(f"aging-provenance/{v}" for v in sorted(SUPPORTED))
        raise UnsupportedProvenance(
            f"provenance schema aging-provenance/{version} is not supported; this ingester reads "
            f"{supported}. Older records name their PSM count in a way that cannot be mapped to a "
            f"definition safely (aging 006)."
        )
    return version


def record_row(
    doc: dict[str, Any], dataset_id: str, *, stage_dir_name: str, bundle_path: str, sha256: str
) -> dict[str, Any]:
    """One ProvenanceRecord row, with the heavy blocks kept verbatim as JSON."""
    pipeline = doc.get("pipeline") or {}
    resources = doc.get("resources") or {}
    return {
        "dataset_id": dataset_id,
        "stage": str(doc.get("stage") or stage_dir_name),
        "provenance_schema": str(doc.get("schema", "")),
        "started_utc": doc.get("started_utc"),
        "finished_utc": doc.get("finished_utc"),
        "pipeline_repo": pipeline.get("repo"),
        "pipeline_commit": pipeline.get("commit"),
        "params_sha256": (doc.get("params_file") or {}).get("sha256"),
        "tools_json": json.dumps(doc.get("tools"), sort_keys=True) if doc.get("tools") else None,
        "params_json": json.dumps(doc.get("params"), sort_keys=True) if doc.get("params") else None,
        "wall_seconds": resources.get("wall_s"),
        "peak_rss_gib": resources.get("peak_rss_gib"),
        "resources_json": json.dumps(resources, sort_keys=True) if resources else None,
        "original_path": bundle_path,
        "original_sha256": sha256,
    }


def metric_rows(doc: dict[str, Any], dataset_id: str, version: int) -> list[dict[str, Any]]:
    """Dataset-level Metric rows from the search stage's own numbers.

    The PSM count is stored under the definition it actually satisfies, which depends on the
    provenance version, so a reader never has to know the field-naming history.
    """
    rows: list[dict[str, Any]] = []
    id_rate = doc.get("id_rate") or {}

    def add(name: str, value: Any, definition: str, source: str) -> None:
        if value is not None:
            rows.append(
                {
                    "scope": "dataset",
                    "scope_id": dataset_id,
                    "name": name,
                    "value": value,
                    "definition_id": definition,
                    "source": source,
                }
            )

    if version >= 3:
        add("psms_1pct", id_rate.get("psms_1pct"), defs.PSM_1PCT.definition_id,
            "provenance.json id_rate.psms_1pct")
        add("psms_fdr_engine_1pct", id_rate.get("psms_fdr_engine_1pct"),
            defs.PSM_FDR_ENGINE.definition_id, "provenance.json id_rate.psms_fdr_engine_1pct")
    else:
        # aging 006: in /2 the field named psms_1pct holds the FDR engine's count.
        add("psms_fdr_engine_1pct", id_rate.get("psms_1pct"), defs.PSM_FDR_ENGINE.definition_id,
            "provenance.json id_rate.psms_1pct (aging-provenance/2 naming)")

    add("ms2", id_rate.get("ms2"), defs.MS2_COUNT.definition_id, "provenance.json id_rate.ms2")
    add("id_rate", id_rate.get("rate"), defs.ID_RATE.definition_id, "provenance.json id_rate.rate")

    mbr = doc.get("mbr") or {}
    mbr_definition = mbr.get("definition") or defs.MBR.definition_id
    for key in ("mbr_rows", "mbr_kept", "msms_peaks", "kept_over_msms", "mbr_fdr_threshold"):
        if key in mbr:
            rows.append(
                {
                    "scope": "dataset",
                    "scope_id": dataset_id,
                    "name": key,
                    "value": mbr[key],
                    "definition_id": defs.MBR.definition_id,
                    "source": f"provenance.json mbr ({mbr_definition})",
                }
            )
    return rows


def contamination_metric_rows(
    doc: dict[str, Any], dataset_id: str, *, run_names: Any = None
) -> list[dict[str, Any]]:
    """Metric rows from the search stage's `contamination` block.

    The block was already becoming a Finding, which says *that* a dataset is contaminated but puts
    the numbers in a sentence. These rows put them where a query can reach them.

    **The intensity share is emitted per run, one row per file, and is never averaged into a
    dataset number here.** It is defined per file (QuantProject DEF-QC-9), and the dataset figure
    is what hid the structure aging found: 7.0% overall against 2.6-18.9% per file, grouped by cell
    line. The producer's own median/min/max are carried as dataset-scope rows under names that say
    they are summaries of the per-run values, so nothing forces a caller to recompute them and
    nothing lets a caller mistake one for the measurement.

    Args:
        doc: the search stage's provenance document.
        dataset_id: ProteomeXchange accession.
        run_names: `RunNameMap`, to resolve the calibrated names the block is keyed by back to the
            deposited run. A file that will not resolve gets no row rather than a row under a
            `run_id` that matches no run.
    """
    block = doc.get("contamination") or {}
    rows: list[dict[str, Any]] = []

    def add(scope: str, scope_id: str, name: str, value: Any, definition: str, source: str) -> None:
        if value is not None:
            rows.append(
                {
                    "scope": scope,
                    "scope_id": scope_id,
                    "name": name,
                    "value": value,
                    "definition_id": definition,
                    "source": source,
                }
            )

    add(
        "dataset",
        dataset_id,
        "contamination_psm_share",
        block.get("psm_share"),
        defs.CONTAM_PSM_SHARE.definition_id,
        f"provenance.json contamination.psm_share ({block.get('psm_share_definition') or block.get('definition') or 'unnamed'})",
    )
    for name, key in (
        ("contaminant_psms", "contaminant_psms"),
        ("target_plus_contaminant_psms", "target_plus_contaminant_psms"),
    ):
        add(
            "dataset",
            dataset_id,
            name,
            block.get(key),
            defs.CONTAM_PSM_SHARE.definition_id,
            f"provenance.json contamination.{key}",
        )

    intensity_definition = defs.CONTAM_INTENSITY_SHARE.definition_id
    per_file = block.get("intensity_share_per_file") or {}
    for reported, value in sorted(per_file.items()):
        base = run_names.resolve(reported) if run_names is not None else reported
        if not base:
            continue
        add(
            "run",
            f"{dataset_id}:{base}",
            "contamination_intensity_share",
            value,
            intensity_definition,
            "provenance.json contamination.intensity_share_per_file",
        )
    for summary in ("median", "min", "max"):
        add(
            "dataset",
            dataset_id,
            f"contamination_intensity_share_{summary}",
            block.get(f"intensity_share_{summary}"),
            intensity_definition,
            f"provenance.json contamination.intensity_share_{summary} "
            f"(a summary of the per-run values, not a measurement of the dataset)",
        )
    return rows


def finding_rows(doc: dict[str, Any], dataset_id: str, source: str) -> list[dict[str, Any]]:
    """Finding rows from the stage's `flags[]`.

    A flag reads `code: explanation`. The code drives severity; the explanation is kept, because
    it is the producer's own words about what is wrong.
    """
    rows = []
    for raw in doc.get("flags") or []:
        text = str(raw)
        code, _, detail = text.partition(":")
        code = code.strip()
        message = FLAG_MESSAGE.get(code, detail.strip() or text)
        if detail.strip() and code in FLAG_MESSAGE:
            message = f"{message} Producer's note: {detail.strip()}"
        rows.append(
            {
                "finding_id": f"{dataset_id}:{code}",
                "dataset_id": dataset_id,
                "run_id": None,
                "code": code,
                "severity": FLAG_SEVERITY.get(code, "warning"),
                "status": "open",
                "message": message,
                "source": source,
            }
        )
    return rows
