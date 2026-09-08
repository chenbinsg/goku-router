"""路由规则里配的 Preferred/Backup 必须真的决定走谁。

## 这条测试为什么存在

2026-09-09 生产实测：Qwen3.8 的路由规则写着「主 openrouter、备 TOKENSTARS」，
而**每一次请求都被打分判给了 TOKENSTARS**，`fallback_used` 还是 false ——
这不是降级，是启发式打分正常地推翻了人写的配置。

两个原因叠加：

1. `preferred_order` 只从 `request.provider.order`（请求体）取，而调用方 Core
   不发这个字段 → `preferred_order_index` 恒为 None → 主备在打分阶段等于没配；
2. 排序以 `-route_score` 为首要键，`preferred_order_index` 只是它的第二级
   tie-break —— 即便填对了也几乎不起作用。

后果最坏的地方不是选错，是**界面上完全看不出被推翻了**：管理台明明白白写着
Preferred，运行时不认。

## 定下的语义

**显式配置压过启发式。** 配了主备就按主备走；没配主备时（`preferred_order_index`
全为 None）排序自然退回按分数决定 —— 两种模式各司其职。
"""
from app import crud

WEIGHTS = {"capability": 0.3, "latency": 0.25, "cost": 0.45}


def _trace(candidates: list) -> dict:
    """`_select_provider_from_trace` 收的是整个 trace 字典，不是候选列表。"""
    return {"candidates": candidates}


def _cand(provider: str, score: float, pref_index=None, priority=100, latency=1000.0):
    """一条候选 trace。`score_components` 是 _candidate_score_from_components 的输入。"""
    return {
        "provider": provider,
        "accepted": True,
        "preferred_order_index": pref_index,
        "priority": priority,
        "avg_latency_ms": latency,
        "route_score": score,
        "score_components": {
            "capability_score": 1.0,
            "latency_score": score,
            "cost_score": 1.0,
        },
    }


class TestExplicitConfigOutranksScoring:
    def test_preferred_wins_even_with_a_worse_score(self):
        """生产上的原形：自建慢（分低）但是配置里的主 provider。"""
        trace = [
            _cand("openrouter", score=0.18, pref_index=0, latency=31816.8),
            _cand("TOKENSTARS_OPENROUTER", score=0.84, pref_index=1, latency=5945.6),
        ]
        assert crud._select_provider_from_trace(_trace(trace), WEIGHTS) == "openrouter"

    def test_backup_is_second_not_first(self):
        trace = [
            _cand("TOKENSTARS_OPENROUTER", score=0.84, pref_index=1),
            _cand("openrouter", score=0.18, pref_index=0),
        ]
        assert crud._select_provider_from_trace(_trace(trace), WEIGHTS) == "openrouter"

    def test_without_a_rule_the_score_still_decides(self):
        """没配主备时不能改变原有行为 —— 启发式仍然挑分高的那个。"""
        trace = [
            _cand("slow", score=0.18, pref_index=None),
            _cand("fast", score=0.84, pref_index=None),
        ]
        assert crud._select_provider_from_trace(_trace(trace), WEIGHTS) == "fast"

    def test_an_unlisted_provider_ranks_below_every_listed_one(self):
        """候选里混进没被点名的 provider（例如 sticky 带进来的），即便分最高，
        也排在被点名的之后 —— 否则「主备」这个词就没有意义。"""
        trace = [
            _cand("wildcard", score=0.99, pref_index=None),
            _cand("backup", score=0.20, pref_index=1),
            _cand("primary", score=0.10, pref_index=0),
        ]
        assert crud._select_provider_from_trace(_trace(trace), WEIGHTS) == "primary"

    def test_rejected_candidates_are_never_selected(self):
        """主 provider 被能力/上限拒掉时，必须落到备用，而不是硬选一个不可用的。"""
        trace = [
            {**_cand("primary", score=0.90, pref_index=0),
             "accepted": False, "reject_reason": "missing capability"},
            _cand("backup", score=0.10, pref_index=1),
        ]
        assert crud._select_provider_from_trace(_trace(trace), WEIGHTS) == "backup"


class TestRouteRuleReachesTheScorer:
    """光改排序不够 —— 名单本身此前根本没传进来。"""

    def test_build_candidate_trace_accepts_preferred_names(self):
        import inspect
        sig = inspect.signature(crud._build_candidate_trace)
        assert "preferred_names" in sig.parameters, (
            "主备名单必须能传进 trace 构建 —— 只读请求体的 provider.order 时，"
            "Core 不发该字段，主备恒等于没配"
        )

    def test_the_deciding_sort_also_accepts_it(self):
        """最终 selected_provider 出自 _filter_and_sort_candidates（调用方取 [0]），
        不是 _select_provider_from_trace。名单没传到这一层，改别处都不生效。"""
        import inspect
        sig = inspect.signature(crud._filter_and_sort_candidates)
        assert "preferred_names" in sig.parameters
