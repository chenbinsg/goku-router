"""路由的延迟维度必须用**吞吐**，不能用整体请求耗时。

## 这条测试为什么存在

2026-09-09 我根据 `avg_latency_ms` 从 5,011 一路读到 22,787ms，判断自建端点
「正在退化，趋势和上次故障前一模一样」。**那是误报**，而且那台机器当时能在
516ms 内响应。

真相是这个数在测一个不存在的东西。同一个 provider 同一时刻：

    max_tokens=1     → 中位数   0.8 秒（30 条，探活类）
    max_tokens=4096  → 中位数  23.4 秒，最慢 265 秒（59 条）

单一 EMA 跨越这样一个总体，只会停在双峰之间的谷底 —— 几乎没有任何真实请求在
那个数值附近。它在 5,011 / 14,425 / 22,787 / 171,839 之间游走，反映的是最近碰巧
跑过哪一档，不是机器状态。而这个数直接进 `latency_score` 参与路由打分。

那 13 条 250 秒的请求，实际速率是 15.5–18.3 tok/s，**方差极小** —— 稳态机器的
签名。4096 ÷ 16.5 ≈ 248 秒，精确复现观测值。吞吐才是该比较的量。
"""
import pytest

from app import crud, schemas


class _P:
    def __init__(self, name="p", lat=5000.0, tps=None):
        self.name = name
        self.avg_latency_ms = lat
        self.avg_output_tokens_per_sec = tps
        self.input_cost_per_1k = 0.001
        self.output_cost_per_1k = 0.002
        self.priority = 100
        self.health_status = "healthy"
        self.max_input_tokens = 1_000_000
        self.max_output_tokens = 8192
        self.capability_tags = "chat"
        self.supported_parameters = "temperature,max_tokens"
        self.supports_zdr = True
        self.data_collection_mode = "deny"
        self.status = "active"


def _lat_score(provider):
    _, comp = crud._provider_route_score(
        provider,
        schemas.ChatCompletionRequest(model="m", messages=[{"role": "user", "content": "hi"}]),
        "chat_general",
        {"capability": 0.3, "latency": 0.25, "cost": 0.45},
        reference_price_per_1k=0.003,
    )
    return comp["latency_score"]


class TestThroughputDrivesTheScore:
    def test_a_slow_but_healthy_machine_is_not_punished_for_long_generations(self):
        """生产原形：自建端点 avg_latency_ms=22,787（被 4096-token 请求拉高），
        但吞吐是正常的 16.5 tok/s。旧口径会把它打成 0.22 分。"""
        selfhosted = _P("selfhosted", lat=22787.0, tps=16.5)
        assert _lat_score(_P("no_tps", lat=22787.0)) == pytest.approx(0.219, abs=0.01)  # 旧口径
        assert _lat_score(selfhosted) > 0.4, "吞吐正常的机器不该因为生成得多而被重罚"

    def test_a_genuinely_slow_machine_still_scores_low(self):
        """别把惩罚一起关掉 —— 真的慢就该低分。"""
        fast = _P("fast", tps=40.0)
        slow = _P("slow", tps=4.0)
        assert _lat_score(fast) == pytest.approx(1.0)
        assert _lat_score(slow) == pytest.approx(0.1, abs=0.01)

    def test_falls_back_to_latency_when_there_is_no_throughput_sample(self):
        """新 provider、或只跑过小请求时，退回旧口径而不是编一个数。"""
        assert _lat_score(_P(lat=5000.0, tps=None)) == pytest.approx(1.0)
        assert _lat_score(_P(lat=50000.0, tps=None)) == pytest.approx(0.1, abs=0.01)


class TestTinyGenerationsAreExcluded:
    """⚠ 这组测试的第一版是假的：它只断言常量存在、名字出现在源码里。
    删掉闸门做变异测试，**5 条全绿**。所以把吞吐更新抽成了纯函数直接测行为。"""

    def test_a_one_token_probe_does_not_touch_the_ema(self):
        """生产原形：max_tokens=1 的探活占最近 100 条请求的 30%，耗时 0.8 秒。
        1 / 0.8 = 1.25 tok/s，而这台机器真实吞吐 16.5 —— 收进去会把 EMA 压垮，
        让健康机器看起来慢 13 倍。"""
        from app.services import providers
        p = _P(tps=16.5)
        providers.update_throughput_ema(p, completion_tokens=1, elapsed_s=0.8)
        assert p.avg_output_tokens_per_sec == 16.5, "小生成量样本污染了吞吐 EMA"

    def test_a_real_generation_updates_the_ema(self):
        """别把统计一起关掉 —— 正常大小的生成必须收进来。

        样本值要和现有 EMA 明显不同，否则「没变化」和「被闸门挡掉」看起来一样。
        （第一版取了 4096/248≈16.5，正好等于初值，这条测试因此毫无鉴别力。）
        """
        from app.services import providers
        p = _P(tps=10.0)
        providers.update_throughput_ema(p, completion_tokens=4096, elapsed_s=100.0)  # 40.96 tok/s
        assert p.avg_output_tokens_per_sec == pytest.approx(0.1 * 40.96 + 0.9 * 10.0, abs=0.01)
        assert p.avg_output_tokens_per_sec > 10.0, "新样本必须把 EMA 往上带"

    def test_first_sample_seeds_the_ema_instead_of_being_damped(self):
        """初值为 None 时直接取样本值 —— 否则 α=0.1 会让新 provider 的读数
        从 0 慢慢爬，前二十次调用里它一直显得极慢。"""
        from app.services import providers
        p = _P(tps=None)
        providers.update_throughput_ema(p, completion_tokens=1000, elapsed_s=50.0)
        assert p.avg_output_tokens_per_sec == 20.0

    def test_zero_elapsed_is_ignored(self):
        from app.services import providers
        p = _P(tps=16.5)
        providers.update_throughput_ema(p, completion_tokens=4096, elapsed_s=0.0)
        assert p.avg_output_tokens_per_sec == 16.5
