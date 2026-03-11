# 大众点评套餐库存监控

这套项目现在拆成三层：

- `monitor.py`：常驻监控进程，部署在你自己的服务器
- `admin_api.py`：管理 API，部署在你自己的服务器
- `web-admin/`：React + TypeScript + Vite 管理前端，使用 Tailwind / shadcn/ui 风格组件，部署到 Cloudflare Pages

## 当前能力

- 多个 `activityid` 链接同时监控
- 默认每 60 秒轮询，可热更新
- 只在 `IN_STOCK` 时推送有货提醒
- 同一监控项的同一异常，当天连续满 `5` 次提醒 `1` 次
- 飞书多分组推送：不同套餐可走不同 webhook
- 邮件通知保留
- 代理池接入入口已预留，后续只需补 provider 参数
- 管理 API 支持 SQLite 用户登录、权限控制、会话 Token 与审计日志
- OpenClaw skill / 网页后台 / Docker 常驻监控共用一份 `config.json`

## 目录说明

- [monitor.py](/Users/daizhenghao/Documents/workspace/TraeSpace/dzdp-monitor/monitor.py)：库存监控主进程
- [admin_api.py](/Users/daizhenghao/Documents/workspace/TraeSpace/dzdp-monitor/admin_api.py)：管理 API
- [proxy_provider.py](/Users/daizhenghao/Documents/workspace/TraeSpace/dzdp-monitor/proxy_provider.py)：代理池 provider 适配入口
- [app_config.py](/Users/daizhenghao/Documents/workspace/TraeSpace/dzdp-monitor/app_config.py)：配置读写、目标 CRUD、分组 CRUD、公用规则
- [web-admin/](/root/.openclaw/workspace/skills/dzdp-monitor/web-admin)：React + TypeScript + Vite 前端
- [docker-compose.server.yml](/Users/daizhenghao/Documents/workspace/TraeSpace/dzdp-monitor/docker-compose.server.yml)：服务端双容器样板
- [DEPLOYMENT.md](/Users/daizhenghao/Documents/workspace/TraeSpace/dzdp-monitor/DEPLOYMENT.md)：详细部署流程

## 配置文件

先复制：

```bash
cp config.example.json config.json
```

核心配置项：

- `targets`：监控套餐列表
- `targets[].group_key`：该套餐走哪个飞书分组
- `notify.feishu_groups`：多个飞书 webhook 分组
- `notify.default_group_key`：默认推送分组
- `admin_api.listen_host/listen_port`：管理 API 监听地址
- `admin_api.cors_allowed_origins`：允许访问 API 的前端域名
- `admin_api.auth_token`：兼容旧版静态 Bearer Token（仍可用）
- `admin_api.default_admin_username/default_admin_password`：首次初始化默认管理员账号
- `admin_api.session_ttl_hours`：登录会话有效期（小时）
- `admin_api.login_rate_limit.*`：登录失败限流参数（防爆破）
- `admin_api.max_body_bytes`：单请求体大小上限（默认 1MB）
- `proxy.*`：代理池 provider 配置

说明：

- 旧的 `notify.feishu_webhook` 仍兼容
- 旧的 `admin_api.auth_token` 仍兼容；新版本优先使用 `/api/auth/login` 登录态
- 链接会自动去掉 `shareid`
- 推荐输入：`https://m.dianping.com/app/femember-groupbuyinter-static/main.html?activityid=xxxx`

## 账号与权限初始化

- 启动 `admin_api.py` 时会在 `sqlite_path` 同库自动建表：`users`、`roles`、`user_permissions`、`auth_sessions`、`audit_logs`。
- 若不存在默认管理员用户，会按 `admin_api.default_admin_username` 和 `admin_api.default_admin_password` 自动创建。
- 若未配置 `default_admin_password`，服务会生成高强度随机密码并写入 `sqlite_path` 同目录下 `admin_bootstrap_credentials.txt`（权限 600），不会在日志输出明文密码。
- 普通用户权限点：
  - `targets_read`
  - `targets_create`
  - `targets_update`
  - `targets_delete`
  - `webhook_manage`
  - `poll_manage`
  - `proxy_manage`

## 迁移说明（从旧版无账号/仅 auth_token 升级）

1. 先备份 `config.json` 与 `sqlite_path` 指向的数据库文件。
2. 在 `config.json` 的 `admin_api` 中补充 `default_admin_password`（建议强密码）。
3. 重启 `admin_api.py`，系统会自动建表并初始化默认 admin。
4. 前端改为通过 `/api/auth/login` 登录；如需临时兼容，仍可继续使用旧 `auth_token` 作为 Bearer。
5. 监控主进程 `monitor.py` 无需改动、无需迁移脚本。

## 安全配置要求

- `admin_api.listen_host` 默认是 `127.0.0.1`；如需外网访问，请显式改为你的监听地址并配合防火墙/反向代理。
- `admin_api.cors_allowed_origins` 不再默认允许 `*`，必须配置为你的前端域名白名单（例如 `https://your-cloudflare-pages.pages.dev`）。
- 建议显式配置 `admin_api.default_admin_password`，避免依赖一次性密码文件。
- `admin_api.login_rate_limit` 默认 `5` 次失败/`10` 分钟窗口，触发后封禁 `10` 分钟。

## 本地启动

### 1. 安装 Python 依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 单次检查

```bash
python3 monitor.py --config config.json --once
```

### 3. 启动持续监控

```bash
python3 monitor.py --config config.json
```

### 4. 启动管理 API

```bash
python3 admin_api.py --config config.json
```

默认监听：`127.0.0.1:8787`

也可以通过 CLI 临时覆盖监听地址（不改配置文件）：

```bash
python3 admin_api.py --config config.json --host 127.0.0.1 --port 18787
```

### 5. 启动前端

```bash
cd web-admin
npm install
npm run dev
```

API 地址改为构建时注入，不再支持在前端页面手填。

本地开发可通过环境变量指定后端入口（推荐）：

```bash
cd web-admin
VITE_API_BASE_URL=http://127.0.0.1:8787 npm run dev
```

如果未提供 `VITE_API_BASE_URL`，前端会使用安全默认值（本地 `http://127.0.0.1:8787` / 灰度 `http://127.0.0.1:18788`）。

## OpenClaw / Skill 命令

查看中文帮助：

```bash
./skills/dzdp-monitor-openclaw/scripts/run_monitor.sh help-zh
```

关键命令：

```bash
# 单次检查
./skills/dzdp-monitor-openclaw/scripts/run_monitor.sh once --config config.json

# 常驻监控
./skills/dzdp-monitor-openclaw/scripts/run_monitor.sh start --config config.json

# 启动管理 API
./skills/dzdp-monitor-openclaw/scripts/run_monitor.sh admin-api --config config.json

# 套餐列表
./skills/dzdp-monitor-openclaw/scripts/run_monitor.sh targets --config config.json list --json

# 新增套餐并指定推送分组
./skills/dzdp-monitor-openclaw/scripts/run_monitor.sh targets --config config.json add --name "春意寻味双人餐" --url "https://m.dianping.com/app/femember-groupbuyinter-static/main.html?activityid=1682152928&shareid=abc" --group-key default --json

# 查看推送分组
./skills/dzdp-monitor-openclaw/scripts/run_monitor.sh groups --config config.json list --json

# 新增推送分组
./skills/dzdp-monitor-openclaw/scripts/run_monitor.sh groups --config config.json add --name "武汉群" --key wuhan --webhook "https://open.feishu.cn/open-apis/bot/v2/hook/..." --json

# 修改轮询时间
./skills/dzdp-monitor-openclaw/scripts/run_monitor.sh poll --config config.json set --seconds 30 --json
```

## 前端部署到 Cloudflare Pages

前端目录：`web-admin/`

Cloudflare Pages 推荐配置：

- Framework preset：`None`
- Build command：`npm run build`
- Build output directory：`dist`
- Root directory：`web-admin`
- 环境变量：`VITE_API_BASE_URL=https://你的服务端域名`

前端会调用你自己服务器上的 `admin_api.py`。

本地构建示例（构建时注入 API 地址）：

```bash
cd web-admin
VITE_API_BASE_URL=https://api.example.com npm run build
```

## 前端技术栈

- React 19
- TypeScript 5
- Vite 7
- Tailwind CSS 3
- shadcn/ui 风格基础组件（本地维护）

前端仍然只负责管理界面，不改后端 API 协议：

- `GET /api/dashboard`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/users`
- `POST /api/users`
- `PATCH /api/users/{id}/permissions`
- `DELETE /api/users/{id}`
- `POST/PATCH/DELETE /api/targets`
- `POST/PATCH/DELETE /api/notify-groups`
- `PUT /api/poll`
- `PUT /api/proxy`

`targets / notify-groups / poll / proxy / users` 写操作会写入 `audit_logs`。

## 服务端 Docker

直接使用样板：

```bash
docker compose -f docker-compose.server.yml up -d --build
```

这会启动两个服务：

- `monitor`
- `admin-api`

挂载约定：

- 宿主机 `config.json` -> 容器 `/app/config.json`
- 宿主机 `data/` -> 容器 `/app/data`

## 推送分组规则

- 每个套餐有自己的 `group_key`
- 有货提醒、异常提醒都会按该套餐的 `group_key` 选择飞书 webhook
- 如果套餐没配 `group_key`，就回落到 `notify.default_group_key`
- 如果分组没配置 webhook，再回落到旧的 `notify.feishu_webhook`

## 代理池入口

代理池配置已经预留：

- `proxy.enabled`
- `proxy.provider`
- `proxy.request_method`
- `proxy.api_url`
- `proxy.api_key`
- `proxy.api_key_header`
- `proxy.extra_headers`
- `proxy.query_params`
- `proxy.request_body`
- `proxy.response_data_path`
- `proxy.response_fields`
- `proxy.cache_seconds`
- `proxy.timeout_seconds`
- `proxy.sticky_mode`
- `proxy.verify_ssl`

当前实现是 `generic_json` provider：

- 可直接读取 `proxy_url`
- 或根据 `scheme/host/port/username/password` 组装代理地址
- 字段名支持通过 `response_fields` 自定义

## 注意事项

- `fooddealdetail?id=...` 这类链接匿名请求通常拿不到库存字段
- 最稳定的输入仍然是带 `activityid` 的分享页
- 前端是管理台，不负责跑定时任务；真正的轮询还是服务器上的 `monitor.py`
- 如果已经用 Docker 常驻跑 `monitor.py`，不要再额外给 OpenClaw 配一个重复的 cron 监控任务

## 不影响生产监控的灰度部署步骤

1. 保持现网 `monitor.py` 容器和配置不变，不停机。
2. 启动一套新的 `admin_api.py`（灰度端口，例如 `8788`），指向同一份 `config.json` 与 `sqlite_path`。
   示例：
   ```bash
   python3 admin_api.py --config config.json --host 127.0.0.1 --port 8788
   ```
3. 先在灰度端口验证登录、权限控制、用户管理和审计日志。
4. 前端先切到灰度 API 地址验证，通过后再切回正式端口或替换网关路由。
5. 全程不重启 `monitor.py`，生产轮询与告警行为不会受影响。
