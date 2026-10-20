# SeekBell

自托管的网站新帖监控与通知工具，按需添加已适配的内置网站，首版支持 NodeSeek 官方 RSS。范围与技术栈见 [SPEC](docs/SPEC.md) 和 [ARCHITECTURE](docs/ARCHITECTURE.md)。

当前已实现 **M1核心闭环与M2四渠道通知**：RSS解析、规则、基线/身份账本、事务outbox、可恢复投递，以及Telegram Bot/Bark/SMTP/Webhook适配、加密目标配置和独立目标测试记录。M2通过模拟验证；M3已接入真实初始化/登录、网站/任务、加密通知配置、工作空间保存、内容/命中/投递历史只读查询、真实概览统计、管理员修改、显式通知测试/手动重发和服务端采集/自动投递生命周期；其余管理能力及验收仍未完成。真实通知与用户验收待Web完成后统一组织，当前证据以[PROJECT_STATE](docs/PROJECT_STATE.md)为准。

## 完整管理界面（模拟数据版）

首轮视觉已获确认，现已补齐六个管理模块、四渠道目标编辑、初始化/登录及全部手机布局。网站管理使用居中内置库、卡片与右侧配置面板；工作空间名称及说明可在设置中自定义；首次空工作空间，可显式载入示例。支持跨页操作、演示账号和普通配置备份恢复，仅浏览器本地保存，尚未接入真实后端。运行、页面清单和源码结构见 [界面说明](docs/UI_PROTOTYPE.md)，完整视觉与交互规则见 [设计规范](docs/UI_DESIGN.md)。独立模拟入口保留用于界面演示；默认生产入口已接入真实API，完成范围见下文。前端演示交付不等同M3完成。

## 真实管理入口（M3分阶段接入）

默认index.html保留v0.4界面，初始化创建唯一管理员，后续登录使用服务端会话。新库无已添加网站：添加内置NodeSeek→配置一个通知目标→创建任务；任务备注、规则、网站配置与工作空间名称/说明存入SQLite，刷新、重启及重新登录后保留。通知目标完整配置加密，读取不回显敏感值，保存不会发送消息。正式入口不读取演示浏览器数据。

内容、逐任务判定、投递与独立测试历史已支持服务端筛选/分页/详情；旧版本未记录的结果不会按当前规则重算，投递成功仍保留曾未知标记。[历史接入记录](docs/history/2026-10-20-历史查询接入.md)说明API及语义。概览已使用数据库统计24小时/7天趋势、送达回执与来源状态；管理员用户名/密码可验证当前密码后修改，旧会话失效。详见[概览与账号接入](docs/history/2026-10-20-概览与管理员接入.md)。独立目标测试与手动重发已接入：确认后发送，单独留证，响应丢失重试不重复建立操作，不改自动去重。详见[通知操作接入](docs/history/2026-10-20-通知测试与手动重发.md)。生产备份/清理/告警待接入；后台采集/自动投递随服务运行，启用网站后按配置执行，关闭浏览器或退出登录不停止；首次只建基线，重启保留队列/退避，异常会降低就绪状态。详见[后台接入记录](docs/history/2026-10-20-后台生命周期接入.md)。目标删除会检查所有未删除任务的依赖（包括暂停任务），删除当前配置、取消等待发送，保留历史身份和快照；在途消息无法撤回。历史试匹配使用当前草稿和本地最近20/50/100条帖子，显示数量/首次发现时间及三值原因，不保存规则、不发送、不改变去重。网站面板的连接测试需明确确认，只请求固定官方RSS并解析，结果独立持久化；与采集共用来源锁、间隔和退避，不改变正式采集状态、基线或历史。详见[管理操作接入](docs/history/2026-10-20-管理操作接入.md)。完整契约及证据见[接入记录](docs/history/2026-10-20-首个真实接入闭环.md)。

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

离线入口继续独立使用临时库。正式页面已接入配置管理；新安装无网站实例，内置来源保持关闭，通知目标为空。

## M2通知故障矩阵

以下检查使用临时SQLite、HTTPX MockTransport和模拟SMTP，测试进程禁止外网，不会向真实目标发送：

~~~bash
uv run --frozen pytest -q tests/test_notification_config.py tests/test_notification_migration.py tests/test_notifier_http.py tests/test_notifier_smtp.py tests/test_notification_integration.py
~~~

渠道配置通过Pydantic schema校验；Telegram/Bark检查业务结果，Webhook默认要求JSON的`ok: true`，也可显式选择HTTP 2xx接受模式。HTTP限流遵循Retry-After；SMTP支持TLS/STARTTLS，明文模式必须显式允许，成功仅代表邮件服务器接受。结果未知可能产生重复，Webhook重试保留相同事件ID和Idempotency-Key。

内部`Configuration(engine, vault)`负责创建/修改目标，`get_target`返回普通配置和已配置敏感字段名，不返回秘密；更新时省略字段即保留旧值。`NotifierRegistry`供DeliveryWorker使用，`TargetTesting`显式测试单目标并单独记录，不改变自动去重；这些服务均未暴露未认证API。

Fernet密钥位于数据目录的`credentials.key`（0600），目标完整配置和outbox/测试快照均加密，发送时才解密。显式首次创建不会覆盖旧密钥，正常加载缺钥/坏钥直接报错，不自动替换。恢复加密配置必须同时恢复原密钥。M3受保护配置API已复用上述机制；应用启动显式初始化/加载密钥并核验已有目标密文。本地自动测试只使用合成凭据，未写入开发数据库。

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

公开接口为版本/健康与/api/auth/status、setup、login；配置接口/api/manage/*需服务端会话，写操作需X-CSRF-Token并校验Origin。首次无需初始化令牌。会话12小时有效，退出立即撤销，API响应禁止缓存；密码8–128字符，登录限速按来源10次/分钟、全局30次/分钟。

反代头默认不信任。HTTPS代理须保留原Host，并在启动Uvicorn时显式设置--proxy-headers及--forwarded-allow-ips为实际可信代理地址，禁止通配信任；受信任的HTTPS请求才设置Secure Cookie，普通本机HTTP也可登录。仅做了HTTP/HTTPS Cookie和来源校验自动测试，实际反代部署待验证。存活不依赖外部服务；就绪检查验证数据库/迁移及后台actor存活。初始化后按已安装网站及启停配置自动采集和投递；空库不请求外网。

真实浏览器复验使用一次性临时服务/数据库：首闭环8011为空库，历史8012、显式发送8013、后台8014、管理操作8015使用各自合成夹具；不读上述开发数据，不访问论坛或发送消息：

~~~bash
pnpm --dir frontend build
pnpm --dir frontend test:live
pnpm --dir frontend test:history
pnpm --dir frontend test:sending
pnpm --dir frontend test:runtime
pnpm --dir frontend test:operations
~~~


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

`check_container.py`只使用已构建的本地镜像，创建禁用外网的临时容器和数据卷，检查API、构建资源、非root身份、进程锁、健康检查、重启持久化和镜像内离线闭环，结束后删除本次创建的临时资源，不触碰日常数据卷。

## 开发与交接

每次从 [AGENTS.md](AGENTS.md) 和 [PROJECT_STATE](docs/PROJECT_STATE.md) 进入，再按当前阅读清单补读。阶段见 [ROADMAP](docs/ROADMAP.md)，验收边界见 [ACCEPTANCE](docs/ACCEPTANCE.md)，外部待办见 [DECISIONS](docs/DECISIONS.md)。首版只支持官方 RSS，不扩展全文、回帖、自定义网站或 TG 频道采集。

远程仓库为私有的 [Aspeternity/seekbell](https://github.com/Aspeternity/seekbell)。镜像发布、SSH、真实通知目标和许可证尚未提供；相关动作按明确授权执行。原始规格文件保存在初始 Git 提交中。

提交身份使用GitHub noreply地址。首次克隆后执行`git config --local core.hooksPath .githooks`启用提交/推送前邮箱检查；CI也检查全部提交身份及Git历史/索引中的非示例邮箱，失败日志不输出被拒地址。真实通知凭据只保存在运行配置，不写入Git。
