import React, { useEffect, useState } from 'react';
import {
  Table, Button, Modal, Form, Input, Select, Switch,
  Tag, Space, Popconfirm, message, Card, Typography, Tooltip,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined,
  KeyOutlined, EyeInvisibleOutlined, CheckCircleOutlined, StopOutlined,
} from '@ant-design/icons';
import {
  getByokKeys, createByokKey, updateByokKey, deleteByokKey,
  type ByokKeyItem,
} from '../api';

const { Text } = Typography;

const PROVIDER_OPTIONS = [
  { value: 'openai',    label: 'OpenAI',        color: 'green' },
  { value: 'anthropic', label: 'Anthropic',     color: 'orange' },
  { value: 'gemini',   label: 'Google Gemini',  color: 'blue' },
  { value: 'azure',    label: 'Azure OpenAI',   color: 'geekblue' },
  { value: 'deepseek', label: 'DeepSeek',       color: 'purple' },
  { value: 'mistral',  label: 'Mistral',        color: 'cyan' },
  { value: 'cohere',   label: 'Cohere',         color: 'magenta' },
  { value: 'custom',   label: 'Custom',         color: 'default' },
];

const providerColor = (p: string) =>
  PROVIDER_OPTIONS.find(o => o.value === p)?.color ?? 'default';

const providerLabel = (p: string) =>
  PROVIDER_OPTIONS.find(o => o.value === p)?.label ?? p;

const ByokAdminPage: React.FC = () => {
  const [keys, setKeys] = useState<ByokKeyItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<ByokKeyItem | null>(null);
  const [form] = Form.useForm();

  const fetchKeys = async () => {
    setLoading(true);
    try {
      setKeys(await getByokKeys());
    } catch {
      message.error('加载 BYOK Keys 失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchKeys(); }, []);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (record: ByokKeyItem) => {
    setEditing(record);
    form.setFieldsValue({
      label: record.label,
      provider: record.provider,
      org_label: record.org_label,
      project_label: record.project_label,
      description: record.description,
      is_active: record.is_active,
    });
    setModalOpen(true);
  };

  const handleSubmit = async (values: any) => {
    try {
      if (editing) {
        const updated = await updateByokKey(editing.id, {
          label: values.label,
          is_active: values.is_active,
          description: values.description,
          org_label: values.org_label,
          project_label: values.project_label,
        });
        setKeys(prev => prev.map(k => k.id === updated.id ? updated : k));
        message.success('已更新');
      } else {
        const created = await createByokKey({
          label: values.label,
          provider: values.provider,
          api_key: values.api_key,
          org_label: values.org_label,
          project_label: values.project_label,
          description: values.description,
        });
        setKeys(prev => [created, ...prev]);
        message.success('Key 已添加');
      }
      setModalOpen(false);
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '操作失败');
    }
  };

  const handleToggle = async (record: ByokKeyItem) => {
    try {
      const updated = await updateByokKey(record.id, { is_active: !record.is_active });
      setKeys(prev => prev.map(k => k.id === updated.id ? updated : k));
      message.success(updated.is_active ? '已启用' : '已停用');
    } catch {
      message.error('操作失败');
    }
  };

  const handleDelete = async (record: ByokKeyItem) => {
    try {
      await deleteByokKey(record.id);
      setKeys(prev => prev.filter(k => k.id !== record.id));
      message.success(`"${record.label}" 已删除`);
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '删除失败');
    }
  };

  const columns = [
    {
      title: '名称',
      dataIndex: 'label',
      key: 'label',
      render: (v: string) => (
        <Space>
          <KeyOutlined style={{ color: '#1677ff' }} />
          <Text strong>{v}</Text>
        </Space>
      ),
    },
    {
      title: 'Provider',
      dataIndex: 'provider',
      key: 'provider',
      render: (v: string) => <Tag color={providerColor(v)}>{providerLabel(v)}</Tag>,
    },
    {
      title: 'API Key',
      dataIndex: 'key_preview',
      key: 'key_preview',
      render: (v: string) => (
        <Space>
          <EyeInvisibleOutlined style={{ color: '#8c8c8c' }} />
          <Text code style={{ fontSize: 12 }}>{v}</Text>
        </Space>
      ),
    },
    {
      title: '组织 / 项目',
      key: 'scope',
      render: (_: any, r: ByokKeyItem) => (
        <Space size={4}>
          {r.org_label && <Tag>{r.org_label}</Tag>}
          {r.project_label && <Tag color="blue">{r.project_label}</Tag>}
          {!r.org_label && !r.project_label && <Text type="secondary">全局</Text>}
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (v: boolean) => v
        ? <Tag icon={<CheckCircleOutlined />} color="success">启用</Tag>
        : <Tag icon={<StopOutlined />} color="error">停用</Tag>,
    },
    {
      title: '最后使用',
      dataIndex: 'last_used_at',
      key: 'last_used_at',
      render: (v: string) => v
        ? new Date(v).toLocaleString()
        : <Text type="secondary">从未</Text>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v: string) => new Date(v).toLocaleDateString(),
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: ByokKeyItem) => (
        <Space>
          <Tooltip title={record.is_active ? '停用' : '启用'}>
            <Switch
              size="small"
              checked={record.is_active}
              onChange={() => handleToggle(record)}
            />
          </Tooltip>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title={`删除 "${record.label}"？`}
            description="此操作不可撤销，路由中使用此 Key 的请求将失败。"
            onConfirm={() => handleDelete(record)}
            okText="删除"
            okButtonProps={{ danger: true }}
            cancelText="取消"
          >
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="BYOK Key 管理"
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          添加 Key
        </Button>
      }
    >
      <Table
        dataSource={keys.map(k => ({ ...k, key: k.id }))}
        columns={columns}
        loading={loading}
        pagination={{ pageSize: 20 }}
      />

      <Modal
        title={editing ? `编辑：${editing.label}` : '添加 BYOK Key'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={null}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit} style={{ marginTop: 16 }}>
          <Form.Item
            label="名称"
            name="label"
            rules={[{ required: true, message: '请输入名称' }]}
          >
            <Input placeholder="例：生产环境 OpenAI Key" />
          </Form.Item>

          {!editing && (
            <>
              <Form.Item
                label="Provider"
                name="provider"
                rules={[{ required: true, message: '请选择 Provider' }]}
              >
                <Select placeholder="选择 Provider">
                  {PROVIDER_OPTIONS.map(o => (
                    <Select.Option key={o.value} value={o.value}>
                      <Tag color={o.color}>{o.label}</Tag>
                    </Select.Option>
                  ))}
                </Select>
              </Form.Item>

              <Form.Item
                label="API Key"
                name="api_key"
                rules={[{ required: true, message: '请输入 API Key' }]}
                extra="Key 仅用于路由调用，界面只展示前8位和后4位"
              >
                <Input.Password placeholder="sk-..." />
              </Form.Item>
            </>
          )}

          <Form.Item label="组织" name="org_label">
            <Input placeholder="可选，留空表示全局生效" />
          </Form.Item>

          <Form.Item label="项目" name="project_label">
            <Input placeholder="可选，指定该 Key 只用于某个项目" />
          </Form.Item>

          <Form.Item label="备注" name="description">
            <Input.TextArea rows={2} placeholder="可选" />
          </Form.Item>

          {editing && (
            <Form.Item label="启用" name="is_active" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setModalOpen(false)}>取消</Button>
              <Button type="primary" htmlType="submit">
                {editing ? '保存' : '添加'}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

export default ByokAdminPage;
