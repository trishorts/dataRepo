"""Translate MetaMorpheus full-sequence notation into ProForma 2.

One peptidoform notation everywhere, with UNIMOD accessions (FRAMEWORK section 3). MetaMorpheus
writes `KLADQC[Common Fixed:Carbamidomethyl on C]TGLQ`; the repository stores
`KLADQC[UNIMOD:4]TGLQ`, which is what ProForma 2 readers, USIs and the benchmark's questions are
written in.

This module is a stop-gap and is meant to be deleted. pyMzLib's `psmtsv` records already carry a
`pro_forma` field; it is null for MetaMorpheus files in 0.1.x, which is why the translation happens
here (DATAREPO-12 to pyMzLib). When that field is populated, this becomes a fallback and then goes.

The one thing it will not do is guess. A modification the registry cannot resolve keeps its name in
a ProForma `[Info:...]` tag and is reported, so an unresolved modification shows up as a Finding on
the dataset rather than as a plausible-looking wrong accession.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .modlist import MOD_TOKEN, ModRegistry

#: Position markers for `ModPlacement.position` outside the residue range.
N_TERMINUS = 0
C_TERMINUS = -1


@dataclass(frozen=True)
class ModPlacement:
    """One modification on one residue of a peptide."""

    position: int
    """1-based residue index in the peptide; `N_TERMINUS` or `C_TERMINUS` for a terminus."""
    residue: str
    """The modified residue's one-letter code, or `N-term` / `C-term`."""
    name: str
    """MetaMorpheus's name for the modification, verbatim."""
    category: str
    """MetaMorpheus's group, e.g. `Common Biological`, `UniProt`."""
    unimod: str | None
    """`UNIMOD:<n>` when the registry resolved it."""
    mass: float | None
    """Monoisotopic mass shift when the registry knows one."""

    @property
    def resolved(self) -> bool:
        return self.unimod is not None


@dataclass(frozen=True)
class Peptidoform:
    """A parsed MetaMorpheus full sequence."""

    proforma: str
    base_sequence: str
    mods: tuple[ModPlacement, ...] = ()
    unresolved: tuple[str, ...] = field(default=())

    @property
    def is_modified(self) -> bool:
        return bool(self.mods)


def _tag(mod_name: str, entry_unimod: str | None, mass: float | None) -> str:
    if entry_unimod is not None:
        return f"[{entry_unimod}]"
    if mass is not None:
        return f"[{mass:+.6f}]"
    return f"[Info:{mod_name}]"


def _split(full_sequence: str) -> list[tuple[str, str | None]]:
    """Split a full sequence into (residue, bracket-content) pairs, plus a leading pair.

    A bracket before the first residue is returned with an empty residue, which is how an
    N-terminal modification announces itself in MetaMorpheus notation.
    """
    out: list[tuple[str, str | None]] = []
    i = 0
    pending_leading: str | None = None
    n = len(full_sequence)
    while i < n:
        ch = full_sequence[i]
        if ch == "[":
            depth = 1
            j = i + 1
            while j < n and depth:
                if full_sequence[j] == "[":
                    depth += 1
                elif full_sequence[j] == "]":
                    depth -= 1
                j += 1
            content = full_sequence[i + 1 : j - 1]
            if out:
                residue, existing = out[-1]
                out[-1] = (residue, content if existing is None else f"{existing}|{content}")
            else:
                pending_leading = content if pending_leading is None else f"{pending_leading}|{content}"
            i = j
            continue
        out.append((ch, None))
        i += 1
    if pending_leading is not None:
        out.insert(0, ("", pending_leading))
    return out


def parse(full_sequence: str, registry: ModRegistry) -> Peptidoform:
    """Convert one MetaMorpheus full sequence to ProForma 2.

    Args:
        full_sequence: the `Full Sequence` column of a `.psmtsv`.
        registry: modifications from the MetaMorpheus install that did the search.

    Returns:
        A `Peptidoform` carrying the ProForma string, the unmodified sequence, where each
        modification sits, and the names nothing could resolve.
    """
    if not full_sequence:
        return Peptidoform(proforma="", base_sequence="")

    pieces = _split(full_sequence)
    base: list[str] = []
    mods: list[ModPlacement] = []
    unresolved: list[str] = []
    n_term_tags: list[str] = []
    residue_tags: dict[int, list[str]] = {}

    for residue, bracket in pieces:
        if residue:
            base.append(residue)
        position = len(base) if residue else N_TERMINUS
        if bracket is None:
            continue
        for token in bracket.split("|"):
            m = MOD_TOKEN.match(token)
            category, name = (m.group("category"), f"{m.group('name')} on {m.group('residue')}") if m else ("", token)
            target = m.group("residue") if m else None
            entry = registry.lookup(name, target)
            unimod = entry.unimod_curie if entry else None
            mass = entry.monoisotopic_mass if entry else None
            if unimod is None and mass is None:
                unresolved.append(token)
            mods.append(
                ModPlacement(
                    position=position,
                    residue="N-term" if position == N_TERMINUS else base[position - 1],
                    name=name,
                    category=category,
                    unimod=unimod,
                    mass=mass,
                )
            )
            tag = _tag(name, unimod, mass)
            if position == N_TERMINUS:
                n_term_tags.append(tag)
            else:
                residue_tags.setdefault(position, []).append(tag)

    parts = ["".join(n_term_tags) + "-"] if n_term_tags else []
    for index, residue in enumerate(base, start=1):
        parts.append(residue + "".join(residue_tags.get(index, ())))

    return Peptidoform(
        proforma="".join(parts),
        base_sequence="".join(base),
        mods=tuple(mods),
        unresolved=tuple(dict.fromkeys(unresolved)),
    )


class ProformaCache:
    """`parse` memoized over one dataset.

    A dataset's 43k PSMs collapse to a few thousand distinct full sequences, so the same string is
    translated over and over. The cache also accumulates the unresolved names, which become one
    Finding per dataset rather than one per PSM.
    """

    def __init__(self, registry: ModRegistry):
        self.registry = registry
        self._cache: dict[str, Peptidoform] = {}
        self.unresolved: dict[str, int] = {}

    def __call__(self, full_sequence: str) -> Peptidoform:
        hit = self._cache.get(full_sequence)
        if hit is None:
            hit = parse(full_sequence, self.registry)
            self._cache[full_sequence] = hit
            for name in hit.unresolved:
                self.unresolved[name] = self.unresolved.get(name, 0)
        for name in hit.unresolved:
            self.unresolved[name] += 1
        return hit

    @property
    def size(self) -> int:
        return len(self._cache)
