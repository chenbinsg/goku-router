export interface ChatMessage {
  role: string;
  content: any;
}

export interface ChatCompletionRequest {
  model: string;
  messages: ChatMessage[];
  stream?: boolean;
  temperature?: number;
  topP?: number;
  maxTokens?: number;
  stop?: string[] | string;
  tools?: Array<{ type: string; function: Record<string, any> }>;
  toolChoice?: any;
  responseFormat?: { type: string; jsonSchema?: Record<string, any> };
  provider?: {
    order?: string[];
    allowFallbacks?: boolean;
    sort?: string;
    maxPricePer1k?: number;
    requireCapabilities?: string[];
    requireParameters?: boolean;
    zdr?: boolean;
    dataCollection?: string;
    organization?: string;
    project?: string;
    stickyKey?: string;
  };
}

export interface ChatCompletionResponse {
  completion: string;
  provider: string;
  fallback_used: boolean;
  request_id: string;
  cache_hit?: boolean;
  response_healed?: boolean;
  healing_strategy?: string;
  selected_model?: string;
  structured_output?: any;
  tool_calls?: Array<Record<string, any>>;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cached_tokens?: number;
    reasoning_tokens?: number;
    provider_reported_cost?: number;
  };
}

export interface EmbeddingRequest {
  text: string;
}

export interface EmbeddingResponse {
  embedding: number[];
}

export interface ModelListResponse {
  models: string[];
}

export interface BillingExportResponse {
  csv_url: string;
}

export interface ByokKey {
  keyId: string;
  organization: string;
  project: string;
}

export interface Credit {
  creditId: string;
  amount: number;
  organization: string;
}

export interface BillingRecord {
  apiKeyLabel: string;
  organizationId?: number;
  projectId?: number;
  environment?: string;
  resolvedModel?: string;
  providerName?: string;
  requestCount: number;
  promptTokens: number;
  completionTokens: number;
  cachedTokens: number;
  reasoningTokens: number;
  totalCost: number;
  providerReportedCost: number;
}

export interface SecurityLog {
  id: number;
  logId?: string;
  action: string;
  details?: string;
  timestamp: string;
}

export interface RequestLog {
  requestId: string;
  apiKeyLabel?: string;
  organizationId?: number;
  projectId?: number;
  environment?: string;
  requestedModel?: string;
  resolvedModel?: string;
  providerName?: string;
  workloadClass?: string;
  appliedProfileName?: string;
  experimentName?: string;
  experimentVariant?: string;
  stickyKey?: string;
  statusCode: number;
  latency: number;
  fallbackUsed?: boolean;
  routeChanged?: boolean;
  cacheHit?: boolean;
  responseHealed?: boolean;
  healingStrategy?: string;
  errorCode?: string;
  routeTrace?: Record<string, any>;
}

export interface Organization {
  id?: number;
  name: string;
}

export interface Project {
  id?: number;
  name: string;
  organizationId: number;
  organizationName?: string;
}

export interface WorkspaceRouteDefault {
  id?: number;
  organizationId?: number;
  organizationName?: string;
  projectId?: number;
  projectName?: string;
  providerOrder: string[];
  sortMode: string;
  maxPricePer1k?: number;
  requireCapabilities: string[];
  requireParameters: boolean;
  zdr?: boolean;
  dataCollection?: string;
}

export interface WorkspaceGuardrailConfig {
  id?: number;
  organizationId?: number;
  organizationName?: string;
  projectId?: number;
  projectName?: string;
  allowedProviders?: string[];
  deniedProviders?: string[];
  blockedWords?: string[];
  maxPromptChars?: number;
  retentionMode?: string;
}

export interface Model {
  modelId: string;
  id?: number;
  providerId?: number;
  providerName?: string;
  providerModelName?: string;
  status?: string;
}

export interface Provider {
  id?: number;
  providerName: string;
  adapterType?: string;
  status?: string;
  healthStatus?: string;
  priority?: number;
  inputCostPer1k?: number;
  outputCostPer1k?: number;
  avgLatencyMs?: number;
  capabilities?: string[];
  supportsZdr?: boolean;
  dataCollectionMode?: string;
  maxInputTokens?: number;
  maxOutputTokens?: number;
  supportedParameters?: string[];
}

export interface ProviderConnectionTestInput {
  providerId: number;
  providerModelName: string;
  prompt?: string;
}

export interface ProviderConnectionTestResult {
  success: boolean;
  providerName: string;
  adapterType: string;
  completion: string;
  promptTokens: number;
  completionTokens: number;
  message: string;
}

export interface QualityEvalCase {
  caseId: string;
  prompt: string;
  systemPrompt?: string;
  expectedContains?: string[];
  mustNotContain?: string[];
  requireJson?: boolean;
  tools?: Array<{ type: string; function: Record<string, any> }>;
  responseFormat?: { type: string; jsonSchema?: Record<string, any> };
  maxLatencyMs?: number;
  maxCostUsd?: number;
  weight?: number;
}

export interface QualityEvalRequestPayload {
  name: string;
  modelId: string;
  providerId?: number;
  temperature?: number;
  maxTokens?: number;
  cases: QualityEvalCase[];
}

export interface QualityEvalCaseResult {
  caseId: string;
  success: boolean;
  score: number;
  providerName: string;
  modelId: string;
  providerModelName: string;
  completion: string;
  matchedTerms: string[];
  missingTerms: string[];
  forbiddenHits: string[];
  jsonValid?: boolean;
  toolSuccess?: boolean;
  latencyMs: number;
  costUsd: number;
  promptTokens: number;
  completionTokens: number;
  error?: string;
}

export interface QualityEvalResponse {
  name: string;
  modelId: string;
  providerName?: string;
  totalCases: number;
  passedCases: number;
  averageScore: number;
  totalCostUsd: number;
  averageLatencyMs: number;
  results: QualityEvalCaseResult[];
}

export interface RouterApiKey {
  id: number;
  name: string;
  keyPrefix: string;
  status: string;
  organizationId?: number;
  projectId?: number;
  environment?: string;
  quotaRequests?: number;
  requestCount?: number;
  expiresAt?: string;
  rotatedFromKeyId?: number;
  plainApiKey?: string;
}

export interface Notification {
  id?: number;
  type: string;
  message: string;
  timestamp?: string;
}

export interface AnomalyAlert {
  category: string;
  severity: string;
  title: string;
  scopeLabel: string;
  message: string;
  metricValue: number;
  threshold: number;
}

export interface GuardrailConfig {
  allowedProviders: string[];
  deniedProviders: string[];
  blockedWords: string[];
  maxPromptChars: number;
  retentionMode: string;
}

export interface GuardrailPolicyPreset {
  id?: number;
  name: string;
  description?: string;
  organizationId?: number;
  organizationName?: string;
  projectId?: number;
  projectName?: string;
  allowedProviders: string[];
  deniedProviders: string[];
  blockedWords: string[];
  maxPromptChars: number;
  retentionMode: string;
}

export interface PolicyDryRunResult {
  workloadClass: string;
  blocked: boolean;
  blockReason?: string;
  selectedProvider?: string;
  selectedModel?: string;
  acceptedCandidates: number;
  rejectedCandidates: number;
  eligibilitySummary: Record<string, number>;
  policyDiff: Record<string, any>;
  routeTrace: Record<string, any>;
}

export interface BatchPolicyDryRunItem {
  exampleId: string;
  workloadClass: string;
  strategy: string;
  blocked: boolean;
  blockReason?: string;
  selectedProvider?: string;
  selectedModel?: string;
  acceptedCandidates: number;
  rejectedCandidates: number;
}

export interface BatchPolicyDryRunResponse {
  datasetName: string;
  workspaceLabel?: string;
  totalCases: number;
  blockedCases: number;
  successCases: number;
  strategySummaries: Array<Record<string, any>>;
  policyDiffSummary: Record<string, any>;
  items: BatchPolicyDryRunItem[];
}

export interface GuardrailPolicyCompareItem {
  exampleId: string;
  workloadClass: string;
  strategy: string;
  baselineBlocked: boolean;
  comparisonBlocked: boolean;
  baselineProvider?: string;
  comparisonProvider?: string;
  baselineModel?: string;
  comparisonModel?: string;
  acceptedCandidatesBefore: number;
  acceptedCandidatesAfter: number;
  changedProvider: boolean;
  changedBlock: boolean;
}

export interface GuardrailPolicyCompareResponse {
  datasetName: string;
  workspaceLabel?: string;
  baselinePolicyName: string;
  comparisonPolicyName: string;
  strategySummaries: Array<Record<string, any>>;
  comparisonSummary: Record<string, any>;
  items: GuardrailPolicyCompareItem[];
}

export interface DownloadArtifact {
  fileName: string;
  downloadUrl: string;
}

export interface RouteScoringProfile {
  name: string;
  sourceDataset: string;
  status: string;
  trainedAt: string;
  weights: Record<string, { capability: number; latency: number; cost: number }>;
}

export interface RouteScoringTrainResult extends RouteScoringProfile {
  workloadWinners: Array<Record<string, any>>;
  calibrationSummary: Array<Record<string, any>>;
}

export interface RouteScoringRecalibrationResult extends RouteScoringProfile {
  calibrationSummary: Array<Record<string, any>>;
  sourceSummary: Record<string, any>;
}

export interface RouteScoringExperiment {
  id?: number;
  name: string;
  controlProfileName: string;
  challengerProfileName: string;
  trafficPercentage: number;
  status: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface RouteReplayItem {
  requestId?: string;
  exampleId?: string;
  workloadClass: string;
  heuristicProvider?: string;
  learnedProvider?: string;
  baselineProfileName?: string;
  comparisonProfileName?: string;
  baselineProvider?: string;
  comparisonProvider?: string;
  originalProvider?: string;
  changed: boolean;
  source: string;
}

export interface RouteReplayResponse {
  source: string;
  sourceLabel: string;
  totalCases: number;
  changedRoutes: number;
  unchangedRoutes: number;
  items: RouteReplayItem[];
}

export interface RouteReplayRequestPayload {
  source: 'dataset' | 'recent_logs';
  datasetPath?: string;
  strategy?: string;
  limit?: number;
  organizationId?: number;
  projectId?: number;
  baselineProfileName?: string;
  comparisonProfileName?: string;
}

export interface AnalyticsSeriesItem {
  label: string;
  requests: number;
  failures: number;
  avgLatency: number;
  totalCost: number;
}

export interface WorkspaceUsageSummaryItem {
  organizationId?: number;
  organizationName?: string;
  projectId?: number;
  projectName?: string;
  environment?: string;
  requestCount: number;
  failureCount: number;
  fallbackCount: number;
  cacheHitCount: number;
  totalCost: number;
  avgLatency: number;
}

export interface CostOptimizationOpportunityItem {
  category: string;
  title: string;
  scopeLabel: string;
  summary: string;
  estimatedSavings: number;
  currentCost: number;
  targetCost?: number;
  recommendation: string;
}

export interface RouteScoringDriftItem {
  workloadClass: string;
  requestCount: number;
  activeProfileName: string;
  driftScore: number;
  routeChangeRate: number;
  defaultWeights: Record<string, number>;
  activeWeights: Record<string, number>;
}

export interface RouteScoringShiftItem {
  workloadClass: string;
  changedRoutes: number;
  totalRoutes: number;
}

export interface AnalyticsSummary {
  totalRequests: number;
  fallbackRate: number;
  blockedRequests: number;
  activeApiKeys: number;
  organizations: number;
  projects: number;
  routeScoringProfileName: string;
  recentRouteChanges: number;
  recentRouteChangeRate: number;
  recentRouteReplayCases: number;
  cacheHitRate: number;
  cacheHits: number;
  stickyRequests: number;
  routeScoringWorkloadShifts: RouteScoringShiftItem[];
  providerBreakdown: AnalyticsSeriesItem[];
  modelBreakdown: AnalyticsSeriesItem[];
  workspaceUsageSummary: WorkspaceUsageSummaryItem[];
  costOptimizationOpportunities: CostOptimizationOpportunityItem[];
  anomalyAlerts: AnomalyAlert[];
  routeScoringDrift: RouteScoringDriftItem[];
  routeScoringExperiments: Array<Record<string, any>>;
}

export interface RouteRule {
  id?: number;
  modelId: string;
  preferredProviderId: number;
  preferredProviderName?: string;
  backupProviderId?: number;
  backupProviderName?: string;
  timeoutMs: number;
}
