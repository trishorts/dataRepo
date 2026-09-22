"""The study delivery path: how stage 7's rows actually reach the repository (DATAREPO-20(a)).

`age_effect` is the output of a modelling stage that runs long after a search, so it cannot arrive
the way a PSM does. These tests are about the path that was built for it, and the promise that path
makes: **delivering a model result never touches a search bundle.** That is the property everything
else here is in service of, and it is the first test in the file.

They build their own miniature bundles and write their own delivery files, so nothing here needs a
parser at all -- which is right for a delivery path that reads a producer's own tabular output and
never touches a producer format.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from datarepo._tables import STUDY_TABLES, STUDY_VERSIONS
from datarepo.catalog import (
    build_catalog,
    catalog_id,
    discover_study_bundles,
    run_query,
    select_study_bundles,
)
from datarepo.errors import CatalogError, IngestError, ManifestError
from datarepo.study import (
    STUDY_BUNDLE_MANIFEST,
    STUDY_CONTENT_FIELDS,
    STUDY_DIR,
    STUDY_NON_CONTENT_FIELDS,
    StudyManifest,
    load_study_manifest,
    write_study_bundle,
)

from test_catalog import rows, write_bundle

AGING = "aging"
DATASET = "PXD000001"

#: One complete age effect, with every NOT NULL column of `aging:DEF-AGE-EFFECT v1` section 2 filled.
EFFECT = {
    "dataset_id": DATASET,
    "organism": "NCBITaxon:9606",
    "age_centre_years": "50",
    "feature_type": "protein_group",
    "feature_id": "P11111",
    "response": "abundance",
    "estimator": "intensity",
    "quant_basis": "mbr_included",
    "model_form": "linear",
    "stratum": "all",
    "beta": "-0.12",
    "se": "0.03",
    "q_value": "0.01",
    "n_samples": "40",
    "age_span_years": "48",
    "covariates": "sex",
    "normalization": "none",
    "method": "statsmodels.ols",
    "method_version": "0.14.1",
    "definition_id": "aging:DEF-AGE-EFFECT",
}


@pytest.fixture
def store(tmp_path):
    return tmp_path / "store"


def write_delivery(tmp_path, tables: dict[str, list[dict]], *, store, definitions=None,
                   **manifest_fields):
    """Write a producer's delivery -- a TSV per table plus a `study.yaml` -- and load the manifest."""
    delivery = tmp_path / "stage7"
    delivery.mkdir(parents=True, exist_ok=True)
    declared = {}
    for name, table_rows in tables.items():
        columns = list(STUDY_TABLES[AGING][name].names)
        path = delivery / f"{name}.tsv"
        lines = ["\t".join(columns)]
        for row in table_rows:
            lines.append("\t".join(str(row.get(c, "")) for c in columns))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        declared[name] = path.name
    doc = [
        "study_manifest_version: 1",
        f"layer: {AGING}",
        f"store: {store.as_posix()}",
        "instance: ncems-aging",
        *(f"{k}: {v}" for k, v in manifest_fields.items()),
        *(["definitions:"] + [f"  - {d}" for d in definitions] if definitions else []),
        "tables:",
        *(f"  {name}: {rel}" for name, rel in sorted(declared.items())),
    ]
    path = delivery / "study.yaml"
    path.write_text("\n".join(doc) + "\n", encoding="utf-8")
    return load_study_manifest(path)


# --- the promise the whole path exists to keep ----------------------------------------------------


def test_delivering_a_study_bundle_does_not_move_a_search_bundle(tmp_path, store):
    # The reason a study bundle is a separate object at all (thread 022 section 2a). A re-fit must
    # never re-identify a bundle somebody has cited, and a search bundle must not even be read.
    ref = write_bundle(store, DATASET)
    before = json.loads((ref.path / "bundle.json").read_text(encoding="utf-8"))

    manifest = write_delivery(tmp_path, {"age_effects": [EFFECT]}, store=store)
    write_study_bundle(manifest)

    after = json.loads((ref.path / "bundle.json").read_text(encoding="utf-8"))
    assert after == before
    assert after["bundle_id"] == ref.bundle_id
    assert ref.path.is_dir()


def test_a_study_bundle_lives_beside_the_datasets_and_not_among_them(tmp_path, store):
    manifest = write_delivery(tmp_path, {"age_effects": [EFFECT]}, store=store)
    result = write_study_bundle(manifest)
    assert result.bundle_path.parent.parent.name == STUDY_DIR
    assert result.bundle_path.parent.name == AGING
    # and a dataset directory is never mistaken for one
    write_bundle(store, DATASET)
    assert [p.name for p in sorted(store.iterdir()) if p.is_dir()] == [STUDY_DIR, DATASET]


# --- content addressing -----------------------------------------------------------------------


def test_an_unchanged_delivery_is_a_no_op(tmp_path, store):
    manifest = write_delivery(tmp_path, {"age_effects": [EFFECT]}, store=store)
    first = write_study_bundle(manifest)
    second = write_study_bundle(manifest)
    assert second.bundle_id == first.bundle_id
    assert second.skipped is True
    assert second.row_counts == first.row_counts


def test_a_changed_row_gives_a_new_bundle_beside_the_old_one(tmp_path, store):
    first = write_study_bundle(write_delivery(tmp_path, {"age_effects": [EFFECT]}, store=store))
    refit = dict(EFFECT, beta="-0.30")
    second = write_study_bundle(write_delivery(tmp_path, {"age_effects": [refit]}, store=store))
    assert second.bundle_id != first.bundle_id
    assert len(discover_study_bundles(store, AGING)) == 2


def test_the_producers_prose_does_not_move_the_id(tmp_path, store):
    # The over-hashing that bit twice already (thread 021 section 4): rewording a label must not
    # re-identify rows that are byte-identical.
    plain = write_study_bundle(write_delivery(tmp_path, {"age_effects": [EFFECT]}, store=store))
    labelled = write_study_bundle(
        write_delivery(
            tmp_path / "again",
            {"age_effects": [EFFECT]},
            store=store,
            delivery="stage7-rerun",
            notes="re-delivered after the meeting",
        )
    )
    assert labelled.bundle_id == plain.bundle_id


def test_every_study_manifest_field_is_classified_for_the_content_hash():
    declared = {f.name for f in dataclasses.fields(StudyManifest)}
    classified = set(STUDY_CONTENT_FIELDS) | set(STUDY_NON_CONTENT_FIELDS)
    assert declared == classified, (
        f"unclassified study manifest field(s): {sorted(declared - classified)}; "
        f"classified but not a field: {sorted(classified - declared)}"
    )
    assert not set(STUDY_CONTENT_FIELDS) & set(STUDY_NON_CONTENT_FIELDS)
    assert all(STUDY_NON_CONTENT_FIELDS.values()), "every excluded field needs its reason"


# --- the definition's rules are enforced on the way in --------------------------------------------


def test_a_beta_without_an_se_is_refused_at_write_time(tmp_path, store):
    # Section 4 as a write error rather than a comment beside the column.
    broken = dict(EFFECT, se="")
    manifest = write_delivery(tmp_path, {"age_effects": [broken]}, store=store)
    with pytest.raises(IngestError, match="required 'se'"):
        write_study_bundle(manifest)


def test_a_refused_fit_has_nowhere_to_write_a_null_beta(tmp_path, store):
    # Section 5: no row, not a row with a null. `age_effect_refusals` has no `beta` column at all.
    assert "beta" not in STUDY_TABLES[AGING]["age_effect_refusals"].names


def test_a_column_the_layer_does_not_have_is_refused(tmp_path, store):
    delivery = tmp_path / "stage7"
    delivery.mkdir(parents=True)
    (delivery / "age_effects.tsv").write_text("dataset_id\tbeta_hat\nPXD000001\t-0.1\n", encoding="utf-8")
    (delivery / "study.yaml").write_text(
        f"study_manifest_version: 1\nlayer: {AGING}\nstore: {store.as_posix()}\n"
        "tables:\n  age_effects: age_effects.tsv\n",
        encoding="utf-8",
    )
    with pytest.raises(IngestError, match="unknown columns"):
        write_study_bundle(load_study_manifest(delivery / "study.yaml"))


def test_two_rows_for_one_fit_are_refused(tmp_path, store):
    # The key was declared in 0.6.0 while the table was empty, exactly so this check could exist the
    # moment something filled it. Two answers to one question is the producer's call, not ours.
    manifest = write_delivery(
        tmp_path, {"age_effects": [EFFECT, dict(EFFECT, beta="-0.44")]}, store=store
    )
    with pytest.raises(IngestError, match="duplicate key"):
        write_study_bundle(manifest)


def test_a_dataset_level_refusal_needs_no_feature(tmp_path, store):
    # Trap J6's answer -- "no liver dataset carries donor ages" -- names no feature at all, and the
    # key check must not choke on the null it leaves in `feature_id`.
    refusals = [
        {
            "dataset_id": DATASET,
            "response": "abundance",
            "estimator": "intensity",
            "quant_basis": "mbr_included",
            "model_form": "linear",
            "stratum": "all",
            "fit_refused": "no_age_metadata",
            "definition_id": "aging:DEF-AGE-EFFECT",
        }
    ]
    manifest = write_delivery(tmp_path, {"age_effect_refusals": refusals}, store=store)
    result = write_study_bundle(manifest)
    assert result.row_counts == {"age_effect_refusals": 1}


def test_a_list_column_survives_a_tsv(tmp_path, store):
    # C3 and D1 need WHICH datasets a pooled estimate came from. A delimited file has to be able to
    # carry that, and the separator is declared rather than sniffed.
    meta = {
        "feature_type": "protein",
        "feature_id": "P11111",
        "response": "abundance",
        "estimator": "intensity",
        "quant_basis": "mbr_included",
        "stratum": "all",
        "organism": "NCBITaxon:9606",
        "tissue": "liver",
        "acquisition": "DDA",
        "quant_method": "label_free",
        "beta_meta": "-0.10",
        "se_meta": "0.02",
        "n_datasets": "2",
        "dataset_ids": "PXD000001;PXD000002",
        "definition_id": "aging:DEF-AGE-EFFECT-META",
    }
    manifest = write_delivery(tmp_path, {"age_effect_meta": [meta]}, store=store)
    result = write_study_bundle(manifest)
    import pyarrow.parquet as pq

    written = pq.read_table(result.bundle_path / "age_effect_meta.parquet").to_pylist()
    assert written[0]["dataset_ids"] == ["PXD000001", "PXD000002"]


def test_a_file_format_is_taken_from_the_extension_and_not_guessed(tmp_path, store):
    delivery = tmp_path / "stage7"
    delivery.mkdir(parents=True)
    (delivery / "age_effects.dat").write_text("dataset_id\n", encoding="utf-8")
    (delivery / "study.yaml").write_text(
        f"study_manifest_version: 1\nlayer: {AGING}\nstore: {store.as_posix()}\n"
        "tables:\n  age_effects: age_effects.dat\n",
        encoding="utf-8",
    )
    with pytest.raises(IngestError, match="extension"):
        write_study_bundle(load_study_manifest(delivery / "study.yaml"))


# --- the manifest is the contract ------------------------------------------------------------


def test_an_unknown_layer_is_refused(tmp_path, store):
    path = tmp_path / "study.yaml"
    path.write_text(
        f"study_manifest_version: 1\nlayer: cardiology\nstore: {store.as_posix()}\n"
        "tables:\n  age_effects: x.tsv\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="does not carry"):
        load_study_manifest(path)


def test_a_table_the_layer_does_not_have_is_refused(tmp_path, store):
    path = tmp_path / "study.yaml"
    path.write_text(
        f"study_manifest_version: 1\nlayer: {AGING}\nstore: {store.as_posix()}\n"
        "tables:\n  psms: x.tsv\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="no table 'psms'"):
        load_study_manifest(path)


def test_a_delivery_that_names_no_table_is_not_a_delivery(tmp_path, store):
    path = tmp_path / "study.yaml"
    path.write_text(
        f"study_manifest_version: 1\nlayer: {AGING}\nstore: {store.as_posix()}\ntables: {{}}\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="non-empty 'tables'"):
        load_study_manifest(path)


def test_a_layer_version_that_does_not_match_this_build_is_refused(tmp_path, store):
    path = tmp_path / "study.yaml"
    path.write_text(
        f"study_manifest_version: 1\nlayer: {AGING}\nlayer_version: 0.0.9\n"
        f"store: {store.as_posix()}\ntables:\n  age_effects: x.tsv\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="silently null"):
        load_study_manifest(path)


# --- the catalog loads it ----------------------------------------------------------------------


def _catalog_with_effects(tmp_path, store, effects=(EFFECT,), **kwargs):
    bundles = [write_bundle(store, DATASET)]
    manifest = write_delivery(tmp_path, {"age_effects": list(effects)}, store=store, **kwargs)
    delivered = write_study_bundle(manifest)
    study = select_study_bundles(store, pins={AGING: delivered.bundle_id})
    return build_catalog(bundles, tmp_path / "catalog.duckdb", study_bundles=study), study


def test_the_tables_stop_being_empty(tmp_path, store):
    result, _ = _catalog_with_effects(tmp_path, store)
    assert rows(result.path, "SELECT count(*) AS n FROM age_effects")[0] == {"n": 1}


def test_section_ds_question_now_returns_a_row(tmp_path, store):
    # The query dataRepo published in thread 022 as parsing and returning nothing. Same SQL.
    result, _ = _catalog_with_effects(tmp_path, store)
    _, data = run_query(
        result.path,
        "SELECT pl.compartment, count(*) AS n, median(ae.beta) AS median_beta "
        "FROM age_effects ae "
        "JOIN protein_localizations pl ON pl.protein_accession = ae.feature_id "
        "WHERE ae.response = 'abundance' AND ae.q_value <= 0.05 AND ae.stratum = 'all' "
        "GROUP BY 1 ORDER BY median_beta",
    )
    # The fixture bundle carries no localizations, so the join is empty -- but the age effect is
    # there, which is the half that was missing.
    assert data == []
    assert rows(result.path, "SELECT count(*) AS n FROM age_effects")[0] == {"n": 1}


def test_every_study_row_says_which_delivery_it_came_from(tmp_path, store):
    result, study = _catalog_with_effects(tmp_path, store)
    row = rows(result.path, "SELECT study_layer, study_bundle_id FROM age_effects")[0]
    assert row == {"study_layer": AGING, "study_bundle_id": study[0].bundle_id}


def test_the_catalog_records_the_delivery_it_loaded(tmp_path, store):
    result, study = _catalog_with_effects(tmp_path, store)
    listed = rows(result.path, "SELECT layer, bundle_id, layer_version FROM catalog_study_bundles")
    assert listed == [
        {"layer": AGING, "bundle_id": study[0].bundle_id, "layer_version": STUDY_VERSIONS[AGING]}
    ]


def test_a_catalog_with_a_delivery_is_not_the_same_catalog_without_one(tmp_path, store):
    # 46 benchmark questions get different answers from the two, so they cannot share an id.
    bundles = [write_bundle(store, DATASET)]
    manifest = write_delivery(tmp_path, {"age_effects": [EFFECT]}, store=store)
    delivered = write_study_bundle(manifest)
    study = select_study_bundles(store, pins={AGING: delivered.bundle_id})
    assert catalog_id(bundles, study) != catalog_id(bundles)


def test_study_bundles_are_opt_in(tmp_path, store):
    # A store holding a delivery must not change what a build that did not ask for it produces.
    bundles = [write_bundle(store, DATASET)]
    write_study_bundle(write_delivery(tmp_path, {"age_effects": [EFFECT]}, store=store))
    result = build_catalog(bundles, tmp_path / "catalog.duckdb")
    assert rows(result.path, "SELECT count(*) AS n FROM age_effects")[0] == {"n": 0}
    assert result.catalog_id == catalog_id(bundles)


def test_an_age_effect_for_a_dataset_the_catalog_lacks_is_refused(tmp_path, store):
    # Not dropped. Section D's answer would come back smaller than the delivery supports and
    # nothing in the catalog would say why.
    stranger = dict(EFFECT, dataset_id="PXD999999")
    with pytest.raises(CatalogError, match="age_effects.dataset_id"):
        _catalog_with_effects(tmp_path, store, effects=(EFFECT, stranger))


def test_a_sample_age_for_an_unknown_sample_is_refused(tmp_path, store):
    bundles = [write_bundle(store, DATASET)]
    ages = [
        {
            "sample_id": "PXD000001:nosuchsample",
            "age_raw": "62Y",
            "age_years": "62",
            "normalizer_version": "sdrf-age/0.1.0",
        }
    ]
    delivered = write_study_bundle(write_delivery(tmp_path, {"sample_ages": ages}, store=store))
    study = select_study_bundles(store, pins={AGING: delivered.bundle_id})
    with pytest.raises(CatalogError, match="sample_ages.sample_id"):
        build_catalog(bundles, tmp_path / "catalog.duckdb", study_bundles=study)


def test_a_release_will_not_take_the_latest_delivery(tmp_path, store):
    # D11, one level out: a release that can pick up a later re-fit is not a release.
    write_study_bundle(write_delivery(tmp_path, {"age_effects": [EFFECT]}, store=store))
    with pytest.raises(CatalogError, match="mutually exclusive"):
        select_study_bundles(store, latest=[AGING], release="v0.2")


def test_a_layer_with_no_delivery_is_named(tmp_path, store):
    store.mkdir(parents=True, exist_ok=True)
    with pytest.raises(CatalogError, match="datarepo study"):
        select_study_bundles(store, latest=[AGING])


def test_a_pin_that_matches_nothing_lists_what_is_there(tmp_path, store):
    delivered = write_study_bundle(write_delivery(tmp_path, {"age_effects": [EFFECT]}, store=store))
    with pytest.raises(CatalogError, match=delivered.bundle_id):
        select_study_bundles(store, pins={AGING: "deadbeef"})


def test_the_delivery_manifest_records_both_versions(tmp_path, store):
    result = write_study_bundle(write_delivery(tmp_path, {"age_effects": [EFFECT]}, store=store))
    doc = json.loads((result.bundle_path / STUDY_BUNDLE_MANIFEST).read_text(encoding="utf-8"))
    assert doc["kind"] == "study"
    assert doc["layer_version"] == STUDY_VERSIONS[AGING]
    # What an operator installed, and what the id was computed from: different questions.
    assert doc["ingester"]["version"] != doc["ingester"]["study_ingest_path"]


# --- the worked example in examples/ is a real one ------------------------------------------------


def test_the_shipped_example_delivery_writes_a_bundle(tmp_path, store):
    # A copyable example that is never run is an example that rots. This one is the producer-facing
    # documentation of the contract, so it has to load.
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    manifest = load_study_manifest(root / "examples" / "study_delivery" / "study.yaml")
    result = write_study_bundle(manifest, store=store)
    assert result.row_counts == {"age_effects": 2, "age_effect_refusals": 1, "sample_ages": 2}
    # and the refusal it ships is the shape DEF-AGE-EFFECT v1 section 5 asks for
    import pyarrow.parquet as pq

    refusal = pq.read_table(result.bundle_path / "age_effect_refusals.parquet").to_pylist()[0]
    assert refusal["fit_refused"] == "too_few_distinct_ages"


# --- the definition register (aging 024 section 2a) -----------------------------------------------


DEFS = ["aging:DEF-AGE-EFFECT", "aging:DEF-AGE-EFFECT-META"]


def test_a_definition_the_delivery_does_not_declare_refuses_the_write(tmp_path, store):
    # aging asked for this check and corrected its target: their definitions are not produced by a
    # search, so the core `definitions` table is the wrong register. A number whose definition id
    # does not resolve is exactly what a register exists to prevent, and they would rather the
    # write failed than the row landed.
    stray = dict(EFFECT, definition_id="aging:DEF-SOMETHING-ELSE")
    manifest = write_delivery(tmp_path, {"age_effects": [stray]}, store=store, definitions=DEFS)
    with pytest.raises(IngestError, match="does not declare"):
        write_study_bundle(manifest)


def test_a_declared_definition_passes(tmp_path, store):
    manifest = write_delivery(tmp_path, {"age_effects": [EFFECT]}, store=store, definitions=DEFS)
    assert write_study_bundle(manifest).row_counts == {"age_effects": 1}


def test_declaring_no_register_skips_the_check(tmp_path, store):
    # Deliberate rather than lax: a producer who has not adopted the register is not silently held
    # to a stricter contract than the one they agreed to. Declaring even one definition opts in.
    stray = dict(EFFECT, definition_id="aging:DEF-SOMETHING-ELSE")
    manifest = write_delivery(tmp_path, {"age_effects": [stray]}, store=store)
    assert write_study_bundle(manifest).row_counts == {"age_effects": 1}


def test_the_register_is_part_of_the_delivery_identity(tmp_path, store):
    # It decides whether a row may be written at all, so two deliveries declaring different
    # registers are not interchangeable even over identical numbers.
    narrow = write_study_bundle(
        write_delivery(tmp_path, {"age_effects": [EFFECT]}, store=store, definitions=DEFS[:1])
    )
    wide = write_study_bundle(
        write_delivery(tmp_path / "b", {"age_effects": [EFFECT]}, store=store, definitions=DEFS)
    )
    assert narrow.bundle_id != wide.bundle_id
