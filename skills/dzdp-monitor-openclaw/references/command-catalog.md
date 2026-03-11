# Command Catalog

Use this reference when the user asks:

- 有哪些命令
- 帮助
- help
- 怎么用这个监控
- 如何添加 / 删除 / 查看套餐
- 如何修改轮询时间
- 如何管理飞书分组
- 如何启动管理 API

## Command groups

### 1. Runtime

- One-shot check:
  - `scripts/run_monitor.sh once`
- Start continuous monitor:
  - `scripts/run_monitor.sh start`
- Start admin API:
  - `scripts/run_monitor.sh admin-api`
- Test email only:
  - `scripts/run_monitor.sh test-email`

### 2. Target CRUD

- List targets:
  - `scripts/run_monitor.sh targets list --json`
- Add target:
  - `scripts/run_monitor.sh targets add --name "<套餐名>" --url "<链接>" --group-key "<group_key>" --json`
- Get one target:
  - `scripts/run_monitor.sh targets get --index <序号> --json`
  - `scripts/run_monitor.sh targets get --name "<套餐名>" --json`
  - `scripts/run_monitor.sh targets get --url "<链接>" --json`
  - `scripts/run_monitor.sh targets get --activity-id <activityid> --json`
- Update one target:
  - `scripts/run_monitor.sh targets update --index <序号> --set-name "<新套餐名>" --json`
  - `scripts/run_monitor.sh targets update --index <序号> --set-url "<新链接>" --json`
  - `scripts/run_monitor.sh targets update --index <序号> --set-group-key "<group_key>" --json`
- Remove one target:
  - `scripts/run_monitor.sh targets remove --index <序号> --json`
  - `scripts/run_monitor.sh targets remove --name "<套餐名>" --json`
  - `scripts/run_monitor.sh targets remove --url "<链接>" --json`
  - `scripts/run_monitor.sh targets remove --activity-id <activityid> --json`

### 3. Notify groups

- List groups:
  - `scripts/run_monitor.sh groups list --json`
- Add group:
  - `scripts/run_monitor.sh groups add --name "<分组名>" --webhook "<webhook>" --key "<group_key>" --json`
- Update group:
  - `scripts/run_monitor.sh groups update --key "<group_key>" --set-name "<新分组名>" --json`
  - `scripts/run_monitor.sh groups update --key "<group_key>" --set-webhook "<webhook>" --json`
  - `scripts/run_monitor.sh groups update --key "<group_key>" --make-default --json`
- Remove group:
  - `scripts/run_monitor.sh groups remove --key "<group_key>" --json`

### 4. Poll interval

- Read current interval:
  - `scripts/run_monitor.sh poll get --json`
- Update interval:
  - `scripts/run_monitor.sh poll set --seconds <秒数> --json`

Guardrails:

- minimum interval is `5` seconds
- target links are normalized by removing `shareid`
- target/group/poll changes hot reload into the running monitor
- Docker deployment does not require a restart after config CRUD

## Conversation mapping

When the user speaks naturally, map to commands like this:

- `查看监控列表`
  - `scripts/run_monitor.sh targets list --json`
- `添加监控：套餐名，链接，分组key`
  - `scripts/run_monitor.sh targets add --name "<套餐名>" --url "<链接>" --group-key "<group_key>" --json`
- `删除监控：1`
  - `scripts/run_monitor.sh targets remove --index 1 --json`
- `查看推送分组`
  - `scripts/run_monitor.sh groups list --json`
- `添加推送分组：武汉群，webhook`
  - `scripts/run_monitor.sh groups add --name "武汉群" --webhook "<webhook>" --json`
- `修改监控分组：1，wuhan`
  - `scripts/run_monitor.sh targets update --index 1 --set-group-key "wuhan" --json`
- `查看轮询时间`
  - `scripts/run_monitor.sh poll get --json`
- `修改轮询时间：30秒`
  - `scripts/run_monitor.sh poll set --seconds 30 --json`
- `启动管理 API`
  - `scripts/run_monitor.sh admin-api`

## Return format

When the user asks for available commands, answer with:

1. a short grouped command list
2. one natural-language example per group
3. a note that:
   - Cloudflare frontend talks to `admin_api.py`
   - the monitor service remains on the user's own server
   - no extra cron is needed if Docker is already running `monitor.py`
