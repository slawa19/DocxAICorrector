import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_MODULES = (
    PROJECT_ROOT / "image_generation.py",
    PROJECT_ROOT / "image_analysis.py",
    PROJECT_ROOT / "image_validation.py",
    PROJECT_ROOT / "image_reconstruction.py",
    PROJECT_ROOT / "image_pipeline.py",
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
        for path in RUNTIME_MODULES
    }
    findings = {path: matches for path, matches in findings.items() if matches}

    assert findings == {}
