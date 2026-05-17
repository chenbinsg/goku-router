import React, { Suspense, lazy } from 'react';
import { Layout, Menu, Segmented, Space, Typography, Button, Avatar, Dropdown } from 'antd';
import { Route, Routes, Link, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { UserOutlined, LogoutOutlined } from '@ant-design/icons';
import { useI18n } from './i18n';
import { isAuthenticated, getUser, clearTokens } from './utils/auth';

const { Header, Content, Sider } = Layout;

const ChatCompletionsPage   = lazy(() => import('./pages/ChatCompletionsPage'));
const EmbeddingsPage        = lazy(() => import('./pages/EmbeddingsPage'));
const ModelsListPage        = lazy(() => import('./pages/ModelsListPage'));
const ModelsAdminPage       = lazy(() => import('./pages/ModelsAdminPage'));
const ProvidersAdminPage    = lazy(() => import('./pages/ProvidersAdminPage'));
const RoutingAdminPage      = lazy(() => import('./pages/RoutingAdminPage'));
const ByokAdminPage         = lazy(() => import('./pages/ByokAdminPage'));
const CreditsAdminPage      = lazy(() => import('./pages/CreditsAdminPage'));
const BillingAdminPage      = lazy(() => import('./pages/BillingAdminPage'));
const SecurityAdminPage     = lazy(() => import('./pages/SecurityAdminPage'));
const LogsAdminPage         = lazy(() => import('./pages/LogsAdminPage'));
const DashboardAdminPage    = lazy(() => import('./pages/DashboardAdminPage'));
const NotificationsAdminPage = lazy(() => import('./pages/NotificationsAdminPage'));
const ApiKeysAdminPage      = lazy(() => import('./pages/ApiKeysAdminPage'));
const LoginPage             = lazy(() => import('./pages/LoginPage'));

/** Redirect to /login if not authenticated */
const RequireAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  if (!isAuthenticated()) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
};

const App: React.FC = () => {
  const { locale, setLocale, t } = useI18n();
  const navigate = useNavigate();
  const user = getUser();

  const handleLogout = () => {
    clearTokens();
    navigate('/login', { replace: true });
  };

  const userMenuItems = [
    {
      key: 'user',
      label: (
        <span>
          <strong>{user?.username}</strong>
          <span style={{ marginLeft: 8, color: '#8c8c8c', fontSize: 12 }}>
            [{user?.role}]
          </span>
        </span>
      ),
      disabled: true,
    },
    { type: 'divider' as const },
    {
      key: 'logout',
      icon: <LogoutOutlined />,
      label: 'Sign out',
      onClick: handleLogout,
    },
  ];

  // Show bare login page without sidebar/header chrome
  if (!isAuthenticated()) {
    return (
      <Suspense fallback={<div style={{ padding: 24 }}>Loading…</div>}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Suspense>
    );
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #2a2a3e', textAlign: 'center' }}>
          <img src="/logo.png" alt="Goku-Router" style={{ width: '100%', maxWidth: 160, objectFit: 'contain' }} />
        </div>
        <Menu theme="dark" mode="inline">
          <Menu.Item key="1"><Link to="/v1/chat/completions">{t('nav.chat')}</Link></Menu.Item>
          <Menu.Item key="2"><Link to="/v1/embeddings">{t('nav.embeddings')}</Link></Menu.Item>
          <Menu.Item key="3"><Link to="/v1/models">{t('nav.modelsList')}</Link></Menu.Item>
          <Menu.Item key="4"><Link to="/admin/models">{t('nav.modelsAdmin')}</Link></Menu.Item>
          <Menu.Item key="5"><Link to="/admin/providers">{t('nav.providersAdmin')}</Link></Menu.Item>
          <Menu.Item key="6"><Link to="/admin/routing">{t('nav.routingAdmin')}</Link></Menu.Item>
          <Menu.Item key="7"><Link to="/admin/byok">{t('nav.byokAdmin')}</Link></Menu.Item>
          <Menu.Item key="8"><Link to="/admin/credits">{t('nav.creditsAdmin')}</Link></Menu.Item>
          <Menu.Item key="9"><Link to="/admin/billing">{t('nav.billingAdmin')}</Link></Menu.Item>
          <Menu.Item key="10"><Link to="/admin/security">{t('nav.securityAdmin')}</Link></Menu.Item>
          <Menu.Item key="11"><Link to="/admin/logs">{t('nav.logsAdmin')}</Link></Menu.Item>
          <Menu.Item key="12"><Link to="/admin/dashboard">{t('nav.dashboardAdmin')}</Link></Menu.Item>
          <Menu.Item key="13"><Link to="/admin/notifications">{t('nav.notificationsAdmin')}</Link></Menu.Item>
          <Menu.Item key="14"><Link to="/admin/api-keys">{t('nav.apiKeysAdmin')}</Link></Menu.Item>
        </Menu>
      </Sider>

      <Layout>
        <Header style={{ background: '#fff', padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 16 }}>
          <Space size={12}>
            <Typography.Text>{t('header.language')}</Typography.Text>
            <Segmented
              value={locale}
              onChange={(value) => setLocale(value as 'en' | 'zh')}
              options={[
                { label: t('lang.en'), value: 'en' },
                { label: t('lang.zh'), value: 'zh' },
              ]}
            />
          </Space>

          <Dropdown menu={{ items: userMenuItems }} placement="bottomRight">
            <Button type="text" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Avatar size="small" icon={<UserOutlined />} style={{ background: '#1677ff' }} />
              <Typography.Text strong>{user?.username}</Typography.Text>
            </Button>
          </Dropdown>
        </Header>

        <Content style={{ margin: '0 16px' }}>
          <Suspense fallback={<div style={{ padding: 24 }}>{t('common.loading')}</div>}>
            <Routes>
              <Route path="/login" element={<Navigate to="/admin/dashboard" replace />} />
              <Route path="/v1/chat/completions"  element={<ChatCompletionsPage />} />
              <Route path="/v1/embeddings"        element={<EmbeddingsPage />} />
              <Route path="/v1/models"            element={<ModelsListPage />} />
              <Route path="/admin/models"         element={<RequireAuth><ModelsAdminPage /></RequireAuth>} />
              <Route path="/admin/providers"      element={<RequireAuth><ProvidersAdminPage /></RequireAuth>} />
              <Route path="/admin/routing"        element={<RequireAuth><RoutingAdminPage /></RequireAuth>} />
              <Route path="/admin/byok"           element={<RequireAuth><ByokAdminPage /></RequireAuth>} />
              <Route path="/admin/credits"        element={<RequireAuth><CreditsAdminPage /></RequireAuth>} />
              <Route path="/admin/billing"        element={<RequireAuth><BillingAdminPage /></RequireAuth>} />
              <Route path="/admin/security"       element={<RequireAuth><SecurityAdminPage /></RequireAuth>} />
              <Route path="/admin/logs"           element={<RequireAuth><LogsAdminPage /></RequireAuth>} />
              <Route path="/admin/dashboard"      element={<RequireAuth><DashboardAdminPage /></RequireAuth>} />
              <Route path="/admin/notifications"  element={<RequireAuth><NotificationsAdminPage /></RequireAuth>} />
              <Route path="/admin/api-keys"       element={<RequireAuth><ApiKeysAdminPage /></RequireAuth>} />
              <Route path="*" element={<Navigate to="/admin/dashboard" replace />} />
            </Routes>
          </Suspense>
        </Content>
      </Layout>
    </Layout>
  );
};

export default App;
