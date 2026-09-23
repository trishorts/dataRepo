"""The public static site (FRAMEWORK step 4a, D16, D17).

The site is written from one catalog and nothing else, so these tests build a catalog from the same
miniature bundles `test_catalog` uses and check the pages against it: every number a page states is
the number the catalog holds, and nothing the catalog does not hold is stated at all.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from datarepo.catalog import build_catalog, run_query
from datarepo.cli import main
from datarepo.errors import CatalogError
from datarepo.site import SITE_MARKER, build_site, summary
from test_catalog import write_bundle  # noqa: F401 - tests/ is on the path (pyproject)


@pytest.fixture
def catalog(tmp_path) -> Path:
    store = tmp_path / "store"
    bundles = [
        write_bundle(store, "PXD000001", ptm_sites=True),
        write_bundle(store, "PXD000002", accessions=("P11111", "P22222")),
    ]
    return build_catalog(bundles, tmp_path / "catalog.duckdb", instance="test-instance").path


def jsonld(page: Path) -> dict:
    text = page.read_text(encoding="utf-8")
    block = re.search(r'<script type="application/ld\+json">\n(.*?)\n</script>', text, re.S)
    assert block, f"{page.name} has no JSON-LD block"
    return json.loads(block.group(1))


def overview(catalog: Path) -> dict[str, dict]:
    columns, data = run_query(catalog, "SELECT * FROM dataset_overview")
    return {row[0]: dict(zip(columns, row)) for row in data}


def test_every_dataset_gets_a_page_and_an_index_entry(tmp_path, catalog):
    result = build_site(catalog, tmp_path / "site")
    index = (tmp_path / "site/index.html").read_text(encoding="utf-8")
    for dataset_id in ("PXD000001", "PXD000002"):
        assert (tmp_path / f"site/datasets/{dataset_id}.html").is_file()
        assert f'href="datasets/{dataset_id}.html"' in index
    assert result.catalog_id in index


def test_the_summary_states_the_catalogs_own_numbers(tmp_path, catalog):
    build_site(catalog, tmp_path / "site")
    facts = json.loads((tmp_path / "site/datasets.json").read_text(encoding="utf-8"))
    held = overview(catalog)
    for ds in facts["datasets"]:
        row = held[ds["dataset_id"]]
        for column in ("n_psms_1pct", "n_peptidoforms_1pct", "n_protein_groups_1pct", "n_ptm_sites"):
            assert ds[column] == row[column]
        text = ds["summary"]
        assert f"{row['n_psms_1pct']:,} PSMs" in text
        assert f"{row['n_protein_groups_1pct']:,} protein groups" in text


def test_the_summary_is_labelled_generated(tmp_path, catalog):
    build_site(catalog, tmp_path / "site")
    page = (tmp_path / "site/datasets/PXD000001.html").read_text(encoding="utf-8")
    assert "Generated summary" in page


def test_each_page_carries_the_bioschemas_dataset_minimum(tmp_path, catalog):
    build_site(catalog, tmp_path / "site", base_url="https://example.org/repo/")
    doc = jsonld(tmp_path / "site/datasets/PXD000001.html")
    assert doc["@type"] == "Dataset"
    assert doc["dct:conformsTo"]["@id"].startswith("https://bioschemas.org/profiles/Dataset/")
    for key in ("name", "description", "identifier", "keywords", "url"):
        assert doc.get(key), key
    assert doc["url"] == "https://example.org/repo/datasets/PXD000001.html"
    # Bioschemas asks for 50-5000 characters.
    assert 50 <= len(doc["description"]) <= 5000


def test_a_licence_the_bundle_does_not_state_is_not_invented(tmp_path, catalog):
    # The fixture bundles carry no licence. D3 says CC BY 4.0, and the page must still not claim it:
    # the bundle is what a user downloads, and the licence it states is the one that binds.
    result = build_site(catalog, tmp_path / "site")
    doc = jsonld(tmp_path / "site/datasets/PXD000001.html")
    assert "license" not in doc
    assert "creator" not in doc
    assert any("no licence" in w for w in result.warnings)


def test_a_title_cannot_break_out_of_the_page(tmp_path, catalog):
    import duckdb

    hostile = "</script><script>alert(1)</script> & <b>"
    with duckdb.connect(str(catalog)) as con:
        con.execute("UPDATE dataset_overview SET title = ? WHERE dataset_id = 'PXD000001'", [hostile])
    build_site(catalog, tmp_path / "site")
    page = (tmp_path / "site/datasets/PXD000001.html").read_text(encoding="utf-8")
    assert "<script>alert" not in page
    assert jsonld(tmp_path / "site/datasets/PXD000001.html")["name"].endswith(hostile)


def test_urls_that_need_an_address_are_skipped_without_one(tmp_path, catalog):
    result = build_site(catalog, tmp_path / "site")
    for name in ("croissant.json", "sitemap.xml", "robots.txt"):
        assert not (tmp_path / "site" / name).exists()
        assert name in result.skipped
    page = (tmp_path / "site/datasets/PXD000001.html").read_text(encoding="utf-8")
    assert "not published yet" in page
    assert "distribution" not in jsonld(tmp_path / "site/datasets/PXD000001.html")


def test_a_data_url_gives_downloads_and_a_croissant_file(tmp_path, catalog):
    import hashlib

    build_site(catalog, tmp_path / "site", data_url="https://data.example.org/store")
    held = overview(catalog)
    bundle_id = held["PXD000001"]["bundle_id"]
    url = f"https://data.example.org/store/PXD000001/{bundle_id}/psms.parquet"
    assert url in (tmp_path / "site/datasets/PXD000001.html").read_text(encoding="utf-8")

    doc = json.loads((tmp_path / "site/croissant.json").read_text(encoding="utf-8"))
    assert doc["conformsTo"] == "http://mlcommons.org/croissant/1.0"
    # One FileObject per file, never a FileSet over a served directory: that form validates and
    # then loads zero records, because a loader cannot list an HTTP directory.
    assert all(d["@type"] == "cr:FileObject" for d in doc["distribution"])
    psms = next(d for d in doc["distribution"] if d["@id"] == "PXD000001/psms.parquet")
    assert psms["contentUrl"] == url
    _, data = run_query(catalog, "SELECT path FROM catalog_bundles WHERE dataset_id = 'PXD000001'")
    on_disk = (Path(data[0][0]) / "psms.parquet").read_bytes()
    assert psms["sha256"] == hashlib.sha256(on_disk).hexdigest()

    record = next(rs for rs in doc["recordSet"] if rs["@id"] == "PXD000001/psms")
    fields = {f["name"]: f for f in record["field"]}
    assert fields["q_value"]["dataType"] == "sc:Float"
    assert fields["protein_accessions"].get("repeated") is True
    assert fields["q_value"]["source"]["fileObject"]["@id"] == "PXD000001/psms.parquet"


def test_a_file_the_store_cannot_supply_is_left_out_not_guessed(tmp_path, catalog):
    _, data = run_query(catalog, "SELECT path FROM catalog_bundles WHERE dataset_id = 'PXD000002'")
    (Path(data[0][0]) / "psms.parquet").unlink()
    result = build_site(catalog, tmp_path / "site", data_url="https://data.example.org/store")
    doc = json.loads((tmp_path / "site/croissant.json").read_text(encoding="utf-8"))
    ids = {d["@id"] for d in doc["distribution"]}
    assert "PXD000002/psms.parquet" not in ids
    assert "PXD000001/psms.parquet" in ids
    assert any("could not read" in w for w in result.warnings)


def test_llms_txt_lists_every_dataset_and_names_the_catalog(tmp_path, catalog):
    result = build_site(catalog, tmp_path / "site")
    text = (tmp_path / "site/llms.txt").read_text(encoding="utf-8")
    assert text.startswith("# ")
    assert result.catalog_id in text
    for dataset_id in ("PXD000001", "PXD000002"):
        assert f"](datasets/{dataset_id}.html)" in text


def test_a_directory_that_is_not_a_site_is_refused(tmp_path, catalog):
    out = tmp_path / "busy"
    out.mkdir()
    (out / "notes.txt").write_text("mine", encoding="utf-8")
    with pytest.raises(CatalogError, match="not empty"):
        build_site(catalog, out)
    assert (out / "notes.txt").read_text(encoding="utf-8") == "mine"


def test_regenerating_removes_a_page_whose_dataset_left(tmp_path, catalog):
    out = tmp_path / "site"
    build_site(catalog, out)
    stale = out / "datasets/PXD000009.html"
    stale.write_text("old", encoding="utf-8")
    marker = json.loads((out / SITE_MARKER).read_text(encoding="utf-8"))
    marker["files"].append("datasets/PXD000009.html")
    (out / SITE_MARKER).write_text(json.dumps(marker), encoding="utf-8")

    build_site(catalog, out)
    assert not stale.exists()


def test_the_same_catalog_gives_the_same_bytes(tmp_path, catalog):
    build_site(catalog, tmp_path / "a")
    build_site(catalog, tmp_path / "b")
    for path in sorted((tmp_path / "a").rglob("*")):
        if path.is_file():
            twin = tmp_path / "b" / path.relative_to(tmp_path / "a")
            assert path.read_bytes() == twin.read_bytes(), path.name


def test_the_summary_mentions_no_warning_when_there_is_none():
    ds = {
        "dataset_id": "PXD1", "acquisition": "DDA", "quant_method": "label_free",
        "organism_names": ["Homo sapiens"], "n_runs": 1, "n_samples": 1, "enrichment": ["none"],
        "search_engine": "MetaMorpheus", "search_engine_version": "1.1.11",
        "n_psms_1pct": 10, "n_peptidoforms_1pct": 5, "n_protein_groups_1pct": 2,
        "n_ptm_sites": 0, "findings": [{"severity": "info", "code": "x", "message": "y"}],
    }
    text = summary(ds)
    assert "warning" not in text
    assert "1 run," in text and "whole proteome" in text


def test_a_notice_reaches_every_page_and_the_agents_entry_point(tmp_path, catalog):
    notice = "Preview: this data will be regenerated."
    build_site(catalog, tmp_path / "site", notice=notice)
    for page in (tmp_path / "site").rglob("*.html"):
        text = page.read_text(encoding="utf-8")
        assert text.index(notice) < text.index("<h1>"), page.name
    llms = (tmp_path / "site/llms.txt").read_text(encoding="utf-8")
    assert llms.index(notice) < llms.index("## Datasets")


def test_the_figures_of_merit_are_the_catalogs_sums(tmp_path, catalog):
    from datarepo.site import read_site_facts

    merit = {m["label"]: m for m in read_site_facts(catalog)["merit"]}
    held = overview(catalog)
    assert merit["Datasets"]["value"] == len(held)
    assert merit["PSMs at 1% FDR"]["value"] == sum(r["n_psms_1pct"] for r in held.values())
    assert merit["PTM sites"]["value"] == sum(r["n_ptm_sites"] for r in held.values())
    # P11111 and P22222 have accepted evidence; nothing in the fixture is a decoy or contaminant.
    assert merit["Proteins identified"]["value"] == 2
    # No bundle in the fixture reports an MS2 count, and the tile must say so rather than read 0.
    assert "0 of 2 datasets report it" in merit["Spectra searched"]["note"]


def test_the_front_page_carries_the_owners_overview(tmp_path, catalog):
    about = (
        "## About\n\nThe **aging** working group asks *why*. <b>no</b>\n\n"
        "- [pipeline](https://example.org/p)"
    )
    build_site(catalog, tmp_path / "site", about=about)
    page = (tmp_path / "site/index.html").read_text(encoding="utf-8")
    assert "<strong>aging</strong>" in page and "<em>why</em>" in page
    assert '<a href="https://example.org/p">pipeline</a>' in page
    assert "<b>no</b>" not in page and "&lt;b&gt;no&lt;/b&gt;" in page
    assert page.index("<strong>aging</strong>") < page.index('class="tiles"')


def test_the_command_line_writes_the_site(tmp_path, catalog, capsys):
    assert main(["site", str(catalog), "--out", str(tmp_path / "site")]) == 0
    out = capsys.readouterr().out
    assert "2 dataset pages" in out
    assert "skipped  croissant.json" in out
