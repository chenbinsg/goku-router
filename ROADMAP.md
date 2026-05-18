# Goku-Router — Product Roadmap

> 当前版本：**v1.4.1** | 更新时间：2026-05

---

## 已发布版本

### ✅ v1.0.0 — 基础能力修复（Foundation Fix）

- 真实 Token 计数（tiktoken，降级 word-count）
- BillingRecord 写入（每次请求 / 缓存命中均记录）
- 配额执行（quota_requests / quota_spend_usd / expires_at → HTTP 429）
- 消费追踪（RouterApiKey.spend_usd 实时累加）
- DB 健康检查（`GET /health` 查询 `SELECT 1`）
- Schema 迁移（ensure_schema() 覆盖所有新列）

---

### ✅ v1.0.1 — 核心路由（Core Routing）

- `host_type`（internal / external）+ `region` 字段
- 电路熔断器（CLOSED → OPEN → HALF_OPEN，5 次失败触发，60s 冷却）
- 熔断器集成到路由执行链
- 延迟 EMA 实时更新（α=0.1，每次真实调用后更新）
- 内部 Provider 超时 15s，外部 30s
- `GET /admin/circuit-breakers` + `POST /admin/circuit-breakers/{name}/reset`

---

### ✅ v1.1.0 — 安全管控（Security）

- `services/safety.py` 统一请求 + 响应安全流水线
- 请求过滤：关键词（精确，大小写不敏感）+ 正则 → 返回结构化 SafetyViolation
- 响应过滤：所有 Provider 返回值过滤后再返回客户端
- PII 检测 & 脱敏：6 种内置正则（邮箱、JP/US 手机、信用卡、SSN、JP My Number）
- Block vs Redact 模式
- 响应拦截写入 AuditLog
- `POST /v1/feedback`（rating 1–5、success、notes）

---

### ✅ v1.2.0 — 可观测性 & 计费（Observability & Billing）

- 月度账单 Rollup Job（每月 1 日 01:00 UTC）→ MonthlyBillingSummary
- Invoice 导出（JSON + CSV）`GET /admin/billing/invoice`
- Token 用量仪表盘（日/周/月，按 model/provider/org 汇总）
- 可配置异常阈值（AnomalyThresholdConfig，per-org）
- 每小时异常巡检 Job（失败率 / 延迟 / 成本 spike → NotificationRecord）
- 日志保留 Job（每日 02:00 UTC，删除超期 RequestLog）
- 日志搜索 API（`GET /admin/logs`，支持分页和多维过滤）

---

### ✅ v1.3.0 — 自演化路由（Self-Evolution）

- 漂移监控 Job（每 6h）：ProviderQualityScore 更新 + 自动重校准
- 重校准触发条件：≥ 500 新日志 + 权重漂移 > 10%
- RecalibrationEvent 审计表
- A/B 实验自动发起（漂移 > 10% → 10% 流量挑战组）
- 夜间 z-test（03:00 UTC）：双比例检验，p < 0.05 且 ≥ 7 天 → 自动晋升/回滚
- ProviderQualityScore：成功率 / Schema 合规率 / 工具调用成功率合成评分
- 质量分乘入路由评分，自动惩罚劣质 Provider
- `GET /admin/provider-quality-scores`
- `POST /admin/provider-quality-scores/refresh`

---

### ✅ v1.4.0 — 登录 & 用户管理（Auth & User Management）

- AdminUser 模型（username / password_hash bcrypt / role / email / is_active / last_login_at）
- `services/auth.py`：bcrypt 哈希、JWT Access（30min）+ Refresh（7d）HS256
- `POST /auth/login` / `POST /auth/refresh` / `POST /auth/logout`
- 所有 `/admin/*` 路由 JWT 中间件保护（OPTIONS 放行 CORS）
- RBAC：superadmin（全权）/ admin（除用户管理）/ viewer（只读）
- `GET/PUT /admin/users/me`（自助改邮箱）
- `PUT /admin/users/me/password`（改密码，需验证当前密码）
- `GET/POST/PUT/DELETE /admin/users`（superadmin 专属）
- 启动自动 seed superadmin（ADMIN_USER / ADMIN_PASSWORD 环境变量）

---

### ✅ v1.4.1 — 管理台 UI 完善（Admin UI Polish）

- 个人资料页（`/admin/profile`）：查看信息、改邮箱、改密码弹窗
- 头部下拉菜单：个人资料 / 修改密码 / 退出登录
- 用户管理页接入侧边栏导航（Access & Security 分组）
- 修复 `/v1/models` 鉴权问题（JWT 被误当 Router API Key 验证导致 401）
- 登录页底部版本号展示

---

## 未来规划

### 🚧 v1.5.0 — 可靠性 & 告警（Reliability & Alerting）

**目标：生产环境零感知故障切换 + 异常第一时间通知到人**

- [ ] **流式 Fallback**：流式请求中途 Provider 断连，自动无缝切换到 backup，客户端不感知
- [ ] **重试预算**：可配置最大重试次数 / 总超时预算，防止雪崩
- [ ] **内部 Provider 健康心跳**：后台 Job 每 30s 主动探活，提前发现故障
- [ ] **Webhook 告警推送**：异常通知推送到钉钉 / Feishu / Slack / PagerDuty（可配置）
- [ ] **实时成本预警**：消费超出预算阈值时立即告警 + 可选自动熔断
- [ ] **Token 黑名单**（Redis 支持）：服务端真正注销 JWT，退出即失效

---

### 🚧 v1.6.0 — 可观测性升级（Observability+）

**目标：对接企业标准监控体系，支持 SRE 级别排障**

- [ ] **OpenTelemetry 导出**：Trace / Metric / Log 统一导出，支持 Grafana / Datadog / Jaeger
- [ ] **延迟分位数**：P50 / P95 / P99 per Provider per Model，告别平均数掩盖长尾
- [ ] **Provider 错误细分**：rate_limit / timeout / server_error / schema_error 分类统计
- [ ] **结构化日志**：JSON Lines 输出到 stdout，兼容 Fluentd / Logstash / ELK
- [ ] **Chargeback 报告**：按 project 精细分摊共享网关成本，支持 CSV 导出
- [ ] **成本预测**：基于历史趋势预测下月消耗，邮件/Webhook 周报

---

### 🚧 v1.7.0 — 安全加固（Security Hardening）

**目标：达到金融 / 医疗场景的安全基线**

- [ ] **TOTP / MFA**：superadmin 账号强制二次验证
- [ ] **Presidio / ML PII 检测**：替换正则，支持上下文感知 NER，降低漏检率
- [ ] **IP 白名单 & 速率限制细化**：per-IP / per-API-Key 独立限流，IP 黑名单
- [ ] **API Key HMAC 签名**：防止 Key 被截获后直接复用
- [ ] **审计 Webhook**：高危操作（删除用户、修改安全策略）实时推送审计系统
- [ ] **敏感字段加密存储**：Provider API Key 落库加密（AES-256）

---

### 🚧 v1.8.0 — 路由智能化（Smart Routing+）

**目标：路由决策精度媲美 OpenRouter，且可自学习**

- [ ] **ML 工作负载分类器**：Logistic Regression 替换规则分类，每月从 RequestLog 重训
- [ ] **语义缓存**：基于 embedding 相似度命中缓存，命中率预计提升 30%+
- [ ] **多目标路由优化**：同时权衡 latency / cost / quality，Pareto 最优解
- [ ] **金丝雀流量动态调整**：A/B 实验流量比例可实时调整（当前固定 10%）
- [ ] **用户反馈 UI**：Chat 页面回复气泡内嵌评分（👍/👎），打通反馈闭环
- [ ] **模型能力自动发现**：调用 Provider `/models` 接口自动同步支持的模型列表

---

### 🚧 v1.9.0 — 生态 & 开发者体验（Ecosystem）

**目标：降低接入门槛，扩大 Provider 覆盖**

- [ ] **预置 Provider 适配器**：Anthropic / Gemini / Cohere / Mistral / Together 原生 SDK 对接
- [ ] **本地模型支持**：Ollama / vLLM / LM Studio 统一接入，内网部署全流程打通
- [ ] **Python SDK**：`pip install goku-router`，支持 OpenAI 兼容接口
- [ ] **Node.js SDK**：`npm install goku-router`
- [ ] **Swagger / Redoc 文档站**：`/docs` 在线 API 文档，自动从代码生成
- [ ] **CLI 工具**：`goku chat "hello"` / `goku providers list` 命令行快速管理
- [ ] **Webhook 回调**：请求完成后推送结构化事件到业务系统

---

### 🚧 v2.0.0 — 高可用 & 多实例（HA & Scale）

**目标：支持水平扩展，达到 99.9% 可用性 SLA**

- [ ] **Redis 集群模式**：会话共享、限流计数器、缓存跨实例同步
- [ ] **多实例无状态部署**：熔断器状态、质量评分持久化到 Redis / DB
- [ ] **Kubernetes Helm Chart**：生产级 k8s 部署方案
- [ ] **MySQL / PostgreSQL Alembic 迁移**：完全替换 ensure_schema() 手工迁移
- [ ] **数据库读写分离**：日志写入走 replica，路由决策走 primary
- [ ] **蓝绿发布支持**：配置热重载，不停机更新路由规则

---

## 版本进度总览

```
v1.0.0  基础能力修复       ████████████████████  ✅ DONE
v1.0.1  核心路由           ████████████████░░░░  ✅ DONE (85%)
v1.1.0  安全管控           ██████████████░░░░░░  ✅ DONE (75%)
v1.2.0  可观测性 & 计费    ██████████████████░░  ✅ DONE (90%)
v1.3.0  自演化路由         ████████████████░░░░  ✅ DONE (80%)
v1.4.0  登录 & 用户管理    ████████████████████  ✅ DONE
v1.4.1  管理台 UI 完善     ████████████████████  ✅ DONE
──────────────────────────────────────────────────
v1.5.0  可靠性 & 告警      ░░░░░░░░░░░░░░░░░░░░  📋 PLANNED
v1.6.0  可观测性升级       ░░░░░░░░░░░░░░░░░░░░  📋 PLANNED
v1.7.0  安全加固           ░░░░░░░░░░░░░░░░░░░░  📋 PLANNED
v1.8.0  路由智能化+        ░░░░░░░░░░░░░░░░░░░░  📋 PLANNED
v1.9.0  生态 & 开发者体验  ░░░░░░░░░░░░░░░░░░░░  📋 PLANNED
v2.0.0  高可用 & 多实例    ░░░░░░░░░░░░░░░░░░░░  📋 PLANNED
```

---

*Goku-Router Roadmap — v1.4.1 | © Chuck 2026*
