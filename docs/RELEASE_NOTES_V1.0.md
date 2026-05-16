# Goku-Router V1.0 正式发版公告

发布时间：2026-05-17

---

## 发布结论

`Goku-Router V1.0` 已正式发布。

这是 Goku-Router 的首个生产就绪版本，从 v0.2 原型完成全面升级，正式具备企业级 LLM 流量管控能力。V1.0 作为 AIOS 平台的统一 LLM 网关正式投入使用，支持多模型三级故障转移、工作负载感知路由、策略引擎与全链路请求追踪。

---

## 本次版本重点

### 🔀 智能路由引擎

- **三级故障转移**：Primary → Fallback → Emergency，任意节点故障自动切换，业务零感知
- **工作负载感知路由**：按 `tool_use`、`structured_extraction`、`long_context`、`chat_general`、`chat_reasoning` 五类工作负载动态调整质量 / 延迟 / 成本权重
- **多路由策略**：`static_primary_backup`、`cheapest_provider`、`fastest_provider`、`openrouter_like_auto`、`current_production_policy` 五种策略可配置
- **模型别名解析**：请求发出前自动将本地别名（如 `deepseek-r1`）解析为真实 Provider API 模型名，避免上游拒绝

### 🛡️ 策略引擎

- **五层策略层次**：Org → Workspace → Project → API Key → Request，细粒度权限管控
- **策略类型**：预算（Budget）、模型白 / 黑名单（Model）、Provider 限制（Provider）、数据留存（Data / ZDR）、能力授权（Capability）、安全过滤（Safety）
- **Guardrail 预设**：内置多套 preset，支持 `/admin/guardrails/dry-run` 在线预检

### 📡 OpenAI 兼容网关

- 完整实现 `/v1/chat/completions`（含 streaming）、`/v1/embeddings`、`/v1/models`
- 现有客户端仅修改 `base_url` 即可接入，无需任何代码改动
- `tool_calls`、`tool_call_id`、`name` 字段透传，工具调用历史完整保留
- `exclude_none=True` 序列化，避免向上游发送空字段

### 🔧 关键 Bug 修复

- **max_prompt_chars 截断问题**：默认值从 4000 提升至 200,000，修复 AIOS 系统提示被压缩为单条消息、导致 ReAct 无限工具调用循环的问题
- **`"NoneNoneNone"` 响应污染**：`_extract_text_content()` 修复 `content: null`（tool_calls 场景）时回退到 `str(None)` 的问题
- **Provider 凭证加载**：`config.py` 新增 `dotenv_values()` 二级查找，确保进程环境变量未注入时仍可正确读取 `.env` 中的 API Key 和 Base URL

### 📊 可观测性与管理

- **全链路追踪**：每个请求记录完整 `route_trace_json`，包含候选 Provider、评分依据、选择路径、fallback 链路、成本与延迟预测
- **Eval 基准套件**：内置 4 套工作负载数据集（`sample_workloads`、`customer_support`、`sales_ops`、`finance_compliance`），路由策略变更前可量化回归验证
- **管理控制台**：React 18 + Ant Design 前端，覆盖 Providers、Models、Routing Rules、API Keys、Billing、Logs、Security 共 14 个功能页面

### ⚙️ 工程基础

- **数据库**：SQLAlchemy 2.0，MySQL（生产）/ SQLite（开发）双模式；`database/init.sql` 提供 MySQL 一键建表
- **认证**：JWT + bcrypt，支持多租户 API Key 鉴权
- **脚本**：`scripts/setup_aios_providers.py` 一键注册 AIOS 所需 Provider；`start.sh` / `stop.sh` 完整服务生命周期管理

---

## 与前序版本对比

| 能力 | V0.1 | V0.2 | V1.0 |
|------|------|------|------|
| OpenAI 兼容端点 | ✅ | ✅ | ✅ |
| 多 Provider 故障转移 | 基础 | 双级 | **三级** |
| 工作负载感知路由 | ❌ | 部分 | ✅ |
| 策略引擎 | ❌ | 基础 | ✅ |
| Tool call 透传 | ❌ | ❌ | ✅ |
| Prompt 截断修复 | ❌ | ❌ | ✅ |
| 模型别名解析 | ❌ | ❌ | ✅ |
| .env 凭证二级加载 | ❌ | ❌ | ✅ |
| 全链路追踪 | 基础 | ✅ | ✅ |
| Eval 基准套件 | ❌ | ✅ | ✅ |
| 管理控制台 | 基础 | ✅ | ✅ |
| AIOS 集成验证 | ❌ | ❌ | ✅ |

---

## 发布适用场景

- **生产网关**：作为 AIOS 或其他 LLM 应用的统一接入层
- **多模型治理**：跨 OpenAI / Anthropic / DeepSeek / 私有模型的统一策略执行
- **成本控制**：基于工作负载类型的自动最优 Provider 选择
- **合规环境**：零数据留存（ZDR）策略强制、Provider 区域约束

---

## 已知非阻断项

- BillingRecord 写入尚未完整实现（billing UI 展示基于估算）
- 响应侧内容过滤（response filtering）仍在开发中
- Alembic 迁移体系规划中，当前使用 ad-hoc schema 初始化

---

## 快速开始

```bash
git clone https://github.com/chenbinsg/Goku-Router.git
cd Goku-Router
cp backend/.env.example .env   # 填入 DATABASE_URL、SECRET_KEY、Provider API Keys
./start.sh
```

- 网关：`http://localhost:8000`  —  Swagger：`http://localhost:8000/docs`
- 管理控制台：`http://localhost:5159`

---

*Goku-Router V1.0 — Enterprise AI Traffic Control Plane*
