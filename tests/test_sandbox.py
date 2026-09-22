"""The bounded connection (D14 stage one).

Most of these assert something about **DuckDB**, not about our code, and that is the point: D14's
choices rest on measurements, and a measurement nobody re-runs becomes a belief. If a future DuckDB
re-enables external access through `SET`, or stops refusing `ATTACH` once `LocalFileSystem` is
disabled, the sandbox stops bounding anything and these fail rather than the server quietly serving
a hole.
"""

from __future__ import annotations

import time

import duckdb
import pytest

from datarepo.errors import CatalogError, QueryRefused, QueryTimeout
from datarepo.sandbox import CONNECT_CONFIG, Sandbox
from test_catalog import write_bundle  # noqa: F401 - tests/ is on the path (pyproject)

# A cross join that DuckDB cannot answer from metadata. `SELECT count(*) FROM range(3e9)`, the
# probe D14 was written against, now returns in half a second on 1.5.5 -- an optimiser caught up
# with the test and the test said nothing.
SLOW_QUERY = (
    "SELECT count(*) FROM (SELECT a.range, b.range FROM range(200000) a, range(200000) b "
    "WHERE (a.range * b.range) % 7 = 3)"
)


@pytest.fixture(scope="module")
def catalog(tmp_path_factory):
    """Built once for the module: nothing here writes to it, and a build costs over a second."""
    from datarepo.catalog import build_catalog

    root = tmp_path_factory.mktemp("sandbox")
    store = root / "store"
    bundles = [write_bundle(store, "PXD000001"), write_bundle(store, "PXD000002")]
    return build_catalog(bundles, root / "catalog.duckdb").path


@pytest.fixture(scope="module")
def box(catalog):
    with Sandbox(catalog) as sandbox:
        yield sandbox


@pytest.fixture
def unopened_catalog(catalog, tmp_path):
    """A copy of the catalog that no `Sandbox` has opened in this process.

    Two measured facts make this necessary, and both are worth knowing beyond the tests:

    * `disabled_filesystems` is a property of the **database instance**, not of the connection.
      DuckDB hands every connection to one file in one process the same instance, so a second
      connection inherits the lock -- and `current_setting('disabled_filesystems')` then reports
      `''` while the lock is in force, so it cannot even be read back.
    * DuckDB refuses a second connection to an open file *with a different config* outright
      ("Can't open a connection to same database file with a different configuration").

    So the two tests below, which need a raw connection to show what the sandbox is protecting
    against, get their own file rather than a second connection to a guarded one.
    """
    import shutil

    copy = tmp_path / "unopened.duckdb"
    shutil.copy(catalog, copy)
    return copy


@pytest.fixture
def outside_file(tmp_path):
    """A file outside the store, which is what the sandbox must not be able to read."""
    path = tmp_path / "secret.csv"
    path.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    return path


# --- what read_only does NOT do ----------------------------------------------------------------


def test_read_only_alone_is_not_a_sandbox(unopened_catalog, outside_file):
    """The measurement D14 rests on. If this ever fails, the sandbox has become unnecessary."""
    with duckdb.connect(str(unopened_catalog), read_only=True) as con:
        assert con.execute(
            f"SELECT count(*) FROM read_csv_auto('{outside_file.as_posix()}')"
        ).fetchone() == (2,)


def test_sandbox_cannot_read_a_file_outside_the_catalog(box, outside_file):
    with pytest.raises(CatalogError, match="disabled"):
        box.query(f"SELECT * FROM read_csv_auto('{outside_file.as_posix()}')")


def test_external_access_cannot_be_re_enabled_from_inside(unopened_catalog):
    """`enable_external_access` is one-way once the database is running -- so a query cannot undo it."""
    with duckdb.connect(str(unopened_catalog), read_only=True, config=dict(CONNECT_CONFIG)) as con:
        for statement in (
            "SET enable_external_access=true",
            "PRAGMA enable_external_access=true",
            "RESET enable_external_access",
        ):
            with pytest.raises(duckdb.Error, match="while database is running"):
                con.execute(statement)


def test_external_access_off_still_leaves_attach_open(unopened_catalog):
    """Why `disabled_filesystems` is also set: this is the hole `enable_external_access` leaves.

    An ATTACHed database would let a query answer from rows that are not in this catalog, under a
    result labelled with this catalog's `catalog_id`. That is a D13 violation before it is a
    security one, which is why it is closed even though the local agent already has the filesystem.
    """
    with duckdb.connect(str(unopened_catalog), read_only=True, config=dict(CONNECT_CONFIG)) as con:
        con.execute(f"ATTACH '{unopened_catalog.as_posix()}' AS other (READ_ONLY)")
        assert con.execute("SELECT count(*) FROM other.datasets").fetchone()[0] >= 1


def test_sandbox_refuses_to_attach_another_database(box, catalog):
    with pytest.raises(QueryRefused, match="ATTACH"):
        box.query(f"ATTACH '{catalog.as_posix()}' AS other (READ_ONLY)")


def test_the_open_catalog_still_serves_with_the_filesystem_disabled(box):
    """Disabling `LocalFileSystem` must not break the catalog that is already open."""
    assert box.query("SELECT count(*) FROM psms").rows[0][0] >= 2
    assert box.query("SELECT dataset_id, count(*) FROM psms_1pct GROUP BY 1").row_count == 2


# --- what it refuses by name -------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        "DROP TABLE psms",
        "CREATE TABLE x AS SELECT 1",
        "DELETE FROM psms",
        "UPDATE psms SET scan = 2",
        "INSTALL httpfs",
        "LOAD httpfs",
        "COPY (SELECT 1) TO 'out.csv'",
    ],
)
def test_only_questions_are_run(box, statement):
    with pytest.raises(QueryRefused):
        box.query(statement)


def test_several_statements_are_refused_rather_than_run(box):
    """One question, one answer. A `SET ...; SELECT ...` pair would answer under changed settings."""
    with pytest.raises(QueryRefused, match="2 statements"):
        box.query("SELECT 1; SELECT 2")


def test_a_refusal_says_what_to_send_instead(box):
    with pytest.raises(QueryRefused) as caught:
        box.query("DROP TABLE psms")
    assert "SELECT" in str(caught.value)


def test_unparseable_sql_is_refused_not_raised_as_a_catalog_error(box):
    with pytest.raises(QueryRefused, match="not valid SQL"):
        box.query("this is not sql")


def test_explain_and_show_are_allowed(box):
    assert box.query("EXPLAIN SELECT * FROM psms").row_count >= 1
    assert box.query("SHOW TABLES").row_count >= 1


def test_a_bad_column_is_a_catalog_error_with_duckdbs_own_message(box):
    with pytest.raises(CatalogError, match="nope"):
        box.query("SELECT nope FROM psms")


# --- the caps ----------------------------------------------------------------------------------


def test_the_row_cap_is_observed_not_inferred(catalog):
    """A result exactly at the cap must still be flagged: `truncated` is read one row past it."""
    with Sandbox(catalog, row_cap=1) as box:
        result = box.query("SELECT dataset_id FROM datasets")
        assert result.row_count == 1
        assert result.truncated and result.truncated_by == "rows"


def test_a_result_inside_the_cap_is_not_flagged(catalog):
    with Sandbox(catalog, row_cap=10) as box:
        result = box.query("SELECT dataset_id FROM datasets")
        assert result.row_count == 2
        assert not result.truncated


def test_the_character_cap_drops_whole_rows(catalog):
    """Never half a value: a truncated peptidoform is a value an agent can read and be wrong about."""
    with Sandbox(catalog, char_cap=60) as box:
        result = box.query("SELECT psm_id, usi, peptidoform FROM psms")
        assert result.truncated and result.truncated_by == "characters"
        assert all(len(row) == 3 for row in result.rows)


def test_the_caps_in_force_are_reported_with_the_result(catalog):
    with Sandbox(catalog, row_cap=5, char_cap=500, timeout_seconds=7) as box:
        caps = box.query("SELECT 1").caps
        assert caps == {"max_rows": 5, "max_characters": 500, "timeout_seconds": 7.0}


def test_max_rows_can_only_tighten_the_cap(catalog):
    with Sandbox(catalog, row_cap=1) as box:
        assert box.query("SELECT dataset_id FROM datasets", row_cap=100).caps["max_rows"] == 1


# --- the watchdog ------------------------------------------------------------------------------


def test_a_long_query_is_stopped_at_the_deadline(catalog):
    with Sandbox(catalog, timeout_seconds=1) as box:
        started = time.monotonic()
        with pytest.raises(QueryTimeout, match="Narrow it"):
            box.query(SLOW_QUERY)
        assert time.monotonic() - started < 20  # generous: the point is that it stopped at all


def test_the_connection_survives_an_interrupt(catalog):
    """An interrupted query must not cost the session: the next question still gets an answer."""
    with Sandbox(catalog, timeout_seconds=1) as box:
        with pytest.raises(QueryTimeout):
            box.query(SLOW_QUERY)
        assert box.query("SELECT count(*) FROM datasets").rows == [(2,)]


def test_the_watchdog_does_not_fire_on_a_fast_query(catalog):
    with Sandbox(catalog, timeout_seconds=30) as box:
        for _ in range(3):
            assert box.query("SELECT count(*) FROM psms").row_count == 1


def test_no_catalog_is_an_error_an_operator_can_act_on(tmp_path):
    with pytest.raises(CatalogError, match="no catalog at"):
        Sandbox(tmp_path / "missing.duckdb")
