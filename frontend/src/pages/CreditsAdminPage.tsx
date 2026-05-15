import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, message, Card } from 'antd';
import { getCredits, addCredit } from '../api';
import { Credit } from '../types';
import { useI18n } from '../i18n';

const CreditsAdminPage: React.FC = () => {
  const { t } = useI18n();
  const [credits, setCredits] = useState<Credit[]>([]);
  const [loading, setLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);

  useEffect(() => {
    const fetchCredits = async () => {
      setLoading(true);
      try {
        const response = await getCredits();
        setCredits(response);
        message.success(t('credits.loaded'));
      } catch (error) {
        message.error(t('credits.loadFailed'));
      } finally {
        setLoading(false);
      }
    };

    fetchCredits();
  }, []);

  const handleAddCredit = async (values: Credit) => {
    try {
      await addCredit(values);
      message.success(t('credits.added'));
      setIsModalVisible(false);
      setCredits([...credits, values]);
    } catch (error) {
      message.error(t('credits.addFailed'));
    }
  };

  const columns = [
    {
      title: t('credits.creditId'),
      dataIndex: 'creditId',
      key: 'creditId',
    },
    {
      title: t('common.amount'),
      dataIndex: 'amount',
      key: 'amount',
    },
    {
      title: t('common.organization'),
      dataIndex: 'organization',
      key: 'organization',
    },
  ];

  return (
    <Card title={t('credits.title')}>
      <Button type="primary" onClick={() => setIsModalVisible(true)}>
        {t('credits.add')}
      </Button>
      <Table dataSource={credits} columns={columns} loading={loading} pagination={false} />
      <Modal
        title={t('credits.modal')}
        visible={isModalVisible}
        onCancel={() => setIsModalVisible(false)}
        footer={null}
      >
        <Form layout="vertical" onFinish={handleAddCredit}>
          <Form.Item
            label={t('credits.creditId')}
            name="creditId"
            rules={[{ required: true, message: t('credits.creditRequired') }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            label={t('common.amount')}
            name="amount"
            rules={[{ required: true, message: t('credits.amountRequired') }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            label={t('common.organization')}
            name="organization"
            rules={[{ required: true, message: t('credits.orgRequired') }]}
          >
            <Input />
          </Form.Item>
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

export default CreditsAdminPage;
