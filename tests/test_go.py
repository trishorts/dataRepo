"""go's two output files, read and checked (G53). Fixtures: tests/data/go, go's own pre-release files."""

from __future__ import annotations

from pathlib import Path

import pytest

from datarepo.errors import IngestError
from datarepo.sources import go

GO = Path(__file__).parent / "data" / "go"
ANNOTATION = GO / "fixture1347_go_annotation.tsv"
CATEGORIES = GO / "fixture1347_go_category_smoke.tsv"


def _copy(tmp_path, source, edit):
    text = source.read_text(encoding="utf-8")
    new = edit(text)
    assert new != text, "the edit did not apply"
    path = tmp_path / source.name
    path.write_bytes(new.encode("utf-8"))
    return path


def test_a_file_from_an_unreleased_mzlib_is_refused_and_the_refusal_names_the_commit():
    with pytest.raises(IngestError, match="282b480ddc96b632c5d52c510a638928aab4fca6"):
        go.read_annotation(ANNOTATION)
    with pytest.raises(IngestError, match="unreleased"):
        go.read_categories(CATEGORIES)


def test_the_fixture_reads_and_every_header_counter_recounts_from_the_rows():
    annotation = go.read_annotation(ANNOTATION, allow_prerelease=True)
    assert len({r["protein_group"] for r in annotation.rows}) == 5
    assert annotation.header["status_contaminant"] == "1"
    # Nothing is dropped without a count: the contaminant group has no term, and the other two
    # aspects have no table here.
    assert annotation.not_stored["no term (contaminant)"] == 1
    assert set(annotation.not_stored) == {
        "no term (contaminant)", "aspect molecular_function", "aspect biological_process",
    }


def test_localizations_are_cellular_component_only_and_expand_over_accession_used():
    annotation = go.read_annotation(ANNOTATION, allow_prerelease=True)
    rows = go.localization_rows(annotation)
    cc_terms = {r["go_id"] for r in annotation.rows if r["aspect"] == "cellular_component"}
    assert {r["compartment"] for r in rows} == cc_terms
    carried = {(a, r["go_id"]) for r in annotation.rows if r["aspect"] == "cellular_component"
               for a in r["accession_used"].split(";") if a}
    assert {(r["protein_accession"], r["compartment"]) for r in rows} == carried
    assert all(r["go_release"] == "releases/2026-07-26" for r in rows)
    assert len({r["source_id"] for r in rows}) == 1


def test_gos_per_row_evidence_is_stored_as_go_wrote_it():
    # Schema 0.0.10 (D28): the columns go's D22/D29 rows carry, taken with gene_resolutions.
    from datarepo.bundle import table_from_rows

    annotation = go.read_annotation(ANNOTATION, allow_prerelease=True)
    rows = go.localization_rows(annotation)
    source = {(a, r["go_id"]): r for r in annotation.rows if r["aspect"] == "cellular_component"
              for a in r["accession_used"].split(";") if a}
    for row in rows:
        want = source[(row["protein_accession"], row["compartment"])]
        assert row["protein_group"] == want["protein_group"]
        assert row["q_value"] == float(want["q_value"])
        assert (row["n_members"], row["n_with"]) == (int(want["n_members"]), int(want["n_with"]))
        assert row["propagated"] == (want["propagated"] == "true")
        assert row["inherited"] == (want["inherited"] == "true")
    assert any(r["propagated"] for r in rows) and any(not r["propagated"] for r in rows)
    assert table_from_rows("protein_localizations", rows).num_rows == len(rows)


def test_a_flag_that_is_not_true_or_false_is_refused():
    assert go._flag("") is None
    with pytest.raises(IngestError, match="expected `true` or `false`"):
        go._flag("yes")


def test_categories_pair_with_their_annotation_file_and_carry_the_map():
    annotation = go.read_annotation(ANNOTATION, allow_prerelease=True)
    categories = go.read_categories(CATEGORIES, allow_prerelease=True)
    go.check_coverage(annotation, categories)
    rows = go.category_rows(categories, annotation)
    assert {(r["category_map_name"], r["organelle_map_version"]) for r in rows} == {("smoke", "1")}


def test_a_header_counter_the_rows_do_not_support_is_refused(tmp_path):
    path = _copy(tmp_path, ANNOTATION, lambda t: t.replace("#!status_annotated 4", "#!status_annotated 5"))
    with pytest.raises(IngestError, match="status_annotated header 5 rows 4"):
        go.read_annotation(path, allow_prerelease=True)


def test_a_category_term_the_annotation_file_lacks_is_refused(tmp_path):
    path = _copy(tmp_path, CATEGORIES, lambda t: t + "GO:9999999\tnucleus\t\n")
    categories = go.read_categories(path, allow_prerelease=True)
    annotation = go.read_annotation(ANNOTATION, allow_prerelease=True)
    with pytest.raises(IngestError, match="GO:9999999"):
        go.check_coverage(annotation, categories)


def test_a_category_file_from_another_ontology_release_is_refused(tmp_path):
    path = _copy(tmp_path, CATEGORIES, lambda t: t.replace("#!go_release releases/2026-07-26", "#!go_release releases/2026-01-01"))
    categories = go.read_categories(path, allow_prerelease=True)
    annotation = go.read_annotation(ANNOTATION, allow_prerelease=True)
    with pytest.raises(IngestError, match="not a pair"):
        go.check_coverage(annotation, categories)


def test_an_accession_in_two_groups_is_refused(tmp_path):
    text = ANNOTATION.read_text(encoding="utf-8")
    header = [l for l in text.split("\n") if l.startswith("#!")]
    table = [l for l in text.split("\n") if l and not l.startswith("#!")]
    groups = [row.split("\t")[0] for row in table[1:]]
    single = next(g for g in groups if "|" not in g)
    other = next(g for g in groups if g != single and "|" not in g)
    # Put `single`'s accession into a second group by renaming one of `other`'s rows' group.
    first_other = next(i for i, row in enumerate(table) if row.split("\t")[0] == other)
    cells = table[first_other].split("\t")
    cells[0] = f"{other}|{single}"
    table[first_other] = "\t".join(cells)
    path = tmp_path / ANNOTATION.name
    path.write_bytes(("\n".join(header + table) + "\n").encode("utf-8"))
    with pytest.raises(IngestError, match="sit in more than one group"):
        go.read_annotation(path, allow_prerelease=True)


def test_a_term_on_a_group_not_marked_annotated_is_refused(tmp_path):
    def edit(text):
        lines = text.split("\n")
        for i, line in enumerate(lines):
            cells = line.split("\t")
            if len(cells) == 15 and cells[2].startswith("GO:"):
                cells[10] = "no_entry"
                lines[i] = "\t".join(cells)
                break
        return "\n".join(lines)

    path = _copy(tmp_path, ANNOTATION, edit)
    with pytest.raises(IngestError, match="a term means annotated"):
        go.read_annotation(path, allow_prerelease=True)
