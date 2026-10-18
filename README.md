# SeekBell

自托管的 NodeSeek 新帖监控与通知工具。范围与技术栈见 [SPEC](docs/SPEC.md) 和 [ARCHITECTURE](docs/ARCHITECTURE.md)。

当前已实现 **M1核心闭环与M2四渠道通知**：RSS解析、规则、基线/身份账本、事务outbox、可恢复投递，以及Telegram Bot/Bark/SMTP/Webhook适配、加密目标配置和独立目标测试记录。M2通过模拟验证；M3已接入管理员认证、四渠道目标/任务配置及模拟/历史规则试匹配，后台采集/投递生命周期及概览、网站与本地内容命中页面也已接入。通知管理已接入目标发送测试、投递记录和独立手动重发，系统设置仍待完成，尚未完成M3。真实通知与用户验收待Web完成后统一组织，当前证据以[PROJECT_STATE](docs/PROJECT_STATE.md)为准。

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

应用默认启动单一采集循环和投递循环，内置来源仍默认关闭、通知目标为空。管理员显式启用网站后才自动采集；关闭浏览器不会停止后台。离线演示使用独立临时数据，不会启用应用的真实来源。

## M2通知故障矩阵

以下检查使用临时SQLite、HTTPX MockTransport和模拟SMTP，测试进程禁止外网，不会向真实目标发送：

~~~bash
uv run --frozen pytest -q tests/test_notification_config.py tests/test_notification_migration.py tests/test_notifier_http.py tests/test_notifier_smtp.py tests/test_notification_integration.py
~~~

渠道配置通过Pydantic schema校验；Telegram/Bark检查业务结果，Webhook默认要求JSON的`ok: true`，也可显式选择HTTP 2xx接受模式。HTTP限流遵循Retry-After；SMTP支持TLS/STARTTLS，明文模式必须显式允许，成功仅代表邮件服务器接受。结果未知可能产生重复，Webhook重试保留相同事件ID和Idempotency-Key。

内部`Configuration(engine, vault)`负责创建/修改目标，`get_target`返回普通配置和已配置敏感字段名，不返回秘密；更新时省略字段即保留旧值。`NotifierRegistry`供DeliveryWorker使用，`TargetTesting`显式测试单目标并单独记录，不改变自动去重；这些服务均未暴露未认证API。

Fernet密钥位于数据目录的`credentials.key`（0600），目标完整配置和outbox/测试快照均加密，发送时才解密。显式首次创建不会覆盖旧密钥，正常加载缺钥/坏钥直接报错，不自动替换。恢复加密配置必须同时恢复原密钥。M3启动生命周期已接入密钥加载/独占创建，并校验现有目标；已有密文而缺钥时停止启动，不生成替代密钥。应用生命周期已接入采集与渠道发送；自动验证只使用合成配置和模拟服务。

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
|`SEEKBELL_BACKGROUND_ENABLED`|`true`|启动采集与投递循环；离线检查可设`false`，不会禁用管理员显式RSS连接测试|
|`SEEKBELL_TRUSTED_PROXIES`|`[]`|明确可信的反代IP/CIDR数组；仅这些连接可影响协议/客户端信息|

只读的 `/api/version`、`/health/live`、`/health/ready` 保持公开；存活检查不依赖外部服务，就绪检查验证数据库、迁移及后台循环是否异常退出；普通RSS网络失败只记录退避，不使就绪失败。管理员入口为 `/api/auth/state`、`setup`、`login`、`logout`；先GET state取得CSRF，再用Cookie和 `X-CSRF-Token` 提交。创建唯一管理员后初始化关闭，没有初始化令牌。用户名1～64字符，密码15～128字符，支持空格和中文。页面不持久保存密码或会话令牌。

认证会话最长7天、登录前会话30分钟，重启保持有效；登录轮换令牌，退出服务端撤销。创建/登录共用每分钟10次的持久预算，超限返回429及Retry-After。认证API不缓存，校验错误不回显凭据。后台组件启动失败会降低就绪状态；来源仍须管理员显式启用。

反代HTTPS时，设置 `SEEKBELL_TRUSTED_PROXIES` 为明确代理IP/CIDR的JSON数组，例如 `'["172.20.0.2"]'`（替换为实际地址）。默认 `[]`，不允许 `*` 或全网段。代理必须保留原始Host并覆盖X-Forwarded-Proto；应用只从可信连接读取协议和客户端转发信息，不读取X-Forwarded-Host。可信HTTPS请求设置Secure Cookie，直接HTTP可登录。保持Uvicorn的 `--no-proxy-headers`，由应用统一处理信任边界，避免两层解析。

## M3认证自动验证

~~~bash
uv run --frozen pytest -q tests/test_authentication.py tests/test_baseline.py
pnpm --dir frontend exec playwright install chromium --only-shell
pnpm --dir frontend build
pnpm --dir frontend test:e2e
~~~

首次安装Chromium系统依赖需在SeekBell-Dev内以root执行[依赖安装命令](docs/DEVELOPMENT_ENVIRONMENT.md#浏览器自动验证)；日常测试使用dev。浏览器测试自动启动127.0.0.1:18765的临时服务与数据库，拒绝复用现有服务；后端禁止外连，浏览器只允许该本地来源。验证桌面/手机宽度下初始化、刷新、退出、错误密码、重新登录、过期恢复及CSRF，不代表用户验收。截图/失败trace仅写入忽略的test-results，可能含测试会话，不上传为发布材料。

## M3配置管理

登录后可管理四渠道通知目标、监控任务和规则。目标字段由渠道schema生成；编辑时敏感字段留空保留原值，显式“恢复默认值”或请求头JSON的空对象可清空可选项。目标重复仅提示，不自动合并。目标停用撤销待发消息，重新启用不会补发。

任务支持创建、编辑、复制草稿（默认暂停）、启停和软删除。条件标签按Enter保存，短语内部空格保留；空组由后端忽略，全空规则明确提示匹配全部新帖。模拟摘要可选择缺失或已知空文本；本地历史只读取最近1～100条并展示实际样本数量/时间，不访问论坛、不发通知、不改变去重账本。

所有/api/manage接口受管理员与CSRF保护；目标编辑需要expected_revision，任务编辑需要expected_version，陈旧编辑返回409并要求重新打开。API错误不回显凭据。模拟/历史测试虽为POST，也需要CSRF。网站页面提供后台采集开关；通知管理提供目标测试与投递记录双标签。

~~~bash
uv run --frozen pytest -q tests/test_management.py
pnpm --dir frontend build
pnpm --dir frontend test:e2e
~~~

浏览器测试使用临时数据库和MockTransport；预置合成帖子并验证显式启用后的自动基线、新帖命中和模拟投递，不使用开发数据库，不联系论坛或真实目标。

## M3调度与运行页面

概览显示采集状态、实际窗口数量、可能缺口、任务/命中/投递统计与结果未知提醒。网站页面固定为NodeSeek官方RSS，不能修改URL或添加其他来源。默认10秒只是候选频率，失败退避并遵守Retry-After；修改频率或启停不能绕过已有退避。网站编辑需要expected_revision，陈旧草稿返回409。

“测试RSS连接”与自动采集共用请求锁，成功仅返回条目数量，不存帖、不建基线或发通知；失败会保存错误和退避。首次启用和主动暂停后恢复只建立当前基线；意外重启保留已见状态。配置变更期间返回的旧响应被丢弃。正常退出先停止新一轮工作，给予在途操作15秒宽限，之后取消网络等待并保留可恢复租约；SQLite线程会等待完成，SMTP线程仍须等待socket关闭，因此宽限不是整个进程退出的硬时限。

内容页只读本地帖子，可按标题子串、作者/版块精确匹配、命中任务筛选；显示原规则版本及原因，已删除任务的历史仍可查询。摘要缺失与空值区分，过长展示有截断提示；外部字段作为文本显示，原帖链接从固定身份重建。所有时间目前使用浏览器本地时区。

~~~bash
uv run --frozen pytest -q tests/test_runtime.py tests/test_collection.py tests/test_management.py
pnpm --dir frontend build
pnpm --dir frontend test:e2e
~~~

## M3通知管理与独立重发

“通知管理”包含目标配置与投递记录。每个目标均可显式发送测试，停用目标也允许测试；确认页使用已保存的配置并显示目标/渠道/版本，不发送未保存草稿。目标测试与手动重发均只尝试一次，不自动重试。响应丢失时可重试同一确认请求；相同request_id与相同资源/配置版本只返回原结果。取消后重新确认使用新请求ID，可能产生一次重复通知，应先检查记录与接收端。

投递记录区分自动投递、手动重发与目标测试，支持目标/状态筛选和分页；详情显示原目标配置版本、规则版本、每次自动尝试、租约/退避及迟到结果。记录不包含秘密、密文或远端错误正文，结果未知持续提示可能重复。显式发送中断后保留未知结果，不在重启时重新发送。

D07手动重发只允许已经结束（渠道接受、最终失败、已取消）的自动事件，当前目标必须启用；等待/自动重试/在途消息继续由自动队列处理。重发使用原通知内容和当前目标配置，标题添加“【手动重发】”，生成新事件ID及独立记录。不会修改原自动事件、重试次数、已见或已发账本，不能用重发成功冒充原自动投递成功。0006_manual_deliveries保存其加密目标快照和原事件引用；备份必须包含原密钥。

POST /api/manage/targets/{id}/test 与 /deliveries/{id}/resend 都要求管理员、CSRF及请求体request_id（UUID v4）、expected_revision和confirmed=true。配置过期、原事件未结束、目标停用或已有显式发送在进行时返回409；客户端应刷新查看状态，不能盲目生成新请求重试。此版本只允许一个显式发送同时进行，退出与应用网络客户端生命周期统一管理。

~~~bash
uv run --frozen pytest -q tests/test_delivery_management.py tests/test_notification_integration.py
pnpm --dir frontend build
pnpm --dir frontend test:e2e
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

`check_container.py`只使用已构建的本地镜像，创建禁用外网的临时容器和数据卷，检查API、构建资源、非root身份、进程锁、健康检查、账号/会话/目标与任务重启持久化、纯规则试匹配和镜像内离线闭环，结束后删除本次创建的临时资源，不触碰日常数据卷。

## 开发与交接

每次从 [AGENTS.md](AGENTS.md) 和 [PROJECT_STATE](docs/PROJECT_STATE.md) 进入，再按当前阅读清单补读。阶段见 [ROADMAP](docs/ROADMAP.md)，验收边界见 [ACCEPTANCE](docs/ACCEPTANCE.md)，外部待办见 [DECISIONS](docs/DECISIONS.md)。首版只支持官方 RSS，不扩展全文、回帖、自定义网站或 TG 频道采集。

远程仓库为私有的 [Aspeternity/seekbell](https://github.com/Aspeternity/seekbell)。镜像发布、SSH、真实通知目标和许可证尚未提供；相关动作按明确授权执行。原始规格文件保存在初始 Git 提交中。

提交身份使用GitHub noreply地址。首次克隆后执行`git config --local core.hooksPath .githooks`启用提交/推送前邮箱检查；CI也检查全部提交身份及Git历史/索引中的非示例邮箱，失败日志不输出被拒地址。真实通知凭据只保存在运行配置，不写入Git。
