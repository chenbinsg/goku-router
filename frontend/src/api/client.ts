import axios from 'axios';
import {
  ChatCompletionRequest,
  ChatCompletionResponse,
  EmbeddingRequest,
  EmbeddingResponse,
  ModelListResponse,
  BillingExportResponse
} from '../types';
import { getAccessToken } from '../utils/auth';

const BASE_URL = import.meta.env.VITE_BACKEND_URL ?? `http://localhost:${import.meta.env.VITE_BACKEND_PORT || '8159'}`;

const adminAuthHeaders = (): { Authorization: string } => {
  const token = getAccessToken();
  if (!token) {
    throw new Error('Admin login required');
  }
  return { Authorization: `Bearer ${token}` };
};

const client = axios.create({
  baseURL: BASE_URL,
});

client.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const createChatCompletion = async (request: ChatCompletionRequest): Promise<ChatCompletionResponse> => {
  const response = await client.post<ChatCompletionResponse>('/admin/playground/chat/completions', {
    ...request,
    top_p: request.topP,
    max_tokens: request.maxTokens,
    tool_choice: request.toolChoice,
    response_format: request.responseFormat ? {
      type: request.responseFormat.type,
      json_schema: request.responseFormat.jsonSchema,
    } : undefined,
    provider: request.provider ? {
      order: request.provider.order,
      allow_fallbacks: request.provider.allowFallbacks,
      sort: request.provider.sort,
      max_price_per_1k: request.provider.maxPricePer1k,
      require_capabilities: request.provider.requireCapabilities,
      require_parameters: request.provider.requireParameters,
      zdr: request.provider.zdr,
      data_collection: request.provider.dataCollection,
      organization: request.provider.organization,
      project: request.provider.project,
      sticky_key: request.provider.stickyKey,
    } : undefined,
  });
  return response.data;
};

export const createChatCompletionStream = async (
  request: ChatCompletionRequest,
  onChunk: (chunk: string) => void,
  onDone: (payload: { provider?: string; fallbackUsed?: boolean; requestId?: string; cacheHit?: boolean; responseHealed?: boolean; healingStrategy?: string; usage?: ChatCompletionResponse['usage'] }) => void,
): Promise<void> => {
  const response = await fetch(`${BASE_URL}/admin/playground/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...adminAuthHeaders(),
    },
    body: JSON.stringify({
      ...request,
      stream: true,
      top_p: request.topP,
      max_tokens: request.maxTokens,
      tool_choice: request.toolChoice,
      response_format: request.responseFormat ? {
        type: request.responseFormat.type,
        json_schema: request.responseFormat.jsonSchema,
      } : undefined,
      provider: request.provider ? {
        order: request.provider.order,
        allow_fallbacks: request.provider.allowFallbacks,
        sort: request.provider.sort,
        max_price_per_1k: request.provider.maxPricePer1k,
        require_capabilities: request.provider.requireCapabilities,
        require_parameters: request.provider.requireParameters,
        zdr: request.provider.zdr,
        data_collection: request.provider.dataCollection,
        organization: request.provider.organization,
        project: request.provider.project,
        sticky_key: request.provider.stickyKey,
      } : undefined,
    }),
  });
  if (!response.ok || !response.body) {
    throw new Error('Streaming request failed');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalMeta: { provider?: string; fallbackUsed?: boolean; requestId?: string; cacheHit?: boolean; responseHealed?: boolean; healingStrategy?: string; usage?: ChatCompletionResponse['usage'] } = {};

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';
    for (const event of events) {
      const line = event.trim();
      if (!line.startsWith('data:')) {
        continue;
      }
      const payloadText = line.replace(/^data:\s*/, '');
      if (payloadText === '[DONE]') {
        onDone(finalMeta);
        return;
      }
      const payload = JSON.parse(payloadText);
      const content = payload.choices?.[0]?.delta?.content;
      if (content) {
        onChunk(content);
      }
      if (payload.usage) {
        finalMeta = {
          provider: payload.provider,
          fallbackUsed: payload.fallback_used,
          requestId: payload.id,
          cacheHit: payload.cache_hit,
          responseHealed: payload.response_healed,
          healingStrategy: payload.healing_strategy,
          usage: payload.usage,
        };
      }
    }
  }
  onDone(finalMeta);
};

export const createEmbedding = async (request: EmbeddingRequest): Promise<EmbeddingResponse> => {
  const response = await client.post<EmbeddingResponse>('/admin/playground/embeddings', request);
  return response.data;
};

export const listModels = async (): Promise<ModelListResponse> => {
  const response = await client.get<ModelListResponse>('/admin/playground/models');
  return response.data;
};

export const exportBilling = async (): Promise<BillingExportResponse> => {
  const response = await client.get<BillingExportResponse>('/admin/billing/export');
  return response.data;
};
