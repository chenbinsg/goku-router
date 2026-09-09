"""打分档案必须能下位，A/B 实验必须有人收尾。

## 这些测试为什么存在

2026-09-09 在生产上发现一个跑了三个月的「僵尸实验」`auto_exp_20260610_0500`
（2026-06-10 起 active，至 09-09 无人判定），牵出三个互相咬合的缺陷：

1. **关掉 ROUTER_AUTO_OPTIMIZE 停掉的是裁判，不是比赛。**
   `drift_monitor_job`（发起实验）和 `ab_significance_check_job`（判定实验）
   共用一个开关。开关一关，已经开着的实验永远跑下去。

2. **实验 active 时接管的是 100% 流量的权重选择**，不是它自己那 10%
   （见 `_resolve_route_scoring_context`：有实验就直接返回，根本不读活跃档案）。
   管理台显示活跃档案是 `auto_recalibrated`，而 90% 的请求走的是对照组
   `default_heuristic_profile` —— 界面与运行时不一致。

3. **promote 和 rollback 效果相同。** 挑战者档案在被 `recalibrate` 造出来时就
   已经是 `status=active`，而 rollback 分支只把实验置为结束、不动档案。实验一
   结束就掉进 fallback，于是「判定挑战者更差」的结局是把挑战者交给全部流量。
   而那个挑战者的权重是 cost 0.8 —— 它是在 `cost_score` 因写死参考价而恒等于
   1.0 的年代「学」出来的，把 80% 权重给了唯一一个没有信息量的维度。

第 3 条尤其阴险：它让「回滚」这个安全动作变成了和「推广」一样的高风险动作。
"""
from datetime import datetime, timedelta

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


def _profile(db, name, status, cost=0.45):
    row = models.RouteScoringProfile(
        name=name, status=status,
        weights_json=f'{{"chat_general": {{"capability": 0.3, "latency": 0.25, "cost": {cost}}}}}',
        source_dataset="test", trained_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    return row


class TestActiveProfileCanBeChanged:
    def test_a_bad_profile_can_be_taken_off(self, db):
        """生产原形：auto_recalibrated（cost 0.8）卡在活跃位上三个月，
        而 train/recalibrate 之外没有任何途径能改。"""
        _profile(db, "auto_recalibrated", "active", cost=0.8)
        assert crud._get_active_route_scoring_profile_name(db) == "auto_recalibrated"

        crud.set_active_route_scoring_profile(db, crud.DEFAULT_SCORING_PROFILE_NAME)
        assert crud._get_active_route_scoring_profile_name(db) == "default_heuristic_profile"

    def test_switching_leaves_exactly_one_active(self, db):
        _profile(db, "a", "active")
        _profile(db, "b", "inactive")
        crud.set_active_route_scoring_profile(db, "b")
        actives = [r.name for r in db.query(models.RouteScoringProfile)
                   .filter(models.RouteScoringProfile.status == "active").all()]
        assert actives == ["b"]

    def test_unknown_profile_is_rejected_without_side_effects(self, db):
        """失败必须什么都不改 —— 否则一次打错字就会把所有档案下线，
        静默把权重切成内置默认。"""
        _profile(db, "keep_me", "active")
        with pytest.raises(ValueError):
            crud.set_active_route_scoring_profile(db, "typo")
        assert crud._get_active_route_scoring_profile_name(db) == "keep_me"


class TestRollbackActuallyRollsBack:
    def test_rollback_deactivates_the_challenger(self, db):
        """此前 rollback 只结束实验、不动档案 —— 而挑战者本就是 active，
        于是「挑战者更差」的判决把它交给了 100% 的流量。"""
        _profile(db, "auto_recalibrated", "active", cost=0.8)
        db.add(models.RouteScoringExperiment(
            name="auto_exp", control_profile_name="default_heuristic_profile",
            challenger_profile_name="auto_recalibrated", traffic_percentage=10,
            status="active",
            created_at=datetime.utcnow() - timedelta(days=91),
            updated_at=datetime.utcnow(),
        ))
        db.commit()

        import inspect
        src = inspect.getsource(crud.run_ab_significance_check)
        rollback = src[src.index("# Rollback: challenger is worse"):]
        assert 'challenger_row.status = "inactive"' in rollback, (
            "rollback 没有把挑战者下线 —— 实验一结束就掉进 fallback，"
            "挑战者反而拿到全部流量，与 promote 效果相同"
        )


class TestTheJanitorIsNotGatedByTheLauncher:
    def test_ab_check_runs_regardless_of_auto_optimize(self):
        """关掉自动优化的语义是「不再开新实验」，不是「已开的没人收尾」。"""
        import inspect
        from app.services import scheduler
        src = inspect.getsource(scheduler.start_scheduler)
        gated = src[src.index("if _auto_optimize:"):]
        launcher_end = gated.index("_scheduler.add_job(\n        ab_significance_check_job")
        assert "drift_monitor_job" in gated[:launcher_end], "发起实验的 job 应继续受开关控制"
        assert "ab_significance_check_job" not in gated[:launcher_end], (
            "判定 job 仍被 ROUTER_AUTO_OPTIMIZE 挡着 —— 关掉开关会让已开的实验永远跑下去"
        )
