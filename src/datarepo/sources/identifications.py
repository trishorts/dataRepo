"""MetaMorpheus `.psmtsv` -> Psm, Peptidoform, Protein and PtmSite rows.

Every PSM the search wrote is stored, decoys and above-threshold matches included. Filtering is a
question a caller asks (`q_value <= 0.01 and target_decoy = 'target'`), not a decision the
repository should have taken for them, and keeping the whole table is what lets a bundle reconcile
its own counts against the producer's summary.

Ambiguity is carried rather than resolved. MetaMorpheus writes alternatives separated by `|` when
it cannot place a modification or choose between sequences; the first alternative becomes the
stored peptidoform and `ambiguity_level` says what it is. PTM sites are derived only from
unambiguous evidence, because a site from an ambiguous localization is a claim the data does not
support.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

from ..errors import IngestError
from ..proforma import N_TERMINUS, ProformaCache
from ..usi import RunNameMap, mint

_RANGE = re.compile(r"\[(\d+)\s+to\s+(\d+)\]")


def _verbatim(value: Any) -> str | None:
    """One producer cell exactly as written, or None when it is absent."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first(value: Any) -> str:
    """MetaMorpheus separates alternatives with `|`; take the first and keep the level column."""
    text = "" if value is None else str(value)
    return text.split("|", 1)[0].strip()


def _int(value: Any) -> int | None:
    try:
        return int(float(_first(value)))
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        number = float(_first(value))
    except (TypeError, ValueError):
        return None
    return None if number != number else number


def _target_decoy(value: Any) -> str:
    """`D`, `C`, `T` (possibly `|`-joined) -> the schema's TargetDecoy value.

    Decoy wins over contaminant, and contaminant over target: the least trustworthy label on an
    ambiguous match is the one a reader needs to see.
    """
    text = ("" if value is None else str(value)).upper()
    if "D" in text:
        return "decoy"
    if "C" in text:
        return "contaminant"
    return "target"


def _residue_range(value: Any) -> tuple[int | None, int | None]:
    m = _RANGE.search("" if value is None else str(value))
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


#: Producer ambiguity levels, best first. A site is credited with the best level that placed it.
AMBIGUITY_ORDER = ("1", "2A", "2B", "2C", "2D", "3", "4", "5")


def _better_level(current: str | None, candidate: str | None) -> str | None:
    """The lower of two producer ambiguity levels, tolerating one this list does not know."""
    if candidate is None:
        return current
    if current is None:
        return candidate
    order = {name: i for i, name in enumerate(AMBIGUITY_ORDER)}
    fallback = len(AMBIGUITY_ORDER)
    return candidate if order.get(candidate, fallback) < order.get(current, fallback) else current


def _residue_starts(value: Any) -> list[int]:
    """Every start residue in a `[a to b]|[c to d]` field, in the order the accessions are in.

    MetaMorpheus writes one span per protein the peptide maps to, `|`-separated and positionally
    aligned with the accession column, so the two must be zipped rather than reduced.
    """
    return [int(m.group(1)) for m in _RANGE.finditer("" if value is None else str(value))]


def _accessions(value: Any) -> list[str]:
    text = "" if value is None else str(value)
    return [a.strip() for a in text.split("|") if a.strip()]


def _column(columns: dict[str, list[Any]], *names: str) -> list[Any] | None:
    for name in names:
        if name in columns:
            return columns[name]
    return None


def psm_rows(
    columns: dict[str, list[Any]],
    dataset_id: str,
    *,
    proforma: ProformaCache,
    run_names: RunNameMap,
    search: str,
) -> list[dict[str, Any]]:
    """Build Psm rows from the columns pyMzLib read out of `AllPSMs.psmtsv`.

    Args:
        columns: the reader's native fields, one list per column.
        dataset_id: ProteomeXchange accession.
        proforma: translator for MetaMorpheus full-sequence notation.
        run_names: maps the search's run names back to deposited ones, for the USI.
        search: which search produced these matches, e.g. `gptmd`.

    Returns:
        One row per PSM, ordered as the file was.
    """
    n = len(columns.get("full_sequence", ()))
    files = _column(columns, "file_name_without_extension", "file_name") or [""] * n
    scans = _column(columns, "one_based_scan_number", "ms2_scan_number") or [None] * n
    full = columns.get("full_sequence", [""] * n)
    charges = _column(columns, "precursor_charge", "charge_state") or [None] * n
    accession = _column(columns, "accession", "protein_accession") or [""] * n
    ranges = columns.get("start_and_end_residues_in_parent_sequence") or [""] * n

    seen: dict[tuple[str, int | None], int] = {}
    rows: list[dict[str, Any]] = []
    for i in range(n):
        reported_run = str(files[i] or "")
        deposited = run_names.resolve(reported_run)
        run_id = f"{dataset_id}:{deposited}" if deposited else f"{dataset_id}:{reported_run}"
        scan = _int(scans[i])
        key = (run_id, scan)
        rank = seen[key] = seen.get(key, 0) + 1

        parsed = proforma(_first(full[i]))
        charge = _int(charges[i])
        start, end = _residue_range(ranges[i])
        usi = (
            mint(dataset_id, deposited, scan, parsed.proforma, charge)
            if deposited and scan is not None and charge is not None and parsed.proforma
            else None
        )
        rows.append(
            {
                "psm_id": f"{run_id}:{scan}:{rank}",
                "run_id": run_id,
                "scan": scan,
                "usi": usi,
                "peptidoform": parsed.proforma,
                "base_sequence": parsed.base_sequence,
                "precursor_charge": charge,
                "precursor_mz": _float((columns.get("precursor_mz") or [None] * n)[i]),
                "retention_time_min": _float((columns.get("retention_time") or [None] * n)[i]),
                "score": _float((columns.get("score") or [None] * n)[i]),
                "delta_score": _float((columns.get("delta_score") or [None] * n)[i]),
                "q_value": _float((columns.get("q_value") or [None] * n)[i]),
                "q_value_notch": _float((columns.get("q_value_notch") or [None] * n)[i]),
                # Verbatim, not _first(): the whole point of this column is to carry the
                # unresolved candidates that notch_ambiguous is derived from.
                "notch": _verbatim((columns.get("notch") or [None] * n)[i]),
                "notch_ambiguous": notch_ambiguous((columns.get("notch") or [None] * n)[i]),
                "pep": _float((columns.get("pep") or [None] * n)[i]),
                "pep_q_value": _float((columns.get("pep_q_value") or [None] * n)[i]),
                "mass_error_ppm": _float((columns.get("mass_diff_ppm") or [None] * n)[i]),
                "target_decoy": _target_decoy((columns.get("decoy_contam_target") or [None] * n)[i]),
                "protein_accessions": _accessions(accession[i]),
                "ambiguity_level": _first((columns.get("ambiguity_level") or [None] * n)[i]) or None,
                "localization_score": None,
                "search": search,
                "missed_cleavages": _int((columns.get("missed_cleavage") or [None] * n)[i]),
                "nonspecific_termini": None,
                "start_residue": start,
                "end_residue": end,
                # pyMzLib excludes the matched-ion fields from its column projection because they
                # are composite; asked for as DATAREPO-13 rather than re-parsed here.
                "matched_ion_series": None,
                "matched_ion_count": None,
            }
        )
    return rows


#: MetaMorpheus prefixes the accessions of its reversed decoy entries.
DECOY_PREFIX = "DECOY_"


def _source_db(accession: str, contaminant: bool) -> str:
    """Where an accession came from.

    Decoy entries are kept -- PSM rows point at them and FDR cannot be recomputed without them --
    but they are not UniProt entries and must not be counted as proteins that were observed.
    """
    if accession.upper().startswith(DECOY_PREFIX):
        return "decoy"
    return "contaminants" if contaminant else "uniprot"


def protein_rows(
    columns_list: Sequence[dict[str, list[Any]]], dataset_id: str, *, organism: str | None
) -> list[dict[str, Any]]:
    """Build Protein rows from the accession/name/gene columns of the identification files.

    Contaminant entries are flagged from the target/decoy column and given their own `source_db`,
    so a query can exclude them without a name-prefix heuristic.
    """
    out: dict[str, dict[str, Any]] = {}
    for columns in columns_list:
        n = len(columns.get("accession", ()))
        accessions = columns.get("accession") or []
        names = columns.get("name") or [""] * n
        genes = columns.get("gene_name") or [""] * n
        organisms = columns.get("organism_name") or [""] * n
        status = columns.get("decoy_contam_target") or [""] * n
        for i in range(n):
            contaminant = _target_decoy(status[i]) == "contaminant"
            gene_parts = str(genes[i] or "").split("|")
            organism_parts = str(organisms[i] or "").split("|")
            for j, acc in enumerate(_accessions(accessions[i])):
                if acc in out:
                    continue
                gene = gene_parts[j] if j < len(gene_parts) else ""
                # MetaMorpheus writes `primary:TUBA1B, synonym:TUBA3`; the primary name is enough.
                primary = gene.split(",")[0].replace("primary:", "").strip() or None
                organism_name = (organism_parts[j] if j < len(organism_parts) else "").strip()
                out[acc] = {
                    "protein_accession": acc,
                    "canonical_accession": acc.split("-")[0] if "-" in acc else acc,
                    "gene": primary,
                    "organism": organism if organism else None,
                    "length": None,
                    "source_db": _source_db(acc, contaminant),
                    "uniprot_release": None,
                    "is_contaminant": contaminant,
                }
                if organism_name and not out[acc]["organism"]:
                    out[acc]["organism"] = organism_name
    return [out[k] for k in sorted(out)]


def add_group_proteins(
    proteins: list[dict[str, Any]],
    protein_groups: Sequence[dict[str, Any]],
    *,
    organism: str | None,
) -> list[dict[str, Any]]:
    """Add any accession that appears only in the protein-group table.

    The producer's quantification can report a group whose peptides are all below the PSM table's
    threshold, or a decoy group whose members never matched a spectrum. Those accessions still need
    a Protein row, or the group's `protein_accessions` point at nothing.
    """
    known = {row["protein_accession"] for row in proteins}
    for group in protein_groups:
        genes = list(group.get("genes") or [])
        contaminant = group.get("target_decoy") == "contaminant"
        for j, acc in enumerate(group.get("protein_accessions") or []):
            if acc in known:
                continue
            known.add(acc)
            proteins.append(
                {
                    "protein_accession": acc,
                    "canonical_accession": acc.split("-")[0] if "-" in acc else acc,
                    "gene": genes[j] if j < len(genes) else None,
                    "organism": organism,
                    "length": None,
                    "source_db": _source_db(acc, contaminant),
                    "uniprot_release": None,
                    "is_contaminant": contaminant,
                }
            )
    proteins.sort(key=lambda row: row["protein_accession"])
    return proteins


def peptidoform_rows(
    columns: dict[str, list[Any]],
    dataset_id: str,
    *,
    proforma: ProformaCache,
    psm_counts: dict[str, int],
    protein_groups: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build Peptidoform rows from `AllPeptides.psmtsv`, the producer's peptide-level FDR output.

    Args:
        protein_groups: the group IDs that actually exist in this bundle. A peptidoform is linked
            to a group only when its accession set *is* one of them: protein grouping is the
            producer's parsimony result, not something to re-derive from a peptide's accessions,
            and a link invented here would dangle.
    """
    n = len(columns.get("full_sequence", ()))
    full = columns.get("full_sequence", [])
    accession = _column(columns, "accession", "protein_accession") or [""] * n
    out: dict[str, dict[str, Any]] = {}
    for i in range(n):
        parsed = proforma(_first(full[i]))
        if not parsed.proforma:
            continue
        pid = f"{dataset_id}:{parsed.proforma}"
        accessions = _accessions(accession[i])
        q = _float((columns.get("q_value") or [None] * n)[i])
        q_notch = _float((columns.get("q_value_notch") or [None] * n)[i])
        pep = _float((columns.get("pep") or [None] * n)[i])
        status = _target_decoy((columns.get("decoy_contam_target") or [None] * n)[i])
        row = out.get(pid)
        if row is None:
            out[pid] = {
                "peptidoform_id": pid,
                "dataset_id": dataset_id,
                "peptidoform": parsed.proforma,
                "base_sequence": parsed.base_sequence,
                "best_q_value": q,
                "best_q_value_notch": q_notch,
                "target_decoy": status,
                "best_pep": pep,
                "n_psms": psm_counts.get(parsed.proforma, 0),
                "protein_group_id": _group_id(dataset_id, accessions, protein_groups),
                "protein_accessions": accessions,
                "is_unique": len(accessions) == 1 if accessions else None,
                "is_isoform_specific": None,
            }
        else:
            if q is not None and (row["best_q_value"] is None or q < row["best_q_value"]):
                row["best_q_value"] = q
            if q_notch is not None and (
                row["best_q_value_notch"] is None or q_notch < row["best_q_value_notch"]
            ):
                row["best_q_value_notch"] = q_notch
            if pep is not None and (row["best_pep"] is None or pep < row["best_pep"]):
                row["best_pep"] = pep
            if row["target_decoy"] == "decoy" or status == "target":
                row["target_decoy"] = status if status == "target" else row["target_decoy"]
    return [out[k] for k in sorted(out)]


def ptm_site_rows(
    columns: dict[str, list[Any]],
    dataset_id: str,
    *,
    proforma: ProformaCache,
    q_threshold: float = 0.01,
) -> list[dict[str, Any]]:
    """Derive PtmSite rows from accepted, non-decoy PSMs that place a modification.

    A site is emitted when two things hold: the match is not a decoy and is at or below
    `q_threshold`, and the peptide's position in the protein is known.

    Three conditions this used to impose are gone. The first two were measured against PXD036557
    (aging 012/013); the third against PXD027318 and PXD032202 (aging 019):

    * **No UNIMOD requirement.** The site key used to end in the UNIMOD accession, so a
      modification the registry could not cross-reference could not form a key -- and the rows were
      not written as nulls, they were not written at all. The evidence survived at PSM and
      peptidoform level, where the id comes from the sequence, and vanished at site level, which is
      the table PTM stoichiometry reads. `Hydroxybutyrylation on K` in PXD027318: 43 PSMs, 10
      peptidoforms, 0 sites, and a query for it could not tell that from "never identified". The
      key now ends in the engine's own name for the modification, which is always present, and
      `modification` carries the UNIMOD accession when there is one and null when there is not.

    * **No ambiguity-level filter.** Requiring level 1 dropped 83% of the sites the producer can
      compute an occupancy for -- 181 of 217 missing sites were covered only by accepted PSMs at
      level >= 2, and level 2D alone is 3,651 accepted PSMs. `DEF-OCC-PSMS` counts every PSM
      passing the q-value threshold at PSM level with no level restriction, so a level filter here
      made `ptm_sites` unable to key the stoichiometry table. `best_ambiguity_level` records the
      lowest level that placed each site, so `WHERE best_ambiguity_level = '1'` reproduces the old
      table exactly.
    * **No target-only filter.** Occupancy is computed on the protein group, and the producer's
      group definition includes contaminants, so a contaminant group has occupancy and no "target"
      PSM. That accounted for the other 36. Contaminant sites are kept and marked rather than
      dropped: they are real measurements, and BSA and trypsin sites are used as a process control.
      Decoys are still excluded.
    * **No terminal-placement skip.** This one was a single `continue`. Every modification at a
      peptide N-terminus was dropped, so `ptm_sites` held **zero** rows for placements
      `peptidoforms` held in full -- a projection gap, not a data-loss gap, which is why it was a
      ruling (aging 024 section 4) and not an incident. Measured on the corpus after the fix (aging
      028): **2,091 terminal sites at q <= 0.01**, being 1,220 `protein_n_term` and 871
      `peptide_n_term` over 20,789 PSMs, taking `ptm_sites` from 35,615 to 38,045 with every other
      table identical row-for-row. The 239 `UNIMOD:1` rows that WERE written are all `on K`: a
      reader querying `ptm_sites` for acetylation got a lysine-only answer with nothing saying so.
      N-terminal acetylation is co-translational, among the most abundant marks in any proteome,
      and governs the N-degron pathway -- protein turnover, which is proteostasis, which is a
      hallmark this repository exists to measure.

      **`_site_type`'s initiator-methionine branch does most of the work here, measured: 958 of the
      1,220 protein N-termini sit at position 2** (aging 028). A `start == 1` rule would have
      mislabelled 79% of them as cleavage artefacts.
    """
    n = len(columns.get("full_sequence", ()))
    full = columns.get("full_sequence", [])
    accession = _column(columns, "accession", "protein_accession") or [""] * n
    ranges = columns.get("start_and_end_residues_in_parent_sequence") or [""] * n
    levels = columns.get("ambiguity_level") or [""] * n
    qs = columns.get("q_value") or [None] * n
    status = columns.get("decoy_contam_target") or [""] * n
    # The residue before the peptide, which is how the producer tells us an initiator methionine
    # was excised. Without it every co-translational N-terminal acetylation is mislabelled.
    prev_residues = _column(columns, "previous_residue", "previous_amino_acid") or [""] * n

    sites: dict[str, dict[str, Any]] = {}
    for i in range(n):
        q = _float(qs[i])
        if q is None or q > q_threshold:
            continue
        state = _target_decoy(status[i])
        if state == "decoy":
            continue
        level = str(levels[i] or "").strip() or None
        # One span per accession, paired by position. A peptide shared between proteins starts at a
        # different residue in each, so taking the first span for all of them would place the site
        # correctly in the leading protein and wrongly in every other. The file carries 3,154 such
        # PSMs in PXD036557; none is at ambiguity level 1, so the filter below is the only reason
        # this has never fired. Relaxing that filter without this pairing would put wrong positions
        # in the repository.
        starts = _residue_starts(ranges[i])
        if not starts:
            continue
        parsed = proforma(_first(full[i]))
        previous = _first(prev_residues[i])
        for mod in parsed.mods:
            name = _site_key_name(mod.name, full[i])
            terminal = mod.position == N_TERMINUS
            # A terminus is a POSITION; the thing modified there is still a residue. So a terminal
            # mod is keyed on the residue it actually sits on -- the peptide's first -- and never on
            # a sentinel. `residue` stays null only when the peptide is somehow empty.
            residue = parsed.base_sequence[:1] or None if terminal else mod.residue
            offset = 1 if terminal else mod.position
            for index, acc in enumerate(_accessions(accession[i])):
                start = starts[index] if index < len(starts) else starts[0]
                position = start + offset - 1
                site_type = _site_type(terminal, start, previous)
                suffix = "" if site_type == "residue" else f"@{site_type}"
                key = f"{dataset_id}:{acc}:{residue}{position}:{name}{suffix}"
                row = sites.get(key)
                if row is None:
                    sites[key] = {
                        "ptm_site_id": key,
                        "dataset_id": dataset_id,
                        "protein_accession": acc,
                        "position": position,
                        "residue": residue,
                        "site_type": site_type,
                        "modification": mod.unimod,
                        "modification_name": name,
                        "target_decoy": state,
                        "best_ambiguity_level": level,
                        "localization_score": None,
                        "n_psms": 1,
                        "best_q_value": q,
                    }
                else:
                    row["n_psms"] += 1
                    if q < row["best_q_value"]:
                        row["best_q_value"] = q
                    # A site seen by both a target and a contaminant PSM is a target site: the
                    # contaminant database also contains real proteins.
                    if state == "target":
                        row["target_decoy"] = "target"
                    row["best_ambiguity_level"] = _better_level(row["best_ambiguity_level"], level)
    return [sites[k] for k in sorted(sites)]


def _site_type(terminal: bool, start: int, previous_residue: str) -> str:
    """Which `SiteType` a placement is, from the producer's own coordinates.

    Only N-terminal placements are classified, because only they are distinguishable in what
    MetaMorpheus writes. A modification on a peptide's LAST residue and one on its C-terminus render
    identically in a full sequence (`...K[mod]`), and the mod file's `PP` line -- the only thing
    that could separate them -- is not parsed by `modlist`. Guessing would move existing ids for no
    evidence, so a C-terminal placement stays `residue`, which is what it has always effectively
    been. Raised to aging as DATAREPO-26.

    The initiator-methionine case is the whole reason this is not `start == 1`. Co-translational
    N-terminal acetylation follows Met excision, so the modified residue is **residue 2** and the
    peptide's previous residue is the excised `M`. Both of the fixture's protein N-terminal
    acetylations are of this shape (`[UniProt:N-acetylalanine on A]AAAGG...`, span `[2 to 16]`,
    previous residue `M`), and a naive rule would label the most abundant terminal chemistry in the
    proteome `peptide_n_term`.
    """
    if not terminal:
        return "residue"
    if start == 1:
        return "protein_n_term"
    if start == 2 and previous_residue.strip().upper() == "M":
        return "protein_n_term"
    return "peptide_n_term"


def _site_key_name(name: str, full_sequence: str) -> str:
    """The modification name, checked for the one thing that would corrupt a site key.

    `ptm_site_id` joins its components with ':', so a name containing one would make the key
    unsplittable and could collide two different sites. Every name MetaMorpheus writes is of the
    form "<id> on <residue>" and carries none -- a colon here means the mod token did not parse and
    the whole bracket was taken as the name, so what we hold is not a modification name at all.
    That is worth stopping for: unlike a missing UNIMOD accession, it leaves us unable to say what
    the modification IS, so there is nothing honest to write.
    """
    if ":" in name:
        raise IngestError(
            f"modification name {name!r} (from full sequence {full_sequence!r}) contains ':', "
            f"which is the ptm_site_id separator. The mod token did not parse, so the name is not "
            f"trustworthy as a site key; fix the token's parsing rather than storing this row."
        )
    return name


def _group_id(dataset_id: str, accessions: list[str], groups: set[str] | None) -> str | None:
    """The protein group this peptide's accession set names, if the producer built that group."""
    if not accessions:
        return None
    candidate = f"{dataset_id}:{';'.join(sorted(accessions))}"
    if groups is None:
        return candidate
    return candidate if candidate in groups else None


def psm_counts_by_peptidoform(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """How many PSMs support each peptidoform, for `Peptidoform.n_psms`."""
    counts: dict[str, int] = {}
    for row in rows:
        key = row.get("peptidoform")
        if key:
            counts[key] = counts.get(key, 0) + 1
    return counts


#: MetaMorpheus accepts a match on BOTH its q-value and its notch q-value, which is why a count
#: filtered on `q_value` alone does not reproduce the number in its own results.txt. Confirmed
#: against PXD036557: this predicate reproduces the peptide and protein-group totals exactly and
#: the PSM total to within 12 of 26,582. The residual is aging's to define (DATAREPO-14).
PRODUCER_THRESHOLD = 0.01

#: A search that cannot settle on one notch reports its candidates separated by this.
NOTCH_SEPARATOR = "|"


def notch_ambiguous(raw: Any) -> bool | None:
    """Did the notch fail to resolve to a single value?

    Returns None when the producer reported no notch at all, which is not the same as a notch that
    resolved: absence is NA here as everywhere else.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    return None if not text else NOTCH_SEPARATOR in text


def producer_counts(columns: dict[str, list[Any]], threshold: float = PRODUCER_THRESHOLD) -> int:
    """Count target matches the way the producing search engine counts them.

    Applies MetaMorpheus's own acceptance rule -- target, `q_value <= threshold` **and**
    `q_value_notch <= threshold`, **and** a notch that actually resolved -- so the bundle can be
    compared with the producer's summary without the caller having to know the rule.

    The notch clause is the one that is not guessable, and it is worth 12 PSMs out of 26,594 on
    PXD036557. aging supplied it in thread 008 as the predicate behind `aging DEF-PSM-1PCT v1`: a
    match whose notch never resolved is not counted even though both its q-values pass. It costs
    nothing on peptidoforms, where no accepted row is ambiguous.
    """
    n = len(columns.get("q_value", ()))
    qs = columns.get("q_value") or []
    notches = columns.get("q_value_notch") or [None] * n
    raw_notches = columns.get("notch") or [None] * n
    status = columns.get("decoy_contam_target") or [""] * n
    total = 0
    for i in range(n):
        if str(status[i] or "").strip() != "T":
            continue
        q = _float(qs[i])
        notch = _float(notches[i])
        if q is None or q > threshold:
            continue
        if notch is not None and notch > threshold:
            continue
        if notch_ambiguous(raw_notches[i]):
            continue
        total += 1
    return total
