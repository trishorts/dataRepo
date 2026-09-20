"""The study layer: tables a consumer project adds on top of the generic core.

The rule (U5) is that a study layer ADDS tables keyed on core identifiers and never alters a core
table, so these tests are mostly about the boundary holding: the core must stay complete and usable
without the layer, and the layer must not shadow anything.

Nothing writes these tables yet. `age_effect` is the output of a modelling stage that runs long
after a search, and how those rows reach a bundle is DATAREPO-20. What is under test is the SHAPE --
which is the deliverable, because aging's benchmark distinguishes NO_TABLE from EMPTY_TABLE and the
46 questions that need an age effect currently score the first.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from datarepo._tables import STUDY_TABLES, STUDY_VERSIONS, TABLES
from datarepo.catalog import (
    ACCEPTED_VIEWS,
    DERIVED_TABLES,
    GRAIN_VIEWS,
    build_catalog,
    run_query,
)
from datarepo.integrity import IDENTIFIERS, STUDY_COMPOSITE_IDENTIFIERS

from test_catalog import rows, write_bundle

AGING = "aging"


@pytest.fixture
def store(tmp_path):
    return tmp_path / "store"


def _fields(table: str) -> dict[str, pa.Field]:
    return {f.name: f for f in STUDY_TABLES[AGING][table]}


# --- the layer exists and is generated, not hand-written ------------------------------------------


def test_the_aging_layer_declares_its_tables():
    assert AGING in STUDY_VERSIONS
    assert set(STUDY_TABLES[AGING]) == {
        "sample_ages",
        "age_effects",
        "age_effect_refusals",
        "age_effect_meta",
        "organelle_age_summaries",
        "clock_models",
        "clock_features",
        "age_mappings",
    }


def test_a_study_layer_never_shadows_a_core_table():
    core = set(TABLES) | set(DERIVED_TABLES) | set(ACCEPTED_VIEWS) | set(GRAIN_VIEWS)
    for layer, tables in STUDY_TABLES.items():
        clash = core & set(tables)
        assert not clash, f"study layer {layer} shadows core {sorted(clash)}"


def test_the_core_is_complete_without_the_layer():
    # U5: a consumer that is not aging gets the whole core and none of this.
    assert not set(TABLES) & set(STUDY_TABLES[AGING])


# --- the age effect's shape is aging's definition, not ours ---------------------------------------


def test_an_age_effect_carries_its_key_and_all_of_it_is_required():
    # `aging:DEF-AGE-EFFECT v1` section 2. Every component is forced by a benchmark question, so a
    # null in any of them would make the row unaddressable.
    key = ("dataset_id", "feature_id", "response", "estimator", "quant_basis", "model_form",
           "stratum")
    fields = _fields("age_effects")
    assert STUDY_COMPOSITE_IDENTIFIERS[AGING]["age_effects"] == key
    for column in key:
        assert column in fields, column
        assert fields[column].nullable is False, f"{column} is part of the key and must be required"


def test_a_beta_without_an_se_is_not_an_age_effect():
    # Section 4, stated as a rule rather than a preference, so the schema enforces it.
    fields = _fields("age_effects")
    assert fields["beta"].nullable is False
    assert fields["se"].nullable is False


def test_the_columns_that_stop_a_misreading_are_required():
    fields = _fields("age_effects")
    # A per-decade effect from a 12-year span is not evidence about a lifetime.
    assert fields["age_span_years"].nullable is False
    # A row whose covariates do not list a term did not adjust for it, whatever the protocol said.
    assert fields["covariates"].nullable is False
    # DEF-PROT-INT is un-normalized when FlashLFQ's Normalize is off, which every run here used.
    assert fields["normalization"].nullable is False
    # Two rows fitted by different engines are not comparable.
    assert fields["method"].nullable is False
    assert fields["method_version"].nullable is False


def test_the_evidence_columns_exist_and_are_optional():
    # Section 4: not optional to *populate* where they apply, but a row for `abundance` has no
    # occupancy depth, so the column is nullable and the definition says when it must be filled.
    fields = _fields("age_effects")
    for column in ("n_covering_psms_median", "intensity_is_floor_frac", "mbr_kept_frac"):
        assert column in fields
        assert fields[column].nullable is True


def test_a_refused_fit_has_a_home_and_can_be_dataset_level():
    # Section 5: when a requirement fails NO row is written to age_effects, so the refusal needs a
    # table of its own -- and trap J6's answer ("no liver dataset carries donor ages") names no
    # feature at all.
    fields = _fields("age_effect_refusals")
    assert fields["fit_refused"].nullable is False
    assert fields["dataset_id"].nullable is False
    assert fields["feature_id"].nullable is True
    assert fields["feature_type"].nullable is True


def test_the_meta_table_keys_on_what_may_never_be_pooled():
    # Section 6's stratification rules are refusals in disguise: never pool across acquisition,
    # quant_method or tissue, because H6, I3 and D4 ask whether those agree.
    fields = _fields("age_effect_meta")
    for column in ("tissue", "acquisition", "quant_method"):
        assert fields[column].nullable is False
        assert column in STUDY_COMPOSITE_IDENTIFIERS[AGING]["age_effect_meta"]
    # C3 and D1 need which datasets, not how many.
    assert fields["dataset_ids"].nullable is False
    assert pa.types.is_list(fields["dataset_ids"].type)
    # n_datasets = 1 is a legitimate row, so heterogeneity must be allowed to be absent.
    assert fields["i_squared"].nullable is True
    assert fields["leave_one_out_max_delta"].nullable is True


def test_an_age_effect_is_never_a_clock():
    # Section 8: an effect is per feature; predicting a donor's age is a model over many features.
    # Different tables, different definitions, and no column in which to confuse them.
    assert "clock_id" not in _fields("age_effects")
    assert "beta" not in _fields("clock_models")


# --- keys are decided while the tables are empty ---------------------------------------------------


def test_every_study_table_has_a_key():
    # quant_values shipped with no key and a duplicated source row wrote one measurement three
    # times. The moment to decide a key is while the table is still empty.
    identified = {table for table, _ in IDENTIFIERS}
    for layer, tables in STUDY_TABLES.items():
        keys = STUDY_COMPOSITE_IDENTIFIERS.get(layer, {})
        for table, schema in tables.items():
            has_own_id = table in identified or any(
                f.name.endswith("_id") and not f.nullable and f.name[:-3] in table
                for f in schema
            )
            assert table in keys or has_own_id, f"{layer}.{table} has no declared key"


def test_every_declared_key_names_real_columns():
    for layer, keys in STUDY_COMPOSITE_IDENTIFIERS.items():
        for table, key in keys.items():
            names = set(STUDY_TABLES[layer][table].names)
            missing = set(key) - names
            assert not missing, f"{layer}.{table} key names missing columns {sorted(missing)}"


# --- the catalog carries the layer, empty ----------------------------------------------------------


def test_the_catalog_creates_the_study_tables_empty(tmp_path, store):
    # EMPTY_TABLE and NO_TABLE are different answers to a benchmark question, and only one of them
    # says "this repository can hold that".
    bundles = [write_bundle(store, "PXD000001")]
    catalog = build_catalog(bundles, tmp_path / "catalog.duckdb").path
    for table in STUDY_TABLES[AGING]:
        assert rows(catalog, f'SELECT count(*) AS n FROM "{table}"')[0] == {"n": 0}


def test_the_catalog_says_which_tables_are_the_study_layers(tmp_path, store):
    bundles = [write_bundle(store, "PXD000001")]
    catalog = build_catalog(bundles, tmp_path / "catalog.duckdb").path
    listed = {
        r["table_name"]: r["kind"]
        for r in rows(catalog, "SELECT table_name, kind FROM catalog_tables")
    }
    for table in STUDY_TABLES[AGING]:
        assert listed[table] == f"study:{AGING}"
    # and the core tables are not relabelled by the layer's arrival
    assert listed["psms"] == "bundle"


def test_an_age_effect_query_runs_and_returns_nothing(tmp_path, store):
    # The shape of the 46 blocked questions: the SQL an agent would write must parse and run, and
    # come back empty rather than failing on a missing table.
    bundles = [write_bundle(store, "PXD000001")]
    catalog = build_catalog(bundles, tmp_path / "catalog.duckdb").path
    columns, data = run_query(
        catalog,
        "SELECT feature_id, beta, se, age_span_years FROM age_effects "
        "WHERE response = 'abundance' AND q_value <= 0.05 ORDER BY beta",
    )
    assert data == []
    assert columns == ["feature_id", "beta", "se", "age_span_years"]


def test_a_refusal_query_is_what_answers_the_missing_tissue(tmp_path, store):
    bundles = [write_bundle(store, "PXD000001")]
    catalog = build_catalog(bundles, tmp_path / "catalog.duckdb").path
    columns, data = run_query(
        catalog,
        "SELECT dataset_id, fit_refused FROM age_effect_refusals "
        "WHERE fit_refused = 'no_age_metadata'",
    )
    assert data == []
    assert columns == ["dataset_id", "fit_refused"]


@pytest.mark.parametrize("table", sorted(STUDY_TABLES[AGING]))
def test_every_study_table_is_selectable(tmp_path, store, table):
    bundles = [write_bundle(store, "PXD000001")]
    catalog = build_catalog(bundles, tmp_path / "catalog.duckdb").path
    columns, data = run_query(catalog, f'SELECT * FROM "{table}" LIMIT 1')
    assert data == []
    assert set(columns) == set(STUDY_TABLES[AGING][table].names)
