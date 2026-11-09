"""Price estimate of the text stages of a run (spec 069 FR-007, contracts/cost-estimate.md).

Pure: no network, no Streamlit, no ``model_accounting`` (the estimate never feeds the accounting;
the snapshot it produces lives in ``app_config["cost_estimate_snapshot"]``, the result bundle and
the runner report). Images are out of scope and the snapshot says so (``excludes: ["images"]``).

Method (research R3): the anchor is the first-pass model of ``single`` (flash-lite, en->ru,
``text_generation``) fitted on the document form known at upload (LLM jobs ``J``, paragraphs ``P``,
source characters ``C``); every other model/stage is a ratio to the anchor; the glossary is a
per-book constant. Upper bound = list price; lower bound = the model's observed discount scenario
(only flash-lite has one), otherwise lower == upper. No self-calibration in v1 (spec Non-goals).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from docxaicorrector.core.constants import RESOURCE_ROOT
from docxaicorrector.pipeline.price_list import PriceList

SCHEMA_VERSION = 1
COEFFICIENTS_PATH = RESOURCE_ROOT / "cost_estimate_coefficients.json"

STAGE_GLOSSARY = "glossary_extraction"
STAGE_TEXT = "text_generation"
STAGE_POLISH = "literary_polish"
STAGES = (STAGE_GLOSSARY, STAGE_TEXT, STAGE_POLISH)

_OVER = " over "


def pair_key(source_language: str, target_language: str) -> str:
    return f"{(source_language or '').strip().lower()}->{(target_language or '').strip().lower()}"


@dataclass(frozen=True)
class RatioRow:
    model: str
    stage: str
    language_pair: str
    input_vs_anchor: float
    output_vs_anchor: float
    reasoning_effort: str | None = None
    editorial_intensity: str | None = None
    provenance: str = ""

    @property
    def document_pair(self) -> str:
        """``"ru->ru over en->ru"`` (a polish row) applies to documents of the pair after ``over``."""
        return self.language_pair.split(_OVER, 1)[1] if _OVER in self.language_pair else self.language_pair


@dataclass(frozen=True)
class DiscountScenario:
    model: str
    lower_bound_factor: tuple[float, ...]
    label: str

    @property
    def factor(self) -> float:
        return min(self.lower_bound_factor)


@dataclass(frozen=True)
class CoefficientTable:
    version: str
    anchor_model: str
    anchor_pair: str
    input_per_llm_job: float
    input_per_source_char: float
    output_per_paragraph: float
    output_per_source_char: float
    glossary_model: str
    glossary_input_tokens: float
    glossary_output_tokens: float
    ratios: tuple[RatioRow, ...]
    discounts: tuple[DiscountScenario, ...]

    def discount_for(self, model: str) -> DiscountScenario | None:
        for scenario in self.discounts:
            if scenario.model == model:
                return scenario
        return None


def load_coefficient_table(path: Path | None = None) -> CoefficientTable:
    raw: dict[str, Any] = json.loads((path or COEFFICIENTS_PATH).read_text(encoding="utf-8"))
    anchor = raw["anchor"]
    glossary = raw["glossary"]
    ratios = tuple(
        RatioRow(
            model=str(row["model"]),
            stage=str(row["stage"]),
            language_pair=str(row["language_pair"]),
            input_vs_anchor=float(row["input_vs_anchor"]),
            output_vs_anchor=float(row["output_vs_anchor"]),
            reasoning_effort=row.get("reasoning_effort"),
            editorial_intensity=row.get("editorial_intensity"),
            provenance=str(row.get("provenance", "")),
        )
        for row in raw.get("ratios", [])
    )
    discounts = tuple(
        DiscountScenario(
            model=str(row["model"]),
            lower_bound_factor=tuple(float(value) for value in row["lower_bound_factor"]),
            label=str(row["label"]),
        )
        for row in raw.get("discount_scenarios", [])
    )
    return CoefficientTable(
        version=str(raw["version"]),
        anchor_model=str(anchor["model"]),
        anchor_pair=str(anchor["language_pair"]),
        input_per_llm_job=float(anchor["input_tokens"]["per_llm_job"]),
        input_per_source_char=float(anchor["input_tokens"]["per_source_char"]),
        output_per_paragraph=float(anchor["output_tokens"]["per_paragraph"]),
        output_per_source_char=float(anchor["output_tokens"]["per_source_char"]),
        glossary_model=str(glossary["model"]),
        glossary_input_tokens=float(glossary["per_book"]["input_tokens"]),
        glossary_output_tokens=float(glossary["per_book"]["output_tokens"]),
        ratios=ratios,
        discounts=discounts,
    )


@dataclass(frozen=True)
class PassSpec:
    """One priced pass of a mode: ``pass_kind`` is ``first`` or ``polish`` (snapshot ``passes[].pass``)."""

    pass_kind: str
    model: str
    stage: str
    reasoning_effort: str | None = None
    editorial_intensity: str | None = None


@dataclass(frozen=True)
class EstimateInput:
    mode: str
    passes: Sequence[PassSpec]
    llm_job_count: int
    paragraph_count: int
    source_chars: int
    source_language: str
    target_language: str
    source_token: str = ""
    prepared_source_key: str | None = None


@dataclass(frozen=True)
class StageEstimate:
    model: str
    input_tokens: int
    output_tokens: int
    upper_usd: float | None
    lower_usd: float | None
    discount_scenario: str | None


@dataclass(frozen=True)
class CostEstimate:
    mode: str
    coefficients_version: str
    price_list_date: str | None
    price_list_source: str | None
    stages: Mapping[str, StageEstimate]
    total_upper_usd: float | None
    total_lower_usd: float | None
    extrapolated: bool
    price_unknown_models: tuple[str, ...]
    coefficients_missing: tuple[str, ...]
    passes: tuple[PassSpec, ...]
    document: Mapping[str, Any] = field(default_factory=dict)
    excludes: tuple[str, ...] = ("images",)

    @property
    def price_known(self) -> bool:
        return self.total_upper_usd is not None

    def to_snapshot(self, created_at: datetime | None = None) -> dict[str, Any]:
        """Dict valid against ``contracts/cost-estimate-snapshot.schema.json``."""
        moment = created_at or datetime.now(timezone.utc)
        snapshot: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "mode": self.mode,
            "passes": [
                {
                    "pass": spec.pass_kind,
                    "model": spec.model,
                    "stage": spec.stage,
                    "reasoning_effort": spec.reasoning_effort,
                    "editorial_intensity": spec.editorial_intensity,
                }
                for spec in self.passes
            ],
            "coefficients_version": self.coefficients_version,
            "price_list_date": self.price_list_date,
            "price_list_source": self.price_list_source,
            "document": dict(self.document),
            "stages": {
                stage: {
                    "model": item.model,
                    "input_tokens": item.input_tokens,
                    "output_tokens": item.output_tokens,
                    "upper_usd": item.upper_usd,
                    "lower_usd": item.lower_usd,
                    "discount_scenario": item.discount_scenario,
                }
                for stage, item in self.stages.items()
            },
            "total_upper_usd": self.total_upper_usd,
            "total_lower_usd": self.total_lower_usd,
            "excludes": list(self.excludes),
            "extrapolated": self.extrapolated,
            "price_unknown_models": list(self.price_unknown_models),
            "created_at": moment.isoformat(),
        }
        return snapshot


def _select_row(
    table: CoefficientTable, spec: PassSpec, document_pair: str
) -> tuple[RatioRow | None, bool]:
    """Best row for (model, stage); the flag says the match was not exact (pair, effort or intensity)."""
    candidates = [row for row in table.ratios if row.model == spec.model and row.stage == spec.stage]
    if not candidates:
        return None, False

    def mismatch(row: RatioRow) -> tuple[bool, bool, bool]:
        return (
            row.document_pair != document_pair,
            row.reasoning_effort is not None and row.reasoning_effort != spec.reasoning_effort,
            row.editorial_intensity is not None and row.editorial_intensity != spec.editorial_intensity,
        )

    best = min(candidates, key=lambda row: (sum(mismatch(row)), mismatch(row)))
    return best, any(mismatch(best))


def _stage_tokens(
    table: CoefficientTable, spec: PassSpec, data: EstimateInput, document_pair: str
) -> tuple[float, float, bool] | None:
    """(input_tokens, output_tokens, extrapolated) for one pass, or None when the table has no row."""
    anchor_in = table.input_per_llm_job * data.llm_job_count + table.input_per_source_char * data.source_chars
    anchor_out = table.output_per_paragraph * data.paragraph_count + table.output_per_source_char * data.source_chars
    row, inexact = _select_row(table, spec, document_pair)
    anchor_pair_mismatch = document_pair != table.anchor_pair

    if spec.stage == STAGE_GLOSSARY:
        base_in, base_out = table.glossary_input_tokens, table.glossary_output_tokens
        if row is None:
            if spec.model != table.glossary_model:
                return None
            return base_in, base_out, anchor_pair_mismatch
        return base_in * row.input_vs_anchor, base_out * row.output_vs_anchor, inexact or anchor_pair_mismatch

    if row is None:
        if spec.stage == STAGE_TEXT and spec.model == table.anchor_model:
            return anchor_in, anchor_out, anchor_pair_mismatch
        return None
    return anchor_in * row.input_vs_anchor, anchor_out * row.output_vs_anchor, inexact or anchor_pair_mismatch


def estimate_text_stages(
    data: EstimateInput, table: CoefficientTable, price_list: PriceList | None
) -> CostEstimate:
    """Estimate the text stages of ``data.passes``. Never raises on missing prices or coefficients:
    a stage without a price has ``upper_usd=None`` (price unknown, not zero), and so does the total."""
    document_pair = pair_key(data.source_language, data.target_language)
    stages: dict[str, StageEstimate] = {}
    price_unknown: list[str] = []
    coefficients_missing: list[str] = []
    extrapolated = False

    for spec in data.passes:
        if spec.stage not in STAGES:
            raise ValueError(f"unknown estimate stage: {spec.stage!r}")
        if spec.stage in stages:
            raise ValueError(f"two passes price the same stage: {spec.stage!r}")
        tokens = _stage_tokens(table, spec, data, document_pair)
        if tokens is None:
            coefficients_missing.append(f"{spec.model}:{spec.stage}")
            if spec.model not in price_unknown:
                price_unknown.append(spec.model)
            stages[spec.stage] = StageEstimate(spec.model, 0, 0, None, None, None)
            continue
        tokens_in, tokens_out, stage_extrapolated = tokens
        extrapolated = extrapolated or stage_extrapolated
        price = price_list.price_for(spec.model) if price_list is not None else None
        scenario = table.discount_for(spec.model)
        if price is None:
            if spec.model not in price_unknown:
                price_unknown.append(spec.model)
            upper = lower = None
        else:
            upper = tokens_in * price[0] / 1e6 + tokens_out * price[1] / 1e6
            lower = upper * scenario.factor if scenario is not None else upper
        stages[spec.stage] = StageEstimate(
            model=spec.model,
            input_tokens=round(tokens_in),
            output_tokens=round(tokens_out),
            upper_usd=upper,
            lower_usd=lower,
            discount_scenario=scenario.label if scenario is not None else None,
        )

    all_priced = bool(stages) and all(item.upper_usd is not None for item in stages.values())
    total_upper = sum(item.upper_usd or 0.0 for item in stages.values()) if all_priced else None
    total_lower = sum(item.lower_usd or 0.0 for item in stages.values()) if all_priced else None
    return CostEstimate(
        mode=data.mode,
        coefficients_version=table.version,
        price_list_date=price_list.fetched_at if price_list is not None else None,
        price_list_source=price_list.source if price_list is not None else None,
        stages=stages,
        total_upper_usd=total_upper,
        total_lower_usd=total_lower,
        extrapolated=extrapolated,
        price_unknown_models=tuple(price_unknown),
        coefficients_missing=tuple(coefficients_missing),
        passes=tuple(data.passes),
        document={
            "source_token": data.source_token,
            "prepared_source_key": data.prepared_source_key,
            "llm_job_count": data.llm_job_count,
            "paragraph_count": data.paragraph_count,
            "source_chars": data.source_chars,
            "source_language": data.source_language,
            "target_language": data.target_language,
        },
    )
