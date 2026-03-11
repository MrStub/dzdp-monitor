# 中文指令清单

当用户用中文问这些问题时，读取这份文件并用中文回答：

- 有哪些命令
- 帮助
- 中文帮助
- 怎么用这个监控
- 我可以怎么指挥你
- 如何添加 / 删除 / 查看监控
- 如何修改轮询时间
- 如何管理飞书分组
- 如何启动管理 API

## 一、监控运行命令

- 单次检查库存：
  - `scripts/run_monitor.sh once`
- 启动持续监控：
  - `scripts/run_monitor.sh start`
- 启动管理 API：
  - `scripts/run_monitor.sh admin-api`
- 测试邮件通道：
  - `scripts/run_monitor.sh test-email`

## 二、监控套餐管理命令

- 查看监控列表：
  - `scripts/run_monitor.sh targets list --json`
- 添加监控套餐：
  - `scripts/run_monitor.sh targets add --name "<套餐名>" --url "<链接>" --group-key "<分组key>" --json`
- 查看单个监控项：
  - `scripts/run_monitor.sh targets get --index <序号> --json`
  - `scripts/run_monitor.sh targets get --name "<套餐名>" --json`
  - `scripts/run_monitor.sh targets get --url "<链接>" --json`
  - `scripts/run_monitor.sh targets get --activity-id <activityid> --json`
- 修改监控项：
  - `scripts/run_monitor.sh targets update --index <序号> --set-name "<新套餐名>" --json`
  - `scripts/run_monitor.sh targets update --index <序号> --set-url "<新链接>" --json`
  - `scripts/run_monitor.sh targets update --index <序号> --set-group-key "<分组key>" --json`
- 删除监控项：
  - `scripts/run_monitor.sh targets remove --index <序号> --json`
  - `scripts/run_monitor.sh targets remove --name "<套餐名>" --json`
  - `scripts/run_monitor.sh targets remove --url "<链接>" --json`
  - `scripts/run_monitor.sh targets remove --activity-id <activityid> --json`

## 三、飞书分组命令

- 查看推送分组：
  - `scripts/run_monitor.sh groups list --json`
- 添加推送分组：
  - `scripts/run_monitor.sh groups add --name "<分组名>" --webhook "<webhook>" --key "<分组key>" --json`
- 修改推送分组：
  - `scripts/run_monitor.sh groups update --key "<分组key>" --set-name "<新分组名>" --json`
  - `scripts/run_monitor.sh groups update --key "<分组key>" --set-webhook "<webhook>" --json`
  - `scripts/run_monitor.sh groups update --key "<分组key>" --make-default --json`
- 删除推送分组：
  - `scripts/run_monitor.sh groups remove --key "<分组key>" --json`

## 四、轮询时间命令

- 查看当前轮询时间：
  - `scripts/run_monitor.sh poll get --json`
- 修改轮询时间：
  - `scripts/run_monitor.sh poll set --seconds <秒数> --json`

约束：

- 最小轮询时间为 `5` 秒
- 链接会自动去掉 `shareid`
- 套餐、分组、轮询时间修改会热更新到运行中的监控进程

## 五、中文对话映射

当用户自然语言表达时，按下面方式映射：

- `查看监控列表`
  - `scripts/run_monitor.sh targets list --json`
- `添加监控：套餐名，链接，分组key`
  - `scripts/run_monitor.sh targets add --name "<套餐名>" --url "<链接>" --group-key "<分组key>" --json`
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
- `帮我看一下现在有货吗`
  - `scripts/run_monitor.sh once`

## 六、推荐给用户的中文版说明格式

当用户问“有哪些命令”时，回答结构固定为：

1. 先按分组列出命令
2. 每组给 1 个中文使用示例
3. 最后补 4 条规则：
   - 链接会自动去掉 `shareid`
   - 套餐、分组、轮询时间修改会热更新到运行中的监控进程
   - 前端部署到 Cloudflare，监控和 API 保留在用户自己的服务器
   - Docker 常驻监控时，不需要额外再配 OpenClaw 的 cron 监控任务
