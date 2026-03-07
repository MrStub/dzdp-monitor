# Command Catalog

Use this reference when the user asks:

- 有哪些命令
- 帮助
- help
- 怎么用这个监控
- 如何添加 / 删除 / 查看套餐
- 如何修改轮询时间

## Command groups

### 1. Monitor operations

- One-shot check:
  - `scripts/run_monitor.sh once`
- Start continuous monitor:
  - `scripts/run_monitor.sh start`
- Test email only:
  - `scripts/run_monitor.sh test-email`

### 2. Target CRUD

- List targets:
  - `scripts/run_monitor.sh targets list --json`
- Add target:
  - `scripts/run_monitor.sh targets add --name "<套餐名>" --url "<链接>" --json`
- Get one target:
  - `scripts/run_monitor.sh targets get --index <序号> --json`
  - `scripts/run_monitor.sh targets get --name "<套餐名>" --json`
  - `scripts/run_monitor.sh targets get --url "<链接>" --json`
  - `scripts/run_monitor.sh targets get --activity-id <activityid> --json`
- Update one target:
  - `scripts/run_monitor.sh targets update --index <序号> --set-name "<新套餐名>" --json`
  - `scripts/run_monitor.sh targets update --index <序号> --set-url "<新链接>" --json`
- Remove one target:
  - `scripts/run_monitor.sh targets remove --index <序号> --json`
  - `scripts/run_monitor.sh targets remove --name "<套餐名>" --json`
  - `scripts/run_monitor.sh targets remove --url "<链接>" --json`
  - `scripts/run_monitor.sh targets remove --activity-id <activityid> --json`

### 3. Poll interval

- Read current interval:
  - `scripts/run_monitor.sh poll get --json`
- Update interval:
  - `scripts/run_monitor.sh poll set --seconds <秒数> --json`

Guardrail:

- minimum interval is `5` seconds

## Conversation mapping

When the user speaks naturally, map to commands like this:

- `查看监控列表`
  - `scripts/run_monitor.sh targets list --json`
- `添加监控：套餐名，链接`
  - `scripts/run_monitor.sh targets add --name "<套餐名>" --url "<链接>" --json`
- `删除监控：1`
  - `scripts/run_monitor.sh targets remove --index 1 --json`
- `删除监控：春意寻味双人餐`
  - `scripts/run_monitor.sh targets remove --name "春意寻味双人餐" --json`
- `查看轮询时间`
  - `scripts/run_monitor.sh poll get --json`
- `修改轮询时间：30秒`
  - `scripts/run_monitor.sh poll set --seconds 30 --json`

## Return format

When the user asks for available commands, answer with:

1. a short grouped command list
2. one natural-language usage example per group
3. a note that:
   - target links will be normalized by removing `shareid`
   - target CRUD changes hot reload into the running monitor
   - Docker deployment does not require a restart after add/remove/update target or interval changes
