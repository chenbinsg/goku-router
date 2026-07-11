import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Card, Input, Select, Space, Table, Tag, Typography, message } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { getSystemEnvironment, type SystemEnvironmentItem, type SystemEnvironmentSnapshot } from '../api';
import { useI18n } from '../i18n';
import { getUser } from '../utils/auth';

const categoryColors: Record<string, string> = {
  runtime: 'blue',
  database: 'purple',
  provider: 'cyan',
  security: 'red',
  routing: 'orange',
  observability: 'green',
};

const sourceColors: Record<string, string> = {
  process_env: 'geekblue',
  dotenv: 'gold',
  default: 'default',
};

const SystemEnvironmentPage: React.FC = () => {
  const { t } = useI18n();
  const user = getUser();
  const [snapshot, setSnapshot] = useState<SystemEnvironmentSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [category, setCategory] = useState<string>('all');
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (user?.role !== 'superadmin') return;
    setLoading(true);
    getSystemEnvironment()
      .then(setSnapshot)
      .catch((error) => message.error(error?.response?.data?.detail || t('environment.loadFailed')))
      .finally(() => setLoading(false));
  }, [user?.role]);

  const rows = useMemo(() => {
    const query = search.trim().toUpperCase();
    return (snapshot?.items || []).filter((item) =>
      (category === 'all' || item.category === category)
      && (!query || item.name.includes(query)),
    );
  }, [snapshot, category, search]);

  const columns: ColumnsType<SystemEnvironmentItem> = [
    {
      title: t('common.name'),
      dataIndex: 'name',
      width: 300,
      fixed: 'left',
      render: (name: string) => <Typography.Text code copyable>{name}</Typography.Text>,
    },
    {
      title: t('environment.value'),
      dataIndex: 'value',
      ellipsis: true,
      render: (value?: string) => <Typography.Text code>{value || '—'}</Typography.Text>,
    },
    {
      title: t('environment.category'),
      dataIndex: 'category',
      width: 140,
      render: (value: string) => <Tag color={categoryColors[value]}>{value}</Tag>,
    },
    {
      title: t('environment.source'),
      dataIndex: 'source',
      width: 140,
      render: (value: string) => <Tag color={sourceColors[value]}>{value}</Tag>,
    },
    {
      title: t('environment.configured'),
      dataIndex: 'configured',
      width: 110,
      render: (value: boolean) => <Tag color={value ? 'green' : 'default'}>{value ? 'Yes' : 'No'}</Tag>,
    },
    {
      title: t('environment.restart'),
      dataIndex: 'restart_required',
      width: 130,
      render: (value: boolean) => <Tag color={value ? 'orange' : 'default'}>{value ? 'Yes' : 'No'}</Tag>,
    },
  ];

  if (user?.role !== 'superadmin') {
    return <Alert type="error" showIcon message={t('environment.superadminOnly')} />;
  }

  return (
    <Card title={t('environment.title')}>
      <Alert type="info" showIcon message={t('environment.description')} style={{ marginBottom: 16 }} />
      {snapshot && (
        <Space wrap style={{ marginBottom: 16 }}>
          <Typography.Text><strong>{t('environment.startedAt')}:</strong> {new Date(snapshot.startup_time).toLocaleString()}</Typography.Text>
          <Typography.Text><strong>{t('environment.dotenvPath')}:</strong> <Typography.Text code>{snapshot.dotenv_path}</Typography.Text></Typography.Text>
        </Space>
      )}
      <Space wrap style={{ marginBottom: 16, display: 'flex' }}>
        <Input.Search allowClear placeholder={t('environment.search')} onChange={(event) => setSearch(event.target.value)} style={{ width: 280 }} />
        <Select value={category} onChange={setCategory} style={{ width: 180 }} options={[
          { value: 'all', label: t('environment.allCategories') },
          ...Object.keys(categoryColors).map((value) => ({ value, label: value })),
        ]} />
      </Space>
      <Table<SystemEnvironmentItem>
        rowKey="name"
        loading={loading}
        columns={columns}
        dataSource={rows}
        scroll={{ x: 1100 }}
        pagination={{ pageSize: 20, showSizeChanger: true }}
      />
    </Card>
  );
};

export default SystemEnvironmentPage;
