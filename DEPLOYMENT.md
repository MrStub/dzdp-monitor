# 服务器 Docker 部署流程

这套监控的职责边界是：

- Docker 容器负责持续轮询库存并推送飞书/邮件
- OpenClaw skill 负责增删改查 `config.json -> targets`
- 监控进程每一轮都会重新加载 `config.json`
- 因此 skill 改完监控列表后，不需要重启容器，下一轮自动生效

## 1. 服务器目录约定

建议在服务器固定一个工作目录，例如 `/srv/dzdp-monitor`：

```text
/srv/dzdp-monitor/
  monitor.py
  requirements.txt
  config.json
  config.example.json
  data/
  skills/
```

要求：

- `config.json` 必须在宿主机上可读写，因为 skill 会直接修改它
- `data/` 必须持久化，因为 SQLite 状态库会写在这里
- 不要把真实 `config.json` 烘焙进镜像，避免 webhook/SMTP 信息进入镜像层

## 2. 宿主机准备

1. 将仓库拉到服务器目录
2. 准备 `config.json`
3. 填好以下关键项：
   - `notify.feishu_webhook`
   - `poll.interval_seconds`
   - `targets`
4. 确保 `data/` 目录存在

建议：

- `config.json` 用宿主机文件保存
- skill 和容器都使用同一份宿主机 `config.json`
- 链接统一使用 `activityid` 形式，`shareid` 会在 skill 写入时自动去掉

## 3. Docker 镜像约束

OpenClaw 在部署时实现镜像和容器即可，镜像只需要满足：

- 基础运行时：`python3`
- 安装 `requirements.txt`
- 工作目录固定为容器内应用目录，例如 `/app`
- 默认启动命令：

```bash
python3 monitor.py --config /app/config.json
```

## 4. 容器挂载要求

这是部署是否可用的关键点。

必须挂载：

- 宿主机 `config.json` -> 容器 `/app/config.json`
- 宿主机 `data/` -> 容器 `/app/data`

推荐：

- `config.json` 挂只读也可以，因为容器只读取，skill 在宿主机修改
- `data/` 必须可写
- 容器使用 `restart: unless-stopped` 或等价策略

推荐的运行效果是：

- skill 在宿主机执行 `targets add/remove/list`
- skill 修改宿主机 `config.json`
- 容器下一轮轮询自动重新加载这份配置
- 新增/删除套餐即时生效，无需重启容器

## 5. 推荐部署顺序

1. 在服务器拉代码到 `/srv/dzdp-monitor`
2. 复制 `config.example.json` 为 `config.json`
3. 写入飞书 webhook 和初始监控列表
4. 创建 `data/` 目录
5. 让 OpenClaw 构建镜像
6. 让 OpenClaw 以挂载 `config.json` 和 `data/` 的方式启动容器
7. 先做一次单次检查，确认接口可访问
8. 再切到常驻运行

## 6. 部署后如何管理监控列表

容器启动后，监控列表不要在容器里改，统一通过宿主机 skill 改。

常用命令：

```bash
# 查看当前监控列表
/srv/dzdp-monitor/skills/dzdp-monitor-openclaw/scripts/run_monitor.sh targets --config /srv/dzdp-monitor/config.json list --json

# 添加套餐（自动去掉 shareid）
/srv/dzdp-monitor/skills/dzdp-monitor-openclaw/scripts/run_monitor.sh targets --config /srv/dzdp-monitor/config.json add --name "套餐名" --url "https://m.dianping.com/app/femember-groupbuyinter-static/main.html?activityid=123&shareid=abc" --json

# 按序号删除
/srv/dzdp-monitor/skills/dzdp-monitor-openclaw/scripts/run_monitor.sh targets --config /srv/dzdp-monitor/config.json remove --index 1 --json

# 按名称删除
/srv/dzdp-monitor/skills/dzdp-monitor-openclaw/scripts/run_monitor.sh targets --config /srv/dzdp-monitor/config.json remove --name "套餐名" --json

# 查看当前轮询时间
/srv/dzdp-monitor/skills/dzdp-monitor-openclaw/scripts/run_monitor.sh poll --config /srv/dzdp-monitor/config.json get --json

# 修改轮询时间
/srv/dzdp-monitor/skills/dzdp-monitor-openclaw/scripts/run_monitor.sh poll --config /srv/dzdp-monitor/config.json set --seconds 30 --json
```

说明：

- skill 的写配置动作是原子替换，不会写出半截 JSON
- 监控进程每轮重载配置，所以 skill 修改后通常在下一个轮询周期生效
- `list` 返回的 `index` 就是删除时可用的序号

## 7. 推送规则

当前规则已经固定为：

- 只有检测到 `IN_STOCK` 才推飞书
- 飞书内容只包含：
  - 套餐名
  - 清洗后的链接
  - 检测时间
- `SOLD_OUT` 不推送，继续监控
- `alerts.notify_failures=true` 时：
  - 同一监控项的相同报错在当天连续出现满 `5` 次才提醒
  - 同一报错当天只提醒一次
  - 第二天重新计数，满 `5` 次后可再次提醒

## 8. 需要重启容器的场景

以下情况才需要重启容器：

- 代码变更，例如 `monitor.py` 或依赖更新
- 镜像重建
- Python 运行时变更
- 容器启动命令或挂载路径变更

以下情况不需要重启容器：

- 新增监控套餐
- 删除监控套餐
- 修改套餐名称
- 修改 `notify.feishu_webhook`
- 修改轮询间隔

这些都会在下一轮自动生效。

## 9. 排障顺序

1. 看容器日志，确认有 `Reloaded X targets from config`
2. 看宿主机 `config.json` 是否已被 skill 正确修改
3. 看容器是否挂载了宿主机同一份 `config.json`
4. 看 `data/` 是否持久化
5. 看飞书 webhook 是否可用

如果出现“skill 改了列表，但容器没生效”，优先检查：

- 改的是否是宿主机真实挂载进去的那份 `config.json`
- 容器日志里是否出现新的 `Reloaded ... targets from config`

## 10. OpenClaw 的实现边界

OpenClaw 在服务器上需要做的事只有两类：

- 部署容器
- 调用 skill 管理 `config.json`

不建议让 OpenClaw：

- 在容器内手工编辑配置
- 把监控目标写进镜像
- 用临时文件替代宿主机 `config.json`

正确做法始终是：

- skill 改宿主机 `config.json`
- 容器读取宿主机 `config.json`
- 下一轮自动热更新
