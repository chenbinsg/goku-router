import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  message,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from 'antd';
import { ExperimentOutlined } from '@ant-design/icons';
import { getModels, getProviders, runQualityEval } from '../api';
import type { Model, Provider, QualityEvalCase, QualityEvalResponse } from '../types';

const { TextArea } = Input;

const DEFAULT_CASES = JSON.stringify(
  [
    {
      caseId: 'basic-answer',
      prompt: '用一句话解释什么是 LLM router',
      expectedContains: ['router'],
      mustNotContain: ['不知道'],
      maxLatencyMs: 3000,
      weight: 1,
    },
  ],
  null,
  2,
);

const normalizeCases = (raw: string): QualityEvalCase[] => {
  const parsed = JSON.parse(raw);
  if (!Array.isArray(parsed)) {
    throw new Error('cases must be a JSON array');
  }
  return parsed.map((item, index) => ({
    caseId: item.caseId ?? item.case_id ?? `case-${index + 1}`,
    prompt: item.prompt,
    systemPrompt: item.systemPrompt ?? item.system_prompt,
    expectedContains: item.expectedContains ?? item.expected_contains ?? [],
    mustNotContain: item.mustNotContain ?? item.must_not_contain ?? [],
    requireJson: item.requireJson ?? item.require_json ?? false,
    tools: item.tools,
    responseFormat: item.responseFormat ?? item.response_format
      ? {
          type: (item.responseFormat ?? item.response_format).type,
          jsonSchema: (item.responseFormat ?? item.response_format).jsonSchema
            ?? (item.responseFormat ?? item.response_format).json_schema,
        }
      : undefined,
    maxLatencyMs: item.maxLatencyMs ?? item.max_latency_ms,
    maxCostUsd: item.maxCostUsd ?? item.max_cost_usd,
    weight: item.weight ?? 1,
  }));
};

const QualityEvalPage: React.FC = () => {
  const [form] = Form.useForm();
  const [models, setModels] = useState<Model[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<QualityEvalResponse | null>(null);

  useEffect(() => {
    const loadOptions = async () => {
      setLoading(true);
      try {
        const [modelItems, providerItems] = await Promise.all([getModels(), getProviders()]);
        setModels(modelItems);
        setProviders(providerItems);
        form.setFieldsValue({
          name: 'manual_quality_eval',
          modelId: modelItems[0]?.modelId,
          providerId: modelItems[0]?.providerId,
          temperature: 0,
          maxTokens: 512,
          casesJson: DEFAULT_CASES,
        });
      } catch {
        message.error('加载模型或 Provider 失败');
      } finally {
        setLoading(false);
      }
    };
    loadOptions();
  }, [form]);

  const modelOptions = useMemo(() => {
    const seen = new Set<string>();
    return models
      .filter((item) => {
        if (seen.has(item.modelId)) return false;
        seen.add(item.modelId);
        return true;
      })
      .map((item) => ({ label: item.modelId, value: item.modelId }));
  }, [models]);

  const providerOptions = providers.map((item) => ({
    label: item.providerName,
    value: item.id,
  }));

  const handleRun = async (values: any) => {
    let cases: QualityEvalCase[];
    try {
      cases = normalizeCases(values.casesJson);
    } catch (error: any) {
      message.error(`测试用例 JSON 无效: ${error.message}`);
      return;
    }
    if (cases.some((item) => !item.prompt)) {
      message.error('每个测试用例都需要 prompt');
      return;
    }

    setRunning(true);
    try {
      const response = await runQualityEval({
        name: values.name,
        modelId: values.modelId,
        providerId: values.providerId,
        temperature: values.temperature,
        maxTokens: values.maxTokens,
        cases,
      });
      setResult(response);
      message.success('质量评估完成');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '质量评估失败');
    } finally {
      setRunning(false);
    }
  };

  const columns = [
    {
      title: 'Case',
      dataIndex: 'caseId',
      key: 'caseId',
      width: 160,
    },
    {
      title: 'Status',
      dataIndex: 'success',
      key: 'success',
      width: 100,
      render: (value: boolean) => (
        <Tag color={value ? 'green' : 'red'}>{value ? 'PASS' : 'FAIL'}</Tag>
      ),
    },
    {
      title: 'Score',
      dataIndex: 'score',
      key: 'score',
      width: 100,
      render: (value: number) => value.toFixed(4),
    },
    {
      title: 'Latency',
      dataIndex: 'latencyMs',
      key: 'latencyMs',
      width: 110,
      render: (value: number) => `${value.toFixed(0)} ms`,
    },
    {
      title: 'Cost',
      dataIndex: 'costUsd',
      key: 'costUsd',
      width: 100,
      render: (value: number) => `$${value.toFixed(6)}`,
    },
    {
      title: 'Signals',
      key: 'signals',
      width: 260,
      render: (_: unknown, record: QualityEvalResponse['results'][number]) => (
        <Space size={[4, 4]} wrap>
          {record.matchedTerms.map((term) => <Tag key={`m-${term}`} color="blue">{term}</Tag>)}
          {record.missingTerms.map((term) => <Tag key={`x-${term}`} color="orange">missing: {term}</Tag>)}
          {record.forbiddenHits.map((term) => <Tag key={`f-${term}`} color="red">blocked: {term}</Tag>)}
          {record.jsonValid !== undefined && <Tag color={record.jsonValid ? 'green' : 'red'}>JSON</Tag>}
        </Space>
      ),
    },
    {
      title: 'Completion',
      dataIndex: 'completion',
      key: 'completion',
      render: (value: string, record: QualityEvalResponse['results'][number]) => (
        <Typography.Paragraph ellipsis={{ rows: 3, expandable: true }}>
          {record.error || value}
        </Typography.Paragraph>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card title="LLM 质量评估">
        <Form form={form} layout="vertical" onFinish={handleRun}>
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item name="name" label="评估名称" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="modelId" label="模型" rules={[{ required: true }]}>
                <Select loading={loading} options={modelOptions} showSearch optionFilterProp="label" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="providerId" label="Provider">
                <Select allowClear loading={loading} options={providerOptions} showSearch optionFilterProp="label" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col xs={24} md={8}>
              <Form.Item name="temperature" label="Temperature">
                <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="maxTokens" label="Max Tokens">
                <InputNumber min={1} max={8192} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="casesJson" label="测试用例 JSON" rules={[{ required: true }]}>
            <TextArea rows={12} spellCheck={false} />
          </Form.Item>
          <Button type="primary" htmlType="submit" icon={<ExperimentOutlined />} loading={running}>
            运行评估
          </Button>
        </Form>
      </Card>

      {result && (
        <>
          <Row gutter={16}>
            <Col xs={12} md={6}>
              <Card>
                <Statistic title="Average Score" value={result.averageScore} precision={4} />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Statistic title="Passed" value={result.passedCases} suffix={`/ ${result.totalCases}`} />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Statistic title="Avg Latency" value={result.averageLatencyMs} suffix="ms" />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Statistic title="Total Cost" value={result.totalCostUsd} precision={6} prefix="$" />
              </Card>
            </Col>
          </Row>
          <Alert
            type={result.averageScore >= 0.75 ? 'success' : 'warning'}
            showIcon
            message={`${result.providerName || ''} / ${result.modelId}`}
          />
          <Card title="Case Results">
            <Table
              rowKey="caseId"
              columns={columns}
              dataSource={result.results}
              pagination={false}
              scroll={{ x: 1100 }}
            />
          </Card>
        </>
      )}
    </Space>
  );
};

export default QualityEvalPage;
