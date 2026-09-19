"""The manifest is the gate: what may be ingested, and from where."""

from __future__ import annotations

import pytest

from datarepo.errors import DatasetExcluded, ManifestError
from datarepo.manifest import load_manifest

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
