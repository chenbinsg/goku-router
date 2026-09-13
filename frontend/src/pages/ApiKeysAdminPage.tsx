import React, { useEffect, useState } from 'react';
import { Alert, Button, Card, Form, Input, Modal, Popconfirm, Space, Table, Tag, Typography, message } from 'antd';

import { createRouterApiKey, deleteRouterApiKey, getOrganizations, getProjects, getRouterApiKeys, rotateRouterApiKey, updateRouterApiKey } from '../api';
import { useI18n } from '../i18n';
import { Organization, Project, RouterApiKey } from '../types';

const ApiKeysAdminPage: React.FC = () => {
  const { t } = useI18n();
  const [keys, setKeys] = useState<RouterApiKey[]>([]);
  const [loading, setLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [createdKey, setCreatedKey] = useState<RouterApiKey | null>(null);
  const [rotateModalOpen, setRotateModalOpen] = useState(false);
  const [rotatingKey, setRotatingKey] = useState<RouterApiKey | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [form] = Form.useForm();
  const [rotateForm] = Form.useForm();

  useEffect(() => {
    const fetchKeys = async () => {
      setLoading(true);
      try {
        const [routerKeys, orgs, projectList] = await Promise.all([
          getRouterApiKeys(),
          getOrganizations(),
          getProjects(),
        ]);
        setKeys(routerKeys);
        setOrganizations(orgs);
        setProjects(projectList);
      } catch {
        message.error(t('apiKeys.loadFailed'));
      } finally {
        setLoading(false);
      }
    };

    fetchKeys();
  }, [t]);

  const handleCreate = async (values: { name: string; organizationId?: string; projectId?: string; environment?: string; quotaRequests?: string; rpmLimit?: string; expiresAt?: string }) => {
    try {
      const created = await createRouterApiKey({
        name: values.name,
        organizationId: values.organizationId ? Number(values.organizationId) : undefined,
        projectId: values.projectId ? Number(values.projectId) : undefined,
        environment: values.environment || undefined,
        quotaRequests: values.quotaRequests ? Number(values.quotaRequests) : undefined,
        rpmLimit: values.rpmLimit ? Number(values.rpmLimit) : undefined,
        expiresAt: values.expiresAt || undefined,
      });
      setKeys((current) => [...current, created]);
      setCreatedKey(created);
      message.success(t('apiKeys.created'));
    } catch {
      message.error(t('apiKeys.createFailed'));
    }
  };

  const handleToggleStatus = async (record: RouterApiKey) => {
    try {
      const updated = await updateRouterApiKey({
        ...record,
        status: record.status === 'active' ? 'inactive' : 'active',
      });
      setKeys((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      message.success(t('apiKeys.updated'));
    } catch {
      message.error(t('apiKeys.updateFailed'));
    }
  };

  const handleDelete = async (record: RouterApiKey) => {
    try {
      await deleteRouterApiKey(record.id);
      setKeys((current) => current.filter((item) => item.id !== record.id));
      message.success('已删除');
    } catch (err: any) {
      const detail = err?.response?.data?.detail || '';
      message.error(detail.includes('CANNOT_DELETE_ACTIVE_KEY') ? '请先停用该 Key 再删除' : '删除失败');
    }
  };

  const handleRotate = async (values: { name?: string; quotaRequests?: string; expiresAt?: string }) => {
    if (!rotatingKey) {
      return;
    }
    try {
      const created = await rotateRouterApiKey(rotatingKey, {
        name: values.name || undefined,
        quotaRequests: values.quotaRequests ? Number(values.quotaRequests) : undefined,
        expiresAt: values.expiresAt || undefined,
      });
      setKeys((current) => current.map((item) => (
        item.id === rotatingKey.id
          ? { ...item, status: 'rotated' }
          : item
      )).concat(created));
      setCreatedKey(created);
      setRotateModalOpen(false);
      setRotatingKey(null);
      rotateForm.resetFields();
      message.success(t('apiKeys.rotated'));
    } catch {
      message.error(t('apiKeys.rotateFailed'));
    }
  };

  return (
    <Card title={t('apiKeys.title')}>
      <Button type="primary" onClick={() => setIsModalVisible(true)} style={{ marginBottom: 16 }}>
        {t('apiKeys.create')}
      </Button>
      <Table
        dataSource={keys.map((item) => ({ ...item, key: item.id }))}
        loading={loading}
        pagination={false}
        columns={[
          { title: 'ID', dataIndex: 'id', key: 'id' },
          { title: t('apiKeys.name'), dataIndex: 'name', key: 'name' },
          { title: t('apiKeys.prefix'), dataIndex: 'keyPrefix', key: 'keyPrefix' },
          { title: t('apiKeys.organizationId'), dataIndex: 'organizationId', key: 'organizationId' },
          { title: t('apiKeys.projectId'), dataIndex: 'projectId', key: 'projectId' },
          { title: t('apiKeys.environment'), dataIndex: 'environment', key: 'environment', render: (value?: string) => value || 'N/A' },
          { title: t('apiKeys.quotaRequests'), dataIndex: 'quotaRequests', key: 'quotaRequests' },
          { title: '每分钟上限(RPM)', dataIndex: 'rpmLimit', key: 'rpmLimit', render: (value?: number) => (value ?? '不限') },
          { title: t('apiKeys.requestCount'), dataIndex: 'requestCount', key: 'requestCount' },
          { title: t('apiKeys.expiresAt'), dataIndex: 'expiresAt', key: 'expiresAt', render: (value?: string) => value || 'N/A' },
          {
            title: t('common.status'),
            dataIndex: 'status',
            key: 'status',
            sorter: (a: RouterApiKey, b: RouterApiKey) => a.status.localeCompare(b.status),
            defaultSortOrder: 'ascend' as const,  // 'active' sorts before 'inactive'/'rotated'
            render: (value: string) => {
              const color = value === 'active' ? 'green' : value === 'rotated' ? 'gold' : 'default';
              return <Tag color={color}>{value}</Tag>;
            },
          },
          {
            title: t('common.actions'),
            key: 'actions',
            render: (_: unknown, record: RouterApiKey) => (
              <Space>
                <Button type="link" onClick={() => handleToggleStatus(record)}>
                  {record.status === 'active' ? t('apiKeys.disable') : t('apiKeys.enable')}
                </Button>
                <Button
                  type="link"
                  onClick={() => {
                    setRotatingKey(record);
                    rotateForm.setFieldsValue({
                      name: `${record.name}-rotated`,
                      quotaRequests: record.quotaRequests,
                      expiresAt: record.expiresAt,
                    });
                    setRotateModalOpen(true);
                  }}
                >
                  {t('apiKeys.rotate')}
                </Button>
                {record.status === 'active' ? (
                  <Button type="link" danger disabled title="请先停用该 Key 再删除">
                    删除
                  </Button>
                ) : (
                  <Popconfirm
                    title="删除该 API Key?"
                    description="此操作不可撤销。历史日志不受影响。"
                    okText="删除"
                    okButtonProps={{ danger: true }}
                    cancelText="取消"
                    onConfirm={() => handleDelete(record)}
                  >
                    <Button type="link" danger>删除</Button>
                  </Popconfirm>
                )}
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={t('apiKeys.create')}
        open={isModalVisible}
        onCancel={() => {
          setIsModalVisible(false);
          setCreatedKey(null);
        }}
        footer={null}
      >
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Form.Item
            label={t('apiKeys.name')}
            name="name"
            rules={[{ required: true, message: t('apiKeys.nameRequired') }]}
          >
            <Input placeholder="customer-team-a" />
          </Form.Item>
          <Form.Item label={t('apiKeys.organizationId')} name="organizationId">
            <Input placeholder={organizations.map((item) => `${item.id}:${item.name}`).join(', ')} />
          </Form.Item>
          <Form.Item label={t('apiKeys.projectId')} name="projectId">
            <Input placeholder={projects.map((item) => `${item.id}:${item.name}`).join(', ')} />
          </Form.Item>
          <Form.Item label={t('apiKeys.environment')} name="environment">
            <Input placeholder="prod / staging / dev" />
          </Form.Item>
          <Form.Item label={t('apiKeys.quotaRequests')} name="quotaRequests">
            <Input placeholder="1000" />
          </Form.Item>
          <Form.Item label="每分钟上限 (RPM)" name="rpmLimit" tooltip="每分钟最多请求数,超出返回 429;留空表示不限速">
            <Input placeholder="60" />
          </Form.Item>
          <Form.Item label={t('apiKeys.expiresAt')} name="expiresAt">
            <Input placeholder="2026-12-31T23:59:59+09:00" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">
              {t('common.submit')}
            </Button>
          </Form.Item>
        </Form>
        {createdKey?.plainApiKey && (
          <Alert
            type="warning"
            showIcon
            message={t('apiKeys.copyNow')}
            description={
              <Space direction="vertical" size={8}>
                <Typography.Text code copyable>
                  {createdKey.plainApiKey}
                </Typography.Text>
              </Space>
            }
          />
        )}
      </Modal>
      <Modal
        title={t('apiKeys.rotate')}
        open={rotateModalOpen}
        onCancel={() => {
          setRotateModalOpen(false);
          setRotatingKey(null);
          rotateForm.resetFields();
        }}
        footer={null}
      >
        <Form form={rotateForm} layout="vertical" onFinish={handleRotate}>
          <Form.Item label={t('apiKeys.name')} name="name">
            <Input placeholder="customer-team-a-rotated" />
          </Form.Item>
          <Form.Item label={t('apiKeys.quotaRequests')} name="quotaRequests">
            <Input placeholder="1000" />
          </Form.Item>
          <Form.Item label={t('apiKeys.expiresAt')} name="expiresAt">
            <Input placeholder="2026-12-31T23:59:59+09:00" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">
              {t('apiKeys.rotate')}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

export default ApiKeysAdminPage;
