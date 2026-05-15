import React, { useState, useEffect } from 'react';
import { Table, Button, message, Card, Select, Space, Input } from 'antd';
import { exportBilling, getBillingUsage, getOrganizations, getProjects } from '../api';
import { BillingRecord, Organization, Project } from '../types';
import { useI18n } from '../i18n';

const BillingAdminPage: React.FC = () => {
  const { t } = useI18n();
  const [billingRecords, setBillingRecords] = useState<BillingRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [organizationFilter, setOrganizationFilter] = useState<number | undefined>(undefined);
  const [projectFilter, setProjectFilter] = useState<number | undefined>(undefined);
  const [environmentFilter, setEnvironmentFilter] = useState<string | undefined>(undefined);

  useEffect(() => {
    const fetchBillingUsage = async () => {
      setLoading(true);
      try {
        const [response, organizationResponse, projectResponse] = await Promise.all([
          getBillingUsage({
            organizationId: organizationFilter,
            projectId: projectFilter,
            environment: environmentFilter,
          }),
          getOrganizations(),
          getProjects(),
        ]);
        setBillingRecords(response);
        setOrganizations(organizationResponse);
        setProjects(projectResponse);
      } catch (error) {
        message.error(t('billing.loadedFailed'));
      } finally {
        setLoading(false);
      }
    };

    fetchBillingUsage();
  }, [organizationFilter, projectFilter, environmentFilter]);

  const handleExport = async () => {
    try {
      const response = await exportBilling();
      window.open(response.csv_url, '_blank');
      message.success(t('billing.exported'));
    } catch (error) {
      message.error(t('billing.exportFailed'));
    }
  };

  const columns = [
    {
      title: t('logs.apiKey'),
      dataIndex: 'apiKeyLabel',
      key: 'apiKeyLabel',
    },
    {
      title: t('apiKeys.environment'),
      dataIndex: 'environment',
      key: 'environment',
      render: (value?: string) => value || 'default',
    },
    {
      title: t('billing.resolvedModel'),
      dataIndex: 'resolvedModel',
      key: 'resolvedModel',
    },
    {
      title: t('common.provider'),
      dataIndex: 'providerName',
      key: 'providerName',
    },
    {
      title: t('common.requests'),
      dataIndex: 'requestCount',
      key: 'requestCount',
    },
    {
      title: t('billing.promptTokens'),
      dataIndex: 'promptTokens',
      key: 'promptTokens',
    },
    {
      title: t('billing.completionTokens'),
      dataIndex: 'completionTokens',
      key: 'completionTokens',
    },
    {
      title: t('billing.cachedTokens'),
      dataIndex: 'cachedTokens',
      key: 'cachedTokens',
    },
    {
      title: t('billing.reasoningTokens'),
      dataIndex: 'reasoningTokens',
      key: 'reasoningTokens',
    },
    {
      title: t('billing.totalCost'),
      dataIndex: 'totalCost',
      key: 'totalCost',
    },
    {
      title: t('billing.providerReportedCost'),
      dataIndex: 'providerReportedCost',
      key: 'providerReportedCost',
    },
  ];

  return (
    <Card title={t('billing.title')}>
      <Space wrap style={{ marginBottom: 16 }}>
        <Button type="primary" onClick={handleExport}>
          {t('common.exportCsv')}
        </Button>
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
      </Space>
      <Table dataSource={billingRecords} columns={columns} loading={loading} pagination={false} />
    </Card>
  );
};

export default BillingAdminPage;
