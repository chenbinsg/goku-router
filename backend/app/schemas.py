from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict


class ChatMessage(BaseModel):
    role: str = "user"
    content: Any


class ProviderPreferences(BaseModel):
    order: Optional[List[str]] = None
    allow_fallbacks: bool = True
    sort: str = "balanced"
    max_price_per_1k: Optional[float] = None
    require_capabilities: Optional[List[str]] = None
    require_parameters: bool = False
    zdr: Optional[bool] = None
    data_collection: Optional[str] = None
    organization: Optional[str] = None
    project: Optional[str] = None
    sticky_key: Optional[str] = None


class ToolDefinition(BaseModel):
    type: str = "function"
    function: dict[str, Any]


class ResponseFormat(BaseModel):
    type: str
    json_schema: Optional[dict[str, Any]] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    stop: Optional[List[str] | str] = None
    tools: Optional[List[ToolDefinition]] = None
    tool_choice: Optional[Any] = None
    response_format: Optional[ResponseFormat] = None
    provider: Optional[ProviderPreferences] = None


class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    provider_reported_cost: float = 0.0

class ChatCompletionResponse(BaseModel):
    completion: str
    provider: str
    fallback_used: bool
    request_id: str
    cache_hit: bool = False
    response_healed: bool = False
    healing_strategy: Optional[str] = None
    selected_model: Optional[str] = None
    structured_output: Optional[Any] = None
    tool_calls: Optional[List[dict[str, Any]]] = None
    usage: Usage

class EmbeddingRequest(BaseModel):
    text: str

class EmbeddingResponse(BaseModel):
    embedding: List[float]
    provider: str = "mock-embedding"

class ModelListResponse(BaseModel):
    models: List[str]

class BillingExportResponse(BaseModel):
    csv_url: str


class DownloadArtifactResponse(BaseModel):
    file_name: str
    download_url: str


class ProviderItem(BaseModel):
    id: int
    name: str
    adapter_type: str
    status: str
    health_status: str
    priority: int
    input_cost_per_1k: float
    output_cost_per_1k: float
    avg_latency_ms: float
    capabilities: List[str]
    supports_zdr: bool
    data_collection_mode: str
    supported_parameters: List[str]
    max_input_tokens: int
    max_output_tokens: int

    model_config = ConfigDict(from_attributes=True)


class ProviderCreate(BaseModel):
    name: str
    adapter_type: str = "mock"
    status: str = "active"
    health_status: str = "healthy"
    priority: int = 100
    input_cost_per_1k: float = 0.001
    output_cost_per_1k: float = 0.002
    avg_latency_ms: float = 500.0
    capabilities: List[str] = ["chat"]
    supports_zdr: bool = False
    data_collection_mode: str = "allow"
    max_input_tokens: int = 4096
    max_output_tokens: int = 2048
    supported_parameters: List[str] = [
        "temperature",
        "top_p",
        "max_tokens",
        "stop",
        "tools",
        "tool_choice",
        "response_format",
    ]


class ModelCatalogItem(BaseModel):
    id: int
    model_id: str
    provider_id: int
    provider_name: str
    provider_model_name: str
    status: str


class ModelCatalogCreate(BaseModel):
    model_id: str
    provider_id: int
    provider_model_name: str
    status: str = "active"


class RouteRuleItem(BaseModel):
    id: int
    model_id: str
    preferred_provider_id: int
    preferred_provider_name: str
    backup_provider_id: Optional[int] = None
    backup_provider_name: Optional[str] = None
    timeout_ms: int


class RouteRuleCreate(BaseModel):
    model_id: str
    preferred_provider_id: int
    backup_provider_id: Optional[int] = None
    timeout_ms: int = 1500


class RequestLogItem(BaseModel):
    request_id: str
    api_key_label: Optional[str] = None
    organization_id: Optional[int] = None
    project_id: Optional[int] = None
    environment: Optional[str] = None
    requested_model: str
    resolved_model: Optional[str] = None
    provider_name: Optional[str] = None
    workload_class: Optional[str] = None
    applied_profile_name: Optional[str] = None
    experiment_name: Optional[str] = None
    experiment_variant: Optional[str] = None
    sticky_key: Optional[str] = None
    status_code: int
    latency: float
    fallback_used: bool
    route_changed: bool = False
    cache_hit: bool = False
    response_healed: bool = False
    healing_strategy: Optional[str] = None
    error_code: Optional[str] = None
    route_trace: Optional[dict[str, Any]] = None


class BillingUsageItem(BaseModel):
    api_key_label: str
    organization_id: Optional[int] = None
    project_id: Optional[int] = None
    environment: Optional[str] = None
    resolved_model: Optional[str] = None
    provider_name: Optional[str] = None
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    cached_tokens: int
    reasoning_tokens: int
    total_cost: float
    provider_reported_cost: float


class BillingUsageResponse(BaseModel):
    items: List[BillingUsageItem]


class ProviderConnectionTestRequest(BaseModel):
    provider_id: int
    provider_model_name: str
    prompt: str = "Connection test from router"


class ProviderConnectionTestResult(BaseModel):
    success: bool
    provider_name: str
    adapter_type: str
    completion: str
    prompt_tokens: int
    completion_tokens: int
    message: str


class RouterApiKeyItem(BaseModel):
    id: int
    name: str
    key_prefix: str
    status: str
    organization_id: Optional[int] = None
    project_id: Optional[int] = None
    environment: Optional[str] = None
    quota_requests: Optional[int] = None
    request_count: int = 0
    expires_at: Optional[str] = None
    rotated_from_key_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class RouterApiKeyCreate(BaseModel):
    name: str
    organization_id: Optional[int] = None
    project_id: Optional[int] = None
    environment: Optional[str] = None
    quota_requests: Optional[int] = None
    expires_at: Optional[str] = None


class RouterApiKeyCreateResult(BaseModel):
    id: int
    name: str
    key_prefix: str
    status: str
    organization_id: Optional[int] = None
    project_id: Optional[int] = None
    environment: Optional[str] = None
    quota_requests: Optional[int] = None
    request_count: int = 0
    expires_at: Optional[str] = None
    rotated_from_key_id: Optional[int] = None
    plain_api_key: str


class RouterApiKeyUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    organization_id: Optional[int] = None
    project_id: Optional[int] = None
    environment: Optional[str] = None
    quota_requests: Optional[int] = None
    expires_at: Optional[str] = None


class RouterApiKeyRotateRequest(BaseModel):
    name: Optional[str] = None
    quota_requests: Optional[int] = None
    expires_at: Optional[str] = None


class OrganizationItem(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class OrganizationCreate(BaseModel):
    name: str


class ProjectItem(BaseModel):
    id: int
    name: str
    organization_id: int
    organization_name: str


class ProjectCreate(BaseModel):
    name: str
    organization_id: int


class WorkspaceRouteDefaultItem(BaseModel):
    id: int
    organization_id: Optional[int] = None
    organization_name: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    provider_order: List[str] = []
    sort_mode: str = "balanced"
    max_price_per_1k: Optional[float] = None
    require_capabilities: List[str] = []
    require_parameters: bool = False
    zdr: Optional[bool] = None
    data_collection: Optional[str] = None


class WorkspaceRouteDefaultCreate(BaseModel):
    organization_id: Optional[int] = None
    project_id: Optional[int] = None
    provider_order: List[str] = []
    sort_mode: str = "balanced"
    max_price_per_1k: Optional[float] = None
    require_capabilities: List[str] = []
    require_parameters: bool = False
    zdr: Optional[bool] = None
    data_collection: Optional[str] = None


class WorkspaceGuardrailConfigItem(BaseModel):
    id: int
    organization_id: Optional[int] = None
    organization_name: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    allowed_providers: Optional[List[str]] = None
    denied_providers: Optional[List[str]] = None
    blocked_words: Optional[List[str]] = None
    max_prompt_chars: Optional[int] = None
    retention_mode: Optional[str] = None


class WorkspaceGuardrailConfigCreate(BaseModel):
    organization_id: Optional[int] = None
    project_id: Optional[int] = None
    allowed_providers: Optional[List[str]] = None
    denied_providers: Optional[List[str]] = None
    blocked_words: Optional[List[str]] = None
    max_prompt_chars: Optional[int] = None
    retention_mode: Optional[str] = None


class GuardrailConfigItem(BaseModel):
    allowed_providers: List[str] = []
    denied_providers: List[str] = []
    blocked_words: List[str] = []
    max_prompt_chars: int = 4000
    retention_mode: str = "standard"


class GuardrailConfigUpdate(BaseModel):
    allowed_providers: List[str] = []
    denied_providers: List[str] = []
    blocked_words: List[str] = []
    max_prompt_chars: int = 4000
    retention_mode: str = "standard"


class GuardrailPolicyPresetItem(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    organization_id: Optional[int] = None
    organization_name: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    allowed_providers: List[str] = []
    denied_providers: List[str] = []
    blocked_words: List[str] = []
    max_prompt_chars: int = 4000
    retention_mode: str = "standard"


class GuardrailPolicyPresetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    organization_id: Optional[int] = None
    project_id: Optional[int] = None
    allowed_providers: List[str] = []
    denied_providers: List[str] = []
    blocked_words: List[str] = []
    max_prompt_chars: int = 4000
    retention_mode: str = "standard"


class AuditLogItem(BaseModel):
    id: int
    action: str
    details: str
    timestamp: str


class NotificationItem(BaseModel):
    id: int
    type: str
    message: str
    timestamp: str


class NotificationCreate(BaseModel):
    type: str
    message: str


class AnalyticsSeriesItem(BaseModel):
    label: str
    requests: int
    failures: int
    avg_latency: float
    total_cost: float


class RouteScoringShiftItem(BaseModel):
    workload_class: str
    changed_routes: int
    total_routes: int


class WorkspaceUsageSummaryItem(BaseModel):
    organization_id: Optional[int] = None
    organization_name: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    environment: Optional[str] = None
    request_count: int
    failure_count: int
    fallback_count: int
    cache_hit_count: int
    total_cost: float
    avg_latency: float


class CostOptimizationOpportunityItem(BaseModel):
    category: str
    title: str
    scope_label: str
    summary: str
    estimated_savings: float
    current_cost: float
    target_cost: Optional[float] = None
    recommendation: str


class AnomalyAlertItem(BaseModel):
    category: str
    severity: str
    title: str
    scope_label: str
    message: str
    metric_value: float
    threshold: float


class RouteScoringDriftItem(BaseModel):
    workload_class: str
    request_count: int
    active_profile_name: str
    drift_score: float
    route_change_rate: float
    default_weights: dict[str, float]
    active_weights: dict[str, float]


class AnalyticsSummary(BaseModel):
    total_requests: int
    fallback_rate: float
    blocked_requests: int
    active_api_keys: int
    organizations: int
    projects: int
    route_scoring_profile_name: str
    recent_route_changes: int
    recent_route_change_rate: float
    recent_route_replay_cases: int
    cache_hit_rate: float
    cache_hits: int
    sticky_requests: int
    route_scoring_workload_shifts: List[RouteScoringShiftItem]
    provider_breakdown: List[AnalyticsSeriesItem]
    model_breakdown: List[AnalyticsSeriesItem]
    workspace_usage_summary: List[WorkspaceUsageSummaryItem]
    cost_optimization_opportunities: List[CostOptimizationOpportunityItem] = []
    anomaly_alerts: List[AnomalyAlertItem] = []
    route_scoring_drift: List[RouteScoringDriftItem] = []
    route_scoring_experiments: List[dict[str, Any]] = []


class PolicyDryRunRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    provider: Optional[ProviderPreferences] = None
    tools: Optional[List[ToolDefinition]] = None
    response_format: Optional[ResponseFormat] = None
    guardrails: GuardrailConfigUpdate


class PolicyDryRunResult(BaseModel):
    workload_class: str
    blocked: bool
    block_reason: Optional[str] = None
    selected_provider: Optional[str] = None
    selected_model: Optional[str] = None
    accepted_candidates: int
    rejected_candidates: int
    eligibility_summary: dict[str, int] = {}
    policy_diff: dict[str, Any] = {}
    route_trace: dict[str, Any]


class BatchPolicyDryRunRequest(BaseModel):
    dataset_path: str
    strategies: List[str] = ["current_production_policy"]
    workspace_label: Optional[str] = None
    guardrails: GuardrailConfigUpdate


class BatchPolicyDryRunItem(BaseModel):
    example_id: str
    workload_class: str
    strategy: str
    blocked: bool
    block_reason: Optional[str] = None
    selected_provider: Optional[str] = None
    selected_model: Optional[str] = None
    accepted_candidates: int
    rejected_candidates: int


class BatchPolicyDryRunResponse(BaseModel):
    dataset_name: str
    workspace_label: Optional[str] = None
    total_cases: int
    blocked_cases: int
    success_cases: int
    strategy_summaries: List[dict[str, Any]] = []
    policy_diff_summary: dict[str, Any] = {}
    items: List[BatchPolicyDryRunItem]


class GuardrailPolicyCompareRequest(BaseModel):
    dataset_path: str
    strategies: List[str] = ["current_production_policy"]
    workspace_label: Optional[str] = None
    baseline_policy_name: str
    comparison_policy_name: str


class GuardrailPolicyCompareItem(BaseModel):
    example_id: str
    workload_class: str
    strategy: str
    baseline_blocked: bool
    comparison_blocked: bool
    baseline_provider: Optional[str] = None
    comparison_provider: Optional[str] = None
    baseline_model: Optional[str] = None
    comparison_model: Optional[str] = None
    accepted_candidates_before: int
    accepted_candidates_after: int
    changed_provider: bool
    changed_block: bool


class GuardrailPolicyCompareResponse(BaseModel):
    dataset_name: str
    workspace_label: Optional[str] = None
    baseline_policy_name: str
    comparison_policy_name: str
    strategy_summaries: List[dict[str, Any]] = []
    comparison_summary: dict[str, Any] = {}
    items: List[GuardrailPolicyCompareItem] = []


class RouteScoringProfileItem(BaseModel):
    name: str
    source_dataset: str
    status: str
    trained_at: str
    weights: dict[str, dict[str, float]]


class RouteScoringTrainRequest(BaseModel):
    dataset_path: str
    baseline_strategy: str = "current_production_policy"
    profile_name: str = "learned_eval_profile"


class RouteScoringTrainResult(RouteScoringProfileItem):
    workload_winners: List[dict[str, Any]]
    calibration_summary: List[dict[str, Any]]


class RouteScoringRecalibrationRequest(BaseModel):
    profile_name: str = "learned_feedback_profile"
    limit: int = 100
    organization_id: Optional[int] = None
    project_id: Optional[int] = None
    experiment_name: Optional[str] = None


class RouteScoringRecalibrationResult(RouteScoringProfileItem):
    calibration_summary: List[dict[str, Any]]
    source_summary: dict[str, Any]


class RouteScoringExperimentItem(BaseModel):
    id: int
    name: str
    control_profile_name: str
    challenger_profile_name: str
    traffic_percentage: int
    status: str
    created_at: str
    updated_at: str


class RouteScoringExperimentCreate(BaseModel):
    name: str
    control_profile_name: str = "default_heuristic_profile"
    challenger_profile_name: str
    traffic_percentage: int = 50
    status: str = "active"


class RouteReplayRequest(BaseModel):
    source: str = "dataset"
    dataset_path: Optional[str] = None
    strategy: str = "current_production_policy"
    limit: int = 20
    organization_id: Optional[int] = None
    project_id: Optional[int] = None
    baseline_profile_name: Optional[str] = None
    comparison_profile_name: Optional[str] = None


class RouteReplayItem(BaseModel):
    request_id: Optional[str] = None
    example_id: Optional[str] = None
    workload_class: str
    heuristic_provider: Optional[str] = None
    learned_provider: Optional[str] = None
    baseline_profile_name: Optional[str] = None
    comparison_profile_name: Optional[str] = None
    baseline_provider: Optional[str] = None
    comparison_provider: Optional[str] = None
    original_provider: Optional[str] = None
    changed: bool
    source: str


class RouteReplayResponse(BaseModel):
    source: str
    source_label: str
    total_cases: int
    changed_routes: int
    unchanged_routes: int
    items: List[RouteReplayItem]
