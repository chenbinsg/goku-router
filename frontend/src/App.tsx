import React, { Suspense, lazy } from 'react';
import { Layout, Menu, Segmented, Space, Typography } from 'antd';
import { Route, Routes, Link } from 'react-router-dom';
import { useI18n } from './i18n';

const { Header, Content, Sider } = Layout;
const ChatCompletionsPage = lazy(() => import('./pages/ChatCompletionsPage'));
const EmbeddingsPage = lazy(() => import('./pages/EmbeddingsPage'));
const ModelsListPage = lazy(() => import('./pages/ModelsListPage'));
const ModelsAdminPage = lazy(() => import('./pages/ModelsAdminPage'));
const ProvidersAdminPage = lazy(() => import('./pages/ProvidersAdminPage'));
const RoutingAdminPage = lazy(() => import('./pages/RoutingAdminPage'));
const ByokAdminPage = lazy(() => import('./pages/ByokAdminPage'));
const CreditsAdminPage = lazy(() => import('./pages/CreditsAdminPage'));
const BillingAdminPage = lazy(() => import('./pages/BillingAdminPage'));
const SecurityAdminPage = lazy(() => import('./pages/SecurityAdminPage'));
const LogsAdminPage = lazy(() => import('./pages/LogsAdminPage'));
const DashboardAdminPage = lazy(() => import('./pages/DashboardAdminPage'));
const NotificationsAdminPage = lazy(() => import('./pages/NotificationsAdminPage'));
const ApiKeysAdminPage = lazy(() => import('./pages/ApiKeysAdminPage'));

const App: React.FC = () => {
  const { locale, setLocale, t } = useI18n();

  return (
  <Layout style={{ minHeight: '100vh' }}>
    <Sider>
      <Menu theme="dark" mode="inline">
        <Menu.Item key="1">
          <Link to="/v1/chat/completions">{t('nav.chat')}</Link>
        </Menu.Item>
        <Menu.Item key="2">
          <Link to="/v1/embeddings">{t('nav.embeddings')}</Link>
        </Menu.Item>
        <Menu.Item key="3">
          <Link to="/v1/models">{t('nav.modelsList')}</Link>
        </Menu.Item>
        <Menu.Item key="4">
          <Link to="/admin/models">{t('nav.modelsAdmin')}</Link>
        </Menu.Item>
        <Menu.Item key="5">
          <Link to="/admin/providers">{t('nav.providersAdmin')}</Link>
        </Menu.Item>
        <Menu.Item key="6">
          <Link to="/admin/routing">{t('nav.routingAdmin')}</Link>
        </Menu.Item>
        <Menu.Item key="7">
          <Link to="/admin/byok">{t('nav.byokAdmin')}</Link>
        </Menu.Item>
        <Menu.Item key="8">
          <Link to="/admin/credits">{t('nav.creditsAdmin')}</Link>
        </Menu.Item>
        <Menu.Item key="9">
          <Link to="/admin/billing">{t('nav.billingAdmin')}</Link>
        </Menu.Item>
        <Menu.Item key="10">
          <Link to="/admin/security">{t('nav.securityAdmin')}</Link>
        </Menu.Item>
        <Menu.Item key="11">
          <Link to="/admin/logs">{t('nav.logsAdmin')}</Link>
        </Menu.Item>
        <Menu.Item key="12">
          <Link to="/admin/dashboard">{t('nav.dashboardAdmin')}</Link>
        </Menu.Item>
        <Menu.Item key="13">
          <Link to="/admin/notifications">{t('nav.notificationsAdmin')}</Link>
        </Menu.Item>
        <Menu.Item key="14">
          <Link to="/admin/api-keys">{t('nav.apiKeysAdmin')}</Link>
        </Menu.Item>
      </Menu>
    </Sider>
    <Layout>
      <Header style={{ background: '#fff', padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
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
      </Header>
      <Content style={{ margin: '0 16px' }}>
        <Suspense fallback={<div style={{ padding: 24 }}>{t('common.loading')}</div>}>
          <Routes>
            <Route path="/v1/chat/completions" element={<ChatCompletionsPage />} />
            <Route path="/v1/embeddings" element={<EmbeddingsPage />} />
            <Route path="/v1/models" element={<ModelsListPage />} />
            <Route path="/admin/models" element={<ModelsAdminPage />} />
            <Route path="/admin/providers" element={<ProvidersAdminPage />} />
            <Route path="/admin/routing" element={<RoutingAdminPage />} />
            <Route path="/admin/byok" element={<ByokAdminPage />} />
            <Route path="/admin/credits" element={<CreditsAdminPage />} />
            <Route path="/admin/billing" element={<BillingAdminPage />} />
            <Route path="/admin/security" element={<SecurityAdminPage />} />
            <Route path="/admin/logs" element={<LogsAdminPage />} />
            <Route path="/admin/dashboard" element={<DashboardAdminPage />} />
            <Route path="/admin/notifications" element={<NotificationsAdminPage />} />
            <Route path="/admin/api-keys" element={<ApiKeysAdminPage />} />
          </Routes>
        </Suspense>
      </Content>
    </Layout>
  </Layout>
  );
};

export default App;
