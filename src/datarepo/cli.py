"""The `datarepo` command line.

    datarepo doctor                              is this machine able to ingest?
    datarepo manifest <manifest.yaml>            what does the producing instance offer?
    datarepo ingest <manifest.yaml> <PXD...>     build the bundle(s)
    datarepo inspect <bundle-dir>                what is in a bundle, and did it reconcile?
    datarepo build <manifest.yaml> <PXD...>      load bundles into one DuckDB catalog
    datarepo catalog <catalog.duckdb>            what is in a catalog, and did it check out?
    datarepo query <catalog.duckdb> <sql>        run one read-only query against a catalog

Exit codes are meant to be usable from the pipeline that calls this: 0 success, 1 a refusal or
failure the operator must act on, 2 bad usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from ._tables import SCHEMA_VERSION
from .bundle import BUNDLE_MANIFEST
from .catalog import (
    build_catalog,
    describe_catalog,
    format_rows,
    run_query,
    select_bundles,
)
from .errors import CatalogError, DataRepoError, DatasetExcluded
from .ingest import ingest_dataset
from .manifest import load_manifest


def _print_result(result, verbose: bool) -> None:
    print(f"  bundle   {result.bundle_path}")
    if result.skipped:
        print("  unchanged: inputs and ingester match the bundle already written; --overwrite to rebuild")
    counts = ", ".join(f"{k} {v:,}" for k, v in result.row_counts.items())
    print(f"  tables   {counts}")
    for check in result.checks:
        if not check["ok"]:
            print(
                f"  MISMATCH {check['name']}: bundle {check['observed']:g} vs producer "
                f"{check['expected']:g} ({check['source']})"
            )
        elif verbose and check["observed"] is not None:
            print(f"  ok       {check['name']}: {check['observed']:g}")
    if result.unresolved_modifications:
        names = ", ".join(sorted(result.unresolved_modifications))
        print(f"  WARN     {len(result.unresolved_modifications)} unresolved modification(s): {names}")
    if result.unmatched_runs:
        print(f"  WARN     run names with no deposited file: {', '.join(sorted(result.unmatched_runs))}")
    warnings = [f for f in result.findings if f["severity"] in ("warning", "error")]
    if warnings:
        print(f"  findings {len(warnings)} open warning(s): {', '.join(sorted({f['code'] for f in warnings}))}")


def cmd_ingest(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    accessions = args.accession or [e.accession for e in manifest.ingestable()]
    if not accessions:
        print(f"{manifest.path}: no dataset has status 'include'", file=sys.stderr)
        return 1

    failures = 0
    for accession in accessions:
        print(f"{accession}")
        try:
            entry = manifest.dataset(accession)
            result = ingest_dataset(
                manifest,
                entry,
                store=Path(args.store) if args.store else None,
                mm_settings=Path(args.mm_settings) if args.mm_settings else None,
                overwrite=args.overwrite,
            )
        except DatasetExcluded as exc:
            print(f"  refused  {exc}")
            failures += 1
            continue
        except DataRepoError as exc:
            print(f"  failed   {exc}", file=sys.stderr)
            failures += 1
            continue
        _print_result(result, args.verbose)
    return 1 if failures else 0


def cmd_manifest(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    print(f"instance   {manifest.instance} (manifest v{manifest.manifest_version})")
    print(f"work root  {manifest.work_root}")
    print(f"store      {manifest.store}")
    if manifest.licence:
        print(f"licence    {manifest.licence} - {manifest.credit or 'no credit line'}")
    print()
    for entry in manifest.datasets.values():
        mark = "+" if entry.ingestable else "-"
        axes = " ".join(
            v for v in (entry.organism, entry.acquisition, entry.quant_method) if v
        )
        print(f" {mark} {entry.accession:<12} {entry.status:<8} {axes}")
        if entry.run:
            print(f"     run    {entry.run}  ({entry.files or '?'} files, MetaMorpheus {entry.metamorpheus or '?'})")
        if entry.flags:
            print(f"     flags  {', '.join(entry.flags)}")
        if entry.reason:
            print(f"     reason {' '.join(entry.reason.split())}")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    path = Path(args.bundle)
    manifest_path = path / BUNDLE_MANIFEST if path.is_dir() else path
    if not manifest_path.is_file():
        print(f"no {BUNDLE_MANIFEST} at {manifest_path}", file=sys.stderr)
        return 1
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps(doc, indent=2))
        return 0
    print(f"{doc['dataset_id']}  bundle {doc['bundle_id']}")
    print(f"  written  {doc['written_utc']} by {doc['ingester']['name']} {doc['ingester']['version']}")
    print(f"  schema   {doc['schema_version']}  qpx {doc['qpx_version']}")
    for table, rows in doc.get("tables", {}).items():
        print(f"    {table:<24} {rows:>10,}")
    mismatches = [c for c in doc.get("reconciliation", []) if not c["ok"]]
    print(f"  checks   {len(doc.get('reconciliation', []))} run, {len(mismatches)} mismatched")
    for check in mismatches:
        print(f"    MISMATCH {check['name']}: {check['observed']:g} vs {check['expected']:g}")
    return 0


def _parse_pins(values: list[str] | None) -> dict[str, str]:
    """`--bundle PXD036557=6fea2187` pairs, which is how a release pins its exact bundles."""
    pins: dict[str, str] = {}
    for value in values or []:
        accession, _, bundle_id = value.partition("=")
        if not bundle_id:
            raise CatalogError(f"--bundle wants <accession>=<bundle id>, got {value!r}")
        pins[accession] = bundle_id
    return pins


def cmd_build(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    accessions = args.accession or [e.accession for e in manifest.ingestable()]
    if not accessions:
        print(f"{manifest.path}: no dataset has status 'include'", file=sys.stderr)
        return 1

    store = Path(args.store) if args.store else manifest.store
    out = Path(args.out) if args.out else store.parent / "catalog.duckdb"

    try:
        bundles = select_bundles(
            manifest,
            accessions,
            store=store,
            pins=_parse_pins(args.bundle),
            latest=args.latest,
        )
    except DatasetExcluded as exc:
        print(f"refused  {exc}", file=sys.stderr)
        return 1

    result = build_catalog(
        bundles,
        out,
        overwrite=args.overwrite,
        instance=manifest.instance,
        notes={"manifest": str(manifest.path), "release": args.release} if args.release else
              {"manifest": str(manifest.path)},
    )

    print(f"catalog  {result.path}")
    print(f"  id       {result.catalog_id}")
    if result.skipped:
        print("  unchanged: these bundles are already the catalog's contents; --overwrite to rebuild")
        return 0
    for ref in result.bundles:
        print(f"  dataset  {ref.dataset_id:<12} bundle {ref.bundle_id}")
    counts = ", ".join(f"{k} {v:,}" for k, v in sorted(result.row_counts.items()))
    print(f"  tables   {counts}")
    print(f"  indexes  {result.indexes}")
    print(f"  checks   {len(result.checks)} run, all passed")
    if args.verbose:
        for check in result.checks:
            print(f"    ok     {check['kind']:<10} {check['name']}")
    return 0


def cmd_catalog(args: argparse.Namespace) -> int:
    doc = describe_catalog(Path(args.catalog))
    if args.json:
        print(json.dumps(doc, indent=2, default=str))
        return 0
    meta = doc["meta"]
    print(f"{doc['path']}  catalog {meta.get('catalog_id')}")
    print(
        f"  built    {meta.get('built_utc')} by {meta.get('builder')} "
        f"{meta.get('builder_version')} (catalog v{meta.get('catalog_version')})"
    )
    print(f"  schema   {meta.get('schema_version')}  qpx {meta.get('qpx_version')}")
    print(f"  instance {meta.get('instance')}")
    for ref in doc["bundles"]:
        mark = " " if ref["reconciliation_ok"] else "!"
        print(f"  {mark} {ref['dataset_id']:<12} bundle {ref['bundle_id']}  {ref['written_utc']}")
        for name in ref["reconciliation_failed"] or []:
            print(f"      bundle reconciliation mismatch carried through: {name}")
    for row in doc["tables"]:
        if row["rows"]:
            kind = "" if row["kind"] == "bundle" else row["kind"]
            print(f"    {row['table_name']:<24} {row['rows']:>10,} {kind}")
    failed = [c for c in doc["checks"] if not c["ok"]]
    print(f"  checks   {len(doc['checks'])} run, {len(failed)} failed")
    for check in failed:
        print(f"    FAILED {check['name']}: {check['observed']} vs {check['expected']}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    columns, rows = run_query(Path(args.catalog), args.sql, limit=args.limit or None)
    print(format_rows(columns, rows, args.format))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    print(f"datarepo {__version__}  schema {SCHEMA_VERSION}")
    ok = True
    try:
        import pyarrow  # noqa: PLC0415

        print(f"  pyarrow          {pyarrow.__version__}")
    except ImportError:  # pragma: no cover
        print("  pyarrow          MISSING")
        ok = False
    try:
        import duckdb  # noqa: PLC0415

        print(f"  duckdb           {duckdb.__version__}")
    except ImportError:  # pragma: no cover
        print("  duckdb           MISSING (needed by `datarepo build`, not by `ingest`)")
    try:
        from .readers import require_pymzlib  # noqa: PLC0415

        require_pymzlib()
        import pymzlib  # noqa: PLC0415

        print(f"  pymzlib          {pymzlib.__version__}")
        print(f"  mzLib bridge     {pymzlib.bridge_path()}")
    except Exception as exc:  # noqa: BLE001 - the message is the point
        print(f"  pymzlib          UNAVAILABLE: {exc}")
        ok = False
    print("ready" if ok else "not ready to ingest")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="datarepo", description=__doc__.split("\n")[0])
    parser.add_argument("--version", action="version", version=f"datarepo {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="build a Parquet bundle for one or more datasets")
    p.add_argument("manifest", help="the producing instance's manifest.yaml")
    p.add_argument("accession", nargs="*", help="datasets to ingest; default is every 'include'")
    p.add_argument("--store", help="where to write bundles; default is the manifest's store")
    p.add_argument("--mm-settings", help="MetaMorpheus install to read modification definitions from")
    p.add_argument("--overwrite", action="store_true", help="rebuild a bundle that already exists")
    p.add_argument("-v", "--verbose", action="store_true", help="show every reconciliation check")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("manifest", help="show what the producing instance offers")
    p.add_argument("manifest")
    p.set_defaults(func=cmd_manifest)

    p = sub.add_parser("inspect", help="summarise a written bundle")
    p.add_argument("bundle", help="bundle directory or its bundle.json")
    p.add_argument("--json", action="store_true", help="print the manifest verbatim")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("build", help="load bundles into one DuckDB catalog")
    p.add_argument("manifest", help="the producing instance's manifest.yaml")
    p.add_argument("accession", nargs="*", help="datasets to load; default is every 'include'")
    p.add_argument("--store", help="where bundles live; default is the manifest's store")
    p.add_argument("--out", help="catalog file to write; default is <store>/../catalog.duckdb")
    p.add_argument(
        "--bundle",
        action="append",
        metavar="PXD=ID",
        help="pin a dataset to one bundle id; repeatable",
    )
    p.add_argument(
        "--latest",
        action="store_true",
        help="when a dataset has several bundles, take the newest instead of refusing",
    )
    p.add_argument("--release", help="release version this catalog is built for, recorded in it")
    p.add_argument("--overwrite", action="store_true", help="rebuild a catalog that is current")
    p.add_argument("-v", "--verbose", action="store_true", help="list every check that ran")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("catalog", help="summarise a built catalog")
    p.add_argument("catalog", help="the catalog .duckdb file")
    p.add_argument("--json", action="store_true", help="print the catalog's own tables verbatim")
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser("query", help="run one read-only SQL query against a catalog")
    p.add_argument("catalog", help="the catalog .duckdb file")
    p.add_argument("sql", help="the statement to run")
    p.add_argument("--format", choices=("table", "tsv", "json"), default="table")
    p.add_argument("--limit", type=int, default=50, help="row cap; 0 for no cap")
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("doctor", help="check this machine can ingest")
    p.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except DataRepoError as exc:
        print(f"datarepo: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
