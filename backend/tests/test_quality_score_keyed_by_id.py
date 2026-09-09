"""质量分必须按 provider **id** 关联，且不给「没走到 provider」的请求算分。

## 这些测试为什么存在

2026-09-09 查生产 `provider_quality_scores`，17 行的 provider_name 只有四个值：

    local-dalian-openrouter / local_dalian_openrouter / local_openai / unknown
    updated_at 全部 = 2026-06-21 11:00:16

**没有一行能映射到现存 provider。** 机器改名/下线后，按名字查永远查不到 ——
于是 drift monitor 每 6 小时算出来的分，三个月里对路由一次都没起过作用。
（它连排序都没进，那是另一个 bug，见 test_quality_score_reaches_the_sort。
两个 bug 叠在一起，这个功能从上线起就是死的。）

第四个值 `unknown` 更离谱：它来自 `row.provider_name or "unknown"`，是「这个请求
没走到任何 provider」的兜底标签 —— 统计代码**给一个不存在的供应商算了一套质量分**。
同一个写法还让成本建议推荐「把流量迁到 unknown，预计省 98 美元」，把「请求全挂了」
读成了「这家不要钱」。
"""
import inspect
import itertools
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


# ⚠ 不要用 id(object()) 造唯一值：对象回收后地址会复用，主键当场撞号。
_seq = itertools.count(1)


def _log(provider_id, provider_name, status=200, latency=100.0):
    return models.RequestLog(
        request_id=f"r{next(_seq)}", requested_model="Qwen3.8", resolved_model="Qwen3.8",
        provider_id=provider_id, provider_name=provider_name,
        status_code=status, latency=latency, cost_amount=0.01,
        created_at=datetime.utcnow(),
    )


class TestLookupIsByIdNotName:
    def test_signature_takes_an_id(self):
        sig = inspect.signature(crud._get_provider_quality_score)
        assert "provider_id" in sig.parameters, (
            "仍按名字查 —— 机器一改名，历史分就永远对不上（生产实测：17 行无一命中）"
        )

    def test_a_row_is_found_by_id(self, db):
        db.add(models.ProviderQualityScore(
            provider_id=10, provider_name="openrouter", workload_class="tool_use",
            quality_score=0.4, updated_at=datetime.utcnow()))
        db.commit()
        assert crud._get_provider_quality_score(db, 10, "tool_use") == pytest.approx(0.4)

    def test_a_renamed_provider_still_matches(self, db):
        """核心收益：名字变了，id 没变，分仍然找得到。"""
        db.add(models.ProviderQualityScore(
            provider_id=10, provider_name="老名字", workload_class="tool_use",
            quality_score=0.4, updated_at=datetime.utcnow()))
        db.commit()
        assert crud._get_provider_quality_score(db, 10, "tool_use") == pytest.approx(0.4)

    def test_missing_data_does_not_punish(self, db):
        """查不到返回 1.0（不惩罚），不是 0 —— 没有数据不等于质量差。"""
        assert crud._get_provider_quality_score(db, 999, "tool_use") == 1.0
        assert crud._get_provider_quality_score(db, None, "tool_use") == 1.0
        assert crud._get_provider_quality_score(None, 10, "tool_use") == 1.0


class TestNoScoreForRequestsThatNeverReachedAProvider:
    def test_null_provider_rows_are_skipped(self, db):
        """`provider_id IS NULL` = 护栏拦截或全候选失败。它们不构成任何供应商的
        质量证据，而原来的 `or "unknown"` 把它们攒成了一个假 provider。"""
        for _ in range(10):
            db.add(_log(10, "openrouter", status=200))
        for _ in range(20):
            db.add(_log(None, None, status=503))
        db.commit()

        crud.update_provider_quality_scores(db=db, lookback_hours=24)

        rows = db.query(models.ProviderQualityScore).all()
        assert [r.provider_id for r in rows] == [10], (
            f"给没走到 provider 的请求算了质量分: "
            f"{[(r.provider_id, r.provider_name) for r in rows]}"
        )
        assert all(r.provider_name != "unknown" for r in rows)

    def test_the_surviving_row_is_not_polluted_by_failures(self, db):
        """那 20 条 503 不该拉低 openrouter 的成功率 —— 它们不是它的失败。"""
        for _ in range(10):
            db.add(_log(10, "openrouter", status=200))
        for _ in range(20):
            db.add(_log(None, None, status=503))
        db.commit()

        crud.update_provider_quality_scores(db=db, lookback_hours=24)
        rec = db.query(models.ProviderQualityScore).filter_by(provider_id=10).one()
        assert rec.success_rate == pytest.approx(1.0)
        assert rec.sample_count == 10

    def test_name_is_written_as_readable_redundancy(self, db):
        for _ in range(3):
            db.add(_log(10, "openrouter"))
        db.commit()
        crud.update_provider_quality_scores(db=db, lookback_hours=24)
        rec = db.query(models.ProviderQualityScore).filter_by(provider_id=10).one()
        assert rec.provider_name == "openrouter"

    def test_a_rename_refreshes_the_readable_name(self, db):
        """已存在的行也要刷新名字，否则可读列会永远停在旧名。"""
        db.add(models.ProviderQualityScore(
            provider_id=10, provider_name="老名字", workload_class="chat_general",
            quality_score=1.0, updated_at=datetime.utcnow()))
        for _ in range(3):
            db.add(_log(10, "新名字"))
        db.commit()

        crud.update_provider_quality_scores(db=db, lookback_hours=24)
        rec = db.query(models.ProviderQualityScore).filter_by(provider_id=10).one()
        assert rec.provider_name == "新名字"
