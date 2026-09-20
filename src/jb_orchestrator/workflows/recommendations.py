"""Deterministic workflow recommendation policy."""

import re
from dataclasses import dataclass
from enum import StrEnum

POLICY_VERSION = "workflow-keyword-v1"
TOKEN_PATTERN = re.compile(r"[0-9a-zA-Z가-힣]+")

INTENT_ALIASES: dict[str, frozenset[str]] = {
    "planning": frozenset(
        {"기획", "계획", "설계", "요구사항", "분석", "architecture", "design", "plan", "planning"}
    ),
    "implementation": frozenset(
        {"개발", "구현", "코드", "기능", "버그", "implement", "implementation", "develop", "code"}
    ),
    "verification": frozenset(
        {
            "검증",
            "테스트",
            "리뷰",
            "품질",
            "보안",
            "verify",
            "verification",
            "test",
            "review",
            "quality",
            "security",
        }
    ),
    "repair": frozenset({"수정", "복구", "개선", "고쳐", "fix", "repair", "recover", "improve"}),
    "research": frozenset(
        {"조사", "검색", "비교", "입증", "타당성", "research", "search", "compare", "evidence"}
    ),
}


class RecommendationConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowRecommendationInput:
    key: str
    version: int
    searchable_text: str
    is_default: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowRecommendationCandidate:
    definition_key: str
    definition_version: int
    score: int
    matched_terms: tuple[str, ...]
    matched_intents: tuple[str, ...]
    is_default: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkflowRecommendation:
    policy_version: str
    confidence: RecommendationConfidence
    requires_confirmation: bool
    candidates: tuple[WorkflowRecommendationCandidate, ...]

    @property
    def recommended(self) -> WorkflowRecommendationCandidate | None:
        return self.candidates[0] if self.candidates else None


def tokenize(value: str) -> frozenset[str]:
    """Normalize Korean and English search terms without locale-dependent behavior."""

    return frozenset(
        token
        for token in (match.lower() for match in TOKEN_PATTERN.findall(value))
        if len(token) > 1
    )


def _intents(terms: frozenset[str]) -> frozenset[str]:
    return frozenset(
        intent
        for intent, aliases in INTENT_ALIASES.items()
        if any(
            alias == term
            or (any("가" <= character <= "힣" for character in alias) and alias in term)
            for alias in aliases
            for term in terms
        )
    )


def recommend_workflows(
    prompt: str,
    workflows: tuple[WorkflowRecommendationInput, ...],
    *,
    limit: int = 3,
) -> WorkflowRecommendation:
    """Rank exact workflow versions and expose whether automatic use is safe."""

    prompt_terms = tokenize(prompt)
    prompt_intents = _intents(prompt_terms)
    ranked: list[WorkflowRecommendationCandidate] = []
    for workflow in workflows:
        workflow_terms = tokenize(workflow.searchable_text)
        matched_terms = tuple(sorted(prompt_terms & workflow_terms))
        matched_intents = tuple(sorted(prompt_intents & _intents(workflow_terms)))
        score = len(matched_terms) * 4 + len(matched_intents) * 6
        if workflow.is_default:
            score += 1
        ranked.append(
            WorkflowRecommendationCandidate(
                definition_key=workflow.key,
                definition_version=workflow.version,
                score=score,
                matched_terms=matched_terms,
                matched_intents=matched_intents,
                is_default=workflow.is_default,
            )
        )
    ranked.sort(
        key=lambda value: (
            -value.score,
            not value.is_default,
            value.definition_key,
            -value.definition_version,
        )
    )
    candidates = tuple(ranked[:limit])
    top_score = candidates[0].score if candidates else 0
    runner_up = candidates[1].score if len(candidates) > 1 else 0
    if top_score >= 10 and top_score - runner_up >= 4:
        confidence = RecommendationConfidence.HIGH
    elif top_score >= 6 and top_score > runner_up:
        confidence = RecommendationConfidence.MEDIUM
    else:
        confidence = RecommendationConfidence.LOW
    return WorkflowRecommendation(
        policy_version=POLICY_VERSION,
        confidence=confidence,
        requires_confirmation=confidence is not RecommendationConfidence.HIGH,
        candidates=candidates,
    )
