import csv
from datetime import datetime, UTC
import hashlib
import io
import json
import logging
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from . import models, schemas
from .config import settings
from .db import Base
from .services.providers import ProviderExecutionError, ProviderResult, execute_chat_completion
from .services.safety import scan_response
from .services.secrets import decrypt_secret, encrypt_secret

logger_crud = logging.getLogger(__name__)


DEFAULT_ROUTE_SCORING_WEIGHTS: dict[str, dict[str, float]] = {
    "tool_use": {"capability": 0.5, "latency": 0.3, "cost": 0.2},
    "multimodal_vision": {"capability": 0.5, "latency": 0.3, "cost": 0.2},
    "structured_extraction": {"capability": 0.35, "latency": 0.15, "cost": 0.5},
    "classification": {"capability": 0.35, "latency": 0.15, "cost": 0.5},
    "long_context": {"capability": 0.2, "latency": 0.1, "cost": 0.7},
    "chat_reasoning": {"capability": 0.3, "latency": 0.25, "cost": 0.45},
    "chat_general": {"capability": 0.3, "latency": 0.25, "cost": 0.45},
}

REQUEST_TYPE_ALIASES: dict[str, str] = {
    "mcp": "mcp_search",
    "mc_search": "mcp_search",
    "mcp-search": "mcp_search",
    "mcp_search": "mcp_search",
    "search": "mcp_search",
    "research": "mcp_search",
    "report": "report",
    "reports": "report",
    "report_generation": "report",
    "long_report": "report",
    "batch": "batch",
    "offline": "batch",
}


def _csv_to_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _list_to_csv(values: list[str] | None) -> str:
    return ",".join(values or [])


def _record_audit_log(db: Session, action: str, details: str):
    db.add(
        models.AuditLog(
            action=action,
            details=details,
            timestamp=datetime.now(UTC),
        )
    )


def _write_billing_record(
    db: Session,
    *,
    request_id: str,
    api_key_name: str | None,
    organization_id: int | None,
    project_id: int | None,
    environment: str | None,
    model: str | None,
    provider: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int,
    cost_usd: float,
    upstream_cost_usd: float,
    cache_hit: bool,
    fallback_used: bool,
) -> None:
    """Write a BillingRecord and update RouterApiKey spend counter. (v0.3)"""
    db.add(models.BillingRecord(
        request_id=request_id,
        api_key_name=api_key_name,
        organization_id=organization_id,
        project_id=project_id,
        environment=environment,
        model=model,
        provider=provider,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
        cost_usd=cost_usd,
        upstream_cost_usd=upstream_cost_usd,
        cache_hit=cache_hit,
        fallback_used=fallback_used,
        date=datetime.now(UTC),
    ))
    # Update running spend on the API key (v0.3)
    if api_key_name:
        db_key = db.query(models.RouterApiKey).filter(
            models.RouterApiKey.name == api_key_name
        ).first()
        if db_key is not None:
            db_key.spend_usd = round((db_key.spend_usd or 0.0) + cost_usd, 6)


def _check_quota(db: Session, api_key_label: str | None) -> None:
    """
    Raise ValueError if the API key has exceeded its request or spend quota. (v0.3)
    Called before routing to enforce hard limits.
    """
    if not api_key_label:
        return
    db_key = db.query(models.RouterApiKey).filter(
        models.RouterApiKey.name == api_key_label
    ).first()
    if db_key is None:
        return
    # Request count quota
    if db_key.quota_requests is not None:
        used = db_key.request_count or 0
        if used >= db_key.quota_requests:
            raise ValueError(
                f"QUOTA_EXCEEDED: API key '{api_key_label}' has reached its request quota "
                f"({used}/{db_key.quota_requests})"
            )
    # Spend quota
    if db_key.quota_spend_usd is not None:
        spent = db_key.spend_usd or 0.0
        if spent >= db_key.quota_spend_usd:
            raise ValueError(
                f"QUOTA_EXCEEDED: API key '{api_key_label}' has reached its spend quota "
                f"(${spent:.4f}/${db_key.quota_spend_usd:.4f})"
            )
    # Expiry check
    if db_key.expires_at is not None:
        expires = _normalize_stored_datetime(db_key.expires_at)
        if expires and expires < datetime.now(UTC):
            raise ValueError(f"QUOTA_EXCEEDED: API key '{api_key_label}' has expired")


def _create_notification(db: Session, notification_type: str, message: str):
    db.add(
        models.NotificationRecord(
            type=notification_type,
            message=message,
            timestamp=datetime.now(UTC),
        )
    )


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_stored_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _guardrail_row_to_schema(
    row: models.GuardrailPolicyPreset,
    organizations: dict[int, str],
    projects: dict[int, str],
) -> schemas.GuardrailPolicyPresetItem:
    return schemas.GuardrailPolicyPresetItem(
        id=row.id,
        name=row.name,
        description=row.description,
        organization_id=row.organization_id,
        organization_name=organizations.get(row.organization_id),
        project_id=row.project_id,
        project_name=projects.get(row.project_id),
        allowed_providers=_csv_to_list(row.allowed_providers),
        denied_providers=_csv_to_list(row.denied_providers),
        blocked_words=_csv_to_list(row.blocked_words),
        max_prompt_chars=row.max_prompt_chars,
        retention_mode=row.retention_mode,
    )


def ensure_schema(db: Session):
    Base.metadata.create_all(bind=db.get_bind())
    inspector = inspect(db.get_bind())
    table_columns = {
        table_name: {column["name"] for column in inspector.get_columns(table_name)}
        for table_name in inspector.get_table_names()
    }

    migrations = {
        "request_logs": [
            ("api_key_label", "ALTER TABLE request_logs ADD COLUMN api_key_label VARCHAR(255)"),
            ("environment", "ALTER TABLE request_logs ADD COLUMN environment VARCHAR(64)"),
            ("resolved_model", "ALTER TABLE request_logs ADD COLUMN resolved_model VARCHAR(255)"),
            ("route_trace_json", "ALTER TABLE request_logs ADD COLUMN route_trace_json TEXT"),
            ("sticky_key", "ALTER TABLE request_logs ADD COLUMN sticky_key VARCHAR(255)"),
            ("cache_key", "ALTER TABLE request_logs ADD COLUMN cache_key VARCHAR(255)"),
            ("cache_hit", "ALTER TABLE request_logs ADD COLUMN cache_hit BOOLEAN DEFAULT 0"),
            ("cached_tokens", "ALTER TABLE request_logs ADD COLUMN cached_tokens INTEGER DEFAULT 0"),
            ("reasoning_tokens", "ALTER TABLE request_logs ADD COLUMN reasoning_tokens INTEGER DEFAULT 0"),
            ("provider_reported_cost", "ALTER TABLE request_logs ADD COLUMN provider_reported_cost FLOAT DEFAULT 0"),
            ("response_healed", "ALTER TABLE request_logs ADD COLUMN response_healed BOOLEAN DEFAULT 0"),
            ("healing_strategy", "ALTER TABLE request_logs ADD COLUMN healing_strategy VARCHAR(64)"),
        ],
        "providers": [
            ("input_cost_per_1k", "ALTER TABLE providers ADD COLUMN input_cost_per_1k FLOAT DEFAULT 0.001"),
            ("output_cost_per_1k", "ALTER TABLE providers ADD COLUMN output_cost_per_1k FLOAT DEFAULT 0.002"),
            ("avg_latency_ms", "ALTER TABLE providers ADD COLUMN avg_latency_ms FLOAT DEFAULT 500"),
            ("latency_ema_alpha", "ALTER TABLE providers ADD COLUMN latency_ema_alpha FLOAT DEFAULT 0.1"),
            ("capability_tags", "ALTER TABLE providers ADD COLUMN capability_tags VARCHAR(512) DEFAULT 'chat'"),
            ("supports_zdr", "ALTER TABLE providers ADD COLUMN supports_zdr BOOLEAN DEFAULT 0"),
            ("data_collection_mode", "ALTER TABLE providers ADD COLUMN data_collection_mode VARCHAR(32) DEFAULT 'allow'"),
            ("supported_parameters", "ALTER TABLE providers ADD COLUMN supported_parameters VARCHAR(512) DEFAULT 'temperature,top_p,max_tokens,stop,tools,tool_choice,response_format'"),
            ("max_input_tokens", "ALTER TABLE providers ADD COLUMN max_input_tokens INTEGER DEFAULT 4096"),
            ("max_output_tokens", "ALTER TABLE providers ADD COLUMN max_output_tokens INTEGER DEFAULT 2048"),
            # v0.4 new columns
            ("host_type", "ALTER TABLE providers ADD COLUMN host_type VARCHAR(32) DEFAULT 'external'"),
            ("region", "ALTER TABLE providers ADD COLUMN region VARCHAR(64)"),
            ("circuit_breaker_state", "ALTER TABLE providers ADD COLUMN circuit_breaker_state VARCHAR(32) DEFAULT 'closed'"),
        ],
        "router_api_keys": [
            ("organization_id", "ALTER TABLE router_api_keys ADD COLUMN organization_id INTEGER"),
            ("project_id", "ALTER TABLE router_api_keys ADD COLUMN project_id INTEGER"),
            ("environment", "ALTER TABLE router_api_keys ADD COLUMN environment VARCHAR(64)"),
            ("quota_requests", "ALTER TABLE router_api_keys ADD COLUMN quota_requests INTEGER"),
            ("quota_spend_usd", "ALTER TABLE router_api_keys ADD COLUMN quota_spend_usd FLOAT"),
            ("request_count", "ALTER TABLE router_api_keys ADD COLUMN request_count INTEGER DEFAULT 0"),
            ("spend_usd", "ALTER TABLE router_api_keys ADD COLUMN spend_usd FLOAT DEFAULT 0"),
            ("expires_at", "ALTER TABLE router_api_keys ADD COLUMN expires_at DATETIME"),
            ("rotated_from_key_id", "ALTER TABLE router_api_keys ADD COLUMN rotated_from_key_id INTEGER"),
        ],
        "prompt_cache_entries": [
            ("response_healed", "ALTER TABLE prompt_cache_entries ADD COLUMN response_healed BOOLEAN DEFAULT 0"),
            ("healing_strategy", "ALTER TABLE prompt_cache_entries ADD COLUMN healing_strategy VARCHAR(64)"),
        ],
        "workspace_guardrail_configs": [
            # v0.5 new columns
            ("blocked_response_words", "ALTER TABLE workspace_guardrail_configs ADD COLUMN blocked_response_words TEXT"),
            ("regex_patterns", "ALTER TABLE workspace_guardrail_configs ADD COLUMN regex_patterns TEXT"),
            ("response_regex_patterns", "ALTER TABLE workspace_guardrail_configs ADD COLUMN response_regex_patterns TEXT"),
            ("detect_pii", "ALTER TABLE workspace_guardrail_configs ADD COLUMN detect_pii BOOLEAN DEFAULT 0"),
            ("log_prompt", "ALTER TABLE workspace_guardrail_configs ADD COLUMN log_prompt BOOLEAN DEFAULT 1"),
            ("log_completion", "ALTER TABLE workspace_guardrail_configs ADD COLUMN log_completion BOOLEAN DEFAULT 1"),
        ],
        "billing_records": [
            # v0.3 enhanced billing record columns
            ("request_id", "ALTER TABLE billing_records ADD COLUMN request_id VARCHAR(255)"),
            ("api_key_name", "ALTER TABLE billing_records ADD COLUMN api_key_name VARCHAR(255)"),
            ("environment", "ALTER TABLE billing_records ADD COLUMN environment VARCHAR(64)"),
            ("model", "ALTER TABLE billing_records ADD COLUMN model VARCHAR(255)"),
            ("provider", "ALTER TABLE billing_records ADD COLUMN provider VARCHAR(255)"),
            ("prompt_tokens", "ALTER TABLE billing_records ADD COLUMN prompt_tokens INTEGER DEFAULT 0"),
            ("completion_tokens", "ALTER TABLE billing_records ADD COLUMN completion_tokens INTEGER DEFAULT 0"),
            ("cached_tokens", "ALTER TABLE billing_records ADD COLUMN cached_tokens INTEGER DEFAULT 0"),
            ("cost_usd", "ALTER TABLE billing_records ADD COLUMN cost_usd FLOAT DEFAULT 0"),
            ("upstream_cost_usd", "ALTER TABLE billing_records ADD COLUMN upstream_cost_usd FLOAT DEFAULT 0"),
            ("cache_hit", "ALTER TABLE billing_records ADD COLUMN cache_hit BOOLEAN DEFAULT 0"),
            ("fallback_used", "ALTER TABLE billing_records ADD COLUMN fallback_used BOOLEAN DEFAULT 0"),
        ],
    }
    changed = False
    for table_name, statements in migrations.items():
        existing_columns = table_columns.get(table_name, set())
        for column_name, statement in statements:
            if column_name not in existing_columns:
                db.execute(text(statement))
                changed = True
    if changed:
        db.commit()


def seed_demo_data(db: Session):
    ensure_schema(db)
    if db.query(models.Provider).count() > 0:
        primary = db.query(models.Provider).filter(models.Provider.name == "provider_primary").first()
        if primary is not None:
            primary.input_cost_per_1k = 0.4
            primary.output_cost_per_1k = 0.7
            primary.avg_latency_ms = 280
            primary.capability_tags = "chat,tool_calling,structured_output,multimodal,zdr"
            primary.supports_zdr = True
            primary.data_collection_mode = "deny"
            primary.supported_parameters = "temperature,top_p,max_tokens,stop,tools,tool_choice,response_format"
            primary.max_input_tokens = 8192
            primary.max_output_tokens = 4096
        backup = db.query(models.Provider).filter(models.Provider.name == "provider_backup").first()
        if backup is not None:
            backup.input_cost_per_1k = 0.2
            backup.output_cost_per_1k = 0.4
            backup.avg_latency_ms = 360
            backup.capability_tags = "chat,structured_output"
            backup.supports_zdr = False
            backup.data_collection_mode = "allow"
            backup.supported_parameters = "temperature,top_p,max_tokens,stop,response_format"
            backup.max_input_tokens = 2048
            backup.max_output_tokens = 1024
        if db.query(models.GuardrailConfig).count() == 0:
            db.add(
                models.GuardrailConfig(
                    allowed_providers="",
                    denied_providers="",
                    blocked_words="",
                    max_prompt_chars=200000,
                    retention_mode="standard",
                )
            )
        if db.query(models.GuardrailPolicyPreset).count() == 0:
            db.add_all(
                [
                    models.GuardrailPolicyPreset(
                        name="balanced_default",
                        description="Balanced baseline policy for general workloads",
                        allowed_providers="",
                        denied_providers="",
                        blocked_words="",
                        max_prompt_chars=200000,
                        retention_mode="standard",
                    ),
                    models.GuardrailPolicyPreset(
                        name="finance_strict",
                        description="Strict finance policy with ZDR-friendly defaults",
                        allowed_providers="provider_primary",
                        denied_providers="provider_backup",
                        blocked_words="password,secret,ssn",
                        max_prompt_chars=200000,
                        retention_mode="strict",
                    ),
                ]
            )
        organization = db.query(models.Organization).filter(models.Organization.name == "Demo Org").first()
        if organization is None:
            organization = models.Organization(name="Demo Org")
            db.add(organization)
            db.flush()
        project = (
            db.query(models.Project)
            .filter(
                models.Project.name == "Demo Project",
                models.Project.organization_id == organization.id,
            )
            .first()
        )
        if project is None:
            db.add(models.Project(name="Demo Project", organization_id=organization.id))
        db.commit()
        return

    primary = models.Provider(
        name="provider_primary",
        adapter_type="mock",
        status="active",
        health_status="healthy",
        priority=100,
        input_cost_per_1k=0.4,
        output_cost_per_1k=0.7,
        avg_latency_ms=280,
        capability_tags="chat,tool_calling,structured_output,multimodal,zdr",
        supports_zdr=True,
        data_collection_mode="deny",
        supported_parameters="temperature,top_p,max_tokens,stop,tools,tool_choice,response_format",
        max_input_tokens=8192,
        max_output_tokens=4096,
    )
    backup = models.Provider(
        name="provider_backup",
        adapter_type="mock",
        status="active",
        health_status="healthy",
        priority=200,
        input_cost_per_1k=0.2,
        output_cost_per_1k=0.4,
        avg_latency_ms=360,
        capability_tags="chat,structured_output",
        supports_zdr=False,
        data_collection_mode="allow",
        supported_parameters="temperature,top_p,max_tokens,stop,response_format",
        max_input_tokens=2048,
        max_output_tokens=1024,
    )
    db.add_all([primary, backup])
    db.flush()

    organization = models.Organization(name="Demo Org")
    db.add(organization)
    db.flush()
    project = models.Project(name="Demo Project", organization_id=organization.id)
    db.add(project)
    db.flush()

    db.add_all(
        [
            models.ModelCatalog(
                model_id="model1",
                provider_id=primary.id,
                provider_model_name="mock-primary-model1",
                status="active",
            ),
            models.ModelCatalog(
                model_id="model1",
                provider_id=backup.id,
                provider_model_name="mock-backup-model1",
                status="active",
            ),
            models.ModelCatalog(
                model_id="model2",
                provider_id=backup.id,
                provider_model_name="mock-backup-model2",
                status="active",
            ),
            models.RouteRule(
                model_id="model1",
                preferred_provider_id=primary.id,
                backup_provider_id=backup.id,
                timeout_ms=1500,
            ),
            models.RouteRule(
                model_id="model2",
                preferred_provider_id=backup.id,
                backup_provider_id=None,
                timeout_ms=1500,
            ),
            models.GuardrailConfig(
                allowed_providers="",
                denied_providers="",
                blocked_words="",
                max_prompt_chars=200000,
                retention_mode="standard",
            ),
            models.GuardrailPolicyPreset(
                name="balanced_default",
                description="Balanced baseline policy for general workloads",
                allowed_providers="",
                denied_providers="",
                blocked_words="",
                max_prompt_chars=200000,
                retention_mode="standard",
            ),
            models.GuardrailPolicyPreset(
                name="finance_strict",
                description="Strict finance policy with ZDR-friendly defaults",
                allowed_providers="provider_primary",
                denied_providers="provider_backup",
                blocked_words="password,secret,ssn",
                max_prompt_chars=200000,
                retention_mode="strict",
            ),
        ]
    )
    db.commit()


def _get_model_mapping(
    db: Session,
    model_id: str,
    provider_id: int,
) -> models.ModelCatalog | None:
    return (
        db.query(models.ModelCatalog)
        .filter(
            models.ModelCatalog.model_id == model_id,
            models.ModelCatalog.provider_id == provider_id,
            models.ModelCatalog.status == "active",
        )
        .first()
    )


def _build_usage(
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
    reasoning_tokens: int = 0,
    provider_reported_cost: float = 0.0,
) -> schemas.Usage:
    return schemas.Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cached_tokens=cached_tokens,
        reasoning_tokens=reasoning_tokens,
        provider_reported_cost=provider_reported_cost,
    )


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _generate_router_api_key() -> str:
    return f"rk_{secrets.token_urlsafe(24)}"


def _get_guardrail_config(db: Session) -> models.GuardrailConfig:
    config = db.query(models.GuardrailConfig).order_by(models.GuardrailConfig.id.asc()).first()
    if config is None:
        config = models.GuardrailConfig(
            allowed_providers="",
            denied_providers="",
            blocked_words="",
            max_prompt_chars=200000,
            retention_mode="standard",
        )
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _get_workspace_guardrail_config(
    db: Session,
    organization_id: int | None,
    project_id: int | None,
) -> models.WorkspaceGuardrailConfig | None:
    if project_id is not None:
        row = (
            db.query(models.WorkspaceGuardrailConfig)
            .filter(models.WorkspaceGuardrailConfig.project_id == project_id)
            .order_by(models.WorkspaceGuardrailConfig.id.desc())
            .first()
        )
        if row is not None:
            return row
    if organization_id is not None:
        return (
            db.query(models.WorkspaceGuardrailConfig)
            .filter(
                models.WorkspaceGuardrailConfig.organization_id == organization_id,
                models.WorkspaceGuardrailConfig.project_id.is_(None),
            )
            .order_by(models.WorkspaceGuardrailConfig.id.desc())
            .first()
        )
    return None


def _resolve_guardrails_for_scope(
    db: Session,
    organization_id: int | None,
    project_id: int | None,
) -> tuple[models.GuardrailConfig, dict[str, Any] | None]:
    base_guardrails = _get_guardrail_config(db)
    workspace_guardrails = _get_workspace_guardrail_config(
        db=db,
        organization_id=organization_id,
        project_id=project_id,
    )
    if workspace_guardrails is None:
        return base_guardrails, None

    resolved_guardrails = models.GuardrailConfig(
        allowed_providers=workspace_guardrails.allowed_providers
        if workspace_guardrails.allowed_providers is not None
        else base_guardrails.allowed_providers,
        denied_providers=workspace_guardrails.denied_providers
        if workspace_guardrails.denied_providers is not None
        else base_guardrails.denied_providers,
        blocked_words=workspace_guardrails.blocked_words
        if workspace_guardrails.blocked_words is not None
        else base_guardrails.blocked_words,
        max_prompt_chars=workspace_guardrails.max_prompt_chars
        if workspace_guardrails.max_prompt_chars is not None
        else base_guardrails.max_prompt_chars,
        retention_mode=workspace_guardrails.retention_mode
        if workspace_guardrails.retention_mode is not None
        else base_guardrails.retention_mode,
    )
    return resolved_guardrails, {
        "workspace_guardrail_id": workspace_guardrails.id,
        "organization_id": organization_id,
        "project_id": project_id,
        "applied_fields": [
            field
            for field in [
                "allowed_providers" if workspace_guardrails.allowed_providers is not None else None,
                "denied_providers" if workspace_guardrails.denied_providers is not None else None,
                "blocked_words" if workspace_guardrails.blocked_words is not None else None,
                "max_prompt_chars" if workspace_guardrails.max_prompt_chars is not None else None,
                "retention_mode" if workspace_guardrails.retention_mode is not None else None,
            ]
            if field is not None
        ],
    }


def _extract_prompt_from_request(request: schemas.ChatCompletionRequest) -> str:
    parts: list[str] = []
    for message in request.messages:
        content = message.content
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
    return "\n".join(part for part in parts if part)


def _build_request_cache_key(
    request: schemas.ChatCompletionRequest,
    organization_id: int | None = None,
    project_id: int | None = None,
    environment: str | None = None,
    guardrails: models.GuardrailConfig | None = None,
) -> str:
    canonical = {
        "model": request.model,
        "messages": [message.model_dump() for message in request.messages],
        "temperature": request.temperature,
        "top_p": request.top_p,
        "max_tokens": request.max_tokens,
        "stop": request.stop,
        "tools": [tool.model_dump() for tool in request.tools] if request.tools else None,
        "tool_choice": request.tool_choice,
        "response_format": request.response_format.model_dump(exclude_none=True) if request.response_format else None,
        "provider": request.provider.model_dump(exclude_none=True) if request.provider else None,
        "organization_id": organization_id,
        "project_id": project_id,
        "environment": environment,
        "guardrails": (
            {
                "allowed_providers": guardrails.allowed_providers,
                "denied_providers": guardrails.denied_providers,
                "blocked_words": guardrails.blocked_words,
                "max_prompt_chars": guardrails.max_prompt_chars,
                "retention_mode": guardrails.retention_mode,
            }
            if guardrails
            else None
        ),
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _resolve_sticky_provider_name(db: Session, request: schemas.ChatCompletionRequest) -> str | None:
    sticky_key = request.provider.sticky_key if request.provider else None
    if not sticky_key:
        return None
    query = (
        db.query(models.RequestLog)
        .filter(
            models.RequestLog.sticky_key == sticky_key,
            models.RequestLog.status_code < 400,
            models.RequestLog.provider_name.isnot(None),
        )
        .order_by(models.RequestLog.id.desc())
    )
    if request.model != "router/auto":
        query = query.filter(models.RequestLog.requested_model == request.model)
    row = query.first()
    return row.provider_name if row is not None else None


def _resolve_workspace_scope_ids(
    db: Session,
    request: schemas.ChatCompletionRequest,
    organization_id: int | None,
    project_id: int | None,
) -> tuple[int | None, int | None]:
    resolved_organization_id = organization_id
    resolved_project_id = project_id
    if request.provider and request.provider.organization and resolved_organization_id is None:
        org = db.query(models.Organization).filter(models.Organization.name == request.provider.organization).first()
        if org is not None:
            resolved_organization_id = org.id
    if request.provider and request.provider.project and resolved_project_id is None:
        project_query = db.query(models.Project).filter(models.Project.name == request.provider.project)
        if resolved_organization_id is not None:
            project_query = project_query.filter(models.Project.organization_id == resolved_organization_id)
        project = project_query.first()
        if project is not None:
            resolved_project_id = project.id
            resolved_organization_id = resolved_organization_id or project.organization_id
    return resolved_organization_id, resolved_project_id


def _get_workspace_route_default(
    db: Session,
    organization_id: int | None,
    project_id: int | None,
) -> models.WorkspaceRouteDefault | None:
    if project_id is not None:
        row = (
            db.query(models.WorkspaceRouteDefault)
            .filter(models.WorkspaceRouteDefault.project_id == project_id)
            .order_by(models.WorkspaceRouteDefault.id.desc())
            .first()
        )
        if row is not None:
            return row
    if organization_id is not None:
        return (
            db.query(models.WorkspaceRouteDefault)
            .filter(
                models.WorkspaceRouteDefault.organization_id == organization_id,
                models.WorkspaceRouteDefault.project_id.is_(None),
            )
            .order_by(models.WorkspaceRouteDefault.id.desc())
            .first()
        )
    return None


def _apply_workspace_route_defaults(
    db: Session,
    request: schemas.ChatCompletionRequest,
    organization_id: int | None,
    project_id: int | None,
) -> tuple[int | None, int | None, dict[str, Any] | None]:
    resolved_organization_id, resolved_project_id = _resolve_workspace_scope_ids(
        db=db,
        request=request,
        organization_id=organization_id,
        project_id=project_id,
    )
    row = _get_workspace_route_default(
        db=db,
        organization_id=resolved_organization_id,
        project_id=resolved_project_id,
    )
    if row is None:
        return resolved_organization_id, resolved_project_id, None

    if request.provider is None:
        request.provider = schemas.ProviderPreferences()

    applied_fields: list[str] = []
    if not request.provider.order and row.provider_order:
        request.provider.order = _csv_to_list(row.provider_order)
        applied_fields.append("order")
    if request.provider.sort == "balanced" and row.sort_mode != "balanced":
        request.provider.sort = row.sort_mode
        applied_fields.append("sort")
    if request.provider.max_price_per_1k is None and row.max_price_per_1k is not None:
        request.provider.max_price_per_1k = row.max_price_per_1k
        applied_fields.append("max_price_per_1k")
    if not request.provider.require_capabilities and row.require_capabilities:
        request.provider.require_capabilities = _csv_to_list(row.require_capabilities)
        applied_fields.append("require_capabilities")
    if request.provider.require_parameters is False and row.require_parameters:
        request.provider.require_parameters = True
        applied_fields.append("require_parameters")
    if request.provider.zdr is None and row.zdr is not None:
        request.provider.zdr = row.zdr
        applied_fields.append("zdr")
    if request.provider.data_collection is None and row.data_collection is not None:
        request.provider.data_collection = row.data_collection
        applied_fields.append("data_collection")

    return resolved_organization_id, resolved_project_id, {
        "workspace_default_id": row.id,
        "organization_id": resolved_organization_id,
        "project_id": resolved_project_id,
        "applied_fields": applied_fields,
        "provider_order": _csv_to_list(row.provider_order),
        "sort_mode": row.sort_mode,
    }


def _get_prompt_cache_entry(
    db: Session,
    cache_key: str,
    provider_name: str,
    resolved_model: str,
) -> models.PromptCacheEntry | None:
    return (
        db.query(models.PromptCacheEntry)
        .filter(
            models.PromptCacheEntry.cache_key == cache_key,
            models.PromptCacheEntry.provider_name == provider_name,
            models.PromptCacheEntry.resolved_model == resolved_model,
        )
        .order_by(models.PromptCacheEntry.updated_at.desc())
        .first()
    )


def _upsert_prompt_cache_entry(
    db: Session,
    cache_key: str,
    sticky_key: str | None,
    provider_name: str,
    resolved_model: str,
    result: Any,
):
    entry = _get_prompt_cache_entry(db, cache_key, provider_name, resolved_model)
    now = datetime.now(UTC)
    if entry is None:
        entry = models.PromptCacheEntry(
            cache_key=cache_key,
            sticky_key=sticky_key,
            provider_name=provider_name,
            resolved_model=resolved_model,
            completion=result.completion,
            structured_output_json=json.dumps(result.structured_output, ensure_ascii=False) if result.structured_output is not None else None,
            tool_calls_json=json.dumps(result.tool_calls, ensure_ascii=False) if result.tool_calls is not None else None,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            cached_tokens=result.cached_tokens,
            reasoning_tokens=result.reasoning_tokens,
            cost_amount=result.cost_amount,
            provider_reported_cost=result.provider_reported_cost,
            response_healed=result.response_healed,
            healing_strategy=result.healing_strategy,
            hit_count=0,
            created_at=now,
            updated_at=now,
        )
        db.add(entry)
        return
    entry.sticky_key = sticky_key
    entry.completion = result.completion
    entry.structured_output_json = json.dumps(result.structured_output, ensure_ascii=False) if result.structured_output is not None else None
    entry.tool_calls_json = json.dumps(result.tool_calls, ensure_ascii=False) if result.tool_calls is not None else None
    entry.prompt_tokens = result.prompt_tokens
    entry.completion_tokens = result.completion_tokens
    entry.cached_tokens = result.cached_tokens
    entry.reasoning_tokens = result.reasoning_tokens
    entry.cost_amount = result.cost_amount
    entry.provider_reported_cost = result.provider_reported_cost
    entry.response_healed = result.response_healed
    entry.healing_strategy = result.healing_strategy
    entry.updated_at = now


def _normalize_weight_map(weights: dict[str, float]) -> dict[str, float]:
    normalized = {
        "capability": max(float(weights.get("capability", 0.0)), 0.01),
        "latency": max(float(weights.get("latency", 0.0)), 0.01),
        "cost": max(float(weights.get("cost", 0.0)), 0.01),
    }
    total = sum(normalized.values())
    return {
        key: round(value / total, 4)
        for key, value in normalized.items()
    }


def _get_default_route_score_weights(workload_class: str) -> dict[str, float]:
    return dict(
        DEFAULT_ROUTE_SCORING_WEIGHTS.get(
            workload_class,
            DEFAULT_ROUTE_SCORING_WEIGHTS["chat_general"],
        )
    )


def _get_active_route_scoring_profile(db: Session) -> models.RouteScoringProfile | None:
    return (
        db.query(models.RouteScoringProfile)
        .filter(models.RouteScoringProfile.status == "active")
        .order_by(models.RouteScoringProfile.trained_at.desc())
        .first()
    )


def _get_route_scoring_profile_by_name(
    db: Session | None,
    profile_name: str | None,
) -> models.RouteScoringProfile | None:
    if db is None or not profile_name or profile_name == "default_heuristic_profile":
        return None
    return (
        db.query(models.RouteScoringProfile)
        .filter(models.RouteScoringProfile.name == profile_name)
        .order_by(models.RouteScoringProfile.trained_at.desc())
        .first()
    )


def _get_active_route_scoring_experiment(db: Session | None) -> models.RouteScoringExperiment | None:
    if db is None:
        return None
    return (
        db.query(models.RouteScoringExperiment)
        .filter(models.RouteScoringExperiment.status == "active")
        .order_by(models.RouteScoringExperiment.updated_at.desc())
        .first()
    )


def _get_active_route_scoring_profile_name(db: Session | None) -> str:
    if db is None:
        return "default_heuristic_profile"
    profile = _get_active_route_scoring_profile(db)
    return profile.name if profile is not None else "default_heuristic_profile"


def _get_route_score_weights_for_profile(
    db: Session | None,
    workload_class: str,
    profile_name: str | None,
) -> dict[str, float]:
    default_weights = _get_default_route_score_weights(workload_class)
    profile = _get_route_scoring_profile_by_name(db, profile_name)
    if profile is None:
        return default_weights
    try:
        parsed = json.loads(profile.weights_json)
    except json.JSONDecodeError:
        return default_weights
    stored_weights = parsed.get(workload_class)
    if not isinstance(stored_weights, dict):
        return default_weights
    return _normalize_weight_map({
        "capability": stored_weights.get("capability", default_weights["capability"]),
        "latency": stored_weights.get("latency", default_weights["latency"]),
        "cost": stored_weights.get("cost", default_weights["cost"]),
    })


def _get_route_score_weights(db: Session | None, workload_class: str) -> dict[str, float]:
    return _get_route_score_weights_for_profile(
        db=db,
        workload_class=workload_class,
        profile_name=_get_active_route_scoring_profile_name(db),
    )


def _compute_route_scoring_experiment_bucket(request: schemas.ChatCompletionRequest) -> int:
    seed = (
        (request.provider.sticky_key if request.provider and request.provider.sticky_key else None)
        or f"{request.model}:{_extract_prompt_from_request(request)}"
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _resolve_route_scoring_context(
    db: Session | None,
    request: schemas.ChatCompletionRequest,
    workload_class: str,
) -> tuple[dict[str, float], str, dict[str, Any] | None]:
    experiment = _get_active_route_scoring_experiment(db)
    if experiment is not None:
        bucket = _compute_route_scoring_experiment_bucket(request)
        variant = "challenger" if bucket < experiment.traffic_percentage else "control"
        profile_name = (
            experiment.challenger_profile_name
            if variant == "challenger"
            else experiment.control_profile_name
        )
        applied_profile_name = (
            profile_name
            if profile_name == "default_heuristic_profile" or _get_route_scoring_profile_by_name(db, profile_name) is not None
            else "default_heuristic_profile"
        )
        return (
            _get_route_score_weights_for_profile(db, workload_class, applied_profile_name),
            applied_profile_name,
            {
                "name": experiment.name,
                "variant": variant,
                "bucket": bucket,
                "control_profile_name": experiment.control_profile_name,
                "challenger_profile_name": experiment.challenger_profile_name,
                "traffic_percentage": experiment.traffic_percentage,
            },
        )
    applied_profile_name = _get_active_route_scoring_profile_name(db)
    return (
        _get_route_score_weights_for_profile(db, workload_class, applied_profile_name),
        applied_profile_name,
        None,
    )


def _candidate_score_from_components(
    candidate: dict[str, Any],
    weights: dict[str, float],
) -> float:
    components = candidate.get("score_components", {})
    capability_score = float(components.get("capability_score", 0.0))
    latency_score = float(components.get("latency_score", 0.0))
    cost_score = float(components.get("cost_score", 0.0))
    normalized = _normalize_weight_map(weights)
    return (
        normalized["capability"] * capability_score
        + normalized["latency"] * latency_score * 100
        + normalized["cost"] * cost_score
    )


def _select_provider_from_trace(
    trace: dict[str, Any],
    weights: dict[str, float],
) -> str | None:
    accepted_candidates = [
        item for item in trace.get("candidates", [])
        if item.get("accepted")
    ]
    if not accepted_candidates:
        return None
    ranked = sorted(
        accepted_candidates,
        key=lambda item: (
            -_candidate_score_from_components(item, weights),
            item.get("preferred_order_index") if item.get("preferred_order_index") is not None else 9999,
            item.get("priority", 9999),
            item.get("avg_latency_ms", 999999),
        ),
    )
    return ranked[0].get("provider")


def _route_trace_changed_from_default(trace: dict[str, Any]) -> bool:
    workload_class = trace.get("workload_class", "chat_general")
    heuristic_provider = _select_provider_from_trace(trace, _get_default_route_score_weights(workload_class))
    learned_provider = trace.get("selected_provider") or _select_provider_from_trace(
        trace,
        trace.get("applied_weights") or _get_default_route_score_weights(workload_class),
    )
    return heuristic_provider != learned_provider


def _generate_weight_grid(step: float = 0.1) -> list[dict[str, float]]:
    values = [round(index * step, 2) for index in range(1, int(1 / step))]
    combinations: list[dict[str, float]] = []
    for capability in values:
        for latency in values:
            cost = round(1.0 - capability - latency, 2)
            if cost < 0.1:
                continue
            combinations.append(
                _normalize_weight_map(
                    {
                        "capability": capability,
                        "latency": latency,
                        "cost": cost,
                    }
                )
            )
    return combinations


def _resolve_dataset_path(dataset_path: str) -> Path:
    path = Path(dataset_path)
    if path.exists():
        return path
    backend_root_candidate = Path(__file__).resolve().parents[1] / dataset_path
    if backend_root_candidate.exists():
        return backend_root_candidate
    repo_root_candidate = Path(__file__).resolve().parents[2] / dataset_path
    if repo_root_candidate.exists():
        return repo_root_candidate
    return path


def _truncate_message_content(content, limit: int):
    """Truncate a message's text content to at most ``limit`` chars.

    Returns ``(new_content, chars_used)``. Non-text parts (e.g. image items in a
    multimodal content list) are preserved as-is and don't count against the
    budget. When ``limit`` is 0 all text is dropped but non-text parts survive.
    """
    if isinstance(content, str):
        if limit <= 0:
            return "", 0
        chunk = content[:limit]
        return chunk, len(chunk)
    if isinstance(content, list):
        remaining = max(0, limit)
        copied: list = []
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "text":
                copied.append(item)
                continue
            text_value = str(item.get("text", ""))[:remaining]
            remaining -= len(text_value)
            copied.append({**item, "text": text_value})
        return copied, max(0, limit) - remaining
    if limit <= 0:
        return "", 0
    text_value = str(content)[:limit]
    return text_value, len(text_value)


def _compress_request_messages(request: schemas.ChatCompletionRequest, max_chars: int):
    prompt = _extract_prompt_from_request(request)
    if len(prompt) <= max_chars:
        return

    messages = request.messages
    # The most recent user message carries the actual request — it must never be
    # dropped. Reserve its budget first, then share whatever remains across the
    # other messages (system prompt + prior history) in order. This fixes the bug
    # where a long system prompt could consume the entire budget and the user's
    # message got silently discarded, leaving the model with no question to answer.
    last_user_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == "user":
            last_user_idx = i
            break

    if last_user_idx is not None:
        preserved_content, preserved_used = _truncate_message_content(
            messages[last_user_idx].content, max_chars
        )
    else:
        preserved_content, preserved_used = None, 0

    remaining = max(0, max_chars - preserved_used)
    compressed_messages: list[schemas.ChatMessage] = []
    for idx, message in enumerate(messages):
        if idx == last_user_idx:
            compressed_messages.append(
                schemas.ChatMessage(role=message.role, content=preserved_content)
            )
            continue
        new_content, used = _truncate_message_content(message.content, remaining)
        remaining -= used
        compressed_messages.append(
            schemas.ChatMessage(role=message.role, content=new_content)
        )
    request.messages = compressed_messages


def _infer_required_capabilities(request: schemas.ChatCompletionRequest) -> set[str]:
    capabilities = {"chat"}
    if request.tools:
        capabilities.add("tool_calling")
    if request.response_format:
        capabilities.add("structured_output")
    for message in request.messages:
        if isinstance(message.content, list):
            for item in message.content:
                if isinstance(item, dict) and item.get("type") in {"image_url", "input_image"}:
                    capabilities.add("multimodal")
    if request.provider and request.provider.require_capabilities:
        capabilities.update(request.provider.require_capabilities)
    return capabilities


def classify_workload(request: schemas.ChatCompletionRequest) -> str:
    if request.tools:
        return "tool_use"
    if request.response_format is not None:
        return "structured_extraction"
    prompt = _extract_prompt_from_request(request).lower()
    prompt_length = len(prompt)
    if any(keyword in prompt for keyword in ["classify", "category", "triage", "label"]):
        return "classification"
    if any(keyword in prompt for keyword in ["reason", "analyze", "decision", "compare"]):
        return "chat_reasoning"
    for message in request.messages:
        if isinstance(message.content, list):
            for item in message.content:
                if isinstance(item, dict) and item.get("type") in {"image_url", "input_image"}:
                    return "multimodal_vision"
    if prompt_length > 240:
        return "long_context"
    return "chat_general"


def _parse_request_type_timeout_ms() -> dict[str, int]:
    values: dict[str, int] = {}
    for item in _csv_to_list(settings.request_type_timeout_ms):
        if "=" not in item:
            continue
        key, raw_value = item.split("=", 1)
        key = key.strip()
        try:
            timeout_ms = int(raw_value.strip())
        except ValueError:
            logger_crud.warning("Ignoring invalid request type timeout item: %s", item)
            continue
        if key and timeout_ms > 0:
            values[key] = timeout_ms
    return values


def _request_type_timeout_key(request: schemas.ChatCompletionRequest, workload_class: str) -> str:
    metadata = request.metadata or {}
    explicit = (
        metadata.get("timeout_tier")
        or metadata.get("request_type")
        or metadata.get("task_type")
    )
    if isinstance(explicit, str) and explicit.strip():
        normalized = explicit.strip().lower().replace(" ", "_")
        return REQUEST_TYPE_ALIASES.get(normalized, normalized)
    return workload_class


def _resolve_request_timeout_ms(
    request: schemas.ChatCompletionRequest,
    workload_class: str,
    route_timeout_ms: int | None,
) -> tuple[int | None, dict[str, Any] | None]:
    timeouts = _parse_request_type_timeout_ms()
    timeout_key = _request_type_timeout_key(request, workload_class)
    request_type_timeout_ms = timeouts.get(timeout_key)

    candidates = [
        value
        for value in (route_timeout_ms, request_type_timeout_ms)
        if value is not None and value > 0
    ]
    if not candidates:
        return None, None

    effective_timeout_ms = max(candidates)
    source_parts = []
    if route_timeout_ms:
        source_parts.append("route_rule")
    if request_type_timeout_ms:
        source_parts.append("request_type")
    return effective_timeout_ms, {
        "source": "+".join(source_parts),
        "workload_class": workload_class,
        "request_type": timeout_key,
        "route_timeout_ms": route_timeout_ms,
        "request_type_timeout_ms": request_type_timeout_ms,
        "effective_timeout_ms": effective_timeout_ms,
        "timeout_s": effective_timeout_ms / 1000.0,
    }


def _provider_capabilities(provider: models.Provider) -> set[str]:
    return set(_csv_to_list(provider.capability_tags))


def _provider_supported_parameters(provider: models.Provider) -> set[str]:
    return set(_csv_to_list(provider.supported_parameters))


def _requested_parameter_names(request: schemas.ChatCompletionRequest) -> set[str]:
    parameter_names: set[str] = set()
    if request.temperature is not None:
        parameter_names.add("temperature")
    if request.top_p is not None:
        parameter_names.add("top_p")
    if request.max_tokens is not None:
        parameter_names.add("max_tokens")
    if request.stop is not None:
        parameter_names.add("stop")
    if request.tools is not None:
        parameter_names.add("tools")
    if request.tool_choice is not None:
        parameter_names.add("tool_choice")
    if request.response_format is not None:
        parameter_names.add("response_format")
    return parameter_names


def _estimate_prompt_tokens(request: schemas.ChatCompletionRequest) -> int:
    prompt = _extract_prompt_from_request(request)
    return max(len(prompt.split()), 1) if prompt else 0


def _provider_sort_key(
    provider: models.Provider,
    request: schemas.ChatCompletionRequest,
):
    sort_mode = request.provider.sort if request.provider else "balanced"
    total_price = provider.input_cost_per_1k + provider.output_cost_per_1k
    if sort_mode == "price":
        return (total_price, provider.avg_latency_ms, provider.priority)
    if sort_mode == "latency":
        return (provider.avg_latency_ms, total_price, provider.priority)
    if sort_mode == "priority":
        return (provider.priority, provider.avg_latency_ms, total_price)
    return (total_price + provider.avg_latency_ms / 1000 + provider.priority / 1000, provider.priority)


def _get_provider_quality_score(db: Session | None, provider_name: str, workload_class: str) -> float:
    """Return the composite quality score [0,1] for a provider+workload_class. Default 1.0."""
    if db is None:
        return 1.0
    rec = (
        db.query(models.ProviderQualityScore)
        .filter(
            models.ProviderQualityScore.provider_name == provider_name,
            models.ProviderQualityScore.workload_class == workload_class,
        )
        .first()
    )
    return rec.quality_score if rec else 1.0


def _provider_route_score(
    provider: models.Provider,
    request: schemas.ChatCompletionRequest,
    workload_class: str,
    weights: dict[str, float] | None = None,
    db: Session | None = None,
) -> tuple[float, dict[str, float]]:
    total_price = provider.input_cost_per_1k + provider.output_cost_per_1k
    capabilities = _provider_capabilities(provider)
    active_weights = _normalize_weight_map(weights or _get_default_route_score_weights(workload_class))

    required_capabilities = _infer_required_capabilities(request)
    matched_capabilities = len(required_capabilities.intersection(capabilities))
    capability_score = matched_capabilities / max(len(required_capabilities), 1)
    latency_score = 1 / max(provider.avg_latency_ms, 1)
    cost_score = 1 / max(total_price, 0.001)

    # v1.3.0: multiply by quality score from drift monitor measurements
    quality_multiplier = _get_provider_quality_score(db, provider.name, workload_class)

    raw_score = (
        active_weights["capability"] * capability_score
        + active_weights["latency"] * latency_score * 100
        + active_weights["cost"] * cost_score
    ) * quality_multiplier

    return raw_score, {
        "applied_capability_weight": round(active_weights["capability"], 4),
        "applied_latency_weight": round(active_weights["latency"], 4),
        "applied_cost_weight": round(active_weights["cost"], 4),
        "capability_score": round(capability_score, 4),
        "latency_score": round(latency_score, 6),
        "cost_score": round(cost_score, 6),
        "quality_multiplier": round(quality_multiplier, 4),
        "raw_score": round(raw_score, 6),
    }


def _build_candidate_trace(
    request: schemas.ChatCompletionRequest,
    candidates: list[tuple[models.Provider, models.ModelCatalog]],
    guardrails: models.GuardrailConfig,
    route_weights: dict[str, float] | None = None,
    sticky_provider_name: str | None = None,
    db: Session | None = None,
) -> list[dict[str, Any]]:
    required_capabilities = _infer_required_capabilities(request)
    requested_parameter_names = _requested_parameter_names(request)
    estimated_prompt_tokens = _estimate_prompt_tokens(request)
    requested_output_tokens = request.max_tokens or 0
    allowed_providers = set(_csv_to_list(guardrails.allowed_providers))
    denied_providers = set(_csv_to_list(guardrails.denied_providers))
    max_price = request.provider.max_price_per_1k if request.provider else None
    preferred_order = request.provider.order if request.provider and request.provider.order else []
    preferred_index = {name: index for index, name in enumerate(preferred_order)}
    workload_class = classify_workload(request)
    traces: list[dict[str, Any]] = []
    for provider, mapping in candidates:
        capabilities = _provider_capabilities(provider)
        supported_parameters = _provider_supported_parameters(provider)
        total_price = provider.input_cost_per_1k + provider.output_cost_per_1k
        sort_key = _provider_sort_key(provider, request)
        route_score, score_components = _provider_route_score(provider, request, workload_class, route_weights, db=db)
        accepted = True
        reject_reason = None
        if not required_capabilities.issubset(capabilities):
            accepted = False
            reject_reason = "missing_required_capabilities"
        elif request.provider and request.provider.zdr is True and not provider.supports_zdr:
            accepted = False
            reject_reason = "zdr_not_supported"
        elif request.provider and request.provider.data_collection == "deny" and provider.data_collection_mode != "deny":
            accepted = False
            reject_reason = "data_collection_not_allowed"
        elif request.provider and request.provider.require_parameters and not requested_parameter_names.issubset(supported_parameters):
            accepted = False
            reject_reason = "missing_required_parameters"
        elif estimated_prompt_tokens > provider.max_input_tokens:
            accepted = False
            reject_reason = "prompt_tokens_above_provider_limit"
        elif requested_output_tokens and requested_output_tokens > provider.max_output_tokens:
            accepted = False
            reject_reason = "max_output_tokens_above_provider_limit"
        elif allowed_providers and provider.name not in allowed_providers:
            accepted = False
            reject_reason = "not_in_allowed_providers"
        elif provider.name in denied_providers:
            accepted = False
            reject_reason = "provider_denied_by_guardrail"
        elif max_price is not None and total_price > max_price:
            accepted = False
            reject_reason = "price_above_request_budget"

        traces.append(
            {
                "provider": provider.name,
                "mapped_model": mapping.model_id,
                "provider_model_name": mapping.provider_model_name,
                "capabilities": sorted(capabilities),
                "required_capabilities": sorted(required_capabilities),
                "requested_parameters": sorted(requested_parameter_names),
                "supported_parameters": sorted(supported_parameters),
                "estimated_prompt_tokens": estimated_prompt_tokens,
                "requested_output_tokens": requested_output_tokens,
                "max_input_tokens": provider.max_input_tokens,
                "max_output_tokens": provider.max_output_tokens,
                "supports_zdr": provider.supports_zdr,
                "data_collection_mode": provider.data_collection_mode,
                "input_cost_per_1k": provider.input_cost_per_1k,
                "output_cost_per_1k": provider.output_cost_per_1k,
                "total_price_per_1k": round(total_price, 6),
                "avg_latency_ms": provider.avg_latency_ms,
                "priority": provider.priority,
                "sticky_match": provider.name == sticky_provider_name if sticky_provider_name else False,
                "sticky_provider_name": sticky_provider_name,
                "preferred_order_index": preferred_index.get(provider.name),
                "sort_key": list(sort_key) if isinstance(sort_key, tuple) else sort_key,
                "workload_class": workload_class,
                "applied_weights": _normalize_weight_map(route_weights or _get_default_route_score_weights(workload_class)),
                "route_score": round(route_score, 6),
                "score_components": score_components,
                "accepted": accepted,
                "reject_reason": reject_reason,
            }
        )
    return traces


def _filter_and_sort_candidates(
    request: schemas.ChatCompletionRequest,
    candidates: list[tuple[models.Provider, models.ModelCatalog]],
    guardrails: models.GuardrailConfig,
    route_weights: dict[str, float] | None = None,
    sticky_provider_name: str | None = None,
) -> list[tuple[models.Provider, models.ModelCatalog]]:
    traces = _build_candidate_trace(request, candidates, guardrails, route_weights, sticky_provider_name)
    accepted_names = {
        item["provider"]
        for item in traces
        if item["accepted"]
    }
    preferred_order = request.provider.order if request.provider and request.provider.order else []
    preferred_index = {name: index for index, name in enumerate(preferred_order)}

    filtered = [
        (provider, mapping)
        for provider, mapping in candidates
        if provider.name in accepted_names
    ]

    sort_mode = request.provider.sort if request.provider else "balanced"

    filtered.sort(
        key=lambda item: (
            preferred_index.get(item[0].name, len(preferred_index)),
            0 if sticky_provider_name and item[0].name == sticky_provider_name else 1,
            *(
                (_provider_sort_key(item[0], request), -_provider_route_score(item[0], request, classify_workload(request), route_weights)[0])
                if sort_mode in {"price", "latency", "priority"}
                else (-_provider_route_score(item[0], request, classify_workload(request), route_weights)[0], _provider_sort_key(item[0], request))
            ),
        )
    )
    if request.provider and request.provider.allow_fallbacks is False:
        return filtered[:1]
    return filtered


def _resolve_candidates(
    db: Session,
    request: schemas.ChatCompletionRequest,
    guardrails: models.GuardrailConfig,
    route_weights: dict[str, float] | None = None,
) -> list[tuple[models.Provider, models.ModelCatalog]]:
    sticky_provider_name = _resolve_sticky_provider_name(db, request)
    if request.model == "router/auto":
        rows = (
            db.query(models.ModelCatalog, models.Provider)
            .join(models.Provider, models.Provider.id == models.ModelCatalog.provider_id)
            .filter(models.ModelCatalog.status == "active")
            .all()
        )
        candidates = [(provider, model) for model, provider in rows]
        return _filter_and_sort_candidates(request, candidates, guardrails, route_weights, sticky_provider_name)

    route = (
        db.query(models.RouteRule)
        .filter(models.RouteRule.model_id == request.model)
        .first()
    )
    if route is None:
        raise ValueError(f"INVALID_MODEL: {request.model}")

    providers = [provider for provider in [route.preferred_provider, route.backup_provider] if provider is not None]
    candidates: list[tuple[models.Provider, models.ModelCatalog]] = []
    for provider in providers:
        mapping = _get_model_mapping(db, request.model, provider.id)
        if mapping is not None:
            candidates.append((provider, mapping))
    no_dynamic_preferences = not request.provider or (
        not request.provider.order
        and request.provider.sort == "balanced"
        and request.provider.max_price_per_1k is None
        and not request.provider.require_capabilities
        and not request.provider.require_parameters
        and request.provider.zdr is None
        and request.provider.data_collection is None
        and not request.provider.sticky_key
    )
    filtered = _filter_and_sort_candidates(request, candidates, guardrails, route_weights, sticky_provider_name)
    if no_dynamic_preferences and not sticky_provider_name:
        preferred_names = [provider.name for provider in providers]
        filtered.sort(key=lambda item: preferred_names.index(item[0].name))
    return filtered


def build_route_decision_trace(
    db: Session,
    request: schemas.ChatCompletionRequest,
    guardrail_override: dict[str, Any] | None = None,
    organization_id: int | None = None,
    project_id: int | None = None,
) -> dict[str, Any]:
    seed_demo_data(db)
    resolved_organization_id, resolved_project_id = _resolve_workspace_scope_ids(
        db=db,
        request=request,
        organization_id=organization_id,
        project_id=project_id,
    )
    scoped_guardrails, workspace_guardrail_meta = _resolve_guardrails_for_scope(
        db=db,
        organization_id=resolved_organization_id,
        project_id=resolved_project_id,
    )
    guardrails = models.GuardrailConfig(
        allowed_providers=guardrail_override.get("allowed_providers", scoped_guardrails.allowed_providers) if guardrail_override else scoped_guardrails.allowed_providers,
        denied_providers=guardrail_override.get("denied_providers", scoped_guardrails.denied_providers) if guardrail_override else scoped_guardrails.denied_providers,
        blocked_words=guardrail_override.get("blocked_words", scoped_guardrails.blocked_words) if guardrail_override else scoped_guardrails.blocked_words,
        max_prompt_chars=guardrail_override.get("max_prompt_chars", scoped_guardrails.max_prompt_chars) if guardrail_override else scoped_guardrails.max_prompt_chars,
        retention_mode=guardrail_override.get("retention_mode", scoped_guardrails.retention_mode) if guardrail_override else scoped_guardrails.retention_mode,
    )
    prompt = _extract_prompt_from_request(request)
    blocked_words = _csv_to_list(guardrails.blocked_words)

    workload_class = classify_workload(request)
    route_weights, applied_profile_name, experiment_meta = _resolve_route_scoring_context(db, request, workload_class)
    sticky_provider_name = _resolve_sticky_provider_name(db, request)
    if request.model == "router/auto":
        rows = (
            db.query(models.ModelCatalog, models.Provider)
            .join(models.Provider, models.Provider.id == models.ModelCatalog.provider_id)
            .filter(models.ModelCatalog.status == "active")
            .all()
        )
        candidates = [(provider, model) for model, provider in rows]
    else:
        route = (
            db.query(models.RouteRule)
            .filter(models.RouteRule.model_id == request.model)
            .first()
        )
        if route is None:
            return {
                "requested_model": request.model,
                "blocked": False,
                "block_reason": "invalid_model",
                "candidates": [],
                "selected_provider": None,
            }
        providers = [provider for provider in [route.preferred_provider, route.backup_provider] if provider is not None]
        candidates = []
        for provider in providers:
            mapping = _get_model_mapping(db, request.model, provider.id)
            if mapping is not None:
                candidates.append((provider, mapping))

    traces = _build_candidate_trace(request, candidates, guardrails, route_weights, sticky_provider_name)
    selected_candidates = _filter_and_sort_candidates(request, candidates, guardrails, route_weights, sticky_provider_name)
    selected_provider = selected_candidates[0][0].name if selected_candidates else None
    selected_model = selected_candidates[0][1].model_id if selected_candidates else None
    block_reason = None
    for blocked_word in blocked_words:
        if blocked_word.lower() in prompt.lower():
            block_reason = "guardrail_blocked_word"
            break
    if len(prompt) > guardrails.max_prompt_chars:
        compression = {
            "applied": True,
            "original_chars": len(prompt),
            "max_prompt_chars": guardrails.max_prompt_chars,
        }
    else:
        compression = {
            "applied": False,
            "original_chars": len(prompt),
            "max_prompt_chars": guardrails.max_prompt_chars,
        }
    return {
        "requested_model": request.model,
        "workload_class": workload_class,
        "applied_profile_name": applied_profile_name,
        "applied_weights": route_weights,
        "route_scoring_experiment": experiment_meta,
        "sticky_key": request.provider.sticky_key if request.provider else None,
        "sticky_provider_name": sticky_provider_name,
        "selected_provider": selected_provider,
        "selected_model": selected_model,
        "blocked": block_reason is not None,
        "block_reason": block_reason,
        "compression": compression,
        "candidates": traces,
        "workspace_guardrails": workspace_guardrail_meta,
    }


def run_policy_dry_run(
    db: Session,
    request: schemas.PolicyDryRunRequest,
):
    chat_request = schemas.ChatCompletionRequest(
        model=request.model,
        messages=request.messages,
        provider=request.provider,
        tools=request.tools,
        response_format=request.response_format,
    )
    baseline_trace = build_route_decision_trace(
        db=db,
        request=chat_request,
        guardrail_override=None,
    )
    trace = build_route_decision_trace(
        db=db,
        request=chat_request,
        guardrail_override={
            "allowed_providers": _list_to_csv(request.guardrails.allowed_providers),
            "denied_providers": _list_to_csv(request.guardrails.denied_providers),
            "blocked_words": _list_to_csv(request.guardrails.blocked_words),
            "max_prompt_chars": request.guardrails.max_prompt_chars,
            "retention_mode": request.guardrails.retention_mode,
        },
    )
    candidates = trace.get("candidates", [])
    baseline_candidates = baseline_trace.get("candidates", [])
    eligibility_summary: dict[str, int] = {}
    for item in candidates:
        key = item.get("reject_reason") or "accepted"
        eligibility_summary[key] = eligibility_summary.get(key, 0) + 1
    policy_diff = {
        "selected_provider_changed": baseline_trace.get("selected_provider") != trace.get("selected_provider"),
        "selected_provider_before": baseline_trace.get("selected_provider"),
        "selected_provider_after": trace.get("selected_provider"),
        "blocked_changed": (baseline_trace.get("blocked", False) or baseline_trace.get("selected_provider") is None)
        != (trace.get("blocked", False) or trace.get("selected_provider") is None),
        "blocked_before": baseline_trace.get("blocked", False) or baseline_trace.get("selected_provider") is None,
        "blocked_after": trace.get("blocked", False) or trace.get("selected_provider") is None,
        "accepted_candidates_before": sum(1 for item in baseline_candidates if item.get("accepted")),
        "accepted_candidates_after": sum(1 for item in candidates if item.get("accepted")),
        "rejected_candidates_before": sum(1 for item in baseline_candidates if not item.get("accepted")),
        "rejected_candidates_after": sum(1 for item in candidates if not item.get("accepted")),
    }
    return schemas.PolicyDryRunResult(
        workload_class=trace.get("workload_class", "unknown"),
        blocked=trace.get("blocked", False) or trace.get("selected_provider") is None,
        block_reason=trace.get("block_reason") or ("no_eligible_provider" if trace.get("selected_provider") is None else None),
        selected_provider=trace.get("selected_provider"),
        selected_model=trace.get("selected_model"),
        accepted_candidates=sum(1 for item in candidates if item.get("accepted")),
        rejected_candidates=sum(1 for item in candidates if not item.get("accepted")),
        eligibility_summary=eligibility_summary,
        policy_diff=policy_diff,
        route_trace=trace,
    )


def run_batch_policy_dry_run(
    db: Session,
    request: schemas.BatchPolicyDryRunRequest,
) -> schemas.BatchPolicyDryRunResponse:
    from .eval_runner import build_request_payload, load_dataset

    dataset = load_dataset(_resolve_dataset_path(request.dataset_path))
    items: list[schemas.BatchPolicyDryRunItem] = []
    strategies = request.strategies or ["current_production_policy"]
    guardrail_override = {
        "allowed_providers": _list_to_csv(request.guardrails.allowed_providers),
        "denied_providers": _list_to_csv(request.guardrails.denied_providers),
        "blocked_words": _list_to_csv(request.guardrails.blocked_words),
        "max_prompt_chars": request.guardrails.max_prompt_chars,
        "retention_mode": request.guardrails.retention_mode,
    }

    for example in dataset.get("examples", []):
        baseline_by_example: dict[str, Any] = {}
        for strategy in strategies:
            payload = build_request_payload(example, strategy)
            chat_request = schemas.ChatCompletionRequest.model_validate(payload)
            trace = build_route_decision_trace(
                db=db,
                request=chat_request,
                guardrail_override=guardrail_override,
            )
            candidates = trace.get("candidates", [])
            items.append(
                schemas.BatchPolicyDryRunItem(
                    example_id=example["example_id"],
                    workload_class=trace.get("workload_class", example.get("workload_class", "unknown")),
                    strategy=strategy,
                    blocked=trace.get("blocked", False) or trace.get("selected_provider") is None,
                    block_reason=trace.get("block_reason") or ("no_eligible_provider" if trace.get("selected_provider") is None else None),
                    selected_provider=trace.get("selected_provider"),
                    selected_model=trace.get("selected_model"),
                    accepted_candidates=sum(1 for item in candidates if item.get("accepted")),
                    rejected_candidates=sum(1 for item in candidates if not item.get("accepted")),
                )
            )
            baseline_by_example.setdefault(example["example_id"], {
                "selected_provider": trace.get("selected_provider"),
                "blocked": trace.get("blocked", False) or trace.get("selected_provider") is None,
            })

    blocked_cases = sum(1 for item in items if item.blocked)
    strategy_summaries: list[dict[str, Any]] = []
    for strategy in strategies:
        strategy_items = [item for item in items if item.strategy == strategy]
        strategy_summaries.append(
            {
                "strategy": strategy,
                "total_cases": len(strategy_items),
                "blocked_cases": sum(1 for item in strategy_items if item.blocked),
                "success_cases": sum(1 for item in strategy_items if not item.blocked),
                "avg_accepted_candidates": round(
                    sum(item.accepted_candidates for item in strategy_items) / len(strategy_items),
                    2,
                ) if strategy_items else 0.0,
            }
        )
    changed_provider_cases = 0
    changed_block_cases = 0
    if strategies:
        baseline_strategy = strategies[0]
        grouped_by_example: dict[str, list[schemas.BatchPolicyDryRunItem]] = {}
        for item in items:
            grouped_by_example.setdefault(item.example_id, []).append(item)
        for example_items in grouped_by_example.values():
            baseline_item = next((item for item in example_items if item.strategy == baseline_strategy), None)
            if baseline_item is None:
                continue
            for item in example_items:
                if item.strategy == baseline_strategy:
                    continue
                if item.selected_provider != baseline_item.selected_provider:
                    changed_provider_cases += 1
                if item.blocked != baseline_item.blocked:
                    changed_block_cases += 1
    return schemas.BatchPolicyDryRunResponse(
        dataset_name=dataset.get("dataset_name", Path(request.dataset_path).stem),
        workspace_label=request.workspace_label,
        total_cases=len(items),
        blocked_cases=blocked_cases,
        success_cases=len(items) - blocked_cases,
        strategy_summaries=strategy_summaries,
        policy_diff_summary={
            "baseline_strategy": strategies[0] if strategies else None,
            "compared_strategies": strategies[1:],
            "changed_provider_cases": changed_provider_cases,
            "changed_block_cases": changed_block_cases,
        },
        items=items,
    )


def export_batch_policy_dry_run_report(
    db: Session,
    request: schemas.BatchPolicyDryRunRequest,
) -> schemas.DownloadArtifactResponse:
    result = run_batch_policy_dry_run(db=db, request=request)
    output = io.StringIO()
    output.write("# Batch Policy Preview Report\n\n")
    output.write(f"- Dataset: `{result.dataset_name}`\n")
    output.write(f"- Workspace: `{result.workspace_label or 'N/A'}`\n")
    output.write(f"- Total Cases: `{result.total_cases}`\n")
    output.write(f"- Success Cases: `{result.success_cases}`\n")
    output.write(f"- Blocked Cases: `{result.blocked_cases}`\n\n")

    output.write("## Policy Diff Summary\n\n")
    for key, value in result.policy_diff_summary.items():
        output.write(f"- {key}: `{value}`\n")
    output.write("\n## Strategy Summaries\n\n")
    for item in result.strategy_summaries:
        output.write(
            f"- `{item['strategy']}`: total=`{item['total_cases']}`, "
            f"success=`{item['success_cases']}`, blocked=`{item['blocked_cases']}`, "
            f"avg_accepted_candidates=`{item['avg_accepted_candidates']}`\n"
        )

    output.write("\n## Batch Items\n\n")
    output.write("| example_id | workload | strategy | blocked | block_reason | provider | model | accepted | rejected |\n")
    output.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
    for item in result.items:
        output.write(
            f"| {item.example_id} | {item.workload_class} | {item.strategy} | {item.blocked} | "
            f"{item.block_reason or ''} | {item.selected_provider or ''} | {item.selected_model or ''} | "
            f"{item.accepted_candidates} | {item.rejected_candidates} |\n"
        )

    file_name = f"batch_policy_preview_{result.dataset_name.replace(' ', '_')}.md"
    return schemas.DownloadArtifactResponse(
        file_name=file_name,
        download_url=f"data:text/markdown;charset=utf-8,{output.getvalue()}",
    )


def _build_guardrail_override(update: schemas.GuardrailConfigUpdate) -> dict[str, Any]:
    return {
        "allowed_providers": _list_to_csv(update.allowed_providers),
        "denied_providers": _list_to_csv(update.denied_providers),
        "blocked_words": _list_to_csv(update.blocked_words),
        "max_prompt_chars": update.max_prompt_chars,
        "retention_mode": update.retention_mode,
    }


def list_guardrail_policy_presets(db: Session):
    ensure_schema(db)
    rows = db.query(models.GuardrailPolicyPreset).order_by(models.GuardrailPolicyPreset.id.desc()).all()
    organizations = {row.id: row.name for row in db.query(models.Organization).all()}
    projects = {row.id: row.name for row in db.query(models.Project).all()}
    return [_guardrail_row_to_schema(row, organizations, projects) for row in rows]


def create_guardrail_policy_preset(db: Session, payload: schemas.GuardrailPolicyPresetCreate):
    ensure_schema(db)
    row = models.GuardrailPolicyPreset(
        name=payload.name,
        description=payload.description,
        organization_id=payload.organization_id,
        project_id=payload.project_id,
        allowed_providers=_list_to_csv(payload.allowed_providers),
        denied_providers=_list_to_csv(payload.denied_providers),
        blocked_words=_list_to_csv(payload.blocked_words),
        max_prompt_chars=payload.max_prompt_chars,
        retention_mode=payload.retention_mode,
    )
    db.add(row)
    _record_audit_log(db, "guardrail_policy_preset_created", f"Created guardrail policy preset {payload.name}")
    db.commit()
    return list_guardrail_policy_presets(db)[0]


def update_guardrail_policy_preset(db: Session, preset_id: int, payload: schemas.GuardrailPolicyPresetCreate):
    ensure_schema(db)
    row = db.query(models.GuardrailPolicyPreset).filter(models.GuardrailPolicyPreset.id == preset_id).first()
    if row is None:
        raise ValueError(f"INVALID_GUARDRAIL_POLICY_PRESET: {preset_id}")
    row.name = payload.name
    row.description = payload.description
    row.organization_id = payload.organization_id
    row.project_id = payload.project_id
    row.allowed_providers = _list_to_csv(payload.allowed_providers)
    row.denied_providers = _list_to_csv(payload.denied_providers)
    row.blocked_words = _list_to_csv(payload.blocked_words)
    row.max_prompt_chars = payload.max_prompt_chars
    row.retention_mode = payload.retention_mode
    _record_audit_log(db, "guardrail_policy_preset_updated", f"Updated guardrail policy preset {payload.name}")
    db.commit()
    items = list_guardrail_policy_presets(db)
    for item in items:
        if item.id == preset_id:
            return item
    raise ValueError(f"INVALID_GUARDRAIL_POLICY_PRESET: {preset_id}")


def _get_guardrail_policy_preset(db: Session, preset_name: str) -> schemas.GuardrailConfigUpdate:
    ensure_schema(db)
    row = db.query(models.GuardrailPolicyPreset).filter(models.GuardrailPolicyPreset.name == preset_name).first()
    if row is None:
        raise ValueError(f"INVALID_GUARDRAIL_POLICY_PRESET: {preset_name}")
    return schemas.GuardrailConfigUpdate(
        allowed_providers=_csv_to_list(row.allowed_providers),
        denied_providers=_csv_to_list(row.denied_providers),
        blocked_words=_csv_to_list(row.blocked_words),
        max_prompt_chars=row.max_prompt_chars,
        retention_mode=row.retention_mode,
    )


def compare_guardrail_policy_presets(
    db: Session,
    request: schemas.GuardrailPolicyCompareRequest,
) -> schemas.GuardrailPolicyCompareResponse:
    baseline_update = _get_guardrail_policy_preset(db, request.baseline_policy_name)
    comparison_update = _get_guardrail_policy_preset(db, request.comparison_policy_name)

    baseline_result = run_batch_policy_dry_run(
        db=db,
        request=schemas.BatchPolicyDryRunRequest(
            dataset_path=request.dataset_path,
            strategies=request.strategies,
            workspace_label=request.workspace_label,
            guardrails=baseline_update,
        ),
    )
    comparison_result = run_batch_policy_dry_run(
        db=db,
        request=schemas.BatchPolicyDryRunRequest(
            dataset_path=request.dataset_path,
            strategies=request.strategies,
            workspace_label=request.workspace_label,
            guardrails=comparison_update,
        ),
    )

    baseline_map = {
        (item.example_id, item.strategy): item
        for item in baseline_result.items
    }
    comparison_map = {
        (item.example_id, item.strategy): item
        for item in comparison_result.items
    }
    keys = sorted(set(baseline_map) | set(comparison_map))
    items: list[schemas.GuardrailPolicyCompareItem] = []
    changed_provider_cases = 0
    changed_block_cases = 0
    accepted_candidate_delta_total = 0

    for key in keys:
        baseline_item = baseline_map.get(key)
        comparison_item = comparison_map.get(key)
        if baseline_item is None or comparison_item is None:
            continue
        changed_provider = baseline_item.selected_provider != comparison_item.selected_provider
        changed_block = baseline_item.blocked != comparison_item.blocked
        if changed_provider:
            changed_provider_cases += 1
        if changed_block:
            changed_block_cases += 1
        accepted_candidate_delta_total += comparison_item.accepted_candidates - baseline_item.accepted_candidates
        items.append(
            schemas.GuardrailPolicyCompareItem(
                example_id=baseline_item.example_id,
                workload_class=baseline_item.workload_class,
                strategy=baseline_item.strategy,
                baseline_blocked=baseline_item.blocked,
                comparison_blocked=comparison_item.blocked,
                baseline_provider=baseline_item.selected_provider,
                comparison_provider=comparison_item.selected_provider,
                baseline_model=baseline_item.selected_model,
                comparison_model=comparison_item.selected_model,
                accepted_candidates_before=baseline_item.accepted_candidates,
                accepted_candidates_after=comparison_item.accepted_candidates,
                changed_provider=changed_provider,
                changed_block=changed_block,
            )
        )

    strategy_summaries: list[dict[str, Any]] = []
    for strategy in request.strategies or ["current_production_policy"]:
        baseline_items = [item for item in items if item.strategy == strategy]
        strategy_summaries.append(
            {
                "strategy": strategy,
                "baseline_blocked_cases": sum(1 for item in baseline_items if item.baseline_blocked),
                "comparison_blocked_cases": sum(1 for item in baseline_items if item.comparison_blocked),
                "changed_provider_cases": sum(1 for item in baseline_items if item.changed_provider),
                "changed_block_cases": sum(1 for item in baseline_items if item.changed_block),
            }
        )

    return schemas.GuardrailPolicyCompareResponse(
        dataset_name=baseline_result.dataset_name,
        workspace_label=request.workspace_label,
        baseline_policy_name=request.baseline_policy_name,
        comparison_policy_name=request.comparison_policy_name,
        strategy_summaries=strategy_summaries,
        comparison_summary={
            "total_cases": len(items),
            "changed_provider_cases": changed_provider_cases,
            "changed_block_cases": changed_block_cases,
            "accepted_candidate_delta_total": accepted_candidate_delta_total,
        },
        items=items,
    )


def export_guardrail_policy_compare_report(
    db: Session,
    request: schemas.GuardrailPolicyCompareRequest,
) -> schemas.DownloadArtifactResponse:
    result = compare_guardrail_policy_presets(db=db, request=request)
    output = io.StringIO()
    output.write("# Guardrail Policy Compare Report\n\n")
    output.write(f"- Dataset: `{result.dataset_name}`\n")
    output.write(f"- Workspace: `{result.workspace_label or 'N/A'}`\n")
    output.write(f"- Baseline Policy: `{result.baseline_policy_name}`\n")
    output.write(f"- Comparison Policy: `{result.comparison_policy_name}`\n\n")
    output.write("## Comparison Summary\n\n")
    for key, value in result.comparison_summary.items():
        output.write(f"- {key}: `{value}`\n")
    output.write("\n## Strategy Summaries\n\n")
    for item in result.strategy_summaries:
        output.write(
            f"- `{item['strategy']}`: baseline_blocked=`{item['baseline_blocked_cases']}`, "
            f"comparison_blocked=`{item['comparison_blocked_cases']}`, changed_provider=`{item['changed_provider_cases']}`, "
            f"changed_block=`{item['changed_block_cases']}`\n"
        )
    output.write("\n## Compared Items\n\n")
    output.write("| example_id | workload | strategy | baseline_provider | comparison_provider | baseline_blocked | comparison_blocked | accepted_before | accepted_after |\n")
    output.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
    for item in result.items:
        output.write(
            f"| {item.example_id} | {item.workload_class} | {item.strategy} | {item.baseline_provider or ''} | "
            f"{item.comparison_provider or ''} | {item.baseline_blocked} | {item.comparison_blocked} | "
            f"{item.accepted_candidates_before} | {item.accepted_candidates_after} |\n"
        )
    file_name = f"guardrail_policy_compare_{result.dataset_name.replace(' ', '_')}.md"
    return schemas.DownloadArtifactResponse(
        file_name=file_name,
        download_url=f"data:text/markdown;charset=utf-8,{output.getvalue()}",
    )


def get_route_scoring_profile(db: Session) -> schemas.RouteScoringProfileItem:
    seed_demo_data(db)
    profile = _get_active_route_scoring_profile(db)
    if profile is None:
        return schemas.RouteScoringProfileItem(
            name="default_heuristic_profile",
            source_dataset="built_in",
            status="active",
            trained_at=datetime.now(UTC).isoformat(),
            weights=DEFAULT_ROUTE_SCORING_WEIGHTS,
        )
    return schemas.RouteScoringProfileItem(
        name=profile.name,
        source_dataset=profile.source_dataset,
        status=profile.status,
        trained_at=profile.trained_at.isoformat(),
        weights=json.loads(profile.weights_json),
    )


def train_route_scoring_profile(
    db: Session,
    request: schemas.RouteScoringTrainRequest,
) -> schemas.RouteScoringTrainResult:
    from .eval_runner import (
        DEFAULT_STRATEGIES,
        aggregate_results_by_workload,
        compute_workload_winners,
        load_dataset,
        run_single_example,
    )

    dataset = load_dataset(_resolve_dataset_path(request.dataset_path))
    examples = dataset.get("examples", [])
    results = []
    for example in examples:
        for strategy in DEFAULT_STRATEGIES:
            results.append(run_single_example(db=db, example=example, strategy=strategy, api_key_label="route_trainer"))

    workload_summary = aggregate_results_by_workload(results)
    workload_winners = compute_workload_winners(workload_summary)
    grouped_results: dict[str, list[Any]] = {}
    for item in results:
        grouped_results.setdefault(item.workload_class, []).append(item)

    weight_grid = _generate_weight_grid()
    fitted_weights: dict[str, dict[str, float]] = {}
    calibration_summary: list[dict[str, Any]] = []
    for workload_class, items in grouped_results.items():
        best_by_example: dict[str, Any] = {}
        for item in items:
            existing = best_by_example.get(item.example_id)
            if existing is None or (
                item.score > existing.score
                or (
                    item.score == existing.score
                    and item.total_cost < existing.total_cost
                )
            ):
                best_by_example[item.example_id] = item

        best_weights = _get_default_route_score_weights(workload_class)
        best_alignment = -1.0
        best_avg_oracle_gap = -999.0
        for candidate_weights in weight_grid:
            alignments = 0
            oracle_gap_total = 0.0
            counted_examples = 0
            for example_id, oracle in best_by_example.items():
                predicted_provider = _select_provider_from_trace(oracle.route_trace, candidate_weights)
                if predicted_provider is None:
                    continue
                counted_examples += 1
                if predicted_provider == oracle.provider:
                    alignments += 1
                heuristic_provider = _select_provider_from_trace(
                    oracle.route_trace,
                    _get_default_route_score_weights(workload_class),
                )
                oracle_gap_total += 1.0 if predicted_provider == oracle.provider else 0.0
                oracle_gap_total -= 0.25 if heuristic_provider == oracle.provider and predicted_provider != oracle.provider else 0.0

            if counted_examples == 0:
                continue
            alignment_rate = alignments / counted_examples
            avg_oracle_gap = oracle_gap_total / counted_examples
            if alignment_rate > best_alignment or (
                alignment_rate == best_alignment and avg_oracle_gap > best_avg_oracle_gap
            ):
                best_alignment = alignment_rate
                best_avg_oracle_gap = avg_oracle_gap
                best_weights = candidate_weights

        fitted_weights[workload_class] = best_weights
        calibration_summary.append(
            {
                "workload_class": workload_class,
                "examples": len(best_by_example),
                "alignment_rate": round(best_alignment, 4) if best_alignment >= 0 else 0.0,
                "tested_weight_sets": len(weight_grid),
                "selected_weights": best_weights,
            }
        )

    db.query(models.RouteScoringProfile).update({models.RouteScoringProfile.status: "inactive"})
    profile = (
        db.query(models.RouteScoringProfile)
        .filter(models.RouteScoringProfile.name == request.profile_name)
        .first()
    )
    if profile is None:
        profile = models.RouteScoringProfile(
            name=request.profile_name,
            source_dataset=request.dataset_path,
            status="active",
            weights_json=json.dumps(fitted_weights, ensure_ascii=False),
            trained_at=datetime.now(UTC),
        )
        db.add(profile)
    else:
        profile.source_dataset = request.dataset_path
        profile.status = "active"
        profile.weights_json = json.dumps(fitted_weights, ensure_ascii=False)
        profile.trained_at = datetime.now(UTC)
    _record_audit_log(db, "route_scoring_trained", f"Trained route scoring profile from {request.dataset_path}")
    db.commit()
    db.refresh(profile)
    return schemas.RouteScoringTrainResult(
        name=profile.name,
        source_dataset=profile.source_dataset,
        status=profile.status,
        trained_at=profile.trained_at.isoformat(),
        weights=fitted_weights,
        workload_winners=workload_winners,
        calibration_summary=sorted(calibration_summary, key=lambda item: item["workload_class"]),
    )


def recalibrate_route_scoring_profile_from_logs(
    db: Session,
    request: schemas.RouteScoringRecalibrationRequest,
) -> schemas.RouteScoringRecalibrationResult:
    seed_demo_data(db)
    query = db.query(models.RequestLog).order_by(models.RequestLog.id.desc())
    if request.organization_id is not None:
        query = query.filter(models.RequestLog.organization_id == request.organization_id)
    if request.project_id is not None:
        query = query.filter(models.RequestLog.project_id == request.project_id)
    rows = query.limit(max(1, min(request.limit, 500))).all()

    grouped_rows: dict[str, list[tuple[models.RequestLog, dict[str, Any], str]]] = {}
    considered_requests = 0
    successful_requests = 0
    fallback_requests = 0
    experiment_requests = 0
    for row in rows:
        if not row.route_trace_json:
            continue
        trace = json.loads(row.route_trace_json)
        experiment = trace.get("route_scoring_experiment") or {}
        if request.experiment_name and experiment.get("name") != request.experiment_name:
            continue
        if request.experiment_name:
            experiment_requests += 1
        workload_class = trace.get("workload_class")
        selected_provider = trace.get("selected_provider") or row.provider_name
        if not workload_class or not selected_provider:
            continue
        considered_requests += 1
        if row.status_code == 200:
            successful_requests += 1
        if row.fallback_used:
            fallback_requests += 1
        grouped_rows.setdefault(workload_class, []).append((row, trace, selected_provider))

    weight_grid = _generate_weight_grid()
    fitted_weights: dict[str, dict[str, float]] = {}
    calibration_summary: list[dict[str, Any]] = []

    for workload_class, samples in grouped_rows.items():
        best_weights = _get_route_score_weights(db, workload_class)
        best_score = float("-inf")
        best_alignment = 0.0
        for candidate_weights in weight_grid:
            score_total = 0.0
            weighted_alignment_total = 0.0
            sample_weight_total = 0.0
            for row, trace, selected_provider in samples:
                predicted_provider = _select_provider_from_trace(trace, candidate_weights)
                if predicted_provider is None:
                    continue
                sample_weight = 1.0
                if row.status_code == 200:
                    sample_weight += 1.0
                if row.cache_hit:
                    sample_weight += 0.25
                if row.response_healed:
                    sample_weight -= 0.15
                if row.fallback_used:
                    sample_weight -= 0.35
                sample_weight = max(sample_weight, 0.1)
                matched = 1.0 if predicted_provider == selected_provider else 0.0
                weighted_alignment_total += matched * sample_weight
                sample_weight_total += sample_weight

                success_bonus = 1.0 if row.status_code == 200 and not row.fallback_used else 0.25
                if row.status_code >= 400:
                    success_bonus = -0.5
                cost_penalty = row.cost_amount * 0.5
                latency_penalty = row.latency / 10000
                score_total += (
                    (1.5 if matched else -0.5) * sample_weight
                    + success_bonus
                    - cost_penalty
                    - latency_penalty
                )

            if sample_weight_total == 0:
                continue
            alignment_rate = weighted_alignment_total / sample_weight_total
            if score_total > best_score or (score_total == best_score and alignment_rate > best_alignment):
                best_score = score_total
                best_alignment = alignment_rate
                best_weights = candidate_weights

        fitted_weights[workload_class] = best_weights
        calibration_summary.append(
            {
                "workload_class": workload_class,
                "requests": len(samples),
                "success_rate": round(sum(1 for row, _, _ in samples if row.status_code == 200) / len(samples), 4),
                "fallback_rate": round(sum(1 for row, _, _ in samples if row.fallback_used) / len(samples), 4),
                "selected_weights": best_weights,
                "alignment_rate": round(best_alignment, 4),
                "tested_weight_sets": len(weight_grid),
            }
        )

    if not fitted_weights:
        active_profile = _get_active_route_scoring_profile(db)
        fallback_weights = json.loads(active_profile.weights_json) if active_profile is not None else DEFAULT_ROUTE_SCORING_WEIGHTS
        fitted_weights = fallback_weights

    db.query(models.RouteScoringProfile).update({models.RouteScoringProfile.status: "inactive"})
    profile = (
        db.query(models.RouteScoringProfile)
        .filter(models.RouteScoringProfile.name == request.profile_name)
        .first()
    )
    now = datetime.now(UTC)
    source_dataset = f"recent_logs:{considered_requests}"
    if request.experiment_name:
        source_dataset = f"{source_dataset}:experiment={request.experiment_name}"
    if profile is None:
        profile = models.RouteScoringProfile(
            name=request.profile_name,
            source_dataset=source_dataset,
            status="active",
            weights_json=json.dumps(fitted_weights, ensure_ascii=False),
            trained_at=now,
        )
        db.add(profile)
    else:
        profile.source_dataset = source_dataset
        profile.status = "active"
        profile.weights_json = json.dumps(fitted_weights, ensure_ascii=False)
        profile.trained_at = now
    _record_audit_log(
        db,
        "route_scoring_recalibrated",
        f"Recalibrated route scoring profile from {considered_requests} recent logs",
    )
    db.commit()
    db.refresh(profile)
    return schemas.RouteScoringRecalibrationResult(
        name=profile.name,
        source_dataset=profile.source_dataset,
        status=profile.status,
        trained_at=profile.trained_at.isoformat(),
        weights=fitted_weights,
        calibration_summary=sorted(calibration_summary, key=lambda item: item["workload_class"]),
        source_summary={
            "considered_requests": considered_requests,
            "successful_requests": successful_requests,
            "fallback_requests": fallback_requests,
            "experiment_requests": experiment_requests if request.experiment_name else None,
            "organization_id": request.organization_id,
            "project_id": request.project_id,
            "experiment_name": request.experiment_name,
        },
    )


def list_route_scoring_experiments(db: Session) -> list[schemas.RouteScoringExperimentItem]:
    seed_demo_data(db)
    rows = (
        db.query(models.RouteScoringExperiment)
        .order_by(models.RouteScoringExperiment.updated_at.desc())
        .all()
    )
    return [
        schemas.RouteScoringExperimentItem(
            id=row.id,
            name=row.name,
            control_profile_name=row.control_profile_name,
            challenger_profile_name=row.challenger_profile_name,
            traffic_percentage=row.traffic_percentage,
            status=row.status,
            created_at=row.created_at.isoformat(),
            updated_at=row.updated_at.isoformat(),
        )
        for row in rows
    ]


def create_route_scoring_experiment(
    db: Session,
    payload: schemas.RouteScoringExperimentCreate,
) -> schemas.RouteScoringExperimentItem:
    seed_demo_data(db)
    now = datetime.now(UTC)
    if payload.status == "active":
        db.query(models.RouteScoringExperiment).update({models.RouteScoringExperiment.status: "inactive"})
    row = models.RouteScoringExperiment(
        name=payload.name,
        control_profile_name=payload.control_profile_name,
        challenger_profile_name=payload.challenger_profile_name,
        traffic_percentage=max(0, min(100, int(payload.traffic_percentage))),
        status=payload.status,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    _record_audit_log(db, "route_scoring_experiment_created", f"Created route scoring experiment {payload.name}")
    db.commit()
    db.refresh(row)
    return list_route_scoring_experiments(db)[0]


def update_route_scoring_experiment(
    db: Session,
    experiment_id: int,
    payload: schemas.RouteScoringExperimentCreate,
) -> schemas.RouteScoringExperimentItem:
    seed_demo_data(db)
    row = (
        db.query(models.RouteScoringExperiment)
        .filter(models.RouteScoringExperiment.id == experiment_id)
        .first()
    )
    if row is None:
        raise ValueError(f"INVALID_ROUTE_SCORING_EXPERIMENT: {experiment_id}")
    if payload.status == "active":
        db.query(models.RouteScoringExperiment).filter(
            models.RouteScoringExperiment.id != experiment_id
        ).update({models.RouteScoringExperiment.status: "inactive"})
    row.name = payload.name
    row.control_profile_name = payload.control_profile_name
    row.challenger_profile_name = payload.challenger_profile_name
    row.traffic_percentage = max(0, min(100, int(payload.traffic_percentage)))
    row.status = payload.status
    row.updated_at = datetime.now(UTC)
    _record_audit_log(db, "route_scoring_experiment_updated", f"Updated route scoring experiment {experiment_id}")
    db.commit()
    items = list_route_scoring_experiments(db)
    for item in items:
        if item.id == experiment_id:
            return item
    raise ValueError(f"INVALID_ROUTE_SCORING_EXPERIMENT: {experiment_id}")


def replay_route_scoring(
    db: Session,
    request: schemas.RouteReplayRequest,
) -> schemas.RouteReplayResponse:
    source = request.source or "dataset"
    items: list[schemas.RouteReplayItem] = []
    baseline_profile_name = request.baseline_profile_name or "default_heuristic_profile"
    comparison_profile_name = request.comparison_profile_name or _get_active_route_scoring_profile_name(db)

    if source == "recent_logs":
        query = db.query(models.RequestLog)
        if request.organization_id is not None:
            query = query.filter(models.RequestLog.organization_id == request.organization_id)
        if request.project_id is not None:
            query = query.filter(models.RequestLog.project_id == request.project_id)
        rows = query.order_by(models.RequestLog.id.desc()).limit(request.limit).all()
        for row in rows:
            if not row.route_trace_json:
                continue
            trace = json.loads(row.route_trace_json)
            workload_class = trace.get("workload_class", "chat_general")
            baseline_weights = _get_route_score_weights_for_profile(db, workload_class, baseline_profile_name)
            comparison_weights = _get_route_score_weights_for_profile(db, workload_class, comparison_profile_name)
            heuristic_provider = _select_provider_from_trace(trace, baseline_weights)
            learned_provider = _select_provider_from_trace(trace, comparison_weights)
            items.append(
                schemas.RouteReplayItem(
                    request_id=row.request_id,
                    workload_class=workload_class,
                    heuristic_provider=heuristic_provider,
                    learned_provider=learned_provider,
                    baseline_profile_name=baseline_profile_name,
                    comparison_profile_name=comparison_profile_name,
                    baseline_provider=heuristic_provider,
                    comparison_provider=learned_provider,
                    original_provider=row.provider_name,
                    changed=heuristic_provider != learned_provider,
                    source="recent_logs",
                )
            )
        source_label = (
            f"recent_logs:{request.limit}:org={request.organization_id or 'all'}:proj={request.project_id or 'all'}:"
            f"{baseline_profile_name}_vs_{comparison_profile_name}"
        )
    else:
        from .eval_runner import build_request_payload, load_dataset

        dataset = load_dataset(_resolve_dataset_path(request.dataset_path or "evals/datasets/sample_workloads.json"))
        for example in dataset.get("examples", []):
            payload = build_request_payload(example, request.strategy)
            chat_request = schemas.ChatCompletionRequest.model_validate(payload)
            trace = build_route_decision_trace(db=db, request=chat_request)
            workload_class = trace.get("workload_class", example.get("workload_class", "chat_general"))
            baseline_weights = _get_route_score_weights_for_profile(db, workload_class, baseline_profile_name)
            comparison_weights = _get_route_score_weights_for_profile(db, workload_class, comparison_profile_name)
            heuristic_provider = _select_provider_from_trace(trace, baseline_weights)
            learned_provider = _select_provider_from_trace(trace, comparison_weights)
            items.append(
                schemas.RouteReplayItem(
                    example_id=example["example_id"],
                    workload_class=workload_class,
                    heuristic_provider=heuristic_provider,
                    learned_provider=learned_provider,
                    baseline_profile_name=baseline_profile_name,
                    comparison_profile_name=comparison_profile_name,
                    baseline_provider=heuristic_provider,
                    comparison_provider=learned_provider,
                    original_provider=trace.get("selected_provider"),
                    changed=heuristic_provider != learned_provider,
                    source="dataset",
                )
            )
        source_label = (
            f"{dataset.get('dataset_name', request.dataset_path or 'dataset')}:"
            f"{baseline_profile_name}_vs_{comparison_profile_name}"
        )

    changed_routes = sum(1 for item in items if item.changed)
    return schemas.RouteReplayResponse(
        source=source,
        source_label=source_label,
        total_cases=len(items),
        changed_routes=changed_routes,
        unchanged_routes=len(items) - changed_routes,
        items=items,
    )


def export_route_scoring_replay_report(
    db: Session,
    request: schemas.RouteReplayRequest,
) -> schemas.DownloadArtifactResponse:
    result = replay_route_scoring(db=db, request=request)
    output = io.StringIO()
    output.write("# Route Replay Report\n\n")
    output.write(f"- Source: `{result.source}`\n")
    output.write(f"- Source Label: `{result.source_label}`\n")
    output.write(f"- Total Cases: `{result.total_cases}`\n")
    output.write(f"- Changed Routes: `{result.changed_routes}`\n")
    output.write(f"- Unchanged Routes: `{result.unchanged_routes}`\n\n")

    output.write("## Replay Items\n\n")
    output.write("| workload | request/example | baseline profile | comparison profile | baseline provider | comparison provider | original provider | changed |\n")
    output.write("| --- | --- | --- | --- | --- | --- | --- | --- |\n")
    for item in result.items:
        identifier = item.request_id or item.example_id or "N/A"
        output.write(
            f"| {item.workload_class} | {identifier} | {item.baseline_profile_name or ''} | "
            f"{item.comparison_profile_name or ''} | {item.baseline_provider or item.heuristic_provider or ''} | "
            f"{item.comparison_provider or item.learned_provider or ''} | {item.original_provider or ''} | "
            f"{item.changed} |\n"
        )

    file_name = f"route_replay_{result.source}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.md"
    return schemas.DownloadArtifactResponse(
        file_name=file_name,
        download_url=f"data:text/markdown;charset=utf-8,{output.getvalue()}",
    )


def _execute_routed_chat_completion(
    db: Session,
    request: schemas.ChatCompletionRequest,
    api_key_label: str | None = None,
    organization_id: int | None = None,
    project_id: int | None = None,
    environment: str | None = None,
):
    seed_demo_data(db)
    organization_id, project_id, workspace_default_meta = _apply_workspace_route_defaults(
        db=db,
        request=request,
        organization_id=organization_id,
        project_id=project_id,
    )
    guardrails, workspace_guardrail_meta = _resolve_guardrails_for_scope(
        db=db,
        organization_id=organization_id,
        project_id=project_id,
    )
    prompt = _extract_prompt_from_request(request)
    sticky_key = request.provider.sticky_key if request.provider else None
    blocked_words = _csv_to_list(guardrails.blocked_words)
    for blocked_word in blocked_words:
        if blocked_word.lower() in prompt.lower():
            route_trace = build_route_decision_trace(
                db=db,
                request=request,
                organization_id=organization_id,
                project_id=project_id,
            )
            route_trace["workspace_default"] = workspace_default_meta
            route_trace["workspace_guardrails"] = workspace_guardrail_meta
            _record_audit_log(db, "guardrail_block", f"Blocked word '{blocked_word}' for key {api_key_label or 'unknown'}")
            _create_notification(db, "guardrail_block", f"Blocked request for API key {api_key_label or 'unknown'}")
            failed_log = models.RequestLog(
                request_id=str(uuid.uuid4()),
                api_key_label=api_key_label,
                organization_id=organization_id,
                project_id=project_id,
                environment=environment,
                requested_model=request.model,
                resolved_model=None,
                model_catalog_id=None,
                provider_name=None,
                sticky_key=sticky_key,
                cache_key=None,
                cache_hit=False,
                status_code=400,
                latency=0,
                prompt_tokens=0,
                completion_tokens=0,
                cached_tokens=0,
                reasoning_tokens=0,
                cost_amount=0,
                provider_reported_cost=0,
                fallback_used=False,
                error_code="GUARDRAIL_BLOCKED_WORD",
                route_trace_json=json.dumps(route_trace, ensure_ascii=False),
            )
            db.add(failed_log)
            db.commit()
            raise ValueError("GUARDRAIL_BLOCKED_WORD")

    original_prompt_length = len(prompt)
    if len(prompt) > guardrails.max_prompt_chars:
        _compress_request_messages(request, guardrails.max_prompt_chars)
        _record_audit_log(db, "context_compressed", f"Compressed prompt for model {request.model}")

    route_trace = build_route_decision_trace(
        db=db,
        request=request,
        organization_id=organization_id,
        project_id=project_id,
    )
    route_trace["workspace_default"] = workspace_default_meta
    route_trace["workspace_guardrails"] = workspace_guardrail_meta
    if original_prompt_length > guardrails.max_prompt_chars:
        route_trace["compression"] = {
            "applied": True,
            "original_chars": original_prompt_length,
            "max_prompt_chars": guardrails.max_prompt_chars,
        }

    workload_class = route_trace.get("workload_class") or classify_workload(request)
    route_weights = route_trace.get("applied_weights") or _get_route_score_weights(db, workload_class)
    candidates = _resolve_candidates(db, request, guardrails, route_weights)
    route = None
    route_timeout_ms: int | None = None
    route_timeout_s: float | None = None
    if request.model != "router/auto":
        route = db.query(models.RouteRule).filter(models.RouteRule.model_id == request.model).first()
        if route is not None and route.timeout_ms:
            route_timeout_ms = route.timeout_ms
    effective_timeout_ms, timeout_trace = _resolve_request_timeout_ms(
        request=request,
        workload_class=workload_class,
        route_timeout_ms=route_timeout_ms,
    )
    if effective_timeout_ms:
        route_timeout_s = max(effective_timeout_ms / 1000.0, 0.001)
        route_trace["timeout"] = timeout_trace
    cache_key = _build_request_cache_key(
        request,
        organization_id=organization_id,
        project_id=project_id,
        environment=environment,
        guardrails=guardrails,
    )
    request_id = str(uuid.uuid4())
    last_error = "NO_AVAILABLE_PROVIDER"
    if not candidates:
        if route:
            raw = [(p, _get_model_mapping(db, request.model, p.id))
                   for p in [route.preferred_provider, route.backup_provider] if p]
            raw = [(p, m) for p, m in raw if m]
            for t in _build_candidate_trace(request, raw, guardrails):
                logger_crud.warning("NO_AVAILABLE_PROVIDER: provider=%s reject=%s prompt_tokens=%s max_input=%s",
                    t["provider"], t["reject_reason"], t["estimated_prompt_tokens"], t["max_input_tokens"])
        raise ValueError("NO_AVAILABLE_PROVIDER")
    for index, (provider, model_mapping) in enumerate(candidates):
        cache_entry = _get_prompt_cache_entry(
            db=db,
            cache_key=cache_key,
            provider_name=provider.name,
            resolved_model=model_mapping.model_id,
        )
        if cache_entry is not None:
            latency = 1.0
            cached_result = ProviderResult(
                completion=cache_entry.completion,
                prompt_tokens=cache_entry.prompt_tokens,
                completion_tokens=cache_entry.completion_tokens,
                cost_amount=cache_entry.cost_amount,
                cached_tokens=cache_entry.prompt_tokens or cache_entry.cached_tokens,
                reasoning_tokens=cache_entry.reasoning_tokens,
                provider_reported_cost=cache_entry.provider_reported_cost,
                tool_calls=json.loads(cache_entry.tool_calls_json) if cache_entry.tool_calls_json else None,
                structured_output=json.loads(cache_entry.structured_output_json) if cache_entry.structured_output_json else None,
                response_healed=cache_entry.response_healed,
                healing_strategy=cache_entry.healing_strategy,
            )
            route_trace["cache"] = {
                "hit": True,
                "cache_key": cache_key,
                "provider": provider.name,
                "resolved_model": model_mapping.model_id,
            }
            route_trace["response_healing"] = {
                "applied": cached_result.response_healed,
                "strategy": cached_result.healing_strategy,
                "response_format": request.response_format.type if request.response_format else None,
                "source": "cache",
            }
            cache_entry.hit_count = (cache_entry.hit_count or 0) + 1
            cache_entry.updated_at = datetime.now(UTC)
            request_log = models.RequestLog(
                request_id=request_id,
                api_key_label=api_key_label,
                organization_id=organization_id,
                project_id=project_id,
                environment=environment,
                requested_model=request.model,
                resolved_model=model_mapping.model_id,
                model_catalog_id=model_mapping.id,
                provider_name=provider.name,
                sticky_key=sticky_key,
                cache_key=cache_key,
                cache_hit=True,
                status_code=200,
                latency=latency,
                prompt_tokens=cached_result.prompt_tokens,
                completion_tokens=cached_result.completion_tokens,
                cached_tokens=cached_result.cached_tokens,
                reasoning_tokens=cached_result.reasoning_tokens,
                cost_amount=0.0,
                provider_reported_cost=cached_result.provider_reported_cost,
                response_healed=cached_result.response_healed,
                healing_strategy=cached_result.healing_strategy,
                fallback_used=index > 0,
                error_code=None,
                route_trace_json=json.dumps(route_trace, ensure_ascii=False),
            )
            db.add(request_log)
            if api_key_label:
                db_key = db.query(models.RouterApiKey).filter(models.RouterApiKey.name == api_key_label).first()
                if db_key is not None:
                    db_key.request_count = (db_key.request_count or 0) + 1
            # v0.3: Write billing record for cache hits (cost = 0)
            _write_billing_record(
                db=db,
                request_id=request_id,
                api_key_name=api_key_label,
                organization_id=organization_id,
                project_id=project_id,
                environment=environment,
                model=model_mapping.model_id,
                provider=provider.name,
                prompt_tokens=cached_result.prompt_tokens,
                completion_tokens=cached_result.completion_tokens,
                cached_tokens=cached_result.cached_tokens,
                cost_usd=0.0,
                upstream_cost_usd=0.0,
                cache_hit=True,
                fallback_used=index > 0,
            )
            db.commit()
            return {
                "request_id": request_id,
                "provider": provider.name,
                "fallback_used": index > 0,
                "cache_hit": True,
                "result": cached_result,
                "selected_model": model_mapping.model_id,
                "route_trace": route_trace,
            }
        started_at = time.perf_counter()
        try:
            result = execute_chat_completion(provider, model_mapping, request, timeout_s=route_timeout_s)
            latency = (time.perf_counter() - started_at) * 1000
            billable_prompt_tokens = max(result.prompt_tokens - result.cached_tokens, 0)
            computed_cost = round(
                (billable_prompt_tokens / 1000) * provider.input_cost_per_1k
                + (result.completion_tokens / 1000) * provider.output_cost_per_1k,
                6,
            )
            # v0.5: Response safety scan
            ws_guardrail = db.query(models.WorkspaceGuardrailConfig).filter(
                models.WorkspaceGuardrailConfig.organization_id == organization_id
            ).first()
            resp_blocked_words = _csv_to_list(
                getattr(ws_guardrail, "blocked_response_words", None) or ""
            )
            resp_regex = json.loads(
                getattr(ws_guardrail, "response_regex_patterns", None) or "[]"
            )
            detect_pii = bool(getattr(ws_guardrail, "detect_pii", False))
            safe_completion, was_modified, resp_violation = scan_response(
                text=result.completion,
                blocked_words=resp_blocked_words,
                regex_patterns=resp_regex,
                detect_pii=detect_pii,
                redact_pii=True,
            )
            if resp_violation and resp_violation.mode == "block":
                _record_audit_log(
                    db, "response_blocked",
                    f"Response from {provider.name} blocked: {resp_violation.category}",
                )
            if was_modified:
                result.completion = safe_completion
            route_trace["cache"] = {
                "hit": False,
                "cache_key": cache_key,
                "provider": provider.name,
                "resolved_model": model_mapping.model_id,
            }
            route_trace["response_healing"] = {
                "applied": result.response_healed,
                "strategy": result.healing_strategy,
                "response_format": request.response_format.type if request.response_format else None,
                "source": "provider",
            }
            request_log = models.RequestLog(
                request_id=request_id,
                api_key_label=api_key_label,
                organization_id=organization_id,
                project_id=project_id,
                environment=environment,
                requested_model=request.model,
                resolved_model=model_mapping.model_id,
                model_catalog_id=model_mapping.id,
                provider_name=provider.name,
                sticky_key=sticky_key,
                cache_key=cache_key,
                cache_hit=False,
                status_code=200,
                latency=latency,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                cached_tokens=result.cached_tokens,
                reasoning_tokens=result.reasoning_tokens,
                cost_amount=computed_cost,
                provider_reported_cost=result.provider_reported_cost,
                response_healed=result.response_healed,
                healing_strategy=result.healing_strategy,
                fallback_used=index > 0,
                error_code=None,
                route_trace_json=json.dumps(route_trace, ensure_ascii=False),
            )
            db.add(request_log)
            _upsert_prompt_cache_entry(
                db=db,
                cache_key=cache_key,
                sticky_key=sticky_key,
                provider_name=provider.name,
                resolved_model=model_mapping.model_id,
                result=result,
            )
            if api_key_label:
                db_key = db.query(models.RouterApiKey).filter(models.RouterApiKey.name == api_key_label).first()
                if db_key is not None:
                    db_key.request_count = (db_key.request_count or 0) + 1
            # v0.3: Write billing record for every successful request
            _write_billing_record(
                db=db,
                request_id=request_id,
                api_key_name=api_key_label,
                organization_id=organization_id,
                project_id=project_id,
                environment=environment,
                model=model_mapping.model_id,
                provider=provider.name,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                cached_tokens=result.cached_tokens,
                cost_usd=computed_cost,
                upstream_cost_usd=result.provider_reported_cost,
                cache_hit=False,
                fallback_used=index > 0,
            )
            # Update provider health status on successful real request
            provider.health_status = "healthy"
            db.commit()
            return {
                "request_id": request_id,
                "provider": provider.name,
                "fallback_used": index > 0,
                "cache_hit": False,
                "result": result,
                "selected_model": model_mapping.model_id,
                "route_trace": route_trace,
            }
        except ProviderExecutionError as exc:
            # Update provider health status on failed real request
            provider.health_status = "unhealthy"
            db.commit()
            last_error = str(exc)

    _record_audit_log(db, "routing_failure", f"Failed to execute request for model {request.model}: {last_error}")
    _create_notification(db, "routing_failure", f"Request for model {request.model} failed after trying all candidates")
    failed_log = models.RequestLog(
        request_id=request_id,
        api_key_label=api_key_label,
        organization_id=organization_id,
        project_id=project_id,
        environment=environment,
        requested_model=request.model,
        resolved_model=None,
        model_catalog_id=None,
        provider_name=None,
        sticky_key=sticky_key,
        cache_key=cache_key,
        cache_hit=False,
        status_code=503,
        latency=0,
        prompt_tokens=0,
        completion_tokens=0,
        cached_tokens=0,
        reasoning_tokens=0,
        cost_amount=0,
        provider_reported_cost=0,
        fallback_used=len(candidates) > 1,
        error_code=last_error,
        route_trace_json=json.dumps(route_trace, ensure_ascii=False),
    )
    db.add(failed_log)
    db.commit()
    raise ValueError(last_error)

def create_chat_completion(
    db: Session,
    request: schemas.ChatCompletionRequest,
    api_key_label: str | None = None,
    organization_id: int | None = None,
    project_id: int | None = None,
    environment: str | None = None,
):
    execution = _execute_routed_chat_completion(
        db=db,
        request=request,
        api_key_label=api_key_label,
        organization_id=organization_id,
        project_id=project_id,
        environment=environment,
    )
    result = execution["result"]
    import time as _time

    # Build OpenAI-compatible message with optional tool_calls
    msg = schemas.ChatMessageOut(
        role="assistant",
        content=result.completion or None,
        tool_calls=result.tool_calls or None,
    )
    finish_reason = "tool_calls" if result.tool_calls else "stop"

    usage = _build_usage(
        result.prompt_tokens,
        result.completion_tokens,
        result.cached_tokens,
        result.reasoning_tokens,
        result.provider_reported_cost,
    )
    request_id = execution["request_id"]
    selected_model = execution.get("selected_model") or request.model
    return schemas.ChatCompletionResponse(
        id=request_id,
        object="chat.completion",
        created=int(_time.time()),
        model=selected_model,
        choices=[schemas.ChatCompletionChoice(index=0, message=msg, finish_reason=finish_reason)],
        usage=usage,
        request_id=request_id,
        selected_model=selected_model,
        tool_calls=result.tool_calls or None,
        provider=execution["provider"],
        fallback_used=execution["fallback_used"],
        cache_hit=execution.get("cache_hit", False),
        response_healed=result.response_healed,
        healing_strategy=result.healing_strategy,
        structured_output=result.structured_output,
    )


def stream_chat_completion(
    db: Session,
    request: schemas.ChatCompletionRequest,
    api_key_label: str | None = None,
    organization_id: int | None = None,
    project_id: int | None = None,
    environment: str | None = None,
):
    import time as _time
    try:
        execution = _execute_routed_chat_completion(
            db=db,
            request=request,
            api_key_label=api_key_label,
            organization_id=organization_id,
            project_id=project_id,
            environment=environment,
        )
    except ValueError as exc:
        err_payload = json.dumps({
            "error": {"message": str(exc), "type": "router_error", "code": "no_available_provider"},
        })
        yield f"data: {err_payload}\n\n"
        yield "data: [DONE]\n\n"
        return
    except Exception as exc:
        err_payload = json.dumps({
            "error": {"message": str(exc), "type": "router_error", "code": "internal_error"},
        })
        yield f"data: {err_payload}\n\n"
        yield "data: [DONE]\n\n"
        return
    result = execution["result"]
    req_id = execution["request_id"]
    selected_model = execution.get("selected_model") or request.model
    created = int(_time.time())

    words = result.completion.split(" ") if result.completion else []
    for index, chunk in enumerate(words):
        content = f"{chunk} " if index < len(words) - 1 else chunk
        payload = {
            "id": req_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": selected_model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": content},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    # Emit tool_calls as proper OpenAI-compatible delta chunks so clients using
    # the OpenAI SDK (e.g. AIOS) can accumulate them via delta.tool_calls.
    if result.tool_calls:
        for tc_index, tc in enumerate(result.tool_calls):
            if not isinstance(tc, dict):
                continue
            tc_func = tc.get("function") or {}
            tc_chunk = {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": selected_model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": tc_index,
                                    "id": tc.get("id", f"call_{tc_index}"),
                                    "type": "function",
                                    "function": {
                                        "name": tc_func.get("name", ""),
                                        "arguments": tc_func.get("arguments", "{}"),
                                    },
                                }
                            ]
                        },
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(tc_chunk, ensure_ascii=False)}\n\n"

    final_payload = {
        "id": req_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": selected_model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": "tool_calls" if result.tool_calls else "stop",
            }
        ],
        "usage": _build_usage(
            result.prompt_tokens,
            result.completion_tokens,
            result.cached_tokens,
            result.reasoning_tokens,
            result.provider_reported_cost,
        ).model_dump(),
    }
    yield f"data: {json.dumps(final_payload, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"

def create_embedding(db: Session, request: schemas.EmbeddingRequest):
    values = [round((ord(char) % 32) / 31, 4) for char in request.text[:8]]
    if not values:
        values = [0.0]
    return schemas.EmbeddingResponse(embedding=values)

def get_models(db: Session):
    seed_demo_data(db)
    rows = (
        db.query(models.ModelCatalog.model_id)
        .filter(models.ModelCatalog.status == "active")
        .distinct()
        .all()
    )
    model_ids = sorted({row.model_id for row in rows} | {"router/auto"})
    return schemas.ModelListResponse(models=model_ids)

def export_billing_to_csv(db: Session):
    ensure_schema(db)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["request_id", "api_key_label", "requested_model", "resolved_model", "provider", "cost_amount"])

    for row in db.query(models.RequestLog).order_by(models.RequestLog.id.desc()).limit(100):
        writer.writerow(
            [
                row.request_id,
                row.api_key_label or "",
                row.requested_model,
                row.resolved_model or "",
                row.provider_name or "",
                row.cost_amount,
            ]
        )

    output.seek(0)
    return {"csv_url": f"data:text/csv;charset=utf-8,{output.getvalue()}"}


def list_providers(db: Session):
    seed_demo_data(db)
    rows = db.query(models.Provider).order_by(models.Provider.priority.asc()).all()
    return [
        schemas.ProviderItem(
            id=row.id,
            name=row.name,
            adapter_type=row.adapter_type,
            status=row.status,
            health_status=row.health_status,
            priority=row.priority,
            input_cost_per_1k=row.input_cost_per_1k,
            output_cost_per_1k=row.output_cost_per_1k,
        avg_latency_ms=row.avg_latency_ms,
        capabilities=_csv_to_list(row.capability_tags),
        supports_zdr=row.supports_zdr,
        data_collection_mode=row.data_collection_mode,
        max_input_tokens=row.max_input_tokens,
        max_output_tokens=row.max_output_tokens,
        supported_parameters=_csv_to_list(row.supported_parameters),
    )
        for row in rows
    ]


def create_provider(db: Session, provider: schemas.ProviderCreate):
    seed_demo_data(db)
    payload = provider.model_dump()
    payload["capability_tags"] = _list_to_csv(payload.pop("capabilities"))
    payload["supported_parameters"] = _list_to_csv(payload.pop("supported_parameters"))
    # New providers are "unknown" until a test or real request confirms health
    payload.setdefault("health_status", "unknown")
    db_provider = models.Provider(**payload)
    db.add(db_provider)
    db.commit()
    db.refresh(db_provider)
    return schemas.ProviderItem(
        id=db_provider.id,
        name=db_provider.name,
        adapter_type=db_provider.adapter_type,
        status=db_provider.status,
        health_status=db_provider.health_status,
        priority=db_provider.priority,
        input_cost_per_1k=db_provider.input_cost_per_1k,
        output_cost_per_1k=db_provider.output_cost_per_1k,
        avg_latency_ms=db_provider.avg_latency_ms,
        capabilities=_csv_to_list(db_provider.capability_tags),
        supports_zdr=db_provider.supports_zdr,
        data_collection_mode=db_provider.data_collection_mode,
        max_input_tokens=db_provider.max_input_tokens,
        max_output_tokens=db_provider.max_output_tokens,
        supported_parameters=_csv_to_list(db_provider.supported_parameters),
    )


def delete_provider(db: Session, provider_id: int):
    db_provider = db.query(models.Provider).filter(models.Provider.id == provider_id).first()
    if db_provider is None:
        raise ValueError(f"INVALID_PROVIDER: {provider_id}")
    # Remove route rules that reference this provider (preferred or backup)
    affected_rules = db.query(models.RouteRule).filter(
        (models.RouteRule.preferred_provider_id == provider_id) |
        (models.RouteRule.backup_provider_id == provider_id)
    ).all()
    for rule in affected_rules:
        db.delete(rule)
    # Remove model catalog entries that reference this provider
    affected_models = db.query(models.ModelCatalog).filter(
        models.ModelCatalog.provider_id == provider_id
    ).all()
    for m in affected_models:
        db.delete(m)
    _record_audit_log(
        db, "provider_deleted",
        f"Deleted provider {db_provider.name} "
        f"(and {len(affected_rules)} route rule(s), {len(affected_models)} model catalog entry/entries)",
    )
    db.delete(db_provider)
    db.commit()


def update_provider(db: Session, provider_id: int, provider: schemas.ProviderCreate):
    seed_demo_data(db)
    db_provider = db.query(models.Provider).filter(models.Provider.id == provider_id).first()
    if db_provider is None:
        raise ValueError(f"INVALID_PROVIDER: {provider_id}")
    payload = provider.model_dump()
    payload["capability_tags"] = _list_to_csv(payload.pop("capabilities"))
    payload["supported_parameters"] = _list_to_csv(payload.pop("supported_parameters"))
    for key, value in payload.items():
        setattr(db_provider, key, value)
    _record_audit_log(db, "provider_updated", f"Updated provider {db_provider.name}")
    db.commit()
    db.refresh(db_provider)
    return schemas.ProviderItem(
        id=db_provider.id,
        name=db_provider.name,
        adapter_type=db_provider.adapter_type,
        status=db_provider.status,
        health_status=db_provider.health_status,
        priority=db_provider.priority,
        input_cost_per_1k=db_provider.input_cost_per_1k,
        output_cost_per_1k=db_provider.output_cost_per_1k,
        avg_latency_ms=db_provider.avg_latency_ms,
        capabilities=_csv_to_list(db_provider.capability_tags),
        supports_zdr=db_provider.supports_zdr,
        data_collection_mode=db_provider.data_collection_mode,
        max_input_tokens=db_provider.max_input_tokens,
        max_output_tokens=db_provider.max_output_tokens,
        supported_parameters=_csv_to_list(db_provider.supported_parameters),
    )


def list_model_catalog(db: Session):
    seed_demo_data(db)
    rows = (
        db.query(models.ModelCatalog, models.Provider.name)
        .join(models.Provider, models.Provider.id == models.ModelCatalog.provider_id)
        .order_by(models.ModelCatalog.model_id.asc(), models.Provider.priority.asc())
        .all()
    )
    return [
        schemas.ModelCatalogItem(
            id=model.id,
            model_id=model.model_id,
            provider_id=model.provider_id,
            provider_name=provider_name,
            provider_model_name=model.provider_model_name,
            status=model.status,
        )
        for model, provider_name in rows
    ]


def create_model_catalog_item(db: Session, model: schemas.ModelCatalogCreate):
    seed_demo_data(db)
    db_model = models.ModelCatalog(**model.model_dump())
    db.add(db_model)
    db.commit()
    db.refresh(db_model)
    provider = db.query(models.Provider).filter(models.Provider.id == db_model.provider_id).first()
    return schemas.ModelCatalogItem(
        id=db_model.id,
        model_id=db_model.model_id,
        provider_id=db_model.provider_id,
        provider_name=provider.name if provider else "",
        provider_model_name=db_model.provider_model_name,
        status=db_model.status,
    )


def update_model_catalog_item(db: Session, model_id: int, model: schemas.ModelCatalogCreate):
    seed_demo_data(db)
    db_model = db.query(models.ModelCatalog).filter(models.ModelCatalog.id == model_id).first()
    if db_model is None:
        raise ValueError(f"INVALID_MODEL_CATALOG: {model_id}")
    for key, value in model.model_dump().items():
        setattr(db_model, key, value)
    db.commit()
    db.refresh(db_model)
    provider = db.query(models.Provider).filter(models.Provider.id == db_model.provider_id).first()
    return schemas.ModelCatalogItem(
        id=db_model.id,
        model_id=db_model.model_id,
        provider_id=db_model.provider_id,
        provider_name=provider.name if provider else "",
        provider_model_name=db_model.provider_model_name,
        status=db_model.status,
    )


def delete_model_catalog_item(db: Session, model_id: int) -> bool:
    db_model = db.query(models.ModelCatalog).filter(models.ModelCatalog.id == model_id).first()
    if db_model is None:
        return False
    db.delete(db_model)
    db.commit()
    return True


def list_route_rules(db: Session):
    seed_demo_data(db)
    rows = db.query(models.RouteRule).order_by(models.RouteRule.model_id.asc()).all()
    return [
        schemas.RouteRuleItem(
            id=route.id,
            model_id=route.model_id,
            preferred_provider_id=route.preferred_provider_id,
            preferred_provider_name=route.preferred_provider.name,
            backup_provider_id=route.backup_provider_id,
            backup_provider_name=route.backup_provider.name if route.backup_provider else None,
            timeout_ms=route.timeout_ms,
        )
        for route in rows
    ]


def upsert_route_rule(db: Session, route_rule: schemas.RouteRuleCreate):
    seed_demo_data(db)
    existing = db.query(models.RouteRule).filter(models.RouteRule.model_id == route_rule.model_id).first()
    if existing is None:
        existing = models.RouteRule(**route_rule.model_dump())
        db.add(existing)
    else:
        for key, value in route_rule.model_dump().items():
            setattr(existing, key, value)
    db.commit()
    db.refresh(existing)
    return schemas.RouteRuleItem(
        id=existing.id,
        model_id=existing.model_id,
        preferred_provider_id=existing.preferred_provider_id,
        preferred_provider_name=existing.preferred_provider.name,
        backup_provider_id=existing.backup_provider_id,
        backup_provider_name=existing.backup_provider.name if existing.backup_provider else None,
        timeout_ms=existing.timeout_ms,
    )


def list_request_logs(
    db: Session,
    organization_id: int | None = None,
    project_id: int | None = None,
    environment: str | None = None,
):
    ensure_schema(db)
    query = db.query(models.RequestLog)
    if organization_id is not None:
        query = query.filter(models.RequestLog.organization_id == organization_id)
    if project_id is not None:
        query = query.filter(models.RequestLog.project_id == project_id)
    if environment:
        query = query.filter(models.RequestLog.environment == environment)
    rows = query.order_by(models.RequestLog.id.desc()).limit(100).all()
    items: list[schemas.RequestLogItem] = []
    for row in rows:
        trace = json.loads(row.route_trace_json) if row.route_trace_json else None
        experiment = (trace.get("route_scoring_experiment") or {}) if trace else {}
        items.append(
            schemas.RequestLogItem(
                request_id=row.request_id,
                api_key_label=row.api_key_label,
                organization_id=row.organization_id,
                project_id=row.project_id,
                environment=row.environment,
                requested_model=row.requested_model,
                resolved_model=row.resolved_model,
                provider_name=row.provider_name,
                workload_class=(trace.get("workload_class") if trace else None),
                applied_profile_name=(trace.get("applied_profile_name") if trace else None),
                experiment_name=experiment.get("name"),
                experiment_variant=experiment.get("variant"),
                sticky_key=row.sticky_key,
                status_code=row.status_code,
                latency=row.latency,
                fallback_used=row.fallback_used,
                route_changed=_route_trace_changed_from_default(trace) if trace else False,
                cache_hit=row.cache_hit,
                response_healed=row.response_healed,
                healing_strategy=row.healing_strategy,
                error_code=row.error_code,
                route_trace=trace,
            )
        )
    return items


def get_billing_usage(
    db: Session,
    organization_id: int | None = None,
    project_id: int | None = None,
    environment: str | None = None,
):
    ensure_schema(db)
    query = db.query(models.RequestLog)
    if organization_id is not None:
        query = query.filter(models.RequestLog.organization_id == organization_id)
    if project_id is not None:
        query = query.filter(models.RequestLog.project_id == project_id)
    if environment:
        query = query.filter(models.RequestLog.environment == environment)
    rows = query.order_by(models.RequestLog.id.desc()).all()
    grouped: dict[tuple[str, str, str, str], schemas.BillingUsageItem] = {}
    for row in rows:
        label = row.api_key_label or "unknown"
        resolved_model = row.resolved_model or row.requested_model
        provider_name = row.provider_name or "unknown"
        environment_label = row.environment or "default"
        key = (label, resolved_model, provider_name, environment_label)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = schemas.BillingUsageItem(
                api_key_label=label,
                organization_id=row.organization_id,
                project_id=row.project_id,
                environment=row.environment,
                resolved_model=resolved_model,
                provider_name=provider_name,
                request_count=1,
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                cached_tokens=row.cached_tokens,
                reasoning_tokens=row.reasoning_tokens,
                total_cost=row.cost_amount,
                provider_reported_cost=row.provider_reported_cost,
            )
        else:
            existing.request_count += 1
            existing.prompt_tokens += row.prompt_tokens
            existing.completion_tokens += row.completion_tokens
            existing.cached_tokens += row.cached_tokens
            existing.reasoning_tokens += row.reasoning_tokens
            existing.total_cost = round(existing.total_cost + row.cost_amount, 6)
            existing.provider_reported_cost = round(existing.provider_reported_cost + row.provider_reported_cost, 6)
    items = sorted(grouped.values(), key=lambda item: (item.api_key_label, item.resolved_model or "", item.provider_name or ""))
    return schemas.BillingUsageResponse(items=items)


def list_router_api_keys(db: Session):
    ensure_schema(db)
    rows = db.query(models.RouterApiKey).order_by(models.RouterApiKey.id.asc()).all()
    return [
        schemas.RouterApiKeyItem(
            id=row.id,
            name=row.name,
            key_prefix=row.key_prefix,
            status=row.status,
            organization_id=row.organization_id,
            project_id=row.project_id,
            environment=row.environment,
            quota_requests=row.quota_requests,
            request_count=row.request_count,
            expires_at=row.expires_at.isoformat() if row.expires_at else None,
            rotated_from_key_id=row.rotated_from_key_id,
        )
        for row in rows
    ]


def create_router_api_key(db: Session, api_key: schemas.RouterApiKeyCreate):
    ensure_schema(db)
    plain_api_key = _generate_router_api_key()
    db_key = models.RouterApiKey(
        name=api_key.name,
        key_hash=_hash_api_key(plain_api_key),
        key_prefix=plain_api_key[:10],
        status="active",
        organization_id=api_key.organization_id,
        project_id=api_key.project_id,
        environment=api_key.environment,
        quota_requests=api_key.quota_requests,
        request_count=0,
        expires_at=_parse_optional_datetime(api_key.expires_at),
    )
    db.add(db_key)
    _record_audit_log(db, "router_api_key_created", f"Created API key {api_key.name}")
    db.commit()
    db.refresh(db_key)
    return schemas.RouterApiKeyCreateResult(
        id=db_key.id,
        name=db_key.name,
        key_prefix=db_key.key_prefix,
        status=db_key.status,
        organization_id=db_key.organization_id,
        project_id=db_key.project_id,
        environment=db_key.environment,
        quota_requests=db_key.quota_requests,
        request_count=db_key.request_count,
        expires_at=db_key.expires_at.isoformat() if db_key.expires_at else None,
        rotated_from_key_id=db_key.rotated_from_key_id,
        plain_api_key=plain_api_key,
    )


def update_router_api_key(db: Session, key_id: int, update: schemas.RouterApiKeyUpdate):
    ensure_schema(db)
    db_key = db.query(models.RouterApiKey).filter(models.RouterApiKey.id == key_id).first()
    if db_key is None:
        raise ValueError(f"INVALID_ROUTER_API_KEY: {key_id}")
    payload = update.model_dump(exclude_none=True)
    if "expires_at" in payload:
        db_key.expires_at = _parse_optional_datetime(payload.pop("expires_at"))
    for key, value in payload.items():
        setattr(db_key, key, value)
    _record_audit_log(db, "router_api_key_updated", f"Updated API key {db_key.name}")
    db.commit()
    items = list_router_api_keys(db)
    for item in items:
        if item.id == key_id:
            return item
    raise ValueError(f"INVALID_ROUTER_API_KEY: {key_id}")


def rotate_router_api_key(db: Session, key_id: int, payload: schemas.RouterApiKeyRotateRequest):
    ensure_schema(db)
    existing = db.query(models.RouterApiKey).filter(models.RouterApiKey.id == key_id).first()
    if existing is None:
        raise ValueError(f"INVALID_ROUTER_API_KEY: {key_id}")
    existing.status = "rotated"
    plain_api_key = _generate_router_api_key()
    rotated_name = payload.name or f"{existing.name}-rotated"
    db_key = models.RouterApiKey(
        name=rotated_name,
        key_hash=_hash_api_key(plain_api_key),
        key_prefix=plain_api_key[:10],
        status="active",
        organization_id=existing.organization_id,
        project_id=existing.project_id,
        environment=existing.environment,
        quota_requests=payload.quota_requests if payload.quota_requests is not None else existing.quota_requests,
        request_count=0,
        expires_at=_parse_optional_datetime(payload.expires_at) if payload.expires_at is not None else existing.expires_at,
        rotated_from_key_id=existing.id,
    )
    db.add(db_key)
    _record_audit_log(db, "router_api_key_rotated", f"Rotated API key {existing.name} to {rotated_name}")
    db.commit()
    db.refresh(db_key)
    return schemas.RouterApiKeyCreateResult(
        id=db_key.id,
        name=db_key.name,
        key_prefix=db_key.key_prefix,
        status=db_key.status,
        organization_id=db_key.organization_id,
        project_id=db_key.project_id,
        environment=db_key.environment,
        quota_requests=db_key.quota_requests,
        request_count=db_key.request_count,
        expires_at=db_key.expires_at.isoformat() if db_key.expires_at else None,
        rotated_from_key_id=db_key.rotated_from_key_id,
        plain_api_key=plain_api_key,
    )


def find_router_api_key_context(db: Session, candidate_key: str) -> dict[str, int | str | None] | None:
    ensure_schema(db)
    key_hash = _hash_api_key(candidate_key)
    db_key = (
        db.query(models.RouterApiKey)
        .filter(
            models.RouterApiKey.key_hash == key_hash,
            models.RouterApiKey.status == "active",
        )
        .first()
    )
    if db_key is None:
        return None
    if db_key.quota_requests is not None and (db_key.request_count or 0) >= db_key.quota_requests:
        return None
    expires_at = _normalize_stored_datetime(db_key.expires_at)
    if expires_at is not None and expires_at <= datetime.now(UTC):
        return None
    return {
        "label": db_key.name,
        "organization_id": db_key.organization_id,
        "project_id": db_key.project_id,
        "environment": db_key.environment,
    }


def find_router_api_key_label(db: Session, candidate_key: str) -> str | None:
    context = find_router_api_key_context(db=db, candidate_key=candidate_key)
    return context["label"] if context else None


def list_organizations(db: Session):
    ensure_schema(db)
    return db.query(models.Organization).order_by(models.Organization.name.asc()).all()


def create_organization(db: Session, organization: schemas.OrganizationCreate):
    ensure_schema(db)
    row = models.Organization(name=organization.name)
    db.add(row)
    _record_audit_log(db, "organization_created", f"Created organization {organization.name}")
    db.commit()
    db.refresh(row)
    return row


def list_projects(db: Session):
    ensure_schema(db)
    rows = (
        db.query(models.Project, models.Organization.name)
        .join(models.Organization, models.Organization.id == models.Project.organization_id)
        .order_by(models.Organization.name.asc(), models.Project.name.asc())
        .all()
    )
    return [
        schemas.ProjectItem(
            id=project.id,
            name=project.name,
            organization_id=project.organization_id,
            organization_name=organization_name,
        )
        for project, organization_name in rows
    ]


def create_project(db: Session, project: schemas.ProjectCreate):
    ensure_schema(db)
    row = models.Project(name=project.name, organization_id=project.organization_id)
    db.add(row)
    _record_audit_log(db, "project_created", f"Created project {project.name}")
    db.commit()
    db.refresh(row)
    organization = db.query(models.Organization).filter(models.Organization.id == row.organization_id).first()
    return schemas.ProjectItem(
        id=row.id,
        name=row.name,
        organization_id=row.organization_id,
        organization_name=organization.name if organization else "",
    )


def list_workspace_route_defaults(db: Session):
    ensure_schema(db)
    rows = db.query(models.WorkspaceRouteDefault).order_by(models.WorkspaceRouteDefault.id.desc()).all()
    organizations = {row.id: row.name for row in db.query(models.Organization).all()}
    projects = {row.id: row.name for row in db.query(models.Project).all()}
    return [
        schemas.WorkspaceRouteDefaultItem(
            id=row.id,
            organization_id=row.organization_id,
            organization_name=organizations.get(row.organization_id),
            project_id=row.project_id,
            project_name=projects.get(row.project_id),
            provider_order=_csv_to_list(row.provider_order),
            sort_mode=row.sort_mode,
            max_price_per_1k=row.max_price_per_1k,
            require_capabilities=_csv_to_list(row.require_capabilities),
            require_parameters=row.require_parameters,
            zdr=row.zdr,
            data_collection=row.data_collection,
        )
        for row in rows
    ]


def create_workspace_route_default(db: Session, payload: schemas.WorkspaceRouteDefaultCreate):
    ensure_schema(db)
    row = models.WorkspaceRouteDefault(
        organization_id=payload.organization_id,
        project_id=payload.project_id,
        provider_order=_list_to_csv(payload.provider_order),
        sort_mode=payload.sort_mode,
        max_price_per_1k=payload.max_price_per_1k,
        require_capabilities=_list_to_csv(payload.require_capabilities),
        require_parameters=payload.require_parameters,
        zdr=payload.zdr,
        data_collection=payload.data_collection,
    )
    db.add(row)
    _record_audit_log(
        db,
        "workspace_route_default_created",
        f"Created workspace route default for org={payload.organization_id} project={payload.project_id}",
    )
    db.commit()
    items = list_workspace_route_defaults(db)
    return items[0]


def update_workspace_route_default(db: Session, default_id: int, payload: schemas.WorkspaceRouteDefaultCreate):
    ensure_schema(db)
    row = db.query(models.WorkspaceRouteDefault).filter(models.WorkspaceRouteDefault.id == default_id).first()
    if row is None:
        raise ValueError(f"INVALID_WORKSPACE_ROUTE_DEFAULT: {default_id}")
    row.organization_id = payload.organization_id
    row.project_id = payload.project_id
    row.provider_order = _list_to_csv(payload.provider_order)
    row.sort_mode = payload.sort_mode
    row.max_price_per_1k = payload.max_price_per_1k
    row.require_capabilities = _list_to_csv(payload.require_capabilities)
    row.require_parameters = payload.require_parameters
    row.zdr = payload.zdr
    row.data_collection = payload.data_collection
    _record_audit_log(db, "workspace_route_default_updated", f"Updated workspace route default {default_id}")
    db.commit()
    items = list_workspace_route_defaults(db)
    for item in items:
        if item.id == default_id:
            return item
    raise ValueError(f"INVALID_WORKSPACE_ROUTE_DEFAULT: {default_id}")


def list_workspace_guardrail_configs(db: Session):
    ensure_schema(db)
    rows = db.query(models.WorkspaceGuardrailConfig).order_by(models.WorkspaceGuardrailConfig.id.desc()).all()
    organizations = {row.id: row.name for row in db.query(models.Organization).all()}
    projects = {row.id: row.name for row in db.query(models.Project).all()}
    return [
        schemas.WorkspaceGuardrailConfigItem(
            id=row.id,
            organization_id=row.organization_id,
            organization_name=organizations.get(row.organization_id),
            project_id=row.project_id,
            project_name=projects.get(row.project_id),
            allowed_providers=_csv_to_list(row.allowed_providers) if row.allowed_providers is not None else None,
            denied_providers=_csv_to_list(row.denied_providers) if row.denied_providers is not None else None,
            blocked_words=_csv_to_list(row.blocked_words) if row.blocked_words is not None else None,
            max_prompt_chars=row.max_prompt_chars,
            retention_mode=row.retention_mode,
        )
        for row in rows
    ]


def create_workspace_guardrail_config(db: Session, payload: schemas.WorkspaceGuardrailConfigCreate):
    ensure_schema(db)
    row = models.WorkspaceGuardrailConfig(
        organization_id=payload.organization_id,
        project_id=payload.project_id,
        allowed_providers=_list_to_csv(payload.allowed_providers) if payload.allowed_providers is not None else None,
        denied_providers=_list_to_csv(payload.denied_providers) if payload.denied_providers is not None else None,
        blocked_words=_list_to_csv(payload.blocked_words) if payload.blocked_words is not None else None,
        max_prompt_chars=payload.max_prompt_chars,
        retention_mode=payload.retention_mode,
    )
    db.add(row)
    _record_audit_log(
        db,
        "workspace_guardrail_created",
        f"Created workspace guardrail for org={payload.organization_id} project={payload.project_id}",
    )
    db.commit()
    return list_workspace_guardrail_configs(db)[0]


def update_workspace_guardrail_config(db: Session, config_id: int, payload: schemas.WorkspaceGuardrailConfigCreate):
    ensure_schema(db)
    row = db.query(models.WorkspaceGuardrailConfig).filter(models.WorkspaceGuardrailConfig.id == config_id).first()
    if row is None:
        raise ValueError(f"INVALID_WORKSPACE_GUARDRAIL: {config_id}")
    row.organization_id = payload.organization_id
    row.project_id = payload.project_id
    row.allowed_providers = _list_to_csv(payload.allowed_providers) if payload.allowed_providers is not None else None
    row.denied_providers = _list_to_csv(payload.denied_providers) if payload.denied_providers is not None else None
    row.blocked_words = _list_to_csv(payload.blocked_words) if payload.blocked_words is not None else None
    row.max_prompt_chars = payload.max_prompt_chars
    row.retention_mode = payload.retention_mode
    _record_audit_log(db, "workspace_guardrail_updated", f"Updated workspace guardrail {config_id}")
    db.commit()
    items = list_workspace_guardrail_configs(db)
    for item in items:
        if item.id == config_id:
            return item
    raise ValueError(f"INVALID_WORKSPACE_GUARDRAIL: {config_id}")


def get_guardrail_config(db: Session):
    ensure_schema(db)
    config = _get_guardrail_config(db)
    return schemas.GuardrailConfigItem(
        allowed_providers=_csv_to_list(config.allowed_providers),
        denied_providers=_csv_to_list(config.denied_providers),
        blocked_words=_csv_to_list(config.blocked_words),
        max_prompt_chars=config.max_prompt_chars,
        retention_mode=config.retention_mode,
    )


def update_guardrail_config(db: Session, update: schemas.GuardrailConfigUpdate):
    ensure_schema(db)
    config = _get_guardrail_config(db)
    config.allowed_providers = _list_to_csv(update.allowed_providers)
    config.denied_providers = _list_to_csv(update.denied_providers)
    config.blocked_words = _list_to_csv(update.blocked_words)
    config.max_prompt_chars = update.max_prompt_chars
    config.retention_mode = update.retention_mode
    _record_audit_log(db, "guardrail_updated", "Updated guardrail configuration")
    db.commit()
    return get_guardrail_config(db)


def list_audit_logs(db: Session):
    ensure_schema(db)
    rows = db.query(models.AuditLog).order_by(models.AuditLog.id.desc()).limit(100).all()
    return [
        schemas.AuditLogItem(
            id=row.id,
            action=row.action,
            details=row.details,
            timestamp=row.timestamp.isoformat(),
        )
        for row in rows
    ]


def list_notifications(db: Session):
    ensure_schema(db)
    rows = db.query(models.NotificationRecord).order_by(models.NotificationRecord.id.desc()).limit(100).all()
    return [
        schemas.NotificationItem(
            id=row.id,
            type=row.type,
            message=row.message,
            timestamp=row.timestamp.isoformat(),
        )
        for row in rows
    ]


def create_notification(db: Session, notification: schemas.NotificationCreate):
    ensure_schema(db)
    row = models.NotificationRecord(
        type=notification.type,
        message=notification.message,
        timestamp=datetime.now(UTC),
    )
    db.add(row)
    _record_audit_log(db, "notification_created", f"Created notification {notification.type}")
    db.commit()
    db.refresh(row)
    return schemas.NotificationItem(
        id=row.id,
        type=row.type,
        message=row.message,
        timestamp=row.timestamp.isoformat(),
    )


def _filter_request_logs_query(
    db: Session,
    organization_id: int | None = None,
    project_id: int | None = None,
    environment: str | None = None,
):
    query = db.query(models.RequestLog)
    if organization_id is not None:
        query = query.filter(models.RequestLog.organization_id == organization_id)
    if project_id is not None:
        query = query.filter(models.RequestLog.project_id == project_id)
    if environment:
        query = query.filter(models.RequestLog.environment == environment)
    return query


def _build_workspace_usage_summary(
    db: Session,
    request_logs: list[models.RequestLog],
) -> list[schemas.WorkspaceUsageSummaryItem]:
    organization_names = {row.id: row.name for row in db.query(models.Organization).all()}
    project_rows = db.query(models.Project).all()
    project_names = {row.id: row.name for row in project_rows}
    project_organizations = {row.id: row.organization_id for row in project_rows}
    grouped: dict[tuple[int | None, int | None, str | None], list[models.RequestLog]] = {}
    for row in request_logs:
        key = (
            row.organization_id or project_organizations.get(row.project_id),
            row.project_id,
            row.environment,
        )
        grouped.setdefault(key, []).append(row)

    summaries: list[schemas.WorkspaceUsageSummaryItem] = []
    for (org_id, proj_id, environment), rows in sorted(grouped.items(), key=lambda item: ((item[0][0] or 0), (item[0][1] or 0), item[0][2] or "")):
        failures = sum(1 for row in rows if row.status_code >= 400)
        fallback_count = sum(1 for row in rows if row.fallback_used)
        cache_hit_count = sum(1 for row in rows if row.cache_hit)
        avg_latency = round(sum(row.latency for row in rows) / len(rows), 2) if rows else 0.0
        total_cost = round(sum(row.cost_amount for row in rows), 6)
        summaries.append(
            schemas.WorkspaceUsageSummaryItem(
                organization_id=org_id,
                organization_name=organization_names.get(org_id),
                project_id=proj_id,
                project_name=project_names.get(proj_id),
                environment=environment,
                request_count=len(rows),
                failure_count=failures,
                fallback_count=fallback_count,
                cache_hit_count=cache_hit_count,
                total_cost=total_cost,
                avg_latency=avg_latency,
            )
        )
    return summaries


def _build_cost_optimization_opportunities(
    db: Session,
    request_logs: list[models.RequestLog],
) -> list[schemas.CostOptimizationOpportunityItem]:
    opportunities: list[schemas.CostOptimizationOpportunityItem] = []
    model_provider_groups: dict[str, dict[str, list[models.RequestLog]]] = {}
    for row in request_logs:
        model_label = row.resolved_model or row.requested_model or "unknown"
        provider_label = row.provider_name or "unknown"
        model_provider_groups.setdefault(model_label, {}).setdefault(provider_label, []).append(row)

    for model_label, provider_groups in sorted(model_provider_groups.items()):
        if len(provider_groups) < 2:
            continue
        provider_stats = []
        for provider_label, rows in provider_groups.items():
            total_cost = sum(row.cost_amount for row in rows)
            request_count = len(rows)
            avg_cost = total_cost / request_count if request_count else 0.0
            provider_stats.append((provider_label, request_count, total_cost, avg_cost))
        provider_stats.sort(key=lambda item: item[3])
        cheapest_provider, _, _, cheapest_avg = provider_stats[0]
        for provider_label, request_count, total_cost, avg_cost in provider_stats[1:]:
            estimated_savings = round(max(avg_cost - cheapest_avg, 0) * request_count, 6)
            if estimated_savings <= 0:
                continue
            opportunities.append(
                schemas.CostOptimizationOpportunityItem(
                    category="provider_shift",
                    title=f"Shift {model_label} traffic off {provider_label}",
                    scope_label=model_label,
                    summary=(
                        f"{provider_label} handles {request_count} requests for {model_label} "
                        f"at a higher average cost than {cheapest_provider}."
                    ),
                    estimated_savings=estimated_savings,
                    current_cost=round(total_cost, 6),
                    target_cost=round(total_cost - estimated_savings, 6),
                    recommendation=(
                        f"Move more {model_label} traffic to {cheapest_provider} or apply a price-first routing rule "
                        f"for this workload."
                    ),
                )
            )

    workspace_summaries = _build_workspace_usage_summary(db=db, request_logs=request_logs)
    for summary in workspace_summaries:
        if summary.request_count < 2 or summary.total_cost <= 0:
            continue
        friction_events = summary.fallback_count + summary.failure_count
        if friction_events <= 0:
            continue
        friction_rate = friction_events / summary.request_count
        estimated_savings = round(summary.total_cost * min(friction_rate * 0.15, 0.3), 6)
        if estimated_savings <= 0:
            continue
        workspace_label = f"{summary.organization_name or summary.organization_id or 'N/A'} / {summary.project_name or summary.project_id or 'N/A'}"
        opportunities.append(
            schemas.CostOptimizationOpportunityItem(
                category="workspace_hotspot",
                title=f"Reduce fallback overhead in {workspace_label}",
                scope_label=workspace_label,
                summary=(
                    f"This workspace has {summary.fallback_count} fallbacks and {summary.failure_count} failures "
                    f"across {summary.request_count} requests."
                ),
                estimated_savings=estimated_savings,
                current_cost=round(summary.total_cost, 6),
                target_cost=round(summary.total_cost - estimated_savings, 6),
                recommendation=(
                    "Tighten workspace routing defaults, add provider constraints, or move repeated traffic to "
                    "lower-friction providers."
                ),
            )
        )

    opportunities.sort(key=lambda item: item.estimated_savings, reverse=True)
    return opportunities[:5]


def _build_anomaly_alerts(
    db: Session,
    request_logs: list[models.RequestLog],
) -> list[schemas.AnomalyAlertItem]:
    alerts: list[schemas.AnomalyAlertItem] = []
    provider_groups: dict[str, list[models.RequestLog]] = {}
    for row in request_logs:
        provider_groups.setdefault(row.provider_name or "unknown", []).append(row)

    for provider_name, rows in sorted(provider_groups.items()):
        if len(rows) < 2:
            continue
        failure_rate = sum(1 for row in rows if row.status_code >= 400) / len(rows)
        avg_latency = sum(row.latency for row in rows) / len(rows)
        if failure_rate >= 0.25:
            alerts.append(
                schemas.AnomalyAlertItem(
                    category="provider_failure",
                    severity="high",
                    title=f"High failure rate on {provider_name}",
                    scope_label=provider_name,
                    message=f"{provider_name} failed {failure_rate:.0%} of {len(rows)} recent requests.",
                    metric_value=round(failure_rate, 4),
                    threshold=0.25,
                )
            )
        if avg_latency >= 600:
            alerts.append(
                schemas.AnomalyAlertItem(
                    category="provider_latency",
                    severity="medium",
                    title=f"High latency on {provider_name}",
                    scope_label=provider_name,
                    message=f"{provider_name} averaged {avg_latency:.2f} ms over {len(rows)} recent requests.",
                    metric_value=round(avg_latency, 2),
                    threshold=600,
                )
            )

    for item in _build_workspace_usage_summary(db=db, request_logs=request_logs):
        if item.request_count < 2:
            continue
        fallback_rate = item.fallback_count / item.request_count if item.request_count else 0.0
        if fallback_rate >= 0.3:
            scope_label = f"{item.organization_name or item.organization_id or 'N/A'} / {item.project_name or item.project_id or 'N/A'}"
            alerts.append(
                schemas.AnomalyAlertItem(
                    category="workspace_fallback",
                    severity="medium",
                    title=f"High fallback rate in {scope_label}",
                    scope_label=scope_label,
                    message=f"{scope_label} has fallback rate {fallback_rate:.0%} across {item.request_count} recent requests.",
                    metric_value=round(fallback_rate, 4),
                    threshold=0.3,
                )
            )

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    alerts.sort(key=lambda item: (severity_rank.get(item.severity, 99), -item.metric_value))
    return alerts[:10]


def _build_route_scoring_drift_summary(
    db: Session,
    request_logs: list[models.RequestLog],
) -> list[schemas.RouteScoringDriftItem]:
    active_profile_name = _get_active_route_scoring_profile_name(db)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in request_logs:
        if not row.route_trace_json:
            continue
        trace = json.loads(row.route_trace_json)
        workload_class = trace.get("workload_class")
        if not workload_class:
            continue
        grouped.setdefault(workload_class, []).append(trace)

    items: list[schemas.RouteScoringDriftItem] = []
    for workload_class, traces in sorted(grouped.items()):
        default_weights = _normalize_weight_map(_get_default_route_score_weights(workload_class))
        active_weights = _normalize_weight_map(_get_route_score_weights(db, workload_class))
        drift_score = round(
            sum(abs(active_weights[key] - default_weights[key]) for key in ["capability", "latency", "cost"]),
            4,
        )
        changed_routes = sum(1 for trace in traces if _route_trace_changed_from_default(trace))
        route_change_rate = round(changed_routes / len(traces), 4) if traces else 0.0
        items.append(
            schemas.RouteScoringDriftItem(
                workload_class=workload_class,
                request_count=len(traces),
                active_profile_name=active_profile_name,
                drift_score=drift_score,
                route_change_rate=route_change_rate,
                default_weights=default_weights,
                active_weights=active_weights,
            )
        )
    items.sort(key=lambda item: (item.drift_score, item.route_change_rate, item.request_count), reverse=True)
    return items[:10]


def get_analytics_summary(
    db: Session,
    organization_id: int | None = None,
    project_id: int | None = None,
    environment: str | None = None,
):
    ensure_schema(db)
    request_logs = _filter_request_logs_query(
        db=db,
        organization_id=organization_id,
        project_id=project_id,
        environment=environment,
    ).all()
    total_requests = len(request_logs)
    fallback_count = sum(1 for row in request_logs if row.fallback_used)
    blocked_requests = sum(1 for row in request_logs if row.error_code == "GUARDRAIL_BLOCKED_WORD")
    cache_hits = sum(1 for row in request_logs if row.cache_hit)
    sticky_requests = sum(1 for row in request_logs if row.sticky_key)
    provider_groups: dict[str, list[models.RequestLog]] = {}
    model_groups: dict[str, list[models.RequestLog]] = {}
    for row in request_logs:
        provider_groups.setdefault(row.provider_name or "unknown", []).append(row)
        model_groups.setdefault(row.resolved_model or row.requested_model, []).append(row)

    def build_series(label: str, rows: list[models.RequestLog]) -> schemas.AnalyticsSeriesItem:
        failures = sum(1 for row in rows if row.status_code >= 400)
        avg_latency = round(sum(row.latency for row in rows) / len(rows), 2) if rows else 0.0
        total_cost = round(sum(row.cost_amount for row in rows), 6)
        return schemas.AnalyticsSeriesItem(
            label=label,
            requests=len(rows),
            failures=failures,
            avg_latency=avg_latency,
            total_cost=total_cost,
        )

    recent_rows = sorted(
        request_logs,
        key=lambda row: row.id or 0,
        reverse=True,
    )[:50]
    recent_traces = [
        json.loads(row.route_trace_json)
        for row in recent_rows
        if row.route_trace_json
    ]
    recent_changed = sum(1 for trace in recent_traces if _route_trace_changed_from_default(trace))
    workload_shift_groups: dict[str, tuple[int, int]] = {}
    experiment_groups: dict[tuple[str, str], list[models.RequestLog]] = {}
    for trace in recent_traces:
        workload_class = trace.get("workload_class", "chat_general")
        changed = 1 if _route_trace_changed_from_default(trace) else 0
        existing_changed, existing_total = workload_shift_groups.get(workload_class, (0, 0))
        workload_shift_groups[workload_class] = (existing_changed + changed, existing_total + 1)
    for row in request_logs:
        if not row.route_trace_json:
            continue
        trace = json.loads(row.route_trace_json)
        experiment = trace.get("route_scoring_experiment") or {}
        name = experiment.get("name")
        variant = experiment.get("variant")
        if not name or not variant:
            continue
        experiment_groups.setdefault((name, variant), []).append(row)

    return schemas.AnalyticsSummary(
        total_requests=total_requests,
        fallback_rate=round(fallback_count / total_requests, 4) if total_requests else 0.0,
        blocked_requests=blocked_requests,
        active_api_keys=(
            db.query(models.RouterApiKey)
            .filter(models.RouterApiKey.status == "active")
            .filter(models.RouterApiKey.environment == environment if environment else text("1=1"))
            .count()
        ),
        organizations=db.query(models.Organization).count(),
        projects=db.query(models.Project).count(),
        route_scoring_profile_name=_get_active_route_scoring_profile_name(db),
        recent_route_changes=recent_changed,
        recent_route_change_rate=round(recent_changed / len(recent_traces), 4) if recent_traces else 0.0,
        recent_route_replay_cases=len(recent_traces),
        cache_hit_rate=round(cache_hits / total_requests, 4) if total_requests else 0.0,
        cache_hits=cache_hits,
        sticky_requests=sticky_requests,
        route_scoring_workload_shifts=[
            schemas.RouteScoringShiftItem(
                workload_class=workload_class,
                changed_routes=values[0],
                total_routes=values[1],
            )
            for workload_class, values in sorted(workload_shift_groups.items())
        ],
        provider_breakdown=[build_series(label, rows) for label, rows in sorted(provider_groups.items())],
        model_breakdown=[build_series(label, rows) for label, rows in sorted(model_groups.items())],
        workspace_usage_summary=_build_workspace_usage_summary(db=db, request_logs=request_logs),
        cost_optimization_opportunities=_build_cost_optimization_opportunities(db=db, request_logs=request_logs),
        anomaly_alerts=_build_anomaly_alerts(db=db, request_logs=request_logs),
        route_scoring_drift=_build_route_scoring_drift_summary(db=db, request_logs=request_logs),
        route_scoring_experiments=[
            {
                "name": name,
                "variant": variant,
                "requests": len(rows),
                "avg_latency": round(sum(row.latency for row in rows) / len(rows), 2) if rows else 0.0,
                "total_cost": round(sum(row.cost_amount for row in rows), 6),
                "changed_routes": sum(
                    1
                    for row in rows
                    if row.route_trace_json and _route_trace_changed_from_default(json.loads(row.route_trace_json))
                ),
            }
            for (name, variant), rows in sorted(experiment_groups.items())
        ],
    )


def export_analytics_report(
    db: Session,
    organization_id: int | None = None,
    project_id: int | None = None,
    environment: str | None = None,
) -> schemas.DownloadArtifactResponse:
    summary = get_analytics_summary(
        db=db,
        organization_id=organization_id,
        project_id=project_id,
        environment=environment,
    )
    output = io.StringIO()
    output.write("# Analytics Report\n\n")
    output.write(f"- Total Requests: `{summary.total_requests}`\n")
    output.write(f"- Fallback Rate: `{summary.fallback_rate}`\n")
    output.write(f"- Blocked Requests: `{summary.blocked_requests}`\n")
    output.write(f"- Cache Hits: `{summary.cache_hits}`\n")
    output.write(f"- Cache Hit Rate: `{summary.cache_hit_rate}`\n")
    output.write(f"- Sticky Requests: `{summary.sticky_requests}`\n\n")

    output.write("## Workspace Usage Summary\n\n")
    output.write("| organization | project | environment | requests | failures | fallback | cache_hits | total_cost | avg_latency |\n")
    output.write("| --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
    for item in summary.workspace_usage_summary:
        output.write(
            f"| {item.organization_name or item.organization_id or 'N/A'} | {item.project_name or item.project_id or 'N/A'} | {item.environment or 'default'} | "
            f"{item.request_count} | {item.failure_count} | {item.fallback_count} | {item.cache_hit_count} | "
            f"{item.total_cost} | {item.avg_latency} |\n"
        )

    output.write("\n## Provider Breakdown\n\n")
    for item in summary.provider_breakdown:
        output.write(
            f"- `{item.label}`: requests=`{item.requests}`, failures=`{item.failures}`, "
            f"avg_latency=`{item.avg_latency}`, total_cost=`{item.total_cost}`\n"
        )

    output.write("\n## Cost Optimization Opportunities\n\n")
    if summary.cost_optimization_opportunities:
        for item in summary.cost_optimization_opportunities:
            output.write(
                f"- `{item.title}` ({item.category}) on `{item.scope_label}`: "
                f"estimated_savings=`{item.estimated_savings}`, current_cost=`{item.current_cost}`, "
                f"target_cost=`{item.target_cost if item.target_cost is not None else 'N/A'}`. "
                f"{item.recommendation}\n"
            )
    else:
        output.write("- No significant cost optimization opportunities found in the current scope.\n")

    output.write("\n## Anomaly Alerts\n\n")
    if summary.anomaly_alerts:
        for item in summary.anomaly_alerts:
            output.write(
                f"- `{item.title}` [{item.severity}] on `{item.scope_label}`: "
                f"metric=`{item.metric_value}`, threshold=`{item.threshold}`. {item.message}\n"
            )
    else:
        output.write("- No anomaly alerts detected in the current scope.\n")

    output.write("\n## Route Scoring Drift\n\n")
    if summary.route_scoring_drift:
        for item in summary.route_scoring_drift:
            output.write(
                f"- `{item.workload_class}`: requests=`{item.request_count}`, drift_score=`{item.drift_score}`, "
                f"route_change_rate=`{item.route_change_rate}`, active_profile=`{item.active_profile_name}`\n"
            )
    else:
        output.write("- No route scoring drift detected in the current scope.\n")

    output.write("\n## Route Scoring Experiments\n\n")
    if summary.route_scoring_experiments:
        for item in summary.route_scoring_experiments:
            output.write(
                f"- `{item['name']}` / `{item['variant']}`: requests=`{item['requests']}`, "
                f"changed_routes=`{item['changed_routes']}`, avg_latency=`{item['avg_latency']}`, "
                f"total_cost=`{item['total_cost']}`\n"
            )
    else:
        output.write("- No active experiment traffic recorded in the current scope.\n")

    file_name = "analytics_report.md"
    if organization_id is not None or project_id is not None or environment:
        file_name = (
            f"analytics_report_org_{organization_id or 'all'}_proj_{project_id or 'all'}_env_{environment or 'all'}.md"
        )
    return schemas.DownloadArtifactResponse(
        file_name=file_name,
        download_url=f"data:text/markdown;charset=utf-8,{output.getvalue()}",
    )


def detect_notification_anomalies(
    db: Session,
    organization_id: int | None = None,
    project_id: int | None = None,
) -> list[schemas.NotificationItem]:
    summary = get_analytics_summary(db=db, organization_id=organization_id, project_id=project_id)
    created: list[schemas.NotificationItem] = []
    for alert in summary.anomaly_alerts:
        row = models.NotificationRecord(
            type=f"anomaly_{alert.category}",
            message=alert.message,
            timestamp=datetime.now(UTC),
        )
        db.add(row)
        created.append(
            schemas.NotificationItem(
                id=0,
                type=row.type,
                message=row.message,
                timestamp=row.timestamp.isoformat(),
            )
        )
    if created:
        _record_audit_log(
            db,
            "anomaly_notifications_created",
            f"Created {len(created)} anomaly notifications",
        )
    db.commit()
    return list_notifications(db)[: len(created)] if created else []


def test_provider_connection(
    db: Session,
    request: schemas.ProviderConnectionTestRequest,
):
    seed_demo_data(db)
    provider = (
        db.query(models.Provider)
        .filter(models.Provider.id == request.provider_id)
        .first()
    )
    if provider is None:
        raise ValueError(f"INVALID_PROVIDER: {request.provider_id}")

    model = models.ModelCatalog(
        model_id="connection-test",
        provider_id=provider.id,
        provider_model_name=request.provider_model_name,
        status="active",
    )
    chat_request = schemas.ChatCompletionRequest(
        model="connection-test",
        messages=[
            schemas.ChatMessage(
                role="user",
                content=request.prompt,
            )
        ],
    )
    try:
        result = execute_chat_completion(provider, model, chat_request)
    except ProviderExecutionError as exc:
        # Mark provider unhealthy on failed connection test
        provider.health_status = "unhealthy"
        db.commit()
        raise ValueError(str(exc)) from exc

    # Mark provider healthy on successful connection test
    provider.health_status = "healthy"
    db.commit()

    return schemas.ProviderConnectionTestResult(
        success=True,
        provider_name=provider.name,
        adapter_type=provider.adapter_type,
        completion=result.completion,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        message="Connection test succeeded",
    )


def _select_quality_eval_target(
    db: Session,
    payload: schemas.QualityEvalRequest,
) -> tuple[models.Provider, models.ModelCatalog]:
    query = (
        db.query(models.ModelCatalog, models.Provider)
        .join(models.Provider, models.Provider.id == models.ModelCatalog.provider_id)
        .filter(
            models.ModelCatalog.model_id == payload.model_id,
            models.ModelCatalog.status == "active",
            models.Provider.status == "active",
        )
    )
    if payload.provider_id is not None:
        query = query.filter(models.Provider.id == payload.provider_id)
    row = query.order_by(models.Provider.priority.asc(), models.Provider.id.asc()).first()
    if row is None:
        target = f"model={payload.model_id}"
        if payload.provider_id is not None:
            target += f" provider_id={payload.provider_id}"
        raise ValueError(f"QUALITY_EVAL_TARGET_NOT_FOUND: {target}")
    model_mapping, provider = row
    return provider, model_mapping


def _quality_eval_json_valid(result: ProviderResult, completion: str) -> bool:
    if result.structured_output is not None:
        return True
    try:
        json.loads(completion)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


def _score_quality_eval_case(
    case: schemas.QualityEvalCase,
    result: ProviderResult,
    provider: models.Provider,
) -> tuple[float, dict[str, Any]]:
    completion = result.completion or ""
    completion_lower = completion.lower()
    expected_terms = [term for term in case.expected_contains if term]
    forbidden_terms = [term for term in case.must_not_contain if term]
    matched_terms = [term for term in expected_terms if term.lower() in completion_lower]
    missing_terms = [term for term in expected_terms if term.lower() not in completion_lower]
    forbidden_hits = [term for term in forbidden_terms if term.lower() in completion_lower]

    content_score = len(matched_terms) / len(expected_terms) if expected_terms else 1.0
    safety_score = 0.0 if forbidden_hits else 1.0
    json_valid = None
    if case.require_json or case.response_format is not None:
        json_valid = _quality_eval_json_valid(result, completion)
    format_score = 1.0 if json_valid is not False else 0.0
    tool_success = None
    if case.tools:
        tool_success = bool(result.tool_calls)
    tool_score = 1.0 if tool_success is not False else 0.0
    latency_score = 1.0
    if case.max_latency_ms is not None:
        latency_score = max(0.0, 1.0 - (result.latency_ms / max(case.max_latency_ms, 1.0)))
    billable_prompt_tokens = max(result.prompt_tokens - result.cached_tokens, 0)
    cost_usd = round(
        (billable_prompt_tokens / 1000) * provider.input_cost_per_1k
        + (result.completion_tokens / 1000) * provider.output_cost_per_1k,
        6,
    )
    cost_score = 1.0
    if case.max_cost_usd is not None:
        cost_score = max(0.0, 1.0 - (cost_usd / max(case.max_cost_usd, 0.000001)))

    score = (
        0.4 * content_score
        + 0.2 * format_score
        + 0.15 * safety_score
        + 0.1 * tool_score
        + 0.1 * latency_score
        + 0.05 * cost_score
    )
    return round(score, 4), {
        "matched_terms": matched_terms,
        "missing_terms": missing_terms,
        "forbidden_hits": forbidden_hits,
        "json_valid": json_valid,
        "tool_success": tool_success,
        "cost_usd": cost_usd,
    }


def run_quality_eval(
    db: Session,
    payload: schemas.QualityEvalRequest,
) -> schemas.QualityEvalResponse:
    seed_demo_data(db)
    if not payload.cases:
        raise ValueError("QUALITY_EVAL_REQUIRES_CASES")
    provider, model_mapping = _select_quality_eval_target(db, payload)
    results: list[schemas.QualityEvalCaseResult] = []
    total_weight = sum(max(case.weight, 0.0) for case in payload.cases) or 1.0
    weighted_score = 0.0

    for case in payload.cases:
        messages: list[schemas.ChatMessage] = []
        if case.system_prompt:
            messages.append(schemas.ChatMessage(role="system", content=case.system_prompt))
        messages.append(schemas.ChatMessage(role="user", content=case.prompt))
        chat_request = schemas.ChatCompletionRequest(
            model=payload.model_id,
            messages=messages,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            tools=case.tools,
            response_format=case.response_format,
        )
        try:
            result = execute_chat_completion(provider, model_mapping, chat_request)
            score, details = _score_quality_eval_case(case, result, provider)
            weighted_score += score * max(case.weight, 0.0)
            results.append(
                schemas.QualityEvalCaseResult(
                    case_id=case.case_id,
                    success=score >= 0.75,
                    score=score,
                    provider_name=provider.name,
                    model_id=model_mapping.model_id,
                    provider_model_name=model_mapping.provider_model_name,
                    completion=result.completion,
                    matched_terms=details["matched_terms"],
                    missing_terms=details["missing_terms"],
                    forbidden_hits=details["forbidden_hits"],
                    json_valid=details["json_valid"],
                    tool_success=details["tool_success"],
                    latency_ms=round(result.latency_ms, 2),
                    cost_usd=details["cost_usd"],
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                )
            )
        except ProviderExecutionError as exc:
            results.append(
                schemas.QualityEvalCaseResult(
                    case_id=case.case_id,
                    success=False,
                    score=0.0,
                    provider_name=provider.name,
                    model_id=model_mapping.model_id,
                    provider_model_name=model_mapping.provider_model_name,
                    completion="",
                    error=str(exc),
                )
            )

    passed_cases = sum(1 for item in results if item.success)
    total_cost = round(sum(item.cost_usd for item in results), 6)
    average_latency = round(sum(item.latency_ms for item in results) / len(results), 2)
    average_score = round(weighted_score / total_weight, 4)
    _record_audit_log(
        db,
        "quality_eval_run",
        f"Ran quality eval {payload.name} for {provider.name}/{model_mapping.model_id}: score={average_score}",
    )
    db.commit()
    return schemas.QualityEvalResponse(
        name=payload.name,
        model_id=payload.model_id,
        provider_name=provider.name,
        total_cases=len(results),
        passed_cases=passed_cases,
        average_score=average_score,
        total_cost_usd=total_cost,
        average_latency_ms=average_latency,
        results=results,
    )


# ── Feedback recording (v0.7 foundation) ──────────────────────────────────────

def record_request_feedback(db: Session, payload: schemas.FeedbackRequest) -> dict:
    """Store user quality feedback on a RequestLog row."""
    log = db.query(models.RequestLog).filter(
        models.RequestLog.request_id == payload.request_id
    ).first()
    if log is None:
        raise ValueError(f"Request '{payload.request_id}' not found")
    # Store feedback in route_trace_json (non-destructive merge)
    try:
        trace = json.loads(log.route_trace_json or "{}")
    except (json.JSONDecodeError, TypeError):
        trace = {}
    trace["user_feedback"] = {
        "rating": payload.rating,
        "success": payload.success,
        "notes": payload.notes,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    log.route_trace_json = json.dumps(trace, ensure_ascii=False)
    _record_audit_log(
        db, "feedback_received",
        f"Feedback for request {payload.request_id}: rating={payload.rating} success={payload.success}",
    )
    db.commit()
    return {"request_id": payload.request_id, "recorded": True}


# ── v1.2.0: Billing Invoice ────────────────────────────────────────────────────

def get_billing_invoice(
    db: Session,
    org_id: int | None,
    month: str | None,
) -> schemas.BillingInvoiceResponse:
    """
    Build a billing invoice for a given org + month.
    First tries MonthlyBillingSummary (if the rollup job has run),
    then falls back to aggregating BillingRecord directly (mid-month).
    """
    from datetime import datetime

    if month is None:
        month = datetime.now(UTC).strftime("%Y-%m")

    # Try pre-rolled summaries first
    q = db.query(models.MonthlyBillingSummary).filter(
        models.MonthlyBillingSummary.year_month == month
    )
    if org_id is not None:
        q = q.filter(models.MonthlyBillingSummary.organization_id == org_id)
    summaries = q.all()

    if summaries:
        items = [
            schemas.BillingInvoiceItem(
                project_id=s.project_id,
                api_key_name=None,
                model=s.model,
                provider=s.provider,
                request_count=s.request_count,
                prompt_tokens=s.prompt_tokens,
                completion_tokens=s.completion_tokens,
                cached_tokens=s.cached_tokens,
                cost_usd=s.cost_usd,
                upstream_cost_usd=s.upstream_cost_usd,
            )
            for s in summaries
        ]
        total_cost = sum(i.cost_usd for i in items)
        total_req = sum(i.request_count for i in items)
        return schemas.BillingInvoiceResponse(
            organization_id=org_id,
            year_month=month,
            total_cost_usd=round(total_cost, 6),
            total_requests=total_req,
            items=items,
        )

    # Fallback: aggregate BillingRecord directly
    try:
        year, mon = int(month[:4]), int(month[5:7])
    except (ValueError, IndexError):
        year, mon = datetime.now(UTC).year, datetime.now(UTC).month

    month_start = datetime(year, mon, 1)
    if mon == 12:
        month_end = datetime(year + 1, 1, 1)
    else:
        month_end = datetime(year, mon + 1, 1)

    query = db.query(models.BillingRecord).filter(
        models.BillingRecord.date >= month_start,
        models.BillingRecord.date < month_end,
    )
    if org_id is not None:
        query = query.filter(models.BillingRecord.organization_id == org_id)
    records = query.all()

    grouped: dict[tuple, dict] = {}
    for r in records:
        key = (r.project_id, r.api_key_name or "", r.model or "", r.provider or "")
        if key not in grouped:
            grouped[key] = {
                "project_id": r.project_id,
                "api_key_name": r.api_key_name,
                "model": r.model,
                "provider": r.provider,
                "request_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cached_tokens": 0,
                "cost_usd": 0.0,
                "upstream_cost_usd": 0.0,
            }
        g = grouped[key]
        g["request_count"] += 1
        g["prompt_tokens"] += r.prompt_tokens or 0
        g["completion_tokens"] += r.completion_tokens or 0
        g["cached_tokens"] += r.cached_tokens or 0
        g["cost_usd"] = round(g["cost_usd"] + (r.cost_usd or 0.0), 6)
        g["upstream_cost_usd"] = round(g["upstream_cost_usd"] + (r.upstream_cost_usd or 0.0), 6)

    items = [schemas.BillingInvoiceItem(**v) for v in grouped.values()]
    total_cost = sum(i.cost_usd for i in items)
    total_req = sum(i.request_count for i in items)
    return schemas.BillingInvoiceResponse(
        organization_id=org_id,
        year_month=month,
        total_cost_usd=round(total_cost, 6),
        total_requests=total_req,
        items=items,
    )


# ── v1.2.0: Token Usage Dashboard ─────────────────────────────────────────────

def get_token_usage_dashboard(
    db: Session,
    period: str,
    org_id: int | None,
    days: int,
) -> schemas.TokenUsageDashboard:
    from datetime import datetime, UTC, timedelta

    now = datetime.now(UTC)
    window_start = now - timedelta(days=days)

    query = db.query(models.BillingRecord).filter(
        models.BillingRecord.date >= window_start,
    )
    if org_id is not None:
        query = query.filter(models.BillingRecord.organization_id == org_id)
    records = query.all()

    # Totals
    total_prompt = sum(r.prompt_tokens or 0 for r in records)
    total_completion = sum(r.completion_tokens or 0 for r in records)
    total_cached = sum(r.cached_tokens or 0 for r in records)
    total_cost = round(sum(r.cost_usd or 0 for r in records), 6)
    total_requests = len(records)

    # By day
    daily: dict[str, dict] = {}
    for r in records:
        d = r.date.strftime("%Y-%m-%d") if r.date else "unknown"
        if d not in daily:
            daily[d] = {"date": d, "prompt_tokens": 0, "completion_tokens": 0,
                        "cached_tokens": 0, "cost_usd": 0.0, "request_count": 0}
        daily[d]["prompt_tokens"] += r.prompt_tokens or 0
        daily[d]["completion_tokens"] += r.completion_tokens or 0
        daily[d]["cached_tokens"] += r.cached_tokens or 0
        daily[d]["cost_usd"] = round(daily[d]["cost_usd"] + (r.cost_usd or 0), 6)
        daily[d]["request_count"] += 1
    by_day = [schemas.DailyTokenUsage(**v) for v in sorted(daily.values(), key=lambda x: x["date"])]

    # By model
    by_model_d: dict[str, dict] = {}
    for r in records:
        m = r.model or "unknown"
        if m not in by_model_d:
            by_model_d[m] = {"model": m, "prompt_tokens": 0, "completion_tokens": 0,
                              "cost_usd": 0.0, "request_count": 0}
        by_model_d[m]["prompt_tokens"] += r.prompt_tokens or 0
        by_model_d[m]["completion_tokens"] += r.completion_tokens or 0
        by_model_d[m]["cost_usd"] = round(by_model_d[m]["cost_usd"] + (r.cost_usd or 0), 6)
        by_model_d[m]["request_count"] += 1
    by_model = sorted(by_model_d.values(), key=lambda x: x["cost_usd"], reverse=True)

    # By provider
    by_prov_d: dict[str, dict] = {}
    for r in records:
        p = r.provider or "unknown"
        if p not in by_prov_d:
            by_prov_d[p] = {"provider": p, "prompt_tokens": 0, "completion_tokens": 0,
                             "cost_usd": 0.0, "request_count": 0}
        by_prov_d[p]["prompt_tokens"] += r.prompt_tokens or 0
        by_prov_d[p]["completion_tokens"] += r.completion_tokens or 0
        by_prov_d[p]["cost_usd"] = round(by_prov_d[p]["cost_usd"] + (r.cost_usd or 0), 6)
        by_prov_d[p]["request_count"] += 1
    by_provider = sorted(by_prov_d.values(), key=lambda x: x["cost_usd"], reverse=True)

    # Top 10 most expensive requests (from RequestLog for richer context)
    top_logs = (
        db.query(models.RequestLog)
        .filter(models.RequestLog.cost_amount > 0)
        .order_by(models.RequestLog.cost_amount.desc())
        .limit(10)
        .all()
    )
    top_expensive = [
        {
            "request_id": r.request_id,
            "model": r.requested_model,
            "provider": r.provider_name,
            "cost_usd": r.cost_amount,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
        }
        for r in top_logs
    ]

    # Quota progress per API key
    api_keys = db.query(models.RouterApiKey).filter(
        models.RouterApiKey.status == "active"
    ).all()
    if org_id is not None:
        api_keys = [k for k in api_keys if k.organization_id == org_id]
    quota_progress = []
    for k in api_keys:
        if k.quota_spend_usd or k.quota_requests:
            quota_progress.append({
                "api_key_name": k.name,
                "spend_used": k.spend_usd,
                "spend_limit": k.quota_spend_usd,
                "requests_used": k.request_count,
                "requests_limit": k.quota_requests,
            })

    # Week-over-week cost change
    wow_pct = None
    if days >= 14:
        prev_start = window_start - timedelta(days=days)
        prev_records = db.query(models.BillingRecord).filter(
            models.BillingRecord.date >= prev_start,
            models.BillingRecord.date < window_start,
        ).all()
        if org_id is not None:
            prev_records = [r for r in prev_records if r.organization_id == org_id]
        prev_cost = sum(r.cost_usd or 0 for r in prev_records)
        if prev_cost > 0:
            wow_pct = round((total_cost - prev_cost) / prev_cost * 100, 2)

    return schemas.TokenUsageDashboard(
        period=period,
        organization_id=org_id,
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_cached_tokens=total_cached,
        total_cost_usd=total_cost,
        total_requests=total_requests,
        by_day=by_day,
        by_model=by_model,
        by_provider=by_provider,
        top_expensive_requests=top_expensive,
        quota_progress=quota_progress,
        wow_cost_change_pct=wow_pct,
    )


# ── v1.2.0: Anomaly Threshold Config ──────────────────────────────────────────

def list_anomaly_threshold_configs(db: Session) -> list:
    return db.query(models.AnomalyThresholdConfig).all()


def upsert_anomaly_threshold_config(
    db: Session,
    org_id: int | None,
    payload: schemas.AnomalyThresholdConfigUpdate,
) -> models.AnomalyThresholdConfig:
    cfg = db.query(models.AnomalyThresholdConfig).filter(
        models.AnomalyThresholdConfig.organization_id == org_id
    ).first()
    if cfg is None:
        cfg = models.AnomalyThresholdConfig(
            organization_id=org_id,
            updated_at=datetime.now(UTC),
        )
        db.add(cfg)

    for field, val in payload.model_dump(exclude_none=True).items():
        setattr(cfg, field, val)
    cfg.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(cfg)
    return cfg


# ── v1.2.0: Log Search ────────────────────────────────────────────────────────

def search_request_logs(
    db: Session,
    q: str | None,
    model: str | None,
    provider: str | None,
    from_dt: str | None,
    to_dt: str | None,
    org_id: int | None,
    limit: int,
    offset: int,
) -> dict:
    from datetime import datetime

    query = db.query(models.RequestLog)

    if q:
        like = f"%{q}%"
        query = query.filter(
            (models.RequestLog.request_id.like(like)) |
            (models.RequestLog.api_key_label.like(like)) |
            (models.RequestLog.requested_model.like(like))
        )
    if model:
        query = query.filter(models.RequestLog.requested_model.like(f"%{model}%"))
    if provider:
        query = query.filter(models.RequestLog.provider_name.like(f"%{provider}%"))
    if org_id is not None:
        query = query.filter(models.RequestLog.organization_id == org_id)
    if from_dt:
        try:
            datetime.fromisoformat(from_dt.replace("Z", "+00:00"))
            query = query.filter(models.RequestLog.id >= 0)  # id placeholder; use raw SQL below
        except ValueError:
            pass

    total = query.count()
    rows = query.order_by(models.RequestLog.id.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": r.id,
                "request_id": r.request_id,
                "api_key_label": r.api_key_label,
                "organization_id": r.organization_id,
                "project_id": r.project_id,
                "requested_model": r.requested_model,
                "resolved_model": r.resolved_model,
                "provider_name": r.provider_name,
                "status_code": r.status_code,
                "latency": r.latency,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "cost_amount": r.cost_amount,
                "cache_hit": r.cache_hit,
                "fallback_used": r.fallback_used,
                "error_code": r.error_code,
            }
            for r in rows
        ],
    }


# ── v1.3.0: Provider Quality Scores ───────────────────────────────────────────

_QUALITY_WORKLOAD_CLASSES = [
    "chat_general", "tool_use", "long_context", "structured_output",
    "reasoning", "code", "multimodal",
]


def update_provider_quality_scores(db: Session, lookback_hours: int = 6) -> list[dict]:
    """
    Compute per-(provider, workload_class) quality metrics from recent RequestLog rows
    and upsert into ProviderQualityScore. Called by drift_monitor_job.
    """
    rows = (
        db.query(models.RequestLog)
        .filter(models.RequestLog.id > 0)
        .order_by(models.RequestLog.id.desc())
        .limit(5000)
        .all()
    )

    # Accumulate stats per (provider, workload_class)
    stats: dict[tuple[str, str], dict] = {}
    for row in rows:
        pname = row.provider_name or "unknown"
        wclass = "chat_general"
        if row.route_trace_json:
            try:
                trace = json.loads(row.route_trace_json)
                wclass = trace.get("workload_class", "chat_general")
            except (json.JSONDecodeError, TypeError):
                pass
        key = (pname, wclass)
        if key not in stats:
            stats[key] = {
                "success": 0, "total": 0,
                "schema_valid": 0, "schema_total": 0,
                "tool_ok": 0, "tool_total": 0,
                "latency_sum": 0.0, "cost_sum": 0.0,
            }
        s = stats[key]
        s["total"] += 1
        if row.status_code == 200:
            s["success"] += 1
        if row.healing_strategy:
            # healed response = schema issue; count toward schema validity
            s["schema_total"] += 1
            if not row.response_healed:
                s["schema_valid"] += 1
        if wclass == "tool_use":
            s["tool_total"] += 1
            if row.status_code == 200 and not row.response_healed:
                s["tool_ok"] += 1
        s["latency_sum"] += row.latency or 0.0
        s["cost_sum"] += row.cost_amount or 0.0

    now = datetime.now(UTC)
    updated = []
    for (pname, wclass), s in stats.items():
        if s["total"] == 0:
            continue
        success_rate = s["success"] / s["total"]
        schema_validity_rate = s["schema_valid"] / max(s["schema_total"], 1) if s["schema_total"] else 1.0
        tool_call_success_rate = s["tool_ok"] / max(s["tool_total"], 1) if s["tool_total"] else 1.0
        avg_latency = s["latency_sum"] / s["total"]
        avg_cost = s["cost_sum"] / s["total"]
        # Composite quality: weighted blend of the three signal rates
        quality = (
            0.5 * success_rate
            + 0.3 * schema_validity_rate
            + 0.2 * tool_call_success_rate
        )

        rec = (
            db.query(models.ProviderQualityScore)
            .filter(
                models.ProviderQualityScore.provider_name == pname,
                models.ProviderQualityScore.workload_class == wclass,
            )
            .first()
        )
        if rec is None:
            rec = models.ProviderQualityScore(
                provider_name=pname,
                workload_class=wclass,
                updated_at=now,
            )
            db.add(rec)
        rec.quality_score = round(quality, 4)
        rec.success_rate = round(success_rate, 4)
        rec.schema_validity_rate = round(schema_validity_rate, 4)
        rec.tool_call_success_rate = round(tool_call_success_rate, 4)
        rec.avg_latency_ms = round(avg_latency, 2)
        rec.avg_cost_usd = round(avg_cost, 6)
        rec.sample_count = s["total"]
        rec.updated_at = now
        updated.append({"provider": pname, "workload_class": wclass, "quality": quality, "n": s["total"]})

    db.commit()
    return updated


def list_provider_quality_scores(db: Session) -> list[models.ProviderQualityScore]:
    return (
        db.query(models.ProviderQualityScore)
        .order_by(
            models.ProviderQualityScore.provider_name,
            models.ProviderQualityScore.workload_class,
        )
        .all()
    )


# ── v1.3.0: Drift Monitor & Auto-Recalibration ────────────────────────────────

def _count_new_logs_since_last_recalibration(db: Session) -> int:
    """Return the number of RequestLog rows written since the most recent RecalibrationEvent."""
    last = (
        db.query(models.RecalibrationEvent)
        .order_by(models.RecalibrationEvent.created_at.desc())
        .first()
    )
    if last is None:
        return db.query(models.RequestLog).count()
    return db.query(models.RequestLog).filter(models.RequestLog.id > 0).count()


def _compute_weight_deltas(
    old_weights_json: str,
    new_weights: dict,
) -> dict:
    """Compute per-workload-class, per-dimension absolute weight delta."""
    try:
        old_weights = json.loads(old_weights_json)
    except (json.JSONDecodeError, TypeError):
        return {}
    deltas = {}
    for wclass, new_w in new_weights.items():
        old_w = old_weights.get(wclass, {})
        class_delta = {}
        for dim in ("capability", "latency", "cost"):
            class_delta[dim] = round(
                abs(new_w.get(dim, 0) - old_w.get(dim, 0)), 4
            )
        deltas[wclass] = class_delta
    return deltas


def _max_weight_delta(deltas: dict) -> float:
    """Return the largest single weight dimension delta across all workload classes."""
    return max(
        (d[dim] for class_deltas in deltas.values() for dim in class_deltas for d in [class_deltas]),
        default=0.0,
    )


def run_drift_monitor(db: Session, drift_threshold: float = 0.10) -> schemas.DriftMonitorResult:
    """
    1. Count new RequestLog rows since last recalibration.
    2. If < 500, skip (guard).
    3. Recalibrate from logs.
    4. Compare weight delta to old active profile.
    5. If delta > drift_threshold (default 10%), auto-launch A/B experiment.
    6. Write RecalibrationEvent audit row.
    """
    from datetime import datetime, UTC

    new_logs = _count_new_logs_since_last_recalibration(db)

    if new_logs < 500:
        return schemas.DriftMonitorResult(
            fired=False,
            reason=f"Only {new_logs} new logs (need ≥ 500)",
            new_log_count=new_logs,
        )

    # Snapshot old profile weights before recalibration
    old_profile = _get_active_route_scoring_profile(db)
    old_weights_json = old_profile.weights_json if old_profile else "{}"
    old_profile_name = old_profile.name if old_profile else "default_heuristic_profile"

    # Run recalibration
    recal_request = schemas.RouteScoringRecalibrationRequest(
        profile_name="auto_recalibrated",
        limit=500,
    )
    result = recalibrate_route_scoring_profile_from_logs(db, recal_request)

    # Compute weight deltas
    new_weights = result.weights
    deltas = _compute_weight_deltas(old_weights_json, new_weights)
    max_delta = _max_weight_delta(deltas)

    # Auto-launch experiment if drift > threshold
    experiment_launched = None
    if max_delta >= drift_threshold:
        exp_name = f"auto_exp_{datetime.now(UTC).strftime('%Y%m%d_%H%M')}"
        try:
            # Deactivate any running experiment first
            db.query(models.RouteScoringExperiment).filter(
                models.RouteScoringExperiment.status == "active"
            ).update({models.RouteScoringExperiment.status: "superseded"})
            now = datetime.now(UTC)
            exp = models.RouteScoringExperiment(
                name=exp_name,
                control_profile_name=old_profile_name,
                challenger_profile_name="auto_recalibrated",
                traffic_percentage=10,  # 10% to challenger
                status="active",
                created_at=now,
                updated_at=now,
            )
            db.add(exp)
            db.commit()
            experiment_launched = exp_name
            _record_audit_log(
                db,
                "auto_experiment_launched",
                f"Auto-launched A/B experiment '{exp_name}' (max weight delta={max_delta:.3f})",
            )
        except Exception:
            logger_crud.exception("Failed to auto-launch A/B experiment")

    # Write RecalibrationEvent
    now = datetime.now(UTC)
    event = models.RecalibrationEvent(
        trigger="auto_drift",
        profile_name="auto_recalibrated",
        samples_used=result.source_summary.get("considered_requests", 0),
        weight_delta_json=json.dumps(deltas, ensure_ascii=False),
        experiment_launched=experiment_launched,
        created_at=now,
    )
    db.add(event)
    db.commit()

    return schemas.DriftMonitorResult(
        fired=True,
        reason=f"Drift detected (max delta={max_delta:.3f}, threshold={drift_threshold})",
        new_log_count=new_logs,
        recalibration_triggered=True,
        experiment_launched=experiment_launched,
        weight_deltas=deltas,
    )


def list_recalibration_events(db: Session, limit: int = 50) -> list[models.RecalibrationEvent]:
    return (
        db.query(models.RecalibrationEvent)
        .order_by(models.RecalibrationEvent.created_at.desc())
        .limit(limit)
        .all()
    )


# ── v1.3.0: A/B Significance Check ───────────────────────────────────────────

def _two_proportion_z_test(n1: int, x1: int, n2: int, x2: int) -> float:
    """
    Two-proportion z-test: returns p-value (two-tailed).
    n1/n2 = total observations, x1/x2 = successes.
    Falls back to 1.0 if insufficient data.
    """
    import math
    if n1 < 30 or n2 < 30:
        return 1.0
    p1 = x1 / n1
    p2 = x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    denom = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if denom == 0:
        return 1.0
    z = (p1 - p2) / denom
    # Approximate p-value from |z| using error function
    p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))
    return round(p_value, 6)


def run_ab_significance_check(db: Session) -> schemas.ABSignificanceResult:
    """
    Nightly A/B significance check on the currently active experiment.
    Promotes challenger if p < 0.05 and ran ≥ 7 days.
    Rolls back if challenger is significantly WORSE (p < 0.05 and negative effect).
    """
    from datetime import datetime, UTC

    experiment = _get_active_route_scoring_experiment(db)
    if experiment is None:
        return schemas.ABSignificanceResult(
            experiment_name="",
            status="no_active",
            action="none",
            message="No active A/B experiment",
        )

    # Collect outcomes for control vs challenger buckets from route_trace_json
    rows = (
        db.query(models.RequestLog)
        .filter(models.RequestLog.route_trace_json.isnot(None))
        .order_by(models.RequestLog.id.desc())
        .limit(10000)
        .all()
    )

    control_total = control_success = 0
    challenger_total = challenger_success = 0
    control_cost_sum = challenger_cost_sum = 0.0

    for row in rows:
        try:
            trace = json.loads(row.route_trace_json or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        exp_meta = trace.get("route_scoring_experiment") or {}
        if exp_meta.get("name") != experiment.name:
            continue
        bucket = exp_meta.get("bucket", 0)
        is_success = row.status_code == 200 and not row.fallback_used
        if bucket < experiment.traffic_percentage:
            # Challenger bucket
            challenger_total += 1
            if is_success:
                challenger_success += 1
            challenger_cost_sum += row.cost_amount or 0
        else:
            # Control bucket
            control_total += 1
            if is_success:
                control_success += 1
            control_cost_sum += row.cost_amount or 0

    # Also factor in user feedback scores
    feedback_boost = 0.0
    for row in rows:
        try:
            trace = json.loads(row.route_trace_json or "{}")
            exp_meta = trace.get("route_scoring_experiment") or {}
            if exp_meta.get("name") != experiment.name:
                continue
            feedback = trace.get("user_feedback") or {}
            rating = feedback.get("rating")
            bucket = exp_meta.get("bucket", 0)
            if rating and bucket < experiment.traffic_percentage:
                # Weight feedback 2x vs system signals
                feedback_boost += (rating - 3) * 0.02  # normalize 1–5 → -0.04 to +0.04
        except (json.JSONDecodeError, TypeError):
            continue

    control_rate = control_success / max(control_total, 1)
    challenger_rate = challenger_success / max(challenger_total, 1) + feedback_boost

    p_value = _two_proportion_z_test(
        control_total, control_success,
        challenger_total, challenger_success,
    )

    days_running = (datetime.now(UTC) - experiment.created_at.replace(tzinfo=None if experiment.created_at.tzinfo is None else experiment.created_at.tzinfo)).days

    now = datetime.now(UTC)
    action = "continue"
    status = "inconclusive"
    message = (
        f"Experiment '{experiment.name}': control={control_rate:.3f} ({control_total}), "
        f"challenger={challenger_rate:.3f} ({challenger_total}), p={p_value:.4f}, "
        f"days={days_running}"
    )

    if p_value < 0.05 and days_running >= 7:
        if challenger_rate > control_rate:
            # Promote: activate challenger profile, deactivate experiment
            db.query(models.RouteScoringProfile).update({models.RouteScoringProfile.status: "inactive"})
            challenger = (
                db.query(models.RouteScoringProfile)
                .filter(models.RouteScoringProfile.name == experiment.challenger_profile_name)
                .first()
            )
            if challenger:
                challenger.status = "active"
            experiment.status = "concluded_promoted"
            experiment.updated_at = now
            _record_audit_log(
                db,
                "ab_experiment_promoted",
                f"Promoted challenger '{experiment.challenger_profile_name}' "
                f"(p={p_value:.4f}, Δrate={challenger_rate - control_rate:+.3f})",
            )
            db.commit()
            action = "promote"
            status = "promoted"
            message += " → PROMOTED"
        else:
            # Rollback: challenger is worse
            experiment.status = "concluded_rolled_back"
            experiment.updated_at = now
            db.add(models.NotificationRecord(
                type="ab_experiment_rolled_back",
                message=f"Experiment '{experiment.name}' rolled back — challenger underperformed "
                        f"(Δrate={challenger_rate - control_rate:+.3f}, p={p_value:.4f})",
                timestamp=now,
            ))
            _record_audit_log(
                db,
                "ab_experiment_rolled_back",
                f"Rolled back challenger '{experiment.challenger_profile_name}' "
                f"(p={p_value:.4f}, Δrate={challenger_rate - control_rate:+.3f})",
            )
            db.commit()
            action = "rollback"
            status = "rolled_back"
            message += " → ROLLED BACK"

    return schemas.ABSignificanceResult(
        experiment_name=experiment.name,
        status=status,
        control_success_rate=round(control_rate, 4),
        challenger_success_rate=round(challenger_rate, 4),
        p_value=p_value,
        days_running=days_running,
        action=action,
        message=message,
    )


# ── v1.4.0: Admin User Management ─────────────────────────────────────────────

def seed_superadmin(db: Session) -> None:
    """
    Called on startup. Creates the initial superadmin from env vars if no
    admin users exist yet.
    """
    from .config import settings
    from .services.auth import hash_password

    count = db.query(models.AdminUser).count()
    if count > 0:
        return

    now = datetime.now(UTC)
    user = models.AdminUser(
        username=settings.admin_user,
        email=None,
        password_hash=hash_password(settings.admin_password),
        role="superadmin",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    logger_crud.info("Seeded initial superadmin user '%s'", settings.admin_user)


def authenticate_user(db: Session, username: str, password: str) -> models.AdminUser | None:
    """Return the user if credentials are valid and account is active, else None."""
    from .services.auth import verify_password

    user = db.query(models.AdminUser).filter(
        models.AdminUser.username == username,
        models.AdminUser.is_active == True,  # noqa: E712
    ).first()
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    # Update last_login_at
    user.last_login_at = datetime.now(UTC)
    db.commit()
    return user


def get_admin_user_by_id(db: Session, user_id: int) -> models.AdminUser | None:
    return db.query(models.AdminUser).filter(models.AdminUser.id == user_id).first()


def list_admin_users(db: Session) -> list[models.AdminUser]:
    return db.query(models.AdminUser).order_by(models.AdminUser.id).all()


def create_admin_user(db: Session, payload: schemas.AdminUserCreate) -> models.AdminUser:
    from .services.auth import hash_password

    existing = db.query(models.AdminUser).filter(
        models.AdminUser.username == payload.username
    ).first()
    if existing:
        raise ValueError(f"Username '{payload.username}' already exists")

    if payload.role not in ("superadmin", "admin", "viewer"):
        raise ValueError(f"Invalid role '{payload.role}'. Must be superadmin | admin | viewer")

    now = datetime.now(UTC)
    user = models.AdminUser(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_admin_user(db: Session, user_id: int, payload: schemas.AdminUserUpdate) -> models.AdminUser:
    user = get_admin_user_by_id(db, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found")

    if payload.email is not None:
        user.email = payload.email
    if payload.role is not None:
        if payload.role not in ("superadmin", "admin", "viewer"):
            raise ValueError(f"Invalid role '{payload.role}'")
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.timezone is not None:
        user.timezone = payload.timezone

    user.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def delete_admin_user(db: Session, user_id: int, requesting_user_id: int) -> None:
    if user_id == requesting_user_id:
        raise ValueError("Cannot delete your own account")
    user = get_admin_user_by_id(db, user_id)
    if user is None:
        raise ValueError(f"User {user_id} not found")
    db.delete(user)
    db.commit()


def change_admin_user_password(
    db: Session,
    user_id: int,
    current_password: str,
    new_password: str,
) -> None:
    from .services.auth import hash_password, verify_password

    user = get_admin_user_by_id(db, user_id)
    if user is None:
        raise ValueError("User not found")
    if not verify_password(current_password, user.password_hash):
        raise ValueError("Current password is incorrect")
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.now(UTC)
    db.commit()


def _user_to_schema(user: models.AdminUser) -> schemas.AdminUserItem:
    return schemas.AdminUserItem(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
        updated_at=user.updated_at.isoformat(),
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


# ── v1.5.0: BYOK Management ──────────────────────────────────────────────────

def _make_key_preview(api_key: str) -> str:
    """Return first-8 + '...' + last-4 for safe display."""
    if len(api_key) <= 12:
        return api_key[:4] + "..." + api_key[-2:]
    return api_key[:8] + "..." + api_key[-4:]


def _byok_to_schema(key: models.ByokKey) -> schemas.ByokKeyItem:
    return schemas.ByokKeyItem(
        id=key.id,
        label=key.label,
        provider=key.provider,
        key_preview=key.key_preview,
        org_label=key.org_label,
        project_label=key.project_label,
        is_active=key.is_active,
        description=key.description,
        created_at=key.created_at.isoformat(),
        updated_at=key.updated_at.isoformat(),
        last_used_at=key.last_used_at.isoformat() if key.last_used_at else None,
    )


def list_byok_keys(db: Session) -> list[schemas.ByokKeyItem]:
    keys = db.query(models.ByokKey).order_by(models.ByokKey.created_at.desc()).all()
    return [_byok_to_schema(k) for k in keys]


def create_byok_key(db: Session, payload: schemas.ByokKeyCreate) -> schemas.ByokKeyItem:
    now = datetime.now(UTC)
    key = models.ByokKey(
        label=payload.label,
        provider=payload.provider,
        api_key_encrypted=encrypt_secret(payload.api_key),
        key_preview=_make_key_preview(payload.api_key),
        org_label=payload.org_label,
        project_label=payload.project_label,
        description=payload.description,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    return _byok_to_schema(key)


def update_byok_key(db: Session, key_id: int, payload: schemas.ByokKeyUpdate) -> schemas.ByokKeyItem | None:
    key = db.query(models.ByokKey).filter(models.ByokKey.id == key_id).first()
    if key is None:
        return None
    if payload.label is not None:
        key.label = payload.label
    if payload.is_active is not None:
        key.is_active = payload.is_active
    if payload.description is not None:
        key.description = payload.description
    if payload.org_label is not None:
        key.org_label = payload.org_label
    if payload.project_label is not None:
        key.project_label = payload.project_label
    key.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(key)
    return _byok_to_schema(key)


def delete_byok_key(db: Session, key_id: int) -> bool:
    key = db.query(models.ByokKey).filter(models.ByokKey.id == key_id).first()
    if key is None:
        return False
    db.delete(key)
    db.commit()
    return True


def get_byok_key_secret(db: Session, key_id: int) -> str | None:
    """Return the raw API key for internal routing use only — never expose in API responses."""
    key = db.query(models.ByokKey).filter(
        models.ByokKey.id == key_id,
        models.ByokKey.is_active.is_(True),
    ).first()
    return decrypt_secret(key.api_key_encrypted) if key else None


# ── Image model → provider resolution ────────────────────────────────────────

_IMAGE_MODEL_PROVIDER: dict[str, str] = {
    "gpt-image-2":        "openai",
    "gpt-image-1":        "openai",
    "gpt-image-1-mini":   "openai",
    "dall-e-3":           "openai",
    "dall-e-2":           "openai",
    # Add other providers here as needed, e.g.:
    # "stabilityai/stable-diffusion-3": "stabilityai",
}

_DALLE3_MODELS = {"dall-e-3", "dall-e-2"}


def _resolve_image_provider(model: str) -> str:
    """Map model name to provider name; default to 'openai'."""
    for prefix, provider in _IMAGE_MODEL_PROVIDER.items():
        if model == prefix or model.startswith(prefix):
            return provider
    return "openai"


def _get_byok_key_for_provider(db: Session, provider: str) -> tuple[str | None, str | None]:
    """Return (api_key, base_url) from BYOK table for the given provider."""
    key = db.query(models.ByokKey).filter(
        models.ByokKey.provider == provider,
        models.ByokKey.is_active.is_(True),
    ).order_by(models.ByokKey.id.desc()).first()
    if key is None:
        return None, None
    # base_url stored in org_label field as a convention if set, otherwise None
    base_url = key.org_label if key.org_label and key.org_label.startswith("http") else None
    return decrypt_secret(key.api_key_encrypted), base_url


def create_image_generation(
    db: Session,
    request: schemas.ImageGenerationRequest,
    api_key_label: str | None = None,
) -> schemas.ImageGenerationResponse:
    """
    Proxy an image generation request to the appropriate provider.

    Provider resolution order:
    1. Model name → provider mapping (_IMAGE_MODEL_PROVIDER)
    2. Look up active BYOK key for that provider
    3. Call provider's image generation API and return OpenAI-compatible response
    """
    import time as _time
    from openai import OpenAI

    provider_name = _resolve_image_provider(request.model)
    api_key, base_url = _get_byok_key_for_provider(db, provider_name)

    if not api_key:
        raise ValueError(
            f"NO_BYOK_KEY: No active BYOK key found for provider '{provider_name}'. "
            f"Add one via POST /admin/byok with provider='{provider_name}'."
        )

    client_kwargs: dict = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = OpenAI(**client_kwargs)

    is_dalle = request.model in _DALLE3_MODELS

    generate_kwargs: dict = {
        "model":   request.model,
        "prompt":  request.prompt,
        "n":       request.n or 1,
    }
    if request.size:
        generate_kwargs["size"] = request.size
    if request.quality:
        generate_kwargs["quality"] = request.quality
    if is_dalle and request.style:
        generate_kwargs["style"] = request.style
    if request.response_format:
        generate_kwargs["response_format"] = request.response_format

    resp = client.images.generate(**generate_kwargs)

    images = [
        schemas.ImageData(
            url=getattr(img, "url", None),
            b64_json=getattr(img, "b64_json", None),
            revised_prompt=getattr(img, "revised_prompt", None),
        )
        for img in resp.data
    ]

    # Update BYOK last_used_at
    key_row = db.query(models.ByokKey).filter(
        models.ByokKey.provider == provider_name,
        models.ByokKey.is_active.is_(True),
    ).order_by(models.ByokKey.id.desc()).first()
    if key_row:
        key_row.last_used_at = datetime.now(UTC)
        db.commit()

    return schemas.ImageGenerationResponse(
        created=int(_time.time()),
        data=images,
        model=request.model,
        provider=provider_name,
    )


# ── v1.6.0: Model Stats ───────────────────────────────────────────────────────

def get_model_stats(db: Session, model_name: str, window_days: int = 7) -> dict:
    """
    Return real-time performance stats for a model over the last N days.
    RequestLog has no created_at column; use id-based recency proxy (last 10 000 rows)
    filtered by a cutoff derived from the newest row's approximate age.
    Since we DO have PromptCacheEntry.created_at but not RequestLog.created_at,
    we filter RequestLog by joining nothing — instead we rely on BillingRecord.date
    to back-derive a cutoff id, falling back to a plain id-desc LIMIT when unavailable.
    """
    from datetime import datetime, timedelta, timezone

    cutoff_dt = datetime.now(timezone.utc) - timedelta(days=window_days)

    # BillingRecord has a date column — find the minimum request_id written after
    # the cutoff, then use it as a proxy to find the id boundary in request_logs.
    # Simpler: query BillingRecords for matching model names and collect request_ids,
    # then look those up in RequestLog.
    billing_rows = (
        db.query(models.BillingRecord)
        .filter(
            models.BillingRecord.model == model_name,
            models.BillingRecord.date >= cutoff_dt,
        )
        .all()
    )
    billing_request_ids = {r.request_id for r in billing_rows}

    # Primary query: RequestLog rows whose request_id appears in recent BillingRecords
    # (covers windowed data accurately).  If billing_request_ids is empty we still
    # run the query — it will return 0 rows which triggers the zero-stats path.
    if billing_request_ids:
        rows = (
            db.query(models.RequestLog)
            .filter(
                models.RequestLog.requested_model == model_name,
                models.RequestLog.request_id.in_(billing_request_ids),
            )
            .all()
        )
    else:
        # Fallback: no billing data — use last 500 rows ordered by id desc as recency proxy
        rows = (
            db.query(models.RequestLog)
            .filter(models.RequestLog.requested_model == model_name)
            .order_by(models.RequestLog.id.desc())
            .limit(500)
            .all()
        )

    total = len(rows)
    if total == 0:
        return {
            "model_name": model_name,
            "window_days": window_days,
            "total_requests": 0,
            "success_rate": 0.0,
            "error_rate": 0.0,
            "avg_latency_ms": 0.0,
            "p99_latency_ms": 0.0,
            "fallback_rate": 0.0,
            "avg_cost_usd": 0.0,
            "error_breakdown": {},
            "providers_used": [],
            "computed_at": datetime.utcnow().isoformat(),
        }

    success = sum(1 for r in rows if r.status_code < 400)
    errors = total - success
    latencies = [r.latency * 1000 for r in rows if r.latency is not None]
    costs = [r.cost_amount for r in rows if r.cost_amount is not None]

    def _p99(values: list) -> float:
        if not values:
            return 0.0
        s = sorted(values)
        idx = int(len(s) * 0.99)
        return round(s[min(idx, len(s) - 1)], 2)

    breakdown: dict = {}
    for r in rows:
        if r.status_code >= 400:
            code = r.error_code or ""
            sc_str = str(r.status_code)
            if "rate" in code.lower() or "429" in code or sc_str == "429":
                key = "rate_limit"
            elif "timeout" in code.lower() or "408" in code or sc_str == "408":
                key = "timeout"
            elif sc_str.startswith("5"):
                key = "server_error"
            else:
                key = "other"
            breakdown[key] = breakdown.get(key, 0) + 1

    providers = list({r.provider_name for r in rows if r.provider_name})

    return {
        "model_name": model_name,
        "window_days": window_days,
        "total_requests": total,
        "success_rate": round(success / total, 4),
        "error_rate": round(errors / total, 4),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "p99_latency_ms": _p99(latencies),
        "fallback_rate": round(sum(1 for r in rows if r.fallback_used) / total, 4),
        "avg_cost_usd": round(sum(costs) / len(costs), 6) if costs else 0.0,
        "error_breakdown": breakdown,
        "providers_used": providers,
        "computed_at": datetime.utcnow().isoformat(),
    }
