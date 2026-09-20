"""Referential checks run before a bundle is written.

Parquet has no foreign keys, so nothing stops a bundle from shipping a quantity whose feature ID
names a peptidoform that is not in the peptidoform table. An agent asking "how much of protein X is
in run Y" would simply get nothing back, and would have no way to tell a missing measurement from a
broken link.

These checks are not advisory. A dangling reference is an ingester bug, not a property of the data,
so it stops the write rather than becoming a Finding: a Finding is for something true about the
dataset, and this would be something false about the bundle.

One escape exists, and only one. A producer can write the *same* row twice -- MetaMorpheus wrote
one protein group three times in PXD027318, byte-identical in every column (aging thread 015). Two
identical rows for one identifier carry no information the one row does not, so
`collapse_exact_duplicates` drops the copies and records what it dropped. Rows that share an
identifier and differ anywhere are still refused, because then the producer is saying two different
things about one thing and someone has to decide which is true. Strict check, lossless escape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, MutableSequence, Sequence

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

#: Tables with no single identifier column whose rows must still be unique on a natural key.
#: `quant_values` is the one that matters: it has no ID at all, so nothing stopped a duplicated
#: source row from writing the same measurement twice, and a caller summing intensities would have
#: double-counted it with no way to tell. Verified unique on PXD036557 and PXD032202 before it was
#: made a rule. `metrics` is deliberately absent -- the same metric legitimately arrives from two
#: sources (provenance and results.txt), which `reconcile.metric_conflicts` compares instead.
COMPOSITE_IDENTIFIERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("quant_values", ("assay_id", "feature_type", "feature_id", "definition_id")),
)

#: A study layer's natural keys, by layer and table. Not yet enforced, because nothing writes these
#: tables: `age_effect` is the output of a modelling stage that runs long after a search, and how
#: those rows reach a bundle is DATAREPO-20 rather than a guess.
#:
#: They are declared now anyway, and a test asserts every study table has either an identifier or an
#: entry here. `quant_values` shipped with no key at all and a duplicated source row wrote one
#: measurement three times, which nothing could have caught; the moment to decide a key is while the
#: table is empty. `aging:DEF-AGE-EFFECT v1` section 2 gives `age_effects` its key outright, and
#: every component of it is forced by a benchmark question -- `estimator` because count- and
#: intensity-based occupancy differ about threefold, `quant_basis` because H8+ asks whether MBR
#: changes the answer, `stratum` because D13 asks whether a decline is seen in both sexes.
STUDY_COMPOSITE_IDENTIFIERS: dict[str, dict[str, tuple[str, ...]]] = {
    "aging": {
        "sample_ages": ("sample_id",),
        "age_effects": (
            "dataset_id", "feature_id", "response", "estimator", "quant_basis", "model_form",
            "stratum",
        ),
        # Same key as the fit it refuses, so a caller can look up the refusal for the exact fit
        # they asked for. `feature_id` is nullable here and part of the key anyway: a dataset-level
        # refusal such as `no_age_metadata` is one row with no feature, and there is only one of it.
        "age_effect_refusals": (
            "dataset_id", "feature_id", "response", "estimator", "quant_basis", "model_form",
            "stratum",
        ),
        "age_effect_meta": (
            "feature_id", "response", "estimator", "quant_basis", "stratum", "tissue",
            "acquisition", "quant_method",
        ),
        "organelle_age_summaries": ("compartment", "organism", "organism_part", "response"),
        "clock_features": ("clock_id", "feature_type", "feature_id"),
        "age_mappings": ("organism", "age_from", "age_to"),
    },
}

#: Tables where a row is a *thing* and its identifier names that thing, so two identical rows are
#: one thing written twice and collapsing them loses nothing.
#:
#: `psms` and `findings` are deliberately absent. A row there is an *event*, and the number of rows
#: is itself a reported number: two identical PSM rows may be two observations that the columns we
#: store cannot tell apart, so collapsing them would quietly change a headline count. A duplicate
#: `psm_id` is an identifier-construction bug in this ingester, and it should stop the write and be
#: fixed here rather than be absorbed.
COLLAPSIBLE: frozenset[str] = frozenset(
    {
        "datasets",
        "samples",
        "runs",
        "assays",
        "peptidoforms",
        "protein_groups",
        "proteins",
        "ptm_sites",
        "definitions",
        "quant_values",
    }
)


@dataclass(frozen=True)
class Collapse:
    """One group of rows that were identical in every column and became one row."""

    table: str
    key: tuple[str, ...]
    identifier: str
    written: int
    """How many identical rows the producer wrote, including the one that was kept."""

    @property
    def dropped(self) -> int:
        return self.written - 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "key": list(self.key),
            "identifier": self.identifier,
            "written": self.written,
            "dropped": self.dropped,
        }


def _keys() -> dict[str, tuple[str, ...]]:
    keys = {table: (column,) for table, column in IDENTIFIERS}
    keys.update(dict(COMPOSITE_IDENTIFIERS))
    return keys


def _hashable(value: Any) -> Any:
    """A comparable form of a cell, so list-valued columns compare by value rather than identity."""
    if isinstance(value, (list, tuple)):
        return tuple(_hashable(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _hashable(v)) for k, v in value.items()))
    return value


def _fingerprint(row: Mapping[str, Any], columns: Sequence[str]) -> tuple[Any, ...]:
    return tuple(_hashable(row.get(c)) for c in columns)


def collapse_exact_duplicates(
    tables: Mapping[str, MutableSequence[dict[str, Any]]],
) -> list[Collapse]:
    """Drop rows that repeat an earlier row of the same table in every column.

    The lists are edited in place, keeping the first of each identical set and the original row
    order. A set of rows that shares an identifier but differs anywhere is left untouched, so
    `check` still refuses it: the producer is then asserting two different things about one thing,
    and that is not ours to resolve (aging thread 015, AGING-Q2).

    Args:
        tables: `{table name: rows}`. Tables not in `COLLAPSIBLE` are ignored whether or not they
            are present, because a repeated row there may be a repeated observation.

    Returns:
        One `Collapse` per identifier that was written more than once, in table then identifier
        order. Empty is the normal case; a non-empty result belongs in the bundle's findings, not
        in a log, because it is something true about the producer's output.
    """
    collapses: list[Collapse] = []
    for table, key in sorted(_keys().items()):
        if table not in COLLAPSIBLE:
            continue
        rows = tables.get(table)
        if not rows:
            continue
        columns = sorted({c for row in rows for c in row})
        groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for row in rows:
            groups.setdefault(_fingerprint(row, key), []).append(row)
        dropped: set[int] = set()
        for identifier, group in groups.items():
            if len(group) == 1:
                continue
            if len({_fingerprint(r, columns) for r in group}) != 1:
                continue  # a real disagreement; check() refuses the bundle
            dropped.update(id(r) for r in group[1:])
            collapses.append(
                Collapse(
                    table=table,
                    key=key,
                    identifier=":".join(str(part) for part in identifier),
                    written=len(group),
                )
            )
        if dropped:
            kept = [row for row in rows if id(row) not in dropped]
            rows[:] = kept
    return sorted(collapses, key=lambda c: (c.table, c.identifier))


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

    for table, key in sorted(_keys().items()):
        rows = tables.get(table) or []
        seen: set[Any] = set()
        duplicates: set[Any] = set()
        for row in rows:
            value = _fingerprint(row, key)
            if any(v is None for v in value):
                continue
            if value in seen:
                duplicates.add(value)
            seen.add(value)
        if duplicates:
            names = ".".join(key) if len(key) == 1 else "(" + ", ".join(key) + ")"
            sample = ", ".join(
                ":".join(str(part) for part in d) for d in sorted(duplicates, key=str)[:3]
            )
            problems.append(
                f"{table}.{names}: {len(duplicates)} duplicate identifier(s), e.g. {sample}. "
                f"Rows sharing an identifier and identical in every column are collapsed before "
                f"this check, so these differ somewhere and the producer has to say which is right."
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
