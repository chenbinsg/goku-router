"""质量分必须影响**真正的排序**，不能只影响展示用的 trace。

## 这条测试为什么存在

v1.3.0（7feeac7，2026-05-18）把 `quality_multiplier` 接进了
`_provider_route_score`，commit message 写的是

    Quality multiplier wired into _provider_route_score() —
    underperforming providers score lower automatically

但那次只在 `_build_candidate_trace` 的调用点传了 `db`，漏了
`_filter_and_sort_candidates` 里的排序 —— 而**决定 `selected_provider` 的是后者**。
`_get_provider_quality_score` 在 `db is None` 时返回 1.0，于是三个多月里：

- 管理台看到的 `route_score`：**带**质量分
- 真正用来选 provider 的分：**不带**

drift monitor 每 6 小时辛苦算出来的质量分，一次都没有改变过路由结果。

这和 Qwen3.8 那次（界面写着 Preferred、运行时不认）是同一类故障：同一份配置
算出两个结果，其中一个只拿来显示，而且**从界面上完全看不出来**。

## 为什么现在修是零风险的

`drift_monitor_job` 被 `ROUTER_AUTO_OPTIMIZE` gate 住，默认 false。表是空的时候
`_get_provider_quality_score` 对谁都返回 1.0，接上 db 的行为变化恰好为零 ——
这是修它成本最低的时刻。等哪天有人打开那个开关，分叉会当场出现。
"""
import pytest

from app import crud


class _P:
    def __init__(self, name, inp=0.001, out=0.002, latency=1000.0):
        self.name = name
        self.input_cost_per_1k = inp
        self.output_cost_per_1k = out
        self.avg_latency_ms = latency
        self.priority = 100
        self.health_status = "healthy"
        self.max_input_tokens = 1_000_000
        self.max_output_tokens = 8192
        self.capability_tags = "chat"
        self.supported_parameters = "temperature,max_tokens"
        self.supports_zdr = True
        self.data_collection_mode = "deny"
        self.status = "active"


class _FakeDB:
    """只回答 `_get_provider_quality_score` 那一个查询。

    真实的 ProviderQualityScore 需要 drift_monitor_job 才会有数据，而那个 job
    默认不跑 —— 与其造一张有数据的表，不如直接把「查得到分」这件事替身掉。
    """

    def __init__(self, scores: dict[str, float]):
        self._scores = scores
        self.queries = 0

    def query(self, model):
        return self

    def filter(self, *args):
        # 从 SQLAlchemy 的 BinaryExpression 里取出被比较的 provider_name 字面量
        self._wanted = None
        for expr in args:
            right = getattr(expr, "right", None)
            value = getattr(right, "value", None)
            if isinstance(value, str) and value in self._scores:
                self._wanted = value
        return self

    def first(self):
        self.queries += 1
        if self._wanted is None:
            return None
        score = self._scores[self._wanted]
        return type("Row", (), {"quality_score": score})()


def _req():
    from app import schemas

    return schemas.ChatCompletionRequest(
        model="qwen3.8", messages=[{"role": "user", "content": "hi"}]
    )


WEIGHTS = {"capability": 0.3, "latency": 0.25, "cost": 0.45}


def _score(provider, db):
    return crud._provider_route_score(
        provider, _req(), "general", WEIGHTS, db=db, reference_price_per_1k=0.003
    )[0]


class TestQualityScoreActuallyApplies:
    def test_a_bad_quality_score_lowers_the_score(self):
        p = _P("flaky")
        good = _score(p, _FakeDB({"flaky": 1.0}))
        bad = _score(p, _FakeDB({"flaky": 0.2}))
        assert bad == pytest.approx(good * 0.2, rel=1e-6)

    def test_omitting_db_silently_ignores_quality(self):
        """把这个漏洞本身钉住：db 为 None 时质量分等于不存在。

        这不是要保留的行为，是**要求调用方必须传 db** 的理由。"""
        p = _P("flaky")
        assert _score(p, None) == pytest.approx(_score(p, _FakeDB({"flaky": 1.0})))
        assert _score(p, None) != pytest.approx(_score(p, _FakeDB({"flaky": 0.2})))


class TestTheDecidingSortSeesIt:
    """光让 `_provider_route_score` 会算不够 —— 三个月的教训是：算了，但没人传 db。"""

    def test_quality_score_flips_the_winner(self):
        """**这条是真正的回归钉子。**

        构造：`fast` 的延迟远好于 `slow`，不看质量分时它稳赢；但它的质量分只有
        0.05。接上 db 之后 `slow` 必须反超。

        不要退回去断言「db 被查过了」—— 我第一版就是那么写的，结果**假阳性**：
        `_filter_and_sort_candidates` 内部会调 `_build_candidate_trace`，而那条
        路径一直是传 db 的，所以查询计数无论如何都大于 0。同理也不能靠两个同分
        候选的顺序，sort 稳定会让它恰好蒙对。**必须让质量分改变胜负。**
        """
        fast, slow = _P("fast", latency=200.0), _P("slow", latency=20000.0)
        mapping = type("M", (), {"model_id": "qwen3.8", "provider_model_name": "qwen3.8"})()

        guardrails = type("G", (), {})()
        guardrails.allowed_providers = ""
        guardrails.denied_providers = ""
        guardrails.max_prompt_tokens = 1_000_000
        guardrails.max_output_tokens = 1_000_000

        # 先验证前提：不看质量分时确实是 fast 赢，否则这条测试什么都没证明
        neutral = _FakeDB({"fast": 1.0, "slow": 1.0})
        baseline = crud._filter_and_sort_candidates(
            _req(), [(slow, mapping), (fast, mapping)], guardrails, WEIGHTS, None, db=neutral
        )
        assert [p.name for p, _ in baseline][0] == "fast", "前提不成立：延迟没能决定胜负"

        db = _FakeDB({"fast": 0.05, "slow": 1.0})
        result = crud._filter_and_sort_candidates(
            _req(), [(slow, mapping), (fast, mapping)], guardrails, WEIGHTS, None, db=db
        )
        assert [p.name for p, _ in result][0] == "slow", (
            "决定性排序没把 db 传给打分函数 —— 质量分只出现在展示用的 trace 里，"
            "对真正选谁毫无影响（v1.3.0 7feeac7 的原始缺陷）"
        )
