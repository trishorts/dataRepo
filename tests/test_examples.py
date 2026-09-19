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
