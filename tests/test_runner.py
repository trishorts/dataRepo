"""The runner (G64, D28): released engines only, idempotent, beside the bundle, fully recorded.

The logs verb is replaced by a stand-in that returns rows the way pyMzLib's `GeneResolutions` does,
because the real one needs Ensembl's files. Everything around it -- input checks, species, database
hashing, acceptance, artefact ids, the catalog join -- is the real path. The real verb was run on
real data before release (CHANGELOG 0.20.0): 20,899 human rows, identical to logs' reference.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from datarepo import runner
from datarepo.bundle import sha256_file
from datarepo.catalog import BundleRef, build_catalog, catalog_id, run_query, select_artefacts
from datarepo.engines import logs
from datarepo.errors import CatalogError, RunnerError

from test_catalog import write_bundle

INSTALL = {"distribution": "datarepo", "version": "test", "source": "test"}
RELEASE = {"pymzlib": "0.2.0", "mzlib": "1.0.592"}
GTF_SHA = "e" * 64


# --- install identity ------------------------------------------------------------------------------

def _identity(monkeypatch, info, git=None):
    monkeypatch.setattr(runner, "_direct_url", lambda dist: info)
    if git is not None:
        monkeypatch.setattr(runner, "_git", lambda path, *args: git[args[0]])
    return runner.install_identity("datarepo", version="9.9.9")


def test_an_editable_install_is_refused(monkeypatch):
    # aging 063: their datarepo on PATH was our working tree, mid-flight on an unreleased version.
    with pytest.raises(RunnerError, match="EDITABLE"):
        _identity(monkeypatch, {"url": "file:///E:/CodeReview/dataRepo", "dir_info": {"editable": True}})


def test_a_clean_clone_install_is_identified_by_its_commit(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    got = _identity(
        monkeypatch,
        {"url": tmp_path.as_uri(), "dir_info": {}},
        git={"status": "", "rev-parse": "c26eba9b756850c616556f93d5b25951bd3a5889"},
    )
    assert got["source"] == "git-clone"
    assert got["commit"] == "c26eba9b756850c616556f93d5b25951bd3a5889"


def test_a_dirty_clone_install_is_refused(monkeypatch, tmp_path):
    (tmp_path / ".git").mkdir()
    with pytest.raises(RunnerError, match="uncommitted"):
        _identity(monkeypatch, {"url": tmp_path.as_uri(), "dir_info": {}},
                  git={"status": " M src/x.py", "rev-parse": "x"})


def test_a_directory_that_is_not_a_clone_is_refused(monkeypatch, tmp_path):
    with pytest.raises(RunnerError, match="not a git clone"):
        _identity(monkeypatch, {"url": tmp_path.as_uri(), "dir_info": {}})


def test_vcs_archive_and_index_installs_are_identified(monkeypatch):
    assert _identity(monkeypatch, {"url": "git+https://x", "vcs_info": {"commit_id": "abc"}})["commit"] == "abc"
    got = _identity(monkeypatch, {"url": "file:///w.whl", "archive_info": {"hashes": {"sha256": "f00"}}})
    assert got["sha256"] == "f00"
    assert _identity(monkeypatch, None) == {"distribution": "datarepo", "version": "9.9.9", "source": "index"}


# --- artefact ids --------------------------------------------------------------------------------

def test_the_artefact_id_covers_engine_release_inputs_and_definition_and_nothing_else():
    base = runner.artefact_id("e", RELEASE, {"db": "1", "gene_set": "2"}, "d v1")
    assert base == runner.artefact_id("e", dict(RELEASE), {"gene_set": "2", "db": "1"}, "d v1")
    assert base != runner.artefact_id("e", {**RELEASE, "pymzlib": "0.3.0"}, {"db": "1", "gene_set": "2"}, "d v1")
    assert base != runner.artefact_id("e", RELEASE, {"db": "9", "gene_set": "2"}, "d v1")
    assert base != runner.artefact_id("e", RELEASE, {"db": "1", "gene_set": "2"}, "d v2")


# --- the logs engine -----------------------------------------------------------------------------

@pytest.fixture
def world(tmp_path):
    """A store with one human bundle that searched a target and a contaminant database, and logs'
    inputs for human."""
    store = tmp_path / "store"
    target = tmp_path / "db" / "human.xml"
    contaminant = tmp_path / "db" / "Contaminants.xml"
    target.parent.mkdir()
    target.write_text("<target/>", encoding="utf-8")
    contaminant.write_text("<contaminant/>", encoding="utf-8")
    ref = write_bundle(store, "PXD000001", accessions=("P11111", "P22222", "P33333"))
    doc = json.loads((ref.path / "bundle.json").read_text(encoding="utf-8"))
    doc["protein_databases"] = {"read": [
        {"path": str(target), "sha256": sha256_file(target), "entries": 3},
        {"path": str(contaminant), "sha256": sha256_file(contaminant), "entries": 1},
    ]}
    (ref.path / "bundle.json").write_text(json.dumps(doc), encoding="utf-8")
    # P33333 is a contaminant-panel protein that ALSO has a gene row, which is the case the join
    # must refuse: a contaminant is never mapped through anything (logs 002 section 0).
    import pyarrow as pa
    import pyarrow.parquet as pq
    proteins = pq.read_table(ref.path / "proteins.parquet")
    flags = [acc == "P33333" for acc in proteins.column("protein_accession").to_pylist()]
    proteins = proteins.set_column(
        proteins.schema.get_field_index("is_contaminant"), "is_contaminant", pa.array(flags, pa.bool_())
    )
    pq.write_table(proteins, ref.path / "proteins.parquet")

    gene_set = tmp_path / "Homo_sapiens.GRCh38.116.genes.tsv.gz"
    xref = tmp_path / "Homo_sapiens.GRCh38.116.uniprot.tsv.gz"
    gene_set.write_bytes(b"genes")
    xref.write_bytes(b"xref")
    manifest = tmp_path / "resolver_inputs_e116.json"
    manifest.write_text(json.dumps({"species": [{
        "species": "homo_sapiens", "ncbi_taxonomy_id": 9606,
        "inputs": {"gene_set": {"sha256": sha256_file(gene_set)},
                   "ensembl_uniprot_xref": {"sha256": sha256_file(xref)}},
        "row_values": {"gene_set_release": "116", "gene_set_sha256": GTF_SHA,
                       "ensembl_xref_sha256": sha256_file(xref)},
    }]}), encoding="utf-8")
    inputs = {"gene_set": gene_set, "xref": xref, "logs_manifest": manifest}
    return SimpleNamespace(store=store, bundle=BundleRef.load(ref.path), inputs=inputs,
                           target=target, xref_sha=sha256_file(xref))


def fake_resolver(world, **override):
    """Rows as pyMzLib returns them: P11111 resolved, P22222 two genes, P33333 no gene."""
    calls = []

    def resolve(database, gene_set, xref):
        calls.append(database)
        sha = sha256_file(database)
        base = {"entry_accession": None, "isoform": None, "namespace": "uniprot",
                "versioned_gene_id": None, "gene_biotype": "protein_coding", "off_primary_genes": 0,
                "uniprot_gene_name": None, "source": "search_database_dbreference",
                "search_database_sha256": sha, "gene_set_release": "116",
                "gene_set_sha256": GTF_SHA, "ensembl_xref_agrees": True,
                "ensembl_xref_info_type": "DIRECT", "ensembl_xref_sha256": world.xref_sha,
                "source_index": 0, "source_path": str(database)}
        rows = [
            {**base, "accession": "P11111", "outcome": "resolved", "n_genes": 1, "gene_id": "ENSG1", "gene_symbol": "G1"},
            {**base, "accession": "P22222", "outcome": "multi_gene", "n_genes": 2, "gene_id": "ENSG2", "gene_symbol": "G2"},
            {**base, "accession": "P22222", "outcome": "multi_gene", "n_genes": 2, "gene_id": "ENSG3", "gene_symbol": "G3"},
            {**base, "accession": "P33333", "outcome": "not_in_source", "n_genes": 0, "gene_id": None,
             "gene_symbol": None, "gene_biotype": None, "ensembl_xref_agrees": None, "ensembl_xref_info_type": None},
        ]
        rows = [{**r, **override} for r in rows]
        names = list(rows[0])
        return SimpleNamespace(column_names=names, columns={n: [r[n] for r in rows] for n in names},
                               failed_count=0, protein_count=3, record_count=len(rows),
                               outcome_counts={"resolved": 1}, caveats=[])

    resolve.calls = calls
    return resolve


def run(world, resolve=None, **kw):
    return logs.run(world.store, [world.bundle], world.inputs, install=INSTALL, release=RELEASE,
                    resolve=resolve or fake_resolver(world), **kw)


def test_one_artefact_per_target_database_and_the_contaminant_database_is_never_resolved(world):
    resolve = fake_resolver(world)
    result = run(world, resolve)
    assert [Path(p).name for p in resolve.calls] == ["human.xml"]
    assert result.skipped_contaminant == ["Contaminants.xml"]
    (artefact,) = result.written
    assert artefact.path.parent == world.store / "_engine" / "logs.resolve_genes"
    assert artefact.row_counts == {"gene_resolutions": 4}
    record = artefact.record
    assert record["definition_id"] == "logs:DEF-GENE-RESOLUTION v1"
    assert record["inputs"]["search_database"] == sha256_file(world.target)
    assert record["datarepo_install"] == INSTALL
    assert record["requested_for"] == [{"dataset_id": "PXD000001", "bundle_id": world.bundle.bundle_id}]
    # pyMzLib's bookkeeping columns are not stored; the definition id is.
    import pyarrow.parquet as pq
    table = pq.read_table(artefact.table_path("gene_resolutions"))
    assert "source_path" not in table.column_names
    assert set(table.column("definition_id").to_pylist()) == {"logs:DEF-GENE-RESOLUTION v1"}


def test_running_twice_runs_once(world):
    first = run(world)
    resolve = fake_resolver(world)
    again = run(world, resolve)
    assert resolve.calls == [] and again.written == []
    assert [a.artefact_id for a in again.already_done] == [first.written[0].artefact_id]


def test_the_bundle_is_never_touched(world):
    before = {p.name: p.read_bytes() for p in world.bundle.path.iterdir() if p.is_file()}
    run(world)
    assert {p.name: p.read_bytes() for p in world.bundle.path.iterdir() if p.is_file()} == before


def test_no_xref_is_not_v1_and_is_refused(world):
    del world.inputs["xref"]
    with pytest.raises(RunnerError, match="not logs:DEF-GENE-RESOLUTION v1"):
        run(world)


def test_a_database_that_no_longer_hashes_to_the_bundles_record_is_refused(world):
    world.target.write_text("<changed/>", encoding="utf-8")
    with pytest.raises(RunnerError, match="not the database they searched"):
        run(world)
    assert not (world.store / "_engine").exists() or not any((world.store / "_engine").rglob("run.json"))


def test_rows_that_disagree_with_logs_manifest_are_refused_and_nothing_is_written(world):
    with pytest.raises(RunnerError, match="gene_set_sha256"):
        run(world, fake_resolver(world, gene_set_sha256="0" * 64))
    assert not any((world.store / "_engine").rglob("run.json")) if (world.store / "_engine").exists() else True


def test_a_gene_set_logs_does_not_list_is_refused(world, tmp_path):
    other = tmp_path / "other.genes.tsv.gz"
    other.write_bytes(b"not logs'")
    world.inputs["gene_set"] = other
    with pytest.raises(RunnerError, match="no species in logs' manifest"):
        run(world)


def test_a_bundle_of_another_species_is_refused(world):
    doc = json.loads(world.inputs["logs_manifest"].read_text(encoding="utf-8"))
    doc["species"][0]["ncbi_taxonomy_id"] = 10090
    world.inputs["logs_manifest"].write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(RunnerError, match="only resolves its own species"):
        run(world)


# --- the catalog -------------------------------------------------------------------------------

def test_the_catalog_loads_the_artefact_and_joins_it_to_target_proteins_only(world, tmp_path):
    artefact = run(world).written[0]
    artefacts, checks = select_artefacts(world.store, [world.bundle])
    assert [a.artefact_id for a in artefacts] == [artefact.artefact_id]
    assert checks[0]["observed"] == checks[0]["expected"] == 1
    out = tmp_path / "cat.duckdb"
    result = build_catalog([world.bundle], out, artefacts=artefacts, engine_checks=checks)
    assert result.row_counts["gene_resolutions"] == 4
    assert result.catalog_id == catalog_id([world.bundle], (), artefacts)
    assert result.catalog_id != catalog_id([world.bundle])

    _, data = run_query(out, "SELECT protein_accession, gene_id FROM protein_genes ORDER BY 1, 2")
    assert data == [("P11111", "ENSG1"), ("P22222", "ENSG2"), ("P22222", "ENSG3")]  # P33333 is a contaminant
    _, kinds = run_query(out, "SELECT kind FROM catalog_tables WHERE table_name = 'gene_resolutions'")
    assert kinds == [("engine:logs.resolve_genes",)]
    _, meta = run_query(out, "SELECT artefact_id, definition_id FROM catalog_engine_artefacts")
    assert meta == [(artefact.artefact_id, "logs:DEF-GENE-RESOLUTION v1")]


def test_a_catalog_without_an_artefact_builds_and_says_so(world, tmp_path):
    artefacts, checks = select_artefacts(world.store, [world.bundle])
    assert artefacts == []
    assert checks[0]["ok"] and checks[0]["observed"] == 0 and "PXD000001" in checks[0]["detail"]
    result = build_catalog([world.bundle], tmp_path / "c.duckdb", engine_checks=checks)
    assert result.row_counts["gene_resolutions"] == 0


def test_two_resolutions_of_one_database_are_refused_rather_than_chosen(world):
    run(world)
    logs.run(world.store, [world.bundle], world.inputs, install=INSTALL,
             release={**RELEASE, "pymzlib": "0.3.0"}, resolve=fake_resolver(world))
    with pytest.raises(CatalogError, match="A catalog serves one"):
        select_artefacts(world.store, [world.bundle])
