"""The three tools (D12), their provenance (D13) and the honesty their bar demands (D15).

The `CatalogServer` methods are tested directly: the MCP SDK is an optional extra, and the tools
have to be provable without it. What `serve()` adds is the transport, and the one thing about it
that can silently drift -- the argument list an agent is shown against the argument list the method
takes -- is asserted here without importing it.

The theme of the file is the D15 bar: **zero silently-wrong answers**. Most of the tests below are
not about a tool returning the right rows. They are about a tool making the *shape* of its
ignorance visible -- an empty table named, a truncation flagged, a decoy marked, an absence scoped
to the datasets actually searched.
"""

from __future__ import annotations

import inspect
import json

import pytest

from datarepo.errors import CatalogError
from datarepo.mcp import (
    TOOL_PREFIX,
    TOOL_SPECS,
    CatalogServer,
    ToolError,
    _error_payload,
    bound_tools,
    install,
    install_entry,
    installed_entries,
)
from test_catalog import write_bundle  # noqa: F401 - tests/ is on the path (pyproject)


@pytest.fixture(scope="module")
def catalog(tmp_path_factory):
    from datarepo.catalog import build_catalog

    root = tmp_path_factory.mktemp("mcp")
    store = root / "store"
    bundles = [
        write_bundle(store, "PXD000001", ptm_sites=True),
        write_bundle(store, "PXD000002", accessions=("P11111", "P22222")),
        # A decoy accession in the protein list, because that is what a real search writes and
        # what `protein_index` therefore holds -- see the decoy test below.
        write_bundle(store, "PXD000003", accessions=("P22222", "DECOY_P22222")),
    ]
    return build_catalog(bundles, root / "catalog.duckdb", instance="test-instance").path


@pytest.fixture(scope="module")
def server(catalog):
    with CatalogServer(catalog) as instance:
        yield instance


# --- D13: every answer says which data it saw ---------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.describe(),
        lambda s: s.describe("tables"),
        lambda s: s.describe("psms"),
        lambda s: s.describe("Acquisition"),
        lambda s: s.search("P11111"),
        lambda s: s.search("nothing matches this"),
        lambda s: s.sql("SELECT 1"),
    ],
)
def test_every_result_carries_its_catalog_id(server, call):
    """D13. The failure this forecloses is one question answered twice, differently, with nothing
    in either result saying which data it saw."""
    provenance = call(server)["provenance"]
    assert provenance["catalog_id"]
    assert provenance["catalog_id"] == server.identity.catalog_id
    assert provenance["schema_version"]
    assert provenance["served_by"].startswith("datarepo ")
    assert provenance["n_bundles"] == len(server.identity.bundles)


def test_the_bundle_list_is_carried_once_in_the_overview_and_nowhere_else(server):
    """aging 070, DATAREPO-58: the 2-3 KB list on every answer buried the answer. catalog_id is
    the hash of that exact list, so it is the whole citation; the list itself is in describe()."""
    overview = server.describe()["provenance"]
    assert {b["bundle_id"] for b in overview["bundles"]} == {b["bundle_id"] for b in server.identity.bundles}
    for result in (server.sql("SELECT 1"), server.search("P11111"), server.describe("psms")):
        assert "bundles" not in result["provenance"]
        assert "catalog_id" in result["provenance"]["bundles_are"]


def test_sql_provenance_is_the_catalog_and_never_the_query(server):
    """It does NOT narrow to what an answer touched, and that is the fix, not a regression.

    Narrowing read the result's own `bundle_id`/`dataset_id` columns -- and a query can put
    anything in a column with those names. `SELECT max(dataset_id) AS dataset_id, count(*) FROM
    ptm_sites` returned a catalog-wide count stamped with one dataset's bundle, in the same words
    a correct narrowing uses. Provenance is now a fact about the server: same on every answer.
    """
    expected = server.sql("SELECT 1 AS n")["provenance"]
    for sql in (
        "SELECT dataset_id, bundle_id, count(*) FROM psms GROUP BY 1, 2",
        "SELECT * FROM psms WHERE dataset_id = 'PXD000001'",
        "SELECT max(dataset_id) AS dataset_id, count(*) AS n FROM psms",
    ):
        assert server.sql(sql)["provenance"] == expected, sql
    assert "describes the server" in expected["bundles_are"]



def test_provenance_says_whether_the_catalog_is_a_release(server):
    """A release is archived and never changes; a working build is rebuilt in place."""
    provenance = server.sql("SELECT 1")["provenance"]
    assert provenance["catalog_kind"] == "working build"
    assert "Cite a release" in provenance["catalog_kind_means"]
    assert provenance["catalog_id"]



def test_the_catalog_is_the_one_named_never_discovered(tmp_path):
    with pytest.raises(CatalogError, match="no catalog at"):
        CatalogServer(tmp_path / "nowhere.duckdb")


# --- D15: an empty table is named, not silently searched ---------------------------------------


def test_describe_separates_tables_with_rows_from_tables_without(server):
    overview = server.describe()
    assert "ptm_sites" in {row["table"] for row in overview["tables_with_rows"]}
    # Delivered by nobody yet: the organelle map is `go`'s (D1) and age effects are aging's.
    assert "protein_localizations" in overview["tables_empty"]
    assert "age_effects" in overview["tables_empty"]
    assert "not evidence that the thing does not exist" in overview["empty_means"]


def test_a_bookkeeping_table_is_not_reported_as_empty(server):
    """`catalog_tables` does not count itself, and an uncounted table must not read as an empty one."""
    overview = server.describe()
    for name in ("catalog_meta", "catalog_bundles", "catalog_tables"):
        assert name not in overview["tables_empty"]


def test_search_reports_what_it_searched_with_each_sources_row_count(server):
    result = server.search("mitochondria")
    assert result["total_hits"] == 0
    sources = {s["source"]: s for s in result["searched"]}
    assert sources["protein_localizations"]["rows"] == 0
    assert "protein_localizations" in result["searched_but_empty"]
    assert "not the same as the answer being no" in result["searched_but_empty_means"]


def test_no_hits_is_scoped_to_the_datasets_actually_held(server):
    """An absence from two datasets is not an absence from proteomics."""
    result = server.search("a string that appears nowhere")
    assert result["hits"] == {}
    assert "not all of PRIDE" in result["no_hits_means"]


def test_describing_an_empty_table_says_not_to_answer_from_another_one(server):
    described = server.describe("age_effects")
    assert described["rows"] == 0
    assert "say the data has not been delivered" in described["empty_means"]


def test_a_decoy_hit_is_marked_and_sorted_last_rather_than_hidden(server):
    """`proteins` is the search's protein LIST, so `protein_index` holds the decoys too.

    Hiding them would lose a fact about the search; showing them unmarked would read as two
    proteins. "LMNA, and also DECOY_LMNA" is a wrong answer produced entirely by presentation.
    """
    hits = server.search("GENE2", kind="protein")["hits"]["protein"]
    marked = {hit["protein_accession"]: hit["is_decoy"] for hit in hits}
    assert marked["P22222"] is False
    assert marked["DECOY_P22222"] is True
    assert [hit["is_decoy"] for hit in hits] == sorted(hit["is_decoy"] for hit in hits)
    source = next(s for s in server.search("GENE2")["searched"] if s["source"] == "protein_index")
    assert "not proteins" in source["note"]


def test_truncation_is_flagged_and_explained(server):
    result = server.sql("SELECT * FROM psms", max_rows=1)
    assert result["truncated"] and result["row_count"] == 1
    assert result["truncated_by"] == "rows"
    assert "NOT the whole answer" in result["truncated_means"]


def test_an_untruncated_answer_carries_no_truncation_language(server):
    result = server.sql("SELECT count(*) FROM psms")
    assert result["truncated"] is False
    assert "truncated_means" not in result


# --- describe -----------------------------------------------------------------------------------


def test_the_catalog_overview_leads_with_the_datasets_and_their_counts(server):
    overview = server.describe()
    assert [row["dataset_id"] for row in overview["datasets"]] == [
        "PXD000001", "PXD000002", "PXD000003",
    ]
    assert all(row["n_psms_1pct"] >= 1 for row in overview["datasets"])
    assert overview["instance"] == "test-instance"


def test_a_columns_meaning_comes_from_the_schema_not_from_a_second_copy(server):
    """The description an agent reads is generated from `schema/datarepo.yaml` (G1 drift rule)."""
    from datarepo._schema_docs import TABLE_DOCS

    described = server.describe("psms", detail="detailed")
    means = {column["column"]: column.get("means") for column in described["columns"]}
    assert means["scan"] == TABLE_DOCS["psms"]["columns"]["scan"]["description"]
    assert means["usi"] == TABLE_DOCS["psms"]["columns"]["usi"]["description"]


def test_the_provenance_columns_build_adds_are_described_too(server):
    """`dataset_id` and `bundle_id` are not in the schema; they are why an answer is traceable."""
    described = server.describe("psms", detail="detailed")
    means = {column["column"]: column.get("means") for column in described["columns"]}
    assert "provenance added by" in means["dataset_id"]
    assert "provenance added by" in means["bundle_id"]


def test_column_types_are_the_catalogs_own(server):
    described = server.describe("datasets", detail="detailed")
    types = {column["column"]: column["type"] for column in described["columns"]}
    assert types["dataset_id"] == "VARCHAR"
    assert types["organisms"] == "VARCHAR[]"  # how a WHERE against it has to be written


def test_concise_keeps_every_fact_and_spends_fewer_tokens(server):
    """Concise renders a column as one line. It must not DROP the meaning -- only the braces."""
    concise = server.describe("datasets", detail="concise")
    detailed = server.describe("datasets", detail="detailed")
    assert len(concise["columns"]) == len(detailed["columns"])
    assert all(isinstance(line, str) for line in concise["columns"])
    acquisition = next(line for line in concise["columns"] if line.startswith("acquisition "))
    assert "Acquisition mode." in acquisition
    assert "DDA, DIA, PRM, mixed" in acquisition
    assert len(json.dumps(concise["columns"])) < len(json.dumps(detailed["columns"]))


def test_an_enum_is_describable_by_name(server):
    described = server.describe("Acquisition")
    assert described["values"] == ["DDA", "DIA", "PRM", "mixed"]


def test_a_definition_id_returns_the_published_text(server):
    described = server.describe("PROVISIONAL:PROTEIN-INTENSITY")
    assert described["text"] == "test"
    assert described["provisional"] is True


def test_the_acceptance_views_are_pointed_at_from_the_table_they_filter(server):
    """A caller who finds `psms` before `psms_1pct` would restate the acceptance rule and get it
    slightly wrong -- which is D15's silently-wrong answer, arrived at honestly."""
    assert "psms_1pct" in server.describe("psms")["see_also"]


def test_an_unknown_target_is_refused_with_a_suggestion(server):
    with pytest.raises(ToolError, match="Did you mean"):
        server.describe("psm")  # singular; the table is `psms`


def test_an_unknown_target_with_no_near_match_still_says_what_to_call(server):
    with pytest.raises(ToolError, match="'tables' for the full list"):
        server.describe("zzzzzzzz")


def test_detail_is_validated(server):
    with pytest.raises(ToolError, match="concise"):
        server.describe("psms", detail="verbose")


def test_tables_lists_every_table_with_what_it_holds(server):
    listing = server.describe("tables")
    rows = {row["table"]: row for row in listing["tables"]}
    assert rows["psms"]["holds"] == "One peptide-spectrum match."
    assert rows["psms_1pct"]["kind"] == "view"
    assert rows["protein_index"]["kind"] == "derived"


# --- search ---------------------------------------------------------------------------------


def test_a_gene_symbol_finds_its_accession(server):
    hits = server.search("GENE1")["hits"]["protein"]
    assert "P11111" in {hit["protein_accession"] for hit in hits}


def test_an_accession_finds_the_datasets_it_passed_in(server):
    hit = next(
        h for h in server.search("P11111", kind="protein")["hits"]["protein"]
        if h["protein_accession"] == "P11111"
    )
    assert hit["n_datasets_1pct"] == 2


def test_a_dataset_accession_finds_the_dataset(server):
    hits = server.search("PXD000001", kind="dataset")["hits"]["dataset"]
    assert [hit["dataset_id"] for hit in hits] == ["PXD000001"]


def test_a_peptide_sequence_is_looked_up_as_one(server):
    hits = server.search("PEPTIDEK", kind="peptide")["hits"]["peptide"]
    assert hits[0]["base_sequence"] == "PEPTIDEK"


def test_a_short_word_is_not_treated_as_a_peptide(server):
    """'CAT' is three amino-acid letters and a word. The peptide index is not asked about words."""
    result = server.search("CAT", kind="peptide")
    source = next(s for s in result["searched"] if s["source"] == "peptide_index")
    assert "not searched" in source["note"]


def test_a_modification_is_found_by_its_engine_name(server):
    hits = server.search("Phosphoserine", kind="modification")["hits"]["modification"]
    assert any(hit.get("modification_name") == "Phosphoserine on S" for hit in hits)


def test_a_modification_search_says_which_table_declared_and_which_placed(server):
    """G31's distinction, carried into the tool: declared is not placed."""
    sources = {s["source"] for s in server.search("phospho", kind="modification")["searched"]}
    assert "ptm_sites" in sources
    assert sources & {"search_modifications_declared", "search_modifications"}


def test_an_unknown_kind_is_refused_with_the_list(server):
    with pytest.raises(ToolError, match="localization"):
        server.search("x", kind="organelle")


def test_an_empty_query_is_refused(server):
    with pytest.raises(ToolError, match="something to look for"):
        server.search("   ")


def test_the_limit_is_capped(server):
    result = server.search("P11111", limit=100000)
    assert result["total_hits"] <= 200


# --- sql ------------------------------------------------------------------------------------


def test_sql_returns_columns_and_rows(server):
    result = server.sql("SELECT dataset_id, count(*) AS n FROM psms GROUP BY 1 ORDER BY 1")
    assert result["columns"] == ["dataset_id", "n"]
    assert [row[0] for row in result["rows"]] == ["PXD000001", "PXD000002", "PXD000003"]


def test_sql_reports_the_limits_in_force(server):
    limits = server.sql("SELECT 1")["limits"]
    assert limits["max_rows"] and limits["max_characters"] and limits["timeout_seconds"]


def test_a_refusal_becomes_an_answerable_error_not_a_stack_trace(server):
    """An agent that gets `{error, message, hint}` can fix its call. A transport error tells it
    only that something went wrong."""
    _, sql_tool = next(pair for pair in bound_tools(server) if pair[0]["method"] == "sql")
    payload = sql_tool(query="DROP TABLE psms")
    assert payload["error"] == "QueryRefused"
    assert "read-only" in payload["hint"]


def test_every_error_payload_carries_a_hint():
    for error in (ToolError("x"), CatalogError("y")):
        assert _error_payload(error)["hint"]


# --- the tools as an agent sees them ------------------------------------------------------------


def test_three_tools_ship_and_no_more(server):
    """D12: three tools, and a fourth only where aging's benchmark shows a specific wrong answer."""
    assert [spec["name"] for spec in TOOL_SPECS] == [
        f"{TOOL_PREFIX}describe",
        f"{TOOL_PREFIX}search",
        f"{TOOL_PREFIX}sql",
    ]


def test_the_tool_an_agent_sees_takes_exactly_what_the_method_takes(server):
    """The one thing that can drift silently between the server and the transport.

    An argument added to a method but not to its wrapper is invisible to every agent; one added to
    the wrapper but not the method is a TypeError at call time. Neither shows up in a smoke test.
    """
    for spec, function in bound_tools(server):
        method = getattr(CatalogServer, spec["method"])
        expected = list(inspect.signature(method).parameters.values())[1:]  # drop `self`
        actual = list(inspect.signature(function).parameters.values())
        assert [(p.name, p.annotation, p.default) for p in actual] == [
            (p.name, p.annotation, p.default) for p in expected
        ], spec["name"]


def test_every_tool_describes_itself_to_an_agent(server):
    for spec in TOOL_SPECS:
        assert len(spec["description"]) > 200, spec["name"]
        assert spec["title"]
        assert hasattr(CatalogServer, spec["method"])


def test_the_sql_tools_description_states_the_caps_it_actually_enforces():
    """An agent told '1,000 rows' and capped at 100 would draw conclusions from a silent cut."""
    from datarepo.sandbox import CHAR_CAP, ROW_CAP, TIMEOUT_SECONDS

    description = next(s for s in TOOL_SPECS if s["method"] == "sql")["description"]
    assert f"{ROW_CAP:,}" in description
    assert f"{CHAR_CAP:,}" in description
    assert f"{TIMEOUT_SECONDS:g} s" in description


# --- --install ----------------------------------------------------------------------------------


def test_install_writes_a_config_that_names_the_catalog_absolutely(catalog, tmp_path):
    config = tmp_path / "claude.json"
    result = install(catalog, config=config)
    assert result["action"] == "added"
    document = json.loads(config.read_text(encoding="utf-8"))
    args = document["mcpServers"]["datarepo"]["args"]
    assert args[:3] == ["-m", "datarepo.cli", "mcp"]
    assert args[args.index("--catalog") + 1] == str(catalog.resolve())


def test_installing_twice_is_a_no_op(catalog, tmp_path):
    config = tmp_path / "claude.json"
    install(catalog, config=config)
    assert install(catalog, config=config)["action"] == "unchanged"


def test_install_refuses_to_repoint_a_name_it_did_not_write(catalog, tmp_path):
    config = tmp_path / "claude.json"
    config.write_text(
        json.dumps({"mcpServers": {"datarepo": {"command": "x", "args": ["--catalog", "other"]}}}),
        encoding="utf-8",
    )
    with pytest.raises(ToolError, match="--force"):
        install(catalog, config=config)
    assert install(catalog, config=config, force=True)["action"] == "updated"


def test_install_keeps_the_rest_of_the_config(catalog, tmp_path):
    """This file is the user's whole Claude Code state, not ours."""
    config = tmp_path / "claude.json"
    config.write_text(
        json.dumps({"theme": "dark", "mcpServers": {"other": {"command": "y", "args": []}}}),
        encoding="utf-8",
    )
    install(catalog, config=config)
    document = json.loads(config.read_text(encoding="utf-8"))
    assert document["theme"] == "dark"
    assert set(document["mcpServers"]) == {"other", "datarepo"}


def test_install_refuses_a_config_it_cannot_parse(catalog, tmp_path):
    config = tmp_path / "claude.json"
    config.write_text("{not json", encoding="utf-8")
    with pytest.raises(ToolError, match="not valid JSON"):
        install(catalog, config=config)


def test_install_refuses_a_catalog_that_is_not_there(tmp_path):
    with pytest.raises(CatalogError, match="nothing to serve"):
        install(tmp_path / "missing.duckdb", config=tmp_path / "claude.json")


def test_several_catalogs_can_be_registered_under_different_names(catalog, tmp_path):
    config = tmp_path / "claude.json"
    install(catalog, config=config)
    install(catalog, name="datarepo-release", config=config)
    assert set(installed_entries(config)) == {"datarepo", "datarepo-release"}


def test_installed_entries_ignores_servers_that_are_not_ours(tmp_path):
    config = tmp_path / "claude.json"
    config.write_text(
        json.dumps({"mcpServers": {"somebody-else": {"command": "z", "args": ["--x"]}}}),
        encoding="utf-8",
    )
    assert installed_entries(config) == {}


def test_the_entry_runs_the_module_not_a_script_on_the_path(catalog):
    """`datarepo` may not be on the client's PATH; the interpreter that installed it always is."""
    entry = install_entry(catalog)
    assert entry["command"].endswith(("python", "python.exe", "pythonw.exe"))
    assert entry["args"][:2] == ["-m", "datarepo.cli"]


# --- what the agents broke: the D15 bar, measured rather than designed -------------------------
#
# Every test below names a specific wrong answer two agents produced against 0.10.0 on aging's real
# catalog. They are the regression suite for the bar, not for the code: each asserts that the SHAPE
# of an answer makes a falsehood harder to state, which is what D15 asks for and what a row-level
# assertion cannot check.


def test_sql_names_the_empty_tables_a_query_touched(server):
    """The guard that earned its place: `describe` and `search` had it, `sql` did not."""
    result = server.sql(
        "SELECT a.feature_id FROM age_effects a "
        "JOIN organelle_age_summaries o ON a.feature_id = o.compartment"
    )
    assert result["row_count"] == 0
    assert set(result["empty_tables"]) == {"age_effects", "organelle_age_summaries"}
    assert "never evidence for a negative answer" in result["empty_tables_mean"]


def test_the_empty_table_warning_does_not_assert_a_cause_it_has_not_checked(server):
    """It used to say "this result is empty because there is nothing to query" and instruct the
    caller to report non-delivery -- on a query that returned nothing because the filter matched
    nothing. A warning that asserts an unchecked reason is the failure it was written to prevent."""
    result = server.sql(
        "SELECT p.protein_accession FROM proteins p "
        "LEFT JOIN protein_localizations l USING (protein_accession) "
        "WHERE p.protein_accession = 'NOTAREALACCESSION'"
    )
    assert result["row_count"] == 0
    assert result["empty_tables"] == ["protein_localizations"]
    assert "depends on the query" in result["empty_tables_mean"]
    assert "Say the data has not been delivered" not in result["empty_tables_mean"]



def test_tables_touched_sees_through_aliases_and_ctes(server):
    """Parsed from DuckDB's own serialization, so a name in a string literal is not a table."""
    touched = {
        t["table"]
        for t in server.sql("WITH t AS (SELECT * FROM psms) SELECT count(*) FROM t")[
            "tables_touched"
        ]
    }
    assert touched == {"psms"}
    assert server.sql("SELECT 'age_effects' AS x")["tables_touched"] == []


def test_a_populated_query_still_names_an_empty_table_it_joined(server):
    result = server.sql(
        "SELECT p.protein_accession, l.compartment FROM proteins p "
        "LEFT JOIN protein_localizations l ON l.protein_accession = p.protein_accession LIMIT 5"
    )
    assert result["row_count"] > 0
    assert result["empty_tables"] == ["protein_localizations"]



def test_a_forged_bundle_id_changes_nothing(server):
    """The old patch rejected UNKNOWN ids and let a real one narrow. Now neither does anything."""
    plain = server.sql("SELECT count(*) AS n FROM psms")["provenance"]
    forged = server.sql("SELECT 'deadbeefdeadbeef' AS bundle_id, count(*) AS n FROM psms")
    real = server.sql("SELECT 'PXD000001' AS dataset_id, count(*) AS n FROM psms")
    for result in (forged, real):
        assert result["provenance"] == plain



def test_a_cte_named_after_a_real_table_certifies_nothing(server):
    """The 0.11.0 hole, and the reason `tables_touched` is a hint rather than evidence.

    `WITH protein_groups_1pct AS (SELECT 99999)` read no catalog bytes and came back certified as
    having read the real view's rows, with a bundle id attached. Naming a working table after the
    thing it relates to needs no adversary.
    """
    result = server.sql(
        "WITH psms AS (SELECT 'PXD000001' AS dataset_id, 99999 AS n) SELECT * FROM psms"
    )
    assert result["rows"] == [["PXD000001", 99999]]
    assert result["tables_touched"] == [], "a CTE name must not be reported as a table read"
    assert "empty_tables" not in result
    assert result["provenance"] == server.sql("SELECT 1")["provenance"]


def test_an_unparseable_read_says_unknown_not_none(server):
    """`query_table('x')` takes its target as a string, so no table node exists to find.

    Returning `[]` here read as "touches nothing" -- the silently-wrong shape exactly.
    """
    result = server.sql("SELECT count(*) FROM query_table('psms')")
    assert result["tables_touched"] is None
    assert "not a claim that none were" in result["tables_touched_undetermined"]
    assert "empty_tables" not in result



def test_search_provenance_covers_every_bundle_that_fed_a_visible_number(server):
    """`n_datasets: 3` beside a two-bundle provenance block. No trickery needed to produce it."""
    hits = server.search("P11111", kind="protein")
    hit = next(h for h in hits["hits"]["protein"] if h["protein_accession"] == "P11111")
    assert hits["provenance"]["catalog_id"] == server.identity.catalog_id
    assert set(hit["dataset_ids"]) <= {
        b["dataset_id"] for b in server.describe()["provenance"]["bundles"]
    }, "a dataset counted in the row is missing from the catalog the provenance names"


def test_a_column_that_is_null_on_every_row_says_so(server):
    """`searched_but_empty` fires on `rows == 0`, so a 100%-NULL column was invisible to it."""
    described = server.describe("samples", detail="detailed")
    by_name = {c["column"]: c for c in described["columns"]}
    assert by_name["organism"]["populated"] > 0
    assert by_name["disease"]["populated"] == 0
    assert "not because the answer is negative" in by_name["disease"]["all_null"]


def test_the_concise_form_carries_the_all_null_warning_too(server):
    """An agent that asked for `concise` did not ask to be misled."""
    line = next(
        line for line in server.describe("samples")["columns"] if line.startswith("disease ")
    )
    assert "NULL on all" in line


def test_search_names_the_columns_it_matched_and_which_were_empty(server):
    """`rows: 57, hits: 0` reads as a considered negative when the columns are all NULL."""
    result = server.search("plasma", kind="sample")
    source = next(s for s in result["searched"] if s["source"] == "samples")
    assert "disease" in source["columns_searched"]
    assert "disease" in source["columns_all_null"]
    assert "missing data, not a negative answer" in source["columns_all_null_mean"]


def test_a_protein_name_query_says_names_are_not_searchable(server):
    """38,002 rows searched, 0 hits, no caveat -- while the gene was sitting right there."""
    source = next(
        s
        for s in server.search("cytochrome c oxidase", kind="protein")["searched"]
        if s["source"] == "protein_index"
    )
    assert "no protein name or description column" in source["note"]
    assert source["columns_searched"] == ["protein_accession", "gene"]


def test_the_derived_tables_are_documented_like_the_schema_ones(server):
    """`describe('protein_index')` returned `one_row_is: null` and zero column meanings.

    These are the tables `search` answers from. An undocumented column gets read as whatever its
    name suggests, which is how `n_datasets_1pct` became "identified at 1% FDR".
    """
    described = server.describe("protein_index", detail="detailed")
    assert "search's protein DATABASE" in described["one_row_is"]
    means = {c["column"]: c.get("means") or "" for c in described["columns"]}
    assert "NOT 'identified at 1% protein FDR'" in means["n_datasets_1pct"]
    assert "different levels" in means["best_q_value"]


def test_the_acceptance_views_state_the_rule_they_apply(server):
    """The tool description promises the views apply the rule; the rule was printed nowhere."""
    assert "q_value_notch" in server.describe("psms_1pct")["one_row_is"]
    assert "No notch-resolution clause" in server.describe("peptidoforms_1pct")["one_row_is"]
    assert "CONTAMINANTS ARE INCLUDED" in server.describe("protein_groups_1pct")["one_row_is"]


def test_a_study_layer_with_no_delivery_is_reported_as_present_and_empty(server):
    """`study_layers: []` read as "there is no study layer" and contradicted describe('tables')."""
    layers = {entry["layer"]: entry for entry in server.describe()["study_layers"]}
    assert layers["aging"]["tables_present"] == 8
    assert layers["aging"]["delivery_loaded"] is False
    assert layers["aging"]["rows"] == 0


def test_search_says_when_it_cut_the_list_off(server):
    """`search("KRT")` returned `total_hits: 25` beside `rows: 38002` when 232 matched.

    `SEARCH_LIMIT`'s own comment called it "how many hits one kind returns before it says there are
    more". It never said. A list whose length is read as a count is a wrong answer with no author.
    """
    result = server.search("GENE2", kind="protein", limit=1)
    assert result["truncated_kinds"] == ["protein"]
    assert "is NOT a count" in result["truncated_means"]
    assert len(result["hits"]["protein"]) == 1


def test_an_uncut_search_carries_no_truncation_language(server):
    result = server.search("P11111", kind="protein", limit=25)
    assert "truncated_kinds" not in result


def test_the_protein_caveat_fires_on_every_hit_not_only_the_zero_ones(server):
    """It used to fire only when EVERY hit had `n_datasets_1pct = 0` -- so never when it mattered.

    `EIF1AY` comes back `n_datasets_1pct: 2` and is in zero accepted protein groups.
    """
    for query in ("P11111", "GENE2"):
        source = next(
            s for s in server.search(query, kind="protein")["searched"]
            if s["source"] == "protein_index"
        )
        assert "NOT 'identified at 1% protein FDR'" in source["note"], query


def test_prose_generated_from_a_different_schema_says_so(server, monkeypatch):
    """Serving a 0.0.5 catalog from 0.0.7 code, `describe` narrated the contaminant fix in the past
    tense and pointed at a column that catalog does not have, while printing a populated count that
    contradicted the same sentence. An agent that called `describe` first came away more confident
    and more wrong."""
    assert server.schema_drift is None, "fixture catalog and code should agree"
    monkeypatch.setattr(server.identity, "schema_version", "0.0.1")
    assert "THE CATALOG IS RIGHT" in server.schema_drift
    assert "schema_drift" in server.describe("psms")
    assert "schema_drift" in server.describe()
    assert "schema_drift" in server.describe("Acquisition")


# --- G70: `pep` is run-relative (pep 002) ----------------------------------------------------------


def test_a_query_reading_pep_is_told_it_is_run_relative(server):
    """`median(pep) GROUP BY dataset_id` reads as a comparison of datasets and is not one: each
    search trains its own PEP model. The note is in the sql envelope because describe can be skipped."""
    result = server.sql("SELECT dataset_id, median(pep) FROM psms GROUP BY 1")
    assert list(result["run_relative_columns"]) == ["pep"]
    assert "Do not compare their values across datasets" in result["run_relative_means"]
    assert "pep:DEF-PEP" in result["run_relative_means"]


@pytest.mark.parametrize(
    "query, expected",
    [
        ("SELECT p.pep AS score FROM psms p", ["pep"]),  # renamed: the result column says nothing
        ("SELECT * FROM psms LIMIT 1", ["pep", "pep_q_value"]),  # a star over a table that holds them
        ("SELECT count(*) FROM peptidoforms WHERE best_pep < 0.01", ["best_pep"]),  # filter only
        ("WITH t AS (SELECT pep_q_value AS x FROM psms) SELECT count(*) FROM t", ["pep_q_value"]),
    ],
)
def test_the_run_relative_note_sees_through_aliases_stars_and_ctes(server, query, expected):
    assert sorted(server.sql(query)["run_relative_columns"]) == expected


@pytest.mark.parametrize(
    "query",
    [
        "SELECT dataset_id, count(*) FROM psms WHERE q_value <= 0.01 GROUP BY 1",
        "SELECT * FROM datasets",  # a star over a table with no PEP column
    ],
)
def test_a_query_that_reads_no_pep_carries_no_pep_language(server, query):
    assert "run_relative_columns" not in server.sql(query)


def test_the_pep_columns_describe_themselves_as_run_relative(server):
    means = {c["column"]: c.get("means") or "" for c in server.describe("psms", detail="detailed")["columns"]}
    assert "RUN-RELATIVE" in means["pep"]
    assert "moves whenever `pep` does" in means["pep_q_value"]
    assert "does not depend on PEP" in means["q_value"]


def test_a_replaced_catalog_file_is_announced_not_silently_served(catalog, tmp_path):
    """aging 070, 57k: a server served `62d419643e71320c` for hours after `1e2f13be6f121fd7` was
    published over the same path. It keeps what it opened, and now says so."""
    import os
    import shutil

    copy = tmp_path / "catalog.duckdb"
    shutil.copyfile(catalog, copy)
    with CatalogServer(copy) as instance:
        assert "catalog_file_changed" not in instance.sql("SELECT 1")["provenance"]
        stat = os.stat(copy)
        os.utime(copy, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000_000))
        warning = instance.sql("SELECT 1")["provenance"]["catalog_file_changed"]
        assert instance.identity.catalog_id in warning and "Restart" in warning


def test_the_first_answer_names_the_rules_agents_otherwise_learn_by_failing(server):
    """aging 070 57h/57i: the contaminant value of target_decoy and the sorted group id were
    reachable only by querying, and the first answer is the one every agent reads."""
    rules = " ".join(server.describe()["read_first"])
    for fact in ("THREE values", "per dataset", "searched protein database", "not a leading", "run-relative"):
        assert fact in rules, fact
    means = {c["column"]: c.get("means") or "" for c in server.describe("protein_groups", detail="detailed")["columns"]}
    assert "SORTED" in means["protein_group_id"]


def test_a_tissue_named_without_a_term_is_found_and_described(tmp_path):
    """G74: `describe('samples')` explains the `_name` columns, and `search` reads them."""
    from datarepo.catalog import build_catalog

    store = tmp_path / "store"
    bundle = write_bundle(store, "PXD000001", characteristics=(("characteristics[organism part]", "heart"),))
    path = build_catalog([bundle], tmp_path / "catalog.duckdb").path
    with CatalogServer(path) as server:
        means = {c["column"]: c.get("means") or "" for c in server.describe("samples", detail="detailed")["columns"]}
        assert "G74" in means["organism_part_name"] and "not available" in means["organism_part_name"]
        hit = next(h for h in server.search("heart", kind="sample")["hits"]["sample"] if "n_samples" in h)
        assert hit["organism_part_names"] == ["heart"] and not hit["organism_parts"]
