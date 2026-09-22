"""Where each producer file is parsed, and by whom.

The rule (FRAMEWORK section 3): **pyMzLib's typed readers parse producer formats**, so dataRepo does
not grow a second, drifting implementation of somebody else's file format. pyMzLib 0.1.x does not
reach every file this ingester needs, and each gap is named here with the request that closes it,
so the in-house reading below is deletable rather than permanent.

| File | Parsed by | Why |
|---|---|---|
| `AllPSMs.psmtsv`, `AllPeptides.psmtsv` | pyMzLib `read_records` | covered, typed |
| `AllQuantifiedPeaks.tsv` | in-house TSV | pyMzLib's reader wants an `MBR Score` column MetaMorpheus 1.1.11 does not write (DATAREPO-13) |
| `AllQuantifiedPeptides.tsv`, `AllQuantifiedProteinGroups.tsv` | in-house TSV | no pyMzLib reader (aging 006; asked as pyMzLib 005) |
| `*.sdrf.tsv` | pyMzLib `sdrf.read` | covered since 0.1.1 |
| `results.txt`, `*.toml`, `Mods/*.txt`, `*.json` | in-house | not file formats pyMzLib owns |
| the searched protein database (`.xml`, `.fasta`) | in-house, `sources/protein_db.py` | pyMzLib has no protein-database reader; only `(accession, sequence)` is read, to place PTM sites (DATAREPO-32) |

`*.sdrf.tsv` is the one that has already gone the other way. dataRepo read it as plain TSV because
pyMzLib's *generic* projection joined header and cells with `;`, which SDRF values contain
themselves, so the columns could not be recovered (DATAREPO-13). pyMzLib 0.1.1 answers that with a
dedicated `pymzlib.sdrf` module, and on the real PXD036557 file it agrees with the in-house read cell
for cell, including all 144 cells that contain a `;`. The in-house read is gone. Note that the
generic `read_records()` path is unchanged and still lossy on an SDRF, so it must not be used for
one.

None of the in-house reading interprets: it splits on tabs and hands back strings. Interpretation
(peptidoform notation, age normalization, metric definitions) stays with the projects that own it.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .errors import ReaderUnavailable

#: Read with pyMzLib; anything else falls to the in-house TSV reader with a reason.
PYMZLIB_FORMATS = (".psmtsv",)


@dataclass
class ReaderLog:
    """Which backend read which file, for the bundle manifest's `readers` block."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, path: Path, backend: str, rows: int, note: str | None = None) -> None:
        self.entries.append(
            {"file": path.name, "backend": backend, "rows": rows, **({"note": note} if note else {})}
        )

    def backends(self) -> list[str]:
        return sorted({e["backend"] for e in self.entries})


def require_pymzlib():
    """Import pyMzLib and prove its bridge is usable, or explain what to do about it.

    Raises:
        ReaderUnavailable: pyMzLib is not installed, or no mzLib bridge exists for this platform.
    """
    try:
        from pymzlib import readers as _readers  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ReaderUnavailable(
            "pyMzLib is not installed. `pip install mzlib` -- the distribution is named `mzlib` and "
            "imports as `pymzlib` -- or `pip install -e .[readers]`. dataRepo does not parse "
            "producer formats itself."
        ) from exc
    try:
        from pymzlib import bridge_path  # noqa: PLC0415

        bridge_path()
    except Exception as exc:  # pragma: no cover - environment dependent
        raise ReaderUnavailable(
            f"pyMzLib is installed but its mzLib bridge is not available: {exc}. A released wheel "
            "carries the bridge, so this usually means a source checkout: build the bridge and "
            "point PYMZLIB_BRIDGE at the executable, or `pip install mzlib`."
        ) from exc
    return _readers


def read_sdrf(path: Path, log: ReaderLog | None = None) -> tuple[list[str], list[list[str]]]:
    """Read an SDRF through pyMzLib, as a header and rows of raw cells.

    `pymzlib.sdrf.read` is used rather than the generic `read_records`, which joins header and cells
    with `;` and cannot be split back apart because SDRF values contain `;` themselves.

    Column names are a *list* and may repeat -- `comment[modification parameters]` legitimately
    appears more than once -- so a name identifies a position, not a column. Cells are raw strings:
    the `NT=...;AC=...` grammar is left exactly as written, and interpreting it is `sources.sdrf`'s
    job, not the reader's.

    Returns:
        `(column names, rows)`, the same shape `read_tsv` returns, so callers need not care which
        backend read the file.
    """
    require_pymzlib()
    from pymzlib import sdrf as _sdrf  # noqa: PLC0415

    doc = _sdrf.read(str(path))
    if getattr(doc, "truncated", False):  # pragma: no cover - only with an explicit limit
        raise ReaderUnavailable(f"pyMzLib truncated its read of {path}")
    rows = [list(row) for row in doc.rows]
    if log is not None:
        log.record(path, "pymzlib", len(rows))
    return list(doc.columns), rows


def read_psmtsv(path: Path, log: ReaderLog | None = None) -> dict[str, list[Any]]:
    """Read a MetaMorpheus `.psmtsv` through pyMzLib, as columns.

    Returns:
        The reader's native fields, one list per column. Composite fields that have no faithful
        column shape (matched fragment ions, protein-group tuples) are excluded by pyMzLib; the
        verbatim text of the ion series is taken from the file's own column where needed.
    """
    readers = require_pymzlib()
    records = readers.read_records(str(path), timeout=None)
    if records.truncated:  # pragma: no cover - only with an explicit limit
        raise ReaderUnavailable(f"pyMzLib truncated its read of {path}")
    if log is not None:
        log.record(path, "pymzlib", records.record_count)
    return records.columns


def read_tsv(path: Path, log: ReaderLog | None = None, note: str | None = None) -> tuple[list[str], list[list[str]]]:
    """Read a tab-separated file as a header and a list of rows, with no interpretation."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE)
        try:
            header = next(reader)
        except StopIteration:
            header = []
        rows = [row for row in reader if row]
    if log is not None:
        log.record(path, "datarepo-tsv", len(rows), note)
    return header, rows


def iter_dicts(header: list[str], rows: list[list[str]]) -> Iterator[dict[str, str]]:
    """Zip a header onto rows, tolerating short rows (trailing empty cells are dropped by writers)."""
    width = len(header)
    for row in rows:
        if len(row) < width:
            row = row + [""] * (width - len(row))
        yield dict(zip(header, row))


_RESULTS_TOTAL = re.compile(r"^All target (?P<what>\w+(?: \w+)*) with q-value <= 0\.01.*?:\s*(?P<n>\d+)")
_RESULTS_PER_FILE = re.compile(
    r"^(?P<run>\S+) - Target (?P<what>\w+(?: \w+)*) with q-value <= 0\.01.*?:\s*(?P<n>\d+)"
)
_RESULTS_SCANS = re.compile(r"^(?:(?P<run>\S+) - )?All (?P<what>MS2 Scans|Precursors):\s*(?P<n>\d+)")
_RESULTS_SCANS_PER_FILE = re.compile(r"^(?P<run>\S+) - (?P<what>MS2 Scans|Precursors):\s*(?P<n>\d+)")


def read_results_txt(path: Path, log: ReaderLog | None = None) -> dict[str, dict[str, int]]:
    """Pull the counted totals out of MetaMorpheus's free-text `results.txt`.

    These are the numbers the ingest reconciles against: `All target PSMs with q-value <= 0.01` is
    aging's canonical `DEF-PSM-1PCT v1` (aging 006), and it differs on purpose from the FDR
    engine's own log line that older provenance records as `psms_1pct`.

    Returns:
        `{scope: {name: count}}` where scope is `""` for dataset-wide totals or the run name.
    """
    out: dict[str, dict[str, int]] = {}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        for pattern in (_RESULTS_PER_FILE, _RESULTS_TOTAL, _RESULTS_SCANS_PER_FILE, _RESULTS_SCANS):
            m = pattern.match(line)
            if not m:
                continue
            scope = (m.groupdict().get("run") or "").strip()
            name = m.group("what").strip().lower().replace(" ", "_")
            out.setdefault(scope, {})[name] = int(m.group("n"))
            break
    if log is not None:
        log.record(path, "datarepo-text", sum(len(v) for v in out.values()))
    return out
