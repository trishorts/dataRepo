"""The `datarepo` command line.

    datarepo doctor                              is this machine able to ingest?
    datarepo manifest <manifest.yaml>            what does the producing instance offer?
    datarepo ingest <manifest.yaml> <PXD...>     build the bundle(s)
    datarepo study <study.yaml>                  write a study layer's delivered rows as a bundle
    datarepo inspect <bundle-dir>                what is in a bundle, and did it reconcile?
    datarepo build <manifest.yaml> <PXD...>      load bundles into one DuckDB catalog
    datarepo catalog <catalog.duckdb>            what is in a catalog, and did it check out?
    datarepo query <catalog.duckdb> <sql>        run one read-only query against a catalog
    datarepo mcp --catalog <catalog.duckdb>      serve one catalog to an agent over stdio

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
    available_study_layers,
    build_catalog,
    describe_catalog,
    format_rows,
    run_query,
    select_bundles,
    select_study_bundles,
)
from .errors import CatalogError, DataRepoError, DatasetExcluded
from .ingest import ingest_dataset
from .manifest import load_manifest
from .study import STUDY_BUNDLE_MANIFEST, load_study_manifest, write_study_bundle


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


def cmd_study(args: argparse.Namespace) -> int:
    manifest = load_study_manifest(args.manifest)
    result = write_study_bundle(
        manifest,
        store=Path(args.store) if args.store else None,
        overwrite=args.overwrite,
    )
    print(f"{result.layer}  (study layer, delivery {manifest.delivery or 'unlabelled'})")
    print(f"  bundle   {result.bundle_path}")
    if result.skipped:
        print("  unchanged: these files are already delivered; --overwrite to rewrite")
    counts = ", ".join(f"{k} {v:,}" for k, v in sorted(result.row_counts.items()))
    print(f"  tables   {counts or '(none)'}")
    empty = [t for t, n in sorted(result.row_counts.items()) if n == 0]
    if empty:
        print(f"  note     delivered with no rows: {', '.join(empty)}")
    print(f"  load it  datarepo build <manifest.yaml> --study {result.layer}={result.bundle_id}")
    return 0


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
    if path.is_dir():
        # A study bundle is a different object with a different manifest, and an operator pointing
        # `inspect` at a directory should not have to know which kind they are holding.
        manifest_path = path / BUNDLE_MANIFEST
        if not manifest_path.is_file() and (path / STUDY_BUNDLE_MANIFEST).is_file():
            manifest_path = path / STUDY_BUNDLE_MANIFEST
    else:
        manifest_path = path
    if not manifest_path.is_file():
        print(f"no {BUNDLE_MANIFEST} or {STUDY_BUNDLE_MANIFEST} at {path}", file=sys.stderr)
        return 1
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps(doc, indent=2))
        return 0
    if doc.get("kind") == "study":
        print(f"{doc['layer']}  study bundle {doc['bundle_id']}  (layer {doc['layer_version']})")
        print(
            f"  written  {doc['written_utc']} by {doc['ingester']['name']} "
            f"{doc['ingester']['version']} (study path {doc['ingester']['study_ingest_path']})"
        )
        print(f"  schema   {doc['schema_version']}")
        print(f"  from     {doc.get('instance') or 'unknown instance'}, "
              f"delivery {doc.get('delivery') or 'unlabelled'}")
        for table, rows in doc.get("tables", {}).items():
            print(f"    {table:<24} {rows:>10,}")
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


def _parse_pins(values: list[str] | None, flag: str = "--bundle", what: str = "accession") -> dict[str, str]:
    """`--bundle PXD036557=6fea2187` pairs, which is how a release pins its exact bundles."""
    pins: dict[str, str] = {}
    for value in values or []:
        accession, _, bundle_id = value.partition("=")
        if not bundle_id:
            raise CatalogError(f"{flag} wants <{what}>=<bundle id>, got {value!r}")
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
            release=args.release,
        )
    except DatasetExcluded as exc:
        print(f"refused  {exc}", file=sys.stderr)
        return 1

    study_bundles = select_study_bundles(
        store,
        pins=_parse_pins(args.study, flag="--study", what="layer"),
        latest=args.study_latest or (),
        release=args.release,
    )

    notes = {"manifest": str(manifest.path)}
    if args.release:
        notes["release"] = args.release
    if study_bundles:
        notes["study"] = {ref.layer: ref.bundle_id for ref in study_bundles}

    result = build_catalog(
        bundles,
        out,
        overwrite=args.overwrite,
        instance=manifest.instance,
        notes=notes,
        study_bundles=study_bundles,
    )

    print(f"catalog  {result.path}")
    print(f"  id       {result.catalog_id}")
    if result.skipped:
        print("  unchanged: these bundles are already the catalog's contents; --overwrite to rebuild")
        return 0
    for ref in result.bundles:
        print(f"  dataset  {ref.dataset_id:<12} bundle {ref.bundle_id}")
    for ref in result.study_bundles:
        print(f"  study    {ref.layer:<12} bundle {ref.bundle_id}  ({ref.layer_version})")
    if not result.study_bundles:
        # Study bundles are opt-in, so a store holding one and a build not asking for it is a
        # legitimate choice -- but a silent one, and this is the only place to make it visible.
        on_offer = available_study_layers(store)
        for layer, refs in on_offer.items():
            print(
                f"  note     study layer '{layer}' has {len(refs)} delivery on offer and none was "
                f"loaded; --study {layer}={refs[-1].bundle_id} to include it"
            )
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
    for ref in doc.get("study_bundles") or []:
        print(
            f"  study    {ref['layer']:<12} bundle {ref['bundle_id']}  "
            f"layer {ref['layer_version']}  {ref['written_utc']}"
        )
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


def cmd_mcp(args: argparse.Namespace) -> int:
    from .mcp import TOOL_SPECS, CatalogServer, install, installed_entries, serve  # noqa: PLC0415

    config = Path(args.config) if args.config else None
    if args.list:
        entries = installed_entries(config)
        if not entries:
            print("no datarepo MCP server is registered")
            return 0
        for name, entry in sorted(entries.items()):
            print(f"{name}  {entry.get('command')} {' '.join(entry.get('args') or [])}")
        return 0

    if not args.catalog:
        print("datarepo mcp: --catalog is required (D13: one catalog, by explicit path)", file=sys.stderr)
        return 2

    if args.install:
        result = install(args.catalog, name=args.name, config=config, force=args.force)
        print(f"{result['action']}  {result['name']} in {result['config']}")
        print(f"  command  {result['entry']['command']} {' '.join(result['entry']['args'])}")
        print(f"  tools    {', '.join(spec['name'] for spec in TOOL_SPECS)}")
        if result["action"] != "unchanged":
            print("  restart Claude Code to pick it up")
        return 0

    if args.check:
        # Open the catalog and answer one question through the tools, without the SDK. This is what
        # tells an operator the failure is the SDK or the config rather than the catalog.
        with CatalogServer(args.catalog) as server:
            overview = server.describe()
            print(f"catalog  {server.box.path}")
            print(f"  id       {server.identity.catalog_id}")
            print(f"  built    {server.identity.built_utc} by {server.identity.builder} "
                  f"{server.identity.builder_version}")
            for row in overview["datasets"]:
                print(f"  dataset  {row['dataset_id']:<12} {row['n_psms_1pct']:>9,} PSMs at 1%")
            print(f"  tools    {', '.join(spec['name'] for spec in TOOL_SPECS)}")
            print(f"  empty    {len(overview['tables_empty'])} table(s) present with no rows")
        return 0

    serve(args.catalog, name=args.name)
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

    # The MCP half. Neither line can make `doctor` fail: ingest does not need the SDK, and a
    # machine that ingests but does not serve is a normal machine (D8 -- aging hosts, we ship).
    try:
        import mcp  # noqa: PLC0415

        print(f"  mcp SDK          {getattr(mcp, '__version__', 'installed')}")
    except ImportError:
        print("  mcp SDK          not installed (`pip install 'datarepo[mcp]'` to serve a catalog)")
    from .mcp import claude_config_path, installed_entries  # noqa: PLC0415

    entries = installed_entries()
    if entries:
        for name, entry in sorted(entries.items()):
            args_ = entry.get("args") or []
            catalog = args_[args_.index("--catalog") + 1] if "--catalog" in args_ else "?"
            served = Path(catalog).is_file()
            print(f"  mcp registered   {name} -> {catalog}{'' if served else '  (MISSING)'}")
    else:
        print(f"  mcp registered   no (`datarepo mcp --catalog <path> --install`)")
        print(f"                   config would be {claude_config_path()}")

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

    p = sub.add_parser("study", help="write a study layer's delivered rows as a study bundle")
    p.add_argument("manifest", help="the study delivery's study.yaml")
    p.add_argument("--store", help="where to write the bundle; default is the manifest's store")
    p.add_argument("--overwrite", action="store_true", help="rewrite a delivery already written")
    p.set_defaults(func=cmd_study)

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
    p.add_argument(
        "--study",
        action="append",
        metavar="LAYER=ID",
        help="load a study layer's delivery, pinned to one bundle id; repeatable",
    )
    p.add_argument(
        "--study-latest",
        action="append",
        metavar="LAYER",
        help="load a study layer's newest delivery; repeatable, refused with --release",
    )
    p.add_argument(
        "--release",
        help="release version this catalog is for; requires every dataset pinned with --bundle",
    )
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

    p = sub.add_parser("mcp", help="serve one catalog to an agent over stdio (MCP)")
    p.add_argument("--catalog", help="the catalog .duckdb file to serve; never auto-discovered")
    p.add_argument("--install", action="store_true", help="register it with Claude Code and exit")
    p.add_argument("--list", action="store_true", help="show the datarepo servers already registered")
    p.add_argument("--check", action="store_true", help="open the catalog and report, without serving")
    p.add_argument("--name", default="datarepo", help="server name, for registering several catalogs")
    p.add_argument("--config", help="MCP config to write; default is the Claude Code user config")
    p.add_argument("--force", action="store_true", help="repoint an entry of that name at this catalog")
    p.set_defaults(func=cmd_mcp)

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
