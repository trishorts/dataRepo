"""Shared fixtures.

`tests/data/` holds a miniature producing instance: a manifest with relative roots, two runs, real
MetaMorpheus `.psmtsv` rows trimmed from PXD036557, and hand-made FlashLFQ tables whose edge cases
are the ones that matter (a zero intensity, a `NotDetected` cell, a q-value of exactly zero, a
decoy group, a contaminant group).

Tests that need pyMzLib are skipped, not failed, when it is not installed. That is a courtesy to a
checkout, not a CI condition: `pip install mzlib` is all it takes, its wheels ship for win-x64,
linux-x64, osx-x64 and osx-arm64 and carry the mzLib bridge, and CI installs it so these tests run
there. `PYMZLIB_BRIDGE` is only for a source checkout of pyMzLib, which ships no bridge.
"""

from __future__ import annotations

from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"
MANIFEST = DATA / "manifest.yaml"
WORK_ROOT = DATA / "work_root"
SEARCH_RESULTS = WORK_ROOT / "run_test/PXD999999/04_search/mm/Task3SearchTask"
MM_SETTINGS = WORK_ROOT / "mm_settings/1.1.11"


def pymzlib_available() -> bool:
    try:
        from datarepo.readers import require_pymzlib

        require_pymzlib()
    except Exception:
        return False
    return True


needs_pymzlib = pytest.mark.skipif(
    not pymzlib_available(),
    reason="pyMzLib is required to parse .psmtsv; `pip install mzlib`",
)


@pytest.fixture
def manifest():
    from datarepo.manifest import load_manifest

    return load_manifest(MANIFEST)


@pytest.fixture
def registry():
    from datarepo.modlist import ModRegistry

    return ModRegistry.from_metamorpheus(MM_SETTINGS)


@pytest.fixture
def bundle(tmp_path, manifest):
    """Ingest the fixture dataset once and return the result."""
    from datarepo.ingest import ingest_dataset

    return ingest_dataset(
        manifest, manifest.dataset("PXD999999"), store=tmp_path / "store", mm_settings=MM_SETTINGS
    )


@pytest.fixture
def tables(bundle):
    """The written bundle read back as `{table: rows}`."""
    import pyarrow.parquet as pq

    return {
        path.stem: pq.read_table(path).to_pylist()
        for path in sorted(bundle.bundle_path.glob("*.parquet"))
    }
