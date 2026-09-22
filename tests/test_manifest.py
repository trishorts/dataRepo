"""The manifest is the gate: what may be ingested, and from where."""

from __future__ import annotations

import dataclasses

import pytest

from datarepo.errors import DatasetExcluded, ManifestError
from datarepo.manifest import (
    CONTENT_FIELDS,
    NON_CONTENT_FIELDS,
    DatasetEntry,
    load_manifest,
)

from conftest import MANIFEST


def test_relative_roots_resolve_against_the_manifest(manifest):
    assert manifest.work_root.is_absolute()
    assert manifest.work_root.name == "work_root"
    assert (manifest.work_root / "run_test/PXD999999").is_dir()


def test_axes_are_read_as_columns(manifest):
    entry = manifest.dataset("PXD999999")
    assert entry.organism == "NCBITaxon:9606"
    assert entry.acquisition == "DDA"
    assert entry.quant_method == "label-free"
    assert entry.enrichment == ("none",)
    assert entry.flags == ("low_id_rate", "no_design_file")


def test_stage_folders_come_from_the_manifest_not_from_guessing(manifest):
    entry = manifest.dataset("PXD999999")
    assert manifest.stage_dir(entry, "search").name == "04_search"
    assert manifest.search_results_dir(entry).name == "Task3SearchTask"
    assert manifest.stage_dir(entry, "nonexistent") is None


def test_an_excluded_dataset_is_refused_with_the_producers_reason(manifest):
    with pytest.raises(DatasetExcluded) as exc:
        manifest.dataset("PXD000000")
    assert "PXD000000" in str(exc.value)
    assert "judged this run unfit" in str(exc.value)


def test_a_held_dataset_is_refused_too(manifest):
    with pytest.raises(DatasetExcluded):
        manifest.dataset("PXD111111")


def test_only_included_datasets_are_offered_for_ingest(manifest):
    assert [e.accession for e in manifest.ingestable()] == ["PXD999999"]


def test_an_unknown_accession_lists_what_is_there(manifest):
    with pytest.raises(ManifestError) as exc:
        manifest.dataset("PXD777777")
    assert "PXD999999" in str(exc.value)


def test_a_missing_manifest_says_so(tmp_path):
    with pytest.raises(ManifestError, match="no ingest manifest"):
        load_manifest(tmp_path / "nope.yaml")


def test_an_unknown_manifest_version_is_refused(tmp_path):
    path = tmp_path / "manifest.yaml"
    path.write_text("manifest_version: 99\nwork_root: .\nstore: .\ndatasets: []\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="manifest_version"):
        load_manifest(path)


def test_an_included_dataset_without_a_run_is_refused(tmp_path):
    path = tmp_path / "manifest.yaml"
    path.write_text(
        "manifest_version: 1\nwork_root: .\nstore: .\ndatasets:\n  - accession: PXD1\n    status: include\n",
        encoding="utf-8",
    )
    with pytest.raises(ManifestError, match="no 'run'"):
        load_manifest(path)


def test_a_utf8_bom_does_not_break_the_manifest(tmp_path):
    # PowerShell's `Set-Content -Encoding utf8` writes a BOM; a manifest written that way must
    # still load rather than failing on a key that reads as "﻿manifest_version".
    path = tmp_path / "manifest.yaml"
    path.write_bytes(b"\xef\xbb\xbf" + MANIFEST.read_bytes())
    assert load_manifest(path).manifest_version == 1


def test_every_manifest_field_is_classified_for_the_content_hash():
    # The bundle id has to mean "these are the same measurements" (aging 019 section 1). That holds
    # only while every DatasetEntry field is deliberately either in the hash or out of it, so a new
    # field must fail here until somebody decides which it is. The rule: anything that reaches a
    # written row, or chooses which file is read, is an input to the content hash.
    declared = {f.name for f in dataclasses.fields(DatasetEntry)}
    classified = set(CONTENT_FIELDS) | set(NON_CONTENT_FIELDS)
    assert declared == classified, (
        f"unclassified manifest field(s): {sorted(declared - classified)}; "
        f"classified but not a field: {sorted(classified - declared)}"
    )
    assert not set(CONTENT_FIELDS) & set(NON_CONTENT_FIELDS)
    assert all(NON_CONTENT_FIELDS.values()), "every excluded field needs its reason in the code"


def test_the_content_declaration_carries_the_axes_and_not_the_prose(manifest):
    entry = manifest.dataset("PXD999999")
    declaration = entry.content_declaration()
    assert set(declaration) == set(CONTENT_FIELDS)
    assert declaration["acquisition"] == "DDA"
    assert declaration["organism"] == "NCBITaxon:9606"
    for prose in ("reason", "notes", "flags", "status"):
        assert prose not in declaration


ENTRY = """manifest_version: 1
work_root: .
store: .
datasets:
  - accession: PXD999999
    status: include
    run: run_test/PXD999999
    title: {title}
    organism: NCBITaxon:9606
    reason: {reason}
    notes: {notes}
    flags: [{flag}]
    permitted_responses: [{permitted}]
"""


def _declaration(tmp_path, name, **fields):
    path = tmp_path / name
    path.write_text(
        ENTRY.format(**{"title": "A title", "reason": "because", "notes": "a note",
                        "flag": "low_id_rate", "permitted": "abundance", **fields}),
        encoding="utf-8",
    )
    return load_manifest(path).dataset("PXD999999").content_declaration()


def test_rewording_the_producers_prose_does_not_move_the_bundle_id(tmp_path):
    # aging edited a `reason` between their ingest and ours and got a different bundle id from
    # byte-identical search output. Identical measurements must land on identical ids, so none of
    # the producer's prose may reach the hash.
    before = _declaration(tmp_path, "before.yaml")
    after = _declaration(tmp_path, "after.yaml", reason="a different wording", notes="rewritten",
                         flag="no_design_file")
    assert before == after


def test_retitling_a_dataset_does_move_the_bundle_id(tmp_path):
    # The converse, and the reason the declaration is hashed at all: the title reaches a row.
    before = _declaration(tmp_path, "before.yaml")
    after = _declaration(tmp_path, "after.yaml", title="Another title")
    assert before != after


def test_changing_what_a_dataset_may_be_used_for_DOES_move_the_bundle_id(tmp_path):
    # The mirror image of the `reason` case, and the reason CONTENT_FIELDS has to be decided per
    # field rather than by a rule of thumb (aging 024 section 7). Two bundles over the same rows,
    # one of which may be used for site localization and one of which may not, are not the same
    # object: the rows MEAN different things. A deny-list would also fail open here, so the
    # declaration is positive and an unlisted response is excluded.
    before = _declaration(tmp_path, "narrow.yaml", permitted="abundance")
    after = _declaration(tmp_path, "wide.yaml", permitted="abundance, occupancy")
    assert before != after
    assert before["permitted_responses"] == ("abundance",)
    assert after["permitted_responses"] == ("abundance", "occupancy")
