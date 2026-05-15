import React, { useState, useEffect } from 'react';
import { Button, Card, Form, Input, InputNumber, Modal, Space, Table, Typography, message } from 'antd';
import {
  addGuardrailPolicyPreset,
  addRouteScoringExperiment,
  addWorkspaceGuardrail,
  compareGuardrailPolicies,
  dryRunGuardrails,
  dryRunGuardrailsBatch,
  exportGuardrailPolicyCompareReport,
  exportRouteReplayReport,
  exportDryRunGuardrailsBatch,
  getGuardrails,
  getGuardrailPolicyPresets,
  getOrganizations,
  getProjects,
  getRouteScoringProfile,
  getRouteScoringExperiments,
  getSecurityLogs,
  getWorkspaceGuardrails,
  recalibrateRouteScoringProfile,
  replayRouteScoring,
  trainRouteScoringProfile,
  updateGuardrails,
  updateGuardrailPolicyPreset,
  updateRouteScoringExperiment,
  updateWorkspaceGuardrail,
} from '../api';
import {
  BatchPolicyDryRunResponse,
  GuardrailConfig,
  GuardrailPolicyCompareResponse,
  GuardrailPolicyPreset,
  Organization,
  PolicyDryRunResult,
  Project,
  RouteReplayResponse,
  RouteScoringExperiment,
  RouteScoringProfile,
  RouteScoringRecalibrationResult,
  RouteScoringTrainResult,
  SecurityLog,
  WorkspaceGuardrailConfig,
} from '../types';
import { useI18n } from '../i18n';

const SecurityAdminPage: React.FC = () => {
  const { t } = useI18n();
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [logs, setLogs] = useState<SecurityLog[]>([]);
  const [workspaceGuardrails, setWorkspaceGuardrails] = useState<WorkspaceGuardrailConfig[]>([]);
  const [policyPresets, setPolicyPresets] = useState<GuardrailPolicyPreset[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [workspaceSaving, setWorkspaceSaving] = useState(false);
  const [workspaceModalOpen, setWorkspaceModalOpen] = useState(false);
  const [editingWorkspaceGuardrail, setEditingWorkspaceGuardrail] = useState<WorkspaceGuardrailConfig | null>(null);
  const [presetSaving, setPresetSaving] = useState(false);
  const [presetModalOpen, setPresetModalOpen] = useState(false);
  const [editingPolicyPreset, setEditingPolicyPreset] = useState<GuardrailPolicyPreset | null>(null);
  const [dryRunLoading, setDryRunLoading] = useState(false);
  const [dryRunResult, setDryRunResult] = useState<PolicyDryRunResult | null>(null);
  const [batchDryRunLoading, setBatchDryRunLoading] = useState(false);
  const [batchDryRunResult, setBatchDryRunResult] = useState<BatchPolicyDryRunResponse | null>(null);
  const [policyCompareLoading, setPolicyCompareLoading] = useState(false);
  const [policyCompareResult, setPolicyCompareResult] = useState<GuardrailPolicyCompareResponse | null>(null);
  const [trainingLoading, setTrainingLoading] = useState(false);
  const [trainingResult, setTrainingResult] = useState<RouteScoringTrainResult | null>(null);
  const [recalibrationLoading, setRecalibrationLoading] = useState(false);
  const [recalibrationResult, setRecalibrationResult] = useState<RouteScoringRecalibrationResult | null>(null);
  const [scoringProfile, setScoringProfile] = useState<RouteScoringProfile | null>(null);
  const [experiments, setExperiments] = useState<RouteScoringExperiment[]>([]);
  const [experimentSaving, setExperimentSaving] = useState(false);
  const [experimentModalOpen, setExperimentModalOpen] = useState(false);
  const [editingExperiment, setEditingExperiment] = useState<RouteScoringExperiment | null>(null);
  const [replayLoading, setReplayLoading] = useState(false);
  const [replayResult, setReplayResult] = useState<RouteReplayResponse | null>(null);
  const [form] = Form.useForm<GuardrailConfig>();
  const [dryRunForm] = Form.useForm();
  const [batchDryRunForm] = Form.useForm();
  const [trainForm] = Form.useForm();
  const [recalibrationForm] = Form.useForm();
  const [replayForm] = Form.useForm();
  const [workspaceGuardrailForm] = Form.useForm();
  const [policyPresetForm] = Form.useForm();
  const [policyCompareForm] = Form.useForm();
  const [experimentForm] = Form.useForm();

  const buildGuardrailPayload = () => {
    const currentGuardrails = form.getFieldsValue();
    return {
      allowedProviders: String(currentGuardrails.allowedProviders || '').split(',').map((item) => item.trim()).filter(Boolean),
      deniedProviders: String(currentGuardrails.deniedProviders || '').split(',').map((item) => item.trim()).filter(Boolean),
      blockedWords: String(currentGuardrails.blockedWords || '').split(',').map((item) => item.trim()).filter(Boolean),
      maxPromptChars: Number(currentGuardrails.maxPromptChars || 4000),
      retentionMode: currentGuardrails.retentionMode || 'standard',
    };
  };

  useEffect(() => {
    const fetchSecurityData = async () => {
      setLoading(true);
      try {
        const [
          auditLogs,
          guardrails,
          routeScoringProfile,
          experimentItems,
          organizationItems,
          projectItems,
          workspaceGuardrailItems,
          policyPresetItems,
        ] = await Promise.all([
          getSecurityLogs(),
          getGuardrails(),
          getRouteScoringProfile(),
          getRouteScoringExperiments(),
          getOrganizations(),
          getProjects(),
          getWorkspaceGuardrails(),
          getGuardrailPolicyPresets(),
        ]);
        setLogs(auditLogs);
        setScoringProfile(routeScoringProfile);
        setExperiments(experimentItems);
        setOrganizations(organizationItems);
        setProjects(projectItems);
        setWorkspaceGuardrails(workspaceGuardrailItems);
        setPolicyPresets(policyPresetItems);
        form.setFieldsValue({
          ...guardrails,
          allowedProviders: guardrails.allowedProviders.join(', '),
          deniedProviders: guardrails.deniedProviders.join(', '),
          blockedWords: guardrails.blockedWords.join(', '),
        } as unknown as GuardrailConfig);
        batchDryRunForm.setFieldsValue({
          datasetPath: 'evals/datasets/finance_compliance_pack.json',
          strategies: 'current_production_policy, openrouter_like_auto',
          workspaceLabel: 'Default Workspace',
        });
        policyCompareForm.setFieldsValue({
          datasetPath: 'evals/datasets/finance_compliance_pack.json',
          strategies: 'current_production_policy, openrouter_like_auto',
          workspaceLabel: 'Default Workspace',
          baselinePolicyName: policyPresetItems[0]?.name || 'balanced_default',
          comparisonPolicyName: policyPresetItems[1]?.name || policyPresetItems[0]?.name || 'finance_strict',
        });
        trainForm.setFieldsValue({
          datasetPath: 'evals/datasets/finance_compliance_pack.json',
          profileName: 'learned_eval_profile',
          baselineStrategy: 'current_production_policy',
        });
        recalibrationForm.setFieldsValue({
          profileName: 'learned_feedback_profile',
          limit: 100,
        });
        replayForm.setFieldsValue({
          source: 'dataset',
          datasetPath: 'evals/datasets/finance_compliance_pack.json',
          strategy: 'current_production_policy',
          limit: 20,
          organizationId: undefined,
          projectId: undefined,
          baselineProfileName: 'default_heuristic_profile',
          comparisonProfileName: routeScoringProfile.name,
        });
        message.success(t('security.loaded'));
      } catch (error) {
        message.error(t('security.loadFailed'));
      } finally {
        setLoading(false);
      }
    };

    fetchSecurityData();
  }, [form, t, batchDryRunForm, policyCompareForm, recalibrationForm, replayForm, trainForm]);

  const handleSave = async (values: any) => {
    setSaving(true);
    try {
      await updateGuardrails({
        allowedProviders: String(values.allowedProviders || '').split(',').map((item) => item.trim()).filter(Boolean),
        deniedProviders: String(values.deniedProviders || '').split(',').map((item) => item.trim()).filter(Boolean),
        blockedWords: String(values.blockedWords || '').split(',').map((item) => item.trim()).filter(Boolean),
        maxPromptChars: Number(values.maxPromptChars || 4000),
        retentionMode: values.retentionMode || 'standard',
      });
      message.success(t('security.updated'));
    } catch {
      message.error(t('security.loadFailed'));
    } finally {
      setSaving(false);
    }
  };

  const columns = [
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
    },
    {
      title: t('common.actions'),
      dataIndex: 'action',
      key: 'action',
    },
    {
      title: t('common.details'),
      dataIndex: 'details',
      key: 'details',
    },
    {
      title: t('common.timestamp'),
      dataIndex: 'timestamp',
      key: 'timestamp',
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card title={t('security.guardrails')}>
        <Form form={form} layout="vertical" onFinish={handleSave}>
          <Form.Item label={t('security.allowedProviders')} name="allowedProviders">
            <Input placeholder="provider_primary,provider_backup" />
          </Form.Item>
          <Form.Item label={t('security.deniedProviders')} name="deniedProviders">
            <Input placeholder="provider_backup" />
          </Form.Item>
          <Form.Item label={t('security.blockedWords')} name="blockedWords">
            <Input placeholder="forbidden,blocked" />
          </Form.Item>
          <Form.Item label={t('security.maxPromptChars')} name="maxPromptChars">
            <InputNumber min={100} max={20000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label={t('security.retentionMode')} name="retentionMode">
            <Input placeholder="standard" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={saving}>
              {t('security.saveGuardrails')}
            </Button>
          </Form.Item>
        </Form>
      </Card>
      <Card
        title={t('security.policyPresets')}
        extra={(
          <Button
            type="primary"
            onClick={() => {
              setEditingPolicyPreset(null);
              policyPresetForm.resetFields();
              policyPresetForm.setFieldsValue({ maxPromptChars: 4000, retentionMode: 'standard' });
              setPresetModalOpen(true);
            }}
          >
            {t('security.addPolicyPreset')}
          </Button>
        )}
      >
        <Table
          dataSource={policyPresets.map((item) => ({ ...item, key: item.id || item.name }))}
          pagination={false}
          columns={[
            { title: t('common.name'), dataIndex: 'name', key: 'name' },
            { title: t('common.details'), dataIndex: 'description', key: 'description' },
            { title: t('dashboard.organizationName'), dataIndex: 'organizationName', key: 'organizationName', render: (value?: string) => value || 'N/A' },
            { title: t('dashboard.projectName'), dataIndex: 'projectName', key: 'projectName', render: (value?: string) => value || 'N/A' },
            { title: t('security.allowedProviders'), dataIndex: 'allowedProviders', key: 'allowedProviders', render: (value?: string[]) => value?.join(', ') || 'N/A' },
            { title: t('security.deniedProviders'), dataIndex: 'deniedProviders', key: 'deniedProviders', render: (value?: string[]) => value?.join(', ') || 'N/A' },
            { title: t('security.maxPromptChars'), dataIndex: 'maxPromptChars', key: 'maxPromptChars' },
            { title: t('security.retentionMode'), dataIndex: 'retentionMode', key: 'retentionMode' },
            {
              title: t('common.actions'),
              key: 'actions',
              render: (_: unknown, record: GuardrailPolicyPreset) => (
                <Button
                  onClick={() => {
                    setEditingPolicyPreset(record);
                    policyPresetForm.setFieldsValue({
                      ...record,
                      allowedProviders: (record.allowedProviders || []).join(', '),
                      deniedProviders: (record.deniedProviders || []).join(', '),
                      blockedWords: (record.blockedWords || []).join(', '),
                    });
                    setPresetModalOpen(true);
                  }}
                >
                  {t('common.edit')}
                </Button>
              ),
            },
          ]}
        />
      </Card>
      <Card
        title={t('security.workspaceGuardrails')}
        extra={(
          <Button
            type="primary"
            onClick={() => {
              setEditingWorkspaceGuardrail(null);
              workspaceGuardrailForm.resetFields();
              workspaceGuardrailForm.setFieldsValue({ retentionMode: 'standard' });
              setWorkspaceModalOpen(true);
            }}
          >
            {t('security.addWorkspaceGuardrail')}
          </Button>
        )}
      >
        <Table
          dataSource={workspaceGuardrails.map((item) => ({ ...item, key: item.id || `${item.organizationId}-${item.projectId}` }))}
          pagination={false}
          columns={[
            { title: t('dashboard.organizationName'), dataIndex: 'organizationName', key: 'organizationName' },
            { title: t('dashboard.projectName'), dataIndex: 'projectName', key: 'projectName' },
            { title: t('security.allowedProviders'), dataIndex: 'allowedProviders', key: 'allowedProviders', render: (value?: string[]) => value?.join(', ') || 'N/A' },
            { title: t('security.deniedProviders'), dataIndex: 'deniedProviders', key: 'deniedProviders', render: (value?: string[]) => value?.join(', ') || 'N/A' },
            { title: t('security.blockedWords'), dataIndex: 'blockedWords', key: 'blockedWords', render: (value?: string[]) => value?.join(', ') || 'N/A' },
            { title: t('security.maxPromptChars'), dataIndex: 'maxPromptChars', key: 'maxPromptChars', render: (value?: number) => value ?? 'N/A' },
            { title: t('security.retentionMode'), dataIndex: 'retentionMode', key: 'retentionMode', render: (value?: string) => value || 'N/A' },
            {
              title: t('common.actions'),
              key: 'actions',
              render: (_: unknown, record: WorkspaceGuardrailConfig) => (
                <Button
                  onClick={() => {
                    setEditingWorkspaceGuardrail(record);
                    workspaceGuardrailForm.setFieldsValue({
                      organizationId: record.organizationId,
                      projectId: record.projectId,
                      allowedProviders: (record.allowedProviders || []).join(', '),
                      deniedProviders: (record.deniedProviders || []).join(', '),
                      blockedWords: (record.blockedWords || []).join(', '),
                      maxPromptChars: record.maxPromptChars,
                      retentionMode: record.retentionMode,
                    });
                    setWorkspaceModalOpen(true);
                  }}
                >
                  {t('common.edit')}
                </Button>
              ),
            },
          ]}
        />
      </Card>
      <Card title={t('security.auditLogs')}>
        <Table dataSource={logs.map((item) => ({ ...item, key: item.id }))} columns={columns} loading={loading} pagination={false} />
      </Card>
      <Card title={t('security.dryRun')}>
        <Form
          form={dryRunForm}
          layout="vertical"
          initialValues={{ model: 'model1', messages: 'Review this policy-sensitive request' }}
          onFinish={async (values) => {
            setDryRunLoading(true);
            try {
              const result = await dryRunGuardrails({
                model: values.model,
                messages: [{ role: 'user', content: values.messages }],
                guardrails: buildGuardrailPayload(),
              });
              setDryRunResult(result);
            } catch {
              message.error(t('security.loadFailed'));
            } finally {
              setDryRunLoading(false);
            }
          }}
        >
          <Form.Item label={t('security.dryRunModel')} name="model">
            <Input />
          </Form.Item>
          <Form.Item label={t('security.dryRunMessages')} name="messages">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={dryRunLoading}>
              {t('security.runDryRun')}
            </Button>
          </Form.Item>
        </Form>
        {dryRunResult && (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Typography.Paragraph style={{ marginBottom: 0 }}>
              <Typography.Text strong>{t('security.dryRunResult')}</Typography.Text>
              {' '}
              {`${dryRunResult.selectedProvider || 'N/A'} | accepted=${dryRunResult.acceptedCandidates} | rejected=${dryRunResult.rejectedCandidates}`}
            </Typography.Paragraph>
            <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
              <Typography.Text strong>{t('security.policyDiff')}</Typography.Text>
              {'\n'}
              {JSON.stringify(dryRunResult.policyDiff, null, 2)}
            </Typography.Paragraph>
            <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
              <Typography.Text strong>{t('security.eligibilitySummary')}</Typography.Text>
              {'\n'}
              {JSON.stringify(dryRunResult.eligibilitySummary, null, 2)}
            </Typography.Paragraph>
            <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
              <Typography.Text strong>{t('logs.routeTrace')}</Typography.Text>
              {'\n'}
              {JSON.stringify(dryRunResult.routeTrace, null, 2)}
            </Typography.Paragraph>
          </Space>
        )}
      </Card>
      <Card title={t('security.batchDryRun')}>
        <Form
          form={batchDryRunForm}
          layout="vertical"
          onFinish={async (values) => {
            setBatchDryRunLoading(true);
            try {
              const result = await dryRunGuardrailsBatch({
                datasetPath: values.datasetPath,
                strategies: String(values.strategies || '')
                  .split(',')
                  .map((item) => item.trim())
                  .filter(Boolean),
                workspaceLabel: values.workspaceLabel,
                guardrails: buildGuardrailPayload(),
              });
              setBatchDryRunResult(result);
            } catch {
              message.error(t('security.loadFailed'));
            } finally {
              setBatchDryRunLoading(false);
            }
          }}
        >
          <Form.Item label={t('security.batchDataset')} name="datasetPath">
            <Input />
          </Form.Item>
          <Form.Item label={t('security.batchStrategies')} name="strategies">
            <Input />
          </Form.Item>
          <Form.Item label={t('security.batchWorkspace')} name="workspaceLabel">
            <Input />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={batchDryRunLoading}>
              {t('security.runBatchDryRun')}
            </Button>
            <Button
              onClick={async () => {
                try {
                  const values = batchDryRunForm.getFieldsValue();
                  const artifact = await exportDryRunGuardrailsBatch({
                    datasetPath: values.datasetPath,
                    strategies: String(values.strategies || '')
                      .split(',')
                      .map((item: string) => item.trim())
                      .filter(Boolean),
                    workspaceLabel: values.workspaceLabel,
                    guardrails: buildGuardrailPayload(),
                  });
                  window.open(artifact.downloadUrl, '_blank');
                  message.success(t('security.exportBatchPreview'));
                } catch {
                  message.error(t('security.exportBatchPreviewFailed'));
                }
              }}
            >
              {t('security.exportBatchPreview')}
            </Button>
          </Form.Item>
        </Form>
        {batchDryRunResult && (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Typography.Paragraph style={{ marginBottom: 0 }}>
              <Typography.Text strong>{t('security.batchDryRunResult')}</Typography.Text>
              {' '}
              {`${batchDryRunResult.successCases}/${batchDryRunResult.totalCases}`}
            </Typography.Paragraph>
            <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
              <Typography.Text strong>{t('security.policyDiff')}</Typography.Text>
              {'\n'}
              {JSON.stringify(batchDryRunResult.policyDiffSummary, null, 2)}
            </Typography.Paragraph>
            <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
              <Typography.Text strong>{t('security.strategySummaries')}</Typography.Text>
              {'\n'}
              {JSON.stringify(batchDryRunResult.strategySummaries, null, 2)}
            </Typography.Paragraph>
            <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
              <Typography.Text strong>{t('security.batchItems')}</Typography.Text>
              {'\n'}
              {JSON.stringify(batchDryRunResult.items, null, 2)}
            </Typography.Paragraph>
          </Space>
        )}
      </Card>
      <Card title={t('security.policyCompare')}>
        <Form
          form={policyCompareForm}
          layout="vertical"
          onFinish={async (values) => {
            setPolicyCompareLoading(true);
            try {
              const result = await compareGuardrailPolicies({
                datasetPath: values.datasetPath,
                strategies: String(values.strategies || '')
                  .split(',')
                  .map((item) => item.trim())
                  .filter(Boolean),
                workspaceLabel: values.workspaceLabel,
                baselinePolicyName: values.baselinePolicyName,
                comparisonPolicyName: values.comparisonPolicyName,
              });
              setPolicyCompareResult(result);
            } catch {
              message.error(t('security.policyCompareFailed'));
            } finally {
              setPolicyCompareLoading(false);
            }
          }}
        >
          <Form.Item label={t('security.batchDataset')} name="datasetPath">
            <Input />
          </Form.Item>
          <Form.Item label={t('security.batchStrategies')} name="strategies">
            <Input />
          </Form.Item>
          <Form.Item label={t('security.batchWorkspace')} name="workspaceLabel">
            <Input />
          </Form.Item>
          <Form.Item label={t('security.baselinePolicyPreset')} name="baselinePolicyName">
            <Input placeholder="balanced_default" />
          </Form.Item>
          <Form.Item label={t('security.comparisonPolicyPreset')} name="comparisonPolicyName">
            <Input placeholder="finance_strict" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={policyCompareLoading}>
              {t('security.runPolicyCompare')}
            </Button>
            <Button
              onClick={async () => {
                try {
                  const values = policyCompareForm.getFieldsValue();
                  const artifact = await exportGuardrailPolicyCompareReport({
                    datasetPath: values.datasetPath,
                    strategies: String(values.strategies || '')
                      .split(',')
                      .map((item: string) => item.trim())
                      .filter(Boolean),
                    workspaceLabel: values.workspaceLabel,
                    baselinePolicyName: values.baselinePolicyName,
                    comparisonPolicyName: values.comparisonPolicyName,
                  });
                  window.open(artifact.downloadUrl, '_blank');
                  message.success(t('security.exportPolicyCompareReport'));
                } catch {
                  message.error(t('security.policyCompareExportFailed'));
                }
              }}
            >
              {t('security.exportPolicyCompareReport')}
            </Button>
          </Form.Item>
        </Form>
        {policyCompareResult && (
          <Space direction="vertical" size={12} style={{ width: '100%' }}>
            <Typography.Paragraph style={{ marginBottom: 0 }}>
              <Typography.Text strong>{t('security.policyCompareResult')}</Typography.Text>
              {' '}
              {`${policyCompareResult.comparisonSummary.changed_provider_cases || 0} provider changes / ${policyCompareResult.comparisonSummary.changed_block_cases || 0} block changes`}
            </Typography.Paragraph>
            <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
              <Typography.Text strong>{t('security.policyDiff')}</Typography.Text>
              {'\n'}
              {JSON.stringify(policyCompareResult.comparisonSummary, null, 2)}
            </Typography.Paragraph>
            <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
              <Typography.Text strong>{t('security.strategySummaries')}</Typography.Text>
              {'\n'}
              {JSON.stringify(policyCompareResult.strategySummaries, null, 2)}
            </Typography.Paragraph>
            <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
              <Typography.Text strong>{t('security.batchItems')}</Typography.Text>
              {'\n'}
              {JSON.stringify(policyCompareResult.items, null, 2)}
            </Typography.Paragraph>
          </Space>
        )}
      </Card>
      <Card title={t('security.routeScoring')}>
        <Form
          form={trainForm}
          layout="vertical"
          onFinish={async (values) => {
            setTrainingLoading(true);
            try {
              const result = await trainRouteScoringProfile({
                datasetPath: values.datasetPath,
                profileName: values.profileName,
                baselineStrategy: values.baselineStrategy,
              });
              setTrainingResult(result);
              setScoringProfile(result);
            } catch {
              message.error(t('security.loadFailed'));
            } finally {
              setTrainingLoading(false);
            }
          }}
        >
          <Form.Item label={t('security.batchDataset')} name="datasetPath">
            <Input />
          </Form.Item>
          <Form.Item label={t('security.profileName')} name="profileName">
            <Input />
          </Form.Item>
          <Form.Item label={t('security.baselineStrategy')} name="baselineStrategy">
            <Input />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={trainingLoading}>
              {t('security.trainProfile')}
            </Button>
          </Form.Item>
        </Form>
        {scoringProfile && (
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap' }}>
            <Typography.Text strong>{t('security.currentProfile')}</Typography.Text>
            {'\n'}
            {JSON.stringify(scoringProfile, null, 2)}
          </Typography.Paragraph>
        )}
        {trainingResult && (
          <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
            <Typography.Text strong>{t('security.trainingResult')}</Typography.Text>
            {'\n'}
            {JSON.stringify(trainingResult, null, 2)}
          </Typography.Paragraph>
        )}
        <Form
          form={recalibrationForm}
          layout="vertical"
          onFinish={async (values) => {
            setRecalibrationLoading(true);
            try {
              const result = await recalibrateRouteScoringProfile({
                profileName: values.profileName,
                limit: Number(values.limit || 100),
                organizationId: values.organizationId ? Number(values.organizationId) : undefined,
                projectId: values.projectId ? Number(values.projectId) : undefined,
                experimentName: values.experimentName || undefined,
              });
              setRecalibrationResult(result);
              setScoringProfile(result);
            } catch {
              message.error(t('security.loadFailed'));
            } finally {
              setRecalibrationLoading(false);
            }
          }}
        >
          <Form.Item label={t('security.feedbackProfileName')} name="profileName">
            <Input />
          </Form.Item>
          <Form.Item label={t('security.replayLimit')} name="limit">
            <InputNumber min={1} max={500} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label={t('apiKeys.organizationId')} name="organizationId">
            <Input placeholder={organizations.map((item) => `${item.id}:${item.name}`).join(', ')} />
          </Form.Item>
          <Form.Item label={t('apiKeys.projectId')} name="projectId">
            <Input placeholder={projects.map((item) => `${item.id}:${item.name}`).join(', ')} />
          </Form.Item>
          <Form.Item label={t('security.experimentName')} name="experimentName">
            <Input placeholder="optional active experiment name" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={recalibrationLoading}>
              {t('security.recalibrateProfile')}
            </Button>
          </Form.Item>
        </Form>
        {recalibrationResult && (
          <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
            <Typography.Text strong>{t('security.recalibrationResult')}</Typography.Text>
            {'\n'}
            {JSON.stringify(recalibrationResult, null, 2)}
          </Typography.Paragraph>
        )}
      </Card>
      <Card
        title={t('security.routeExperiments')}
        extra={(
          <Button
            type="primary"
            onClick={() => {
              setEditingExperiment(null);
              experimentForm.resetFields();
              experimentForm.setFieldsValue({
                controlProfileName: 'default_heuristic_profile',
                trafficPercentage: 50,
                status: 'active',
              });
              setExperimentModalOpen(true);
            }}
          >
            {t('security.addExperiment')}
          </Button>
        )}
      >
        <Table
          dataSource={experiments.map((item) => ({ ...item, key: item.id || item.name }))}
          pagination={false}
          columns={[
            { title: t('common.name'), dataIndex: 'name', key: 'name' },
            { title: t('security.controlProfile'), dataIndex: 'controlProfileName', key: 'controlProfileName' },
            { title: t('security.challengerProfile'), dataIndex: 'challengerProfileName', key: 'challengerProfileName' },
            { title: t('security.trafficPercentage'), dataIndex: 'trafficPercentage', key: 'trafficPercentage' },
            { title: t('common.status'), dataIndex: 'status', key: 'status' },
            {
              title: t('common.actions'),
              key: 'actions',
              render: (_: unknown, record: RouteScoringExperiment) => (
                <Button
                  onClick={() => {
                    setEditingExperiment(record);
                    experimentForm.setFieldsValue(record);
                    setExperimentModalOpen(true);
                  }}
                >
                  {t('common.edit')}
                </Button>
              ),
            },
          ]}
        />
      </Card>
      <Card title={t('security.routeReplay')}>
        <Form
          form={replayForm}
          layout="vertical"
          onFinish={async (values) => {
            setReplayLoading(true);
            try {
              const result = await replayRouteScoring({
                source: values.source,
                datasetPath: values.datasetPath,
                strategy: values.strategy,
                limit: Number(values.limit || 20),
                organizationId: values.organizationId ? Number(values.organizationId) : undefined,
                projectId: values.projectId ? Number(values.projectId) : undefined,
                baselineProfileName: values.baselineProfileName || undefined,
                comparisonProfileName: values.comparisonProfileName || undefined,
              });
              setReplayResult(result);
            } catch {
              message.error(t('security.loadFailed'));
            } finally {
              setReplayLoading(false);
            }
          }}
        >
          <Form.Item label={t('security.replaySource')} name="source">
            <Input />
          </Form.Item>
          <Form.Item label={t('security.replayDataset')} name="datasetPath">
            <Input />
          </Form.Item>
          <Form.Item label={t('apiKeys.organizationId')} name="organizationId">
            <Input placeholder={organizations.map((item) => `${item.id}:${item.name}`).join(', ')} />
          </Form.Item>
          <Form.Item label={t('apiKeys.projectId')} name="projectId">
            <Input placeholder={projects.map((item) => `${item.id}:${item.name}`).join(', ')} />
          </Form.Item>
          <Form.Item label={t('security.baselineStrategy')} name="strategy">
            <Input />
          </Form.Item>
          <Form.Item label={t('security.controlProfile')} name="baselineProfileName">
            <Input placeholder="default_heuristic_profile" />
          </Form.Item>
          <Form.Item label={t('security.challengerProfile')} name="comparisonProfileName">
            <Input placeholder="learned_feedback_profile" />
          </Form.Item>
          <Form.Item label={t('security.replayLimit')} name="limit">
            <InputNumber min={1} max={200} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={replayLoading}>
              {t('security.runReplay')}
            </Button>
            <Button
              onClick={async () => {
                try {
                  const values = replayForm.getFieldsValue();
                  const artifact = await exportRouteReplayReport({
                    source: values.source,
                    datasetPath: values.datasetPath,
                    strategy: values.strategy,
                    limit: Number(values.limit || 20),
                    organizationId: values.organizationId ? Number(values.organizationId) : undefined,
                    projectId: values.projectId ? Number(values.projectId) : undefined,
                    baselineProfileName: values.baselineProfileName || undefined,
                    comparisonProfileName: values.comparisonProfileName || undefined,
                  });
                  window.open(artifact.downloadUrl, '_blank');
                  message.success(t('security.exportReplayReport'));
                } catch {
                  message.error(t('security.exportReplayReportFailed'));
                }
              }}
            >
              {t('security.exportReplayReport')}
            </Button>
          </Form.Item>
        </Form>
        {replayResult && (
          <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: 'pre-wrap' }}>
            <Typography.Text strong>{t('security.replayResult')}</Typography.Text>
            {'\n'}
            {JSON.stringify(replayResult, null, 2)}
          </Typography.Paragraph>
        )}
      </Card>
      <Modal
        title={editingPolicyPreset ? t('security.editPolicyPreset') : t('security.addPolicyPreset')}
        open={presetModalOpen}
        onCancel={() => {
          setPresetModalOpen(false);
          setEditingPolicyPreset(null);
          policyPresetForm.resetFields();
        }}
        footer={null}
      >
        <Form
          form={policyPresetForm}
          layout="vertical"
          onFinish={async (values) => {
            setPresetSaving(true);
            try {
              const payload = {
                id: editingPolicyPreset?.id,
                name: values.name,
                description: values.description || undefined,
                organizationId: values.organizationId ? Number(values.organizationId) : undefined,
                projectId: values.projectId ? Number(values.projectId) : undefined,
                allowedProviders: String(values.allowedProviders || '').split(',').map((item: string) => item.trim()).filter(Boolean),
                deniedProviders: String(values.deniedProviders || '').split(',').map((item: string) => item.trim()).filter(Boolean),
                blockedWords: String(values.blockedWords || '').split(',').map((item: string) => item.trim()).filter(Boolean),
                maxPromptChars: Number(values.maxPromptChars || 4000),
                retentionMode: values.retentionMode || 'standard',
              };
              const saved = editingPolicyPreset
                ? await updateGuardrailPolicyPreset(payload)
                : await addGuardrailPolicyPreset(payload);
              setPolicyPresets((current) => (
                editingPolicyPreset
                  ? current.map((item) => (item.id === saved.id ? saved : item))
                  : [saved, ...current]
              ));
              message.success(t('security.policyPresetSaved'));
              setPresetModalOpen(false);
              setEditingPolicyPreset(null);
              policyPresetForm.resetFields();
            } catch {
              message.error(t('security.policyPresetSaveFailed'));
            } finally {
              setPresetSaving(false);
            }
          }}
        >
          <Form.Item label={t('common.name')} name="name">
            <Input />
          </Form.Item>
          <Form.Item label={t('common.details')} name="description">
            <Input />
          </Form.Item>
          <Form.Item label={t('apiKeys.organizationId')} name="organizationId">
            <Input placeholder={organizations.map((item) => `${item.id}:${item.name}`).join(', ')} />
          </Form.Item>
          <Form.Item label={t('apiKeys.projectId')} name="projectId">
            <Input placeholder={projects.map((item) => `${item.id}:${item.name}`).join(', ')} />
          </Form.Item>
          <Form.Item label={t('security.allowedProviders')} name="allowedProviders">
            <Input placeholder="provider_primary,provider_backup" />
          </Form.Item>
          <Form.Item label={t('security.deniedProviders')} name="deniedProviders">
            <Input placeholder="provider_backup" />
          </Form.Item>
          <Form.Item label={t('security.blockedWords')} name="blockedWords">
            <Input placeholder="forbidden,blocked" />
          </Form.Item>
          <Form.Item label={t('security.maxPromptChars')} name="maxPromptChars">
            <InputNumber min={1} max={20000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label={t('security.retentionMode')} name="retentionMode">
            <Input placeholder="standard" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={presetSaving}>
              {t('common.submit')}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={editingExperiment ? t('security.editExperiment') : t('security.addExperiment')}
        open={experimentModalOpen}
        onCancel={() => {
          setExperimentModalOpen(false);
          setEditingExperiment(null);
          experimentForm.resetFields();
        }}
        footer={null}
      >
        <Form
          form={experimentForm}
          layout="vertical"
          onFinish={async (values) => {
            setExperimentSaving(true);
            try {
              const payload = {
                id: editingExperiment?.id,
                name: values.name,
                controlProfileName: values.controlProfileName || 'default_heuristic_profile',
                challengerProfileName: values.challengerProfileName,
                trafficPercentage: Number(values.trafficPercentage || 50),
                status: values.status || 'active',
              };
              const saved = editingExperiment
                ? await updateRouteScoringExperiment(payload)
                : await addRouteScoringExperiment(payload);
              setExperiments((current) => (
                editingExperiment
                  ? current.map((item) => (item.id === saved.id ? saved : item))
                  : [saved, ...current.filter((item) => saved.status !== 'active' || item.status !== 'active')]
              ));
              message.success(t('security.experimentSaved'));
              setExperimentModalOpen(false);
              setEditingExperiment(null);
              experimentForm.resetFields();
            } catch {
              message.error(t('security.experimentSaveFailed'));
            } finally {
              setExperimentSaving(false);
            }
          }}
        >
          <Form.Item label={t('common.name')} name="name">
            <Input />
          </Form.Item>
          <Form.Item label={t('security.controlProfile')} name="controlProfileName">
            <Input placeholder="default_heuristic_profile" />
          </Form.Item>
          <Form.Item label={t('security.challengerProfile')} name="challengerProfileName">
            <Input placeholder="learned_eval_profile" />
          </Form.Item>
          <Form.Item label={t('security.trafficPercentage')} name="trafficPercentage">
            <InputNumber min={0} max={100} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label={t('common.status')} name="status">
            <Input placeholder="active / inactive" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={experimentSaving}>
              {t('common.submit')}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={editingWorkspaceGuardrail ? t('security.editWorkspaceGuardrail') : t('security.addWorkspaceGuardrail')}
        open={workspaceModalOpen}
        onCancel={() => {
          setWorkspaceModalOpen(false);
          setEditingWorkspaceGuardrail(null);
          workspaceGuardrailForm.resetFields();
        }}
        footer={null}
      >
        <Form
          form={workspaceGuardrailForm}
          layout="vertical"
          onFinish={async (values) => {
            setWorkspaceSaving(true);
            try {
              const payload = {
                id: editingWorkspaceGuardrail?.id,
                organizationId: values.organizationId ? Number(values.organizationId) : undefined,
                projectId: values.projectId ? Number(values.projectId) : undefined,
                allowedProviders: String(values.allowedProviders || '').split(',').map((item: string) => item.trim()).filter(Boolean),
                deniedProviders: String(values.deniedProviders || '').split(',').map((item: string) => item.trim()).filter(Boolean),
                blockedWords: String(values.blockedWords || '').split(',').map((item: string) => item.trim()).filter(Boolean),
                maxPromptChars: values.maxPromptChars === undefined || values.maxPromptChars === null ? undefined : Number(values.maxPromptChars),
                retentionMode: values.retentionMode || undefined,
              };
              const saved = editingWorkspaceGuardrail
                ? await updateWorkspaceGuardrail(payload)
                : await addWorkspaceGuardrail(payload);
              setWorkspaceGuardrails((current) => (
                editingWorkspaceGuardrail
                  ? current.map((item) => (item.id === saved.id ? saved : item))
                  : [saved, ...current]
              ));
              message.success(t('security.workspaceGuardrailsSaved'));
              setWorkspaceModalOpen(false);
              setEditingWorkspaceGuardrail(null);
              workspaceGuardrailForm.resetFields();
            } catch {
              message.error(t('security.workspaceGuardrailsSaveFailed'));
            } finally {
              setWorkspaceSaving(false);
            }
          }}
        >
          <Form.Item label={t('apiKeys.organizationId')} name="organizationId">
            <Input placeholder={organizations.map((item) => `${item.id}:${item.name}`).join(', ')} />
          </Form.Item>
          <Form.Item label={t('apiKeys.projectId')} name="projectId">
            <Input placeholder={projects.map((item) => `${item.id}:${item.name}`).join(', ')} />
          </Form.Item>
          <Form.Item label={t('security.allowedProviders')} name="allowedProviders">
            <Input placeholder="provider_primary,provider_backup" />
          </Form.Item>
          <Form.Item label={t('security.deniedProviders')} name="deniedProviders">
            <Input placeholder="provider_backup" />
          </Form.Item>
          <Form.Item label={t('security.blockedWords')} name="blockedWords">
            <Input placeholder="forbidden,blocked" />
          </Form.Item>
          <Form.Item label={t('security.maxPromptChars')} name="maxPromptChars">
            <InputNumber min={1} max={20000} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label={t('security.retentionMode')} name="retentionMode">
            <Input placeholder="standard" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={workspaceSaving}>
              {t('common.submit')}
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
};

export default SecurityAdminPage;
