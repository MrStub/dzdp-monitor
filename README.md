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
- `admin_api.auth_token`：管理 API Bearer Token，建议启用
- `proxy.*`：代理池 provider 配置

说明：

- 旧的 `notify.feishu_webhook` 仍兼容
- 链接会自动去掉 `shareid`
- 推荐输入：`https://m.dianping.com/app/femember-groupbuyinter-static/main.html?activityid=xxxx`

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

默认监听：`0.0.0.0:8787`

### 5. 启动前端

```bash
cd web-admin
npm install
npm run dev
```

如果本地前端不是直接连 `http://127.0.0.1:8787`，可在浏览器里改 API 地址；页面会存到 localStorage。

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

## 前端技术栈

- React 19
- TypeScript 5
- Vite 7
- Tailwind CSS 3
- shadcn/ui 风格基础组件（本地维护）

前端仍然只负责管理界面，不改后端 API 协议：

- `GET /api/dashboard`
- `POST/PATCH/DELETE /api/targets`
- `POST/PATCH/DELETE /api/notify-groups`
- `PUT /api/poll`
- `PUT /api/proxy`

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
