import React, { useEffect, useState } from 'react';
import { Alert, Button, Card, Checkbox, Descriptions, Form, Input, Modal, Space, Table, Typography, message } from 'antd';

import { addProvider, getProviders, testProviderConnection, updateProvider } from '../api';
import { Provider, ProviderConnectionTestResult } from '../types';
import { useI18n } from '../i18n';

const normalizeProviderEnvKey = (providerName: string) =>
  providerName
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '_');

const ProvidersAdminPage: React.FC = () => {
  const { t } = useI18n();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isTestModalVisible, setIsTestModalVisible] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<Provider | null>(null);
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
  const [draftProviderName, setDraftProviderName] = useState('external_router');
  const [testResult, setTestResult] = useState<ProviderConnectionTestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [providerForm] = Form.useForm<Provider>();

  useEffect(() => {
    const fetchProviders = async () => {
      setLoading(true);
      try {
        const response = await getProviders();
        setProviders(response);
      } catch (error) {
        message.error(t('providers.loadFailed'));
      } finally {
        setLoading(false);
      }
    };

    fetchProviders();
  }, []);

  const handleAddProvider = async (values: Provider) => {
    try {
      if (editingProvider?.id) {
        const updated = await updateProvider({ ...editingProvider, ...values });
        setProviders((current) => current.map((item) => (item.id === updated.id ? updated : item)));
        message.success(t('providers.updated'));
      } else {
        const created = await addProvider(values);
        setProviders((current) => [...current, created]);
        message.success(t('providers.added'));
      }
      setIsModalVisible(false);
      setEditingProvider(null);
      providerForm.resetFields();
    } catch (error) {
      message.error(t('providers.addFailed'));
    }
  };

  const handleOpenTestModal = (provider: Provider) => {
    setSelectedProvider(provider);
    setTestResult(null);
    setIsTestModalVisible(true);
  };

  const handleTestProvider = async (values: { providerModelName: string; prompt: string }) => {
    if (!selectedProvider?.id) {
      message.error(t('providers.missingId'));
      return;
    }
    setTesting(true);
    try {
      const result = await testProviderConnection({
        providerId: selectedProvider.id,
        providerModelName: values.providerModelName,
        prompt: values.prompt,
      });
      setTestResult(result);
      message.success(t('providers.connectionSucceeded'));
    } catch (error) {
      setTestResult(null);
      message.error(t('providers.connectionFailed'));
    } finally {
      setTesting(false);
    }
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
    },
    {
      title: t('providers.name'),
      dataIndex: 'providerName',
      key: 'providerName',
    },
    {
      title: t('providers.adapterType'),
      dataIndex: 'adapterType',
      key: 'adapterType',
    },
    {
      title: t('common.status'),
      dataIndex: 'status',
      key: 'status',
    },
    {
      title: t('providers.health'),
      dataIndex: 'healthStatus',
      key: 'healthStatus',
    },
    {
      title: t('common.priority'),
      dataIndex: 'priority',
      key: 'priority',
    },
    {
      title: t('providers.inputCost'),
      dataIndex: 'inputCostPer1k',
      key: 'inputCostPer1k',
    },
    {
      title: t('providers.outputCost'),
      dataIndex: 'outputCostPer1k',
      key: 'outputCostPer1k',
    },
    {
      title: t('providers.avgLatency'),
      dataIndex: 'avgLatencyMs',
      key: 'avgLatencyMs',
    },
    {
      title: t('providers.maxInputTokens'),
      dataIndex: 'maxInputTokens',
      key: 'maxInputTokens',
    },
    {
      title: t('providers.maxOutputTokens'),
      dataIndex: 'maxOutputTokens',
      key: 'maxOutputTokens',
    },
    {
      title: t('providers.capabilities'),
      key: 'capabilities',
      render: (_: unknown, record: Provider) => (record.capabilities || []).join(', '),
    },
    {
      title: t('providers.supportsZdr'),
      dataIndex: 'supportsZdr',
      key: 'supportsZdr',
      render: (value: boolean | undefined) => (value ? t('logs.yes') : t('logs.no')),
    },
    {
      title: t('providers.dataCollectionMode'),
      dataIndex: 'dataCollectionMode',
      key: 'dataCollectionMode',
    },
    {
      title: t('providers.supportedParameters'),
      key: 'supportedParameters',
      render: (_: unknown, record: Provider) => (record.supportedParameters || []).join(', '),
    },
    {
      title: t('providers.envVars'),
      key: 'envVars',
      render: (_: unknown, record: Provider) => {
        const normalized = normalizeProviderEnvKey(record.providerName);
        return (
          <Space direction="vertical" size={0}>
            <Typography.Text code>{`PROVIDER_${normalized}_BASE_URL`}</Typography.Text>
            <Typography.Text code>{`PROVIDER_${normalized}_API_KEY`}</Typography.Text>
          </Space>
        );
      },
    },
    {
      title: t('common.actions'),
      key: 'actions',
      render: (_: unknown, record: Provider) => (
        <Space>
          <Button
            type="link"
            onClick={() => {
              setEditingProvider(record);
              setDraftProviderName(record.providerName);
              providerForm.setFieldsValue(record);
              setIsModalVisible(true);
            }}
          >
            {t('common.edit')}
          </Button>
          <Button onClick={() => handleOpenTestModal(record)}>
            {t('providers.testConnection')}
          </Button>
        </Space>
      ),
    },
  ];

  const normalizedDraftProviderName = normalizeProviderEnvKey(draftProviderName);

  return (
    <Card title={t('providers.title')}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={t('providers.envHint')}
        description={
          <Space direction="vertical" size={0}>
            <Typography.Text code>{`PROVIDER_${normalizedDraftProviderName}_BASE_URL`}</Typography.Text>
            <Typography.Text code>{`PROVIDER_${normalizedDraftProviderName}_API_KEY`}</Typography.Text>
          </Space>
        }
      />
      <Button
        type="primary"
        onClick={() => {
          setEditingProvider(null);
          setDraftProviderName('external_router');
          providerForm.resetFields();
          providerForm.setFieldsValue({
            providerName: 'external_router',
            adapterType: 'mock',
            status: 'active',
            healthStatus: 'healthy',
            priority: 100,
            inputCostPer1k: 0.001,
            outputCostPer1k: 0.002,
            avgLatencyMs: 500,
            maxInputTokens: 4096,
            maxOutputTokens: 2048,
            capabilities: ['chat'],
            supportsZdr: false,
            dataCollectionMode: 'allow',
            supportedParameters: ['temperature', 'top_p', 'max_tokens', 'stop', 'tools', 'tool_choice', 'response_format'],
          });
          setIsModalVisible(true);
        }}
        style={{ marginBottom: 16 }}
      >
        {t('providers.add')}
      </Button>
      <Table
        dataSource={providers.map((provider) => ({
          ...provider,
          key: provider.id || provider.providerName,
        }))}
        columns={columns}
        loading={loading}
        pagination={false}
      />
      <Modal
        title={editingProvider ? t('providers.edit') : t('providers.add')}
        open={isModalVisible}
        onCancel={() => {
          setIsModalVisible(false);
          setEditingProvider(null);
          providerForm.resetFields();
        }}
        footer={null}
      >
        <Form
          form={providerForm}
          layout="vertical"
          onFinish={handleAddProvider}
          onValuesChange={(changedValues) => {
            if (typeof changedValues.providerName === 'string') {
              setDraftProviderName(changedValues.providerName || 'external_router');
            }
          }}
        >
          <Form.Item name="id" hidden>
            <Input />
          </Form.Item>
          <Form.Item
            label={t('providers.name')}
            name="providerName"
            rules={[{ required: true, message: t('providers.nameRequired') }]}
          >
            <Input placeholder="external_router" />
          </Form.Item>
          <Form.Item
            label={t('providers.adapterType')}
            name="adapterType"
            rules={[{ required: true, message: t('providers.adapterRequired') }]}
          >
            <Input placeholder="mock or openai_compatible" />
          </Form.Item>
          <Form.Item
            label={t('common.status')}
            name="status"
            rules={[{ required: true, message: t('providers.statusRequired') }]}
          >
            <Input placeholder="active" />
          </Form.Item>
          <Form.Item
            label={t('providers.health')}
            name="healthStatus"
            rules={[{ required: true, message: t('providers.healthRequired') }]}
          >
            <Input placeholder="healthy" />
          </Form.Item>
          <Form.Item
            label={t('common.priority')}
            name="priority"
            rules={[{ required: true, message: t('providers.priorityRequired') }]}
          >
            <Input placeholder="100" />
          </Form.Item>
          <Form.Item label={t('providers.inputCost')} name="inputCostPer1k">
            <Input placeholder="0.001" />
          </Form.Item>
          <Form.Item label={t('providers.outputCost')} name="outputCostPer1k">
            <Input placeholder="0.002" />
          </Form.Item>
          <Form.Item label={t('providers.avgLatency')} name="avgLatencyMs">
            <Input placeholder="500" />
          </Form.Item>
          <Form.Item label={t('providers.maxInputTokens')} name="maxInputTokens">
            <Input placeholder="4096" />
          </Form.Item>
          <Form.Item label={t('providers.maxOutputTokens')} name="maxOutputTokens">
            <Input placeholder="2048" />
          </Form.Item>
          <Form.Item
            label={t('providers.capabilities')}
            name="capabilities"
            getValueProps={(value) => ({ value: Array.isArray(value) ? value.join(', ') : value })}
            normalize={(value) =>
              typeof value === 'string'
                ? value.split(',').map((item) => item.trim()).filter(Boolean)
                : value
            }
          >
            <Input placeholder="chat,tool_calling,structured_output" />
          </Form.Item>
          <Form.Item label={t('providers.supportsZdr')} name="supportsZdr" valuePropName="checked">
            <Checkbox>{t('providers.supportsZdr')}</Checkbox>
          </Form.Item>
          <Form.Item label={t('providers.dataCollectionMode')} name="dataCollectionMode">
            <Input placeholder="allow or deny" />
          </Form.Item>
          <Form.Item
            label={t('providers.supportedParameters')}
            name="supportedParameters"
            getValueProps={(value) => ({ value: Array.isArray(value) ? value.join(', ') : value })}
            normalize={(value) =>
              typeof value === 'string'
                ? value.split(',').map((item) => item.trim()).filter(Boolean)
                : value
            }
          >
            <Input placeholder="temperature,top_p,max_tokens,stop,tools,tool_choice,response_format" />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            message={t('providers.envHintModal')}
            description={
              <Space direction="vertical" size={0}>
                <Typography.Text code>{`PROVIDER_${normalizedDraftProviderName}_BASE_URL`}</Typography.Text>
                <Typography.Text code>{`PROVIDER_${normalizedDraftProviderName}_API_KEY`}</Typography.Text>
              </Space>
            }
            style={{ marginBottom: 16 }}
          />
          <Form.Item>
            <Button type="primary" htmlType="submit">
              {t('common.submit')}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={selectedProvider ? `${t('providers.testConnection')}: ${selectedProvider.providerName}` : t('providers.testConnection')}
        open={isTestModalVisible}
        onCancel={() => {
          setIsTestModalVisible(false);
          setSelectedProvider(null);
          setTestResult(null);
        }}
        footer={null}
      >
        <Form
          layout="vertical"
          onFinish={handleTestProvider}
          initialValues={{
            providerModelName: selectedProvider?.adapterType === 'mock' ? 'mock-primary-model1' : 'gpt-4.1-mini',
            prompt: 'Connection test from router',
          }}
        >
          <Form.Item
            label={t('providers.modelName')}
            name="providerModelName"
            rules={[{ required: true, message: t('providers.modelNameRequired') }]}
          >
            <Input placeholder="gpt-4.1-mini" />
          </Form.Item>
          <Form.Item
            label={t('providers.connectionPrompt')}
            name="prompt"
            rules={[{ required: true, message: t('providers.promptRequired') }]}
          >
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={testing}>
              {t('providers.runTest')}
            </Button>
          </Form.Item>
        </Form>
        {testResult && (
          <Card type="inner" title={t('providers.testResult')}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label={t('common.provider')}>{testResult.providerName}</Descriptions.Item>
              <Descriptions.Item label={t('providers.adapterType')}>{testResult.adapterType}</Descriptions.Item>
              <Descriptions.Item label={t('chat.promptTokens')}>{testResult.promptTokens}</Descriptions.Item>
              <Descriptions.Item label={t('chat.completionTokens')}>{testResult.completionTokens}</Descriptions.Item>
              <Descriptions.Item label={t('common.message')}>{testResult.message}</Descriptions.Item>
            </Descriptions>
            <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
              {testResult.completion}
            </Typography.Paragraph>
          </Card>
        )}
      </Modal>
    </Card>
  );
};

export default ProvidersAdminPage;
