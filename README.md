# SeekBell

自托管的网站新帖监控与通知工具，按需添加已适配的内置网站，当前支持 NodeSeek 与 Linux DO 官方 RSS。范围与技术栈见 [SPEC](docs/SPEC.md) 和 [ARCHITECTURE](docs/ARCHITECTURE.md)。

当前已实现 **M1核心闭环与M2四渠道通知**：RSS解析、规则、基线/身份账本、事务outbox、可恢复投递，以及Telegram Bot/Bark/SMTP/Webhook适配、加密目标配置和独立目标测试记录。M2通过模拟验证；M3已接入真实初始化/登录、网站/任务、加密通知配置、工作空间保存、内容/命中/投递历史只读查询、真实概览统计、管理员修改、显式通知测试/手动重发和服务端采集/自动投递生命周期、保留策略与分批历史清理、显示时区及系统故障/恢复告警；版本信息已接入，M3本地自动退出核对已通过；已提供M4停服加密备份/独立恢复维护命令，网页加密下载/上传生成独立副本已接入，保留原卷的切换/升级回退维护流程已实现，真实验收仍未完成。真实通知与用户验收待Web完成后统一组织，当前证据以[PROJECT_STATE](docs/PROJECT_STATE.md)为准。

## 管理界面

仅维护一个正式前端入口，页面、导航与样式遵循已确认的[设计规范](docs/UI_DESIGN.md)。旧独立演示版已退役，不再提供模拟账户、浏览器备份、载入示例工作台或第二套构建。源码集中在frontend/src的pages、components、styles和API服务模块，结构见[ARCHITECTURE](docs/ARCHITECTURE.md)。

默认index.html保留v0.4界面，初始化创建唯一管理员，后续登录使用服务端会话。新库无已添加网站：添加内置NodeSeek或Linux DO→配置一个通知目标→创建任务；任务备注、规则、网站配置与工作空间名称/说明存入SQLite，刷新、重启及重新登录后保留。通知目标完整配置加密，读取不回显敏感值，保存不会发送消息。正式入口不读取演示浏览器数据。

内容、逐任务判定、投递与独立测试历史已支持服务端筛选/分页/详情；旧版本未记录的结果不会按当前规则重算，投递成功仍保留曾未知标记。[历史接入记录](docs/history/2026-10-20-历史查询接入.md)说明API及语义。概览已使用数据库统计24小时/7天趋势、送达回执与来源状态；管理员用户名/密码可验证当前密码后修改，旧会话失效。详见[概览与账号接入](docs/history/2026-10-20-概览与管理员接入.md)。独立目标测试与手动重发已接入：确认后发送，单独留证，响应丢失重试不重复建立操作，不改自动去重。详见[通知操作接入](docs/history/2026-10-20-通知测试与手动重发.md)。生产备份已提供停服维护命令，网页已支持加密下载和上传生成独立恢复副本；后台采集/自动投递随服务运行，启用网站后按配置执行，关闭浏览器或退出登录不停止；首次只建基线，重启保留队列/退避，异常会降低就绪状态。详见[后台接入记录](docs/history/2026-10-20-后台生命周期接入.md)。目标删除会检查所有未删除任务的依赖（包括暂停任务），删除当前配置、取消等待发送，保留历史身份和快照；在途消息无法撤回。历史试匹配使用当前草稿和本地最近20/50/100条帖子，显示数量/首次发现时间及三值原因，不保存规则、不发送、不改变去重。网站面板的连接测试需明确确认，只请求固定官方RSS并解析，结果独立持久化；与采集共用来源锁和错误退避，测试采用独立防连点间隔、不改变正常采集周期，不改变正式采集状态、基线或历史。详见[管理操作接入](docs/history/2026-10-20-管理操作接入.md)。保留策略默认30天，可调1–365天，保存确认后由后台分批清理普通历史；队列/在途/未完成操作受保护，已见/送达/来源身份账本始终保留，删除的历史无法通过改回天数恢复。详见[保留与清理记录](docs/history/2026-10-20-保留策略与清理接入.md)。显示时区由首次初始化时的浏览器时区设定，修改后全局展示与日期筛选同步，后续登录不覆盖。系统告警独立选目标、默认关闭，确认启用后每次故障/恢复只尝试一次；重复故障不刷屏，全部渠道失败或未知也能在网页查看。Webhook系统事件使用schema_version 2/type system_alert，帖子消息仍为v1。详见[时区与告警记录](docs/history/2026-10-20-时区与系统告警接入.md)。系统设置的版本信息显示实际应用/完整代码/迁移版本，就绪和后台状态独立读取，故障时仍可查看可用版本并重试。完整M3操作映射、退出结论和后续边界见[退出核对](docs/history/2026-10-20-版本信息与M3退出核对.md)。完整契约及证据见[接入记录](docs/history/2026-10-20-首个真实接入闭环.md)。

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

Python 测试使用临时 SQLite 和进程内 HTTP 客户端，并拒绝测试进程的外网连接。所有浏览器套件直接运行同一frontend/dist正式构建；test:ui覆盖通用交互，其余按API/历史/备份/HTTPS等专项使用独立临时服务。测试夹具与合成发送器不构成额外产品版本。普通CI执行这些检查及迁移命令、镜像构建；独立手动双架构候选流程默认不发布，显式启用后可写GHCR，详见[镜像流程](docs/IMAGE_RELEASE.md)。尚无远程部署或真实发送步骤。远程 Actions 的执行结果和对应提交见 [PROJECT_STATE](docs/PROJECT_STATE.md)。

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
|`SEEKBELL_TRUSTED_PROXY_IPS`|空|确切可信代理IP，逗号分隔；默认忽略转发头|
|`SEEKBELL_BUILD_REVISION`|`development`|显示的代码版本；镜像通过 `VCS_REF` 写入完整提交 SHA|

公开接口为版本/健康与/api/auth/status、setup、login；配置接口/api/manage/*需服务端会话，写操作需X-CSRF-Token并校验Origin。首次无需初始化令牌。会话12小时有效，退出立即撤销，API响应禁止缓存；密码8–128字符，登录限速按来源10次/分钟、全局30次/分钟。

反代头默认不信任。外部HTTPS代理须保留Host（含非默认端口）并覆盖转发头，通过SEEKBELL_TRUSTED_PROXY_IPS明确指定应用实际看到的代理IP；ASGI层统一处理，Uvicorn入口保持--no-proxy-headers。受信HTTPS设置Secure Cookie，普通本机HTTP仍可登录。配置示例、只读检查与本地真实Nginx/TLS演练见[HTTPS部署](docs/PROXY_DEPLOYMENT.md)，实际目标环境部署仍待授权验证。存活不依赖外部服务；就绪检查验证数据库/迁移及后台actor存活。初始化后按已安装网站及启停配置自动采集和投递；空库不请求外网。

浏览器复验使用一次性临时服务/数据库：首闭环8011为空库；历史8012、显式发送8013、后台8014、管理操作8015、保留清理8016、时区/系统告警8017使用各自合成夹具；备份8018/8019为独立空库，加载8020、筛选修复8021、通用UI8022和内容稳定性8023为临时服务；不读上述开发数据，不访问论坛或发送消息：

~~~bash
pnpm --dir frontend build
pnpm --dir frontend test:ui
pnpm --dir frontend test:live
pnpm --dir frontend test:history
pnpm --dir frontend test:sending
pnpm --dir frontend test:runtime
pnpm --dir frontend test:operations
pnpm --dir frontend test:retention
pnpm --dir frontend test:system
pnpm --dir frontend test:backup
pnpm --dir frontend test:approved-ui
pnpm --dir frontend test:loading
pnpm --dir frontend test:history-ui-fixes
pnpm --dir frontend test:content-stability
pnpm --dir frontend test:workspace-stability
pnpm --dir frontend test:first-entry
pnpm --dir frontend test:hotlist
pnpm --dir frontend test:evaluations
pnpm --dir frontend test:linuxdo
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

镜像使用 UID/GID 10001，数据持久化在命名卷；绑定已有宿主目录时需预先配置正确所有权。只运行一个容器实例/一个 Uvicorn worker。Compose与停服加密备份/独立恢复CLI已提供，详见[维护说明](docs/BACKUP_RESTORE.md)。保留原卷的切换/升级回退维护流程见[发布维护](docs/RELEASES.md)，实机部署仍待后续；双架构和PVE验证尚未完成。

`check_container.py`只使用已构建的本地镜像，创建禁用外网的临时容器和数据卷，检查API、构建资源、非root身份、进程锁、健康检查、重启持久化和镜像内离线闭环，结束后删除本次创建的临时资源，不触碰日常数据卷。

## 停服维护备份

~~~bash
uv run --frozen python -m seekbell.backup --help
uv run --frozen python -m seekbell.services.backup_demo
~~~

实际备份使用create --output、恢复使用restore --archive/--destination，口令在交互终端输入；禁止覆盖原目录。含原凭据密钥的整库备份加密，恢复需重新验证备份管理员并撤销旧会话，保留队列/去重。使用前按[备份恢复说明](docs/BACKUP_RESTORE.md)停止服务、准备私有目录并选匹配镜像；Compose与禁外网演练命令均在该文档。普通演示备份不能恢复生产数据。

## 开发与交接

每次从 [AGENTS.md](AGENTS.md) 和 [PROJECT_STATE](docs/PROJECT_STATE.md) 进入，再按当前阅读清单补读。阶段见 [ROADMAP](docs/ROADMAP.md)，验收边界见 [ACCEPTANCE](docs/ACCEPTANCE.md)，外部待办见 [DECISIONS](docs/DECISIONS.md)。首版只支持官方 RSS，不扩展全文、回帖、自定义网站或 TG 频道采集。

远程仓库为私有的 [Aspeternity/seekbell](https://github.com/Aspeternity/seekbell)。镜像发布、SSH、真实通知目标和许可证尚未提供；相关动作按明确授权执行。原始规格文件保存在初始 Git 提交中。

提交身份使用GitHub noreply地址。首次克隆后执行`git config --local core.hooksPath .githooks`启用提交/推送前邮箱检查；CI也检查全部提交身份及Git历史/索引中的非示例邮箱，失败日志不输出被拒地址。真实通知凭据只保存在运行配置，不写入Git。

### 概览模块与社区热榜验证

概览模块显隐/顺序在系统设置→偏好与保留保存；首接NodeSeek第三方热榜，生产无需额外服务。热榜不参与规则或通知，隐藏后不再专用刷新。

    uv run --frozen pytest -q tests/test_hotlists.py tests/test_release.py tests/test_backup.py
    pnpm --dir frontend build
    pnpm --dir frontend test:hotlist

浏览器命令启动一次性临时库和合成HTTP服务（8028），退出清理；不读取正式数据库或访问真实热榜。Linux DO与持久热榜快照使用迁移0011；切换前做完整备份，旧0010镜像回退必须恢复匹配旧库。

### Linux DO与多站验证

Linux DO从内置网站库添加，初始暂停；候选默认和最小采集间隔为60秒，不代表官方限频保证。仅公开主题RSS，作者显示名不能用于用户名条件。NodeSeek热榜为第三方实时/每日/每周，Linux DO为原站RSS热门/每日/每周；缺失来源更新时间时显示获取时间。热榜快照独立保存、最多展示24小时，不参与监控或通知。

~~~bash
uv run --frozen pytest tests/test_public_http.py tests/test_linuxdo.py tests/test_linuxdo_runtime.py tests/test_hotlists.py tests/test_runtime.py -q
pnpm --dir frontend test:linuxdo
~~~

浏览器套件使用一次性8030服务和合成两站HTTP，不请求真实论坛。Linux DO三入口使用HTTPX HTTP/2（仅该域名），保留匿名请求、TLS与共享退避。2026-10-24本机四源HTTP/2匿名对照通过，HTTP/1.1仍返回403；部署环境/持续可用性需单独验收，遇挑战继续显示来源异常并退避。新站不会随升级自动安装或启用。

### Linux DO退避与人工重试

自动403/访问挑战等待5→10分钟，最长10分钟；无Retry-After的429最长10分钟，超时/传输/服务端错误最长5分钟。服务器指定等待独立保存，最多24小时。网站配置的“测试连接”每60秒最多一次，可提前验证自动退避中的连接；成功后安排失败采集真实重试，不更改健康计划或历史/基线，也不直接发通知。刷新页面不等于重试。0012_retry_controls只增两个时间字段，旧等待原因不明时保守保留；升级前整卷备份，回退旧0011镜像须恢复匹配备份。

~~~bash
uv run --frozen pytest tests/test_retry_controls.py tests/test_source_probe_scheduling.py tests/test_linuxdo_runtime.py -q
pnpm --dir frontend test:linuxdo
~~~

2026-10-24多站修正：网站按添加顺序持久排列，新加项在末尾；0013_site_order从原SQLite记录顺序回填。人工60秒配额仅由真实人工测试消耗，自动失败不占用；短暂忙碌/间隔延期按短等待重试。Linux DO热榜只请求选中周期，waiting状态自动重试而不误报失败。0012→0013升级前整卷备份；旧镜像回退必须恢复匹配0012备份。

2026-10-24任务多站：新建/编辑任务可复选已添加网站，共用规则与通知目标，保存形成新配置版本，无需删除重建，不补发历史。章节高亮随滚动同步。0014_task_websites只新增并回填版本的网站集合；升级前整卷备份，回退必须恢复匹配0013整卷后启旧镜像。验证：uv run --frozen pytest tests/test_task_websites.py -q；pnpm --dir frontend test:linuxdo。

2026-10-24匹配诊断：未命中直接查看单任务历史原因，搜索切换/完整条件/当前规则只读试算；历史样本用汇总和10条分页弹窗，网站鼠标选择无粗框。0015_category_values通过新配置版本修复已知NodeSeek旧中文版块值，不改旧判定或补发。升级前备份0014整卷，回退必须恢复匹配旧镜像/卷。检查：uv run --frozen pytest tests/test_match_diagnostics.py -q；pnpm --dir frontend test:diagnostics。
