"""The system design as a typed graph: components (nodes) connected by edges.

Every input format (YAML, text, image) is turned into this one structure, so reviewers,
calculators, diagrams and the eval all work on the same data.

Unknown facts are `None` (e.g. `encryption_at_rest=None` means "not stated"), which lets
reviewers tell "missing" apart from "explicitly off".
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_COMPONENTS = 50
COMPONENT_ID_PATTERN = r"^[a-z][a-z0-9_-]{0,39}$"


class ComponentType(StrEnum):
    CLIENT = "client"  # users, browsers, mobile apps
    DNS = "dns"  # Route 53
    CDN = "cdn"  # CloudFront
    WAF = "waf"  # AWS WAF
    LOAD_BALANCER = "load_balancer"  # ALB / NLB
    API_GATEWAY = "api_gateway"
    COMPUTE_VM = "compute_vm"  # EC2
    CONTAINER_SERVICE = "container_service"  # ECS / EKS / Fargate
    SERVERLESS_FUNCTION = "serverless_function"  # Lambda
    RELATIONAL_DATABASE = "relational_database"  # RDS / Aurora
    NOSQL_DATABASE = "nosql_database"  # DynamoDB
    CACHE = "cache"  # ElastiCache
    OBJECT_STORAGE = "object_storage"  # S3
    QUEUE = "queue"  # SQS
    STREAM = "stream"  # Kinesis / MSK
    SEARCH = "search"  # OpenSearch
    EXTERNAL_SERVICE = "external_service"  # third-party APIs (e.g. payment provider)
    OTHER = "other"


DATA_STORE_TYPES = frozenset(
    {
        ComponentType.RELATIONAL_DATABASE,
        ComponentType.NOSQL_DATABASE,
        ComponentType.CACHE,
        ComponentType.OBJECT_STORAGE,
        ComponentType.SEARCH,
        ComponentType.QUEUE,
        ComponentType.STREAM,
    }
)


class DataClassification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    CARDHOLDER = "cardholder"  # payment card data, in scope for PCI DSS


class EdgeMode(StrEnum):
    SYNC = "sync"  # caller waits for the answer (HTTP, SQL, gRPC)
    ASYNC = "async"  # fire-and-forget via a queue/stream/event


class AutoscalingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_replicas: int = Field(ge=1, description="Lowest number of running copies.")
    max_replicas: int = Field(ge=1, description="Highest number of running copies.")

    @model_validator(mode="after")
    def _max_not_below_min(self) -> AutoscalingConfig:
        if self.max_replicas < self.min_replicas:
            raise ValueError("max_replicas must be >= min_replicas")
        return self


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        pattern=COMPONENT_ID_PATTERN,
        description="Short unique id: lowercase letters, digits, '-' or '_' (e.g. 'orders-db').",
    )
    name: str = Field(min_length=1, max_length=80, description="Human-readable name.")
    type: ComponentType
    aws_service: str | None = Field(
        default=None, max_length=60, description="AWS service, e.g. 'EC2', 'RDS PostgreSQL'."
    )
    instance_type: str | None = Field(
        default=None, max_length=40, description="Size used for pricing, e.g. 't3.medium'."
    )
    replicas: int = Field(default=1, ge=1, le=1000, description="Running copies (baseline).")
    availability_zones: int = Field(
        default=1, ge=1, le=6, description="Number of AZs the component spans."
    )
    autoscaling: AutoscalingConfig | None = None
    public: bool = Field(default=False, description="Reachable directly from the internet.")
    encryption_at_rest: bool | None = None
    encryption_in_transit: bool | None = None
    backups_enabled: bool | None = None
    data_classification: DataClassification | None = None
    notes: str = Field(default="", max_length=500, description="Anything else worth knowing.")

    @property
    def is_data_store(self) -> bool:
        return self.type in DATA_STORE_TYPES


class Edge(BaseModel):
    """A call or data flow from one component to another.
    In YAML you may write `from`/`to`; in code the fields are `source`/`target`."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source: str = Field(alias="from", pattern=COMPONENT_ID_PATTERN)
    target: str = Field(alias="to", pattern=COMPONENT_ID_PATTERN)
    mode: EdgeMode = EdgeMode.SYNC
    protocol: str | None = Field(default=None, max_length=30, description="e.g. https, sql, grpc")
    description: str = Field(default="", max_length=200)


class ComponentGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    components: list[Component] = Field(min_length=1, max_length=MAX_COMPONENTS)
    edges: list[Edge] = Field(default_factory=list)
    assumptions: list[str] = Field(
        default_factory=list,
        description="Facts that were not stated and had to be assumed (filled by text parsing).",
    )

    @model_validator(mode="after")
    def _check_references(self) -> ComponentGraph:
        ids = [c.id for c in self.components]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate component ids: {', '.join(duplicates)}")
        known = set(ids)
        for edge in self.edges:
            for end in (edge.source, edge.target):
                if end not in known:
                    raise ValueError(
                        f"edge {edge.source} -> {edge.target}: unknown component '{end}'"
                    )
            if edge.source == edge.target:
                raise ValueError(
                    f"edge {edge.source} -> {edge.target}: a component cannot call itself"
                )
        return self

    # -- small read helpers used by reviewers and renderers --
    def component(self, component_id: str) -> Component:
        for c in self.components:
            if c.id == component_id:
                return c
        raise KeyError(component_id)

    def edges_from(self, component_id: str) -> list[Edge]:
        return [e for e in self.edges if e.source == component_id]

    def edges_to(self, component_id: str) -> list[Edge]:
        return [e for e in self.edges if e.target == component_id]
