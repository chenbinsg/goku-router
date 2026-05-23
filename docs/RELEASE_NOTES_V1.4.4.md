# Goku-Router V1.4.4 Release Notes

发布时间：2026-05-23
上一版本：[V1.4.1](./RELEASE_NOTES_V1.1.md)

---

## 发布结论

`Goku-Router V1.4.4` 正式发布。

本次更新覆盖 **v1.4.2 → v1.4.4** 三个版本迭代，重点围绕四个方向：BYOK（Bring Your Own Key）密钥管理体系的完整落地、图片生成代理能力、认证稳定性优化，以及 CI/CD 流水线建设。

---

## 本次版本重点

### 🔑 BYOK Key 管理（完整实现）

后端新增完整的 BYOK 密钥管理模块：

- `ByokKey` ORM 模型：`label / provider / api_key_encrypted / key_preview / org_label / project_label / is_active`
- API 接口：`GET/POST /admin/byok`，`PUT/DELETE /admin/byok/{id}`
- 密钥存储时加密，展示时前 8 后 4 脱敏，原始值不落日志
- 前端完整重写 `ByokAdminPage`：表格展示、启停 Switch、编辑/删除 Popconfirm
- 支持 8 种 Provider：OpenAI / Anthropic / Gemini / Azure / DeepSeek / Mistral / Cohere / Custom

### 🖼️ 图片生成代理接口

新增 `POST /v1/images/generations` 端点，通过 BYOK Key 代理图片生成请求：

- 根据 model 名称自动解析 Provider（`gpt-image-2` → OpenAI 等）
- 查找该 Provider 下激活的 BYOK Key，透明转发请求
- AIOS `generate_image` 工具现可通过 Router 路由，无需在 AIOS 侧硬编码 API Key
- 更换图片 Provider 只需在 Router 管理台添加/激活对应 BYOK Key

### 🛠️ Model Catalog 删除 API

- 新增 `DELETE /admin/models/{id}` 端点（HTTP 204）
- 前端添加删除按钮（Popconfirm 二次确认）、编辑图标、加载态
- 优化错误信息格式，移除加载时多余的成功 Toast

### 🔄 OpenRouter Provider 增强

- `ChatCompletionRequest` 新增 `presence_penalty` 和 `extra_body` 字段，透传至上游 vLLM
- 路由到 `openrouter` Provider 时自动注入推荐参数：
  - `enable_thinking: false`（关闭 Qwen3 hybrid thinking）
  - `top_k: 20, top_p: 0.8, presence_penalty: 1.5`
- 调用方传入的值优先（setdefault 语义）

---

## Bug 修复

### 认证 & Token 管理

| 修复项 | 详情 |
|---|---|
| 外部 Provider 超时 | 从 120s 提升至 300s，适配 35B 模型（Qwen3.6 等）长输出场景 |
| HTTP 错误日志 | 非 2xx 响应自动记录 response body 前 500 字符，方便诊断 vLLM 400/422 |
| JWT TTL | access token 改为 24 小时，减少频繁登出 |
| 401 自动刷新 | access token 过期后拦截器静默用 refresh token 换新 token 并重试原请求，并发请求排队等待 |
| Refresh 队列泄漏 | refresh 失败时正确清空 `_refreshQueue`，避免 Promise 永久挂起 |
| Provider ID 字段 | 改为下拉选择框（数字 ID），修复手填名称字符串导致的 422 错误 |

---

## CI / DevOps

新增三条 GitHub Actions 工作流：

| 工作流 | 触发条件 | 执行内容 |
|---|---|---|
| `frontend.yml` | `frontend/**` 变更 | TypeScript 类型检查 + Vite 构建 |
| `backend.yml` | `backend/**` 变更 | ruff lint + pytest |
| `docker.yml` | `main` 分支 / tag 推送 | 多阶段镜像构建并推送至 Docker Hub |

Dockerfile 使用多阶段构建（Node 前端编译 → Python 后端），最终镜像不含 Node 环境。

---

## 升级说明

版本间无 DB 迁移变更，直接重启服务即可。

```bash
git pull
./stop.sh && ./start.sh
```
