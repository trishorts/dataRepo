"""The search's protein database -> one sequence per accession, for placing sites (DATAREPO-32).

`ptm_sites` needs each PTM's position in every protein a peptide maps to. The psmtsv cannot supply
it: MetaMorpheus writes `Start and End Residues In Full Sequence` **de-duplicated**, one span per
distinct position rather than one per accession, and one per occurrence when a peptide repeats
within a protein:

    Accession                        Start and End Residues In Full Sequence
    P60709|P63261|Q6S8J3             [216 to 238]|[916 to 938]

Beta- and gamma-actin share a span, so it is written once. Across aging's ten datasets 140,818
target PSMs at 1% FDR have a span count different from their accession count, and 9,093 have MORE
spans than accessions (aging 043). No pairing of the two cells is right in general, including the
case where the counts happen to agree. So the position comes from the sequence: find the peptide
in each member protein, which is what MetaMorpheus's own occupancy code does.

Which databases were searched is read from the search provenance's `inputs`, the same list
`search_params.searched_database` reads, and each file's sha256 is checked against the one the
provenance recorded. A database edited after the search would place sites against sequences the
engine never saw, so a mismatch stops the ingest rather than being worked around.

pyMzLib has no protein-database reader, so this is in-house reading under `readers.py`'s rule: it
extracts the accession and the sequence and interprets nothing. Delete it when pyMzLib can hand
back `(accession, sequence)` for a UniProt XML or FASTA.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from ..bundle import sha256_file
from ..errors import IngestError
from . import search_params

_UNIPROT_NS = "{http://uniprot.org/uniprot}"


@dataclass
class ProteinSequences:
    """Accession -> every distinct sequence the searched databases carry under it.

    A list rather than one string because an accession can appear in two searched databases -- a
    human keratin is in both the proteome and the contaminant panel -- and the two need not agree.
    A site is placed wherever the peptide occurs in any of them.
    """

    by_accession: dict[str, list[str]] = field(default_factory=dict)
    files: list[dict[str, Any]] = field(default_factory=list)
    """What was read: path, sha256 and entry count per database, for bundle.json."""
    missing: list[str] = field(default_factory=list)
    """Databases the provenance names that are not on disk, so their proteins cannot be aligned."""

    def add(self, accession: str, sequence: str) -> None:
        known = self.by_accession.setdefault(accession, [])
        if sequence not in known:
            known.append(sequence)

    def get(self, accession: str) -> list[str]:
        return self.by_accession.get(accession, [])

    def __len__(self) -> int:
        return len(self.by_accession)


def occurrences(base_sequence: str, protein_sequence: str) -> list[int]:
    """Every 1-based start of `base_sequence` in `protein_sequence`, overlapping ones included."""
    starts = []
    at = protein_sequence.find(base_sequence)
    while at >= 0:
        starts.append(at + 1)
        at = protein_sequence.find(base_sequence, at + 1)
    return starts


def _iter_uniprot_xml(path: Path) -> Iterator[tuple[str, str]]:
    """`(first accession, sequence)` per `<entry>`, streamed.

    The first `<accession>` is the one mzLib's loader keys a protein on. Only the entry's direct
    `<sequence>` child is read; isoform sequences named inside comments are not entries.
    """
    try:
        from lxml import etree  # noqa: PLC0415 -- three times faster on a 1 GB file

        for _, entry in etree.iterparse(
            str(path), events=("end",), tag=f"{_UNIPROT_NS}entry", huge_tree=True
        ):
            accession = entry.findtext(f"{_UNIPROT_NS}accession")
            sequence = entry.find(f"{_UNIPROT_NS}sequence")
            if accession and sequence is not None and sequence.text:
                yield accession.strip(), "".join(sequence.text.split()).upper()
            entry.clear()
            while entry.getprevious() is not None:
                del entry.getparent()[0]
    except ImportError:
        import xml.etree.ElementTree as ET  # noqa: PLC0415

        context = ET.iterparse(str(path), events=("start", "end"))
        _, root = next(context)
        for event, element in context:
            if event != "end" or element.tag != f"{_UNIPROT_NS}entry":
                continue
            accession = element.findtext(f"{_UNIPROT_NS}accession")
            sequence = element.find(f"{_UNIPROT_NS}sequence")
            if accession and sequence is not None and sequence.text:
                yield accession.strip(), "".join(sequence.text.split()).upper()
            root.clear()


def _fasta_accession(header: str) -> str:
    """UniProt `sp|P12345|NAME_HUMAN ...` -> `P12345`; anything else -> its first token."""
    token = header[1:].split()[0] if header[1:].split() else ""
    parts = token.split("|")
    if len(parts) >= 3 and parts[0] in {"sp", "tr"}:
        return parts[1]
    return token


def _iter_fasta(path: Path) -> Iterator[tuple[str, str]]:
    accession, chunks = None, []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if line.startswith(">"):
                if accession and chunks:
                    yield accession, "".join(chunks).upper()
                accession, chunks = _fasta_accession(line), []
            elif line:
                chunks.append(line)
    if accession and chunks:
        yield accession, "".join(chunks).upper()


def read_database(path: Path, into: ProteinSequences) -> int:
    """Add every entry of one UniProt XML or FASTA file; returns how many were read."""
    name = path.name.lower()
    if name.endswith(".xml"):
        entries = _iter_uniprot_xml(path)
    elif name.endswith((".fasta", ".fa")):
        entries = _iter_fasta(path)
    else:
        # A gzipped database is legal input to MetaMorpheus but none has been searched yet; refuse
        # rather than silently place nothing.
        raise IngestError(f"cannot read protein database {path}: only .xml and .fasta are supported")
    count = 0
    for accession, sequence in entries:
        into.add(accession, sequence)
        count += 1
    return count


def searched_databases(provenance: dict[str, Any], work_root: Path) -> list[tuple[Path, str | None]]:
    """Every protein database the search provenance lists as an input, with its recorded sha256."""
    out = []
    for entry in provenance.get("inputs") or []:
        raw = str(entry.get("path", ""))
        if raw.lower().endswith(search_params.DATABASE_SUFFIXES):
            path = Path(raw)
            out.append((path if path.is_absolute() else work_root / path, entry.get("sha256")))
    return out


def load(provenance: dict[str, Any], work_root: Path) -> ProteinSequences:
    """Read every searched database that is on disk, after checking it is the file that was searched.

    Raises:
        IngestError: a database on disk does not match the sha256 the search recorded for it.
    """
    sequences = ProteinSequences()
    for path, recorded in searched_databases(provenance, work_root):
        if not path.is_file():
            sequences.missing.append(str(path))
            continue
        actual = sha256_file(path)
        if recorded and actual != recorded:
            raise IngestError(
                f"{path} is not the database that was searched: the search provenance recorded "
                f"sha256 {recorded} and the file on disk is {actual}. Sites would be placed against "
                f"sequences the engine never saw."
            )
        count = read_database(path, sequences)
        sequences.files.append({"path": str(path), "sha256": actual, "entries": count})
    return sequences
