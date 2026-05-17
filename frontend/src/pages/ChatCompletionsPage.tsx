import React, { useState, useEffect, useRef } from 'react';
import { Alert, Button, Card, Checkbox, Descriptions, Form, Input, InputNumber, Space, Typography, message } from 'antd';
import { createChatCompletion, createChatCompletionStream } from '../api';
import { ChatCompletionResponse } from '../types';
import { useI18n } from '../i18n';

type ChatCompletionFormValues = {
  model: string;
  messages: string;
  stream?: boolean;
  temperature?: number;
  topP?: number;
  maxTokens?: number;
  preferredProviders?: string;
  providerSort?: string;
  maxPricePer1k?: number;
  requiredCapabilities?: string;
  requireParameters?: boolean;
  zdr?: boolean;
  dataCollection?: string;
  stickyKey?: string;
  toolName?: string;
  responseSchema?: string;
};

const rollingKeyframes = `
@keyframes monkeyRoll {
  0%   { left: -60px;  transform: rotate(0deg);          }
  48%  { left: calc(100vw + 60px); transform: rotate(1080deg);           }
  50%  { left: calc(100vw + 60px); transform: rotate(1080deg) scaleX(-1);}
  98%  { left: -60px;  transform: rotate(0deg)   scaleX(-1);             }
  100% { left: -60px;  transform: rotate(0deg);          }
}
`;

const ChatCompletionsPage: React.FC = () => {
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ChatCompletionResponse | null>(null);
  const [showMonkey, setShowMonkey] = useState(false);
  const monkeyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (result) {
      setShowMonkey(true);
      if (monkeyTimer.current) clearTimeout(monkeyTimer.current);
      // 跑两圈后消失（每圈 8s，跑 2 圈 = 16s）
      monkeyTimer.current = setTimeout(() => setShowMonkey(false), 16000);
    }
  }, [result]);

  useEffect(() => () => { if (monkeyTimer.current) clearTimeout(monkeyTimer.current); }, []);

  const onFinish = async (values: ChatCompletionFormValues) => {
    setLoading(true);
    try {
      const request = {
        model: values.model,
        messages: values.messages
          .split('\n')
          .map((messageLine) => messageLine.trim())
          .filter(Boolean)
          .map((messageLine) => ({ role: 'user', content: messageLine })),
        stream: values.stream,
        temperature: values.temperature,
        topP: values.topP,
        maxTokens: values.maxTokens,
        provider: values.preferredProviders
          ? {
              order: values.preferredProviders
                .split(',')
                .map((item) => item.trim())
                .filter(Boolean),
              sort: values.providerSort,
              maxPricePer1k: values.maxPricePer1k,
              requireCapabilities: values.requiredCapabilities
                ? values.requiredCapabilities.split(',').map((item) => item.trim()).filter(Boolean)
                : undefined,
              requireParameters: values.requireParameters,
              zdr: values.zdr,
              dataCollection: values.dataCollection,
              stickyKey: values.stickyKey,
            }
          : values.providerSort || values.maxPricePer1k || values.requiredCapabilities || values.requireParameters || values.zdr || values.dataCollection || values.stickyKey
            ? {
                sort: values.providerSort,
                maxPricePer1k: values.maxPricePer1k,
                requireCapabilities: values.requiredCapabilities
                  ? values.requiredCapabilities.split(',').map((item) => item.trim()).filter(Boolean)
                  : undefined,
                requireParameters: values.requireParameters,
                zdr: values.zdr,
                dataCollection: values.dataCollection,
                stickyKey: values.stickyKey,
              }
            : undefined,
        tools: values.toolName
          ? [
              {
                type: 'function',
                function: {
                  name: values.toolName,
                  description: `Tool ${values.toolName}`,
                  parameters: { type: 'object' },
                },
              },
            ]
          : undefined,
        responseFormat: values.responseSchema
          ? {
              type: 'json_schema',
              jsonSchema: {
                schema: JSON.parse(values.responseSchema),
              },
            }
          : undefined,
      };
      if (values.stream) {
        let streamedCompletion = '';
        setResult({
          completion: '',
          provider: '',
          fallback_used: false,
          request_id: '',
          response_healed: false,
          usage: {
            prompt_tokens: 0,
            completion_tokens: 0,
            total_tokens: 0,
            cached_tokens: 0,
            reasoning_tokens: 0,
            provider_reported_cost: 0,
          },
        });
        await createChatCompletionStream(
          request,
          (chunk) => {
            streamedCompletion += chunk;
            setResult((current) => ({
              completion: streamedCompletion,
              provider: current?.provider || '',
              fallback_used: current?.fallback_used || false,
              cache_hit: current?.cache_hit || false,
              response_healed: current?.response_healed || false,
              healing_strategy: current?.healing_strategy,
              request_id: current?.request_id || '',
              usage: current?.usage || {
                prompt_tokens: 0,
                completion_tokens: 0,
                total_tokens: 0,
                cached_tokens: 0,
                reasoning_tokens: 0,
                provider_reported_cost: 0,
              },
            }));
          },
          (meta) => {
            setResult((current) => ({
              completion: current?.completion || streamedCompletion,
              provider: meta.provider || current?.provider || '',
              fallback_used: meta.fallbackUsed || false,
              cache_hit: meta.cacheHit || current?.cache_hit || false,
              response_healed: meta.responseHealed || current?.response_healed || false,
              healing_strategy: meta.healingStrategy || current?.healing_strategy,
              request_id: meta.requestId || current?.request_id || '',
              usage: meta.usage || current?.usage || {
                prompt_tokens: 0,
                completion_tokens: 0,
                total_tokens: 0,
                cached_tokens: 0,
                reasoning_tokens: 0,
                provider_reported_cost: 0,
              },
            }));
          },
        );
      } else {
        const response: ChatCompletionResponse = await createChatCompletion(request);
        setResult(response);
      }
      message.success(t('chat.success'));
    } catch (error) {
      message.error(t('chat.failure'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
    <style>{rollingKeyframes}</style>
    {showMonkey && (
      <img
        src="/logo.png"
        alt=""
        style={{
          position: 'fixed',
          bottom: 16,
          left: -60,
          width: 52,
          height: 52,
          objectFit: 'contain',
          animation: 'monkeyRoll 8s linear 2',
          pointerEvents: 'none',
          zIndex: 9999,
        }}
      />
    )}
    <Card title={t('chat.title')}>
      <Form layout="vertical" onFinish={onFinish}>
        <Form.Item
          label={t('chat.model')}
          name="model"
          initialValue="gpt-4o-mini"
          rules={[{ required: true, message: t('chat.modelRequired') }]}
        >
          <Input />
        </Form.Item>
        <Form.Item
          label={t('chat.messages')}
          name="messages"
          initialValue="Hello router"
          rules={[{ required: true, message: t('chat.messagesRequired') }]}
        >
          <Input.TextArea rows={4} />
        </Form.Item>
        <Form.Item name="stream" valuePropName="checked">
          <Checkbox>{t('chat.stream')}</Checkbox>
        </Form.Item>
        <Form.Item label={t('chat.temperature')} name="temperature" initialValue={0.7}>
          <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label={t('chat.topP')} name="topP" initialValue={1}>
          <InputNumber min={0} max={1} step={0.1} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label={t('chat.maxTokens')} name="maxTokens" initialValue={256}>
          <InputNumber min={1} max={8192} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label={t('chat.providerOrder')} name="preferredProviders">
          <Input placeholder="provider_primary,provider_backup" />
        </Form.Item>
        <Form.Item label="Provider Sort" name="providerSort" initialValue="balanced">
          <Input placeholder="balanced / price / latency / priority" />
        </Form.Item>
        <Form.Item label="Max Price / 1K" name="maxPricePer1k">
          <InputNumber min={0} step={0.1} style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item label="Required Capabilities" name="requiredCapabilities">
          <Input placeholder="tool_calling,structured_output" />
        </Form.Item>
        <Form.Item name="requireParameters" valuePropName="checked">
          <Checkbox>{t('chat.requireParameters')}</Checkbox>
        </Form.Item>
        <Form.Item name="zdr" valuePropName="checked">
          <Checkbox>{t('chat.zdr')}</Checkbox>
        </Form.Item>
        <Form.Item label={t('chat.dataCollection')} name="dataCollection">
          <Input placeholder="allow / deny" />
        </Form.Item>
        <Form.Item label={t('chat.stickyKey')} name="stickyKey">
          <Input placeholder="conversation-001" />
        </Form.Item>
        <Form.Item label="Tool Name" name="toolName">
          <Input placeholder="lookup_weather" />
        </Form.Item>
        <Form.Item label="Response Schema (JSON)" name="responseSchema">
          <Input.TextArea rows={6} placeholder='{"type":"object","properties":{"summary":{"type":"string"}},"required":["summary"]}' />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>
            {t('common.submit')}
          </Button>
        </Form.Item>
      </Form>
      {result && (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Alert
            type={result.fallback_used ? 'warning' : 'success'}
            showIcon
            message={result.fallback_used ? t('chat.fallbackUsed') : t('chat.primaryUsed')}
            description={
              <Space direction="vertical" size={0}>
                <Typography.Text>
                  {t('common.provider')}: <Typography.Text strong>{result.provider}</Typography.Text>
                </Typography.Text>
                <Typography.Text>
                  {t('chat.requestId')}: <Typography.Text code>{result.request_id}</Typography.Text>
                </Typography.Text>
              </Space>
            }
          />
          <Card type="inner" title={t('chat.requestSummary')}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label={t('common.provider')}>{result.provider}</Descriptions.Item>
              <Descriptions.Item label={t('chat.fallback')}>
                {result.fallback_used ? t('logs.yes') : t('logs.no')}
              </Descriptions.Item>
              <Descriptions.Item label={t('chat.requestId')}>
                <Typography.Text code>{result.request_id}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label={t('billing.resolvedModel')}>
                {result.selected_model || result.provider}
              </Descriptions.Item>
              <Descriptions.Item label={t('chat.cacheHit')}>
                {result.cache_hit ? t('logs.yes') : t('logs.no')}
              </Descriptions.Item>
              <Descriptions.Item label={t('chat.responseHealed')}>
                {result.response_healed ? t('logs.yes') : t('logs.no')}
              </Descriptions.Item>
              <Descriptions.Item label={t('chat.healingStrategy')}>
                {result.healing_strategy || 'N/A'}
              </Descriptions.Item>
              <Descriptions.Item label={t('chat.promptTokens')}>
                {result.usage.prompt_tokens}
              </Descriptions.Item>
              <Descriptions.Item label={t('chat.cachedTokens')}>
                {result.usage.cached_tokens || 0}
              </Descriptions.Item>
              <Descriptions.Item label={t('chat.completionTokens')}>
                {result.usage.completion_tokens}
              </Descriptions.Item>
              <Descriptions.Item label={t('chat.reasoningTokens')}>
                {result.usage.reasoning_tokens || 0}
              </Descriptions.Item>
              <Descriptions.Item label={t('chat.totalTokens')}>
                {result.usage.total_tokens}
              </Descriptions.Item>
              <Descriptions.Item label={t('chat.providerReportedCost')}>
                {result.usage.provider_reported_cost || 0}
              </Descriptions.Item>
            </Descriptions>
          </Card>
          <Card type="inner" title={t('chat.completionResult')}>
            <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
              {result.completion}
            </Typography.Paragraph>
            {result.structured_output && (
              <Typography.Paragraph style={{ marginTop: 16, marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                <Typography.Text strong>Structured Output</Typography.Text>
                {'\n'}
                {JSON.stringify(result.structured_output, null, 2)}
              </Typography.Paragraph>
            )}
            {result.tool_calls && (
              <Typography.Paragraph style={{ marginTop: 16, marginBottom: 0, whiteSpace: 'pre-wrap' }}>
                <Typography.Text strong>Tool Calls</Typography.Text>
                {'\n'}
                {JSON.stringify(result.tool_calls, null, 2)}
              </Typography.Paragraph>
            )}
          </Card>
        </Space>
      )}
    </Card>
    </>
  );
};

export default ChatCompletionsPage;
