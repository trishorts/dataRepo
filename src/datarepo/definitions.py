"""Metric definitions, copied from the registers that own them.

Every number in the repository carries a definition ID (FRAMEWORK section 3), and dataRepo owns
none of them: metric definitions belong to QuantProject, and the pipeline's own counts to aging.
What is stored here is a *copy* of the owner's text, with the owner named, so a bundle can be read
without reaching back into another project's repository.

IDs are namespaced `<owner>:<ID>` because two registers can and do use the same short code (aging's
`DEF-CONTAM-PSM` and QuantProject's `DEF-QC-9` both describe a contaminant share). The bare form in
the schema's example is ambiguous the moment a second register appears; U7 in OPEN_QUESTIONS.md
records the namespacing as the default.

`PROVISIONAL:` entries are placeholders where no owner has published a definition yet. They say so
in their own text, so an agent that reads one is told the number's meaning is not yet fixed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Def:
    definition_id: str
    version: str
    owner_project: str
    text: str
    url: str | None = None

    def row(self) -> dict[str, str | None]:
        return {
            "definition_id": self.definition_id,
            "version": self.version,
            "owner_project": self.owner_project,
            "text": self.text,
            "url": self.url,
        }


#: aging's two PSM counts. They differ on purpose; S21 closed by aging thread 006.
PSM_1PCT = Def(
    "aging:DEF-PSM-1PCT",
    "v1",
    "aging",
    "Target PSMs at 1% FDR, as MetaMorpheus's results.txt summary line reports them: "
    "'All target PSMs with q-value <= 0.01'. Target PSMs only. This is the canonical PSM count.",
)
PSM_FDR_ENGINE = Def(
    "aging:DEF-PSM-FDRENGINE",
    "v1",
    "aging",
    "PSMs within 1% FDR as MetaMorpheus's FDR engine logs them. Higher than DEF-PSM-1PCT; it "
    "appears to include contaminant PSMs. In aging-provenance/2 and earlier this is the number "
    "stored as id_rate.psms_1pct, which is why the provenance field name cannot be trusted alone.",
)
ID_RATE = Def(
    "aging:DEF-ID-RATE",
    "v1",
    "aging",
    "Identified fraction of MS2 spectra, as the pipeline records it in provenance id_rate.rate: "
    "the stage's PSM count over the MS2 count. Which PSM count it uses follows the provenance "
    "schema version (DEF-PSM-FDRENGINE in /2 and earlier).",
)
MBR = Def(
    "QuantProject:DEF-QC-MBR",
    "v1",
    "QuantProject",
    "Match-between-runs quality block as the pipeline records it: rows attempted, rows kept at the "
    "MBR FDR threshold, MS/MS-anchored peaks, and the kept-over-MSMS ratio. Copied from the "
    "provenance record that names this definition.",
)

#: Placeholders. Replace with the owner's text when QuantProject publishes it (DATAREPO-11).
PEPTIDE_INTENSITY = Def(
    "PROVISIONAL:PEPTIDE-INTENSITY",
    "v0",
    "dataRepo (provisional)",
    "PROVISIONAL, not an owner's definition. FlashLFQ's per-run peptide intensity as written in "
    "AllQuantifiedPeptides.tsv, stored verbatim. Awaiting QuantProject's definition of the "
    "summarisation from peak apexes to a peptide intensity (DATAREPO-11).",
)
PROTEIN_INTENSITY = Def(
    "PROVISIONAL:PROTEIN-INTENSITY",
    "v0",
    "dataRepo (provisional)",
    "PROVISIONAL, not an owner's definition. FlashLFQ's per-run protein-group intensity as written "
    "in AllQuantifiedProteinGroups.tsv, stored verbatim (DATAREPO-11).",
)
PROTEIN_SPECTRAL_COUNT = Def(
    "PROVISIONAL:PROTEIN-SPECTRAL-COUNT",
    "v0",
    "dataRepo (provisional)",
    "PROVISIONAL, not an owner's definition. Spectral count per protein group per run as written "
    "in AllQuantifiedProteinGroups.tsv, stored verbatim (DATAREPO-11).",
)
PEPTIDE_COUNT_1PCT = Def(
    "PROVISIONAL:PEPTIDE-COUNT-1PCT",
    "v0",
    "dataRepo (provisional)",
    "PROVISIONAL. Target peptides at 1% FDR from MetaMorpheus's results.txt summary line. aging "
    "has not yet registered a definition ID for it (DATAREPO-11).",
)
PROTEIN_GROUP_COUNT_1PCT = Def(
    "PROVISIONAL:PROTEIN-GROUP-COUNT-1PCT",
    "v0",
    "dataRepo (provisional)",
    "PROVISIONAL. Target protein groups at 1% FDR from MetaMorpheus's results.txt summary line "
    "(DATAREPO-11).",
)
MS2_COUNT = Def(
    "PROVISIONAL:MS2-COUNT",
    "v0",
    "dataRepo (provisional)",
    "PROVISIONAL. MS2 spectra counted by the pipeline's spectra QC stage, or by MetaMorpheus's "
    "results.txt where the QC report is absent (DATAREPO-11).",
)
RUN_MINUTES = Def(
    "PROVISIONAL:RUN-MINUTES",
    "v0",
    "dataRepo (provisional)",
    "PROVISIONAL. Acquisition length in minutes from the pipeline's qc_report.json (DATAREPO-11).",
)
PRECURSOR_COUNT = Def(
    "PROVISIONAL:PRECURSOR-COUNT",
    "v0",
    "dataRepo (provisional)",
    "PROVISIONAL. Precursors reported by MetaMorpheus's results.txt (DATAREPO-11).",
)

ALL: tuple[Def, ...] = (
    PSM_1PCT,
    PSM_FDR_ENGINE,
    ID_RATE,
    MBR,
    PEPTIDE_INTENSITY,
    PROTEIN_INTENSITY,
    PROTEIN_SPECTRAL_COUNT,
    PEPTIDE_COUNT_1PCT,
    PROTEIN_GROUP_COUNT_1PCT,
    MS2_COUNT,
    RUN_MINUTES,
    PRECURSOR_COUNT,
)

BY_ID = {d.definition_id: d for d in ALL}


def rows(used: set[str] | None = None) -> list[dict[str, str | None]]:
    """Definition rows for a bundle; `used` restricts them to the IDs the bundle actually cites."""
    return [d.row() for d in ALL if used is None or d.definition_id in used]
