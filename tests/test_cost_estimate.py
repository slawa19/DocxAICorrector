"""Spec 069 WP-7: the pure text-stage price estimator (FR-007).

The book estimates of research R3 are reproduced here at the 2026-11-09 list prices; the formulas and
the frozen v1 table are the thing under test, so the table is NOT patched except in the anti-vacuum
proofs, which perturb one coefficient and require the regression to notice.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from docxaicorrector.pipeline import cost_estimate as ce
from docxaicorrector.pipeline.cost_estimate import (
    CoefficientTable,
    EstimateInput,
    PassSpec,
    estimate_text_stages,
    load_coefficient_table,
)
from docxaicorrector.pipeline.price_list import PriceList

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "specs" / "069-translation-modes" / "contracts" / "cost-estimate-snapshot.schema.json"
FLASH_LITE = "google/gemini-3.1-flash-lite-preview"
HAIKU = "anthropic/claude-haiku-5.5"
GEMINI_37 = "google/gemini-3.7-flash"

PRICES_2026_11_09 = PriceList(
    fetched_at="2026-11-09T10:00:00+00:00",
    source="network",
    prices={FLASH_LITE: (0.25, 1.50), HAIKU: (0.10, 0.50), GEMINI_37: (0.75, 3.75)},
)

# Document form of the full books (research R3): LLM jobs J, paragraphs P, source characters C.
BOOKS = {
    "rm": {"llm_job_count": 218, "paragraph_count": 2666, "source_chars": 513842},
    "money": {"llm_job_count": 293, "paragraph_count": 1440, "source_chars": 515837},
}
RESEARCH_USD = {
    ("rm", "standard"): 1.22,
    ("money", "standard"): 1.05,
    ("rm", "quality"): 1.88,
    ("money", "quality"): 1.81,
}


def _passes(mode: str) -> list[PassSpec]:
    if mode == "standard":
        return [
            PassSpec("first", FLASH_LITE, ce.STAGE_GLOSSARY),
            PassSpec("first", FLASH_LITE, ce.STAGE_TEXT),
            PassSpec("polish", HAIKU, ce.STAGE_POLISH),
        ]
    return [
        PassSpec("first", GEMINI_37, ce.STAGE_GLOSSARY, reasoning_effort="low"),
        PassSpec("first", GEMINI_37, ce.STAGE_TEXT, reasoning_effort="low", editorial_intensity="conservative"),
    ]


def _input(book: str, mode: str, **overrides: object) -> EstimateInput:
    fields: dict[str, object] = dict(
        mode=mode,
        passes=_passes(mode),
        source_language="en",
        target_language="ru",
        source_token="tok",
        prepared_source_key="key",
        **BOOKS[book],
    )
    fields.update(overrides)
    return EstimateInput(**fields)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def table() -> CoefficientTable:
    return load_coefficient_table()


# ---------------------------------------------------------------- T7.1 import guard

_FORBIDDEN_ROOTS = ("streamlit", "docxaicorrector.core.model_accounting")


def _forbidden_imports(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = [module] + [f"{module}.{alias.name}" for alias in node.names]
        for name in names:
            if any(name == root or name.startswith(root + ".") for root in _FORBIDDEN_ROOTS):
                found.append(name)
    return found


@pytest.mark.parametrize("module_name", ["cost_estimate", "price_list"])
def test_estimator_modules_do_not_import_streamlit_or_model_accounting(module_name: str) -> None:
    path = REPO_ROOT / "src" / "docxaicorrector" / "pipeline" / f"{module_name}.py"
    assert _forbidden_imports(path.read_text(encoding="utf-8")) == []


def test_import_guard_sees_a_forbidden_import(tmp_path: Path) -> None:
    """Anti-vacuum: the same checker flags every spelling of a forbidden import."""
    bad = tmp_path / "bad.py"
    bad.write_text(
        "import streamlit as st\n"
        "from docxaicorrector.core import model_accounting\n"
        "from docxaicorrector.core.model_accounting import snapshot_run_model_accounting\n",
        encoding="utf-8",
    )
    found = _forbidden_imports(bad.read_text(encoding="utf-8"))
    assert "streamlit" in found
    assert "docxaicorrector.core.model_accounting" in found
    assert len(found) >= 3


# ---------------------------------------------------------------- T7.2 book regression


@pytest.mark.parametrize("book", ["rm", "money"])
def test_quality_estimate_reproduces_research_books(table: CoefficientTable, book: str) -> None:
    estimate = estimate_text_stages(_input(book, "quality"), table, PRICES_2026_11_09)
    assert estimate.total_upper_usd == pytest.approx(RESEARCH_USD[(book, "quality")], rel=0.03)


@pytest.mark.parametrize("book", ["rm", "money"])
def test_standard_estimate_with_mean_ratio_is_within_five_percent_of_research(
    table: CoefficientTable, book: str
) -> None:
    """The table carries the MEAN polish ratio of the two chapters; research R3 priced each book with
    its own chapter's ratio, so the table is off by up to ~3.7 % on the two books (see next test)."""
    estimate = estimate_text_stages(_input(book, "standard"), table, PRICES_2026_11_09)
    assert estimate.total_upper_usd == pytest.approx(RESEARCH_USD[(book, "standard")], rel=0.05)


@pytest.mark.parametrize(
    ("book", "input_ratio", "output_ratio"),
    [("rm", 1.363, 3.291), ("money", 1.248, 2.818)],
)
def test_standard_estimate_with_per_book_polish_ratio_reproduces_research(
    table: CoefficientTable, book: str, input_ratio: float, output_ratio: float
) -> None:
    """Formula regression at the research tolerance (3 %): with the per-chapter polish ratio the
    table's spread records, the formulas return the 1.22 / 1.05 of research R3."""
    rows = tuple(
        dataclasses.replace(row, input_vs_anchor=input_ratio, output_vs_anchor=output_ratio)
        if row.stage == ce.STAGE_POLISH
        else row
        for row in table.ratios
    )
    per_book = dataclasses.replace(table, ratios=rows)
    estimate = estimate_text_stages(_input(book, "standard"), per_book, PRICES_2026_11_09)
    assert estimate.total_upper_usd == pytest.approx(RESEARCH_USD[(book, "standard")], rel=0.03)


def test_regression_is_not_vacuous_a_perturbed_coefficient_leaves_the_tolerance(table: CoefficientTable) -> None:
    perturbed = dataclasses.replace(table, input_per_llm_job=table.input_per_llm_job * 1.15)
    estimate = estimate_text_stages(_input("rm", "quality"), perturbed, PRICES_2026_11_09)
    assert estimate.total_upper_usd is not None
    assert abs(estimate.total_upper_usd - RESEARCH_USD[("rm", "quality")]) / RESEARCH_USD[("rm", "quality")] > 0.03


def test_anchor_stage_formula_matches_the_contract(table: CoefficientTable) -> None:
    data = _input("rm", "standard", passes=[PassSpec("first", FLASH_LITE, ce.STAGE_TEXT)])
    stage = estimate_text_stages(data, table, PRICES_2026_11_09).stages[ce.STAGE_TEXT]
    assert stage.input_tokens == round(3111 * 218 + 1.329 * 513842)
    assert stage.output_tokens == round(48.3 * 2666 + 0.160 * 513842)


def test_glossary_is_a_per_book_constant(table: CoefficientTable) -> None:
    small = estimate_text_stages(
        _input("rm", "standard", llm_job_count=1, paragraph_count=1, source_chars=100,
               passes=[PassSpec("first", FLASH_LITE, ce.STAGE_GLOSSARY)]),
        table, PRICES_2026_11_09,
    ).stages[ce.STAGE_GLOSSARY]
    big = estimate_text_stages(
        _input("rm", "standard", passes=[PassSpec("first", FLASH_LITE, ce.STAGE_GLOSSARY)]),
        table, PRICES_2026_11_09,
    ).stages[ce.STAGE_GLOSSARY]
    assert (small.input_tokens, small.output_tokens) == (big.input_tokens, big.output_tokens) == (31625, 6745)


# ---------------------------------------------------------------- T7.3 bounds, flags, unknowns


def test_discount_scenario_only_for_flash_lite(table: CoefficientTable) -> None:
    standard = estimate_text_stages(_input("rm", "standard"), table, PRICES_2026_11_09)
    for stage in (ce.STAGE_GLOSSARY, ce.STAGE_TEXT):
        item = standard.stages[stage]
        assert item.discount_scenario is not None
        assert item.upper_usd is not None and item.lower_usd is not None
        assert item.lower_usd == pytest.approx(item.upper_usd * 0.762)
    polish = standard.stages[ce.STAGE_POLISH]
    assert polish.discount_scenario is None
    assert polish.lower_usd == polish.upper_usd


def test_lower_equals_upper_for_models_without_an_observed_discount(table: CoefficientTable) -> None:
    quality = estimate_text_stages(_input("money", "quality"), table, PRICES_2026_11_09)
    assert quality.total_lower_usd == quality.total_upper_usd
    assert all(item.discount_scenario is None for item in quality.stages.values())


def test_pair_outside_the_table_is_flagged_extrapolated_not_silently_en_ru(table: CoefficientTable) -> None:
    known = estimate_text_stages(_input("rm", "standard"), table, PRICES_2026_11_09)
    other = estimate_text_stages(_input("rm", "standard", source_language="de", target_language="ru"),
                                 table, PRICES_2026_11_09)
    assert known.extrapolated is False
    assert other.extrapolated is True
    assert other.total_upper_usd is not None  # still estimated, from the nearest row


def test_mismatched_reasoning_effort_is_extrapolated(table: CoefficientTable) -> None:
    passes = [PassSpec("first", GEMINI_37, ce.STAGE_TEXT, reasoning_effort="high", editorial_intensity="conservative")]
    estimate = estimate_text_stages(_input("rm", "quality", passes=passes), table, PRICES_2026_11_09)
    assert estimate.extrapolated is True


def test_without_a_price_list_the_price_is_unknown_not_zero(table: CoefficientTable) -> None:
    estimate = estimate_text_stages(_input("rm", "standard"), table, None)
    assert estimate.total_upper_usd is None and estimate.total_lower_usd is None
    assert all(item.upper_usd is None and item.lower_usd is None for item in estimate.stages.values())
    assert estimate.price_list_date is None
    assert set(estimate.price_unknown_models) == {FLASH_LITE, HAIKU}
    # tokens are still known without a price
    assert estimate.stages[ce.STAGE_TEXT].input_tokens > 0


@pytest.mark.parametrize("native", ["anthropic:claude-haiku-5.5", "openai:gpt-5.4"])
def test_native_provider_models_have_unknown_price(table: CoefficientTable, native: str) -> None:
    prices = PriceList(fetched_at="2026-11-09T10:00:00+00:00", source="cache",
                       prices={**PRICES_2026_11_09.prices, native: (1.0, 1.0)})
    passes = [PassSpec("first", FLASH_LITE, ce.STAGE_TEXT), PassSpec("polish", native, ce.STAGE_POLISH)]
    estimate = estimate_text_stages(_input("rm", "standard", passes=passes), table, prices)
    assert estimate.stages[ce.STAGE_POLISH].upper_usd is None
    assert estimate.stages[ce.STAGE_TEXT].upper_usd is not None
    assert native in estimate.price_unknown_models
    assert estimate.total_upper_usd is None  # never a partial sum shown as the price


def test_model_without_coefficients_is_reported_not_substituted_by_the_anchor(table: CoefficientTable) -> None:
    passes = [PassSpec("first", "vendor/unseen-model", ce.STAGE_TEXT)]
    estimate = estimate_text_stages(_input("rm", "quality", passes=passes), table, PRICES_2026_11_09)
    assert estimate.coefficients_missing == ("vendor/unseen-model:text_generation",)
    assert estimate.total_upper_usd is None
    assert estimate.stages[ce.STAGE_TEXT].input_tokens == 0


def test_duplicate_stage_is_rejected(table: CoefficientTable) -> None:
    passes = [PassSpec("first", FLASH_LITE, ce.STAGE_TEXT), PassSpec("polish", FLASH_LITE, ce.STAGE_TEXT)]
    with pytest.raises(ValueError):
        estimate_text_stages(_input("rm", "standard", passes=passes), table, PRICES_2026_11_09)


def test_estimate_without_network_is_fast(table: CoefficientTable) -> None:
    started = time.perf_counter()
    for _ in range(20):
        estimate_text_stages(_input("rm", "standard"), table, PRICES_2026_11_09)
    assert (time.perf_counter() - started) / 20 < 0.05


# ---------------------------------------------------------------- snapshot vs schema


def _validate(value: object, schema: dict, root: dict, path: str = "$") -> list[str]:
    """Minimal draft-2020-12 subset used by cost-estimate-snapshot.schema.json (no jsonschema dependency)."""
    errors: list[str] = []
    if "$ref" in schema:
        target: object = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            target = target[part]  # type: ignore[index]
        return _validate(value, target, root, path)  # type: ignore[arg-type]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: const {schema['const']!r} != {value!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in enum")
    type_names = schema.get("type")
    if type_names is not None:
        names = type_names if isinstance(type_names, list) else [type_names]
        checks = {
            "object": lambda v: isinstance(v, dict),
            "array": lambda v: isinstance(v, list),
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "null": lambda v: v is None,
        }
        if not any(checks[name](value) for name in names):
            errors.append(f"{path}: {value!r} is not {names}")
            return errors
    if isinstance(value, (int, float)) and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: below minimum")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing {key}")
        properties = schema.get("properties", {})
        for key, item in value.items():
            if key in properties:
                errors += _validate(item, properties[key], root, f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected {key}")
    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append(f"{path}: too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: too many items")
        for index, item in enumerate(value):
            if "items" in schema:
                errors += _validate(item, schema["items"], root, f"{path}[{index}]")
    return errors


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("mode", ["standard", "quality"])
def test_snapshot_is_valid_against_the_contract_schema(table: CoefficientTable, mode: str) -> None:
    estimate = estimate_text_stages(_input("rm", mode), table, PRICES_2026_11_09)
    snapshot = estimate.to_snapshot(created_at=datetime(2026, 11, 9, tzinfo=timezone.utc))
    assert _validate(snapshot, _schema(), _schema()) == []
    assert snapshot["excludes"] == ["images"]
    assert snapshot["coefficients_version"] == "069-v1"
    assert snapshot["price_list_date"] == PRICES_2026_11_09.fetched_at
    assert json.loads(json.dumps(snapshot)) == snapshot


def test_snapshot_without_price_list_is_valid_and_carries_nulls(table: CoefficientTable) -> None:
    snapshot = estimate_text_stages(_input("money", "standard"), table, None).to_snapshot()
    assert _validate(snapshot, _schema(), _schema()) == []
    assert snapshot["price_list_date"] is None and snapshot["total_upper_usd"] is None


def test_schema_validator_is_not_vacuous(table: CoefficientTable) -> None:
    snapshot = estimate_text_stages(_input("rm", "standard"), table, PRICES_2026_11_09).to_snapshot()
    broken = dict(snapshot, excludes=[], surprise=1)
    del broken["mode"]
    errors = _validate(broken, _schema(), _schema())
    assert any("missing mode" in e for e in errors)
    assert any("unexpected surprise" in e for e in errors)
    assert any("too few items" in e for e in errors)
