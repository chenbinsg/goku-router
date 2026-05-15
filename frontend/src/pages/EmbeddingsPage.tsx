import React, { useState } from 'react';
import { Form, Input, Button, message, Card } from 'antd';
import { createEmbedding } from '../api';
import { EmbeddingRequest, EmbeddingResponse } from '../types';
import { useI18n } from '../i18n';

const EmbeddingsPage: React.FC = () => {
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);
  const [embedding, setEmbedding] = useState<number[] | null>(null);

  const onFinish = async (values: EmbeddingRequest) => {
    setLoading(true);
    try {
      const response: EmbeddingResponse = await createEmbedding(values);
      setEmbedding(response.embedding);
      message.success(t('embeddings.success'));
    } catch (error) {
      message.error(t('embeddings.failure'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card title={t('embeddings.title')}>
      <Form layout="vertical" onFinish={onFinish}>
        <Form.Item
          label={t('common.text')}
          name="text"
          rules={[{ required: true, message: t('embeddings.textRequired') }]}
        >
          <Input.TextArea rows={4} />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>
            {t('common.submit')}
          </Button>
        </Form.Item>
      </Form>
      {embedding && (
        <Card type="inner" title={t('embeddings.result')}>
          <pre>{JSON.stringify(embedding, null, 2)}</pre>
        </Card>
      )}
    </Card>
  );
};

export default EmbeddingsPage;
