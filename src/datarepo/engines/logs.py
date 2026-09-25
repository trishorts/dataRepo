"""`logs.resolve_genes`: protein -> Ensembl gene, per searched database (G64, D28 U15).

The method is logs' (`logs:DEF-GENE-RESOLUTION v1`, logs 017); the code is mzLib's
`EnsemblGeneResolver`, called through pyMzLib's `proteins.resolve_genes`. This module computes
nothing about genes. It decides WHAT to run on, checks every input, calls the released verb, and
refuses rows that do not keep logs' contract.

**The unit is one searched target database**, not a bundle and not a dataset. Fifteen human
datasets search one proteome, so one artefact serves all of them, and re-ingesting a dataset never
re-runs an unchanged resolution (U13). Resolving a bundle's databases together would not do: a
dataset searched with aging's isoform database and one searched without it would each carry the
proteome's rows, and a catalog holding both would hold every proteome row twice.

**The contaminant database is never resolved** (our logs 018): a contaminant must not be mapped
through anything (logs 002 section 0), so a contaminant protein has no row rather than a target's.
Which file is a contaminant panel is MetaMorpheus's own rule (`protein_db.is_contaminant_database`).

Inputs, each by role (U14), and each checked before anything runs:

- `gene_set`: logs' compact gene table (or an Ensembl GTF), hashed into the artefact id;
- `xref`: Ensembl's UniProt xref. Required: without it the run is not v1 (logs 017 section 3);
- `logs_manifest`: logs' `resolver_inputs_e<release>.json`. Used only to CHECK (the species whose
  gene set and xref these are, and the values every row must carry), so it is recorded and not
  hashed: a reworded manifest that names the same files must not re-identify an artefact;
- the searched databases, taken from each bundle's own `bundle.json` and refused unless the file
  on disk still hashes to what the bundle recorded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pyarrow.parquet as pq

from .. import runner
from .._schema_docs import ENUMS
from .._tables import TABLES
from ..bundle import sha256_file
from ..catalog import BundleRef
from ..errors import RunnerError
from ..sources.protein_db import is_contaminant_database

ENGINE = "logs.resolve_genes"
DEFINITION_ID = "logs:DEF-GENE-RESOLUTION v1"
TABLE = "gene_resolutions"
ROLES = ("gene_set", "xref", "logs_manifest")

#: pyMzLib's bookkeeping columns: which of the files passed a row came from. Not part of mzLib's
#: `GeneResolutionTsv` schema, and `search_database_sha256` already says the same thing portably.
_NOT_STORED = ("source_index", "source_path")


@dataclass
class TargetDatabase:
    """One searched target database, and the bundles that searched it."""

    path: Path
    sha256: str
    bundles: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class RunResult:
    """What one invocation did, per database."""

    written: list[runner.ArtefactRef] = field(default_factory=list)
    already_done: list[runner.ArtefactRef] = field(default_factory=list)
    skipped_contaminant: list[str] = field(default_factory=list)


def _organisms(ref: BundleRef) -> list[str]:
    path = ref.table_path("datasets")
    if path is None:
        return []
    rows = pq.read_table(path, columns=["organisms"]).to_pylist()
    return sorted({o for r in rows for o in (r["organisms"] or [])})


def species_entry(manifest: Mapping[str, Any], gene_set_sha: str, xref_sha: str) -> dict[str, Any]:
    """logs' manifest entry whose gene set AND xref are the files given, or a refusal."""
    for entry in manifest.get("species") or []:
        inputs = entry.get("inputs") or {}
        if (inputs.get("gene_set") or {}).get("sha256") != gene_set_sha:
            continue
        if (inputs.get("ensembl_uniprot_xref") or {}).get("sha256") != xref_sha:
            raise RunnerError(
                f"the gene set is logs' {entry.get('species')} file, but the xref (sha256 {xref_sha}) "
                f"is not the one logs' manifest pairs with it "
                f"({(inputs.get('ensembl_uniprot_xref') or {}).get('sha256')})."
            )
        if not entry.get("row_values"):
            raise RunnerError(f"logs' manifest entry for {entry.get('species')} has no row_values")
        return entry
    raise RunnerError(
        f"no species in logs' manifest has a gene set with sha256 {gene_set_sha}. Pass the gene set "
        f"file the manifest names, unchanged."
    )


def target_databases(bundles: Sequence[BundleRef], taxon: str) -> tuple[list[TargetDatabase], list[str]]:
    """The distinct target databases the bundles searched, and the contaminant files left out.

    Raises:
        RunnerError: a bundle of another organism than the gene set's, or one that records no
            searched database.
    """
    by_sha: dict[str, TargetDatabase] = {}
    contaminants: set[str] = set()
    for ref in bundles:
        organisms = _organisms(ref)
        if organisms != [taxon]:
            # Two organisms means two proteomes, and nothing in bundle.json says which database is
            # which species: resolving both against one gene set would be wrong for one of them.
            raise RunnerError(
                f"{ref.dataset_id} bundle {ref.bundle_id} is {', '.join(organisms) or 'of no recorded organism'}, "
                f"and the gene set is {taxon}. A gene set only resolves its own species, and a "
                f"dataset of several organisms is not run until its databases can be told apart."
            )
        read = ((ref.manifest.get("protein_databases") or {}).get("read")) or []
        if not read:
            raise RunnerError(
                f"{ref.dataset_id} bundle {ref.bundle_id} records no searched database "
                f"(`protein_databases.read` in bundle.json), so there is nothing to resolve."
            )
        for db in read:
            path = Path(str(db["path"]))
            if is_contaminant_database(path):
                contaminants.add(path.name)
                continue
            target = by_sha.setdefault(str(db["sha256"]), TargetDatabase(path=path, sha256=str(db["sha256"])))
            target.bundles.append((ref.dataset_id, ref.bundle_id))
    return [by_sha[k] for k in sorted(by_sha)], sorted(contaminants)


def _release() -> dict[str, str]:
    """pyMzLib's release and the mzLib its bridge reports, refusing an unreleased pyMzLib."""
    import pymzlib  # noqa: PLC0415

    identity = runner.install_identity("mzlib", version=pymzlib.__version__)
    if identity["source"] not in ("index", "archive"):
        raise RunnerError(
            f"pyMzLib {pymzlib.__version__} is installed from {identity.get('url')}, not as a "
            f"released package. The runner runs released engines only: `pip install mzlib==<version>`."
        )
    return {"pymzlib": pymzlib.__version__, "mzlib": str(pymzlib.bridge_version()["mzlib"])}


def _resolve(database: Path, gene_set: Path, xref: Path) -> Any:
    from pymzlib import proteins  # noqa: PLC0415

    return proteins.resolve_genes([database], gene_set=gene_set, xref=xref)


def rows_from(result: Any, *, database_sha: str, row_values: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The verb's table as `gene_resolutions` rows, after logs' acceptance checks (RUNNER.md).

    Raises:
        RunnerError: a failed database read, a row for another database, a row whose gene set or
            xref differ from logs' manifest (the check logs asked for, 016 section 1), an outcome
            outside mzLib's six, or no rows at all.
    """
    if getattr(result, "failed_count", 0):
        raise RunnerError(f"the resolver failed to read {result.failed_count} database file(s)")
    names = list(result.column_names)
    columns = result.columns
    n = len(columns[names[0]]) if names else 0
    if n == 0:
        raise RunnerError("the resolver returned no rows for the database")
    outcomes = set(ENUMS["GeneResolutionOutcome"]["values"])
    expected = {
        "gene_set_sha256": str(row_values["gene_set_sha256"]),
        "ensembl_xref_sha256": str(row_values["ensembl_xref_sha256"]),
        "gene_set_release": str(row_values["gene_set_release"]),
    }
    stored = [c for c in names if c not in _NOT_STORED]
    unknown = sorted(set(stored) - set(TABLES[TABLE].names))
    if unknown:
        raise RunnerError(
            f"the resolver writes column(s) {unknown} that `{TABLE}` has no place for. A newer "
            f"pyMzLib changed the contract; the schema has to take it before the runner does."
        )
    rows = []
    for i in range(n):
        row = {c: columns[c][i] for c in stored}
        where = f"row {i} ({row.get('accession')}, {row.get('gene_id')})"
        if row.get("search_database_sha256") != database_sha:
            raise RunnerError(f"{where}: search_database_sha256 {row.get('search_database_sha256')} is not the database resolved")
        for key, value in expected.items():
            if str(row.get(key) or "") != value:
                raise RunnerError(f"{where}: {key} {row.get(key)!r} differs from logs' manifest {value!r}")
        if row.get("outcome") not in outcomes:
            raise RunnerError(f"{where}: outcome {row.get('outcome')!r} is not one of mzLib's {sorted(outcomes)}")
        row["definition_id"] = DEFINITION_ID
        rows.append(row)
    return rows


def run(
    store: Path,
    bundles: Sequence[BundleRef],
    inputs: Mapping[str, Path],
    *,
    install: Mapping[str, Any] | None = None,
    release: Mapping[str, str] | None = None,
    resolve: Callable[[Path, Path, Path], Any] = _resolve,
) -> RunResult:
    """Resolve every target database the bundles searched, one artefact per database.

    Args:
        store: the instance's store; artefacts go under `<store>/_engine/logs.resolve_genes/`.
        bundles: the bundles to run on behalf of, one or more, all of the gene set's species.
        inputs: `{role: path}` for every role in `ROLES`.
        install: the datarepo install record; `runner.install_identity()` when None. Tests pass one.
        release: the engine release; `_release()` when None. Tests pass one.
        resolve: the verb. Tests pass a stand-in; everything around it is the real path.

    Raises:
        RunnerError: a missing or mismatched input, an unreleased engine or datarepo, or rows that
            fail acceptance. Databases already resolved stay resolved: each artefact is written
            whole or not at all.
    """
    missing = [r for r in ROLES if r not in inputs]
    if missing:
        extra = " Without `xref`, the rows are not logs:DEF-GENE-RESOLUTION v1 (logs 017)." if "xref" in missing else ""
        raise RunnerError(f"{ENGINE} needs --input {'=<path>, --input '.join(missing)}=<path>.{extra}")
    unknown = sorted(set(inputs) - set(ROLES))
    if unknown:
        raise RunnerError(f"{ENGINE} takes inputs {', '.join(ROLES)}; not {', '.join(unknown)}")
    for role, path in inputs.items():
        if not Path(path).is_file():
            raise RunnerError(f"--input {role}={path}: no such file")
    if not bundles:
        raise RunnerError(f"{ENGINE} needs at least one bundle to run on behalf of")

    install = dict(install) if install is not None else runner.install_identity()
    gene_set_sha = sha256_file(Path(inputs["gene_set"]))
    xref_sha = sha256_file(Path(inputs["xref"]))
    manifest_path = Path(inputs["logs_manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = species_entry(manifest, gene_set_sha, xref_sha)
    taxon = f"NCBITaxon:{entry['ncbi_taxonomy_id']}"
    databases, contaminants = target_databases(bundles, taxon)
    release = dict(release) if release is not None else _release()

    result = RunResult(skipped_contaminant=contaminants)
    for db in databases:
        hashed = {"search_database": db.sha256, "gene_set": gene_set_sha, "xref": xref_sha}
        aid = runner.artefact_id(ENGINE, release, hashed, DEFINITION_ID)
        existing = runner.artefact_dir(store, ENGINE, aid)
        if (existing / runner.RUN_RECORD).is_file():
            result.already_done.append(runner.ArtefactRef.load(existing))
            continue
        if not db.path.is_file():
            raise RunnerError(
                f"{db.path} (searched by {', '.join(d for d, _ in db.bundles)}) is not on disk. The "
                f"runner fetches nothing: restore the file the bundle recorded."
            )
        actual = sha256_file(db.path)
        if actual != db.sha256:
            raise RunnerError(
                f"{db.path} now hashes to {actual}, and the bundles recorded {db.sha256}. It is not "
                f"the database they searched, so resolving it would describe some other search."
            )
        verb = resolve(db.path, Path(inputs["gene_set"]), Path(inputs["xref"]))
        rows = rows_from(verb, database_sha=db.sha256, row_values=entry["row_values"])
        record = {
            "definition_id": DEFINITION_ID,
            "release": release,
            "inputs": hashed,
            "input_files": {
                "search_database": str(db.path),
                "gene_set": str(inputs["gene_set"]),
                "xref": str(inputs["xref"]),
            },
            "checked_against": {
                "logs_manifest": str(manifest_path),
                "logs_manifest_sha256": sha256_file(manifest_path),
                "species": entry.get("species"),
                "row_values": entry["row_values"],
            },
            "datarepo_install": install,
            "requested_for": [{"dataset_id": d, "bundle_id": b} for d, b in db.bundles],
            "engine_summary": {
                "protein_count": getattr(verb, "protein_count", None),
                "record_count": getattr(verb, "record_count", None),
                "outcome_counts": dict(getattr(verb, "outcome_counts", {}) or {}),
                "caveats": list(getattr(verb, "caveats", []) or []),
            },
            "acceptance": "passed",
        }
        result.written.append(runner.write_artefact(store, ENGINE, aid, record, {TABLE: rows}))
    return result
