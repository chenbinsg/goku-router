#!/usr/bin/env python3
"""把 request_logs / provider_quality_scores 的 provider **名字**回填成 **id**。

## 为什么需要这个脚本

这两张表用名字字符串引用 provider。provider 一改名或被删除，历史行就永久冻结在
旧名字上 —— 所有按 provider 聚合的东西（分析页、质量分、成本建议、异常告警）各自
被劈开。生产实测 2026-09-09：同一台大连的机器以 `local_dalian_openrouter`(6,453)
和 `local-dalian-openrouter`(1,361) 两个名字各自统计，平均延迟一个 50,280ms、
一个 31,339ms。

配套工单：`ops/DBA-provider-id-migration-2026-09-09.md`（含 DDL 与决策项）。

## 用法

    python backend/scripts/backfill_provider_id.py --dry-run
    python backend/scripts/backfill_provider_id.py --apply \\
        --merge local-dalian-openrouter=local_dalian_openrouter
    python backend/scripts/backfill_provider_id.py --verify

## 设计取舍

- **只回填，不建表也不建 provider。** DDL 由 DBA 执行（应用账号没有 ALTER 权限，
  一条失败会让每个落库端点同时 500 —— 见 README「数据库 schema 变更」）。
- **映射不到就中止，不静默留 NULL。** 留 NULL 等于把今天的问题换个形式保留下来，
  而且下一个人会以为迁移成功了。
- **`provider_name IS NULL` 的行跳过。** 那些请求确实没走到任何 provider
  （护栏拦截或全候选失败），NULL 是正确答案，不是缺失。
- **分批提交。** 37,000+ 行一次性 UPDATE 会长时间持锁，而 providers 表上每次成功
  请求都在写 avg_latency_ms。
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# 让脚本能从仓库任意位置运行
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# `provider_name or "unknown"` 的兜底标签会被 drift monitor 写进 provider_quality_scores
# ——「unknown」不是一家供应商，是「这些请求根本没走到任何 provider」。它无法、也不该
# 被映射成 id。生产上这样的行有 4 条（2026-06-21）。
SENTINEL_NAMES = {"unknown"}

TABLES = {
    "request_logs": "provider_name",
    "provider_quality_scores": "provider_name",
}


def _connect(url: str):
    engine = create_engine(url)
    return sessionmaker(bind=engine)(), engine


def _column_exists(db, table: str, column: str) -> bool:
    from sqlalchemy import inspect

    return column in {c["name"] for c in inspect(db.get_bind()).get_columns(table)}


def _provider_ids(db) -> dict[str, int]:
    rows = db.execute(text("SELECT id, name FROM providers")).fetchall()
    return {name: pid for pid, name in rows}


def _pending(db, table: str, name_col: str) -> dict[str, int]:
    """待回填的行，按 provider 名字分组计数。"""
    rows = db.execute(
        text(
            f"SELECT {name_col} AS n, COUNT(*) AS c FROM {table} "
            f"WHERE provider_id IS NULL AND {name_col} IS NOT NULL "
            f"GROUP BY {name_col}"
        )
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def _resolve(names: dict[str, int], ids: dict[str, int], merge: dict[str, str]):
    """把名字解析成 id。返回 (可映射, 无法映射)。"""
    ok, missing = {}, {}
    for name, count in names.items():
        target = merge.get(name, name)
        if target in ids:
            ok[name] = (ids[target], count, target)
        else:
            missing[name] = count
    return ok, missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="只打印将要改什么，不写库")
    mode.add_argument("--apply", action="store_true", help="执行回填")
    mode.add_argument("--verify", action="store_true", help="校验是否还有未映射的行")
    ap.add_argument(
        "--merge", action="append", default=[], metavar="旧名=新名",
        help="把一个名字并入另一个 provider，可重复。"
             "例：--merge local-dalian-openrouter=local_dalian_openrouter",
    )
    ap.add_argument("--batch", type=int, default=5000, help="每批提交行数（默认 5000）")
    ap.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = ap.parse_args()

    if not args.database_url:
        print("需要 --database-url 或环境变量 DATABASE_URL", file=sys.stderr)
        return 2

    merge = {}
    for item in args.merge:
        if "=" not in item:
            print(f"--merge 格式应为 旧名=新名，收到: {item}", file=sys.stderr)
            return 2
        old, new = item.split("=", 1)
        merge[old.strip()] = new.strip()

    db, engine = _connect(args.database_url)
    try:
        # 前置检查：列必须已由 DBA 建好
        for table in TABLES:
            if not _column_exists(db, table, "provider_id"):
                print(
                    f"❌ {table}.provider_id 不存在。\n"
                    f"   这一列必须由 DBA 先执行 DDL（应用账号没有 ALTER 权限）：\n"
                    f"     ALTER TABLE {table} ADD COLUMN provider_id INT NULL;\n"
                    f"   详见 ops/DBA-provider-id-migration-2026-09-09.md",
                    file=sys.stderr,
                )
                return 1

        ids = _provider_ids(db)
        print(f"providers 表现有 {len(ids)} 家: {', '.join(sorted(ids))}\n")

        if args.verify:
            bad = 0
            for table, name_col in TABLES.items():
                left = _pending(db, table, name_col)
                if left:
                    bad += sum(left.values())
                    print(f"❌ {table}: 仍有 {sum(left.values())} 行未映射 -> {left}")
                else:
                    print(f"✅ {table}: 无未映射行")
                orphan = db.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE provider_id IS NOT NULL "
                         f"AND provider_id NOT IN (SELECT id FROM providers)")
                ).scalar()
                if orphan:
                    bad += orphan
                    print(f"❌ {table}: {orphan} 行的 provider_id 指向不存在的 provider")
            return 1 if bad else 0

        # 先把所有表都解析完再决定，不要边打印计划边中止 —— 那看起来像「写了一半」。
        total_planned = 0
        plans = {}
        blockers: dict[str, tuple[dict, dict]] = {}
        resolved: dict[str, tuple[str, dict]] = {}
        for table, name_col in TABLES.items():
            names = _pending(db, table, name_col)
            if not names:
                print(f"{table}: 没有待回填的行")
                continue
            ok, missing = _resolve(names, ids, merge)
            sentinels = {n: c for n, c in missing.items() if n in SENTINEL_NAMES}
            real_missing = {n: c for n, c in missing.items() if n not in SENTINEL_NAMES}
            if real_missing or sentinels:
                blockers[table] = (real_missing, sentinels)
            resolved[table] = (name_col, ok)

        if blockers:
            print("\n❌ 未写入任何数据。以下名字无法映射到 provider id：\n", file=sys.stderr)
            for table, (real_missing, sentinels) in blockers.items():
                for name, count in sorted(real_missing.items(), key=lambda x: -x[1]):
                    print(f"  {table}.{name!r}: {count} 行  —— providers 表里没有这一家",
                          file=sys.stderr)
                for name, count in sorted(sentinels.items(), key=lambda x: -x[1]):
                    print(f"  {table}.{name!r}: {count} 行  —— 这不是 provider，是 "
                          f"`provider_name or \"unknown\"` 的兜底标签", file=sys.stderr)
            print(
                "\n处置：\n"
                "  · providers 表里没有的（已删除的机器）→ 请 DBA 按工单 3.2 节重建为\n"
                "    status='retired'，或用 --merge 并入现存 provider；\n"
                "  · 兜底标签 'unknown' → 它没有对应的 provider，也不该有。按工单 3.5 节\n"
                "    (决策 C1) 删除那些行：DELETE FROM provider_quality_scores;\n"
                "\n中止而不是留 NULL：留 NULL 会让今天的问题换个形式保留下来，"
                "而且看起来像迁移成功了。",
                file=sys.stderr,
            )
            return 1

        for table, (name_col, ok) in resolved.items():
            print(f"\n{table}:")
            for name, (pid, count, target) in sorted(ok.items(), key=lambda x: -x[1][1]):
                via = "" if target == name else f"  （并入 {target!r}）"
                print(f"  {name!r} -> id={pid}  {count} 行{via}")
                total_planned += count
            plans[table] = (name_col, ok)
            skipped = db.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {name_col} IS NULL")
            ).scalar()
            if skipped:
                print(f"  （另有 {skipped} 行 {name_col} 为 NULL，保持 provider_id=NULL —— "
                      f"这些请求确实没走到任何 provider）")

        if args.dry_run:
            print(f"\n[dry-run] 共将回填 {total_planned} 行。加 --apply 执行。")
            return 0

        written = 0
        for table, (name_col, ok) in plans.items():
            for name, (pid, count, _target) in ok.items():
                while True:
                    # 先取一页主键，再按 id 更新。
                    #
                    # ⚠ 不要用 `UPDATE ... LIMIT`：那是 MySQL 专有语法，SQLite 直接
                    # 报 `near "LIMIT": syntax error`。生产是 MySQL 会跑通，但那意味着
                    # 这个脚本**在本地永远无法验证** —— 而 2026-09-09 的事故教训正是
                    # 「只在一种数据库上验证不算验证」。分页写法两边都能跑。
                    ids_page = [
                        r[0] for r in db.execute(
                            text(
                                f"SELECT id FROM {table} "
                                f"WHERE provider_id IS NULL AND {name_col} = :name "
                                f"ORDER BY id LIMIT :batch"
                            ),
                            {"name": name, "batch": args.batch},
                        ).fetchall()
                    ]
                    if not ids_page:
                        break
                    placeholders = ", ".join(f":i{n}" for n in range(len(ids_page)))
                    params = {f"i{n}": v for n, v in enumerate(ids_page)}
                    params["pid"] = pid
                    db.execute(
                        text(f"UPDATE {table} SET provider_id = :pid WHERE id IN ({placeholders})"),
                        params,
                    )
                    db.commit()
                    written += len(ids_page)
                    print(f"  {table} {name!r}: +{len(ids_page)}（累计 {written}）")

        print(f"\n✅ 回填完成，共 {written} 行。")
        print("   下一步：DBA 建索引（工单 3.4），然后跑 --verify 确认。")
        return 0
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
