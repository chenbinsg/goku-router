# DBA 工单：provider 引用从「名字」改为「id」

**状态**：待 chenbin 决策（第 2 节三个选项），DDL 尚未执行
**背景**：2026-09-09 排查中发现，按 provider 聚合的所有统计都被改名劈成了几份

---

## 1. 问题

`request_logs.provider_name` 和 `provider_quality_scores.provider_name` 存的都是
**名字字符串**，没有 `provider_id`。provider 一改名或被删除，历史行就永久冻结在
旧名字上，而新行用新名字 —— 所有按 provider 聚合的东西（分析页、质量分、成本建议、
异常告警）各自被劈开。

生产现状：

| 日志里的 provider 名 | 请求数 | 现在还存在吗 |
|---|---:|---|
| `openrouter` | 25,234 | ✅ id=10 |
| `local_dalian_openrouter` | 6,453 | ❌ 已删除 |
| `TOKENSTARS_OPENROUTER` | 2,527 | ✅ id=13 |
| `unknown` | 1,794 | ❌ 不是 provider，是 `provider_name IS NULL` 的兜底标签 |
| `local-dalian-openrouter` | 1,361 | ❌ 已删除 |
| `local_openai` | 12 | ❌ 已删除 |

**注意第 2、5 行**：`local_dalian_openrouter` 和 `local-dalian-openrouter` 只差一个
字符（下划线 vs 连字符），服务的是同一个模型 `Qwen3.6-35B-A3B-FP8`，几乎可以肯定
是同一台大连的机器被登记了两次。它们的统计各自独立：平均延迟一个 50,280ms、一个
31,339ms，样本窗口完全分开。

### `provider_quality_scores` 的 17 行全是孤儿

```
local-dalian-openrouter / local_dalian_openrouter / local_openai / unknown
updated_at 全部 = 2026-06-21 11:00:16
```

**没有一行能映射到现存 provider。** 迁移到 id 不会修好它们，只会把「对不上号」
从隐性变成显式的 NULL。而且其中的 `unknown` 说明 `update_provider_quality_scores`
也用了 `provider_name or "unknown"` —— drift monitor 给一个不存在的 provider 算了
一套质量分。

---

## 2. ⚠ 需要决策的三件事

### 决策 A：两个「大连」算一家还是两家？

- **A1 合并**（推荐）：都指向同一个 retired provider id。历史统计合并，反映物理现实。
- **A2 保留区分**：建两个 retired provider。保留「曾经登记过两次」这个事实。

> 我倾向 A1：它们是同一台机器，分开统计本身就是这次要修的 bug。
> 但如果两个名字对应过不同的部署/配置，A2 更诚实 —— **这一点只有你知道**。

### 决策 B：已删除的 provider 怎么办？

- **B1 重建为 `retired` 行**（推荐）：给它们真实的 id，历史行全部可映射，
  引用完整性完整。`status='retired'` 不参与选路（`_resolve_candidates` 只取
  `status='active'`）。
- **B2 留 NULL**：`provider_id` 为空，靠 `provider_name` 兜底显示。

> 倾向 B1：7,826 行历史（占 21%）否则永远无法参与按 id 的聚合，
> 等于把今天的问题换个形式留下。

### 决策 C：质量分那 17 行

- **C1 删除**（推荐）：六月的数据，机器已不存在，其中一条是伪造的 `unknown`。
- **C2 随 B1 一起迁移**：保留但它们永远不会被读到（现存 provider 名字对不上）。

> 倾向 C1。留着只会让下一个人以为质量分有数据。

---

## 3. DDL（决策确认后执行）

**应用账号 `goku_router_owner` 没有 ALTER 权限**，以下必须由 DBA 执行。
执行顺序不能颠倒：先加列（可空）→ 回填 → 再加索引/外键。

### 3.1 加列（可空，不加外键约束）

```sql
ALTER TABLE request_logs           ADD COLUMN provider_id INT NULL;
ALTER TABLE provider_quality_scores ADD COLUMN provider_id INT NULL;
```

> 先不加 FK：回填期间会有一段时间存在无法映射的行。回填完成、确认无孤儿后
> 再考虑加约束（见 3.4）。

### 3.2 重建已删除的 provider（仅当选 B1）

**A1（合并大连）**：

```sql
INSERT INTO providers
  (name, adapter_type, host_type, status, health_status, priority,
   input_cost_per_1k, output_cost_per_1k, avg_latency_ms, capability_tags,
   supported_parameters, max_input_tokens, max_output_tokens,
   data_collection_mode, supports_zdr, circuit_breaker_state)
VALUES
  ('local_dalian_openrouter', 'openai_compatible', 'internal', 'retired', 'unknown',
   999, 0.001, 0.002, 500, 'chat', 'temperature,max_tokens', 32768, 4096, 'deny', 0, 'closed'),
  ('local_openai',            'openai_compatible', 'internal', 'retired', 'unknown',
   999, 0.001, 0.002, 500, 'chat', 'temperature,max_tokens', 32768, 4096, 'deny', 0, 'closed');
```

**A2（保留区分）**：在上面基础上再插一行 `'local-dalian-openrouter'`（连字符版）。

> `status='retired'`（非 `active`）确保它们不参与选路。
> `priority=999` 是第二道保险。

### 3.3 回填

用 `backend/scripts/backfill_provider_id.py`（见第 4 节），**不要手写 UPDATE** ——
脚本会先 dry-run 打印每一类映射的行数，确认后才写。

它做的事等价于：

```sql
-- 能直接对上名字的
UPDATE request_logs r
  JOIN providers p ON p.name = r.provider_name
  SET r.provider_id = p.id
WHERE r.provider_id IS NULL AND r.provider_name IS NOT NULL;

-- A1 时额外：连字符版并入下划线版
UPDATE request_logs r
  JOIN providers p ON p.name = 'local_dalian_openrouter'
  SET r.provider_id = p.id
WHERE r.provider_id IS NULL AND r.provider_name = 'local-dalian-openrouter';
```

`provider_name IS NULL` 的 1,794 行**保持 provider_id 为 NULL** —— 它们确实没有
provider（护栏拦截或全候选失败）。v1.5.22 起 503 会如实署名，新数据不再有这个洞。

### 3.4 索引

```sql
CREATE INDEX ix_request_logs_provider_id            ON request_logs (provider_id);
CREATE INDEX ix_provider_quality_scores_provider_id ON provider_quality_scores (provider_id);
```

> 外键约束**暂不加**：`request_logs` 是高写入表，FK 会在每次插入时对 `providers`
> 加共享锁 —— core 侧 2026-09 那次 MCP 遥测死锁正是这个模式（子表 INSERT 持 S 锁，
> 父表 UPDATE 要 X 锁）。而 `providers` 的 `avg_latency_ms` 每次成功请求都会被更新。
> 收益（引用完整性）远小于风险。

### 3.5 质量分表清理（选 C1）

```sql
DELETE FROM provider_quality_scores;   -- 17 行，全部是 2026-06-21 的孤儿
```

---

## 4. 回填脚本

`backend/scripts/backfill_provider_id.py`

```bash
# 1) 先看会改什么，不写库
python backend/scripts/backfill_provider_id.py --dry-run

# 2) 确认后执行（分批提交，默认每批 5000 行）
python backend/scripts/backfill_provider_id.py --apply

# 3) 校验：应输出 0 孤儿
python backend/scripts/backfill_provider_id.py --verify
```

脚本特性：

- **幂等**：只处理 `provider_id IS NULL AND provider_name IS NOT NULL` 的行，
  重复执行安全；
- **分批提交**：`request_logs` 有 37,000+ 行，一次性 UPDATE 会长时间持锁；
- **合并映射可配置**：`--merge local-dalian-openrouter=local_dalian_openrouter`
  （对应决策 A1），不写死在代码里；
- **不创建 provider**：3.2 的 INSERT 由 DBA 执行，脚本只读 `providers` 做映射。
  映射不到的名字会被列出来并**中止**，不会静默留 NULL。

---

## 5. 代码侧改动（DDL 完成后另行发版）

本工单**只涉及数据**。代码改动会在单独的版本里跟进：

1. `RequestLog.provider_id` / `ProviderQualityScore.provider_id` 加进 ORM 模型；
2. 写入路径同时写 id 和 name（name 保留一段时间作为可读冗余）；
3. 聚合路径（分析、质量分查询、成本建议、异常扫描）改按 id 分组；
4. `_get_provider_quality_score` 改用 id 查找 —— 这才是「质量分对不上号」的真正修复。

> ⚠ 顺序要求：**先 DDL，后发代码**。ORM 模型一旦声明了库里没有的列，
> 该表所有查询会报 `Unknown column`（2026-09-09 v1.5.21 事故的第三层原因）。
> 详见 README「数据库 schema 变更」。
