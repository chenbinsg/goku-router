import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, InputNumber, message, Card, Popconfirm, Space, Select } from 'antd';
import { deleteRouteRule, getModels, getProviders, getRouteRules, saveRouteRule } from '../api';
import { Model, Provider, RouteRule } from '../types';
import { useI18n } from '../i18n';

const RoutingAdminPage: React.FC = () => {
  const { t } = useI18n();
  const [routeRules, setRouteRules] = useState<RouteRule[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingRoute, setEditingRoute] = useState<RouteRule | null>(null);
  const [form] = Form.useForm<RouteRule>();

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [routes, modelList, providerList] = await Promise.all([
          getRouteRules(),
          getModels(),
          getProviders(),
        ]);
        setRouteRules(routes);
        setModels(modelList);
        setProviders(providerList);
      } catch (error) {
        message.error(t('routing.loadFailed'));
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  const activeModels = models.filter((model) => (model.status || 'active') === 'active');
  const modelOptions = Array.from(new Set(activeModels.map((model) => model.modelId))).sort();
  const selectedModelId = Form.useWatch('modelId', form);
  const preferredProviderId = Form.useWatch('preferredProviderId', form);
  const timeoutMsValue = Form.useWatch('timeoutMs', form);

  const formatTimeout = (value?: number | null) => {
    if (!value || value <= 0) return '—';
    const seconds = value / 1000;
    const secondsLabel = Number.isInteger(seconds) ? `${seconds}` : seconds.toFixed(1);
    return `${value.toLocaleString()} ms (${secondsLabel}s)`;
  };
  const matchingModelMappings = selectedModelId
    ? activeModels.filter((model) => model.modelId === selectedModelId)
    : [];
  const providerOptions = matchingModelMappings.length > 0
    ? matchingModelMappings.map((model) => {
        const provider = providers.find((item) => item.id === model.providerId);
        return {
          value: model.providerId,
          label: provider?.providerName || model.providerName || String(model.providerId),
          providerModelName: model.providerModelName,
        };
      }).filter((provider) => provider.value !== undefined)
    : providers
        .filter((provider) => (provider.status || 'active') === 'active')
        .map((provider) => ({
          value: provider.id,
          label: provider.providerName,
          providerModelName: undefined,
        }))
        .filter((provider) => provider.value !== undefined);

  const handleDelete = async (record: RouteRule) => {
    try {
      await deleteRouteRule(record);
      setRouteRules((current) => current.filter((item) => item.id !== record.id));
      message.success(t('routing.deleted'));
    } catch (error) {
      message.error(t('routing.deleteFailed'));
    }
  };

  const columns = [
    {
      title: t('common.model'),
      dataIndex: 'modelId',
      key: 'modelId',
    },
    {
      title: t('routing.preferredProvider'),
      dataIndex: 'preferredProviderName',
      key: 'preferredProviderName',
    },
    {
      title: t('routing.backupProvider'),
      dataIndex: 'backupProviderName',
      key: 'backupProviderName',
    },
    {
      title: t('routing.timeout'),
      dataIndex: 'timeoutMs',
      key: 'timeoutMs',
      render: (value: number) => formatTimeout(value),
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: unknown, record: RouteRule) => (
        <Space>
          <Button
            type="link"
            onClick={() => {
              setEditingRoute(record);
              form.setFieldsValue(record);
              setIsModalVisible(true);
            }}
          >
            {t('common.edit')}
          </Button>
          <Popconfirm
            title={t('routing.deleteConfirmTitle')}
            description={t('routing.deleteConfirmDesc')}
            okText={t('common.delete')}
            cancelText={t('common.cancel')}
            onConfirm={() => handleDelete(record)}
          >
            <Button type="link" danger>
              {t('common.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const handleOk = async (values: RouteRule) => {
    const saved = await saveRouteRule({
      modelId: values.modelId,
      preferredProviderId: Number(values.preferredProviderId),
      backupProviderId: values.backupProviderId ? Number(values.backupProviderId) : undefined,
      timeoutMs: Number(values.timeoutMs),
    });
    setRouteRules((current) => {
      const withoutCurrent = current.filter((item) => item.modelId !== saved.modelId);
      return [...withoutCurrent, saved].sort((a, b) => a.modelId.localeCompare(b.modelId));
    });
    setIsModalVisible(false);
    setEditingRoute(null);
    form.resetFields();
    message.success(t('routing.updated'));
  };

  return (
    <Card title={t('routing.title')}>
      <Button
        type="primary"
        onClick={() => {
          setEditingRoute(null);
          form.resetFields();
          form.setFieldsValue({ timeoutMs: 60000 } as RouteRule);
          setIsModalVisible(true);
        }}
        style={{ marginBottom: 16 }}
      >
        {t('routing.add')}
      </Button>
      <Table dataSource={routeRules.map((item) => ({ ...item, key: item.id || item.modelId }))} columns={columns} loading={loading} pagination={false} />
      <Modal
        title={editingRoute ? t('routing.edit') : t('routing.add')}
        open={isModalVisible}
        onCancel={() => {
          setIsModalVisible(false);
          setEditingRoute(null);
          form.resetFields();
        }}
        footer={null}
      >
        <Form form={form} layout="vertical" onFinish={handleOk}>
          <Form.Item
            label={t('common.model')}
            name="modelId"
            rules={[{ required: true, message: t('routing.modelRequired') }]}
          >
            <Select
              showSearch
              placeholder={t('routing.modelPlaceholder')}
              optionFilterProp="label"
              onChange={(modelId) => {
                const candidates = activeModels.filter((model) => model.modelId === modelId);
                form.setFieldsValue({
                  preferredProviderId: candidates[0]?.providerId,
                  backupProviderId: undefined,
                } as RouteRule);
              }}
            >
              {modelOptions.map((modelId) => (
                <Select.Option key={modelId} value={modelId} label={modelId}>
                  {modelId}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            label={t('routing.preferredProvider')}
            name="preferredProviderId"
            rules={[{ required: true, message: t('routing.providerRequired') }]}
          >
            <Select
              showSearch
              placeholder={t('routing.providerPlaceholder')}
              optionFilterProp="label"
            >
              {providerOptions.map((provider) => (
                <Select.Option
                  key={provider.value}
                  value={provider.value}
                  label={`${provider.label} ${provider.providerModelName || ''}`}
                >
                  {provider.label}
                  {provider.providerModelName ? ` (${provider.providerModelName})` : ''}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item label={t('routing.backupProvider')} name="backupProviderId">
            <Select
              allowClear
              showSearch
              placeholder={t('routing.backupProviderPlaceholder')}
              optionFilterProp="label"
            >
              {providerOptions
                .filter((provider) => provider.value !== preferredProviderId)
                .map((provider) => (
                  <Select.Option
                    key={provider.value}
                    value={provider.value}
                    label={`${provider.label} ${provider.providerModelName || ''}`}
                  >
                    {provider.label}
                    {provider.providerModelName ? ` (${provider.providerModelName})` : ''}
                  </Select.Option>
                ))}
            </Select>
          </Form.Item>
          <Form.Item
            label={t('routing.timeoutMs')}
            name="timeoutMs"
            rules={[{ required: true, message: t('routing.timeoutRequired') }]}
            extra={
              timeoutMsValue && Number(timeoutMsValue) > 0
                ? t('routing.timeoutHelp').replace('{s}', String(Number(timeoutMsValue) / 1000))
                : t('routing.timeoutHelpHint')
            }
          >
            <InputNumber<number>
              min={1000}
              max={600000}
              step={1000}
              style={{ width: '100%' }}
              formatter={(value) => (value ? `${Number(value).toLocaleString()}` : '')}
              parser={(value) => Number((value || '').replace(/[^\d]/g, ''))}
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">
              {t('common.submit')}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

export default RoutingAdminPage;
