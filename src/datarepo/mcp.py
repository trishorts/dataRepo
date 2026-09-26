"""The local MCP server: three tools over one catalog (FRAMEWORK step 3, D12-D15).

Run as `datarepo mcp --catalog <path>`, over stdio, against **one** catalog named by explicit path.
Three tools ship, and a fourth is added only where aging's benchmark shows a specific wrong answer
(D12):

* `datarepo_describe` -- what this catalog is, what tables it has, what a column means.
* `datarepo_search` -- what do you have on LMNA / mitochondria / PXD036557 / "skeletal muscle"?
* `datarepo_sql` -- read-only SQL for everything else, bounded by `sandbox.Sandbox` (D14).

**Every result carries its provenance** (D13): the `catalog_id`, the catalog's versions, and every
bundle this catalog holds. The failure this forecloses is the one this repository keeps writing
threads about -- the same question answered twice, differently, with nothing in either result
saying which data it saw.

**Provenance is a fact about the server and is inferred from nothing.** It does not narrow to what
an answer touched, and that is deliberate. It used to, by reading the result's own `bundle_id` and
`dataset_id` columns -- and a query can put anything in a column with those names, so
`SELECT max(dataset_id) AS dataset_id, count(*) FROM ptm_sites` returned a catalog-wide count
stamped with one dataset's bundle, in the same words a correct narrowing uses. The narrowing was
never needed: `catalog_id` is a hash of the exact (dataset, bundle) set, so naming it already states
precisely which frozen copy of every dataset was available. That is the whole citation. A slice of
it is a convenience, it cannot be computed honestly from a result, and so it is not computed.

**The bar is zero silently-wrong answers, not a percentage** (D15). `SCHEMA_COVERAGE.md` says 94 of
aging's 168 questions wait on a producer, so on this data most honest answers are "no data yet".
Three things in here exist only to make that answer available instead of an invention:

1. `search` reports **what it searched**, with each source's row count. `protein_localizations` is
   present and holds 0 rows in every catalog built so far -- the organelle map belongs to `go`
   (D1) and has not been delivered -- so a search for "mitochondria" that said only "no hits" would
   let an agent conclude no protein is mitochondrial. It says instead that the table which would
   answer this is empty.
2. `describe` reads its column meanings from `_schema_docs.py`, generated from the LinkML schema by
   the same tool that generates the Arrow schemas, so a description cannot drift from the column it
   describes **within one version**. Across versions it can: the prose is generated from the schema
   THIS CODE was built against, and a catalog built by an older `datarepo` may not match it. Every
   result carrying a description says so through `schema_drift` when the two differ.
3. Nothing here summarises or interprets. A tool returns rows and the names of the things it looked
   in; the model reading them does the reasoning, and can be wrong in the open.

The module is named `mcp` after the protocol, and `import mcp` inside it resolves to the SDK, not
to itself -- Python 3 imports are absolute. The SDK is an optional `[mcp]` extra and is imported
only inside `serve()`, so every tool here is callable, and tested, without it.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence, get_args

from . import __version__
from ._schema_docs import ENUMS, SCHEMA_DESCRIPTION, STUDY_ENUMS, STUDY_TABLE_DOCS, TABLE_DOCS
from ._tables import SCHEMA_VERSION
from .catalog import DERIVED_DOCS
from .errors import CatalogError, DataRepoError, QueryRefused, QueryTimeout
from .sandbox import CHAR_CAP, ROW_CAP, TIMEOUT_SECONDS, Sandbox

#: Tools are named with this prefix because an agent sees them alongside every other server's.
TOOL_PREFIX = "datarepo_"

#: The argument vocabularies, as `Literal`s so the SDK renders them as enums in the tool schema an
#: agent reads. An agent that can see `kind` is one of eight words does not guess a ninth.
DetailLevel = Literal["concise", "detailed"]
SearchKind = Literal[
    "dataset", "protein", "peptide", "modification", "sample", "run", "definition", "localization"
]

#: How many hits one `search` kind returns before it says there are more.
SEARCH_LIMIT = 25
SEARCH_LIMIT_MAX = 200

#: A query that looks like this is also tried as a peptide sequence. Deliberately strict: three
#: letters would make "SAD" a peptide and every free-text search a peptide search.
#:
#: There is no accession or gene regex here on purpose. Every kind is searched unless the caller
#: names one, so a query does not have to be *classified* before it is answered -- and a classifier
#: that decided "ELAVL1 is a gene, not a peptide" would be the first place a wrong answer could
#: enter, in a tool whose whole job is to keep them out.
PEPTIDE_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWY]{6,}$")

#: What the no-target `describe()` says before anything else.
READ_FIRST = [
    "`target_decoy` has THREE values: target, decoy and contaminant. Count targets explicitly; "
    "decoys are FDR machinery and contaminants are reagents.",
    "The contaminant label is per dataset: human albumin is a target in a human search and a "
    "contaminant in a rodent one. Never use one corpus-wide flag.",
    "`datasets.organisms` is the organism of the searched protein database, not a statement "
    "about the samples.",
    "A protein group's accessions are sorted alphabetically, in `protein_accessions` and in "
    "`protein_group_id`: the first is not a leading or razor protein.",
    "`pep` is run-relative: never compare its values across datasets.",
    "An empty table means nothing was delivered, not that the answer is none.",
]

#: Columns whose VALUE means something only inside the search that wrote it (pep 002, G70).
#: MetaMorpheus retrains its PEP model from scratch on every search, on that search's own targets
#: and decoys, so two datasets' `pep` come from two different models even on one release. Stored
#: faithfully, and useful -- within one dataset the ranking is sound, and a count at a threshold
#: compares -- but `median(pep) GROUP BY dataset_id` reads as a comparison and is not one. Put in
#: the `sql` envelope, not only in the column descriptions, for D19's reason: `describe` can be
#: skipped and an envelope field cannot.
RUN_RELATIVE_COLUMNS: dict[str, str] = {
    "pep": "run-relative: a per-search model's score, not comparable across datasets or releases",
    "best_pep": "run-relative: the lowest `pep` of the dataset's PSMs, so it inherits `pep`'s scale",
    "pep_q_value": (
        "ordered by `pep`, so it moves whenever `pep` does; a count at a threshold compares within "
        "one MetaMorpheus release. Across releases use `q_value`, which does not depend on PEP"
    ),
}


class ToolError(DataRepoError):
    """The tool was called with something it cannot act on. The message says what to send instead."""


# ---------------------------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------------------------


@dataclass
class CatalogIdentity:
    """What a catalog says about itself. Read once, when the server opens it."""

    catalog_id: str | None
    catalog_version: str | None
    schema_version: str | None
    builder: str | None
    builder_version: str | None
    built_utc: str | None
    instance: str | None
    qpx_version: str | None
    release: str | None
    bundles: list[dict[str, Any]]
    study_bundles: list[dict[str, Any]]

    def base(self) -> dict[str, Any]:
        return {
            "catalog_id": self.catalog_id,
            "catalog_version": self.catalog_version,
            "schema_version": self.schema_version,
            "built_by": f"{self.builder} {self.builder_version}" if self.builder else None,
            "built_utc": self.built_utc,
            "instance": self.instance,
            "release": self.release,
            "served_by": f"datarepo {__version__}",
        }


def _read_identity(box: Sandbox) -> CatalogIdentity:
    meta_rows = box.dicts("SELECT * FROM catalog_meta")
    if not meta_rows:
        raise CatalogError(f"{box.path} has no catalog_meta; it is not a datarepo catalog")
    meta = meta_rows[0]
    release = None
    try:
        release = (json.loads(meta.get("notes") or "{}") or {}).get("release")
    except (TypeError, ValueError):
        release = None
    bundles = box.dicts(
        "SELECT dataset_id, bundle_id, ingester_version, written_utc, reconciliation_ok "
        "FROM catalog_bundles ORDER BY dataset_id"
    )
    study = (
        box.dicts("SELECT * FROM catalog_study_bundles ORDER BY layer")
        if box.has_table("catalog_study_bundles")
        else []
    )
    return CatalogIdentity(
        catalog_id=meta.get("catalog_id"),
        catalog_version=meta.get("catalog_version"),
        schema_version=meta.get("schema_version"),
        builder=meta.get("builder"),
        builder_version=meta.get("builder_version"),
        built_utc=meta.get("built_utc"),
        instance=meta.get("instance"),
        qpx_version=meta.get("qpx_version"),
        release=release,
        bundles=bundles,
        study_bundles=study,
    )


# ---------------------------------------------------------------------------------------------
# the server
# ---------------------------------------------------------------------------------------------


class CatalogServer:
    """The three tools, over one open catalog. No SDK involved -- `serve()` wires this to one.

    One catalog, named by explicit path, never auto-discovered (D13). A server that searched for a
    catalog could answer today from a working build and tomorrow from a release, with nothing in
    either answer saying which.
    """

    def __init__(self, catalog: Path | str, **sandbox_kwargs: Any) -> None:
        self.box = Sandbox(catalog, **sandbox_kwargs)
        self.identity = _read_identity(self.box)
        self._tables: dict[str, dict[str, Any]] | None = None
        self._opened_stat = self._file_stat()

    def _file_stat(self) -> tuple[int, int] | None:
        try:
            stat = os.stat(self.box.path)
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    @property
    def catalog_file_changed(self) -> str | None:
        """Set when the file at the catalog's path is no longer the one this server opened.

        aging's server answered from `62d419643e71320c` for hours after they published
        `1e2f13be6f121fd7` over the same path (070, 57k). The server keeps what it opened, on
        purpose: an answer must not change catalogs halfway through a conversation, and a reload
        would do exactly that. What it must not do is keep quiet about it.
        """
        if self._file_stat() == self._opened_stat:
            return None
        return (
            f"The file at {self.box.path} has changed since this server opened it. Every answer "
            f"still comes from the catalog it opened ({self.identity.catalog_id}), which may no "
            f"longer be the one published there. Restart the MCP server to serve the current file."
        )

    @property
    def schema_drift(self) -> str | None:
        """Set when the prose this server carries describes a NEWER schema than the catalog holds.

        Column descriptions come from `_schema_docs.py`, generated from the schema **this code**
        was built against. A catalog built by an older `datarepo` is two things at once: real data,
        and data whose columns may not match the sentences describing them.

        Not hypothetical, and the worst finding of the 0.11.0 review. Serving a 0.0.5 catalog from
        0.0.7 code, `describe('proteins')` narrated the contaminant-organism fix in the past tense
        and directed the reader to `organism_name`, a column that catalog does not have, while
        `describe('protein_index')` stated flatly that `organism` is "NULL for contaminant and
        decoy entries" and printed "[38,002 non-null]" on the same line. **An agent that did the
        diligent thing and called `describe` first came away more confident and more wrong.**

        The fix is not to suppress the prose -- it is correct about the schema it names -- but to
        say, in every result carrying a description, which schema the description is of.
        """
        served = self.identity.schema_version
        if not served or served == SCHEMA_VERSION:
            return None
        return (
            f"This catalog was built against schema {served}; the descriptions here are generated "
            f"from schema {SCHEMA_VERSION}, which this server was built against. Where they "
            f"disagree THE CATALOG IS RIGHT and the description is of a later version: a column "
            f"the prose mentions may not exist here, and a rule it states may not yet hold. Trust "
            f"the `type`, the `populated` count and the rows over the prose. Rebuilding the "
            f"catalog with this version of datarepo makes them agree."
        )

    def close(self) -> None:
        self.box.close()

    def __enter__(self) -> "CatalogServer":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- shared -----------------------------------------------------------------------------

    def tables(self) -> dict[str, dict[str, Any]]:
        """Every table and view actually in this catalog, with row count and kind.

        Read from `catalog_tables` where it exists and from `information_schema` where it does not,
        so a catalog built by an older `datarepo` still describes itself.
        """
        if self._tables is None:
            rows = (
                self.box.dicts("SELECT table_name, rows, kind FROM catalog_tables")
                if self.box.has_table("catalog_tables")
                else []
            )
            found = {r["table_name"]: dict(r) for r in rows}
            for row in self.box.dicts(
                "SELECT table_name, table_type FROM information_schema.tables"
            ):
                name = row["table_name"]
                if name not in found:
                    # `catalog_tables` does not count the catalog's own bookkeeping tables, and a
                    # catalog built before it existed counts nothing. Count them here rather than
                    # leave the row count None: an unknown count renders the same as zero
                    # everywhere it is read, and "empty" is the one word this server must not
                    # say when it does not know.
                    found[name] = {
                        "table_name": name,
                        "rows": self.box.one_value(f'SELECT count(*) FROM "{name}"'),
                        "kind": "view" if row["table_type"] == "VIEW" else "table",
                    }
            self._tables = dict(sorted(found.items()))
        return self._tables

    def _provenance(self, full: bool = False) -> dict[str, Any]:
        """What frozen data this server holds. **Identical on every answer, and inferred from
        nothing.**

        **Compact by default; the bundle list is in `describe()` only** (aging 070, DATAREPO-58).
        All four of aging's agents said the 2-3 KB list on every answer buried the answer. Nothing
        is lost by carrying it once: `catalog_id` is the hash of exactly that list, so it names the
        same set, and it cannot drift from it within one server.

        It used to narrow per answer -- 'the bundles named in the rows returned' -- and that was a
        mistake of kind, not of implementation. Two different questions were being answered as one:

        * **Which frozen data does this server hold?** A fact about the server, fixed when it opened
          the file. No question can change it.
        * **Which slice of it did this answer touch?** A guess, made by reading the query's own
          output.

        The first is provenance. The second was a convenience, and labelling it as provenance made
        it forgeable: `SELECT max(dataset_id) AS dataset_id, count(*) FROM ptm_sites` returned the
        catalog-wide 38,045 stamped with one dataset's bundle, in the same words a correct
        narrowing uses. Nobody had to be trying.

        **The narrowing added nothing anyway.** `catalog_id` is a hash of the exact (dataset,
        bundle) set below, so naming it already states, precisely and immutably, which frozen copy
        of every dataset was available. That is the whole citation. A slice of it is a convenience
        that cannot be computed honestly here, so it is not computed at all.
        """
        out = self.identity.base()
        out["n_bundles"] = len(self.identity.bundles)
        if full:
            out["bundles"] = [
                {"dataset_id": b["dataset_id"], "bundle_id": b["bundle_id"]}
                for b in self.identity.bundles
            ]
            out["bundles_are"] = (
                "every bundle this catalog holds, which is what `catalog_id` is a hash of. This is "
                "a fact about the server, not a claim about any answer: no question can change it, "
                "and it is NOT narrowed to what a result touched, because that cannot be determined "
                "from a result without being wrong sometimes and silent about which times."
            )
            if self.identity.study_bundles:
                out["study_bundles"] = [
                    {"layer": b.get("layer"), "bundle_id": b.get("bundle_id")}
                    for b in self.identity.study_bundles
                ]
        else:
            if self.identity.study_bundles:
                out["n_study_bundles"] = len(self.identity.study_bundles)
            out["bundles_are"] = (
                "the whole citation is catalog_id: it is a hash of the exact set of bundles this "
                "catalog holds, listed once by describe() with no target. It describes the server, "
                "not a slice this answer touched."
            )
        # A release is archived at a fixed path and never changes; a working catalog is rebuilt in
        # place and its id moves when the bundles under it do. Both ids are exact -- only one is
        # durable, and a caller citing a number needs to know which kind it is holding.
        out["catalog_kind"] = "release" if self.identity.release else "working build"
        if not self.identity.release:
            out["catalog_kind_means"] = (
                "a working catalog is rebuilt in place, so this catalog_id identifies the data "
                "exactly today but the file at this path may be replaced. Cite a release."
            )
        changed = self.catalog_file_changed
        if changed:
            out["catalog_file_changed"] = changed
        return out

    # -- describe ---------------------------------------------------------------------------

    def describe(
        self, target: str | None = None, detail: DetailLevel = "concise"
    ) -> dict[str, Any]:
        """What this catalog is, what is in it, and what a table's columns mean.

        Args:
            target: nothing for the catalog itself; a table or view name for its columns; an enum
                name for its permissible values; a definition id for the published text behind a
                stored number; `"tables"` for the full list.
            detail: `"concise"` or `"detailed"`. Detailed adds each column's description.
        """
        if detail not in ("concise", "detailed"):
            raise ToolError(f"detail is 'concise' or 'detailed', not {detail!r}")
        target = (target or "").strip()
        if not target or target.lower() in ("catalog", "overview", "."):
            return self._describe_catalog()
        if target.lower() in ("tables", "schema"):
            return self._describe_tables()
        if target in self.tables():
            return self._describe_table(target, detail)
        if target in ENUMS or any(target in e for e in STUDY_ENUMS.values()):
            return self._describe_enum(target)
        definition = self._describe_definition(target)
        if definition is not None:
            return definition
        for layer in STUDY_TABLE_DOCS:
            if target.lower() == layer.lower():
                return self._describe_study_layer(layer)
        raise ToolError(self._unknown_target(target))

    def _unknown_target(self, target: str) -> str:
        pool = list(self.tables()) + list(ENUMS) + ["catalog", "tables"]
        close = difflib.get_close_matches(target, pool, n=4, cutoff=0.6)
        hint = f" Did you mean {', '.join(close)}?" if close else ""
        return (
            f"{target!r} is not a table, view, enum or definition id in this catalog.{hint} "
            f"Call describe with no target for the catalog, or 'tables' for the full list."
        )

    def _describe_catalog(self) -> dict[str, Any]:
        tables = self.tables()
        populated = {n: t for n, t in tables.items() if (t.get("rows") or 0) > 0}
        datasets = (
            self.box.dicts(
                "SELECT dataset_id, title, organisms, acquisition, quant_method, labelling, "
                "enrichment, enrichment_mixed, instrument_vendor, n_runs, n_samples, n_psms_1pct, "
                "n_peptidoforms_1pct, n_protein_groups_1pct, n_ptm_sites, n_open_findings "
                "FROM dataset_overview ORDER BY dataset_id"
            )
            if self.box.has_table("dataset_overview")
            else []
        )
        findings = self.box.dicts(
            "SELECT code, severity, count(*) AS n, min(message) AS example FROM findings "
            "WHERE severity IN ('warning', 'error') GROUP BY 1, 2 ORDER BY n DESC"
        ) if self.box.has_table("findings") else []
        return {
            "catalog": str(self.box.path),
            "what_it_is": SCHEMA_DESCRIPTION,
            **({"schema_drift": self.schema_drift} if self.schema_drift else {}),
            "instance": self.identity.instance,
            "qpx_version": self.identity.qpx_version,
            "datasets": datasets,
            # Every layer the BUILD knows about, each saying whether a delivery was loaded. Only
            # the loaded ones used to be reported, so a catalog whose eight `aging` tables exist
            # and are empty answered `study_layers: []` -- which reads as "there is no study
            # layer" when it means "the tables are here and nobody has delivered rows yet", and
            # contradicted `describe('tables')`, which marked the same tables `kind: study:aging`.
            "study_layers": self._study_layers(),
            "tables_with_rows": [
                {"table": n, "rows": t.get("rows"), "kind": t.get("kind")}
                for n, t in sorted(populated.items(), key=lambda kv: -(kv[1].get("rows") or 0))
            ],
            "tables_empty": sorted(n for n in tables if n not in populated),
            "empty_means": (
                "the table exists and holds no rows in THIS catalog. It is not evidence that the "
                "thing does not exist -- a producer may simply not have delivered it yet. Say so "
                "rather than answering from the empty table."
            ),
            "open_findings": findings,
            # The rules an agent in aging's evaluation reached only by querying, or not at all
            # (aging 070 57h/i/g, 57f, pep 002). Short, and on the first answer, because the first
            # answer is the one every agent reads.
            "read_first": READ_FIRST,
            "next": [
                "describe('tables') for every table with its row count",
                "describe('<table>') for one table's columns and what they mean",
                "search('<gene, accession, peptide, tissue or modification>') to find ids",
                "sql('SELECT ...') for anything else",
            ],
            "provenance": self._provenance(full=True),
        }

    def _study_layers(self) -> list[dict[str, Any]]:
        """Every study layer this build knows, loaded or not.

        A layer whose tables exist and hold nothing is a different fact from a layer that does not
        exist -- aging's benchmark distinguishes NO_TABLE from EMPTY_TABLE, and so must this.
        """
        loaded = {b.get("layer"): b for b in self.identity.study_bundles}
        known = self.tables()
        out: list[dict[str, Any]] = []
        for layer, tables in STUDY_TABLE_DOCS.items():
            present = [name for name in tables if name in known]
            if not present and layer not in loaded:
                continue
            delivery = loaded.get(layer) or {}
            out.append(
                {
                    "layer": layer,
                    "tables_present": len(present),
                    "delivery_loaded": layer in loaded,
                    "bundle_id": delivery.get("bundle_id"),
                    "layer_version": delivery.get("layer_version"),
                    "rows": sum((known[name].get("rows") or 0) for name in present),
                }
            )
        for layer, delivery in loaded.items():
            if layer not in STUDY_TABLE_DOCS:
                out.append(
                    {
                        "layer": layer,
                        "tables_present": None,
                        "delivery_loaded": True,
                        "bundle_id": delivery.get("bundle_id"),
                        "layer_version": delivery.get("layer_version"),
                    }
                )
        return out

    def _describe_tables(self) -> dict[str, Any]:
        docs = self._all_docs()
        rows = []
        for name, table in self.tables().items():
            doc = docs.get(name, {})
            rows.append(
                {
                    "table": name,
                    "rows": table.get("rows"),
                    "kind": table.get("kind"),
                    "holds": doc.get("description"),
                    "layer": doc.get("layer"),
                }
            )
        return {
            "tables": rows,
            "kinds": {
                "bundle": "written by the ingester from a producer's results; the evidence",
                "view": "an acceptance rule or a coarser grain applied to a bundle table",
                "derived": "built by `datarepo build` across datasets; the reason a catalog exists",
                "study": "delivered by a study layer, keyed on core identifiers (U5)",
                "table": "a catalog's own bookkeeping (catalog_meta, catalog_bundles, ...)",
            },
            "provenance": self._provenance(),
        }

    def _all_docs(self) -> dict[str, dict[str, Any]]:
        """Prose for every table an agent can reach, keyed by table name.

        Three sources, and the third is the one that was missing: the core schema, each study
        layer's schema, and `catalog.DERIVED_DOCS` for the tables and views `build` invents. The
        derived ones are in no LinkML file, so the generator cannot describe them -- and they are
        exactly the tables `search` answers from and `describe`'s `next` block points at.
        """
        docs: dict[str, dict[str, Any]] = {n: dict(d) for n, d in TABLE_DOCS.items()}
        for layer, tables in STUDY_TABLE_DOCS.items():
            for name, doc in tables.items():
                docs[name] = {**doc, "layer": layer}
        for name, doc in DERIVED_DOCS.items():
            docs[name] = {
                "description": doc["description"],
                "columns": {
                    column: {"description": text}
                    for column, text in (doc.get("columns") or {}).items()
                },
                "derived": True,
            }
        return docs

    def _populated(self, table: str, columns: Sequence[str] | None = None) -> dict[str, int]:
        """Non-null count per column, in one pass.

        The other half of "an empty table is named". `searched_but_empty` fires on `rows == 0`, so
        a table with rows and a 100%-NULL column is invisible to it -- and that is the common case
        on this data, not an edge: aging's `samples` holds 57 rows with `organism_part`,
        `cell_type`, `disease`, `condition` and `cell_line` all entirely NULL, and
        `peptidoforms.is_isoform_specific` is NULL on all 394,255 rows while `describe` advertises
        it as the column that answers isoform questions. A search for "plasma" came back
        `rows: 57, hits: 0`, which reads as "we looked and it is not there".
        """
        names = list(columns) if columns is not None else list(self._column_types(table))
        if not names:
            return {}
        counts = ", ".join(f'count("{name}") AS "{name}"' for name in names)
        rows = self.box.dicts(f'SELECT {counts} FROM "{table}"')
        return {k: int(v or 0) for k, v in (rows[0] if rows else {}).items()}

    def _column_types(self, table: str) -> dict[str, str]:
        """DuckDB's own types for the table as built, not the Arrow schema's.

        The catalog is what the agent will write SQL against, and it carries columns the schema
        does not -- `dataset_id` and `bundle_id` are added by `datarepo build` (D10). Describing it
        from the Arrow schema would have left those two typeless, and `VARCHAR[]` is the form a
        `WHERE list_contains(...)` has to be written for anyway.
        """
        return {
            row["column_name"]: row["data_type"]
            for row in self.box.dicts(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position",
                [table],
            )
        }

    def _describe_table(self, table: str, detail: str) -> dict[str, Any]:
        doc = self._all_docs().get(table, {})
        types = self._column_types(table)
        column_docs = doc.get("columns", {})
        info = self.tables().get(table, {})
        total = info.get("rows") or 0
        # In both detail modes, because a 100%-NULL column is the thing most likely to produce a
        # confident false negative, and an agent asking for `concise` has not asked to be misled.
        # Measured: 31 columns over 1.2M `psms` rows costs 60 ms.
        populated = self._populated(table) if total else {}
        columns = []
        for name in types:
            entry: dict[str, Any] = {"column": name, "type": types.get(name)}
            if name in populated:
                entry["populated"] = populated[name]
                if populated[name] == 0:
                    entry["all_null"] = (
                        f"NULL on all {total:,} rows. Nothing has been delivered in this column, "
                        f"so a query filtering on it returns nothing for THAT reason -- not "
                        f"because the answer is negative."
                    )
            cdoc = column_docs.get(name)
            if cdoc:
                entry["means"] = cdoc.get("description")
                if cdoc.get("identifier"):
                    entry["identifier"] = True
                if cdoc.get("enum"):
                    entry["enum"] = cdoc["enum"]
                    entry["values"] = self._enum_values(cdoc["enum"])
                if cdoc.get("unit"):
                    entry["unit"] = cdoc["unit"]
            elif name in ("dataset_id", "bundle_id", "study_layer", "study_bundle_id"):
                entry["means"] = (
                    "provenance added by `datarepo build`: which dataset and which bundle this row "
                    "came from. Every answer can be traced back through it."
                )
            columns.append(entry)
        info = self.tables().get(table, {})
        out = {
            "table": table,
            "kind": info.get("kind"),
            "rows": info.get("rows"),
            "one_row_is": doc.get("description"),
            **({"schema_drift": self.schema_drift} if self.schema_drift else {}),
            "layer": doc.get("layer"),
            # `concise` renders each column as one line instead of a JSON object. The SAME facts,
            # a third of the tokens -- nothing is dropped, because a column description an agent
            # does not read is exactly how it invents what a column means.
            "columns": columns if detail == "detailed" else [_one_line_column(c) for c in columns],
            "provenance": self._provenance(),
        }
        if (info.get("rows") or 0) == 0:
            out["empty_means"] = (
                f"{table} exists in this catalog and holds no rows. Do not answer a question about "
                f"it from another table; say the data has not been delivered."
            )
        if table in ("psms", "peptidoforms", "protein_groups"):
            out["see_also"] = (
                f"{table}_1pct applies the producing search engine's acceptance rule once, so no "
                f"caller has to restate it. Use it unless you specifically want the rejected rows."
            )
        if table == "ptm_sites":
            out["see_also"] = (
                "ptm_sites is keyed on the search engine's own name for a modification, which is "
                "the grain it was measured at; ptm_sites_by_chemistry groups the handful of sites "
                "that reach one dataset under two names."
            )
        return out

    def _enum_values(self, name: str) -> list[str]:
        if name in ENUMS:
            return list(ENUMS[name]["values"])
        for enums in STUDY_ENUMS.values():
            if name in enums:
                return list(enums[name]["values"])
        return []

    def _describe_enum(self, name: str) -> dict[str, Any]:
        entry = ENUMS.get(name)
        layer = None
        if entry is None:
            for layer_name, enums in STUDY_ENUMS.items():
                if name in enums:
                    entry, layer = enums[name], layer_name
                    break
        assert entry is not None  # describe() only routes here when one of the two held it
        return {
            "enum": name,
            "layer": layer,
            "means": entry.get("description"),
            **({"schema_drift": self.schema_drift} if self.schema_drift else {}),
            "values": list(entry.get("values") or []),
            "note": "a column of this enum holds exactly one of these strings, or NULL",
            "provenance": self._provenance(),
        }

    def _describe_definition(self, target: str) -> dict[str, Any] | None:
        """The published text behind a stored number, if `target` names one.

        Definition ids are namespaced `<owner>:<ID>` (U7), and a number with no published
        definition carries `PROVISIONAL:<NAME>` and says so in its own text.
        """
        if not self.box.has_table("definitions"):
            return None
        rows = self.box.dicts(
            "SELECT DISTINCT definition_id, version, owner_project, text, url FROM definitions "
            "WHERE upper(definition_id) = upper(?) ORDER BY version DESC",
            [target],
        )
        if not rows:
            return None
        used_by = self.box.dicts(
            "SELECT DISTINCT name FROM metrics WHERE upper(definition_id) = upper(?) ORDER BY 1",
            [target],
        ) if self.box.has_table("metrics") else []
        return {
            "definition_id": rows[0]["definition_id"],
            "owner_project": rows[0]["owner_project"],
            "versions": [r["version"] for r in rows],
            "text": rows[0]["text"],
            "url": rows[0]["url"],
            "metrics_using_it": [r["name"] for r in used_by],
            "provisional": str(rows[0]["definition_id"]).upper().startswith("PROVISIONAL:"),
            "provenance": self._provenance(),
        }

    def _describe_study_layer(self, layer: str) -> dict[str, Any]:
        loaded = {b.get("layer"): b for b in self.identity.study_bundles}
        tables = []
        for name, doc in STUDY_TABLE_DOCS[layer].items():
            info = self.tables().get(name)
            tables.append(
                {
                    "table": name,
                    "present": info is not None,
                    "rows": (info or {}).get("rows"),
                    "one_row_is": doc.get("description"),
                }
            )
        return {
            "study_layer": layer,
            "loaded_into_this_catalog": layer in loaded,
            "delivery": loaded.get(layer, {}).get("bundle_id"),
            "layer_version": loaded.get(layer, {}).get("layer_version"),
            "tables": tables,
            "note": (
                "A study layer ADDS tables keyed on core identifiers and never alters a core table "
                "(U5). A table present with 0 rows has been delivered empty, which is a different "
                "fact from the table not existing -- both mean 'no data', neither means 'no effect'."
            ),
            "provenance": self._provenance(),
        }

    # -- search -----------------------------------------------------------------------------

    def search(
        self, query: str, kind: SearchKind | None = None, limit: int = SEARCH_LIMIT
    ) -> dict[str, Any]:
        """Find the ids behind a name: a dataset, protein, gene, peptide, modification or tissue.

        Args:
            query: what to look for. An accession, a gene symbol, a peptide sequence, a
                modification name, a tissue or free text.
            kind: restrict to one of `dataset`, `protein`, `peptide`, `modification`, `sample`,
                `run`, `definition`, `localization`. Omit to search them all.
            limit: hits per kind.

        Returns:
            The hits, **and what was searched to get them** -- each source with the rows it holds,
            so "no hits" can be told apart from "that table is empty in this catalog".
        """
        query = (query or "").strip()
        if not query:
            raise ToolError("search needs something to look for")
        limit = max(1, min(int(limit), SEARCH_LIMIT_MAX))
        kinds = self._search_kinds(kind)

        hits: dict[str, list[dict[str, Any]]] = {}
        searched: list[dict[str, Any]] = []
        # One more than asked for, so truncation is OBSERVED rather than inferred from a full page
        # -- the discipline `sql` already used and `search` did not. Without it `search("KRT")`
        # returned `total_hits: 25` beside `rows: 38002` when the real count is 232, with nothing
        # anywhere saying "there are more". `SEARCH_LIMIT`'s own comment claimed it was "how many
        # hits one kind returns before it says there are more". It never said.
        truncated: list[str] = []
        for name in kinds:
            found, sources = getattr(self, f"_search_{name}")(query, limit + 1)
            if len(found) > limit:
                found = found[:limit]
                truncated.append(name)
            searched.extend(sources)
            if found:
                hits[name] = found

        datasets = {
            str(row.get("dataset_id"))
            for rows in hits.values()
            for row in rows
            if row.get("dataset_id")
        }
        for rows in hits.values():
            for row in rows:
                for value in row.get("dataset_ids_1pct") or row.get("dataset_ids") or []:
                    datasets.add(str(value))

        empty = sorted({s["source"] for s in searched if s.get("rows") == 0})
        out: dict[str, Any] = {
            "query": query,
            "hits": hits,
            "total_hits": sum(len(v) for v in hits.values()),
            "searched": searched,
            "provenance": self._provenance(),
        }
        if empty:
            out["searched_but_empty"] = empty
            out["searched_but_empty_means"] = (
                "these tables exist in this catalog and hold no rows, so they could not match "
                "anything. A question they would have answered has no answer here yet -- that is "
                "not the same as the answer being no."
            )
        if truncated:
            out["truncated_kinds"] = truncated
            out["truncated_means"] = (
                f"{', '.join(truncated)} matched MORE than the {limit} hits shown and was cut off. "
                f"The list is not complete and its length is NOT a count -- raise `limit`, narrow "
                f"the query, or count with datarepo_sql."
            )
        if not hits:
            out["no_hits_means"] = (
                f"nothing in the sources listed under 'searched' matched {query!r}. This catalog "
                f"holds {len(self.identity.bundles)} dataset(s), not all of PRIDE, so an absence "
                f"here is an absence from these datasets only."
            )
        return out

    def _search_kinds(self, kind: SearchKind | None) -> list[str]:
        known = list(get_args(SearchKind))
        if kind is None:
            return known
        if kind not in known:
            raise ToolError(f"kind is one of {', '.join(known)}, not {kind!r}")
        return [kind]

    def _source(
        self,
        table: str,
        hits: int,
        note: str | None = None,
        searched_columns: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """One line of the `searched` block: what was looked in, and what was actually in it.

        `searched_columns` is what makes an absence readable. `rows: 57, hits: 0` looks like a
        considered negative; it is not one when the five columns that were matched against are NULL
        on all 57 rows, which is the state of aging's `samples` today. The columns are named
        whether or not they are empty, because an agent also needs to know that a protein NAME
        query never touched a name column -- there is no such column in the schema.
        """
        info = self.tables().get(table)
        entry: dict[str, Any] = {
            "source": table,
            "present": info is not None,
            "rows": None if info is None else info.get("rows"),
            "hits": hits,
        }
        if searched_columns and (info or {}).get("rows"):
            entry["columns_searched"] = list(searched_columns)
            populated = self._populated(table, searched_columns)
            empty = sorted(name for name, count in populated.items() if count == 0)
            if empty:
                entry["columns_all_null"] = empty
                entry["columns_all_null_mean"] = (
                    f"{', '.join(empty)} is NULL on all {info['rows']:,} rows of {table}, so no "
                    f"query could have matched there. Zero hits from this source is missing data, "
                    f"not a negative answer."
                )
        if note:
            entry["note"] = note
        return entry

    def _maybe(self, table: str, sql: str, params: list[Any], limit: int) -> list[dict[str, Any]]:
        """Run a search query only if its table is in this catalog, so an older one still works."""
        if not self.box.has_table(table):
            return []
        return self.box.dicts(sql, params, limit=limit)

    def _search_dataset(self, query: str, limit: int):
        like = f"%{query.lower()}%"
        rows = self._maybe(
            "dataset_overview",
            "SELECT dataset_id, title, organisms, acquisition, quant_method, labelling, "
            "enrichment, enrichment_mixed, instrument_vendor, n_runs, n_samples, n_psms_1pct, "
            "n_protein_groups_1pct FROM dataset_overview "
            "WHERE upper(dataset_id) = upper(?) OR lower(coalesce(title, '')) LIKE ? "
            "OR lower(coalesce(instrument_vendor, '')) LIKE ? "
            "OR lower(list_aggregate(organisms, 'string_agg', ' ')) LIKE ? "
            "ORDER BY dataset_id",
            [query, like, like, like],
            limit,
        )
        return rows, [self._source("dataset_overview", len(rows), searched_columns=(
            "dataset_id", "title", "instrument_vendor", "organisms",
        ))]

    def _search_protein(self, query: str, limit: int):
        upper = query.upper()
        like = f"{upper}%"
        # `proteins` is the search's protein LIST, so `protein_index` holds the decoys too. They
        # are not hidden -- a decoy hit is a real fact about the search -- but they are marked and
        # sorted last, because "LMNA, and also DECOY_P02545" read as two proteins would be a wrong
        # answer produced entirely by presentation.
        rows = self._maybe(
            "protein_index",
            "SELECT protein_accession, gene, organism, n_datasets_contaminant, "
            "starts_with(protein_accession, 'DECOY_') AS is_decoy, n_datasets, "
            "n_datasets_1pct, dataset_ids, dataset_ids_1pct, best_q_value FROM protein_index "
            "WHERE upper(protein_accession) = ? OR upper(coalesce(gene, '')) = ? "
            "OR upper(coalesce(gene, '')) LIKE ? "
            "ORDER BY is_decoy, "
            "(upper(protein_accession) = ? OR upper(coalesce(gene, '')) = ?) DESC, "
            "n_datasets_1pct DESC, protein_accession",
            [upper, upper, like, upper, upper],
            limit,
        )
        notes = []
        if rows:
            # ALWAYS, not only when every hit is zero -- which is what it used to do, so the note
            # never fired on the case that matters. `EIF1AY` comes back `n_datasets_1pct: 2` and
            # sits in ZERO accepted protein groups; 585 accessions here carry `n_datasets_1pct > 0`
            # beside a NULL `best_q_value`. The caveat lived only in describe('protein_index'), and
            # `search` is the tool an agent is told to call first.
            notes.append(
                "n_datasets_1pct counts an accepted protein GROUP **or** an accepted PEPTIDOFORM, "
                "so it is NOT 'identified at 1% protein FDR'. A NULL best_q_value beside a "
                "non-zero n_datasets_1pct means NO accepted protein group contains this "
                "accession -- for protein-level identification query protein_groups_1pct directly"
            )
        if any(r.get("is_decoy") for r in rows):
            notes.append(
                "hits marked is_decoy are reversed-sequence entries the search used to estimate "
                "FDR; they are not proteins and must never be counted as evidence"
            )
        if any(r.get("n_datasets_contaminant") for r in rows):
            # There used to be one corpus-wide `is_contaminant`, and P02768 read `true` while it is
            # a target in all 17 human datasets; an agent concluded albumin was excluded (aging 070).
            notes.append(
                "the contaminant label is PER DATASET: n_datasets_contaminant counts the datasets "
                "whose search labelled this accession a contaminant, out of n_datasets. Human "
                "albumin is a target in a human search and a contaminant in a rodent one. Use "
                "protein_datasets.is_contaminant for one dataset"
            )
        notes.append(
            "matched on ACCESSION (exact) and GENE SYMBOL (exact, then prefix) ONLY. There is no "
            "protein name or description column anywhere in this schema, so a query like "
            "'cytochrome c oxidase' cannot match however many rows this table holds -- zero hits "
            "for a protein NAME is 'never searched', not 'not present'. Search the gene symbol "
            "instead (COX4I1, NDUFA9)"
        )
        return rows, [
            self._source(
                "protein_index",
                len(rows),
                "; ".join(notes),
                searched_columns=("protein_accession", "gene"),
            )
        ]

    def _search_peptide(self, query: str, limit: int):
        if not PEPTIDE_RE.match(query.upper()):
            return [], [
                self._source(
                    "peptide_index",
                    0,
                    "not searched: the query is not 6 or more amino-acid letters",
                )
            ]
        rows = self._maybe(
            "peptide_index",
            "SELECT base_sequence, n_datasets, dataset_ids, n_peptidoforms, best_q_value "
            "FROM peptide_index WHERE base_sequence = ? OR base_sequence LIKE ? "
            "ORDER BY base_sequence = ? DESC, n_datasets DESC",
            [query.upper(), f"%{query.upper()}%", query.upper()],
            limit,
        )
        return rows, [self._source(
            "peptide_index", len(rows), searched_columns=("base_sequence",)
        )]

    def _search_modification(self, query: str, limit: int):
        like = f"%{query.lower()}%"
        rows = self._maybe(
            "ptm_sites",
            "SELECT modification, modification_name, count(*) AS n_sites, "
            "count(DISTINCT dataset_id) AS n_datasets, "
            "list_sort(list(DISTINCT dataset_id)) AS dataset_ids, sum(n_psms) AS n_psms "
            "FROM ptm_sites "
            "WHERE lower(coalesce(modification_name, '')) LIKE ? "
            "OR lower(coalesce(modification, '')) LIKE ? "
            "GROUP BY 1, 2 ORDER BY n_sites DESC",
            [like, like],
            limit,
        )
        sources = [self._source(
            "ptm_sites", len(rows), searched_columns=("modification_name", "modification")
        )]
        declared_table = (
            "search_modifications_declared"
            if self.box.has_table("search_modifications_declared")
            else "search_modifications"
        )
        declared = self._maybe(
            declared_table,
            f'SELECT DISTINCT modification, name, residues, usage, dataset_id FROM "{declared_table}" '
            "WHERE lower(coalesce(name, '')) LIKE ? OR lower(coalesce(modification, '')) LIKE ? "
            "ORDER BY name, dataset_id",
            [like, like],
            limit,
        )
        sources.append(
            self._source(
                declared_table,
                len(declared),
                "what the search was TOLD to look for, which is not what it placed; "
                "a declared modification with no ptm_sites row was searched and not found",
            )
        )
        for row in declared:
            row["_source"] = declared_table
        return rows + declared, sources

    def _search_sample(self, query: str, limit: int):
        like = f"%{query.lower()}%"
        rows = self._maybe(
            "samples",
            # NULLs are filtered out rather than coalesced to a placeholder: an empty list reads as
            # "not recorded for these samples", where a list of '-' reads as a value.
            "SELECT dataset_id, count(*) AS n_samples, "
            "list_sort(list(DISTINCT organism) FILTER (WHERE organism IS NOT NULL)) AS organisms, "
            "list_sort(list(DISTINCT organism_part) FILTER (WHERE organism_part IS NOT NULL)) "
            "  AS organism_parts, "
            "list_sort(list(DISTINCT cell_type) FILTER (WHERE cell_type IS NOT NULL)) AS cell_types, "
            "list_sort(list(DISTINCT disease) FILTER (WHERE disease IS NOT NULL)) AS diseases, "
            "list_sort(list(DISTINCT condition) FILTER (WHERE condition IS NOT NULL)) AS conditions "
            "FROM samples WHERE lower(coalesce(organism, '')) LIKE ? "
            "OR lower(coalesce(organism_part, '')) LIKE ? OR lower(coalesce(cell_type, '')) LIKE ? "
            "OR lower(coalesce(disease, '')) LIKE ? OR lower(coalesce(condition, '')) LIKE ? "
            "OR lower(coalesce(cell_line, '')) LIKE ? OR lower(coalesce(source_name, '')) LIKE ? "
            "GROUP BY dataset_id ORDER BY dataset_id",
            [like] * 7,
            limit,
        )
        sources = [self._source("samples", len(rows), searched_columns=(
            "organism", "organism_part", "cell_type", "disease", "condition", "cell_line",
            "source_name",
        ))]
        characteristics = self._maybe(
            "sample_characteristics",
            "SELECT name, value, count(*) AS n_samples FROM sample_characteristics "
            "WHERE lower(value) LIKE ? OR lower(name) LIKE ? GROUP BY 1, 2 ORDER BY n_samples DESC",
            [like, like],
            limit,
        )
        sources.append(self._source(
            "sample_characteristics", len(characteristics), searched_columns=("name", "value")
        ))
        return rows + characteristics, sources

    def _search_run(self, query: str, limit: int):
        like = f"%{query.lower()}%"
        rows = self._maybe(
            "runs",
            "SELECT dataset_id, run_id, file_name, fraction, technical_replicate, "
            "instrument_model, ms2_spectra, run_minutes, qc_pass FROM runs "
            "WHERE lower(run_id) LIKE ? OR lower(coalesce(file_name, '')) LIKE ? "
            "OR lower(coalesce(instrument_model, '')) LIKE ? ORDER BY dataset_id, run_id",
            [like, like, like],
            limit,
        )
        return rows, [self._source("runs", len(rows), searched_columns=(
            "run_id", "file_name", "instrument_model",
        ))]

    def _search_definition(self, query: str, limit: int):
        like = f"%{query.lower()}%"
        rows = self._maybe(
            "definitions",
            "SELECT DISTINCT definition_id, version, owner_project, text, url FROM definitions "
            "WHERE lower(definition_id) LIKE ? OR lower(coalesce(text, '')) LIKE ? "
            "ORDER BY definition_id, version DESC",
            [like, like],
            limit,
        )
        sources = [self._source(
            "definitions", len(rows), searched_columns=("definition_id", "text")
        )]
        metrics = self._maybe(
            "metrics",
            "SELECT dataset_id, scope, scope_id, name, value, definition_id, source FROM metrics "
            "WHERE lower(name) LIKE ? OR lower(coalesce(definition_id, '')) LIKE ? "
            "ORDER BY dataset_id, name",
            [like, like],
            limit,
        )
        sources.append(self._source(
            "metrics", len(metrics), searched_columns=("name", "definition_id")
        ))
        return rows + metrics, sources

    def _search_localization(self, query: str, limit: int):
        """Organelle and compartment. Usually empty, and saying so is the point.

        The organelle map belongs to `go` (D1) and dataRepo only stores it. A search for
        "mitochondria" against a catalog whose `protein_localizations` holds 0 rows must not come
        back looking like a considered no.
        """
        like = f"%{query.lower()}%"
        # The category is a property of the term (go 004, DATAREPO-29), so it is joined in rather
        # than read off the protein row. A catalog from before schema 0.0.8 has neither table
        # shape; it gets no rows rather than an error.
        rows = []
        if self.box.has_table("organelle_term_categories"):
            rows = self._maybe(
                "protein_localizations",
                # An annotation row names no map (go D28, schema 0.0.9), so the join gives one
                # category row per map; the map is returned so an answer says whose map it used.
                "SELECT l.dataset_id, l.compartment, c.category_map_name, c.organelle_map_version, "
                "c.organelle_category, c.organelle_subcategory, "
                "l.evidence, count(DISTINCT l.protein_accession) AS n_proteins, "
                "list_sort(list(DISTINCT l.protein_accession))[1:10] AS examples "
                "FROM protein_localizations l LEFT JOIN organelle_term_categories c "
                "ON c.compartment = l.compartment AND c.go_release = l.go_release "
                "WHERE lower(l.compartment) LIKE ? OR lower(coalesce(c.organelle_category, '')) LIKE ? "
                "OR lower(coalesce(c.organelle_subcategory, '')) LIKE ? "
                "GROUP BY 1, 2, 3, 4, 5, 6, 7 ORDER BY n_proteins DESC",
                [like, like, like],
                limit,
            )
        sources = [
            self._source(
                "protein_localizations",
                len(rows),
                "where compartment and organelle live. The map is `go`'s to produce (D1); "
                "dataRepo stores it",
            )
        ]
        annotations = self._maybe(
            "protein_annotations",
            "SELECT dataset_id, key, value, count(*) AS n_proteins FROM protein_annotations "
            "WHERE lower(coalesce(value, '')) LIKE ? OR lower(key) LIKE ? "
            "GROUP BY 1, 2, 3 ORDER BY n_proteins DESC",
            [like, like],
            limit,
        )
        sources.append(self._source("protein_annotations", len(annotations)))
        return rows + annotations, sources

    # -- sql --------------------------------------------------------------------------------

    def sql(self, query: str, max_rows: int | None = None) -> dict[str, Any]:
        """Run one read-only SQL statement against this catalog, bounded by D14's sandbox.

        Args:
            query: one statement. `SELECT`, `EXPLAIN`, `PRAGMA` or `SHOW`; several at once are
                refused, and so is anything that writes.
            max_rows: a tighter row cap than the server's, for a query you expect to be large.

        Returns:
            Columns, rows as lists, whether the answer was cut short and by which cap, and the
            provenance of the rows returned.
        """
        result = self.box.query(query, row_cap=max_rows)
        provenance = self._provenance()
        touched, undetermined = self._tables_touched(query)

        out: dict[str, Any] = {
            "sql": query,
            "columns": result.columns,
            "rows": [list(r) for r in result.rows],
            "row_count": result.row_count,
            "truncated": result.truncated,
            "elapsed_seconds": round(result.elapsed_seconds, 3),
            "limits": result.caps,
            "tables_touched": touched,
            "provenance": provenance,
        }
        if undetermined:
            out["tables_touched_undetermined"] = undetermined
        # The reason this key exists. Every "this table is empty, do not answer from it" guard used
        # to live in describe() and search(), the two tools an agent may skip, and was absent from
        # the one it always reaches: a join over two empty tables returned `rows: []` with nothing
        # in the envelope, and "no compartment shows a differential age effect" was one careless
        # step away. An envelope field cannot be skipped.
        empty = [t["table"] for t in (touched or []) if t.get("rows") == 0]
        if empty:
            out["empty_tables"] = empty
            # States the fact and stops. It used to assert the CAUSE -- "this result is empty
            # because there is nothing to query... say the data has not been delivered" -- which it
            # had not established: the same sentence fired on a query that returned nothing because
            # the gene did not exist. A warning that asserts a reason it has not checked is the
            # failure it was written to prevent, pointed the other way.
            out["empty_tables_mean"] = (
                f"{', '.join(empty)} exist in this catalog and hold NO ROWS, so they contributed "
                f"nothing here. Whether that is WHY this result looks as it does depends on the "
                f"query: check before reporting an absence as a finding. An undelivered table is "
                f"never evidence for a negative answer."
            )
        run_relative = self._run_relative_read(query, result.columns, touched)
        if run_relative:
            out["run_relative_columns"] = {c: RUN_RELATIVE_COLUMNS[c] for c in run_relative}
            # Not a refusal: a within-dataset ranking and a count at a threshold are correct uses,
            # and nothing in the text of a query says which one it is. It states what the values
            # are, which the reader cannot see from the numbers.
            out["run_relative_means"] = (
                f"This query reads {', '.join(run_relative)}. MetaMorpheus trains its PEP model "
                f"afresh on every search, so these values are on a scale set by the search that "
                f"wrote them. Rank or threshold them WITHIN one dataset. Do not compare their values "
                f"across datasets or MetaMorpheus releases (no per-dataset medians, means or "
                f"distributions set side by side): compare counts at a threshold instead, and prefer "
                f"`q_value` across releases. Definition: describe('pep:DEF-PEP')."
            )
        if result.truncated:
            out["truncated_by"] = result.truncated_by
            out["truncated_means"] = (
                f"you were given the first {result.row_count} row(s) the query produced, cut off "
                f"by the {result.truncated_by} cap. This is NOT the whole answer: aggregate in SQL "
                f"(count, group by) rather than counting the rows you can see."
            )
        return out


    def _run_relative_read(
        self, query: str, result_columns: Sequence[str], touched: list[dict[str, Any]] | None
    ) -> list[str]:
        """The `RUN_RELATIVE_COLUMNS` a statement reads, as far as can be seen.

        Three routes, any one enough: the parse names the column (through an alias too); the result
        has a column of that name; or the statement expands a `*` and reads a table that holds one.
        The last over-reports -- `count(*) FROM (SELECT * FROM psms)` reads no `pep` -- and that
        side is chosen on purpose: an unneeded note costs a sentence, a missing one a wrong answer.
        What it cannot see is a value renamed inside a CTE whose parse this does not reach; that is
        why the column descriptions carry the same warning.
        """
        hits = {c.lower() for c in result_columns} & RUN_RELATIVE_COLUMNS.keys()
        parsed = self.box.referenced_columns(query)
        if parsed is not None:
            names, star = parsed
            hits |= names & RUN_RELATIVE_COLUMNS.keys()
            if star:
                for table in touched or []:
                    hits |= set(self._column_types(table["table"])) & RUN_RELATIVE_COLUMNS.keys()
        return sorted(hits)

    def _tables_touched(self, query: str) -> tuple[list[dict[str, Any]] | None, str | None]:
        """The catalog tables a statement reads, or `(None, why)` when that cannot be determined.

        **This reads the query, not the engine.** It is a hint about where to look, never evidence
        of where an answer came from -- provenance is `catalog_id` and comes from the server, not
        from anything a question can influence. The distinction is the whole lesson: while this was
        presented as certification, a `WITH protein_groups_1pct AS (SELECT 99999)` came back with
        the real view's 8,055-row count attached to a fabricated number.
        """
        names = self.box.referenced_tables(query)
        if names is None:
            return None, (
                "could not be determined for this statement -- it names a table function that "
                "takes its target as a string (query/query_table/read_*), or is a kind whose "
                "reads cannot be parsed. Tables MAY have been read that are not listed. This is "
                "not a claim that none were."
            )
        known = self.tables()
        return [
            {
                "table": name,
                "rows": known[name].get("rows"),
                "kind": known[name].get("kind"),
            }
            for name in names
            if name in known
        ], None


def _one_line_column(entry: dict[str, Any]) -> str:
    """`concise` form of one column: name, type, meaning, and an enum's values if it has them."""
    parts = [f"{entry['column']} {entry.get('type') or ''}".strip()]
    if entry.get("identifier"):
        parts.append("(identifier)")
    line = " ".join(parts)
    if entry.get("means"):
        line += f" -- {entry['means']}"
    if entry.get("values"):
        line += f" One of: {', '.join(entry['values'])}."
    if entry.get("unit"):
        line += f" Unit: {entry['unit']}."
    if entry.get("all_null"):
        line += f" **{entry['all_null']}**"
    elif entry.get("populated") is not None:
        line += f" [{entry['populated']:,} non-null]"
    return line


# ---------------------------------------------------------------------------------------------
# the MCP wiring
# ---------------------------------------------------------------------------------------------

#: The tools as an agent sees them. Kept here rather than in decorators so `datarepo mcp --list`
#: and the tests can read them without the SDK installed.
TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": f"{TOOL_PREFIX}describe",
        "method": "describe",
        "title": "Describe the catalog, a table, an enum or a definition",
        "description": (
            "What this dataRepo catalog holds and what its columns mean. Call it with no target "
            "first: it returns the datasets, every table with its row count, and the open "
            "findings. Then call it with a table name for that table's columns and what each one "
            "means, an enum name for its permissible values, or a definition id (e.g. "
            "'aging:DEF-PSM-1PCT') for the published text behind a stored number. A table listed "
            "with 0 rows exists and is empty: the data has not been delivered, which is not the "
            "same as the answer being no."
        ),
    },
    {
        "name": f"{TOOL_PREFIX}search",
        "method": "search",
        "title": "Find the ids behind a name",
        "description": (
            "Look up a dataset accession, UniProt accession, gene symbol, peptide sequence, "
            "modification, tissue, cell type, raw file or definition and get back the ids needed "
            "to query it. Returns the hits AND the list of sources searched with the rows each "
            "one holds, so that 'no hits' can be told apart from 'that table is empty in this "
            "catalog'. Use it before writing SQL against an identifier you have not confirmed."
        ),
    },
    {
        "name": f"{TOOL_PREFIX}sql",
        "method": "sql",
        "title": "Run one read-only SQL query",
        "description": (
            "Run one read-only DuckDB statement against the catalog. The catalog is derived and "
            f"cannot be written to. Results are capped at {ROW_CAP:,} rows or {CHAR_CAP:,} "
            f"characters with a 'truncated' flag, and a query still running after "
            f"{TIMEOUT_SECONDS:g} s is stopped -- so aggregate in "
            "SQL rather than fetching rows to count them. Prefer the *_1pct views (psms_1pct, "
            "peptidoforms_1pct, protein_groups_1pct): they apply the producing search engine's "
            "acceptance rule, so you do not have to restate it. Call describe('<table>') first if "
            "you are unsure of a column."
        ),
    },
]


def _error_payload(exc: Exception) -> dict[str, Any]:
    """An error an agent can act on: what went wrong, and what to send instead."""
    hints = {
        QueryRefused: "Send one statement, and only a question -- the catalog is read-only.",
        QueryTimeout: "Narrow it: filter on dataset_id, or aggregate instead of returning rows.",
        ToolError: "Check the argument named in the message.",
        CatalogError: "Call datarepo_describe('tables') to see what this catalog actually has.",
    }
    return {
        "error": type(exc).__name__,
        "message": str(exc),
        "hint": hints.get(type(exc), "Call datarepo_describe() for what this catalog holds."),
    }


def bound_tools(server: CatalogServer) -> list[tuple[dict[str, Any], Any]]:
    """The three tools as annotated functions the SDK can read a schema off, paired with their spec.

    The annotations are copied from the `CatalogServer` methods rather than restated as JSON --
    `tests/test_mcp.py` asserts each wrapper's signature equals its method's, so a new argument
    cannot reach the method without reaching the tool an agent sees. A hand-written JSON schema
    beside a Python signature is two statements of one fact, which is the drift `_schema_docs.py`
    exists to prevent one level down.

    Every `DataRepoError` becomes a RESULT, not an exception: an agent that gets a structured
    `{error, message, hint}` can fix its call, where a transport-level error tells it only that
    something went wrong.
    """

    def wrap(method: Any) -> Any:
        def call(**kwargs: Any) -> dict[str, Any]:
            try:
                return method(**kwargs)
            except DataRepoError as exc:
                return _error_payload(exc)

        return call

    describe_call = wrap(server.describe)
    search_call = wrap(server.search)
    sql_call = wrap(server.sql)

    def datarepo_describe(
        target: str | None = None, detail: DetailLevel = "concise"
    ) -> dict[str, Any]:
        return describe_call(target=target, detail=detail)

    def datarepo_search(
        query: str, kind: SearchKind | None = None, limit: int = SEARCH_LIMIT
    ) -> dict[str, Any]:
        return search_call(query=query, kind=kind, limit=limit)

    def datarepo_sql(query: str, max_rows: int | None = None) -> dict[str, Any]:
        return sql_call(query=query, max_rows=max_rows)

    functions = {
        f"{TOOL_PREFIX}describe": datarepo_describe,
        f"{TOOL_PREFIX}search": datarepo_search,
        f"{TOOL_PREFIX}sql": datarepo_sql,
    }
    pairs = []
    for spec in TOOL_SPECS:
        function = functions[spec["name"]]
        function.__doc__ = spec["description"]
        pairs.append((spec, function))
    return pairs


def _load_sdk() -> Any:
    """The SDK's server class, across the 1.x -> 2.x rename.

    `FastMCP` became `MCPServer` in mcp 2.0 with `add_tool` and `run` unchanged, so both are
    accepted rather than pinning: an operator who already has one installed should not have to
    change it to serve a catalog.
    """
    try:
        from mcp.server.mcpserver import MCPServer  # noqa: PLC0415

        return MCPServer
    except ImportError:
        pass
    try:
        from mcp.server.fastmcp import FastMCP  # noqa: PLC0415

        return FastMCP
    except ImportError as exc:
        raise ToolError(
            "the MCP SDK is not installed. `pip install 'datarepo[mcp]'` (or `pip install mcp`). "
            "It is an optional extra so that `ingest` and `build` keep three dependencies."
        ) from exc


def serve(catalog: Path | str, *, name: str = "datarepo") -> None:
    """Run the stdio MCP server over one catalog until the client disconnects.

    Raises:
        ToolError: the `mcp` SDK is not installed. It is an optional extra, so the core stays at
            three dependencies as `[readers]` does.
        CatalogError: there is no catalog at `catalog`.
    """
    server_class = _load_sdk()
    server = CatalogServer(catalog)
    app = server_class(name)
    for spec, function in bound_tools(server):
        app.add_tool(
            function,
            name=spec["name"],
            description=spec["description"],
            title=spec.get("title"),
            structured_output=True,
        )

    # stderr, never stdout: stdout IS the protocol channel, and a banner printed there would be
    # read as a malformed JSON-RPC message and close the connection.
    print(
        f"datarepo {__version__} mcp: serving catalog {server.identity.catalog_id} "
        f"({server.box.path}) over stdio",
        file=sys.stderr,
    )
    try:
        app.run()
    finally:
        server.close()


# ---------------------------------------------------------------------------------------------
# --install
# ---------------------------------------------------------------------------------------------

#: The Claude Code config this server registers itself in. `--install` writes it so that no JSON is
#: hand-edited (D12), and `datarepo doctor` reports whether the entry is there.
def claude_config_path() -> Path:
    """Where Claude Code keeps its user-level MCP server registrations."""
    override = os.environ.get("CLAUDE_CONFIG_PATH")
    if override:
        return Path(override)
    return Path.home() / ".claude.json"


def install_entry(catalog: Path | str, *, python: str | None = None) -> dict[str, Any]:
    """The `mcpServers` entry for this catalog. Absolute paths: the client sets its own cwd."""
    return {
        "command": python or sys.executable,
        "args": ["-m", "datarepo.cli", "mcp", "--catalog", str(Path(catalog).resolve())],
        "env": {},
    }


def install(
    catalog: Path | str, *, name: str = "datarepo", config: Path | None = None, force: bool = False
) -> dict[str, Any]:
    """Register this server with Claude Code, writing the config rather than asking for hand edits.

    Returns:
        `{"config": path, "name": name, "entry": {...}, "action": "added"|"updated"|"unchanged"}`.

    Raises:
        ToolError: an entry of that name already points somewhere else and `force` is not set.
        CatalogError: there is no catalog at `catalog`.
    """
    path = Path(catalog).resolve()
    if not path.is_file():
        raise CatalogError(f"no catalog at {path}; nothing to serve")
    config = Path(config) if config else claude_config_path()

    document: dict[str, Any] = {}
    if config.is_file():
        try:
            document = json.loads(config.read_text(encoding="utf-8")) or {}
        except ValueError as exc:
            raise ToolError(
                f"{config} is not valid JSON ({exc}); fix or move it rather than have this "
                f"overwrite a config you cannot read"
            ) from exc
    servers = document.setdefault("mcpServers", {})
    entry = install_entry(path)

    existing = servers.get(name)
    if existing == entry:
        action = "unchanged"
    elif existing is not None and not force:
        raise ToolError(
            f"{config} already has an MCP server named {name!r} pointing at "
            f"{' '.join(existing.get('args', []))!r}. Pass --force to repoint it, or --name to "
            f"register this catalog alongside it."
        )
    else:
        action = "updated" if existing is not None else "added"
        servers[name] = entry

    if action != "unchanged":
        config.parent.mkdir(parents=True, exist_ok=True)
        # A config this rewrites is the user's whole Claude Code state, so it is written through a
        # temporary file in the same directory: a crash mid-write leaves the old one intact.
        temp = config.with_suffix(config.suffix + ".datarepo-tmp")
        temp.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        temp.replace(config)
    return {"config": str(config), "name": name, "entry": entry, "action": action}


def installed_entries(config: Path | None = None) -> dict[str, Any]:
    """Every datarepo MCP server registered in the config, for `datarepo doctor`."""
    config = Path(config) if config else claude_config_path()
    if not config.is_file():
        return {}
    try:
        document = json.loads(config.read_text(encoding="utf-8")) or {}
    except ValueError:
        return {}
    servers = (document.get("mcpServers") or {}) if isinstance(document, dict) else {}
    return {
        name: entry
        for name, entry in servers.items()
        if isinstance(entry, dict) and "datarepo" in " ".join(map(str, entry.get("args") or []))
    }
