"""Spec 069 WP-3: reasoning/cache fields, ``literary_polish`` stage, ``pass_counter_scope``.

Part A (``Test*Golden``) pins the pre-069 output on existing stages; it must stay green
before and after the change. Parts B (everything else) must fail on the pre-069 module.
"""

from __future__ import annotations

import pytest

from docxaicorrector.core import model_accounting as ma

LEGACY_STAGE_KEYS = {
    "model_call_count",
    "model_calls_with_usage",
    "model_calls_without_usage",
    "model_calls_without_cost",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_usd_reported_by_provider",
}

LEGACY_USAGE_FIELDS = (
    "usage_reported",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cost_reported",
    "cost_usd",
)


def _responses(**extra: object) -> dict[str, object]:
    return {"usage": {"input_tokens": 100, "output_tokens": 40, "total_tokens": 140, **extra}}


def _chat(**extra: object) -> dict[str, object]:
    return {"usage": {"prompt_tokens": 200, "completion_tokens": 50, "cost": 0.01, **extra}}


def _legacy(stage_dict: dict[str, object]) -> dict[str, object]:
    return {key: stage_dict[key] for key in LEGACY_STAGE_KEYS}


# ---------------------------------------------------------------- A. golden


class TestLegacyUsageGolden:
    def test_responses_usage_snapshot(self) -> None:
        usage = ma.extract_model_call_usage(_responses())
        assert {name: getattr(usage, name) for name in LEGACY_USAGE_FIELDS} == {
            "usage_reported": True,
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "total_tokens": 140,
            "cost_reported": False,
            "cost_usd": 0.0,
        }

    def test_chat_usage_snapshot_derives_total(self) -> None:
        usage = ma.extract_model_call_usage(_chat())
        assert {name: getattr(usage, name) for name in LEGACY_USAGE_FIELDS} == {
            "usage_reported": True,
            "prompt_tokens": 200,
            "completion_tokens": 50,
            "total_tokens": 250,
            "cost_reported": True,
            "cost_usd": 0.01,
        }

    def test_no_usage_is_unreported(self) -> None:
        usage = ma.extract_model_call_usage({})
        assert (usage.usage_reported, usage.total_tokens, usage.cost_reported) == (False, 0, False)

    def test_existing_stages_stage_dicts(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            ma.record_model_call_usage(stage=ma.STAGE_TEXT_GENERATION, response=_responses())
            ma.record_model_call_usage(stage=ma.STAGE_TEXT_GENERATION, response=_chat())
            ma.record_model_call_usage(stage=ma.STAGE_GLOSSARY_EXTRACTION, response={})
            snapshot = ma.snapshot_run_model_accounting()
        stages = snapshot["stages"]
        assert isinstance(stages, dict)
        assert sorted(stages) == ["glossary_extraction", "text_generation"]
        assert _legacy(stages["text_generation"]) == {
            "model_call_count": 2,
            "model_calls_with_usage": 2,
            "model_calls_without_usage": 0,
            "model_calls_without_cost": 1,
            "prompt_tokens": 300,
            "completion_tokens": 90,
            "total_tokens": 390,
            "cost_usd_reported_by_provider": 0.01,
        }
        assert _legacy(stages["glossary_extraction"]) == {
            "model_call_count": 1,
            "model_calls_with_usage": 0,
            "model_calls_without_usage": 1,
            "model_calls_without_cost": 1,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd_reported_by_provider": 0.0,
        }
        assert snapshot["model_call_count"] == 3
        assert snapshot["total_tokens"] == 390
        assert snapshot["token_accounting_complete"] is False
        assert snapshot["cost_accounting_complete"] is False


class TestCounterGolden:
    def test_counters_without_scope_land_in_run_totals(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            ma.record_paragraph_disposition(status="accepted", count=3)
            ma.record_retry_attempt(reason="x", paragraph_count=2, first_retry_for_block=True)
            ma.record_text_api_path("responses")
            snapshot = ma.snapshot_run_model_accounting()
        assert snapshot["paragraph_disposition_counts"] == {
            "accepted": 3,
            "omitted": 0,
            "retry_required": 0,
            "source_restored": 0,
        }
        assert snapshot["retry_attempt_count"] == 1
        assert snapshot["api_path_counts"] == {"responses": 1}


# ---------------------------------------------------------------- B. reasoning


class TestReasoningTokens:
    def test_responses_reads_output_tokens_details(self) -> None:
        usage = ma.extract_model_call_usage(_responses(output_tokens_details={"reasoning_tokens": 25}))
        assert usage.reasoning_tokens == 25

    def test_chat_reads_completion_tokens_details(self) -> None:
        usage = ma.extract_model_call_usage(_chat(completion_tokens_details={"reasoning_tokens": 7}))
        assert usage.reasoning_tokens == 7

    def test_attribute_style_response_object(self) -> None:
        class Obj:
            pass

        details = Obj()
        details.reasoning_tokens = 11  # type: ignore[attr-defined]
        usage_obj = Obj()
        usage_obj.input_tokens = 5  # type: ignore[attr-defined]
        usage_obj.output_tokens = 6  # type: ignore[attr-defined]
        usage_obj.output_tokens_details = details  # type: ignore[attr-defined]
        response = Obj()
        response.usage = usage_obj  # type: ignore[attr-defined]
        assert ma.extract_model_call_usage(response).reasoning_tokens == 11

    def test_absent_field_is_none_not_zero_and_counts_unreported(self) -> None:
        usage = ma.extract_model_call_usage(_responses())
        assert usage.reasoning_tokens is None  # anti-vacuum: a substituted 0 fails here
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            ma.record_model_call_usage(stage=ma.STAGE_TEXT_GENERATION, response=_responses())
            stage = ma.snapshot_run_model_accounting()["stages"]["text_generation"]  # type: ignore[index]
        assert stage["reasoning_unreported_call_count"] == 1
        assert stage["reasoning_reported_call_count"] == 0

    def test_reported_zero_is_a_reported_zero(self) -> None:
        usage = ma.extract_model_call_usage(_responses(output_tokens_details={"reasoning_tokens": 0}))
        assert usage.reasoning_tokens == 0
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            ma.record_model_call_usage(
                stage=ma.STAGE_TEXT_GENERATION,
                response=_responses(output_tokens_details={"reasoning_tokens": 0}),
            )
            stage = ma.snapshot_run_model_accounting()["stages"]["text_generation"]  # type: ignore[index]
        assert stage["reasoning_reported_call_count"] == 1
        assert stage["reasoning_unreported_call_count"] == 0

    def test_stage_sums_known_values_and_counts_both_kinds(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            for response in (
                _responses(output_tokens_details={"reasoning_tokens": 10}),
                _chat(completion_tokens_details={"reasoning_tokens": 5}),
                _responses(),
            ):
                ma.record_model_call_usage(stage=ma.STAGE_TEXT_GENERATION, response=response)
            stage = ma.snapshot_run_model_accounting()["stages"]["text_generation"]  # type: ignore[index]
        assert stage["reasoning_tokens"] == 15
        assert stage["reasoning_reported_call_count"] == 2
        assert stage["reasoning_unreported_call_count"] == 1

    def test_call_without_usage_is_reasoning_unreported(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            ma.record_model_call_usage(stage=ma.STAGE_TEXT_GENERATION, response={})
            stage = ma.snapshot_run_model_accounting()["stages"]["text_generation"]  # type: ignore[index]
        assert stage["reasoning_unreported_call_count"] == 1


# ---------------------------------------------------------------- B. cache


class TestCacheFields:
    def test_responses_cached_tokens(self) -> None:
        usage = ma.extract_model_call_usage(_responses(input_tokens_details={"cached_tokens": 64}))
        assert usage.cached_tokens == 64
        assert usage.cache_write_tokens is None
        assert usage.cache_discount_usd is None

    def test_chat_cache_fields_as_given(self) -> None:
        usage = ma.extract_model_call_usage(
            _chat(
                prompt_tokens_details={"cached_tokens": 128, "cache_write_tokens": 32},
                cache_discount=0.002,
            )
        )
        assert (usage.cached_tokens, usage.cache_write_tokens, usage.cache_discount_usd) == (128, 32, 0.002)

    def test_negative_cache_discount_is_kept_as_reported(self) -> None:
        usage = ma.extract_model_call_usage(_chat(cache_discount=-0.001))
        assert usage.cache_discount_usd == -0.001

    def test_stage_sums_and_counts_reporting_calls_only(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            ma.record_model_call_usage(
                stage=ma.STAGE_TEXT_GENERATION,
                response=_chat(prompt_tokens_details={"cached_tokens": 100, "cache_write_tokens": 10}, cache_discount=0.5),
            )
            ma.record_model_call_usage(
                stage=ma.STAGE_TEXT_GENERATION,
                response=_responses(input_tokens_details={"cached_tokens": 20}),
            )
            ma.record_model_call_usage(stage=ma.STAGE_TEXT_GENERATION, response=_responses())
            stage = ma.snapshot_run_model_accounting()["stages"]["text_generation"]  # type: ignore[index]
        assert stage["cached_tokens"] == 120
        assert stage["cache_write_tokens"] == 10
        assert stage["cache_discount_usd"] == 0.5
        assert stage["cache_fields_reported_call_count"] == 2

    def test_absent_cache_fields_do_not_count_as_reported(self) -> None:
        usage = ma.extract_model_call_usage(_responses())
        assert (usage.cached_tokens, usage.cache_write_tokens, usage.cache_discount_usd) == (None, None, None)
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            ma.record_model_call_usage(stage=ma.STAGE_TEXT_GENERATION, response=_responses())
            stage = ma.snapshot_run_model_accounting()["stages"]["text_generation"]  # type: ignore[index]
        assert stage["cache_fields_reported_call_count"] == 0


# ---------------------------------------------------------------- B. stage


class TestLiteraryPolishStage:
    def test_stage_is_separate_from_text_generation(self) -> None:
        assert ma.STAGE_LITERARY_POLISH == "literary_polish"
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            ma.record_model_call_usage(stage=ma.STAGE_TEXT_GENERATION, response=_responses())
            ma.record_model_call_usage(stage=ma.STAGE_LITERARY_POLISH, response=_chat())
            stages = ma.snapshot_run_model_accounting()["stages"]
        assert isinstance(stages, dict)
        assert set(stages) == {"text_generation", "literary_polish"}
        assert stages["text_generation"]["total_tokens"] == 140
        assert stages["literary_polish"]["total_tokens"] == 250


# ---------------------------------------------------------------- B. pass scope


def _polish_section(snapshot: dict[str, object]) -> dict[str, object]:
    section = snapshot["literary_polish"]
    assert isinstance(section, dict)
    generator = section["generator_counters"]
    assert isinstance(generator, dict)
    return generator


class TestPassCounterScope:
    def test_counters_inside_scope_go_to_section_not_totals(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            ma.record_paragraph_disposition(status="accepted", count=2)
            with ma.pass_counter_scope("literary_polish"):
                ma.record_paragraph_disposition(status="omitted", count=4)
                ma.record_retry_attempt(reason="polish", paragraph_count=1, first_retry_for_block=True)
                ma.record_text_api_path("chat_completions")
                ma.record_text_removal(site="polish_trim", chars=9, emptied_units=1)
                ma.record_model_output_discarded(reason="d", paragraph_count=3, block_count=1)
            snapshot = ma.snapshot_run_model_accounting()
        # run-wide counters are exactly what was recorded OUTSIDE the scope
        assert snapshot["paragraph_disposition_counts"]["omitted"] == 0  # type: ignore[index]
        assert snapshot["paragraph_disposition_counts"]["accepted"] == 2  # type: ignore[index]
        assert snapshot["retry_attempt_count"] == 0
        assert snapshot["api_path_counts"] == {}
        assert snapshot["text_removal_chars"] == 0
        assert snapshot["model_output_discarded_block_count"] == 0
        generator = _polish_section(snapshot)
        assert generator["paragraph_disposition_counts"]["omitted"] == 4  # type: ignore[index]
        assert generator["retry_attempt_count"] == 1
        assert generator["retried_block_count"] == 1
        assert generator["api_path_counts"] == {"chat_completions": 1}
        assert generator["text_removal_chars"] == 9
        assert generator["text_removal_emptied_unit_count"] == 1
        assert generator["model_output_discarded_paragraph_count"] == 3

    def test_section_present_with_zeros_when_no_scope_was_used(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            generator = _polish_section(ma.snapshot_run_model_accounting())
        assert generator["retry_attempt_count"] == 0
        assert generator["paragraph_disposition_counts"] == {
            "accepted": 0,
            "omitted": 0,
            "retry_required": 0,
            "source_restored": 0,
        }

    def test_usage_inside_scope_still_goes_to_its_stage_and_totals(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            with ma.pass_counter_scope("literary_polish"):
                ma.record_model_call_usage(stage=ma.STAGE_LITERARY_POLISH, response=_chat())
            snapshot = ma.snapshot_run_model_accounting()
        assert snapshot["model_call_count"] == 1
        assert snapshot["total_tokens"] == 250
        assert snapshot["stages"]["literary_polish"]["model_call_count"] == 1  # type: ignore[index]
        assert "model_call_count" not in _polish_section(snapshot)

    def test_scope_exit_restores_routing(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            with ma.pass_counter_scope("literary_polish"):
                ma.record_retry_attempt(reason="in", paragraph_count=0)
            ma.record_retry_attempt(reason="out", paragraph_count=0)
            snapshot = ma.snapshot_run_model_accounting()
        assert snapshot["retry_reason_counts"] == {"out": 1}
        assert _polish_section(snapshot)["retry_reason_counts"] == {"in": 1}

    def test_exception_restores_previous_scope(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            with pytest.raises(RuntimeError):
                with ma.pass_counter_scope("literary_polish"):
                    raise RuntimeError("boom")
            ma.record_retry_attempt(reason="after", paragraph_count=0)
            snapshot = ma.snapshot_run_model_accounting()
        assert snapshot["retry_attempt_count"] == 1
        assert _polish_section(snapshot)["retry_attempt_count"] == 0

    def test_nesting_restores_outer_scope_on_inner_exit(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            with ma.pass_counter_scope("literary_polish"):
                ma.record_retry_attempt(reason="a", paragraph_count=0)
                with ma.pass_counter_scope("literary_polish"):
                    ma.record_retry_attempt(reason="b", paragraph_count=0)
                ma.record_retry_attempt(reason="c", paragraph_count=0)
            snapshot = ma.snapshot_run_model_accounting()
        assert snapshot["retry_attempt_count"] == 0
        assert _polish_section(snapshot)["retry_reason_counts"] == {"a": 1, "b": 1, "c": 1}

    def test_nested_scope_after_exception_in_inner_keeps_outer(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            with ma.pass_counter_scope("literary_polish"):
                with pytest.raises(ValueError):
                    with ma.pass_counter_scope("literary_polish"):
                        raise ValueError("inner")
                ma.record_retry_attempt(reason="outer", paragraph_count=0)
            snapshot = ma.snapshot_run_model_accounting()
        assert snapshot["retry_attempt_count"] == 0
        assert _polish_section(snapshot)["retry_attempt_count"] == 1

    def test_unknown_scope_name_is_rejected(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            with pytest.raises(ValueError):
                with ma.pass_counter_scope("nonsense"):
                    pass

    def test_scopes_of_two_runs_do_not_share_sections(self) -> None:
        with ma.run_model_accounting_scope(run_id="a", source_token="s"):
            with ma.pass_counter_scope("literary_polish"):
                ma.record_retry_attempt(reason="a", paragraph_count=0)
        with ma.run_model_accounting_scope(run_id="b", source_token="s"):
            snapshot = ma.snapshot_run_model_accounting()
        assert _polish_section(snapshot)["retry_attempt_count"] == 0

    def test_pass_own_counters_are_reported_beside_generator_counters(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s"):
            ma.record_pass_counter("literary_polish", "sent_paragraph_count", 5)
            ma.record_pass_counter("literary_polish", "sent_paragraph_count", 2)
            ma.record_pass_counter("literary_polish", "ignored_zero", 0)
            snapshot = ma.snapshot_run_model_accounting()
        section = snapshot["literary_polish"]
        assert isinstance(section, dict)
        assert section["counters"] == {"sent_paragraph_count": 7}
        assert snapshot["model_call_count"] == 0

    def test_reset_clears_pass_sections(self) -> None:
        with ma.run_model_accounting_scope(run_id="r", source_token="s") as ledger:
            with ma.pass_counter_scope("literary_polish"):
                ma.record_retry_attempt(reason="x", paragraph_count=0)
            ma.record_pass_counter("literary_polish", "k", 1)
            ledger.reset()
            snapshot = ma.snapshot_run_model_accounting()
        assert _polish_section(snapshot)["retry_attempt_count"] == 0
        assert snapshot["literary_polish"]["counters"] == {}  # type: ignore[index]
