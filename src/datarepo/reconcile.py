"""Check the bundle's own tables against the producer's summary numbers.

Step 1's test is that counts reconcile (FRAMEWORK section 6). An ingester that silently drops a
tenth of the PSMs still writes a plausible-looking bundle, so every bundle recounts its own tables
and compares them with what MetaMorpheus's `results.txt` and the pipeline's provenance reported.

A mismatch is never fatal and never hidden: it is written into `bundle.json` and raised as a
Finding on the dataset, because some mismatches are real and already known (aging's S20 and S21)
and the repository's job is to carry them with their explanation, not to paper over them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

#: Counts within this relative distance of each other are treated as agreeing.
TOLERANCE = 0.0


@dataclass(frozen=True)
class Check:
    """One comparison between a number the bundle holds and a number the producer reported."""

    name: str
    observed: float | None
    expected: float | None
    source: str
    note: str | None = None

    @property
    def ok(self) -> bool:
        if self.observed is None or self.expected is None:
            return True  # nothing to compare against; the absence is reported, not judged
        if self.expected == 0:
            return self.observed == 0
        return abs(self.observed - self.expected) / abs(self.expected) <= TOLERANCE

    @property
    def comparable(self) -> bool:
        return self.observed is not None and self.expected is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "observed": self.observed,
            "expected": self.expected,
            "source": self.source,
            "ok": self.ok,
            **({"note": self.note} if self.note else {}),
        }


def build(
    *,
    psm_count_1pct: int,
    peptidoform_count_1pct: int,
    protein_group_count_1pct: int,
    runs: Sequence[dict[str, Any]],
    results: dict[str, dict[str, int]],
    expected_files: int | None,
    provenance_ms2: int | None,
) -> list[Check]:
    """Compare the bundle's own counts with the producer's reported totals.

    The three identification counts are computed with the producer's own acceptance rule (target,
    and both q-values at or below 1%), because a count taken under a different rule would differ
    for a reason that says nothing about whether the ingest was faithful.

    Args:
        psm_count_1pct, peptidoform_count_1pct, protein_group_count_1pct: the bundle's counts.
        runs: the Run rows about to be written.
        results: parsed `results.txt`, `{scope: {name: count}}`.
        expected_files: the manifest's file count for the dataset.
        provenance_ms2: `id_rate.ms2` from the search provenance.
    """
    totals = results.get("", {})
    ms2_observed = sum(r["ms2_spectra"] for r in runs if r.get("ms2_spectra") is not None)
    return [
        Check(
            "psms_target_1pct",
            psm_count_1pct,
            totals.get("psms"),
            "results.txt: All target PSMs with q-value <= 0.01 (aging DEF-PSM-1PCT v1)",
        ),
        Check(
            "peptidoforms_target_1pct",
            peptidoform_count_1pct,
            totals.get("peptides"),
            "results.txt: All target peptides with q-value <= 0.01",
        ),
        Check(
            "protein_groups_1pct",
            protein_group_count_1pct,
            totals.get("protein_groups"),
            "results.txt: All target protein groups with q-value <= 0.01",
        ),
        Check("runs", len(runs), expected_files, "ingest manifest: files"),
        Check(
            "ms2_spectra",
            ms2_observed or None,
            provenance_ms2 if provenance_ms2 is not None else totals.get("ms2_scans"),
            "provenance.json id_rate.ms2 / results.txt All MS2 Scans",
        ),
    ]


def finding_rows(checks: Sequence[Check], dataset_id: str) -> list[dict[str, Any]]:
    """A Finding for each comparison that did not agree."""
    rows = []
    for check in checks:
        if check.ok or not check.comparable:
            continue
        message = (
            f"The bundle holds {check.observed:g} where the producer reported {check.expected:g} "
            f"({check.source}). Both numbers are kept; treat the producer's as canonical until the "
            f"difference is explained."
        )
        if check.note:
            message = f"{message} {check.note}"
        rows.append(
            {
                "finding_id": f"{dataset_id}:count_mismatch:{check.name}",
                "dataset_id": dataset_id,
                "run_id": None,
                "code": "count_mismatch",
                "severity": "warning",
                "status": "open",
                "message": message,
                "source": "datarepo ingest reconciliation",
            }
        )
    return rows
