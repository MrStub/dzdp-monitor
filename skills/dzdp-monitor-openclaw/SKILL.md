---
name: dzdp-monitor-openclaw
description: Monitor Dianping package stock from activityid links using monitor.py, including one-shot checks, continuous polling, target CRUD, Feishu group routing, admin API startup, and server Docker deployment guidance for OpenClaw.
metadata: {"openclaw":{"requires":{"bins":["python3"]}}}
---

# Dianping Stock Monitor Skill (OpenClaw)

Use this skill to operate the local Dianping monitor in this repository, including conversational CRUD management of monitor targets and Feishu routing groups.

If the user asks to install this skill, deploy the monitor to a server, or prepare Docker deployment handoff for OpenClaw, read [references/server-docker-deploy.md](references/server-docker-deploy.md) and follow that workflow.
If the user asks what commands are available, asks for help, or asks how to use the skill, read [references/command-catalog.md](references/command-catalog.md) and answer with the grouped command list.
If the user asks in Chinese what commands are available, asks for Chinese help, or asks how to instruct OpenClaw in Chinese, read [references/command-catalog-zh.md](references/command-catalog-zh.md) and answer in Chinese.

Target URLs should be normalized before storing:
- Keep `activityid`
- Remove `shareid`
- Store the cleaned URL back into `config.json`

## Operate

- Run one-shot stock check:
  - `scripts/run_monitor.sh once`
- Start continuous monitoring:
  - `scripts/run_monitor.sh start`
- Start admin API for the Cloudflare frontend:
  - `scripts/run_monitor.sh admin-api`
- Test email channel only:
  - `scripts/run_monitor.sh test-email`

## Manage poll interval

Use `scripts/run_monitor.sh poll ...` to read or update `config.json -> poll.interval_seconds`.

## Manage targets

Use `scripts/run_monitor.sh targets ...` to manage `config.json -> targets`.

Supported selectors:
- `index`
- `name`
- `url`
- `activity_id`

Add/update can also set `group_key` so each target routes notifications to the correct Feishu webhook group.

## Manage Feishu groups

Use `scripts/run_monitor.sh groups ...` to manage `config.json -> notify.feishu_groups`.

Supported operations:
- `groups list`
- `groups add`
- `groups update`
- `groups remove`

When the user changes a target's `group_key`, the running monitor reloads it automatically on the next polling cycle.

## Conversation mapping

- If user says `查看监控列表 / 列出套餐`:
  - Run `scripts/run_monitor.sh targets list --json`
- If user says `新增监控` and gives `套餐名，链接` or `套餐名，链接，分组key`:
  - Run `scripts/run_monitor.sh targets add --name "<name>" --url "<url>" --group-key "<group_key>" --json`
- If user says `修改监控分组`:
  - Prefer `index` selector and run `scripts/run_monitor.sh targets update --index "<n>" --set-group-key "<group_key>" --json`
- If user says `查看推送分组 / 添加推送分组 / 修改推送分组 / 删除推送分组`:
  - Map to `scripts/run_monitor.sh groups ...`
- If user says `查看轮询时间 / 当前刷新频率`:
  - Run `scripts/run_monitor.sh poll get --json`
- If user says `修改轮询时间 / 修改刷新频率`:
  - Run `scripts/run_monitor.sh poll set --seconds "<n>" --json`
- If user says `启动管理 API`:
  - Run `scripts/run_monitor.sh admin-api`
- After any add/update/remove:
  - Run the matching `list` command and show latest state back to the user

## Deploy

Deployment contract is now:
- `monitor.py` runs in Docker on the user's own server
- `admin_api.py` runs in Docker on the user's own server
- `web-admin/` is deployed to Cloudflare Pages
- host `config.json` and host `data/` are the source of truth
- target CRUD / group CRUD / poll changes hot reload into the running monitor

## Notes

- `flow/api/trigger-webhook/...` is a Feishu Flow webhook, not a group-bot webhook.
- For direct group message delivery, prefer `https://open.feishu.cn/open-apis/bot/v2/hook/...`
- Stock notifications are sent only when state becomes `IN_STOCK`.
- Feishu notification routing is based on `targets[].group_key`.
