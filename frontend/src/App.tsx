import React, { Suspense, lazy, useEffect, useState } from 'react';
import { Layout, Menu, Segmented, Space, Typography, Button, Avatar, Dropdown } from 'antd';
import { Route, Routes, Link, Navigate, useLocation, useNavigate } from 'react-router-dom';
import {
  DashboardOutlined,
  MessageOutlined,
  ApiOutlined,
  AppstoreOutlined,
  CloudServerOutlined,
  BranchesOutlined,
  KeyOutlined,
  SafetyOutlined,
  DollarOutlined,
  FileTextOutlined,
  BellOutlined,
  UserOutlined,
  LogoutOutlined,
  ThunderboltOutlined,
  CreditCardOutlined,
  TeamOutlined,
  LockOutlined,
  ProfileOutlined,
  ExperimentOutlined,
} from '@ant-design/icons';
import { useI18n } from './i18n';
import { isAuthenticated, getUser, clearTokens } from './utils/auth';

const { Header, Content, Sider } = Layout;

const ChatCompletionsPage    = lazy(() => import('./pages/ChatCompletionsPage'));
const EmbeddingsPage         = lazy(() => import('./pages/EmbeddingsPage'));
const ModelsListPage         = lazy(() => import('./pages/ModelsListPage'));
const ModelsAdminPage        = lazy(() => import('./pages/ModelsAdminPage'));
const ProvidersAdminPage     = lazy(() => import('./pages/ProvidersAdminPage'));
const RoutingAdminPage       = lazy(() => import('./pages/RoutingAdminPage'));
const QualityEvalPage        = lazy(() => import('./pages/QualityEvalPage'));
const ByokAdminPage          = lazy(() => import('./pages/ByokAdminPage'));
const CreditsAdminPage       = lazy(() => import('./pages/CreditsAdminPage'));
const BillingAdminPage       = lazy(() => import('./pages/BillingAdminPage'));
const SecurityAdminPage      = lazy(() => import('./pages/SecurityAdminPage'));
const LogsAdminPage          = lazy(() => import('./pages/LogsAdminPage'));
const DashboardAdminPage     = lazy(() => import('./pages/DashboardAdminPage'));
const NotificationsAdminPage = lazy(() => import('./pages/NotificationsAdminPage'));
const ApiKeysAdminPage       = lazy(() => import('./pages/ApiKeysAdminPage'));
const UsersAdminPage         = lazy(() => import('./pages/UsersAdminPage'));
const ProfilePage            = lazy(() => import('./pages/ProfilePage'));
const LoginPage              = lazy(() => import('./pages/LoginPage'));

const RequireAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  if (!isAuthenticated()) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
};

// Map route path → [itemKey, parentGroupKey]
const PATH_TO_KEY: Record<string, [string, string]> = {
  '/admin/dashboard':     ['dashboard',  ''],
  '/v1/chat/completions': ['chat',       'grp-playground'],
  '/v1/embeddings':       ['embeddings', 'grp-playground'],
  '/v1/models':           ['models-list','grp-playground'],
  '/admin/models':        ['models',     'grp-routing'],
  '/admin/providers':     ['providers',  'grp-routing'],
  '/admin/routing':       ['routing',    'grp-routing'],
  '/admin/quality-evals': ['quality-evals','grp-routing'],
  '/admin/api-keys':      ['api-keys',   'grp-access'],
  '/admin/byok':          ['byok',       'grp-access'],
  '/admin/security':      ['security',   'grp-access'],
  '/admin/users':         ['users',      'grp-access'],
  '/admin/profile':       ['profile',    ''],
  '/admin/credits':       ['credits',    'grp-billing'],
  '/admin/billing':       ['billing',    'grp-billing'],
  '/admin/logs':          ['logs',       'grp-observability'],
  '/admin/notifications': ['notifications','grp-observability'],
};

const App: React.FC = () => {
  const { locale, setLocale, t } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  const user = getUser();
  const [systemVersion, setSystemVersion] = useState<string>('');

  useEffect(() => {
    fetch('/admin/system/info')
      .then(r => r.json())
      .then(d => setSystemVersion(d.version || ''))
      .catch(() => {});
  }, []);

  const handleLogout = () => {
    clearTokens();
    navigate('/login', { replace: true });
  };

  const [selectedKey, openGroupKey] = PATH_TO_KEY[location.pathname] ?? ['dashboard', ''];

  const userMenuItems = [
    {
      key: 'info',
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
      key: 'profile',
      icon: <ProfileOutlined />,
      label: '个人资料',
      onClick: () => navigate('/admin/profile'),
    },
    {
      key: 'change-password',
      icon: <LockOutlined />,
      label: '修改密码',
      onClick: () => navigate('/admin/profile'),
    },
    { type: 'divider' as const },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: handleLogout },
  ];

  // Unauthenticated — show only login
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

  const menuItems = [
    // ── Overview ──────────────────────────────────────────────────────────────
    {
      key: 'dashboard',
      icon: <DashboardOutlined />,
      label: <Link to="/admin/dashboard">{t('nav.dashboard')}</Link>,
    },

    // ── Playground (collapsible submenu) ──────────────────────────────────────
    {
      key: 'grp-playground',
      icon: <MessageOutlined />,
      label: t('nav.group.playground'),
      children: [
        {
          key: 'chat',
          icon: <MessageOutlined />,
          label: <Link to="/v1/chat/completions">{t('nav.chat')}</Link>,
        },
        {
          key: 'embeddings',
          icon: <ThunderboltOutlined />,
          label: <Link to="/v1/embeddings">{t('nav.embeddings')}</Link>,
        },
        {
          key: 'models-list',
          icon: <AppstoreOutlined />,
          label: <Link to="/v1/models">{t('nav.modelsList')}</Link>,
        },
      ],
    },

    // ── Routing (collapsible submenu) ─────────────────────────────────────────
    {
      key: 'grp-routing',
      icon: <BranchesOutlined />,
      label: t('nav.group.routing'),
      children: [
        {
          key: 'models',
          icon: <AppstoreOutlined />,
          label: <Link to="/admin/models">{t('nav.modelsAdmin')}</Link>,
        },
        {
          key: 'providers',
          icon: <CloudServerOutlined />,
          label: <Link to="/admin/providers">{t('nav.providersAdmin')}</Link>,
        },
        {
          key: 'routing',
          icon: <BranchesOutlined />,
          label: <Link to="/admin/routing">{t('nav.routingAdmin')}</Link>,
        },
        {
          key: 'quality-evals',
          icon: <ExperimentOutlined />,
          label: <Link to="/admin/quality-evals">质量评估</Link>,
        },
      ],
    },

    // ── Access & Security (collapsible submenu) ───────────────────────────────
    {
      key: 'grp-access',
      icon: <SafetyOutlined />,
      label: t('nav.group.access'),
      children: [
        {
          key: 'api-keys',
          icon: <KeyOutlined />,
          label: <Link to="/admin/api-keys">{t('nav.apiKeysAdmin')}</Link>,
        },
        {
          key: 'byok',
          icon: <ApiOutlined />,
          label: <Link to="/admin/byok">{t('nav.byokAdmin')}</Link>,
        },
        {
          key: 'security',
          icon: <SafetyOutlined />,
          label: <Link to="/admin/security">{t('nav.securityAdmin')}</Link>,
        },
        {
          key: 'users',
          icon: <TeamOutlined />,
          label: <Link to="/admin/users">{t('nav.usersAdmin')}</Link>,
        },
      ],
    },

    // ── Billing (collapsible submenu) ─────────────────────────────────────────
    {
      key: 'grp-billing',
      icon: <DollarOutlined />,
      label: t('nav.group.billing'),
      children: [
        {
          key: 'credits',
          icon: <CreditCardOutlined />,
          label: <Link to="/admin/credits">{t('nav.creditsAdmin')}</Link>,
        },
        {
          key: 'billing',
          icon: <DollarOutlined />,
          label: <Link to="/admin/billing">{t('nav.billingAdmin')}</Link>,
        },
      ],
    },

    // ── Observability (collapsible submenu) ───────────────────────────────────
    {
      key: 'grp-observability',
      icon: <FileTextOutlined />,
      label: t('nav.group.observability'),
      children: [
        {
          key: 'logs',
          icon: <FileTextOutlined />,
          label: <Link to="/admin/logs">{t('nav.logsAdmin')}</Link>,
        },
        {
          key: 'notifications',
          icon: <BellOutlined />,
          label: <Link to="/admin/notifications">{t('nav.notificationsAdmin')}</Link>,
        },
      ],
    },
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} style={{ overflow: 'auto', height: '100vh', position: 'fixed', left: 0, top: 0, bottom: 0 }}>
        {/* Logo */}
        <div style={{ padding: '14px 16px', borderBottom: '1px solid #2a2a3e', textAlign: 'center' }}>
          <img src="/logo.png" alt="Goku-Router" style={{ width: '100%', maxWidth: 160, objectFit: 'contain' }} />
        </div>

        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          defaultOpenKeys={openGroupKey ? [openGroupKey] : []}
          items={menuItems}
          style={{ borderRight: 0, paddingBottom: 8 }}
        />
        {/* Version badge at bottom of sidebar */}
        {systemVersion && (
          <div style={{ padding: '10px 16px', borderTop: '1px solid #2a2a3e', textAlign: 'center' }}>
            <Typography.Text style={{ color: '#888', fontSize: 11 }}>{systemVersion}</Typography.Text>
          </div>
        )}
      </Sider>

      <Layout style={{ marginLeft: 220 }}>
        <Header style={{ background: '#fff', padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 16, position: 'sticky', top: 0, zIndex: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.08)' }}>
          <Space size={12}>
            <Typography.Text style={{ color: '#666' }}>{t('header.language')}</Typography.Text>
            <Segmented
              value={locale}
              onChange={(v) => setLocale(v as 'en' | 'zh')}
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

        <Content style={{ margin: '24px 16px', minHeight: 'calc(100vh - 64px)' }}>
          <Suspense fallback={<div style={{ padding: 24 }}>{t('common.loading')}</div>}>
            <Routes>
              <Route path="/login"                element={<Navigate to="/admin/dashboard" replace />} />
              <Route path="/"                     element={<Navigate to="/admin/dashboard" replace />} />
              <Route path="/v1/chat/completions"  element={<ChatCompletionsPage />} />
              <Route path="/v1/embeddings"        element={<EmbeddingsPage />} />
              <Route path="/v1/models"            element={<ModelsListPage />} />
              <Route path="/admin/dashboard"      element={<RequireAuth><DashboardAdminPage /></RequireAuth>} />
              <Route path="/admin/models"         element={<RequireAuth><ModelsAdminPage /></RequireAuth>} />
              <Route path="/admin/providers"      element={<RequireAuth><ProvidersAdminPage /></RequireAuth>} />
              <Route path="/admin/routing"        element={<RequireAuth><RoutingAdminPage /></RequireAuth>} />
              <Route path="/admin/quality-evals"  element={<RequireAuth><QualityEvalPage /></RequireAuth>} />
              <Route path="/admin/api-keys"       element={<RequireAuth><ApiKeysAdminPage /></RequireAuth>} />
              <Route path="/admin/byok"           element={<RequireAuth><ByokAdminPage /></RequireAuth>} />
              <Route path="/admin/security"       element={<RequireAuth><SecurityAdminPage /></RequireAuth>} />
              <Route path="/admin/credits"        element={<RequireAuth><CreditsAdminPage /></RequireAuth>} />
              <Route path="/admin/billing"        element={<RequireAuth><BillingAdminPage /></RequireAuth>} />
              <Route path="/admin/logs"           element={<RequireAuth><LogsAdminPage /></RequireAuth>} />
              <Route path="/admin/notifications"  element={<RequireAuth><NotificationsAdminPage /></RequireAuth>} />
              <Route path="/admin/users"          element={<RequireAuth><UsersAdminPage /></RequireAuth>} />
              <Route path="/admin/profile"        element={<RequireAuth><ProfilePage /></RequireAuth>} />
              <Route path="*"                     element={<Navigate to="/admin/dashboard" replace />} />
            </Routes>
          </Suspense>
        </Content>
      </Layout>
    </Layout>
  );
};

export default App;
