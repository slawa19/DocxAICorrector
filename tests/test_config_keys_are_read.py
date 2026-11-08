"""Spec 066 FR-012: an app-config key nobody reads, or a read of a key nobody produces, is dead.

Both directions are a rule of form, not a list of keys: the key sets are recomputed from the
code on every run, and only the exceptions below are written down, each with its reason.

**What "produced by the loader" means (direction 1).** The fields of ``core.config.AppConfig``.
``load_app_config`` builds the config as ``AppConfig(**build_app_config_payload(...))``
(``core/config.py::_build_app_config``), so a key the loader emits that is not a field fails at
construction, and a field the loader does not emit keeps only its dataclass default. The field
list is therefore exactly the key set every consumer receives, which makes it a better source
of truth than the payload dict in ``core/config_loader_layers.py`` (same keys, but a dict
literal that a refactor can split across helpers). The fields are read with ``ast`` from the
source, not imported, so the same functions can be pointed at another checkout.

**What "read" means (the heuristic).** In the reader scope, the key counts as read when it
appears as (a) a string subscript index in load context (``cfg["k"]``), (b) a string
positional argument of any call (``cfg.get("k")``, ``getattr(cfg, "k")``,
``_config_int(cfg, "k", 0)``), or (c) an attribute name in load context (``app_config.k``).
Dict-literal keys and subscript stores are productions, not reads. The heuristic leans towards
"read" (an unrelated ``x.chunk_size`` also counts), so a failure here is a real finding, while
a pass is not a proof of use.

**Reader scope.** ``src/docxaicorrector`` minus the loader layers that only parse and assemble
(``core/config_loader_layers.py``, ``config_runtime_sections.py``,
``config_structure_sections.py``, ``config_model_registry.py``) and minus the ``AppConfig``
class body; plus ``tests/artifacts/real_document_pipeline/run_lietaer_validation.py``, the
canonical real-document validation runner that ``scripts/run-real-document-validation.sh``
executes. ``core/config.py`` stays in scope because it hosts the runtime accessors
(``get_client``, ``get_text_model_options``, ...). Tests do not count as readers: a key only a
test reads is exactly the dead key this guard exists for.

**Direction 2 (read of a key nobody produces).** Every literal read ``<recv>.get("k")`` or
``<recv>["k"]`` in ``src/docxaicorrector`` whose receiver is an app config by name
(``*app_config*``, ``config``, ``resolved_config``, ``self.config``) must name a produced key:
an ``AppConfig`` field, a ``ResolvedRuntimeConfig`` field (``validation/profiles.py`` merges its
``to_dict()`` into the run's app config), or a key stored by a literal ``<recv>["k"] = ...`` in
the reader scope (UI runtime overrides, run-profile overrides, the validation runner).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
import logging
from pathlib import Path
import re

import pytest

import docxaicorrector.core.config as config
from docxaicorrector.core import constants
from docxaicorrector.core.config_loader_layers import ReadTrackingConfigData

REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = Path("src") / "docxaicorrector"
_RUNNER = Path("tests") / "artifacts" / "real_document_pipeline" / "run_lietaer_validation.py"
_LOADER_LAYERS = frozenset(
    {
        "core/config_loader_layers.py",
        "core/config_runtime_sections.py",
        "core/config_structure_sections.py",
        "core/config_model_registry.py",
    }
)
_CONFIG_RECEIVER = re.compile(r"(?:^|\.)(?:\w*app_config\w*|resolved_config|config)$")

# Direction 1 exceptions: produced by the loader, read by no one in the reader scope.
UNREAD_ALLOWED: dict[str, str] = {
    "image_vision_model_default": "read through an f-string key, core/config.py get_image_model_choice",
    "image_draw_model_default": "read through an f-string key, core/config.py get_image_model_choice",
    "default_model": "unread flat copy of models.text.default; found by this guard, outside spec 066 scope",
    "model_options": "unread flat copy of models.text.options; found by this guard, outside spec 066 scope",
    "validation_model": "unread flat copy of models.image_validation; found by this guard, outside spec 066 scope",
    "reconstruction_model": "unread flat copy of models.image_reconstruction; found by this guard, outside spec 066 scope",
    "structure_validation_enabled": "C-6, removed by spec 066 P2/P4 — drop this entry when merged",
    "structure_validation_save_debug_artifacts": "C-6, removed by spec 066 P2/P4 — drop this entry when merged",
    "structure_validation_block_on_high_risk_noop": "C-6, removed by spec 066 P2/P4 — drop this entry when merged",
}

# Direction 2 exceptions: read under an app-config receiver name, produced by no one.
UNPRODUCED_ALLOWED: dict[str, str] = {
    "document_context_prompt": "dead fallback in pipeline/setup.py and support.py (the prompt arrives as an "
    "argument, spec 064); found by this guard, those modules are spec 066 P1's",
    "structure_recovery_enabled": "C-1, removed by spec 066 P2/P4 — drop this entry when merged",
    "structure_recovery_mode": "C-1, removed by spec 066 P2/P4 — drop this entry when merged",
    "structure_recognition_model": "C-8, removed by spec 066 P2/P4 — drop this entry when merged",
    "structure_recognition_mode": "C-6 (dead debug writer), removed by spec 066 P2/P4 — drop this entry when merged",
    "image_model_call_budget_per_document": "C-12, removed by spec 066 P2/P4 — drop this entry when merged",
    "semantic_redraw_max_model_calls_per_document": "C-12, removed by spec 066 P2/P4 — drop this entry when merged",
}


# Functions whose local ``config`` is not an app config, so the receiver-name heuristic of
# direction 2 does not apply inside them.
NOT_APP_CONFIG_SCOPES: dict[tuple[str, str], str] = {
    ("image/reconstruction.py", "_resolve_render_config"): "``config`` is the reconstruction render config",
}


def _dataclass_fields(source: Path, class_name: str) -> set[str]:
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                statement.target.id
                for statement in node.body
                if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
            }
    raise AssertionError(f"{class_name} not found in {source}")


def loader_keys(root: Path) -> set[str]:
    return _dataclass_fields(root / _PACKAGE / "core" / "config.py", "AppConfig")


def runtime_keys(root: Path) -> set[str]:
    return _dataclass_fields(root / _PACKAGE / "validation" / "profiles.py", "ResolvedRuntimeConfig")


def _reader_modules(root: Path) -> Iterator[tuple[str, ast.Module]]:
    for path in sorted((root / _PACKAGE).rglob("*.py")):
        relative = path.relative_to(root / _PACKAGE).as_posix()
        if relative in _LOADER_LAYERS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if relative == "core/config.py":
            tree.body = [
                node for node in tree.body if not (isinstance(node, ast.ClassDef) and node.name == "AppConfig")
            ]
        yield relative, tree
    runner = root / _RUNNER
    if runner.exists():
        yield _RUNNER.as_posix(), ast.parse(runner.read_text(encoding="utf-8"))


def _string(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _read_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
            key = _string(node.slice)
            if key:
                names.add(key)
        elif isinstance(node, ast.Call):
            for argument in node.args:
                key = _string(argument)
                if key:
                    names.add(key)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            names.add(node.attr)
    return names


def _is_config_receiver(node: ast.AST) -> bool:
    return bool(_CONFIG_RECEIVER.search(ast.unparse(node)))


def _config_key_stores(tree: ast.AST) -> set[str]:
    stored: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store) and _is_config_receiver(node.value):
            key = _string(node.slice)
            if key:
                stored.add(key)
    return stored


def _config_key_reads(relative: str, tree: ast.AST) -> Iterator[tuple[str, int]]:
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (relative, node.name) in NOT_APP_CONFIG_SCOPES:
            skipped.update(id(inner) for inner in ast.walk(node))
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and _is_config_receiver(node.func.value)
        ):
            key = _string(node.args[0])
            if key:
                yield key, node.lineno
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) and _is_config_receiver(node.value):
            key = _string(node.slice)
            if key:
                yield key, node.lineno


def unread_loader_keys(root: Path) -> set[str]:
    read: set[str] = set()
    for _, tree in _reader_modules(root):
        read |= _read_names(tree)
    return loader_keys(root) - read


def unproduced_reads(root: Path) -> dict[str, list[str]]:
    modules = list(_reader_modules(root))
    produced = loader_keys(root) | runtime_keys(root)
    for _, tree in modules:
        produced |= _config_key_stores(tree)
    findings: dict[str, list[str]] = {}
    for relative, tree in modules:
        if relative == _RUNNER.as_posix():
            continue
        for key, lineno in _config_key_reads(relative, tree):
            if key not in produced:
                findings.setdefault(key, []).append(f"{relative}:{lineno}")
    return findings


def test_every_loader_key_is_read_somewhere() -> None:
    unread = unread_loader_keys(REPO_ROOT) - set(UNREAD_ALLOWED)
    assert not unread, (
        "app-config keys produced by the loader but read nowhere outside the loader layers "
        f"(spec 066 FR-012): {sorted(unread)}. Delete the key with its parser and config.toml "
        "line, or add it to UNREAD_ALLOWED with the reason it must stay."
    )


def test_every_literal_app_config_read_names_a_produced_key() -> None:
    unproduced = {key: sites for key, sites in unproduced_reads(REPO_ROOT).items() if key not in UNPRODUCED_ALLOWED}
    assert not unproduced, (
        "literal app-config reads of keys that no loader, runtime layer or override produces "
        f"(spec 066 FR-012): {unproduced}. The branch behind such a read is dead in the product."
    )


def test_allow_lists_carry_reasons_and_name_live_findings() -> None:
    # An exception without a reason is a silent skip; an exception for a key that is no
    # longer a finding is a stale one and hides the next regression with the same name.
    for name, allowed, live in (
        ("UNREAD_ALLOWED", UNREAD_ALLOWED, unread_loader_keys(REPO_ROOT)),
        ("UNPRODUCED_ALLOWED", UNPRODUCED_ALLOWED, set(unproduced_reads(REPO_ROOT))),
    ):
        assert all(reason.strip() for reason in allowed.values()), name
        stale = sorted(set(allowed) - live)
        assert not stale, f"{name} lists keys that are no longer findings: {stale}"


def _load_capturing(monkeypatch: pytest.MonkeyPatch, config_path: Path) -> tuple[object, list[tuple[int, str, dict]], list]:
    events: list[tuple[int, str, dict]] = []
    loaded: list[ReadTrackingConfigData] = []
    original_load_config_data = config.load_config_data

    def _recording_load_config_data(**kwargs):
        data = original_load_config_data(**kwargs)
        loaded.append(data)
        return data

    monkeypatch.setattr(config, "CONFIG_PATH", config_path)
    monkeypatch.setattr(config, "load_config_data", _recording_load_config_data)
    monkeypatch.setattr(
        config,
        "log_event",
        lambda level, event_id, message, **context: events.append((level, event_id, context)),
    )
    config._EMITTED_MODEL_REGISTRY_LOG_KEYS.clear()
    config.reset_app_config_cache()
    try:
        app_config = config.load_app_config()
    finally:
        config.reset_app_config_cache()
    return app_config, events, loaded


def test_top_level_config_key_no_resolver_reads_is_reported_as_ignored(monkeypatch, tmp_path) -> None:
    # The other half of FR-012, for a user's own config.toml: a removed key left there must
    # be named in a WARNING, not silently accepted. The known set is whatever the resolvers
    # read, so the test needs only keys no resolver asks for next to one that it does.
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "chunk_size = 5000\n"
        'spec_066_never_read_key = "x"\n\n'
        "[spec_066_never_read_table]\nvalue = 1\n\n"
        '[models.text]\ndefault = "gpt-5.4-mini"\noptions = ["gpt-5.4-mini"]\n',
        encoding="utf-8",
    )

    app_config, events, _ = _load_capturing(monkeypatch, config_path)

    assert app_config["chunk_size"] == 5000
    ignored = [(level, context) for level, event_id, context in events if event_id == "config_key_ignored"]
    assert ignored == [
        (
            logging.WARNING,
            {
                "config_path": str(config_path),
                "ignored_keys": ["spec_066_never_read_key", "spec_066_never_read_table"],
            },
        )
    ]


def test_shipped_config_toml_has_no_ignored_keys(monkeypatch) -> None:
    # Anti-vacuum for the rule above: the tracking must not flag what the loader does read.
    _, events, loaded = _load_capturing(monkeypatch, constants.CONFIG_PATH)

    assert loaded and len(loaded[-1]) > 5
    assert loaded[-1].ignored_keys() == []
    assert not [event_id for _, event_id, _ in events if event_id == "config_key_ignored"]
