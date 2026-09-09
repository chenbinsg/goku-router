"""`/admin/provider-quality-scores` 只要表里有一行就 500。

## 这条测试为什么存在

`ProviderQualityScoreItem.updated_at` 声明成 `Optional[str]`，而 ORM 上那一列是
`DateTime`。端点用 `response_model` + `from_attributes` 直接读 ORM 对象，于是
**有行 → ResponseValidationError → 500；空表 → [] → 200**。

本文件里别的 `_at: Optional[str]` 字段没事，是因为它们的路由层手工
`.isoformat()` 组 dict；只有这个端点直接把 ORM 对象交给 pydantic。

危害不止于端点本身：这是查看 provider 质量分的**唯一入口**（前端没有对应页面）。
2026-06-16~21 那五天 ROUTER_AUTO_OPTIMIZE 开着，drift monitor 跑了 21 轮往表里
写数据 —— 从那天起这个端点就一直 500，两个多月没人发现。而它一坏，
「质量分从没影响过真正的路由」（见 test_quality_score_reaches_the_sort）这件事
也就没人看得见。两个 bug 互相掩护。
"""
from datetime import datetime

import pytest

from app import schemas


class _Row:
    id = 1
    provider_name = "openrouter"
    workload_class = "chat_general"
    quality_score = 0.9
    success_rate = 0.9
    schema_validity_rate = 1.0
    tool_call_success_rate = 1.0
    avg_latency_ms = 500.0
    avg_cost_usd = 0.0
    sample_count = 10
    updated_at = datetime(2026, 6, 21, 11, 0, 18)


def test_a_row_with_a_datetime_serialises():
    """ORM 给的是 datetime —— 这正是线上 500 的那一行。"""
    item = schemas.ProviderQualityScoreItem.model_validate(_Row())
    assert item.updated_at == "2026-06-21T11:00:18"


def test_none_stays_none():
    row = type("R", (_Row,), {"updated_at": None})()
    assert schemas.ProviderQualityScoreItem.model_validate(row).updated_at is None


def test_an_existing_string_passes_through():
    """别的调用方可能已经手工 isoformat 过了，不能再转一次。"""
    row = type("R", (_Row,), {"updated_at": "2026-06-21T11:00:18"})()
    assert schemas.ProviderQualityScoreItem.model_validate(row).updated_at == "2026-06-21T11:00:18"


@pytest.mark.parametrize("field", ["quality_score", "success_rate", "sample_count"])
def test_the_numeric_fields_still_come_through(field):
    item = schemas.ProviderQualityScoreItem.model_validate(_Row())
    assert getattr(item, field) == getattr(_Row, field)
