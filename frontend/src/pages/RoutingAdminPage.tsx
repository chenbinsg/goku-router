import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, message, Card } from 'antd';
import { getModels, getProviders, getRouteRules, saveRouteRule } from '../api';
import { Model, Provider, RouteRule } from '../types';
import { useI18n } from '../i18n';

const RoutingAdminPage: React.FC = () => {
  const { t } = useI18n();
  const [routeRules, setRouteRules] = useState<RouteRule[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [loading, setLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingRoute, setEditingRoute] = useState<RouteRule | null>(null);
  const [form] = Form.useForm<RouteRule>();

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [routes, providerList, modelList] = await Promise.all([
          getRouteRules(),
          getProviders(),
          getModels(),
        ]);
        setRouteRules(routes);
        setProviders(providerList);
        setModels(modelList);
      } catch (error) {
        message.error(t('routing.loadFailed'));
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

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
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: unknown, record: RouteRule) => (
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
          form.setFieldsValue({ timeoutMs: 1500 } as RouteRule);
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
              placeholder={t('routing.modelPlaceholder')}
              showSearch
              optionFilterProp="label"
              disabled={!!editingRoute}
              options={Array.from(new Set(models.map((m) => m.modelId)))
                .sort()
                .map((modelId) => ({ value: modelId, label: modelId }))}
            />
          </Form.Item>
          <Form.Item
            label={t('routing.preferredProviderId')}
            name="preferredProviderId"
            rules={[{ required: true, message: t('routing.providerRequired') }]}
          >
            <Select
              placeholder={t('routing.providerPlaceholder')}
              showSearch
              optionFilterProp="label"
              options={providers
                .filter((p) => p.id !== undefined)
                .map((p) => ({ value: p.id, label: `${p.providerName} (#${p.id})` }))}
            />
          </Form.Item>
          <Form.Item label={t('routing.backupProviderId')} name="backupProviderId">
            <Select
              placeholder={t('routing.backupPlaceholder')}
              allowClear
              showSearch
              optionFilterProp="label"
              options={providers
                .filter((p) => p.id !== undefined)
                .map((p) => ({ value: p.id, label: `${p.providerName} (#${p.id})` }))}
            />
          </Form.Item>
          <Form.Item label={t('routing.timeoutMs')} name="timeoutMs">
            <Input />
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
