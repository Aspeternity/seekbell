# 本地 Compose 与停服备份恢复（M4 第一阶段）

仅支持 Linux 本地文件系统。当前是维护命令；网页下载/上传恢复、跨迁移版本恢复、原目录覆盖、升级回退流程和实机部署尚未交付。使用已验证的完整代码 SHA 对应镜像，不能用新镜像直接覆盖旧数据尝试回退。阶段证据与构建基准见 PROJECT_STATE。

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

目标必须是**尚不存在的新目录**，不能等于当前 SEEKBELL_DATA_DIR；已有文件、空/非空目录和符号链接一律拒绝。首次恢复仅支持备份和程序的迁移版本完全一致。先完成加密认证再解释清单/SQLite；验证数据库版本/结构/摘要/关联、备份中的管理员用户名及当时密码、原钥和全部凭据快照。失败不发布目标、不改变原库；并发恢复只能有一个成功。

~~~bash
docker compose -p seekbell-test -f compose.yaml -f compose.maintenance.yaml \
  run --rm --no-deps seekbell python -m seekbell.backup restore \
  --archive /backup/before-update.sbbackup \
  --destination /restore/recovered-before-update

docker compose -p seekbell-test -f compose.yaml -f compose.maintenance.yaml \
  run --rm --no-deps -T -e SEEKBELL_DATA_DIR=/restore/recovered-before-update \
  seekbell python -m seekbell.db check
~~~

交互输入备份口令、备份时管理员用户名/密码。校验通过后仅清除恢复副本的旧登录会话，其余表保持原样，再同步并通过 Linux RENAME_NOREPLACE 原子发布新目录；不运行迁移、不启动采集或通知。源数据不变；恢复文件 0600、目录 0700，使用执行命令的 UID（容器中 10001）。后续启动会加载原钥并要求重新登录。

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
