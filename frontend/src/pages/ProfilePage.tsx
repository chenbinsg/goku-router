import React, { useEffect, useState } from 'react';
import {
  Card, Form, Input, Button, Tag, Descriptions, Space,
  message, Modal, Divider, Typography, Skeleton, Select,
} from 'antd';
import { UserOutlined, LockOutlined, MailOutlined, SaveOutlined, GlobalOutlined } from '@ant-design/icons';
import { getMyProfile, updateMyEmail, updateMyTimezone, changeMyPassword, type AdminUser } from '../api';

const COMMON_TIMEZONES = [
  { label: 'UTC', value: 'UTC' },
  { label: 'Asia/Tokyo (JST, UTC+9)', value: 'Asia/Tokyo' },
  { label: 'Asia/Shanghai (CST, UTC+8)', value: 'Asia/Shanghai' },
  { label: 'Asia/Singapore (SGT, UTC+8)', value: 'Asia/Singapore' },
  { label: 'Asia/Seoul (KST, UTC+9)', value: 'Asia/Seoul' },
  { label: 'America/New_York (EST/EDT)', value: 'America/New_York' },
  { label: 'America/Los_Angeles (PST/PDT)', value: 'America/Los_Angeles' },
  { label: 'Europe/London (GMT/BST)', value: 'Europe/London' },
  { label: 'Europe/Paris (CET/CEST)', value: 'Europe/Paris' },
];
import { getUser, setTokens, getAccessToken, getRefreshToken } from '../utils/auth';

const { Title, Text } = Typography;

const ROLE_COLOR: Record<string, string> = {
  superadmin: 'red',
  admin: 'blue',
  viewer: 'default',
};

const ProfilePage: React.FC = () => {
  const [profile, setProfile] = useState<AdminUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [emailForm] = Form.useForm();
  const [pwForm] = Form.useForm();
  const [savingEmail, setSavingEmail] = useState(false);
  const [savingPw, setSavingPw] = useState(false);
  const [savingTz, setSavingTz] = useState(false);
  const [pwModalOpen, setPwModalOpen] = useState(false);

  useEffect(() => {
    getMyProfile()
      .then(data => {
        setProfile(data);
        emailForm.setFieldsValue({ email: data.email ?? '' });
      })
      .catch(() => message.error('加载个人资料失败'))
      .finally(() => setLoading(false));
  }, [emailForm]);

  const handleEmailSave = async (values: { email: string }) => {
    setSavingEmail(true);
    try {
      const updated = await updateMyEmail(values.email);
      setProfile(updated);
      // sync auth store so header shows fresh info
      const cur = getUser();
      if (cur) {
        setTokens(
          getAccessToken()!,
          getRefreshToken()!,
          cur.username,
          cur.role,
        );
      }
      message.success('邮箱已更新');
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '更新失败');
    } finally {
      setSavingEmail(false);
    }
  };

  const handleTimezoneSave = async (tz: string) => {
    setSavingTz(true);
    try {
      const updated = await updateMyTimezone(tz);
      setProfile(updated);
      message.success('时区已更新');
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '更新失败');
    } finally {
      setSavingTz(false);
    }
  };

  const handlePasswordSave = async (values: {
    current_password: string;
    new_password: string;
    confirm_password: string;
  }) => {
    if (values.new_password !== values.confirm_password) {
      message.error('两次输入的新密码不一致');
      return;
    }
    setSavingPw(true);
    try {
      await changeMyPassword({
        current_password: values.current_password,
        new_password: values.new_password,
      });
      message.success('密码已修改，请重新登录');
      pwForm.resetFields();
      setPwModalOpen(false);
    } catch (err: any) {
      message.error(err?.response?.data?.detail ?? '密码修改失败');
    } finally {
      setSavingPw(false);
    }
  };

  if (loading) return <Card><Skeleton active /></Card>;
  if (!profile) return null;

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={24}>
      {/* 基本信息 */}
      <Card title="个人资料">
        <Descriptions column={2} bordered size="middle">
          <Descriptions.Item label="用户名">
            <Space>
              <UserOutlined />
              <Text strong>{profile.username}</Text>
            </Space>
          </Descriptions.Item>
          <Descriptions.Item label="角色">
            <Tag color={ROLE_COLOR[profile.role] ?? 'default'}>{profile.role}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            {profile.is_active
              ? <Tag color="success">启用</Tag>
              : <Tag color="error">禁用</Tag>}
          </Descriptions.Item>
          <Descriptions.Item label="注册时间">
            {new Date(profile.created_at).toLocaleString()}
          </Descriptions.Item>
          <Descriptions.Item label="最后登录" span={2}>
            {profile.last_login_at
              ? new Date(profile.last_login_at).toLocaleString()
              : <Text type="secondary">从未登录</Text>}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 修改邮箱 */}
      <Card title="邮箱设置">
        <Form
          form={emailForm}
          layout="inline"
          onFinish={handleEmailSave}
          style={{ maxWidth: 480 }}
        >
          <Form.Item name="email" style={{ flex: 1 }}>
            <Input
              prefix={<MailOutlined />}
              placeholder="输入新邮箱（可选）"
              type="email"
            />
          </Form.Item>
          <Form.Item>
            <Button
              type="primary"
              htmlType="submit"
              icon={<SaveOutlined />}
              loading={savingEmail}
            >
              保存
            </Button>
          </Form.Item>
        </Form>
      </Card>

      {/* 时区设置 */}
      <Card title={<Space><GlobalOutlined />时区设置</Space>}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            选择你的本地时区，日志和报表时间将按此时区显示。
            当前设置：<strong>{profile.timezone ?? 'UTC'}</strong>
          </Typography.Text>
          <Space>
            <Select
              defaultValue={profile.timezone ?? 'UTC'}
              style={{ width: 320 }}
              options={COMMON_TIMEZONES}
              onChange={handleTimezoneSave}
              loading={savingTz}
            />
          </Space>
        </Space>
      </Card>

      {/* 修改密码 */}
      <Card title="安全设置">
        <Button
          icon={<LockOutlined />}
          onClick={() => { pwForm.resetFields(); setPwModalOpen(true); }}
        >
          修改密码
        </Button>

        <Modal
          title="修改密码"
          open={pwModalOpen}
          onCancel={() => setPwModalOpen(false)}
          footer={null}
          destroyOnClose
        >
          <Form
            form={pwForm}
            layout="vertical"
            onFinish={handlePasswordSave}
            style={{ marginTop: 16 }}
          >
            <Form.Item
              label="当前密码"
              name="current_password"
              rules={[{ required: true, message: '请输入当前密码' }]}
            >
              <Input.Password prefix={<LockOutlined />} />
            </Form.Item>
            <Divider />
            <Form.Item
              label="新密码"
              name="new_password"
              rules={[
                { required: true, message: '请输入新密码' },
                { min: 6, message: '至少 6 位' },
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="至少 6 位" />
            </Form.Item>
            <Form.Item
              label="确认新密码"
              name="confirm_password"
              rules={[{ required: true, message: '请再次输入新密码' }]}
            >
              <Input.Password prefix={<LockOutlined />} />
            </Form.Item>
            <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
              <Space>
                <Button onClick={() => setPwModalOpen(false)}>取消</Button>
                <Button type="primary" htmlType="submit" loading={savingPw}>
                  确认修改
                </Button>
              </Space>
            </Form.Item>
          </Form>
        </Modal>
      </Card>
    </Space>
  );
};

export default ProfilePage;
