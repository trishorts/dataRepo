"""A bounded, read-only DuckDB connection over one catalog.

This is stage one of D14: what an agent gets when it runs SQL through `datarepo mcp`. It is not the
sqlglot AST allow-list of FRAMEWORK section 4 -- that is stage two, for when D2's public no-login
endpoint exists and the thing being bounded is an attacker. Locally the agent already has the
filesystem through Claude Code, so the job here is **blast radius and provenance**, not security:
a query should not be able to run for an hour, return a million rows into a context window, or --
the one that matters most -- quietly answer from data that is not this catalog.

Everything below was measured on DuckDB 1.5.5 against a real catalog, because the obvious
assumptions are wrong:

* **`read_only=True` alone is not a sandbox.** A read-only connection ran `read_csv_auto` on a file
  outside the store and returned its 2 rows.
* **`enable_external_access=false` closes that** and cannot be undone from inside the session:
  `SET`, `PRAGMA` and `RESET` all fail with "Cannot enable external access while database is
  running", and `INSTALL`/`LOAD`/`COPY ... TO`/`glob()` are refused with it.
* **It does not close `ATTACH`.** With external access off, `ATTACH 'other.duckdb' (READ_ONLY)`
  still succeeded -- so an agent could read any other DuckDB file on the machine and return rows
  under a result labelled with THIS catalog's `catalog_id`. That is a D13 violation before it is a
  security one. `SET disabled_filesystems='LocalFileSystem'`, issued after the connection is open,
  refuses the ATTACH and is itself one-way ("has been disabled previously, it cannot be
  re-enabled"). The already-open catalog keeps serving: a 1.2M-row scan, a group-by and the
  acceptance views all run unchanged with it set.
* **The `range(3e9)` probe no longer demonstrates a timeout.** DuckDB 1.5 answers
  `SELECT count(*) FROM range(3000000000)` from metadata in half a second. A real cross join is
  needed to show the watchdog working, and it does: interrupted at 2.01 s of a 2 s deadline, with
  the connection usable immediately afterwards.

One consequence of the filesystem lock is worth knowing before it surprises someone: it belongs to
the DuckDB **database instance**, not to the connection. Every connection to one file in one
process shares that instance, so a second connection inherits the lock, `current_setting(
'disabled_filesystems')` reads back `''` while it is in force, and DuckDB refuses a second
connection with a *different* config outright ("Can't open a connection to same database file with
a different configuration"). In one process, `catalog.run_query` -- which connects plainly -- cannot
open a catalog a `Sandbox` already holds. The server is its own process, so this costs nothing
there; it matters to anything that would open a catalog twice.

The row and character caps are applied by **reading fewer rows**, never by rewriting the query. A
wrapped `SELECT * FROM (<their sql>) LIMIT n` would silently change the meaning of a statement that
is not a plain SELECT, and a tool that edits a question before answering it is the shape of a
silently-wrong answer.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .errors import CatalogError, QueryRefused, QueryTimeout

#: Config applied when the connection is opened. Nothing here can be undone from inside a query.
CONNECT_CONFIG: dict[str, Any] = {"enable_external_access": False}

#: Set immediately after connecting -- it cannot be passed to `connect()` ("Cannot change/set
#: disabled_filesystems before the database is started") and cannot be reset afterwards. This is
#: what closes the ATTACH hole that `enable_external_access` leaves open.
DISABLED_FILESYSTEMS = "LocalFileSystem"

#: Caps, from D14. A result at either cap is still returned, with `truncated` set and a reason --
#: an agent that is told it saw the first 1,000 of 26,582 rows can ask a narrower question; an
#: agent handed 1,000 rows with no flag concludes there were 1,000.
ROW_CAP = 1_000
CHAR_CAP = 50_000

#: Wall-clock seconds before the watchdog calls `con.interrupt()`. DuckDB 1.5 has no
#: `statement_timeout` setting, so the deadline is enforced from a thread of ours.
TIMEOUT_SECONDS = 30.0

#: Statement kinds this sandbox will execute. Everything else is refused **by name, before it
#: runs**, so the agent gets a sentence it can act on rather than a DuckDB permission error.
#: `SELECT` covers the questions; the other three are how an agent explores a schema it has not
#: seen. This is deliberately not the sqlglot allow-list (D14 stage two): it inspects the statement
#: KIND, which DuckDB tells us for free, and makes no claim about what is inside one.
ALLOWED_STATEMENTS = ("SELECT", "EXPLAIN", "PRAGMA", "SHOW")


@dataclass
class BoundedResult:
    """One query's answer, with everything needed to say how complete it is."""

    columns: list[str]
    rows: list[tuple]
    truncated: bool = False
    #: Why it was cut short: `"rows"`, `"characters"`, or None when it is whole.
    truncated_by: str | None = None
    elapsed_seconds: float = 0.0
    #: The caps in force, so a caller can report them without importing this module's constants.
    caps: dict[str, Any] = field(default_factory=dict)

    @property
    def row_count(self) -> int:
        return len(self.rows)


def _statement_kinds(sql: str) -> list[str]:
    """Parse without executing. Raises `QueryRefused` when DuckDB cannot parse it at all."""
    import duckdb  # noqa: PLC0415

    try:
        statements = duckdb.extract_statements(sql)
    except duckdb.Error as exc:
        raise QueryRefused(f"not valid SQL: {exc}") from exc
    return [str(getattr(s.type, "name", s.type)).upper() for s in statements]


def check_statement(sql: str) -> str:
    """Refuse a query before it runs, and say why in a sentence the agent can act on.

    Returns:
        The statement kind, e.g. `"SELECT"`.

    Raises:
        QueryRefused: empty, more than one statement, or a kind not in `ALLOWED_STATEMENTS`.
    """
    kinds = _statement_kinds(sql)
    if not kinds:
        raise QueryRefused("no statement to run")
    if len(kinds) > 1:
        raise QueryRefused(
            f"{len(kinds)} statements in one query ({', '.join(kinds)}); send one at a time, so "
            f"that the result you get back is the answer to a question you asked"
        )
    kind = kinds[0]
    if kind not in ALLOWED_STATEMENTS:
        raise QueryRefused(
            f"{kind} is not one of the statement kinds this catalog answers "
            f"({', '.join(ALLOWED_STATEMENTS)}). The catalog is derived and read-only: it is "
            f"rebuilt from its bundles by `datarepo build`, never written to through a query."
        )
    return kind


class Sandbox:
    """An open, bounded connection to one catalog file.

    The connection is opened once and reused, because opening a DuckDB file costs more than most
    of the queries an agent asks. It is not thread-safe: the MCP server serves one call at a time.
    """

    def __init__(
        self,
        path: Path | str,
        *,
        timeout_seconds: float = TIMEOUT_SECONDS,
        row_cap: int = ROW_CAP,
        char_cap: int = CHAR_CAP,
    ) -> None:
        import duckdb  # noqa: PLC0415

        self.path = Path(path)
        if not self.path.is_file():
            raise CatalogError(f"no catalog at {self.path}")
        self.timeout_seconds = float(timeout_seconds)
        self.row_cap = int(row_cap)
        self.char_cap = int(char_cap)
        try:
            self._con = duckdb.connect(str(self.path), read_only=True, config=dict(CONNECT_CONFIG))
        except duckdb.Error as exc:
            raise CatalogError(f"{self.path} could not be opened read-only: {exc}") from exc
        # Order matters and is not optional: this cannot be passed to connect(), and once set it
        # cannot be unset. Do it before any caller-supplied SQL reaches the connection.
        self._con.execute(f"SET disabled_filesystems='{DISABLED_FILESYSTEMS}'")

    # -- lifecycle ---------------------------------------------------------------------------

    def close(self) -> None:
        try:
            self._con.close()
        except Exception:  # noqa: BLE001 - closing a broken connection is not an error worth raising
            pass

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @property
    def caps(self) -> dict[str, Any]:
        return {
            "max_rows": self.row_cap,
            "max_characters": self.char_cap,
            "timeout_seconds": self.timeout_seconds,
        }

    # -- querying ----------------------------------------------------------------------------

    def query(self, sql: str, *, row_cap: int | None = None) -> BoundedResult:
        """Run one statement under every bound this module documents.

        Args:
            sql: one SQL statement. Several are refused rather than run.
            row_cap: a tighter cap than `self.row_cap` for this call. It can only tighten.

        Raises:
            QueryRefused: the statement is not one this sandbox runs.
            QueryTimeout: it was still running at the deadline and was interrupted.
            CatalogError: DuckDB rejected it -- a bad column name, a missing table.
        """
        import duckdb  # noqa: PLC0415

        check_statement(sql)
        cap = self.row_cap if row_cap is None else min(self.row_cap, int(row_cap))

        watchdog = threading.Timer(self.timeout_seconds, self._con.interrupt)
        watchdog.daemon = True
        started = time.monotonic()
        watchdog.start()
        try:
            result = self._con.execute(sql)
            columns = [d[0] for d in result.description or []]
            # Read one more than the cap so truncation is *observed*, not inferred from a full page.
            fetched = result.fetchmany(cap + 1) if columns else []
        except duckdb.InterruptException as exc:
            raise QueryTimeout(
                f"query ran longer than {self.timeout_seconds:g} s and was stopped. Narrow it -- "
                f"add a WHERE on dataset_id, or aggregate instead of returning rows."
            ) from exc
        except duckdb.Error as exc:
            raise CatalogError(f"{exc}") from exc
        finally:
            watchdog.cancel()
        elapsed = time.monotonic() - started

        rows = [tuple(r) for r in fetched]
        truncated_by = None
        if len(rows) > cap:
            rows = rows[:cap]
            truncated_by = "rows"
        rows, truncated_by = self._apply_char_cap(columns, rows, truncated_by)
        return BoundedResult(
            columns=columns,
            rows=rows,
            truncated=truncated_by is not None,
            truncated_by=truncated_by,
            elapsed_seconds=elapsed,
            caps={**self.caps, "max_rows": cap},
        )

    def _apply_char_cap(
        self, columns: Sequence[str], rows: list[tuple], truncated_by: str | None
    ) -> tuple[list[tuple], str | None]:
        """Drop whole rows until the rendered result fits `char_cap`.

        Whole rows, never a truncated cell: half a peptidoform or half a UniProt accession is a
        value an agent can read and be wrong about, where a missing row is covered by the
        `truncated` flag it is handed alongside.
        """
        budget = self.char_cap - sum(len(str(c)) + 1 for c in columns)
        used = 0
        for i, row in enumerate(rows):
            used += sum(len(str(v)) + 1 for v in row)
            if used > budget:
                return rows[:i], "characters"
        return rows, truncated_by

    def one_value(self, sql: str, params: Sequence[Any] = ()) -> Any:
        """A single scalar, for the server's own bookkeeping queries. Not for caller SQL."""
        result = self._con.execute(sql, list(params)).fetchone()
        return None if result is None else result[0]

    def dicts(self, sql: str, params: Sequence[Any] = (), *, limit: int | None = None) -> list[dict]:
        """Rows as dicts, for the server's own queries. Not for caller SQL -- no watchdog, no caps.

        Everything this runs is written in this repository, so the bound that matters is the one the
        query itself carries. Callers that build a `LIMIT` from user input pass `limit` instead.
        """
        import duckdb  # noqa: PLC0415

        try:
            result = self._con.execute(sql, list(params))
            names = [d[0] for d in result.description or []]
            rows = result.fetchmany(limit) if limit is not None else result.fetchall()
        except duckdb.Error as exc:
            raise CatalogError(f"{exc}") from exc
        return [dict(zip(names, row)) for row in rows]

    def has_table(self, name: str) -> bool:
        """Is this table or view present? A catalog built before a table existed still is one."""
        return bool(
            self.one_value(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]
            )
        )

    def columns_of(self, name: str) -> list[str]:
        return [
            row["column_name"]
            for row in self.dicts(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position",
                [name],
            )
        ]
