# Server Docker Deploy

Use this reference when the user asks to install this skill, deploy the monitor to a server, or prepare an OpenClaw deployment handoff.

## Goal

Ensure one of these outcomes:

1. OpenClaw deploys the server-side services into Docker directly.
2. If direct deployment is blocked, OpenClaw guides the user with the minimum missing inputs and the exact next steps.

Do not stop at "here is a general idea". Either deploy, or clearly state what is missing and how the user should provide it.

## Deployment Contract

The deployment shape is fixed:

- `monitor.py` runs as a long-lived Docker service.
- `admin_api.py` runs as a second long-lived Docker service.
- The frontend `web-admin/` is static and should be deployed to Cloudflare Pages, not bundled into the server container.
- Host files are the source of truth:
  - host `config.json` -> container `/app/config.json`
  - host `data/` -> container `/app/data`
- Skill CRUD commands modify the host `config.json`, not files inside the container.
- The monitor process reloads `config.json` every polling cycle, so target/group/poll/proxy changes do not require a container restart.

## Defaults

If the user does not specify these and there is no conflicting local context, assume:

- server app path: `/srv/dzdp-monitor`
- container workdir: `/app`
- monitor service name: `dzdp-monitor`
- admin-api service name: `dzdp-admin-api`
- image name: `dzdp-monitor:latest`
- config path on host: `/srv/dzdp-monitor/config.json`
- data path on host: `/srv/dzdp-monitor/data`
- admin API port: `8787`

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
   - `notify.feishu_groups`
   - `notify.default_group_key`
   - `targets`
   - `admin_api.cors_allowed_origins`
   - `admin_api.auth_token`
4. Ensure host `data/` exists.
5. Create or update Docker artifacts if they do not exist yet.
6. Start both `monitor` and `admin-api` with host-mounted `config.json` and `data/`.
7. Verify:
   - both containers are running
   - monitor logs show target loading or reloading
   - admin API health endpoint responds
8. Tell the user how Cloudflare Pages should connect to the admin API.

## Guided Mode

If direct deployment cannot be completed, ask only what is blocking:

- Which server path should hold the project? Default: `/srv/dzdp-monitor`
- Is Docker already installed on the server?
- Do you want OpenClaw to create `config.json` from `config.example.json`?
- Do you already have the Feishu webhook groups and initial target list?
- What Cloudflare Pages domain should be added to `admin_api.cors_allowed_origins`?

Do not ask broad architecture questions unless they are strictly necessary.

## Required Docker Shape

Use this as the expected runtime contract even if OpenClaw generates the actual files itself.

### Dockerfile template

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

CMD ["python3", "monitor.py", "--config", "/app/config.json"]
```

### Compose template

```yaml
services:
  monitor:
    image: dzdp-monitor:latest
    restart: unless-stopped
    command: ["python3", "monitor.py", "--config", "/app/config.json"]
    volumes:
      - /srv/dzdp-monitor/config.json:/app/config.json
      - /srv/dzdp-monitor/data:/app/data

  admin-api:
    image: dzdp-monitor:latest
    restart: unless-stopped
    command: ["python3", "admin_api.py", "--config", "/app/config.json"]
    ports:
      - "8787:8787"
    volumes:
      - /srv/dzdp-monitor/config.json:/app/config.json
      - /srv/dzdp-monitor/data:/app/data
```

If OpenClaw prefers `docker run` instead of Compose, keep the same mount contract.

## Cloudflare Pages Handoff

When the user asks for the frontend deployment instructions, give these exact parameters:

- project root: `web-admin`
- build command: `npm run build`
- output directory: `dist`
- env var: `VUE_APP_API_BASE_URL=https://<server-domain>`

Also tell the user:

- the frontend will prompt for or store the Bearer Token locally
- `admin_api.cors_allowed_origins` must include the Cloudflare Pages origin

## Install-Time Command Template

Use this template when the user asks to "install this skill and make it deployable" or equivalent.

```text
任务：安装并启用 dzdp-monitor-openclaw skill；如果服务器环境可操作，则直接把 monitor + admin-api 部署到 Docker；如果缺少前提，则只问最少的阻塞信息并引导用户补齐。前端部署目标固定为 Cloudflare Pages。

执行要求：
1. 技能安装后，默认使用服务器宿主机上的 config.json 作为唯一配置源。
2. 容器必须挂载：
   - <host_app_path>/config.json -> /app/config.json
   - <host_app_path>/data -> /app/data
3. monitor 启动命令固定为：
   - python3 monitor.py --config /app/config.json
4. admin-api 启动命令固定为：
   - python3 admin_api.py --config /app/config.json
5. 不要把真实 config.json 烘焙进镜像。
6. 不要在容器内手工编辑 config.json。
7. 部署完成后必须验证：
   - monitor 容器运行中
   - admin-api 容器运行中
   - admin-api /api/health 可访问
   - 后续通过 skill 增删套餐、修改分组、修改轮询时，无需重启 monitor

交付结果：
1. 如果部署成功，输出：
   - 宿主机路径
   - monitor / admin-api 容器名
   - 管理 API 地址
   - 挂载路径
   - 验证结果
   - Cloudflare Pages 需要填写的参数
2. 如果无法直接部署，输出：
   - 当前缺少的最小信息
   - 用户下一步需要提供的内容
   - 部署将在拿到这些信息后如何继续
```

## Post-Deploy Validation

Deployment is not complete until these checks pass:

1. `docker ps` shows both monitor and admin-api are running.
2. Monitor logs show startup and target loading.
3. `curl http://127.0.0.1:8787/api/health` succeeds.
4. A config change made by the skill is picked up on the next monitor polling cycle.

If possible, prove hot reload by:

1. start the services
2. add a temporary target through the skill
3. confirm logs show `Reloaded X targets from config`
4. remove the temporary target

## User-Facing Result Format

When reporting deployment status, keep it structured:

- `status`: deployed / blocked
- `host_path`
- `monitor_container`
- `admin_api_container`
- `config_mount`
- `data_mount`
- `admin_api_url`
- `verification`
- `cloudflare_pages_next_step`

## Guardrails

- Prefer `activityid` links for targets.
- Normalize target URLs by removing `shareid`.
- Do not claim deployment succeeded until verification is done.
- Do not tell the user to restart the monitor container after config CRUD changes; this system hot reloads configuration.
