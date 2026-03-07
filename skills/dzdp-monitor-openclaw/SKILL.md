---
name: dzdp-monitor-openclaw
description: Monitor Dianping package stock from activityid links using monitor.py, including one-shot checks, continuous polling, target CRUD, Feishu/email notification tests, and server Docker deployment guidance for OpenClaw.
metadata: {"openclaw":{"requires":{"bins":["python3"]}}}
---

# Dianping Stock Monitor Skill (OpenClaw)

Use this skill to operate the local Dianping monitor in this repository, including conversational CRUD management of monitor targets.

If the user asks to install this skill, deploy the monitor to a server, or prepare Docker deployment handoff for OpenClaw, read [references/server-docker-deploy.md](references/server-docker-deploy.md) and follow that workflow.
If the user asks what commands are available, asks for help, or asks how to use the skill, read [references/command-catalog.md](references/command-catalog.md) and answer with the grouped command list.

Target URLs should be normalized before storing:
- Keep `activityid`
- Remove `shareid`
- Store the cleaned URL back into `config.json`

## Operate

- Run one-shot stock check:
  - `scripts/run_monitor.sh once`
- Start continuous monitoring (default 60s interval from `config.json`):
  - `scripts/run_monitor.sh start`
- Test email channel only:
  - `scripts/run_monitor.sh test-email`

## Manage poll interval

Use `scripts/run_monitor.sh poll ...` to read or update `config.json -> poll.interval_seconds`.

- Read current poll interval:
  - `scripts/run_monitor.sh poll get`
- Update poll interval:
  - `scripts/run_monitor.sh poll set --seconds 60`

The running monitor service will reload the new interval on the next polling cycle.

## Manage targets (CRUD)

Use `scripts/run_monitor.sh targets ...` to manage `config.json -> targets`.

- List targets:
  - `scripts/run_monitor.sh targets list`
- Read one target:
  - `scripts/run_monitor.sh targets get --index 1`
  - `scripts/run_monitor.sh targets get --name "春意寻味双人餐"`
  - `scripts/run_monitor.sh targets get --url "https://m.dianping.com/app/femember-groupbuyinter-static/main.html?activityid=1682152928"`
  - `scripts/run_monitor.sh targets get --activity-id 1682152928`
- Add target:
  - `scripts/run_monitor.sh targets add --name "春意寻味双人餐" --url "https://m.dianping.com/app/femember-groupbuyinter-static/main.html?activityid=1682152928&shareid=xxx"`
- Update target:
  - `scripts/run_monitor.sh targets update --index 1 --set-name "春意寻味双人餐(东湖)"`
  - `scripts/run_monitor.sh targets update --activity-id 1682152928 --set-url "https://...activityid=1682152928&shareid=..."`
- Delete target:
  - `scripts/run_monitor.sh targets remove --index 1`
  - `scripts/run_monitor.sh targets remove --name "春意寻味双人餐"`
  - `scripts/run_monitor.sh targets remove --url "https://m.dianping.com/app/femember-groupbuyinter-static/main.html?activityid=1682152928"`
  - `scripts/run_monitor.sh targets remove --activity-id 1682152928`

Use `--json` on any target command to return machine-readable output.

## Conversation mapping

- If user says "有哪些命令 / 帮助 / help / 怎么用":
  - Read [references/command-catalog.md](references/command-catalog.md)
  - Answer with the grouped command list and one example per group
- If user says "查看监控列表 / 列出套餐":
  - Run `scripts/run_monitor.sh targets list --json`
- If user says "新增监控"，输入格式是 `套餐名，链接`:
  - Parse `name` and `url`
  - Run `scripts/run_monitor.sh targets add --name "<name>" --url "<url>" --json`
  - Stored URL must be the normalized URL with `shareid` removed
- If user says "修改监控":
  - Prefer selector priority: `index` -> `name` -> `url` -> `activity_id`
  - Run `scripts/run_monitor.sh targets update --index "<n>" --set-name "<new_name>" --set-url "<new_url>" --json`
- If user says "删除监控":
  - Accept `序号 / 套餐名 / 链接 / activity_id`
  - Run one of:
    - `scripts/run_monitor.sh targets remove --index "<n>" --json`
    - `scripts/run_monitor.sh targets remove --name "<name>" --json`
    - `scripts/run_monitor.sh targets remove --url "<url>" --json`
    - `scripts/run_monitor.sh targets remove --activity-id "<id>" --json`
- If user says "查看轮询时间 / 当前刷新频率":
  - Run `scripts/run_monitor.sh poll get --json`
- If user says "修改轮询时间 / 修改刷新频率":
  - Run `scripts/run_monitor.sh poll set --seconds "<n>" --json`
- After any add/update/remove:
  - Run `scripts/run_monitor.sh targets list --json` and show latest list back to user
  - The running monitor service will reload `config.json` on the next polling cycle; restart is not required
- After poll interval update:
  - Run `scripts/run_monitor.sh poll get --json` and show latest interval back to user

## Configure

- Edit `config.json` before running:
  - `targets`: managed by CRUD commands above
  - `notify.feishu_webhook`: fill Feishu webhook
  - `notify.email`: fill SMTP config if email is needed

## Deploy

- For first-run deployment or install-time deployment handoff:
  - Read [references/server-docker-deploy.md](references/server-docker-deploy.md)
- Default deployment contract:
  - monitor runs in Docker
  - host `config.json` is mounted into container
  - host `data/` is mounted into container
  - target CRUD continues to operate on host `config.json`
  - the monitor reloads `config.json` on the next polling cycle

## Return format (recommended)

- For target list, always include:
  - `index | activityid | name | url`
- For one-shot check, summarize each target in one line:
  - `activityid | title | soldOut | state(有货/售罄) | timestamp`
- For errors, include:
  - failing target/activityid
  - exact error message
  - whether notify channels are configured

## Notes

- `flow/api/trigger-webhook/...` is a Feishu Flow webhook, not group-bot webhook.
- For direct group message delivery, prefer:
  - `https://open.feishu.cn/open-apis/bot/v2/hook/...`
- Stock notifications should only be sent when state becomes `IN_STOCK`.
- Feishu in-stock notification should contain the package name and cleaned link.
