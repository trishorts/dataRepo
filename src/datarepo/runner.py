"""`datarepo run`: an instance operator runs a RELEASED engine on stored data (G64, D27, D28).

Engines that work on stored results (logs' gene resolution first; go and ptmQtl once released) never
learn which consumer they serve, so none of them runs itself. dataRepo ships this runner and
operates nothing: the instance operator (today aging) runs it. Its output is an **engine artefact**,
content-addressed and written beside the bundles, never inside one (U12):

    <store>/_engine/<engine>/<artefact id>/
        run.json              the record: engine, releases, every input with its sha256
        <table>.parquet       one file per schema table the engine fills

The four rules it keeps (charter section 2, aging 055 section 1, design/RUNNER.md):

1. **Released inputs only.** The engine is a released package; an editable or source install is
   refused. So is an editable or unidentifiable datarepo (aging 063): an artefact stamped by
   uncommitted code is reproducible by nobody.
2. **Idempotent.** The artefact id is a sha256 over the engine, its release, every input's role and
   sha256, the definition id, `RUNNER_VERSION` and the schema version (U13). An id already on disk
   is "already done", and nothing is re-run.
3. **Beside the bundle, never inside it.** A run never reads a bundle's rows, never rewrites one and
   never moves a bundle id. It reads only a bundle's `bundle.json`, for which databases it searched.
4. **The record is the output's provenance.** `run.json` holds everything hashed plus what was not:
   the datarepo install, the bundles asked about, the engine's own summary and acceptance result.

Same boundary as `bundle.INGESTER_VERSION`: what reaches a written row is hashed, and nothing else.
The datarepo install is recorded but NOT hashed, because a runner release that writes the same rows
must not re-identify an artefact. `RUNNER_VERSION` is what moves when it would not.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlparse

import pyarrow.parquet as pq

from . import __version__
from ._tables import SCHEMA_VERSION
from .bundle import table_from_rows
from .errors import RunnerError

#: The version of the RUN PATH, and the only datarepo version in an artefact's id. Bump it in the
#: same commit as any change to what a run reads, checks, derives or writes.
RUNNER_VERSION = "1"

#: Where engine artefacts live in the store. The underscore keeps it out of the dataset namespace,
#: as `_study/` does: no ProteomeXchange or MassIVE accession starts with one.
ENGINE_DIR = "_engine"
RUN_RECORD = "run.json"


# --- who is running: the install identities ----------------------------------------------------

def _direct_url(distribution: str) -> dict[str, Any] | None:
    import importlib.metadata  # noqa: PLC0415

    try:
        dist = importlib.metadata.distribution(distribution)
    except importlib.metadata.PackageNotFoundError as exc:
        raise RunnerError(f"{distribution} is not installed") from exc
    text = dist.read_text("direct_url.json")
    return json.loads(text) if text else None


def _local_path(url: str) -> Path:
    parsed = urlparse(url)
    path = unquote(parsed.path)
    # file:///F:/x parses to "/F:/x" on Windows.
    if len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return Path(path)


def _git(path: Path, *args: str) -> str:
    try:
        done = subprocess.run(
            ["git", "-C", str(path), *args], capture_output=True, text=True, check=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RunnerError(f"could not ask git about {path}: {exc}") from exc
    return done.stdout.strip()


def install_identity(distribution: str = "datarepo", *, version: str | None = None) -> dict[str, Any]:
    """Which release of `distribution` is running, or a refusal (aging 063).

    Accepted, each with what identifies it:

    - installed from an index: the version (an index never serves two builds under one version);
    - from a VCS URL: the commit pip recorded;
    - from a wheel or sdist file: its sha256, from pip's record or by hashing the file;
    - from a local directory, NOT editable: the directory's git HEAD, and only if that clone is
      clean. This is how aging installs a release: a read-only clone at the announced sha.

    Refused: an editable install (the code can change under a running operator, which is how a
    0.18.0 working tree was on aging's PATH mid-release), and anything else with no identity.
    """
    import importlib.metadata  # noqa: PLC0415

    version = version or importlib.metadata.version(distribution)
    info = _direct_url(distribution)
    if info is None:
        return {"distribution": distribution, "version": version, "source": "index"}
    url = str(info.get("url", ""))
    if (info.get("dir_info") or {}).get("editable"):
        raise RunnerError(
            f"{distribution} {version} is an EDITABLE install from {url}. An artefact stamped by a "
            f"working tree is reproducible by nobody, so the runner refuses it. Install a release "
            f"into its own environment: `pip install <clone at the announced sha>` (not -e)."
        )
    if "vcs_info" in info:
        commit = (info["vcs_info"] or {}).get("commit_id")
        if not commit:
            raise RunnerError(f"{distribution} {version} came from {url} with no recorded commit")
        return {"distribution": distribution, "version": version, "source": "vcs", "url": url,
                "commit": commit}
    if "archive_info" in info:
        archive = info["archive_info"] or {}
        hashes = archive.get("hashes") or {}
        digest = hashes.get("sha256")
        if not digest and str(archive.get("hash", "")).startswith("sha256="):
            digest = archive["hash"].split("=", 1)[1]
        if not digest:
            path = _local_path(url)
            if not path.is_file():
                raise RunnerError(
                    f"{distribution} {version} was installed from {url}, which pip recorded no hash "
                    f"for and which is no longer on disk, so which build it was cannot be shown."
                )
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"distribution": distribution, "version": version, "source": "archive", "url": url,
                "sha256": digest}
    if "dir_info" in info:
        path = _local_path(url)
        if not (path / ".git").exists():
            raise RunnerError(
                f"{distribution} {version} was installed from the directory {path}, which is not a "
                f"git clone, so no commit identifies it. Install from a clone at a released sha."
            )
        dirty = _git(path, "status", "--porcelain")
        if dirty:
            raise RunnerError(
                f"{distribution} {version} was installed from {path}, whose working tree has "
                f"uncommitted changes, so its commit does not identify the code that was installed."
            )
        return {"distribution": distribution, "version": version, "source": "git-clone",
                "url": url, "commit": _git(path, "rev-parse", "HEAD")}
    raise RunnerError(f"{distribution} {version}: unrecognised install record {info!r}")


# --- artefacts -----------------------------------------------------------------------------------

def artefact_id(
    engine: str,
    release: Mapping[str, Any],
    inputs: Mapping[str, str],
    definition_id: str,
) -> str:
    """The artefact's content hash, and the "already done" test (U13).

    Args:
        engine: e.g. `logs.resolve_genes`.
        release: the engine's released versions, e.g. `{"pymzlib": "0.2.0", "mzlib": "..."}`.
        inputs: `{role: sha256}` for every input that reaches a row.
        definition_id: the method the rows are written under.
    """
    digest = hashlib.sha256()
    digest.update(f"runner/{RUNNER_VERSION}\nschema/{SCHEMA_VERSION}\nengine/{engine}\n".encode())
    for key, value in sorted(release.items()):
        digest.update(f"release/{key}\t{value}\n".encode())
    for role, sha in sorted(inputs.items()):
        digest.update(f"input/{role}\t{sha}\n".encode())
    digest.update(f"definition/{definition_id}\n".encode())
    return digest.hexdigest()[:16]


@dataclass(frozen=True)
class ArtefactRef:
    """One written engine artefact, as `build` sees it."""

    path: Path
    record: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "ArtefactRef":
        record_path = path / RUN_RECORD
        if not record_path.is_file():
            raise RunnerError(f"{path} holds no {RUN_RECORD}, so it is not an engine artefact")
        return cls(path=path, record=json.loads(record_path.read_text(encoding="utf-8")))

    @property
    def engine(self) -> str:
        return str(self.record["engine"])

    @property
    def artefact_id(self) -> str:
        return str(self.record["artefact_id"])

    @property
    def schema_version(self) -> str:
        return str(self.record.get("schema_version", "?"))

    @property
    def inputs(self) -> dict[str, str]:
        return {str(k): str(v) for k, v in (self.record.get("inputs") or {}).items()}

    @property
    def row_counts(self) -> dict[str, int]:
        return {str(k): int(v) for k, v in (self.record.get("tables") or {}).items()}

    def table_path(self, table: str) -> Path | None:
        path = self.path / f"{table}.parquet"
        return path if path.is_file() else None


def artefact_dir(store: Path, engine: str, aid: str) -> Path:
    return Path(store) / ENGINE_DIR / engine / aid


def discover_artefacts(store: Path, engine: str | None = None) -> list[ArtefactRef]:
    """Every engine artefact in the store (or one engine's), ordered by engine and id."""
    root = Path(store) / ENGINE_DIR
    if not root.is_dir():
        return []
    engines = [root / engine] if engine else sorted(p for p in root.iterdir() if p.is_dir())
    found = []
    for directory in engines:
        if not directory.is_dir():
            continue
        for child in sorted(directory.iterdir()):
            if child.is_dir() and (child / RUN_RECORD).is_file():
                found.append(ArtefactRef.load(child))
    return found


def write_artefact(
    store: Path,
    engine: str,
    aid: str,
    record: dict[str, Any],
    tables: Mapping[str, Sequence[dict[str, Any]]],
) -> ArtefactRef:
    """Write one artefact atomically: into a staging directory, then renamed into place.

    A failure leaves nothing that `discover_artefacts` would find, so a half-written run can never
    be mistaken for "already done".
    """
    final = artefact_dir(store, engine, aid)
    if final.exists():
        raise RunnerError(f"{final} already exists")
    staging = final.with_name(f".{aid}.writing")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        counts = {}
        for table, rows in sorted(tables.items()):
            pq.write_table(table_from_rows(table, rows), staging / f"{table}.parquet")
            counts[table] = len(rows)
        full = {
            **record,
            "engine": engine,
            "artefact_id": aid,
            "runner_version": RUNNER_VERSION,
            "schema_version": SCHEMA_VERSION,
            "datarepo_version": __version__,
            "tables": counts,
            "written_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        (staging / RUN_RECORD).write_text(json.dumps(full, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        staging.rename(final)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return ArtefactRef.load(final)


#: Engines the runner knows. Each is a module in `datarepo.engines` with a `run(...)` entry point.
ENGINES = ("logs.resolve_genes",)

#: Core tables that only an engine artefact fills, and the engine that fills each. A bundle never
#: holds one; `build` loads them from `<store>/_engine/` instead.
ENGINE_TABLES: dict[str, str] = {"gene_resolutions": "logs.resolve_genes"}
