# SeekBell

自托管的 NodeSeek 新帖监控与通知工具。范围与技术栈见 [SPEC](docs/SPEC.md) 和 [ARCHITECTURE](docs/ARCHITECTURE.md)。

当前已实现 **M1核心闭环与M2四渠道通知**：RSS解析、规则、基线/身份账本、事务outbox、可恢复投递，以及Telegram Bot/Bark/SMTP/Webhook适配、加密目标配置和独立目标测试记录。M2通过模拟验证；M3已接入唯一管理员初始化、登录/退出与持久会话，六页Web管理和自动调度仍待实现，当前不能作为监控服务投入使用。真实通知与用户验收待Web完成后统一组织，当前证据以[PROJECT_STATE](docs/PROJECT_STATE.md)为准。

## 环境

本机已确认使用独立WSL2发行版`SeekBell-Dev`，源码位于Linux文件系统的`/home/dev/projects/seekbell`。Windows终端执行`wsl.exe -d SeekBell-Dev --cd /home/dev/projects/seekbell`进入。原D盘目录保留为交接副本；具体配置、隔离边界和Docker维护命令见[开发环境](docs/DEVELOPMENT_ENVIRONMENT.md)。

服务运行于 Linux，Python 3.12、Node 24.22.0（`.node-version`）、uv 0.13.1、pnpm 10.34.7。精确依赖见 `uv.lock` 和 `frontend/pnpm-lock.yaml`。工具安装参考 [uv](https://docs.astral.sh/uv/getting-started/installation/)、[Node](https://nodejs.org/en/download)、[pnpm](https://pnpm.io/installation)。

WSL 请使用 Linux Node/pnpm，避免误用 Windows 的可执行文件。数据目录放在 Linux 本地文件系统，正式部署不能直接使用 `/mnt/c`、`/mnt/d`、NFS 或 SMB 数据卷。跨文件系统安装 uv 依赖时可设置 `UV_LINK_MODE=copy`。

## 安装与检查

在仓库根目录执行；以下命令不联系论坛或真实通知目标。

```bash
python3 scripts/check_privacy.py
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

Python 测试使用临时 SQLite 和进程内 HTTP 客户端，并拒绝测试进程的外网连接。CI 执行这些检查及迁移命令、镜像构建；没有发布、远程部署或真实发送步骤。远程 Actions 的执行结果和对应提交见 [PROJECT_STATE](docs/PROJECT_STATE.md)。

## M1 离线闭环演示

在独立开发WSL内执行：

~~~bash
uv run --frozen python -m seekbell.services.demo
~~~

演示创建临时SQLite，使用HTTPX MockTransport和模拟通知，退出后清理临时数据。依次验证首次成功基线、新帖、两任务合并、认领后租约过期、退避重试和重复摄取。预期为2次规则命中、1条合并投递意图、3次尝试（含过期租约）、1条成功回执、重复摄取新增0条投递；历史不确定性仍保留。不会读取正式数据库或通知凭据。

核心服务仍由离线入口验证；默认内置来源关闭、通知目标为空，页面提供管理员初始化/登录及登录后的运行状态。

## M2通知故障矩阵

以下检查使用临时SQLite、HTTPX MockTransport和模拟SMTP，测试进程禁止外网，不会向真实目标发送：

~~~bash
uv run --frozen pytest -q tests/test_notification_config.py tests/test_notification_migration.py tests/test_notifier_http.py tests/test_notifier_smtp.py tests/test_notification_integration.py
~~~

渠道配置通过Pydantic schema校验；Telegram/Bark检查业务结果，Webhook默认要求JSON的`ok: true`，也可显式选择HTTP 2xx接受模式。HTTP限流遵循Retry-After；SMTP支持TLS/STARTTLS，明文模式必须显式允许，成功仅代表邮件服务器接受。结果未知可能产生重复，Webhook重试保留相同事件ID和Idempotency-Key。

内部`Configuration(engine, vault)`负责创建/修改目标，`get_target`返回普通配置和已配置敏感字段名，不返回秘密；更新时省略字段即保留旧值。`NotifierRegistry`供DeliveryWorker使用，`TargetTesting`显式测试单目标并单独记录，不改变自动去重；这些服务均未暴露未认证API。

Fernet密钥位于数据目录的`credentials.key`（0600），目标完整配置和outbox/测试快照均加密，发送时才解密。显式首次创建不会覆盖旧密钥，正常加载缺钥/坏钥直接报错，不自动替换。恢复加密配置必须同时恢复原密钥。密钥初始化及渠道服务将在M3认证与应用生命周期中接入，当前开发数据库未写入真实凭据。

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
|`SEEKBELL_TRUSTED_PROXIES`|`[]`|明确可信的反代IP/CIDR数组；仅这些连接可影响协议/客户端信息|

只读的 `/api/version`、`/health/live`、`/health/ready` 保持公开；存活检查不依赖外部服务，就绪检查验证数据库和迁移。管理员入口为 `/api/auth/state`、`setup`、`login`、`logout`；先GET state取得CSRF，再用Cookie和 `X-CSRF-Token` 提交。创建唯一管理员后初始化关闭，没有初始化令牌。用户名1～64字符，密码15～128字符，支持空格和中文。页面不持久保存密码或会话令牌。

认证会话最长7天、登录前会话30分钟，重启保持有效；登录轮换令牌，退出服务端撤销。创建/登录共用每分钟10次的持久预算，超限返回429及Retry-After。认证API不缓存，校验错误不回显凭据。当前仍不启动采集/通知调度。

反代HTTPS时，设置 `SEEKBELL_TRUSTED_PROXIES` 为明确代理IP/CIDR的JSON数组，例如 `'["172.20.0.2"]'`（替换为实际地址）。默认 `[]`，不允许 `*` 或全网段。代理必须保留原始Host并覆盖X-Forwarded-Proto；应用只从可信连接读取协议和客户端转发信息，不读取X-Forwarded-Host。可信HTTPS请求设置Secure Cookie，直接HTTP可登录。保持Uvicorn的 `--no-proxy-headers`，由应用统一处理信任边界，避免两层解析。

## M3认证自动验证

~~~bash
uv run --frozen pytest -q tests/test_authentication.py tests/test_baseline.py
pnpm --dir frontend exec playwright install chromium --only-shell
pnpm --dir frontend build
pnpm --dir frontend test:e2e
~~~

首次安装Chromium系统依赖需在SeekBell-Dev内以root执行[依赖安装命令](docs/DEVELOPMENT_ENVIRONMENT.md#浏览器自动验证)；日常测试使用dev。浏览器测试自动启动127.0.0.1:18765的临时服务与数据库，拒绝复用现有服务；后端禁止外连，浏览器只允许该本地来源。验证桌面/手机宽度下初始化、刷新、退出、错误密码、重新登录、过期恢复及CSRF，不代表用户验收。截图/失败trace仅写入忽略的test-results，可能含测试会话，不上传为发布材料。

## 本地镜像

用于当前阶段的打包与离线闭环检查，不代表已完成 M4/M5 部署验收。Docker daemon 需要可用；端口只绑定本机。构建前确认代码已提交，以保证版本对应镜像内容。

```bash
docker build --build-arg VCS_REF="$(git rev-parse HEAD)" -t seekbell:local .
python3 scripts/check_container.py seekbell:local --revision "$(git rev-parse HEAD)"
docker volume create seekbell-dev-data
docker run --rm --name seekbell-dev -p 127.0.0.1:8000:8000 \
  -v seekbell-dev-data:/data seekbell:local
```

镜像使用 UID/GID 10001，数据持久化在命名卷；绑定已有宿主目录时需预先配置正确所有权。只运行一个容器实例/一个 Uvicorn worker。Compose、备份封装、升级回退与实机部署在 M4；双架构和 PVE 验证尚未完成。

`check_container.py`只使用已构建的本地镜像，创建禁用外网的临时容器和数据卷，检查API、构建资源、非root身份、进程锁、健康检查、账号/会话重启持久化和镜像内离线闭环，结束后删除本次创建的临时资源，不触碰日常数据卷。

## 开发与交接

每次从 [AGENTS.md](AGENTS.md) 和 [PROJECT_STATE](docs/PROJECT_STATE.md) 进入，再按当前阅读清单补读。阶段见 [ROADMAP](docs/ROADMAP.md)，验收边界见 [ACCEPTANCE](docs/ACCEPTANCE.md)，外部待办见 [DECISIONS](docs/DECISIONS.md)。首版只支持官方 RSS，不扩展全文、回帖、自定义网站或 TG 频道采集。

远程仓库为私有的 [Aspeternity/seekbell](https://github.com/Aspeternity/seekbell)。镜像发布、SSH、真实通知目标和许可证尚未提供；相关动作按明确授权执行。原始规格文件保存在初始 Git 提交中。

提交身份使用GitHub noreply地址。首次克隆后执行`git config --local core.hooksPath .githooks`启用提交/推送前邮箱检查；CI也检查全部提交身份及Git历史/索引中的非示例邮箱，失败日志不输出被拒地址。真实通知凭据只保存在运行配置，不写入Git。
