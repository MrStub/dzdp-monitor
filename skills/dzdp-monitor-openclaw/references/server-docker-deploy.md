# Server Docker Deploy

Use this reference when the user asks to install this skill, deploy the monitor to a server, or prepare an OpenClaw deployment handoff.

## Goal

Ensure one of these outcomes:

1. OpenClaw deploys the monitor into server Docker directly.
2. If direct deployment is blocked, OpenClaw guides the user with the minimum missing inputs and the exact next steps.

Do not stop at "here is a general idea". Either deploy, or clearly state what is missing and how the user should provide it.

## Deployment Contract

The deployment shape is fixed:

- The monitor runs as a long-lived Docker container.
- The container starts with:
  - `python3 monitor.py --config /app/config.json`
- Host files are the source of truth:
  - host `config.json` -> container `/app/config.json`
  - host `data/` -> container `/app/data`
- Skill CRUD commands modify the host `config.json`, not files inside the container.
- The monitor process reloads `config.json` every polling cycle, so add/remove/update target changes do not require a container restart.

## Defaults

If the user does not specify these and there is no conflicting local context, assume:

- server app path: `/srv/dzdp-monitor`
- container workdir: `/app`
- container name: `dzdp-monitor`
- image name: `dzdp-monitor:latest`
- config path on host: `/srv/dzdp-monitor/config.json`
- data path on host: `/srv/dzdp-monitor/data`

## Preconditions

Direct deployment is possible only if the current environment gives access to:

- the server filesystem or repo checkout
- Docker or Docker Compose
- a writable host path for `config.json` and `data/`

If any of these are missing, switch to guided mode and ask only the minimum blocking questions.

## Direct Deployment Workflow

1. Confirm or assume the host path.
2. Ensure the project files exist on the server host path.
3. Ensure `config.json` exists and contains:
   - `notify.feishu_webhook`
   - `poll.interval_seconds`
   - `targets`
4. Ensure host `data/` exists.
5. Create or update Docker artifacts if they do not exist yet.
6. Start the container with host-mounted `config.json` and `data/`.
7. Verify:
   - container is running
   - logs show the monitor started
   - logs show target loading or reloading
8. Tell the user how future target management works through the skill.

## Guided Mode

If direct deployment cannot be completed, ask only what is blocking:

- Which server path should hold the project? Default: `/srv/dzdp-monitor`
- Is Docker already installed on the server?
- Do you want OpenClaw to create `config.json` from `config.example.json`?
- Do you already have the Feishu webhook and initial target list?

Do not ask broad architecture questions unless they are strictly necessary.

## Required Docker Shape

Use this as the expected runtime contract even if OpenClaw generates the actual files itself.

### Dockerfile template

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY monitor.py /app/monitor.py

CMD ["python3", "monitor.py", "--config", "/app/config.json"]
```

### Compose template

```yaml
services:
  dzdp-monitor:
    image: dzdp-monitor:latest
    container_name: dzdp-monitor
    restart: unless-stopped
    working_dir: /app
    command: ["python3", "monitor.py", "--config", "/app/config.json"]
    volumes:
      - /srv/dzdp-monitor/config.json:/app/config.json:ro
      - /srv/dzdp-monitor/data:/app/data
```

If OpenClaw prefers `docker run` instead of Compose, keep the same mount contract.

## Install-Time Command Template

Use this template when the user asks to "install this skill and make it deployable" or equivalent.

```text
任务：安装并启用 dzdp-monitor-openclaw skill；如果服务器环境可操作，则直接把监控部署到 Docker；如果缺少前提，则只问最少的阻塞信息并引导用户补齐。

执行要求：
1. 技能安装后，默认使用服务器宿主机上的 config.json 作为唯一配置源。
2. 容器必须挂载：
   - <host_app_path>/config.json -> /app/config.json
   - <host_app_path>/data -> /app/data
3. 容器启动命令固定为：
   - python3 monitor.py --config /app/config.json
4. 不要把真实 config.json 烘焙进镜像。
5. 不要在容器内手工编辑 config.json。
6. 部署完成后必须验证：
   - 容器运行中
   - 日志能看到监控启动
   - 后续通过 skill 增删套餐时，无需重启容器

交付结果：
1. 如果部署成功，输出：
   - 宿主机路径
   - 容器名 / 镜像名
   - 挂载路径
   - 验证结果
   - 后续使用的 add/list/remove 命令
2. 如果无法直接部署，输出：
   - 当前缺少的最小信息
   - 用户下一步需要提供的内容
   - 部署将在拿到这些信息后如何继续
```

## Post-Deploy Validation

Deployment is not complete until these checks pass:

1. `docker ps` shows the monitor container is running.
2. Container logs show monitor startup.
3. Container logs show target loading or reloading.
4. Host `config.json` changes made by the skill are picked up on the next polling cycle.

If possible, prove hot reload by:

1. start the monitor
2. add a temporary target through the skill
3. confirm logs show `Reloaded X targets from config`
4. remove the temporary target

## User-Facing Result Format

When reporting deployment status, keep it structured:

- `status`: deployed / blocked
- `host_path`
- `container_name`
- `config_mount`
- `data_mount`
- `verification`
- `next_step`

## Guardrails

- Prefer `activityid` links for targets.
- Normalize target URLs by removing `shareid`.
- Do not claim deployment succeeded until verification is done.
- Do not tell the user to restart the container after target CRUD changes; this system hot reloads configuration.
