from jb_orchestrator.workflows import (
    RecommendationConfidence,
    WorkflowRecommendationInput,
    recommend_workflows,
)


def test_recommendation_ranks_matching_intent_with_explainable_terms() -> None:
    result = recommend_workflows(
        "구현 결과를 보안 테스트하고 검증해줘",
        (
            WorkflowRecommendationInput(
                key="planning-only", version=1, searchable_text="기획 요구사항 설계"
            ),
            WorkflowRecommendationInput(
                key="security-review",
                version=2,
                searchable_text="보안 검증 test review security",
            ),
        ),
    )

    assert result.confidence is RecommendationConfidence.HIGH
    assert result.requires_confirmation is False
    assert result.recommended is not None
    assert result.recommended.definition_key == "security-review"
    assert result.recommended.matched_terms == ("보안",)
    assert result.recommended.matched_intents == ("verification",)


def test_recommendation_prefers_default_but_requires_confirmation_without_evidence() -> None:
    result = recommend_workflows(
        "무언가 처리해줘",
        (
            WorkflowRecommendationInput(key="alpha", version=1, searchable_text="alpha"),
            WorkflowRecommendationInput(
                key="default", version=3, searchable_text="default", is_default=True
            ),
        ),
    )

    assert result.confidence is RecommendationConfidence.LOW
    assert result.requires_confirmation is True
    assert result.recommended is not None
    assert result.recommended.definition_key == "default"
