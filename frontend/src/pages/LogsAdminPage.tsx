import React, { useState, useEffect } from 'react';
import { Button, Card, Input, Select, Space, Table, Tag, message, Typography } from 'antd';
import { getOrganizations, getProjects, getRequestLogs } from '../api';
import { Organization, Project, RequestLog } from '../types';
import { useI18n } from '../i18n';

const LogsAdminPage: React.FC = () => {
  const { t } = useI18n();
  const [logs, setLogs] = useState<RequestLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [organizationFilter, setOrganizationFilter] = useState<number | undefined>(undefined);
  const [projectFilter, setProjectFilter] = useState<number | undefined>(undefined);
  const [environmentFilter, setEnvironmentFilter] = useState<string | undefined>(undefined);
  const [requestIdFilter, setRequestIdFilter] = useState('');
  const [providerFilter, setProviderFilter] = useState<string | undefined>(undefined);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [errorOnly, setErrorOnly] = useState<string | undefined>(undefined);
  const [changedOnly, setChangedOnly] = useState<string | undefined>(undefined);

  useEffect(() => {
    const fetchLogs = async () => {
      setLoading(true);
      try {
        const [response, organizationResponse, projectResponse] = await Promise.all([
          getRequestLogs({
            organizationId: organizationFilter,
            projectId: projectFilter,
            environment: environmentFilter,
          }),
          getOrganizations(),
          getProjects(),
        ]);
        setLogs(response);
        setOrganizations(organizationResponse);
        setProjects(projectResponse);
        message.success(t('logs.loaded'));
      } catch (error) {
        message.error(t('logs.failed'));
      } finally {
        setLoading(false);
      }
    };

    fetchLogs();
  }, [organizationFilter, projectFilter, environmentFilter]);

  const columns = [
    {
      title: t('chat.requestId'),
      dataIndex: 'requestId',
      key: 'requestId',
    },
    {
      title: t('logs.apiKey'),
      dataIndex: 'apiKeyLabel',
      key: 'apiKeyLabel',
    },
    {
      title: t('apiKeys.environment'),
      dataIndex: 'environment',
      key: 'environment',
      render: (value: string | undefined) => value || 'default',
    },
    {
      title: t('common.model'),
      dataIndex: 'requestedModel',
      key: 'requestedModel',
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
      title: t('logs.workload'),
      dataIndex: 'workloadClass',
      key: 'workloadClass',
    },
    {
      title: t('logs.profile'),
      dataIndex: 'appliedProfileName',
      key: 'appliedProfileName',
    },
    {
      title: t('security.routeExperiments'),
      dataIndex: 'experimentName',
      key: 'experimentName',
      render: (value: string | undefined, record: RequestLog) => (
        value ? `${value} / ${record.experimentVariant || 'N/A'}` : 'N/A'
      ),
    },
    {
      title: t('chat.stickyKey'),
      dataIndex: 'stickyKey',
      key: 'stickyKey',
    },
    {
      title: t('logs.statusCode'),
      dataIndex: 'statusCode',
      key: 'statusCode',
    },
    {
      title: t('logs.errorCode'),
      dataIndex: 'errorCode',
      key: 'errorCode',
    },
    {
      title: t('logs.latency'),
      dataIndex: 'latency',
      key: 'latency',
    },
    {
      title: t('logs.fallback'),
      dataIndex: 'fallbackUsed',
      key: 'fallbackUsed',
      render: (value: boolean | undefined) => (value ? t('logs.yes') : t('logs.no')),
    },
    {
      title: t('logs.routeChanged'),
      dataIndex: 'routeChanged',
      key: 'routeChanged',
      render: (value: boolean | undefined) => (
        <Tag color={value ? 'gold' : 'default'}>
          {value ? t('logs.yes') : t('logs.no')}
        </Tag>
      ),
    },
    {
      title: t('chat.cacheHit'),
      dataIndex: 'cacheHit',
      key: 'cacheHit',
      render: (value: boolean | undefined) => (
        <Tag color={value ? 'green' : 'default'}>
          {value ? t('logs.yes') : t('logs.no')}
        </Tag>
      ),
    },
    {
      title: t('logs.responseHealed'),
      dataIndex: 'responseHealed',
      key: 'responseHealed',
      render: (value: boolean | undefined) => (
        <Tag color={value ? 'blue' : 'default'}>
          {value ? t('logs.yes') : t('logs.no')}
        </Tag>
      ),
    },
    {
      title: t('logs.healingStrategy'),
      dataIndex: 'healingStrategy',
      key: 'healingStrategy',
      render: (value: string | undefined) => value || 'N/A',
    },
  ];

  const filteredLogs = logs.filter((item) => {
    if (requestIdFilter && !item.requestId.toLowerCase().includes(requestIdFilter.toLowerCase())) {
      return false;
    }
    if (providerFilter && item.providerName !== providerFilter) {
      return false;
    }
    if (statusFilter && String(item.statusCode) !== statusFilter) {
      return false;
    }
    if (errorOnly === 'with_error' && !item.errorCode) {
      return false;
    }
    if (errorOnly === 'without_error' && item.errorCode) {
      return false;
    }
    if (changedOnly === 'changed' && !item.routeChanged) {
      return false;
    }
    if (changedOnly === 'unchanged' && item.routeChanged) {
      return false;
    }
    return true;
  });

  const providerOptions = Array.from(new Set(logs.map((item) => item.providerName).filter(Boolean))) as string[];
  const statusOptions = Array.from(new Set(logs.map((item) => String(item.statusCode))));

  return (
    <Card title={t('logs.title')}>
      <Space wrap style={{ marginBottom: 16 }}>
        <Typography.Text strong>{t('logs.filters')}</Typography.Text>
        <Input
          value={requestIdFilter}
          onChange={(event) => setRequestIdFilter(event.target.value)}
          placeholder={t('logs.requestIdFilter')}
          style={{ width: 220 }}
        />
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
        <Select
          allowClear
          value={providerFilter}
          onChange={(value) => setProviderFilter(value)}
          placeholder={t('logs.providerFilter')}
          style={{ width: 180 }}
          options={providerOptions.map((item) => ({ label: item, value: item }))}
        />
        <Select
          allowClear
          value={statusFilter}
          onChange={(value) => setStatusFilter(value)}
          placeholder={t('logs.statusFilter')}
          style={{ width: 160 }}
          options={statusOptions.map((item) => ({ label: item, value: item }))}
        />
        <Select
          allowClear
          value={errorOnly}
          onChange={(value) => setErrorOnly(value)}
          placeholder={t('logs.errorFilter')}
          style={{ width: 180 }}
          options={[
            { label: 'With Error', value: 'with_error' },
            { label: 'Without Error', value: 'without_error' },
          ]}
        />
        <Select
          allowClear
          value={changedOnly}
          onChange={(value) => setChangedOnly(value)}
          placeholder={t('logs.changedOnly')}
          style={{ width: 180 }}
          options={[
            { label: t('logs.yes'), value: 'changed' },
            { label: t('logs.no'), value: 'unchanged' },
          ]}
        />
        <Button
          onClick={() => {
            setRequestIdFilter('');
            setOrganizationFilter(undefined);
            setProjectFilter(undefined);
            setProviderFilter(undefined);
            setStatusFilter(undefined);
            setErrorOnly(undefined);
            setChangedOnly(undefined);
          }}
        >
          {t('logs.clearFilters')}
        </Button>
      </Space>
      <Table
        dataSource={filteredLogs.map((item) => ({ ...item, key: item.requestId }))}
        columns={columns}
        loading={loading}
        pagination={false}
        expandable={{
          expandedRowRender: (record: RequestLog) => (
            <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
              <Typography.Text strong>{t('logs.routeTrace')}</Typography.Text>
              {'\n'}
              {record.routeTrace ? JSON.stringify(record.routeTrace, null, 2) : 'N/A'}
            </Typography.Paragraph>
          ),
        }}
      />
    </Card>
  );
};

export default LogsAdminPage;
