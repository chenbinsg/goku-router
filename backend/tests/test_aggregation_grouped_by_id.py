"""所有按 provider 的聚合都要按 **id** 分组，不能按名字。

## 这些测试为什么存在

按名字分组的后果，生产实测 2026-09-09：同一台大连的机器以
`local_dalian_openrouter`(6,453 次) 和 `local-dalian-openrouter`(1,361 次) 两个
名字各自统计，平均延迟一个 50,280ms、一个 31,339ms —— **两组都不代表这台机器的
真实表现**，而界面上看起来像两家供应商。

另一半是 `or "unknown"` 兜底：`provider_id` 为空意味着请求**没走到任何 provider**
（护栏拦截或全候选失败），把它们攒成一家叫 "unknown" 的供应商制造过两次事故级
误导 ——

  · 成本建议推荐「把流量迁到 unknown，预计省 98 美元」（失败不计费 → 成本恒 0）；
  · 每小时异常告警报「unknown 失败率 100%」，而故障 01:12 就已结束，03:07 仍在报。

所以：**按 id 分组；「没走到 provider」那一桶由调用方决定要不要**，分析页要看
（有多少请求根本没发出去），告警和打分不能把它当供应商。
"""
import itertools
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud, models

_seq = itertools.count(1)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    models.Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _log(pid, pname, status=200, latency=100.0, cost=0.01, model="Qwen3.8"):
    return models.RequestLog(
        request_id=f"r{next(_seq)}", requested_model=model, resolved_model=model,
        provider_id=pid, provider_name=pname, status_code=status, latency=latency,
        cost_amount=cost, created_at=datetime.utcnow(),
    )


class TestRenameDoesNotSplitTheGroup:
    def test_one_machine_two_names_is_one_group(self):
        """核心场景：同一 id、前后两个名字，必须合成一组。"""
        rows = ([_log(21, "local_dalian_openrouter", latency=50280.0) for _ in range(6)]
                + [_log(21, "local-dalian-openrouter", latency=31339.0) for _ in range(2)])
        groups = crud._group_by_provider(rows)
        assert len(groups) == 1, f"同一台机器被劈成了 {len(groups)} 组"
        label, grouped = groups[0]
        assert len(grouped) == 8
        assert label in {"local_dalian_openrouter", "local-dalian-openrouter"}

    def test_different_providers_stay_separate(self):
        """别把分组一起关掉 —— 不同 id 仍要分开。"""
        rows = [_log(10, "a"), _log(13, "b")]
        assert len(crud._group_by_provider(rows)) == 2


class TestUnroutedIsNotAProvider:
    def test_excluded_by_default(self):
        rows = [_log(10, "openrouter")] * 1 + [_log(None, None, status=503) for _ in range(5)]
        labels = [label for label, _ in crud._group_by_provider(rows)]
        assert labels == ["openrouter"], f"把没走到 provider 的请求当成了供应商: {labels}"

    def test_included_when_asked_with_an_honest_label(self):
        rows = [_log(10, "openrouter")] + [_log(None, None, status=503) for _ in range(5)]
        groups = dict(crud._group_by_provider(rows, include_unrouted=True))
        assert crud._UNROUTED_LABEL in groups
        assert len(groups[crud._UNROUTED_LABEL]) == 5
        assert "unknown" not in groups, "标签仍在暗示这是一家供应商"


class TestAnomalyAlertsIgnoreUnrouted:
    def test_no_alert_for_the_unrouted_bucket(self, db):
        """生产原形：5 条 503 全部没走到 provider，不该报「失败率 100%」。"""
        rows = [_log(None, None, status=503) for _ in range(20)]
        alerts = crud._build_anomaly_alerts(db=db, request_logs=rows)
        assert alerts == [], f"对「没走到 provider」的请求报了告警: {[a.title for a in alerts]}"

    def test_a_real_provider_failing_still_alerts(self, db):
        """别把告警一起关掉 —— 真实 provider 挂了必须报。"""
        rows = [_log(10, "openrouter", status=503) for _ in range(20)]
        alerts = crud._build_anomaly_alerts(db=db, request_logs=rows)
        assert any(a.category == "provider_failure" and a.scope_label == "openrouter"
                   for a in alerts), "真实 provider 的高失败率没有报出来"


class TestCostAdviceGroupsById:
    def test_a_renamed_provider_is_not_compared_against_itself(self, db):
        """按名字分组时，改过名的同一台机器会变成两家，然后「建议把流量从自己
        迁到自己」。"""
        rows = ([_log(21, "老名字", cost=0.10) for _ in range(10)]
                + [_log(21, "新名字", cost=0.01) for _ in range(10)])
        items = crud._build_cost_optimization_opportunities(db=db, request_logs=rows)
        shifts = [i for i in items if i.category == "provider_shift"]
        assert shifts == [], (
            f"把同一台机器的前后两个名字当成两家在比价: "
            f"{[(i.scope_label, i.title) for i in shifts]}"
        )


class TestNoNameFallbackRemains:
    def test_no_or_unknown_in_code_paths(self):
        """`provider_name or \"unknown\"` 是这一族 bug 的共同写法，代码里不该再有。"""
        import inspect
        from app.services import scheduler

        for module in (crud, scheduler):
            for line in inspect.getsource(module).splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("·"):
                    continue    # 注释里引用历史写法是可以的
                assert 'provider_name or "unknown"' not in line, (
                    f"{module.__name__} 仍在用名字兜底: {line.strip()}"
                )
