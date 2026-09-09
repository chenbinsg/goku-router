"""一条迁移语句失败，不能让整个服务不可用。

## 这条测试为什么存在

2026-09-09 生产事故形状：v1.5.21 上线后**所有落库端点同时 500**，包括业务链路
`/v1/models`；只有不碰数据库的 `/admin/system/info` 还活着。

`ensure_schema` 被 `seed_demo_data` 以及几乎每个 admin/业务读路径调用，而它的
ALTER 循环没有任何 try/except：

    if column_name not in existing_columns:
        db.execute(text(statement))      # 抛了就一路冒到请求层

于是一个**加列动作**把整个路由器打下线。代价与收益完全不成比例：那一列只是给
异常扫描提供时间窗口，而它的失败让所有请求不可用。

失败的正确后果是「那一列不存在」，读它的代码自己容错（新列一律可空 + getattr）。
"""
import logging

import pytest
from sqlalchemy import create_engine, text
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


def test_a_failing_alter_does_not_take_down_ensure_schema(db, monkeypatch, caplog):
    """注入一条必然失败的迁移，ensure_schema 必须照常返回。"""
    original = dict(getattr(crud, "_MIGRATIONS_FOR_TEST", {}))  # 占位，保持可读性
    del original

    real_execute = db.execute

    def boom(stmt, *a, **kw):
        text_sql = str(stmt)
        if "ADD COLUMN" in text_sql:
            raise RuntimeError("simulated: duplicate column / lock timeout")
        return real_execute(stmt, *a, **kw)

    # 先把已有列删掉一列，逼 ensure_schema 去执行 ALTER
    db.execute(text("DROP TABLE request_logs"))
    db.execute(text(
        "CREATE TABLE request_logs (id INTEGER PRIMARY KEY, request_id VARCHAR(255), "
        "requested_model VARCHAR(255), status_code INTEGER, latency FLOAT)"
    ))
    db.commit()
    monkeypatch.setattr(db, "execute", boom)

    # ensure_schema 现在每进程只真正跑一次（迁移已挪到启动阶段，不再在请求路径上）。
    # 测试要的是迁移逻辑本身，所以显式重置缓存。
    crud.reset_schema_cache()
    with caplog.at_level(logging.ERROR):
        crud.ensure_schema(db)          # 不抛 = 通过

    assert any("SCHEMA_MIGRATION_FAILED" in r.message or "SCHEMA_MIGRATION_FAILED" in r.getMessage()
               for r in caplog.records), "迁移失败必须留下可告警的日志，不能静默吞掉"


def test_migrations_are_individually_guarded():
    """静态兜底：ALTER 循环里必须有 try/except，否则一条失败全站 500。"""
    import inspect
    src = inspect.getsource(crud.ensure_schema)
    loop = src[src.index("for table_name, statements in migrations.items():"):]
    assert "try:" in loop and "except Exception:" in loop, (
        "ensure_schema 的迁移循环没有单条容错 —— 一条 ALTER 失败会让每个"
        "调用它的端点同时 500（含业务链路 /v1/models）"
    )
    assert "db.rollback()" in loop, "失败后必须回滚，否则会话留在坏事务里"
