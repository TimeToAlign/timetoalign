"""Tests for ``timetoalign.testdata._corpus_file_lock`` (cross-process locking).

These tests pin the contract documented in ``tests/testdata/README.md``:
concurrent ``ensure_data()`` calls for the *same* corpus, issued from
independent OS processes, must never observe a partial extraction, and a
process that loses the race to extract must not redundantly re-fetch once
its peer has already finished. Everything here is network-free — a tiny
``.tar.gz`` fixture is built on disk and ``timetoalign.testdata._POOCH`` is
replaced with a fake object whose ``fetch()`` returns that local path.

Workers are spawned via ``multiprocessing`` (the ``spawn`` start method, to
match how ``pytest-xdist`` workers are independent processes rather than
threads or forked children). Because ``spawn`` starts a fresh interpreter,
monkeypatching in the parent process (e.g. via pytest's ``monkeypatch``
fixture) is invisible to the children — each worker function patches
``timetoalign.testdata.DATA_DIR`` and ``._POOCH`` on its own copy of the
module after it starts.
"""

from __future__ import annotations

import io
import multiprocessing
import tarfile
from pathlib import Path

import pytest

import timetoalign.testdata as testdata

_CORPUS_NAME = "midi"  # any REGISTRY-known name; its real contents are irrelevant here
_JOIN_TIMEOUT = 30.0


def _build_archive(
    dest_dir: Path, name: str, member_count: int
) -> tuple[Path, tuple[str, ...]]:
    """Build a ``<name>.tar.gz`` fixture under ``dest_dir``.

    Args:
        dest_dir: Directory to write the archive into.
        name: Corpus name; becomes the archive's single top-level directory.
        member_count: Number of small member files to include.

    Returns:
        The archive path and the tuple of ``"<name>/file_NNN.txt"`` member
        names it contains (relative to the extraction root).
    """
    archive_path = dest_dir / f"{name}.tar.gz"
    member_names = tuple(f"{name}/file_{i:03d}.txt" for i in range(member_count))
    with tarfile.open(archive_path, "w:gz") as tar:
        for member_name in member_names:
            payload = member_name.encode("utf-8")
            info = tarfile.TarInfo(name=member_name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return archive_path, member_names


def _join_or_kill(processes: list[multiprocessing.process.BaseProcess]) -> None:
    """Join every process, killing (and failing) on any that hang."""
    for proc in processes:
        proc.join(timeout=_JOIN_TIMEOUT)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
            pytest.fail(
                f"worker process {proc.pid} did not finish within {_JOIN_TIMEOUT}s"
            )


def _race_worker(
    name: str,
    data_dir: str,
    archive_path: str,
    member_names: tuple[str, ...],
    barrier: multiprocessing.synchronize.Barrier,
    result_queue: multiprocessing.Queue,
) -> None:
    """Patch the module in-process, then race every sibling on ``ensure_data``.

    Completeness is verified *inside the worker*, immediately after
    ``ensure_data()`` returns — not deferred to the parent process after all
    workers have joined. By the time every worker has finished, a slower
    sibling may have completed the extraction and papered over a window in
    which this worker briefly held an incomplete-but-trusted directory;
    checking here catches that window instead of missing it.
    """
    import timetoalign.testdata as td

    td.DATA_DIR = Path(data_dir)

    class _FakePooch:
        def fetch(self, archive_name: str) -> str:
            return archive_path

    td._POOCH = _FakePooch()

    barrier.wait()
    try:
        resolved = td.ensure_data(name)
        missing = [m for m in member_names if not (Path(data_dir) / m).is_file()]
        if missing:
            result_queue.put(("incomplete", repr(missing)))
        else:
            result_queue.put(("ok", str(resolved)))
    except Exception as exc:  # noqa: BLE001 - surfaced to the parent via the queue
        result_queue.put(("error", repr(exc)))


def _held_lock_worker(
    name: str,
    data_dir: str,
    archive_path: str,
    fetch_calls: multiprocessing.sharedctypes.Synchronized,
    started_event: multiprocessing.synchronize.Event,
    release_event: multiprocessing.synchronize.Event,
    result_queue: multiprocessing.Queue,
) -> None:
    """Call ``ensure_data`` but block inside ``fetch()`` until told to proceed.

    Signals ``started_event`` once inside ``fetch()`` (i.e. once the file
    lock is held), then waits on ``release_event`` before returning the
    archive path. This lets the parent test deterministically hold the lock
    open long enough to prove a second, concurrently-started process blocks
    on it rather than racing the extraction.
    """
    import timetoalign.testdata as td

    td.DATA_DIR = Path(data_dir)

    class _FakePooch:
        def fetch(self, archive_name: str) -> str:
            with fetch_calls.get_lock():
                fetch_calls.value += 1
            started_event.set()
            release_event.wait(timeout=_JOIN_TIMEOUT)
            return archive_path

    td._POOCH = _FakePooch()

    try:
        resolved = td.ensure_data(name)
        result_queue.put(("ok", str(resolved)))
    except Exception as exc:  # noqa: BLE001 - surfaced to the parent via the queue
        result_queue.put(("error", repr(exc)))


def _counting_worker(
    name: str,
    data_dir: str,
    archive_path: str,
    fetch_calls: multiprocessing.sharedctypes.Synchronized,
    result_queue: multiprocessing.Queue,
) -> None:
    """Call ``ensure_data`` immediately, counting ``fetch()`` invocations."""
    import timetoalign.testdata as td

    td.DATA_DIR = Path(data_dir)

    class _FakePooch:
        def fetch(self, archive_name: str) -> str:
            with fetch_calls.get_lock():
                fetch_calls.value += 1
            return archive_path

    td._POOCH = _FakePooch()

    try:
        resolved = td.ensure_data(name)
        result_queue.put(("ok", str(resolved)))
    except Exception as exc:  # noqa: BLE001 - surfaced to the parent via the queue
        result_queue.put(("error", repr(exc)))


@pytest.mark.parametrize("round_index", range(5))
def test_concurrent_processes_never_observe_partial_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, round_index: int
) -> None:
    """Six processes racing ``ensure_data()`` on one corpus all see a full extraction.

    ``target_dir`` is seeded with stale contents (a mismatched sentinel)
    before the race starts, matching the production scenario: the race in
    ``_ensure_one()`` only bites when a corpus needs *re*-extraction, because
    that is the branch that ``rmtree``s an existing directory while sibling
    processes may be mid-``extractall`` into it. Racing an empty
    ``target_dir`` (first-ever extraction) never exercises that ``rmtree``,
    so it would not reproduce the defect.

    Repeated as five independent rounds (via parametrization, each with its
    own ``tmp_path``) to make the race likely to be hit at least once if the
    locking regresses; every round is asserted independently rather than
    relying on any one round to prove the fix.
    """
    data_dir = tmp_path / "data"
    archive_path, member_names = _build_archive(
        tmp_path, _CORPUS_NAME, member_count=400
    )
    monkeypatch.setattr(testdata, "DATA_DIR", data_dir)

    stale_target_dir = data_dir / _CORPUS_NAME
    stale_target_dir.mkdir(parents=True)
    (stale_target_dir / "stale_file.txt").write_text("stale", encoding="utf-8")
    (stale_target_dir / ".tta_testdata_hash").write_text(
        "0" * 64, encoding="utf-8"
    )  # deliberately mismatched digest, forcing every racer into re-extraction

    worker_count = 6
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(worker_count)
    result_queue = ctx.Queue()

    processes = [
        ctx.Process(
            target=_race_worker,
            args=(
                _CORPUS_NAME,
                str(data_dir),
                str(archive_path),
                member_names,
                barrier,
                result_queue,
            ),
        )
        for _ in range(worker_count)
    ]
    for proc in processes:
        proc.start()
    _join_or_kill(processes)

    for proc in processes:
        assert proc.exitcode == 0, f"worker {proc.pid} exited with {proc.exitcode}"

    results = [result_queue.get(timeout=5) for _ in range(worker_count)]
    assert all(status == "ok" for status, _detail in results), results

    target_dir = data_dir / _CORPUS_NAME
    marker = target_dir / ".tta_testdata_hash"
    expected_digest = testdata.REGISTRY[f"{_CORPUS_NAME}.tar.gz"].removeprefix(
        "sha256:"
    )

    assert marker.is_file()
    assert marker.read_text(encoding="utf-8").strip() == expected_digest
    assert not (target_dir / "stale_file.txt").exists()
    for member in member_names:
        assert (data_dir / member).is_file(), f"round {round_index}: missing {member}"
    # No leftover temp sentinel from an interrupted write-then-rename.
    assert list(target_dir.glob(".tta_testdata_hash.tmp*")) == []

    # The parent process, with DATA_DIR patched the same way, must also see
    # the (already-extracted) corpus as ready without re-extracting.
    assert testdata.get_data_dir(_CORPUS_NAME) == target_dir


def test_second_process_blocked_by_lock_does_not_reextract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A process that loses the lock race must skip ``fetch()`` entirely.

    The first process is held inside ``fetch()`` (i.e. lock acquired, not
    yet released) until the test explicitly releases it. A second process
    started while the first is held must block on the file lock, then, on
    waking, see the sentinel already written by the first and return
    without ever calling ``fetch()`` itself.
    """
    data_dir = tmp_path / "data"
    archive_path, member_names = _build_archive(tmp_path, _CORPUS_NAME, member_count=5)
    monkeypatch.setattr(testdata, "DATA_DIR", data_dir)

    ctx = multiprocessing.get_context("spawn")
    fetch_calls = ctx.Value("i", 0)
    started_event = ctx.Event()
    release_event = ctx.Event()
    result_queue = ctx.Queue()

    first = ctx.Process(
        target=_held_lock_worker,
        args=(
            _CORPUS_NAME,
            str(data_dir),
            str(archive_path),
            fetch_calls,
            started_event,
            release_event,
            result_queue,
        ),
    )
    first.start()
    assert started_event.wait(
        timeout=_JOIN_TIMEOUT
    ), "first process never reached fetch()"

    second = ctx.Process(
        target=_counting_worker,
        args=(
            _CORPUS_NAME,
            str(data_dir),
            str(archive_path),
            fetch_calls,
            result_queue,
        ),
    )
    second.start()

    release_event.set()
    _join_or_kill([first, second])

    assert first.exitcode == 0
    assert second.exitcode == 0

    results = [result_queue.get(timeout=5) for _ in range(2)]
    assert all(status == "ok" for status, _detail in results), results

    assert fetch_calls.value == 1

    target_dir = data_dir / _CORPUS_NAME
    marker = target_dir / ".tta_testdata_hash"
    expected_digest = testdata.REGISTRY[f"{_CORPUS_NAME}.tar.gz"].removeprefix(
        "sha256:"
    )
    assert marker.read_text(encoding="utf-8").strip() == expected_digest
    for member in member_names:
        assert (data_dir / member).is_file()
