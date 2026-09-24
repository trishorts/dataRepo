"""FlashLFQ's wide tables -> ProteinGroup and QuantValue rows.

FlashLFQ writes one column per run (`Intensity_<run>`, `SpectralCount_<run>`); the schema stores
quantities long, one row per (assay, feature, definition), because that is the shape that survives
TMT channels and DIA without a schema change (D5). Melting is therefore the whole job here.

Two rules from the producer side are enforced while melting. **Missing is missing**: a
`NotDetected` cell or a zero intensity produces no row at all, never a zero, because a zero would
be read downstream as a measurement of absence. And **every number carries a definition**, which is
what lets intensity and spectral count share one `value` column without ambiguity.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import definitions as defs
from ..readers import ReaderLog, iter_dicts, read_tsv
from ..usi import RunNameMap

#: FlashLFQ's detection labels mapped onto the schema's DetectionType.
DETECTION_TYPE = {
    "MSMS": "MSMS",
    "MBR": "MBR",
    "MSMSAmbiguousPeakfinding": "MSMS",
    "MSMSIdentifiedButNotQuantified": "not_detected",
    "NotDetected": "not_detected",
    "": None,
}

#: Reason pyMzLib does not read these files; carried into the reader log.
_NO_READER = "no pyMzLib reader for FlashLFQ's wide tables (aging 006 / pyMzLib 005)"
_PEAKS_NOTE = "pyMzLib's FlashLFQ peak reader requires an 'MBR Score' column MetaMorpheus 1.1.11 does not write"


def _wide_columns(header: list[str], prefix: str) -> dict[str, str]:
    """`{run name reported by the search: column}` for every `<prefix>_<run>` column."""
    tag = prefix + "_"
    return {c[len(tag):]: c for c in header if c.startswith(tag)}


def _intensity(raw: str) -> float | None:
    """A quantity, where zero means *not measured* and must not be stored as a number.

    FlashLFQ writes 0 into a wide cell for a run where the feature was never detected. Storing
    that 0 would make an undetected protein look like a measured absence, so it becomes no row.
    """
    value = _number(raw)
    return None if value == 0.0 else value


def _number(raw: str) -> float | None:
    """A plain number, where zero is a real value (a q-value of 0, a coverage of 0)."""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return None if value != value else value


def _target_decoy(raw: str) -> str | None:
    """FlashLFQ's `Protein Decoy/Contaminant/Target` column -> the schema's TargetDecoy."""
    text = str(raw or "").upper()
    if not text:
        return None
    if "D" in text:
        return "decoy"
    if "C" in text:
        return "contaminant"
    return "target"


def _int(raw: str) -> int | None:
    try:
        return int(float(str(raw).split("|")[0]))
    except (TypeError, ValueError):
        return None


def _split(raw: str) -> list[str]:
    return [p.strip() for p in str(raw or "").split("|") if p.strip()]


def peak_quality(
    path: Path, dataset_id: str, *, run_names: RunNameMap, mbr_q_threshold: float, log: ReaderLog | None = None
) -> dict[tuple[str, str], dict[str, Any]]:
    """Best PIP q-value per (run, full sequence) from `AllQuantifiedPeaks.tsv`.

    FlashLFQ's peak table is per charge state and per peak, finer than the peptide table the
    quantities come from, so it is used only to attach the peak-level quality that the peptide
    table does not carry: the PIP q-value and whether the match-between-runs transfer passes the
    producer's threshold (QuantProject DEF-QC-MBR).
    """
    if not path.is_file():
        return {}
    header, rows = read_tsv(path, log, note=_PEAKS_NOTE)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in iter_dicts(header, rows):
        reported = row.get("File Name", "")
        run = run_names.resolve(reported) or reported
        sequence = row.get("Full Sequence", "")
        if not sequence:
            continue
        try:
            pip_q = float(row.get("PIP Q-Value", ""))
        except (TypeError, ValueError):
            pip_q = None
        key = (run, sequence)
        current = out.get(key)
        if current is None or (pip_q is not None and (current["pip_q_value"] is None or pip_q < current["pip_q_value"])):
            out[key] = {
                "pip_q_value": pip_q,
                "mbr_kept": None if pip_q is None else pip_q <= mbr_q_threshold,
            }
    return out


def peptide_quant_rows(
    path: Path,
    dataset_id: str,
    *,
    run_names: RunNameMap,
    to_proforma,
    peak_quality_index: dict[tuple[str, str], dict[str, Any]] | None = None,
    log: ReaderLog | None = None,
) -> list[dict[str, Any]]:
    """Melt `AllQuantifiedPeptides.tsv` into QuantValue rows for peptidoforms.

    Args:
        path: the wide peptide table.
        dataset_id: ProteomeXchange accession.
        run_names: maps FlashLFQ's column suffixes to deposited run names.
        to_proforma: the dataset's `ProformaCache`, so feature IDs match the Peptidoform table.
        peak_quality_index: output of `peak_quality`, for PIP q and the MBR flag.
        log: reader log.
    """
    header, rows = read_tsv(path, log, note=_NO_READER)
    intensity_cols = _wide_columns(header, "Intensity")
    detection_cols = _wide_columns(header, "Detection Type")
    index = peak_quality_index or {}

    out: list[dict[str, Any]] = []
    for row in iter_dicts(header, rows):
        sequence = row.get("Sequence") or row.get("Base Sequence") or ""
        parsed = to_proforma(sequence.split("|", 1)[0].strip())
        if not parsed.proforma:
            continue
        feature_id = f"{dataset_id}:{parsed.proforma}"
        for reported, column in intensity_cols.items():
            value = _intensity(row.get(column, ""))
            if value is None:
                continue
            run = run_names.resolve(reported) or reported
            detection = DETECTION_TYPE.get((row.get(detection_cols.get(reported, ""), "") or "").strip())
            quality = index.get((run, sequence.split("|", 1)[0].strip()), {})
            out.append(
                {
                    "assay_id": f"{dataset_id}:{run}:label_free",
                    "feature_type": "peptidoform",
                    "feature_id": feature_id,
                    "value": value,
                    "detection_type": detection,
                    "pip_q_value": quality.get("pip_q_value"),
                    "mbr_kept": quality.get("mbr_kept"),
                    "definition_id": defs.PEPTIDE_INTENSITY.definition_id,
                }
            )
    return out


def accepted_group_count(groups: list[dict[str, Any]]) -> int:
    """The producer's protein-group count at 1% FDR, over ProteinGroup rows.

    The producer counts a "target protein group" as anything not a decoy, contaminants included;
    matching that is what makes the reconciliation meaningful. It lives here, once, so the count
    can be retaken after the rows change -- an exact-duplicate collapse removes a row the file
    contained, and the reconciled count has to describe the rows the bundle holds.
    """
    return sum(
        1
        for g in groups
        if g.get("target_decoy") != "decoy"
        and g.get("q_value") is not None
        and g["q_value"] <= 0.01
    )


def protein_group_rows(
    path: Path, dataset_id: str, *, run_names: RunNameMap, log: ReaderLog | None = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Read `AllQuantifiedProteinGroups.tsv` into ProteinGroup rows and their QuantValues.

    Returns:
        `(protein_groups, quant_values, producer_count)`. Intensity and spectral count become
        separate QuantValue rows for the same feature, told apart by their definition ID;
        `producer_count` is the group count at 1% FDR as the producer counts it, for reconciling.
    """
    header, rows = read_tsv(path, log, note=_NO_READER)
    intensity_cols = _wide_columns(header, "Intensity")
    count_cols = _wide_columns(header, "SpectralCount")

    groups: list[dict[str, Any]] = []
    quants: list[dict[str, Any]] = []
    for row in iter_dicts(header, rows):
        accessions = _split(row.get("Protein Accession", ""))
        if not accessions:
            continue
        group_id = f"{dataset_id}:{';'.join(sorted(accessions))}"
        n_peptides = _int(row.get("Number of Peptides", ""))
        n_unique = _int(row.get("Number of Unique Peptides", ""))
        coverage = row.get("Sequence Coverage Fraction", "")
        status = _target_decoy(row.get("Protein Decoy/Contaminant/Target", ""))
        q_value = _number(row.get("Protein QValue", ""))
        groups.append(
            {
                "protein_group_id": group_id,
                "dataset_id": dataset_id,
                "protein_accessions": sorted(accessions),
                "genes": _split(row.get("Gene", "")),
                "target_decoy": status,
                "q_value": q_value,
                "sequence_coverage": _number(str(coverage).split("|")[0]),
                "unique_peptides": n_unique,
                "shared_peptides": (
                    n_peptides - n_unique if n_peptides is not None and n_unique is not None else None
                ),
            }
        )
        # The two columns of a block encode "nothing" differently, and reading both one way was a
        # defect until 0.18.0: an intensity of 0 (or blank) means NOT measured and is no row, but a
        # spectral count of 0 IS a measurement -- no qualifying PSM in that sample group
        # (QuantProject:DEF-PROT-SPC, "0 is a real zero here"). Dropping it stored a real zero as NA.
        for columns, definition, parse in (
            (intensity_cols, defs.PROTEIN_INTENSITY.definition_id, _intensity),
            (count_cols, defs.PROTEIN_SPECTRAL_COUNT.definition_id, _number),
        ):
            for reported, column in columns.items():
                value = parse(row.get(column, ""))
                if value is None:
                    continue
                run = run_names.resolve(reported) or reported
                quants.append(
                    {
                        "assay_id": f"{dataset_id}:{run}:label_free",
                        "feature_type": "protein_group",
                        "feature_id": group_id,
                        "value": value,
                        "detection_type": None,
                        "pip_q_value": None,
                        "mbr_kept": None,
                        "definition_id": definition,
                    }
                )
    return groups, quants, accepted_group_count(groups)
