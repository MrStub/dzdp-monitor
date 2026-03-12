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
