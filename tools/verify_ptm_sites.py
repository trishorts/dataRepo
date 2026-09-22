#!/usr/bin/env python
"""Check every `ptm_sites` row in one or more bundles against the protein database that was searched.

For each site: is the residue it names really at its position in that protein's sequence? This is
the external check aging ran to find DATAREPO-32 (their 043): 1,452 rows naming the wrong residue
and 297 positions beyond the protein's length, all from pairing MetaMorpheus's de-duplicated span
column with its accession column. Since 0.15.0 every ingest runs the same check on itself and
records it in `bundle.json` (`protein_databases.site_residue_check`); this tool re-runs it from the
written Parquet, independently of the ingest's own bookkeeping, so a consumer can verify a bundle
they did not build.

    python tools/verify_ptm_sites.py F:/aging_data/repo/store                  # latest bundle per dataset
    python tools/verify_ptm_sites.py F:/aging_data/repo/store PXD036557 PXD027318
    python tools/verify_ptm_sites.py path/to/store/PXD036557/<bundle_id>       # one bundle
    python tools/verify_ptm_sites.py <store> --db human.xml --db contaminants.xml   # a pre-0.15.0 bundle

The databases are the ones the bundle recorded, found at the paths it recorded and checked against
the sha256 it recorded. A bundle whose databases are not on this machine is reported, not guessed
at. Exit status is 1 if any checked site names the wrong residue or lies beyond its protein.

Target sites only by default, since a contaminant accession can collide with a target one; pass
`--all` to include contaminants.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from datarepo.bundle import sha256_file  # noqa: E402
from datarepo.sources import protein_db  # noqa: E402
from datarepo.sources.identifications import verify_site_residues  # noqa: E402


def _bundles(target: Path, datasets: list[str]) -> list[Path]:
    if (target / "bundle.json").is_file():
        return [target]
    out = []
    for dataset_dir in sorted(p for p in target.iterdir() if p.is_dir() and not p.name.startswith("_")):
        if datasets and dataset_dir.name not in datasets:
            continue
        candidates = sorted(dataset_dir.glob("*/bundle.json"), key=lambda p: p.stat().st_mtime)
        if candidates:
            out.append(candidates[-1].parent)
    return out


_cache: dict[tuple[str, ...], protein_db.ProteinSequences] = {}


def _sequences(recorded: list[dict]) -> tuple[protein_db.ProteinSequences | None, str | None]:
    key = tuple(sorted(d["sha256"] for d in recorded))
    if key in _cache:
        return _cache[key], None
    seqs = protein_db.ProteinSequences()
    for db in recorded:
        path = Path(db["path"])
        if not path.is_file():
            return None, f"database not on this machine: {path}"
        if sha256_file(path) != db["sha256"]:
            return None, f"database changed since ingest: {path}"
        protein_db.read_database(path, seqs)
    _cache[key] = seqs
    return seqs, None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("target", type=Path, help="a store directory or one bundle directory")
    parser.add_argument("datasets", nargs="*", help="limit a store to these dataset ids")
    parser.add_argument("--all", action="store_true", help="include contaminant sites")
    parser.add_argument("--db", type=Path, action="append", default=[],
                        help="check against this database instead of the recorded ones (repeatable); needed for a bundle built before 0.15.0, which recorded none")
    args = parser.parse_args(argv)

    failed = False
    for bundle in _bundles(args.target, args.datasets):
        manifest = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
        label = f"{manifest['dataset_id']} {manifest['bundle_id']} (ingester {manifest.get('ingester', {}).get('ingest_path', '?')})"
        recorded = (manifest.get("protein_databases") or {}).get("read") or []
        if args.db:
            recorded = [{"path": str(p), "sha256": sha256_file(p)} for p in args.db]
        if not recorded:
            print(f"{label}: SKIPPED -- built before 0.15.0 or with no database; pass --db to check it")
            continue
        seqs, problem = _sequences(recorded)
        if seqs is None:
            print(f"{label}: SKIPPED -- {problem}")
            continue
        path = bundle / "ptm_sites.parquet"
        rows = pq.read_table(path).to_pylist() if path.is_file() else []
        if not args.all:
            rows = [r for r in rows if r.get("target_decoy") == "target"]
        counts = verify_site_residues(rows, seqs)
        bad = counts["wrong_residue"] + counts["beyond_length"]
        failed |= bad > 0
        print(f"{label}: {'FAIL' if bad else 'ok'}  {counts}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
