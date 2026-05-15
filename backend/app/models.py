from sqlalchemy import Column, Integer, String, ForeignKey, Float, Boolean, DateTime
from sqlalchemy.orm import relationship
from .db import Base


class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    projects = relationship("Project", back_populates="organization")

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'))
    organization = relationship("Organization", back_populates="projects")


class WorkspaceRouteDefault(Base):
    __tablename__ = "workspace_route_defaults"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    provider_order = Column(String, nullable=True)
    sort_mode = Column(String, nullable=False, default="balanced")
    max_price_per_1k = Column(Float, nullable=True)
    require_capabilities = Column(String, nullable=True)
    require_parameters = Column(Boolean, nullable=False, default=False)
    zdr = Column(Boolean, nullable=True)
    data_collection = Column(String, nullable=True)


class WorkspaceGuardrailConfig(Base):
    __tablename__ = "workspace_guardrail_configs"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    allowed_providers = Column(String, nullable=True)
    denied_providers = Column(String, nullable=True)
    blocked_words = Column(String, nullable=True)
    max_prompt_chars = Column(Integer, nullable=True)
    retention_mode = Column(String, nullable=True)


class GuardrailPolicyPreset(Base):
    __tablename__ = "guardrail_policy_presets"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    allowed_providers = Column(String, nullable=True)
    denied_providers = Column(String, nullable=True)
    blocked_words = Column(String, nullable=True)
    max_prompt_chars = Column(Integer, nullable=False, default=4000)
    retention_mode = Column(String, nullable=False, default="standard")


class Provider(Base):
    __tablename__ = "providers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    adapter_type = Column(String, nullable=False, default="mock")
    status = Column(String, nullable=False, default="active")
    health_status = Column(String, nullable=False, default="healthy")
    priority = Column(Integer, nullable=False, default=100)
    input_cost_per_1k = Column(Float, nullable=False, default=0.001)
    output_cost_per_1k = Column(Float, nullable=False, default=0.002)
    avg_latency_ms = Column(Float, nullable=False, default=500.0)
    capability_tags = Column(String, nullable=False, default="chat")
    supports_zdr = Column(Boolean, nullable=False, default=False)
    data_collection_mode = Column(String, nullable=False, default="allow")
    supported_parameters = Column(String, nullable=False, default="temperature,top_p,max_tokens,stop,tools,tool_choice,response_format")
    max_input_tokens = Column(Integer, nullable=False, default=4096)
    max_output_tokens = Column(Integer, nullable=False, default=2048)

    models = relationship("ModelCatalog", back_populates="provider")


class RouterApiKey(Base):
    __tablename__ = "router_api_keys"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    key_hash = Column(String, unique=True, index=True, nullable=False)
    key_prefix = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    environment = Column(String, nullable=True)
    quota_requests = Column(Integer, nullable=True)
    request_count = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime, nullable=True)
    rotated_from_key_id = Column(Integer, ForeignKey("router_api_keys.id"), nullable=True)


class ModelCatalog(Base):
    __tablename__ = "model_catalog"
    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(String, index=True, nullable=False)
    provider_id = Column(Integer, ForeignKey('providers.id'), nullable=False)
    provider_model_name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")

    provider = relationship("Provider", back_populates="models")


class RouteRule(Base):
    __tablename__ = "route_rules"
    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(String, unique=True, index=True, nullable=False)
    preferred_provider_id = Column(Integer, ForeignKey('providers.id'), nullable=False)
    backup_provider_id = Column(Integer, ForeignKey('providers.id'), nullable=True)
    timeout_ms = Column(Integer, nullable=False, default=1500)

    preferred_provider = relationship("Provider", foreign_keys=[preferred_provider_id])
    backup_provider = relationship("Provider", foreign_keys=[backup_provider_id])

class RequestLog(Base):
    __tablename__ = "request_logs"
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String, unique=True, index=True, nullable=False)
    api_key_label = Column(String, nullable=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'), nullable=True)
    project_id = Column(Integer, ForeignKey('projects.id'), nullable=True)
    environment = Column(String, nullable=True)
    model_catalog_id = Column(Integer, ForeignKey('model_catalog.id'), nullable=True)
    requested_model = Column(String, nullable=False)
    resolved_model = Column(String, nullable=True)
    provider_name = Column(String, nullable=True)
    sticky_key = Column(String, nullable=True)
    cache_key = Column(String, nullable=True)
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
    healing_strategy = Column(String, nullable=True)
    fallback_used = Column(Boolean, nullable=False, default=False)
    error_code = Column(String, nullable=True)
    route_trace_json = Column(String, nullable=True)

class BillingRecord(Base):
    __tablename__ = "billing_records"
    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey('organizations.id'))
    project_id = Column(Integer, ForeignKey('projects.id'))
    amount = Column(Float)
    date = Column(DateTime)


class GuardrailConfig(Base):
    __tablename__ = "guardrail_configs"
    id = Column(Integer, primary_key=True, index=True)
    allowed_providers = Column(String, nullable=True)
    denied_providers = Column(String, nullable=True)
    blocked_words = Column(String, nullable=True)
    max_prompt_chars = Column(Integer, nullable=False, default=4000)
    retention_mode = Column(String, nullable=False, default="standard")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    action = Column(String, nullable=False)
    details = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)


class NotificationRecord(Base):
    __tablename__ = "notification_records"
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False)
    message = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)


class RouteScoringProfile(Base):
    __tablename__ = "route_scoring_profiles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    source_dataset = Column(String, nullable=False)
    status = Column(String, nullable=False, default="active")
    weights_json = Column(String, nullable=False)
    trained_at = Column(DateTime, nullable=False)


class RouteScoringExperiment(Base):
    __tablename__ = "route_scoring_experiments"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    control_profile_name = Column(String, nullable=False, default="default_heuristic_profile")
    challenger_profile_name = Column(String, nullable=False)
    traffic_percentage = Column(Integer, nullable=False, default=50)
    status = Column(String, nullable=False, default="inactive")
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class PromptCacheEntry(Base):
    __tablename__ = "prompt_cache_entries"
    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String, index=True, nullable=False)
    sticky_key = Column(String, index=True, nullable=True)
    provider_name = Column(String, nullable=False)
    resolved_model = Column(String, nullable=False)
    completion = Column(String, nullable=False)
    structured_output_json = Column(String, nullable=True)
    tool_calls_json = Column(String, nullable=True)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    cached_tokens = Column(Integer, nullable=False, default=0)
    reasoning_tokens = Column(Integer, nullable=False, default=0)
    cost_amount = Column(Float, nullable=False, default=0.0)
    provider_reported_cost = Column(Float, nullable=False, default=0.0)
    response_healed = Column(Boolean, nullable=False, default=False)
    healing_strategy = Column(String, nullable=True)
    hit_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
