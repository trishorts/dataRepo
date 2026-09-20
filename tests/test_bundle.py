"""Writing a bundle: typing, the missing-is-NA rule, content addressing and immutability."""

from __future__ import annotations

import json

import pyarrow.parquet as pq
import pytest

from datarepo.bundle import BundleWriter, table_from_rows
from datarepo.errors import IngestError


def test_rows_are_written_in_the_schemas_column_order():
    table = table_from_rows("definitions", [
        {"definition_id": "X", "version": "v1", "owner_project": "test", "text": "t"},
    ])
    assert table.column_names[:3] == ["definition_id", "version", "owner_project"]
    assert table.num_rows == 1


def test_an_empty_string_becomes_null_not_an_empty_value():
    table = table_from_rows("definitions", [
        {"definition_id": "X", "version": "v1", "owner_project": "test", "text": "t", "url": "  "},
    ])
    assert table.column("url").to_pylist() == [None]


def test_a_nan_is_stored_as_null_because_absence_is_not_a_number():
    table = table_from_rows("metrics", [
        {"scope": "dataset", "scope_id": "PXD1", "name": "m", "value": float("nan"),
         "definition_id": "D", "source": "s"},
    ])
    assert table.column("value").to_pylist() == [None]


def test_a_zero_is_kept_because_zero_is_a_real_measurement():
    table = table_from_rows("metrics", [
        {"scope": "dataset", "scope_id": "PXD1", "name": "m", "value": 0.0,
         "definition_id": "D", "source": "s"},
    ])
    assert table.column("value").to_pylist() == [0.0]


def test_a_missing_required_column_fails_the_write():
    with pytest.raises(IngestError, match="required 'version'"):
        table_from_rows("definitions", [{"definition_id": "X", "owner_project": "t", "text": "t"}])


def test_an_unknown_column_fails_rather_than_being_dropped():
    with pytest.raises(IngestError, match="unknown columns"):
        table_from_rows("definitions", [
            {"definition_id": "X", "version": "v", "owner_project": "t", "text": "t", "typo": 1},
        ])


def test_an_unknown_table_name_fails_loudly(tmp_path):
    writer = BundleWriter(store=tmp_path, dataset_id="PXD1")
    with pytest.raises(IngestError, match="no table named"):
        writer.add("psmz", [])


def _minimal(tmp_path, source_text="a"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "provenance.json"
    source.write_text(source_text, encoding="utf-8")
    writer = BundleWriter(store=tmp_path / "store", dataset_id="PXD000001")
    writer.add_source(source, "provenance:test", copy_as="provenance_test.json")
    writer.add("datasets", [{
        "dataset_id": "PXD000001", "organisms": ["NCBITaxon:9606"], "acquisition": "DDA",
        "quant_method": "label_free", "labelling": "none", "enrichment": ["none"],
        "axis_source": "provenance", "search_engine": "MetaMorpheus", "search_engine_version": "1.1.11",
    }])
    return writer


def test_the_bundle_directory_is_a_content_hash(tmp_path):
    first = _minimal(tmp_path / "a").bundle_id
    same = _minimal(tmp_path / "b").bundle_id
    different = _minimal(tmp_path / "c", source_text="changed").bundle_id
    assert first == same
    assert first != different


def test_writing_produces_parquet_the_sources_and_a_manifest(tmp_path):
    writer = _minimal(tmp_path)
    out = writer.write()
    assert (out / "datasets.parquet").is_file()
    assert (out / "sources/provenance_test.json").read_text(encoding="utf-8") == "a"
    doc = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
    assert doc["dataset_id"] == "PXD000001"
    assert doc["tables"] == {"datasets": 1}
    assert doc["sources"][0]["role"] == "provenance:test"
    assert pq.read_table(out / "datasets.parquet").num_rows == 1


def test_an_existing_bundle_is_not_silently_overwritten(tmp_path):
    _minimal(tmp_path).write()
    with pytest.raises(IngestError, match="already exists"):
        _minimal(tmp_path).write()


def test_overwrite_rebuilds_in_place(tmp_path):
    first = _minimal(tmp_path).write()
    second = _minimal(tmp_path).write(overwrite=True)
    assert first == second


def test_a_dangling_reference_stops_the_write(tmp_path):
    writer = _minimal(tmp_path)
    writer.add("samples", [{
        "sample_id": "PXD000001:S1", "dataset_id": "PXD_OTHER", "source_name": "S1",
        "organism": "NCBITaxon:9606",
    }])
    with pytest.raises(IngestError, match="do not hold together"):
        writer.write()
    assert not writer.path().exists()


def test_a_declared_input_changes_the_bundle_id(tmp_path):
    """The manifest entry shapes the datasets row, so it has to be in the hash.

    aging added a `title:` to their manifest and the bundle id did not move, which is exactly the
    change content addressing exists to make visible.
    """
    first = BundleWriter(store=tmp_path, dataset_id="PXD1")
    first.add_declaration("manifest_entry", {"accession": "PXD1", "acquisition": "DDA"})
    second = BundleWriter(store=tmp_path, dataset_id="PXD1")
    second.add_declaration("manifest_entry", {"accession": "PXD1", "acquisition": "DIA"})
    assert first.bundle_id != second.bundle_id


def test_a_declared_input_hashes_the_same_however_the_mapping_is_ordered(tmp_path):
    first = BundleWriter(store=tmp_path, dataset_id="PXD1")
    first.add_declaration("manifest_entry", {"a": 1, "b": 2})
    second = BundleWriter(store=tmp_path, dataset_id="PXD1")
    second.add_declaration("manifest_entry", {"b": 2, "a": 1})
    assert first.bundle_id == second.bundle_id


def test_a_bundle_id_does_not_move_when_the_package_version_does(tmp_path, monkeypatch):
    # 0.6.0 added the study layer, which `build` creates and `ingest` never writes. A bundle id has
    # to mean "these are the same measurements", so a release that changes nothing an ingest reads
    # or writes must leave every stored bundle addressable by the id it was cited under.
    import datarepo
    from datarepo.bundle import BundleWriter

    source = tmp_path / "input.txt"
    source.write_text("same bytes", encoding="utf-8")

    def make() -> str:
        writer = BundleWriter(store=tmp_path / "store", dataset_id="PXD999999")
        writer.add_source(source, "test")
        return writer.bundle_id

    before = make()
    monkeypatch.setattr(datarepo, "__version__", "99.0.0")
    assert make() == before


def test_a_bundle_id_does_move_when_the_ingest_path_does(tmp_path, monkeypatch):
    # The converse, and the reason the constant exists at all: reading a file differently must
    # produce a different bundle, or the same id names two different sets of rows.
    from datarepo import bundle as bundle_module
    from datarepo.bundle import BundleWriter

    source = tmp_path / "input.txt"
    source.write_text("same bytes", encoding="utf-8")

    def make() -> str:
        writer = BundleWriter(store=tmp_path / "store", dataset_id="PXD999999")
        writer.add_source(source, "test")
        return writer.bundle_id

    before = make()
    monkeypatch.setattr(bundle_module, "INGESTER_VERSION", "99.0.0")
    assert make() != before
