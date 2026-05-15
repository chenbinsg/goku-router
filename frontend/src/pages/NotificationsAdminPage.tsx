import React, { useState, useEffect } from 'react';
import { Table, Button, Modal, Form, Input, message, Card } from 'antd';
import { getNotifications, addNotification, detectAnomalyNotifications } from '../api';
import { Notification } from '../types';
import { useI18n } from '../i18n';

const NotificationsAdminPage: React.FC = () => {
  const { t } = useI18n();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);

  useEffect(() => {
    const fetchNotifications = async () => {
      setLoading(true);
      try {
        const response = await getNotifications();
        setNotifications(response);
        message.success(t('notifications.loaded'));
      } catch (error) {
        message.error(t('notifications.loadFailed'));
      } finally {
        setLoading(false);
      }
    };

    fetchNotifications();
  }, []);

  const handleAddNotification = async (values: Notification) => {
    try {
      await addNotification(values);
      message.success(t('notifications.added'));
      setIsModalVisible(false);
      setNotifications([...notifications, values]);
    } catch (error) {
      message.error(t('notifications.addFailed'));
    }
  };

  const handleDetectAnomalies = async () => {
    try {
      const created = await detectAnomalyNotifications();
      setNotifications([...(created || []), ...notifications]);
      message.success(t('notifications.detected', { count: created.length }));
    } catch (error) {
      message.error(t('notifications.detectFailed'));
    }
  };

  const columns = [
    {
      title: t('notifications.notificationType'),
      dataIndex: 'type',
      key: 'type',
    },
    {
      title: t('common.message'),
      dataIndex: 'message',
      key: 'message',
    },
    {
      title: t('common.timestamp'),
      dataIndex: 'timestamp',
      key: 'timestamp',
    },
  ];

  return (
    <Card title={t('notifications.title')}>
      <Button type="primary" onClick={() => setIsModalVisible(true)}>
        {t('notifications.add')}
      </Button>
      <Button onClick={handleDetectAnomalies} style={{ marginLeft: 8 }}>
        {t('notifications.detectAnomalies')}
      </Button>
      <Table dataSource={notifications.map((item, index) => ({ ...item, key: item.id || `${item.type}-${index}` }))} columns={columns} loading={loading} pagination={false} />
      <Modal
        title={t('notifications.modal')}
        open={isModalVisible}
        onCancel={() => setIsModalVisible(false)}
        footer={null}
      >
        <Form layout="vertical" onFinish={handleAddNotification}>
          <Form.Item
            label={t('notifications.notificationType')}
            name="type"
            rules={[{ required: true, message: t('notifications.typeRequired') }]}
          >
            <Input />
          </Form.Item>
          <Form.Item
            label={t('common.message')}
            name="message"
            rules={[{ required: true, message: t('notifications.messageRequired') }]}
          >
            <Input.TextArea rows={4} />
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

export default NotificationsAdminPage;
