# CHANGELOG

## 2026-03-12

### 修复
- 修复前端“新增监控无反应”问题：当账号无 `webhook_manage` 权限时，`notify_groups` 为空，不再强制要求勾选分组，允许提交并使用系统默认分组。
- 在新增弹窗中补充提示文案：无分组列表权限时，提交后将使用默认分组。

### 优化
- 新增/编辑监控目标时，支持从混合文本中自动截取第一个 `https://` 开始的链接。
- 保持历史 URL 规范化行为：保存时继续清理 `shareid/shareId` 参数。

### 验证
- `web-admin` 执行 `npm run build` 通过（TypeScript + Vite）。

### 新增
- 监控目标与通知分组改为 SQLite 持久化（`monitor_targets` / `monitor_notify_groups`），轮询间隔等 poll 配置仍保持 JSON 管理。
- 新增监控目标启停开关 `enabled`（默认开启），支持前端卡片开关与新增/编辑表单设置。
- 新增“不可用信号自动停查”机制：当出现 `productBrieflnfo is null` / 需登录态类不可用信号连续达到阈值（默认 5 次）后，自动停用该目标并记录原因。

### 调整
- 推送文案不再展示“通知分组”字段。
- Dashboard 返回增加 `disabled_reason` 与 `consecutive_null_brief_count`，用于前端展示停查状态。

### 新增验证
- 新增最小化测试：验证 `enabled` 参数链路与“连续 5 次自动停查”逻辑。
- 灰度环境完成套餐监控增删改查接口验证（Create/Read/Update/Delete 全通过）。

### 修复（v1.0.2 后补）
- 新增/编辑套餐监控提交前增加前端前置校验：无法从输入中识别 `activity_id` 时，直接提示“链接无效：未识别 activity_id，请检查链接或手动填写 activity_id”，并阻止请求发出。
