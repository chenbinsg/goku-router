from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from . import models, schemas, crud
from .config import get_allowed_router_api_keys
from .db import SessionLocal, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    yield


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
def read_health():
    return {"ok": True}

@app.post("/v1/chat/completions", response_model=schemas.ChatCompletionResponse)
def create_chat_completion(
    request: schemas.ChatCompletionRequest,
    db: Session = Depends(get_db),
    api_key_context: dict = Depends(require_api_key),
):
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
