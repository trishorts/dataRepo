"""The whole ingest, end to end, on the fixture instance.

These are the tests that would catch a bundle that looks right and is not: counts that do not match
the producer's own summary, quantities attached to assays that do not exist, USIs that name a file
nobody deposited.
"""

from __future__ import annotations

import json

import pytest

from datarepo.errors import DatasetExcluded
from datarepo.ingest import ingest_dataset
from datarepo.integrity import check

from conftest import MM_SETTINGS, needs_pymzlib

pytestmark = needs_pymzlib


def test_every_reconciliation_check_agrees_with_the_producer(bundle):
    mismatched = [c for c in bundle.checks if not c["ok"]]
    assert mismatched == [], f"counts drifted from the producer's summary: {mismatched}"


def test_the_bundle_holds_together(tables):
    assert check(tables) == []


def test_the_manifest_records_what_was_read_and_what_came_out(bundle):
    doc = json.loads((bundle.bundle_path / "bundle.json").read_text(encoding="utf-8"))
    assert doc["dataset_id"] == "PXD999999"
    assert doc["provenance_schema"] == "aging-provenance/2"
    assert doc["licence"] == "CC-BY-4.0"
    assert doc["tables"]["psms"] == 60
    roles = {s["role"] for s in doc["sources"]}
    assert {"psms", "peptides", "qc_report", "sdrf", "results_txt"} <= roles
    assert "provenance:04_search" in roles


def test_the_reader_log_says_which_backend_read_each_file(bundle):
    doc = json.loads((bundle.bundle_path / "bundle.json").read_text(encoding="utf-8"))
    backends = {e["file"]: e["backend"] for e in doc["readers"]}
    assert backends["AllPSMs.psmtsv"] == "pymzlib"
    assert backends["AllQuantifiedPeptides.tsv"] == "datarepo-tsv"
    # Every in-house read carries the reason pyMzLib could not do it.
    assert all(e.get("note") for e in doc["readers"] if e["backend"] == "datarepo-tsv")


def test_the_lineage_is_the_provenance_chain_not_a_directory_scan(tables):
    stages = {r["stage"] for r in tables["provenance_records"]}
    assert stages == {"search_metamorpheus", "qc_spectra", "fetch"}


def test_every_psm_carries_a_resolvable_usi(tables):
    psms = tables["psms"]
    assert psms
    assert all(p["usi"] and p["usi"].startswith("mzspec:PXD999999:") for p in psms)
    # The USI must name the deposited file, not the calibrated copy the search reported.
    assert all("-calib" not in p["usi"] for p in psms)


def test_peptidoforms_are_proforma_with_unimod_accessions(tables):
    modified = [p for p in tables["peptidoforms"] if "[" in p["peptidoform"]]
    assert modified, "the fixture should contain modified peptidoforms"
    assert any("UNIMOD:" in p["peptidoform"] for p in modified)


def test_quantities_never_store_a_zero(tables):
    assert all(q["value"] != 0 for q in tables["quant_values"])


def test_every_quantity_carries_a_definition_that_is_in_the_bundle(tables):
    known = {d["definition_id"] for d in tables["definitions"]}
    assert {q["definition_id"] for q in tables["quant_values"]} <= known
    assert {m["definition_id"] for m in tables["metrics"]} <= known


def test_provisional_definitions_say_they_are_provisional(tables):
    for row in tables["definitions"]:
        if row["definition_id"].startswith("PROVISIONAL:"):
            assert "PROVISIONAL" in row["text"]
            assert "provisional" in row["owner_project"].lower()


def test_the_producers_flags_arrive_as_findings(tables):
    codes = {f["code"] for f in tables["findings"]}
    assert {"low_id_rate", "no_design_file"} <= codes


def test_a_skeleton_sdrf_is_flagged_so_nobody_mistakes_it_for_annotation(tables):
    codes = {f["code"] for f in tables["findings"]}
    assert "sdrf_skeleton" in codes


def test_decoy_accessions_are_not_presented_as_uniprot_entries(tables):
    by_accession = {p["protein_accession"]: p for p in tables["proteins"]}
    assert by_accession["DECOY_P12345"]["source_db"] == "decoy"
    assert by_accession["CONTAM_P00001"]["source_db"] == "contaminants"
    assert by_accession["CONTAM_P00001"]["is_contaminant"] is True


def test_ptm_sites_come_only_from_accepted_evidence(tables):
    assert tables["ptm_sites"], "the fixture should yield some sites"
    for site in tables["ptm_sites"]:
        assert site["best_q_value"] <= 0.01
        assert site["position"] >= 1
        # The name is the key component and is always there; the accession is a derived view and
        # may be absent, which is the whole point of the rekey (aging 019 section 3).
        assert site["modification_name"]
        assert site["ptm_site_id"].endswith(f":{site['modification_name']}")
        assert site["modification"] is None or site["modification"].startswith("UNIMOD:")


def test_a_modification_with_no_unimod_accession_still_gets_its_sites(tables):
    # It used to get none: the key could not be formed, so the rows were dropped rather than
    # written with a null, and the loss was invisible in the table PTM stoichiometry reads.
    unmapped = [s for s in tables["ptm_sites"] if s["modification"] is None]
    assert unmapped, "the fixture carries a modification with no UNIMOD cross-reference"
    names = {s["modification_name"] for s in unmapped}
    assert names == {"N6,N6-dimethyllysine on K"}
    # The name carries a comma, which is fine -- ':' is the only character the key cannot hold.
    assert all(":" not in n for n in names)
    # The key is still a key: one row per (protein, position, modification).
    assert len({s["ptm_site_id"] for s in unmapped}) == len(unmapped)
    assert all(s["n_psms"] >= 1 and s["best_q_value"] <= 0.01 for s in unmapped)


def test_an_unmapped_modification_is_still_named_in_a_finding(tables):
    # Option (1) makes the absence queryable; the finding stays, because a caller who never looks
    # at ptm_sites should still be told the bundle holds a chemistry with no Unimod term.
    finding = next(f for f in tables["findings"] if f["code"] == "unresolved_modifications")
    assert finding["severity"] == "warning"
    assert "modification_name" in finding["message"]


def test_the_site_key_refuses_a_modification_name_it_cannot_encode(tables):
    from datarepo.errors import IngestError
    from datarepo.sources.identifications import _site_key_name

    assert _site_key_name("Oxidation on M", "PEPM[x]IDE") == "Oxidation on M"
    with pytest.raises(IngestError, match="ptm_site_id separator"):
        _site_key_name("Common Fixed:Carbamidomethyl on C", "PEPC[y]IDE")


def test_re_ingesting_unchanged_inputs_is_a_no_op(manifest, tmp_path):
    entry = manifest.dataset("PXD999999")
    first = ingest_dataset(manifest, entry, store=tmp_path / "s", mm_settings=MM_SETTINGS)
    again = ingest_dataset(manifest, entry, store=tmp_path / "s", mm_settings=MM_SETTINGS)
    assert first.bundle_id == again.bundle_id
    assert again.skipped is True


def test_an_excluded_dataset_is_never_ingested(manifest, tmp_path):
    with pytest.raises(DatasetExcluded):
        ingest_dataset(manifest, manifest.datasets["PXD000000"], store=tmp_path / "s")


def test_an_excluded_dataset_leaves_nothing_behind(manifest, tmp_path):
    store = tmp_path / "s"
    with pytest.raises(DatasetExcluded):
        manifest.dataset("PXD000000")
    assert not store.exists()
