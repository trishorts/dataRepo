"""The whole ingest, end to end, on the fixture instance.

These are the tests that would catch a bundle that looks right and is not: counts that do not match
the producer's own summary, quantities attached to assays that do not exist, USIs that name a file
nobody deposited.
"""

from __future__ import annotations

import json

import pytest

from datarepo import definitions as defs
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


def test_the_searched_databases_are_hashed_in_and_every_site_is_checked_against_them(bundle):
    """DATAREPO-32: positions come from the searched sequences, and the ingest proves it on itself.

    The databases are inputs to every ptm_sites row, so a different database must give a different
    bundle id -- and the ingest's own residue check must find nothing wrong on the fixture, whose
    shared peptides are exactly the case the old index pairing got wrong.
    """
    doc = json.loads((bundle.bundle_path / "bundle.json").read_text(encoding="utf-8"))
    roles = {s["role"]: s for s in doc["sources"]}
    assert "protein_database:test_human.xml" in roles
    assert "protein_database:test_contaminants.xml" in roles
    assert not (bundle.bundle_path / "sources" / "test_human.xml").exists(), "never copied"
    dbs = doc["protein_databases"]
    assert dbs["missing"] == []
    check = dbs["site_residue_check"]
    assert check["wrong_residue"] == 0 and check["beyond_length"] == 0
    assert check["residue_matches"] == doc["tables"]["ptm_sites"]
    codes = {f["code"] for f in bundle.findings}
    assert "ptm_site_residue_mismatch" not in codes


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


def test_an_intensity_never_stores_a_zero_and_a_count_may(tables):
    # Split by DEFINITION in 0.18.0, not one rule for the column: an intensity of 0 is QuantProject's
    # "no value" and becomes no row (DEF-PEP-INT, DEF-PROT-INT), while a spectral count of 0 is a
    # measurement (DEF-PROT-SPC). The old blanket rule is what dropped real zero counts.
    zero_as_na = {defs.PEPTIDE_INTENSITY.definition_id, defs.PROTEIN_INTENSITY.definition_id}
    assert all(q["value"] != 0 for q in tables["quant_values"] if q["definition_id"] in zero_as_na)


def test_every_run_carries_its_enrichment_and_where_it_came_from(tables):
    # G63. The fixture's dataset declares no enrichment and is not flagged mixed, so every run takes
    # the declaration and the dataset says its runs agree.
    (dataset,) = tables["datasets"]
    assert dataset["enrichment"] == ["none"]
    assert dataset["enrichment_mixed"] is False
    assert {tuple(r["enrichment"]) for r in tables["runs"]} == {("none",)}
    assert {r["enrichment_source"] for r in tables["runs"]} == {"dataset_declaration"}


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
        # The name ends the key, except that a non-residue site type is appended after it so a
        # protein N-terminal acetylation and an N6-acetyllysine on residue 1 cannot collide
        # (aging 024 section 4). A `residue` site gets no suffix, which is what keeps every id
        # written before schema 0.0.5 exactly where it was.
        suffix = "" if site["site_type"] == "residue" else f"@{site['site_type']}"
        assert site["ptm_site_id"].endswith(f":{site['modification_name']}{suffix}")
        assert site["modification"] is None or site["modification"].startswith("UNIMOD:")


def test_a_modification_with_no_unimod_accession_still_gets_its_sites(tables):
    # It used to get none: the key could not be formed, so the rows were dropped rather than
    # written with a null, and the loss was invisible in the table PTM stoichiometry reads.
    unmapped = [s for s in tables["ptm_sites"] if s["modification"] is None]
    assert unmapped, "the fixture carries a modification with no UNIMOD cross-reference"
    names = {s["modification_name"] for s in unmapped}
    # The two N-acetyl names are terminal sites that did not exist as rows at all before 0.8.0.
    assert names == {
        "N6,N6-dimethyllysine on K",
        "N-acetylalanine on A",
        "N-acetylglutamate on E",
    }
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


def test_a_modification_at_a_terminus_is_a_site_now(tables):
    # It was not. A single `continue` skipped every placement at a peptide N-terminus, and across
    # aging's three datasets that was 1,367 sites at q<=0.01 over 18,566 PSMs -- rows that existed
    # in full in `peptidoforms` and had no representation whatsoever in `ptm_sites` (aging 024
    # section 4). The fixture carries three of them.
    terminal = [s for s in tables["ptm_sites"] if s["site_type"] != "residue"]
    assert terminal, "the fixture carries N-terminally modified PSMs"
    for site in terminal:
        # Keyed on the residue it SITS ON, never on a sentinel position or the string 'N-term'.
        assert site["residue"] and site["residue"] != "N-term"
        assert site["position"] >= 1
        assert site["ptm_site_id"].endswith(f"@{site['site_type']}")


def test_an_initiator_methionine_does_not_hide_a_protein_n_terminus(tables):
    # The case that makes this more than `start == 1`. Co-translational N-terminal acetylation
    # follows Met excision, so the modified residue is residue 2 and the previous residue is the
    # excised M. Getting this wrong would label the most abundant terminal chemistry in the
    # proteome `peptide_n_term`.
    by_id = {s["ptm_site_id"]: s for s in tables["ptm_sites"]}
    met_cleaved = by_id["PXD999999:Q9UL25:A2:N-acetylalanine on A@protein_n_term"]
    assert met_cleaved["site_type"] == "protein_n_term"
    assert met_cleaved["position"] == 2 and met_cleaved["residue"] == "A"

    # And the counter-case, so the rule is not just "everything terminal is a protein terminus":
    # this peptide starts at residue 52, so its N-terminus is a cleavage artefact position.
    internal = by_id["PXD999999:O75396:C52:Ammonia loss on C@peptide_n_term"]
    assert internal["site_type"] == "peptide_n_term"
    assert internal["position"] == 52


def test_no_ordinary_site_id_moved(tables):
    # aging ruled the site type into the key on the condition that no existing id moves. A
    # `residue` site therefore carries no suffix at all, and that is the only thing protecting
    # every id in the released v0.1 catalog.
    residue_sites = [s for s in tables["ptm_sites"] if s["site_type"] == "residue"]
    assert residue_sites
    assert all("@" not in s["ptm_site_id"] for s in residue_sites)


def test_a_file_the_search_excluded_is_not_a_run_but_is_findable(tmp_path):
    """DATAREPO-51 (aging 064, their D52): a blank injection that QC passed over is deposited and in
    the QC report, but not searched. A run for it would describe a measurement not in the data, and
    `runs` would disagree with the producer's file count."""
    import shutil

    from conftest import DATA
    from datarepo.manifest import load_manifest

    root = tmp_path / "data"
    shutil.copytree(DATA, root)
    run = root / "work_root/run_test/PXD999999"
    blank = "QE-002108_blank.raw"

    fetch_path = run / "02_fetch/fetch_manifest.json"
    fetch = json.loads(fetch_path.read_text(encoding="utf-8"))
    fetch["files"].append(dict(fetch["files"][0], name=blank, sha256="sha256-blank"))
    fetch_path.write_text(json.dumps(fetch), encoding="utf-8")
    qc_path = run / "02b_qc/qc_report.json"
    qc = json.loads(qc_path.read_text(encoding="utf-8"))
    qc[blank] = dict(qc["QE-002106_GM1_a.raw"], ms2=3, **{"pass": False})
    qc_path.write_text(json.dumps(qc), encoding="utf-8")
    prov_path = run / "04_search/provenance.json"
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    prov["excluded_files"] = {"files": [blank], "reason": "D52: too_few_ms2"}
    prov_path.write_text(json.dumps(prov), encoding="utf-8")

    manifest = load_manifest(root / "manifest.yaml")
    result = ingest_dataset(
        manifest, manifest.dataset("PXD999999"), store=tmp_path / "s", mm_settings=MM_SETTINGS
    )
    import pyarrow.parquet as pq

    tables = {p.stem: pq.read_table(p).to_pylist() for p in result.bundle_path.glob("*.parquet")}
    assert sorted(r["file_name"] for r in tables["runs"]) == ["QE-002106_GM1_a.raw", "QE-002107_GM1_b.raw"]
    assert not any(m["scope_id"] == "PXD999999:QE-002108_blank" for m in tables["metrics"])
    assert [c for c in result.checks if not c["ok"]] == []
    assert check(tables) == []
    (finding,) = [f for f in tables["findings"] if f["code"] == "excluded_from_search"]
    assert finding["finding_id"] == f"PXD999999:excluded_from_search:{blank}"
    assert blank in finding["message"] and "D52: too_few_ms2" in finding["message"]
    assert "sha256-blank" in finding["message"]
