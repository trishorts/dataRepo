"""Resolve MetaMorpheus modification names to UNIMOD accessions and monoisotopic masses.

MetaMorpheus names modifications in its own notation (`Common Biological:Hydroxylation on K`,
`UniProt:N6-acetyllysine on K`). The schema wants UNIMOD accessions, because ProForma 2 and every
downstream question are written in those. The mapping is not ours to invent: it is already written
down in the modification files that ship with the MetaMorpheus build that did the search, in the
`DR   Unimod; <n>.` lines of `Mods/*.txt` and `Data/ptmlist.txt`.

So the registry is *read from the search's own MetaMorpheus install*, which pins it to the version
recorded in the manifest. A modification that no file resolves is reported, never guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: UniProt's `TG` lines spell the residue out; MetaMorpheus's use the letter.
_RESIDUE_NAMES = {
    "alanine": "A", "arginine": "R", "asparagine": "N", "aspartate": "D",
    "aspartic acid": "D", "cysteine": "C", "glutamate": "E", "glutamic acid": "E",
    "glutamine": "Q", "glycine": "G", "histidine": "H", "isoleucine": "I",
    "leucine": "L", "lysine": "K", "methionine": "M", "phenylalanine": "F",
    "proline": "P", "pyrrolysine": "O", "selenocysteine": "U", "serine": "S",
    "threonine": "T", "tryptophan": "W", "tyrosine": "Y", "valine": "V",
}

_UNIMOD_LINE = re.compile(r"^DR\s+Unimod;\s*(\d+)", re.IGNORECASE)

#: `Category:Name on X` as MetaMorpheus writes it inside a full-sequence bracket.
MOD_TOKEN = re.compile(r"^(?P<category>[^:]+):(?P<name>.+?) on (?P<residue>[A-Zc-z]|[A-Z][a-z]+)$")


@dataclass(frozen=True)
class ModEntry:
    """One modification as its defining file describes it."""

    name: str
    targets: frozenset[str]
    unimod: int | None
    monoisotopic_mass: float | None
    source: str

    @property
    def unimod_curie(self) -> str | None:
        return None if self.unimod is None else f"UNIMOD:{self.unimod}"


def _targets(value: str) -> frozenset[str]:
    """Turn a `TG` line into single-letter residues.

    Handles MetaMorpheus's `K or N`, its motif forms such as `Nxs`, and UniProt's `Methionine.`
    """
    out: set[str] = set()
    for part in re.split(r"\s+or\s+|,", value.strip().rstrip(".")):
        part = part.strip()
        if not part:
            continue
        letter = _RESIDUE_NAMES.get(part.lower())
        if letter:
            out.add(letter)
        elif part.isalpha():
            # `C`, or a motif such as `Nxs` whose first residue is the modified one.
            out.add(part[0].upper())
    return frozenset(out)


def _parse_entries(text: str, source: str):
    """Yield ModEntry rows from a UniProt-style `ID/TG/MM/DR` flat file."""
    ident = target = mass = unimod = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("//"):
            if ident:
                yield ModEntry(
                    name=ident,
                    targets=_targets(target or ""),
                    unimod=unimod,
                    monoisotopic_mass=mass,
                    source=source,
                )
            ident = target = mass = unimod = None
            continue
        if line.startswith("ID   "):
            # A new ID without a closing `//` means the previous block ended (ptmlist.txt style).
            if ident:
                yield ModEntry(ident, _targets(target or ""), unimod, mass, source)
                target = mass = unimod = None
            ident = line[5:].strip()
        elif line.startswith("TG   "):
            target = line[5:].strip()
        elif line.startswith("MM   "):
            try:
                mass = float(line[5:].strip())
            except ValueError:
                mass = None
        elif (m := _UNIMOD_LINE.match(line)) is not None:
            unimod = int(m.group(1))
    if ident:
        yield ModEntry(ident, _targets(target or ""), unimod, mass, source)


class ModRegistry:
    """Every modification the search engine could have written, indexed by name."""

    def __init__(self, entries: list[ModEntry] | None = None):
        self._by_name: dict[str, list[ModEntry]] = {}
        self.sources: list[str] = []
        for entry in entries or []:
            self.add(entry)

    def add(self, entry: ModEntry) -> None:
        self._by_name.setdefault(entry.name.casefold(), []).append(entry)
        if entry.source not in self.sources:
            self.sources.append(entry.source)

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_name.values())

    @classmethod
    def from_metamorpheus(cls, install_dir: str | Path) -> ModRegistry:
        """Read `Mods/*.txt` and `Data/ptmlist.txt` from a MetaMorpheus install.

        A missing install is not an error here; it yields an empty registry, and every unresolved
        modification is reported by the caller instead.
        """
        install = Path(install_dir)
        registry = cls()
        for path in sorted((install / "Mods").glob("*.txt")) + [install / "Data" / "ptmlist.txt"]:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            for entry in _parse_entries(text, path.name):
                registry.add(entry)
        return registry

    def lookup(self, name: str, residue: str | None = None) -> ModEntry | None:
        """Find the entry for a MetaMorpheus modification name.

        `name` is the part inside the bracket after the category, e.g. `Hydroxylation on K` or
        `N6-acetyllysine on K`. Some files spell the target into the ID and some do not, so the
        full name is tried first and then the name with ` on <residue>` stripped.
        """
        candidates = self._by_name.get(name.casefold())
        if not candidates and " on " in name:
            stem, _, tail = name.rpartition(" on ")
            residue = residue or tail.strip()[:1].upper()
            candidates = self._by_name.get(stem.casefold())
        if not candidates:
            return None
        if residue:
            for entry in candidates:
                if residue.upper() in entry.targets:
                    return entry
        # No target match: prefer an entry that at least carries a UNIMOD accession.
        for entry in candidates:
            if entry.unimod is not None:
                return entry
        return candidates[0]
