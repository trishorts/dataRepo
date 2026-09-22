"""Build the query catalog: many immutable bundles into one DuckDB file.

Layer 2 of the architecture (FRAMEWORK section 2, roadmap step 2). Layer 1 is the product -- the
Parquet bundles are what gets cited and what a release freezes -- and this layer is a *derived*
artifact built from them and thrown away whenever it needs rebuilding. Nothing is ever written back
into a bundle, and deleting the catalog loses nothing.

Three things make it a catalog rather than a pile of Parquet:

* **It is one file.** Tables are materialised, not views over `read_parquet`, so the catalog can be
  copied to a server, mounted in a container or handed to an agent on its own (D1: it has to move).
* **Rows carry where they came from.** Every table gains `dataset_id` and `bundle_id`, so a
  cross-dataset answer can always be traced back to the bundle that holds the evidence.
* **Cross-dataset indexes exist.** A bundle can answer "what is in this dataset". Only the catalog
  can answer "which datasets have this protein", which is the question the repository exists for.

Like a bundle, a catalog is content-addressed on what went into it -- the bundle ids, the schema
version and the builder version -- so rebuilding from the same bundles is a no-op, and a catalog
that is cited alongside a release can be checked against the bundles it claims to hold.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import __version__
from ._tables import SCHEMA_VERSION, STUDY_TABLES, STUDY_VERSIONS, TABLES
from .bundle import BUNDLE_MANIFEST, QPX_VERSION
from .errors import CatalogError
from .integrity import (
    FEATURE_TABLES,
    IDENTIFIERS,
    REFERENCES,
    STUDY_COMPOSITE_IDENTIFIERS,
    STUDY_REFERENCES,
)
from .manifest import Manifest
from .study import STUDY_BUNDLE_MANIFEST, STUDY_DIR

#: Bumped when the shape of the catalog changes in a way a caller would notice. It is part of the
#: content hash, so a change to the builder gives every catalog a new id even from the same bundles.
#: Bumped when a build produces a different catalog from the same bundles. Separate from
#: `__version__` on purpose: a change to what `build` writes must re-id catalogs, and must NOT re-id
#: bundles holding byte-identical rows from an unchanged ingest path. "2" added the study layer's
#: tables; "3" fills them -- a study bundle's rows, their two provenance columns and
#: `catalog_study_bundles`; "4" adds `search_modifications_placed`. Same principle as
#: `manifest.CONTENT_FIELDS` one level down -- an id moves when its own content moves, and not
#: otherwise.
CATALOG_VERSION = "4"

#: Provenance columns prepended to every table. `dataset_id` is re-derived from the bundle rather
#: than trusted from the row, so a table without one (proteins, definitions) still gets it.
PROVENANCE_COLUMNS = ("dataset_id", "bundle_id")

#: Provenance columns prepended to every STUDY table. Deliberately not `PROVENANCE_COLUMNS`:
#: `dataset_id` there is a fact about the bundle, and a study bundle spans datasets -- an
#: `age_effect_meta` row is pooled across several by construction, so stating one would be false.
#: Study tables that *are* per dataset keep their own `dataset_id` column, which is a fact about the
#: row instead.
STUDY_PROVENANCE_COLUMNS = ("study_layer", "study_bundle_id")

#: Tables the catalog builds itself. They are not in the schema: they describe the catalog, not the
#: science, and a caller can tell them apart by this prefix.
CATALOG_TABLES = (
    "catalog_meta",
    "catalog_bundles",
    "catalog_study_bundles",
    "catalog_tables",
    "catalog_checks",
)

#: Derived cross-dataset tables. These are the reason the catalog exists.
DERIVED_TABLES = (
    "dataset_overview",
    "protein_index",
    "protein_datasets",
    "peptide_index",
    "search_modifications_placed",
)

#: Views that apply the producing search engine's acceptance rule, so no caller has to restate it.
#: The rule is target, `q_value` at or below 1% **and** `q_value_notch` at or below 1% where there
#: is one, **and** -- for PSMs -- a notch that actually resolved (aging thread 008, worth 12 rows
#: out of 26,594 on PXD036557); for protein groups, anything not a decoy -- contaminants count --
#: with a group q-value at or below 1%. It is the same rule `sources.identifications.producer_counts`
#: and `sources.quant.accepted_group_count` apply when a bundle reconciles itself, and
#: `tests/test_catalog.py` asserts the two agree so they cannot drift.
#:
#: **It is an acceptance rule, not a reproduction of MetaMorpheus's own count.** aging published it
#: as a recipe for rebuilding `aging:DEF-PSM-1PCT` from `AllPSMs.psmtsv`; it is exact on PXD036557
#: and six short of 183,029 on PXD032202 (aging thread 016), and aging is amending the definition
#: text to say so. The canonical number stays the producer's `results.txt` summary line, which is
#: what `metrics` holds and what the reconciliation compares against; these views are how the
#: catalog selects *rows*, and on a dataset where the predicate is imperfect they will differ from
#: the canonical count by a small margin and the `count_mismatch` finding will say by how much.
ACCEPTED_VIEWS: dict[str, str] = {
    "psms_1pct": (
        "SELECT * FROM psms WHERE target_decoy = 'target' AND q_value <= {t} "
        "AND (q_value_notch IS NULL OR q_value_notch <= {t}) "
        "AND coalesce(notch_ambiguous, false) = false"
    ),
    "peptidoforms_1pct": (
        "SELECT * FROM peptidoforms WHERE target_decoy = 'target' AND best_q_value <= {t} "
        "AND (best_q_value_notch IS NULL OR best_q_value_notch <= {t})"
    ),
    "protein_groups_1pct": (
        "SELECT * FROM protein_groups WHERE target_decoy <> 'decoy' AND q_value <= {t}"
    ),
}

#: Views that restate a table at a coarser grain than it is stored at, so a caller never has to.
#:
#: `ptm_sites` is keyed on the search engine's own name for a modification, which is the grain the
#: engine measured at and the only grain at which every site can be represented (aging 019 section
#: 3). One chemistry can reach a dataset under two names -- `Phosphorylation on S` from the search's
#: variable-mod list and `Phosphoserine on S` from a UniProt annotation are the same thing -- so the
#: stored table splits a handful of sites that a UNIMOD-keyed table merged: 2 in PXD027318 and 3 in
#: PXD032202, out of 20,044 and 13,527. This view puts them back together.
#:
#: The split is finer, not wrong, and this view is the proof: grouping the stored table this way
#: reproduces the UNIMOD-keyed table exactly -- all 20,044 and 13,527 groups, `n_psms` summing to
#: the old row's value and `best_q_value` to its minimum, zero mismatches. Storing the merged row
#: instead would have been storing coarser than the measurement, which is the half of the grain rule
#: (thread 018 section 3) that is easiest to break without noticing.
#:
#: A site whose chemistry has no UNIMOD term groups on its name instead, so two different unmapped
#: chemistries on one residue stay two rows. `_site_key_name` forbids ':' in a name, which is what
#: makes `coalesce` safe: a name can never be mistaken for an accession.
GRAIN_VIEWS: dict[str, str] = {
    "ptm_sites_by_chemistry": (
        "SELECT dataset_id, protein_accession, position, residue, modification, "
        "       coalesce(modification, modification_name) AS chemistry_key, "
        "       count(*) AS n_names, list(DISTINCT modification_name) AS modification_names, "
        "       sum(n_psms) AS n_psms, min(best_q_value) AS best_q_value, "
        "       min(best_ambiguity_level) AS best_ambiguity_level, "
        "       max(target_decoy) AS target_decoy "
        "FROM ptm_sites "
        "GROUP BY dataset_id, protein_accession, position, residue, modification, chemistry_key"
    ),
}

#: Point-lookup indexes. Built only where the column exists and is not a list: DuckDB's ART index
#: does not accept list types, and the list columns are covered by the derived tables instead.
INDEX_COLUMNS: tuple[tuple[str, str], ...] = (
    ("psms", "run_id"),
    ("psms", "peptidoform"),
    ("psms", "base_sequence"),
    ("psms", "usi"),
    ("peptidoforms", "base_sequence"),
    ("peptidoforms", "peptidoform"),
    ("peptidoforms", "protein_group_id"),
    ("protein_groups", "protein_group_id"),
    ("proteins", "protein_accession"),
    ("proteins", "gene"),
    ("ptm_sites", "protein_accession"),
    ("ptm_sites", "modification"),
    # The queryable identity of a site whose chemistry has no UNIMOD term (aging 019 section 3).
    ("ptm_sites", "modification_name"),
    ("quant_values", "feature_id"),
    ("quant_values", "assay_id"),
    ("assays", "sample_id"),
    ("runs", "dataset_id"),
    ("metrics", "name"),
    ("findings", "code"),
    ("protein_index", "protein_accession"),
    ("protein_datasets", "protein_accession"),
    ("peptide_index", "base_sequence"),
)


def _quote(value: str) -> str:
    """A SQL string literal. Paths on Windows go in here, so the escaping is not decorative."""
    return "'" + str(value).replace("'", "''") + "'"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"cannot read {path}: {exc}") from exc


@dataclass(frozen=True)
class BundleRef:
    """One written bundle, as the catalog sees it: its manifest and where it sits."""

    path: Path
    manifest: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "BundleRef":
        manifest_path = path / BUNDLE_MANIFEST
        if not manifest_path.is_file():
            raise CatalogError(f"{path} holds no {BUNDLE_MANIFEST}, so it is not a bundle")
        return cls(path=path, manifest=_read_json(manifest_path))

    @property
    def dataset_id(self) -> str:
        return str(self.manifest["dataset_id"])

    @property
    def bundle_id(self) -> str:
        return str(self.manifest["bundle_id"])

    @property
    def schema_version(self) -> str:
        return str(self.manifest.get("schema_version", "?"))

    @property
    def written_utc(self) -> str:
        return str(self.manifest.get("written_utc", ""))

    @property
    def row_counts(self) -> dict[str, int]:
        return {str(k): int(v) for k, v in (self.manifest.get("tables") or {}).items()}

    def table_path(self, table: str) -> Path | None:
        path = self.path / f"{table}.parquet"
        return path if path.is_file() else None


def discover_bundles(store: Path, dataset_id: str) -> list[BundleRef]:
    """Every bundle written for one dataset, oldest first.

    A dataset can have more than one: re-ingesting changed inputs writes a new content hash beside
    the old one rather than overwriting it, which is the whole point of content addressing.
    """
    root = Path(store) / dataset_id
    if not root.is_dir():
        return []
    found = [
        BundleRef.load(child)
        for child in sorted(root.iterdir())
        if child.is_dir() and (child / BUNDLE_MANIFEST).is_file()
    ]
    # `written_utc` is recorded to the second, so two bundles written in the same second would
    # otherwise order by hash -- which is arbitrary, and would make `--latest` mean "highest hash".
    # The manifest's own mtime breaks the tie with the resolution the clock in the file lacks.
    return sorted(
        found,
        key=lambda ref: (
            ref.written_utc,
            (ref.path / BUNDLE_MANIFEST).stat().st_mtime,
            ref.bundle_id,
        ),
    )


def select_bundles(
    manifest: Manifest,
    accessions: Sequence[str],
    *,
    store: Path | None = None,
    pins: dict[str, str] | None = None,
    latest: bool = False,
    release: str | None = None,
) -> list[BundleRef]:
    """Choose exactly one bundle per dataset, and refuse to guess.

    Args:
        manifest: the producing instance's manifest. It stays the contract here for the same reason
            it is the contract for ingest (D9): which datasets belong in the repository is the
            producer's recorded decision, not something inferred from what happens to be on disk.
        accessions: datasets to include. Each is looked up in the manifest, so one the producer
            marked `hold` or `exclude` is refused with their own reason.
        store: override the manifest's store.
        pins: `{accession: bundle id or unique prefix}`, for pinning a release to exact bundles.
        latest: when a dataset has several bundles and none is pinned, take the newest instead of
            refusing.
        release: the release this catalog is for. Every dataset must then be pinned, and `latest`
            is refused: a release that can silently pick up a later re-ingest is not a release
            (aging thread 011). Pinning is enforced here rather than merely defaulted, because the
            failure it prevents is invisible -- the catalog builds fine and says the wrong thing.

    Raises:
        CatalogError: a dataset has no bundle, a pin matches none or several, or a dataset has
            several bundles with no pin and no `latest`.
        DatasetExcluded: the producer marked the dataset unfit to load.
    """
    root = Path(store) if store else manifest.store
    pins = pins or {}
    if release:
        if latest:
            raise CatalogError(
                f"--release {release} and --latest are mutually exclusive. A release names the "
                f"exact bundles it was checked against; --latest would let it pick up a later "
                f"re-ingest silently. Pin each dataset with --bundle <accession>=<id>."
            )
        unpinned = [a for a in accessions if a not in pins]
        if unpinned:
            raise CatalogError(
                f"--release {release} needs every dataset pinned, and "
                f"{', '.join(sorted(unpinned))} {'is' if len(unpinned) == 1 else 'are'} not. Add "
                f"--bundle {unpinned[0]}=<id>; `datarepo build` without --release will list the "
                f"ids on offer."
            )
    chosen: list[BundleRef] = []
    for accession in accessions:
        manifest.dataset(accession)  # the producer's gate, and it raises for us
        candidates = discover_bundles(root, accession)
        if not candidates:
            raise CatalogError(
                f"{accession} has no bundle under {root}. Run `datarepo ingest` for it first."
            )
        pin = pins.get(accession)
        if pin:
            matches = [c for c in candidates if c.bundle_id.startswith(pin)]
            if len(matches) != 1:
                known = ", ".join(c.bundle_id for c in candidates)
                raise CatalogError(
                    f"{accession}: --bundle {pin} matches {len(matches)} of the bundles on disk "
                    f"({known})"
                )
            chosen.append(matches[0])
        elif len(candidates) == 1:
            chosen.append(candidates[0])
        elif latest:
            chosen.append(candidates[-1])
        else:
            listing = "\n    ".join(f"{c.bundle_id}  written {c.written_utc}" for c in candidates)
            raise CatalogError(
                f"{accession} has {len(candidates)} bundles and nothing says which one this "
                f"catalog is of:\n    {listing}\n  Pin it with --bundle "
                f"{accession}=<id>, or pass --latest to take the newest."
            )
    return chosen


@dataclass(frozen=True)
class StudyBundleRef:
    """One written study bundle, as the catalog sees it.

    Separate from `BundleRef` because the two are not interchangeable: a search bundle is one
    dataset's evidence and a study bundle is one layer's model results over however many datasets.
    They share a store and nothing else.
    """

    path: Path
    manifest: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "StudyBundleRef":
        manifest_path = path / STUDY_BUNDLE_MANIFEST
        if not manifest_path.is_file():
            raise CatalogError(f"{path} holds no {STUDY_BUNDLE_MANIFEST}, so it is not a study bundle")
        return cls(path=path, manifest=_read_json(manifest_path))

    @property
    def layer(self) -> str:
        return str(self.manifest["layer"])

    @property
    def bundle_id(self) -> str:
        return str(self.manifest["bundle_id"])

    @property
    def layer_version(self) -> str:
        return str(self.manifest.get("layer_version", "?"))

    @property
    def schema_version(self) -> str:
        return str(self.manifest.get("schema_version", "?"))

    @property
    def written_utc(self) -> str:
        return str(self.manifest.get("written_utc", ""))

    @property
    def row_counts(self) -> dict[str, int]:
        return {str(k): int(v) for k, v in (self.manifest.get("tables") or {}).items()}

    def table_path(self, table: str) -> Path | None:
        path = self.path / f"{table}.parquet"
        return path if path.is_file() else None


def discover_study_bundles(store: Path, layer: str) -> list[StudyBundleRef]:
    """Every study bundle written for one layer, oldest first. Same ordering rule as a dataset's."""
    root = Path(store) / STUDY_DIR / layer
    if not root.is_dir():
        return []
    found = [
        StudyBundleRef.load(child)
        for child in sorted(root.iterdir())
        if child.is_dir() and (child / STUDY_BUNDLE_MANIFEST).is_file()
    ]
    return sorted(
        found,
        key=lambda ref: (
            ref.written_utc,
            (ref.path / STUDY_BUNDLE_MANIFEST).stat().st_mtime,
            ref.bundle_id,
        ),
    )


def available_study_layers(store: Path) -> dict[str, list[StudyBundleRef]]:
    """Every layer the store holds a delivery for, so `build` can say what is on offer."""
    root = Path(store) / STUDY_DIR
    if not root.is_dir():
        return {}
    found = {}
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        bundles = discover_study_bundles(store, child.name)
        if bundles:
            found[child.name] = bundles
    return found


def select_study_bundles(
    store: Path,
    *,
    pins: dict[str, str] | None = None,
    latest: Sequence[str] = (),
    release: str | None = None,
) -> list[StudyBundleRef]:
    """Choose at most one study bundle per layer, and load none unless asked.

    **Study bundles are opt-in.** A build that names no layer gets the empty study tables it has had
    since 0.6.0, which is the honest default: a catalog that silently picked up whichever model
    results happened to be in the store would answer a benchmark question differently from one
    built an hour earlier, with nothing in either to say why.

    Args:
        store: the instance's bundle store; study bundles live under its `_study/` directory.
        pins: `{layer: bundle id or unique prefix}`.
        latest: layers to take the newest delivery of.
        release: the release this catalog is for. `latest` is then refused, for the same reason
            D11 refuses it for datasets -- a release that can pick up a later re-fit is not a
            release.

    Raises:
        CatalogError: a layer has no delivery, a pin matches none or several, a layer is both
            pinned and asked for latest, or `latest` is combined with `release`.
    """
    pins = dict(pins or {})
    latest = list(latest)
    both = sorted(set(pins) & set(latest))
    if both:
        raise CatalogError(
            f"study layer {', '.join(both)} is both pinned with --study and asked for with "
            f"--study-latest. Say which delivery this catalog is of, once."
        )
    if release and latest:
        raise CatalogError(
            f"--release {release} and --study-latest are mutually exclusive. A release names the "
            f"exact deliveries it was checked against; --study-latest would let it pick up a later "
            f"re-fit silently. Pin each layer with --study <layer>=<id>."
        )
    chosen: list[StudyBundleRef] = []
    for layer in sorted(set(pins) | set(latest)):
        candidates = discover_study_bundles(store, layer)
        if not candidates:
            raise CatalogError(
                f"study layer '{layer}' has no delivery under {Path(store) / STUDY_DIR / layer}. "
                f"Run `datarepo study` for it first."
            )
        pin = pins.get(layer)
        if pin is None:
            chosen.append(candidates[-1])
            continue
        matches = [c for c in candidates if c.bundle_id.startswith(pin)]
        if len(matches) != 1:
            known = ", ".join(c.bundle_id for c in candidates)
            raise CatalogError(
                f"study layer '{layer}': --study {pin} matches {len(matches)} of the deliveries on "
                f"disk ({known})"
            )
        chosen.append(matches[0])
    return chosen


def catalog_id(
    bundles: Sequence[BundleRef], study_bundles: Sequence[StudyBundleRef] = ()
) -> str:
    """Content hash of the bundles, the schema, the study layers and the builder.

    The same bundles built by the same code give the same id, so `build` can tell a rebuild from a
    no-op, and a release can record which catalog its citations were checked against.
    """
    digest = hashlib.sha256()
    digest.update(
        f"datarepo/{__version__}\ncatalog/{CATALOG_VERSION}\nschema/{SCHEMA_VERSION}\n".encode()
    )
    # A study layer's tables are part of what a catalog holds, so its version is part of the
    # catalog's identity. Without this, adding a column to `age_effect` would leave two
    # different catalogs sharing an id.
    for layer, version in sorted(STUDY_VERSIONS.items()):
        digest.update(f"study/{layer}/{version}\n".encode())
    for ref in sorted(bundles, key=lambda r: (r.dataset_id, r.bundle_id)):
        digest.update(f"{ref.dataset_id}\t{ref.bundle_id}\n".encode())
    # And so are its ROWS. A catalog built with a delivery of age effects and one built without it
    # answer 46 of aging's benchmark questions differently, so sharing an id would make the two
    # indistinguishable to anyone citing one of them.
    for ref in sorted(study_bundles, key=lambda r: (r.layer, r.bundle_id)):
        digest.update(f"study-bundle/{ref.layer}\t{ref.bundle_id}\n".encode())
    return digest.hexdigest()[:16]


@dataclass
class CatalogResult:
    """What a build did, in the terms an operator or a release checklist needs."""

    path: Path
    catalog_id: str
    datasets: list[str]
    bundles: list[BundleRef]
    study_bundles: list[StudyBundleRef] = field(default_factory=list)
    row_counts: dict[str, int] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)
    indexes: int = 0
    skipped: bool = False

    @property
    def failed_checks(self) -> list[dict[str, Any]]:
        return [c for c in self.checks if not c["ok"]]


def _select_from_parquet(ref: BundleRef, table: str, path: Path) -> str:
    """One bundle's contribution to a catalog table, with provenance columns prepended.

    `dataset_id` is dropped from the bundle's own columns and re-stated from the bundle manifest.
    They agree today; stating it once means they cannot disagree tomorrow, and it gives the tables
    that have no `dataset_id` of their own -- `proteins`, `definitions` -- the one thing a
    cross-dataset query needs from them.
    """
    has_dataset_id = "dataset_id" in TABLES[table].names
    body = "* EXCLUDE (dataset_id)" if has_dataset_id else "*"
    return (
        f"SELECT {_quote(ref.dataset_id)} AS dataset_id, {_quote(ref.bundle_id)} AS bundle_id, "
        f"{body} FROM read_parquet({_quote(path.as_posix())})"
    )


def _create_empty(con: Any, table: str) -> None:
    """Create a table the bundles do not fill, so every schema table exists to be queried.

    A bundle omits a table it has no rows for, which is right for a file that is the product. A
    catalog that did the same would make "no such table" and "no such rows" indistinguishable to a
    caller that cannot see which bundles went in.
    """
    import pyarrow as pa  # noqa: PLC0415

    schema = TABLES[table]
    if "dataset_id" in schema.names:
        schema = schema.remove(schema.get_field_index("dataset_id"))
    empty = pa.schema(
        [pa.field("dataset_id", pa.string()), pa.field("bundle_id", pa.string()), *schema]
    ).empty_table()
    con.register("_empty_table", empty)
    con.execute(f'CREATE TABLE "{table}" AS SELECT * FROM _empty_table')
    con.unregister("_empty_table")


def _study_schema(schema: Any) -> Any:
    """One study table's catalog schema: the layer's columns behind the two provenance ones."""
    import pyarrow as pa  # noqa: PLC0415

    return pa.schema(
        [
            pa.field("study_layer", pa.string()),
            pa.field("study_bundle_id", pa.string()),
            *schema,
        ]
    )


def _create_study_tables(
    con: Any, study_bundles: Sequence["StudyBundleRef"] = ()
) -> dict[str, int]:
    """Create every study layer's tables, filled from a delivery where there is one.

    A study layer ADDS tables keyed on core identifiers and never alters a core table (U5), so it is
    created separately and a catalog is complete without one.

    **A table with no delivery is created empty, and that has always been the point.** aging's
    benchmark distinguishes NO_TABLE from EMPTY_TABLE, and the 46 questions that need an age effect
    scored the first until 0.6.0 created these. An empty table with the right columns says "this
    repository can hold that, and holds none"; a missing table says nothing at all, and a caller
    cannot tell it from a repository that never modelled age. Study bundles are opt-in
    (`select_study_bundles`), so the empty case stays the default rather than the accident.

    Returns:
        `{table: row count}` for every study table, including the empty ones -- which is the
        difference that matters to a caller and so the difference `catalog_tables` records.
    """
    by_layer = {ref.layer: ref for ref in study_bundles}
    row_counts: dict[str, int] = {}
    taken = set(TABLES) | set(DERIVED_TABLES) | set(ACCEPTED_VIEWS) | set(GRAIN_VIEWS)
    for layer, tables in STUDY_TABLES.items():
        ref = by_layer.get(layer)
        for table, schema in tables.items():
            if table in taken:
                raise CatalogError(
                    f"study layer '{layer}' declares a table named '{table}', which the core "
                    f"catalog already uses. A study layer adds tables; it never shadows one."
                )
            taken.add(table)
            path = ref.table_path(table) if ref is not None else None
            if path is None:
                con.register("_empty_study", _study_schema(schema).empty_table())
                con.execute(f'CREATE TABLE "{table}" AS SELECT * FROM _empty_study')
                con.unregister("_empty_study")
                row_counts[table] = 0
                continue
            con.execute(
                f'CREATE TABLE "{table}" AS '
                f"SELECT {_quote(layer)} AS study_layer, "
                f"{_quote(ref.bundle_id)} AS study_bundle_id, * "
                f"FROM read_parquet({_quote(path.as_posix())})"
            )
            row_counts[table] = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
    return row_counts


def _load_tables(con: Any, bundles: Sequence[BundleRef]) -> dict[str, int]:
    """Materialise every schema table as the union of the bundles that hold it."""
    row_counts: dict[str, int] = {}
    for table in TABLES:
        parts = [
            _select_from_parquet(ref, table, path)
            for ref in bundles
            if (path := ref.table_path(table)) is not None
        ]
        if not parts:
            _create_empty(con, table)
            continue
        # BY NAME rather than positionally: the bundles all carry one schema version, and a union
        # that lined columns up by position would turn a violation of that into silent nonsense.
        union = "\nUNION ALL BY NAME\n".join(parts)
        con.execute(f'CREATE TABLE "{table}" AS\n{union}')
        row_counts[table] = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
    return row_counts


def _build_derived(con: Any) -> None:
    """The acceptance views and the cross-dataset tables.

    The views come first: everything below counts through them, so the catalog's headline numbers
    are the same numbers the bundle reconciled against the producer's `results.txt`. A catalog whose
    front page disagreed with the bundle it was built from would be worse than no front page.
    """
    from .sources.identifications import PRODUCER_THRESHOLD  # noqa: PLC0415

    for name, body in ACCEPTED_VIEWS.items():
        con.execute(f'CREATE VIEW "{name}" AS {body.format(t=PRODUCER_THRESHOLD)}')
    for name, body in GRAIN_VIEWS.items():
        con.execute(f'CREATE VIEW "{name}" AS {body}')

    con.execute(
        """
        CREATE TABLE dataset_overview AS
        SELECT
            d.dataset_id,
            d.bundle_id,
            d.title,
            d.organisms,
            d.acquisition,
            d.quant_method,
            d.labelling,
            d.enrichment,
            d.instrument_vendor,
            d.search_engine,
            d.search_engine_version,
            (SELECT count(*) FROM runs r WHERE r.dataset_id = d.dataset_id) AS n_runs,
            (SELECT count(*) FROM samples s WHERE s.dataset_id = d.dataset_id) AS n_samples,
            (SELECT count(*) FROM psms_1pct p WHERE p.dataset_id = d.dataset_id) AS n_psms_1pct,
            (SELECT count(*) FROM peptidoforms_1pct pf
              WHERE pf.dataset_id = d.dataset_id) AS n_peptidoforms_1pct,
            (SELECT count(*) FROM protein_groups_1pct pg
              WHERE pg.dataset_id = d.dataset_id) AS n_protein_groups_1pct,
            (SELECT count(*) FROM psms p WHERE p.dataset_id = d.dataset_id) AS n_psms_all,
            (SELECT count(*) FROM ptm_sites ps WHERE ps.dataset_id = d.dataset_id) AS n_ptm_sites,
            (SELECT count(*) FROM quant_values q
               JOIN assays a ON a.assay_id = q.assay_id
               JOIN runs r ON r.run_id = a.run_id
              WHERE r.dataset_id = d.dataset_id) AS n_quant_values,
            (SELECT count(*) FROM findings f
              WHERE f.dataset_id = d.dataset_id AND f.severity IN ('warning', 'error')) AS n_open_findings
        FROM datasets d
        """
    )

    con.execute(
        """
        CREATE TABLE protein_datasets AS
        WITH observed AS (
            SELECT DISTINCT dataset_id, protein_accession FROM proteins
        ),
        in_groups AS (
            SELECT dataset_id, unnest(protein_accessions) AS protein_accession, protein_group_id,
                   q_value
            FROM protein_groups_1pct
        ),
        in_peptides AS (
            SELECT dataset_id, unnest(protein_accessions) AS protein_accession, peptidoform_id
            FROM peptidoforms_1pct
        )
        SELECT
            o.dataset_id,
            o.protein_accession,
            count(DISTINCT g.protein_group_id) AS n_protein_groups,
            count(DISTINCT p.peptidoform_id)   AS n_peptidoforms,
            min(g.q_value)                     AS best_q_value
        FROM observed o
        LEFT JOIN in_groups g
               ON g.dataset_id = o.dataset_id AND g.protein_accession = o.protein_accession
        LEFT JOIN in_peptides p
               ON p.dataset_id = o.dataset_id AND p.protein_accession = o.protein_accession
        GROUP BY o.dataset_id, o.protein_accession
        """
    )

    # Attributes are recorded per dataset in `proteins`, so the global row has to pick. max() is an
    # arbitrary choice made deterministic; `protein_datasets` keeps the per-dataset truth.
    #
    # `n_datasets` counts where the accession appears in the search output at all -- decoys and
    # sub-threshold matches included, because `proteins` is the search's protein list, not its
    # answer. `n_datasets_1pct` counts where it has evidence that passed. An agent asking "which
    # datasets have this protein" almost always means the second one, so both are here with names
    # that say which is which.
    con.execute(
        """
        CREATE TABLE protein_index AS
        SELECT
            p.protein_accession,
            max(p.gene)                                AS gene,
            max(p.organism)                            AS organism,
            bool_or(coalesce(p.is_contaminant, false)) AS is_contaminant,
            count(DISTINCT p.dataset_id)               AS n_datasets,
            count(DISTINCT p.dataset_id) FILTER (
                WHERE d.n_protein_groups > 0 OR d.n_peptidoforms > 0)  AS n_datasets_1pct,
            list_sort(list(DISTINCT p.dataset_id))     AS dataset_ids,
            list_sort(list(DISTINCT p.dataset_id) FILTER (
                WHERE d.n_protein_groups > 0 OR d.n_peptidoforms > 0)) AS dataset_ids_1pct,
            min(d.best_q_value)                        AS best_q_value
        FROM proteins p
        LEFT JOIN protein_datasets d
               ON d.dataset_id = p.dataset_id AND d.protein_accession = p.protein_accession
        GROUP BY p.protein_accession
        """
    )

    # What the search actually PLACED, as against what it declared (aging 024 section 6).
    #
    # **Derived from the peptidoforms, not from `ptm_sites`, and the choice is the whole point.**
    # `ptm_sites` is per RESOLVED PROTEIN POSITION, so it drops every placement without one: the
    # 210 occupancy sites at pos0, the 264 with no determinate position, and -- before 0.8.0 -- the
    # 1,367 protein-N-terminal sites. A placed view built on it would have reported that N-terminal
    # acetylation was NEVER PLACED in any of the three datasets while 3,085 peptidoforms carried
    # it. That is S39 reproduced in a new table, which is the failure this view exists to prevent:
    # a view trusted about ABSENCE must draw from the table that loses nothing.
    #
    # **Grain: accession-or-mass, and it cannot name the chemistry.** A ProForma tag carries a
    # UNIMOD accession or a mass, never an `IdWithMotif`, so `_declared` and `_placed` are NOT
    # comparable row for row -- `_declared` names chemistries, this names accessions and masses.
    # For a J8-style mass-silent check that is the right grain anyway, because the question is
    # about masses. Do not resolve a position rule through an accession from here: one accession
    # spans entries with different rules (UNIMOD:34 covers Anywhere, N-terminal and C-terminal
    # across ~20 entries), which is how a probe on the accession reported 247 C-terminal
    # peptidoforms where the true number is 0.
    con.execute(
        r"""
        CREATE TABLE search_modifications_placed AS
        SELECT
            dataset_id,
            bundle_id,
            tag,
            CASE WHEN tag LIKE 'UNIMOD:%' THEN tag END                        AS modification,
            CASE WHEN regexp_matches(tag, '^[+-][0-9]')
                 THEN try_cast(tag AS DOUBLE) END                             AS mass_shift,
            CASE WHEN tag LIKE 'Info:%' THEN substr(tag, 6) END               AS unresolved_name,
            count(*)                                                          AS n_placements,
            count(DISTINCT peptidoform_id)                                    AS n_peptidoforms
        FROM (
            SELECT dataset_id, bundle_id, peptidoform_id,
                   unnest(regexp_extract_all(peptidoform, '\[([^\]]*)\]', 1)) AS tag
            FROM peptidoforms_1pct
        )
        GROUP BY dataset_id, bundle_id, tag
        """
    )

    con.execute(
        """
        CREATE TABLE peptide_index AS
        SELECT
            base_sequence,
            count(DISTINCT dataset_id)           AS n_datasets,
            list_sort(list(DISTINCT dataset_id)) AS dataset_ids,
            count(*)                             AS n_peptidoforms,
            min(best_q_value)                    AS best_q_value
        FROM peptidoforms_1pct
        GROUP BY base_sequence
        """
    )


def _column_type(con: Any, table: str, column: str) -> str | None:
    rows = con.execute(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = ? AND column_name = ?",
        [table, column],
    ).fetchall()
    return rows[0][0] if rows else None


def _build_indexes(con: Any) -> int:
    """ART indexes on the point-lookup columns, skipping what a DuckDB index cannot hold."""
    built = 0
    for table, column in INDEX_COLUMNS:
        kind = _column_type(con, table, column)
        if kind is None or kind.endswith("[]") or kind.startswith("STRUCT"):
            continue
        con.execute(f'CREATE INDEX "ix_{table}_{column}" ON "{table}" ("{column}")')
        built += 1
    return built


def _count(con: Any, sql: str, params: Sequence[Any] = ()) -> tuple[int, Any]:
    row = con.execute(sql, list(params)).fetchone()
    return (int(row[0]), row[1] if len(row) > 1 else None)


def _check_row_counts(con: Any, bundles: Sequence[BundleRef]) -> list[dict[str, Any]]:
    """Every table must hold exactly the rows its bundle manifest says it wrote.

    This is the catalog's version of the ingester's reconciliation, and it catches the thing a
    content hash cannot: a bundle whose Parquet was truncated or edited after `bundle.json` was
    written.
    """
    checks: list[dict[str, Any]] = []
    for ref in bundles:
        for table, expected in sorted(ref.row_counts.items()):
            if table not in TABLES:
                checks.append({
                    "name": f"{ref.dataset_id}/{table}",
                    "kind": "row_count",
                    "ok": False,
                    "observed": None,
                    "expected": expected,
                    "detail": f"bundle {ref.bundle_id} claims a table no schema {SCHEMA_VERSION} knows",
                })
                continue
            observed, _ = _count(
                con,
                f'SELECT count(*), NULL FROM "{table}" WHERE bundle_id = ?',
                [ref.bundle_id],
            )
            checks.append({
                "name": f"{ref.dataset_id}/{table}",
                "kind": "row_count",
                "ok": observed == expected,
                "observed": observed,
                "expected": expected,
                "detail": f"bundle {ref.bundle_id}",
            })
    return checks


def _check_integrity(con: Any) -> list[dict[str, Any]]:
    """The bundle's referential rules, re-run across the union.

    Driven by the same `REFERENCES` / `IDENTIFIERS` / `FEATURE_TABLES` constants the ingester uses,
    so there is one list of what points at what. Every join is *within* a dataset: identifiers are
    namespaced per dataset by the ingester, and a bundle's rows may only resolve against their own.
    """
    checks: list[dict[str, Any]] = []

    for table, column in IDENTIFIERS:
        duplicates, example = _count(
            con,
            f'SELECT count(*), min(k) FROM (SELECT "{column}" AS k FROM "{table}" '
            f'WHERE "{column}" IS NOT NULL GROUP BY dataset_id, "{column}" HAVING count(*) > 1)',
        )
        checks.append({
            "name": f"{table}.{column}",
            "kind": "unique",
            "ok": duplicates == 0,
            "observed": duplicates,
            "expected": 0,
            "detail": None if duplicates == 0 else f"e.g. {example}",
        })

    for table, column, target, target_column in REFERENCES:
        name = column[:-2] if column.endswith("[]") else column
        source = (
            f'SELECT DISTINCT dataset_id, unnest("{name}") AS val FROM "{table}"'
            if column.endswith("[]")
            else f'SELECT DISTINCT dataset_id, "{name}" AS val FROM "{table}" WHERE "{name}" IS NOT NULL'
        )
        dangling, example = _count(
            con,
            f"SELECT count(*), min(val) FROM ({source}) s WHERE val IS NOT NULL AND NOT EXISTS ("
            f'SELECT 1 FROM "{target}" t WHERE t.dataset_id = s.dataset_id '
            f'AND t."{target_column}" = s.val)',
        )
        checks.append({
            "name": f"{table}.{column} -> {target}.{target_column}",
            "kind": "reference",
            "ok": dangling == 0,
            "observed": dangling,
            "expected": 0,
            "detail": None if dangling == 0 else f"e.g. {example}",
        })

    types = [r[0] for r in con.execute(
        "SELECT DISTINCT feature_type FROM quant_values WHERE feature_type IS NOT NULL"
    ).fetchall()]
    for feature_type in sorted(types):
        target = FEATURE_TABLES.get(feature_type)
        if target is None:
            checks.append({
                "name": f"quant_values.feature_type '{feature_type}'",
                "kind": "reference",
                "ok": False,
                "observed": None,
                "expected": 0,
                "detail": "names no table",
            })
            continue
        dangling, example = _count(
            con,
            "SELECT count(*), min(feature_id) FROM (SELECT DISTINCT dataset_id, feature_id "
            "FROM quant_values WHERE feature_type = ?) s WHERE NOT EXISTS ("
            f'SELECT 1 FROM "{target[0]}" t WHERE t.dataset_id = s.dataset_id '
            f'AND t."{target[1]}" = s.feature_id)',
            [feature_type],
        )
        checks.append({
            "name": f"quant_values.feature_id ({feature_type}) -> {target[0]}.{target[1]}",
            "kind": "reference",
            "ok": dangling == 0,
            "observed": dangling,
            "expected": 0,
            "detail": None if dangling == 0 else f"e.g. {example}",
        })
    return checks


def _check_study(con: Any, study_bundles: Sequence["StudyBundleRef"]) -> list[dict[str, Any]]:
    """A loaded study layer's own rules: its keys are unique and its joins into the core resolve.

    Only runs for layers a delivery was loaded for. An empty study table has nothing to check and
    the checks would pass vacuously, which would put a reassuring line in `catalog_checks` about
    something nobody delivered.

    The reference checks are NOT scoped by `dataset_id` the way the core's are. A study layer's
    rows are not namespaced per dataset by us -- the producer chose their identifiers -- and
    `age_effect_meta` is pooled across datasets by construction, so a per-dataset join would be
    wrong for the table the layer exists to produce.

    `build` refuses on a failure rather than dropping the rows. An age effect naming a dataset this
    catalog does not hold is not a row to quietly skip: section D's question would come back with a
    smaller answer than the delivery supports, and nothing in the catalog would say so.
    """
    checks: list[dict[str, Any]] = []
    for ref in sorted(study_bundles, key=lambda r: r.layer):
        layer = ref.layer
        for table, key in sorted(STUDY_COMPOSITE_IDENTIFIERS.get(layer, {}).items()):
            if table not in STUDY_TABLES[layer]:
                continue
            columns = ", ".join(f'"{c}"' for c in key)
            not_null = " AND ".join(f'"{c}" IS NOT NULL' for c in key)
            duplicates, example = _count(
                con,
                f"SELECT count(*), min(k) FROM (SELECT {columns}, min("
                f'CAST("{key[0]}" AS VARCHAR)) AS k FROM "{table}" WHERE {not_null} '
                f"GROUP BY {columns} HAVING count(*) > 1)",
            )
            checks.append({
                "name": f"{layer}.{table} ({', '.join(key)})",
                "kind": "study-unique",
                "ok": duplicates == 0,
                "observed": duplicates,
                "expected": 0,
                "detail": None if duplicates == 0 else f"e.g. {example}",
            })

        for table, column, target, target_column in STUDY_REFERENCES.get(layer, ()):
            if table not in STUDY_TABLES[layer]:
                continue
            dangling, example = _count(
                con,
                f'SELECT count(*), min(val) FROM (SELECT DISTINCT "{column}" AS val '
                f'FROM "{table}" WHERE "{column}" IS NOT NULL) s WHERE NOT EXISTS ('
                f'SELECT 1 FROM "{target}" t WHERE t."{target_column}" = s.val)',
            )
            checks.append({
                "name": f"{layer}.{table}.{column} -> {target}.{target_column}",
                "kind": "study-reference",
                "ok": dangling == 0,
                "observed": dangling,
                "expected": 0,
                "detail": None if dangling == 0 else f"e.g. {example}",
            })
    return checks


def _write_catalog_tables(
    con: Any,
    bundles: Sequence[BundleRef],
    row_counts: dict[str, int],
    checks: Sequence[dict[str, Any]],
    *,
    cid: str,
    instance: str | None,
    notes: dict[str, Any] | None,
    study_bundles: Sequence["StudyBundleRef"] = (),
    study_counts: dict[str, int] | None = None,
) -> None:
    """The catalog's account of itself: what went in, what came out, and what was checked."""
    con.execute(
        """
        CREATE TABLE catalog_meta (
            catalog_id VARCHAR, catalog_version VARCHAR, schema_version VARCHAR,
            qpx_version VARCHAR, builder VARCHAR, builder_version VARCHAR,
            built_utc VARCHAR, instance VARCHAR, n_datasets BIGINT, notes JSON
        )
        """
    )
    con.execute(
        "INSERT INTO catalog_meta VALUES (?, ?, ?, ?, 'datarepo', ?, ?, ?, ?, ?)",
        [
            cid,
            CATALOG_VERSION,
            SCHEMA_VERSION,
            QPX_VERSION,
            __version__,
            # A string, like the bundle's `written_utc`: reading a TIMESTAMPTZ back out of DuckDB
            # needs pytz, and a catalog should not carry a dependency for a field nobody sorts on.
            dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            instance,
            len(bundles),
            json.dumps(notes or {}),
        ],
    )

    con.execute(
        """
        CREATE TABLE catalog_bundles (
            dataset_id VARCHAR, bundle_id VARCHAR, path VARCHAR, written_utc VARCHAR,
            schema_version VARCHAR, ingester_version VARCHAR, reconciliation_ok BOOLEAN,
            reconciliation_failed VARCHAR[]
        )
        """
    )
    for ref in bundles:
        failed = [
            str(c.get("name"))
            for c in (ref.manifest.get("reconciliation") or [])
            if not c.get("ok")
        ]
        con.execute(
            "INSERT INTO catalog_bundles VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ref.dataset_id,
                ref.bundle_id,
                ref.path.as_posix(),
                ref.written_utc,
                ref.schema_version,
                str((ref.manifest.get("ingester") or {}).get("version", "?")),
                not failed,
                failed,
            ],
        )

    # A separate table from `catalog_bundles`, because the two are separate objects: a search
    # bundle is one dataset's evidence, a study bundle is one layer's model results over however
    # many datasets. Squeezing a delivery into a `dataset_id` column would have meant inventing a
    # dataset for `age_effect_meta`, which is pooled across them by construction.
    con.execute(
        """
        CREATE TABLE catalog_study_bundles (
            layer VARCHAR, bundle_id VARCHAR, layer_version VARCHAR, path VARCHAR,
            written_utc VARCHAR, schema_version VARCHAR, instance VARCHAR, delivery VARCHAR
        )
        """
    )
    for ref in study_bundles:
        con.execute(
            "INSERT INTO catalog_study_bundles VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ref.layer,
                ref.bundle_id,
                ref.layer_version,
                ref.path.as_posix(),
                ref.written_utc,
                ref.schema_version,
                ref.manifest.get("instance"),
                ref.manifest.get("delivery"),
            ],
        )

    con.execute(
        "CREATE TABLE catalog_tables (table_name VARCHAR, rows BIGINT, kind VARCHAR)"
    )
    for name in TABLES:
        con.execute(
            "INSERT INTO catalog_tables VALUES (?, ?, 'bundle')", [name, row_counts.get(name, 0)]
        )
    for name in (*DERIVED_TABLES, *ACCEPTED_VIEWS, *GRAIN_VIEWS):
        rows = con.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
        kind = "view" if name in ACCEPTED_VIEWS or name in GRAIN_VIEWS else "derived"
        con.execute("INSERT INTO catalog_tables VALUES (?, ?, ?)", [name, rows, kind])
    study_counts = study_counts or {}
    for layer, tables in STUDY_TABLES.items():
        for name in tables:
            con.execute(
                "INSERT INTO catalog_tables VALUES (?, ?, ?)",
                [name, study_counts.get(name, 0), f"study:{layer}"],
            )

    con.execute(
        "CREATE TABLE catalog_checks (name VARCHAR, kind VARCHAR, ok BOOLEAN, "
        "observed BIGINT, expected BIGINT, detail VARCHAR)"
    )
    for check in checks:
        con.execute(
            "INSERT INTO catalog_checks VALUES (?, ?, ?, ?, ?, ?)",
            [
                check["name"],
                check["kind"],
                check["ok"],
                check["observed"],
                check["expected"],
                check["detail"],
            ],
        )


def read_catalog_id(path: Path) -> str | None:
    """The id of an existing catalog, or None if there is no readable one at `path`."""
    if not Path(path).is_file():
        return None
    try:
        import duckdb  # noqa: PLC0415

        with duckdb.connect(str(path), read_only=True) as con:
            row = con.execute("SELECT catalog_id FROM catalog_meta").fetchone()
        return None if row is None else str(row[0])
    except Exception:  # noqa: BLE001 - an unreadable or foreign file is simply not our catalog
        return None


def build_catalog(
    bundles: Sequence[BundleRef],
    out: Path,
    *,
    overwrite: bool = False,
    instance: str | None = None,
    notes: dict[str, Any] | None = None,
    study_bundles: Sequence[StudyBundleRef] = (),
) -> CatalogResult:
    """Load bundles into one DuckDB catalog at `out`.

    Args:
        bundles: exactly one bundle per dataset, as `select_bundles` returns.
        out: the catalog file to write. It is replaced atomically: the build happens in a temporary
            file beside it, so a failed build leaves the previous catalog serving.
        overwrite: rebuild even when a catalog with this id is already there.
        instance: the producing instance's name, recorded in `catalog_meta`.
        notes: anything else worth recording, e.g. the release this catalog was built for.
        study_bundles: at most one delivery per study layer, as `select_study_bundles` returns.
            Empty is the normal case and leaves the study tables empty, which is an answer rather
            than an omission.

    Returns:
        A `CatalogResult`. `skipped` is True when the catalog was already current.

    Raises:
        CatalogError: no bundles, two bundles for one dataset, a bundle written against a different
            schema version, or checks that fail. Nothing is moved into place in those cases.
    """
    try:
        import duckdb  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - a packaging failure, not a data one
        raise CatalogError(
            "duckdb is not installed. `pip install datarepo` pulls it in; in a checkout, "
            "`pip install -e .`."
        ) from exc

    bundles = list(bundles)
    if not bundles:
        raise CatalogError("no bundles to build a catalog from")

    seen: dict[str, BundleRef] = {}
    for ref in bundles:
        if ref.dataset_id in seen:
            raise CatalogError(
                f"{ref.dataset_id} appears twice ({seen[ref.dataset_id].bundle_id} and "
                f"{ref.bundle_id}). A catalog holds one bundle per dataset."
            )
        seen[ref.dataset_id] = ref
        if ref.schema_version != SCHEMA_VERSION:
            raise CatalogError(
                f"{ref.dataset_id} bundle {ref.bundle_id} was written against schema "
                f"{ref.schema_version}, and this build writes schema {SCHEMA_VERSION}. Re-ingest "
                f"it, or build with the ingester that wrote it."
            )

    study_bundles = list(study_bundles)
    seen_layers: dict[str, StudyBundleRef] = {}
    for ref in study_bundles:
        if ref.layer not in STUDY_TABLES:
            raise CatalogError(
                f"study bundle {ref.bundle_id} delivers layer '{ref.layer}', which this build does "
                f"not carry. Layers available: {', '.join(sorted(STUDY_TABLES)) or '(none)'}."
            )
        if ref.layer in seen_layers:
            raise CatalogError(
                f"study layer '{ref.layer}' appears twice ({seen_layers[ref.layer].bundle_id} and "
                f"{ref.bundle_id}). A catalog holds one delivery per layer."
            )
        seen_layers[ref.layer] = ref
        if ref.layer_version != STUDY_VERSIONS[ref.layer]:
            raise CatalogError(
                f"study bundle {ref.bundle_id} was written against {ref.layer} "
                f"{ref.layer_version}, and this build carries {STUDY_VERSIONS[ref.layer]}. A "
                f"column added between the two would land silently null, so re-run "
                f"`datarepo study`, or build with the version that wrote it."
            )

    out = Path(out)
    cid = catalog_id(bundles, study_bundles)
    if not overwrite and read_catalog_id(out) == cid:
        return CatalogResult(
            path=out,
            catalog_id=cid,
            datasets=sorted(seen),
            bundles=bundles,
            study_bundles=study_bundles,
            skipped=True,
        )

    out.parent.mkdir(parents=True, exist_ok=True)
    staging = out.with_name(f".{out.name}.{cid}.building")
    staging.unlink(missing_ok=True)

    try:
        with duckdb.connect(str(staging)) as con:
            row_counts = _load_tables(con, bundles)
            _build_derived(con)
            study_counts = _create_study_tables(con, study_bundles)
            checks = (
                _check_row_counts(con, bundles)
                + _check_integrity(con)
                + _check_study(con, study_bundles)
            )
            failed = [c for c in checks if not c["ok"]]
            if failed:
                detail = "\n  - ".join(
                    f"{c['name']}: {c['observed']} vs {c['expected']}"
                    + (f" ({c['detail']})" if c["detail"] else "")
                    for c in failed
                )
                raise CatalogError(
                    "the bundles do not hold together as one catalog, so nothing was written:\n"
                    f"  - {detail}"
                )
            indexes = _build_indexes(con)
            _write_catalog_tables(
                con,
                bundles,
                row_counts,
                checks,
                cid=cid,
                instance=instance,
                notes=notes,
                study_bundles=study_bundles,
                study_counts=study_counts,
            )
    except BaseException:
        staging.unlink(missing_ok=True)
        raise

    out.unlink(missing_ok=True)
    staging.replace(out)
    return CatalogResult(
        path=out,
        catalog_id=cid,
        datasets=sorted(seen),
        bundles=bundles,
        study_bundles=study_bundles,
        row_counts={**row_counts, **{k: v for k, v in study_counts.items() if v}},
        checks=checks,
        indexes=indexes,
    )


def _rows_if_present(con: Any, rows: Any, table: str, order: str) -> list[dict[str, Any]]:
    """A catalog table's rows, or none when an older catalog does not have that table."""
    import duckdb  # noqa: PLC0415

    try:
        return rows(f'SELECT * FROM "{table}" ORDER BY "{order}"')
    except duckdb.Error:
        return []


def describe_catalog(path: Path) -> dict[str, Any]:
    """Read a built catalog's own account of itself, without loading any science.

    Raises:
        CatalogError: there is no catalog at `path`.
    """
    import duckdb  # noqa: PLC0415

    path = Path(path)
    if not path.is_file():
        raise CatalogError(f"no catalog at {path}")
    def rows(sql: str) -> list[dict[str, Any]]:
        result = con.execute(sql)
        names = [d[0] for d in result.description]
        return [dict(zip(names, row)) for row in result.fetchall()]

    with duckdb.connect(str(path), read_only=True) as con:
        try:
            meta = rows("SELECT * FROM catalog_meta")
        except duckdb.Error as exc:
            raise CatalogError(f"{path} is not a datarepo catalog: {exc}") from exc
        return {
            "path": str(path),
            "meta": meta[0] if meta else {},
            "bundles": rows("SELECT * FROM catalog_bundles ORDER BY dataset_id"),
            # A catalog from before 0.7.0 has no study bundles table and is still a catalog, so an
            # absent one reads as "no delivery" rather than as a broken file.
            "study_bundles": _rows_if_present(con, rows, "catalog_study_bundles", "layer"),
            "tables": rows("SELECT * FROM catalog_tables ORDER BY kind, table_name"),
            "checks": rows("SELECT * FROM catalog_checks ORDER BY ok, kind, name"),
        }


def run_query(path: Path, sql: str, *, limit: int | None = None) -> tuple[list[str], list[tuple]]:
    """Run one read-only query against a catalog.

    The connection is opened read-only, so a query that tries to write is refused by DuckDB rather
    than by a rule of ours. This is the smallest thing that makes the catalog usable and provable
    from the command line; the Python client and the MCP tools (roadmap step 3) come later and call
    the same catalog.

    Args:
        path: the catalog file.
        sql: one SQL statement.
        limit: wrap the statement in a `LIMIT` so an exploratory query cannot print a million rows.

    Returns:
        `(column names, rows)`.

    Raises:
        CatalogError: there is no catalog at `path`, or the query is not valid against it.
    """
    import duckdb  # noqa: PLC0415

    path = Path(path)
    if not path.is_file():
        raise CatalogError(f"no catalog at {path}")
    statement = sql.strip().rstrip(";")
    if limit is not None:
        statement = f"SELECT * FROM ({statement}) LIMIT {int(limit)}"
    try:
        with duckdb.connect(str(path), read_only=True) as con:
            result = con.execute(statement)
            return [d[0] for d in result.description], result.fetchall()
    except duckdb.Error as exc:
        raise CatalogError(f"{exc}") from exc


def format_rows(columns: Sequence[str], rows: Iterable[Sequence[Any]], fmt: str = "table") -> str:
    """Render query results as an aligned table, TSV, or JSON lines."""
    rows = [list(r) for r in rows]
    if fmt == "json":
        return "\n".join(json.dumps(dict(zip(columns, r)), default=str) for r in rows)
    cells = [[("" if v is None else str(v)) for v in r] for r in rows]
    if fmt == "tsv":
        return "\n".join(["\t".join(columns), *("\t".join(c) for c in cells)])
    widths = [len(c) for c in columns]
    for row in cells:
        for i, value in enumerate(row):
            widths[i] = max(widths[i], len(value))
    lines = ["  ".join(c.ljust(widths[i]) for i, c in enumerate(columns))]
    lines.append("  ".join("-" * w for w in widths))
    lines.extend("  ".join(c.ljust(widths[i]) for i, c in enumerate(row)) for row in cells)
    return "\n".join(lines)
