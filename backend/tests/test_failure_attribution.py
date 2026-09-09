"""失败请求必须署上是哪个 provider 失败的。

## 这条测试为什么存在

生产实测 2026-09-09：37,322 次请求里 1,794 次失败，而

    所有模型的失败数之和 = 1794
    "unknown" 桶的请求数 = 1794          ← 完全相等
    每一个真实 provider 的失败数 = 0     ← 无一例外

原因是两条失败路径都写死 `provider_name=None`。于是：

1. **任何 provider 的失败率恒等于 0**，`provider_failure_spike` 告警结构性地
   永远不可能对真实 provider 触发；
2. `gpt-4.1-mini` 显示 41% 失败率，而它的 provider TOKENSTARS 显示 0 失败 ——
   同一批失败在按模型切分时出现、按 provider 切分时消失，看起来像两个矛盾的事实；
3. 最要命的是 `except ProviderExecutionError` 会把 provider 置为 unhealthy，
   **紧接着就把这个名字丢掉** —— 系统知道是谁挂了、据此改了健康状态，却不在
   日志里留下它。事后无法归因。

护栏拦截（400）保持 None 是对的：那种请求确实没走到任何 provider。
"""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud, models


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    models.Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _log(provider, status=200, cost=0.01, model="Qwen3.8"):
    return models.RequestLog(
        request_id=f"r{id(object())}", requested_model=model, resolved_model=model,
        provider_name=provider, status_code=status, latency=100.0, cost_amount=cost,
        created_at=datetime.utcnow(),
    )


class TestTheFailingProviderIsNamed:
    def test_the_503_path_records_who_failed(self):
        """静态兜底：全候选失败时不能再写 None。"""
        import inspect
        src = inspect.getsource(crud._execute_routed_chat_completion)
        tail = src[src.index('_create_notification(db, "routing_failure"'):]
        assert "provider_name=failed_provider_name" in tail, (
            "503 失败日志仍写 provider_name=None —— 真实 provider 的失败率恒为 0，"
            "provider_failure_spike 告警永远不可能触发"
        )
        assert "attempted_providers" in src, (
            "没有记录完整的尝试清单 —— 只看 provider_name 无法区分"
            "「一家挂了」和「三家全挂了」"
        )

    def test_every_attempt_is_collected_not_just_the_last(self):
        import inspect
        src = inspect.getsource(crud._execute_routed_chat_completion)
        assert "attempted.append((provider.name, last_error))" in src


class TestFailuresStayOutOfCostComparison:
    def test_a_failing_provider_does_not_look_cheap(self, db):
        """**这条锁的是上一个修复的副作用。**

        失败署名之后，503 行会带着真实 provider 名和 cost=0 进入成本比较 ——
        挂得越多越显得便宜。判据必须同时看 status_code，只看 provider_name
        是否为 None 已经不够了。
        """
        rows = [_log("steady", cost=0.01) for _ in range(10)]
        rows += [_log("flaky", cost=0.01) for _ in range(5)]
        rows += [_log("flaky", status=503, cost=0.0) for _ in range(20)]

        items = crud._build_cost_optimization_opportunities(db=db, request_logs=rows)
        # 只看 provider 之间的成本迁移建议。同时会产生一条 workspace_hotspot
        # （失败/fallback 开销提示），那条是对的，不在本测试的射程内。
        shifts = [i for i in items if i.category == "provider_shift"]
        assert shifts == [], (
            f"两家单价相同、只有失败次数不同，不该产生成本迁移建议，"
            f"实际: {[(i.scope_label, i.title) for i in shifts]}"
        )

    def test_guardrail_blocks_keep_a_null_provider(self):
        """400 护栏拦截确实没走到任何 provider，保持 None 是对的。"""
        import inspect
        src = inspect.getsource(crud._execute_routed_chat_completion)
        head = src[:src.index('_create_notification(db, "routing_failure"')]
        assert "provider_name=None," in head, "护栏拦截路径不该被一起改掉"
