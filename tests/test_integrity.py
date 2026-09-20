"""The bundle's self-checks: duplicate identifiers, the lossless escape, and what it refuses.

The escape exists because MetaMorpheus wrote one protein group three times in PXD027318, identical
in every column (aging thread 015). These tests pin both halves of the answer: the identical case
collapses, and the differing case still stops the write.
"""

from __future__ import annotations

import pytest

from datarepo.integrity import check, collapse_exact_duplicates


def group(accessions, **overrides):
    row = {
        "protein_group_id": "PXD1:" + ";".join(accessions),
        "dataset_id": "PXD1",
        "protein_accessions": list(accessions),
        "genes": ["G"],
        "target_decoy": "target",
        "q_value": 0.1157,
        "sequence_coverage": 0.1,
        "unique_peptides": 2,
        "shared_peptides": 1,
    }
    row.update(overrides)
    return row


def test_rows_identical_in_every_column_collapse_to_one():
    rows = [group(["A6NJZ7", "A6NNM3"]) for _ in range(3)]
    tables = {"protein_groups": rows}

    collapsed = collapse_exact_duplicates(tables)

    assert len(rows) == 1
    assert [c.written for c in collapsed] == [3]
    assert collapsed[0].dropped == 2
    assert collapsed[0].identifier == "PXD1:A6NJZ7;A6NNM3"
    assert [p for p in check(tables) if "duplicate identifier" in p] == []


def test_rows_that_share_an_identifier_and_differ_are_left_for_the_check_to_refuse():
    rows = [group(["A6NJZ7"]), group(["A6NJZ7"], q_value=0.5)]
    tables = {"protein_groups": rows}

    assert collapse_exact_duplicates(tables) == []
    assert len(rows) == 2
    problems = [p for p in check(tables) if "duplicate identifier" in p]
    assert len(problems) == 1
    assert "PXD1:A6NJZ7" in problems[0]


def test_a_list_valued_column_compares_by_value_not_by_identity():
    rows = [group(["A", "B"]), group(["A", "B"])]

    collapse_exact_duplicates({"protein_groups": rows})

    assert len(rows) == 1


def test_a_list_valued_column_that_differs_blocks_the_collapse():
    a = group(["A", "B"])
    b = group(["A", "B"])
    b["genes"] = ["G", "H"]

    assert collapse_exact_duplicates({"protein_groups": [a, b]}) == []


def test_the_first_row_is_the_one_kept_so_order_is_stable():
    first, second, third = group(["A"]), group(["B"]), group(["A"])
    rows = [first, second, third]

    collapse_exact_duplicates({"protein_groups": rows})

    assert rows == [first, second]


def test_duplicate_psms_are_never_collapsed_because_a_psm_row_is_an_observation():
    psm = {"psm_id": "PXD1:run:1", "run_id": "run", "dataset_id": "PXD1"}
    rows = [dict(psm), dict(psm)]

    assert collapse_exact_duplicates({"psms": rows}) == []
    assert len(rows) == 2


def test_a_duplicated_group_row_also_duplicates_its_quantities():
    """The reason the collapse covers quant_values: it has no identifier of its own.

    Three identical protein-group rows melt into three identical quantities per run, and a caller
    summing intensities would have read the group as three times as abundant.
    """
    quant = {
        "assay_id": "PXD1:run:label_free",
        "feature_type": "protein_group",
        "feature_id": "PXD1:A6NJZ7",
        "value": 1000.0,
        "detection_type": None,
        "pip_q_value": None,
        "mbr_kept": None,
        "definition_id": "PROVISIONAL:PROTEIN-INTENSITY",
    }
    rows = [dict(quant) for _ in range(3)]

    collapsed = collapse_exact_duplicates({"quant_values": rows})

    assert len(rows) == 1
    assert collapsed[0].written == 3


def test_two_quantities_for_one_feature_under_different_definitions_are_not_duplicates():
    base = {
        "assay_id": "PXD1:run:label_free",
        "feature_type": "protein_group",
        "feature_id": "PXD1:A6NJZ7",
        "value": 1000.0,
        "detection_type": None,
        "pip_q_value": None,
        "mbr_kept": None,
        "definition_id": "PROVISIONAL:PROTEIN-INTENSITY",
    }
    other = dict(base, definition_id="PROVISIONAL:PROTEIN-SPECTRAL-COUNT", value=4.0)
    rows = [base, other]

    assert collapse_exact_duplicates({"quant_values": rows}) == []
    assert [p for p in check({"quant_values": rows}) if "duplicate identifier" in p] == []


def test_the_same_quantity_written_twice_with_different_values_is_refused():
    base = {
        "assay_id": "PXD1:run:label_free",
        "feature_type": "protein_group",
        "feature_id": "PXD1:A6NJZ7",
        "value": 1000.0,
        "detection_type": None,
        "pip_q_value": None,
        "mbr_kept": None,
        "definition_id": "PROVISIONAL:PROTEIN-INTENSITY",
    }
    rows = [base, dict(base, value=2000.0)]

    assert collapse_exact_duplicates({"quant_values": rows}) == []
    problems = [p for p in check({"quant_values": rows}) if "duplicate identifier" in p]
    assert len(problems) == 1


@pytest.mark.parametrize("table", ["protein_groups", "peptidoforms", "proteins", "ptm_sites"])
def test_an_empty_or_absent_table_is_not_a_problem(table):
    assert collapse_exact_duplicates({table: []}) == []
    assert collapse_exact_duplicates({}) == []
