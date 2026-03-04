# 大众点评套餐库存监控（多链接）

支持：
- 多个 `activityid` 链接同时监控
- 默认每 60 秒轮询
- 仅在状态变化时告警（默认只告警“有货”）
- 飞书机器人 / 邮件通知
- SQLite 持久化状态，避免重复提醒

## 1. 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. 配置

```bash
cp config.example.json config.json
```

编辑 `config.json`：
- `targets`: 填你的监控链接列表（推荐 `...activityid=xxxx` 这类）
- `notify.feishu_webhook`: 填飞书机器人 webhook（可选）
- `notify.email`: 填 SMTP（可选）

## 3. 运行

单次检查（调试）：

```bash
python3 monitor.py --config config.json --once
```

仅测试邮件通道：

```bash
python3 monitor.py --config config.json --test-email
```

持续监控：

```bash
python3 monitor.py --config config.json
```

## 4. 说明

- `fooddealdetail?id=...` 这类链接通常需要登录态，匿名请求可能拿不到库存字段。
- 监控最稳定的输入是：`https://m.dianping.com/app/femember-groupbuyinter-static/main.html?activityid=xxxx`
