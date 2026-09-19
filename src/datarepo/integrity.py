"""Referential checks run before a bundle is written.

Parquet has no foreign keys, so nothing stops a bundle from shipping a quantity whose feature ID
names a peptidoform that is not in the peptidoform table. An agent asking "how much of protein X is
in run Y" would simply get nothing back, and would have no way to tell a missing measurement from a
broken link.

These checks are not advisory. A dangling reference is an ingester bug, not a property of the data,
so it stops the write rather than becoming a Finding: a Finding is for something true about the
dataset, and this would be something false about the bundle.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

#: (table, column, target table, target column). Multivalued columns are named with a `[]` suffix.
REFERENCES: tuple[tuple[str, str, str, str], ...] = (
    ("samples", "dataset_id", "datasets", "dataset_id"),
    ("sample_characteristics", "sample_id", "samples", "sample_id"),
    ("runs", "dataset_id", "datasets", "dataset_id"),
    ("assays", "run_id", "runs", "run_id"),
    ("assays", "sample_id", "samples", "sample_id"),
    ("psms", "run_id", "runs", "run_id"),
    ("psms", "protein_accessions[]", "proteins", "protein_accession"),
    ("peptidoforms", "dataset_id", "datasets", "dataset_id"),
    ("peptidoforms", "protein_group_id", "protein_groups", "protein_group_id"),
    ("peptidoforms", "protein_accessions[]", "proteins", "protein_accession"),
    ("protein_groups", "dataset_id", "datasets", "dataset_id"),
    ("protein_groups", "protein_accessions[]", "proteins", "protein_accession"),
    ("ptm_sites", "dataset_id", "datasets", "dataset_id"),
    ("ptm_sites", "protein_accession", "proteins", "protein_accession"),
    ("quant_values", "assay_id", "assays", "assay_id"),
    ("quant_values", "definition_id", "definitions", "definition_id"),
    ("metrics", "definition_id", "definitions", "definition_id"),
    ("findings", "dataset_id", "datasets", "dataset_id"),
    ("findings", "run_id", "runs", "run_id"),
    ("provenance_records", "dataset_id", "datasets", "dataset_id"),
    ("search_modifications", "dataset_id", "datasets", "dataset_id"),
)

#: `QuantValue.feature_id` points into whichever table `feature_type` names.
FEATURE_TABLES = {
    "peptidoform": ("peptidoforms", "peptidoform_id"),
    "protein_group": ("protein_groups", "protein_group_id"),
    "ptm_site": ("ptm_sites", "ptm_site_id"),
    "glycopeptide": ("glycopeptides", "glycopeptide_id"),
    "proteoform": ("proteoform_inferences", "proteoform_id"),
    "protein": ("proteins", "protein_accession"),
}

#: Columns whose values must be unique within a bundle.
IDENTIFIERS = (
    ("datasets", "dataset_id"),
    ("samples", "sample_id"),
    ("runs", "run_id"),
    ("assays", "assay_id"),
    ("psms", "psm_id"),
    ("peptidoforms", "peptidoform_id"),
    ("protein_groups", "protein_group_id"),
    ("proteins", "protein_accession"),
    ("ptm_sites", "ptm_site_id"),
    ("definitions", "definition_id"),
    ("findings", "finding_id"),
)


def _values(rows: Iterable[dict[str, Any]], column: str) -> set[Any]:
    if column.endswith("[]"):
        name = column[:-2]
        return {v for row in rows for v in (row.get(name) or ())}
    return {row[column] for row in rows if row.get(column) is not None}


def check(tables: dict[str, Sequence[dict[str, Any]]]) -> list[str]:
    """Every broken reference and duplicate identifier in a set of table rows.

    Args:
        tables: `{table name: rows}` for the tables the bundle will hold. Tables that are absent
            are treated as empty, which is normal: a bundle holds only the tables its producer
            filled.

    Returns:
        Human-readable problems, empty when the bundle is sound.
    """
    problems: list[str] = []

    for table, column in IDENTIFIERS:
        rows = tables.get(table) or []
        seen: set[Any] = set()
        duplicates: set[Any] = set()
        for row in rows:
            value = row.get(column)
            if value is None:
                continue
            if value in seen:
                duplicates.add(value)
            seen.add(value)
        if duplicates:
            sample = ", ".join(str(d) for d in sorted(duplicates, key=str)[:3])
            problems.append(
                f"{table}.{column}: {len(duplicates)} duplicate identifier(s), e.g. {sample}"
            )

    for table, column, target, target_column in REFERENCES:
        rows = tables.get(table) or []
        if not rows:
            continue
        known = _values(tables.get(target) or [], target_column)
        dangling = _values(rows, column) - known
        if dangling:
            sample = ", ".join(str(d) for d in sorted(dangling, key=str)[:3])
            problems.append(
                f"{table}.{column} -> {target}.{target_column}: {len(dangling)} value(s) with no "
                f"matching row, e.g. {sample}"
            )

    quant = tables.get("quant_values") or []
    by_type: dict[str, set[Any]] = {}
    for row in quant:
        by_type.setdefault(row.get("feature_type"), set()).add(row.get("feature_id"))
    for feature_type, ids in by_type.items():
        target = FEATURE_TABLES.get(feature_type)
        if target is None:
            problems.append(f"quant_values.feature_type: '{feature_type}' names no table")
            continue
        known = _values(tables.get(target[0]) or [], target[1])
        dangling = ids - known
        if dangling:
            sample = ", ".join(str(d) for d in sorted(dangling, key=str)[:3])
            problems.append(
                f"quant_values.feature_id ({feature_type}) -> {target[0]}.{target[1]}: "
                f"{len(dangling)} value(s) with no matching row, e.g. {sample}"
            )
    return problems
