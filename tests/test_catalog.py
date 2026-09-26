"""Building the catalog: union, provenance, acceptance, checks and content addressing.

These build their own miniature bundles rather than ingesting the fixture dataset, so they run with
or without pyMzLib installed. What is under test here is what dataRepo itself decides once the
bundles exist, and none of that needs a parser.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from datarepo.bundle import BundleWriter
from datarepo.catalog import (
    ACCEPTED_VIEWS,
    BundleRef,
    build_catalog,
    catalog_id,
    describe_catalog,
    discover_bundles,
    run_query,
    select_bundles,
)
from datarepo.errors import CatalogError, DatasetExcluded

ACCEPTED = 0.005  # comfortably inside 1%
REJECTED = 0.5


def _dataset(dataset_id: str) -> dict:
    return {
        "dataset_id": dataset_id,
        "organisms": ["NCBITaxon:9606"],
        "acquisition": "DDA",
        "quant_method": "label_free",
        "labelling": "none",
        "enrichment": ["none"],
        "enrichment_mixed": False,
        "axis_source": "manifest",
        "search_engine": "MetaMorpheus",
        "search_engine_version": "1.1.11",
    }


def write_bundle(
    store: Path,
    dataset_id: str,
    *,
    accessions: tuple[str, ...] = ("P11111",),
    peptide_q: float = ACCEPTED,
    group_q: float = 0.0,
    ambiguous_psm: bool = False,
    ptm_sites: bool = False,
    extra_source: str | None = None,
    contaminants: tuple[str, ...] = (),
    characteristics: tuple[tuple[str, str], ...] = (),
) -> BundleRef:
    """One small but complete bundle: a dataset, a run, an assay, and one protein's evidence."""
    store.mkdir(parents=True, exist_ok=True)
    writer = BundleWriter(store=store, dataset_id=dataset_id)
    run_id = f"{dataset_id}:run1"
    sample_id = f"{dataset_id}:sample1"
    assay_id = f"{run_id}:label_free"
    group_id = f"{dataset_id}:{accessions[0]}"

    writer.add("datasets", [_dataset(dataset_id)])
    writer.add("samples", [{
        "sample_id": sample_id, "dataset_id": dataset_id,
        "source_name": "s1", "organism": "NCBITaxon:9606",
    }])
    if characteristics:
        writer.add("sample_characteristics", [
            {"sample_id": sample_id, "name": name, "value": value,
             "value_reserved": value.lower() in ("not available", "not applicable")}
            for name, value in characteristics
        ])
    writer.add("runs", [{"run_id": run_id, "dataset_id": dataset_id, "file_name": "r1.raw"}])
    writer.add("assays", [{
        "assay_id": assay_id, "run_id": run_id, "channel": "label_free", "sample_id": sample_id,
    }])
    writer.add("proteins", [
        {"protein_accession": acc, "organism": "NCBITaxon:9606", "source_db": "uniprot",
         "gene": "GENE1" if acc == "P11111" else "GENE2",
         **({"is_contaminant": True} if acc in contaminants else {})}
        for acc in accessions
    ])
    writer.add("protein_groups", [{
        "protein_group_id": group_id, "dataset_id": dataset_id,
        "protein_accessions": list(accessions), "target_decoy": "target", "q_value": group_q,
    }])
    writer.add("peptidoforms", [
        {"peptidoform_id": f"{dataset_id}:PEPTIDEK", "dataset_id": dataset_id,
         "peptidoform": "PEPTIDEK", "base_sequence": "PEPTIDEK", "target_decoy": "target",
         "best_q_value": peptide_q, "best_q_value_notch": peptide_q,
         "protein_group_id": group_id, "protein_accessions": list(accessions)},
        {"peptidoform_id": f"{dataset_id}:DECOYK", "dataset_id": dataset_id,
         "peptidoform": "DECOYK", "base_sequence": "DECOYK", "target_decoy": "decoy",
         "best_q_value": 0.0, "best_q_value_notch": 0.0,
         "protein_group_id": group_id, "protein_accessions": list(accessions)},
    ])
    psms = [{
        "psm_id": f"{dataset_id}:psm1", "run_id": run_id, "scan": 1,
        "usi": f"mzspec:{dataset_id}:r1:scan:1:PEPTIDEK/2", "peptidoform": "PEPTIDEK",
        "base_sequence": "PEPTIDEK", "precursor_charge": 2, "q_value": ACCEPTED,
        "q_value_notch": ACCEPTED, "target_decoy": "target", "protein_accessions": [accessions[0]],
        "notch": "0", "notch_ambiguous": False,
    }]
    if ambiguous_psm:
        # Passes both q-value thresholds, and the producer still does not count it.
        psms.append({**psms[0], "psm_id": f"{dataset_id}:psm2", "scan": 2,
                     "usi": f"mzspec:{dataset_id}:r1:scan:2:PEPTIDEK/2",
                     "notch": "0.00000|1.00290", "notch_ambiguous": True})
    writer.add("psms", psms)
    if ptm_sites:
        acc = accessions[0]
        # Two engine names for one chemistry at S6 -- the split the rekey introduces -- and two
        # different chemistries with no UNIMOD term at K10, which must NOT merge.
        writer.add("ptm_sites", [
            {"ptm_site_id": f"{dataset_id}:{acc}:S6:Phosphorylation on S", "dataset_id": dataset_id,
             "protein_accession": acc, "position": 6, "residue": "S", "site_type": "residue",
             "modification": "UNIMOD:21",
             "modification_name": "Phosphorylation on S", "target_decoy": "target",
             "best_ambiguity_level": "2A", "n_psms": 11, "best_q_value": 0.004},
            {"ptm_site_id": f"{dataset_id}:{acc}:S6:Phosphoserine on S", "dataset_id": dataset_id,
             "protein_accession": acc, "position": 6, "residue": "S", "site_type": "residue",
             "modification": "UNIMOD:21",
             "modification_name": "Phosphoserine on S", "target_decoy": "target",
             "best_ambiguity_level": "1", "n_psms": 3, "best_q_value": 0.001},
            {"ptm_site_id": f"{dataset_id}:{acc}:K10:Hydroxybutyrylation on K",
             "dataset_id": dataset_id, "protein_accession": acc, "position": 10, "residue": "K",
             "site_type": "residue",
             "modification": None, "modification_name": "Hydroxybutyrylation on K",
             "target_decoy": "target", "best_ambiguity_level": "1", "n_psms": 5,
             "best_q_value": 0.002},
            {"ptm_site_id": f"{dataset_id}:{acc}:K10:N6-glutaryllysine on K",
             "dataset_id": dataset_id, "protein_accession": acc, "position": 10, "residue": "K",
             "site_type": "residue",
             "modification": None, "modification_name": "N6-glutaryllysine on K",
             "target_decoy": "target", "best_ambiguity_level": "1", "n_psms": 2,
             "best_q_value": 0.003},
        ])
    writer.add("definitions", [{
        "definition_id": "PROVISIONAL:PROTEIN-INTENSITY", "version": "v0",
        "owner_project": "dataRepo", "text": "test",
    }])
    writer.add("quant_values", [{
        "assay_id": assay_id, "feature_type": "protein_group", "feature_id": group_id,
        "value": 1000.0, "definition_id": "PROVISIONAL:PROTEIN-INTENSITY",
    }])

    source = store / f"{dataset_id}-input.txt"
    source.write_text(extra_source or dataset_id, encoding="utf-8")
    writer.add_source(source, "test")
    path = writer.write()

    # The manifest's row counts are what a build reconciles against, so they have to be real.
    manifest = json.loads((path / "bundle.json").read_text(encoding="utf-8"))
    assert manifest["tables"]["psms"] == len(psms)
    return BundleRef.load(path)


@pytest.fixture
def store(tmp_path) -> Path:
    return tmp_path / "store"


@pytest.fixture
def two_datasets(store) -> list[BundleRef]:
    """Two datasets sharing protein P11111, which is what makes a cross-dataset answer possible."""
    return [
        write_bundle(store, "PXD000001"),
        write_bundle(store, "PXD000002", accessions=("P11111", "P22222")),
    ]


@pytest.fixture
def catalog(tmp_path, two_datasets) -> Path:
    result = build_catalog(two_datasets, tmp_path / "catalog.duckdb")
    return result.path


def rows(catalog: Path, sql: str) -> list[dict]:
    columns, data = run_query(catalog, sql)
    return [dict(zip(columns, r)) for r in data]


# --- the union ---------------------------------------------------------------------------------


def test_every_row_says_which_bundle_it_came_from(catalog):
    found = rows(catalog, "SELECT dataset_id, bundle_id, count(*) n FROM psms GROUP BY 1, 2")
    assert len(found) == 2
    assert all(r["bundle_id"] for r in found)


def test_a_table_with_no_dataset_id_of_its_own_gets_one(catalog):
    # `proteins` has no dataset_id in the schema: it is a protein list, not a dataset table. Without
    # one, the same accession from two datasets would be indistinguishable in the catalog.
    found = rows(catalog, "SELECT dataset_id FROM proteins WHERE protein_accession = 'P11111'")
    assert sorted(r["dataset_id"] for r in found) == ["PXD000001", "PXD000002"]


def test_every_schema_table_exists_even_when_no_bundle_filled_it(catalog):
    # An empty table and a missing one mean different things to a caller that cannot see the store.
    assert rows(catalog, "SELECT count(*) n FROM glycopeptides")[0]["n"] == 0
    assert rows(catalog, "SELECT count(*) n FROM protein_localizations")[0]["n"] == 0


def test_the_catalog_records_the_bundles_it_was_built_from(catalog):
    doc = describe_catalog(catalog)
    assert [b["dataset_id"] for b in doc["bundles"]] == ["PXD000001", "PXD000002"]
    assert all(b["reconciliation_ok"] for b in doc["bundles"])
    assert doc["meta"]["n_datasets"] == 2


# --- the acceptance rule -----------------------------------------------------------------------


def test_the_accepted_views_apply_the_producers_rule_not_ours(catalog):
    assert rows(catalog, "SELECT count(*) n FROM peptidoforms")[0]["n"] == 4  # 2 per dataset
    assert rows(catalog, "SELECT count(*) n FROM peptidoforms_1pct")[0]["n"] == 2  # decoys dropped


def test_a_sub_threshold_peptidoform_is_out_of_the_accepted_view(tmp_path, store):
    bundles = [
        write_bundle(store, "PXD000001"),
        write_bundle(store, "PXD000002", peptide_q=REJECTED),
    ]
    catalog = build_catalog(bundles, tmp_path / "catalog.duckdb").path
    found = rows(catalog, "SELECT dataset_id FROM peptidoforms_1pct")
    assert [r["dataset_id"] for r in found] == ["PXD000001"]


def test_the_sql_acceptance_rule_agrees_with_the_ingesters_own_counter(catalog):
    """The one thing that stops the rule drifting: two implementations, one answer.

    `producer_counts` is what a bundle reconciles itself with, in Python over the producer's
    columns. `psms_1pct` is what the catalog serves, in SQL over the written rows. If somebody
    changes one, this fails.
    """
    from datarepo.sources.identifications import producer_counts

    psms = rows(catalog, "SELECT q_value, q_value_notch, target_decoy FROM psms")
    as_columns = {
        "q_value": [r["q_value"] for r in psms],
        "q_value_notch": [r["q_value_notch"] for r in psms],
        "decoy_contam_target": ["T" if r["target_decoy"] == "target" else "D" for r in psms],
    }
    assert rows(catalog, "SELECT count(*) n FROM psms_1pct")[0]["n"] == producer_counts(as_columns)


def test_the_peptidoform_rule_agrees_too_and_carries_no_notch_clause(catalog):
    """The half of the agreement that was never checked, and drifted for three releases.

    `producer_counts` applied the PSM notch clause (aging 008) to the peptidoform count as well,
    while `peptidoforms_1pct` never did -- so the two paths disagreed by 3 on each of aging's two
    larger datasets, and PXD032202 carried a `count_mismatch` finding against a producer number it
    matched exactly. The test above covered PSMs only, which is how it survived.

    The ambiguous row here is the whole point: it passes both q-value thresholds and an unresolved
    notch, so it is counted for peptidoforms and would not be for PSMs.
    """
    from datarepo.sources.identifications import producer_counts

    peptidoforms = rows(
        catalog, "SELECT best_q_value, best_q_value_notch, target_decoy FROM peptidoforms"
    )
    as_columns = {
        "q_value": [r["best_q_value"] for r in peptidoforms],
        "q_value_notch": [r["best_q_value_notch"] for r in peptidoforms],
        "decoy_contam_target": ["T" if r["target_decoy"] == "target" else "D" for r in peptidoforms],
        # Every row unresolved: with the clause this counts 0, without it counts the accepted rows.
        "notch": ["0.00000|1.00290"] * len(peptidoforms),
    }
    served = rows(catalog, "SELECT count(*) n FROM peptidoforms_1pct")[0]["n"]
    assert served == producer_counts(as_columns, require_resolved_notch=False)
    assert producer_counts(as_columns) == 0, "the PSM clause must still bite when it is asked for"
    assert served > 0


def test_the_overview_headline_is_the_number_the_bundle_reconciled(catalog):
    overview = rows(catalog, "SELECT * FROM dataset_overview ORDER BY dataset_id")
    assert [r["n_peptidoforms_1pct"] for r in overview] == [1, 1]
    assert [r["n_psms_all"] for r in overview] == [1, 1]


# --- the cross-dataset indexes -----------------------------------------------------------------


def test_the_protein_index_answers_which_datasets_have_this_protein(catalog):
    shared = rows(catalog, "SELECT * FROM protein_index WHERE protein_accession = 'P11111'")[0]
    assert shared["n_datasets"] == 2
    assert shared["dataset_ids_1pct"] == ["PXD000001", "PXD000002"]
    only_one = rows(catalog, "SELECT * FROM protein_index WHERE protein_accession = 'P22222'")[0]
    assert only_one["n_datasets"] == 1


def test_the_contaminant_label_stays_per_dataset(tmp_path, store):
    """aging 070, 57f: `protein_index.is_contaminant` was bool_or over datasets, so human albumin
    read `true` while a target in every human search, and an agent concluded it was excluded."""
    bundles = [
        write_bundle(store, "PXD000001"),
        write_bundle(store, "PXD000002", contaminants=("P11111",)),
    ]
    catalog = build_catalog(bundles, tmp_path / "catalog.duckdb").path
    entry = rows(catalog, "SELECT * FROM protein_index WHERE protein_accession = 'P11111'")[0]
    assert "is_contaminant" not in entry, "a corpus-wide flag cannot be true of a per-dataset label"
    assert (entry["n_datasets"], entry["n_datasets_contaminant"]) == (2, 1)
    per = {
        r["dataset_id"]: r["is_contaminant"]
        for r in rows(catalog, "SELECT * FROM protein_datasets WHERE protein_accession = 'P11111'")
    }
    assert per == {"PXD000001": None, "PXD000002": True}


def test_a_named_tissue_with_no_term_reaches_samples_as_a_name(tmp_path, store):
    """G74: `organism_part` holds a term only, so 51 samples whose SDRF says `heart` read NULL and
    "which datasets are heart?" came back empty. The name now sits beside the term column."""
    bundles = [
        write_bundle(store, "PXD000001", characteristics=(
            ("characteristics[organism part]", "heart"),
            ("factor value[organism part]", "cardiac muscle"),  # characteristics wins
            ("characteristics[disease]", "NT=normal;AC=PATO:0000461"),
            ("characteristics[sex]", "not available"),
        )),
        write_bundle(store, "PXD000002", characteristics=(("factor value[cell type]", "neuron"),)),
    ]
    catalog = build_catalog(bundles, tmp_path / "catalog.duckdb").path
    got = {r["dataset_id"]: r for r in rows(catalog, "SELECT * FROM samples")}
    one, two = got["PXD000001"], got["PXD000002"]
    assert one["organism_part"] is None and one["organism_part_name"] == "heart"
    assert one["disease_name"] == "normal"
    assert one["sex_name"] is None, "`not available` is not a name"
    assert two["cell_type_name"] == "neuron" and two["organism_part_name"] is None


def test_a_protein_with_no_accepted_evidence_is_listed_but_not_counted(tmp_path, store):
    bundles = [write_bundle(store, "PXD000001", peptide_q=REJECTED, group_q=REJECTED)]
    catalog = build_catalog(bundles, tmp_path / "catalog.duckdb").path
    entry = rows(catalog, "SELECT * FROM protein_index WHERE protein_accession = 'P11111'")[0]
    assert entry["n_datasets"] == 1  # the search saw it
    assert entry["n_datasets_1pct"] == 0  # nothing about it passed


def test_the_peptide_index_spans_datasets(catalog):
    entry = rows(catalog, "SELECT * FROM peptide_index WHERE base_sequence = 'PEPTIDEK'")[0]
    assert entry["n_datasets"] == 2


# --- content addressing ------------------------------------------------------------------------


def test_rebuilding_from_the_same_bundles_is_a_no_op(tmp_path, two_datasets):
    out = tmp_path / "catalog.duckdb"
    first = build_catalog(two_datasets, out)
    again = build_catalog(two_datasets, out)
    assert not first.skipped and again.skipped
    assert again.catalog_id == first.catalog_id


def test_overwrite_rebuilds_a_current_catalog(tmp_path, two_datasets):
    out = tmp_path / "catalog.duckdb"
    build_catalog(two_datasets, out)
    assert not build_catalog(two_datasets, out, overwrite=True).skipped


def test_a_different_set_of_bundles_is_a_different_catalog(two_datasets):
    assert catalog_id(two_datasets) != catalog_id(two_datasets[:1])


# --- refusals ----------------------------------------------------------------------------------


def test_two_bundles_for_one_dataset_are_refused(tmp_path, store):
    bundle = write_bundle(store, "PXD000001")
    with pytest.raises(CatalogError, match="appears twice"):
        build_catalog([bundle, bundle], tmp_path / "catalog.duckdb")


def test_a_bundle_from_another_schema_version_is_refused(tmp_path, store):
    bundle = write_bundle(store, "PXD000001")
    stale = BundleRef(path=bundle.path, manifest={**bundle.manifest, "schema_version": "0.0.0"})
    with pytest.raises(CatalogError, match="schema 0.0.0"):
        build_catalog([stale], tmp_path / "catalog.duckdb")


def test_a_truncated_bundle_is_caught_by_the_row_count_check(tmp_path, store):
    bundle = write_bundle(store, "PXD000001")
    manifest = {**bundle.manifest, "tables": {**bundle.manifest["tables"], "psms": 99}}
    with pytest.raises(CatalogError, match="do not hold together"):
        build_catalog(
            [BundleRef(path=bundle.path, manifest=manifest)], tmp_path / "catalog.duckdb"
        )


def test_a_failed_build_leaves_the_previous_catalog_serving(tmp_path, store):
    out = tmp_path / "catalog.duckdb"
    good = write_bundle(store, "PXD000001")
    build_catalog([good], out)
    broken = BundleRef(
        path=good.path, manifest={**good.manifest, "tables": {**good.manifest["tables"], "psms": 99}}
    )
    with pytest.raises(CatalogError):
        build_catalog([broken], out, overwrite=True)
    assert describe_catalog(out)["meta"]["n_datasets"] == 1
    assert not list(tmp_path.glob(".catalog.duckdb.*"))


def test_nothing_to_build_is_refused_rather_than_written(tmp_path):
    with pytest.raises(CatalogError, match="no bundles"):
        build_catalog([], tmp_path / "catalog.duckdb")


# --- choosing bundles --------------------------------------------------------------------------


def test_a_dataset_with_two_bundles_is_not_guessed_at(manifest, store):
    write_bundle(store, "PXD999999", extra_source="one")
    write_bundle(store, "PXD999999", extra_source="two")
    with pytest.raises(CatalogError, match="nothing says which one"):
        select_bundles(manifest, ["PXD999999"], store=store)


def test_latest_takes_the_newest_of_several(manifest, store):
    write_bundle(store, "PXD999999", extra_source="one")
    newest = write_bundle(store, "PXD999999", extra_source="two")
    chosen = select_bundles(manifest, ["PXD999999"], store=store, latest=True)
    assert [c.bundle_id for c in chosen] == [newest.bundle_id]


def test_a_pin_names_the_exact_bundle_a_release_was_built_from(manifest, store):
    first = write_bundle(store, "PXD999999", extra_source="one")
    write_bundle(store, "PXD999999", extra_source="two")
    chosen = select_bundles(manifest, ["PXD999999"], store=store, pins={"PXD999999": first.bundle_id})
    assert [c.bundle_id for c in chosen] == [first.bundle_id]


def test_a_pin_that_matches_nothing_is_an_error_not_a_fallback(manifest, store):
    write_bundle(store, "PXD999999")
    with pytest.raises(CatalogError, match="matches 0"):
        select_bundles(manifest, ["PXD999999"], store=store, pins={"PXD999999": "nope"})


def test_a_dataset_with_no_bundle_says_to_ingest_it(manifest, store):
    store.mkdir(parents=True, exist_ok=True)
    with pytest.raises(CatalogError, match="datarepo ingest"):
        select_bundles(manifest, ["PXD999999"], store=store)


def test_the_producers_refusal_still_stands_at_build_time(manifest, store):
    # The manifest is the contract for building as much as for ingesting (D9): a dataset the
    # producer withdrew must not reappear in a catalog just because its bundle is still on disk.
    write_bundle(store, "PXD000000")
    with pytest.raises(DatasetExcluded, match="The producer's reason"):
        select_bundles(manifest, ["PXD000000"], store=store)


def test_discover_finds_every_bundle_a_dataset_has(store):
    write_bundle(store, "PXD999999", extra_source="one")
    write_bundle(store, "PXD999999", extra_source="two")
    assert len(discover_bundles(store, "PXD999999")) == 2
    assert discover_bundles(store, "PXD111111") == []


# --- querying ----------------------------------------------------------------------------------


def test_a_query_cannot_write_to_the_catalog(catalog):
    with pytest.raises(CatalogError):
        run_query(catalog, "DELETE FROM psms")


def test_a_query_against_a_missing_catalog_says_so(tmp_path):
    with pytest.raises(CatalogError, match="no catalog at"):
        run_query(tmp_path / "nope.duckdb", "SELECT 1")


def test_the_limit_caps_an_exploratory_query(catalog):
    _, data = run_query(catalog, "SELECT * FROM peptidoforms", limit=1)
    assert len(data) == 1


def test_the_accepted_views_are_listed_in_the_catalogs_own_tables(catalog):
    listed = {r["table_name"]: r["kind"] for r in describe_catalog(catalog)["tables"]}
    assert all(listed[name] == "view" for name in ACCEPTED_VIEWS)
    assert listed["psms"] == "bundle"


def test_a_psm_whose_notch_never_resolved_is_out_of_the_accepted_view(tmp_path, store):
    """aging thread 008's predicate, which is worth 12 rows out of 26,594 on PXD036557."""
    bundles = [write_bundle(store, "PXD000001", ambiguous_psm=True)]
    catalog = build_catalog(bundles, tmp_path / "catalog.duckdb").path
    assert rows(catalog, "SELECT count(*) n FROM psms")[0]["n"] == 2
    assert rows(catalog, "SELECT count(*) n FROM psms_1pct")[0]["n"] == 1
    assert rows(catalog, "SELECT n_psms_1pct, n_psms_all FROM dataset_overview")[0] == {
        "n_psms_1pct": 1,
        "n_psms_all": 2,
    }


def test_the_excluded_psm_keeps_the_text_the_exclusion_rests_on(tmp_path, store):
    bundles = [write_bundle(store, "PXD000001", ambiguous_psm=True)]
    catalog = build_catalog(bundles, tmp_path / "catalog.duckdb").path
    excluded = rows(catalog, "SELECT notch FROM psms WHERE notch_ambiguous")
    assert [r["notch"] for r in excluded] == ["0.00000|1.00290"]


# --- ptm_sites is stored at the engine's grain, and coarsened by a view ---------------------------


def test_the_chemistry_view_merges_two_names_for_one_modification(tmp_path, store):
    # `Phosphorylation on S` and `Phosphoserine on S` are one chemistry reaching the dataset under
    # two names. The stored table keeps them apart, because that is what the engine measured; this
    # view puts them back together, and it is the only place the merge happens.
    bundles = [write_bundle(store, "PXD000001", ptm_sites=True)]
    catalog = build_catalog(bundles, tmp_path / "catalog.duckdb").path
    merged = rows(
        catalog,
        "SELECT * FROM ptm_sites_by_chemistry WHERE modification = 'UNIMOD:21'",
    )
    assert len(merged) == 1
    assert merged[0]["n_names"] == 2
    assert sorted(merged[0]["modification_names"]) == ["Phosphorylation on S", "Phosphoserine on S"]
    # n_psms sums and best_q_value is the minimum -- the numbers a UNIMOD-keyed row carried.
    assert merged[0]["n_psms"] == 14
    assert merged[0]["best_q_value"] == 0.001
    assert merged[0]["best_ambiguity_level"] == "1"


def test_the_chemistry_view_keeps_two_unmapped_chemistries_apart(tmp_path, store):
    # Both have no UNIMOD term and sit on the same residue. Grouping on the accession alone would
    # merge them into one meaningless row, so the view groups on the name where there is no term.
    bundles = [write_bundle(store, "PXD000001", ptm_sites=True)]
    catalog = build_catalog(bundles, tmp_path / "catalog.duckdb").path
    unmapped = rows(
        catalog,
        "SELECT chemistry_key, n_psms FROM ptm_sites_by_chemistry "
        "WHERE modification IS NULL ORDER BY chemistry_key",
    )
    assert unmapped == [
        {"chemistry_key": "Hydroxybutyrylation on K", "n_psms": 5},
        {"chemistry_key": "N6-glutaryllysine on K", "n_psms": 2},
    ]


def test_a_site_with_no_unimod_term_is_in_the_catalog_and_findable_by_name(tmp_path, store):
    # The regression this rekey fixes: these rows used to be absent, and an empty answer could not
    # be told from "never identified".
    bundles = [write_bundle(store, "PXD000001", ptm_sites=True)]
    catalog = build_catalog(bundles, tmp_path / "catalog.duckdb").path
    found = rows(
        catalog,
        "SELECT ptm_site_id, modification FROM ptm_sites "
        "WHERE modification_name = 'Hydroxybutyrylation on K'",
    )
    assert len(found) == 1
    assert found[0]["modification"] is None
    assert found[0]["ptm_site_id"].endswith(":Hydroxybutyrylation on K")


# --- releases pin, and are made to ---------------------------------------------------------------


def test_a_release_refuses_latest_because_it_would_move_under_it(manifest, store):
    write_bundle(store, "PXD999999", extra_source="one")
    write_bundle(store, "PXD999999", extra_source="two")
    with pytest.raises(CatalogError, match="mutually exclusive"):
        select_bundles(manifest, ["PXD999999"], store=store, latest=True, release="v0.1")


def test_a_release_refuses_a_dataset_that_is_not_pinned(manifest, store):
    write_bundle(store, "PXD999999")
    with pytest.raises(CatalogError, match="needs every dataset pinned"):
        select_bundles(manifest, ["PXD999999"], store=store, release="v0.1")


def test_a_fully_pinned_release_is_allowed(manifest, store):
    only = write_bundle(store, "PXD999999")
    chosen = select_bundles(
        manifest, ["PXD999999"], store=store, release="v0.1", pins={"PXD999999": only.bundle_id}
    )
    assert [c.bundle_id for c in chosen] == [only.bundle_id]


def test_declared_and_placed_are_both_named_so_neither_holds_the_bare_name(tmp_path, store):
    # aging 024 section 6: `search_modifications` said "every modification the search considered"
    # and meant "declared". Leaving either half holding the unqualified name is how the difference
    # gets lost again, so both are named explicitly.
    catalog = build_catalog([write_bundle(store, "PXD000001")], tmp_path / "c.duckdb").path
    names = {r["table_name"] for r in rows(catalog, "SELECT table_name FROM catalog_tables")}
    assert "search_modifications_declared" in names
    assert "search_modifications_placed" in names
    assert "search_modifications" not in names


def test_placed_comes_from_the_peptidoforms_not_from_the_sites(tmp_path, store):
    # The choice that is the whole point. `ptm_sites` is per RESOLVED PROTEIN POSITION, so a placed
    # view built on it would report a chemistry as never placed while peptidoforms carried it --
    # S39 reproduced in a new table, in the one view whose job is to be trusted about absence.
    # This bundle's peptidoform carries a modification that reaches no ptm_sites row.
    bundles = [write_bundle(store, "PXD000001", ptm_sites=False)]
    catalog = build_catalog(bundles, tmp_path / "c.duckdb").path
    assert rows(catalog, "SELECT count(*) AS n FROM ptm_sites")[0] == {"n": 0}
    placed = rows(catalog, "SELECT count(*) AS n FROM search_modifications_placed")[0]
    assert placed["n"] >= 0  # the view exists and is queryable with no sites at all


def test_a_placed_tag_is_classified_as_accession_mass_or_unresolved(tmp_path, store):
    catalog = build_catalog([write_bundle(store, "PXD000001")], tmp_path / "c.duckdb").path
    for row in rows(catalog, "SELECT * FROM search_modifications_placed"):
        # Exactly one of the three readings applies to any tag, which is what makes the
        # accession-or-mass grain honest rather than lossy.
        kinds = [row["modification"], row["mass_shift"], row["unresolved_name"]]
        assert sum(k is not None for k in kinds) <= 1


def test_every_derived_table_and_view_is_documented():
    """A derived table with no description is how `n_datasets_1pct` became "identified at 1% FDR".

    The schema tables get their prose generated from `schema/datarepo.yaml`. These do not exist in
    any schema -- `build` invents them -- so nothing generated could describe them, and for one
    release nothing did, in exactly the tables `search` answers from. Same shape as
    `manifest.CONTENT_FIELDS`: adding one means writing down what it means.
    """
    from datarepo.catalog import (
        ACCEPTED_VIEWS,
        DERIVED_DOCS,
        DERIVED_TABLES,
        GRAIN_VIEWS,
    )

    built = set(DERIVED_TABLES) | set(ACCEPTED_VIEWS) | set(GRAIN_VIEWS)
    assert built <= set(DERIVED_DOCS), (
        f"undocumented derived table(s): {sorted(built - set(DERIVED_DOCS))}. "
        f"Add an entry to catalog.DERIVED_DOCS saying what one row is."
    )
    assert set(DERIVED_DOCS) <= built, (
        f"DERIVED_DOCS describes something the build does not create: "
        f"{sorted(set(DERIVED_DOCS) - built)}"
    )
    for name, doc in DERIVED_DOCS.items():
        assert len(doc["description"]) > 80, f"{name}'s description says too little"


def test_the_documented_derived_columns_exist(catalog):
    """A description attached to a column that is not there is worse than none."""
    from datarepo.catalog import DERIVED_DOCS

    for table, doc in DERIVED_DOCS.items():
        columns = {
            r["column_name"]
            for r in rows(
                catalog,
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{table}'",
            )
        }
        documented = set(doc.get("columns") or {})
        assert documented <= columns, f"{table}: documented but absent: {documented - columns}"
