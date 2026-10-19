# 技术架构

## 已确认技术栈

后端 Python / FastAPI / Pydantic；前端 TypeScript / Vue 3 / Vite / Naive UI；SQLite；SQLAlchemy / Alembic；HTTPX；feedparser；uv / pnpm。创建项目时查官方兼容说明，锁定实际依赖版本，不无理由更换技术栈。

M0运行基线：Python 3.12、Node 24.22.0、uv 0.13.1、pnpm 10.34.7。直接依赖约束在`pyproject.toml`和`frontend/package.json`，精确解析结果以两个锁文件为准。TypeScript选用5.9.3，满足vue-tsc的声明范围，后续升级需重新检查生态兼容性，不追随所有工具的最新大版本。兼容依据：[FastAPI/Pydantic v2](https://fastapi.tiangolo.com/how-to/migrate-from-pydantic-v1-to-pydantic-v2/)、[Vite Node要求](https://vite.dev/guide/)、[Vue环境要求](https://vuejs.org/guide/quick-start.html)、[Alembic兼容说明](https://alembic.sqlalchemy.org/en/latest/front.html)；执行证据见阶段记录。

模块化单体，单容器、单服务进程、一个持久化数据目录、一个 Web 端口。FastAPI 提供 API 和编译后的前端静态文件。单实例，不支持多副本/多个 Uvicorn worker。启动防止第二个进程重复调度。

建议目录（实现时可小幅调整）：

- backend/seekbell/api：路由、认证、配置校验。
- backend/seekbell/domain：规范化帖子、规则三值判断、投递意图。
- backend/seekbell/sites：NodeSeek 适配、能力声明、ID/分类映射。
- backend/seekbell/collectors：RSS HTTP 获取与解析。
- backend/seekbell/notifiers：Telegram、Bark、SMTP、Webhook。
- backend/seekbell/services：调度、摄取、匹配、投递、备份。
- backend/seekbell/db：模型/事务；backend/migrations：Alembic。
- frontend：Vue 页面、类型、公共组件。
- tests：合成样本、模拟 HTTP/SMTP、集成测试。
- deploy：Compose 示例；docs：规格、进度、验收；.github/workflows：CI/镜像发布。

M0目录调整：Alembic实际位于`backend/seekbell/migrations`，随Python包一起安装；源码、wheel和容器共用同一路径，不依赖工作目录或外部资源映射。通过`python -m seekbell.db upgrade/current/check`维护数据库，复用应用配置和数据目录进程锁，避免服务运行时并发迁移。初始迁移仅存安装标记，不创建管理员或初始化令牌；管理员在M3原子化创建。

## 模块契约

SiteAdapter 声明标识、能力、采集配置、规范链接、帖子 ID 提取、分类映射。首版只注册 NodeSeek RSS；未来可以接入其他网站，但不提前实现主备、TG 会话或网页抓取。

Collector 返回来源条目及采集状态。只处理连接/解析，不运行关键词规则。RSS 使用异步 HTTP 获取；同步解析、大型备份及同步 SMTP 不阻塞事件循环。显式超时、响应大小限制、禁用 XML 外部实体/网络展开、并发上限。M1采用defusedxml先拒绝DTD/实体，再以内存流交给feedparser，避免把输入当URL/文件；解析在线程中执行。由于defusedxml已完成XML良构与安全校验，feedparser仅因轻微格式标记bozo且条目数与原始item一致时记录`feed_bozo_warning`诊断而不丢弃整批；条目数失配才按`feed_parse_error`失败。RSS请求要求identity编码，限1MiB并拒绝未协商的压缩响应。NodeSeek保留原始版块文字，不虚构稳定分类编号。

RuleEngine 为无网络纯逻辑，输入规范化字段和规则快照，输出 match/no_match/insufficient_data 及结构化原因（含NFKC与空白折叠、整词正则缓存及可选`notify_on_insufficient`）。前端试匹配与后台执行共用同一后端逻辑。

Notifier 声明配置 schema、敏感字段、校验与发送能力，返回成功/临时错误/永久错误/结果未知以及可用 Retry-After。重试由投递管理统一控制。各渠道不能仅以 HTTP 200 判断成功，还要解析业务响应；SMTP 成功仅表示服务器接受，不保证进入收件箱。

普通配置表单由渠道 schema 生成；特殊交互可单独组件。目标可有自定义服务地址。Webhook 采用固定 JSON schema_version、event_id、post、matched_tasks（`published_at`与`first_seen_at`统一为ISO 8601 UTC字符串）；允许必要 URL/Header 配置，不执行任意脚本。URL 仅支持 HTTP(S)，禁止凭据泄漏到日志/跨域重定向；自托管内网服务需求通过明确配置处理，不能简单禁止所有内网目标。

## 数据与一致性

核心实体：管理员、会话、网站实例、采集来源、监控任务及规则版本、规范帖子、来源条目、命中记录、通知目标、投递意图、投递尝试、去重标识、来源运行状态。

约束：

1. 唯一 website_id + external_post_id；来源记录另有 source_id + source_item_id。
2. 首版一个网站单来源，但不把 RSS GUID 当全局唯一 ID。
3. 在事务中完成新帖入库、任务命中、目标合并和 outbox 写入，然后提交；网络发送不在数据库事务内执行。无新帖且无基线/缺口/诊断的空轮询仅更新`SourceState`，不重复写入`SourceRun`。
4. 自动投递意图以帖子+目标唯一；命中记录按任务版本留证。任务规则/内容/目标配置变更的快照或版本可追踪。
5. Worker 原子认领、记录租约；崩溃后租约过期可恢复。远端结果未知的重试可能重复，UI 不宣称绝对不重复。
6. 已发送标识和已见标识独立于可读历史。清理正文不允许重建旧投递。
7. 配置/任务变更和摄取并发须有明确事务边界，变更只影响之后发现的帖子。
8. SQLite 设置合理 busy_timeout，可用 WAL；短事务、串行写入协调。单实例数据目录用 VM 本地文件系统，不默认放 NFS/SMB。

M1实现边界：0002_core迁移仅播种NodeSeek网站、默认关闭的官方RSS来源和运行状态，不创建管理员或通知目标。内部Configuration/Ingestion与DeliveryWorker共用BEGIN IMMEDIATE短写事务；迁移也显式开启事务，失败时DDL与迁移号一同回滚。TaskVersion不可变，Post内容首次见到时固定；SeenPost与DeliveredPost独立于可读历史，M3保留策略按下文分批清理普通历史，精简身份账本不随之删除。

任务停用/删除撤销尚未发送的贡献，其他任务仍可合并发送；在途请求保留租约并记录实际结果。目标重新启用不恢复已取消消息。主动停用网站/来源后重建当前基线，进程重启则保留已见状态并处理仍在RSS窗口内的未见帖子；不相交窗口只记“可能缺口”。

Outbox按帖子和目标唯一；每次原子认领有新token和递增尝试号。认领查询使用有界扫描（`LIMIT 64`）并排除当前已有活跃租约的目标，Worker按目标并发派发（默认最多4个不同目标并发，同一目标严格串行），避免慢渠道阻塞其他渠道。过期租约记为结果未知，再按上限恢复；旧token不能覆盖新租约。迟到成功留下独立回执与尝试证据，无新租约时修正终态。默认最多5次，退避5～300秒，Retry-After可延长等待；发送超时10秒、租约30秒。未知状态留下持久uncertain标记，即使后续成功也保留。渠道实现在事务外运行。

SourceRunner接受长生命周期HTTPX客户端，固定周期、不重叠；失败退避10～300秒并尊重Retry-After，状态持久化。M3已在FastAPI生命周期中创建单一Runner/Worker及长生命周期HTTP客户端；默认循环运行但来源关闭，管理接口要求认证。

## M2通知实现契约

通知schema位于notifiers/configs.py，schema的writeOnly字段在读取目标时省略，只返回configured_secrets字段名；更新省略字段保留原值。Webhook URL/Header、Telegram/Bark服务URL与凭据、SMTP登录/发收地址均不回传。自定义HTTP(S)地址允许内网，由管理员明确配置；拒绝userinfo/fragment、Header注入和危险转发Header。不跟随任何重定向、不使用环境代理或服务端Cookie，TLS验证保持开启。HTTPX/httpcore限制至WARNING，避免请求URL/报文调试日志泄密；不存远端错误文本。

0003_notifications增加目标密文及独立目标测试记录。使用cryptography Fernet认证加密整个配置，密文绑定目标ID和渠道；outbox与目标测试保存同样的加密快照和revision。修改目标不回写旧快照，发送边界解密并重新校验；坏钥/坏密文作为永久配置错误。credentials.key在持久化目录，显式创建使用O_EXCL/0600/fsync，加载缺钥不生成。M3已在启动生命周期中独占初始化/加载并校验现有目标；有密文缺钥停止而不生成替代密钥。M4负责含原密钥的备份封装。

HTTP请求有连接3秒/单次I/O 8秒限制，Worker外层10秒；业务响应限64KiB并拒绝压缩。Telegram检查ok及message_id，默认纯文本/不展开链接；Bark使用POST /push并检查code=200。Webhook固定schema_version=1/event_id/post/matched_tasks，默认json_ok要求ok为true，status模式由管理员显式选择以2xx确认接受；未知响应不伪称成功。事件ID及Idempotency-Key在自动重试保持不变。429/5xx可有限重试，其他明确拒绝永久失败，读写超时/不完整响应为未知；业务Retry-After与HTTP头均可延长等待。

SMTP使用标准库smtplib在线程执行，默认隐式TLS，也可选STARTTLS，plain须allow_insecure明确允许；不降级TLS校验。每目标单一收件人避免部分接受，4xx临时/5xx永久，DATA阶段断连为未知。已接受后关闭连接失败不撤销成功；线程取消后仍持发送锁直到socket关闭，避免同时重试。邮件Message-ID稳定，但不承诺接收端去重或进入收件箱。

统一纯文本模板含标题/原帖链接/作者/版块/UTC时间/命中任务；摘要默认关，可限长。Telegram最多4000个UTF-16单位、Bark短文本1800；过长字段带省略号，Webhook保留完整任务列表。`TargetTesting`仅显式调用，禁用目标亦可手动测试；每次新事件和独立记录，不进入自动帖子账本；超时/中断保留未知，不自动重试。M3的D07使用独立ManualDeliveryAttempt，不能用目标测试冒充。

协议依据：[Telegram Bot API](https://core.telegram.org/bots/api#sendmessage)、[Bark服务端API](https://github.com/Finb/bark-server/blob/master/docs/API_V2.md)、[Python SMTP](https://docs.python.org/3.12/library/smtplib.html)、[Fernet](https://cryptography.io/en/latest/fernet/)。M2只用合成样本验证，不作真实接收承诺。

## 调度与恢复

10秒为候选默认配置：用户提出且助手建议采纳，非官方限频保证，需保留来源说明。所有任务共享采集；固定周期不重叠、不补跑错过的全部定时 tick。网络失败指数退避并设置上限；429遵循 Retry-After；解析失败不能当作空列表成功。支持少量抖动，避免多个部署同时请求。

实施默认建议：通知最多自动尝试5次，使用有上限的退避；可重试状态与配置错误区分。具体间隔集中配置并测试，不散落常量。

健康检查分离进程存活与业务健康：RSS暂不可达不应触发容器不断重启。启动执行迁移、验证数据目录/密钥、恢复任务，再启动调度。正常退出停止新认领，给予在途任务有限完成时间。

## 部署与凭据

镜像使用非 root，多阶段构建，不带测试依赖、真实样本/凭据。数据卷保存 SQLite 与恢复所需材料；环境变量负责启动基础参数，日常设置在 Web。

首版无初始化令牌；服务端保护管理员唯一性。会话/CSRF/登录限速、密码哈希、加密凭据、日志脱敏。允许指定可信反代，不能信任任意 X-Forwarded-*。

备份使用 SQLite 一致性备份机制；包含凭据时连同所需密钥安全封装并明确提示。普通配置导出默认不含凭据。恢复需要管理员重新验证，停止后台写入并先校验版本；迁移失败不得继续运行。

## M3认证实现契约

0004_authentication新增administrators、browser_sessions和auth_throttle。管理员固定id=1且有CHECK约束；在BEGIN IMMEDIATE中检查并创建，账号存在即关闭初始化，不维护可能失配的独立开关。密码使用Argon2id（19MiB、2轮、并行度1，随机盐）；哈希在线程池中执行，不占数据库写事务。用户名修剪首尾空白，密码不修剪/截断，默认6～128字符。

会话为32随机字节的opaque令牌，数据库只存SHA-256摘要、管理员引用、到期时间和Secure绑定。匿名30分钟、认证7天绝对有效期，登录轮换并撤销旧会话，退出删除服务端记录；重启不丢会话。新建时清理到期记录，并将匿名/认证会话分别限制为128/32个。Cookie为HttpOnly/SameSite=Strict、Path=/、无Domain；HTTPS设置Secure，HTTPS会话拒绝HTTP回放。

GET /api/auth/state返回会话派生的HMAC-CSRF值及认证状态；setup/login/logout与后续管理写操作要求X-CSRF-Token，另检查出现的Origin与Sec-Fetch-Site。无跨域CORS授权；错误不回显输入，API设置no-store。管理路由统一复用require_administrator依赖；已接入目标、任务和纯规则试匹配API。初始化/登录共用持久全局预算10次/60秒（含成功），错误用户名也执行密码校验，不保留客户端IP或密码样本。

Uvicorn入口不解析代理头；应用ProxyHeadersMiddleware只信任SEEKBELL_TRUSTED_PROXIES显式IP/CIDR，默认空，拒绝通配符/全网段。代理须保留Host并覆盖协议头，不信任Forwarded/X-Forwarded-Host。通过直接HTTP、真实ASGI HTTPS和模拟可信反代测试Cookie及CSRF；PVE真实反代验证仍待M5。

选型依据：[OWASP密码存储](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)、[CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)、[会话](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)、[Uvicorn代理](https://www.uvicorn.org/deployment/)。

## M3配置管理契约

/api/manage在路由层统一要求管理员，所有写方法与POST预览/历史试匹配均校验CSRF。通知配置只允许四个内置渠道，任务只允许nodeseek，不开放mock/自定义网站。请求校验不回显输入；返回值使用明确的安全投影，不返回目标密文、秘密值或底层异常。

Configuration复用原短写事务，目标update在事务内校验expected_revision，任务update校验expected_version，失配返回409；启停与规则编辑分开，避免陈旧规则编辑重新启用已暂停任务。原规则版本、命中和outbox快照不可变，暂停/删除继续使用既有贡献撤销语义。复制是一个默认暂停的新草稿，保存后生成独立ID。

服务端返回规范化规则及同一explain/evaluate结果。历史试匹配仅读取nodeseek本地Post最近1～100条，给出实际样本数、总数及样本时间边界；不写规则、SeenPost/DeliveredPost/RuleHit/outbox，也不访问网络。摘要None与空字符串保持区别；帖子链接重新构造为固定NodeSeek HTTPS路径，外部字段按文本呈现。

启动在数据目录进程锁内加载/独占创建credentials.key，检查目标与outbox/目标测试的加密快照；有密文缺钥、坏钥/权限/配置时停止并释放锁。当前已接入Configuration与采集/投递生命周期，目标测试及D07已接入受保护的显式Web操作。网页管理401统一恢复会话入口，多请求合并恢复，组件卸载清空敏感草稿；无浏览器持久凭据。

## M3调度与运行页契约

ApplicationRuntime在迁移、认证与密钥检查完成后构造一套RSS客户端、NotifierRegistry、SourceRunner、DeliveryWorker和历史维护循环。SEEKBELL_BACKGROUND_ENABLED默认true，false关闭采集/投递/维护循环，不禁止管理员显式连接测试。所有工作都在数据目录实例锁生命周期内；退出置stop/wake，给予循环15秒宽限，取消剩余网络等待并保留租约恢复证据，然后关闭客户端、数据库并释放锁。短SQLite线程任务取消时排空；SMTP沿用socket关闭前持锁语义，不能宣称整个退出过程有15秒硬上限。

意外循环异常只记录固定错误码，不输出异常字符串/参数，退避期间降低readiness（503）但不改变liveness，并以指数退避（5～300秒）自动重启循环，成功完成下一周期后恢复readiness并累计`restarts`计数；普通采集失败只改变来源状态和退避。网站设置提交后唤醒Runner，仍检查持久化next_attempt_at，不回放错过的tick。0005_source_revision为来源新增配置版本，网站与来源启停及频率修改在同一短事务内更新；expected_revision拒绝旧页面，摄取时核对抓取前版本，防止在途响应跨越暂停/恢复边界。

POST /api/manage/site/test要求管理员/CSRF并共用SourceRunner锁；重叠返回409，遵守已有失败退避，15秒请求预算。成功只返回合法数/原始数/安全诊断，不建基线或写帖子；失败保存SourceRun、错误码与退避。URL和适配器固定，不能通过此入口访问其他来源。GET site/overview/content/options均受认证；内容筛选分页及命中原因只读本地表，保留任务原规则版本与软删除证据。链接从正数字ID重建，文本展示限长不改变后端匹配字段。

## M3显式通知与D07契约

0006_manual_deliveries增加manual_delivery_attempts，保存原outbox引用、当前目标加密快照、独立payload/event_id和单次结果。原通知内容保留，标题加“【手动重发】”；不写自动Outbox/DeliveryAttempt/DeliveredPost/SeenPost/RuleHit。只有已结束的自动事件（sent/failed/cancelled）可手动重发，当前目标须启用；事务内核对expected_revision。任务停用/删除不抹去历史，管理员明确重发历史消息不恢复任务贡献。重发成功不修正原自动终态。

目标测试沿用独立TargetTestAttempt，允许测试已停用目标。两个写入口统一要求管理员/CSRF、confirmed严格布尔true与UUID v4 request_id。每个请求ID在短事务中先保存未知结果和加密配置，再在事务外发送，最后写结果。相同ID/资源/快照版本重放只读原结果；跨资源/跨显式类型或与自动事件ID冲突返回409。完成、中断与结果未知都不自动重试；新确认才创建新事件，Webhook Idempotency-Key使用该事件ID。端到端重复仍可能发生。

ApplicationRuntime全局互斥一个显式发送，复用NotifierRegistry，纳入退出宽限/取消与SQLite工作排空，拒绝关闭后新发送。HTTPX/SMTP超时及脱敏沿用M2。GET deliveries/detail按明确安全投影返回原目标名称/渠道/版本、状态、自动尝试及迟到证据；不返回目标密文、秘密、完整wire快照或异常文本。UI目标配置/投递记录双标签，发送前显示接收目标与使用的配置版本并明确确认；过期配置或在途事件拒绝，保留同一确认请求ID用于响应丢失恢复。

## M3系统设置、账号更新与保留契约

0007_settings创建唯一ApplicationSettings（时区初始null、保留期30天、告警目标`alert_target_id`初始null、revision=1、清理统计）及独立AccountThrottle，并为历史时间字段加索引。设置在短事务中核对expected_revision，时区用系统zoneinfo/IANA集合验证、保留天数1～3650、可选`alert_target_id`校验目标存在；配置`alert_target_id`后，后台组件异常、RSS连续失败达5次或发现可能窗口缺口时单次发送系统告警，恢复时单次发送恢复通知。显示值不改变UTC存储或通知快照。前端未设置时取浏览器时区，实例偏好在登录/刷新/设置页读取，所有页面共用格式化函数，导航顺序与URL hash（`#overview`/`#site`/`#tasks`/`#content`/`#targets`/`#status`）同步。

管理员修改必须提供当前密码，新密码可省略且不修剪；用户名沿用可打印1～64字符校验。重新验证使用独立持久每分钟10次预算，不通过登出/刷新重置。Argon2工作在事务外完成，提交时核对原哈希/用户名和会话仍有效，再原子修改并撤销全部认证会话，HTTP删除当前Cookie。login签发前也再次核对已验证的账号和原会话，防止旧校验跨越改密或退出。失败不写账号、错误不回显输入。

SystemSettings.cleanup使用BEGIN IMMEDIATE和有上限的批次，ApplicationRuntime维护循环启动及每60秒调用，每类主记录最多200条，关联尝试/贡献一并清理；手动POST需管理员/CSRF/confirmed=true与当前策略版本。按过期完成的显式记录→确定结束自动outbox及其尝试/贡献→无贡献引用的命中→无outbox保护的Post→SourceRun顺序清理。自动事件只清理sent/failed/cancelled且uncertain=false、无未完成/近期尝试或迟到证据、无剩余手动引用的记录。未知显式结果、未完成自动投递及依赖内容保留。整个批次与统计一同提交，出错回滚，不在网络事务内执行。

SeenPost、DeliveredPost、SourceItem及SourceState与任务版本不参与普通清理；DeliveredPost.event_id是精简回执信息，允许其可读outbox已过期。清理不重新摄取、匹配或发送，不能重置去重。SQLite文件不自动VACUUM，数据大小不宣称同步缩小。系统页说明停服备份恢复维护流程，具体契约见下文M4。

## 私有开发与实机验证（建议路线）

已接入用户创建的私有 GitHub 仓库，实际地址和授权见 DECISIONS。私有 GHCR 镜像仍是建议路线，命名空间及发布权限尚未提供，不能假定公开或发布权限。

PR进行代码检查和容器构建；只有受信任、获授权的流水线发布测试镜像，不能给不受信任 PR 注入发布密钥。待验收镜像标注完整提交 SHA/镜像 digest，页面显示版本。

日常环境与测试环境使用不同 Compose 项目名、端口、数据卷。第一版可先仅测试环境；测试默认关闭实时采集和真实通知。演示数据只存在测试/开发流程，不污染正式状态。

Codex 可在授权 SSH 范围内部署测试环境；没有 SSH 则提供含固定镜像版本的更新命令。不要把 docker socket 暴露给应用用于自更新。

发布 amd64/arm64 镜像；架构构建成功不等于两种架构均已原生实机验证。正式环境不自动升级。回退需结合数据库版本和备份，不能仅更换旧镜像。

## M4 停服备份与恢复契约

`python -m seekbell.backup create|restore ARCHIVE` 是交互维护入口，不提供在线文件覆盖API。全量备份必须重新验证当前管理员密码，持有实例锁，用SQLite backup API快照并校验完整性/外键、当前schema和全部加密目标/历史快照，包含原credentials.key。固定清单/数据库/密钥由scrypt派生的AES-256-GCM整体认证加密，流式I/O，归档0600、临时目录0700；密码不接受命令行/环境变量，非终端输入拒绝。无普通配置导出功能。

恢复验证备份中的管理员密码，要求目标空目录，认证解密后只接受三个固定普通成员；先校验已知数据库版本，再在私有暂存目录迁移及验证全部凭据，撤销浏览器会话后安装。迁移失败不修改现用卷/备份。安装前持久化.restore-in-progress，成功fsync完整数据库/密钥后移除；异常中断保留标记时统一实例锁拒绝服务与维护启动。恢复不会自动停用队列或重建基线，恢复到旧时间可能再次发送，演练须隔离网络。

Compose默认独立测试项目、回环端口、后台关闭，非root只读根文件系统、唯一可写数据卷及临时tmpfs，日志轮换，保留旧卷进行升级回退。备份为匹配的数据库与密钥对；旧镜像不能直接打开升级后的卷，不自动downgrade。GHCR流程只在main手动触发，默认只构建；发布授权与环境审核设置独立于代码。操作命令和限制见DEPLOYMENT。
