"""The generated artefacts must not drift from the code and schema that generate them."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from conftest import needs_pymzlib

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))


def test_the_arrow_schemas_match_the_linkml_schema():
    # `_tables.py` is generated; a schema edit without a regeneration would ship a stale writer.
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_tables.py"), "--check"],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@needs_pymzlib
def test_the_committed_example_bundle_is_what_the_ingester_writes():
    import build_example_bundle

    current = (ROOT / "examples" / "ingested_bundle.yaml").read_text(encoding="utf-8")
    assert current == build_example_bundle.render(build_example_bundle.export()), (
        "examples/ingested_bundle.yaml is stale; run python tools/build_example_bundle.py"
    )


def test_the_example_bundle_validates_against_the_schema():
    linkml_validate = pytest.importorskip(
        "linkml.validator", reason="linkml is a dev dependency; CI installs it"
    )
    report = linkml_validate.validate(
        __import__("yaml").safe_load((ROOT / "examples" / "ingested_bundle.yaml").read_text(encoding="utf-8")),
        str(ROOT / "schema" / "datarepo.yaml"),
        "Bundle",
    )
    assert not report.results, [str(r) for r in report.results]


def test_the_packaged_version_is_the_package_version():
    # It was restated in pyproject.toml and drifted: the file said 0.3.1, the package said 0.7.0,
    # and what was actually installed said 0.1.0 -- three answers to one question, for four
    # releases, with nothing to catch it. `__version__` is in every catalog_id, so an operator
    # reconciling "what did I install" against a catalog was reading two different numbers.
    import importlib.metadata

    import datarepo

    assert importlib.metadata.version("datarepo") == datarepo.__version__, (
        "the installed distribution's version differs from datarepo.__version__; "
        "reinstall (`pip install -e .`) or check pyproject's dynamic version"
    )
