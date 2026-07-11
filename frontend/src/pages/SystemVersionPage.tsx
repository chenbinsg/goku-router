import React, { useEffect, useState } from 'react';
import { Button, Card, Descriptions, Tag, message } from 'antd';
import { GithubOutlined } from '@ant-design/icons';
import { getSystemInfo, type SystemInfo } from '../api';
import { useI18n } from '../i18n';

const SystemVersionPage: React.FC = () => {
  const { t } = useI18n();
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    getSystemInfo()
      .then(setInfo)
      .catch(() => message.error(t('version.loadFailed')))
      .finally(() => setLoading(false));
  }, []);

  const normalizedVersion = info?.version?.replace(/^v/, '') || '';
  const releaseUrl = normalizedVersion
    ? `https://github.com/chenbinsg/goku-router/releases/tag/v${normalizedVersion}`
    : 'https://github.com/chenbinsg/goku-router/releases';

  return (
    <Card title={t('version.title')} loading={loading}>
      <Descriptions bordered column={1}>
        <Descriptions.Item label={t('version.current')}>
          <Tag color="blue">{info?.version || '—'}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label={t('version.serverTime')}>
          {info?.server_time_utc || '—'}
        </Descriptions.Item>
        <Descriptions.Item label="GitHub">
          <Button icon={<GithubOutlined />} href={releaseUrl} target="_blank" rel="noreferrer">
            {t('version.release')}
          </Button>
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );
};

export default SystemVersionPage;
