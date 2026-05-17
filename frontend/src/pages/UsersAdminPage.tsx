import React, { useEffect, useState } from 'react';
import {
  Table, Button, Modal, Form, Input, Select, Switch,
  Tag, Space, Popconfirm, message, Card, Typography,
} from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, UserOutlined } from '@ant-design/icons';
import {
  getAdminUsers, createAdminUser, updateAdminUser, deleteAdminUser,
  type AdminUser,
} from '../api';
import { getUser } from '../utils/auth';

const { Text } = Typography;

const ROLE_COLOR: Record<string, string> = {
  superadmin: 'red',
  admin: 'blue',
  viewer: 'default',
};

const UsersAdminPage: React.FC = () => {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<AdminUser | null>(null);
  const [form] = Form.useForm();
  const currentUser = getUser();
  const isSuperadmin = currentUser?.role === 'superadmin';

  const fetchUsers = async () => {
    setLoading(true);
    try {
      setUsers(await getAdminUsers());
    } catch {
      message.error('Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchUsers(); }, []);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ role: 'admin', is_active: true });
    setModalOpen(true);
  };

  const openEdit = (user: AdminUser) => {
    setEditing(user);
    form.setFieldsValue({ email: user.email, role: user.role, is_active: user.is_active });
    setModalOpen(true);
  };

  const handleSubmit = async (values: any) => {
    try {
      if (editing) {
        const updated = await updateAdminUser(editing.id, {
          email: values.email,
          role: values.role,
          is_active: values.is_active,
        });
        setUsers(prev => prev.map(u => u.id === updated.id ? updated : u));
        message.success('User updated');
      } else {
        const created = await createAdminUser({
          username: values.username,
          password: values.password,
          email: values.email,
          role: values.role,
        });
        setUsers(prev => [...prev, created]);
        message.success('User created');
      }
      setModalOpen(false);
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? 'Operation failed');
    }
  };

  const handleDelete = async (user: AdminUser) => {
    try {
      await deleteAdminUser(user.id);
      setUsers(prev => prev.filter(u => u.id !== user.id));
      message.success(`User "${user.username}" deleted`);
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? 'Delete failed');
    }
  };

  const columns = [
    {
      title: 'Username',
      dataIndex: 'username',
      key: 'username',
      render: (name: string, record: AdminUser) => (
        <Space>
          <UserOutlined style={{ color: '#1677ff' }} />
          <Text strong>{name}</Text>
          {record.username === currentUser?.username && (
            <Tag color="green" style={{ fontSize: 11 }}>me</Tag>
          )}
        </Space>
      ),
    },
    {
      title: 'Email',
      dataIndex: 'email',
      key: 'email',
      render: (v: string) => v ?? <Text type="secondary">—</Text>,
    },
    {
      title: 'Role',
      dataIndex: 'role',
      key: 'role',
      render: (role: string) => <Tag color={ROLE_COLOR[role] ?? 'default'}>{role}</Tag>,
    },
    {
      title: 'Status',
      dataIndex: 'is_active',
      key: 'is_active',
      render: (active: boolean) =>
        active
          ? <Tag color="success">Active</Tag>
          : <Tag color="error">Inactive</Tag>,
    },
    {
      title: 'Last Login',
      dataIndex: 'last_login_at',
      key: 'last_login_at',
      render: (v: string) => v
        ? new Date(v).toLocaleString()
        : <Text type="secondary">Never</Text>,
    },
    {
      title: 'Created',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v: string) => new Date(v).toLocaleDateString(),
    },
    {
      title: 'Actions',
      key: 'actions',
      render: (_: any, record: AdminUser) => (
        <Space>
          <Button
            size="small"
            icon={<EditOutlined />}
            disabled={!isSuperadmin}
            onClick={() => openEdit(record)}
          >
            Edit
          </Button>
          <Popconfirm
            title={`Delete user "${record.username}"?`}
            description="This action cannot be undone."
            onConfirm={() => handleDelete(record)}
            okText="Delete"
            okButtonProps={{ danger: true }}
            cancelText="Cancel"
            disabled={!isSuperadmin || record.username === currentUser?.username}
          >
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              disabled={!isSuperadmin || record.username === currentUser?.username}
            >
              Delete
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="User Management"
      extra={
        isSuperadmin && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            Add User
          </Button>
        )
      }
    >
      {!isSuperadmin && (
        <Text type="secondary" style={{ display: 'block', marginBottom: 12 }}>
          You have read-only access. Superadmin role is required to create, edit, or delete users.
        </Text>
      )}

      <Table
        dataSource={users.map(u => ({ ...u, key: u.id }))}
        columns={columns}
        loading={loading}
        pagination={{ pageSize: 20 }}
      />

      <Modal
        title={editing ? `Edit user: ${editing.username}` : 'Create New User'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        footer={null}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit} style={{ marginTop: 16 }}>
          {!editing && (
            <>
              <Form.Item
                label="Username"
                name="username"
                rules={[{ required: true, message: 'Username is required' }]}
              >
                <Input prefix={<UserOutlined />} placeholder="e.g. alice" />
              </Form.Item>
              <Form.Item
                label="Password"
                name="password"
                rules={[{ required: true, message: 'Password is required' }, { min: 6, message: 'At least 6 characters' }]}
              >
                <Input.Password placeholder="Min 6 characters" />
              </Form.Item>
            </>
          )}

          <Form.Item label="Email" name="email">
            <Input placeholder="optional" />
          </Form.Item>

          <Form.Item
            label="Role"
            name="role"
            rules={[{ required: true }]}
          >
            <Select>
              <Select.Option value="superadmin">
                <Tag color="red">superadmin</Tag> — full access incl. user management
              </Select.Option>
              <Select.Option value="admin">
                <Tag color="blue">admin</Tag> — all admin APIs except user management
              </Select.Option>
              <Select.Option value="viewer">
                <Tag color="default">viewer</Tag> — read-only access
              </Select.Option>
            </Select>
          </Form.Item>

          {editing && (
            <Form.Item label="Active" name="is_active" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}

          <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
            <Space>
              <Button onClick={() => setModalOpen(false)}>Cancel</Button>
              <Button type="primary" htmlType="submit">
                {editing ? 'Save Changes' : 'Create User'}
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
};

export default UsersAdminPage;
