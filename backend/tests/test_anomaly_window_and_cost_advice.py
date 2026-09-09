"""异常扫描的「最近一小时」必须真的是一小时；成本建议不能把失败当成便宜。

## 这两条测试为什么存在

2026-09-09 排查生产告警噪音时发现的两个 bug，共用同一个根：
`request_logs` 此前**没有任何时间字段**，而 `provider_name` 在失败时是 NULL。

1. `run_anomaly_sweep` 的注释写着 `# Recent window: last 1 hour`，代码却是
   `id > 0 ... limit(200)` —— 按时间过滤当时根本无从谈起。取的是「最近 200 行」，
   系统越安静这 200 行跨的时间越长。实测：01:12 就结束的 Qwen3.8 故障，03:07 的
   扫描仍在报「failure rate 100%」。

2. `_build_cost_optimization_opportunities` 用 `row.provider_name or "unknown"`
   把所有失败请求并成一桶。失败不计费、成本恒为 0，于是这一桶永远是「最便宜的
   provider」，五条建议里五条都在说「把流量迁到 unknown，预计省 98 美元」——
   把「请求全挂了」读成了「这家不要钱」。

第 2 条不只是文案难看：ROUTER_AUTO_OPTIMIZE 打开时 drift monitor 会照着这类
信号自动开 A/B 实验，而它 2026-06-16~21 开过五天。
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud, models


@pytest.fixture
def db():
    """内存库。`_build_cost_optimization_opportunities` 内部会查 organizations /
    projects 建工作空间汇总，所以给它一个空的真库比伪造更省事。"""
    engine = create_engine("sqlite://")
    models.Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _log(provider, status=200, cost=0.01, age_minutes=1, model="Qwen3.8"):
    return models.RequestLog(
        request_id=f"r{id(object())}",
        requested_model=model,
        resolved_model=model,
        provider_name=provider,
        status_code=status,
        latency=100.0,
        cost_amount=cost,
        created_at=datetime.utcnow() - timedelta(minutes=age_minutes),
    )


class TestCostAdviceIgnoresFailures:
    def test_null_provider_is_not_a_cheap_provider(self, db):
        """生产原形：openrouter 正常计费，一批失败请求成本为 0。

        修复前这会生成「Move more Qwen3.8 traffic to unknown」。
        """
        rows = [_log("openrouter", cost=0.01) for _ in range(10)]
        rows += [_log(None, status=503, cost=0.0) for _ in range(10)]

        items = crud._build_cost_optimization_opportunities(db=db, request_logs=rows)
        targets = " ".join(f"{i.title} {i.summary} {i.recommendation}" for i in items)
        assert "unknown" not in targets, (
            "把 provider_name 为 NULL 的失败请求当成了一家便宜的供应商"
        )

    def test_a_genuinely_cheaper_provider_is_still_reported(self, db):
        """别把功能一起关掉 —— 两家都真实存在时仍要给出建议。"""
        rows = [_log("expensive", cost=0.10) for _ in range(10)]
        rows += [_log("cheap", cost=0.01) for _ in range(10)]

        items = crud._build_cost_optimization_opportunities(db=db, request_logs=rows)
        assert any("expensive" in i.summary for i in items), "真实的成本差异不该被漏掉"


class TestAnomalyWindowIsTimeBased:
    def test_request_log_has_a_timestamp(self):
        """整件事的根 —— 没有这一列，「最近一小时」永远是句空话。"""
        assert hasattr(models.RequestLog, "created_at")

    def test_every_write_site_sets_it(self):
        """尤其是**两条失败路径** —— 只在成功时记时间，等于故障期间没有数据。"""
        import inspect
        src = inspect.getsource(crud)
        constructions = src.count("models.RequestLog(")
        stamped = src.count("created_at=datetime.utcnow(),")
        assert stamped >= constructions, (
            f"{constructions} 处构造 RequestLog，只有 {stamped} 处写了 created_at"
        )

    def test_the_sweep_filters_by_time_not_by_row_count(self):
        import inspect
        from app.services import scheduler
        src = inspect.getsource(scheduler.run_anomaly_sweep)
        assert "created_at >= window_start" in src.replace("models.RequestLog.", ""), (
            "异常扫描仍在按行数取窗口 —— 安静时段会拿几天前的旧行反复告警"
        )
        assert "MIN_SAMPLES_FOR_RATE" in src, "缺最小样本量，几个请求就能报出 100% 失败率"
