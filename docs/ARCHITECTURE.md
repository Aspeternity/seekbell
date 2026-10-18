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

Collector 返回来源条目及采集状态。只处理连接/解析，不运行关键词规则。RSS 使用异步 HTTP 获取；同步解析、大型备份及同步 SMTP 不阻塞事件循环。显式超时、响应大小限制、禁用 XML 外部实体/网络展开、并发上限。M1采用defusedxml先拒绝DTD/实体，再以内存流交给feedparser，避免把输入当URL/文件；解析在线程中执行。RSS请求要求identity编码，限1MiB并拒绝未协商的压缩响应。NodeSeek保留原始版块文字，不虚构稳定分类编号。

RuleEngine 为无网络纯逻辑，输入规范化字段和规则快照，输出 match/no_match/insufficient_data 及结构化原因。前端试匹配与后台执行共用同一后端逻辑。

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
