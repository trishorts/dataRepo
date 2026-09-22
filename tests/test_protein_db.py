"""The searched protein database, read for placing sites (DATAREPO-32)."""

from __future__ import annotations

import hashlib

import pytest

from datarepo.errors import IngestError
from datarepo.sources import protein_db

XML = """<?xml version="1.0" encoding="UTF-8"?>
<uniprot xmlns="http://uniprot.org/uniprot">
<entry dataset="Swiss-Prot">
  <accession>P60709</accession>
  <accession>Q1XHY6</accession>
  <comment type="alternative products"><isoform><sequence type="displayed"/></isoform></comment>
  <sequence length="10" mass="1">MDDDI
  AALVV</sequence>
</entry>
<entry dataset="Swiss-Prot">
  <accession>P63261</accession>
  <sequence length="5" mass="1">MEEEI</sequence>
</entry>
</uniprot>
"""


def test_a_uniprot_xml_gives_the_first_accession_and_the_entrys_own_sequence(tmp_path):
    path = tmp_path / "db.xml"
    path.write_text(XML, encoding="utf-8")
    seqs = protein_db.ProteinSequences()
    assert protein_db.read_database(path, seqs) == 2
    assert seqs.get("P60709") == ["MDDDIAALVV"]
    assert seqs.get("Q1XHY6") == []          # a secondary accession is not how mzLib keys it
    assert seqs.get("P63261") == ["MEEEI"]


def test_a_fasta_is_keyed_on_the_uniprot_accession(tmp_path):
    path = tmp_path / "db.fasta"
    path.write_text(">sp|P02769|ALBU_BOVIN Albumin\nMKWV\nTFIS\n>custom_progerin\nMETP\n", encoding="utf-8")
    seqs = protein_db.ProteinSequences()
    protein_db.read_database(path, seqs)
    assert seqs.get("P02769") == ["MKWVTFIS"]
    assert seqs.get("custom_progerin") == ["METP"]


def test_an_accession_in_two_databases_keeps_both_sequences():
    seqs = protein_db.ProteinSequences()
    seqs.add("P04264", "MSRQ")
    seqs.add("P04264", "MSRQ")
    seqs.add("P04264", "MSRK")
    assert seqs.get("P04264") == ["MSRQ", "MSRK"]


def test_occurrences_include_overlapping_ones():
    assert protein_db.occurrences("AA", "AAAB") == [1, 2]
    assert protein_db.occurrences("PEP", "XPEPXPEP") == [2, 6]
    assert protein_db.occurrences("ZZ", "AAAB") == []


def test_a_database_that_is_not_the_searched_one_stops_the_ingest(tmp_path):
    path = tmp_path / "db.xml"
    path.write_text(XML, encoding="utf-8")
    provenance = {"inputs": [{"path": "db.xml", "sha256": "0" * 64}]}
    with pytest.raises(IngestError, match="not the database that was searched"):
        protein_db.load(provenance, tmp_path)


def test_a_matching_database_is_read_and_a_missing_one_is_named(tmp_path):
    path = tmp_path / "db.xml"
    path.write_text(XML, encoding="utf-8")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    provenance = {
        "inputs": [
            {"path": "db.xml", "sha256": sha},
            {"path": "gone/contaminants.xml", "sha256": "1" * 64},
            {"path": "tasks/3_SearchTask.toml", "sha256": "2" * 64},
        ]
    }
    seqs = protein_db.load(provenance, tmp_path)
    assert len(seqs) == 2
    assert seqs.files == [{"path": str(path), "sha256": sha, "entries": 2}]
    assert seqs.missing == [str(tmp_path / "gone/contaminants.xml")]


def test_the_standard_library_parser_reads_exactly_what_lxml_reads(tmp_path, monkeypatch):
    """The two paths must agree, or a bundle's rows depend on whether lxml happened to be installed."""
    import builtins

    path = tmp_path / "db.xml"
    path.write_text(XML, encoding="utf-8")
    fast = list(protein_db._iter_uniprot_xml(path))

    real_import = builtins.__import__

    def no_lxml(name, *args, **kwargs):
        if name == "lxml" or name.startswith("lxml."):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_lxml)
    slow = list(protein_db._iter_uniprot_xml(path))
    assert slow == fast == [("P60709", "MDDDIAALVV"), ("P63261", "MEEEI")]


def test_the_fixture_databases_parse_identically_both_ways(monkeypatch):
    """Same check on real UniProt XML rather than a hand-written one."""
    import builtins

    from conftest import WORK_ROOT

    for name in ("test_human.xml", "test_contaminants.xml"):
        path = WORK_ROOT / "db" / name
        fast = list(protein_db._iter_uniprot_xml(path))
        real_import = builtins.__import__
        monkeypatch.setattr(
            builtins, "__import__",
            lambda n, *a, **k: (_ for _ in ()).throw(ImportError(n)) if n.startswith("lxml") else real_import(n, *a, **k),
        )
        slow = list(protein_db._iter_uniprot_xml(path))
        monkeypatch.undo()
        assert fast and slow == fast


def test_the_residue_check_catches_a_wrong_residue_and_a_position_beyond_the_protein():
    from datarepo.sources.identifications import verify_site_residues

    seqs = protein_db.ProteinSequences()
    seqs.add("P1", "MKCDE")
    sites = [
        {"protein_accession": "P1", "position": 3, "residue": "C"},    # right
        {"protein_accession": "P1", "position": 2, "residue": "C"},    # wrong residue
        {"protein_accession": "P1", "position": 1067, "residue": "P"}, # gamma-actin with POTE-E's numbering
        {"protein_accession": "P9", "position": 1, "residue": "M"},    # no sequence
    ]
    assert verify_site_residues(sites, seqs) == {
        "residue_matches": 1, "wrong_residue": 1, "beyond_length": 1, "no_sequence": 1,
    }
