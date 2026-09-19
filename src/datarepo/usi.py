"""Mint Universal Spectrum Identifiers.

Every PSM carries a USI, which is what lets a person or an agent pull up the actual spectrum behind
a claim from PRIDE's PROXI service (FRAMEWORK section 1, lesson 5).

    mzspec:PXD036557:QE-002123_GM7_b:scan:40132:KLADQC[UNIMOD:4]TGLQ/3

The trap is the run name. A USI must name the file *as deposited in the archive*, but the search
ran on calibrated copies, so MetaMorpheus reports `QE-002123_GM7_b-calib`. Resolving that back to
the deposited name is done against the fetch manifest's own file list, not by guessing, so a run
that cannot be matched produces no USI rather than one that fails to resolve.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Suffixes the pipeline's calibration stage appends to a run's base name.
CALIBRATION_SUFFIXES = ("-calib", "-averaged", "-calibrated")


def strip_pipeline_suffix(name: str) -> str:
    """Remove the calibration suffixes MetaMorpheus adds to a run name."""
    changed = True
    while changed:
        changed = False
        for suffix in CALIBRATION_SUFFIXES:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                changed = True
    return name


@dataclass
class RunNameMap:
    """Map the names a search reports onto the run IDs of deposited files.

    Args:
        deposited: run base names as the archive holds them, e.g. `QE-002123_GM7_b`.
    """

    deposited: tuple[str, ...]

    def __post_init__(self) -> None:
        self._index = {name.casefold(): name for name in self.deposited}
        self.unmatched: dict[str, int] = {}

    def resolve(self, reported: str) -> str | None:
        """Return the deposited run name for a name a search reported, or None."""
        for candidate in (reported, strip_pipeline_suffix(reported)):
            hit = self._index.get(candidate.casefold())
            if hit is not None:
                return hit
        self.unmatched[reported] = self.unmatched.get(reported, 0) + 1
        return None


def mint(dataset_id: str, run_name: str, scan: int, proforma: str, charge: int) -> str:
    """Build a USI for one PSM.

    Args:
        dataset_id: ProteomeXchange accession, the USI collection.
        run_name: the deposited run name, without extension.
        scan: 1-based scan number of the MS2 spectrum.
        proforma: ProForma 2 peptidoform.
        charge: precursor charge state.
    """
    return f"mzspec:{dataset_id}:{run_name}:scan:{scan}:{proforma}/{charge}"
