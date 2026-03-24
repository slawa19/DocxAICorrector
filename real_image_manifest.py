from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_TESTS_DIR = REPO_ROOT / "tests"
DEFAULT_ARTIFACTS_DIR = DEFAULT_TESTS_DIR / "artifacts" / "real_image_pipeline"
DEFAULT_MANIFEST_PATH = DEFAULT_ARTIFACTS_DIR / "manifest.json"


def artifact_basename(filename: str) -> str:
    return Path(filename).stem


def build_output_artifact_name(filename: str, suffix: str) -> str:
    return f"{artifact_basename(filename)}_output{suffix}"


def _resolve_output_artifact_path(filename: str, artifacts_dir: Path, explicit_name: str | None) -> tuple[str, Path]:
    if explicit_name:
        output_path = artifacts_dir / explicit_name
        if not output_path.exists():
            raise FileNotFoundError(f"Output artifact not found for {filename}: {explicit_name}")
        return explicit_name, output_path

    matches = sorted(artifacts_dir.glob(f"{artifact_basename(filename)}_output.*"))
    if not matches:
        raise FileNotFoundError(f"No output artifact found for {filename} under {artifacts_dir}")
    if len(matches) > 1:
        raise RuntimeError(f"Multiple output artifacts found for {filename}: {[path.name for path in matches]}")
    return matches[0].name, matches[0]


def build_manifest_entries(
    manifest_data: list[dict[str, object]],
    *,
    tests_dir: Path = DEFAULT_TESTS_DIR,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
) -> list[dict[str, object]]:
    updated_entries: list[dict[str, object]] = []
    referenced_output_names: set[str] = set()

    for entry in manifest_data:
        filename = str(entry.get("filename") or "").strip()
        if not filename:
            raise ValueError("Manifest entry is missing filename")

        source_path = tests_dir / filename
        if not source_path.exists():
            raise FileNotFoundError(f"Source image not found: {source_path}")

        output_artifact_name, output_path = _resolve_output_artifact_path(
            filename,
            artifacts_dir,
            str(entry.get("output_artifact") or "").strip() or None,
        )
        if not output_artifact_name.startswith(f"{artifact_basename(filename)}_output."):
            raise ValueError(
                f"Output artifact for {filename} must use canonical _output naming, got: {output_artifact_name}"
            )

        updated_entry = dict(entry)
        updated_entry["output_artifact"] = output_artifact_name
        updated_entry["bytes_in"] = source_path.stat().st_size
        updated_entry["bytes_out"] = output_path.stat().st_size
        updated_entries.append(updated_entry)
        referenced_output_names.add(output_artifact_name)

    for output_path in sorted(artifacts_dir.glob("*_output.*")):
        if output_path.name not in referenced_output_names:
            raise RuntimeError(f"Untracked output artifact found: {output_path.name}")

    return updated_entries


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> list[dict[str, object]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Manifest root must be a JSON list")
    return [dict(item) for item in data]


def render_manifest(entries: list[dict[str, object]]) -> str:
    return json.dumps(entries, ensure_ascii=False, indent=2) + "\n"


def validate_manifest(
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    *,
    tests_dir: Path = DEFAULT_TESTS_DIR,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
) -> list[dict[str, object]]:
    current_entries = load_manifest(manifest_path)
    updated_entries = build_manifest_entries(current_entries, tests_dir=tests_dir, artifacts_dir=artifacts_dir)
    current_rendered = render_manifest(current_entries)
    updated_rendered = render_manifest(updated_entries)
    if current_rendered != updated_rendered:
        raise RuntimeError("Manifest drift detected. Run real_image_manifest.py --write to refresh bytes and output names.")
    return updated_entries


def write_manifest(
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    *,
    tests_dir: Path = DEFAULT_TESTS_DIR,
    artifacts_dir: Path = DEFAULT_ARTIFACTS_DIR,
) -> list[dict[str, object]]:
    entries = build_manifest_entries(load_manifest(manifest_path), tests_dir=tests_dir, artifacts_dir=artifacts_dir)
    manifest_path.write_text(render_manifest(entries), encoding="utf-8")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate or refresh tests/artifacts/real_image_pipeline/manifest.json")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--tests-dir", type=Path, default=DEFAULT_TESTS_DIR)
    parser.add_argument("--artifacts-dir", type=Path, default=DEFAULT_ARTIFACTS_DIR)
    parser.add_argument("--write", action="store_true", help="Rewrite manifest with refreshed bytes and output artifact names")
    args = parser.parse_args()

    if args.write:
        entries = write_manifest(args.manifest, tests_dir=args.tests_dir, artifacts_dir=args.artifacts_dir)
        print(f"Updated manifest entries: {len(entries)}")
        return 0

    entries = validate_manifest(args.manifest, tests_dir=args.tests_dir, artifacts_dir=args.artifacts_dir)
    print(f"Manifest is up to date: {len(entries)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())