import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, message, Card } from 'antd';
import { getByokKeys, addByokKey } from '../api';
import { ByokKey } from '../types';
import { useI18n } from '../i18n';

const ByokAdminPage: React.FC = () => {
  const { t } = useI18n();
  const [keys, setKeys] = useState<ByokKey[]>([]);
  const [loading, setLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);

  useEffect(() => {
    const fetchKeys = async () => {
      setLoading(true);
      try {
        const response = await getByokKeys();
        setKeys(response);
        message.success(t('byok.loaded'));
      } catch (error) {
        message.error(t('byok.loadFailed'));
      } finally {
        setLoading(false);
      }
    };

    fetchKeys();
  }, []);

  const handleAddKey = async (values: ByokKey) => {
    try {
      await addByokKey(values);
      message.success(t('byok.added'));
      setIsModalVisible(false);
      setKeys([...keys, values]);
    } catch (error) {
      message.error(t('byok.addFailed'));
    }
  };

  const columns = [
    {
      title: t('byok.keyId'),
      dataIndex: 'keyId',
      key: 'keyId',
    },
    {
      title: t('common.organization'),
      dataIndex: 'organization',
      key: 'organization',
    },
    {
      title: t('common.project'),
      dataIndex: 'project',
      key: 'project',
    },
  ];

  return (
    <Card title={t('byok.title')}>
      <Button type="primary" onClick={() => setIsModalVisible(true)}>
        {t('byok.add')}
      </Button>
      <Table dataSource={keys} columns={columns} loading={loading} pagination={false} />
      <Modal
        title={t('byok.modal')}
        visible={isModalVisible}
        onCancel={() => setIsModalVisible(false)}
        footer={null}
      >
        <Form layout="vertical" onFinish={handleAddKey}>
          <Form.Item
            label={t('byok.keyId')}
            name="keyId"
            rules={[{ required: true, message: t('byok.keyRequired') }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            label={t('common.organization')}
            name="organization"
            rules={[{ required: true, message: t('byok.orgRequired') }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            label={t('common.project')}
            name="project"
            rules={[{ required: true, message: t('byok.projectRequired') }]}
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

export default ByokAdminPage;
