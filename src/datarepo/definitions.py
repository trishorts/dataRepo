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
    "'All target PSMs with q-value <= 0.01'. Target PSMs only. This is the canonical PSM count. "
    "Four conditions, all required (aging thread 011): Decoy/Contaminant/Target == 'T', "
    "QValue <= 0.01, QValue Notch <= 0.01, and notch_ambiguous == false "
    "(aging:DEF-PSM-NOTCH-AMBIGUOUS). The fourth is not inferable from the written file alone, "
    "which is why a count taken without it comes out high.",
)
NOTCH_AMBIGUOUS = Def(
    "aging:DEF-PSM-NOTCH-AMBIGUOUS",
    "v1",
    "aging",
    "A PSM is notch-ambiguous when the Notch cell of AllPSMs.psmtsv contains a '|' separator, i.e. "
    "MetaMorpheus wrote more than one notch hypothesis for the match. For such a PSM, "
    "SpectralMatch.ResolveAllAmbiguities leaves the in-memory PsmFdrInfo.QValueNotch unresolved at "
    "> 1, while PsmTsvWriter.AddMatchScoreData writes the MINIMUM notch q-value across hypotheses. "
    "The written 'QValue Notch' can therefore pass a threshold the counted one fails, which is why "
    "aging:DEF-PSM-1PCT needs this condition as well as the two q-values.",
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

#: The two contaminant shares. Both are named in the provenance block itself, which is why they
#: could be copied without a round trip; the text is aging thread 014's description of them.
CONTAM_PSM_SHARE = Def(
    "aging:DEF-CONTAM-PSM",
    "v1",
    "aging",
    "Contaminant share of the identifications in a dataset: contaminant PSMs over "
    "(target + contaminant) PSMs, over the whole dataset. An identification-level share, so it "
    "says how much of the evidence came from the contaminant database, not how much of the signal "
    "did -- QuantProject:DEF-QC-9 is the intensity-level answer and the two differ by several fold.",
)
CONTAM_INTENSITY_SHARE = Def(
    "QuantProject:DEF-QC-9",
    "v2",
    "QuantProject",
    "Contaminant share of the measured intensity in ONE raw file: summed intensity of contaminant "
    "features over summed intensity of all features. It is defined per file, and aggregating it to "
    "a dataset hides real structure: on PXD036557 the per-file values run 2.6% to 18.9% and are "
    "grouped by cell line, which is serum carryover differing sevenfold inside one experiment "
    "(aging thread 014).",
)

#: The three that stay provisional, and should. QuantProject owns them and has not ruled; an ID
#: implying they had would be worse than the placeholder (DATAREPO-11).
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
#: aging's five, published in their thread 008 section 4 (their D20) and copied verbatim here. They
#: were placeholders for nine minutes longer than they needed to be: the first bundle was written
#: just before 008 arrived.
PEPTIDE_COUNT_1PCT = Def(
    "aging:DEF-PEPTIDE-1PCT",
    "v1",
    "aging",
    "Target peptides at 1% FDR: results.txt line 'All target peptides with q-value <= 0.01'. From "
    "AllPeptides.psmtsv: Decoy/Contaminant/Target == 'T', QValue <= 0.01, QValue Notch <= 0.01. "
    "MetaMorpheus computes it at peptide-level FDR, collapsing to one row per full sequence "
    "(lowest PEP). Verified on PXD036557: 5,541. No ambiguous-notch rows survive the collapse, so "
    "aging:DEF-PSM-NOTCH-AMBIGUOUS does not bite here.",
)
PROTEIN_GROUP_COUNT_1PCT = Def(
    "aging:DEF-PROTEINGROUP-1PCT",
    "v1",
    "aging",
    "Target protein groups at 1% FDR: results.txt line 'All target protein groups with q-value "
    "<= 0.01 (1% FDR)'. The predicate is Protein QValue <= 0.01 && !IsDecoy, so contaminant groups "
    "ARE counted -- unlike the PSM and peptide lines, which exclude them. Verified on PXD036557: "
    "1,652 not-decoy against 1,623 strictly 'T'.",
)
MS2_COUNT = Def(
    "aging:DEF-MS2",
    "v1",
    "aging",
    "MS2 scans in the run's raw files, counted by aging's QC stage from "
    "pymzlib.readers.read_spectra (scans with MS level 2), summed over files. Verified against "
    "MetaMorpheus's own 'All MS2 Scans' line on PXD036557: both 266,402.",
)
RUN_MINUTES = Def(
    "aging:DEF-RUN-MINUTES",
    "v1",
    "aging",
    "Acquisition length of one raw file: the maximum retention time over all its scans, in "
    "minutes, rounded to 2 dp. On PXD036557 all 18 files report 180.0, checked at full precision "
    "on two of them (180.00184 and 179.99996 min), so an identical value across files is a real "
    "method length rather than a rounding artefact or a default.",
)
PRECURSOR_COUNT = Def(
    "aging:DEF-PRECURSORS",
    "v1",
    "aging",
    "results.txt line 'All Precursors': the precursor envelopes MetaMorpheus deconvoluted from the "
    "MS2 scans, which is more than one per scan (495,127 over 266,402 scans on PXD036557). It is "
    "NOT a count of scans, and it is not a count of distinct species.",
)

ALL: tuple[Def, ...] = (
    PSM_1PCT,
    NOTCH_AMBIGUOUS,
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
    CONTAM_PSM_SHARE,
    CONTAM_INTENSITY_SHARE,
)

BY_ID = {d.definition_id: d for d in ALL}


def rows(used: set[str] | None = None) -> list[dict[str, str | None]]:
    """Definition rows for a bundle; `used` restricts them to the IDs the bundle actually cites."""
    return [d.row() for d in ALL if used is None or d.definition_id in used]
