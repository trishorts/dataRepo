"""Generate the public static site from a built catalog (FRAMEWORK step 4a, D16, D17).

    datarepo site <catalog.duckdb> --out <dir> [--base-url URL] [--data-url URL]

The site is a derived artefact like the catalog itself: it is written from one catalog and nothing
else, regenerating it moves no bundle id and no catalog id, and deleting it loses nothing. dataRepo
ships the generator; aging publishes the output (D8, D16). It needs no server: every page is plain
HTML that works with no API behind it, which FRAMEWORK section 5 requires.

What it writes:

* `index.html` -- every dataset in the catalog, with the catalog's id so a reader knows which data
  the numbers describe. Carries a schema.org `DataCatalog` block.
* `datasets/<id>.html` -- one page per dataset, with a Bioschemas `Dataset` block, the dataset's
  open findings, and a summary sentence.
* `llms.txt` -- the entry point for an agent (llmstxt.org), which is who this repository is for.
* `datasets.json` -- the same facts as the pages, for a program rather than a reader.
* `croissant.json` -- only with `--data-url`, because a Croissant file is a description of files
  someone can download, and without one it would describe nothing.
* `sitemap.xml` and `robots.txt` -- only with `--base-url`, because both need absolute URLs.

**The summary is grounded by construction (D17).** It is a template filled from catalog fields, not
prose from a model, so it may be clumsy but it cannot say anything about biology the catalog does
not hold. It is still labelled "generated", because D17 makes the label part of the contract and a
model-written summary can later replace the template without changing what the label promises.

**Nothing here is invented to fill a gap.** An absent licence is left out of the metadata and
reported, not defaulted to D3's value; an organism with no name in the catalog is shown as its
taxon id; a dataset with no title is shown under its accession. A field the catalog cannot fill is
the same failure as a `required: true` column with no true value.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote

from . import __version__
from .errors import CatalogError

#: Written into the output directory; the only thing that lets a regeneration delete what the last
#: one wrote. A directory without it is not ours, and the generator refuses to write into it.
SITE_MARKER = ".datarepo-site.json"

BIOSCHEMAS_DATASET = "https://bioschemas.org/profiles/Dataset/1.0-RELEASE"
CROISSANT_CONFORMS_TO = "http://mlcommons.org/croissant/1.0"
PARQUET = "application/x-parquet"
REPOSITORY = "https://github.com/trishorts/dataRepo"

LICENCE_URLS = {"CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/"}

#: The bundle tables a dataset page links to, in the order a reader wants them. Everything else a
#: bundle holds is reached through the Croissant file and the schema documentation.
DOWNLOAD_TABLES = (
    "psms", "peptidoforms", "protein_groups", "proteins", "ptm_sites", "quant_values",
    "runs", "samples", "assays", "findings", "metrics", "definitions",
)


@dataclass
class SiteResult:
    out: Path
    catalog_id: str
    files: list[str]
    skipped: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# --- reading the catalog -----------------------------------------------------------------------


def _rows(con: Any, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    result = con.execute(sql, list(params))
    names = [d[0] for d in result.description]
    return [dict(zip(names, row)) for row in result.fetchall()]


def _bundle_licence(path: str | None) -> tuple[str | None, str | None]:
    """The licence and credit line a bundle was written under, or (None, None) if unreadable.

    The catalog does not carry them, the bundle does. Read from the bundle rather than restated
    from D3, because the bundle is what a user downloads and the licence it states is the one that
    binds; a site that restated a decision could disagree with the files it links to.
    """
    if not path:
        return None, None
    try:
        doc = json.loads((Path(path) / "bundle.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    return doc.get("licence"), doc.get("credit")


def _bundle_public_pipeline(path: str | None, commit: str | None) -> tuple[str | None, str | None]:
    """The PUBLIC repo and commit for a private pipeline commit, if the producer records one.

    aging 069 55e: their pipeline repo is private and their public copy is a subtree split with
    different hashes, so neither pair can be derived from the other. They record the public pair in
    the provenance's `pipeline` block (`public_repo`, `public_commit`), and the bundle keeps a
    verbatim copy of every provenance file. The block is found by its `commit`, not by the file's
    name, because the stage names are the producer's.
    """
    if not path or not commit:
        return None, None
    try:
        doc = json.loads((Path(path) / "bundle.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    for source in doc.get("sources") or []:
        if not str(source.get("role", "")).startswith("provenance:") or not source.get("bundle_path"):
            continue
        try:
            provenance = json.loads((Path(path) / source["bundle_path"]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pipeline = provenance.get("pipeline") or {}
        if pipeline.get("commit") == commit and pipeline.get("public_commit"):
            return pipeline.get("public_repo"), pipeline.get("public_commit")
    return None, None


def read_site_facts(catalog: Path) -> dict[str, Any]:
    """Everything the site says, read from one catalog in one pass.

    Raises:
        CatalogError: there is no catalog at `catalog`.
    """
    import duckdb  # noqa: PLC0415

    catalog = Path(catalog)
    if not catalog.is_file():
        raise CatalogError(f"no catalog at {catalog}")
    with duckdb.connect(str(catalog), read_only=True) as con:
        try:
            meta = _rows(con, "SELECT * FROM catalog_meta")[0]
        except (duckdb.Error, IndexError) as exc:
            raise CatalogError(f"{catalog} is not a datarepo catalog: {exc}") from exc
        if "is_contaminant" not in _columns(con, "protein_datasets"):
            # Catalog format 7 made the contaminant label per dataset. Counting proteins from an
            # older catalog would fall back on the corpus-wide flag that dropped albumin (57f).
            raise CatalogError(
                f"{catalog} is catalog format {meta.get('catalog_version')}, built before the "
                f"contaminant label was per dataset (format 7); rebuild it with this datarepo"
            )
        overview = _rows(con, "SELECT * FROM dataset_overview ORDER BY dataset_id")
        extra = {
            r["dataset_id"]: r
            for r in _rows(
                con,
                "SELECT dataset_id, instruments, search_database, sdrf_status, pipeline_repo, "
                "pipeline_commit FROM datasets",
            )
        }
        bundles = {r["dataset_id"]: r for r in _rows(con, "SELECT * FROM catalog_bundles")}
        findings = _rows(
            con,
            "SELECT dataset_id, code, severity, message FROM findings WHERE status = 'open' "
            "ORDER BY dataset_id, CASE severity WHEN 'error' THEN 0 WHEN 'warning' THEN 1 "
            "ELSE 2 END, code",
        )
        # The searched proteome's own species name, taken from the entries that carry its taxon.
        # A contaminant entry has no taxon (schema 0.0.7), so it cannot lend its species here.
        names = _rows(
            con,
            "SELECT dataset_id, organism, mode(organism_name) AS organism_name FROM proteins "
            "WHERE organism IS NOT NULL AND organism_name IS NOT NULL GROUP BY ALL",
        )
        modifications = _rows(
            con,
            "SELECT dataset_id, modification_name, any_value(modification) AS modification, "
            "count(*) AS n_sites FROM ptm_sites WHERE target_decoy = 'target' "
            "GROUP BY dataset_id, modification_name "
            "ORDER BY dataset_id, n_sites DESC, modification_name",
        )
        metrics = _rows(
            con,
            "SELECT dataset_id, name, value, definition_id FROM metrics WHERE scope = 'dataset' "
            "AND name IN ('id_rate', 'contamination_psm_share')",
        )
        merit = _figures_of_merit(con)
        proteins = _protein_evidence(con)

    organism_names: dict[tuple[str, str], str] = {
        (r["dataset_id"], r["organism"]): r["organism_name"] for r in names
    }
    datasets = []
    for row in overview:
        ds = row["dataset_id"]
        bundle = bundles.get(ds, {})
        licence, credit = _bundle_licence(bundle.get("path"))
        public_repo, public_commit = _bundle_public_pipeline(
            bundle.get("path"), (extra.get(ds) or {}).get("pipeline_commit")
        )
        datasets.append({
            **row,
            **{k: v for k, v in extra.get(ds, {}).items() if k != "dataset_id"},
            "organism_names": [
                organism_names.get((ds, taxon)) or taxon for taxon in (row["organisms"] or [])
            ],
            "bundle": {
                "bundle_id": bundle.get("bundle_id"),
                "written_utc": bundle.get("written_utc"),
                "ingester_version": bundle.get("ingester_version"),
                "reconciliation_ok": bundle.get("reconciliation_ok"),
                "reconciliation_failed": list(bundle.get("reconciliation_failed") or []),
                "path": bundle.get("path"),
            },
            "licence": licence,
            "credit": credit,
            "pipeline_public_repo": public_repo,
            "pipeline_public_commit": public_commit,
            "findings": [
                {k: f[k] for k in ("code", "severity", "message")}
                for f in findings if f["dataset_id"] == ds
            ],
            # All of them: a list cut at ten read "zero" for the eleventh (PXD026608's deamidation,
            # aging 069 55c).
            "modifications": [
                {k: m[k] for k in ("modification_name", "modification", "n_sites")}
                for m in modifications if m["dataset_id"] == ds
            ],
            "metrics": {
                m["name"]: {"value": m["value"], "definition_id": m["definition_id"]}
                for m in metrics if m["dataset_id"] == ds
            },
        })
    for ds in datasets:
        severities = [f["severity"] for f in ds["findings"]]
        ds["findings_by_severity"] = {s: severities.count(s) for s in ("error", "warning", "info")}
        ds["finding_codes"] = sorted({f["code"] for f in ds["findings"]})
    return {"meta": meta, "datasets": datasets, "merit": merit, "proteins": proteins}


def _columns(con: Any, table: str) -> set[str]:
    return {
        r["column_name"]
        for r in _rows(
            con, "SELECT column_name FROM information_schema.columns WHERE table_name = ?", [table]
        )
    }


def _protein_evidence(con: Any) -> dict[str, dict[str, Any]]:
    """Every accession with accepted evidence somewhere, and where (aging 070, DATAREPO-56).

    The site could answer no protein-level question at all -- is albumin identified, which datasets
    have tau -- because nothing below the dataset reached it. This is the smallest thing that does:
    per accession, the datasets where a protein group or peptidoform passed, with the contaminant
    label AS THAT DATASET HAS IT. Decoys are left out; a contaminant is kept and labelled.
    """
    rows = _rows(
        con,
        "SELECT d.protein_accession, i.gene, i.organism, d.dataset_id, d.n_protein_groups, "
        "d.n_peptidoforms, d.best_q_value, d.is_contaminant "
        "FROM protein_datasets d JOIN protein_index i USING (protein_accession) "
        "WHERE (d.n_protein_groups > 0 OR d.n_peptidoforms > 0) "
        "AND d.protein_accession NOT LIKE 'DECOY%' ORDER BY 1, 4",
    )
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        entry = out.setdefault(
            r["protein_accession"], {"gene": r["gene"], "organism": r["organism"], "datasets": []}
        )
        entry["datasets"].append({
            "dataset_id": r["dataset_id"],
            "n_protein_groups": r["n_protein_groups"],
            "n_peptidoforms": r["n_peptidoforms"],
            "best_protein_group_q_value": r["best_q_value"],
            "is_contaminant": r["is_contaminant"],
        })
    return out


def _figures_of_merit(con: Any) -> list[dict[str, Any]]:
    """The front page's headline numbers, each with the rule that produced it.

    Every figure is a sum or a count over catalog tables the dataset pages also show, and each
    carries a note saying what it counts, because a bare "9,236 proteins" invites the reader to
    supply their own definition -- decoys or not, contaminants or not, 1% FDR or anything matched.
    A figure some datasets cannot supply says how many did, rather than presenting a partial sum
    as a total.
    """
    n_datasets, runs, psms, sites = con.execute(
        "SELECT count(*), sum(n_runs), sum(n_psms_1pct), sum(n_ptm_sites) FROM dataset_overview"
    ).fetchone()
    ms2, ms2_datasets = con.execute(
        "SELECT sum(value), count(DISTINCT dataset_id) FROM metrics "
        "WHERE scope = 'dataset' AND name = 'ms2'"
    ).fetchone()
    # Per dataset, because the contaminant label is: human albumin is a target in a human search
    # and a contaminant in a rodent one, and a corpus-wide flag dropped it from every count (aging
    # 070 57f). An accession counts in a dataset where it was accepted and was not a contaminant.
    proteins, shared = con.execute(
        "SELECT count(*), count(*) FILTER (WHERE n >= 3) FROM ("
        "  SELECT protein_accession, count(DISTINCT dataset_id) AS n FROM protein_datasets "
        "  WHERE (n_protein_groups > 0 OR n_peptidoforms > 0) "
        "    AND NOT coalesce(is_contaminant, false) AND protein_accession NOT LIKE 'DECOY%' "
        "  GROUP BY 1)"
    ).fetchone()
    # Enriched datasets (pull-downs, probes, IPs) say nothing about a proteome, so the count a reader
    # asking "how much of the proteome is here" needs is the one over whole-proteome datasets only
    # (aging 070 57d). A mixed deposit is left out: its declaration is true of some runs only.
    whole = con.execute(
        "SELECT count(DISTINCT p.protein_accession) FROM protein_datasets p "
        "JOIN datasets d USING (dataset_id) "
        "WHERE d.enrichment = ['none'] AND NOT coalesce(d.enrichment_mixed, false) "
        "AND (p.n_protein_groups > 0 OR p.n_peptidoforms > 0) "
        "AND NOT coalesce(p.is_contaminant, false) AND p.protein_accession NOT LIKE 'DECOY%'"
    ).fetchone()[0]
    n_whole = con.execute(
        "SELECT count(*) FROM datasets WHERE enrichment = ['none'] AND NOT coalesce(enrichment_mixed, false)"
    ).fetchone()[0]
    kinds = con.execute(
        "SELECT count(DISTINCT modification_name) FROM ptm_sites WHERE target_decoy = 'target'"
    ).fetchone()[0]
    ms2_note = "MS2 scans in the raw files, summed (aging:DEF-MS2)"
    if ms2_datasets != n_datasets:
        ms2_note += f"; {ms2_datasets} of {n_datasets} datasets report it"
    return [
        {"label": "Datasets", "value": n_datasets,
         "note": "public PRIDE datasets, each reanalysed from its raw files"},
        {"label": "Raw files searched", "value": runs, "note": "LC-MS/MS runs"},
        {"label": "Spectra searched", "value": ms2 and int(ms2), "note": ms2_note},
        {"label": "PSMs at 1% FDR", "value": psms,
         "note": "target peptide-spectrum matches, as the search engine counts them"},
        {"label": "Proteins identified", "value": proteins,
         "note": f"accessions with 1%-FDR evidence, decoys and contaminants excluded; "
                 f"{shared or 0:,} of them in 3 or more datasets"},
        {"label": "Proteins, whole-proteome datasets", "value": whole,
         "note": f"the same count over the {n_whole:,} datasets with no enrichment step; an "
                 f"enriched dataset (pull-down, probe, IP) says nothing about the proteome"},
        {"label": "PTM sites", "value": sites,
         "note": f"modified residues on proteins, {kinds or 0:,} kinds of modification"},
    ]


# --- words -------------------------------------------------------------------------------------


def _n(value: Any) -> str:
    return "unknown" if value is None else f"{value:,}"


def _plural(n: int, word: str) -> str:
    return f"{n:,} {word}" if n == 1 else f"{n:,} {word}s"


def _join(items: Sequence[str]) -> str:
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _enrichment_words(values: Sequence[str] | None, mixed: bool = False) -> str:
    values = list(values or [])
    if mixed:
        # A mixed deposit's declaration is true of some runs only (G63): saying "enrichment:
        # chemical_probe" alone would present its whole-proteome runs as captures.
        declared = _join(values) or "an unrecorded enrichment"
        return f"runs that differ in enrichment ({declared} on some runs; see each run's own)"
    if not values:
        return "no recorded enrichment"
    if values == ["none"]:
        return "no enrichment step (whole proteome)"
    if values == ["other"]:
        return "an enrichment step outside the controlled list (recorded as `other`)"
    return "enrichment: " + _join(values)


def _enrichment_cell(ds: dict[str, Any]) -> str:
    """The declared enrichment, saying so when the runs differ (G63)."""
    text = ", ".join(ds.get("enrichment") or [])
    return f"{text} (on some runs only; runs differ)" if ds.get("enrichment_mixed") else text


def summary(ds: dict[str, Any]) -> str:
    """The dataset's summary sentence, filled only from catalog fields (D17).

    Every clause is a field or a count the page also shows, so a reader can check the sentence
    against the table below it. Nothing about what the study found biologically can appear here,
    because the catalog holds no such field.
    """
    quant = (ds.get("quant_method") or "").replace("_", "-")
    kind = " ".join(x for x in (ds.get("acquisition"), quant) if x)
    # The organism is the dataset's, as the producer's manifest states it -- not the organism a
    # title mentions. PXD050351's title says "in mice"; its PRIDE record and its samples are a
    # human cell line, which is what the proteomics measured.
    organisms = _join(ds["organism_names"]) or "unrecorded organism"
    parts = [
        f"{ds['dataset_id']} is a {kind} dataset ({organisms}) "
        f"with {_plural(ds['n_runs'], 'run')}, {_plural(ds['n_samples'], 'sample')} and "
        f"{_enrichment_words(ds.get('enrichment'), bool(ds.get('enrichment_mixed')))}."
    ]
    engine = " ".join(x for x in (ds.get("search_engine"), ds.get("search_engine_version")) if x)
    if engine:
        parts.append(f"It was reanalysed with {engine}.")
    parts.append(
        f"At 1% FDR the search reports {_n(ds['n_psms_1pct'])} PSMs, "
        f"{_n(ds['n_peptidoforms_1pct'])} peptidoforms and {_n(ds['n_protein_groups_1pct'])} "
        f"protein groups, and the repository holds {_n(ds['n_ptm_sites'])} PTM sites for it."
    )
    warnings = sum(1 for f in ds["findings"] if f["severity"] in ("warning", "error"))
    if warnings:
        parts.append(f"{_plural(warnings, 'open warning')} about it are recorded.")
    return " ".join(parts)


# --- URLs --------------------------------------------------------------------------------------


def _pride_url(dataset_id: str) -> str | None:
    if dataset_id.startswith("PXD"):
        return f"https://www.ebi.ac.uk/pride/archive/projects/{quote(dataset_id)}"
    return None


def _page_path(dataset_id: str) -> str:
    return f"datasets/{quote(dataset_id)}.html"


def _absolute(base_url: str | None, path: str) -> str | None:
    return f"{base_url.rstrip('/')}/{path}" if base_url else None


def _download_url(data_url: str | None, ds: dict[str, Any], table: str) -> str | None:
    bundle_id = ds["bundle"]["bundle_id"]
    if not data_url or not bundle_id:
        return None
    return f"{data_url.rstrip('/')}/{quote(ds['dataset_id'])}/{bundle_id}/{table}.parquet"


def _licence_url(licence: str | None) -> str | None:
    return LICENCE_URLS.get(licence or "", licence)


# --- structured data ---------------------------------------------------------------------------


def dataset_jsonld(
    ds: dict[str, Any], meta: dict[str, Any], *, base_url: str | None, data_url: str | None
) -> dict[str, Any]:
    """A Bioschemas Dataset (1.0-RELEASE) block for one dataset page."""
    doc: dict[str, Any] = {
        "@context": "https://schema.org/",
        "@type": "Dataset",
        "dct:conformsTo": {"@id": BIOSCHEMAS_DATASET, "@type": "CreativeWork"},
        "@id": _absolute(base_url, _page_path(ds["dataset_id"])),
        "url": _absolute(base_url, _page_path(ds["dataset_id"])),
        "name": f"{ds['dataset_id']} reanalysis: {ds.get('title') or ds['dataset_id']}",
        "identifier": [ds["dataset_id"], f"datarepo:bundle:{ds['bundle']['bundle_id']}"],
        "description": summary(ds),
        "version": ds["bundle"]["bundle_id"],
        "dateModified": ds["bundle"]["written_utc"],
        "keywords": [
            "proteomics", "mass spectrometry", "reanalysis", "aging",
            *(ds["organism_names"] or []),
        ],
        "measurementTechnique": "mass spectrometry",
        "variableMeasured": [
            "peptide-spectrum match", "peptidoform", "protein group", "PTM site",
            "protein abundance",
        ],
        "isBasedOn": _pride_url(ds["dataset_id"]),
        "license": _licence_url(ds.get("licence")),
        "creator": {"@type": "Organization", "name": ds["credit"]} if ds.get("credit") else None,
        "includedInDataCatalog": {
            "@type": "DataCatalog",
            "name": f"datarepo catalog {meta['catalog_id']}",
            "url": _absolute(base_url, "index.html"),
        },
    }
    downloads = [
        {"@type": "DataDownload", "name": f"{t}.parquet", "encodingFormat": PARQUET,
         "contentUrl": url}
        for t in DOWNLOAD_TABLES
        if (url := _download_url(data_url, ds, t))
    ]
    if downloads:
        doc["distribution"] = downloads
    return {k: v for k, v in doc.items() if v is not None}


def catalog_jsonld(
    facts: dict[str, Any], *, title: str, base_url: str | None
) -> dict[str, Any]:
    meta = facts["meta"]
    doc = {
        "@context": "https://schema.org/",
        "@type": "DataCatalog",
        "name": title,
        "url": _absolute(base_url, "index.html"),
        "identifier": f"datarepo:catalog:{meta['catalog_id']}",
        "description": (
            f"Search and quantification results for {len(facts['datasets'])} public proteomics "
            "datasets reanalysed with one pipeline, for questions about how organelle proteomes "
            "change with age."
        ),
        "dataset": [
            {"@type": "Dataset", "name": ds["dataset_id"], "identifier": ds["dataset_id"],
             "url": _absolute(base_url, _page_path(ds["dataset_id"]))}
            for ds in facts["datasets"]
        ],
    }
    for entry in doc["dataset"]:
        if entry["url"] is None:
            del entry["url"]
    return {k: v for k, v in doc.items() if v is not None}


_ARROW_TO_CROISSANT = {
    "string": "sc:Text", "large_string": "sc:Text",
    "int64": "sc:Integer", "int32": "sc:Integer",
    "double": "sc:Float", "float": "sc:Float",
    "bool": "sc:Boolean",
}


def _croissant_type(arrow_type: Any) -> tuple[str, bool]:
    """(Croissant dataType, repeated) for an Arrow type."""
    import pyarrow as pa  # noqa: PLC0415

    if pa.types.is_list(arrow_type) or pa.types.is_large_list(arrow_type):
        return _croissant_type(arrow_type.value_type)[0], True
    return _ARROW_TO_CROISSANT.get(str(arrow_type), "sc:Text"), False


def _sha256(path: Path) -> str:
    import hashlib  # noqa: PLC0415

    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def croissant(
    facts: dict[str, Any], *, title: str, base_url: str | None, data_url: str
) -> tuple[dict[str, Any], list[str]]:
    """A Croissant 1.0 description of the bundles' Parquet files, and the files it could not read.

    **One FileObject and one RecordSet per (dataset, table), not one FileSet per table.** A FileSet
    has to sit inside a container a loader can list -- a git repository, an archive or a local
    folder -- and a directory served over HTTP is none of those. The FileSet form passed
    `mlcroissant validate` and then loaded ZERO records from a served store, with no error. The
    per-file form loads; that was measured, not assumed (2026-09-23).

    Every file is hashed from the store, and its fields are read from the file's own Parquet
    schema rather than this package's, because a catalog may hold bundles written against an
    earlier schema. A file that cannot be read is left out and returned, never described from a
    guess at its contents.
    """
    import pyarrow.parquet as pq  # noqa: PLC0415

    meta = facts["meta"]
    datasets = [ds for ds in facts["datasets"] if ds["bundle"]["bundle_id"]]
    licences = sorted({ds["licence"] for ds in datasets if ds.get("licence")})
    credits = sorted({ds["credit"] for ds in datasets if ds.get("credit")})
    files, record_sets, unreadable = [], [], []
    for ds in datasets:
        folder = Path(ds["bundle"]["path"] or "")
        for table in DOWNLOAD_TABLES:
            path = folder / f"{table}.parquet"
            try:
                schema = pq.read_schema(path)
                sha256 = _sha256(path)
            except OSError:
                unreadable.append(f"{ds['dataset_id']}/{table}.parquet")
                continue
            key = f"{ds['dataset_id']}/{table}"
            files.append({
                "@type": "cr:FileObject",
                "@id": f"{key}.parquet",
                "name": f"{key}.parquet",
                "contentUrl": _download_url(data_url, ds, table),
                "encodingFormat": PARQUET,
                "contentSize": f"{path.stat().st_size} B",
                "sha256": sha256,
            })
            fields = []
            for column in schema:
                data_type, repeated = _croissant_type(column.type)
                spec: dict[str, Any] = {
                    "@type": "cr:Field",
                    "@id": f"{key}/{column.name}",
                    "name": column.name,
                    "dataType": data_type,
                    "source": {"fileObject": {"@id": f"{key}.parquet"},
                               "extract": {"column": column.name}},
                }
                if repeated:
                    spec["repeated"] = True
                fields.append(spec)
            record_sets.append({"@type": "cr:RecordSet", "@id": key, "name": key, "field": fields})
    doc = {
        "@context": {
            "@language": "en", "@vocab": "https://schema.org/", "sc": "https://schema.org/",
            "cr": "http://mlcommons.org/croissant/", "rai": "http://mlcommons.org/croissant/RAI/",
            "dct": "http://purl.org/dc/terms/",
            "equivalentProperty": "cr:equivalentProperty",
            "examples": {"@id": "cr:examples", "@type": "@json"},
            "samplingRate": "cr:samplingRate",
            "citeAs": "cr:citeAs", "column": "cr:column", "conformsTo": "dct:conformsTo",
            "data": {"@id": "cr:data", "@type": "@json"},
            "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
            "extract": "cr:extract", "field": "cr:field", "fileProperty": "cr:fileProperty",
            "fileObject": "cr:fileObject", "fileSet": "cr:fileSet", "format": "cr:format",
            "includes": "cr:includes", "isLiveDataset": "cr:isLiveDataset",
            "jsonPath": "cr:jsonPath", "key": "cr:key", "md5": "cr:md5",
            "parentField": "cr:parentField", "path": "cr:path", "recordSet": "cr:recordSet",
            "references": "cr:references", "regex": "cr:regex", "repeated": "cr:repeated",
            "replace": "cr:replace", "separator": "cr:separator", "source": "cr:source",
            "subField": "cr:subField", "transform": "cr:transform",
        },
        "@type": "sc:Dataset",
        "conformsTo": CROISSANT_CONFORMS_TO,
        "name": title,
        "description": catalog_jsonld(facts, title=title, base_url=base_url)["description"],
        "url": _absolute(base_url, "index.html") or data_url,
        # Not `version`: Croissant wants semver there, and a catalog id is a content hash. The id
        # is what identifies the data, so it goes where identifiers go.
        "identifier": f"datarepo:catalog:{meta['catalog_id']}",
        "datePublished": str(meta["built_utc"])[:10],
        "license": [_licence_url(x) for x in licences] or None,
        "creator": [{"@type": "Organization", "name": c} for c in credits] or None,
        "distribution": files,
        "recordSet": record_sets,
    }
    return {k: v for k, v in doc.items() if v is not None}, unreadable


# --- HTML --------------------------------------------------------------------------------------


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _jsonld_script(doc: dict[str, Any]) -> str:
    # `</` cannot appear inside a script element; escaping `<` keeps a title from closing it.
    text = json.dumps(doc, indent=1, ensure_ascii=False).replace("<", "\\u003c")
    return f'<script type="application/ld+json">\n{text}\n</script>'


STYLE = """\
:root {
  --bg: #fbfaf7; --fg: #1c1b22; --muted: #5b5968; --line: #e4e1ea; --panel: #f4f2f8;
  --accent: #6d28d9; --accent-soft: #efe9fb;
  --band: linear-gradient(120deg, #0e7490 0%, #4f46e5 48%, #a21caf 100%);
  --band-fg: #ffffff; --band-muted: #e5e7ff;
  --c1: #0e9f8e; --c2: #3b82f6; --c3: #8b5cf6; --c4: #e0447a; --c5: #f08c1c; --c6: #16a34a;
  --warn-bg: #fff4dc; --warn-line: #e3a008; --err-bg: #fde8e6; --err-line: #dc4c3f;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14131a; --fg: #ebe9f2; --muted: #a4a1b3; --line: #2f2c3b; --panel: #1d1b26;
    --accent: #c4b5fd; --accent-soft: #2a2340;
    --band: linear-gradient(120deg, #0b5566 0%, #3730a3 50%, #86198f 100%);
    --band-fg: #ffffff; --band-muted: #d6d8ff;
    --c1: #2dd4bf; --c2: #60a5fa; --c3: #a78bfa; --c4: #f472b6; --c5: #fbbf24; --c6: #4ade80;
    --warn-bg: #2f2716; --warn-line: #c08a2a; --err-bg: #36201f; --err-line: #e06b5f;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
}
main, footer { max-width: 60rem; margin: 0 auto; padding: 0 16px; }
header {
  background: var(--band); color: var(--band-fg);
  padding: 2.25rem max(16px, calc((100% - 60rem) / 2 + 16px)) 1.75rem;
  margin-bottom: 1.5rem;
}
header h1 { margin: 0.25rem 0 0.4rem; }
header p { margin: 0.3rem 0; color: var(--band-muted); }
header a { color: var(--band-fg); text-decoration-color: rgba(255, 255, 255, 0.5); }
header code { color: var(--band-fg); }
footer {
  color: var(--muted); font-size: 0.875rem; padding: 2rem 16px 3rem; margin-top: 2.5rem;
  border-top: 4px solid transparent; border-image: var(--band) 1;
}
h1 { font-size: 1.75rem; line-height: 1.25; }
h2 { font-size: 1.15rem; margin: 2rem 0 0.5rem; padding-left: 0.6rem;
  border-left: 4px solid var(--accent); }
a { color: var(--accent); }
code { font: 0.9em ui-monospace, "Cascadia Mono", Consolas, monospace; }
.crumb { font-size: 0.9rem; }
.tagline { font-size: 1.05rem; }
.lede { font-size: 1.05rem; }
.generated {
  background: var(--accent-soft); border-left: 4px solid var(--accent); padding: 0.75rem 1rem;
  margin: 1rem 0; border-radius: 0 6px 6px 0;
}
.generated .label {
  display: block; font-size: 0.75rem; letter-spacing: 0.04em; text-transform: uppercase;
  color: var(--accent); font-weight: 600; margin-bottom: 0.25rem;
}
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 0.925rem; }
th, td { text-align: left; padding: 0.45rem 0.6rem; border-bottom: 1px solid var(--line);
  vertical-align: top; }
thead th { font-weight: 600; color: var(--fg); background: var(--accent-soft); }
tbody tr:hover { background: var(--panel); }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 0.35rem 1rem; margin: 0; }
dt { color: var(--muted); }
dd { margin: 0; overflow-wrap: anywhere; }
.finding { border-left: 4px solid var(--line); padding: 0.5rem 0.75rem; margin: 0.5rem 0;
  background: var(--panel); border-radius: 0 6px 6px 0; }
.finding.warning { border-color: var(--warn-line); background: var(--warn-bg); }
.finding.error { border-color: var(--err-line); background: var(--err-bg); }
.finding .code { font-weight: 600; }
.note { color: var(--muted); font-size: 0.9rem; }
.about p { margin: 0.6rem 0; }
.about h2 { margin-top: 1.25rem; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(10.5rem, 1fr));
  gap: 0.75rem; margin: 1.5rem 0 0.5rem; }
.tile { background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  border-top: 5px solid var(--c1); padding: 0.75rem 0.9rem; }
.tile:nth-child(6n+2) { border-top-color: var(--c2); }
.tile:nth-child(6n+3) { border-top-color: var(--c3); }
.tile:nth-child(6n+4) { border-top-color: var(--c4); }
.tile:nth-child(6n+5) { border-top-color: var(--c5); }
.tile:nth-child(6n+6) { border-top-color: var(--c6); }
.tile-label { font-size: 0.85rem; color: var(--muted); font-weight: 500; }
.tile-value { font-size: 2rem; font-weight: 650; line-height: 1.2; margin: 0.15rem 0; }
.tile-note { font-size: 0.8rem; color: var(--muted); line-height: 1.35; }
.notice { background: var(--warn-bg); border-bottom: 2px solid var(--warn-line);
  padding: 0.6rem 16px; text-align: center; font-size: 0.925rem; }
@media (max-width: 36rem) {
  dl { grid-template-columns: 1fr; }
  dt { margin-top: 0.5rem; }
  header { padding-top: 1.5rem; }
}
"""


def _page(title: str, body: str, *, root: str, jsonld: dict[str, Any], meta: dict[str, Any]) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)}</title>
<link rel="stylesheet" href="{root}style.css">
<link rel="alternate" type="text/plain" href="{root}llms.txt" title="llms.txt">
{_jsonld_script(jsonld)}
</head>
<body>
{body}
<footer>
Generated by <a href="{REPOSITORY}">datarepo</a> {_e(__version__)} from catalog
<code>{_e(meta['catalog_id'])}</code>, built {_e(meta['built_utc'])} by datarepo
{_e(meta['builder_version'])} (schema {_e(meta['schema_version'])}).
Every number on this site is read from that catalog; cite its id with any number you reuse.
</footer>
</body>
</html>
"""


def _compact(value: Any) -> str:
    """1,284 / 12.9K / 4.45M: a tile's headline. The exact value is in its title attribute."""
    if value is None:
        return "—"
    # (threshold, divisor, suffix): thousands are compacted only from 10,000, so 9,236 stays exact.
    for threshold, size, suffix in (
        (1_000_000_000, 1_000_000_000, "B"), (1_000_000, 1_000_000, "M"), (10_000, 1_000, "K"),
    ):
        if value >= threshold:
            return f"{value / size:.3g}{suffix}"
    return f"{value:,}"


_MD_INLINE = (
    (re.compile(r"\*\*(.+?)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])"), r"<em>\1</em>"),
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+|[\w./#-]+)\)"), r'<a href="\2">\1</a>'),
)


def about_html(markdown: str) -> str:
    """A small, safe subset of Markdown: `## ` headings, `- ` lists, paragraphs, and inline bold,
    italic, code and links.

    The text is escaped BEFORE any markup is added, so the file cannot inject HTML, and a link may
    only be http(s) or a relative path. Deliberately not a Markdown library: the about text is a
    few paragraphs written by the instance owner, and the core stays at three dependencies.
    """
    def inline(text: str) -> str:
        text = html.escape(text, quote=True)
        for pattern, repl in _MD_INLINE:
            text = pattern.sub(repl, text)
        return text

    out: list[str] = []
    for block in re.split(r"\n\s*\n", markdown.strip()):
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if lines and lines[0].startswith("## "):
            out.append(f"<h2>{inline(lines[0][3:].strip())}</h2>")
            lines = lines[1:]
        if not lines:
            continue
        if all(line.lstrip().startswith("- ") for line in lines):
            items = "".join(f"<li>{inline(line.lstrip()[2:])}</li>" for line in lines)
            out.append(f"<ul>{items}</ul>")
        else:
            out.append(f"<p>{inline(' '.join(line.strip() for line in lines))}</p>")
    return "\n".join(out)


def _severity_words(ds: dict[str, Any]) -> str:
    counts = ds["findings_by_severity"]
    return (
        f"Recorded against this dataset: {_plural(counts['error'], 'error')}, "
        f"{_plural(counts['warning'], 'warning')} and {counts['info']:,} for information"
    )


def _findings_cell(ds: dict[str, Any]) -> str:
    counts = ds["findings_by_severity"]
    head = f"{counts['error']} E / {counts['warning']} W / {counts['info']} I"
    return f'{head}<br><span class="note">{_e(", ".join(ds["finding_codes"]))}</span>'


def _corpus_table(datasets: Sequence[dict[str, Any]]) -> str:
    """Datasets by organism and enrichment (aging 070 57d), so "which datasets are whole-proteome
    mouse" is one glance rather than 34 page opens."""
    grid: dict[str, dict[str, int]] = {}
    for ds in datasets:
        organism = _join(ds["organism_names"]) or "not recorded"
        enrichment = _enrichment_cell(ds) or "not recorded"
        grid.setdefault(organism, {}).setdefault(enrichment, 0)
        grid[organism][enrichment] += 1
    columns = sorted({e for row in grid.values() for e in row}, key=lambda e: (e != "none", e))
    head = "".join(f'<th class="num">{_e(c)}</th>' for c in columns)
    body = "\n".join(
        f"<tr><td>{_e(org)}</td>"
        + "".join(f'<td class="num">{row.get(c, "")}</td>' for c in columns)
        + f'<td class="num">{sum(row.values())}</td></tr>'
        for org, row in sorted(grid.items())
    )
    return (
        '<div class="scroll"><table>\n<thead><tr><th>Organism searched</th>'
        f'{head}<th class="num">All</th></tr></thead>\n<tbody>\n{body}\n</tbody></table></div>\n'
        '<p class="note">Datasets by the organism of the searched database and the declared '
        'enrichment. "none" is a whole-proteome dataset; any other value is a capture, and a '
        "protein's absence from one says nothing about the proteome.</p>"
    )


def _index_html(
    facts: dict[str, Any], *, title: str, base_url: str | None, about: str | None = None
) -> str:
    meta = facts["meta"]
    rows = []
    for ds in facts["datasets"]:
        rows.append(
            "<tr>"
            f'<td><a href="{_page_path(ds["dataset_id"])}">{_e(ds["dataset_id"])}</a></td>'
            f"<td>{_e(ds.get('title') or '')}</td>"
            f"<td>{_e(', '.join(ds['organism_names']))}</td>"
            f"<td>{_e(_enrichment_cell(ds))}</td>"
            f'<td class="num">{_n(ds["n_runs"])}</td>'
            f'<td class="num">{_n(ds["n_psms_1pct"])}</td>'
            f'<td class="num">{_n(ds["n_protein_groups_1pct"])}</td>'
            f'<td class="num">{_n(ds["n_ptm_sites"])}</td>'
            f"<td>{_findings_cell(ds)}</td>"
            "</tr>"
        )
    tiles = "\n".join(
        f'<div class="tile"><div class="tile-label">{_e(m["label"])}</div>'
        f'<div class="tile-value" title="{_n(m["value"])}">{_compact(m["value"])}</div>'
        f'<div class="tile-note">{_e(m["note"])}</div></div>'
        for m in facts["merit"]
    )
    about_block = f'<section class="about">\n{about_html(about)}\n</section>' if about else ""
    body = f"""<header>
<h1>{_e(title)}</h1>
<p class="tagline">Public proteomics data, reanalysed with one pipeline, for questions about aging.</p>
</header>
<main>
{about_block}
<div class="tiles">
{tiles}
</div>
<p class="note">Figures of merit from catalog <code>{_e(meta['catalog_id'])}</code>. Hover a number for its exact value.</p>
<h2>This repository</h2>
<p class="lede">Search and quantification results for {_plural(len(facts['datasets']), 'public proteomics dataset')},
reanalysed with one pipeline and stored with the same schema, so they can be compared. The question
they serve is how organelle proteomes change with age.</p>
<p><strong>For AI agents:</strong> start at <a href="llms.txt"><code>llms.txt</code></a>. The same facts
as this page are in <a href="datasets.json"><code>datasets.json</code></a>.</p>
<h2>The corpus at a glance</h2>
{_corpus_table(facts["datasets"])}
<h2>Datasets</h2>
<p class="note">Counts are at 1% FDR, as the search engine reports them. "Findings" are what is
recorded against a dataset, by type; most are about what the deposit lacks (no SDRF, no design).
Read them before using it. Organism is that of the protein database searched.</p>
<div class="scroll"><table>
<thead><tr><th>Dataset</th><th>Title</th><th>Organism</th><th>Enrichment</th>
<th class="num">Runs</th><th class="num">PSMs</th><th class="num">Protein groups</th>
<th class="num">PTM sites</th><th>Findings</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table></div>
<h2>This catalog</h2>
<dl>
<dt>Catalog id</dt><dd><code>{_e(meta['catalog_id'])}</code></dd>
<dt>Built</dt><dd>{_e(meta['built_utc'])}</dd>
<dt>Built by</dt><dd>datarepo {_e(meta['builder_version'])}, catalog format {_e(meta['catalog_version'])}</dd>
<dt>Schema</dt><dd>{_e(meta['schema_version'])}</dd>
<dt>Instance</dt><dd>{_e(meta.get('instance') or 'not recorded')}</dd>
</dl>
</main>"""
    return _page(
        title, body, root="", meta=meta,
        jsonld=catalog_jsonld(facts, title=title, base_url=base_url),
    )


def _dataset_html(
    ds: dict[str, Any], meta: dict[str, Any], *, title: str, base_url: str | None,
    data_url: str | None,
) -> str:
    dataset_id = ds["dataset_id"]
    pride = _pride_url(dataset_id)
    counts = [
        ("PSMs at 1% FDR", ds["n_psms_1pct"]),
        ("Peptidoforms at 1% FDR", ds["n_peptidoforms_1pct"]),
        ("Protein groups at 1% FDR", ds["n_protein_groups_1pct"]),
        ("PTM sites", ds["n_ptm_sites"]),
        ("Quantitative values", ds["n_quant_values"]),
        ("PSMs, all (including decoys and sub-threshold)", ds["n_psms_all"]),
    ]
    count_rows = "\n".join(
        f'<tr><td>{_e(label)}</td><td class="num">{_n(value)}</td></tr>' for label, value in counts
    )
    for name, label in (("id_rate", "MS2 identification rate"),
                        ("contamination_psm_share", "Contaminant share of PSMs")):
        metric = ds["metrics"].get(name)
        if metric and metric["value"] is not None:
            count_rows += (
                f'\n<tr><td>{label} <span class="note">({_e(metric["definition_id"])})</span></td>'
                f'<td class="num">{metric["value"]:.1%}</td></tr>'
            )

    if ds["findings"]:
        findings = "\n".join(
            f'<div class="finding {_e(f["severity"])}"><span class="code">{_e(f["code"])}</span> '
            f'<span class="note">{_e(f["severity"])}</span><br>{_e(f["message"])}</div>'
            for f in ds["findings"]
        )
    else:
        findings = "<p>None recorded.</p>"

    if ds["modifications"]:
        mods = "\n".join(
            f"<tr><td>{_e(m['modification_name'])}</td><td>{_e(m['modification'] or '—')}</td>"
            f'<td class="num">{_n(m["n_sites"])}</td></tr>'
            for m in ds["modifications"]
        )
        mods = f"""<div class="scroll"><table>
<thead><tr><th>Search engine's name</th><th>UNIMOD</th><th class="num">Sites</th></tr></thead>
<tbody>
{mods}
</tbody></table></div>
<p class="note">Every modification with a site on a target protein, most frequent first. A dash in the UNIMOD
column means the modification has no UNIMOD term in the registry that searched it, not that it is
unknown. One chemistry can appear under two names (UniProt's and MetaMorpheus's); the catalog's
<code>ptm_sites_by_chemistry</code> view merges them.</p>"""
    else:
        mods = "<p>No PTM sites are recorded for this dataset.</p>"

    bundle = ds["bundle"]
    if bundle["reconciliation_ok"] is False:
        reconciliation = (
            "failed: " + _e(", ".join(bundle["reconciliation_failed"]))
            + ' <span class="note">(the bundle disagrees with the producer\'s own count here)</span>'
        )
    elif bundle["reconciliation_ok"]:
        reconciliation = "every check agreed with the producer's own counts"
    else:
        reconciliation = "not recorded"

    # The public pair when the producer records one (aging 069 55e): the private repo is where the
    # commit lives, and a reader cannot open it.
    commit = ds.get("pipeline_public_commit") or ds.get("pipeline_commit")
    repo = (ds.get("pipeline_public_repo") or ds.get("pipeline_repo") or "").removesuffix(".git")
    pipeline = (
        f'<a href="{_e(repo)}/tree/{_e(commit)}">{_e(commit[:12])}</a>'
        if commit and repo.startswith("https://github.com/")
        else _e(commit or "not recorded")
    )

    links = [f'<a href="{_e(pride)}">PRIDE record</a>'] if pride else []
    downloads = [
        f'<a href="{_e(url)}"><code>{t}.parquet</code></a>'
        for t in DOWNLOAD_TABLES
        if (url := _download_url(data_url, ds, t))
    ]
    download_html = (
        "<p>" + " · ".join(downloads) + "</p>"
        if downloads
        else "<p>The Parquet files for this dataset are not published yet.</p>"
    )
    licence = ds.get("licence")
    licence_html = (
        f'<a href="{_e(_licence_url(licence))}">{_e(licence)}</a>'
        if licence in LICENCE_URLS else _e(licence or "not recorded in the bundle")
    )

    body = f"""<header>
<p class="crumb"><a href="../index.html">{_e(title)}</a> / {_e(dataset_id)}</p>
<h1>{_e(ds.get('title') or dataset_id)}</h1>
<p>{_e(dataset_id)}{' · ' + ' · '.join(links) if links else ''}</p>
</header>
<main>
<div class="generated"><span class="label">Generated summary</span>
{_e(summary(ds))}
<br><span class="note">Written from catalog fields only (D17), with no model involved. It says nothing the tables below do not.</span></div>

<h2>Open findings</h2>
<p><strong>{_severity_words(ds)}</strong></p>
{findings}

<h2>What was found</h2>
<div class="scroll"><table><tbody>
{count_rows}
</tbody></table></div>

<h2>How it was measured</h2>
<dl>
<dt>Organism searched</dt><dd>{_e(_join(ds['organism_names']) or 'not recorded')} <span class="note">(the protein database's organism, not a statement about the samples)</span></dd>
<dt>Acquisition</dt><dd>{_e(ds.get('acquisition'))}</dd>
<dt>Quantification</dt><dd>{_e(ds.get('quant_method'))}</dd>
<dt>Labelling</dt><dd>{_e(ds.get('labelling'))}</dd>
<dt>Enrichment</dt><dd>{_e(_enrichment_cell(ds))}</dd>
<dt>Instrument vendor</dt><dd>{_e(ds.get('instrument_vendor') or 'not recorded')}</dd>
<dt>Runs / samples</dt><dd>{_n(ds['n_runs'])} / {_n(ds['n_samples'])}</dd>
<dt>Sample metadata</dt><dd>{_e(ds.get('sdrf_status') or 'not recorded')}</dd>
<dt>Search engine</dt><dd>{_e(ds.get('search_engine'))} {_e(ds.get('search_engine_version'))}</dd>
<dt>Protein database</dt><dd>{_e(ds.get('search_database') or 'not recorded')}</dd>
<dt>Pipeline commit</dt><dd>{pipeline}</dd>
</dl>

<h2>Modifications</h2>
{mods}

<h2>Data</h2>
{download_html}
<dl>
<dt>Bundle</dt><dd><code>{_e(bundle['bundle_id'])}</code>, written {_e(bundle['written_utc'])} by ingester {_e(bundle['ingester_version'])}</dd>
<dt>Reconciliation</dt><dd>{reconciliation}</dd>
<dt>Licence</dt><dd>{licence_html}</dd>
<dt>Credit</dt><dd>{_e(ds.get('credit') or 'not recorded in the bundle')}</dd>
</dl>
</main>"""
    return _page(
        f"{dataset_id}: {ds.get('title') or dataset_id}", body, root="../", meta=meta,
        jsonld=dataset_jsonld(ds, meta, base_url=base_url, data_url=data_url),
    )


# --- llms.txt ----------------------------------------------------------------------------------


def _llms_txt(
    facts: dict[str, Any], *, title: str, data_url: str | None, base_url: str | None = None
) -> str:
    meta = facts["meta"]
    lines = [
        f"# {title}",
        "",
        "> Search and quantification results for "
        f"{_plural(len(facts['datasets']), 'public proteomics dataset')}, reanalysed with one "
        "pipeline into one schema, for questions about how organelle proteomes change with age. "
        f"Every number here comes from catalog `{meta['catalog_id']}` (datarepo "
        f"{meta['builder_version']}, schema {meta['schema_version']}, built {meta['built_utc']}); "
        "cite that id with any number you reuse.",
        "",
        "Before you answer from this data:",
        "",
        "- Counts at 1% FDR come from the `*_1pct` views (`psms_1pct`, `peptidoforms_1pct`, "
        "`protein_groups_1pct`). The base tables also hold decoys and sub-threshold matches.",
        "- Each dataset page lists its open findings. A `low_id_rate` or `sdrf_skeleton` finding "
        "means the absence of a protein, or of sample metadata, is weak evidence.",
        "- An empty table means nothing was delivered. It does not mean the answer is zero or "
        "none. The MCP `describe` tool says which tables are empty.",
        "- Contaminant proteins (e.g. bovine albumin, porcine trypsin) are flagged and carry "
        "their own species. They are reagents, not evidence about the sample's organism. The "
        "flag is PER DATASET: human albumin is a target in a human search and a contaminant in "
        "a rodent one.",
        "- A dataset's organism is the organism of the protein database searched, not a "
        "statement about the samples.",
        "- `pep` values are not comparable across datasets: the model is retrained on every "
        "search. Compare counts at a threshold instead.",
        "- A protein group's accession list is kept in the search engine's order, and "
        "MetaMorpheus writes it alphabetically. The first accession is not a leading or razor "
        "protein, and nothing in this repository names one.",
        "",
        "## Datasets",
        "",
    ]
    for ds in facts["datasets"]:
        lines.append(
            f"- [{ds['dataset_id']}: {ds.get('title') or ds['dataset_id']}]"
            f"({_page_path(ds['dataset_id'])}): {summary(ds)}"
        )
    lines += [
        "",
        "## Access",
        "",
        "- [datasets.json](datasets.json): a small index, one entry per dataset, each naming "
        "its full JSON (`datasets/<id>.json`: every fact on its page, all findings and "
        "modifications).",
        "- [proteins/index.json](proteins/index.json): which datasets have accepted evidence for "
        "a protein. It lists every protein shard by accession prefix: fetch the shard whose "
        "prefix is the longest one the accession starts with. A gene symbol is in "
        "`genes/<first letter>.json`, which gives its accessions.",
        f"- [MCP server]({REPOSITORY}/blob/master/docs/mcp.md): `datarepo mcp --catalog "
        "<catalog.duckdb>` serves a catalog to an agent over stdio (describe, search, "
        "read-only SQL).",
        f"- [Schema]({REPOSITORY}/tree/master/docs/schema): every table and column, with its "
        "meaning.",
    ]
    if data_url:
        lines.append(
            "- [croissant.json](croissant.json): the Parquet files, described for ML loaders."
        )
    else:
        lines.append("- Bulk Parquet download: not published yet.")
    lines += [
        "",
        "## Optional",
        "",
        f"- [Source code]({REPOSITORY}): the ingester and catalog builder that made this data.",
        f"- [Limitations]({REPOSITORY}/blob/master/docs/limitations.md): what the repository "
        "does not yet hold.",
        "",
    ]
    return "\n".join(lines)


# --- JSON for programs ---------------------------------------------------------------------------

#: Said wherever a dataset's organism is shown, because it reads as a fact about the sample and it
#: is not one: PXD050351 is a human cell line, and an agent judged it "maybe a mouse sample" from the
#: title while `organisms` said only which proteome was searched (aging 070 57g).
ORGANISMS_ARE = (
    "`organisms` is the organism of the protein DATABASE the search used, not a statement about "
    "the samples. Sample annotation, where any exists, is in the catalog's `samples` and "
    "`sample_characteristics` tables."
)

DATASETS_ARE = (
    "One entry per dataset. Each names its page and its full JSON (`json`), which holds every "
    "fact on the page including all findings and modifications. `findings_by_severity` and "
    "`finding_codes` say what is recorded against a dataset; whether that makes it usable for a "
    "question is the question's call, not this file's. " + ORGANISMS_ARE
)

#: No protein shard is written larger than this. A fixed two-character prefix put 3.6 MB in
#: `Q9.json` on aging's 34 datasets, which is the truncation 55a was about in a new file; so a shard
#: over the cap is split by lengthening its prefix, and the index names every shard.
MAX_SHARD_BYTES = 150_000


def _json(doc: Any) -> str:
    return json.dumps(doc, indent=1, ensure_ascii=False, default=str) + "\n"


def _json_path(dataset_id: str) -> str:
    return f"datasets/{quote(dataset_id)}.json"


def _links(dataset_id: str, base_url: str | None) -> dict[str, str | None]:
    """Relative paths always; absolute URLs as well when the site's address is known (55b)."""
    page, doc = _page_path(dataset_id), _json_path(dataset_id)
    return {
        "page": page, "json": doc,
        "page_url": _absolute(base_url, page), "json_url": _absolute(base_url, doc),
    }


def _index_entry(ds: dict[str, Any], base_url: str | None) -> dict[str, Any]:
    keys = (
        "dataset_id", "title", "organisms", "organism_names", "acquisition", "quant_method",
        "labelling", "enrichment", "enrichment_mixed", "n_runs", "n_samples", "n_psms_1pct",
        "n_peptidoforms_1pct", "n_protein_groups_1pct", "n_ptm_sites", "sdrf_status",
        "findings_by_severity", "finding_codes",
    )
    return {**{k: ds.get(k) for k in keys}, "summary": summary(ds), **_links(ds["dataset_id"], base_url)}


def _json_compact(doc: Any) -> str:
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False, default=str) + "\n"


def _shards(entries: dict[str, Any], length: int = 2) -> dict[str, dict[str, Any]]:
    """`{prefix: entries}` with every shard under `MAX_SHARD_BYTES`, prefixes as short as allows."""
    groups: dict[str, dict[str, Any]] = {}
    for accession, entry in entries.items():
        groups.setdefault(accession[:length], {})[accession] = entry
    out: dict[str, dict[str, Any]] = {}
    for prefix, group in groups.items():
        too_big = len(_json_compact(group).encode("utf-8")) > MAX_SHARD_BYTES
        if too_big and any(len(a) > length for a in group):
            out.update(_shards(group, length + 1))
        else:
            out[prefix] = group
    return out


def _protein_files(proteins: dict[str, dict[str, Any]], catalog: dict[str, Any]) -> dict[str, str]:
    """`proteins/<shard>.json`, `genes/<letter>.json` and `proteins/index.json` (DATAREPO-56)."""
    shards = _shards(proteins)
    genes: dict[str, dict[str, list[str]]] = {}
    for accession, entry in proteins.items():
        gene = entry.get("gene")
        if gene:
            letter = gene[0].upper() if gene[0].isalnum() else "_"
            genes.setdefault(letter, {}).setdefault(gene.upper(), []).append(accession)
    about = (
        "Accessions with evidence that passed acceptance (an accepted protein group OR an "
        "accepted peptidoform) in at least one dataset; decoys excluded, contaminants kept and "
        "labelled PER DATASET, because the label is: human albumin is a target in a human search "
        "and a contaminant in a rodent one. `best_protein_group_q_value` is NULL where only a "
        "peptidoform passed, so a listed dataset is not 'identified at 1% protein FDR'. An "
        "accession absent from its shard had no accepted evidence anywhere in this catalog."
    )
    paths = {key: f"proteins/{quote(key, safe='')}.json" for key in shards}
    files = {
        paths[key]: _json_compact({"catalog": catalog, "proteins_are": about, "proteins": entries})
        for key, entries in sorted(shards.items())
    }
    files.update({
        f"genes/{key}.json": _json_compact({
            "catalog": catalog,
            "genes_are": "Gene symbol (upper-cased) -> accessions, from the producer's display "
                         "symbol. Look each accession up in its proteins/ shard.",
            "genes": dict(sorted(entries.items())),
        })
        for key, entries in sorted(genes.items())
    })
    files["proteins/index.json"] = _json({
        "catalog": catalog,
        "how_to_look_up": (
            "Find the LONGEST key of `protein_shards` that the accession starts with, and fetch "
            "that shard's `file` (P02768 -> the key 'P02' or 'P0', whichever is listed). By gene "
            "symbol, fetch genes/<first letter, upper-cased>.json first. " + about
        ),
        "protein_shards": {
            k: {"file": paths[k], "n": len(v)} for k, v in sorted(shards.items())
        },
        "gene_shards": {k: len(v) for k, v in sorted(genes.items())},
    })
    return files


# --- writing -----------------------------------------------------------------------------------


def _clear_previous(out: Path) -> None:
    """Delete what the last generation wrote, and refuse a directory that is not a site of ours."""
    if not out.exists():
        return
    if not out.is_dir():
        raise CatalogError(f"{out} exists and is not a directory")
    marker = out / SITE_MARKER
    if not marker.is_file():
        if any(out.iterdir()):
            raise CatalogError(
                f"{out} is not empty and was not written by `datarepo site`; choose an empty "
                "directory. The generator deletes what it wrote last time, so it will not adopt "
                "a directory it cannot account for."
            )
        return
    try:
        previous = json.loads(marker.read_text(encoding="utf-8")).get("files", [])
    except ValueError as exc:
        raise CatalogError(f"{marker} is unreadable: {exc}") from exc
    for name in previous:
        path = (out / name).resolve()
        if out.resolve() in path.parents and path.is_file():
            path.unlink()
    for folder in ("datasets", "proteins", "genes"):
        path = out / folder
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def build_site(
    catalog: Path,
    out: Path,
    *,
    title: str | None = None,
    base_url: str | None = None,
    data_url: str | None = None,
    notice: str | None = None,
    about: str | None = None,
) -> SiteResult:
    """Write the static site for one catalog into `out`.

    Args:
        catalog: a catalog written by `datarepo build`.
        out: an empty directory, or one a previous `build_site` wrote.
        title: the site's name. Defaults to one built from the catalog's instance.
        base_url: where the site will be served. Needed for absolute URLs in the structured data,
            `sitemap.xml` and `robots.txt`; without it links are relative and those are skipped.
        data_url: where the bundle store is served, as `<data_url>/<dataset>/<bundle>/<table>.parquet`.
            Without it no download links are written and `croissant.json` is skipped.
        about: Markdown for the front page's overview: what the project behind this instance is
            and why it exists. It is the instance owner's text, not dataRepo's, so it comes in
            from outside rather than being written here.
        notice: a banner shown at the top of every page and of `llms.txt`, e.g. that the site is a
            preview whose data will be regenerated. It goes where no reader, human or agent, can
            miss it, because a caveat on a page nobody opens is not a caveat.

    Raises:
        CatalogError: no catalog at `catalog`, or `out` holds files this generator did not write.
    """
    facts = read_site_facts(catalog)
    meta = facts["meta"]
    title = title or (
        f"{meta['instance']} proteomics repository" if meta.get("instance")
        else "Reanalysed proteomics repository"
    )
    out = Path(out)
    _clear_previous(out)
    (out / "datasets").mkdir(parents=True, exist_ok=True)

    catalog_block = {
        **{k: meta[k] for k in (
            "catalog_id", "catalog_version", "schema_version", "builder_version", "built_utc",
            "instance")},
        "base_url": base_url,
    }
    files: dict[str, str] = {
        "style.css": STYLE,
        "index.html": _index_html(facts, title=title, base_url=base_url, about=about),
        "llms.txt": _llms_txt(facts, title=title, data_url=data_url, base_url=base_url),
        # An INDEX, one small entry per dataset. The whole thing in one file was cut off by agent
        # fetch tools after about 19 of 26 entries, and the agent could not tell (aging 069 55a).
        "datasets.json": _json({
            "catalog": catalog_block,
            "datasets_are": DATASETS_ARE,
            "datasets": [_index_entry(ds, base_url) for ds in facts["datasets"]],
        }),
    }
    for ds in facts["datasets"]:
        files[_page_path(ds["dataset_id"])] = _dataset_html(
            ds, meta, title=title, base_url=base_url, data_url=data_url
        )
        files[_json_path(ds["dataset_id"])] = _json({
            "catalog": catalog_block,
            "dataset": {
                **{k: v for k, v in ds.items() if k != "bundle"},
                "bundle": {k: v for k, v in ds["bundle"].items() if k != "path"},
                "summary": summary(ds),
                **_links(ds["dataset_id"], base_url),
            },
            "organisms_are": ORGANISMS_ARE,
        })
    files.update(_protein_files(facts["proteins"], catalog_block))

    result = SiteResult(out=out, catalog_id=meta["catalog_id"], files=[])
    if data_url:
        doc, unreadable = croissant(facts, title=title, base_url=base_url, data_url=data_url)
        files["croissant.json"] = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
        if unreadable:
            result.warnings.append(
                f"croissant.json leaves out {len(unreadable)} file(s) it could not read from the "
                f"store, e.g. {unreadable[0]}; a file is described from its own bytes or not at all"
            )
    else:
        result.skipped["croissant.json"] = (
            "no --data-url: a Croissant file describes downloadable files, and none are published"
        )
    if base_url:
        urls = ["index.html", "llms.txt", *(_page_path(ds["dataset_id"]) for ds in facts["datasets"])]
        files["sitemap.xml"] = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            + "".join(f"<url><loc>{_e(_absolute(base_url, u))}</loc></url>\n" for u in urls)
            + "</urlset>\n"
        )
        files["robots.txt"] = f"User-agent: *\nAllow: /\nSitemap: {_absolute(base_url, 'sitemap.xml')}\n"
    else:
        for name in ("sitemap.xml", "robots.txt"):
            result.skipped[name] = "no --base-url: both need the site's absolute address"

    missing = sorted(ds["dataset_id"] for ds in facts["datasets"] if not ds.get("licence"))
    if missing:
        result.warnings.append(
            f"no licence readable from the bundle for {', '.join(missing)}; those pages state "
            "none rather than assume one (is the store at the path the catalog recorded?)"
        )

    if notice:
        banner = f'<div class="notice" role="note">{_e(notice)}</div>'
        for name in files:
            if name.endswith(".html"):
                files[name] = files[name].replace("<body>\n", f"<body>\n{banner}\n", 1)
        head, sep, rest = files["llms.txt"].partition("\n\nBefore you answer")
        files["llms.txt"] = f"{head}\n\n**Notice:** {notice}{sep}{rest}"

    for name, text in files.items():
        path = out / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n": the output is published from any OS and must be byte-identical across them.
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    result.files = sorted(files)
    with open(out / SITE_MARKER, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(
            json.dumps({"catalog_id": meta["catalog_id"], "generator": f"datarepo {__version__}",
                        "files": result.files}, indent=1) + "\n"
        )
    return result


__all__ = ["SITE_MARKER", "SiteResult", "build_site", "read_site_facts", "summary"]
