"""MetaMorpheus's PTM site occupancy -> `ptm_stoichiometry` rows (D29).

MetaMorpheus writes, per protein group and per sample group, two cells: `CountOccupancy_<label>` and
`IntensityOccupancy_<label>`. pyMzLib `read_occupancy` parses them with mzLib's own parser; this
module turns its entries into rows and computes nothing about occupancy. The definitions are
QuantProject's (`DEF-OCC-*`), and three of them decide how:

- **DEF-OCC-ACCESSION.** A cell's `|` segments skip every protein with no entry, with no placeholder,
  so segment i is NOT accession i whenever a member has no modified site. It is the fourth `|`-list
  in MetaMorpheus's output that cannot be zipped by position (0.13.0, 0.15.0, 0.19.0 were the other
  three). So the segments are assigned to accessions by the one thing that can tell: every entry's
  residue must match its modification's motif in that accession's searched sequence, and the
  segments keep the accessions' order. An assignment that is not unique is not guessed; its
  entries are counted and reported.
- **DEF-OCC-KEY.** `pos{p}` is 1-based in the accession's sequence, 0 for the protein N-terminus and
  Length + 1 for the C-terminus. `ptm_sites` keys a terminal modification on the residue it sits on,
  so p = 0 becomes position 1 `@protein_n_term` and p = Length + 1 becomes position Length
  `@protein_c_term`. Measured on PXD036557 and PXD051644 before this was written: 11,370 of 11,388
  entries land on an existing `ptm_sites` key this way (all 133 N-terminal ones included); the other
  18 are decoy groups (never in `ptm_sites`) and one protein our sites do not hold.
- **DEF-OCC-COUNTONLY.** Count and intensity entries are joined per (site, run) into one row and its
  state: quantified, floor, or count-only. Absent is no row.

Everything not stored is counted by reason and becomes a finding: nothing is dropped silently.
"""

from __future__ import annotations

import itertools
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import definitions as defs
from ..readers import ReaderLog, read_occupancy
from ..usi import RunNameMap
from .protein_db import ProteinSequences

#: Past this many candidate assignments of segments to accessions, the cell is reported rather than
#: searched. Groups are small; this bounds a pathological one.
MAX_ASSIGNMENTS = 20_000

#: pyMzLib's `failed_fields` / truncation mean part of a cell never reached us.
_TRUNCATED = "cell_truncated"


@dataclass
class OccupancyResult:
    rows: list[dict[str, Any]] = field(default_factory=list)
    entries: int = 0
    #: `{reason: entries}` for every entry not stored.
    not_stored: Counter = field(default_factory=Counter)
    truncated_cells: int = 0
    failed_fields: list[str] = field(default_factory=list)
    #: Cells whose segments did not line up with their accessions and were resolved by sequence.
    realigned_cells: int = 0
    #: Up to `MAX_DUPLICATE_EXAMPLES` dropped duplicates whose values differ from the stored row.
    differing_duplicates: list[dict[str, Any]] = field(default_factory=list)


MAX_DUPLICATE_EXAMPLES = 10


def _duplicate(out: OccupancyResult, row: dict[str, Any], group_id: str, basis: str, same: bool) -> None:
    """Count a second entry for a (site, run) that already has a row, by whether it could matter.

    The first entry in file order is kept. That is safe only when the dropped one says the same
    thing (aging 069, DATAREPO-53), so the two cases are counted apart, and so is whether the second
    came from the same protein group (MetaMorpheus writing one group twice, aging's S34) or from
    another group holding the same accession.
    """
    where = "same protein group" if group_id == row["protein_group_id"] else "another protein group"
    what = "identical values" if same else "DIFFERENT values, first in file kept"
    out.not_stored[f"duplicate entry for one site and run ({what}; {where})"] += 1
    if not same and len(out.differing_duplicates) < MAX_DUPLICATE_EXAMPLES:
        out.differing_duplicates.append({
            "ptm_site_id": row["ptm_site_id"], "assay_id": row["assay_id"], "basis": basis,
            "kept_group": row["protein_group_id"], "dropped_group": group_id,
        })


def _motif(modification: str) -> str | None:
    """The residue letter a MetaMorpheus `IdWithMotif` names (`Phosphorylation on S` -> `S`)."""
    head, sep, tail = modification.rpartition(" on ")
    tail = tail.strip()
    return tail if sep and len(tail) == 1 else None


def _fits(entry: dict[str, Any], sequence: str | None) -> bool:
    """Can this entry belong to a protein with this sequence?"""
    if not sequence:
        return False
    p = int(entry["position"])
    if p == 0 or p == len(sequence) + 1:
        return True  # a terminus slot: any protein has one
    if not 1 <= p <= len(sequence):
        return False
    motif = _motif(str(entry["modification"]))
    return motif in (None, "X") or sequence[p - 1] == motif


def _assign(segments: dict[int, list[dict]], accessions: list[str], sequences: ProteinSequences) -> list[str] | None:
    """Accession for each segment index, or None when it cannot be told uniquely.

    Segments are a subsequence of the accessions in order (DEF-OCC-ACCESSION), so a candidate is an
    increasing choice of accessions; it holds when every entry fits its accession's sequence.
    """
    k = len(segments)
    order = sorted(segments)

    def seq(acc: str) -> str | None:
        found = sequences.get(acc)
        return found[0] if found else None

    def holds(choice: tuple[int, ...]) -> bool:
        return all(_fits(e, seq(accessions[a])) for s, a in zip(order, choice) for e in segments[s])

    if k == len(accessions):
        choice = tuple(range(k))
        return [accessions[a] for a in choice] if holds(choice) else None
    if k > len(accessions):
        return None
    valid = []
    for n, choice in enumerate(itertools.combinations(range(len(accessions)), k)):
        if n >= MAX_ASSIGNMENTS:
            return None
        if holds(choice):
            valid.append(choice)
            if len(valid) > 1:
                return None
    return [accessions[a] for a in valid[0]] if len(valid) == 1 else None


def _site_key(dataset_id: str, accession: str, sequence: str | None, entry: dict[str, Any]) -> str | None:
    """The `ptm_sites` key this entry describes (DEF-OCC-KEY), or None without a sequence."""
    if not sequence:
        return None
    p = int(entry["position"])
    name = str(entry["modification"])
    if p == 0 or entry.get("is_n_terminus"):
        position, suffix = 1, "@protein_n_term"
    elif p == len(sequence) + 1:
        position, suffix = len(sequence), "@protein_c_term"
    else:
        position, suffix = p, ""
    if not 1 <= position <= len(sequence):
        return None
    return f"{dataset_id}:{accession}:{sequence[position - 1]}{position}:{name}{suffix}"


def rows(
    path: Path,
    dataset_id: str,
    *,
    run_names: RunNameMap,
    sequences: ProteinSequences,
    site_ids: set[str],
    group_ids: set[str],
    assay_ids: set[str],
    log: ReaderLog | None = None,
) -> OccupancyResult:
    """`ptm_stoichiometry` rows for one label-free, design-less search.

    Args:
        path: the search's `AllQuantifiedProteinGroups.tsv` (or `AllProteinGroups.tsv`).
        run_names: deposited run names, to map each `<label>` to a run.
        sequences: the searched databases, to assign segments and read residues.
        site_ids: the bundle's `ptm_sites` keys; an entry keyed elsewhere is not stored.
        group_ids: the bundle's protein group ids.
        assay_ids: the bundle's assay ids; a run with no label-free assay stores nothing.
    """
    read = read_occupancy(path, log)
    # A private map: a label that is not a run must not be reported as an unmatched USI run name.
    labels = RunNameMap(run_names.deposited)
    out = OccupancyResult(
        entries=len(read.records),
        truncated_cells=int(getattr(read, "truncated_cell_count", 0) or 0),
        failed_fields=list(getattr(read, "failed_fields", []) or []),
    )

    cells: dict[tuple[str, str, str], dict[int, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for entry in read.records:
        if entry.get("cell_is_truncated"):
            out.not_stored[_TRUNCATED] += 1
            continue
        key = (str(entry["protein_group_name"]), str(entry["sample_label"]), str(entry["basis"]))
        cells[key][int(entry["entity_index"])].append(entry)

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    #: (group id, label, basis) of cells present in the file but not assignable to accessions.
    unassigned: set[tuple[str, str, str]] = set()
    for (group_name, label, basis), segments in sorted(cells.items()):
        n_entries = sum(len(v) for v in segments.values())
        accessions = [a for a in group_name.split("|") if a]
        if all(a.startswith("DECOY_") for a in accessions):
            out.not_stored["decoy group"] += n_entries
            continue
        group_id = f"{dataset_id}:{';'.join(sorted(accessions))}"
        if group_id not in group_ids:
            out.not_stored["protein group not in the bundle"] += n_entries
            continue
        run = labels.resolve(label)
        if run is None:
            out.not_stored["label is not a deposited run (a design's sample group?)"] += n_entries
            continue
        assigned = _assign(segments, accessions, sequences)
        if assigned is None:
            out.not_stored["segment's accession not determinable from the sequences"] += n_entries
            unassigned.add((group_id, label, basis))
            continue
        if len(segments) != len(accessions):
            out.realigned_cells += 1
        assay_id = f"{dataset_id}:{run}:label_free"
        if assay_id not in assay_ids:
            out.not_stored["run has no label-free assay"] += n_entries
            continue
        for index, accession in zip(sorted(segments), assigned):
            sequence = (sequences.get(accession) or [None])[0]
            for entry in segments[index]:
                site = _site_key(dataset_id, accession, sequence, entry)
                if site is None or site not in site_ids:
                    out.not_stored["site not in ptm_sites"] += 1
                    continue
                row = merged.setdefault((site, assay_id), {
                    "ptm_site_id": site,
                    "assay_id": assay_id,
                    "denominator_grouping": "run",
                    "sample_label": label,
                    "protein_group_id": group_id,
                    "mm_position": int(entry["position"]),
                    "mm_modification": str(entry["modification"]),
                    "definition_id": defs.OCCUPANCY.definition_id,
                })
                if basis == "count":
                    if row.get("n_covering_psms") is not None:
                        same = (row["modified_fraction_count"], row["n_modified_psms"], row["n_covering_psms"]) == (
                            entry["fraction"], int(entry["numerator"]), int(entry["denominator"])
                        )
                        _duplicate(out, row, group_id, basis, same)
                        continue
                    row["modified_fraction_count"] = entry["fraction"]
                    row["n_modified_psms"] = int(entry["numerator"])
                    row["n_covering_psms"] = int(entry["denominator"])
                    row["count_is_ceiling"] = int(entry["numerator"]) == int(entry["denominator"])
                elif basis == "intensity":
                    if row.get("intensity_total") is not None:
                        same = (row["modified_fraction_intensity"], row["intensity_modified"], row["intensity_total"]) == (
                            entry["fraction"], float(entry["numerator"]), float(entry["denominator"])
                        )
                        _duplicate(out, row, group_id, basis, same)
                        continue
                    row["modified_fraction_intensity"] = entry["fraction"]
                    row["intensity_modified"] = float(entry["numerator"])
                    row["intensity_total"] = float(entry["denominator"])
                    row["intensity_is_floor"] = float(entry["fraction"]) == 0.0 and float(entry["numerator"]) == 0.0
                    row["intensity_is_ceiling"] = float(entry["fraction"]) == 1.0
                else:
                    out.not_stored[f"unknown basis {basis}"] += 1

    for row in merged.values():
        if row.get("intensity_total") is None:
            # An intensity cell that exists but could not be assigned to an accession is NOT
            # "nothing was quantified": calling it count_only would state a falsehood.
            key = (row["protein_group_id"], row["sample_label"], "intensity")
            row["occupancy_state"] = "intensity_unassigned" if key in unassigned else "count_only"
        elif row["intensity_is_floor"]:
            row["occupancy_state"] = "floor"
        else:
            row["occupancy_state"] = "quantified"
    out.rows = [merged[k] for k in sorted(merged)]
    return out
