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

`test_identical_prices_still_tie` 记的是**这个修复的局限**：现网 openrouter 与
TOKENSTARS_OPENROUTER 的价格一字不差（0.001/0.002），成本维度依旧分不出胜负。
那是价格数据填错了（自建推理照抄了商用报价），不是打分函数能解决的。

`TestZeroIsARealPrice` 是随后补的：把自建改成 0 之后才发现，**光改数据也没用**
—— `total_price or reference` 里 0 是 falsy，会被当成「未知」悄悄替换成参考价。
两个 bug 叠在一起，导致「在管理台把自建价格改成 0」这个动作从头到尾没有任何
可观察的效果。
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

    def test_unpriced_providers_do_not_become_the_reference(self):
        """真的没填（NULL）不参与取基准 —— 一条缺失数据不该废掉整个维度。

        ⚠ 这条原本写的是「价格为 0 通常是没填」，把 `0.0` 排除在基准之外。
        那个假设是错的：自建推理**没有**按 token 计费的边际成本，0 是如实描述。
        判据现在是 `is None`，不是 `> 0`，见 TestZeroIsARealPrice。
        """
        unpriced = _P("legacy", None, None)
        real = _P("real", 0.001, 0.002)
        ref = crud._candidate_reference_price([(unpriced, None), (real, None)])
        assert ref == pytest.approx(0.003)
        assert _cost_of(real, ref) == pytest.approx(1.0)

    def test_no_priced_candidate_falls_back_to_the_constant(self):
        """全都没填价 → 没有基准可取，退回旧常量，行为与修复前一致。"""
        assert crud._candidate_reference_price([(_P("a", None, None), None)]) is None


class TestKnownLimitation:
    def test_identical_prices_still_tie(self):
        """**现网 Qwen3.8 的实际情形。** 两家价格一模一样，成本维度必然打平 ——
        这个修复不会、也不应该改变那条路由。要让成本说话，得先把自建推理的
        价格改成它真实的边际成本（现在照抄了商用 API 的 0.001/0.002）。"""
        selfhosted = _P("openrouter", 0.001, 0.002)
        commercial = _P("TOKENSTARS_OPENROUTER", 0.001, 0.002)
        ref = crud._candidate_reference_price([(selfhosted, None), (commercial, None)])
        assert _cost_of(selfhosted, ref) == _cost_of(commercial, ref) == pytest.approx(1.0)


class TestZeroIsARealPrice:
    """自建推理没有按 token 计费的边际成本，填 0 是如实描述，不是「没填」。

    原先 `total_price or reference` 把 0 当 falsy 吞掉了 —— 在管理台把自建的价格
    改成 0，对路由**没有任何影响**，而界面上看不出为什么。
    """

    def test_free_provider_scores_full_marks(self):
        free = _P("selfhosted", 0.0, 0.0)
        paid = _P("commercial", 0.001, 0.002)
        ref = crud._candidate_reference_price([(free, None), (paid, None)])
        assert ref == 0.0, "免费候选必须参与取基准，否则它的 0 等于白填"
        assert _cost_of(free, ref) == pytest.approx(1.0)

    def test_paid_cannot_tie_with_free(self):
        """这是修这个 bug 的全部意义：0 和 0.003 必须能分出高下。"""
        free = _P("selfhosted", 0.0, 0.0)
        paid = _P("commercial", 0.001, 0.002)
        ref = crud._candidate_reference_price([(free, None), (paid, None)])
        assert _cost_of(free, ref) > _cost_of(paid, ref)

    def test_a_free_candidate_zeroes_the_cost_axis_for_paid_ones(self):
        """比值语义下，相对「不要钱」任何价格都无从比较 —— 付费的成本分归零。

        这不等于出局：成本权重 0.45，能力+延迟合计 0.55 仍可翻盘。
        真要保留付费候选之间的成本排序，就别把自建填成字面 0，
        填它真实的摊销成本（见 test_amortised_price_keeps_ordering）。
        """
        free = _P("selfhosted", 0.0, 0.0)
        cheap = _P("cheap", 0.0005, 0.0005)
        dear = _P("dear", 0.01, 0.01)
        ref = crud._candidate_reference_price([(free, None), (cheap, None), (dear, None)])
        assert _cost_of(cheap, ref) == _cost_of(dear, ref) == 0.0

    def test_amortised_price_keeps_ordering(self):
        """填一个很小但非零的真实成本，比值语义完好，付费之间仍分得出高下。"""
        selfhosted = _P("selfhosted", 0.0001, 0.0002)   # 0.0003
        cheap = _P("cheap", 0.0005, 0.0005)             # 0.001
        dear = _P("dear", 0.001, 0.002)                 # 0.003
        ref = crud._candidate_reference_price([(selfhosted, None), (cheap, None), (dear, None)])
        assert _cost_of(selfhosted, ref) == pytest.approx(1.0)
        assert _cost_of(cheap, ref) == pytest.approx(0.3, rel=1e-3)
        assert _cost_of(dear, ref) == pytest.approx(0.1, rel=1e-3)

    def test_none_price_is_not_treated_as_free(self):
        """真的没填（历史行的 NULL）不能冒充免费 —— 那会让一条缺失数据赢下成本轴。"""
        unknown = _P("legacy", None, None)
        paid = _P("commercial", 0.001, 0.002)
        ref = crud._candidate_reference_price([(unknown, None), (paid, None)])
        assert ref == pytest.approx(0.003), "None 必须被跳过，不能当成 0"
