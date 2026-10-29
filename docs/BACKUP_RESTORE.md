# 本地 Compose 与加密备份恢复（M4 分阶段）

仅支持 Linux 本地文件系统。已提供停服维护命令、网页加密下载和网页直接恢复（系统设置或新安装的初始化页），网页恢复在服务不中断的情况下替换当前数据，原数据保留在数据目录的before-restore-*文件夹；较旧迁移版本的备份在私有暂存副本中自动升级，较新版本拒绝。宿主机[发布维护工具](RELEASES.md)仍可用于大库和保留原卷的切换。实机部署尚未交付。使用已验证的完整代码 SHA 对应镜像，不能用新镜像直接覆盖旧数据尝试回退。阶段证据与构建基准见 PROJECT_STATE。

## Compose

`compose.yaml` 要求显式设置 SEEKBELL_IMAGE，且不自动拉取；请预先构建/加载固定提交标签或 digest 镜像。启动一个进程，UID/GID 10001、根文件系统只读、丢弃 capabilities、禁止提权、退出宽限 30 秒，数据放命名卷。默认端口仅绑定 127.0.0.1:8000，SEEKBELL_PORT 可改。没有反代信任通配、Docker socket、自更新或发布步骤。

在正式 SeekBell-Dev 工作目录，先核对代码与拟构建 SHA 一致；将 SEEKBELL_REVISION 设为 PROJECT_STATE 的完整构建基准后：

~~~bash
export SEEKBELL_IMAGE="seekbell:${SEEKBELL_REVISION:?请先设置已验证的完整代码SHA}"
docker build --build-arg VCS_REF="$SEEKBELL_REVISION" -t "$SEEKBELL_IMAGE" .
docker compose -p seekbell-test config
docker compose -p seekbell-test up -d
docker compose -p seekbell-test ps
~~~

新库没有已添加网站，来源关闭、没有通知目标。启用网站/目标后会实际运行；本阶段验证只用独立项目、临时卷及禁外网覆盖，不运行日常已启用配置。测试和日常必须使用不同项目名、端口和数据卷。新验收还须先核对项目名是否已有卷：up -d会复用同项目旧数据，不保证空库；如遇不识别的迁移号，停止并保留旧卷，使用经确认未占用的新项目名创建独立验收库，不能手改迁移号或删卷绕过。不要用 `down --volumes` 停日常服务；这会删除数据卷。保留数据使用 `stop` 或不带 volumes 的 `down`。

## 网页加密下载与独立恢复副本（第二子阶段）

系统设置 → 备份恢复。需已登录管理员；下载和上传均校验同源、CSRF、限速，并重新验证当前管理员密码（登录或上次输入后15分钟内免输入，进程内记录，重启后重新要求）。下载设置独立的12–1024字符备份口令并确认；使用与CLI相同的.sbbackup v1，包含完整数据库和原凭据密钥。网页/CLI生成的加密格式互通。演示原型的普通JSON备份不适用。

网页下载由持有实例锁的单进程应用执行SQLite一致性快照，不释放实例锁、不调用停服CLI，也不暂停后台。原钥在本次进程生命周期不轮换；校验的是快照数据库及全部当前/历史密文。快照后的修改和投递回执不在备份中，恢复仍可能重复发送。CLI继续要求停服，不能从另一个进程绕锁制作快照。未初始化管理员时拒绝。

上传时输入备份口令（及按需的当前管理员密码）；明确勾选只生成独立副本。先完成加密认证，再复用版本/结构/完整性/原钥验证，副本管理员替换为当前管理员并撤销副本旧会话。只原子发布到当前数据目录下固定的web-restore（容器为/data/web-restore），不接受客户端路径；不覆盖原库或已有副本，不自动迁移、不启动副本，不修改当前启停或队列。网页成功仅表示副本生成，**不等于当前工作空间已恢复**。恢复失败原库不变；响应丢失可刷新读取副本存在状态，不能盲目重复覆盖。

### 网页直接恢复（2026-10-29）

系统设置“恢复备份”只需备份口令（及按需的当前管理员密码），恢复后保留当前管理员账号；新安装尚无管理员时，初始化页“从备份恢复”输入备份口令并设置管理员用户名/密码（创建管理员后该入口关闭，返回409）。不需要备份中的管理员凭据：能解密备份即已可读取其中全部数据，旧密码不提供额外保护，反而让久远备份因遗忘密码而无法使用。上传格式与上文相同，先在数据目录私有暂存区完成解密、版本/结构/完整性/原钥验证，写入保留或新设的管理员并撤销旧会话；较旧版本在暂存副本中迁移。默认勾选“恢复后暂停采集和通知”：所有网站和通知目标置为暂停，备份中待发送消息随后取消而不发出。验证通过后服务拒绝新请求（503并提示稍候）并等待其他请求结束（最长15秒，否则409不恢复），关闭后台、凭据与数据库，把当前数据库/WAL/SHM/密钥移入before-restore-时间-随机（0700），再移入恢复数据并重新打开全部服务；重新打开失败则放回原文件并以原数据重开，返回“已回到原数据”。成功后旧会话全部失效，发起恢复的浏览器获得新会话直接进入，记录“恢复备份·已恢复”。before-restore目录不自动删除，确认无需回退后可在宿主机删除。旧实例若仍在运行且未勾选暂停，会重复采集和通知。

旧的“恢复验证”独立副本流程（下文）保留给维护工具使用，网页不再生成；已有副本可在网页删除。

当前仅保留一个独立副本，无网页覆盖或启用操作。不再需要的副本可在网页输入当前管理员密码删除（`DELETE /api/manage/backups/candidate`），删除后可重新上传；副本被实例锁占用时拒绝，符号链接只删除链接本身。未删除的副本保留待后续维护核对；不得与原服务并行启动同一套真实采集/通知。正式切换、升级与显式回退通过[发布维护工具](RELEASES.md)执行，Web不直接操作Docker。停服后可用下文维护容器检查候选（不启动服务、不联网）：

~~~bash
docker compose -p seekbell-test stop
docker compose -p seekbell-test -f compose.yaml -f compose.maintenance.yaml \
  run --rm --no-deps -T -e SEEKBELL_DATA_DIR=/data/web-restore \
  seekbell python -m seekbell.db check
~~~

数据库上限2GiB、上传清单行8KiB、上传最长300秒；根据实际流量累计限制，不能只信Content-Length。一次仅一个备份/恢复，下载传输结束或中断后释放门禁。文件操作/验证在线程中执行，取消请求会等待已有数据库线程结束再清理；已完成发布后即使响应丢失副本也会保留。网页下载在浏览器中形成Blob，会占用备份体积相应内存，大库建议使用停服CLI。服务器在可信数据盘预留约数据库3倍的暂存空间及额外候选空间；0700临时目录、0600文件，完成/异常/断开清理，强杀残留不承诺安全擦除。口令只在请求体和内存中使用，无URL/日志/浏览器持久化，不提供免认证下载URL。API和下载均no-store。

接口：GET /api/manage/backups返回候选存在状态和大小上限；POST /download接收JSON current_password/password，返回加密附件；POST /restore使用application/octet-stream，请求体第一行为有界UTF-8 JSON（current_password/password/username/admin_password），一个换行后跟加密文件原始字节。只接收白名单字段，不接受路径。无需multipart依赖，后台不读取浏览器演示存储。

复验仅用临时数据/合成密码/模拟网络：

~~~bash
uv run --frozen pytest -q tests/test_backup.py tests/test_web_backups.py
pnpm --dir frontend build
pnpm --dir frontend test:backup
python3 scripts/check_backup_container.py "$SEEKBELL_IMAGE" --revision "$SEEKBELL_REVISION"
~~~

浏览器专项为桌面/手机分别启动8018/8019一次性服务，不读取当前验收实例。Compose脚本新增运行中网页往返，仍保持禁外网、旧CLI运行中拒绝、停服CLI恢复和恢复实例重新登录检查。

## 加密备份

备份包含整个一致性数据库（管理员密码哈希、配置/历史、独立身份/回执账本、队列、会话等）和原 credentials.key，不是普通配置导出。独立备份口令与管理员密码分别输入，口令 12–1024 字符；丢失口令不能解密。口令不接受命令行参数、环境变量或管道，getpass 输入不回显。

备份用 SQLite Connection.backup 生成快照，原库只读访问；与服务/迁移使用同一个实例锁，必须先停服务。snapshot 包含已提交 WAL，不能用裸复制单个 sqlite 文件代替。检查当前迁移、表/列/索引结构、完整性/关联、管理员哈希格式以及当前和历史加密快照的原钥解密，再发布备份。只支持当前迁移版本；无管理员/缺钥/错钥/结构异常时拒绝。

首次为容器准备**新的空** Linux 备份/恢复父目录：

~~~bash
export SEEKBELL_BACKUP_DIR="$HOME/.local/share/seekbell-backups"
export SEEKBELL_RESTORE_DIR="$HOME/.local/share/seekbell-restores"
mkdir -p "$SEEKBELL_BACKUP_DIR" "$SEEKBELL_RESTORE_DIR"
chmod 700 "$SEEKBELL_BACKUP_DIR" "$SEEKBELL_RESTORE_DIR"
docker compose -p seekbell-test stop
~~~

`compose.maintenance.yaml` 叠加后禁用网络/端口，将上述两个已存在目录挂载至 /backup、/restore，不会自动创建错误的宿主路径。要求 Compose 支持 !reset（本机 v5.6.0 已验证）。首次用同一 Rootless/rootful Docker 上下文准备容器 UID 10001 的目录所有权；不要对已有日常目录使用此初始化命令：

~~~bash
docker compose -p seekbell-test -f compose.yaml -f compose.maintenance.yaml \
  run --rm --no-deps -T --user 0 --cap-add CHOWN seekbell python -c \
  "import os; [(os.chmod(p,0o700),os.chown(p,10001,10001)) for p in ('/backup','/restore')]"

docker compose -p seekbell-test -f compose.yaml -f compose.maintenance.yaml \
  run --rm --no-deps seekbell python -m seekbell.backup create \
  --output /backup/before-update.sbbackup
~~~

在真实交互终端运行最后一条命令，输入并确认备份口令。不要添加 -T，不要把口令写进命令或 shell 历史。输出文件必须不存在；最终文件 0600，原子发布、从不覆盖。数据库上限 2 GiB，流式处理；同一私有文件系统预留约数据库体积 3 倍并留余量的暂存/输出空间。暂存目录 0700、明文文件 0600，正常成功或失败清理；强制终止可能留下私有暂存文件，不承诺文件系统级安全擦除。备份目录也必须放可信私有磁盘。

Rootless 下宿主看到的是映射 UID。需要带走加密文件时，可用容器 UID 读取并在宿主以当前用户另存，避免修改数据卷或密钥权限：

~~~bash
(
  umask 077
  set -C
  docker compose -p seekbell-test -f compose.yaml -f compose.maintenance.yaml \
    run --rm --no-deps -T seekbell cat /backup/before-update.sbbackup \
    > "$HOME/seekbell-before-update.sbbackup"
)
~~~

这里只传输加密文件字节，不传口令。备份与独立口令分别保管；不入 Git。

## 独立恢复

目标必须是**尚不存在的新目录**，不能等于当前 SEEKBELL_DATA_DIR；已有文件、空/非空目录和符号链接一律拒绝。首次恢复仅支持备份和程序的迁移版本完全一致。先完成加密认证再解释清单/SQLite；验证数据库版本/结构/摘要/关联、原钥和全部凭据快照。失败不发布目标、不改变原库；并发恢复只能有一个成功。

~~~bash
docker compose -p seekbell-test -f compose.yaml -f compose.maintenance.yaml \
  run --rm --no-deps seekbell python -m seekbell.backup restore \
  --archive /backup/before-update.sbbackup \
  --destination /restore/recovered-before-update

docker compose -p seekbell-test -f compose.yaml -f compose.maintenance.yaml \
  run --rm --no-deps -T -e SEEKBELL_DATA_DIR=/restore/recovered-before-update \
  seekbell python -m seekbell.db check
~~~

交互输入备份口令和恢复后的管理员用户名；直接回车沿用备份中的管理员，填写则再输入两次新密码并替换。校验通过后仅清除恢复副本的旧登录会话（及按需替换管理员），其余表保持原样，再同步并通过 Linux RENAME_NOREPLACE 原子发布新目录；不运行迁移、不启动采集或通知。源数据不变；恢复文件 0600、目录 0700，使用执行命令的 UID（容器中 10001）。后续启动会加载原钥并要求重新登录。

恢复保留网站/目标原启停、队列与租约/退避。**启动恢复实例前停止原实例，不能让两份数据同时真实发送。**这是时间点恢复，不包含备份后产生的回执；之后重新运行可能重复发送，不能承诺外部 exactly-once。恢复副本在本阶段只用于禁外网检查，正式切换数据卷、升级/失败回退与 Web 恢复流程留后续阶段，不提供覆盖原卷的快捷命令。

## 格式和离线验证

.sbbackup v1：固定魔数/版本、随机 16 字节 salt、12 字节 nonce；scrypt N=131072/r=8/p=1 派生 256 位密钥，AES-256-GCM 流式加密，完整头部作认证附加数据，末尾 16 字节 tag。内部为有界 JSON 清单、44 字节原密钥和 SQLite 快照，无可控解包路径。清单含格式、应用/构建/迁移版本、UTC时间、数据库大小和 SHA-256；元信息也加密。认证完成前不会解析明文，不执行备份脚本。

设计依据：[Python SQLite backup](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup)、[Cryptography GCM 认证边界](https://cryptography.io/en/latest/hazmat/primitives/symmetric-encryption/#cryptography.hazmat.primitives.ciphers.modes.GCM)、[Compose 环境插值](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)。复用已锁定依赖，没有引入新库或改变技术栈。

~~~bash
uv run --frozen pytest -q tests/test_backup.py
uv run --frozen python -m seekbell.services.backup_demo
python3 scripts/check_backup_container.py "$SEEKBELL_IMAGE" --revision "$SEEKBELL_REVISION"
~~~

backup_demo 只用临时库、合成账号/目标和模拟通知；验证除撤销会话外所有表一致、原钥/账号可用、待发送/告警队列保留及继续投递。容器脚本创建唯一 Compose 项目和临时卷，所有服务禁外网，验证只读根/本机端口配置、运行中拒绝备份、停服备份、独立恢复后重新启动登录/配置保持，finally 仅清理本轮资源。不能将这些证据当作真实发送、PVE/arm64、反代或用户验收。
