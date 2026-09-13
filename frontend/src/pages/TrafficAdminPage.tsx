import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Card, Row, Col, Statistic, Segmented, Space, Button, Switch, Typography, Spin, message } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { getTrafficTimeseries, TrafficTimeseries, TrafficPoint } from '../api';

const { Text } = Typography;

const RANGES: { label: string; hours: number }[] = [
  { label: '1小时', hours: 1 },
  { label: '6小时', hours: 6 },
  { label: '24小时', hours: 24 },
  { label: '7天', hours: 24 * 7 },
];

const COLORS = {
  success: '#3b82f6',
  error: '#ef4444',
  grid: 'rgba(140,140,140,0.18)',
  axis: 'rgba(140,140,140,0.55)',
};

// ── Stacked area chart (dependency-free inline SVG) ────────────────────────────
// Stacks error on top of success so total height = total requests per bucket.
const VIEW_W = 960;
const VIEW_H = 320;
const PAD = { top: 16, right: 16, bottom: 28, left: 44 };

function niceCeil(v: number): number {
  if (v <= 0) return 1;
  const pow = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / pow;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * pow;
}

const TrafficChart: React.FC<{ data: TrafficTimeseries }> = ({ data }) => {
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const points = data.points;
  const plotW = VIEW_W - PAD.left - PAD.right;
  const plotH = VIEW_H - PAD.top - PAD.bottom;
  const maxTotal = niceCeil(Math.max(1, ...points.map((p) => p.total)));

  const x = (i: number) =>
    PAD.left + (points.length <= 1 ? plotW / 2 : (i / (points.length - 1)) * plotW);
  const y = (v: number) => PAD.top + plotH - (v / maxTotal) * plotH;

  const areaPath = (topFor: (p: TrafficPoint) => number, baseFor: (p: TrafficPoint) => number) => {
    if (points.length === 0) return '';
    const up = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(topFor(p)).toFixed(1)}`);
    const down = [...points]
      .map((p, i) => ({ p, i }))
      .reverse()
      .map(({ p, i }) => `L ${x(i).toFixed(1)} ${y(baseFor(p)).toFixed(1)}`);
    return `${up.join(' ')} ${down.join(' ')} Z`;
  };

  const successArea = areaPath((p) => p.success, () => 0);
  const totalArea = areaPath((p) => p.total, (p) => p.success);

  const yTicks = useMemo(() => {
    const n = 4;
    return Array.from({ length: n + 1 }, (_, i) => Math.round((maxTotal / n) * i));
  }, [maxTotal]);

  // Sparse x labels (about 6) so they never overlap.
  const xLabelIdx = useMemo(() => {
    const want = 6;
    const stride = Math.max(1, Math.round(points.length / want));
    return points.map((_, i) => i).filter((i) => i % stride === 0);
  }, [points]);

  const fmtTime = (ts: number) => {
    const d = new Date(ts * 1000);
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    if (data.hours > 24) {
      return `${d.getMonth() + 1}/${d.getDate()} ${hh}:00`;
    }
    return `${hh}:${mm}`;
  };

  const onMove = (e: React.MouseEvent) => {
    const svg = svgRef.current;
    if (!svg || points.length === 0) return;
    const rect = svg.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * VIEW_W;
    const rel = (px - PAD.left) / plotW;
    const idx = Math.round(rel * (points.length - 1));
    setHover(Math.max(0, Math.min(points.length - 1, idx)));
  };

  const hp = hover != null ? points[hover] : null;

  return (
    <div style={{ position: 'relative', width: '100%' }}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        width="100%"
        style={{ display: 'block', maxHeight: 360 }}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {/* y grid + labels */}
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={PAD.left} x2={VIEW_W - PAD.right} y1={y(v)} y2={y(v)} stroke={COLORS.grid} />
            <text x={PAD.left - 8} y={y(v) + 4} textAnchor="end" fontSize="11" fill={COLORS.axis}>
              {v}
            </text>
          </g>
        ))}

        {/* areas */}
        <path d={totalArea} fill={COLORS.error} fillOpacity={0.5} stroke="none" />
        <path d={successArea} fill={COLORS.success} fillOpacity={0.55} stroke="none" />
        <path
          d={points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(p.total).toFixed(1)}`).join(' ')}
          fill="none"
          stroke={COLORS.error}
          strokeWidth={1.2}
          strokeOpacity={0.9}
        />
        <path
          d={points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(p.success).toFixed(1)}`).join(' ')}
          fill="none"
          stroke={COLORS.success}
          strokeWidth={1.5}
        />

        {/* x labels */}
        {xLabelIdx.map((i) => (
          <text key={i} x={x(i)} y={VIEW_H - 8} textAnchor="middle" fontSize="11" fill={COLORS.axis}>
            {fmtTime(points[i].ts)}
          </text>
        ))}

        {/* hover marker */}
        {hp && (
          <g>
            <line x1={x(hover!)} x2={x(hover!)} y1={PAD.top} y2={PAD.top + plotH} stroke={COLORS.axis} strokeDasharray="3 3" />
            <circle cx={x(hover!)} cy={y(hp.total)} r={3.5} fill={COLORS.error} />
            <circle cx={x(hover!)} cy={y(hp.success)} r={3.5} fill={COLORS.success} />
          </g>
        )}
      </svg>

      {hp && (
        <div
          style={{
            position: 'absolute', top: 8, left: 56, pointerEvents: 'none',
            background: 'rgba(0,0,0,0.78)', color: '#fff', padding: '6px 10px',
            borderRadius: 6, fontSize: 12, lineHeight: 1.6, whiteSpace: 'nowrap',
          }}
        >
          <div>{fmtTime(hp.ts)}</div>
          <div>总计: <b>{hp.total}</b></div>
          <div><span style={{ color: '#93c5fd' }}>成功</span>: {hp.success}</div>
          <div><span style={{ color: '#fca5a5' }}>失败</span>: {hp.error}</div>
          <div>平均延迟: {hp.avg_latency_ms} ms</div>
        </div>
      )}
    </div>
  );
};

const LegendDot: React.FC<{ color: string; label: string }> = ({ color, label }) => (
  <Space size={6}>
    <span style={{ width: 10, height: 10, borderRadius: 2, background: color, display: 'inline-block' }} />
    <Text type="secondary" style={{ fontSize: 12 }}>{label}</Text>
  </Space>
);

const TrafficAdminPage: React.FC = () => {
  const [hours, setHours] = useState<number>(24);
  const [data, setData] = useState<TrafficTimeseries | null>(null);
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);

  const load = useCallback(async (showMsg = false) => {
    setLoading(true);
    try {
      const res = await getTrafficTimeseries({ hours });
      setData(res);
      if (showMsg) message.success('已刷新');
    } catch {
      message.error('加载流量数据失败');
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(() => load(), 15000);
    return () => clearInterval(id);
  }, [autoRefresh, load]);

  const errPct = data ? (data.error_rate * 100).toFixed(2) : '0';

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={6}><Card size="small"><Statistic title="请求总数" value={data?.total_requests ?? 0} /></Card></Col>
        <Col xs={12} sm={6}><Card size="small"><Statistic title="失败数" value={data?.total_errors ?? 0} valueStyle={{ color: (data?.total_errors ?? 0) > 0 ? '#ef4444' : undefined }} /></Card></Col>
        <Col xs={12} sm={6}><Card size="small"><Statistic title="错误率" value={errPct} suffix="%" valueStyle={{ color: Number(errPct) > 0 ? '#ef4444' : undefined }} /></Card></Col>
        <Col xs={12} sm={6}><Card size="small"><Statistic title="峰值 (次/分)" value={data?.peak_rpm ?? 0} /></Card></Col>
      </Row>

      <Card
        title="请求流量"
        extra={
          <Space>
            <LegendDot color={COLORS.success} label="成功" />
            <LegendDot color={COLORS.error} label="失败" />
            <Segmented
              options={RANGES.map((r) => ({ label: r.label, value: r.hours }))}
              value={hours}
              onChange={(v) => setHours(v as number)}
            />
            <Space size={4}>
              <Text type="secondary" style={{ fontSize: 12 }}>自动</Text>
              <Switch size="small" checked={autoRefresh} onChange={setAutoRefresh} />
            </Space>
            <Button icon={<ReloadOutlined />} onClick={() => load(true)} loading={loading} />
          </Space>
        }
      >
        <Spin spinning={loading}>
          {data && data.points.length > 0
            ? <TrafficChart data={data} />
            : <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>暂无数据</div>}
        </Spin>
        {data && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            每点 {data.bucket_minutes} 分钟 · 时间为本地时区
          </Text>
        )}
      </Card>
    </div>
  );
};

export default TrafficAdminPage;
