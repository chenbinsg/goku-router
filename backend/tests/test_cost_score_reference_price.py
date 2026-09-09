"""成本维度必须真的能区分候选，而不是所有人都拿满分。

## 这条测试为什么存在

2026-09-09 排查 Qwen3.8 路由时发现，`cost_score` 的参考价被写死成
`0.01`（1 美分/1k token）：

    reference_price_per_1k = 0.01
    cost_score = min(reference_price_per_1k / safe_total_price, 1.0)

而现网所有 provider 的单价都在 **0.001–0.003** 区间。代入后每一家算出来都
≥ 3.3，被 `min(..., 1.0)` 齐齐削到 **1.0** —— 一个占 45–80% 权重的维度，
对所有候选返回同一个常数，**完全不参与决策**。路由实际上只由权重 10–25% 的
延迟分决定。

改成「参考价 = 候选集里最便宜的那家」：最便宜的得 1.0，其余按倍数递减，
且没有需要随物价调整的魔法数。

## 一并钉住的边界

最后一条 `test_identical_prices_still_tie` 记的是**这个修复的局限**：
现网 openrouter 与 TOKENSTARS_OPENROUTER 的价格一字不差（0.001/0.002），
成本维度依旧分不出胜负。那是价格数据填错了（自建推理照抄了商用报价），
不是打分函数能解决的问题 —— 别指望这个修复改变 Qwen3.8 的路由。
"""
import pytest

from app import crud


class _P:
    """够 _provider_route_score 用的最小 provider 替身。"""

    def __init__(self, name, inp, out, latency=1000.0):
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


def _cost_of(provider, reference):
    _, comp = crud._provider_route_score(
        provider,
        _req(),
        "general",
        {"capability": 0.3, "latency": 0.25, "cost": 0.45},
        reference_price_per_1k=reference,
    )
    return comp["cost_score"]


def _req():
    from app import schemas

    return schemas.ChatCompletionRequest(
        model="qwen3.8",
        messages=[{"role": "user", "content": "hi"}],
    )


class TestReferencePriceComesFromTheCandidates:
    def test_cheapest_scores_one_and_dearer_scales_down(self):
        cheap = _P("cheap", 0.0005, 0.0005)   # 0.001 /1k
        dear = _P("dear", 0.002, 0.002)       # 0.004 /1k
        ref = crud._candidate_reference_price([(cheap, None), (dear, None)])
        assert ref == pytest.approx(0.001)
        assert _cost_of(cheap, ref) == pytest.approx(1.0)
        # 贵 4 倍 → 得分是最便宜那家的四分之一
        assert _cost_of(dear, ref) == pytest.approx(0.25, rel=1e-3)

    def test_the_old_constant_flattened_everything(self):
        """回归钉子：现网价位下，写死 0.01 会让两家都拿 1.0。"""
        cheap = _P("cheap", 0.0005, 0.0005)
        dear = _P("dear", 0.002, 0.002)
        assert _cost_of(cheap, 0.01) == pytest.approx(1.0)
        assert _cost_of(dear, 0.01) == pytest.approx(1.0)   # ← 这就是 bug

    def test_single_candidate_scores_one(self):
        """只有一个候选时成本没有可比性，给 1.0，不影响其它维度。"""
        solo = _P("solo", 0.05, 0.05)  # 绝对值很贵，但没有对手
        ref = crud._candidate_reference_price([(solo, None)])
        assert _cost_of(solo, ref) == pytest.approx(1.0)

    def test_free_providers_do_not_become_the_reference(self):
        """价格为 0 通常是「没填」而不是「真免费」。让它当基准会把所有人
        的成本分压成 0，等于用一条缺失数据废掉整个维度。"""
        unpriced = _P("unpriced", 0.0, 0.0)
        real = _P("real", 0.001, 0.002)
        ref = crud._candidate_reference_price([(unpriced, None), (real, None)])
        assert ref == pytest.approx(0.003)
        assert _cost_of(real, ref) == pytest.approx(1.0)

    def test_no_priced_candidate_falls_back_to_the_constant(self):
        """全都没填价 → 没有基准可取，退回旧常量，行为与修复前一致。"""
        assert crud._candidate_reference_price([(_P("a", 0.0, 0.0), None)]) is None


class TestKnownLimitation:
    def test_identical_prices_still_tie(self):
        """**现网 Qwen3.8 的实际情形。** 两家价格一模一样，成本维度必然打平 ——
        这个修复不会、也不应该改变那条路由。要让成本说话，得先把自建推理的
        价格改成它真实的边际成本（现在照抄了商用 API 的 0.001/0.002）。"""
        selfhosted = _P("openrouter", 0.001, 0.002)
        commercial = _P("TOKENSTARS_OPENROUTER", 0.001, 0.002)
        ref = crud._candidate_reference_price([(selfhosted, None), (commercial, None)])
        assert _cost_of(selfhosted, ref) == _cost_of(commercial, ref) == pytest.approx(1.0)
