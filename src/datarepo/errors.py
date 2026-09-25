"""Failure modes of an ingest, each one a thing an operator can act on."""

from __future__ import annotations


class DataRepoError(Exception):
    """Base class for every error dataRepo raises on purpose."""


class ManifestError(DataRepoError):
    """The instance manifest is missing, malformed, or does not name the dataset asked for."""


class DatasetExcluded(DataRepoError):
    """The manifest marks the dataset `exclude` or `hold`.

    Refusing is the point: the producer has already judged the run unfit (a TMT dataset searched as
    label-free, say), and loading it would put invalid quant in the repository under a status that
    says not to.
    """


class UnsupportedProvenance(DataRepoError):
    """The run's `provenance.json` uses a schema version this ingester cannot read safely."""


class ReaderUnavailable(DataRepoError):
    """pyMzLib is not importable, or the mzLib bridge its wheel carries did not resolve.

    Parsing producer formats belongs to pyMzLib (FRAMEWORK section 3), so there is no in-house
    fallback for the formats it covers.
    """


class IngestError(DataRepoError):
    """The inputs are present and readable but do not add up."""


class CatalogError(DataRepoError):
    """The bundles a catalog was asked to load are missing, ambiguous, or do not hold together."""


class QueryRefused(DataRepoError):
    """The sandbox would not run the statement (D14): several at once, or the wrong kind.

    Refused before execution, so the message can say what to send instead. An agent that gets a
    reason can fix its query; an agent that gets a permission error from deep inside DuckDB guesses.
    """


class QueryTimeout(DataRepoError):
    """The query was still running at the deadline and the watchdog interrupted it (D14)."""


class RunnerError(DataRepoError):
    """`datarepo run` refused: an unreleased engine or datarepo, an input that does not hash to its
    record, or engine output that fails the engine's own acceptance checks. Nothing is written."""
