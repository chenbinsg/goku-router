import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Descriptions, Input, Popconfirm, Select, Space, Table, Tabs, Tag, Typography, message } from 'antd';
import { PoweroffOutlined, SettingOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { getSystemEnvironment, restartRouter, type SystemEnvironmentItem, type SystemEnvironmentSnapshot } from '../api';
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
  const [restartLoading, setRestartLoading] = useState(false);

  useEffect(() => {
    if (user?.role !== 'superadmin') return;
    setLoading(true);
    getSystemEnvironment()
      .then(setSnapshot)
      .catch((error) => message.error(error?.response?.data?.detail || t('environment.loadFailed')))
      .finally(() => setLoading(false));
  }, [user?.role]);

  const rows = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return (snapshot?.items || []).filter((item) =>
      (category === 'all' || item.category === category)
      && (!query || [item.name, item.value, item.source, item.category]
        .some((value) => String(value || '').toLocaleLowerCase().includes(query))),
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
      render: (value?: string) => (
        <Typography.Text code copyable={Boolean(value)} style={{ wordBreak: 'break-all' }}>
          {value || '—'}
        </Typography.Text>
      ),
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

  const handleRestart = async () => {
    setRestartLoading(true);
    try {
      await restartRouter();
      message.success(t('system.restartRequested'));
    } catch (error: any) {
      message.error(error?.response?.data?.detail || t('system.restartFailed'));
      setRestartLoading(false);
    }
  };

  if (user?.role !== 'superadmin') {
    return <Alert type="error" showIcon message={t('environment.superadminOnly')} />;
  }

  return (
    <Card title={t('environment.title')}>
      <Tabs items={[
        {
          key: 'parameters',
          label: t('environment.parametersTab'),
          icon: <SettingOutlined />,
          children: <>
            <Alert type="warning" showIcon message={t('environment.description')} style={{ marginBottom: 16 }} />
            {snapshot && (
              <Space wrap style={{ marginBottom: 16 }}>
                <Typography.Text><strong>{t('environment.startedAt')}:</strong> {new Date(snapshot.startup_time).toLocaleString()}</Typography.Text>
                <Typography.Text><strong>{t('environment.dotenvPath')}:</strong> <Typography.Text code>{snapshot.dotenv_path}</Typography.Text></Typography.Text>
              </Space>
            )}
            <Space wrap style={{ marginBottom: 16, display: 'flex' }}>
              <Input.Search
                allowClear
                placeholder={t('environment.search')}
                onChange={(event) => {
                  setSearch(event.target.value);
                  if (event.target.value) setCategory('all');
                }}
                style={{ width: 280 }}
              />
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
          </>,
        },
        {
          key: 'startup',
          label: t('environment.startupTab'),
          icon: <PoweroffOutlined />,
          children: <>
            <Alert type="warning" showIcon message={t('environment.restartWarning')} style={{ marginBottom: 16 }} />
            <Descriptions bordered column={1} style={{ marginBottom: 20 }}>
              <Descriptions.Item label={t('environment.startedAt')}>
                {snapshot ? new Date(snapshot.startup_time).toLocaleString() : '—'}
              </Descriptions.Item>
              <Descriptions.Item label={t('environment.processStatus')}>
                <Tag color="green">{t('environment.running')}</Tag>
              </Descriptions.Item>
            </Descriptions>
            <Popconfirm
              title={t('system.restartConfirmTitle')}
              description={t('system.restartConfirmDesc')}
              okText={t('system.restart')}
              cancelText={t('common.cancel')}
              okButtonProps={{ danger: true }}
              onConfirm={handleRestart}
            >
              <Button danger type="primary" icon={<PoweroffOutlined />} loading={restartLoading}>
                {t('system.restart')}
              </Button>
            </Popconfirm>
          </>,
        },
      ]} />
    </Card>
  );
};

export default SystemEnvironmentPage;
