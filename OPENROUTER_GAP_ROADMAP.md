# OpenRouter Gap Roadmap

## 目标

这份文档用于把当前 `router` 应用与 OpenRouter 的差距，转成可执行的产品与研发路线图。

当前结论：

- 当前产品已经具备 `统一入口 + Provider 管理 + 模型映射 + 路由 fallback + API key 鉴权 + 基础 usage/billing`
- 当前定位更接近 `MVP 级多模型网关`
- 与 OpenRouter 的差距主要不在“有没有页面”，而在：
  - 协议兼容层深度
  - 路由智能度
  - usage/billing 精细化
  - 平台化与企业治理能力

## 当前能力 vs OpenRouter

### 已有能力

- OpenAI 风格统一入口
- Mock + `openai_compatible` Provider 适配
- 静态主备路由与 fallback
- Provider / Model / Route 控制台
- Provider 连接测试
- API key 鉴权
- 基础请求日志
- 按 API key 维度的 usage/billing 汇总
- 中英文 UI 切换

### 主要缺口

- 缺少自动选模和高级 provider routing
- 缺少完整 OpenAI-compatible 参数支持
- 缺少 streaming 主链
- 缺少 structured outputs / tool calling 完整能力
- 缺少 context compression / message transforms
- 缺少更丰富 usage accounting
- 缺少 organization / workspace / guardrails / analytics / key lifecycle

## 差距分级

### P0：必须补，决定是否像一个“OpenRouter 替代品”

这些能力最直接影响客户是否认为它只是一个内部 demo，还是一个真正可用的模型路由平台。

1. 完整协议兼容层
- 支持更多标准字段：`stream`、`temperature`、`max_tokens`、`top_p`、`stop`
- 支持 `tools`、`tool_choice`
- 支持 `response_format`
- 支持多模态 message content 结构

2. Streaming 主链
- `/v1/chat/completions` 支持流式返回
- fallback 与 streaming 的边界策略明确
- usage 信息在流式结束时回传

3. 动态 provider routing
- 不只是静态主备
- 支持按价格、健康、延迟、能力做选择
- 支持 request 级 provider 偏好

4. 更真实的 usage accounting
- 每次响应直接返回更完整 usage
- 明细日志包含 cost、provider、API key、fallback
- billing 面板按 key / model / provider 聚合

### P1：强烈建议补，决定“好不好卖”

这些能力决定平台是否能进入更真实的客户试用和团队使用。

1. Auto Router / 智能选模
- 提供一个平台虚拟模型，如 `router/auto`
- 根据任务类型、预算、模型能力自动选模

2. Structured Outputs
- 支持 `json_object`
- 支持 `json_schema`
- 给出校验失败和修复策略

3. Tool Calling 兼容
- 工具定义透传
- Provider 不兼容时的转换或降级策略

4. 客户 key 管理闭环
- 后台生成 router key
- Key 命名、启停、轮换
- 不同客户 key 的配额与统计

5. 更完善的控制台
- Provider 编辑已做，但还需要更完整校验
- Model / Route 编辑体验继续打磨
- 增加更清晰的错误反馈和状态提示

### P2：平台化提升，决定“能不能成为产品”

这些能力更偏平台成熟度、企业能力和长线竞争力。

1. Organization / Workspace / Project 隔离
- 组织维度配置
- 项目维度 key 和 usage
- 环境隔离

2. Guardrails / 策略治理
- 可配置 provider allowlist / denylist
- 数据保留策略
- 高风险模型或路由策略约束

3. Analytics / 可观测性
- 请求趋势
- Provider 成功率与延迟面板
- fallback 率
- model 成本排行

4. Prompt transforms / context compression
- 超长上下文处理
- 压缩策略
- 参数不兼容时的自动变换

5. 运营能力
- 审计日志
- 告警
- key usage 异常检测

## 推荐路线图

## 阶段 1：把 MVP 网关升级成“可替代基础路由平台”

目标：

- 让客户觉得“这个已经不是 demo，而是能替代一部分 OpenRouter 基础能力”

建议周期：2-3 周

交付项：

1. Streaming 支持
2. 更多标准参数透传
3. billing / logs 明细增强
4. request 级 provider 偏好
5. 真实 API key 管理页面

验收标准：

- 客户可以用自己熟悉的 OpenAI 调用方式切过来
- 可以用流式调用
- 可以看到比较可信的 usage / cost / fallback 明细

## 阶段 2：把静态路由升级成智能路由

目标：

- 从“可配置路由器”升级到“能帮客户优化成本和稳定性的路由平台”

建议周期：2-4 周

交付项：

1. 动态 provider 选择
2. 按价格 / 延迟 / 健康状态排序
3. provider capability 过滤
4. `router/auto` 虚拟模型

验收标准：

- 同一模型请求可根据策略命中不同 provider
- 可用配置证明成本或成功率优化

## 阶段 3：把协议层补齐到更接近 OpenRouter

目标：

- 让集成方在“不改业务结构”的前提下迁移更多 workload

建议周期：3-4 周

交付项：

1. Tool calling
2. Structured outputs
3. 多模态消息内容
4. 更多高级参数兼容

验收标准：

- 至少一个 tool calling 场景可跑通
- 至少一个 `json_schema` 场景可跑通

## 阶段 4：把平台做成“可商用产品”

目标：

- 从技术能力接近，走向运营与企业能力接近

建议周期：4 周+

交付项：

1. Organization / project / workspace
2. 审计与告警
3. 仪表盘和 analytics
4. key lifecycle
5. guardrails

验收标准：

- 不同客户 / 团队可以独立管理和对账
- 平台维护者能看见异常与趋势

## 推荐 backlog

### P0 Backlog

- `stream=true` 支持
- Chat streaming usage 汇总
- 标准采样参数透传
- `tools` / `tool_choice` schema 扩展
- `response_format` schema 扩展
- Request-level provider preference
- Billing usage by key/model/provider
- API key 管理页面

### P1 Backlog

- Auto Router 策略引擎
- Provider capability registry
- Price / latency / health 排序器
- Structured outputs validator
- Tool calling compatibility layer
- 客户 key 启停与轮换

### P2 Backlog

- Organization / workspace / project
- Guardrails
- Context compression
- Analytics dashboard
- 审计日志
- 告警系统

## 你现在最该做什么

如果目标是“尽快让客户感到它像 OpenRouter”，建议优先顺序是：

1. `streaming + 标准参数兼容`
2. `更细 usage/billing`
3. `动态 provider routing`
4. `tool calling + structured outputs`
5. `真实客户 key 管理`

原因：

- 这些能力最直接影响迁移难度
- 这些能力比继续堆后台页面更能提升替代感

## 最终判断

当前应用已经越过“纯原型”阶段，但距离 OpenRouter 仍有一段明显差距。

最核心的差距不是 UI，而是：

- 路由逻辑不够智能
- 协议兼容不够完整
- 平台化能力不够成熟

如果按这份路线图推进，最现实的目标不是“短期完全对标 OpenRouter”，而是：

先成为一个对中小团队足够可用的 `OpenRouter-lite`，
再逐步补足企业和平台能力。
