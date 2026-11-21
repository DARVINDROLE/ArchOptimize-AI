"""Free text → DesignSubmission with an LLM (structured output).

The model may only state what the text says; unknowns become `assumptions`, which the user
sees on the confirm screen (human in the loop) before any review runs.
"""

from __future__ import annotations

from archoptimize.agents.agent_base import call_structured, load_prompt
from archoptimize.core.app_settings import get_app_settings
from archoptimize.core.errors import DesignInputError, InputIssue
from archoptimize.core.untrusted_input import wrap_untrusted
from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_router import ModelRouter
from archoptimize.schemas import ComponentType, DesignSubmission

ROLE = "normalizer"
MIN_CHARS = 20

# When the AWS service is known, its component type is not a judgement call: fix it in code.
_SERVICE_TYPES: list[tuple[str, ComponentType]] = [
    ("elasticache", ComponentType.CACHE),
    ("aurora", ComponentType.RELATIONAL_DATABASE),
    ("rds", ComponentType.RELATIONAL_DATABASE),
    ("dynamodb", ComponentType.NOSQL_DATABASE),
    ("lambda", ComponentType.SERVERLESS_FUNCTION),
    ("fargate", ComponentType.CONTAINER_SERVICE),
    ("ecs", ComponentType.CONTAINER_SERVICE),
    ("eks", ComponentType.CONTAINER_SERVICE),
    ("ec2", ComponentType.COMPUTE_VM),
    ("api gateway", ComponentType.API_GATEWAY),
    ("cloudfront", ComponentType.CDN),
    ("waf", ComponentType.WAF),
    ("s3", ComponentType.OBJECT_STORAGE),
    ("sqs", ComponentType.QUEUE),
    ("kinesis", ComponentType.STREAM),
    ("opensearch", ComponentType.SEARCH),
    ("route 53", ComponentType.DNS),
    ("alb", ComponentType.LOAD_BALANCER),
    ("nlb", ComponentType.LOAD_BALANCER),
    ("elb", ComponentType.LOAD_BALANCER),
]


def normalise_component_types(submission: DesignSubmission) -> DesignSubmission:
    """Correct types that contradict the stated AWS service; clients are never 'public'."""
    fixed = []
    for c in submission.design.components:
        service = (c.aws_service or "").lower()
        expected = next((t for key, t in _SERVICE_TYPES if key in service), None)
        if expected is not None and c.type is not expected:
            c = c.model_copy(update={"type": expected})
        if c.type is ComponentType.CLIENT and c.public:
            c = c.model_copy(update={"public": False})
        fixed.append(c)
    design = submission.design.model_copy(update={"components": fixed})
    return submission.model_copy(update={"design": design})


def parse_design_text(
    text: str,
    *,
    keys: ProviderKeys | None = None,
    router: ModelRouter | None = None,
) -> DesignSubmission:
    limit = get_app_settings().max_design_chars
    if len(text) > limit:
        raise DesignInputError(
            [InputIssue("", f"input is {len(text):,} characters; the limit is {limit:,}")]
        )
    if len(text.strip()) < MIN_CHARS:
        raise DesignInputError([InputIssue("", "please describe the system in a few sentences")])
    call = call_structured(
        ROLE,
        DesignSubmission,
        load_prompt("text_design_parser"),
        wrap_untrusted(text.strip()),
        keys=keys,
        router=router,
    )
    return normalise_component_types(call.output)
