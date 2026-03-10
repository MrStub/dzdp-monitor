# 部署流程

目标架构：

- `Cloudflare Pages`：托管前端 [web-admin/](/Users/daizhenghao/Documents/workspace/TraeSpace/dzdp-monitor/web-admin)
- `你自己的服务器`：运行 `monitor.py` 和 `admin_api.py`
- `OpenClaw skill`：继续负责命令式增删改查和辅助部署，不承担轮询调度

## 一、职责边界

### 1. 监控进程

- 进程：`python3 monitor.py --config /app/config.json`
- 职责：轮询库存、写 SQLite 状态、发飞书/邮件
- 特点：每轮都会重新加载 `config.json`

### 2. 管理 API

- 进程：`python3 admin_api.py --config /app/config.json`
- 职责：为前端提供套餐 CRUD、飞书分组 CRUD、轮询配置、代理配置
- 特点：直接读写同一份 `config.json`

### 3. 前端

- 项目：`web-admin/`
- 技术：Vue 2 + vue-cli
- 部署：Cloudflare Pages
- 职责：人机交互，不直接负责监控调度

## 二、服务器目录

建议固定在 `/srv/dzdp-monitor`：

```text
/srv/dzdp-monitor/
  monitor.py
  admin_api.py
  proxy_provider.py
  app_config.py
  requirements.txt
  Dockerfile
  docker-compose.server.yml
  config.json
  data/
  skills/
```

关键要求：

- `config.json` 必须保存在宿主机，不能写死进镜像
- `data/` 必须持久化
- `monitor` 和 `admin-api` 必须挂载同一份 `config.json`

## 三、服务端部署

### 1. 拉代码

```bash
git clone https://github.com/MrStub/dzdp-monitor.git /srv/dzdp-monitor
cd /srv/dzdp-monitor
```

### 2. 准备配置

```bash
cp config.example.json config.json
mkdir -p data
```

至少填这些：

- `notify.feishu_groups`
- `notify.default_group_key`
- `targets`
- `admin_api.cors_allowed_origins`
- `admin_api.auth_token`

建议：

- `admin_api.cors_allowed_origins` 精确写你的 Cloudflare Pages 域名
- `admin_api.auth_token` 使用长随机串

### 3. Docker 启动

```bash
docker compose -f docker-compose.server.yml up -d --build
```

Compose 已经定义了两个服务：

- `monitor`
- `admin-api`

如果你不用 compose，也要保证这两个进程都跑起来。

### 4. 验证服务端

```bash
curl http://127.0.0.1:8787/api/health
curl -H "Authorization: Bearer 你的token" http://127.0.0.1:8787/api/dashboard
```

## 四、Cloudflare Pages 部署

前端目录固定为：`web-admin/`

### 1. Pages 项目参数

- Root directory：`web-admin`
- Build command：`npm run build`
- Build output directory：`dist`
- Framework preset：`None`

### 2. 环境变量

设置：

- `VUE_APP_API_BASE_URL=https://你的服务端域名`

说明：

- 前端会优先读取浏览器 localStorage 里的 API 地址
- 如果用户没改，才用 `VUE_APP_API_BASE_URL`

### 3. 前端接入鉴权

管理 API 如果配置了 `admin_api.auth_token`：

- 页面连接区要填 Bearer Token
- Token 只存浏览器 localStorage
- 不要把 token 写进 Cloudflare Pages 的公开环境变量给所有人共用，除非这个站本身只对你可见

更稳妥的做法：

- 给 Pages 再套一层 Cloudflare Access
- 或者把 API 域名限制在内网/零信任网络

## 五、热更新规则

这套结构的关键点是“配置热更新”：

- 网页新增套餐 -> 写宿主机 `config.json`
- Skill 新增套餐 -> 写宿主机 `config.json`
- 管理 API 改轮询时间 -> 写宿主机 `config.json`
- 管理 API 改飞书分组 -> 写宿主机 `config.json`
- `monitor.py` 下一轮自动读取新配置

所以：

- 套餐增删改，不需要重启 `monitor`
- 轮询间隔修改，不需要重启 `monitor`
- 飞书分组和 webhook 修改，不需要重启 `monitor`
- 代理参数修改，不需要重启 `monitor`

只有这些场景需要重启：

- Python 代码变更
- Docker 镜像重建
- 依赖升级
- 容器挂载路径变更

## 六、前端支持的功能

页面里已经支持：

- 添加套餐
- 编辑套餐名、链接、推送分组
- 删除套餐
- 查看最新库存状态 / 错误状态 / 最近变更时间
- 添加飞书分组
- 编辑飞书 webhook
- 设置默认分组
- 删除飞书分组
- 修改轮询时间
- 修改代理池参数
- 配置 API 地址和 Bearer Token

## 七、飞书分组路由

配置结构：

```json
{
  "notify": {
    "default_group_key": "default",
    "feishu_groups": [
      {
        "key": "default",
        "name": "默认分组",
        "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/..."
      },
      {
        "key": "wuhan",
        "name": "武汉群",
        "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/..."
      }
    ]
  },
  "targets": [
    {
      "name": "春意寻味双人餐",
      "url": "https://m.dianping.com/app/femember-groupbuyinter-static/main.html?activityid=1682152928",
      "group_key": "wuhan"
    }
  ]
}
```

路由逻辑：

1. 优先用套餐自己的 `group_key`
2. 找不到时回落到 `notify.default_group_key`
3. 再找不到时回落到旧的 `notify.feishu_webhook`

## 八、代理池接入

现在已经预留了 provider 入口，不需要改监控主循环，只需要补配置：

```json
{
  "proxy": {
    "enabled": true,
    "provider": "generic_json",
    "request_method": "GET",
    "api_url": "https://proxy-provider.example.com/get",
    "api_key": "your-api-key",
    "api_key_header": "X-API-Key",
    "extra_headers": {},
    "query_params": {},
    "request_body": {},
    "response_data_path": "data",
    "response_fields": {
      "proxy_url": "proxy"
    },
    "cache_seconds": 120,
    "timeout_seconds": 8,
    "sticky_mode": "per_target",
    "verify_ssl": true
  }
}
```

`generic_json` provider 支持两种返回：

### 1. 直接给完整代理地址

```json
{
  "data": {
    "proxy": "http://user:pass@1.2.3.4:8000"
  }
}
```

配：

```json
"response_data_path": "data",
"response_fields": {
  "proxy_url": "proxy"
}
```

### 2. 拆字段返回

```json
{
  "data": {
    "scheme": "http",
    "host": "1.2.3.4",
    "port": 8000,
    "username": "user",
    "password": "pass"
  }
}
```

## 九、OpenClaw 的正确使用方式

OpenClaw 在这套架构里主要做两类事：

- 调用 skill 改配置
- 协助部署服务器容器

不应该让 OpenClaw：

- 自己再跑一套定时库存检查 cron
- 在容器内手工改配置
- 把 `config.json` 烘焙进镜像

正确模式：

- `monitor` 常驻
- `admin-api` 常驻
- `web-admin` 走 Cloudflare Pages
- Skill / 网页都改宿主机 `config.json`
- `monitor` 下一轮热更新生效

## 十、排障顺序

### 1. 页面打不开数据

检查：

- `admin-api` 是否在跑
- `admin_api.cors_allowed_origins` 是否包含你的前端域名
- Bearer Token 是否正确
- 浏览器控制台是否报 CORS / 401

### 2. 页面改了配置，但监控没生效

检查：

- 改的是不是宿主机真实 `config.json`
- `monitor` 是否挂载了同一份 `config.json`
- `monitor` 日志里有没有下一轮的 `Reloaded ... targets from config`

### 3. 飞书没收到消息

检查：

- 套餐的 `group_key` 是否正确
- 该分组 webhook 是否已配置
- 是否误用了 Flow webhook 而不是群机器人 webhook
- 群机器人是否有关键词/签名/IP 白名单限制

### 4. 代理池开启后报错

检查：

- `proxy.api_url` 是否可访问
- `response_data_path` 是否指到正确层级
- `response_fields` 是否和 provider 返回字段匹配
- `monitor` 日志里是否出现 `proxy resolve error`
