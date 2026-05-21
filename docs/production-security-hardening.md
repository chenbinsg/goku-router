# Goku-Router 生产部署与安全加固记录

本文记录 2026-05 腾讯云部署过程中遇到的问题、已落地的源码加固，以及生产安装时必须执行的加固步骤。所有密钥值均不应写入仓库或 PR。

## 本次源码加固

- 管理前端不再打包 `VITE_ROUTER_API_KEY` 或默认 `demo-router-key`。Playground 调用改走 `/admin/playground/*`，使用管理员 JWT，由服务端转发到内部路由逻辑。
- CORS 从 `*` 改为 `ALLOWED_ORIGINS` 白名单，避免任意站点携带浏览器凭据访问管理接口。
- BYOK provider API key 保存时使用 `ROUTER_SECRET_KEY` 派生的 Fernet 加密，历史明文记录保持只读兼容，后续新建 key 不再明文入库。
- 增加生产 `.env` 示例项：`ALLOWED_ORIGINS`、`JWT_SECRET_KEY`、`ADMIN_PASSWORD`、`ROUTER_SECRET_KEY`。

## 部署时遇到的问题

- Router 后端和前端端口曾直接监听公网地址。生产环境应只暴露 Nginx/CLB 的 80/443，后端端口、前端静态服务端口、数据库端口只允许内网访问。
- 前端历史实现会把 Router API key 打包给浏览器，等同于把后端调用凭据发给所有管理员浏览器和构建产物；本 PR 改为管理员 JWT 代理调用。
- `ROUTER_API_KEYS=demo-router-key`、`JWT_SECRET_KEY=change-me...`、`ADMIN_PASSWORD=admin123` 都只能用于本地开发，生产启动前必须替换。
- OpenAI official provider 与 Qwen/OpenRouter-compatible provider 是两条不同链路。Qwen 当前配置指向 ngrok gateway，后端实际模型位置取决于 ngrok 对端。
- 上游 LLM 超时较长，应用层和反代层需要统一超时，否则浏览器可能先断开，后台仍在等待 upstream。
- 腾讯云 CLI、GitHub token、OpenAI key、provider key 均属于部署凭据，不应写入镜像、仓库、前端环境变量或 PR；聊天和日志中出现过的密钥应轮换。

## 生产安装步骤

1. 拉取版本并准备环境：

```bash
git checkout v1.4.3
cp backend/.env.example backend/.env
```

2. 生成并填写生产密钥：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"  # JWT_SECRET_KEY
python -c "import secrets; print('goku_' + secrets.token_urlsafe(32))"  # ROUTER_API_KEYS item
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # ROUTER_SECRET_KEY
```

3. 至少设置以下生产环境变量：

```dotenv
APP_ENV=production
DATABASE_URL=mysql+pymysql://router:<password>@db:3306/goku_router
ALLOWED_ORIGINS=https://router.yourdomain.com
ROUTER_API_KEYS=<server-to-server api key list>
JWT_SECRET_KEY=<48+ char random value>
ADMIN_PASSWORD=<strong initial password>
ROUTER_SECRET_KEY=<stable Fernet key>
PROVIDER_OPENAI_OFFICIAL_BASE_URL=https://api.openai.com/v1
PROVIDER_OPENAI_OFFICIAL_API_KEY=<provider key>
PROVIDER_OPENROUTER_BASE_URL=<openrouter-compatible endpoint>
PROVIDER_OPENROUTER_API_KEY=<provider key>
```

前端生产构建不应再设置 `VITE_ROUTER_API_KEY`。浏览器只保存管理员 JWT；真正的 Router API key 仅用于服务端到 Router 的调用。

4. 启动与验证：

```bash
docker compose pull
docker compose up -d db
docker compose up -d backend frontend
curl -fsS https://router.yourdomain.com/health
curl -i https://router.yourdomain.com/admin/playground/models
```

未带管理员 JWT 访问 `/admin/playground/models` 应返回 401。登录管理端后，Playground 聊天和 embedding 请求应使用 `/admin/playground/*`，浏览器请求中不应出现 Router API key。

## 基础设施加固清单

- 云安全组：公网只开放 80/443；SSH 只允许固定运维 IP；数据库、后端、前端服务端口仅允许内网或同机反代访问。
- TLS：通过腾讯云 CLB/证书或 Nginx 终止 HTTPS，启用 TLS 1.2/1.3 和 HSTS。
- 管理面：`/admin/*` 只允许可信来源，管理员密码上线后立即更换，后续补充 MFA 与 token blacklist。
- Secrets：所有 provider key、Router API key、JWT secret、云 AK/SK 放入环境变量或 Secret Manager；前端构建变量不得包含服务端密钥。
- BYOK：设置稳定的 `ROUTER_SECRET_KEY` 并纳入密钥备份流程。丢失该 key 会导致已加密 BYOK 记录无法解密，只能重新录入。
- 观测：记录 upstream HTTP 错误响应体时继续脱敏 Authorization、API key、Cookie；对 401/403、5xx、provider timeout 和 circuit breaker open 建告警。
- 出站：只允许 Router 后端访问必要 LLM provider endpoint；对 ngrok 或临时 gateway 设置单独告警和过期检查。
