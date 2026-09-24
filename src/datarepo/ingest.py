"""`datarepo ingest`: one dataset's pipeline output -> one immutable Parquet bundle.

The order of work is the order of trust. The manifest decides whether the dataset may be ingested
at all; the provenance decides how its numbers should be read; only then are the result files
parsed. Nothing is inferred from directory names, and nothing the producer marked unfit is loaded.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import definitions as defs
from ._tables import SCHEMA_VERSION
from .bundle import BundleWriter, sha256_file
from .errors import DatasetExcluded, IngestError
from .manifest import DatasetEntry, Manifest, load_manifest
from .modlist import ModRegistry
from .proforma import ProformaCache
from .readers import ReaderLog, read_psmtsv, read_results_txt
from .integrity import Collapse, collapse_exact_duplicates
from .reconcile import build as build_checks
from .reconcile import finding_rows as reconciliation_findings
from .reconcile import metric_conflicts
from .sources import identifications, provenance as prov, quant, runs as runs_source, sdrf as sdrf_source
from .sources import protein_db, search_params
from .usi import RunNameMap

#: Manifest `quant_method` spellings mapped onto the schema's enum.
QUANT_METHODS = {
    "label-free": "label_free",
    "label free": "label_free",
    "labelfree": "label_free",
    "lfq": "label_free",
    "tmt": "isobaric",
    "itraq": "isobaric",
    "silac": "metabolic",
}

#: Enough instrument-name to vendor mapping for the instruments in scope.
VENDORS = (
    (("q exactive", "orbitrap", "lumos", "eclipse", "astral", "exploris", "velos", "elite", "ltq"), "Thermo"),
    (("timstof", "maxis", "impact"), "Bruker"),
    (("triple tof", "tripletof", "qtrap", "zenotof"), "SCIEX"),
    (("synapt", "xevo"), "Waters"),
)


@dataclass
class IngestResult:
    """What one ingest produced, for the CLI and for tests."""

    dataset_id: str
    bundle_path: Path
    bundle_id: str
    row_counts: dict[str, int]
    checks: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    unresolved_modifications: dict[str, int] = field(default_factory=dict)
    unmatched_runs: dict[str, int] = field(default_factory=dict)
    skipped: bool = False
    """True when the bundle already existed unchanged, so nothing was rewritten."""

    @property
    def mismatches(self) -> list[dict[str, Any]]:
        return [c for c in self.checks if not c["ok"]]


def _vendor(instruments: list[str]) -> str | None:
    for name in instruments:
        lowered = name.lower()
        for needles, vendor in VENDORS:
            if any(needle in lowered for needle in needles):
                return vendor
    return None


def _find(run_dir: Path, *relative: str) -> Path | None:
    for rel in relative:
        candidate = run_dir / rel
        if candidate.is_file():
            return candidate
    return None


def _lineage(
    work_root: Path, search_provenance_path: Path, search_provenance: dict[str, Any]
) -> tuple[list[Path], list[dict[str, Any]]]:
    """The search stage's provenance and every stage it declares upstream of itself.

    Globbing the run folder for `provenance.json` would be wrong: a run folder can hold more than
    one search of the same data (`04_search` beside `04_search_mm1111`), and only one of them is
    the canonical run the manifest names. The provenance's own `upstream[]` is the authoritative
    lineage, so the bundle records exactly the stages that produced it.

    **An upstream file is read only if it is still the file the search recorded** (0.19.0). Each
    `upstream[]` entry carries the sha256 the file had when the search ran, and until 0.19.0 that
    was never checked. aging's `db/provenance.json` is ONE shared file that every database
    preparation overwrites, so 33 of the 38 searches on their disk pointed at a record of some later
    preparation -- a mouse dataset's bundle carried the record of a human isoform database made
    three days after its search, and re-ingesting unchanged search output moved its bundle id. A
    file whose sha256 no longer matches is left out and reported, never read as this search's.

    Returns:
        `(paths to read, mismatches)`, each mismatch `{stage, path, recorded, actual}`.
    """
    paths = [search_provenance_path]
    mismatches: list[dict[str, Any]] = []
    for entry in search_provenance.get("upstream") or []:
        candidate = work_root / str(entry.get("path", ""))
        if not candidate.is_file() or candidate in paths:
            continue
        recorded = entry.get("sha256")
        if recorded:
            actual = sha256_file(candidate)
            if actual != recorded:
                mismatches.append(
                    {"stage": entry.get("stage"), "path": str(entry.get("path")), "recorded": recorded, "actual": actual}
                )
                continue
        paths.append(candidate)
    return paths, mismatches


def _task_files(work_root: Path, search_provenance: dict[str, Any]) -> list[Path]:
    """The MetaMorpheus task `.toml` files the run actually executed.

    A MetaMorpheus `tasks/` folder also holds the shipped templates for tasks that did not run
    (`GlycoSearchTask.toml`, `XLSearchTask.toml`). Reading those would put modifications into
    `search_modifications_declared` that this search never declared, which is the opposite of
    the point.
    """
    out = []
    for entry in search_provenance.get("inputs") or []:
        path = str(entry.get("path", ""))
        if path.lower().endswith("task.toml"):
            candidate = work_root / path
            if candidate.is_file():
                out.append(candidate)
    return out


def ingest_dataset(
    manifest: Manifest,
    entry: DatasetEntry,
    *,
    store: Path | None = None,
    mm_settings: Path | None = None,
    overwrite: bool = False,
) -> IngestResult:
    """Build the bundle for one dataset.

    Args:
        manifest: the producing instance's manifest.
        entry: the dataset's entry, already checked as ingestable.
        store: where to write; defaults to the manifest's store.
        mm_settings: the MetaMorpheus install that did the search, for the modification registry.
            Defaults to `<work_root>/mm_settings/<version from the manifest>`.
        overwrite: rebuild a bundle that already exists at the same content hash.

    Raises:
        DatasetExcluded: the manifest does not mark the dataset `include`.
        IngestError: a file the ingest cannot do without is missing.
        UnsupportedProvenance: the run's provenance schema cannot be mapped safely.
    """
    # The refusal lives here, not only in the CLI: loading a run the producer marked unfit is the
    # one thing this function must never do, however it is called.
    if not entry.ingestable:
        raise DatasetExcluded(
            f"{entry.accession} has status '{entry.status}' in {manifest.path} and will not be "
            f"ingested. The producer's reason: {(entry.reason or 'no reason given').strip()}"
        )

    dataset_id = entry.accession
    run_dir = manifest.run_dir(entry)
    if not run_dir.is_dir():
        raise IngestError(f"{dataset_id}: run folder {run_dir} does not exist")

    search_dir = manifest.stage_dir(entry, "search")
    if search_dir is None or not search_dir.is_dir():
        raise IngestError(f"{dataset_id}: the manifest's search stage folder is missing ({search_dir})")
    results_dir = manifest.search_results_dir(entry)
    if not results_dir.is_dir():
        raise IngestError(f"{dataset_id}: search results folder {results_dir} does not exist")

    writer = BundleWriter(store=store or manifest.store, dataset_id=dataset_id)

    # The manifest entry is an input like any other: it supplies the title and the D5 axes that the
    # `datasets` row is built from, so it belongs in the content hash (aging 013 added a title and
    # the id did not move, which is how this was found). Only the fields that shape content are
    # hashed, never the producer's prose -- see manifest.CONTENT_FIELDS for the classification and
    # aging 019 section 1 for why an id that moves when a `reason` is reworded is the wrong id.
    writer.add_declaration("manifest_entry", entry.content_declaration())
    log = ReaderLog()

    # --- provenance first: it tells us how to read every number that follows -------------------
    search_provenance_path = search_dir / "provenance.json"
    if not search_provenance_path.is_file():
        raise IngestError(f"{dataset_id}: no provenance.json in {search_dir}")
    search_provenance = prov.load(search_provenance_path)
    provenance_version = prov.schema_version(search_provenance)

    provenance_rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    lineage, lineage_mismatches = _lineage(manifest.work_root, search_provenance_path, search_provenance)
    findings += _lineage_findings(lineage_mismatches, dataset_id)
    for path in lineage:
        doc = prov.load(path)
        stage_name = path.parent.name
        source = writer.add_source(path, f"provenance:{stage_name}", copy_as=f"provenance_{stage_name}.json")
        provenance_rows.append(
            prov.record_row(
                doc,
                dataset_id,
                stage_dir_name=stage_name,
                bundle_path=source["bundle_path"],
                sha256=source["sha256"],
            )
        )
        if path == search_provenance_path:
            findings += prov.finding_rows(doc, dataset_id, f"provenance.json flags ({stage_name})")

    metrics = prov.metric_rows(search_provenance, dataset_id, provenance_version)

    # --- the modification registry from the build that did the search --------------------------
    settings = mm_settings
    if settings is None and entry.metamorpheus:
        settings = manifest.work_root / "mm_settings" / entry.metamorpheus
    registry = ModRegistry.from_metamorpheus(settings) if settings else ModRegistry()
    proforma = ProformaCache(registry)

    # --- samples and runs ----------------------------------------------------------------------
    fetch_path = next(iter(sorted(run_dir.glob("*/fetch_manifest.json"))), None)
    fetch = runs_source.load_fetch_manifest(fetch_path) if fetch_path else None
    if fetch_path:
        writer.add_source(fetch_path, "fetch_manifest")

    qc_dir = manifest.stage_dir(entry, "qc")
    qc_path = _find(qc_dir, "qc_report.json") if qc_dir else None
    qc = runs_source.load_qc_report(qc_path) if qc_path else None
    if qc_path:
        writer.add_source(qc_path, "qc_report", copy_as="qc_report.json")

    sdrf_path = next(iter(sorted(run_dir.glob("*/metadata/*.sdrf.tsv"))), None)
    if sdrf_path:
        writer.add_source(sdrf_path, "sdrf", copy_as=sdrf_path.name)
        sdrf = sdrf_source.parse(sdrf_path, dataset_id, default_organism=entry.organism, log=log)
    else:
        sdrf = sdrf_source.SdrfTable([], [], [], {}, {}, ())

    run_rows, run_metrics = runs_source.build(
        dataset_id, fetch=fetch, qc=qc, run_facts=sdrf.run_facts
    )
    if not run_rows:
        raise IngestError(
            f"{dataset_id}: no runs found. Neither a fetch manifest nor a QC report was readable "
            f"under {run_dir}, so there is nothing to attach measurements to."
        )
    metrics += run_metrics
    enrichment_mixed = runs_source.assign_enrichment(
        run_rows,
        dataset_id,
        declared=entry.enrichment,
        mixed=entry.mixed_enrichment,
        run_enrichment=entry.run_enrichment,
    )

    samples = list(sdrf.samples)
    assays = list(sdrf.assays)
    if not samples:
        # No SDRF at all: one synthetic sample per run, clearly flagged, so quantities still have
        # something to hang on. Nothing biological is invented, only the identity of the sample.
        for run in run_rows:
            base = Path(run["file_name"]).stem
            sample_id = f"{dataset_id}:{base}"
            samples.append(
                {
                    "sample_id": sample_id,
                    "dataset_id": dataset_id,
                    "source_name": base,
                    "organism": entry.organism,
                }
            )
            assays.append(
                {
                    "assay_id": f"{dataset_id}:{base}:label_free",
                    "run_id": run["run_id"],
                    "channel": "label_free",
                    "sample_id": sample_id,
                }
            )
        findings.append(
            {
                "finding_id": f"{dataset_id}:no_sdrf",
                "dataset_id": dataset_id,
                "run_id": None,
                "code": "no_sdrf",
                "severity": "warning",
                "status": "open",
                "message": (
                    "No SDRF was found for this dataset, so each run was given a synthetic sample "
                    "of its own. There is no sample metadata: treat every sample as unannotated."
                ),
                "source": "datarepo ingest",
            }
        )
    elif not any(
        s.get(column) for s in samples for column in ("organism_part", "cell_type", "disease", "individual_id")
    ) and (uncoded := _uncoded_annotation(sdrf.characteristics)):
        # The curated columns want an ontology term; an SDRF that writes `Blood serum` with no term
        # leaves them empty while the text sits in sample_characteristics. Calling that "absent" was
        # false for PXD010115 and PXD034432 -- found by an agent reading both tables (0.18.0).
        findings.append(
            {
                "finding_id": f"{dataset_id}:sdrf_uncoded",
                "dataset_id": dataset_id,
                "run_id": None,
                "code": "sdrf_uncoded",
                "severity": "warning",
                "status": "open",
                "message": (
                    "The deposited SDRF describes its samples only as text with no ontology term, so "
                    "the curated organism part, cell type, disease and individual columns are empty. "
                    f"The text is in sample_characteristics: {uncoded}. Match on it as text; it has "
                    "not been mapped to a term."
                ),
                "source": "datarepo ingest",
            }
        )
    elif not any(
        s.get(column) for s in samples for column in ("organism_part", "cell_type", "disease", "individual_id")
    ):
        findings.append(
            {
                "finding_id": f"{dataset_id}:sdrf_skeleton",
                "dataset_id": dataset_id,
                "run_id": None,
                "code": "sdrf_skeleton",
                "severity": "warning",
                "status": "open",
                "message": (
                    "The deposited SDRF carries no biological annotation: organism part, cell "
                    "type, disease and individual are all absent. Sample-level questions cannot "
                    "be answered for this dataset until it is curated."
                ),
                "source": "datarepo ingest",
            }
        )

    run_names = RunNameMap(tuple(Path(r["file_name"]).stem for r in run_rows))

    # --- identifications -----------------------------------------------------------------------
    all_psms_path = results_dir / "AllPSMs.psmtsv"
    all_peptides_path = results_dir / "AllPeptides.psmtsv"
    if not all_psms_path.is_file():
        raise IngestError(f"{dataset_id}: no AllPSMs.psmtsv in {results_dir}")
    writer.add_source(all_psms_path, "psms")

    protein_groups: list[dict[str, Any]] = []
    protein_group_count = 0
    protein_group_quant: list[dict[str, Any]] = []
    pg_path = results_dir / "AllQuantifiedProteinGroups.tsv"
    if pg_path.is_file():
        writer.add_source(pg_path, "protein_group_quant")
        protein_groups, protein_group_quant, protein_group_count = quant.protein_group_rows(
            pg_path, dataset_id, run_names=run_names, log=log
        )

    searches = [t.lower() for t in search_params.task_names(search_provenance)]
    search_label = "gptmd" if "gptmd" in searches else "standard"

    psm_columns = read_psmtsv(all_psms_path, log)
    psm_rows = identifications.psm_rows(
        psm_columns, dataset_id, proforma=proforma, run_names=run_names, search=search_label
    )
    # Sites are placed by finding each peptide in the searched proteins, because the producer's
    # spans cannot be paired with its accessions (aging 043, DATAREPO-32). The databases are inputs
    # to every ptm_sites row, so they are in the content hash; they are not copied.
    sequences = protein_db.load(search_provenance, manifest.work_root)
    for db in sequences.files:
        # Role carries the file name: `bundle_id` orders sources by (role, path), and a path is
        # absolute and site-specific, so two databases under one role could hash in a different
        # order on another machine.
        writer.add_hashed_source(Path(db["path"]), f"protein_database:{Path(db['path']).name}", db["sha256"])
    unplaced: dict[str, int] = {}
    ptm_sites = identifications.ptm_site_rows(
        psm_columns, dataset_id, proforma=proforma, sequences=sequences, unplaced=unplaced
    )
    site_check = identifications.verify_site_residues(ptm_sites, sequences)

    peptide_columns: dict[str, list[Any]] = {}
    if all_peptides_path.is_file():
        writer.add_source(all_peptides_path, "peptides")
        peptide_columns = read_psmtsv(all_peptides_path, log)
    peptidoforms = identifications.peptidoform_rows(
        peptide_columns or psm_columns,
        dataset_id,
        proforma=proforma,
        psm_counts=identifications.psm_counts_by_peptidoform(psm_rows),
        protein_groups={g["protein_group_id"] for g in protein_groups},
    )
    # A protein's contaminant label comes from the database it was read from, not from the PSM row
    # it shares with a contaminant (G66). An accession in BOTH a target and the contaminant database
    # is whatever the search's TCAmbiguity made it; MetaMorpheus's default drops the contaminant copy.
    tc = search_params.tc_ambiguity(_task_files(manifest.work_root, search_provenance))

    def contaminant_of(accession: str) -> bool | None:
        status = sequences.database_status(accession)
        if status == "both":
            return {"RemoveContaminant": False, "RemoveTarget": True}.get(tc or "")
        return {"contaminant": True, "target": False}.get(status or "")

    unresolved_labels: Counter = Counter()
    proteins = identifications.add_group_proteins(
        identifications.protein_rows(
            [c for c in (psm_columns, peptide_columns) if c],
            dataset_id,
            organism=entry.organism,
            contaminant_of=contaminant_of,
            unresolved=unresolved_labels,
        ),
        protein_groups,
        organism=entry.organism,
    )

    # --- quantities ----------------------------------------------------------------------------
    mbr_threshold = float((search_provenance.get("mbr") or {}).get("mbr_fdr_threshold", 0.01))
    peaks_path = results_dir / "AllQuantifiedPeaks.tsv"
    if peaks_path.is_file():
        writer.add_source(peaks_path, "peaks")
    peak_quality = quant.peak_quality(
        peaks_path, dataset_id, run_names=run_names, mbr_q_threshold=mbr_threshold, log=log
    )

    quant_values: list[dict[str, Any]] = list(protein_group_quant)
    peptide_quant_path = results_dir / "AllQuantifiedPeptides.tsv"
    if peptide_quant_path.is_file():
        writer.add_source(peptide_quant_path, "peptide_quant")
        quant_values += quant.peptide_quant_rows(
            peptide_quant_path,
            dataset_id,
            run_names=run_names,
            to_proforma=proforma,
            peak_quality_index=peak_quality,
            log=log,
        )

    # --- search parameters and reported totals -------------------------------------------------
    task_files = _task_files(manifest.work_root, search_provenance)
    for path in task_files:
        writer.add_source(path, f"task:{path.stem}", copy_as=path.name)
    search_modifications = search_params.modification_rows(task_files, dataset_id, registry)

    results_path = results_dir / "results.txt"
    results: dict[str, dict[str, int]] = {}
    if results_path.is_file():
        writer.add_source(results_path, "results_txt", copy_as="results.txt")
        results = read_results_txt(results_path, log)
        metrics += _results_metrics(results, dataset_id, run_names)
    # Emitted here rather than with the other provenance metrics because the per-run rows need the
    # deposited run names, which only exist once the runs are built (aging 014 section 3).
    metrics += prov.contamination_metric_rows(search_provenance, dataset_id, run_names=run_names)

    # --- the dataset row -------------------------------------------------------------------
    instruments = sorted({f["instrument_model"] for f in sdrf.run_facts.values() if f.get("instrument_model")})
    database_name, database_sha = search_params.searched_database(search_provenance)
    tools = search_provenance.get("tools") or {}
    engine_version = (tools.get("MetaMorpheus") or {}).get("release") or entry.metamorpheus
    pipeline = search_provenance.get("pipeline") or {}
    dataset_row = {
        "dataset_id": dataset_id,
        # The producer holds it (they fetch it from PRIDE); dataRepo does not call PRIDE itself.
        "title": entry.title,
        "organisms": [entry.organism] if entry.organism else [],
        "acquisition": entry.acquisition,
        "quant_method": QUANT_METHODS.get((entry.quant_method or "").lower(), entry.quant_method),
        "labelling": entry.labelling,
        "labelling_plex": entry.labelling_plex,
        "enrichment": list(entry.enrichment),
        "enrichment_mixed": enrichment_mixed,
        "instrument_vendor": _vendor(instruments),
        "instruments": instruments,
        # An allow-list, so an empty declaration means unrestricted and a response type invented
        # later is excluded until somebody says otherwise (aging 024 section 7).
        "permitted_responses": list(entry.permitted_responses),
        "axis_source": "provenance",
        "submission_type": None,
        "search_engine": "MetaMorpheus",
        "search_engine_version": engine_version,
        "search_database": database_name,
        "search_database_sha256": database_sha,
        "sdrf_status": "trusted" if sdrf_path else "absent",
        "pipeline_repo": pipeline.get("repo"),
        "pipeline_commit": pipeline.get("commit"),
        "searches": [search_label],
        "first_release_id": None,
        "latest_release_id": None,
    }

    # --- exact duplicates the producer wrote -----------------------------------------------------
    # MetaMorpheus can write one row twice, identical in every column (aging 015: one protein group
    # three times in PXD027318). Collapsing those is lossless by construction and it happens before
    # anything counts the rows, so every number below describes what the bundle will actually hold.
    # It also removes the duplicate's *derived* rows -- three identical group rows melt into three
    # identical quantities per run, and quant_values has no identifier to catch that.
    collapsed = collapse_exact_duplicates(
        {
            "samples": samples,
            "runs": run_rows,
            "assays": assays,
            "peptidoforms": peptidoforms,
            "protein_groups": protein_groups,
            "proteins": proteins,
            "ptm_sites": ptm_sites,
            "quant_values": quant_values,
        }
    )
    if collapsed:
        # The group count has to describe the rows, not the file: the file said one group three
        # times and the bundle holds it once.
        protein_group_count = quant.accepted_group_count(protein_groups)
        findings += _duplicate_findings(collapsed, dataset_id)

    # --- reconciliation ------------------------------------------------------------------------
    checks = build_checks(
        psm_count_1pct=identifications.producer_counts(psm_columns),
        # No notch clause here: it is a PSM rule (aging 008), and applying it to peptidoforms cost
        # exactly 3 on each of aging's two larger datasets -- making PXD032202's count_mismatch
        # finding entirely spurious against a dataset that matched perfectly. See `producer_counts`.
        peptidoform_count_1pct=identifications.producer_counts(
            peptide_columns or psm_columns, require_resolved_notch=False
        ),
        protein_group_count_1pct=protein_group_count,
        runs=run_rows,
        results=results,
        expected_files=entry.files,
        provenance_ms2=(search_provenance.get("id_rate") or {}).get("ms2"),
    )
    findings += reconciliation_findings(checks, dataset_id)
    findings += metric_conflicts(metrics, dataset_id)
    findings += _modification_findings(proforma, dataset_id)
    findings += _usi_findings(run_names, dataset_id)
    findings += _enrichment_findings(run_rows, dataset_id, enrichment_mixed)
    findings += _contaminant_label_findings(unresolved_labels, tc, dataset_id)
    findings += _unplaced_site_findings(unplaced, sequences, dataset_id)
    findings += _site_residue_findings(site_check, dataset_id)

    # --- assemble ------------------------------------------------------------------------------
    writer.add("datasets", [dataset_row])
    writer.add("samples", samples)
    writer.add("sample_characteristics", sdrf.characteristics)
    writer.add("runs", run_rows)
    writer.add("assays", assays)
    writer.add("psms", psm_rows)
    writer.add("peptidoforms", peptidoforms)
    writer.add("protein_groups", protein_groups)
    writer.add("proteins", proteins)
    writer.add("ptm_sites", ptm_sites)
    writer.add("quant_values", quant_values)
    writer.add("search_modifications_declared", search_modifications)
    writer.add("metrics", metrics)
    writer.add("provenance_records", provenance_rows)
    writer.add("findings", findings)
    # A definition is carried when something in the bundle depends on it. That is every metric and
    # quantity, plus the notch rule: `Psm.notch_ambiguous` is a stored conclusion, so the text
    # behind it has to travel with the rows rather than live only in aging's thread.
    used = {m["definition_id"] for m in metrics} | {q["definition_id"] for q in quant_values}
    if psm_rows:
        used.add(defs.NOTCH_AMBIGUOUS.definition_id)
    writer.add("definitions", defs.rows(used))

    writer.notes = {
        "instance": manifest.instance,
        "manifest": str(manifest.path),
        "run": entry.run,
        "provenance_schema": str(search_provenance.get("schema")),
        "metamorpheus": engine_version,
        "licence": manifest.licence,
        "credit": manifest.credit,
        "readers": log.entries,
        "modification_registry": {
            "source": str(settings) if settings else None,
            "entries": len(registry),
            "files": registry.sources,
            "unresolved": proforma.unresolved,
        },
        "protein_databases": {
            "read": sequences.files,
            "missing": sequences.missing,
            "unplaced_site_pairs": unplaced,
            "site_residue_check": site_check,
        },
        "reconciliation": [c.as_dict() for c in checks],
        "collapsed_duplicates": [c.as_dict() for c in collapsed],
    }

    # Re-ingesting unchanged inputs with unchanged code is a no-op, not an error: the pipeline
    # that calls this runs it again after every stage, and it should be safe to do so.
    existing = writer.path() / "bundle.json"
    skipped = existing.is_file() and not overwrite
    out = writer.path() if skipped else writer.write(overwrite=overwrite)
    manifest_doc = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
    return IngestResult(
        dataset_id=dataset_id,
        bundle_path=out,
        bundle_id=writer.bundle_id,
        row_counts=manifest_doc["tables"],
        checks=[c.as_dict() for c in checks],
        findings=findings,
        unresolved_modifications=dict(proforma.unresolved),
        unmatched_runs=dict(run_names.unmatched),
        skipped=skipped,
    )


def _results_metrics(
    results: dict[str, dict[str, int]], dataset_id: str, run_names: RunNameMap
) -> list[dict[str, Any]]:
    """Metric rows for every total MetaMorpheus's results.txt reports."""
    definition_for = {
        "psms": defs.PSM_1PCT.definition_id,
        "peptides": defs.PEPTIDE_COUNT_1PCT.definition_id,
        "protein_groups": defs.PROTEIN_GROUP_COUNT_1PCT.definition_id,
        "ms2_scans": defs.MS2_COUNT.definition_id,
        "precursors": defs.PRECURSOR_COUNT.definition_id,
    }
    rows = []
    for scope, counts in results.items():
        if scope:
            resolved = run_names.resolve(scope)
            if resolved is None:
                continue
            scope_kind, scope_id = "run", f"{dataset_id}:{resolved}"
        else:
            scope_kind, scope_id = "dataset", dataset_id
        for name, value in counts.items():
            definition = definition_for.get(name)
            if definition is None:
                continue
            rows.append(
                {
                    "scope": scope_kind,
                    "scope_id": scope_id,
                    "name": name if name != "psms" else "psms_1pct",
                    "value": value,
                    "definition_id": definition,
                    "source": "results.txt",
                }
            )
    return rows


def _duplicate_findings(collapsed: list[Collapse], dataset_id: str) -> list[dict[str, Any]]:
    """One Finding naming every row the producer wrote more than once.

    The collapse is lossless, so this is not a warning about the bundle -- it is a fact about the
    producer's output that would otherwise vanish the moment it was repaired. Someone reading the
    bundle should be able to see that a row arrived twice without diffing it against the TSV.
    """
    if not collapsed:
        return []
    per_table: dict[str, list[Collapse]] = {}
    for c in collapsed:
        per_table.setdefault(c.table, []).append(c)
    parts = []
    for table in sorted(per_table):
        group = per_table[table]
        dropped = sum(c.dropped for c in group)
        example = group[0]
        parts.append(
            f"{table}: {len(group)} identifier(s), {dropped} row(s) dropped, "
            f"e.g. {example.identifier} written {example.written} times"
        )
    return [
        {
            "finding_id": f"{dataset_id}:collapsed_duplicate_rows",
            "dataset_id": dataset_id,
            "run_id": None,
            "code": "collapsed_duplicate_rows",
            "severity": "info",
            "status": "open",
            "message": (
                "The producer wrote some rows more than once, identical in every column, and the "
                "copies were dropped so each identifier appears once. Nothing was lost: the kept "
                "row is byte-for-byte what the duplicates said. Rows that share an identifier and "
                "disagree anywhere are still refused rather than collapsed. "
                + "; ".join(parts)
                + ". The full list is in bundle.json under collapsed_duplicates."
            ),
            "source": "datarepo ingest integrity (aging thread 015, AGING-Q2)",
        }
    ]


def _modification_findings(proforma: ProformaCache, dataset_id: str) -> list[dict[str, Any]]:
    if not proforma.unresolved:
        return []
    names = ", ".join(sorted(proforma.unresolved))
    return [
        {
            "finding_id": f"{dataset_id}:unresolved_modifications",
            "dataset_id": dataset_id,
            "run_id": None,
            "code": "unresolved_modifications",
            "severity": "warning",
            "status": "open",
            "message": (
                f"{len(proforma.unresolved)} modification(s) could not be mapped to a UNIMOD "
                f"accession or a mass, and are carried in ProForma as [Info:...] tags: {names}. "
                f"Their ptm_sites rows exist and carry modification_name, with modification null, "
                f"so a query by name finds them and a query by UNIMOD accession will not."
            ),
            "source": "datarepo ingest",
        }
    ]


def _unplaced_site_findings(
    unplaced: dict[str, int], sequences: protein_db.ProteinSequences, dataset_id: str
) -> list[dict[str, Any]]:
    """Say how many (PSM, protein) pairs got no site because their position could not be found.

    The alternative was the old behaviour: pair the producer's spans with its accessions and write
    a confident wrong position (aging 043). An unplaced site is a gap a reader can see; a misplaced
    one is a fact they will quote.
    """
    if not unplaced and not sequences.missing:
        return []
    parts = []
    if unplaced.get("no_sequence"):
        parts.append(f"{unplaced['no_sequence']} had no sequence in the searched databases")
    if unplaced.get("peptide_not_in_sequence"):
        # Measured on PXD036557: every one was a level 4/5 PSM, ambiguous between peptide
        # SEQUENCES, whose accession list mixes the proteins of all candidates. The stored
        # peptidoform is the first candidate, and these proteins carry another one.
        parts.append(
            f"{unplaced['peptide_not_in_sequence']} named a protein that does not contain the "
            f"stored peptide -- typically a PSM ambiguous between peptide sequences (level 4 or 5), "
            f"where this protein carries a different candidate than the first, which is the one "
            f"stored"
        )
    if unplaced.get("c_term_no_sequence"):
        # A single-accession PSM can be placed from its spans without a sequence, but a C-terminal
        # site also needs the protein's length to be typed (aging 045 section 2), so it is held.
        parts.append(
            f"{unplaced['c_term_no_sequence']} carried a C-terminal modification on a protein with "
            f"no sequence, so protein and peptide C-terminus could not be told apart"
        )
    if sequences.missing:
        parts.append("database(s) named by the search provenance but not on disk: " + ", ".join(sequences.missing))
    return [
        {
            "finding_id": f"{dataset_id}:unplaced_ptm_sites",
            "dataset_id": dataset_id,
            "run_id": None,
            "code": "unplaced_ptm_sites",
            "severity": "warning",
            "status": "open",
            "message": (
                "Some modifications on peptides shared between proteins were not written to "
                "ptm_sites for one or more of those proteins, because the peptide could not be "
                "located in that protein's sequence and the producer's residue spans cannot be "
                "paired with its accessions. Of the (PSM, protein) pairs affected: "
                + "; ".join(parts)
                + ". Sites on the other proteins of the same PSMs are written. Counts are in "
                "bundle.json under protein_databases."
            ),
            "source": "datarepo ingest (aging 043, DATAREPO-32)",
        }
    ]


def _site_residue_findings(check: dict[str, int], dataset_id: str) -> list[dict[str, Any]]:
    """A finding when any written site does not name the residue at its own position.

    Should never fire for a site placed by alignment, which is correct by construction. It exists
    for the span fallback and for whatever comes next -- the defect it would have caught was found
    by a consumer, from outside, after it had shipped in every bundle for days.
    """
    bad = check.get("wrong_residue", 0) + check.get("beyond_length", 0)
    if not bad:
        return []
    return [
        {
            "finding_id": f"{dataset_id}:ptm_site_residue_mismatch",
            "dataset_id": dataset_id,
            "run_id": None,
            "code": "ptm_site_residue_mismatch",
            "severity": "warning",
            "status": "open",
            "message": (
                f"{check.get('wrong_residue', 0)} ptm_sites row(s) name a residue that is not at "
                f"their position in the searched sequence, and {check.get('beyond_length', 0)} have "
                f"a position beyond the protein's length. Treat those positions as wrong. Counts "
                f"are in bundle.json under protein_databases.site_residue_check."
            ),
            "source": "datarepo ingest (DATAREPO-32 self-check)",
        }
    ]


def _lineage_findings(mismatches: list[dict[str, Any]], dataset_id: str) -> list[dict[str, Any]]:
    """One finding per upstream provenance file that changed after the search recorded it."""
    return [
        {
            "finding_id": f"{dataset_id}:upstream_provenance_changed:{m['stage']}",
            "dataset_id": dataset_id,
            "run_id": None,
            "code": "upstream_provenance_changed",
            "severity": "warning",
            "status": "open",
            "message": (
                f"The search recorded its upstream '{m['stage']}' provenance ({m['path']}) with sha256 "
                f"{m['recorded']}, and the file there now has {m['actual']}: it was overwritten after "
                f"the search. It is left out of this bundle rather than read as this search's record. "
                f"The search's own record of the {m['stage']} stage is gone unless the producer archived it."
            ),
            "source": "datarepo ingest",
        }
        for m in mismatches
    ]


def _contaminant_label_findings(unresolved: Counter, tc: str | None, dataset_id: str) -> list[dict[str, Any]]:
    """A finding when a protein's contaminant label had to fall back to its PSM row's (G66)."""
    if not unresolved:
        return []
    examples = ", ".join(sorted(unresolved)[:5])
    return [
        {
            "finding_id": f"{dataset_id}:contaminant_label_unresolved",
            "dataset_id": dataset_id,
            "run_id": None,
            "code": "contaminant_label_unresolved",
            "severity": "warning",
            "status": "open",
            "message": (
                f"{len(unresolved)} protein(s) share a PSM row with proteins of another kind, and the "
                f"searched databases could not say which they are (not on disk, or in both a target "
                f"and the contaminant database under TCAmbiguity {tc or 'unknown'}). Each was given "
                f"its row's label, contaminant over target, so `is_contaminant` may over-state for "
                f"them: {examples}."
            ),
            "source": "datarepo ingest",
        }
    ]


#: The SDRF characteristics behind the four curated sample columns an `sdrf_skeleton` finding names.
_ANNOTATION_CHARACTERISTICS = (
    "characteristics[organism part]",
    "characteristics[cell type]",
    "characteristics[disease]",
    "characteristics[individual]",
)


def _uncoded_annotation(characteristics: list[dict[str, Any]]) -> str:
    """The distinct text values of the four annotation characteristics, e.g. `organism part: Urine`.

    Empty when the SDRF holds none, which is when `sdrf_skeleton` is true.
    """
    from .sources.sdrf import NOT_AVAILABLE  # noqa: PLC0415

    seen: dict[str, set[str]] = {}
    for row in characteristics:
        name = str(row.get("name", "")).strip().lower()
        value = str(row.get("value") or "").strip()
        if name in _ANNOTATION_CHARACTERISTICS and value.lower() not in NOT_AVAILABLE:
            seen.setdefault(name[len("characteristics["):-1], set()).add(value)
    return "; ".join(f"{name}: {', '.join(sorted(values)[:5])}" for name, values in sorted(seen.items()))


def _enrichment_findings(runs: list[dict[str, Any]], dataset_id: str, mixed: bool) -> list[dict[str, Any]]:
    """A finding when a dataset's runs differ in enrichment (G63).

    `datasets.enrichment` is the producer's declaration, and on a mixed deposit it is true of only
    some runs: PXD058611 declares `[chemical_probe]` and 15 of its 36 runs are whole proteome. A
    filter on the dataset row alone gets both halves wrong, and `enrichment_mixed` is a column a
    caller has to know to read. A finding reaches every answer that cites the dataset (D19), so the
    fact is carried where it cannot be skipped rather than where it is easiest to write.
    """
    if not mixed:
        return []
    known = Counter(", ".join(r["enrichment"]) for r in runs if r["enrichment"] is not None)
    unknown = sum(1 for r in runs if r["enrichment"] is None)
    if known:
        split = "; ".join(f"{n} run(s) [{value}]" for value, n in sorted(known.items()))
        message = (
            f"The runs of this dataset differ in enrichment: {split}. The dataset's own `enrichment` "
            f"is the producer's declaration and is true of only some runs, so answer any "
            f"enrichment-dependent question per run from `runs.enrichment`, and never pool its runs "
            f"as one kind."
        )
    else:
        message = (
            f"The producer flagged this dataset as mixing enrichments but did not say which run is "
            f"which, so `runs.enrichment` is NULL on all {unknown} runs. Do not use it for any "
            f"question that depends on whether a run was enriched."
        )
    return [
        {
            "finding_id": f"{dataset_id}:mixed_enrichment",
            "dataset_id": dataset_id,
            "run_id": None,
            "code": "mixed_enrichment",
            "severity": "warning",
            "status": "open",
            "message": message,
            "source": "datarepo ingest",
        }
    ]


def _usi_findings(run_names: RunNameMap, dataset_id: str) -> list[dict[str, Any]]:
    if not run_names.unmatched:
        return []
    names = ", ".join(sorted(run_names.unmatched))
    return [
        {
            "finding_id": f"{dataset_id}:unmatched_runs",
            "dataset_id": dataset_id,
            "run_id": None,
            "code": "unmatched_runs",
            "severity": "warning",
            "status": "open",
            "message": (
                f"Run name(s) the search reported could not be matched to a deposited file, so "
                f"their PSMs carry no USI and their quantities are attached to an assay ID that "
                f"has no run row: {names}."
            ),
            "source": "datarepo ingest",
        }
    ]


def ingest(
    manifest_path: str | Path,
    accession: str,
    *,
    store: Path | None = None,
    mm_settings: Path | None = None,
    overwrite: bool = False,
) -> IngestResult:
    """Load a manifest and ingest one dataset from it."""
    manifest = load_manifest(manifest_path)
    entry = manifest.dataset(accession)
    return ingest_dataset(
        manifest, entry, store=store, mm_settings=mm_settings, overwrite=overwrite
    )


__all__ = ["ingest", "ingest_dataset", "IngestResult", "SCHEMA_VERSION"]
