import ast
from functools import lru_cache
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
OWNED_KEYS = {
    "processing_outcome",
    "processing_worker",
    "processing_event_queue",
    "processing_stop_event",
    "processing_stop_requested",
    "preparation_worker",
    "preparation_event_queue",
    "latest_source_name",
    "latest_source_token",
    "selected_source_token",
    "latest_image_mode",
    "latest_preparation_summary",
    "prepared_source_key",
    "restart_source",
    "completed_source",
    "persisted_source_cleanup_done",
    "app_start_logged",
    "text_transform_assessment",
    "recommended_text_settings",
    "recommended_text_settings_applied_for_token",
    "recommended_text_settings_applied_snapshot",
    "recommended_text_settings_pending_widget_state",
    "recommended_text_settings_notice_token",
    "recommended_text_settings_notice_details",
    "manual_text_settings_override_for_token",
}


class _SessionStateAccessVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.path = path
        self.findings: list[str] = []
        self.injected_read_findings: list[str] = []
        self.injected_write_findings: list[str] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if _is_st_session_state_attribute(node.value) and node.attr in OWNED_KEYS:
            self._maybe_record(node.attr, node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if _is_st_session_state_get_call(node) and node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str) and first_arg.value in OWNED_KEYS:
                self._maybe_record(first_arg.value, node.lineno)
        if _is_session_state_parameter_get_call(node) and node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str) and first_arg.value in OWNED_KEYS:
                self.injected_read_findings.append(
                    f"{self.path.relative_to(PROJECT_ROOT)}:{node.lineno}: injected session_state read of owned key {first_arg.value!r}"
                )
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        key = _extract_owned_session_state_subscript_key(node)
        if key is None:
            self.generic_visit(node)
            return
        if _is_st_session_state_attribute(node.value):
            self._maybe_record(key, node.lineno)
        elif _is_session_state_parameter_name(node.value):
            self.injected_read_findings.append(
                f"{self.path.relative_to(PROJECT_ROOT)}:{node.lineno}: injected session_state read of owned key {key!r}"
            )
        self.generic_visit(node)

    def _maybe_record(self, key: str, lineno: int) -> None:
        if self.path in OWNER_FILES:
            return
        if (self.path, key) in ALLOWED_RAW_READ_LOCATIONS:
            return
        self.findings.append(f"{self.path.relative_to(PROJECT_ROOT)}:{lineno}: raw session access to owned key {key!r}")

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._maybe_record_injected_write(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._maybe_record_injected_write(node.target)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        for target in node.targets:
            self._maybe_record_injected_write(target)
        self.generic_visit(node)

    def _maybe_record_injected_write(self, target: ast.AST) -> None:
        if isinstance(target, ast.Attribute):
            if not _is_session_state_parameter_name(target.value):
                return
            if target.attr not in OWNED_KEYS:
                return
            self.injected_write_findings.append(
                f"{self.path.relative_to(PROJECT_ROOT)}:{target.lineno}: injected session_state write to owned key {target.attr!r}"
            )
            return
        if isinstance(target, ast.Subscript):
            key = _extract_owned_session_state_subscript_key(target)
            if key is None or not _is_session_state_parameter_name(target.value):
                return
            self.injected_write_findings.append(
                f"{self.path.relative_to(PROJECT_ROOT)}:{target.lineno}: injected session_state write to owned key {key!r}"
            )


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


def _is_session_state_parameter_name(node: ast.AST) -> bool:
    return isinstance(node, ast.Name) and node.id == "session_state"


def _is_session_state_parameter_get_call(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and _is_session_state_parameter_name(node.func.value)
    )


def _extract_owned_session_state_subscript_key(node: ast.Subscript) -> str | None:
    slice_node = node.slice
    if not isinstance(slice_node, ast.Constant) or not isinstance(slice_node.value, str):
        return None
    if slice_node.value not in OWNED_KEYS:
        return None
    return slice_node.value


def _should_scan_python_file(path: Path) -> bool:
    if path.suffix != ".py":
        return False
    relative_parts = path.relative_to(PROJECT_ROOT).parts
    return not any(part in SKIPPED_DIR_NAMES for part in relative_parts[:-1])


def _iter_candidate_python_files():
    for path in sorted(PROJECT_ROOT.rglob("*.py")):
        if not _should_scan_python_file(path):
            continue
        if path.name == "state.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "session_state" not in source:
            continue
        yield path, source


@lru_cache(maxsize=1)
def _collect_session_state_findings_cached() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    raw_access_findings: list[str] = []
    injected_read_findings: list[str] = []
    injected_write_findings: list[str] = []
    for path, source in _iter_candidate_python_files():
        tree = ast.parse(source, filename=str(path))
        visitor = _SessionStateAccessVisitor(path)
        visitor.visit(tree)
        raw_access_findings.extend(visitor.findings)
        injected_read_findings.extend(visitor.injected_read_findings)
        injected_write_findings.extend(visitor.injected_write_findings)
    return tuple(raw_access_findings), tuple(injected_read_findings), tuple(injected_write_findings)


def _collect_session_state_findings() -> tuple[list[str], list[str], list[str]]:
    raw_access_findings, injected_read_findings, injected_write_findings = _collect_session_state_findings_cached()
    return list(raw_access_findings), list(injected_read_findings), list(injected_write_findings)


# The current enforced contract intentionally has no temporary legacy raw-read exceptions.
# Add explicit entries here only for short-lived, review-approved migration seams.
ALLOWED_RAW_READ_LOCATIONS: frozenset[tuple[Path, str]] = frozenset()


def test_p1a_owned_session_keys_are_not_accessed_raw_outside_owner_module() -> None:
    raw_access_findings, _, _ = _collect_session_state_findings()
    assert raw_access_findings == []


def test_p1a_owned_session_keys_are_not_read_via_injected_session_state_parameter() -> None:
    _, injected_read_findings, _ = _collect_session_state_findings()
    assert injected_read_findings == []


def test_p1a_owned_session_keys_are_not_written_via_injected_session_state_parameter() -> None:
    _, _, injected_write_findings = _collect_session_state_findings()
    assert injected_write_findings == []
