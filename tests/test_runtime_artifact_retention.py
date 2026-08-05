import os
import time
from pathlib import Path

from docxaicorrector.runtime.artifact_retention import prune_artifact_dir, prune_ui_result_artifact_groups


def _write_file(path: Path, *, mtime: float, content: str = "{}") -> None:
    path.write_text(content, encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_prune_artifact_dir_noop_when_dir_missing(tmp_path):
    missing = tmp_path / "missing"
    pruned = prune_artifact_dir(
        target_dir=missing,
        max_age_seconds=10,
        max_count=5,
        now_epoch_seconds=100.0,
    )
    assert pruned == []


def test_prune_artifact_dir_removes_files_older_than_max_age(tmp_path):
    target = tmp_path / "boundary_reports"
    target.mkdir()
    old = target / "old.json"
    fresh = target / "fresh.json"
    _write_file(old, mtime=1.0)
    _write_file(fresh, mtime=90.0)

    pruned = prune_artifact_dir(
        target_dir=target,
        max_age_seconds=50,
        max_count=None,
        now_epoch_seconds=100.0,
        emit_log=False,
    )

    remaining = sorted(p.name for p in target.glob("*.json"))
    assert remaining == ["fresh.json"]
    assert [Path(p).name for p in pruned] == ["old.json"]


def test_prune_artifact_dir_enforces_max_count_removing_oldest_first(tmp_path):
    target = tmp_path / "relation_reports"
    target.mkdir()
    for index, mtime in enumerate([10.0, 20.0, 30.0, 40.0], start=1):
        _write_file(target / f"r_{index}.json", mtime=mtime)

    pruned = prune_artifact_dir(
        target_dir=target,
        max_age_seconds=None,
        max_count=2,
        now_epoch_seconds=1000.0,
        emit_log=False,
    )

    remaining = sorted(p.name for p in target.glob("*.json"))
    assert remaining == ["r_3.json", "r_4.json"]
    assert sorted(Path(p).name for p in pruned) == ["r_1.json", "r_2.json"]


def test_prune_artifact_dir_preserves_files_below_count_cap(tmp_path):
    target = tmp_path / "structure_maps"
    target.mkdir()
    for index, mtime in enumerate([10.0, 20.0], start=1):
        _write_file(target / f"m_{index}.json", mtime=mtime)

    pruned = prune_artifact_dir(
        target_dir=target,
        max_age_seconds=None,
        max_count=5,
        now_epoch_seconds=1000.0,
        emit_log=False,
    )

    assert pruned == []
    assert sorted(p.name for p in target.glob("*.json")) == ["m_1.json", "m_2.json"]


def test_prune_artifact_dir_respects_glob_filter(tmp_path):
    target = tmp_path / "mixed"
    target.mkdir()
    _write_file(target / "keep.txt", mtime=1.0)
    _write_file(target / "drop_a.json", mtime=1.0)
    _write_file(target / "drop_b.json", mtime=1.0)

    pruned = prune_artifact_dir(
        target_dir=target,
        max_age_seconds=10,
        max_count=None,
        now_epoch_seconds=1000.0,
        glob="*.json",
        emit_log=False,
    )

    assert sorted(Path(p).name for p in pruned) == ["drop_a.json", "drop_b.json"]
    remaining = sorted(p.name for p in target.iterdir() if p.is_file())
    assert remaining == ["keep.txt"]


def test_prune_artifact_dir_emits_debug_log_event_once(tmp_path, monkeypatch):
    target = tmp_path / "struct_validation"
    target.mkdir()
    _write_file(target / "stale.json", mtime=1.0)
    _write_file(target / "fresh.json", mtime=500.0)

    captured: list[tuple[int, str, str, dict]] = []

    def fake_log_event(level, event, message, **context):
        captured.append((level, event, message, context))
        return "evt-stub"

    import docxaicorrector.core.logger as logger

    monkeypatch.setattr(logger, "log_event", fake_log_event)

    pruned = prune_artifact_dir(
        target_dir=target,
        max_age_seconds=600,
        max_count=None,
        now_epoch_seconds=1000.0,
    )

    assert [Path(p).name for p in pruned] == ["stale.json"]
    assert len(captured) == 1
    level, event_name, _message, context = captured[0]
    import logging

    assert level == logging.DEBUG
    assert event_name == "artifact_pruned"
    assert context["removed_count"] == 1
    assert context["dir"] == str(target)


def test_prune_artifact_dir_skips_subdirectories(tmp_path):
    target = tmp_path / "with_subdir"
    target.mkdir()
    subdir = target / "nested"
    subdir.mkdir()
    _write_file(target / "old.json", mtime=1.0)

    pruned = prune_artifact_dir(
        target_dir=target,
        max_age_seconds=10,
        max_count=None,
        now_epoch_seconds=1000.0,
        emit_log=False,
    )

    assert [Path(p).name for p in pruned] == ["old.json"]
    assert subdir.exists() and subdir.is_dir()


def test_prune_artifact_dir_negative_limits_disable_policy(tmp_path):
    target = tmp_path / "disabled"
    target.mkdir()
    for index, mtime in enumerate([1.0, 2.0, 3.0], start=1):
        _write_file(target / f"f_{index}.json", mtime=mtime)

    pruned = prune_artifact_dir(
        target_dir=target,
        max_age_seconds=-1,
        max_count=-1,
        now_epoch_seconds=1000.0,
        emit_log=False,
    )

    assert pruned == []
    assert len(list(target.glob("*.json"))) == 3


def test_prune_artifact_dir_with_glob_star_prunes_non_json_artifacts(tmp_path):
    target = tmp_path / "ui_results"
    target.mkdir()
    _write_file(target / "old.result.md", mtime=1.0, content="# old")
    _write_file(target / "new.result.docx", mtime=999.0, content="docx")

    pruned = prune_artifact_dir(
        target_dir=target,
        max_age_seconds=10,
        max_count=None,
        now_epoch_seconds=1000.0,
        glob="*",
        emit_log=False,
    )

    assert [Path(p).name for p in pruned] == ["old.result.md"]
    assert sorted(p.name for p in target.iterdir() if p.is_file()) == ["new.result.docx"]


def test_prune_ui_result_artifact_groups_removes_whole_stem_group(tmp_path):
    target = tmp_path / "ui_results"
    target.mkdir()
    _write_file(target / "20260423_101010_old.result.md", mtime=10.0, content="old-md")
    _write_file(target / "20260423_101010_old.result.docx", mtime=10.0, content="old-docx")
    _write_file(target / "20260423_101010_old.result.tts.txt", mtime=10.0, content="old-tts")
    _write_file(target / "20260423_111111_new.result.md", mtime=20.0, content="new-md")
    _write_file(target / "20260423_111111_new.result.docx", mtime=20.0, content="new-docx")

    pruned = prune_ui_result_artifact_groups(
        target_dir=target,
        max_age_seconds=None,
        max_count=1,
        now_epoch_seconds=1000.0,
        emit_log=False,
    )

    assert sorted(Path(p).name for p in pruned) == [
        "20260423_101010_old.result.docx",
        "20260423_101010_old.result.md",
        "20260423_101010_old.result.tts.txt",
    ]
    assert sorted(p.name for p in target.iterdir() if p.is_file()) == [
        "20260423_111111_new.result.docx",
        "20260423_111111_new.result.md",
    ]


# --- spec 056 D': rejected marker attempts are a bounded family --------------------


def test_marker_attempt_artifacts_are_pruned_by_age_and_count(tmp_path, monkeypatch):
    from docxaicorrector.generation import marker_attempt_capture

    target = tmp_path / "marker_attempts"
    monkeypatch.setattr(marker_attempt_capture, "MARKER_ATTEMPT_DIAGNOSTICS_DIR", target)
    monkeypatch.setattr(marker_attempt_capture, "MARKER_ATTEMPT_ARTIFACTS_MAX_COUNT", 2)

    written = []
    for attempt in range(1, 5):
        path = marker_attempt_capture.write_marker_attempt_artifact(
            block_index=274,
            attempt=attempt,
            max_attempts=4,
            stage="attempt",
            error_code="empty_marker_chunk",
            expected_paragraph_ids=["p1336"],
            found_paragraph_ids=["p1336"],
            raw_response="[[DOCX_PARA_p1336]]\n",
        )
        assert path is not None
        written.append(Path(path))

    # Count cap holds: the newest two survive, the oldest two are gone. Ordering is
    # deterministic either way — mtimes rise with write order, and the name tiebreaker
    # (``_a01`` … ``_a04``) carries the same order when a coarse clock makes them equal.
    assert sorted(p.name for p in target.glob("*.json")) == sorted(p.name for p in written[-2:])

    # Age cap holds too: the family is pruned by the same age policy as its neighbours.
    now = time.time()
    os.utime(written[-2], (now - 100.0, now - 100.0))
    pruned = prune_artifact_dir(
        target_dir=target,
        max_age_seconds=10,
        max_count=None,
        now_epoch_seconds=now,
        emit_log=False,
    )
    assert [Path(p).name for p in pruned] == [written[-2].name]
    assert [p.name for p in target.glob("*.json")] == [written[-1].name]


def test_marker_attempt_artifact_write_failure_returns_none(tmp_path, monkeypatch):
    """A diagnostic that cannot be written must not raise into the generation it observes."""

    from docxaicorrector.generation import marker_attempt_capture

    # A file where the directory is expected: mkdir raises, the writer swallows it.
    blocker = tmp_path / "marker_attempts"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(marker_attempt_capture, "MARKER_ATTEMPT_DIAGNOSTICS_DIR", blocker)

    assert (
        marker_attempt_capture.write_marker_attempt_artifact(
            block_index=1,
            attempt=1,
            max_attempts=1,
            stage="attempt",
            error_code="markers_missing",
            expected_paragraph_ids=["p0001"],
            found_paragraph_ids=[],
            raw_response="no markers here",
        )
        is None
    )
