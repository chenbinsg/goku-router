import React, { useEffect, useState } from 'react';
import { Table, Button, Modal, Form, Input, Select, message, Card, Space, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { addModel, deleteModel, getModels, getProviders, updateModel } from '../api';
import { Model, Provider } from '../types';
import { useI18n } from '../i18n';

const ModelsAdminPage: React.FC = () => {
  const { t } = useI18n();
  const [models, setModels] = useState<Model[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [editingModel, setEditingModel] = useState<Model | null>(null);
  const [form] = Form.useForm<Model>();

  useEffect(() => {
    const fetchModels = async () => {
      setLoading(true);
      try {
        const [modelResponse, providerResponse] = await Promise.all([
          getModels(),
          getProviders(),
        ]);
        setModels(modelResponse);
        setProviders(providerResponse);
      } catch (error) {
        message.error(t('modelsAdmin.loadFailed'));
      } finally {
        setLoading(false);
      }
    };

    fetchModels();
  }, []);

  const columns = [
    {
      title: t('modelsList.modelId'),
      dataIndex: 'modelId',
      key: 'modelId',
    },
    {
      title: t('common.provider'),
      dataIndex: 'providerName',
      key: 'providerName',
    },
    {
      title: t('modelsAdmin.providerModel'),
      dataIndex: 'providerModelName',
      key: 'providerModelName',
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: unknown, record: Model) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => {
              setEditingModel(record);
              form.setFieldsValue(record);
              setIsModalVisible(true);
            }}
          >
            {t('common.edit')}
          </Button>
          <Popconfirm
            title="确认删除这条模型映射？"
            onConfirm={async () => {
              try {
                await deleteModel(record.id!);
                setModels((current) => current.filter((m) => m.id !== record.id));
                message.success('已删除');
              } catch {
                message.error('删除失败');
              }
            }}
            okText="删除"
            cancelText="取消"
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const formatError = (err: any): string => {
    const detail = err?.response?.data?.detail;
    if (!detail) return '操作失败';
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail.map((d: any) => `${d.loc?.slice(-1)[0] ?? ''}: ${d.msg}`).join('; ');
    }
    return JSON.stringify(detail);
  };

  const handleOk = async (values: Model) => {
    setSubmitting(true);
    try {
      if (editingModel?.id) {
        const updated = await updateModel({ ...editingModel, ...values });
        setModels((current) => current.map((item) => (item.id === updated.id ? updated : item)));
        message.success(t('modelsAdmin.updated'));
      } else {
        const created = await addModel(values);
        setModels((current) => [...current, created]);
        message.success(t('modelsAdmin.added'));
      }
      setIsModalVisible(false);
      setEditingModel(null);
      form.resetFields();
    } catch (err: any) {
      message.error(formatError(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Card title={t('modelsAdmin.title')}>
      <Button
        type="primary"
        icon={<PlusOutlined />}
        onClick={() => {
          setEditingModel(null);
          form.resetFields();
          form.setFieldsValue({ status: 'active' });
          setIsModalVisible(true);
        }}
        style={{ marginBottom: 16 }}
      >
        {t('modelsAdmin.add')}
      </Button>
      <Table
        dataSource={models.map((model) => ({ ...model, key: model.id || `${model.modelId}-${model.providerId}` }))}
        columns={columns}
        loading={loading}
        pagination={false}
      />
      <Modal
        title={editingModel ? t('modelsAdmin.edit') : t('modelsAdmin.add')}
        open={isModalVisible}
        onCancel={() => {
          if (submitting) return;
          setIsModalVisible(false);
          setEditingModel(null);
          form.resetFields();
        }}
        footer={null}
      >
        <Form form={form} layout="vertical" onFinish={handleOk}>
          <Form.Item name="id" hidden>
            <Input />
          </Form.Item>
          <Form.Item
            label={t('modelsList.modelId')}
            name="modelId"
            rules={[{ required: true, message: t('modelsAdmin.modelIdRequired') }]}
          >
            <Input placeholder="例如: gpt-4o, qwen3.6" />
          </Form.Item>
          <Form.Item
            label="Provider"
            name="providerId"
            rules={[{ required: true, message: t('modelsAdmin.providerIdRequired') }]}
          >
            <Select placeholder="选择 Provider" showSearch optionFilterProp="label">
              {providers.map((p) => (
                <Select.Option key={p.id} value={p.id} label={p.providerName}>
                  {p.providerName}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          <Form.Item
            label={t('modelsAdmin.providerModelName')}
            name="providerModelName"
            rules={[{ required: true, message: t('modelsAdmin.providerModelRequired') }]}
          >
            <Input placeholder="Provider 侧的实际模型名" />
          </Form.Item>
          <Form.Item name="status" hidden>
            <Input />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={submitting}>
              {t('common.submit')}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

export default ModelsAdminPage;
