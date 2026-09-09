#!/usr/bin/env python3
"""检查数据库是否满足当前代码的 schema 要求。**上线前跑这个。**

## 为什么需要

v1.5.23 起，启动时会比对 ORM 模型声明的列与数据库实际的列，**不一致就拒绝启动**
（2026-09-09 事故的第三层修复：模型声明了库里没有的列，SQLAlchemy 会把它写进每条
SELECT，该表所有查询报 Unknown column，而迁移容错救不了）。

拒绝启动是刻意的 —— 起不来一眼可诊断，每个请求 500 则伪装成「服务还活着」。
但要在**部署前**知道，而不是在滚动更新时发现。

这个脚本跑的是**和启动闸门完全同一套判断**（`crud.verify_model_columns`），
所以不会出现「脚本说没问题、服务却起不来」。

## 用法

在 v1.5.23 的代码目录下，用生产库的连接串：

    DATABASE_URL='mysql+pymysql://user:pass@host:3306/db' \\
      python backend/scripts/check_schema.py

或直接在容器里：

    kubectl exec deploy/goku-router -- python backend/scripts/check_schema.py

退出码 0 = 可以部署；1 = 有缺列，输出里会给出要执行的 ALTER。

> ⚠ 必须在**要部署的那个版本**的代码上跑。在旧版本代码上跑，检查的是旧版本的
> 模型集合，会漏掉新版本新增的列 —— 那正是要防的情况。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if len(sys.argv) > 1:
        url = sys.argv[1]
    if not url:
        print("用法: DATABASE_URL=... python backend/scripts/check_schema.py", file=sys.stderr)
        print("  或: python backend/scripts/check_schema.py '<database-url>'", file=sys.stderr)
        return 2

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app import crud, models

    engine = create_engine(url)
    db = sessionmaker(bind=engine)()
    try:
        version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "VERSION")
        version = "unknown"
        if os.path.exists(version_file):
            with open(version_file, encoding="utf-8") as fh:
                version = fh.read().strip()

        total = sum(len(t.columns) for t in models.Base.metadata.tables.values())
        print(f"代码版本 {version} —— 模型声明 {total} 列 / "
              f"{len(models.Base.metadata.tables)} 张表")

        missing = crud.verify_model_columns(db)
        if not missing:
            print("\n✅ 数据库满足要求，可以部署。")
            return 0

        print(f"\n❌ 缺少 {len(missing)} 列。**这个版本会拒绝启动。**\n")
        print("请 DBA 执行（类型以模型为准，下面给的是建议值）：\n")
        for item in missing:
            table_name, column_name = item.split(".", 1)
            column = models.Base.metadata.tables[table_name].columns[column_name]
            try:
                sql_type = column.type.compile(engine.dialect)
            except Exception:
                sql_type = str(column.type)
            print(f"  ALTER TABLE {table_name} ADD COLUMN {column_name} {sql_type} NULL;")
        print("\n新增列一律 NULL：历史行无法诚实回填。")
        print("详见 README「数据库 schema 变更」。")
        return 1
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
