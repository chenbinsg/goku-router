from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from . import models, schemas, crud
from .config import get_allowed_router_api_keys
from .db import SessionLocal, engine
from .services.circuit_breaker import circuit_breakers
from .services.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_api_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    allowed_keys = get_allowed_router_api_keys()
    bearer_token = None
    if authorization and authorization.lower().startswith("bearer "):
        bearer_token = authorization[7:].strip()

    candidate_keys = [value for value in [x_api_key, bearer_token] if value]
    for candidate in candidate_keys:
        if candidate in allowed_keys:
            suffix = candidate[-4:] if len(candidate) >= 4 else candidate
            return {"label": f"key_...{suffix}", "organization_id": None, "project_id": None}
        db_key_context = crud.find_router_api_key_context(db=db, candidate_key=candidate)
        if db_key_context:
            return db_key_context

    raise HTTPException(status_code=401, detail="Invalid or missing API key")

@app.get("/health")
def read_health(db: Session = Depends(get_db)):
    """Health check with DB connectivity and circuit breaker status. (v0.3)"""
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    cb_states = circuit_breakers.get_all_states()
    tripped = [name for name, info in cb_states.items() if info["state"] == "open"]
    return {
        "ok": db_ok,
        "db": "ok" if db_ok else "error",
        "circuit_breakers": cb_states,
        "providers_tripped": tripped,
    }

@app.post("/v1/chat/completions", response_model=schemas.ChatCompletionResponse)
def create_chat_completion(
    request: schemas.ChatCompletionRequest,
    db: Session = Depends(get_db),
    api_key_context: dict = Depends(require_api_key),
):
    # v0.3: Enforce request/spend quotas before routing
    try:
        crud._check_quota(db=db, api_key_label=api_key_context.get("label"))
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    try:
        if request.stream:
            return StreamingResponse(
                crud.stream_chat_completion(
                    db=db,
                    request=request,
                    api_key_label=api_key_context["label"],
                    organization_id=api_key_context.get("organization_id"),
                    project_id=api_key_context.get("project_id"),
                    environment=api_key_context.get("environment"),
                ),
                media_type="text/event-stream",
            )
        return crud.create_chat_completion(
            db=db,
            request=request,
            api_key_label=api_key_context["label"],
            organization_id=api_key_context.get("organization_id"),
            project_id=api_key_context.get("project_id"),
            environment=api_key_context.get("environment"),
        )
    except ValueError as exc:
        detail = str(exc)
        if detail.startswith("INVALID_MODEL"):
            raise HTTPException(status_code=400, detail=detail) from exc
        raise HTTPException(status_code=503, detail=detail) from exc

@app.post("/v1/embeddings", response_model=schemas.EmbeddingResponse)
def create_embedding(
    request: schemas.EmbeddingRequest,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    return crud.create_embedding(db=db, request=request)

@app.get("/v1/models", response_model=schemas.ModelListResponse)
def list_models(
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    return crud.get_models(db=db)

@app.get("/admin/billing/export")
def export_billing(db: Session = Depends(get_db)):
    return crud.export_billing_to_csv(db=db)


@app.get("/admin/billing/usage", response_model=schemas.BillingUsageResponse)
def get_billing_usage(
    organization_id: int | None = None,
    project_id: int | None = None,
    environment: str | None = None,
    db: Session = Depends(get_db),
):
    return crud.get_billing_usage(db=db, organization_id=organization_id, project_id=project_id, environment=environment)


@app.get("/admin/providers", response_model=list[schemas.ProviderItem])
def list_providers(db: Session = Depends(get_db)):
    return crud.list_providers(db=db)


@app.post("/admin/providers", response_model=schemas.ProviderItem)
def create_provider(provider: schemas.ProviderCreate, db: Session = Depends(get_db)):
    return crud.create_provider(db=db, provider=provider)


@app.put("/admin/providers/{provider_id}", response_model=schemas.ProviderItem)
def update_provider(provider_id: int, provider: schemas.ProviderCreate, db: Session = Depends(get_db)):
    try:
        return crud.update_provider(db=db, provider_id=provider_id, provider=provider)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/admin/providers/{provider_id}", status_code=204)
def delete_provider(provider_id: int, db: Session = Depends(get_db)):
    try:
        crud.delete_provider(db=db, provider_id=provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/admin/providers/test", response_model=schemas.ProviderConnectionTestResult)
def test_provider_connection(
    request: schemas.ProviderConnectionTestRequest,
    db: Session = Depends(get_db),
):
    try:
        return crud.test_provider_connection(db=db, request=request)
    except ValueError as exc:
        detail = str(exc)
        if detail.startswith("INVALID_PROVIDER"):
            raise HTTPException(status_code=404, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc


@app.get("/admin/models", response_model=list[schemas.ModelCatalogItem])
def list_model_catalog(db: Session = Depends(get_db)):
    return crud.list_model_catalog(db=db)


@app.post("/admin/models", response_model=schemas.ModelCatalogItem)
def create_model_catalog_item(model: schemas.ModelCatalogCreate, db: Session = Depends(get_db)):
    return crud.create_model_catalog_item(db=db, model=model)


@app.put("/admin/models/{model_id}", response_model=schemas.ModelCatalogItem)
def update_model_catalog_item(model_id: int, model: schemas.ModelCatalogCreate, db: Session = Depends(get_db)):
    try:
        return crud.update_model_catalog_item(db=db, model_id=model_id, model=model)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/admin/routes", response_model=list[schemas.RouteRuleItem])
def list_route_rules(db: Session = Depends(get_db)):
    return crud.list_route_rules(db=db)


@app.post("/admin/routes", response_model=schemas.RouteRuleItem)
def upsert_route_rule(route_rule: schemas.RouteRuleCreate, db: Session = Depends(get_db)):
    return crud.upsert_route_rule(db=db, route_rule=route_rule)


@app.get("/admin/logs", response_model=list[schemas.RequestLogItem])
def list_request_logs(
    organization_id: int | None = None,
    project_id: int | None = None,
    environment: str | None = None,
    db: Session = Depends(get_db),
):
    return crud.list_request_logs(db=db, organization_id=organization_id, project_id=project_id, environment=environment)


@app.get("/admin/router-api-keys", response_model=list[schemas.RouterApiKeyItem])
def list_router_api_keys(db: Session = Depends(get_db)):
    return crud.list_router_api_keys(db=db)


@app.post("/admin/router-api-keys", response_model=schemas.RouterApiKeyCreateResult)
def create_router_api_key(api_key: schemas.RouterApiKeyCreate, db: Session = Depends(get_db)):
    return crud.create_router_api_key(db=db, api_key=api_key)


@app.put("/admin/router-api-keys/{key_id}", response_model=schemas.RouterApiKeyItem)
def update_router_api_key(key_id: int, update: schemas.RouterApiKeyUpdate, db: Session = Depends(get_db)):
    try:
        return crud.update_router_api_key(db=db, key_id=key_id, update=update)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/admin/router-api-keys/{key_id}/rotate", response_model=schemas.RouterApiKeyCreateResult)
def rotate_router_api_key(key_id: int, payload: schemas.RouterApiKeyRotateRequest, db: Session = Depends(get_db)):
    try:
        return crud.rotate_router_api_key(db=db, key_id=key_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/admin/organizations", response_model=list[schemas.OrganizationItem])
def list_organizations(db: Session = Depends(get_db)):
    return crud.list_organizations(db=db)


@app.post("/admin/organizations", response_model=schemas.OrganizationItem)
def create_organization(organization: schemas.OrganizationCreate, db: Session = Depends(get_db)):
    return crud.create_organization(db=db, organization=organization)


@app.get("/admin/projects", response_model=list[schemas.ProjectItem])
def list_projects(db: Session = Depends(get_db)):
    return crud.list_projects(db=db)


@app.post("/admin/projects", response_model=schemas.ProjectItem)
def create_project(project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    return crud.create_project(db=db, project=project)


@app.get("/admin/workspace-route-defaults", response_model=list[schemas.WorkspaceRouteDefaultItem])
def list_workspace_route_defaults(db: Session = Depends(get_db)):
    return crud.list_workspace_route_defaults(db=db)


@app.post("/admin/workspace-route-defaults", response_model=schemas.WorkspaceRouteDefaultItem)
def create_workspace_route_default(payload: schemas.WorkspaceRouteDefaultCreate, db: Session = Depends(get_db)):
    return crud.create_workspace_route_default(db=db, payload=payload)


@app.put("/admin/workspace-route-defaults/{default_id}", response_model=schemas.WorkspaceRouteDefaultItem)
def update_workspace_route_default(default_id: int, payload: schemas.WorkspaceRouteDefaultCreate, db: Session = Depends(get_db)):
    try:
        return crud.update_workspace_route_default(db=db, default_id=default_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/admin/guardrails", response_model=schemas.GuardrailConfigItem)
def get_guardrails(db: Session = Depends(get_db)):
    return crud.get_guardrail_config(db=db)


@app.get("/admin/workspace-guardrails", response_model=list[schemas.WorkspaceGuardrailConfigItem])
def list_workspace_guardrails(db: Session = Depends(get_db)):
    return crud.list_workspace_guardrail_configs(db=db)


@app.get("/admin/guardrail-policy-presets", response_model=list[schemas.GuardrailPolicyPresetItem])
def list_guardrail_policy_presets(db: Session = Depends(get_db)):
    return crud.list_guardrail_policy_presets(db=db)


@app.post("/admin/guardrail-policy-presets", response_model=schemas.GuardrailPolicyPresetItem)
def create_guardrail_policy_preset(payload: schemas.GuardrailPolicyPresetCreate, db: Session = Depends(get_db)):
    return crud.create_guardrail_policy_preset(db=db, payload=payload)


@app.put("/admin/guardrail-policy-presets/{preset_id}", response_model=schemas.GuardrailPolicyPresetItem)
def update_guardrail_policy_preset(
    preset_id: int,
    payload: schemas.GuardrailPolicyPresetCreate,
    db: Session = Depends(get_db),
):
    try:
        return crud.update_guardrail_policy_preset(db=db, preset_id=preset_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/admin/workspace-guardrails", response_model=schemas.WorkspaceGuardrailConfigItem)
def create_workspace_guardrail(payload: schemas.WorkspaceGuardrailConfigCreate, db: Session = Depends(get_db)):
    return crud.create_workspace_guardrail_config(db=db, payload=payload)


@app.put("/admin/workspace-guardrails/{config_id}", response_model=schemas.WorkspaceGuardrailConfigItem)
def update_workspace_guardrail(
    config_id: int,
    payload: schemas.WorkspaceGuardrailConfigCreate,
    db: Session = Depends(get_db),
):
    try:
        return crud.update_workspace_guardrail_config(db=db, config_id=config_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/admin/guardrails", response_model=schemas.GuardrailConfigItem)
def update_guardrails(update: schemas.GuardrailConfigUpdate, db: Session = Depends(get_db)):
    return crud.update_guardrail_config(db=db, update=update)


@app.post("/admin/guardrails/dry-run", response_model=schemas.PolicyDryRunResult)
def dry_run_guardrails(request: schemas.PolicyDryRunRequest, db: Session = Depends(get_db)):
    return crud.run_policy_dry_run(db=db, request=request)


@app.post("/admin/guardrails/dry-run-batch", response_model=schemas.BatchPolicyDryRunResponse)
def dry_run_guardrails_batch(request: schemas.BatchPolicyDryRunRequest, db: Session = Depends(get_db)):
    return crud.run_batch_policy_dry_run(db=db, request=request)


@app.post("/admin/guardrails/dry-run-batch/export", response_model=schemas.DownloadArtifactResponse)
def export_dry_run_guardrails_batch(request: schemas.BatchPolicyDryRunRequest, db: Session = Depends(get_db)):
    return crud.export_batch_policy_dry_run_report(db=db, request=request)


@app.post("/admin/guardrails/preset-compare", response_model=schemas.GuardrailPolicyCompareResponse)
def compare_guardrail_policy_presets(request: schemas.GuardrailPolicyCompareRequest, db: Session = Depends(get_db)):
    return crud.compare_guardrail_policy_presets(db=db, request=request)


@app.post("/admin/guardrails/preset-compare/export", response_model=schemas.DownloadArtifactResponse)
def export_guardrail_policy_compare(request: schemas.GuardrailPolicyCompareRequest, db: Session = Depends(get_db)):
    return crud.export_guardrail_policy_compare_report(db=db, request=request)


@app.get("/admin/router-scoring/profile", response_model=schemas.RouteScoringProfileItem)
def get_route_scoring_profile(db: Session = Depends(get_db)):
    return crud.get_route_scoring_profile(db=db)


@app.post("/admin/router-scoring/train", response_model=schemas.RouteScoringTrainResult)
def train_route_scoring_profile(request: schemas.RouteScoringTrainRequest, db: Session = Depends(get_db)):
    return crud.train_route_scoring_profile(db=db, request=request)


@app.post("/admin/router-scoring/recalibrate", response_model=schemas.RouteScoringRecalibrationResult)
def recalibrate_route_scoring_profile(
    request: schemas.RouteScoringRecalibrationRequest,
    db: Session = Depends(get_db),
):
    return crud.recalibrate_route_scoring_profile_from_logs(db=db, request=request)


@app.get("/admin/router-scoring/experiments", response_model=list[schemas.RouteScoringExperimentItem])
def list_route_scoring_experiments(db: Session = Depends(get_db)):
    return crud.list_route_scoring_experiments(db=db)


@app.post("/admin/router-scoring/experiments", response_model=schemas.RouteScoringExperimentItem)
def create_route_scoring_experiment(
    payload: schemas.RouteScoringExperimentCreate,
    db: Session = Depends(get_db),
):
    return crud.create_route_scoring_experiment(db=db, payload=payload)


@app.put("/admin/router-scoring/experiments/{experiment_id}", response_model=schemas.RouteScoringExperimentItem)
def update_route_scoring_experiment(
    experiment_id: int,
    payload: schemas.RouteScoringExperimentCreate,
    db: Session = Depends(get_db),
):
    try:
        return crud.update_route_scoring_experiment(db=db, experiment_id=experiment_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/admin/router-scoring/replay", response_model=schemas.RouteReplayResponse)
def replay_route_scoring(request: schemas.RouteReplayRequest, db: Session = Depends(get_db)):
    return crud.replay_route_scoring(db=db, request=request)


@app.post("/admin/router-scoring/replay/export", response_model=schemas.DownloadArtifactResponse)
def export_route_scoring_replay(request: schemas.RouteReplayRequest, db: Session = Depends(get_db)):
    return crud.export_route_scoring_replay_report(db=db, request=request)


@app.get("/admin/audit-logs", response_model=list[schemas.AuditLogItem])
def list_audit_logs(db: Session = Depends(get_db)):
    return crud.list_audit_logs(db=db)


@app.get("/admin/notifications", response_model=list[schemas.NotificationItem])
def list_notifications(db: Session = Depends(get_db)):
    return crud.list_notifications(db=db)


@app.post("/admin/notifications", response_model=schemas.NotificationItem)
def create_notification(notification: schemas.NotificationCreate, db: Session = Depends(get_db)):
    return crud.create_notification(db=db, notification=notification)


@app.post("/admin/notifications/detect-anomalies", response_model=list[schemas.NotificationItem])
def detect_anomaly_notifications(
    organization_id: int | None = None,
    project_id: int | None = None,
    db: Session = Depends(get_db),
):
    return crud.detect_notification_anomalies(
        db=db,
        organization_id=organization_id,
        project_id=project_id,
    )


@app.get("/admin/analytics/summary", response_model=schemas.AnalyticsSummary)
def get_analytics_summary(
    organization_id: int | None = None,
    project_id: int | None = None,
    environment: str | None = None,
    db: Session = Depends(get_db),
):
    return crud.get_analytics_summary(db=db, organization_id=organization_id, project_id=project_id, environment=environment)


@app.get("/admin/analytics/export", response_model=schemas.DownloadArtifactResponse)
def export_analytics_summary(
    organization_id: int | None = None,
    project_id: int | None = None,
    environment: str | None = None,
    db: Session = Depends(get_db),
):
    return crud.export_analytics_report(db=db, organization_id=organization_id, project_id=project_id, environment=environment)

# ── Circuit breaker admin endpoints (v0.4) ────────────────────────────────────

@app.get("/admin/circuit-breakers")
def list_circuit_breaker_states():
    """Return current circuit breaker state for all providers."""
    return circuit_breakers.get_all_states()


@app.post("/admin/circuit-breakers/{provider_name}/reset")
def reset_circuit_breaker(provider_name: str):
    """Manually reset a tripped circuit breaker."""
    circuit_breakers.reset(provider_name)
    return {"provider": provider_name, "state": "closed", "reset": True}


# ── Feedback endpoint (v0.7 foundation) ──────────────────────────────────────

@app.post("/v1/feedback")
def submit_feedback(
    payload: schemas.FeedbackRequest,
    db: Session = Depends(get_db),
    _: dict = Depends(require_api_key),
):
    """
    Accept quality feedback for a completed request.
    Stored on RequestLog.user_feedback_score for use in route scoring recalibration.
    """
    try:
        return crud.record_request_feedback(db=db, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ── v1.2.0: Billing Invoice ───────────────────────────────────────────────────

@app.get("/admin/billing/invoice", response_model=schemas.BillingInvoiceResponse)
def get_billing_invoice(
    org_id: int | None = None,
    month: str | None = None,   # "2026-05" — defaults to current month
    db: Session = Depends(get_db),
):
    """
    Return a billing invoice for an org for a given month.
    Falls back to live BillingRecord aggregation when the monthly rollup job hasn't
    run yet (e.g. mid-month queries).
    """
    return crud.get_billing_invoice(db=db, org_id=org_id, month=month)


@app.get("/admin/billing/invoice/export")
def export_billing_invoice_csv(
    org_id: int | None = None,
    month: str | None = None,
    db: Session = Depends(get_db),
):
    """Download the billing invoice as a CSV file."""
    import csv, io
    invoice = crud.get_billing_invoice(db=db, org_id=org_id, month=month)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[
        "project_id", "api_key_name", "model", "provider",
        "request_count", "prompt_tokens", "completion_tokens", "cached_tokens",
        "cost_usd", "upstream_cost_usd",
    ])
    writer.writeheader()
    for item in invoice.items:
        writer.writerow(item.model_dump())
    content = buf.getvalue()
    filename = f"invoice_{invoice.year_month}{'_org' + str(org_id) if org_id else ''}.csv"
    from fastapi.responses import Response
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── v1.2.0: Token Usage Dashboard ─────────────────────────────────────────────

@app.get("/admin/analytics/token-usage", response_model=schemas.TokenUsageDashboard)
def get_token_usage_dashboard(
    period: str = "daily",          # "daily" | "weekly" | "monthly"
    org_id: int | None = None,
    days: int = 7,
    db: Session = Depends(get_db),
):
    """
    Token usage dashboard: daily burn by model/provider/org, quota progress,
    week-over-week cost change, top-10 most expensive requests.
    """
    return crud.get_token_usage_dashboard(db=db, period=period, org_id=org_id, days=days)


# ── v1.2.0: Anomaly Threshold Config ──────────────────────────────────────────

@app.get("/admin/anomaly-thresholds", response_model=list[schemas.AnomalyThresholdConfigItem])
def list_anomaly_thresholds(db: Session = Depends(get_db)):
    """List all anomaly threshold configs (global + per-org overrides)."""
    return crud.list_anomaly_threshold_configs(db=db)


@app.put("/admin/anomaly-thresholds", response_model=schemas.AnomalyThresholdConfigItem)
def upsert_anomaly_threshold(
    payload: schemas.AnomalyThresholdConfigUpdate,
    org_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Create or update anomaly thresholds for the global config (org_id=None) or a specific org."""
    return crud.upsert_anomaly_threshold_config(db=db, org_id=org_id, payload=payload)


# ── v1.2.0: Log Search & Retention ────────────────────────────────────────────

@app.get("/admin/logs")
def search_logs(
    q: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    from_dt: str | None = None,   # ISO-8601 or "2026-05-01"
    to_dt: str | None = None,
    org_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """
    Search request logs. Supports free-text search on request_id/api_key_label,
    filter by model/provider/org and time window.
    """
    return crud.search_request_logs(
        db=db, q=q, model=model, provider=provider,
        from_dt=from_dt, to_dt=to_dt, org_id=org_id,
        limit=limit, offset=offset,
    )


@app.post("/admin/logs/enforce-retention", response_model=schemas.LogRetentionResult)
def enforce_retention_now(db: Session = Depends(get_db)):
    """Trigger log retention enforcement immediately (normally runs daily at 02:00 UTC)."""
    from .services.scheduler import enforce_log_retention
    enforce_log_retention()
    return schemas.LogRetentionResult(deleted_rows=0, retention_days=int(os.getenv("LOG_RETENTION_DAYS", "90")))


# ── v1.2.0: Monthly Billing Summaries ─────────────────────────────────────────

@app.get("/admin/billing/summaries")
def list_monthly_billing_summaries(
    org_id: int | None = None,
    year_month: str | None = None,
    db: Session = Depends(get_db),
):
    """List pre-rolled monthly billing summaries."""
    query = db.query(models.MonthlyBillingSummary)
    if org_id is not None:
        query = query.filter(models.MonthlyBillingSummary.organization_id == org_id)
    if year_month:
        query = query.filter(models.MonthlyBillingSummary.year_month == year_month)
    rows = query.order_by(models.MonthlyBillingSummary.year_month.desc()).limit(200).all()
    return [
        {
            "id": r.id, "year_month": r.year_month,
            "organization_id": r.organization_id, "project_id": r.project_id,
            "model": r.model, "provider": r.provider,
            "request_count": r.request_count,
            "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
            "cached_tokens": r.cached_tokens,
            "cost_usd": r.cost_usd, "upstream_cost_usd": r.upstream_cost_usd,
            "rolled_up_at": r.rolled_up_at.isoformat() if r.rolled_up_at else None,
        }
        for r in rows
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
