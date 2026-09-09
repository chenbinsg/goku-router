"""写日志时必须同时记下 provider 的 **id**，而不只是名字。

## 这些测试为什么存在

`request_logs` 和 `provider_quality_scores` 此前只存 provider **名字字符串**。
provider 一改名或被删除，历史行就永久冻结在旧名字上 —— 所有按 provider 的聚合
各自被劈开。生产实测 2026-09-09：同一台大连的机器以 `local_dalian_openrouter`
(6,453 次) 和 `local-dalian-openrouter`(1,361 次) 两个名字各自统计，平均延迟一个
50,280ms、一个 31,339ms，样本窗口完全分开。

`provider_quality_scores` 更糟：2026-06-21 写下的 17 行，改名后**没有一行**能对上
现存 provider —— drift monitor 每 6 小时辛苦算出来的分，三个月里一次都没被读到过。

本文件只覆盖**写入**（双写 id + name，name 保留作可读冗余）。聚合改按 id 读是
另一批改动。
"""
import inspect

from app import crud, models


def _request_log_write_sites() -> list[str]:
    """从源码里切出每一处 models.RequestLog(...) 构造。"""
    src = inspect.getsource(crud)
    sites, start = [], 0
    while True:
        i = src.find("models.RequestLog(", start)
        if i == -1:
            return sites
        j = src.index("\n    )", i) if "\n    )" in src[i:i + 3000] else i + 3000
        sites.append(src[i:i + 3000].split("db.add")[0])
        start = i + 1


class TestModelsDeclareTheColumn:
    def test_request_log_has_provider_id(self):
        assert hasattr(models.RequestLog, "provider_id")

    def test_quality_score_has_provider_id(self):
        assert hasattr(models.ProviderQualityScore, "provider_id")

    def test_both_are_nullable(self):
        """护栏拦截、全候选失败等情况确实没有 provider —— NULL 是正确答案。
        而 provider_quality_scores 的历史行也无法回填。"""
        assert models.RequestLog.__table__.c.provider_id.nullable
        assert models.ProviderQualityScore.__table__.c.provider_id.nullable

    def test_name_is_kept_as_readable_redundancy(self):
        """不删 provider_name：日志要能直接读懂，不必每次去 join。"""
        assert hasattr(models.RequestLog, "provider_name")


class TestEveryWriteSiteSetsIt:
    def test_all_four_sites_write_provider_id(self):
        sites = _request_log_write_sites()
        assert len(sites) == 4, f"预期 4 处 RequestLog 构造，实际 {len(sites)}"
        for n, site in enumerate(sites):
            assert "provider_id=" in site, (
                f"第 {n + 1} 处 RequestLog 构造没写 provider_id —— "
                f"只写名字的话，那一行永远无法按 id 聚合"
            )

    def test_success_paths_use_the_provider_object(self):
        src = inspect.getsource(crud._execute_routed_chat_completion)
        assert src.count("provider_id=provider.id,") == 2, (
            "两条成功路径（缓存命中 / 真实调用）都该直接用 provider.id"
        )

    def test_the_failure_path_records_the_failing_provider_id(self):
        """503 全候选失败时要署上**最后尝试**那家的 id —— 和 provider_name 一致。"""
        src = inspect.getsource(crud._execute_routed_chat_completion)
        assert "provider_id=failed_provider_id," in src
        assert "failed_provider_id = attempted[-1][0]" in src

    def test_the_guardrail_block_path_stays_null(self):
        """400 护栏拦截确实没走到任何 provider，NULL 是正确答案而非缺失。"""
        src = inspect.getsource(crud._execute_routed_chat_completion)
        head = src[:src.index('_create_notification(db, "routing_failure"')]
        assert "provider_id=None," in head


class TestFreshEnvironmentsCanBootstrap:
    def test_migration_list_covers_both_tables(self):
        """全新环境（测试、本地首启）靠 ensure_schema 自举，两张表都要在清单里。

        生产上这两列由 DBA 执行（应用账号没有 ALTER 权限），但清单仍要写 ——
        否则新环境起不来。
        """
        src = inspect.getsource(crud.ensure_schema)
        assert "ALTER TABLE request_logs ADD COLUMN provider_id" in src
        assert "ALTER TABLE provider_quality_scores ADD COLUMN provider_id" in src


class TestProviderIdIsInspectable:
    """写进去了还得看得见 —— 否则「有没有写」在界面上无从确认。

    v1.5.24 上线后写入侧已双写，但 /admin/logs 的响应里只有名字，于是没人能验证
    id 是否真的落库。这一整轮排查反复撞见同一类缺口：改了、但看不见。
    """

    def test_the_log_api_exposes_provider_id(self):
        from app import schemas
        assert "provider_id" in schemas.RequestLogItem.model_fields, (
            "/admin/logs 不返回 provider_id —— 无法验证双写是否生效"
        )

    def test_the_mapper_actually_fills_it(self):
        import inspect
        src = inspect.getsource(crud.list_request_logs)
        assert "provider_id=row.provider_id," in src, (
            "schema 声明了字段但映射没填，响应里会恒为 null"
        )
