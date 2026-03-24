from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import real_image_manifest


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_manifest_entries_refreshes_sizes_and_output_names(tmp_path):
    tests_dir = tmp_path / "tests"
    artifacts_dir = tests_dir / "artifacts" / "real_image_pipeline"
    tests_dir.mkdir(parents=True)
    artifacts_dir.mkdir(parents=True)

    (tests_dir / "sample.png").write_bytes(b"input-bytes")
    (artifacts_dir / "sample_output.png").write_bytes(b"output-bytes-123")

    updated_entries = real_image_manifest.build_manifest_entries(
        [{"filename": "sample.png", "recognized_type": "diagram", "bytes_in": 1, "bytes_out": 2}],
        tests_dir=tests_dir,
        artifacts_dir=artifacts_dir,
    )

    assert updated_entries == [
        {
            "filename": "sample.png",
            "recognized_type": "diagram",
            "output_artifact": "sample_output.png",
            "bytes_in": len(b"input-bytes"),
            "bytes_out": len(b"output-bytes-123"),
        }
    ]


def test_validate_manifest_detects_drift(tmp_path):
    tests_dir = tmp_path / "tests"
    artifacts_dir = tests_dir / "artifacts" / "real_image_pipeline"
    manifest_path = artifacts_dir / "manifest.json"
    tests_dir.mkdir(parents=True)
    artifacts_dir.mkdir(parents=True)

    (tests_dir / "sample.png").write_bytes(b"input-bytes")
    (artifacts_dir / "sample_output.png").write_bytes(b"output-bytes")
    manifest_path.write_text(
        json.dumps([{"filename": "sample.png", "output_artifact": "sample_output.png", "bytes_in": 1, "bytes_out": 2}]),
        encoding="utf-8",
    )

    try:
        real_image_manifest.validate_manifest(manifest_path, tests_dir=tests_dir, artifacts_dir=artifacts_dir)
    except RuntimeError as exc:
        assert "Manifest drift detected" in str(exc)
    else:
        raise AssertionError("Expected manifest drift to be detected")


def test_manifest_cli_write_updates_file(tmp_path):
    tests_dir = tmp_path / "tests"
    artifacts_dir = tests_dir / "artifacts" / "real_image_pipeline"
    manifest_path = artifacts_dir / "manifest.json"
    tests_dir.mkdir(parents=True)
    artifacts_dir.mkdir(parents=True)

    (tests_dir / "sample.png").write_bytes(b"input-bytes")
    (artifacts_dir / "sample_output.png").write_bytes(b"output-bytes")
    manifest_path.write_text(
        json.dumps([{"filename": "sample.png", "bytes_in": 0, "bytes_out": 0}], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "real_image_manifest.py"),
            "--manifest",
            str(manifest_path),
            "--tests-dir",
            str(tests_dir),
            "--artifacts-dir",
            str(artifacts_dir),
            "--write",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert updated_manifest[0]["output_artifact"] == "sample_output.png"
    assert updated_manifest[0]["bytes_in"] == len(b"input-bytes")
    assert updated_manifest[0]["bytes_out"] == len(b"output-bytes")