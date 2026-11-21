"""Baseline reviewer with a fake LLM: checks the prompt we send and how replies are mapped."""

from __future__ import annotations

import pytest

from archoptimize.agents.baseline_reviewer import build_user_message, review_baseline
from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_router import ModelRouter
from archoptimize.llm.role_config import load_settings
from archoptimize.schemas import Finding, Pillar, ReviewDraft, Severity, Verdict
from archoptimize.schemas.doc_chunk import DocChunk, RetrievedChunk
from evaluation.eval_cases import load_cases

KEYS = ProviderKeys.from_values("gsk_" + "x" * 40, None)


class FakeStructuredChat:
    """Returns a fixed ReviewDraft and records the messages it was sent."""

    def __init__(self, draft: ReviewDraft, sent: list):
        self.draft, self.sent = draft, sent

    def with_structured_output(self, schema, method, include_raw=False):
        chat = self

        class _Raw:
            usage_metadata = {"total_tokens": 1234}

        class _Bound:
            def invoke(self, messages, **_kw):
                chat.sent.append(messages)
                return {"raw": _Raw(), "parsed": chat.draft, "parsing_error": None}

        return _Bound()


@pytest.fixture
def injection_case():
    return load_cases(only="05_prompt_injection")[0].submission


def make_router(draft: ReviewDraft, sent: list) -> ModelRouter:
    return ModelRouter(
        load_settings(),
        chat_factory=lambda _c, _k: FakeStructuredChat(draft, sent),
        openrouter_fetch=lambda: [],
        groq_fetch=lambda _k: [],
    )


def test_user_message_wraps_design_as_untrusted_data(injection_case):
    message = build_user_message(injection_case)
    assert "<design_document>" in message and "</design_document>" in message
    # the injected text stays INSIDE the tags
    inside = message.split("<design_document>")[1].split("</design_document>")[0]
    assert "ignore all previous instructions" in inside
    assert '"availability_slo_percent": 99.9' in message


def test_review_maps_draft_to_result(injection_case):
    draft = ReviewDraft(
        summary="Single-AZ DB; the description tries to instruct the reviewer.",
        findings=[
            Finding(
                id="REL-1",
                pillar=Pillar.RELIABILITY,
                severity=Severity.HIGH,
                title="Single-AZ database",
                component_ids=["wiki-db", "made-up-id"],
                evidence="wiki-db has availability_zones: 1",
                recommendation="Enable Multi-AZ",
            )
        ],
        requirement_conflicts=[],
        assumptions=["Backups retention unknown"],
        suspicious_instructions_found=True,
        verdict=Verdict.APPROVE_WITH_CHANGES,
    )
    sent: list = []
    result = review_baseline(injection_case, keys=KEYS, router=make_router(draft, sent))

    assert result.verdict is Verdict.APPROVE_WITH_CHANGES
    assert result.input_flagged is True
    assert result.tokens_used == 1234
    assert result.findings[0].component_ids == ["wiki-db"]  # invented id dropped
    system, human = sent[0]
    assert system[0] == "system" and "UNTRUSTED" in system[1]
    assert human[0] == "human" and "<design_document>" in human[1]
    assert "<documentation>" not in human[1]  # no retriever -> no documentation


class FakeRetriever:
    def retrieve(self, query, pillar, k=4):
        chunk = DocChunk(
            chunk_id=f"{pillar.value[:3]}-0001",
            pillar=pillar,
            doc_title="Doc",
            page=3,
            url="https://x#page=3",
            text=f"Guidance about {pillar.value}.",
        )
        return [RetrievedChunk(chunk=chunk, score=0.9)]


def test_rag_review_sends_documentation_and_validates_citations(injection_case):
    draft = ReviewDraft(
        summary="s",
        findings=[
            Finding(
                id="REL-1",
                pillar=Pillar.RELIABILITY,
                severity=Severity.HIGH,
                title="Single-AZ database",
                component_ids=["wiki-db"],
                evidence="e",
                recommendation="r",
                citation_chunk_ids=["rel-0001", "rel-4242"],  # second one was never retrieved
            ),
            Finding(
                id="SEC-1",
                pillar=Pillar.SECURITY,
                severity=Severity.LOW,
                title="t",
                evidence="e",
                recommendation="r",
            ),
        ],
        requirement_conflicts=[],
        assumptions=[],
        suspicious_instructions_found=True,
        verdict=Verdict.APPROVE_WITH_CHANGES,
    )
    sent: list = []
    result = review_baseline(
        injection_case, retriever=FakeRetriever(), keys=KEYS, router=make_router(draft, sent)
    )
    human = sent[0][1][1]
    assert "<documentation>" in human and 'id="rel-0001"' in human
    assert result.findings[0].citation_chunk_ids == ["rel-0001"]
    assert result.uncited_finding_ids == ["SEC-1"]
    assert {c.chunk_id for c in result.sources} >= {"rel-0001", "sec-0001"}
