// Add missing type exports
export type ByokKey = {
  keyId: string;
  organization: string;
  project: string;
};

export type Credit = {
  creditId: string;
  amount: number;
  organization: string;
};

export type BillingRecord = {
  recordId: string;
  amount: number;
  organization: string;
};

export type SecurityLog = {
  logId: string;
  action: string;
  timestamp: string;
};

export type RequestLog = {
  requestId: string;
  statusCode: number;
  latency: number;
};

export type Organization = {
  name: string;
};

export type Model = {
  modelId: string;
};

export type Provider = {
  providerName: string;
};

export type Notification = {
  type: string;
  message: string;
};

// Existing types
export type ChatCompletionRequest = {
  // Define properties
};

export type ChatCompletionResponse = {
  // Define properties
};

export type EmbeddingRequest = {
  // Define properties
};

export type EmbeddingResponse = {
  // Define properties
};

export type ModelListResponse = {
  // Define properties
};

export type BillingExportResponse = {
  csv_url: string;
};
