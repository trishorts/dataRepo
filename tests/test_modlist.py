"""The modification registry is read from the search's own MetaMorpheus install."""

from __future__ import annotations

from datarepo.modlist import ModRegistry, _targets

from conftest import MM_SETTINGS


def test_registry_reads_both_metamorpheus_and_uniprot_files(registry):
    assert len(registry) > 0
    assert "aListOfmods.txt" in registry.sources
    assert "ptmlist.txt" in registry.sources


def test_a_name_that_carries_its_target_resolves(registry):
    entry = registry.lookup("Carbamidomethyl on C")
    assert entry is not None
    assert entry.unimod_curie == "UNIMOD:4"


def test_a_name_whose_file_entry_omits_the_target_still_resolves(registry):
    # The file's ID is "Hydroxylation" with targets "K or N"; the data says "Hydroxylation on K".
    entry = registry.lookup("Hydroxylation on K")
    assert entry is not None
    assert entry.unimod_curie == "UNIMOD:35"


def test_a_uniprot_ptm_name_resolves_through_ptmlist(registry):
    entry = registry.lookup("N6-acetyllysine on K")
    assert entry is not None
    assert entry.unimod_curie == "UNIMOD:1"
    assert entry.monoisotopic_mass == 42.010565


def test_an_entry_with_a_mass_but_no_accession_keeps_the_mass(registry):
    entry = registry.lookup("Calcium on D")
    assert entry is not None
    assert entry.unimod is None
    assert entry.monoisotopic_mass == 37.946941


def test_an_unknown_name_returns_nothing_rather_than_a_near_match(registry):
    assert registry.lookup("Not A Real Modification on Z") is None


def test_a_missing_install_yields_an_empty_registry(tmp_path):
    assert len(ModRegistry.from_metamorpheus(tmp_path / "absent")) == 0


def test_targets_are_parsed_from_both_notations():
    assert _targets("K or N") == frozenset({"K", "N"})
    assert _targets("Methionine.") == frozenset({"M"})
    assert _targets("Nxs") == frozenset({"N"})  # a motif's first residue is the modified one
    assert _targets("") == frozenset()


def test_the_registry_is_pinned_to_the_searching_build():
    # Reading the install named in the manifest, rather than a copy kept here, is what keeps the
    # accession mapping in step with the MetaMorpheus version that produced the results.
    assert (MM_SETTINGS / "Mods").is_dir()
