from sqlalchemy import Column, Integer, String, Text, ForeignKey, Float, Boolean, DateTime
from sqlalchemy.orm import relationship
from .db import Base


class AdminUser(Base):
    """Console/admin users who log in with username + password. (v1.4.0)"""
    __tablename__ = "admin_users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="admin")
    # roles: superadmin | admin | viewer
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    last_login_at = Column(DateTime, nullable=True)


class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True)
    projects = relationship("Project", back_populates="organization")

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'))
    organization = relationship("Organization", back_populates="projects")


class WorkspaceRouteDefault(Base):
    __tablename__ = "workspace_route_defaults"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    provider_order = Column(Text, nullable=True)
    sort_mode = Column(String(64), nullable=False, default="balanced")
    max_price_per_1k = Column(Float, nullable=True)
    require_capabilities = Column(String(512), nullable=True)
    require_parameters = Column(Boolean, nullable=False, default=False)
    zdr = Column(Boolean, nullable=True)
    data_collection = Column(String(64), nullable=True)


class WorkspaceGuardrailConfig(Base):
    __tablename__ = "workspace_guardrail_configs"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    allowed_providers = Column(Text, nullable=True)
    denied_providers = Column(Text, nullable=True)
    blocked_words = Column(Text, nullable=True)
    blocked_response_words = Column(Text, nullable=True)   # v0.5: response-side filter
    regex_patterns = Column(Text, nullable=True)           # v0.5: request regex patterns (JSON array)
    response_regex_patterns = Column(Text, nullable=True)  # v0.5: response regex patterns (JSON array)
    detect_pii = Column(Boolean, nullable=False, default=False)  # v0.5: enable PII detection
    log_prompt = Column(Boolean, nullable=False, default=True)   # v0.5: store prompt in logs
    log_completion = Column(Boolean, nullable=False, default=True)  # v0.5: store completion in logs
    max_prompt_chars = Column(Integer, nullable=True)
    retention_mode = Column(String(64), nullable=True)


class GuardrailPolicyPreset(Base):
    __tablename__ = "guardrail_policy_presets"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    allowed_providers = Column(Text, nullable=True)
    denied_providers = Column(Text, nullable=True)
    blocked_words = Column(Text, nullable=True)
    max_prompt_chars = Column(Integer, nullable=False, default=4000)
    retention_mode = Column(String(64), nullable=False, default="standard")


class Provider(Base):
    __tablename__ = "providers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True, nullable=False)
    adapter_type = Column(String(64), nullable=False, default="mock")
    host_type = Column(String(32), nullable=False, default="external")   # v0.4: "internal" | "external"
    region = Column(String(64), nullable=True)                           # v0.4: e.g. "jp-east-1"
    status = Column(String(32), nullable=False, default="active")
    health_status = Column(String(32), nullable=False, default="healthy")
    circuit_breaker_state = Column(String(32), nullable=False, default="closed")  # v0.4
    priority = Column(Integer, nullable=False, default=100)
    input_cost_per_1k = Column(Float, nullable=False, default=0.001)
    output_cost_per_1k = Column(Float, nullable=False, default=0.002)
    avg_latency_ms = Column(Float, nullable=False, default=500.0)
    latency_ema_alpha = Column(Float, nullable=False, default=0.1)  # v0.4: EMA smoothing factor
    capability_tags = Column(String(512), nullable=False, default="chat")
    supports_zdr = Column(Boolean, nullable=False, default=False)
    data_collection_mode = Column(String(32), nullable=False, default="allow")
    supported_parameters = Column(String(512), nullable=False, default="temperature,top_p,max_tokens,stop,tools,tool_choice,response_format")
    max_input_tokens = Column(Integer, nullable=False, default=4096)
    max_output_tokens = Column(Integer, nullable=False, default=2048)

    models = relationship("ModelCatalog", back_populates="provider")


class RouterApiKey(Base):
    __tablename__ = "router_api_keys"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True, nullable=False)
    key_hash = Column(String(255), unique=True, index=True, nullable=False)
    key_prefix = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="active")
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    environment = Column(String(64), nullable=True)
    quota_requests = Column(Integer, nullable=True)
    quota_spend_usd = Column(Float, nullable=True)        # v0.3: max cumulative spend
    request_count = Column(Integer, nullable=False, default=0)
    spend_usd = Column(Float, nullable=False, default=0.0)  # v0.3: cumulative spend tracker
    expires_at = Column(DateTime, nullable=True)
    rotated_from_key_id = Column(Integer, ForeignKey("router_api_keys.id"), nullable=True)


class ModelCatalog(Base):
    __tablename__ = "model_catalog"
    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(String(255), index=True, nullable=False)
    provider_id = Column(Integer, ForeignKey('providers.id'), nullable=False)
    provider_model_name = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="active")

    provider = relationship("Provider", back_populates="models")


class RouteRule(Base):
    __tablename__ = "route_rules"
    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(String(255), unique=True, index=True, nullable=False)
    preferred_provider_id = Column(Integer, ForeignKey('providers.id'), nullable=False)
    backup_provider_id = Column(Integer, ForeignKey('providers.id'), nullable=True)
    timeout_ms = Column(Integer, nullable=False, default=1500)

    preferred_provider = relationship("Provider", foreign_keys=[preferred_provider_id])
    backup_provider = relationship("Provider", foreign_keys=[backup_provider_id])

class RequestLog(Base):
    __tablename__ = "request_logs"
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(255), unique=True, index=True, nullable=False)
    api_key_label = Column(String(255), nullable=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=True)
    environment = Column(String(64), nullable=True)
    model_catalog_id = Column(Integer, ForeignKey('model_catalog.id'), nullable=True)
    requested_model = Column(String(255), nullable=False)
    resolved_model = Column(String(255), nullable=True)
    provider_name = Column(String(255), nullable=True)
    sticky_key = Column(String(255), nullable=True)
    cache_key = Column(String(255), nullable=True)
    cache_hit = Column(Boolean, nullable=False, default=False)
    status_code = Column(Integer, nullable=False)
    latency = Column(Float, nullable=False)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    cached_tokens = Column(Integer, nullable=False, default=0)
    reasoning_tokens = Column(Integer, nullable=False, default=0)
    cost_amount = Column(Float, nullable=False, default=0.0)
    provider_reported_cost = Column(Float, nullable=False, default=0.0)
    response_healed = Column(Boolean, nullable=False, default=False)
    healing_strategy = Column(String(64), nullable=True)
    fallback_used = Column(Boolean, nullable=False, default=False)
    error_code = Column(String(64), nullable=True)
    route_trace_json = Column(Text, nullable=True)

class BillingRecord(Base):
    """One row per completed LLM request. Written by crud._write_billing_record()."""
    __tablename__ = "billing_records"
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(255), index=True, nullable=False)
    api_key_name = Column(String(255), nullable=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=True)
    environment = Column(String(64), nullable=True)
    model = Column(String(255), nullable=True)
    provider = Column(String(255), nullable=True)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    cached_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    upstream_cost_usd = Column(Float, nullable=False, default=0.0)
    cache_hit = Column(Boolean, nullable=False, default=False)
    fallback_used = Column(Boolean, nullable=False, default=False)
    date = Column(DateTime, nullable=False)


class GuardrailConfig(Base):
    __tablename__ = "guardrail_configs"
    id = Column(Integer, primary_key=True, index=True)
    allowed_providers = Column(Text, nullable=True)
    denied_providers = Column(Text, nullable=True)
    blocked_words = Column(Text, nullable=True)
    max_prompt_chars = Column(Integer, nullable=False, default=4000)
    retention_mode = Column(String(64), nullable=False, default="standard")


class MonthlyBillingSummary(Base):
    """APScheduler rollup: one row per (org, project, model, provider) per month. (v1.2.0)"""
    __tablename__ = "monthly_billing_summaries"
    id = Column(Integer, primary_key=True, index=True)
    year_month = Column(String(7), nullable=False, index=True)   # "2026-05"
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=True)
    model = Column(String(255), nullable=True)
    provider = Column(String(255), nullable=True)
    request_count = Column(Integer, nullable=False, default=0)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    cached_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0.0)
    upstream_cost_usd = Column(Float, nullable=False, default=0.0)
    rolled_up_at = Column(DateTime, nullable=False)


class AnomalyThresholdConfig(Base):
    """Per-org configurable anomaly detection thresholds. (v1.2.0)"""
    __tablename__ = "anomaly_threshold_configs"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=True, unique=True)
    provider_failure_rate_pct = Column(Float, nullable=False, default=25.0)
    provider_latency_ms = Column(Float, nullable=False, default=600.0)
    workspace_fallback_rate_pct = Column(Float, nullable=False, default=30.0)
    cost_spike_multiplier = Column(Float, nullable=False, default=3.0)
    token_spike_multiplier = Column(Float, nullable=False, default=2.5)
    rolling_window_days = Column(Integer, nullable=False, default=7)
    updated_at = Column(DateTime, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(255), nullable=False)
    details = Column(Text, nullable=False)
    timestamp = Column(DateTime, nullable=False)


class NotificationRecord(Base):
    __tablename__ = "notification_records"
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String(64), nullable=False)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, nullable=False)


class RouteScoringProfile(Base):
    __tablename__ = "route_scoring_profiles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True, nullable=False)
    source_dataset = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="active")
    weights_json = Column(Text, nullable=False)
    trained_at = Column(DateTime, nullable=False)


class RouteScoringExperiment(Base):
    __tablename__ = "route_scoring_experiments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True, nullable=False)
    control_profile_name = Column(String(255), nullable=False, default="default_heuristic_profile")
    challenger_profile_name = Column(String(255), nullable=False)
    traffic_percentage = Column(Integer, nullable=False, default=50)
    status = Column(String(32), nullable=False, default="inactive")
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class ProviderQualityScore(Base):
    """Per (provider, workload_class) quality metrics updated by the drift monitor. (v1.3.0)"""
    __tablename__ = "provider_quality_scores"
    id = Column(Integer, primary_key=True, index=True)
    provider_name = Column(String(255), nullable=False, index=True)
    workload_class = Column(String(64), nullable=False, index=True)
    # Composite quality score in [0, 1]
    quality_score = Column(Float, nullable=False, default=1.0)
    # Raw metrics driving the score
    success_rate = Column(Float, nullable=False, default=1.0)
    schema_validity_rate = Column(Float, nullable=False, default=1.0)
    tool_call_success_rate = Column(Float, nullable=False, default=1.0)
    avg_latency_ms = Column(Float, nullable=False, default=500.0)
    avg_cost_usd = Column(Float, nullable=False, default=0.0)
    sample_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, nullable=False)


class RecalibrationEvent(Base):
    """Audit trail for automatic and manual recalibration runs. (v1.3.0)"""
    __tablename__ = "recalibration_events"
    id = Column(Integer, primary_key=True, index=True)
    trigger = Column(String(64), nullable=False)   # "auto_drift" | "manual" | "api"
    profile_name = Column(String(255), nullable=False)
    samples_used = Column(Integer, nullable=False, default=0)
    weight_delta_json = Column(Text, nullable=True)   # JSON {workload_class: {field: delta}}
    experiment_launched = Column(String(255), nullable=True)  # experiment name if auto-launched
    created_at = Column(DateTime, nullable=False)


class PromptCacheEntry(Base):
    __tablename__ = "prompt_cache_entries"
    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String(255), index=True, nullable=False)
    sticky_key = Column(String(255), index=True, nullable=True)
    provider_name = Column(String(255), nullable=False)
    resolved_model = Column(String(255), nullable=False)
    completion = Column(Text, nullable=False)
    structured_output_json = Column(Text, nullable=True)
    tool_calls_json = Column(Text, nullable=True)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    cached_tokens = Column(Integer, nullable=False, default=0)
    reasoning_tokens = Column(Integer, nullable=False, default=0)
    cost_amount = Column(Float, nullable=False, default=0.0)
    provider_reported_cost = Column(Float, nullable=False, default=0.0)
    response_healed = Column(Boolean, nullable=False, default=False)
    healing_strategy = Column(String(64), nullable=True)
    hit_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
