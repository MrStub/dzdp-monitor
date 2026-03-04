---
name: dzdp-monitor-openclaw
description: Monitor Dianping package stock from activityid links using monitor.py, including one-shot checks, continuous polling, and Feishu/email notification tests. Use when users ask to query stock status now, monitor multiple packages, debug webhook/email delivery, or operate the monitor service.
metadata: {"openclaw":{"requires":{"bins":["python3"]}}}
---

# Dianping Stock Monitor Skill (OpenClaw)

Use this skill to operate the local Dianping monitor in this repository, including conversational CRUD management of monitor targets.

## Operate

- Run one-shot stock check:
  - `scripts/run_monitor.sh once`
- Start continuous monitoring (default 60s interval from `config.json`):
  - `scripts/run_monitor.sh start`
- Test email channel only:
  - `scripts/run_monitor.sh test-email`

## Manage targets (CRUD)

Use `scripts/run_monitor.sh targets ...` to manage `config.json -> targets`.

- List targets:
  - `scripts/run_monitor.sh targets list`
- Read one target:
  - `scripts/run_monitor.sh targets get --activity-id 1682152928`
- Add target:
  - `scripts/run_monitor.sh targets add --name "春意寻味双人餐" --url "https://m.dianping.com/app/femember-groupbuyinter-static/main.html?activityid=1682152928"`
- Update target:
  - `scripts/run_monitor.sh targets update --activity-id 1682152928 --name "春意寻味双人餐(东湖)"`
  - `scripts/run_monitor.sh targets update --activity-id 1682152928 --url "https://...activityid=1682152928&shareid=..."`
- Delete target:
  - `scripts/run_monitor.sh targets remove --activity-id 1682152928`

Use `--json` on any target command to return machine-readable output.

## Conversation mapping

- If user says "查看监控列表 / 列出套餐":
  - Run `scripts/run_monitor.sh targets list --json`
- If user says "新增监控":
  - Run `scripts/run_monitor.sh targets add --name "<name>" --url "<url>" --json`
- If user says "修改监控":
  - Run `scripts/run_monitor.sh targets update --activity-id "<old_id>" --name "<new_name>" --url "<new_url>" --json`
- If user says "删除监控":
  - Run `scripts/run_monitor.sh targets remove --activity-id "<id>" --json`
- After any add/update/remove:
  - Run `scripts/run_monitor.sh targets list --json` and show latest list back to user

## Configure

- Edit `config.json` before running:
  - `targets`: managed by CRUD commands above
  - `notify.feishu_webhook`: fill Feishu webhook
  - `notify.email`: fill SMTP config if email is needed

## Return format (recommended)

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
