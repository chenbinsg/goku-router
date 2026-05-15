import React, { useState, useEffect } from 'react';
import { Row, Col, Statistic, Table, Button, Modal, Form, Input, InputNumber, Checkbox, message, Card, Typography, Select, Space } from 'antd';
import { getOrganizations, addOrganization, getProjects, addProject, getAnalyticsSummary, getWorkspaceRouteDefaults, addWorkspaceRouteDefault, updateWorkspaceRouteDefault, exportAnalyticsSummary } from '../api';
import { AnalyticsSummary, Organization, Project, WorkspaceRouteDefault } from '../types';
import { useI18n } from '../i18n';

const DashboardAdminPage: React.FC = () => {
  const { t } = useI18n();
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [workspaceDefaults, setWorkspaceDefaults] = useState<WorkspaceRouteDefault[]>([]);
  const [organizationFilter, setOrganizationFilter] = useState<number | undefined>(undefined);
  const [projectFilter, setProjectFilter] = useState<number | undefined>(undefined);
  const [environmentFilter, setEnvironmentFilter] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [modalType, setModalType] = useState<'organization' | 'project' | 'workspace'>('organization');
  const [editingWorkspaceDefault, setEditingWorkspaceDefault] = useState<WorkspaceRouteDefault | null>(null);
  const [form] = Form.useForm();

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const [orgResponse, projectResponse, analyticsResponse, workspaceResponse] = await Promise.all([
          getOrganizations(),
          getProjects(),
          getAnalyticsSummary({
            organizationId: organizationFilter,
            projectId: projectFilter,
            environment: environmentFilter,
          }),
          getWorkspaceRouteDefaults(),
        ]);
        setOrganizations(orgResponse);
        setProjects(projectResponse);
        setAnalytics(analyticsResponse);
        setWorkspaceDefaults(workspaceResponse);
        message.success(t('dashboard.loaded'));
      } catch (error) {
        message.error(t('dashboard.loadFailed'));
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [organizationFilter, projectFilter, environmentFilter]);

  const handleAdd = async (values: any) => {
    try {
      if (modalType === 'organization') {
        const created = await addOrganization(values);
        setOrganizations([...organizations, created]);
      } else if (modalType === 'project') {
        const created = await addProject({
          name: values.name,
          organizationId: Number(values.organizationId),
        });
        setProjects([...projects, created]);
      } else if (modalType === 'workspace') {
        const payload = {
          id: editingWorkspaceDefault?.id,
          organizationId: values.organizationId ? Number(values.organizationId) : undefined,
          projectId: values.projectId ? Number(values.projectId) : undefined,
          providerOrder: String(values.providerOrder || '').split(',').map((item: string) => item.trim()).filter(Boolean),
          sortMode: values.sortMode || 'balanced',
          maxPricePer1k: values.maxPricePer1k,
          requireCapabilities: String(values.requireCapabilities || '').split(',').map((item: string) => item.trim()).filter(Boolean),
          requireParameters: Boolean(values.requireParameters),
          zdr: typeof values.zdr === 'boolean' ? values.zdr : undefined,
          dataCollection: values.dataCollection || undefined,
        };
        const created = editingWorkspaceDefault
          ? await updateWorkspaceRouteDefault(payload)
          : await addWorkspaceRouteDefault(payload);
        setWorkspaceDefaults((current) => {
          if (!editingWorkspaceDefault) {
            return [created, ...current];
          }
          return current.map((item) => (item.id === created.id ? created : item));
        });
      }
      message.success(t('dashboard.added', { item: modalType }));
      setIsModalVisible(false);
      setEditingWorkspaceDefault(null);
    } catch (error) {
      message.error(t('dashboard.addFailed', { item: modalType }));
    }
  };

  const columns = (type: 'organization' | 'project') => [
    {
      title: type === 'organization' ? t('dashboard.organizationName') : t('dashboard.projectName'),
      dataIndex: 'name',
      key: 'name',
    },
  ];

  return (
    <Card title={t('dashboard.title')}>
      {analytics && (
        <Card title={t('dashboard.analytics')} style={{ marginBottom: 16 }}>
          <Space wrap style={{ marginBottom: 16 }}>
            <Select
              allowClear
              value={organizationFilter}
              onChange={(value) => setOrganizationFilter(value)}
              placeholder={t('apiKeys.organizationId')}
              style={{ width: 180 }}
              options={organizations.map((item) => ({ label: `${item.id}: ${item.name}`, value: item.id }))}
            />
            <Select
              allowClear
              value={projectFilter}
              onChange={(value) => setProjectFilter(value)}
              placeholder={t('apiKeys.projectId')}
              style={{ width: 180 }}
              options={projects
                .filter((item) => !organizationFilter || item.organizationId === organizationFilter)
                .map((item) => ({ label: `${item.id}: ${item.name}`, value: item.id }))}
            />
            <Input
              value={environmentFilter}
              onChange={(event) => setEnvironmentFilter(event.target.value || undefined)}
              placeholder={t('apiKeys.environment')}
              style={{ width: 180 }}
            />
            <Button
              onClick={async () => {
                try {
                  const artifact = await exportAnalyticsSummary({
                    organizationId: organizationFilter,
                    projectId: projectFilter,
                    environment: environmentFilter,
                  });
                  window.open(artifact.downloadUrl, '_blank');
                  message.success(t('dashboard.analyticsExported'));
                } catch {
                  message.error(t('dashboard.analyticsExportFailed'));
                }
              }}
            >
              {t('dashboard.exportAnalytics')}
            </Button>
          </Space>
          <Row gutter={16}>
            <Col span={6}><Statistic title={t('dashboard.totalRequests')} value={analytics.totalRequests} /></Col>
            <Col span={6}><Statistic title={t('dashboard.fallbackRate')} value={analytics.fallbackRate} precision={2} /></Col>
            <Col span={6}><Statistic title={t('dashboard.blockedRequests')} value={analytics.blockedRequests} /></Col>
            <Col span={6}><Statistic title={t('dashboard.activeApiKeys')} value={analytics.activeApiKeys} /></Col>
          </Row>
        </Card>
      )}
      {analytics && (
        <Card title={t('dashboard.routeScoring')} style={{ marginBottom: 16 }}>
          <Row gutter={16}>
            <Col span={6}><Statistic title={t('dashboard.routeChanges')} value={analytics.recentRouteChanges} /></Col>
            <Col span={6}><Statistic title={t('dashboard.routeChangeRate')} value={analytics.recentRouteChangeRate} precision={2} /></Col>
            <Col span={6}><Statistic title={t('dashboard.routeReplayCases')} value={analytics.recentRouteReplayCases} /></Col>
            <Col span={6}><Statistic title={t('dashboard.activeProfile')} value={analytics.routeScoringProfileName} /></Col>
          </Row>
          <Row gutter={16} style={{ marginTop: 16 }}>
            <Col span={8}><Statistic title={t('dashboard.cacheHits')} value={analytics.cacheHits} /></Col>
            <Col span={8}><Statistic title={t('dashboard.cacheHitRate')} value={analytics.cacheHitRate} precision={2} /></Col>
            <Col span={8}><Statistic title={t('dashboard.stickyRequests')} value={analytics.stickyRequests} /></Col>
          </Row>
          <Typography.Paragraph style={{ marginTop: 16 }}>
            <Typography.Text strong>{t('dashboard.workloadShifts')}</Typography.Text>
          </Typography.Paragraph>
          <Table
            dataSource={analytics.routeScoringWorkloadShifts.map((item) => ({ ...item, key: item.workloadClass }))}
            columns={[
              { title: t('dashboard.workloadClass'), dataIndex: 'workloadClass', key: 'workloadClass' },
              { title: t('dashboard.routeChanges'), dataIndex: 'changedRoutes', key: 'changedRoutes' },
              { title: t('dashboard.routeReplayCases'), dataIndex: 'totalRoutes', key: 'totalRoutes' },
            ]}
            pagination={false}
            size="small"
          />
          <Typography.Paragraph style={{ marginTop: 16 }}>
            <Typography.Text strong>{t('dashboard.anomalyAlerts')}</Typography.Text>
          </Typography.Paragraph>
          <Table
            dataSource={analytics.anomalyAlerts.map((item, index) => ({ ...item, key: `${item.category}-${index}` }))}
            columns={[
              { title: t('dashboard.alertSeverity'), dataIndex: 'severity', key: 'severity' },
              { title: t('dashboard.costOpportunityTitle'), dataIndex: 'title', key: 'title' },
              { title: t('dashboard.costOpportunityScope'), dataIndex: 'scopeLabel', key: 'scopeLabel' },
              { title: t('dashboard.alertMetric'), dataIndex: 'metricValue', key: 'metricValue' },
              { title: t('dashboard.alertThreshold'), dataIndex: 'threshold', key: 'threshold' },
              { title: t('common.message'), dataIndex: 'message', key: 'message' },
            ]}
            locale={{ emptyText: t('dashboard.anomalyAlertsEmpty') }}
            pagination={false}
            size="small"
          />
          <Typography.Paragraph style={{ marginTop: 16 }}>
            <Typography.Text strong>{t('dashboard.routeScoringDrift')}</Typography.Text>
          </Typography.Paragraph>
          <Table
            dataSource={analytics.routeScoringDrift.map((item) => ({ ...item, key: item.workloadClass }))}
            columns={[
              { title: t('dashboard.workloadClass'), dataIndex: 'workloadClass', key: 'workloadClass' },
              { title: t('common.requests'), dataIndex: 'requestCount', key: 'requestCount' },
              { title: t('dashboard.activeProfile'), dataIndex: 'activeProfileName', key: 'activeProfileName' },
              { title: t('dashboard.driftScore'), dataIndex: 'driftScore', key: 'driftScore' },
              { title: t('dashboard.routeChangeRate'), dataIndex: 'routeChangeRate', key: 'routeChangeRate' },
              {
                title: t('dashboard.defaultWeights'),
                dataIndex: 'defaultWeights',
                key: 'defaultWeights',
                render: (value: Record<string, number>) => JSON.stringify(value),
              },
              {
                title: t('dashboard.activeWeights'),
                dataIndex: 'activeWeights',
                key: 'activeWeights',
                render: (value: Record<string, number>) => JSON.stringify(value),
              },
            ]}
            pagination={false}
            size="small"
          />
          <Typography.Paragraph style={{ marginTop: 16 }}>
            <Typography.Text strong>{t('security.routeExperiments')}</Typography.Text>
          </Typography.Paragraph>
          <Table
            dataSource={analytics.routeScoringExperiments.map((item, index) => ({ ...item, key: `${item.name}-${item.variant}-${index}` }))}
            columns={[
              { title: t('common.name'), dataIndex: 'name', key: 'name' },
              { title: t('security.challengerProfile'), dataIndex: 'variant', key: 'variant' },
              { title: t('common.requests'), dataIndex: 'requests', key: 'requests' },
              { title: t('dashboard.routeChanges'), dataIndex: 'changed_routes', key: 'changed_routes' },
              { title: t('logs.latency'), dataIndex: 'avg_latency', key: 'avg_latency' },
              { title: t('billing.totalCost'), dataIndex: 'total_cost', key: 'total_cost' },
            ]}
            pagination={false}
            size="small"
          />
          <Typography.Paragraph style={{ marginTop: 16 }}>
            <Typography.Text strong>{t('dashboard.workspaceUsageSummary')}</Typography.Text>
          </Typography.Paragraph>
          <Table
            dataSource={analytics.workspaceUsageSummary.map((item) => ({
              ...item,
              key: `${item.organizationId || 'na'}-${item.projectId || 'na'}`,
            }))}
            columns={[
              { title: t('dashboard.organizationName'), dataIndex: 'organizationName', key: 'organizationName' },
              { title: t('dashboard.projectName'), dataIndex: 'projectName', key: 'projectName' },
              { title: t('apiKeys.environment'), dataIndex: 'environment', key: 'environment', render: (value?: string) => value || 'default' },
              { title: t('common.requests'), dataIndex: 'requestCount', key: 'requestCount' },
              { title: t('dashboard.failureCount'), dataIndex: 'failureCount', key: 'failureCount' },
              { title: t('dashboard.fallbackCount'), dataIndex: 'fallbackCount', key: 'fallbackCount' },
              { title: t('dashboard.cacheHits'), dataIndex: 'cacheHitCount', key: 'cacheHitCount' },
              { title: t('billing.totalCost'), dataIndex: 'totalCost', key: 'totalCost' },
              { title: t('logs.latency'), dataIndex: 'avgLatency', key: 'avgLatency' },
            ]}
            pagination={false}
            size="small"
          />
          <Typography.Paragraph style={{ marginTop: 16 }}>
            <Typography.Text strong>{t('dashboard.costOptimization')}</Typography.Text>
          </Typography.Paragraph>
          <Table
            dataSource={analytics.costOptimizationOpportunities.map((item, index) => ({
              ...item,
              key: `${item.category}-${index}`,
            }))}
            columns={[
              { title: t('dashboard.costOpportunityTitle'), dataIndex: 'title', key: 'title' },
              { title: t('dashboard.costOpportunityScope'), dataIndex: 'scopeLabel', key: 'scopeLabel' },
              { title: t('dashboard.costOpportunitySavings'), dataIndex: 'estimatedSavings', key: 'estimatedSavings' },
              { title: t('dashboard.costOpportunityCurrentCost'), dataIndex: 'currentCost', key: 'currentCost' },
              { title: t('dashboard.costOpportunityTargetCost'), dataIndex: 'targetCost', key: 'targetCost', render: (value: number | undefined) => value ?? 'N/A' },
              { title: t('dashboard.costOpportunityRecommendation'), dataIndex: 'recommendation', key: 'recommendation' },
            ]}
            locale={{ emptyText: t('dashboard.costOptimizationEmpty') }}
            pagination={false}
            size="small"
          />
        </Card>
      )}
      <Button type="primary" onClick={() => { setModalType('organization'); setEditingWorkspaceDefault(null); form.resetFields(); setIsModalVisible(true); }}>
        {t('dashboard.addOrganization')}
      </Button>
      <Table dataSource={organizations.map((item) => ({ ...item, key: item.id || item.name }))} columns={columns('organization')} loading={loading} pagination={false} />

      <Button type="primary" onClick={() => { setModalType('project'); setEditingWorkspaceDefault(null); form.resetFields(); setIsModalVisible(true); }}>
        {t('dashboard.addProject')}
      </Button>
      <Table
        dataSource={projects.map((item) => ({ ...item, key: item.id || `${item.organizationId}-${item.name}` }))}
        columns={[
          ...columns('project'),
          { title: t('dashboard.organizationName'), dataIndex: 'organizationName', key: 'organizationName' },
        ]}
        loading={loading}
        pagination={false}
      />
      <Button type="primary" onClick={() => { setModalType('workspace'); setEditingWorkspaceDefault(null); form.resetFields(); form.setFieldsValue({ sortMode: 'balanced' }); setIsModalVisible(true); }}>
        {t('dashboard.addWorkspaceRouteDefault')}
      </Button>
      <Table
        dataSource={workspaceDefaults.map((item) => ({ ...item, key: item.id || `${item.organizationId}-${item.projectId}` }))}
        columns={[
          { title: t('dashboard.organizationName'), dataIndex: 'organizationName', key: 'organizationName' },
          { title: t('dashboard.projectName'), dataIndex: 'projectName', key: 'projectName' },
          { title: t('dashboard.workspaceProviderOrder'), dataIndex: 'providerOrder', key: 'providerOrder', render: (value: string[]) => value.join(', ') || 'N/A' },
          { title: t('dashboard.workspaceSortMode'), dataIndex: 'sortMode', key: 'sortMode' },
          { title: t('dashboard.workspaceMaxPrice'), dataIndex: 'maxPricePer1k', key: 'maxPricePer1k', render: (value: number | undefined) => value ?? 'N/A' },
          { title: t('dashboard.workspaceCapabilities'), dataIndex: 'requireCapabilities', key: 'requireCapabilities', render: (value: string[]) => value.join(', ') || 'N/A' },
          { title: t('dashboard.workspaceRequireParameters'), dataIndex: 'requireParameters', key: 'requireParameters', render: (value: boolean) => value ? t('logs.yes') : t('logs.no') },
          { title: t('dashboard.workspaceZdr'), dataIndex: 'zdr', key: 'zdr', render: (value: boolean | undefined) => value === undefined ? 'N/A' : value ? t('logs.yes') : t('logs.no') },
          { title: t('dashboard.workspaceDataCollection'), dataIndex: 'dataCollection', key: 'dataCollection', render: (value: string | undefined) => value || 'N/A' },
          {
            title: t('common.actions'),
            key: 'actions',
            render: (_: unknown, record: WorkspaceRouteDefault) => (
              <Button
                onClick={() => {
                  setModalType('workspace');
                  setEditingWorkspaceDefault(record);
                  form.setFieldsValue({
                    organizationId: record.organizationId,
                    projectId: record.projectId,
                    providerOrder: record.providerOrder.join(', '),
                    sortMode: record.sortMode,
                    maxPricePer1k: record.maxPricePer1k,
                    requireCapabilities: record.requireCapabilities.join(', '),
                    requireParameters: record.requireParameters,
                    zdr: record.zdr,
                    dataCollection: record.dataCollection,
                  });
                  setIsModalVisible(true);
                }}
              >
                {t('common.edit')}
              </Button>
            ),
          },
        ]}
        loading={loading}
        pagination={false}
      />

      <Modal
        title={modalType === 'workspace' && editingWorkspaceDefault ? t('dashboard.editWorkspaceRouteDefault') : `${t('common.add')} ${modalType}`}
        open={isModalVisible}
        onCancel={() => { setIsModalVisible(false); setEditingWorkspaceDefault(null); form.resetFields(); }}
        footer={null}
      >
        <Form form={form} layout="vertical" onFinish={handleAdd}>
          {modalType !== 'workspace' && (
            <Form.Item
              label={modalType === 'organization' ? t('dashboard.organizationName') : t('dashboard.projectName')}
              name="name"
              rules={[{ required: true, message: t('dashboard.inputName', { item: modalType }) }]}
            >
              <Input />
            </Form.Item>
          )}
          {modalType === 'workspace' && (
            <>
              <Form.Item label={t('apiKeys.organizationId')} name="organizationId">
                <Input placeholder={organizations.map((item) => `${item.id}:${item.name}`).join(', ')} />
              </Form.Item>
              <Form.Item label={t('apiKeys.projectId')} name="projectId">
                <Input placeholder={projects.map((item) => `${item.id}:${item.name}`).join(', ')} />
              </Form.Item>
              <Form.Item label={t('dashboard.workspaceProviderOrder')} name="providerOrder">
                <Input placeholder="provider_primary,provider_backup" />
              </Form.Item>
              <Form.Item label={t('dashboard.workspaceSortMode')} name="sortMode">
                <Input placeholder="balanced / price / latency / priority" />
              </Form.Item>
              <Form.Item label={t('dashboard.workspaceMaxPrice')} name="maxPricePer1k">
                <InputNumber min={0} step={0.1} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item label={t('dashboard.workspaceCapabilities')} name="requireCapabilities">
                <Input placeholder="structured_output,zdr" />
              </Form.Item>
              <Form.Item name="requireParameters" valuePropName="checked">
                <Checkbox>{t('dashboard.workspaceRequireParameters')}</Checkbox>
              </Form.Item>
              <Form.Item name="zdr" valuePropName="checked">
                <Checkbox>{t('dashboard.workspaceZdr')}</Checkbox>
              </Form.Item>
              <Form.Item label={t('dashboard.workspaceDataCollection')} name="dataCollection">
                <Input placeholder="allow / deny" />
              </Form.Item>
            </>
          )}
          {modalType === 'project' && (
            <Form.Item
              label={t('apiKeys.organizationId')}
              name="organizationId"
              rules={[{ required: true, message: t('dashboard.inputName', { item: 'organizationId' }) }]}
            >
              <Input placeholder={organizations.map((item) => `${item.id}:${item.name}`).join(', ')} />
            </Form.Item>
          )}
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

export default DashboardAdminPage;
