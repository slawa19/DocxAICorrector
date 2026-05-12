import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_SURFACES = (
    PROJECT_ROOT / "src" / "docxaicorrector" / "image",
    PROJECT_ROOT / "src" / "docxaicorrector" / "processing",
    PROJECT_ROOT / "src" / "docxaicorrector" / "pipeline",
    PROJECT_ROOT / "src" / "docxaicorrector" / "validation",
    PROJECT_ROOT / "src" / "docxaicorrector" / "ui",
    PROJECT_ROOT / "tests" / "artifacts" / "real_document_pipeline" / "run_lietaer_validation.py",
)
# Explicitly allowed locations for canonical model literals that should not be
# treated as runtime drift: config defaults, docs/examples, and test fixtures.
MODEL_LITERAL_ALLOWLIST = (
    PROJECT_ROOT / "config.toml",
    PROJECT_ROOT / "docs",
    PROJECT_ROOT / "tests",
)
FORBIDDEN_MODEL_LITERALS = {
    "gpt-5.4",
    "gpt-5.4-mini",
    "gpt-5-mini",
    "gpt-4.1-mini",
    "gpt-4.1",
    "gpt-4o-mini",
    "gpt-image-1",
}


def _is_allowlisted_model_literal_path(path: Path) -> bool:
    return any(path == allowed_path or allowed_path in path.parents for allowed_path in MODEL_LITERAL_ALLOWLIST)


def _iter_runtime_modules() -> list[Path]:
    modules: list[Path] = []
    for surface in RUNTIME_SURFACES:
        if surface.is_dir():
            modules.extend(
                sorted(
                    path
                    for path in surface.rglob("*.py")
                    if path.name != "__init__.py"
                    and not _is_allowlisted_model_literal_path(path)
                )
            )
            continue
        if not _is_allowlisted_model_literal_path(surface):
            modules.append(surface)
    return modules


def _collect_forbidden_string_literals(path: Path) -> list[tuple[int, str]]:
    tree = _annotate_parents(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if (
                node.value in FORBIDDEN_MODEL_LITERALS
                and not isinstance(getattr(node, "parent", None), ast.Set)
            ):
                findings.append((getattr(node, "lineno", 0), node.value))
    return findings


def _annotate_parents(tree: ast.AST) -> ast.AST:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent  # type: ignore[attr-defined]
    return tree


def test_runtime_modules_do_not_define_canonical_model_literals() -> None:
    findings = {
        str(path.relative_to(PROJECT_ROOT)): _collect_forbidden_string_literals(path)
        for path in _iter_runtime_modules()
    }
    findings = {path: matches for path, matches in findings.items() if matches}

    assert findings == {}
