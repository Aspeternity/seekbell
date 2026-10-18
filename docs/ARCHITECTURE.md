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

Collector 返回来源条目及采集状态。只处理连接/解析，不运行关键词规则。RSS 使用异步 HTTP 获取；同步解析、大型备份及同步 SMTP 不阻塞事件循环。显式超时、响应大小限制、禁用 XML 外部实体/网络展开、并发上限。

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

## 调度与恢复

10秒为候选默认配置：用户提出且助手建议采纳，非官方限频保证，需保留来源说明。所有任务共享采集；固定周期不重叠、不补跑错过的全部定时 tick。网络失败指数退避并设置上限；429遵循 Retry-After；解析失败不能当作空列表成功。支持少量抖动，避免多个部署同时请求。

实施默认建议：通知最多自动尝试5次，使用有上限的退避；可重试状态与配置错误区分。具体间隔集中配置并测试，不散落常量。

健康检查分离进程存活与业务健康：RSS暂不可达不应触发容器不断重启。启动执行迁移、验证数据目录/密钥、恢复任务，再启动调度。正常退出停止新认领，给予在途任务有限完成时间。

## 部署与凭据

镜像使用非 root，多阶段构建，不带测试依赖、真实样本/凭据。数据卷保存 SQLite 与恢复所需材料；环境变量负责启动基础参数，日常设置在 Web。

首版无初始化令牌；服务端保护管理员唯一性。会话/CSRF/登录限速、密码哈希、加密凭据、日志脱敏。允许指定可信反代，不能信任任意 X-Forwarded-*。

备份使用 SQLite 一致性备份机制；包含凭据时连同所需密钥安全封装并明确提示。普通配置导出默认不含凭据。恢复需要管理员重新验证，停止后台写入并先校验版本；迁移失败不得继续运行。

## 私有开发与实机验证（建议路线）

私有 GitHub 仓库+私有 GHCR 镜像。Owner、实际可见性和凭据尚未提供。不能假定创建/公开/发布权限。

PR进行代码检查和容器构建；只有受信任、获授权的流水线发布测试镜像，不能给不受信任 PR 注入发布密钥。待验收镜像标注完整提交 SHA/镜像 digest，页面显示版本。

日常环境与测试环境使用不同 Compose 项目名、端口、数据卷。第一版可先仅测试环境；测试默认关闭实时采集和真实通知。演示数据只存在测试/开发流程，不污染正式状态。

Codex 可在授权 SSH 范围内部署测试环境；没有 SSH 则提供含固定镜像版本的更新命令。不要把 docker socket 暴露给应用用于自更新。

发布 amd64/arm64 镜像；架构构建成功不等于两种架构均已原生实机验证。正式环境不自动升级。回退需结合数据库版本和备份，不能仅更换旧镜像。
