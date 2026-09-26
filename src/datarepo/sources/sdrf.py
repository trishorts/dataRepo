"""`*.sdrf.tsv` -> Sample, SampleCharacteristic and Assay rows.

The harmonized sample table is the most valuable thing the repository builds (FRAMEWORK section 1),
and it is also the thinnest: most deposited SDRFs are skeletons with `not available` where the
biology should be. So two rules hold here.

*Nothing is invented.* A curated column is filled only when the SDRF carries an ontology accession
for it; `not available` becomes a null, never a guess.

*Nothing is lost.* Every `characteristics[...]` column is also copied verbatim into
SampleCharacteristic, so a column this ingester does not yet understand is still in the bundle and
still queryable.

Age is deliberately absent. It is a study-layer column (`schema/study/aging.yaml`), and normalizing
"P60D" or "60-65" into years belongs to sdrf/mzLib, not here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..readers import ReaderLog, read_sdrf
from ..usi import strip_pipeline_suffix

#: Values SDRF writers use to mean "absent". They become nulls, not strings.
NOT_AVAILABLE = {"", "not available", "not applicable", "na", "n/a", "unknown", "none"}

#: Enough of the organism axis to read the datasets in scope (D5: human and rodent).
ORGANISM_TAXA = {
    "homo sapiens": "NCBITaxon:9606",
    "mus musculus": "NCBITaxon:10090",
    "rattus norvegicus": "NCBITaxon:10116",
}

#: PATO terms for the sex axis.
SEX_TERMS = {"male": "PATO:0000384", "female": "PATO:0000383"}

_COLUMN = re.compile(r"^(?P<kind>characteristics|comment|factor value)\[(?P<name>.+)\]$", re.IGNORECASE)


def parse_value(raw: str) -> dict[str, str]:
    """Split an SDRF `NT=...;AC=...;TA=...` cell into its parts.

    A plain value comes back as `{"NT": value}`, so callers can treat every cell the same way.
    """
    raw = (raw or "").strip()
    if "=" not in raw:
        return {"NT": raw}
    parts: dict[str, str] = {}
    for piece in raw.split(";"):
        key, sep, value = piece.partition("=")
        if sep:
            parts[key.strip().upper()] = value.strip()
        elif piece.strip() and "NT" not in parts:
            parts["NT"] = piece.strip()
    return parts or {"NT": raw}


def _clean(raw: str) -> str | None:
    value = (raw or "").strip()
    return None if value.lower() in NOT_AVAILABLE else value


def _term(raw: str) -> str | None:
    parts = parse_value(raw)
    accession = parts.get("AC")
    return accession if accession and accession.lower() not in NOT_AVAILABLE else None


def _name(raw: str) -> str | None:
    return _clean(parse_value(raw).get("NT", ""))


@dataclass
class SdrfTable:
    """A parsed SDRF: the rows the schema wants, plus the run-level facts it carries."""

    samples: list[dict[str, Any]]
    characteristics: list[dict[str, Any]]
    assays: list[dict[str, Any]]
    run_facts: dict[str, dict[str, Any]]
    """Deposited run base name -> instrument, fraction and technical replicate."""
    sample_of_run: dict[str, str]
    """Deposited run base name -> sample_id."""
    columns: tuple[str, ...]


def parse(
    path: Path, dataset_id: str, *, default_organism: str | None = None, log: ReaderLog | None = None
) -> SdrfTable:
    """Read one SDRF into schema rows.

    Args:
        path: the deposited (or repaired) SDRF.
        dataset_id: ProteomeXchange accession, which prefixes every generated ID.
        default_organism: NCBITaxon CURIE from the ingest manifest, used when the SDRF names an
            organism this module has no term for.
        log: reader log to record the backend in.
    """
    header, rows = read_sdrf(path, log)
    samples: dict[str, dict[str, Any]] = {}
    characteristics: list[dict[str, Any]] = []
    assays: list[dict[str, Any]] = []
    run_facts: dict[str, dict[str, Any]] = {}
    sample_of_run: dict[str, str] = {}

    for cells in rows:
        # An SDRF column name is a POSITION, not a key: `comment[modification parameters]` can
        # appear many times in one file, and a name-keyed map keeps only the last. Lookups below
        # use the map, because no column they read repeats; copying characteristics verbatim walks
        # the pairs, so a repeated one is not silently dropped.
        padded = list(cells) + [""] * max(0, len(header) - len(cells))
        pairs = list(zip(header, padded))
        row = dict(pairs)
        source_name = (row.get("source name") or "").strip()
        if not source_name:
            continue
        sample_id = f"{dataset_id}:{source_name}"

        if sample_id not in samples:
            organism_name = _name(row.get("characteristics[organism]", "")) or ""
            organism = (
                _term(row.get("characteristics[organism]", ""))
                or ORGANISM_TAXA.get(organism_name.lower())
                or default_organism
            )
            sex_name = (_name(row.get("characteristics[sex]", "")) or "").lower()
            replicate = _clean(row.get("characteristics[biological replicate]", ""))
            samples[sample_id] = {
                "sample_id": sample_id,
                "dataset_id": dataset_id,
                "source_name": source_name,
                "organism": organism,
                "sex": _term(row.get("characteristics[sex]", "")) or SEX_TERMS.get(sex_name),
                "organism_part": _term(row.get("characteristics[organism part]", "")),
                "cell_type": _term(row.get("characteristics[cell type]", "")),
                "disease": _term(row.get("characteristics[disease]", "")),
                "condition": _name(row.get("characteristics[disease]", "")),
                "material_type": _name(row.get("material type", ""))
                or _name(row.get("characteristics[material type]", "")),
                "cell_line": _name(row.get("characteristics[cell line]", "")),
                "individual_id": _name(row.get("characteristics[individual]", "")),
                "biological_replicate": int(replicate) if replicate and replicate.isdigit() else None,
                "timepoint": _name(row.get("characteristics[time]", "")),
            }
            default_source = _clean(row.get("comment[characteristics source]", ""))
            for column, raw in pairs:
                m = _COLUMN.match(column.strip())
                if not m or m.group("kind").lower() == "comment":
                    continue
                written = (raw or "").strip()
                if not written:
                    continue  # an empty cell says nothing, not even "not available"
                inner = m.group("name").strip()
                # A reserved word is kept, flagged: `not available` is an answer to a question
                # that was asked, and dropping it made it look like one never asked (G42).
                characteristics.append({
                    "sample_id": sample_id,
                    "name": column.strip(),
                    "value": written,
                    "value_reserved": _clean(written) is None,
                    "term": _term(raw),
                    # sdrf's D31 grain: a column's own `comment[<name> source]` overrides the row's
                    # `comment[characteristics source]`. Neither present means NULL, never
                    # `deposited`: nothing in the file says so (G62).
                    "source": _clean(row.get(f"comment[{inner} source]", "")) or default_source,
                    "source_reference": _clean(row.get(f"comment[{inner} source reference]", "")),
                    "source_method": _clean(row.get(f"comment[{inner} source method]", "")),
                })

        data_file = _clean(row.get("comment[data file]", "")) or _clean(row.get("assay name", ""))
        if not data_file:
            continue
        # An SDRF MetaMorpheus writes names the file it SEARCHED, which after Calibrate is
        # `X-calib.mzML`, not the deposited `X.raw` (sdrf D40, aging 069 DATAREPO-54). Runs are keyed
        # on the deposited name, so without the same stripping the USI path does, that run would
        # silently get no sample, instrument or fraction.
        run_name = strip_pipeline_suffix(Path(data_file).stem)
        sample_of_run[run_name] = sample_id
        fraction = _clean(row.get("comment[fraction identifier]", ""))
        technical = _clean(row.get("comment[technical replicate]", ""))
        run_facts[run_name] = {
            "instrument_model": _name(row.get("comment[instrument]", "")),
            "instrument_term": _term(row.get("comment[instrument]", "")),
            "fraction": int(fraction) if fraction and fraction.isdigit() else None,
            "technical_replicate": int(technical) if technical and technical.isdigit() else None,
            # SDRF-DR10: a drafted `1` is a default nothing established, so where it came from is
            # carried beside it. NULL until the SDRF writes the column.
            "fraction_source": _clean(row.get("comment[fraction identifier source]", "")),
            "technical_replicate_source": _clean(row.get("comment[technical replicate source]", "")),
            "acquisition": _name(row.get("comment[proteomics data acquisition method]", "")),
        }
        channel = _channel(row.get("comment[label]", ""))
        assays.append(
            {
                "assay_id": f"{dataset_id}:{run_name}:{channel}",
                "run_id": f"{dataset_id}:{run_name}",
                "channel": channel,
                "sample_id": sample_id,
            }
        )

    return SdrfTable(
        samples=list(samples.values()),
        characteristics=characteristics,
        assays=assays,
        run_facts=run_facts,
        sample_of_run=sample_of_run,
        columns=tuple(header),
    )


def _channel(raw: str) -> str:
    """Assay channel from the SDRF label comment: `label_free`, or the reporter channel."""
    name = _name(raw) or ""
    if not name or "label free" in name.lower() or name.lower() == "none":
        return "label_free"
    return name.replace(" ", "")
