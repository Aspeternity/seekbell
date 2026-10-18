# SeekBell

自托管的 NodeSeek 新帖监控与通知工具。范围与技术栈见 [SPEC](docs/SPEC.md) 和 [ARCHITECTURE](docs/ARCHITECTURE.md)。

当前为 **M0 工程基线**：可运行的 FastAPI / Vue 3 / Naive UI 骨架、SQLite 迁移、版本页和基础 CI。管理员、采集、规则与通知尚未实现，不能作为监控服务投入使用。当前进度和证据以 [PROJECT_STATE](docs/PROJECT_STATE.md) 为准。

## 环境

本机已确认使用独立WSL2发行版`SeekBell-Dev`，源码位于Linux文件系统的`/home/dev/projects/seekbell`。Windows终端执行`wsl.exe -d SeekBell-Dev --cd /home/dev/projects/seekbell`进入。原D盘目录保留为交接副本；具体配置、隔离边界和Docker维护命令见[开发环境](docs/DEVELOPMENT_ENVIRONMENT.md)。

服务运行于 Linux，Python 3.12、Node 24.22.0（`.node-version`）、uv 0.13.1、pnpm 10.34.7。精确依赖见 `uv.lock` 和 `frontend/pnpm-lock.yaml`。工具安装参考 [uv](https://docs.astral.sh/uv/getting-started/installation/)、[Node](https://nodejs.org/en/download)、[pnpm](https://pnpm.io/installation)。

WSL 请使用 Linux Node/pnpm，避免误用 Windows 的可执行文件。数据目录放在 Linux 本地文件系统，正式部署不能直接使用 `/mnt/c`、`/mnt/d`、NFS 或 SMB 数据卷。跨文件系统安装 uv 依赖时可设置 `UV_LINK_MODE=copy`。

## 安装与检查

在仓库根目录执行；以下命令不联系论坛或真实通知目标。

```bash
uv lock --check
uv sync --frozen
pnpm --dir frontend install --frozen-lockfile
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen pytest -q
uv build --wheel
pnpm --dir frontend format:check
pnpm --dir frontend build
```

Python 测试使用临时 SQLite 和进程内 HTTP 客户端，并拒绝测试进程的外网连接。CI 执行这些检查及迁移命令、镜像构建；没有发布、远程部署或真实发送步骤。远程 Actions 是否通过需在仓库配置后单独确认。

## 本地运行

```bash
export SEEKBELL_DATA_DIR="$HOME/.local/share/seekbell-dev"
uv run --frozen python -m seekbell.db upgrade
uv run --frozen python -m seekbell.db current
uv run --frozen python -m seekbell.db check
pnpm --dir frontend build
uv run --frozen python -m seekbell
```

打开 [本地页面](http://127.0.0.1:8000/)。后端以一个进程提供 API 与构建后的静态文件，启动自动迁移；迁移失败直接停止。同一数据目录只允许一个服务/维护进程，停止服务后才能运行维护命令。

开发前端时，保持后端运行，在另一终端执行 `pnpm --dir frontend dev`，打开终端显示的地址。Vite 将 `/api` 和 `/health` 代理到本地 8000 端口；仅用于开发。后端单独运行且尚未构建前端时，API 可用，首页返回 404。

|环境变量|默认|用途|
|---|---|---|
|`SEEKBELL_DATA_DIR`|`data`|SQLite 和进程锁目录；容器内为 `/data`|
|`SEEKBELL_STATIC_DIR`|`frontend/dist`|构建后的前端目录|
|`SEEKBELL_BUILD_REVISION`|`development`|显示的代码版本；镜像通过 `VCS_REF` 写入完整提交 SHA|

只开放只读的 `/api/version`、`/health/live`、`/health/ready`。存活检查不依赖外部服务；就绪检查验证数据库和迁移。M0 不启用采集/通知调度，也没有管理员初始化入口或初始化令牌。反代头默认不信任，HTTPS/认证将在后续阶段验证。

## 本地镜像

仅用于 M0 冒烟检查，不代表已完成 M4/M5 部署验收。Docker daemon 需要可用；端口只绑定本机。构建前确认代码已提交，以保证版本对应镜像内容。

```bash
docker build --build-arg VCS_REF="$(git rev-parse HEAD)" -t seekbell:local .
python3 scripts/check_container.py seekbell:local --revision "$(git rev-parse HEAD)"
docker volume create seekbell-m0-data
docker run --rm --name seekbell-m0 -p 127.0.0.1:8000:8000 \
  -v seekbell-m0-data:/data seekbell:local
```

镜像使用 UID/GID 10001，数据持久化在命名卷；绑定已有宿主目录时需预先配置正确所有权。只运行一个容器实例/一个 Uvicorn worker。Compose、备份、凭据加密、升级回退与实机部署在 M4；双架构和 PVE 验证尚未完成。

`check_container.py`只使用已构建的本地镜像，创建禁用外网的临时容器和数据卷，检查API、构建资源、非root身份、进程锁、健康检查与重启持久化，结束后删除本次创建的临时资源，不触碰日常数据卷。

## 开发与交接

每次从 [AGENTS.md](AGENTS.md) 和 [PROJECT_STATE](docs/PROJECT_STATE.md) 进入，再按当前阅读清单补读。阶段见 [ROADMAP](docs/ROADMAP.md)，验收边界见 [ACCEPTANCE](docs/ACCEPTANCE.md)，外部待办见 [DECISIONS](docs/DECISIONS.md)。首版只支持官方 RSS，不扩展全文、回帖、自定义网站或 TG 频道采集。

远程仓库、镜像发布、SSH、真实通知目标和许可证尚未提供；本地开发继续，远程动作按明确授权执行。原始规格文件保存在初始 Git 提交中。
