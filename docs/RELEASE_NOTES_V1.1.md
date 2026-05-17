# Goku-Router V1.1.0 Release Notes

发布时间：2026-05-17
上一版本：[V1.0](./RELEASE_NOTES_V1.0.md)

---

## 发布结论

`Goku-Router V1.1.0` 正式发布。

本次更新聚焦 **Provider 管理体验**，新增 Provider 删除能力与一键启用/禁用开关，同时对管理控制台的 Providers 页面进行了全面视觉和交互升级，让运维操作更直观、更安全。

---

## 本次版本重点

### 🗑️ Provider 删除

此前 Provider 一旦创建便无法从界面删除，只能直接操作数据库。V1.1.0 补全了这一能力：

- 新增 `DELETE /admin/providers/{provider_id}` API 端点（HTTP 204）
- **级联处理**：删除 Provider 前自动清理所有引用该 Provider 的路由规则，避免外键约束报错
- 操作记录写入 Audit Log，保留完整变更历史
- 前端以 `Popconfirm` 二次确认对话框防止误操作，并注明"关联路由规则将受影响"

### ⚡ Provider 启用 / 禁用开关

- 每行内联 `Switch`（ON/OFF），无需进入编辑弹窗即可翻转状态
- 切换期间显示 loading 状态，防止重复点击
- 操作结果以 Toast 实时反馈："Provider 已启用" / "Provider 已禁用"

---

## 管理控制台升级 — Providers 页面

### 表格优化

| 变更项 | V1.0 | V1.1.0 |
|--------|------|--------|
| 状态 / 健康列 | 纯文本 | 彩色 Tag（✅ Active / ❌ Disabled / ⚠️ Degraded） |
| 操作列 | Edit + Test | Switch + Edit + Test + Delete |
| 新增按钮位置 | Alert 下方独立按钮 | Card 右上角（PlusOutlined 图标） |
| 列宽 | 展示 12 列（含 env 变量、Token 上限、成本） | 精简为 7 列，聚焦核心信息 |
| 延迟列 | 原始数字 | 格式化为 `xxx ms`，空值显示 `—` |

### 编辑弹窗优化

- 字段分组排列：状态 / 健康 / 优先级 同行；输入成本 / 输出成本 / 延迟 同行；Token 上限同行
- 弹窗宽度统一设为 560px，避免过窄截断
- Test Connection 弹窗宽度设为 480px

---

## Bug 修复 & 代码质量

- `handleAddProvider` 重命名为 `handleSaveProvider`，语义更准确（统一覆盖新增和编辑场景）
- `fetchProviders` 提取为独立函数，支持操作后手动刷新
- `onCancel` 回调精简，消除弹窗关闭后的 stale state 残留
- 全部 `catch (error)` 改为 `catch`，消除 TypeScript unused variable 警告

---

## 变更文件

| 文件 | 变更说明 |
|------|---------|
| `backend/app/crud.py` | 新增 `delete_provider()`，含路由规则级联删除 |
| `backend/app/main.py` | 新增 `DELETE /admin/providers/{provider_id}` 路由 |
| `frontend/src/api/index.ts` | 新增 `deleteProvider()` API 调用 |
| `frontend/src/i18n.tsx` | 新增 EN/ZH 文案：delete、cancel、enabled、disabled、deleteConfirm |
| `frontend/src/pages/ProvidersAdminPage.tsx` | 全面 UI 重构（+272 / -251 行） |
| `frontend/index.html` | 页面标题从 "Frontend" 更正为 "Goku-Router" |
| `VERSION` | V0.2 → V1.1 |

---

## 升级说明

本次为纯功能增量更新，**无 Breaking Change，无数据库 Schema 变更**，直接替换部署即可。

```bash
git pull origin main
./stop.sh && ./start.sh
```

---

**完整变更记录：** https://github.com/chenbinsg/Goku-Router/compare/V1.0...v1.1.0
