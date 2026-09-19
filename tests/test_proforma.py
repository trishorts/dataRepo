"""MetaMorpheus notation into ProForma 2.

The peptidoform string is the join key for quantities, the body of every USI and the thing every
benchmark question about a modification is phrased in, so a wrong translation is not a cosmetic
problem: it silently splits one peptidoform into two, or points a USI at a spectrum that does not
contain what the string claims.
"""

from __future__ import annotations

import pytest

from datarepo.modlist import ModEntry, ModRegistry
from datarepo.proforma import N_TERMINUS, ProformaCache, parse


@pytest.fixture
def small_registry():
    return ModRegistry(
        [
            ModEntry("Carbamidomethyl on C", frozenset("C"), 4, 57.021464, "test"),
            ModEntry("Oxidation on M", frozenset("M"), 35, 15.994915, "test"),
            ModEntry("Ammonia loss", frozenset("CN"), 385, -17.026549, "test"),
            ModEntry("Calcium", frozenset("DE"), None, 37.946941, "test"),
            ModEntry("Nameless", frozenset("K"), None, None, "test"),
        ]
    )


def test_unmodified_sequence_is_returned_unchanged(small_registry):
    result = parse("PEPTIDEK", small_registry)
    assert result.proforma == "PEPTIDEK"
    assert result.base_sequence == "PEPTIDEK"
    assert not result.is_modified


def test_residue_modification_becomes_a_unimod_tag(small_registry):
    result = parse("KLADQC[Common Fixed:Carbamidomethyl on C]TGLQ", small_registry)
    assert result.proforma == "KLADQC[UNIMOD:4]TGLQ"
    assert result.base_sequence == "KLADQCTGLQ"
    assert [(m.position, m.residue, m.unimod) for m in result.mods] == [(6, "C", "UNIMOD:4")]


def test_leading_bracket_is_an_n_terminal_modification(small_registry):
    result = parse("[Common Artifact:Ammonia loss on C]C[Common Fixed:Carbamidomethyl on C]AK", small_registry)
    assert result.proforma == "[UNIMOD:385]-C[UNIMOD:4]AK"
    assert result.base_sequence == "CAK"
    assert result.mods[0].position == N_TERMINUS
    assert result.mods[0].residue == "N-term"


def test_two_modifications_on_one_peptide_keep_their_positions(small_registry):
    result = parse("M[Common Variable:Oxidation on M]PEC[Common Fixed:Carbamidomethyl on C]K", small_registry)
    assert result.proforma == "M[UNIMOD:35]PEC[UNIMOD:4]K"
    assert [m.position for m in result.mods] == [1, 4]


def test_a_modification_with_no_unimod_falls_back_to_its_mass(small_registry):
    result = parse("PEPD[Metal:Calcium on D]K", small_registry)
    assert result.proforma == "PEPD[+37.946941]K"
    assert result.unresolved == ()  # a mass is a real answer, not a failure


def test_a_modification_with_neither_accession_nor_mass_is_reported(small_registry):
    result = parse("PEPK[Custom:Nameless on K]R", small_registry)
    assert result.proforma == "PEPK[Info:Nameless on K]R"
    assert result.unresolved == ("Custom:Nameless on K",)


def test_an_unknown_modification_is_reported_rather_than_guessed(small_registry):
    result = parse("PEPS[Common Biological:Phosphorylation on S]K", small_registry)
    assert "[Info:Phosphorylation on S]" in result.proforma
    assert result.unresolved == ("Common Biological:Phosphorylation on S",)
    assert result.mods[0].resolved is False


def test_the_cache_counts_each_unresolved_occurrence(small_registry):
    cache = ProformaCache(small_registry)
    for _ in range(3):
        cache("PEPS[Common Biological:Phosphorylation on S]K")
    assert cache.size == 1
    assert cache.unresolved == {"Common Biological:Phosphorylation on S": 3}


def test_empty_input_is_not_an_error(small_registry):
    assert parse("", small_registry).proforma == ""
