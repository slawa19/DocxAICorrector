import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OWNER_FILES = {
    PROJECT_ROOT / "state.py",
}
SKIPPED_DIR_NAMES = {
    ".git",
    ".kilo",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".run",
    ".venv",
    ".venv-win",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "tests",
}
WHITELISTED_READ_LOCATIONS = {
    (PROJECT_ROOT / "application_flow.py", "selected_source_token"),
}
OWNED_KEYS = {
    "processing_outcome",
    "processing_worker",
    "processing_event_queue",
    "processing_stop_event",
    "processing_stop_requested",
    "latest_source_name",
    "latest_source_token",
    "selected_source_token",
    "latest_image_mode",
}


class _SessionStateAccessVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.findings: list[str] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if _is_st_session_state_attribute(node.value) and node.attr in OWNED_KEYS:
            self._maybe_record(node.attr, node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _is_st_session_state_get_call(node) and node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str) and first_arg.value in OWNED_KEYS:
                self._maybe_record(first_arg.value, node.lineno)
        self.generic_visit(node)

    def _maybe_record(self, key: str, lineno: int) -> None:
        if self.path in OWNER_FILES:
            return
        if (self.path, key) in WHITELISTED_READ_LOCATIONS:
            return
        self.findings.append(f"{self.path.relative_to(PROJECT_ROOT)}:{lineno}: raw session access to owned key {key!r}")


def _is_st_session_state_attribute(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "session_state"
        and isinstance(node.value, ast.Name)
        and node.value.id == "st"
    )


def _is_st_session_state_get_call(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and _is_st_session_state_attribute(node.func.value)
    )


def _should_scan_python_file(path: Path) -> bool:
    if path.suffix != ".py":
        return False
    relative_parts = path.relative_to(PROJECT_ROOT).parts
    return not any(part in SKIPPED_DIR_NAMES for part in relative_parts[:-1])


def test_p1a_owned_session_keys_are_not_accessed_raw_outside_owner_or_whitelist() -> None:
    findings: list[str] = []
    for path in sorted(PROJECT_ROOT.rglob("*.py")):
        if not _should_scan_python_file(path):
            continue
        if path.name == "state.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _SessionStateAccessVisitor(path)
        visitor.visit(tree)
        findings.extend(visitor.findings)

    assert findings == []
