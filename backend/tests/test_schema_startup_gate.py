"""schema 迁移只在启动时跑一次；模型与库不一致时拒绝启动。

## 这些测试为什么存在

2026-09-09 v1.5.21 事故有三层，这个文件覆盖后两层：

1. 生产应用账号 `goku_router_owner` 没有 ALTER 权限 —— 环境问题，代码管不了；
2. **`ensure_schema` 在每个请求路径上执行 DDL**（全仓 47 处调用），于是一条被拒的
   ALTER 让每个落库端点持续 500 四分钟，而不是失败一次；
3. **模型声明了库里没有的列** —— SQLAlchemy 把它写进每条 SELECT，该表所有查询报
   `Unknown column`。这一层最致命，而且迁移容错**救不了**：问题不在迁移，在于模型
   与库不一致。

对第 3 层，正确反应是**拒绝启动**：崩溃循环刺眼且一眼可诊断（日志直接给出要执行的
ALTER），持续 500 则要翻 traceback 才能发现是加列引起的。
"""
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
        crud.reset_schema_cache()


class TestMigrationsRunOncePerProcess:
    def test_second_call_is_a_noop(self, db, monkeypatch):
        """请求路径上的 47 处调用必须退化成空操作。

        ⚠ 监视点必须是 `crud.inspect`，不是 `db.execute`：`create_all` 和
        `inspect()` 都直接走 engine，绕过 Session。第一版监视 db.execute，
        把缓存整个删掉做变异测试仍然全绿 —— 那条测试什么都没测到。
        """
        crud.reset_schema_cache()
        crud.ensure_schema(db)

        calls = []
        real_inspect = crud.inspect
        monkeypatch.setattr(crud, "inspect", lambda *a, **k: (calls.append(1), real_inspect(*a, **k))[1])
        crud.ensure_schema(db)
        assert calls == [], (
            "ensure_schema 第二次仍在做全库反射 —— 每个请求都会重跑一次，"
            "且迁移失败时每个请求都会抛一次（v1.5.21 的放大机制）"
        )

        crud.ensure_schema(db, force=True)
        assert calls, "force=True 必须仍然真的执行，否则新环境无法自举"

    def test_force_still_works_for_startup(self, db):
        """启动路径要能强制执行，否则新环境无法自举。"""
        crud.reset_schema_cache()
        crud.ensure_schema(db)
        crud.ensure_schema(db, force=True)   # 不抛即可


class TestModelDatabaseConsistency:
    def test_a_complete_schema_reports_nothing_missing(self, db):
        assert crud.verify_model_columns(db) == []

    def test_a_missing_column_is_reported(self, db):
        """精确复现 v1.5.21：库里没有 created_at，而模型声明着它。"""
        db.execute(text("DROP TABLE request_logs"))
        db.execute(text(
            "CREATE TABLE request_logs (id INTEGER PRIMARY KEY, request_id VARCHAR(255), "
            "requested_model VARCHAR(255), status_code INTEGER, latency FLOAT)"
        ))
        db.commit()

        missing = crud.verify_model_columns(db)
        assert "request_logs.created_at" in missing, (
            "没能发现模型与库不一致 —— 这正是让每个 RequestLog 查询报 "
            "Unknown column 的那一层"
        )
        # 那张精简表缺的不止一列，全都该被列出来
        assert "request_logs.provider_name" in missing

    def test_a_table_that_does_not_exist_is_not_reported(self, db):
        """表整个不存在交给 create_all，不该在这里报缺列 —— 否则全新环境永远起不来。"""
        db.execute(text("DROP TABLE request_logs"))
        db.commit()
        assert not any(m.startswith("request_logs.") for m in crud.verify_model_columns(db))


class TestStartupRefusesOnMismatch:
    def test_lifespan_raises_instead_of_serving_500s(self):
        """启动路径必须在不一致时抛出，而不是放行然后每个请求 500。"""
        import inspect
        from app import main

        src = inspect.getsource(main.lifespan)
        assert "verify_model_columns" in src, "启动时没有做模型/库一致性检查"
        assert "raise RuntimeError" in src, (
            "发现不一致却仍然放行 —— 服务会以每个请求 500 的方式活着，"
            "而不是以拒绝启动的方式死掉"
        )
        assert "ensure_schema(db, force=True)" in src, "启动时没有显式跑迁移"
