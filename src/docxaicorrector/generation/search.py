from __future__ import annotations

from pathlib import Path


SEARCH_TERMS = ("gpt-", "gpt-4", "gpt-5", "gpt-image")


def iter_model_string_matches(root: Path) -> list[str]:
    matches: list[str] = []
    for path in sorted(root.glob("*.py")):
        try:
            with path.open(encoding="utf-8") as file:
                for index, line in enumerate(file, 1):
                    if any(term in line for term in SEARCH_TERMS):
                        matches.append(f"{path.name}:{index}:{line.strip()}")
        except OSError as exc:
            matches.append(f"Error {path.name}: {exc}")
    return matches


def main() -> int:
    for match in iter_model_string_matches(Path.cwd()):
        print(match)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
