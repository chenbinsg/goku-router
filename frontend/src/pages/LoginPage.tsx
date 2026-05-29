import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, Alert, Space } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { setTokens } from '../utils/auth';

const { Title, Text } = Typography;

const rollingKeyframes = `
@keyframes rollLR {
  0%   { left: -60px;  transform: rotate(0deg);   }
  48%  { left: calc(100vw + 60px); transform: rotate(1080deg); }
  50%  { left: calc(100vw + 60px); transform: rotate(1080deg) scaleX(-1); }
  98%  { left: -60px;  transform: rotate(0deg)    scaleX(-1); }
  100% { left: -60px;  transform: rotate(0deg);   }
}
`;

const BACKEND =
  (import.meta as any).env?.VITE_BACKEND_URL ??
  `http://localhost:${(import.meta as any).env?.VITE_BACKEND_PORT || '8159'}`;

const LoginPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await axios.post(`${BACKEND}/auth/login`, {
        username: values.username,
        password: values.password,
      });
      const { access_token, refresh_token, username, role } = resp.data;
      setTokens(access_token, refresh_token, username, role);
      navigate('/admin/dashboard', { replace: true });
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ||
        err?.message ||
        'Login failed. Check your credentials.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)',
        overflow: 'hidden',
      }}
    >
      <style>{rollingKeyframes}</style>
      {/* Rolling monkey */}
      <img
        src="/logo.png"
        alt=""
        style={{
          position: 'fixed',
          bottom: 16,
          left: -60,
          width: 52,
          height: 52,
          objectFit: 'contain',
          objectPosition: 'center',
          animation: 'rollLR 8s linear infinite',
          pointerEvents: 'none',
          zIndex: 0,
        }}
      />
      <Card
        style={{
          width: 400,
          borderRadius: 12,
          boxShadow: '0 20px 60px rgba(0,0,0,0.4)',
        }}
      >
        <Space direction="vertical" size={24} style={{ width: '100%' }}>
          <div style={{ textAlign: 'center' }}>
            <img
              src="/logo.png"
              alt="Goku-Router"
              style={{ width: 220, objectFit: 'contain', marginBottom: 8 }}
            />
            <div>
              <Text type="secondary">Admin Console</Text>
            </div>
          </div>

          {error && (
            <Alert
              message={error}
              type="error"
              showIcon
              closable
              onClose={() => setError(null)}
            />
          )}

          <Form
            name="login"
            onFinish={onFinish}
            autoComplete="off"
            size="large"
          >
            <Form.Item
              name="username"
              rules={[{ required: true, message: 'Please enter your username' }]}
            >
              <Input
                prefix={<UserOutlined style={{ color: '#bfbfbf' }} />}
                placeholder="Username"
              />
            </Form.Item>

            <Form.Item
              name="password"
              rules={[{ required: true, message: 'Please enter your password' }]}
            >
              <Input.Password
                prefix={<LockOutlined style={{ color: '#bfbfbf' }} />}
                placeholder="Password"
              />
            </Form.Item>

            <Form.Item style={{ marginBottom: 0 }}>
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                block
                style={{ height: 44 }}
              >
                Sign In
              </Button>
            </Form.Item>
          </Form>

          <Text type="secondary" style={{ display: 'block', textAlign: 'center', fontSize: 11, opacity: 0.5 }}>
            v1.4.1
          </Text>
        </Space>
      </Card>
    </div>
  );
};

export default LoginPage;
