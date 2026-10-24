# 技术架构

## 已确认技术栈

后端 Python / FastAPI / Pydantic；前端 TypeScript / Vue 3 / Vite / Naive UI；SQLite；SQLAlchemy / Alembic；HTTPX；feedparser；uv / pnpm。创建项目时查官方兼容说明，锁定实际依赖版本，不无理由更换技术栈。

M0运行基线：Python 3.12、Node 24.22.0、uv 0.13.1、pnpm 10.34.7。直接依赖约束在`pyproject.toml`和`frontend/package.json`，精确解析结果以两个锁文件为准。TypeScript选用5.9.3，满足vue-tsc的声明范围，后续升级需重新检查生态兼容性，不追随所有工具的最新大版本。兼容依据：[FastAPI/Pydantic v2](https://fastapi.tiangolo.com/how-to/migrate-from-pydantic-v1-to-pydantic-v2/)、[Vite Node要求](https://vite.dev/guide/)、[Vue环境要求](https://vuejs.org/guide/quick-start.html)、[Alembic兼容说明](https://alembic.sqlalchemy.org/en/latest/front.html)；执行证据见阶段记录。

模块化单体，单容器、单服务进程、一个持久化数据目录、一个 Web 端口。FastAPI 提供 API 和编译后的前端静态文件。单实例，不支持多副本/多个 Uvicorn worker。启动防止第二个进程重复调度。

建议目录（实现时可小幅调整）：

- backend/seekbell/api：路由、认证、配置校验。
- backend/seekbell/domain：规范化帖子、规则三值判断、投递意图。
- backend/seekbell/sites：NodeSeek/Linux DO内置适配、能力声明、ID/分类映射。
- backend/seekbell/collectors：RSS HTTP 获取与解析。
- backend/seekbell/notifiers：Telegram、Bark、SMTP、Webhook。
- backend/seekbell/services：调度、摄取、匹配、投递、备份。
- backend/seekbell/db：模型/事务；backend/migrations：Alembic。
- frontend：Vue 页面、类型、公共组件。
- tests：合成样本、模拟 HTTP/SMTP、集成测试。
- deploy：Compose 示例；docs：规格、进度、验收；.github/workflows：CI/镜像发布。

M0目录调整：Alembic实际位于`backend/seekbell/migrations`，随Python包一起安装；源码、wheel和容器共用同一路径，不依赖工作目录或外部资源映射。通过`python -m seekbell.db upgrade/current/check`维护数据库，复用应用配置和数据目录进程锁，避免服务运行时并发迁移。初始迁移仅存安装标记，不创建管理员或初始化令牌；管理员在M3原子化创建。

## 模块契约

SiteAdapter 声明标识、能力、采集配置、规范链接、帖子 ID 提取、分类映射。当前注册NodeSeek/Linux DO固定RSS；未来可以接入其他内置网站，但不提前实现主备、TG 会话或网页抓取。

Collector 返回来源条目及采集状态。只处理连接/解析，不运行关键词规则。RSS 使用异步 HTTP 获取；同步解析、大型备份及同步 SMTP 不阻塞事件循环。显式超时、响应大小限制、禁用 XML 外部实体/网络展开、并发上限。M1采用defusedxml先拒绝DTD/实体，再以内存流交给feedparser，避免把输入当URL/文件；解析在线程中执行。RSS请求要求identity编码，限1MiB并拒绝未协商的压缩响应。NodeSeek保留原始版块文字，不虚构稳定分类编号。

RuleEngine 为无网络纯逻辑，输入规范化字段和规则快照，输出 match/no_match/insufficient_data 及结构化原因。前端试匹配与后台执行共用同一后端逻辑。“标题＋摘要”仅检查实际提供的字段，缺摘要时只检查标题；“仅摘要”与显式作者/版块限制仍保留缺失字段的三值判断。历史判定不追溯重写。

Notifier 声明配置 schema、敏感字段、校验与发送能力，返回成功/临时错误/永久错误/结果未知以及可用 Retry-After。重试由投递管理统一控制。各渠道不能仅以 HTTP 200 判断成功，还要解析业务响应；SMTP 成功仅表示服务器接受，不保证进入收件箱。

普通配置表单由渠道 schema 生成；特殊交互可单独组件。目标可有自定义服务地址。Webhook 采用固定 JSON schema_version、event_id、post、matched_tasks；允许必要 URL/Header 配置，不执行任意脚本。URL 仅支持 HTTP(S)，禁止凭据泄漏到日志/跨域重定向；自托管内网服务需求通过明确配置处理，不能简单禁止所有内网目标。

## 数据与一致性

核心实体：管理员、会话、网站实例、采集来源、监控任务及规则版本、规范帖子、来源条目、命中记录、通知目标、投递意图、投递尝试、去重标识、来源运行状态。

约束：

1. 唯一 website_id + external_post_id；来源记录另有 source_id + source_item_id。
2. 首版一个网站单来源，但不把 RSS GUID 当全局唯一 ID。
3. 在事务中完成新帖入库、任务命中、目标合并和 outbox 写入，然后提交；网络发送不在数据库事务内执行。
4. 自动投递意图以帖子+目标唯一；命中记录按任务版本留证。任务规则/内容/目标配置变更的快照或版本可追踪。
5. Worker 原子认领、记录租约；崩溃后租约过期可恢复。远端结果未知的重试可能重复，UI 不宣称绝对不重复。
6. 已发送标识和已见标识独立于可读历史。清理正文不允许重建旧投递。
7. 配置/任务变更和摄取并发须有明确事务边界，变更只影响之后发现的帖子。
8. SQLite 设置合理 busy_timeout，可用 WAL；短事务、串行写入协调。单实例数据目录用 VM 本地文件系统，不默认放 NFS/SMB。

M1实现边界：0002_core迁移仅播种NodeSeek网站、默认关闭的官方RSS来源和运行状态，不创建管理员或通知目标。内部Configuration/Ingestion与DeliveryWorker共用BEGIN IMMEDIATE短写事务；迁移也显式开启事务，失败时DDL与迁移号一同回滚。TaskVersion不可变，Post内容首次见到时固定；SeenPost与DeliveredPost独立于可读历史，当前没有自动清理策略。

任务停用/删除撤销尚未发送的贡献，其他任务仍可合并发送；在途请求保留租约并记录实际结果。目标重新启用不恢复已取消消息。主动停用网站/来源后重建当前基线，进程重启则保留已见状态并处理仍在RSS窗口内的未见帖子；不相交窗口只记“可能缺口”。

Outbox按帖子和目标唯一；每次原子认领有新token和递增尝试号。过期租约记为结果未知，再按上限恢复；旧token不能覆盖新租约。迟到成功留下独立回执与尝试证据，无新租约时修正终态。默认最多5次，退避5～300秒，Retry-After可延长等待；发送超时10秒、租约30秒。未知状态留下持久uncertain标记，即使后续成功也保留。渠道实现在事务外运行。

SourceRunner接受长生命周期HTTPX客户端，固定周期、不重叠；失败退避10～300秒并尊重Retry-After，状态持久化。当前只有显式离线演示构造Runner/Worker，FastAPI生命周期尚不启动业务调度；M3接入认证、管理和生命周期后再启用，不暴露未认证配置接口。

## M2通知实现契约

通知schema位于notifiers/configs.py，schema的writeOnly字段在读取目标时省略，只返回configured_secrets字段名；更新省略字段保留原值。Webhook URL/Header、Telegram/Bark服务URL与凭据、SMTP登录/发收地址均不回传。自定义HTTP(S)地址允许内网，由管理员明确配置；拒绝userinfo/fragment、Header注入和危险转发Header。不跟随任何重定向、不使用环境代理或服务端Cookie，TLS验证保持开启。HTTPX/httpcore限制至WARNING，避免请求URL/报文调试日志泄密；不存远端错误文本。

0003_notifications增加目标密文及独立目标测试记录。使用cryptography Fernet认证加密整个配置，密文绑定目标ID和渠道；outbox与目标测试保存同样的加密快照和revision。修改目标不回写旧快照，发送边界解密并重新校验；坏钥/坏密文作为永久配置错误。credentials.key在持久化目录，显式创建使用O_EXCL/0600/fsync，加载缺钥不生成。M3负责在受保护生命周期中初始化/加载，M4负责含原密钥的备份封装。

HTTP请求有连接3秒/单次I/O 8秒限制，Worker外层10秒；业务响应限64KiB并拒绝压缩。Telegram检查ok及message_id，默认纯文本/不展开链接；Bark使用POST /push并检查code=200。Webhook固定schema_version=1/event_id/post/matched_tasks，默认json_ok要求ok为true，status模式由管理员显式选择以2xx确认接受；未知响应不伪称成功。事件ID及Idempotency-Key在自动重试保持不变。429/5xx可有限重试，其他明确拒绝永久失败，读写超时/不完整响应为未知；业务Retry-After与HTTP头均可延长等待。

SMTP使用标准库smtplib在线程执行，默认隐式TLS，也可选STARTTLS，plain须allow_insecure明确允许；不降级TLS校验。每目标单一收件人避免部分接受，4xx临时/5xx永久，DATA阶段断连为未知。已接受后关闭连接失败不撤销成功；线程取消后仍持发送锁直到socket关闭，避免同时重试。邮件Message-ID稳定，但不承诺接收端去重或进入收件箱。

统一纯文本模板含标题/原帖链接/作者/版块/UTC时间/命中任务；摘要默认关，可限长。Telegram最多4000个UTF-16单位、Bark短文本1800；过长字段带省略号，Webhook保留完整任务列表。`TargetTesting`仅显式调用，禁用目标亦可手动测试；每次新事件和独立记录，不进入自动帖子账本；超时/中断保留未知，不自动重试。手动重发自动消息属于M3（D07），不能用目标测试冒充。

协议依据：[Telegram Bot API](https://core.telegram.org/bots/api#sendmessage)、[Bark服务端API](https://github.com/Finb/bark-server/blob/master/docs/API_V2.md)、[Python SMTP](https://docs.python.org/3.12/library/smtplib.html)、[Fernet](https://cryptography.io/en/latest/fernet/)。M2只用合成样本验证，不作真实接收承诺。

## 调度与恢复

10秒为候选默认配置：用户提出且助手建议采纳，非官方限频保证，需保留来源说明。所有任务共享采集；固定周期不重叠、不补跑错过的全部定时 tick。网络失败指数退避并设置上限；429遵循 Retry-After；解析失败不能当作空列表成功。支持少量抖动，避免多个部署同时请求。

实施默认建议：通知最多自动尝试5次，使用有上限的退避；可重试状态与配置错误区分。具体间隔集中配置并测试，不散落常量。

健康检查分离进程存活与业务健康：RSS暂不可达不应触发容器不断重启。启动执行迁移、验证数据目录/密钥、恢复任务，再启动调度。正常退出停止新认领，给予在途任务有限完成时间。

## 部署与凭据

镜像使用非 root，多阶段构建，不带测试依赖、真实样本/凭据。数据卷保存 SQLite 与恢复所需材料；环境变量负责启动基础参数，日常设置在 Web。

首版无初始化令牌；服务端保护管理员唯一性。会话/CSRF/登录限速、密码哈希、加密凭据、日志脱敏。允许指定可信反代，不能信任任意 X-Forwarded-*。

备份使用 SQLite 一致性备份机制；包含凭据时连同所需密钥安全封装并明确提示。普通配置导出默认不含凭据。恢复需要管理员重新验证，停止后台写入并先校验版本；迁移失败不得继续运行。

## 私有开发与实机验证（建议路线）

已接入用户创建的私有 GitHub 仓库，实际地址和授权见 DECISIONS。私有 GHCR 镜像仍是建议路线，命名空间及发布权限尚未提供，不能假定公开或发布权限。

PR进行代码检查和容器构建；只有受信任、获授权的流水线发布测试镜像，不能给不受信任 PR 注入发布密钥。待验收镜像标注完整提交 SHA/镜像 digest，页面显示版本。

日常环境与测试环境使用不同 Compose 项目名、端口、数据卷。第一版可先仅测试环境；测试默认关闭实时采集和真实通知。演示数据只存在测试/开发流程，不污染正式状态。

Codex 可在授权 SSH 范围内部署测试环境；没有 SSH 则提供含固定镜像版本的更新命令。不要把 docker socket 暴露给应用用于自更新。

发布 amd64/arm64 镜像；架构构建成功不等于两种架构均已原生实机验证。正式环境不自动升级。回退需结合数据库版本和备份，不能仅更换旧镜像。

## 单一正式管理界面（2026-10-23）

用户授权结构清理后，仅维护frontend/index.html → src/main.ts → Bootstrap.vue → App.vue一个正式入口。App负责既有Hash路由、认证跳转、导航与未保存保护；pages集中实际页面，components放共用控件，styles保持批准视觉。store.ts只接真实认证和配置API，history/overview/readCache等服务模块维持原契约；model/shared/websites为实际表单类型与目录定义。

删除独立原型入口/构建、重复概览/内容/通知/设置页、演示store、浏览器演示账户与备份、前端JS规则试算及组件注入/构建别名。所有规则试匹配仍由后端RuleEngine计算；预览仍调用正式预览API与发送formatter，不维护额外离线JSON模板。既有批准UI与统计口径不变，统计数字不增加点击。

仅构建frontend/dist，开发/CI/容器共用该产物。浏览器套件使用同一正式界面，scripts/run_web_smoke.py在一次性临时库配合被动或合成运行器验证，退出清理；不安装测试版产品、不读取正式库。backend/services中的离线demo命令是核心/调度/备份的合成验证工具，继续供CI和容器检查使用。旧原型说明与交接已[归档](history/2026-10-23-原型退役前说明.md)，不是第二套运行指南。

useRemote初读/非搜索立即请求，仅明确的搜索字段变化防抖180ms。同查询保留快照，内容/通知列表及概览等显式keepPrevious跨条件保留，并以stale禁用旧结果交互；scope约束告警详情只能保留同一事件分页，不借用其他对象。新响应原子替换数据/统计/分页。readCache最多20项，以数据revision标记写后过期、session revision处理身份失效；写后保留旧快照并刷新，退出/失效立即清空。迟到响应同时检查generation、数据和会话revision。ReadRegion统一稳定占位、200ms覆盖反馈、失败重试及旧快照交互隔离，取代分散的高度补丁；概览仅允许标记的查询控件继续操作。编辑草稿和密码不使用只读缓存。列表后端保留first_seen_at主排序，同批以published_at倒序（缺失置后）及稳定身份收尾；发现日过滤不改。

usePopup把按钮和portalled面板作为单一边界，统一外部/焦点离开关闭；DateFilter与AppSelect复用，不叠加库捕获阶段clickoutside。AppSelect归并15处原生选择与旧WebsiteSelect，以preventScroll聚焦、仅滚动菜单选项，保留不同场景尺寸和类型；Bootstrap的abstract NConfigProvider禁用组件库全局preflight，防止首次挂载改写body字体。Notifications外壳持有标题与NotificationTabs，内容按菜单/记录键隔离；Settings内部换分类保留外壳并清空获准放弃的草稿，避免跨页面KeepAlive敏感表单。

2026-10-23补修：recordQueries集中通知记录的默认/筛选参数、缓存键及加载器，预读与Records使用同一契约。readCache.fetchRead按会话/数据revision/查询键合并在途读取；所有useRemote读取共用它，清会话时清在途索引并拒绝旧请求回填。Notifications区分请求目的地与实际展示对象，只在目标列表/选项完成后整体提交；从冷预读交接的首次useRemote消费已完成快照，后续筛选/重试仍正常请求。只读区域占位和反馈同时延迟200ms，原有身份/写后失效规则保留。

## 网站库与实例

src/websites.ts声明已实现适配器及能力，服务端WebsiteInstallation表示用户安装关系，Website/Source保留适配器身份与历史锚点。新库没有安装实例；当前目录含NodeSeek和Linux DO。已有任务固定网站，有未删除任务依赖时阻止移除；无依赖时移除安装配置、保留历史并按正式服务契约取消待发送动作。网站库使用居中原生dialog，安装完成关闭；实例配置仍右侧面板，支持键盘/未保存保护，手机全屏。工作空间名称/说明由SQLite偏好保存并显示在侧栏，不读取旧演示浏览器数据。

## M3首个真实接入契约（2026-10-20）

2026-10-20首个接入沿用批准v0.4页面与样式，正式状态来自/api/manage/workspace，不迁移演示账号/浏览器备份。2026-10-23已收敛为上节单入口结构；下文保留各接入阶段的后端契约和证据，完成范围以PROJECT_STATE为准。

0004_management增加单例Administrator、LoginSession、WebsiteInstallation、WorkspacePreferences；TaskVersion增加最多160字符description。SQLite迁移入口持BEGIN IMMEDIATE后识别空库/既有迁移版本：空库安装实例表为空，从既有M0/M1/M2升级保留原网站实例。适配器身份行不是用户已安装实例；移除实例仅删除安装关系、禁用来源并重建后续基线，保留历史身份。活跃任务依赖阻止移除；创建任务在同一配置写事务检查安装关系。任务所属网站固定，备注随规则版本留证。

初始化的管理员和会话同事务创建，管理员主键限制id=1，不使用初始化令牌。密码为独立随机盐scrypt(N=2^17,r=8,p=1)。不透明随机会话令牌仅以SHA-256摘要存入服务端，12小时过期，退出删除。Cookie为HttpOnly/SameSite=Strict，可信HTTPS请求标Secure。登录/初始化使用进程密钥签名的预会话CSRF，管理写入验证会话CSRF及Origin；不信任未配置的代理。API no-store，验证错误不包含输入，SQL日志隐藏参数。认证来源每分钟10次/全局30次，内存限速且哈希串行；重启重置限速，不是多副本方案。参考[OWASP密码存储](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)及[CSRF](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)。

M3配置API复用Configuration及CredentialVault，启动创建/加载私有密钥；已有密文缺钥/错钥直接停止。目标新增/编辑/启停和配置读写已接入，留空敏感字段保留，不回显值；目标更新与停用取消在同一事务。为满足任务至少一个已配置目标的规格，首闭环支持四渠道配置，但不启用测试发送或采集/投递生命周期。规则试算使用原RuleEngine。工作空间名称/说明单例存储，不扩展多用户或多工作空间。

本子阶段不宣称M3完成：正式概览仅配置数量，历史/投递/统计、管理员修改、目标删除/测试及备份/保留/告警仍待接入，不执行模拟成功。离线核心服务维持已有语义；SourceRunner/DeliveryWorker尚不由FastAPI启动。检查与复现见本阶段证据及README。


## M3历史查询与判定快照（2026-10-20，第二子阶段）

接续首闭环，正式入口现已接内容/判定、自动投递及独立目标测试的只读历史。0005_history新增TaskEvaluation（task_id/task_version/website_id/external_post_id四元主键、三值结果/原因/时间）及Post.baseline可空列，和新帖子/RuleHit/outbox同事务保存。基线不匹配，重复摄取不重写。旧baseline保持NULL，不回填缺失负面判定；旧RuleHit与新结果按四元键去重读取，不调用当前规则重算。TaskEvaluation属于普通历史，未来清理不得影响SeenPost/DeliveredPost精简账本。

services/history.py仅数据库读取，api/history.py复用管理员会话/no-store。总数、聚合和分页使用显式BEGIN的WAL读快照，不获取BEGIN IMMEDIATE写锁；固定时间+身份排序，默认20/最大100条。内容按首次发现、意图按建立、测试按开始日期，IANA时区午夜到次日午夜处理DST。列表只返回摘要和少量任务标签；判定、关联投递、尝试与任务快照均分页。详情链接使用网站/帖子复合身份的规范base64url键。

结果聚合为命中优先、其次信息不足、其次不命中；无判定的基线/无适用任务与旧版本未记录结果明确区分。按任务筛选时仅使用该任务的历史结果。规则名称/版本/原因取不可变TaskVersion和判定；目标/消息名取outbox快照，删除或改名不重写。uncertain独立于投递状态，sent仍可标为曾未知；尝试和迟到结果分别展示，读接口不自动过期租约或调度。Post清理不影响outbox消息快照与回执读取。

读取按白名单构建DTO，不返回目标密文/连接字段或lease_token；HTML仍为文本，原帖链接通过NodeSeek身份校验后规范化。查询失败、空结果、缺失记录分开；新查询及组件卸载丢弃旧响应。正式组件通过Bootstrap注入，独立模拟入口保持隔离。测试合成历史只在scripts/run_web_smoke.py --history的临时库/本机8012生成，不提供产品种子接口；应用生命周期仍不启动采集/投递。细节、命令和证据见[本阶段记录](history/2026-10-20-历史查询接入.md)。

## M3概览与管理员修改（2026-10-20，第三子阶段）

2026-10-22原UI恢复：概览额外返回当前未删除任务的tasks统计，命中按同一滚动窗口/判定账本聚合，最近命中按窗口终点前仍保留证据取最大时间；已删除任务继续影响历史总数但不占当前任务行，新任务明确返回0/null。仍在同一只读快照内，无网络/写入。设置恢复原四标签，Preferences以既有四个API保存；每个成功响应分别更新本地基线与revision，后续请求失败保留剩余草稿，重试不重放已经成功的写入；旧保留/时区/告警深链接保留，独立状态/告警记录从原说明栏访问。


GET /api/manage/overview?range=24h|7d复用认证/no-store与显式BEGIN只读快照。UTC滚动窗口左闭右开，分别24个一小时桶、7个24小时桶；显示时区仅负责时间格式，不将滚动24小时冒充日历日。首次发现数限仍保留的Post；命中/信息不足取判定账本，兼容旧RuleHit且按四元键去重，包含已删除任务及历史版本。趋势/最近5条与汇总同窗，最近名称取TaskVersion，内容已清理时明确无原文入口。不会访问网络或执行规则。

2026-10-22采集卡补充：同一只读快照返回today的保存时区/自然日起点/快照终点，以及每来源配置间隔、本日首次发现数和最近30次实际SourceRun。today_posts按SeenPost.first_seen_at左闭右开分网站统计，含首次基线发现，独立于可读Post保留和上方滚动窗口；默认无偏好时UTC。自然日起点复用IANA日期边界以处理夏令时，不用固定UTC偏移。最近记录限定快照终点之前，利用既有source_id索引按持久化整数ID倒取30条后正序展示；按实际写入顺序而非可能回拨的时钟排序。显式SourceProbe不混入采集条；未知status只返回unknown，不暴露原值/诊断。无需迁移，不改变采集/规则/队列语义。首次发现账本为耐久身份记录，查询仅手动刷新概览时执行。真实时间/当日统计不受前端选中卡片影响，多站切换仅为本页展示状态。

渠道确认接受按DeliveredPost.delivered_at统计帖子×目标唯一回执，重试/迟到结果不重复计数，不包含独立目标测试，不推断进入收件箱。当前队列及待关注使用全部保留Outbox，不跟随窗口：failed/retry/uncertain取并集，曾未知即便后续sent仍保留。来源仅列安装实例对应的数据库状态（最后尝试/成功、连续失败、可能缺口）；配置启用与运行状态分开，应用生命周期仍未启动采集/发送。

PUT /api/auth/administrator接受username、current_password及可选new_password，复用会话CSRF/Origin、认证限速与串行scrypt；当前密码错误400、会话失效401、格式或无修改422。新用户名沿用3–32位ASCII字母/数字/下划线/短横线，新密码8–128字符；省略新密码保留密码。昂贵哈希在写锁外，写事务再次核对会话存在/过期、CSRF及凭据哈希，原子更新单例管理员、删除全部旧会话并建立新Cookie/CSRF。仅改用户名也换随机盐，防止改名往返后旧凭据验证继续生效；登录在哈希后写事务重查用户名/哈希，阻止密码修改竞态重新发出旧密码会话。无需新增迁移。

正式设置等待服务端成功后才同步账号并清空密码草稿，错误保留编辑、支持未保存保护，不写浏览器持久存储。浏览器统计与管理员表单测试仍复用history临时库；固定时钟只通过测试入口依赖覆盖，不提供生产时间参数或模拟数据开关。接口口径、自动证据及未完成范围见[阶段记录](history/2026-10-20-概览与管理员接入.md)。

## M3独立通知操作（2026-10-20，第四子阶段）

应用生命周期创建/关闭NotifierRegistry，供受保护的显式测试/重发使用，仍不启动SourceRunner或DeliveryWorker。GET /api/manage/targets/{id}/test-preview与/deliveries/{id}/resend-preview只返回目标名称/渠道/版本及消息标题；POST对应/test、/resend要求会话CSRF/Origin、request_id UUID和确认的目标revision。仅支持四种已配置渠道；目标测试允许暂停目标，重发要求目标启用、原意图为sent/failed/cancelled，避免与pending/retry/leased自动投递并行。确认后配置版本变化返回409，界面需重新打开确认。

沿用TargetTesting的先持久化后网络、单次10秒上限及未知留证，新增ConfiguredTargetTesting验证入口和ManualSending。每次界面操作生成随机UUID，结果响应丢失后的重试沿用同一UUID：记录存在时返回已有结果，不再次发送；同一UUID绑定原目标/原投递，不能用于另一对象。SQLite写事务串行检查和建立记录，覆盖并发重复请求；记录存续期间实现此幂等，不承诺渠道端exactly-once。进程内显式操作最多2个并发，满额429，未建立新记录。取消/退出/重启中断可留下finished_at为空的unknown，刷新可读，绝不自动重试或把未知当成功。SMTP线程和HTTP渠道沿用M2边界。

0006_manual_delivery仅增加manual_deliveries及开始/目标/来源索引；保存原自动事件ID、当前目标的加密配置快照、原消息快照、开始/完成时间及结果。原ID不是外键，原自动可读历史清理不破坏独立留证；目标身份仍为外键。重发使用当前目标配置及原消息内容/任务快照，生成新消息事件ID，不重写原outbox、attempt、贡献、SeenPost或DeliveredPost，不重新执行规则；不会因手动成功修改自动去重，不进入自动队列或重试。明确接受/拒绝/临时错误/未知均单独记录。

GET /api/manage/history/manual及/{id}复用只读快照、分页/日期/目标/状态/目标名筛选；支持source_event_id查询关联记录。详情含当前操作时目标名称/配置版本、消息/任务快照分页和原记录入口，只按白名单返回，无密文/地址/租约。概览回执指标明确为自动投递，独立测试与手动重发不计入。目标列表/确认弹窗使用正式页面和共享组件。弹窗确认前无发送，取消不改变数据，未知明确提示可能重复；普通HTTP也可生成操作UUID，不依赖secure-context的randomUUID。

浏览器发送验证使用独立--sending临时库/8013及测试依赖覆盖，全部渠道替换为合成Notifier，产品无模拟渠道开关；正常生产端只在管理员确认POST时调用真实适配器。离线CLI演练增加显式操作，仍只用临时库、合成配置及模拟发送。检查、授权和限制见[阶段证据](history/2026-10-20-通知测试与手动重发.md)。

## M3服务端运行生命周期（2026-10-20，第五子阶段）

FastAPI lifespan在数据目录实例锁内完成迁移/密钥校验，再建立唯一Runtime：一个NodeSeek SourceRunner、一个DeliveryWorker，共享既有NotifierRegistry，线程化SQLite操作。首版不创建多进程/副本或任务级采集器；初始化前不采集/发送，来源还需已安装实例、网站及来源启用。空库仍无网站，启用后首次成功仅建立基线；关闭浏览器或退出登录不停止服务，进程重启保留初始化/已见/回执、退避和队列。无需新增迁移。

SourceRunner的持久next_attempt_at决定网络频率，循环每秒检查启停/配置，不因旧3600秒间隔长睡眠；跳过未到期轮次，不补抓错过的时刻、不重叠请求。成功采集/入库后按当前间隔排下次；修改正常来源间隔按last_attempt_at重排，缩短可及时生效、延长不会先按旧短间隔额外抓取。失败已有退避不因改频率或重新启用而缩短，更长间隔可延后。RSS总获取/解析等待上限15秒，沿用1MiB、无重定向/环境代理和固定官方URL，错误落来源状态/退避，不误记成功空源。暂停后恢复重建基线；仅重启不重建。网站暂停停止新采集，已生成消息仍按任务/目标和原贡献规则处理。

DeliveryWorker自行认领、发送、完成与有限重试，沿用同帖×目标唯一、不可变快照、租约及未知留证。后台和显式操作共享真实渠道实例，保持SMTP发送锁。停止先设置stop、唤醒等待并等待在途轮次；16秒宽限后取消未完成actor，未完成自动认领保留租约/尝试，重启至租约过期后记unknown并按原政策恢复，不能伪称撤回或exactly-once。统一database_call屏蔽单次取消、等待SQLite线程完成，再关闭RSS/渠道客户端、dispose引擎并释放实例锁；因此16秒不是强杀数据库线程的硬截止。纯RSS解析线程不持数据库或发通知。

来源HTTP/解析可预期错误只影响来源；actor意外退出/异常则置failed、停止另一actor且不在进程内盲目重启。日志只记固定collection/delivery标签与代码，不记录异常文本、参数、URL或凭据。GET /api/manage/runtime返回active/status/code，workspace/overview也携带实际进程状态，/health/ready同时检查数据库和两个actor；actor失效503，/health/live仍报告进程存在。running表示循环存活，不替代外部RSS/渠道健康，来源错误/退避另行显示。前端每5秒仅刷新轻量运行状态，不轮询配置覆盖编辑草稿；概览仍手动刷新历史统计，新增下次可尝试时间。

测试默认以构造依赖隔离旧CRUD/历史用例，独立runtime用例使用真实Runtime和MockTransport/模拟Notifier，产品无关闭后台/模拟结果环境开关。8014浏览器临时服务在真实10秒间隔中关闭浏览器、停止所有API轮询，再观察后台新投递；生产默认构造与Rootless镜像运行另有检查。runtime_demo是独立临时库/合成服务演练，和日常数据无关。细节及证据见[本阶段记录](history/2026-10-20-后台生命周期接入.md)。


## M3管理操作补全（2026-10-20，第六子阶段）

0007_management_operations给NotificationTarget增加deleted_at，删除保留身份与已有不可变快照，仅清空当前密文、禁用并提升版本。Configuration.delete_target在BEGIN IMMEDIATE中读取所有未删除任务的当前版本。2026-10-22获批删除流程增加只读GET /api/manage/targets/{id}/delete-preview：仅返回失去唯一通知目标的任务名称/状态，确认摘要绑定目标版本、全部当前任务依赖/版本/启停及相关告警版本。DELETE可携带confirmation；事务内重新核对，变化则409且不写。确认后为所有关联任务建立新版本并移除此目标，规则/名称/备注不变；没有剩余目标的任务暂停，其余保持状态，旧版本不改。无目标任务重新启用被拒，重新配置目标后可恢复。未携确认的旧API调用仍对依赖返回409，不静默拆关联。新建/修改任务与删除使用同一串行写事务，防止悬空依赖。删除取消pending/retry；leased标cancel_requested，保留租约和在途/迟到接受回执。当前目标列表/概览排除已删除；配置更新、重新启用、新测试/重发拒绝已删除目标。已建立显式操作可完成或沿用ID查询，不重复发送；删除不能撤回在途消息。最后一个当前配置删除后，启动仍检查历史密文并要求原密钥，不能静默换钥。

POST /api/manage/rules/history接受内置website_id、当前草稿Rule及1–100条上限。仅在显式BEGIN只读快照内统计本地Post，并按first_seen_at和身份倒序取最近样本（包括基线），通过纯RuleEngine试算。返回本地总数、样本数、首次发现时间范围和逐条三值原因/警告；缺失摘要与空摘要保持不同。不补抓网页，不引用旧判定冒充当前草稿结果，不保存规则、判定/命中或身份/回执，不触碰队列。前端20/50/100选择、空历史/错误与过期草稿响应分别处理；模拟入口维持合成样本。

GET/POST /api/manage/websites/nodeseek/connection-test复用认证和CSRF。POST接受空对象，拒绝额外URL配置；使用Runtime持有的同一个SourceRunner锁和RSS客户端，15秒获取/解析等待、1MiB、固定官方地址、不跟随重定向/环境代理。暂停/未到期的调度轮次在锁外只读检查，真正到期后锁内再次核对状态；显式检查与正式采集绝不重叠。来源忙409，间隔/退避429并带Retry-After。未安装或后台未运行拒绝操作。

SourceProbe每来源仅存最近一次测试的开始/完成时间、结果/固定诊断码、有效条目数和下次可测试时间；发请求前先持久化unknown，中断不伪称成功。它不写SourceState/SourceRun、Post、基线/命中或账本；网站移除保留锚点和独立限频，重新添加不能绕过。

2026-10-21按用户明确要求分离正常计时：后台遵守SourceState中的采集周期；显式测试使用独立2秒防连点，不服从成功采集的next_attempt_at/last_attempt_at，也不随保存的监控间隔变化。成功测试不影响后台下次采集时间；仍使用同一个来源锁，请求在途时拒绝重叠，但不预约或等待下一轮周期。失败继续保留SourcePolicy/Retry-After退避，测试和采集互相遵守真实错误等待。概览仅合并测试失败退避，不合并成功测试冷却；GET测试时间合并测试独立冷却和正式采集失败退避。旧成功测试记录即使存有旧的长周期，也按finished_at/started_at+2秒重新解释，无需迁移；失败记录保留既有退避。测试成功不清除正式采集故障或冒充采集成功，不改变正常监控节奏。结果刷新可读，Runtime停止时join/cancel在途显式检查，再关闭客户端/数据库。

管理操作浏览器验证使用独立--operations临时库/8015：实际锁/采集器配MockTransport，投递actor隔离，显式通知服务由测试依赖替换。产品无新增模拟开关。证据与命令见[本阶段记录](history/2026-10-20-管理操作接入.md)。


## M3保留策略与历史清理（2026-10-20，第七子阶段）

0008_retention新增单例RetentionPolicy：days（1–365，默认30）、revision、next_run_at、last_run_at及last_counts；只修改保留天数时提升版本。GET/PUT /api/manage/retention沿用管理员会话/no-store和写入CSRF/Origin；PUT严格校验天数/期望revision，过期版本409，不能覆盖另一个页面的新策略。GET和保存请求不执行清理；更改天数将next_run_at置0，由服务端actor处理。workspace返回实际retention天数。正式设置新增独立保留策略页，确认清理不可逆、保存成功后更新基准；失败/409保留草稿，可明确重新读取，沿用导航未保存保护。

新HistoryRetention与采集、投递同属唯一Runtime，初始化前不工作；无需网站启用或浏览器保持打开。默认每小时完成一次检查，候选达到每类100个父项时每秒续批，不补跑错过的轮次。未到期/初始化前的唤醒只读；真正清理持BEGIN IMMEDIATE，同事务重查策略/到期并删除依赖、父项及更新检查点。与摄取/认领/完成/配置取消串行，避免检查后被另一写入改变。停止复用database_call的屏蔽取消/join规则，先等待数据库线程，再dispose；actor意外失败使用固定retention_stopped代码并降低就绪，日志不输出异常/SQL参数。

按UTC连续86400秒/天，严格早于cutoff才过期，边界时刻保留。Outbox只清sent/failed/cancelled，要求created_at与completed_at均过期，且所有尝试已结束、开始/完成/迟到结果都过期；pending/retry/leased和未完成尝试始终受保护。先删除该批DeliveryAttempt与OutboxContribution，再删Outbox；只有不再有任何保留Outbox的过期Post才与对应TaskEvaluation/RuleHit同批清理。旧版已经没有Post的孤立过期判定/命中另行有界清理，贡献仍有引用则不删。已完成目标测试/手动重发按finished_at清理，finished_at为空的未知/未完成记录保留；SourceRun按at清理。ManualDelivery原事件ID不是FK，原自动记录过期不损坏仍保留的手动消息快照，详情标示原记录已清理。显式操作同ID幂等仅在对应记录保留期间成立。

SeenPost、DeliveredPost和SourceItem均为独立身份/回执账本，不参与普通历史清理；SourceState/SourceProbe、安装关系、管理员、任务/版本和通知配置也不在清理范围。不因Post/outbox消失重新入库旧帖或补发，迟到结果/未知状态在受保护或保留周期内继续可追踪。清理不执行VACUUM，不承诺SQLite文件立即缩小；版本清理、备份恢复和账本主动删除不在本阶段。

Outbox新增completed_at和清理索引，正常完成、认领时确认终态、任务/目标取消等待意图，以及终态收到迟到结果均记录当前时间；不会仅凭很久以前的created_at清掉刚完成的重试或取消。旧库原来没有终态时间，迁移时仅对已有终态设升级时刻，额外保留完整周期，不猜测历史完成时间；队列/租约原样保留。给采集历史/判定/命中/显式操作增加清理时间索引，ORM与迁移一致，失败DDL/数据/版本整体回滚。

普通历史清理会影响内容/命中/采集统计窗口；自动投递数量继续取独立回执，概览说明两种口径。最近一批数量与下次检查时间可读取，不将它冒充永久累计值。只在独立临时库/模拟依赖验证；--retention浏览器服务8016仅启用实际清理actor，源与通知actor使用测试注入隔离，产品无模拟开关。runtime_demo增加真实后台清理与保留两条已见/来源身份及一条回执的离线检查。证据见[本阶段记录](history/2026-10-20-保留策略与清理接入.md)。


## M3显示时区与系统告警（2026-10-20，第八子阶段）

0009_display_alerts给WorkspacePreferences增加timezone/display_revision。旧库保留原Asia/Shanghai显示；新管理员与会话创建事务中写入浏览器IANA时区，缺省UTC，之后登录不覆盖。服务端zoneinfo校验并返回可选目录，GET/PUT /api/manage/display使用认证、CSRF和期望revision，冲突409。时间戳仍存UTC，内容/投递/概览/事件共享保存时区，日历日筛选沿用历史API的时区参数；客户端不支持保存时区则明确回退UTC。设置草稿、错误、重新读取/导航保护以及离开页面后的迟到响应均不能覆盖新页面设置。

AlertSettings单例默认关闭，独立选择最多64个已配置目标，版本冲突409；开启需至少一个目标。保存只影响之后的事件，不回填旧故障。SystemState是每组件永久状态/代次锚点；首次失败产生fault，新故障代次递增，持续失败不重复事件，实际成功产生同代recovery。SystemEvent按组件/代次/阶段唯一，AlertDelivery按事件/目标唯一，生成时固定加密目标快照。正式RSS记录失败/成功与observe同事务；自动渠道仅当前有效租约、目标启用且配置revision相同时更新，旧租约/旧配置回调不回退当前健康。显式来源测试、目标测试、手动重发均不改变正式故障状态；暂停/改配置自身不伪称恢复。

独立AlertWorker先将pending持久化为unknown/started_at再在事务外发送，单次上限10秒；每事件×目标只尝试一次，临时失败和中断未知也不自动重发，不承诺远端exactly-once。重新启动不认领unknown；失败不触发递归告警。生成和认领均检查目标状态，禁用/取消选择取消尚未开始的pending，恢复不倾倒旧告警；在途无法撤回。确认删除目标时同步从告警设置移除引用并提升设置版本，无剩余目标时关闭告警；只读预览明确展示此影响。未带确认摘要的旧删除调用仍须先解除告警选择（关闭设置也仍保留依赖）。只有历史告警密文仍存时也必须加载原凭据密钥，不能换钥。

Runtime增加独立alert_stop；其他actor意外失败降低就绪并停止采集/自动投递/清理，告警actor继续处理持久化事件。固定标签异步报告任务由Runtime追踪并在退出时join；正常启动循环后才恢复已有runtime故障，RSS/渠道仍要求自身实际成功。告警actor自身故障可留诊断，无法保证当时发送；整进程退出、数据库不可写或所有通道失效均不能由同进程保证外部通知。本功能不是外部看门狗。关停先停止所有actor/报告/探测，再关闭网络客户端和引擎。

系统消息使用独立schema_version=2、type=system_alert及alert对象，无伪造Post或任务；Webhook投递ID同时作稳定event_id/Idempotency-Key，普通帖子v1保持原约定。TG/Bark/SMTP复用既有凭据解密、网络限制和纯文本边界；Bark系统消息不带原帖url。固定故障代码不含远端错误/配置。GET /api/manage/alerts/state、/history及/history/{id}只读快照分页（上限100）返回白名单诊断/结果，不返回密文或接收地址。未知与失败可见，但本阶段不加手动重发系统告警入口。

普通保留清理可删过期SystemEvent及其全部已结束、完成时间过期的AlertDelivery；pending或未结束unknown保护整个事件。SystemState代次锚点不删，历史清空不重新发持续故障。新表、索引与ORM一致，迁移整体回滚。独立--system/8017浏览器服务使用临时库、真实Runtime及模拟HTTP/Notifier；产品无模拟开关。验证与边界见[阶段记录](history/2026-10-20-时区与系统告警接入.md)。


## M3版本信息与退出核对（2026-10-20，第九子阶段）

正式设置AboutSettings复用/api/version、/health/ready及受认证/api/manage/runtime，不新增后端或数据库结构。api.ts分离版本/就绪读取及协议校验，两者各自限8秒/禁止缓存；就绪503仍允许显示可读版本，非约定健康响应显示读取错误。原独立状态入口loadSystemInfo仍要求就绪。界面保留完整构建版本，development标明未固定提交，迁移null不冒充管理员未初始化；真实Runtime状态另行读取，401沿用会话过期处理。共享useRemote忽略过期/卸载响应，手动刷新/重试不写配置或发送消息。就绪只说明数据库与运行循环，不作为外部RSS可用或实际收信的证明。

正式导航提供版本信息；生产备份恢复按M4，既有备份直达地址明确未可用，不提供模拟导入/导出。未知设置地址404，正式空态与帮助说明以已接入范围为准；旧模拟原型已退役。M3操作/路由核对及证据见[退出矩阵](history/2026-10-20-版本信息与M3退出核对.md)，用户验收与真实服务验证另记。


## M4本地Compose与停服加密备份（2026-10-20，第一子阶段）

compose.yaml显式要求SEEKBELL_IMAGE，pull_policy=never；单实例/10001、只读根、/data命名卷、/tmp、cap_drop ALL/no-new-privileges和30秒stop_grace_period，默认只绑定127.0.0.1。维护覆盖文件禁外网/端口，私有/backup及/restore绑定路径必须已存在；首次目录初始化仅对新的空目录由临时root+CHOWN准备UID10001，不改变业务权限。检查脚本为每次创建唯一项目/卷，禁外网执行并清理，不接触日常卷。

backup.py只提供交互式本地维护CLI，没有未经认证的备份HTTP接口。create复用instance_lock要求停服，通过sqlite3.Connection.backup复制已提交WAL的一致快照；先校验迁移/SQLAlchemy结构、quick_check/外键、管理员及全量当前/历史密文原钥可解密。格式v1用固定参数scrypt(N=2^17,r=8,p=1,256位输出)、随机salt/96位nonce、AES-256-GCM流式加密；头作AAD、128位tag，完整认证前不解析。元信息/原密钥/数据库全部加密，无可控路径解包；JSON清单上限16KiB/数据库2GiB。原子独占发布0600备份；私有暂存目录0700，成功/异常清理，不宣称强制终止后的安全擦除。

restore仅当前迁移版本，独立新目录，先解密认证、版本/结构/摘要/凭据检查及备份管理员重新验证；不运行迁移。只删除副本LoginSession，管理员/全部业务表/任务版本/来源与队列/租约/账本保留，原库不变；同步文件/目录后Linux renameat2(RENAME_NOREPLACE)发布，竞争创建的空目标也拒绝，无覆盖回退。启动仍需原钥，恢复登录不得沿用备份会话。CLI口令只getpass，不接受参数/环境/管道；错误只输出固定应用消息或脱敏错误，不输出异常参数/SQL/秘密。

备份是时间点状态，不含之后的送达回执；切换前停原实例，恢复实例按原启停/退避/租约执行，不能承诺外部exactly-once。普通配置导出不在本阶段；Web备份/恢复、跨版本/升级/失败回退与正式数据卷切换后续实施。格式、真实命令及依据见[维护说明](BACKUP_RESTORE.md)，自动证据见[本阶段记录](history/2026-10-20-Compose与加密备份恢复.md)。


## M4网页加密下载与独立恢复候选（2026-10-20，第二子阶段）

运行中应用已持有整个生命周期的instance_lock，因此复用snapshot_backup做SQLite一致快照，后台继续运行、原钥在本生命周期不轮换；快照中全部密文独立校验。create_backup仍为停服CLI包装，另一个进程必须取得同一锁，未增加跳过锁的CLI选项。进度检查限制数据库2GiB及120秒快照等待，不把单文件裸复制当备份。

/api/manage/backups全部要求管理员会话，写操作继承CSRF/来源检查和认证限速；特权操作再验当前密码及哈希期间的会话/账号有效性。单个asyncio门禁覆盖创建、上传、验证及完整下载传输；下载Response在结束/取消时清理并释放。昂贵验证/数据库/文件写入用database_call，取消先join线程再清理。0700暂存目录放数据卷，0600文件；API/附件no-store，错误固定脱敏，无新依赖/迁移。

上传以8KiB内UTF-8 JSON行传验证字段，换行后流式接收加密字节，限制实际累计大小和300秒上传；口令不进URL/头或浏览器存储。认证与CLI相同，恢复只发布固定data_dir/web-restore，拒绝已有路径（含符号链接），不接受用户路径。仅副本旧会话撤销，原库不改；不接管原实例、不启动恢复actor，数据库版本须一致。一个候选最多保留一份，无网页覆盖/删除/启用接口；正式切换及升级回退留下一子阶段。GET状态用于重新连接后识别已发布候选，不能把候选存在解释为当前恢复已生效。浏览器下载形成Blob，大库走CLI。接口、磁盘/内存和复验边界见BACKUP_RESTORE。


## M4保留原卷的切换与显式回退（2026-10-20，第三子阶段）

宿主机scripts/manage_release.py负责Docker/Compose编排，应用Web无Docker socket/升级接口。只接受本机Unix socket、标准命名卷/10001/只读根/本机端口或禁外网实例。准备须已停服务；目标固定镜像在network none维护容器中将原卷只读挂载，以相同锁inode的只读描述符持独占flock，SQLite一致快照到全新卷。已知旧迁移只在候选执行；验证全量结构/账号/原钥/密文后清副本会话、生成带构建/迁移/文件摘要的准备记录，原子发布。原库不迁移，未知迁移失败；普通加密恢复仍要求匹配版本，不混为跨版本恢复。

状态以固定image ID/volume/data_dir成对保存。激活前核对daemon、Compose指纹、原容器身份/启动时刻、原快照及候选摘要；external卷必须已存在，避免误建空库。单用户本地项目文件锁及0700/0600原子状态，保留preparing/prepared/activating/active等阶段与失败状态；status同时报告实际实例，崩溃中间态不得解释为成功。失败启动停止匹配的新实例，无自动回退；显式rollback需accept-data-loss，才停止当前匹配实例并启动原镜像/原卷，绝不downgrade新库或合并数据。原卷/失败候选不自动清理。真实队列在启用后按原配置执行，回退/时间点恢复可能重复发送。

--restored把已验证web-restore从原卷复制到独立新卷，再同样准备/切换，源父实例锁及已有副本锁均受保护。只提供受控维护工具，不能承诺任意自定义Compose/跨主机/其他用户或外部手动Docker并发的协调。维护命令与故障边界见RELEASES；CI以唯一禁外网项目和合成未来迁移/启动失败镜像验证，不交付合成迁移。


## M4外部HTTPS反代与部署检查（2026-10-20，第四子阶段）

Settings新增精确可信代理IP（默认空、最多32个，拒绝*/CIDR/hostname/未指定/组播/zone）；统一在ASGI层使用已锁定Uvicorn ProxyHeadersMiddleware，网络入口保持no-proxy-headers避免重复解释。可信peer才影响scheme/client，Host保留端口，同源校验及Secure Cookie仍用实际请求上下文；直接HTTP可用。应用/native关闭访问日志，固定业务诊断保留，不记录请求体/凭据。无新依赖或迁移。

提供外部Nginx模板，单边缘覆盖转发头、保留Host端口、清除其他转发头、TLS由外部终止，备份上传/下载不缓存/不重放，2049MiB及超时配合应用总量校验。无代理服务加入产品Compose，应用仍单容器。宿主机只读部署CLI分别核对容器权限/卷/本机端口及HTTPS证书/版本/健康/Cookie，拒绝URL秘密、跳转和环境代理，不触发认证写入/网络采集。发布维护对保存代理配置并在切换/回退重放，空值兼容旧状态；配置文件指纹保护仍生效。

本地以独立内部Docker网络、固定Nginx1.30.6 digest和临时CA验证真实TLS/认证/流式备份/伪造代理头与日志样本，桌面手机验证HTTPS会话。临时CA不入系统信任库，浏览器仅测试证书场景忽略未知CA，Python端严格验证链/主机名与未知CA拒绝。实际目标证书/代理/PVE/GHCR/双架构与用户验收另记。命令及信任边界见PROXY_DEPLOYMENT。

## M4镜像候选与发布边界

双架构采用原生amd64/arm64 runner，分别构建与禁业务外网演练后保存镜像归档；只读可复用工作流由codex/开发分支push的完整CI及手动候选流程共同调用，支持合并前验证；手动流程默认只生成候选，显式仓库开关和手动发布选择、默认分支及完整CI通过后才授予独立job的GHCR写权限。发布复用测试产物，核对运行配置digest与层指纹，再以两个单平台digest合成索引并固定索引digest部署。区分classic/containerd的本机image ID、运行配置digest和registry manifest/index digest；不以代码SHA标签推定逐字节可重现或标签不可改写。只有发布job使用短期GITHUB_TOKEN写GHCR；写前后确认私有源仓库及显式public镜像包；公开仅涉及GHCR包，源码仓库保持私有。包缺失/不可读或可见性不符则在写前停止，不自动变更权限或创建默认私有包。GitHub包repository元数据可选/可空，缺失记not-reported，明确报告的错配则拒绝；镜像source/config与测试归档独立核对，不将缺失字段当成关联失败或关联成功的证明。发布后按索引digest拉取amd64并在隔离新实例复验；arm64以发布前原生检查为证。真实写入回执即使后置失败也保留，整轮成功仍要求全部检查通过。没有自动部署/自动真实发送。[具体流程与限制](IMAGE_RELEASE.md)。


## 通知呈现时区与Telegram排版（2026-10-21，M5实测修正）

自动认领、目标测试、手动重发、告警认领在各自事务内读取WorkspacePreferences.timezone，向发往Notifier的独立payload副本加入display_timezone；不改Outbox/ManualDelivery保存的原始消息和UTC时间戳。旧队列不要求迁移，重试/重发按本次发送准备时的时区呈现；保存时区后的在途请求可能继续使用认领时的值。无时区上下文时回退UTC。render统一将发布ISO时间/首次发现epoch/系统事件epoch转换为带IANA名称的可读时间，发布缺失/无效时明确用发现时间；Webhook仍由显式白名单字段生成原版本JSON，不泄漏呈现上下文。

用户随后确认Telegram隐藏时区名：格式化层显式控制后缀，普通通知/测试/手动重发/告警均仅显示已转换的日期时间，不通过字符串全局替换删除正文内容。Bark/SMTP保留时区名。Telegram单独生成普通文本、UTF-16偏移/长度的bold实体和原帖URL按钮，不使用parse_mode、不执行外部标记；标题/作者/版块/任务/摘要逐段限长，整段最多4000 UTF-16单位，按钮URL独立于截断正文。系统告警只加粗标题、不附原帖按钮。禁用链接预览、话题ID、HTTP错误分类、去重及重试策略沿用原实现。Bark/SMTP仅更新共享的可读时间格式，无新增依赖/迁移。

## 社区热榜与概览布局（2026-10-23实现）

产品契约见SPEC 6.1。0010_overview_preferences新增单例OverviewPreferences：modules/revision保存三模块布局，website_id/periods/selection_revision保存浏览选择，避免周期选择与布局编辑冲突；旧库默认三模块全显示，整库加密备份/恢复保留非默认布局和选择。workspace返回overviewModules。GET/PUT /api/manage/overview-preferences读取配置/来源能力及更新布局，PUT /api/manage/hotlists/selection只更新浏览选择；沿用认证、CSRF、no-store和版本冲突，严格校验模块集合。

sites/hotlists.py独立声明网站、提供方、周期、固定HTTPS端点和解析函数。NodeSeek第三方三榜及Linux DO官方RSS三榜已注册，V2EX未实现；只列已安装且有能力的网站。原帖URL由本站适配器生成，外部条目仅按文本展示，不补抓正文/评论，不进入Ingestion/RuleEngine/Outbox或监控历史/统计。

GET /api/manage/hotlists/{website_id}?period=...校验安装和模块可见后调用独立HotlistService；overview统计不访问热榜网络。服务随生命周期创建/关闭，使用固定端点、TLS验证、无重定向/环境代理；总等待10秒，连接3秒/I/O8秒，流式限1MiB并拒绝未协商压缩。限制条数、标识、文本和数值，跳过无效/重复项，非空无有效项作为失败；仅返回固定错误码，不回显远端正文/异常。

网站＋提供方＋周期隔离缓存/在途任务/退避，600秒按需刷新；同键并发共享任务。冷读等待共享任务且客户端取消不取消其他读者；已有快照立即返回并触发一次过期后台刷新。refreshing独立于失败状态，刷新期间客户端按next_attempt_at约2秒读完成结果，结束后恢复正常冷却，不轮询来源。生命周期关闭先取消/等待在途任务再关闭HTTP。失败30～600秒退避，遵守Retry-After（上限一天）；频率为工程候选，不冒充提供方限频保证。source_updated_at与fetched_at分开，仅对可靠提供来源时间的提供方检查时间倒退；ready/stale/unavailable区分正常、失败旧快照和无数据。榜单成功快照经0011持久化、重启按需恢复，最多展示24小时，布局和浏览选择持久化。健康检查独立于热榜，无消费者周期轮询。

概览固定统计与可排序内容区分开；同一统计请求只显示一处反馈，模块保留stale交互保护。热榜独立useRemote，身份含网站/周期，切换不串其他榜单，沿用会话/data revision和迟到响应隔离。选择串行保存，其专用写入不使监控查询缓存失效；保存冲突保留当前选择并可重试。页面隐藏/组件卸载停止刷新，手动刷新服从后端冷却。来源时间按保存时区展示。可见卡片在当前榜单就绪后预读当前网站其他支持周期，fresh缓存跳过，fetchRead合并点击与预取；预取不写选择，不预抓其他网站。HTTP仍no-store，保留服务进程/认证会话缓存，0011另加独立SQLite成功快照，不增加Service Worker。

Preferences复用草稿、部分保存、冲突与导航保护；设置支持鼠标/触屏手柄、键盘上下键、上下按钮和默认草稿。概览不再显示设置快捷入口，模块设置从系统设置进入；设置定位参数仍支持直接链接，App只以路径部分识别页面。单站显示名称，多站标签、超过四站AppSelect，单周期不显示无效切换。

test:hotlist在8028临时库验证；所有run_web_smoke浏览器环境注入synthetic_hotlists，不访问真实论坛。hotlist_factory仅为Python测试注入，无生产模拟开关。后端验证迁移/冲突/重启、缓存/并发/退避/异常及加密恢复；合成多站只验证UI能力，不增加产品适配器。验证结果见开发记录；用户验收和真实来源长期稳定性独立。

## 内容详情的命中依据（2026-10-23后续确认）

GET /api/manage/history/posts/{key}/evaluations增加group=matched，始终在OFFSET/LIMIT前过滤status=match，没有命中也不回退全部。默认all及已交付primary/other读接口保持兼容；matched_total/other_total元数据继续保留，不新增界面入口。继续基于TaskEvaluation/legacy RuleHit合并视图、历史TaskVersion与脱敏快照；判定数据不删除、不重算，不新增迁移。

Content仅请求matched，缓存身份含帖子/筛选/页码，删除其他判定的状态、加载器、折叠和样式；匹配卡片继续按任务显示原因与历史版本。零命中时按帖子已保存总状态区分不命中/信息不足/未执行/历史未知，匹配读取成功前不渲染空态；match状态却缺少依据时仅提示刷新，不冒充不命中。超过单页容量才显示分页，换帖重置页码/投递页并沿用generation/session隔离。

## Linux DO与多站采集（2026-10-23后续确认）

0011_linuxdo新增默认关闭的Website/Source/SourceState身份行，不新增WebsiteInstallation；Post.author_display_name为可空展示字段，既有行/快照不回写。WebsiteRequestState保存Linux DO域名请求间隔/退避，HotlistSnapshot按网站＋提供方＋周期唯一保存成功结果；迁移失败整体回滚。新schema回退须使用匹配旧镜像的完整备份，不运行旧镜像直接读0011。

sites/registry.py统一内置监控注册和WebsiteId，LinuxDoAdapter以主题ID/固定域名GUID对照并生成规范链接；RSS作者仅显示名，不填规则author。SourceEntry暂存原始description供适配层剔除已知Discourse尾注后纯文本化，不全局替换NodeSeek摘要。Post与通知快照留存显示名，可读通知回退展示它；纯规则不读取展示字段，管理保存/历史试算按能力拒绝用户名规则。历史原帖链接用统一注册表校验，显示名可搜索但不等于用户名匹配。

Runtime.sources为按站映射，每站SourceRunner和RssCollector独立互斥，HTTP连接池容量覆盖已注册站点；collection actor通过TaskGroup拥有/关停全部来源，仍保留原固定actor诊断。SourceFailure只写当前来源；SourceDeferred不发HTTP且不伪造采集失败。连接测试按website_id选同一个runner，维持基线/历史/通知只读。

WebsiteRequestBudget由Runtime与HotlistService共用，同站HTTP互斥及2秒间隔。Linux DO自动挑战/403为300/600秒封顶，429为60～600秒，其他传输/服务端错误30～300秒；Retry-After最多86400秒独立保存。0012_retry_controls仅给WebsiteRequestState增加retry_after_until与next_manual_at，分别保护服务器等待和60秒人工测试配额；旧预算/失败来源/失败测试截止时间取最大值保守继承，原列/数据不重写。恢复必须匹配旧镜像/schema备份。

SourceProbe仅对Linux DO将显式manual标记经SourceRunner/RssCollector传入预算：手动reserve可跳过程序blocked_until，但不能跳过retry_after_until、next_manual_at及同站2秒间隔/锁；配额跨重启保存，取消不伪造失败、并发延期仍为deferred。成功不清除SourceState失败证据，只将其失败next_attempt_at提前以便真实采集；健康来源计划不变。失败测试的独立60秒限频不替代自动预算；普通API/热榜/重启不获得人工重试权限。NodeSeek继续原测试2秒及失败退避语义。

collectors/http.public_client供Runtime与HotlistService创建客户端，通过精确HTTPS域名mount仅为linux.do建立http2=True且trust_env=False的AsyncHTTPTransport；默认池保持HTTP/1.1，注入测试transport时不创建mount以避免测试漏网，客户端关闭时共同回收各池。依赖使用httpx[http2]并锁定h2/hpack/hyperframe，不引入curl_cffi或浏览器。HTTPX保留正常协议协商回退；实际来源可用性按镜像/环境单独验收。

collectors/http.public_response构造匿名请求、显式移除Cookie且不跟随跳转，关闭响应；RSS与热榜共用。固定端点/TLS/无环境代理/1MiB/总超时保持。HotlistSource声明JSON或RSS格式和每站支持项，Linux DO不使用帖子时间冒充榜单更新时间。持久快照读取校验时间/条数/字段并重新生成规范链接；600秒TTL、24小时展示上限、按键共享更新和客户端取消隔离沿用。无消费者常驻轮询，持久化失败不能伪称网络成功。

验证命令：uv run --frozen pytest tests/test_public_http.py tests/test_linuxdo.py tests/test_linuxdo_runtime.py tests/test_hotlists.py tests/test_runtime.py -q；pnpm --dir frontend test:linuxdo（独立8030合成库）。所有浏览器环境注入合成两站热榜，不访问真实论坛或发送真实消息。正式来源可访问性与用户验收另行记录。

## 多站验收修正（2026-10-24）

0013_site_order为WebsiteInstallation新增position，从现存SQLite rowid插入顺序回填，后续添加在写事务中按max(position)+1追加，列表/概览/热榜元数据共用该顺序。原网站身份、配置与历史不变；移除重加置末。迁移还从真实SourceProbe(success/failure/unknown)重建next_manual_at，消除旧自动失败生成的伪人工配额，保留真实/取消测试限频，服务器retry_after_until不改。

WebsiteRequestBudget.failed不再写人工配额；配额仅在人工请求真正reserve时占用。SourceProbe staged/延期只按2秒短间隔，成功/失败仍按60秒且重启保存。HotlistService将source_busy/source_cooldown返回waiting而非unavailable，不增加失败；CommunityHotlist对Linux DO关闭跨周期预取，按现有可见性/next_attempt_at调度重试，其他站预取保持。
