"""Each producer file turned into rows: provenance, QC, the SDRF, the FlashLFQ tables."""

from __future__ import annotations

import json
from pathlib import Path

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


CONTAMINATION = {
    "schema": "aging-provenance/3",
    "contamination": {
        "psm_share": 0.039,
        "psm_share_definition": "aging DEF-CONTAM-PSM v1",
        "contaminant_psms": 1090,
        "target_plus_contaminant_psms": 27984,
        "intensity_share_per_file": {"GM3_c-calib": 0.189, "GM6_c-calib": 0.026},
        "intensity_share_definition": "QuantProject DEF-QC-9 v2",
        "intensity_share_median": 0.055,
        "intensity_share_min": 0.026,
        "intensity_share_max": 0.189,
    },
}


def test_the_contaminant_intensity_share_is_emitted_once_per_run():
    names = RunNameMap(("GM3_c", "GM6_c"))

    rows = prov.contamination_metric_rows(CONTAMINATION, "PXD1", run_names=names)

    per_run = [r for r in rows if r["scope"] == "run"]
    assert {r["scope_id"] for r in per_run} == {"PXD1:GM3_c", "PXD1:GM6_c"}
    assert {r["name"] for r in per_run} == {"contamination_intensity_share"}
    assert all(r["definition_id"] == "QuantProject:DEF-QC-9" for r in per_run)


def test_the_dataset_level_intensity_summaries_say_they_are_summaries():
    rows = prov.contamination_metric_rows(CONTAMINATION, "PXD1", run_names=RunNameMap(("GM3_c",)))

    summaries = [r for r in rows if r["name"].startswith("contamination_intensity_share_")]
    assert {r["name"] for r in summaries} == {
        "contamination_intensity_share_median",
        "contamination_intensity_share_min",
        "contamination_intensity_share_max",
    }
    assert all("not a measurement of the dataset" in r["source"] for r in summaries)


def test_the_psm_share_is_a_dataset_number_under_agings_definition():
    rows = prov.contamination_metric_rows(CONTAMINATION, "PXD1", run_names=RunNameMap(()))

    share = next(r for r in rows if r["name"] == "contamination_psm_share")
    assert share["scope"] == "dataset"
    assert share["definition_id"] == "aging:DEF-CONTAM-PSM"
    assert share["value"] == 0.039


def test_a_contaminated_file_that_does_not_resolve_gets_no_row_rather_than_a_dangling_one():
    rows = prov.contamination_metric_rows(CONTAMINATION, "PXD1", run_names=RunNameMap(("GM3_c",)))

    assert [r["scope_id"] for r in rows if r["scope"] == "run"] == ["PXD1:GM3_c"]


def test_a_provenance_with_no_contamination_block_emits_nothing():
    assert prov.contamination_metric_rows({"schema": "aging-provenance/3"}, "PXD1") == []


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
    # G42: a `not available` cell is an answer to a question that was asked, so it is kept, flagged,
    # and never carries a term. No row at all is what "never asked" looks like.
    reserved = [c for c in parsed.characteristics if c["name"] == "characteristics[disease]"]
    assert reserved and all(c["value_reserved"] and c["term"] is None for c in reserved)
    assert not any(c["value_reserved"] for c in parsed.characteristics if c["name"] == "characteristics[organism]")


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


def test_a_contaminant_keeps_its_own_species_and_is_not_claimed_for_the_dataset():
    """The dataset's organism is evidence about the searched proteome and nothing else.

    It used to be written to every row with the producer's own `organism_name` consulted only as a
    fallback -- which, for a manifest that names an organism, is never. All 339 contaminant entries
    in aging's catalog therefore read `NCBITaxon:9606`: porcine trypsin, bovine albumin (identified
    at q = 0 in all three of their datasets), horse cytochrome c and E. coli lacZ. "No non-human
    proteins were identified" was a flatly false answer the tools would have supported.
    """
    from datarepo.sources.identifications import protein_rows

    columns = {
        "accession": ["P11111", "P00761", "DECOY_P00722"],
        "gene_name": ["primary:GENE1", "", ""],
        "organism_name": ["Homo sapiens", "Sus scrofa", "Escherichia coli (strain K12)"],
        "decoy_contam_target": ["T", "C", "D"],
    }
    by_acc = {r["protein_accession"]: r for r in protein_rows([columns], "PXD999999",
                                                              organism="NCBITaxon:9606")}

    # From the searched proteome: the dataset's taxon is exactly what it is.
    assert by_acc["P11111"]["organism"] == "NCBITaxon:9606"
    assert by_acc["P11111"]["organism_name"] == "Homo sapiens"

    # From the contaminant panel: no taxon is asserted, and the species survives verbatim.
    assert by_acc["P00761"]["organism"] is None
    assert by_acc["P00761"]["organism_name"] == "Sus scrofa"
    assert by_acc["P00761"]["is_contaminant"] is True

    # A reversed sequence is no organism's protein at all.
    assert by_acc["DECOY_P00722"]["organism"] is None
    assert by_acc["DECOY_P00722"]["source_db"] == "decoy"


def test_no_species_name_is_ever_parsed_into_a_taxon_here():
    """Mapping `Bos taurus` -> NCBITaxon:9913 is a reference resource this project does not own."""
    from datarepo.sources.identifications import protein_rows

    rows_out = protein_rows(
        [{"accession": ["P02769"], "gene_name": ["primary:ALB"],
          "organism_name": ["Bos taurus"], "decoy_contam_target": ["C"]}],
        "PXD999999",
        organism="NCBITaxon:9606",
    )
    assert rows_out[0]["organism_name"] == "Bos taurus"
    assert rows_out[0]["organism"] is None  # not 9913, and emphatically not 9606


def test_the_group_count_can_be_retaken_from_the_rows_and_gives_the_same_answer():
    """After an exact-duplicate collapse the count has to describe the rows, not the file."""
    names = RunNameMap(("QE-002106_GM1_a", "QE-002107_GM1_b"))
    groups, _quants, count = quant.protein_group_rows(
        SEARCH_RESULTS / "AllQuantifiedProteinGroups.tsv", "PXD999999", run_names=names
    )
    assert quant.accepted_group_count(groups) == count

    accepted = next(g for g in groups if g["target_decoy"] != "decoy" and g["q_value"] <= 0.01)
    groups.remove(accepted)
    assert quant.accepted_group_count(groups) == count - 1


def test_intensity_and_spectral_count_are_told_apart_by_their_definition():
    names = RunNameMap(("QE-002106_GM1_a", "QE-002107_GM1_b"))
    _groups, quants, _count = quant.protein_group_rows(
        SEARCH_RESULTS / "AllQuantifiedProteinGroups.tsv", "PXD999999", run_names=names
    )
    definitions = {q["definition_id"] for q in quants}
    assert definitions == {"QuantProject:DEF-PROT-INT", "QuantProject:DEF-PROT-SPC"}


def test_a_zero_spectral_count_is_a_measurement_and_a_zero_intensity_is_not(tmp_path):
    """QuantProject:DEF-PROT-SPC: "0 is a real zero here". DEF-PROT-INT: blank or 0 is no value.

    Until 0.18.0 both columns went through the intensity rule, so every zero spectral count was
    stored as missing -- a real "no qualifying PSM" turned into "unknown".
    """
    header = [
        "Protein Accession", "Gene", "Number of Peptides", "Number of Unique Peptides",
        "Sequence Coverage Fraction", "SpectralCount_run_a", "Intensity_run_a",
        "SpectralCount_run_b", "Intensity_run_b", "Protein Decoy/Contaminant/Target", "Protein QValue",
    ]
    rows = [["P05141", "SLC25A5", "10", "4", "0.33", "0", "", "3", "0", "T", "0.001"]]
    path = tmp_path / "AllQuantifiedProteinGroups.tsv"
    path.write_text("\n".join("\t".join(r) for r in [header, *rows]) + "\n", encoding="utf-8")
    _groups, quants, _count = quant.protein_group_rows(
        path, "PXD1", run_names=RunNameMap(("run_a", "run_b"))
    )
    got = sorted((q["assay_id"], q["definition_id"], q["value"]) for q in quants)
    assert got == [
        ("PXD1:run_a:label_free", "QuantProject:DEF-PROT-SPC", 0.0),
        ("PXD1:run_b:label_free", "QuantProject:DEF-PROT-SPC", 3.0),
    ]


def test_the_three_quant_definitions_are_quantprojects_and_state_their_zero_rule():
    from datarepo import definitions as defs

    for d in (defs.PEPTIDE_INTENSITY, defs.PROTEIN_INTENSITY, defs.PROTEIN_SPECTRAL_COUNT):
        assert d.definition_id.startswith("QuantProject:DEF-")
        assert d.owner_project == "QuantProject"
        assert "f4bb910" in d.text, "the text says which revision of the owner's file it copies"
    assert "Read 0 as NA" in defs.PEPTIDE_INTENSITY.text
    assert "0 is a real zero here" in defs.PROTEIN_SPECTRAL_COUNT.text
    assert not [d for d in defs.ALL if d.definition_id.startswith("PROVISIONAL:")]


# --- per-run enrichment (G63) -----------------------------------------------------------------

def _runs(*names):
    return [{"file_name": f"{n}.raw"} for n in names]


def test_a_dataset_that_is_not_mixed_gives_every_run_its_declaration():
    runs = _runs("a", "b")
    mixed = runs_source.assign_enrichment(
        runs, "PXD1", declared=("affinity_purification", "chemical_probe"), mixed=False, run_enrichment=()
    )
    assert mixed is False
    assert [r["enrichment"] for r in runs] == [["affinity_purification", "chemical_probe"]] * 2
    assert {r["enrichment_source"] for r in runs} == {"dataset_declaration"}


def test_a_mixed_dataset_with_no_per_run_source_gets_null_never_the_dataset_value():
    runs = _runs("a", "b")
    mixed = runs_source.assign_enrichment(
        runs, "PXD1", declared=("chemical_probe",), mixed=True, run_enrichment=()
    )
    assert mixed is True
    assert [(r["enrichment"], r["enrichment_source"]) for r in runs] == [(None, None)] * 2


def test_a_per_run_map_fills_every_run_and_marks_the_dataset_mixed():
    # PXD058611's shape (aging 058): probe captures and whole-proteome runs in one deposit.
    runs = _runs("178", "179", "199")
    mixed = runs_source.assign_enrichment(
        runs, "PXD058611", declared=("chemical_probe",), mixed=True,
        run_enrichment=(("178", "chemical_probe"), ("179", "chemical_probe"), ("199", "none")),
    )
    assert mixed is True
    assert [r["enrichment"] for r in runs] == [["chemical_probe"], ["chemical_probe"], ["none"]]
    assert {r["enrichment_source"] for r in runs} == {"manifest_run_enrichment"}


def test_a_per_run_map_with_two_values_marks_the_dataset_mixed_even_unflagged():
    runs = _runs("a", "b")
    assert runs_source.assign_enrichment(
        runs, "PXD1", declared=("phospho",), mixed=False,
        run_enrichment=(("a", "phospho"), ("b", "none")),
    ) is True


@pytest.mark.parametrize(
    ("run_enrichment", "mixed", "message"),
    [
        ((("a", "chemical_probe"),), True, "covers 1 of 2 runs"),
        ((("a", "chemical_probe"), ("b", "none"), ("zz", "none")), True, "not runs of this dataset"),
        ((("a", "phospho"), ("b", "none")), True, "does not include"),
        ((("a", "pulldown"), ("b", "none")), True, "vocabulary"),
        ((("a", "chemical_probe"), ("b", "chemical_probe")), True, "contradict"),
    ],
    ids=["partial", "unknown-run", "undeclared-value", "not-in-vocabulary", "flag-contradicts-map"],
)
def test_a_per_run_map_that_does_not_add_up_is_refused(run_enrichment, mixed, message):
    from datarepo.errors import IngestError

    with pytest.raises(IngestError, match=message):
        runs_source.assign_enrichment(
            _runs("a", "b"), "PXD1", declared=("chemical_probe",), mixed=mixed,
            run_enrichment=run_enrichment,
        )


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
    assert sha == "89fb8c7a1140939de96ca740ab818deedd70063d00ac3789976908eec8d8ad6d"


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


def _sequences(**by_acc):
    from datarepo.sources.protein_db import ProteinSequences

    seqs = ProteinSequences()
    for acc, seq in by_acc.items():
        seqs.add(acc, seq)
    return seqs


_PEP = "PEPTCIDEK"   # Cys at peptide position 5


def _shared(accessions, spans, **over):
    columns = {
        "full_sequence": ["PEPTC[Common Fixed:Carbamidomethyl on C]IDEK"],
        "accession": [accessions],
        "start_and_end_residues_in_parent_sequence": [spans],
        "ambiguity_level": ["2D"],
        "q_value": [0.001],
        "decoy_contam_target": ["T"],
    }
    columns.update({k: [v] for k, v in over.items()})
    return columns


@needs_pymzlib
def test_a_site_is_placed_in_each_protein_by_its_own_sequence(registry):
    """Each protein gets the position the peptide actually has in it, from the sequence."""
    from datarepo.proforma import ProformaCache
    from datarepo.sources.identifications import ptm_site_rows

    seqs = _sequences(P11111="A" * 9 + _PEP + "G" * 5, P22222="A" * 154 + _PEP)
    rows = ptm_site_rows(
        _shared("P11111|P22222", "[10 to 18]|[155 to 163]"), "PXD1",
        proforma=ProformaCache(registry), sequences=seqs,
    )
    assert {r["protein_accession"]: r["position"] for r in rows} == {"P11111": 14, "P22222": 159}


@needs_pymzlib
def test_a_deduplicated_span_cell_does_not_misplace_the_site(registry):
    """aging 043: `P60709|P63261|Q6S8J3` beside `[216 to 238]|[916 to 938]`.

    Two proteins share a span, so the producer writes it once. Pairing by index gave the third
    protein the second's... nothing, and fell back to the first span -- gamma-actin ended up with
    POTE-E's numbering and POTE-E with actin's.
    """
    from datarepo.proforma import ProformaCache
    from datarepo.sources.identifications import ptm_site_rows

    seqs = _sequences(
        P1="A" * 9 + _PEP, P2="C" * 9 + _PEP, P3="G" * 99 + _PEP,
    )
    rows = ptm_site_rows(
        _shared("P1|P2|P3", "[10 to 18]|[100 to 108]"), "PXD1",
        proforma=ProformaCache(registry), sequences=seqs,
    )
    assert {r["protein_accession"]: r["position"] for r in rows} == {"P1": 14, "P2": 14, "P3": 104}


@needs_pymzlib
def test_matching_counts_are_not_evidence_of_alignment(registry):
    """The class, not the reproduction: equal span and accession counts can still be misaligned.

    P1 contains the peptide twice; P2 shares P1's first occurrence. The producer writes two spans
    for two accessions -- and index pairing would give P2 the position of P1's SECOND copy.
    """
    from datarepo.proforma import ProformaCache
    from datarepo.sources.identifications import ptm_site_rows

    seqs = _sequences(P1="A" * 9 + _PEP + "G" * 40 + _PEP, P2="C" * 9 + _PEP)
    rows = ptm_site_rows(
        _shared("P1|P2", "[10 to 18]|[59 to 67]"), "PXD1",
        proforma=ProformaCache(registry), sequences=seqs,
    )
    placed = sorted((r["protein_accession"], r["position"]) for r in rows)
    assert placed == [("P1", 14), ("P1", 63), ("P2", 14)]


@needs_pymzlib
def test_a_shared_peptide_with_no_sequence_is_counted_not_guessed(registry):
    from datarepo.proforma import ProformaCache
    from datarepo.sources.identifications import ptm_site_rows

    unplaced: dict[str, int] = {}
    rows = ptm_site_rows(
        _shared("P1|P2", "[10 to 18]|[155 to 163]"), "PXD1",
        proforma=ProformaCache(registry), sequences=_sequences(P1="A" * 9 + _PEP), unplaced=unplaced,
    )
    assert [(r["protein_accession"], r["position"]) for r in rows] == [("P1", 14)]
    assert unplaced == {"no_sequence": 1}


@needs_pymzlib
def test_a_single_accession_can_still_use_its_spans_without_a_sequence(registry):
    """One accession means every span is its own; no pairing is involved."""
    from datarepo.proforma import ProformaCache
    from datarepo.sources.identifications import ptm_site_rows

    rows = ptm_site_rows(
        _shared("P1", "[10 to 18]|[59 to 67]"), "PXD1", proforma=ProformaCache(registry)
    )
    assert sorted(r["position"] for r in rows) == [14, 63]


@needs_pymzlib
def test_the_initiator_methionine_is_read_from_each_proteins_own_sequence(registry):
    """`Previous Residue` is collapsed like the spans, so it comes from the sequence too.

    The same peptide at residue 2 after an M in one protein, and after a K in another, is a
    protein N-terminus in the first and a peptide N-terminus in the second.
    """
    from datarepo.proforma import ProformaCache
    from datarepo.sources.identifications import ptm_site_rows

    columns = _shared(
        "P1|P2", "[2 to 10]",
        full_sequence="[UniProt:N-acetylalanine on A]AEPTCIDEK",
        previous_residue="M",
    )
    seqs = _sequences(P1="MAEPTCIDEK", P2="KAEPTCIDEK")
    rows = ptm_site_rows(columns, "PXD1", proforma=ProformaCache(registry), sequences=seqs)
    kinds = {r["protein_accession"]: r["site_type"] for r in rows}
    assert kinds == {"P1": "protein_n_term", "P2": "peptide_n_term"}


@needs_pymzlib
def test_a_c_terminal_site_is_typed_by_whether_the_peptide_ends_the_protein(registry):
    """aging 045 section 2 (DATAREPO-33): keyed on the peptide's LAST residue at its own position,
    `protein_c_term` when that residue ends the protein, else `peptide_c_term`. Never length + 1.
    """
    from datarepo.proforma import ProformaCache
    from datarepo.sources.identifications import ptm_site_rows

    columns = _shared(
        "P1|P2", "[3 to 10]",
        full_sequence="KPVADYFL-[Common Artifact:Leucine methyl ester on L]",
    )
    seqs = _sequences(P1="MSKPVADYFL", P2="MSKPVADYFLGG")
    rows = ptm_site_rows(columns, "PXD1", proforma=ProformaCache(registry), sequences=seqs)
    got = {r["protein_accession"]: (r["residue"], r["position"], r["site_type"]) for r in rows}
    assert got == {"P1": ("L", 10, "protein_c_term"), "P2": ("L", 10, "peptide_c_term")}
    assert all(r["ptm_site_id"].endswith(f"@{r['site_type']}") for r in rows)


@needs_pymzlib
def test_a_c_terminal_site_with_no_sequence_is_counted_not_typed(registry):
    """Without the protein there is no telling a protein C-terminus from a cleavage one."""
    from datarepo.proforma import ProformaCache
    from datarepo.sources.identifications import ptm_site_rows

    unplaced: dict[str, int] = {}
    rows = ptm_site_rows(
        _shared("P1", "[3 to 10]", full_sequence="KPVADYFL-[Common Artifact:Leucine methyl ester on L]"),
        "PXD1", proforma=ProformaCache(registry), unplaced=unplaced,
    )
    assert rows == []
    assert unplaced == {"c_term_no_sequence": 1}


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


def test_a_collapsed_producer_column_is_broadcast_not_zipped():
    """MetaMorpheus writes ONE organism when every protein on the row shares it.

    `Accession = P60709|P63261` beside `Organism Name = Homo sapiens` is two proteins and one
    species, not a missing one. Zipping positionally gave the first accession its species and the
    rest an empty string -- 2,678 uniprot proteins, 4,523 decoys and 9 contaminants on aging's
    four-dataset catalog, in the release whose whole point was handling species correctly. It was
    nearly reported upstream as a MetaMorpheus defect before anyone read their file.
    """
    from datarepo.sources.identifications import protein_rows

    rows_out = protein_rows(
        [{
            "accession": ["P60709|P63261"],
            "gene_name": ["primary:ACTB|primary:ACTG1"],
            "organism_name": ["Homo sapiens"],          # collapsed: one for two
            "decoy_contam_target": ["T"],
        }],
        "PXD999999",
        organism="NCBITaxon:9606",
    )
    by_acc = {r["protein_accession"]: r for r in rows_out}
    assert by_acc["P60709"]["organism_name"] == "Homo sapiens"
    assert by_acc["P63261"]["organism_name"] == "Homo sapiens", "the second accession lost it"
    # The gene column was NOT collapsed here, so it still zips positionally.
    assert by_acc["P60709"]["gene"] == "ACTB"
    assert by_acc["P63261"]["gene"] == "ACTG1"


def test_an_unalignable_column_gives_null_rather_than_the_wrong_value():
    """Three accessions and two genes: the alignment is unknown and a guess would be a claim.

    A null reads as "not recorded". A gene symbol on the wrong protein reads as a fact, and is the
    kind of thing that gets quoted back as evidence.
    """
    from datarepo.sources.identifications import protein_rows

    rows_out = protein_rows(
        [{
            "accession": ["P11111|P22222|P33333"],
            "gene_name": ["primary:GENE1|primary:GENE2"],   # two for three -- unalignable
            "organism_name": ["Homo sapiens"],
            "decoy_contam_target": ["T"],
        }],
        "PXD999999",
        organism="NCBITaxon:9606",
    )
    by_acc = {r["protein_accession"]: r for r in rows_out}
    assert [by_acc[a]["gene"] for a in ("P11111", "P22222", "P33333")] == [None, None, None]
    # The organism WAS alignable (one value, broadcast), so it survives.
    assert all(by_acc[a]["organism_name"] == "Homo sapiens" for a in by_acc)


def test_the_collapsed_case_reaches_contaminants_too():
    """The seven contaminants that looked speciesless were this bug, not a producer gap."""
    from datarepo.sources.identifications import protein_rows

    rows_out = protein_rows(
        [{
            "accession": ["P02769|A2I7N2"],
            "gene_name": ["primary:ALB|primary:SERPINA3-6"],
            "organism_name": ["Bos taurus"],
            "decoy_contam_target": ["C"],
        }],
        "PXD999999",
        organism="NCBITaxon:9606",
    )
    by_acc = {r["protein_accession"]: r for r in rows_out}
    assert by_acc["A2I7N2"]["organism_name"] == "Bos taurus"
    assert by_acc["A2I7N2"]["organism"] is None  # still no taxon: contaminant panel


def test_a_mixed_dataset_gets_a_finding_that_says_how_its_runs_split():
    from datarepo.ingest import _enrichment_findings

    runs = [{"enrichment": ["chemical_probe"]}] * 21 + [{"enrichment": ["none"]}] * 15
    (finding,) = _enrichment_findings(runs, "PXD058611", True)
    assert finding["code"] == "mixed_enrichment" and finding["severity"] == "warning"
    assert "21 run(s) [chemical_probe]" in finding["message"]
    assert "15 run(s) [none]" in finding["message"]
    unknown = _enrichment_findings([{"enrichment": None}] * 4, "PXD1", True)
    assert "NULL on all 4 runs" in unknown[0]["message"]
    assert _enrichment_findings(runs, "PXD1", False) == []


def test_text_only_annotation_is_not_reported_as_absent():
    from datarepo.ingest import _uncoded_annotation

    rows = [
        {"name": "characteristics[organism part]", "value": "Urine"},
        {"name": "characteristics[disease]", "value": "not available"},
        {"name": "characteristics[age]", "value": "63"},
    ]
    assert _uncoded_annotation(rows) == "organism part: Urine"
    assert _uncoded_annotation(rows[1:]) == ""


# --- contaminant label per accession (G66) ----------------------------------------------------

def _proteins(status, accessions, contaminant_of, unresolved=None):
    from datarepo.sources import identifications

    columns = {
        "accession": [accessions], "decoy_contam_target": [status],
        "organism_name": ["Homo sapiens|Bos taurus"], "gene_name": [""], "name": [""],
    }
    rows = identifications.protein_rows(
        [columns], "PXD1", organism="NCBITaxon:9606", contaminant_of=contaminant_of, unresolved=unresolved
    )
    return {r["protein_accession"]: r for r in rows}


def test_a_target_sharing_a_psm_with_a_contaminant_stays_a_target():
    # Human albumin P02768 is in both the proteome and the contaminant panel; under MetaMorpheus's
    # default RemoveContaminant it is the target entry. Bovine P02769 is contaminant-only.
    decided = {"P02768": False, "P02769": True}
    rows = _proteins("T|C", "P02768|P02769", decided.get)
    assert rows["P02768"]["is_contaminant"] is False and rows["P02768"]["source_db"] == "uniprot"
    assert rows["P02768"]["organism"] == "NCBITaxon:9606"
    assert rows["P02769"]["is_contaminant"] is True and rows["P02769"]["source_db"] == "contaminants"


def test_one_letter_holds_for_every_accession_because_every_match_agreed():
    rows = _proteins("C", "P02768|P02769", {"P02768": False}.get)
    assert rows["P02768"]["is_contaminant"] is True and rows["P02769"]["is_contaminant"] is True


def test_an_accession_the_databases_cannot_place_keeps_the_row_rule_and_is_counted():
    from collections import Counter

    unresolved = Counter()
    rows = _proteins("T|C", "P02768|P02769", {"P02769": True}.get, unresolved)
    assert rows["P02768"]["is_contaminant"] is True
    assert unresolved == Counter({"P02768": 1})


def test_database_status_and_tc_ambiguity(tmp_path):
    from datarepo.sources import protein_db, search_params

    seqs = protein_db.ProteinSequences()
    for acc, contam in (("P02768", False), ("P02768", True), ("P02769", True), ("P60709", False)):
        seqs.add(acc, "SEQ")
        seqs.contaminant_from.setdefault(acc, set()).add(contam)
    assert [seqs.database_status(a) for a in ("P02768", "P02769", "P60709", "Q00000")] == [
        "both", "contaminant", "target", None,
    ]
    assert protein_db.is_contaminant_database(Path("F:/db/MetaMorpheusContaminants.xml"))
    assert protein_db.is_contaminant_database(Path("crap.fasta"))
    assert not protein_db.is_contaminant_database(Path("uniprotkb_proteome_UP000005640.xml"))

    task = tmp_path / "3_SearchTask.toml"
    task.write_text('[SearchParameters]\nTCAmbiguity = "RemoveTarget"\n', encoding="utf-8")
    assert search_params.tc_ambiguity([task]) == "RemoveTarget"
    task.write_text("[SearchParameters]\n", encoding="utf-8")
    assert search_params.tc_ambiguity([task]) == "RemoveContaminant"
    assert search_params.tc_ambiguity([]) is None


def test_an_upstream_provenance_file_changed_after_the_search_is_left_out(tmp_path):
    # aging's db/provenance.json is one shared file every database preparation overwrites; a search
    # that recorded it must not later be given another preparation's record (0.19.0).
    import hashlib

    from datarepo.ingest import _lineage, _lineage_findings

    (tmp_path / "db").mkdir()
    (tmp_path / "qc").mkdir()
    db, qc = tmp_path / "db" / "provenance.json", tmp_path / "qc" / "provenance.json"
    db.write_text('{"stage": "db_prepare", "prepared": "mouse"}', encoding="utf-8")
    qc.write_text('{"stage": "qc_spectra"}', encoding="utf-8")
    recorded_db = hashlib.sha256(db.read_bytes()).hexdigest()
    search = tmp_path / "search.json"
    doc = {"upstream": [
        {"stage": "db_prepare", "path": "db/provenance.json", "sha256": recorded_db},
        {"stage": "qc_spectra", "path": "qc/provenance.json",
         "sha256": hashlib.sha256(qc.read_bytes()).hexdigest()},
    ]}
    paths, mismatches = _lineage(tmp_path, search, doc)
    assert db in paths and qc in paths and mismatches == []

    db.write_text('{"stage": "db_prepare", "prepared": "human isoforms"}', encoding="utf-8")
    paths, mismatches = _lineage(tmp_path, search, doc)
    assert db not in paths and qc in paths
    assert [m["stage"] for m in mismatches] == ["db_prepare"]
    (finding,) = _lineage_findings(mismatches, "PXD1")
    assert finding["code"] == "upstream_provenance_changed" and recorded_db in finding["message"]


def test_a_file_the_search_excluded_gets_no_run_and_no_run_metrics():
    fetch = runs_source.load_fetch_manifest(RUN / "02_fetch/fetch_manifest.json")
    qc = runs_source.load_qc_report(RUN / "02b_qc/qc_report.json")
    excluded, reason = runs_source.excluded_files(
        {"excluded_files": {"files": ["/work/QE-002107_GM1_b.raw"], "reason": "D52"}}
    )
    assert excluded == {"QE-002107_GM1_b.raw"} and reason == "D52"
    rows, metrics = runs_source.build("PXD999999", fetch=fetch, qc=qc, run_facts={}, excluded=excluded)
    assert [r["file_name"] for r in rows] == ["QE-002106_GM1_a.raw"]
    assert {m["scope_id"] for m in metrics} == {"PXD999999:QE-002106_GM1_a"}


def test_no_excluded_files_block_excludes_nothing():
    assert runs_source.excluded_files({}) == (frozenset(), None)
    assert runs_source.excluded_files({"excluded_files": None}) == (frozenset(), None)


# --- occupancy (D29) ---------------------------------------------------------------------------

def _seqs(**by_accession):
    from datarepo.sources.protein_db import ProteinSequences

    seqs = ProteinSequences()
    for acc, seq in by_accession.items():
        seqs.add(acc, seq)
    return seqs


def _entry(p, mod, index=0):
    return {"position": p, "modification": mod, "entity_index": index, "is_n_terminus": p == 0}


def test_occupancy_segments_are_realigned_when_a_member_has_no_site():
    """DEF-OCC-ACCESSION: segments skip members with no entry, so segment 0 here is B, not A."""
    from datarepo.sources import occupancy

    seqs = _seqs(A="MKKKKKK", B="MSSSSSS", C="MTTTTTT")
    segments = {0: [_entry(3, "Phosphorylation on S")], 1: [_entry(2, "Phosphorylation on T")]}
    assert occupancy._assign(segments, ["A", "B", "C"], seqs) == ["B", "C"]


def test_occupancy_segments_are_never_guessed_when_two_members_fit():
    from datarepo.sources import occupancy

    seqs = _seqs(A="MSSS", B="MSSS")
    assert occupancy._assign({0: [_entry(2, "Phosphorylation on S")]}, ["A", "B"], seqs) is None


def test_occupancy_positions_map_onto_ptm_sites_coordinates():
    from datarepo.sources import occupancy

    seq = "MASKR"
    key = lambda e: occupancy._site_key("D", "P1", seq, e)  # noqa: E731
    assert key(_entry(3, "Phosphorylation on S")) == "D:P1:S3:Phosphorylation on S"
    assert key(_entry(0, "Acetylation on X")) == "D:P1:M1:Acetylation on X@protein_n_term"
    assert key(_entry(6, "Amidation on X")) == "D:P1:R5:Amidation on X@protein_c_term"


def test_ptm_pairs_take_site_grain_and_per_species_pooling_with_n_kept_as_runs():
    """D31: `feature_type`, `meta:<species>`, `datasets` / `n_datasets`, and `n` never a dataset count."""
    from datarepo.bundle import table_from_rows
    from datarepo._tables import TABLES

    pooled = {
        "result_type": "P", "scope": "meta:human", "feature_type": "ptm_site_canonical",
        "feature_key_a": "P62805:K13:UNIMOD:1", "protein_accessions_a": ["P62805"],
        "feature_key_b": "P62805:K17:UNIMOD:1", "protein_accessions_b": ["P62805"],
        "same_protein": True, "class_pair": "biological x biological", "statistic": "recurrence",
        "value": None, "n": None, "datasets": ["PXD1", "PXD2"], "n_datasets": 2,
        "n_datasets_agreeing": 2, "definition_id": "ptmQtl:DEF-PTM-PAIR v1",
    }
    table = table_from_rows("ptm_pairs", [pooled])
    assert table.num_rows == 1
    assert TABLES["ptm_pairs"].field("n").nullable  # NULL on a pooled row whose run total is unknown
    assert TABLES["ptm_pairs"].field("feature_type").nullable is False


def test_pep_regime_follows_metamorpheus_and_refuses_to_guess(tmp_path):
    """G70: MetaMorpheus picks the PEP feature set by search type (`FdrAnalysisEngine.cs:410-416`)."""
    from datarepo.sources import search_params

    def task(name, text):
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return path

    gptmd = task("2_GptmdTask.toml", 'TaskType = "Gptmd"\n')
    search = task("3_SearchTask.toml", 'TaskType = "Search"\n[CommonParameters.DigestionParams]\nProtease = "trypsin"\n')
    assert search_params.pep_regime([gptmd, search]) == "standard"
    top_down = task("td.toml", 'TaskType = "Search"\n[CommonParameters.DigestionParams]\nProtease = "top-down"\n')
    assert search_params.pep_regime([top_down]) == "top-down"
    assert search_params.pep_regime([task("xl.toml", 'TaskType = "XLSearch"\n')]) == "crosslink"
    # Glyco's mapping is not established, and two searches that disagree have no one regime.
    assert search_params.pep_regime([task("g.toml", 'TaskType = "GlycoSearch"\n')]) is None
    assert search_params.pep_regime([search, top_down]) is None
    assert search_params.pep_regime([gptmd]) is None


def test_an_sdrf_naming_the_calibrated_file_still_meets_the_deposited_run(tmp_path):
    """aging 069, DATAREPO-54: an SDRF MetaMorpheus writes names `X-calib.mzML`, the file it searched.
    Keyed on that stem, the run `X` got no sample, instrument or fraction and nothing said so."""
    source = RUN / "02_fetch/metadata/PXD999999.sdrf.tsv"
    deposited = sdrf_source.parse(source, "PXD999999")
    text = source.read_text(encoding="utf-8")
    for run in deposited.sample_of_run:
        text = text.replace(f"{run}.raw", f"{run}-calib.mzML")
    assert "-calib.mzML" in text, "fixture no longer names .raw files; rewrite this test"
    calibrated = tmp_path / "calibrated.sdrf.tsv"
    calibrated.write_text(text, encoding="utf-8")
    parsed = sdrf_source.parse(calibrated, "PXD999999")
    assert parsed.sample_of_run == deposited.sample_of_run
    assert parsed.run_facts == deposited.run_facts
    assert [a["assay_id"] for a in parsed.assays] == [a["assay_id"] for a in deposited.assays]


def test_a_dropped_occupancy_duplicate_says_whether_it_matched_the_stored_row():
    """aging 069, DATAREPO-53: dropping a duplicate is safe only when it says the same thing."""
    from datarepo.sources import occupancy

    out = occupancy.OccupancyResult()
    row = {"ptm_site_id": "D:P1:S3:Phosphorylation on S", "assay_id": "D:r1:label_free", "protein_group_id": "D:P1"}
    occupancy._duplicate(out, row, "D:P1", "count", same=True)
    occupancy._duplicate(out, row, "D:P1;P2", "intensity", same=False)
    assert out.not_stored == {
        "duplicate entry for one site and run (identical values; same protein group)": 1,
        "duplicate entry for one site and run (DIFFERENT values, first in file kept; another protein group)": 1,
    }
    assert out.differing_duplicates == [{
        "ptm_site_id": row["ptm_site_id"], "assay_id": row["assay_id"], "basis": "intensity",
        "kept_group": "D:P1", "dropped_group": "D:P1;P2",
    }]


def test_a_drafted_sdrf_says_where_each_value_came_from(tmp_path):
    """G62 / sdrf D31: a column's own `comment[<name> source]` overrides the row default; neither
    means NULL, never `deposited`. DR10 and DR11 columns are read when present."""
    header = [
        "source name", "characteristics[organism]", "characteristics[organism part]",
        "characteristics[biological replicate]", "characteristics[age]", "comment[fraction identifier]",
        "comment[technical replicate]", "comment[data file]", "comment[biological replicate source]",
        "comment[characteristics source]", "comment[age source]", "comment[age source reference]",
        "comment[fraction identifier source]",
    ]
    row = [
        "S1", "NT=homo sapiens;AC=NCBITaxon:9606", "NT=Cell culture;AC=BTO:0000214", "1", "24 months",
        "1", "1", "R1.raw", "default", "pride project record", "publication", "PMC123#Methods", "inferred",
    ]
    path = tmp_path / "drafted.sdrf.tsv"
    path.write_text("\t".join(header) + "\n" + "\t".join(row) + "\n", encoding="utf-8")
    parsed = sdrf_source.parse(path, "PXD1")
    by = {c["name"]: c for c in parsed.characteristics}
    assert by["characteristics[organism]"]["source"] == "pride project record"
    assert by["characteristics[biological replicate]"]["source"] == "default"
    assert (by["characteristics[age]"]["source"], by["characteristics[age]"]["source_reference"]) == (
        "publication", "PMC123#Methods")
    assert parsed.run_facts["R1"]["fraction_source"] == "inferred"
    assert parsed.run_facts["R1"]["technical_replicate_source"] is None

    deposited = sdrf_source.parse(RUN / "02_fetch/metadata/PXD999999.sdrf.tsv", "PXD999999")
    assert {c["source"] for c in deposited.characteristics} == {None}
