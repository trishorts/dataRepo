"""Reading a `.psmtsv` in windows (DATAREPO-37, aging 049).

pyMzLib's bridge returns a read as one JSON document, and .NET cannot build one past ~2 GB, so a
1.75 GB `AllPSMs.psmtsv` could not be read whole. `read_psmtsv` now reads a large file in windows.
The property that matters is the CLASS one: **a windowed read is the same columns, values and
order as a whole read**, whatever the window size. The first test holds it on real pyMzLib output;
the rest pin the loop's edges with a fake reader, because a real out-of-memory failure needs a
file too big to keep in the repository.
"""

from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import SEARCH_RESULTS, needs_pymzlib
from datarepo import readers as mod
from datarepo.errors import ReaderUnavailable
from datarepo.readers import ReaderLog, read_psmtsv


def _same(a, b) -> bool:
    return a == b or (isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b))


@needs_pymzlib
@pytest.mark.parametrize("name", ["AllPSMs.psmtsv", "AllPeptides.psmtsv"])
def test_a_windowed_read_is_the_whole_read(name, monkeypatch):
    path = SEARCH_RESULTS / name
    whole = read_psmtsv(path)
    log = ReaderLog()
    # One byte of budget and a 7-record floor split the fixture's 40-60 rows into windows that do
    # not divide it evenly, so the last window is a short one. (At the real 1,000-record floor the
    # fixture fits one window and this test would prove nothing -- it did, in its first draft.)
    monkeypatch.setattr(mod, "MIN_WINDOW_RECORDS", 7)
    windowed = read_psmtsv(path, log, window_bytes=1)
    assert list(windowed) == list(whole)
    for column, values in whole.items():
        assert len(windowed[column]) == len(values), column
        assert all(_same(a, b) for a, b in zip(values, windowed[column])), column
    calls = int(log.entries[0]["note"].split(" windows")[0].split()[-1])
    assert calls == math.ceil(len(next(iter(whole.values()))) / 7) and calls > 1


class FakeReaders:
    """`read_records` over an in-memory table, failing like the bridge when a window is too big."""

    def __init__(self, n: int, *, max_window: int | None = None, error: str = "Insufficient memory",
                 grow_after: int | None = None):
        self.n, self.max_window, self.error, self.grow_after = n, max_window, error, grow_after
        self.calls: list[tuple[int | None, int]] = []

    def read_records(self, path, *, limit=None, offset=0, timeout=None):
        self.calls.append((limit, offset))
        if self.max_window is not None and (limit is None or limit > self.max_window):
            raise RuntimeError(self.error)
        n = self.n + (1 if self.grow_after is not None and len(self.calls) > self.grow_after else 0)
        stop = n if limit is None else min(offset + limit, n)
        rows = range(offset, stop)
        return SimpleNamespace(
            columns={"scan": list(rows), "sequence": [f"PEP{i}K" for i in rows]},
            record_count=n, truncated=stop < n or offset > 0,
        )


@pytest.fixture
def big_file(tmp_path) -> Path:
    # 5,000 records of ~100 bytes: large next to the budgets used below, tiny on disk.
    path = tmp_path / "AllPSMs.psmtsv"
    path.write_text("header\n" + "x" * 99 + "\n" * 1 + ("y" * 99 + "\n") * 4999, encoding="utf-8")
    return path


def _install(monkeypatch, fake):
    monkeypatch.setattr(mod, "require_pymzlib", lambda: fake)
    monkeypatch.setattr(mod, "MIN_WINDOW_RECORDS", 10)


def test_windows_concatenate_in_order(monkeypatch, big_file):
    fake = FakeReaders(5000)
    _install(monkeypatch, fake)
    cols = read_psmtsv(big_file, window_bytes=100 * 700)
    assert cols["scan"] == list(range(5000))
    assert len(fake.calls) > 1 and all(limit is not None for limit, _ in fake.calls)


def test_a_small_file_is_still_one_whole_read(monkeypatch, big_file):
    fake = FakeReaders(5000)
    _install(monkeypatch, fake)
    read_psmtsv(big_file, window_bytes=10**9)
    assert fake.calls == [(None, 0)]


def test_an_out_of_memory_window_is_halved_and_retried(monkeypatch, big_file):
    fake = FakeReaders(5000, max_window=300)
    _install(monkeypatch, fake)
    log = ReaderLog()
    cols = read_psmtsv(big_file, log, window_bytes=100 * 2000)
    assert cols["scan"] == list(range(5000))
    assert any(limit > 300 for limit, _ in fake.calls)  # it did fail first
    assert log.entries[0]["rows"] == 5000


def test_a_failure_that_is_not_memory_is_not_swallowed(monkeypatch, big_file):
    fake = FakeReaders(5000, max_window=300, error="UsageError: not a file type mzLib recognises")
    _install(monkeypatch, fake)
    with pytest.raises(RuntimeError, match="not a file type"):
        read_psmtsv(big_file, window_bytes=100 * 2000)


def test_out_of_memory_at_the_smallest_window_is_raised(monkeypatch, big_file):
    fake = FakeReaders(5000, max_window=5)
    _install(monkeypatch, fake)
    with pytest.raises(RuntimeError, match="memory"):
        read_psmtsv(big_file, window_bytes=100 * 2000)


def test_a_file_that_changes_between_windows_is_refused(monkeypatch, big_file):
    fake = FakeReaders(5000, grow_after=1)
    _install(monkeypatch, fake)
    with pytest.raises(ReaderUnavailable, match="changed while it was being read"):
        read_psmtsv(big_file, window_bytes=100 * 700)
