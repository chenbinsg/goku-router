import {
  createChatCompletion,
  createChatCompletionStream,
  createEmbedding,
  exportBilling,
  listModels,
  listProviderSummaries,
} from './client';
import axios from 'axios';
import type {
  ByokKey,
  Credit,
  Model,
  Notification,
  Organization,
  Project,
  Provider,
  WorkspaceGuardrailConfig,
  WorkspaceRouteDefault,
  BillingRecord,
  ProviderConnectionTestInput,
  ProviderConnectionTestResult,
  RouterApiKey,
  RouteRule,
  RequestLog,
  SecurityLog,
  GuardrailConfig,
  GuardrailPolicyPreset,
  AnalyticsSummary,
  DownloadArtifact,
  PolicyDryRunResult,
  BatchPolicyDryRunResponse,
  GuardrailPolicyCompareResponse,
  RouteScoringProfile,
  RouteReplayResponse,
  RouteReplayRequestPayload,
  RouteScoringExperiment,
  RouteScoringRecalibrationResult,
  RouteScoringTrainResult,
} from '../types';

export { createChatCompletion, createChatCompletionStream, createEmbedding, listModels, listProviderSummaries, exportBilling };

import { getAccessToken, getRefreshToken, setTokens, clearTokens } from '../utils/auth';

const adminClient = axios.create({
  baseURL:
    (window as any).__CONFIG__?.backendUrl
    || import.meta.env.VITE_BACKEND_URL
    || (import.meta.env.DEV
      ? `http://localhost:${import.meta.env.VITE_BACKEND_PORT || '8159'}`
      : ''),
});

// Attach JWT on every /admin request
adminClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers = config.headers ?? {};
    config.headers['Authorization'] = `Bearer ${token}`;
  }
  return config;
});

// Shared in-flight refresh — concurrent 401s wait on the same call instead of
// firing N parallel refreshes (which would consume N refresh tokens, since each
// /auth/refresh rotates the refresh token).
let refreshInFlight: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  if (refreshInFlight) return refreshInFlight;
  const refresh = getRefreshToken();
  if (!refresh) throw new Error('no_refresh_token');
  refreshInFlight = (async () => {
    try {
      // Direct axios (not adminClient) so this call bypasses our 401 interceptor.
      const response = await axios.post(
        `${adminClient.defaults.baseURL}/auth/refresh`,
        { refresh_token: refresh },
      );
      const { access_token, refresh_token, username, role } = response.data;
      setTokens(access_token, refresh_token, username, role);
      return access_token as string;
    } finally {
      refreshInFlight = null;
    }
  })();
  return refreshInFlight;
}

// On 401: try refresh once; if it works, retry the original request transparently.
// If refresh fails (refresh token also expired or absent), clear tokens and redirect.
adminClient.interceptors.response.use(
  (res) => res,
  async (error) => {
    console.log('[adminClient.401-interceptor] hit', {
      status: error?.response?.status,
      url: error?.config?.url,
      isRetry: error?.config?.__isRetry,
      hasRefreshToken: !!getRefreshToken(),
    });
    const original = error?.config as (typeof error.config & { __isRetry?: boolean }) | undefined;
    if (error?.response?.status !== 401 || !original || original.__isRetry) {
      if (error?.response?.status === 401) {
        console.log('[adminClient.401-interceptor] giving up → clearTokens + redirect');
        clearTokens();
        window.location.href = '/login';
      }
      return Promise.reject(error);
    }
    try {
      console.log('[adminClient.401-interceptor] calling refreshAccessToken()');
      const newToken = await refreshAccessToken();
      console.log('[adminClient.401-interceptor] refresh OK, retrying', original.url);
      original.__isRetry = true;
      original.headers = original.headers ?? {};
      (original.headers as Record<string, string>)['Authorization'] = `Bearer ${newToken}`;
      return adminClient.request(original);
    } catch (refreshErr) {
      console.log('[adminClient.401-interceptor] refresh FAILED', refreshErr);
      clearTokens();
      window.location.href = '/login';
      return Promise.reject(error);
    }
  }
);

export const getByokKeys = async (): Promise<ByokKey[]> => [];

export const addByokKey = async (key: ByokKey): Promise<ByokKey> => key;

export const getCredits = async (): Promise<Credit[]> => [];

export const addCredit = async (credit: Credit): Promise<Credit> => credit;

export const getRequestLogs = async (filters?: {
  organizationId?: number;
  projectId?: number;
  environment?: string;
}): Promise<RequestLog[]> => {
  const response = await adminClient.get('/admin/logs', {
    params: {
      organization_id: filters?.organizationId,
      project_id: filters?.projectId,
      environment: filters?.environment,
    },
  });
  // v1.2.0: endpoint returns { total, items, ... } instead of a plain array
  const logs: any[] = Array.isArray(response.data) ? response.data : (response.data.items ?? []);
  return logs.map((log: any) => ({
    requestId: log.request_id,
    apiKeyLabel: log.api_key_label,
    organizationId: log.organization_id,
    projectId: log.project_id,
    environment: log.environment,
    requestedModel: log.requested_model,
    resolvedModel: log.resolved_model,
    providerName: log.provider_name,
    workloadClass: log.workload_class,
    appliedProfileName: log.applied_profile_name,
    experimentName: log.experiment_name,
    experimentVariant: log.experiment_variant,
    stickyKey: log.sticky_key,
    statusCode: log.status_code,
    latency: log.latency,
    fallbackUsed: log.fallback_used,
    routeChanged: log.route_changed,
    cacheHit: log.cache_hit,
    responseHealed: log.response_healed,
    healingStrategy: log.healing_strategy,
    errorCode: log.error_code,
    routeTrace: log.route_trace,
  }));
};

export const getBillingUsage = async (filters?: {
  organizationId?: number;
  projectId?: number;
  environment?: string;
}): Promise<BillingRecord[]> => {
  const response = await adminClient.get('/admin/billing/usage', {
    params: {
      organization_id: filters?.organizationId,
      project_id: filters?.projectId,
      environment: filters?.environment,
    },
  });
  return response.data.items.map((item: any) => ({
    apiKeyLabel: item.api_key_label,
    organizationId: item.organization_id,
    projectId: item.project_id,
    environment: item.environment,
    resolvedModel: item.resolved_model,
    providerName: item.provider_name,
    requestCount: item.request_count,
    promptTokens: item.prompt_tokens,
    completionTokens: item.completion_tokens,
    cachedTokens: item.cached_tokens,
    reasoningTokens: item.reasoning_tokens,
    totalCost: item.total_cost,
    providerReportedCost: item.provider_reported_cost,
  }));
};

export const getOrganizations = async (): Promise<Organization[]> => {
  const response = await adminClient.get('/admin/organizations');
  return response.data.map((item: any) => ({ id: item.id, name: item.name }));
};

export const addOrganization = async (
  organization: Organization,
): Promise<Organization> => {
  const response = await adminClient.post('/admin/organizations', { name: organization.name });
  return { id: response.data.id, name: response.data.name };
};

export const getProjects = async (): Promise<Project[]> => {
  const response = await adminClient.get('/admin/projects');
  return response.data.map((item: any) => ({
    id: item.id,
    name: item.name,
    organizationId: item.organization_id,
    organizationName: item.organization_name,
  }));
};

export const addProject = async (project: Project): Promise<Project> => {
  const response = await adminClient.post('/admin/projects', {
    name: project.name,
    organization_id: Number(project.organizationId),
  });
  return {
    id: response.data.id,
    name: response.data.name,
    organizationId: response.data.organization_id,
    organizationName: response.data.organization_name,
  };
};

export const getWorkspaceRouteDefaults = async (): Promise<WorkspaceRouteDefault[]> => {
  const response = await adminClient.get('/admin/workspace-route-defaults');
  return response.data.map((item: any) => ({
    id: item.id,
    organizationId: item.organization_id,
    organizationName: item.organization_name,
    projectId: item.project_id,
    projectName: item.project_name,
    providerOrder: item.provider_order,
    sortMode: item.sort_mode,
    maxPricePer1k: item.max_price_per_1k,
    requireCapabilities: item.require_capabilities,
    requireParameters: item.require_parameters,
    zdr: item.zdr,
    dataCollection: item.data_collection,
  }));
};

export const addWorkspaceRouteDefault = async (
  payload: WorkspaceRouteDefault,
): Promise<WorkspaceRouteDefault> => {
  const response = await adminClient.post('/admin/workspace-route-defaults', {
    organization_id: payload.organizationId,
    project_id: payload.projectId,
    provider_order: payload.providerOrder,
    sort_mode: payload.sortMode,
    max_price_per_1k: payload.maxPricePer1k,
    require_capabilities: payload.requireCapabilities,
    require_parameters: payload.requireParameters,
    zdr: payload.zdr,
    data_collection: payload.dataCollection,
  });
  return {
    id: response.data.id,
    organizationId: response.data.organization_id,
    organizationName: response.data.organization_name,
    projectId: response.data.project_id,
    projectName: response.data.project_name,
    providerOrder: response.data.provider_order,
    sortMode: response.data.sort_mode,
    maxPricePer1k: response.data.max_price_per_1k,
    requireCapabilities: response.data.require_capabilities,
    requireParameters: response.data.require_parameters,
    zdr: response.data.zdr,
    dataCollection: response.data.data_collection,
  };
};

export const updateWorkspaceRouteDefault = async (
  payload: WorkspaceRouteDefault,
): Promise<WorkspaceRouteDefault> => {
  const response = await adminClient.put(`/admin/workspace-route-defaults/${payload.id}`, {
    organization_id: payload.organizationId,
    project_id: payload.projectId,
    provider_order: payload.providerOrder,
    sort_mode: payload.sortMode,
    max_price_per_1k: payload.maxPricePer1k,
    require_capabilities: payload.requireCapabilities,
    require_parameters: payload.requireParameters,
    zdr: payload.zdr,
    data_collection: payload.dataCollection,
  });
  return {
    id: response.data.id,
    organizationId: response.data.organization_id,
    organizationName: response.data.organization_name,
    projectId: response.data.project_id,
    projectName: response.data.project_name,
    providerOrder: response.data.provider_order,
    sortMode: response.data.sort_mode,
    maxPricePer1k: response.data.max_price_per_1k,
    requireCapabilities: response.data.require_capabilities,
    requireParameters: response.data.require_parameters,
    zdr: response.data.zdr,
    dataCollection: response.data.data_collection,
  };
};

export const getModels = async (): Promise<Model[]> => {
  const response = await adminClient.get('/admin/models');
  return response.data.map((item: any) => ({
    id: item.id,
    modelId: item.model_id,
    providerId: item.provider_id,
    providerName: item.provider_name,
    providerModelName: item.provider_model_name,
    status: item.status,
  }));
};

export const addModel = async (model: Model): Promise<Model> => {
  const response = await adminClient.post('/admin/models', {
    model_id: model.modelId,
    provider_id: Number(model.providerId),
    provider_model_name: model.providerModelName || model.modelId,
    status: model.status || 'active',
  });
  return {
    id: response.data.id,
    modelId: response.data.model_id,
    providerId: response.data.provider_id,
    providerName: response.data.provider_name,
    providerModelName: response.data.provider_model_name,
    status: response.data.status,
  };
};

export const updateModel = async (model: Model): Promise<Model> => {
  const response = await adminClient.put(`/admin/models/${model.id}`, {
    model_id: model.modelId,
    provider_id: Number(model.providerId),
    provider_model_name: model.providerModelName || model.modelId,
    status: model.status || 'active',
  });
  return {
    id: response.data.id,
    modelId: response.data.model_id,
    providerId: response.data.provider_id,
    providerName: response.data.provider_name,
    providerModelName: response.data.provider_model_name,
    status: response.data.status,
  };
};

export const getProviders = async (): Promise<Provider[]> => {
  const response = await adminClient.get('/admin/providers');
  return response.data.map((item: any) => ({
    id: item.id,
    providerName: item.name,
    adapterType: item.adapter_type,
    baseUrl: item.base_url,
    hasApiKey: item.has_api_key,
    status: item.status,
    healthStatus: item.health_status,
    priority: item.priority,
    inputCostPer1k: item.input_cost_per_1k,
    outputCostPer1k: item.output_cost_per_1k,
    avgLatencyMs: item.avg_latency_ms,
    capabilities: item.capabilities,
    supportsZdr: item.supports_zdr,
    dataCollectionMode: item.data_collection_mode,
    maxInputTokens: item.max_input_tokens,
    maxOutputTokens: item.max_output_tokens,
    supportedParameters: item.supported_parameters,
  }));
};

export const addProvider = async (provider: Provider): Promise<Provider> => {
  const response = await adminClient.post('/admin/providers', {
    name: provider.providerName,
    adapter_type: provider.adapterType || 'mock',
    base_url: provider.baseUrl || null,
    ...(provider.apiKey ? { api_key: provider.apiKey } : {}),
    status: provider.status || 'active',
    health_status: provider.healthStatus || 'healthy',
    priority: provider.priority || 100,
    input_cost_per_1k: Number(provider.inputCostPer1k || 0.001),
    output_cost_per_1k: Number(provider.outputCostPer1k || 0.002),
    avg_latency_ms: Number(provider.avgLatencyMs || 500),
    capabilities: provider.capabilities || ['chat'],
    supports_zdr: provider.supportsZdr || false,
    data_collection_mode: provider.dataCollectionMode || 'allow',
    max_input_tokens: Number(provider.maxInputTokens || 4096),
    max_output_tokens: Number(provider.maxOutputTokens || 2048),
    supported_parameters: provider.supportedParameters || ['temperature', 'top_p', 'max_tokens', 'stop', 'tools', 'tool_choice', 'response_format'],
  });
  return {
    id: response.data.id,
    providerName: response.data.name,
    adapterType: response.data.adapter_type,
    baseUrl: response.data.base_url,
    hasApiKey: response.data.has_api_key,
    status: response.data.status,
    healthStatus: response.data.health_status,
    priority: response.data.priority,
    inputCostPer1k: response.data.input_cost_per_1k,
    outputCostPer1k: response.data.output_cost_per_1k,
    avgLatencyMs: response.data.avg_latency_ms,
    capabilities: response.data.capabilities,
    supportsZdr: response.data.supports_zdr,
    dataCollectionMode: response.data.data_collection_mode,
    maxInputTokens: response.data.max_input_tokens,
    maxOutputTokens: response.data.max_output_tokens,
    supportedParameters: response.data.supported_parameters,
  };
};

export const updateProvider = async (provider: Provider): Promise<Provider> => {
  const response = await adminClient.put(`/admin/providers/${provider.id}`, {
    name: provider.providerName,
    adapter_type: provider.adapterType || 'mock',
    base_url: provider.baseUrl || null,
    ...(provider.apiKey ? { api_key: provider.apiKey } : {}),
    status: provider.status || 'active',
    health_status: provider.healthStatus || 'healthy',
    priority: Number(provider.priority || 100),
    input_cost_per_1k: Number(provider.inputCostPer1k || 0.001),
    output_cost_per_1k: Number(provider.outputCostPer1k || 0.002),
    avg_latency_ms: Number(provider.avgLatencyMs || 500),
    capabilities: provider.capabilities || ['chat'],
    supports_zdr: provider.supportsZdr || false,
    data_collection_mode: provider.dataCollectionMode || 'allow',
    max_input_tokens: Number(provider.maxInputTokens || 4096),
    max_output_tokens: Number(provider.maxOutputTokens || 2048),
    supported_parameters: provider.supportedParameters || ['temperature', 'top_p', 'max_tokens', 'stop', 'tools', 'tool_choice', 'response_format'],
  });
  return {
    id: response.data.id,
    providerName: response.data.name,
    adapterType: response.data.adapter_type,
    baseUrl: response.data.base_url,
    hasApiKey: response.data.has_api_key,
    status: response.data.status,
    healthStatus: response.data.health_status,
    priority: response.data.priority,
    inputCostPer1k: response.data.input_cost_per_1k,
    outputCostPer1k: response.data.output_cost_per_1k,
    avgLatencyMs: response.data.avg_latency_ms,
    capabilities: response.data.capabilities,
    supportsZdr: response.data.supports_zdr,
    dataCollectionMode: response.data.data_collection_mode,
    maxInputTokens: response.data.max_input_tokens,
    maxOutputTokens: response.data.max_output_tokens,
    supportedParameters: response.data.supported_parameters,
  };
};

export const deleteProvider = async (providerId: string): Promise<void> => {
  await adminClient.delete(`/admin/providers/${providerId}`);
};

export const testProviderConnection = async (
  payload: ProviderConnectionTestInput,
): Promise<ProviderConnectionTestResult> => {
  const response = await adminClient.post('/admin/providers/test', {
    provider_id: payload.providerId,
    provider_model_name: payload.providerModelName,
    prompt: payload.prompt || 'Connection test from router',
  });
  return {
    success: response.data.success,
    providerName: response.data.provider_name,
    adapterType: response.data.adapter_type,
    completion: response.data.completion,
    promptTokens: response.data.prompt_tokens,
    completionTokens: response.data.completion_tokens,
    message: response.data.message,
  };
};

export const getRouteRules = async (): Promise<RouteRule[]> => {
  const response = await adminClient.get('/admin/routes');
  return response.data.map((item: any) => ({
    id: item.id,
    modelId: item.model_id,
    preferredProviderId: item.preferred_provider_id,
    preferredProviderName: item.preferred_provider_name,
    backupProviderId: item.backup_provider_id,
    backupProviderName: item.backup_provider_name,
    timeoutMs: item.timeout_ms,
  }));
};

export const saveRouteRule = async (routeRule: RouteRule): Promise<RouteRule> => {
  const response = await adminClient.post('/admin/routes', {
    model_id: routeRule.modelId,
    preferred_provider_id: Number(routeRule.preferredProviderId),
    backup_provider_id: routeRule.backupProviderId ? Number(routeRule.backupProviderId) : null,
    timeout_ms: Number(routeRule.timeoutMs),
  });
  return {
    id: response.data.id,
    modelId: response.data.model_id,
    preferredProviderId: response.data.preferred_provider_id,
    preferredProviderName: response.data.preferred_provider_name,
    backupProviderId: response.data.backup_provider_id,
    backupProviderName: response.data.backup_provider_name,
    timeoutMs: response.data.timeout_ms,
  };
};

export const getNotifications = async (): Promise<Notification[]> => {
  const response = await adminClient.get('/admin/notifications');
  return response.data.map((item: any) => ({
    id: item.id,
    type: item.type,
    message: item.message,
    timestamp: item.timestamp,
  }));
};

export const addNotification = async (
  notification: Notification,
): Promise<Notification> => {
  const response = await adminClient.post('/admin/notifications', notification);
  return {
    id: response.data.id,
    type: response.data.type,
    message: response.data.message,
    timestamp: response.data.timestamp,
  };
};

export const detectAnomalyNotifications = async (filters?: {
  organizationId?: number;
  projectId?: number;
}): Promise<Notification[]> => {
  const response = await adminClient.post('/admin/notifications/detect-anomalies', null, {
    params: {
      organization_id: filters?.organizationId,
      project_id: filters?.projectId,
    },
  });
  return response.data.map((item: any) => ({
    id: item.id,
    type: item.type,
    message: item.message,
    timestamp: item.timestamp,
  }));
};

export const getRouterApiKeys = async (): Promise<RouterApiKey[]> => {
  const response = await adminClient.get('/admin/router-api-keys');
  return response.data.map((item: any) => ({
    id: item.id,
    name: item.name,
    keyPrefix: item.key_prefix,
    status: item.status,
    organizationId: item.organization_id,
    projectId: item.project_id,
    environment: item.environment,
    quotaRequests: item.quota_requests,
    requestCount: item.request_count,
    expiresAt: item.expires_at,
    rotatedFromKeyId: item.rotated_from_key_id,
  }));
};

export const createRouterApiKey = async (
  payload: { name: string; organizationId?: number; projectId?: number; environment?: string; quotaRequests?: number; expiresAt?: string },
): Promise<RouterApiKey> => {
  const response = await adminClient.post('/admin/router-api-keys', {
    name: payload.name,
    organization_id: payload.organizationId,
    project_id: payload.projectId,
    environment: payload.environment,
    quota_requests: payload.quotaRequests,
    expires_at: payload.expiresAt,
  });
  return {
    id: response.data.id,
    name: response.data.name,
    keyPrefix: response.data.key_prefix,
    status: response.data.status,
    organizationId: response.data.organization_id,
    projectId: response.data.project_id,
    environment: response.data.environment,
    quotaRequests: response.data.quota_requests,
    requestCount: response.data.request_count,
    expiresAt: response.data.expires_at,
    rotatedFromKeyId: response.data.rotated_from_key_id,
    plainApiKey: response.data.plain_api_key,
  };
};

export const updateRouterApiKey = async (key: RouterApiKey): Promise<RouterApiKey> => {
  const response = await adminClient.put(`/admin/router-api-keys/${key.id}`, {
    name: key.name,
    status: key.status,
    organization_id: key.organizationId,
    project_id: key.projectId,
    environment: key.environment,
    quota_requests: key.quotaRequests,
    expires_at: key.expiresAt,
  });
  return {
    id: response.data.id,
    name: response.data.name,
    keyPrefix: response.data.key_prefix,
    status: response.data.status,
    organizationId: response.data.organization_id,
    projectId: response.data.project_id,
    environment: response.data.environment,
    quotaRequests: response.data.quota_requests,
    requestCount: response.data.request_count,
    expiresAt: response.data.expires_at,
    rotatedFromKeyId: response.data.rotated_from_key_id,
  };
};

export const rotateRouterApiKey = async (
  key: RouterApiKey,
  payload?: { name?: string; quotaRequests?: number; expiresAt?: string },
): Promise<RouterApiKey> => {
  const response = await adminClient.post(`/admin/router-api-keys/${key.id}/rotate`, {
    name: payload?.name,
    quota_requests: payload?.quotaRequests,
    expires_at: payload?.expiresAt,
  });
  return {
    id: response.data.id,
    name: response.data.name,
    keyPrefix: response.data.key_prefix,
    status: response.data.status,
    organizationId: response.data.organization_id,
    projectId: response.data.project_id,
    environment: response.data.environment,
    quotaRequests: response.data.quota_requests,
    requestCount: response.data.request_count,
    expiresAt: response.data.expires_at,
    rotatedFromKeyId: response.data.rotated_from_key_id,
    plainApiKey: response.data.plain_api_key,
  };
};

export const getSecurityLogs = async (): Promise<SecurityLog[]> => {
  const response = await adminClient.get('/admin/audit-logs');
  return response.data.map((item: any) => ({
    id: item.id,
    action: item.action,
    details: item.details,
    timestamp: item.timestamp,
  }));
};

export const getGuardrails = async (): Promise<GuardrailConfig> => {
  const response = await adminClient.get('/admin/guardrails');
  return {
    allowedProviders: response.data.allowed_providers,
    deniedProviders: response.data.denied_providers,
    blockedWords: response.data.blocked_words,
    maxPromptChars: response.data.max_prompt_chars,
    retentionMode: response.data.retention_mode,
  };
};

export const getWorkspaceGuardrails = async (): Promise<WorkspaceGuardrailConfig[]> => {
  const response = await adminClient.get('/admin/workspace-guardrails');
  return response.data.map((item: any) => ({
    id: item.id,
    organizationId: item.organization_id,
    organizationName: item.organization_name,
    projectId: item.project_id,
    projectName: item.project_name,
    allowedProviders: item.allowed_providers || undefined,
    deniedProviders: item.denied_providers || undefined,
    blockedWords: item.blocked_words || undefined,
    maxPromptChars: item.max_prompt_chars,
    retentionMode: item.retention_mode,
  }));
};

export const getGuardrailPolicyPresets = async (): Promise<GuardrailPolicyPreset[]> => {
  const response = await adminClient.get('/admin/guardrail-policy-presets');
  return response.data.map((item: any) => ({
    id: item.id,
    name: item.name,
    description: item.description,
    organizationId: item.organization_id,
    organizationName: item.organization_name,
    projectId: item.project_id,
    projectName: item.project_name,
    allowedProviders: item.allowed_providers || [],
    deniedProviders: item.denied_providers || [],
    blockedWords: item.blocked_words || [],
    maxPromptChars: item.max_prompt_chars,
    retentionMode: item.retention_mode,
  }));
};

export const addGuardrailPolicyPreset = async (
  payload: GuardrailPolicyPreset,
): Promise<GuardrailPolicyPreset> => {
  const response = await adminClient.post('/admin/guardrail-policy-presets', {
    name: payload.name,
    description: payload.description,
    organization_id: payload.organizationId,
    project_id: payload.projectId,
    allowed_providers: payload.allowedProviders,
    denied_providers: payload.deniedProviders,
    blocked_words: payload.blockedWords,
    max_prompt_chars: payload.maxPromptChars,
    retention_mode: payload.retentionMode,
  });
  return {
    id: response.data.id,
    name: response.data.name,
    description: response.data.description,
    organizationId: response.data.organization_id,
    organizationName: response.data.organization_name,
    projectId: response.data.project_id,
    projectName: response.data.project_name,
    allowedProviders: response.data.allowed_providers || [],
    deniedProviders: response.data.denied_providers || [],
    blockedWords: response.data.blocked_words || [],
    maxPromptChars: response.data.max_prompt_chars,
    retentionMode: response.data.retention_mode,
  };
};

export const updateGuardrailPolicyPreset = async (
  payload: GuardrailPolicyPreset,
): Promise<GuardrailPolicyPreset> => {
  const response = await adminClient.put(`/admin/guardrail-policy-presets/${payload.id}`, {
    name: payload.name,
    description: payload.description,
    organization_id: payload.organizationId,
    project_id: payload.projectId,
    allowed_providers: payload.allowedProviders,
    denied_providers: payload.deniedProviders,
    blocked_words: payload.blockedWords,
    max_prompt_chars: payload.maxPromptChars,
    retention_mode: payload.retentionMode,
  });
  return {
    id: response.data.id,
    name: response.data.name,
    description: response.data.description,
    organizationId: response.data.organization_id,
    organizationName: response.data.organization_name,
    projectId: response.data.project_id,
    projectName: response.data.project_name,
    allowedProviders: response.data.allowed_providers || [],
    deniedProviders: response.data.denied_providers || [],
    blockedWords: response.data.blocked_words || [],
    maxPromptChars: response.data.max_prompt_chars,
    retentionMode: response.data.retention_mode,
  };
};

export const addWorkspaceGuardrail = async (
  payload: WorkspaceGuardrailConfig,
): Promise<WorkspaceGuardrailConfig> => {
  const response = await adminClient.post('/admin/workspace-guardrails', {
    organization_id: payload.organizationId,
    project_id: payload.projectId,
    allowed_providers: payload.allowedProviders,
    denied_providers: payload.deniedProviders,
    blocked_words: payload.blockedWords,
    max_prompt_chars: payload.maxPromptChars,
    retention_mode: payload.retentionMode,
  });
  return {
    id: response.data.id,
    organizationId: response.data.organization_id,
    organizationName: response.data.organization_name,
    projectId: response.data.project_id,
    projectName: response.data.project_name,
    allowedProviders: response.data.allowed_providers || undefined,
    deniedProviders: response.data.denied_providers || undefined,
    blockedWords: response.data.blocked_words || undefined,
    maxPromptChars: response.data.max_prompt_chars,
    retentionMode: response.data.retention_mode,
  };
};

export const updateWorkspaceGuardrail = async (
  payload: WorkspaceGuardrailConfig,
): Promise<WorkspaceGuardrailConfig> => {
  const response = await adminClient.put(`/admin/workspace-guardrails/${payload.id}`, {
    organization_id: payload.organizationId,
    project_id: payload.projectId,
    allowed_providers: payload.allowedProviders,
    denied_providers: payload.deniedProviders,
    blocked_words: payload.blockedWords,
    max_prompt_chars: payload.maxPromptChars,
    retention_mode: payload.retentionMode,
  });
  return {
    id: response.data.id,
    organizationId: response.data.organization_id,
    organizationName: response.data.organization_name,
    projectId: response.data.project_id,
    projectName: response.data.project_name,
    allowedProviders: response.data.allowed_providers || undefined,
    deniedProviders: response.data.denied_providers || undefined,
    blockedWords: response.data.blocked_words || undefined,
    maxPromptChars: response.data.max_prompt_chars,
    retentionMode: response.data.retention_mode,
  };
};

export const updateGuardrails = async (guardrails: GuardrailConfig): Promise<GuardrailConfig> => {
  const response = await adminClient.put('/admin/guardrails', {
    allowed_providers: guardrails.allowedProviders,
    denied_providers: guardrails.deniedProviders,
    blocked_words: guardrails.blockedWords,
    max_prompt_chars: guardrails.maxPromptChars,
    retention_mode: guardrails.retentionMode,
  });
  return {
    allowedProviders: response.data.allowed_providers,
    deniedProviders: response.data.denied_providers,
    blockedWords: response.data.blocked_words,
    maxPromptChars: response.data.max_prompt_chars,
    retentionMode: response.data.retention_mode,
  };
};

export const dryRunGuardrails = async (payload: {
  model: string;
  messages: Array<{ role: string; content: any }>;
  responseFormat?: { type: string; jsonSchema?: Record<string, any> };
  tools?: Array<{ type: string; function: Record<string, any> }>;
  guardrails: GuardrailConfig;
}): Promise<PolicyDryRunResult> => {
  const response = await adminClient.post('/admin/guardrails/dry-run', {
    model: payload.model,
    messages: payload.messages,
    response_format: payload.responseFormat
      ? {
          type: payload.responseFormat.type,
          json_schema: payload.responseFormat.jsonSchema,
        }
      : undefined,
    tools: payload.tools,
    guardrails: {
      allowed_providers: payload.guardrails.allowedProviders,
      denied_providers: payload.guardrails.deniedProviders,
      blocked_words: payload.guardrails.blockedWords,
      max_prompt_chars: payload.guardrails.maxPromptChars,
      retention_mode: payload.guardrails.retentionMode,
    },
  });
  return {
    workloadClass: response.data.workload_class,
    blocked: response.data.blocked,
    blockReason: response.data.block_reason,
    selectedProvider: response.data.selected_provider,
    selectedModel: response.data.selected_model,
    acceptedCandidates: response.data.accepted_candidates,
    rejectedCandidates: response.data.rejected_candidates,
    eligibilitySummary: response.data.eligibility_summary || {},
    policyDiff: response.data.policy_diff || {},
    routeTrace: response.data.route_trace,
  };
};

export const dryRunGuardrailsBatch = async (payload: {
  datasetPath: string;
  strategies?: string[];
  workspaceLabel?: string;
  guardrails: GuardrailConfig;
}): Promise<BatchPolicyDryRunResponse> => {
  const response = await adminClient.post('/admin/guardrails/dry-run-batch', {
    dataset_path: payload.datasetPath,
    strategies: payload.strategies || ['current_production_policy'],
    workspace_label: payload.workspaceLabel,
    guardrails: {
      allowed_providers: payload.guardrails.allowedProviders,
      denied_providers: payload.guardrails.deniedProviders,
      blocked_words: payload.guardrails.blockedWords,
      max_prompt_chars: payload.guardrails.maxPromptChars,
      retention_mode: payload.guardrails.retentionMode,
    },
  });
  return {
    datasetName: response.data.dataset_name,
    workspaceLabel: response.data.workspace_label,
    totalCases: response.data.total_cases,
    blockedCases: response.data.blocked_cases,
    successCases: response.data.success_cases,
    strategySummaries: response.data.strategy_summaries || [],
    policyDiffSummary: response.data.policy_diff_summary || {},
    items: response.data.items.map((item: any) => ({
      exampleId: item.example_id,
      workloadClass: item.workload_class,
      strategy: item.strategy,
      blocked: item.blocked,
      blockReason: item.block_reason,
      selectedProvider: item.selected_provider,
      selectedModel: item.selected_model,
      acceptedCandidates: item.accepted_candidates,
      rejectedCandidates: item.rejected_candidates,
    })),
  };
};

export const exportDryRunGuardrailsBatch = async (payload: {
  datasetPath: string;
  strategies?: string[];
  workspaceLabel?: string;
  guardrails: GuardrailConfig;
}): Promise<DownloadArtifact> => {
  const response = await adminClient.post('/admin/guardrails/dry-run-batch/export', {
    dataset_path: payload.datasetPath,
    strategies: payload.strategies || ['current_production_policy'],
    workspace_label: payload.workspaceLabel,
    guardrails: {
      allowed_providers: payload.guardrails.allowedProviders,
      denied_providers: payload.guardrails.deniedProviders,
      blocked_words: payload.guardrails.blockedWords,
      max_prompt_chars: payload.guardrails.maxPromptChars,
      retention_mode: payload.guardrails.retentionMode,
    },
  });
  return {
    fileName: response.data.file_name,
    downloadUrl: response.data.download_url,
  };
};

export const compareGuardrailPolicies = async (payload: {
  datasetPath: string;
  strategies?: string[];
  workspaceLabel?: string;
  baselinePolicyName: string;
  comparisonPolicyName: string;
}): Promise<GuardrailPolicyCompareResponse> => {
  const response = await adminClient.post('/admin/guardrails/preset-compare', {
    dataset_path: payload.datasetPath,
    strategies: payload.strategies || ['current_production_policy'],
    workspace_label: payload.workspaceLabel,
    baseline_policy_name: payload.baselinePolicyName,
    comparison_policy_name: payload.comparisonPolicyName,
  });
  return {
    datasetName: response.data.dataset_name,
    workspaceLabel: response.data.workspace_label,
    baselinePolicyName: response.data.baseline_policy_name,
    comparisonPolicyName: response.data.comparison_policy_name,
    strategySummaries: response.data.strategy_summaries || [],
    comparisonSummary: response.data.comparison_summary || {},
    items: (response.data.items || []).map((item: any) => ({
      exampleId: item.example_id,
      workloadClass: item.workload_class,
      strategy: item.strategy,
      baselineBlocked: item.baseline_blocked,
      comparisonBlocked: item.comparison_blocked,
      baselineProvider: item.baseline_provider,
      comparisonProvider: item.comparison_provider,
      baselineModel: item.baseline_model,
      comparisonModel: item.comparison_model,
      acceptedCandidatesBefore: item.accepted_candidates_before,
      acceptedCandidatesAfter: item.accepted_candidates_after,
      changedProvider: item.changed_provider,
      changedBlock: item.changed_block,
    })),
  };
};

export const exportGuardrailPolicyCompareReport = async (payload: {
  datasetPath: string;
  strategies?: string[];
  workspaceLabel?: string;
  baselinePolicyName: string;
  comparisonPolicyName: string;
}): Promise<DownloadArtifact> => {
  const response = await adminClient.post('/admin/guardrails/preset-compare/export', {
    dataset_path: payload.datasetPath,
    strategies: payload.strategies || ['current_production_policy'],
    workspace_label: payload.workspaceLabel,
    baseline_policy_name: payload.baselinePolicyName,
    comparison_policy_name: payload.comparisonPolicyName,
  });
  return {
    fileName: response.data.file_name,
    downloadUrl: response.data.download_url,
  };
};

export const getRouteScoringProfile = async (): Promise<RouteScoringProfile> => {
  const response = await adminClient.get('/admin/router-scoring/profile');
  return {
    name: response.data.name,
    sourceDataset: response.data.source_dataset,
    status: response.data.status,
    trainedAt: response.data.trained_at,
    weights: response.data.weights,
  };
};

export const trainRouteScoringProfile = async (payload: {
  datasetPath: string;
  profileName?: string;
  baselineStrategy?: string;
}): Promise<RouteScoringTrainResult> => {
  const response = await adminClient.post('/admin/router-scoring/train', {
    dataset_path: payload.datasetPath,
    profile_name: payload.profileName || 'learned_eval_profile',
    baseline_strategy: payload.baselineStrategy || 'current_production_policy',
  });
  return {
    name: response.data.name,
    sourceDataset: response.data.source_dataset,
    status: response.data.status,
    trainedAt: response.data.trained_at,
    weights: response.data.weights,
    workloadWinners: response.data.workload_winners,
    calibrationSummary: response.data.calibration_summary,
  };
};

export const recalibrateRouteScoringProfile = async (payload: {
  profileName?: string;
  limit?: number;
  organizationId?: number;
  projectId?: number;
  experimentName?: string;
}): Promise<RouteScoringRecalibrationResult> => {
  const response = await adminClient.post('/admin/router-scoring/recalibrate', {
    profile_name: payload.profileName || 'learned_feedback_profile',
    limit: payload.limit || 100,
    organization_id: payload.organizationId,
    project_id: payload.projectId,
    experiment_name: payload.experimentName,
  });
  return {
    name: response.data.name,
    sourceDataset: response.data.source_dataset,
    status: response.data.status,
    trainedAt: response.data.trained_at,
    weights: response.data.weights,
    calibrationSummary: response.data.calibration_summary,
    sourceSummary: response.data.source_summary,
  };
};

export const getRouteScoringExperiments = async (): Promise<RouteScoringExperiment[]> => {
  const response = await adminClient.get('/admin/router-scoring/experiments');
  return response.data.map((item: any) => ({
    id: item.id,
    name: item.name,
    controlProfileName: item.control_profile_name,
    challengerProfileName: item.challenger_profile_name,
    trafficPercentage: item.traffic_percentage,
    status: item.status,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
  }));
};

export const addRouteScoringExperiment = async (payload: RouteScoringExperiment): Promise<RouteScoringExperiment> => {
  const response = await adminClient.post('/admin/router-scoring/experiments', {
    name: payload.name,
    control_profile_name: payload.controlProfileName,
    challenger_profile_name: payload.challengerProfileName,
    traffic_percentage: payload.trafficPercentage,
    status: payload.status,
  });
  return {
    id: response.data.id,
    name: response.data.name,
    controlProfileName: response.data.control_profile_name,
    challengerProfileName: response.data.challenger_profile_name,
    trafficPercentage: response.data.traffic_percentage,
    status: response.data.status,
    createdAt: response.data.created_at,
    updatedAt: response.data.updated_at,
  };
};

export const updateRouteScoringExperiment = async (payload: RouteScoringExperiment): Promise<RouteScoringExperiment> => {
  const response = await adminClient.put(`/admin/router-scoring/experiments/${payload.id}`, {
    name: payload.name,
    control_profile_name: payload.controlProfileName,
    challenger_profile_name: payload.challengerProfileName,
    traffic_percentage: payload.trafficPercentage,
    status: payload.status,
  });
  return {
    id: response.data.id,
    name: response.data.name,
    controlProfileName: response.data.control_profile_name,
    challengerProfileName: response.data.challenger_profile_name,
    trafficPercentage: response.data.traffic_percentage,
    status: response.data.status,
    createdAt: response.data.created_at,
    updatedAt: response.data.updated_at,
  };
};

export const replayRouteScoring = async (payload: RouteReplayRequestPayload): Promise<RouteReplayResponse> => {
  const response = await adminClient.post('/admin/router-scoring/replay', {
    source: payload.source,
    dataset_path: payload.datasetPath,
    strategy: payload.strategy || 'current_production_policy',
    limit: payload.limit || 20,
    organization_id: payload.organizationId,
    project_id: payload.projectId,
    baseline_profile_name: payload.baselineProfileName,
    comparison_profile_name: payload.comparisonProfileName,
  });
  return {
    source: response.data.source,
    sourceLabel: response.data.source_label,
    totalCases: response.data.total_cases,
    changedRoutes: response.data.changed_routes,
    unchangedRoutes: response.data.unchanged_routes,
    items: response.data.items.map((item: any) => ({
      requestId: item.request_id,
      exampleId: item.example_id,
      workloadClass: item.workload_class,
      heuristicProvider: item.heuristic_provider,
      learnedProvider: item.learned_provider,
      baselineProfileName: item.baseline_profile_name,
      comparisonProfileName: item.comparison_profile_name,
      baselineProvider: item.baseline_provider,
      comparisonProvider: item.comparison_provider,
      originalProvider: item.original_provider,
      changed: item.changed,
      source: item.source,
    })),
  };
};

export const exportRouteReplayReport = async (payload: RouteReplayRequestPayload): Promise<DownloadArtifact> => {
  const response = await adminClient.post('/admin/router-scoring/replay/export', {
    source: payload.source,
    dataset_path: payload.datasetPath,
    strategy: payload.strategy || 'current_production_policy',
    limit: payload.limit || 20,
    organization_id: payload.organizationId,
    project_id: payload.projectId,
    baseline_profile_name: payload.baselineProfileName,
    comparison_profile_name: payload.comparisonProfileName,
  });
  return {
    fileName: response.data.file_name,
    downloadUrl: response.data.download_url,
  };
};

export const getAnalyticsSummary = async (filters?: {
  organizationId?: number;
  projectId?: number;
  environment?: string;
}): Promise<AnalyticsSummary> => {
  const response = await adminClient.get('/admin/analytics/summary', {
    params: {
      organization_id: filters?.organizationId,
      project_id: filters?.projectId,
      environment: filters?.environment,
    },
  });
  return {
    totalRequests: response.data.total_requests,
    fallbackRate: response.data.fallback_rate,
    blockedRequests: response.data.blocked_requests,
    activeApiKeys: response.data.active_api_keys,
    organizations: response.data.organizations,
    projects: response.data.projects,
    routeScoringProfileName: response.data.route_scoring_profile_name,
    recentRouteChanges: response.data.recent_route_changes,
    recentRouteChangeRate: response.data.recent_route_change_rate,
    recentRouteReplayCases: response.data.recent_route_replay_cases,
    cacheHitRate: response.data.cache_hit_rate,
    cacheHits: response.data.cache_hits,
    stickyRequests: response.data.sticky_requests,
    routeScoringWorkloadShifts: response.data.route_scoring_workload_shifts.map((item: any) => ({
      workloadClass: item.workload_class,
      changedRoutes: item.changed_routes,
      totalRoutes: item.total_routes,
    })),
    providerBreakdown: response.data.provider_breakdown.map((item: any) => ({
      label: item.label,
      requests: item.requests,
      failures: item.failures,
      avgLatency: item.avg_latency,
      totalCost: item.total_cost,
    })),
    modelBreakdown: response.data.model_breakdown.map((item: any) => ({
      label: item.label,
      requests: item.requests,
      failures: item.failures,
      avgLatency: item.avg_latency,
      totalCost: item.total_cost,
    })),
    workspaceUsageSummary: response.data.workspace_usage_summary.map((item: any) => ({
      organizationId: item.organization_id,
      organizationName: item.organization_name,
      projectId: item.project_id,
      projectName: item.project_name,
      environment: item.environment,
      requestCount: item.request_count,
      failureCount: item.failure_count,
      fallbackCount: item.fallback_count,
      cacheHitCount: item.cache_hit_count,
      totalCost: item.total_cost,
      avgLatency: item.avg_latency,
    })),
    costOptimizationOpportunities: (response.data.cost_optimization_opportunities || []).map((item: any) => ({
      category: item.category,
      title: item.title,
      scopeLabel: item.scope_label,
      summary: item.summary,
      estimatedSavings: item.estimated_savings,
      currentCost: item.current_cost,
      targetCost: item.target_cost,
      recommendation: item.recommendation,
    })),
    anomalyAlerts: (response.data.anomaly_alerts || []).map((item: any) => ({
      category: item.category,
      severity: item.severity,
      title: item.title,
      scopeLabel: item.scope_label,
      message: item.message,
      metricValue: item.metric_value,
      threshold: item.threshold,
    })),
    routeScoringDrift: (response.data.route_scoring_drift || []).map((item: any) => ({
      workloadClass: item.workload_class,
      requestCount: item.request_count,
      activeProfileName: item.active_profile_name,
      driftScore: item.drift_score,
      routeChangeRate: item.route_change_rate,
      defaultWeights: item.default_weights,
      activeWeights: item.active_weights,
    })),
    routeScoringExperiments: response.data.route_scoring_experiments || [],
  };
};

export const exportAnalyticsSummary = async (filters?: {
  organizationId?: number;
  projectId?: number;
  environment?: string;
}): Promise<DownloadArtifact> => {
  const response = await adminClient.get('/admin/analytics/export', {
    params: {
      organization_id: filters?.organizationId,
      project_id: filters?.projectId,
      environment: filters?.environment,
    },
  });
  return {
    fileName: response.data.file_name,
    downloadUrl: response.data.download_url,
  };
};

// ── v1.4.0: User Management ────────────────────────────────────────────────────

export interface AdminUser {
  id: number;
  username: string;
  email?: string;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  last_login_at?: string;
}

export const getAdminUsers = async (): Promise<AdminUser[]> => {
  const response = await adminClient.get('/admin/users');
  return response.data;
};

export const createAdminUser = async (payload: {
  username: string;
  password: string;
  email?: string;
  role: string;
}): Promise<AdminUser> => {
  const response = await adminClient.post('/admin/users', payload);
  return response.data;
};

export const updateAdminUser = async (
  id: number,
  payload: { email?: string; role?: string; is_active?: boolean },
): Promise<AdminUser> => {
  const response = await adminClient.put(`/admin/users/${id}`, payload);
  return response.data;
};

export const deleteAdminUser = async (id: number): Promise<void> => {
  await adminClient.delete(`/admin/users/${id}`);
};

export const getMyProfile = async (): Promise<AdminUser> => {
  const response = await adminClient.get('/admin/users/me');
  return response.data;
};

export const updateMyEmail = async (email: string): Promise<AdminUser> => {
  const response = await adminClient.put('/admin/users/me', { email });
  return response.data;
};

export const changeMyPassword = async (payload: {
  current_password: string;
  new_password: string;
}): Promise<void> => {
  await adminClient.put('/admin/users/me/password', payload);
};
