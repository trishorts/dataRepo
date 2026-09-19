"""MetaMorpheus task `.toml` files -> SearchModification rows and the searched database.

Which modifications a search *considered* is not recoverable from its results: a modification that
was searched for and never found leaves no trace in the PSM table. It is the difference between
"this dataset has no phosphorylation" and "this dataset was never searched for phosphorylation",
which is exactly the trap question P1 is built on, so the search's own parameter files are read.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from ..modlist import ModRegistry

#: MetaMorpheus packs its mod lists as `Category<TAB>Name` pairs joined by a double tab.
_PAIR_SEPARATOR = "\t\t"

#: Where each list lives, and what usage it means.
MOD_LISTS = (
    ("CommonParameters", "ListOfModsFixed", "fixed"),
    ("CommonParameters", "ListOfModsVariable", "variable"),
    ("GptmdParameters", "ListOfModsGptmd", "gptmd"),
)

DATABASE_SUFFIXES = (".xml", ".xml.gz", ".fasta", ".fasta.gz", ".fa")


def _pairs(packed: str):
    for chunk in str(packed or "").split(_PAIR_SEPARATOR):
        if not chunk.strip():
            continue
        category, _, name = chunk.partition("\t")
        yield category.strip(), name.strip()


def modification_rows(
    task_files: list[Path], dataset_id: str, registry: ModRegistry
) -> list[dict[str, Any]]:
    """Every modification the search could have assigned, with its UNIMOD accession where known.

    Args:
        task_files: the task `.toml` files the run used.
        dataset_id: ProteomeXchange accession.
        registry: modifications from the MetaMorpheus install that did the search.

    Returns:
        One row per (modification, usage), deduplicated and sorted.
    """
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for path in task_files:
        if not path.is_file():
            continue
        try:
            doc = tomllib.loads(path.read_text(encoding="utf-8-sig"))
        except tomllib.TOMLDecodeError:
            continue
        for section, key, usage in MOD_LISTS:
            packed = (doc.get(section) or {}).get(key)
            if not packed:
                continue
            for _category, name in _pairs(packed):
                if not name:
                    continue
                entry = registry.lookup(name)
                _, _, residues = name.rpartition(" on ")
                key_ = (name, usage)
                if key_ in seen:
                    continue
                seen[key_] = {
                    "dataset_id": dataset_id,
                    "modification": entry.unimod_curie if entry else None,
                    "name": name,
                    "residues": residues or "unspecified",
                    "usage": usage,
                }
    return [seen[k] for k in sorted(seen)]


def searched_database(provenance: dict[str, Any]) -> tuple[str | None, str | None]:
    """Name and SHA-256 of the protein database the search used, from its provenance inputs.

    Returns:
        `(name, sha256)`, either of which may be None when the provenance does not list one.
    """
    for entry in provenance.get("inputs") or []:
        path = str(entry.get("path", ""))
        if path.lower().endswith(DATABASE_SUFFIXES):
            return Path(path).name, entry.get("sha256")
    return None, None


def task_names(provenance: dict[str, Any]) -> list[str]:
    """Which MetaMorpheus tasks ran, from the search stage's params."""
    return [str(t) for t in ((provenance.get("params") or {}).get("tasks") or [])]
