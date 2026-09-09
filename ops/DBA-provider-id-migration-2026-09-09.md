# DBA 工单：清空遥测表 + provider 引用改为 id

**状态**：决策已定（chenbin 2026-09-09），**待 DBA 执行**
**执行者**：DBA（应用账号 `goku_router_owner` 没有 ALTER 权限）
**耗时**：约 2 分钟。**不可逆。**

---

## 1. 为什么

`request_logs` 和 `provider_quality_scores` 用**名字字符串**引用 provider，没有
`provider_id`。provider 一改名或被删除，历史行就永久冻结在旧名字上 —— 所有按
provider 聚合的东西（分析页、质量分、成本建议、异常告警）各自被劈开。

生产实测：同一台大连的机器以 `local_dalian_openrouter`(6,453 次) 和
`local-dalian-openrouter`(1,361 次) 两个名字各自统计，平均延迟一个 50,280ms、
一个 31,339ms，样本窗口完全分开。这两家连同 `local_openai` 都已从 `providers`
表删除，现存只有：

| id | name | status |
|---:|---|---|
| 13 | `TOKENSTARS_OPENROUTER` | active |
| 10 | `openrouter` | active |

`provider_quality_scores` 的 17 行**没有一行能映射到现存 provider**
（`local-dalian-openrouter` / `local_dalian_openrouter` / `local_openai` /
`unknown`，updated_at 全是 2026-06-21 11:00:16）。其中 `unknown` 不是供应商，是
`provider_name or "unknown"` 的兜底标签 —— drift monitor 给一个不存在的 provider
算了一套质量分。

---

## 2. 决策（chenbin 2026-09-09）

> **两张遥测表全部清空，重新开始。不保留、不备份、不回填。**

演进过程记录在此，便于日后追溯为何选了最激进的一档：

| 曾考虑 | 结论 |
|---|---|
| 把已下线的 provider 重建为 `retired` 行以保住历史 | 否决 —— 「已经删除的都不要了」 |
| 只删已下线 provider 的日志（7,826 行），保留失败记录 | 否决 —— 「即使没问题，我也要 trim 这些日志」 |
| 全表清空 | **采纳** —— 「丙更干净」「二丙」 |

我曾建议保留 `provider_name IS NULL` 的 1,794 行失败记录（含 2026-09-08 那批
Qwen3.8 的 503），理由是它们是故障史、且 NULL 对它们是正确答案而非缺失。
chenbin 重申要清，按此执行。

### ⚠ 执行前请知晓

- **不可逆，且不做备份**（明确选择丙-2）。
- **分析页与账单用量页会归零。** `/admin/billing/usage` 读的是 `request_logs`
  而**不是** `billing_records` —— 清空后累计 $273.8 的用量明细在界面上消失。
- `billing_records` 表本身**不动**，原始账目仍在库里，只是当前没有接口读它。
  月度汇总 `billing_summaries` 是独立表，不受影响。
- 清空后**不需要回填**：新写入的行天生带 `provider_id`（代码上线后）。

---

## 3. 执行

按顺序，全部由 DBA 执行。

```sql
-- ① 清空遥测表
TRUNCATE TABLE request_logs;
TRUNCATE TABLE provider_quality_scores;

-- ② 加列（可空）
ALTER TABLE request_logs            ADD COLUMN provider_id INT NULL;
ALTER TABLE provider_quality_scores ADD COLUMN provider_id INT NULL;

-- ③ 索引
CREATE INDEX ix_request_logs_provider_id            ON request_logs (provider_id);
CREATE INDEX ix_provider_quality_scores_provider_id ON provider_quality_scores (provider_id);
```

校验（三条都应返回 0 / 一行）：

```sql
SELECT COUNT(*) FROM request_logs;                                  -- 0
SELECT COUNT(*) FROM provider_quality_scores;                       -- 0
SHOW COLUMNS FROM request_logs            LIKE 'provider_id';       -- 1 row
SHOW COLUMNS FROM provider_quality_scores LIKE 'provider_id';       -- 1 row
```

> **不加外键约束。** `request_logs` 是高写入表，而 `providers.avg_latency_ms`
> 每次成功请求都在更新。FK 会让子表 INSERT 对父表持共享锁、父表 UPDATE 要排他锁
> —— 正是 core 侧 2026-09 那次 MCP 遥测死锁的模式。收益（引用完整性）远小于风险。

### 附带收益：告警窗口立刻可用

`request_logs.created_at`（本次事故中已由 DBA 补上）在旧数据里全是 NULL，异常扫描
会显式排除它们。表清空后所有新行都带时间，**一小时窗口不再有过渡期**。

---

## 4. 代码侧改动（DDL 完成后另行发版）

本工单**只动数据**。代码改动单独发版，且**必须在 DDL 之后**：

1. `RequestLog.provider_id` / `ProviderQualityScore.provider_id` 加进 ORM 模型；
2. 写入路径同时写 id 和 name（name 保留作为可读冗余）；
3. 聚合路径（分析、质量分、成本建议、异常扫描）改按 id 分组；
4. `_get_provider_quality_score` 改用 id 查找 —— 这才是「质量分对不上号」的真正修复。

> ⚠ **顺序不能颠倒。** ORM 模型一旦声明了库里没有的列，SQLAlchemy 会把它写进
> 每条 SELECT，该表所有查询报 `Unknown column` —— 这正是 2026-09-09 v1.5.21
> 让生产瘫 4 分钟的第三层原因。详见 README「数据库 schema 变更」。

---

## 5. 回填脚本（本次用不上，留作下次）

`backend/scripts/backfill_provider_id.py` —— 三段式 `--dry-run` / `--apply` /
`--verify`，幂等、分批提交。**本次清空后无需回填**，保留是因为下一次有 provider
下线时会再次面对同样的选择，而它把「留 NULL」变成命令行上写明的决定
（`--discard`），而不是沉默的默认。

已用生产比例的 fixture 端到端验证过（含合并、放弃、幂等、verify 各路径）。
