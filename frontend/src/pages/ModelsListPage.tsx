import React, { useEffect, useState } from 'react';
import { Table, message, Card } from 'antd';
import { listModels } from '../api';
import { ModelListResponse } from '../types';
import { useI18n } from '../i18n';

const ModelsListPage: React.FC = () => {
  const { t } = useI18n();
  const [models, setModels] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchModels = async () => {
      setLoading(true);
      try {
        const response: ModelListResponse = await listModels();
        setModels(response.models);
        message.success(t('modelsList.loaded'));
      } catch (error) {
        message.error(t('modelsList.failed'));
      } finally {
        setLoading(false);
      }
    };

    fetchModels();
  }, []);

  const columns = [
    {
      title: t('modelsList.modelId'),
      dataIndex: 'model',
      key: 'model',
    },
  ];

  return (
    <Card title={t('modelsList.title')}>
      <Table
        dataSource={models.map((model) => ({ key: model, model }))}
        columns={columns}
        loading={loading}
        pagination={false}
      />
    </Card>
  );
};

export default ModelsListPage;
