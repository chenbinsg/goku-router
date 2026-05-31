import React, { useEffect, useState } from 'react';
import {
  Alert, Button, Card, Checkbox, Descriptions, Form, Input,
  Modal, Popconfirm, Space, Switch, Table, Tag, Typography, message,
} from 'antd';
import { CheckCircleOutlined, CloseCircleOutlined, DeleteOutlined, ExperimentOutlined, PlusOutlined } from '@ant-design/icons';

import { addProvider, deleteProvider, getProviders, testProviderConnection, updateProvider } from '../api';
import { Provider, ProviderConnectionTestResult } from '../types';
import { useI18n } from '../i18n';

const normalizeProviderEnvKey = (providerName: string) =>
  providerName.toUpperCase().replace(/[^A-Z0-9]/g, '_');

const ProvidersAdminPage: React.FC = () => {
  const { t } = useI18n();
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(false);
  const [togglingId, setTogglingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [isTestModalVisible, setIsTestModalVisible] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<Provider | null>(null);
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null);
  const [draftProviderName, setDraftProviderName] = useState('external_router');
  const [testResult, setTestResult] = useState<ProviderConnectionTestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [providerForm] = Form.useForm<Provider>();

  const fetchProviders = async () => {
    setLoading(true);
    try {
      const response = await getProviders();
      setProviders(response);
    } catch {
      message.error(t('providers.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchProviders(); }, []);

  const handleToggleStatus = async (record: Provider) => {
    const newStatus = record.status === 'active' ? 'disabled' : 'active';
    setTogglingId(String(record.id ?? record.providerName));
    try {
      const updated = await updateProvider({ ...record, status: newStatus });
      setProviders(cur => cur.map(p => p.id === updated.id ? updated : p));
      message.success(newStatus === 'active' ? t('providers.enabled') : t('providers.disabled'));
    } catch {
      message.error(t('providers.updateFailed'));
    } finally {
      setTogglingId(null);
    }
  };

  const handleDelete = async (record: Provider) => {
    const key = record.id ?? record.providerName;
    setDeletingId(String(key));
    try {
      await deleteProvider(String(record.id));
      setProviders(cur => cur.filter(p => p.id !== record.id));
      message.success(t('providers.deleted'));
    } catch {
      message.error(t('providers.deleteFailed'));
    } finally {
      setDeletingId(null);
    }
  };

  const handleSaveProvider = async (values: Provider) => {
    try {
      if (editingProvider?.id) {
        const updated = await updateProvider({ ...editingProvider, ...values });
        setProviders(cur => cur.map(p => p.id === updated.id ? updated : p));
        message.success(t('providers.updated'));
      } else {
        const created = await addProvider(values);
        setProviders(cur => [...cur, created]);
        message.success(t('providers.added'));
      }
      setIsModalVisible(false);
      setEditingProvider(null);
      providerForm.resetFields();
    } catch {
      message.error(t('providers.addFailed'));
    }
  };

  const handleOpenTestModal = (provider: Provider) => {
    setSelectedProvider(provider);
    setTestResult(null);
    setIsTestModalVisible(true);
  };

  const handleTestProvider = async (values: { providerModelName: string; prompt: string }) => {
    if (!selectedProvider?.id) { message.error(t('providers.missingId')); return; }
    setTesting(true);
    try {
      const result = await testProviderConnection({
        providerId: selectedProvider.id,
        providerModelName: values.providerModelName,
        prompt: values.prompt,
      });
      setTestResult(result);
      message.success(t('providers.connectionSucceeded'));
    } catch {
      setTestResult(null);
      message.error(t('providers.connectionFailed'));
    } finally {
      setTesting(false);
    }
  };

  const columns = [
    {
      title: t('providers.name'),
      dataIndex: 'providerName',
      key: 'providerName',
      render: (name: string) => <Typography.Text strong>{name}</Typography.Text>,
    },
    {
      title: t('providers.adapterType'),
      dataIndex: 'adapterType',
      key: 'adapterType',
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: t('common.status'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) =>
        status === 'active'
          ? <Tag icon={<CheckCircleOutlined />} color="success">Active</Tag>
          : <Tag icon={<CloseCircleOutlined />} color="error">Disabled</Tag>,
    },
    {
      title: t('providers.health'),
      dataIndex: 'healthStatus',
      key: 'healthStatus',
      render: (v: string) => {
        const color = v === 'healthy' ? 'success' : v === 'degraded' ? 'warning' : 'default';
        return <Tag color={color}>{v}</Tag>;
      },
    },
    {
      title: t('common.priority'),
      dataIndex: 'priority',
      key: 'priority',
      width: 80,
    },
    {
      title: t('providers.avgLatency'),
      dataIndex: 'avgLatencyMs',
      key: 'avgLatencyMs',
      width: 100,
      render: (v: number) => v ? `${v} ms` : '—',
    },
    {
      title: t('common.actions'),
      key: 'actions',
      width: 220,
      render: (_: unknown, record: Provider) => {
        const isActive = record.status === 'active';
        const isToggling = togglingId === (record.id ?? record.providerName);
        const isDeleting = deletingId === (record.id ?? record.providerName);
        return (
          <Space>
            <Switch
              size="small"
              checked={isActive}
              loading={isToggling}
              checkedChildren="ON"
              unCheckedChildren="OFF"
              onChange={() => handleToggleStatus(record)}
            />
            <Button
              size="small"
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
            <Button
              size="small"
              icon={<ExperimentOutlined />}
              onClick={() => handleOpenTestModal(record)}
            >
              {t('providers.testConnection')}
            </Button>
            <Popconfirm
              title={t('providers.deleteConfirmTitle')}
              description={t('providers.deleteConfirmDesc')}
              onConfirm={() => handleDelete(record)}
              okText={t('common.delete')}
              okButtonProps={{ danger: true }}
              cancelText={t('common.cancel')}
            >
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                loading={isDeleting}
              >
                {t('common.delete')}
              </Button>
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  const normalizedDraftProviderName = normalizeProviderEnvKey(draftProviderName);

  return (
    <Card
      title={t('providers.title')}
      extra={
        <Button
          type="primary"
          icon={<PlusOutlined />}
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
        >
          {t('providers.add')}
        </Button>
      }
    >
      <Table
        dataSource={providers.map(p => ({ ...p, key: p.id || p.providerName }))}
        columns={columns}
        loading={loading}
        pagination={false}
        size="middle"
      />

      {/* Add / Edit Modal */}
      <Modal
        title={editingProvider ? t('providers.edit') : t('providers.add')}
        open={isModalVisible}
        onCancel={() => { setIsModalVisible(false); setEditingProvider(null); providerForm.resetFields(); }}
        footer={null}
        width={560}
      >
        <Form
          form={providerForm}
          layout="vertical"
          onFinish={handleSaveProvider}
          onValuesChange={(changed) => {
            if (typeof changed.providerName === 'string')
              setDraftProviderName(changed.providerName || 'external_router');
          }}
        >
          <Form.Item name="id" hidden><Input /></Form.Item>

          <Form.Item label={t('providers.name')} name="providerName"
            rules={[{ required: true, message: t('providers.nameRequired') }]}>
            <Input placeholder="external_router" />
          </Form.Item>

          <Form.Item label={t('providers.adapterType')} name="adapterType"
            rules={[{ required: true, message: t('providers.adapterRequired') }]}>
            <Input placeholder="openai_compatible" />
          </Form.Item>

          <Space style={{ width: '100%' }} size={12}>
            <Form.Item label={t('common.status')} name="status" style={{ flex: 1 }}
              rules={[{ required: true, message: t('providers.statusRequired') }]}>
              <Input placeholder="active" />
            </Form.Item>
            <Form.Item label={t('providers.health')} name="healthStatus" style={{ flex: 1 }}
              rules={[{ required: true, message: t('providers.healthRequired') }]}>
              <Input placeholder="healthy" />
            </Form.Item>
            <Form.Item label={t('common.priority')} name="priority" style={{ width: 90 }}
              rules={[{ required: true, message: t('providers.priorityRequired') }]}>
              <Input placeholder="100" />
            </Form.Item>
          </Space>

          <Space style={{ width: '100%' }} size={12}>
            <Form.Item label={t('providers.inputCost')} name="inputCostPer1k" style={{ flex: 1 }}>
              <Input placeholder="0.001" />
            </Form.Item>
            <Form.Item label={t('providers.outputCost')} name="outputCostPer1k" style={{ flex: 1 }}>
              <Input placeholder="0.002" />
            </Form.Item>
            <Form.Item label={t('providers.avgLatency')} name="avgLatencyMs" style={{ flex: 1 }}>
              <Input placeholder="500" />
            </Form.Item>
          </Space>

          <Space style={{ width: '100%' }} size={12}>
            <Form.Item label={t('providers.maxInputTokens')} name="maxInputTokens" style={{ flex: 1 }}>
              <Input placeholder="4096" />
            </Form.Item>
            <Form.Item label={t('providers.maxOutputTokens')} name="maxOutputTokens" style={{ flex: 1 }}>
              <Input placeholder="2048" />
            </Form.Item>
          </Space>

          <Form.Item label={t('providers.capabilities')} name="capabilities"
            getValueProps={v => ({ value: Array.isArray(v) ? v.join(', ') : v })}
            normalize={v => typeof v === 'string' ? v.split(',').map(s => s.trim()).filter(Boolean) : v}>
            <Input placeholder="chat,tool_calling,structured_output" />
          </Form.Item>

          <Form.Item label={t('providers.supportsZdr')} name="supportsZdr" valuePropName="checked">
            <Checkbox>{t('providers.supportsZdr')}</Checkbox>
          </Form.Item>

          <Form.Item label={t('providers.dataCollectionMode')} name="dataCollectionMode">
            <Input placeholder="allow" />
          </Form.Item>

          <Form.Item label={t('providers.supportedParameters')} name="supportedParameters"
            getValueProps={v => ({ value: Array.isArray(v) ? v.join(', ') : v })}
            normalize={v => typeof v === 'string' ? v.split(',').map(s => s.trim()).filter(Boolean) : v}>
            <Input placeholder="temperature,top_p,max_tokens,stop,tools,tool_choice,response_format" />
          </Form.Item>

          <Alert
            type="info" showIcon
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
            <Button type="primary" htmlType="submit">{t('common.submit')}</Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* Test Connection Modal */}
      <Modal
        title={selectedProvider ? `${t('providers.testConnection')}: ${selectedProvider.providerName}` : t('providers.testConnection')}
        open={isTestModalVisible}
        onCancel={() => { setIsTestModalVisible(false); setSelectedProvider(null); setTestResult(null); }}
        footer={null}
        width={480}
      >
        <Form
          layout="vertical"
          onFinish={handleTestProvider}
          initialValues={{
            providerModelName: selectedProvider?.adapterType === 'mock' ? 'mock-primary-model1' : 'gpt-4.1-mini',
            prompt: 'Connection test from router',
          }}
        >
          <Form.Item label={t('providers.modelName')} name="providerModelName"
            rules={[{ required: true, message: t('providers.modelNameRequired') }]}>
            <Input placeholder="gpt-4.1-mini" />
          </Form.Item>
          <Form.Item label={t('providers.connectionPrompt')} name="prompt"
            rules={[{ required: true, message: t('providers.promptRequired') }]}>
            <Input.TextArea rows={3} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={testing}>{t('providers.runTest')}</Button>
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
