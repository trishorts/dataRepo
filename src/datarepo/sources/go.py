"""`go`'s two output files -> `protein_localizations` and `organelle_term_categories` rows (G53).

go (the engine) annotates every non-decoy protein group of a search with GO terms, and writes two
files per run (go D28): an **annotation file**, one row per (group, term), map-independent; and one
**category file per consumer map**, one row per (term, category, subcategory). The contract is go's
own, `go/design/PLAN.md` S5-S6 and rulings D1-D30. This module reads it and refuses a file that does
not keep it; it computes nothing about GO.

What it checks, each refusing the file on failure (``IngestError``):

- **A released mzLib wrote it.** ``#!mzlib_release none`` is a build with no release tag. A reader may
  be built and tested against such a file (GO-A1), but it is never ingested; the refusal names the
  commit from ``#!mzlib_version`` (go 010 section 2). ``allow_prerelease`` exists for tests only.
- **The five header counters are the rows' own** (go D26), each counting groups at
  ``q_value <= counter_q_value_max`` (D29), recounted here so a reader tests go's writer.
- **Every row agrees with the header** on ``go_release`` and both sha256s, a non-empty ``go_id`` means
  ``annotated`` (D19), and ``n_with`` is the size of ``accession_used`` (D22).
- **No accession sits in two groups.** go has never seen it (go 010 section 3), and a per-accession
  row would then have two group q-values. Refused until MetaMorpheus says whether parsimony can do it
  (our go 011).
- **Coverage** (go 009 section 4): every ``go_id`` of a category file is a term of its annotation file,
  under the same ``go_release`` and ontology sha256. A mismatched pair stored would be a join that
  silently drops categories.

What it does NOT store, and says so in the result rather than dropping it silently:

- **Terms outside cellular_component.** ``protein_localizations`` is GO-CC by definition; go's file
  also carries biological_process and molecular_function rows.
- **``annotation_status``.** Every stored row carries a term, so it would always read ``annotated``;
  a group with no term has no ``protein_localizations`` row at all and is counted in ``not_stored``.
  go's other per-row evidence (``protein_group``, ``q_value``, ``n_members``, ``n_with``,
  ``inherited``, ``propagated``) IS stored, from schema 0.0.10 (D28: one schema change with the
  runner's ``gene_resolutions``).
"""

from __future__ import annotations

import csv
import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import IngestError

ANNOTATION_FORMAT = "1"
CATEGORY_FORMAT = "1"
ANNOTATION_COLUMNS = (
    "protein_group", "accession_used", "go_id", "go_name", "aspect", "evidence", "inherited",
    "propagated", "n_members", "n_with", "annotation_status", "q_value", "go_release",
    "go_obo_sha256", "annotation_db_sha256",
)
CATEGORY_COLUMNS = ("go_id", "category", "subcategory")
STATUSES = ("annotated", "no_go_terms", "no_entry", "contaminant")
#: The aspect `protein_localizations` holds.
CELLULAR_COMPONENT = "cellular_component"


@dataclass
class GoAnnotation:
    """One parsed and checked annotation file."""

    path: Path
    header: dict[str, str]
    rows: list[dict[str, str]]
    sha256: str
    #: Rows read but not stored, by reason, so nothing is dropped without a count.
    not_stored: Counter = field(default_factory=Counter)

    @property
    def go_release(self) -> str:
        return self.header["go_release"]

    @property
    def mzlib_release(self) -> str:
        return self.header.get("mzlib_release", "")


@dataclass
class GoCategories:
    """One parsed category file: one consumer map's categories under one ontology release."""

    path: Path
    header: dict[str, str]
    map_name: str
    map_version: str
    map_sha256: str
    rows: list[dict[str, str]]
    sha256: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read(path: Path, format_key: str, format_version: str, columns: tuple[str, ...]):
    """`#!key value` header lines, then a tab-separated table with a header row."""
    header: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        lines = f.read().split("\n")
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("#!"):
            key, _, value = line[2:].partition(" ")
            if key in header:
                raise IngestError(f"{path.name}: header key {key!r} appears twice")
            header[key] = value.strip()
            continue
        body_start = i
        break
    if not header or next(iter(header)) != format_key:
        raise IngestError(f"{path.name}: the first header line must be `#!{format_key}`")
    if header[format_key] != format_version:
        raise IngestError(
            f"{path.name}: {format_key} {header[format_key]!r}; this reader knows {format_version}"
        )
    reader = csv.reader([l for l in lines[body_start:] if l != ""], delimiter="\t")
    names = next(reader, None)
    if names is None or tuple(names) != columns:
        raise IngestError(f"{path.name}: columns {names} are not go's {list(columns)}")
    rows = []
    for n, cells in enumerate(reader, start=body_start + 2):
        if len(cells) != len(columns):
            raise IngestError(f"{path.name}: line {n} has {len(cells)} cells, not {len(columns)}")
        rows.append(dict(zip(columns, cells)))
    return header, rows


def _require_release(path: Path, header: dict[str, str], allow_prerelease: bool) -> None:
    release = header.get("mzlib_release")
    if release is None:
        raise IngestError(f"{path.name}: no `#!mzlib_release` line, so which code wrote it is unknown")
    if release == "none" and not allow_prerelease:
        commit = header.get("mzlib_version", "").partition("+")[2] or "unknown"
        raise IngestError(
            f"{path.name}: written by an unreleased mzLib (`#!mzlib_release none`, commit {commit}). "
            f"A pre-release file may be used to build and test a reader, never ingested (GO-A1)."
        )


def _split(cell: str) -> list[str]:
    return [x for x in cell.split(";") if x]


def _flag(cell: str) -> bool | None:
    """go's `true`/`false`; anything else is refused, and empty is NULL (unknown, not false)."""
    if cell == "":
        return None
    if cell in ("true", "false"):
        return cell == "true"
    raise IngestError(f"expected `true` or `false`, found {cell!r}")


def read_annotation(path: str | Path, *, allow_prerelease: bool = False) -> GoAnnotation:
    """Read and check one go annotation file.

    Raises:
        IngestError: any check in the module docstring fails.
    """
    path = Path(path)
    header, rows = _read(path, "go_annotation_format", ANNOTATION_FORMAT, ANNOTATION_COLUMNS)
    _require_release(path, header, allow_prerelease)
    for key in ("go_release", "go_obo_sha256", "annotation_db_sha256", "counter_q_value_max",
                "n_multi_member_groups", *(f"status_{s}" for s in STATUSES)):
        if key not in header:
            raise IngestError(f"{path.name}: header has no `#!{key}`")
    q_max = float(header["counter_q_value_max"])

    group_status: dict[str, str] = {}
    group_q: dict[str, float] = {}
    group_members: dict[str, int] = {}
    groups_of: dict[str, set[str]] = defaultdict(set)
    for n, row in enumerate(rows, start=1):
        where = f"{path.name}: row {n} ({row['protein_group']}, {row['go_id'] or 'no term'})"
        for key in ("go_release", "go_obo_sha256", "annotation_db_sha256"):
            if row[key] != header[key]:
                raise IngestError(f"{where}: {key} {row[key]!r} differs from the header's {header[key]!r}")
        status = row["annotation_status"]
        if status not in STATUSES:
            raise IngestError(f"{where}: annotation_status {status!r} is not one of {STATUSES}")
        if row["go_id"] and status != "annotated":
            raise IngestError(f"{where}: carries a term but reads {status!r}; a term means annotated (go D19)")
        used = _split(row["accession_used"])
        if row["go_id"] and int(row["n_with"]) != len(used):
            raise IngestError(f"{where}: n_with {row['n_with']} but {len(used)} accession(s) used (go D22)")
        group = row["protein_group"]
        if group_status.setdefault(group, status) != status:
            raise IngestError(f"{where}: group has rows with two statuses")
        group_q[group] = float(row["q_value"])
        group_members[group] = int(row["n_members"])
        for accession in group.split("|"):
            groups_of[accession].add(group)

    shared = sorted(a for a, g in groups_of.items() if len(g) > 1)
    if shared:
        raise IngestError(
            f"{path.name}: {len(shared)} accession(s) sit in more than one group, e.g. {shared[:3]}. A "
            f"per-accession row would carry two group q-values; refused until MetaMorpheus says whether "
            f"parsimony can produce this (dataRepo go 011)."
        )

    counted = [g for g in group_status if group_q[g] <= q_max]
    recount = {f"status_{s}": sum(1 for g in counted if group_status[g] == s) for s in STATUSES}
    recount["n_multi_member_groups"] = sum(1 for g in counted if group_members[g] > 1)
    wrong = {k: (header[k], v) for k, v in recount.items() if int(header[k]) != v}
    if wrong:
        detail = ", ".join(f"{k} header {h} rows {v}" for k, (h, v) in sorted(wrong.items()))
        raise IngestError(
            f"{path.name}: header counters disagree with the rows at q_value <= {q_max} (go D26, D29): {detail}"
        )

    result = GoAnnotation(path=path, header=header, rows=rows, sha256=_sha256(path))
    for row in rows:
        if not row["go_id"]:
            result.not_stored[f"no term ({row['annotation_status']})"] += 1
        elif row["aspect"] != CELLULAR_COMPONENT:
            result.not_stored[f"aspect {row['aspect']}"] += 1
    return result


def read_categories(path: str | Path, *, allow_prerelease: bool = False) -> GoCategories:
    """Read and check one go category file (one consumer map).

    Raises:
        IngestError: a bad header or table, or an unreleased writer.
    """
    path = Path(path)
    header, rows = _read(path, "go_category_format", CATEGORY_FORMAT, CATEGORY_COLUMNS)
    _require_release(path, header, allow_prerelease)
    for key in ("go_release", "go_obo_sha256", "category_map"):
        if key not in header:
            raise IngestError(f"{path.name}: header has no `#!{key}`")
    parts = header["category_map"].split()
    if len(parts) != 3:
        raise IngestError(f"{path.name}: `#!category_map` must be `<name> <version> <sha256>`")
    seen = Counter((r["go_id"], r["category"], r["subcategory"]) for r in rows)
    repeated = [k for k, n in seen.items() if n > 1]
    if repeated:
        raise IngestError(f"{path.name}: {len(repeated)} (term, category, subcategory) row(s) repeat, e.g. {repeated[0]}")
    for n, row in enumerate(rows, start=1):
        if not row["go_id"] or not row["category"]:
            raise IngestError(f"{path.name}: row {n} lacks a go_id or a category")
    return GoCategories(
        path=path, header=header, map_name=parts[0], map_version=parts[1], map_sha256=parts[2],
        rows=rows, sha256=_sha256(path),
    )


def check_coverage(annotation: GoAnnotation, categories: GoCategories) -> None:
    """Refuse a category file that is not the pair of this annotation file (go 009 section 4).

    Raises:
        IngestError: a different ontology release or sha256, or a category term the annotation file
            does not carry.
    """
    for key in ("go_release", "go_obo_sha256"):
        if categories.header[key] != annotation.header[key]:
            raise IngestError(
                f"{categories.path.name}: {key} {categories.header[key]!r} is not the annotation "
                f"file's {annotation.header[key]!r}; the two files are not a pair"
            )
    terms = {r["go_id"] for r in annotation.rows if r["go_id"]}
    missing = sorted({r["go_id"] for r in categories.rows} - terms)
    if missing:
        raise IngestError(
            f"{categories.path.name}: {len(missing)} term(s) are not in {annotation.path.name}, e.g. "
            f"{missing[:3]}. Stored together, they would be a join that silently drops categories."
        )


def source_row(annotation: GoAnnotation) -> dict[str, Any]:
    """The `annotation_sources` row both tables cite."""
    # `annotation_sources` has no free-text column, so the version carries every pin: the ontology
    # release, the code that wrote the file, and the three sha256s a second run must match.
    return {
        "source_id": source_id(annotation),
        "owner_project": "go",
        "version": (
            f"{annotation.go_release}; mzLib {annotation.header.get('mzlib_version', '?')}; "
            f"file {annotation.sha256}; go.obo {annotation.header['go_obo_sha256']}; "
            f"annotation db {annotation.header['annotation_db_sha256']}"
        ),
        "doi": None,
    }


def source_id(annotation: GoAnnotation) -> str:
    return f"go:{annotation.go_release}:{annotation.sha256[:12]}"


def localization_rows(annotation: GoAnnotation) -> list[dict[str, Any]]:
    """`protein_localizations`: one row per (accession, CC term), over `accession_used` only (go D22).

    A group member that does not carry a term gets no row for it. Evidence codes stay `;`-joined as
    go wrote them.
    """
    src = source_id(annotation)
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in annotation.rows:
        if not row["go_id"] or row["aspect"] != CELLULAR_COMPONENT:
            continue
        for accession in _split(row["accession_used"]):
            out[(accession, row["go_id"])] = {
                "protein_accession": accession,
                "compartment": row["go_id"],
                "go_release": annotation.go_release,
                "evidence": row["evidence"] or None,
                "source_id": src,
                "protein_group": row["protein_group"],
                "q_value": float(row["q_value"]),
                "n_members": int(row["n_members"]),
                "n_with": int(row["n_with"]),
                "inherited": _flag(row["inherited"]),
                "propagated": _flag(row["propagated"]),
            }
    return [out[k] for k in sorted(out)]


def category_rows(categories: GoCategories, annotation: GoAnnotation) -> list[dict[str, Any]]:
    """`organelle_term_categories`: one row per (term, category, subcategory) under one map."""
    src = source_id(annotation)
    return [
        {
            "compartment": r["go_id"],
            "category_map_name": categories.map_name,
            "organelle_map_version": categories.map_version,
            "go_release": categories.header["go_release"],
            "organelle_category": r["category"],
            "organelle_subcategory": r["subcategory"] or None,
            "source_id": src,
        }
        for r in sorted(categories.rows, key=lambda r: (r["go_id"], r["category"], r["subcategory"]))
    ]
