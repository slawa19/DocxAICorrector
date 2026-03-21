import json

import pytest

from real_document_validation_profiles import load_validation_registry
from real_document_validation_structural import evaluate_extraction_profile, run_structural_passthrough_validation


REGISTRY = load_validation_registry()
STRUCTURAL_RUN_PROFILE = REGISTRY.get_run_profile("structural-passthrough-default")


@pytest.mark.parametrize("document_profile", REGISTRY.documents, ids=[profile.id for profile in REGISTRY.documents])
def test_corpus_extraction(document_profile) -> None:
    source_path = document_profile.resolved_source_path()
    if not source_path.exists():
        pytest.skip(f"missing real-document source: {source_path}")

    result = evaluate_extraction_profile(document_profile)

    assert result["validation_tier"] == "extraction"
    assert result["document_profile_id"] == document_profile.id
    assert result["passed"] is True, json.dumps(result, ensure_ascii=False, indent=2)


@pytest.mark.parametrize("document_profile", REGISTRY.documents, ids=[profile.id for profile in REGISTRY.documents])
def test_corpus_structural_passthrough(document_profile) -> None:
    source_path = document_profile.resolved_source_path()
    if not source_path.exists():
        pytest.skip(f"missing real-document source: {source_path}")

    result = run_structural_passthrough_validation(document_profile, STRUCTURAL_RUN_PROFILE)

    assert result["validation_tier"] == "structural"
    assert result["run_profile_id"] == STRUCTURAL_RUN_PROFILE.id
    assert result["runtime_config"]["effective"]["image_mode"] == STRUCTURAL_RUN_PROFILE.image_mode
    assert result["passed"] is True, json.dumps(result, ensure_ascii=False, indent=2)
