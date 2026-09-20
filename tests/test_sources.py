"""Each producer file turned into rows: provenance, QC, the SDRF, the FlashLFQ tables."""

from __future__ import annotations

import json

import pytest

from datarepo.errors import UnsupportedProvenance
from datarepo.readers import read_results_txt, read_tsv
from datarepo.sources import provenance as prov
from datarepo.sources import quant, runs as runs_source, sdrf as sdrf_source, search_params
from datarepo.usi import RunNameMap, mint, strip_pipeline_suffix

from conftest import MM_SETTINGS, SEARCH_RESULTS, WORK_ROOT, needs_pymzlib

RUN = WORK_ROOT / "run_test/PXD999999"


# --- provenance -------------------------------------------------------------------------------

def test_the_provenance_version_decides_which_definition_the_psm_count_gets():
    doc = {"schema": "aging-provenance/2", "id_rate": {"psms_1pct": 27958, "ms2": 266402, "rate": 0.1}}
    rows = {r["name"]: r for r in prov.metric_rows(doc, "PXD1", 2)}
    # In /2 the field called psms_1pct is the FDR engine's count, whatever its name says.
    assert "psms_1pct" not in rows
    assert rows["psms_fdr_engine_1pct"]["value"] == 27958
    assert rows["psms_fdr_engine_1pct"]["definition_id"] == "aging:DEF-PSM-FDRENGINE"


def test_provenance_3_carries_both_counts_under_their_own_definitions():
    doc = {"schema": "aging-provenance/3",
           "id_rate": {"psms_1pct": 26582, "psms_fdr_engine_1pct": 27958, "ms2": 1, "rate": 0.1}}
    rows = {r["name"]: r for r in prov.metric_rows(doc, "PXD1", 3)}
    assert rows["psms_1pct"]["definition_id"] == "aging:DEF-PSM-1PCT"
    assert rows["psms_fdr_engine_1pct"]["definition_id"] == "aging:DEF-PSM-FDRENGINE"


def test_an_old_provenance_schema_is_refused_rather_than_misread():
    with pytest.raises(UnsupportedProvenance, match="aging-provenance/1"):
        prov.schema_version({"schema": "aging-provenance/1"})


def test_an_unrecognisable_provenance_schema_is_refused():
    with pytest.raises(UnsupportedProvenance):
        prov.schema_version({"schema": "something-else/2"})


def test_flags_become_findings_that_explain_themselves():
    doc = {"flags": ["low_id_rate: 9/300 = 3.0% (S3)", "no_design_file: none written"]}
    rows = {r["code"]: r for r in prov.finding_rows(doc, "PXD1", "provenance.json")}
    assert rows["low_id_rate"]["severity"] == "warning"
    assert "weak evidence" in rows["low_id_rate"]["message"]
    assert "9/300" in rows["low_id_rate"]["message"]  # the producer's own note is kept


def test_a_provenance_record_keeps_the_heavy_blocks_verbatim():
    doc = json.loads((RUN / "04_search/provenance.json").read_text(encoding="utf-8"))
    row = prov.record_row(doc, "PXD999999", stage_dir_name="04_search",
                          bundle_path="sources/p.json", sha256="0" * 64)
    assert row["provenance_schema"] == "aging-provenance/2"
    assert row["pipeline_repo"] == "trishorts/aging"
    assert json.loads(row["params_json"])["metamorpheus_version"] == "1.1.11"
    assert row["original_path"] == "sources/p.json"


# --- runs and QC ------------------------------------------------------------------------------

def test_runs_combine_the_fetch_manifest_the_qc_report_and_the_sdrf():
    fetch = runs_source.load_fetch_manifest(RUN / "02_fetch/fetch_manifest.json")
    qc = runs_source.load_qc_report(RUN / "02b_qc/qc_report.json")
    parsed = sdrf_source.parse(RUN / "02_fetch/metadata/PXD999999.sdrf.tsv", "PXD999999")
    rows, metrics = runs_source.build("PXD999999", fetch=fetch, qc=qc, run_facts=parsed.run_facts)
    assert [r["run_id"] for r in rows] == [
        "PXD999999:QE-002106_GM1_a", "PXD999999:QE-002107_GM1_b",
    ]
    first = rows[0]
    assert first["sha256"] == "sha256-0"
    assert first["pride_checksum_sha1"] == "sha1-0"
    assert first["fragmentation"] == ["HCD"]
    assert first["ms2_spectra"] == 150
    assert first["qc_pass"] is True
    assert first["instrument_model"] == "Q Exactive Plus"
    # aging 006: neither is available yet, and raw headers must not be parsed here.
    assert first["acquisition_datetime"] is None
    assert {m["name"] for m in metrics} == {"ms2", "run_minutes"}


# --- SDRF -------------------------------------------------------------------------------------

def test_the_sdrf_gives_one_sample_per_source_name_and_one_assay_per_run():
    parsed = sdrf_source.parse(RUN / "02_fetch/metadata/PXD999999.sdrf.tsv", "PXD999999")
    assert [s["sample_id"] for s in parsed.samples] == [
        "PXD999999:PXD999999-Sample-1", "PXD999999:PXD999999-Sample-2",
    ]
    assert parsed.assays[0]["channel"] == "label_free"
    assert parsed.assays[0]["assay_id"] == "PXD999999:QE-002106_GM1_a:label_free"


def test_not_available_becomes_null_rather_than_a_string():
    parsed = sdrf_source.parse(RUN / "02_fetch/metadata/PXD999999.sdrf.tsv", "PXD999999")
    sample = parsed.samples[0]
    assert sample["organism_part"] is None
    assert sample["disease"] is None
    assert sample["organism"] == "NCBITaxon:9606"  # mapped from the organism name


def test_every_characteristic_is_kept_verbatim_even_when_it_has_no_curated_column():
    parsed = sdrf_source.parse(RUN / "02_fetch/metadata/PXD999999.sdrf.tsv", "PXD999999")
    names = {c["name"] for c in parsed.characteristics}
    assert "characteristics[organism]" in names
    assert "characteristics[biological replicate]" in names
    # `not available` cells carry no information, so they are not stored as characteristics.
    assert "characteristics[disease]" not in names


def test_an_ontology_term_in_the_cell_is_preferred_over_a_name_lookup():
    assert sdrf_source.parse_value("NT=Q Exactive Plus;AC=MS:1002634")["AC"] == "MS:1002634"
    assert sdrf_source.parse_value("Homo sapiens") == {"NT": "Homo sapiens"}


# --- FlashLFQ ---------------------------------------------------------------------------------

def test_a_zero_intensity_produces_no_quant_row_because_missing_is_not_zero(registry):
    from datarepo.proforma import ProformaCache

    names = RunNameMap(("QE-002106_GM1_a", "QE-002107_GM1_b"))
    rows = quant.peptide_quant_rows(
        SEARCH_RESULTS / "AllQuantifiedPeptides.tsv", "PXD999999",
        run_names=names, to_proforma=ProformaCache(registry),
    )
    assert rows, "the fixture should produce quantities"
    assert all(r["value"] not in (0, 0.0) for r in rows)
    assert all(r["detection_type"] != "not_detected" for r in rows)


def test_detection_type_and_the_mbr_flag_come_from_the_producer(registry):
    from datarepo.proforma import ProformaCache

    names = RunNameMap(("QE-002106_GM1_a", "QE-002107_GM1_b"))
    peaks = quant.peak_quality(
        SEARCH_RESULTS / "AllQuantifiedPeaks.tsv", "PXD999999",
        run_names=names, mbr_q_threshold=0.01,
    )
    rows = quant.peptide_quant_rows(
        SEARCH_RESULTS / "AllQuantifiedPeptides.tsv", "PXD999999",
        run_names=names, to_proforma=ProformaCache(registry), peak_quality_index=peaks,
    )
    assert {r["detection_type"] for r in rows} <= {"MSMS", "MBR", None}
    flagged = [r for r in rows if r["mbr_kept"] is not None]
    assert flagged, "the peak table should have supplied at least one MBR verdict"
    assert all((r["mbr_kept"] is True) == (r["pip_q_value"] <= 0.01) for r in flagged)


def test_a_protein_group_q_value_of_exactly_zero_survives():
    names = RunNameMap(("QE-002106_GM1_a", "QE-002107_GM1_b"))
    groups, quants, count = quant.protein_group_rows(
        SEARCH_RESULTS / "AllQuantifiedProteinGroups.tsv", "PXD999999", run_names=names
    )
    by_id = {g["protein_group_id"]: g for g in groups}
    assert by_id["PXD999999:P68363;Q71U36"]["q_value"] == 0.0


def test_the_producer_counts_contaminant_groups_but_not_decoys():
    names = RunNameMap(("QE-002106_GM1_a", "QE-002107_GM1_b"))
    groups, _quants, count = quant.protein_group_rows(
        SEARCH_RESULTS / "AllQuantifiedProteinGroups.tsv", "PXD999999", run_names=names
    )
    statuses = {g["protein_group_id"]: g["target_decoy"] for g in groups}
    assert statuses["PXD999999:DECOY_P12345"] == "decoy"
    assert statuses["PXD999999:CONTAM_P00001"] == "contaminant"
    assert count == 3  # two targets at q <= 0.01 plus the contaminant; the decoy never counts


def test_intensity_and_spectral_count_are_told_apart_by_their_definition():
    names = RunNameMap(("QE-002106_GM1_a", "QE-002107_GM1_b"))
    _groups, quants, _count = quant.protein_group_rows(
        SEARCH_RESULTS / "AllQuantifiedProteinGroups.tsv", "PXD999999", run_names=names
    )
    definitions = {q["definition_id"] for q in quants}
    assert definitions == {"PROVISIONAL:PROTEIN-INTENSITY", "PROVISIONAL:PROTEIN-SPECTRAL-COUNT"}


# --- search parameters ------------------------------------------------------------------------

def test_only_the_tasks_that_ran_contribute_search_modifications(registry):
    doc = json.loads((RUN / "04_search/provenance.json").read_text(encoding="utf-8"))
    files = [WORK_ROOT / e["path"] for e in doc["inputs"] if e["path"].endswith("Task.toml")]
    rows = search_params.modification_rows(files, "PXD999999", registry)
    names = {r["name"] for r in rows}
    assert {"Carbamidomethyl on C", "Oxidation on M", "Hydroxylation on K", "Calcium on D"} == names
    # GlycoSearchTask.toml is a shipped template that did not run; its mods must not appear.
    assert "Phosphorylation on S" not in names


def test_a_modification_with_no_unimod_still_gets_a_row(registry):
    doc = json.loads((RUN / "04_search/provenance.json").read_text(encoding="utf-8"))
    files = [WORK_ROOT / e["path"] for e in doc["inputs"] if e["path"].endswith("Task.toml")]
    rows = {r["name"]: r for r in search_params.modification_rows(files, "PXD999999", registry)}
    assert rows["Calcium on D"]["modification"] is None
    assert rows["Calcium on D"]["usage"] == "gptmd"
    assert rows["Carbamidomethyl on C"]["modification"] == "UNIMOD:4"


def test_the_searched_database_comes_from_the_provenance_inputs():
    doc = json.loads((RUN / "04_search/provenance.json").read_text(encoding="utf-8"))
    name, sha = search_params.searched_database(doc)
    assert name == "test_human.xml"
    assert sha == "e" * 64


# --- results.txt and USIs -----------------------------------------------------------------------

def test_results_txt_totals_are_read_per_scope():
    results = read_results_txt(SEARCH_RESULTS / "results.txt")
    assert "psms" in results[""]
    assert results[""]["ms2_scans"] == 300
    assert results["QE-002106_GM1_a-calib"]["ms2_scans"] == 150


def test_a_calibration_suffix_is_stripped_to_reach_the_deposited_name():
    assert strip_pipeline_suffix("QE-002123_GM7_b-calib") == "QE-002123_GM7_b"
    assert strip_pipeline_suffix("plain") == "plain"


def test_an_unmatched_run_gets_no_usi_and_is_recorded():
    names = RunNameMap(("QE-002106_GM1_a",))
    assert names.resolve("QE-002106_GM1_a-calib") == "QE-002106_GM1_a"
    assert names.resolve("somewhere_else-calib") is None
    assert names.unmatched == {"somewhere_else-calib": 1}


def test_a_usi_names_the_deposited_file_and_carries_the_proforma():
    assert mint("PXD1", "run_a", 42, "PEPC[UNIMOD:4]K", 2) == "mzspec:PXD1:run_a:scan:42:PEPC[UNIMOD:4]K/2"


# --- the notch, which is what makes a producer's PSM count reproducible -------------------------


def test_an_unresolved_notch_is_recognised_by_its_separator():
    from datarepo.sources.identifications import notch_ambiguous

    assert notch_ambiguous("0.00000|1.00290") is True
    assert notch_ambiguous("0") is False
    assert notch_ambiguous(0) is False


def test_a_missing_notch_is_absence_not_resolution():
    # NA is never a value here either: a producer that reports no notch has not told us the notch
    # resolved, and counting it as resolved would be inventing an answer.
    from datarepo.sources.identifications import notch_ambiguous

    assert notch_ambiguous(None) is None
    assert notch_ambiguous("   ") is None


def test_the_producer_count_drops_a_psm_whose_notch_never_resolved():
    """aging thread 008: this clause is the whole of the 12-PSM difference on PXD036557."""
    from datarepo.sources.identifications import producer_counts

    columns = {
        "q_value": [0.001, 0.001, 0.001],
        "q_value_notch": [0.001, 0.001, 0.001],
        "decoy_contam_target": ["T", "T", "T"],
        "notch": ["0", "0.00000|1.00290", None],
    }
    assert producer_counts(columns) == 2


@needs_pymzlib
def test_every_psm_carries_the_notch_its_flag_was_derived_from(tables):
    """The flag is a conclusion; the text is the evidence. A bundle must hold both."""
    from datarepo.sources.identifications import notch_ambiguous

    psms = tables["psms"]
    assert psms, "the fixture bundle has no PSMs"
    for row in psms:
        assert row["notch_ambiguous"] == notch_ambiguous(row["notch"])


# --- SDRF now goes through pyMzLib (DATAREPO-13, fixed in 0.1.1) --------------------------------


@needs_pymzlib
def test_the_sdrf_is_read_by_pymzlib_not_by_us(bundle):
    """The in-house SDRF read is deleted, and the bundle's own log is what proves it."""
    import json

    manifest = json.loads((bundle.bundle_path / "bundle.json").read_text(encoding="utf-8"))
    sdrf_entries = [r for r in manifest["readers"] if r["file"].endswith(".sdrf.tsv")]
    assert sdrf_entries, "the fixture bundle read no SDRF"
    assert all(r["backend"] == "pymzlib" for r in sdrf_entries)
    assert all("note" not in r for r in sdrf_entries), "a pyMzLib read needs no excuse"


@needs_pymzlib
def test_a_repeated_characteristics_column_is_kept_rather_than_overwritten(tmp_path):
    """An SDRF column name is a position, not a key -- pyMzLib's own caveat, and it is real.

    `comment[modification parameters]` appears twice in PXD036557's own SDRF. A name-keyed map
    keeps the last occurrence and silently drops the rest, so characteristics are copied by
    walking the pairs instead.
    """
    path = tmp_path / "PXD000000.sdrf.tsv"
    path.write_text(
        "source name\tcharacteristics[organism]\tcharacteristics[disease]\t"
        "characteristics[disease]\tassay name\tcomment[data file]\n"
        "S1\tHomo sapiens\tprogeria\tcardiomyopathy\trun1\trun1.raw\n",
        encoding="utf-8",
    )
    table = sdrf_source.parse(path, "PXD000000")
    diseases = [c["value"] for c in table.characteristics if c["name"] == "characteristics[disease]"]
    assert diseases == ["progeria", "cardiomyopathy"]


# --- a shared peptide sits at a different residue in each protein --------------------------------


def test_residue_starts_keeps_one_span_per_protein():
    from datarepo.sources.identifications import _residue_starts

    assert _residue_starts("[10 to 20]|[155 to 165]") == [10, 155]
    assert _residue_starts("[10 to 20]") == [10]
    assert _residue_starts("") == []


@needs_pymzlib
def test_a_site_is_placed_in_each_protein_at_that_proteins_own_coordinates(registry):
    """Taking the leading protein's start for all of them is right once and wrong thereafter.

    PXD036557 carries 3,154 PSMs whose accessions have differing spans; none is at ambiguity
    level 1, so only the level filter has kept this from producing wrong positions.
    """
    from datarepo.proforma import ProformaCache
    from datarepo.sources.identifications import ptm_site_rows

    columns = {
        "full_sequence": ["PEPTC[Common Fixed:Carbamidomethyl on C]IDEK"],
        "accession": ["P11111|P22222"],
        "start_and_end_residues_in_parent_sequence": ["[10 to 20]|[155 to 165]"],
        "ambiguity_level": ["1"],
        "q_value": [0.001],
        "decoy_contam_target": ["T"],
    }
    rows = ptm_site_rows(columns, "PXD999999", proforma=ProformaCache(registry))
    placed = {r["protein_accession"]: r["position"] for r in rows}
    assert placed == {"P11111": 14, "P22222": 159}


# --- ptm_sites after aging 013: no level filter, contaminants kept and marked --------------------


def _site_columns(**over):
    columns = {
        "full_sequence": ["PEPTC[Common Fixed:Carbamidomethyl on C]IDEK"],
        "accession": ["P11111"],
        "start_and_end_residues_in_parent_sequence": ["[10 to 20]"],
        "ambiguity_level": ["1"],
        "q_value": [0.001],
        "decoy_contam_target": ["T"],
    }
    columns.update({k: [v] for k, v in over.items()})
    return columns


@needs_pymzlib
def test_a_site_is_emitted_at_any_ambiguity_level(registry):
    """DEF-OCC-PSMS applies no level filter, so a level filter here cannot key the R7 table."""
    from datarepo.proforma import ProformaCache
    from datarepo.sources.identifications import ptm_site_rows

    rows = ptm_site_rows(_site_columns(ambiguity_level="2D"), "PXD1", proforma=ProformaCache(registry))
    assert [r["best_ambiguity_level"] for r in rows] == ["2D"]


@needs_pymzlib
def test_a_contaminant_site_is_kept_and_marked_rather_than_dropped(registry):
    """Occupancy is computed on groups that include contaminants, so dropping them loses real sites."""
    from datarepo.proforma import ProformaCache
    from datarepo.sources.identifications import ptm_site_rows

    rows = ptm_site_rows(_site_columns(decoy_contam_target="C"), "PXD1", proforma=ProformaCache(registry))
    assert [r["target_decoy"] for r in rows] == ["contaminant"]


@needs_pymzlib
def test_a_decoy_site_is_still_dropped(registry):
    from datarepo.proforma import ProformaCache
    from datarepo.sources.identifications import ptm_site_rows

    assert ptm_site_rows(
        _site_columns(decoy_contam_target="D"), "PXD1", proforma=ProformaCache(registry)
    ) == []


def test_the_best_ambiguity_level_is_the_lowest_one_seen():
    from datarepo.sources.identifications import _better_level

    assert _better_level("2D", "1") == "1"
    assert _better_level("1", "2D") == "1"
    assert _better_level(None, "3") == "3"
    assert _better_level("2A", None) == "2A"
    assert _better_level("2D", "unknown-level") == "2D"
