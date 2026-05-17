from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from . import models, schemas, crud
from .config import get_allowed_router_api_keys
from .db import SessionLocal, engine
from .services.circuit_breaker import circuit_breakers
from .services.scheduler import start_scheduler, stop_scheduler
from .services.auth import (
    create_access_token, create_refresh_token,
    decode_access_token, decode_refresh_token,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    models.Base.metadata.create_all(bind=engine)
    # Seed initial superadmin if no admin users exist
    db = SessionLocal()
    try:
        crud.seed_superadmin(db)
    finally:
        db.close()
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


# ── Admin JWT middleware ────────────────────────────────────────────────────────
# All /admin/* routes require a valid access token.
# /auth/* and /v1/* routes are exempt.

@app.middleware("http")
async def admin_auth_middleware(request: Request, call_next):
    path = request.url.path
    # Let CORS preflight pass through — the real request that follows will be checked
    if request.method == "OPTIONS":
        return await call_next(request)
    if path.startswith("/admin/"):
        auth_header = request.headers.get("authorization", "")
        token = None
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Admin routes require a valid JWT. POST /auth/login to obtain one."},
            )
        payload = decode_access_token(token)
        if payload is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token. POST /auth/login to re-authenticate."},
            )
        # Attach caller info to request state for downstream use
        request.state.admin_user_id = int(payload["sub"])
        request.state.admin_username = payload["username"]
        request.state.admin_role = payload["role"]
    return await call_next(request)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _admin_context(request: Request) -> dict:
    """Extract admin identity set by the middleware. Raises 401 if missing."""
    try:
        return {
            "user_id": request.state.admin_user_id,
            "username": request.state.admin_username,
            "role": request.state.admin_role,
        }
    except AttributeError:
        raise HTTPException(status_code=401, detail="Not authenticated")


def require_superadmin(request: Request) -> dict:
    """Dependency: only superadmin may call this endpoint."""
    ctx = _admin_context(request)
    if ctx["role"] != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin role required")
    return ctx


def require_admin_write(request: Request) -> dict:
    """Dependency: superadmin or admin may call this endpoint (not viewer)."""
    ctx = _admin_context(request)
    if ctx["role"] == "viewer":
        raise HTTPException(status_code=403, detail="Write access requires admin or superadmin role")
    return ctx


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


# ── Auth endpoints (/auth/*) ───────────────────────────────────────────────────

@app.post("/auth/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate with username + password.
    Returns access token (30 min) and refresh token (7 days).
    """
    user = crud.authenticate_user(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    access_token = create_access_token(user.id, user.username, user.role)
    refresh_token = create_refresh_token(user.id, user.username)
    return schemas.TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=user.role,
        username=user.username,
    )


@app.post("/auth/refresh", response_model=schemas.TokenResponse)
def refresh_token(payload: schemas.RefreshRequest, db: Session = Depends(get_db)):
    """Exchange a refresh token for a new access + refresh token pair."""
    data = decode_refresh_token(payload.refresh_token)
    if data is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = crud.get_admin_user_by_id(db, int(data["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or deactivated")
    access_token = create_access_token(user.id, user.username, user.role)
    new_refresh = create_refresh_token(user.id, user.username)
    return schemas.TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        role=user.role,
        username=user.username,
    )


@app.post("/auth/logout")
def logout():
    """
    Stateless logout — client should discard tokens.
    (Token blacklist is a v1.5.0 addition for stricter security.)
    """
    return {"detail": "Logged out. Discard your tokens client-side."}


# ── Admin: current user ────────────────────────────────────────────────────────

@app.get("/admin/users/me", response_model=schemas.AdminUserItem)
def get_me(request: Request, db: Session = Depends(get_db)):
    """Return the currently authenticated admin user's profile."""
    ctx = _admin_context(request)
    user = crud.get_admin_user_by_id(db, ctx["user_id"])
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return crud._user_to_schema(user)


@app.put("/admin/users/me/password")
def change_my_password(
    payload: schemas.PasswordChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Change the currently authenticated user's password."""
    ctx = _admin_context(request)
    try:
        crud.change_admin_user_password(
            db, ctx["user_id"], payload.current_password, payload.new_password
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"detail": "Password updated successfully"}


# ── Admin: user management (superadmin only for create/delete/update) ──────────

@app.get("/admin/users", response_model=list[schemas.AdminUserItem])
def list_users(request: Request, db: Session = Depends(get_db)):
    """List all admin users. Requires admin or superadmin role."""
    _admin_context(request)   # any authenticated admin may list
    return [crud._user_to_schema(u) for u in crud.list_admin_users(db)]


@app.post("/admin/users", response_model=schemas.AdminUserItem, status_code=201)
def create_user(
    payload: schemas.AdminUserCreate,
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_superadmin),
):
    """Create a new admin user. Superadmin only."""
    try:
        user = crud.create_admin_user(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return crud._user_to_schema(user)


@app.put("/admin/users/{user_id}", response_model=schemas.AdminUserItem)
def update_user(
    user_id: int,
    payload: schemas.AdminUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_superadmin),
):
    """Update a user's role, email, or active status. Superadmin only."""
    try:
        user = crud.update_admin_user(db, user_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return crud._user_to_schema(user)


@app.delete("/admin/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _: dict = Depends(require_superadmin),
):
    """Delete an admin user. Superadmin only. Cannot delete yourself."""
    ctx = _admin_context(request)
    try:
        crud.delete_admin_user(db, user_id, ctx["user_id"])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
):
    """Public endpoint — no API key required to browse the model catalog."""
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


# ── v1.3.0: Provider Quality Scores ───────────────────────────────────────────

@app.get("/admin/provider-quality-scores", response_model=list[schemas.ProviderQualityScoreItem])
def list_provider_quality_scores(db: Session = Depends(get_db)):
    """Per-(provider, workload_class) quality metrics computed by the drift monitor."""
    return crud.list_provider_quality_scores(db=db)


@app.post("/admin/provider-quality-scores/refresh", response_model=list[dict])
def refresh_provider_quality_scores(
    lookback_hours: int = 6,
    db: Session = Depends(get_db),
):
    """Manually trigger a provider quality score recomputation from recent logs."""
    return crud.update_provider_quality_scores(db=db, lookback_hours=lookback_hours)


# ── v1.3.0: Drift Monitor ─────────────────────────────────────────────────────

@app.post("/admin/drift-monitor/run", response_model=schemas.DriftMonitorResult)
def run_drift_monitor_now(
    drift_threshold: float = 0.10,
    db: Session = Depends(get_db),
):
    """
    Manually trigger the drift monitor (normally runs every 6h).
    Auto-recalibrates routing weights if ≥ 500 new logs and drift > threshold.
    """
    return crud.run_drift_monitor(db=db, drift_threshold=drift_threshold)


# ── v1.3.0: Recalibration Events ──────────────────────────────────────────────

@app.get("/admin/recalibration-events", response_model=list[schemas.RecalibrationEventItem])
def list_recalibration_events(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Audit trail of automatic and manual recalibration runs."""
    rows = crud.list_recalibration_events(db=db, limit=limit)
    return [
        schemas.RecalibrationEventItem(
            id=r.id,
            trigger=r.trigger,
            profile_name=r.profile_name,
            samples_used=r.samples_used,
            weight_delta_json=r.weight_delta_json,
            experiment_launched=r.experiment_launched,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in rows
    ]


# ── v1.3.0: A/B Significance Check ───────────────────────────────────────────

@app.post("/admin/router-scoring/ab-check", response_model=schemas.ABSignificanceResult)
def run_ab_significance_check(db: Session = Depends(get_db)):
    """
    Manually trigger the A/B significance check (normally runs nightly at 03:00 UTC).
    Promotes or rolls back the active experiment based on two-proportion z-test.
    """
    return crud.run_ab_significance_check(db=db)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
