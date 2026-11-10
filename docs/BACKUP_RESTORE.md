# 本地 Compose 与备份恢复

仅支持 Linux 本地文件系统。备份保存在服务器上的备份库（数据目录下`backups/`），可在网页立即备份、下载、检查后恢复，也可用停服命令生成和恢复。恢复前自动备份当前数据，可从列表回退；较旧迁移版本的备份在私有暂存副本中自动升级，较新版本拒绝。宿主机[发布维护工具](RELEASES.md)仍用于镜像升级与回退。使用已验证的完整代码 SHA 对应镜像，不能用新镜像直接覆盖旧数据尝试回退。2026-11-10起采用本格式（[方案](plans/2026-11-10-备份重构方案.md)），此前的`.sbbackup`加密备份与网页验证副本已不再支持。

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

## 备份文件

标准`tar.gz`，只含按顺序排列的三个普通文件：

| 文件 | 内容 |
| --- | --- |
| `manifest.json` | 格式版本2、类型（manual/auto/pre-restore/pre-upgrade）、应用/数据库结构/构建版本、创建时间、另两个文件的大小与SHA-256、内容摘要（工作空间名、网站/任务/目标/内容条数） |
| `seekbell.sqlite3` | SQLite备份机制取得的一致快照（含已提交WAL），已删除管理员和登录会话并VACUUM，不留可离线破解的密码哈希 |
| `credentials.key` | 原凭据密钥，恢复后通知渠道凭据可直接使用 |

**不加密**（用户2026-11-10决定）：服务器上的数据本身未加密，本地备份加密不增加安全性；离开服务器的文件包含通知渠道凭据（TG Bot Token、SMTP密码、Bark密钥、Webhook地址），请像保管密码一样保管，不要放到公开位置。万一泄露，到各平台重置Token/密码，再在SeekBell里更新通知目标。

读取时只接受这三个固定名称的普通USTAR成员，拒绝扩展头、链接、目录、多余成员和尾部数据；解压大小按成员上限（数据库2 GiB）截断，逐个核对SHA-256，再做完整性、外键、结构版本和全部历史密文校验。`tar -xzf`可手工解开，出问题时也能不依赖界面恢复。

## 网页备份库

系统设置“备份”页：状态卡显示上次备份时间与类型、存放目录、份数/占用和磁盘可用（超过30天未备份显示橙色）；列表每份可命名（立即备份时选填或之后重命名，名称存于`backups/labels.json`，恢复不影响）、下载、恢复、删除。不再记录操作历史（迁移0020删除`backup_records`）。

- **立即备份**：在服务器生成一份手动备份，不需输入密码；同一时间只运行一个备份或恢复。可用空间不足数据库2倍时直接拒绝。
- **下载**：先换一张一次性、60秒有效、绑定当前会话的票据，再由浏览器直接流式保存（不占内存，原生进度）。下载和删除只需登录会话（2026-11-10用户确认）；恢复要当前管理员密码，登录或上次输入后15分钟内免输。
- **保留**：恢复前、升级前备份保留30天，每种最新一份不删；手动备份不自动删除。备份文件0600、目录0700，计入“数据”页存储占用。
- 目录中手动放入的`*.tar.gz`也会列出，无法识别的只能删除；符号链接和其他文件不列出、不可访问。启动时删除旧版本留下的`before-restore-*`、`web-restore`目录和中断的临时文件（被其他实例占用的保留）。

## 网页恢复

三步：选择（列表中的一份或上传文件）→ 检查（不需要任何口令；服务器校验后显示备份时间、类型、版本、工作空间，以及网站/任务/目标/内容条数与当前对比，内容条数从数据库重新统计而非取自清单；不改任何数据）→ 确认（默认勾选“恢复后暂停采集和通知”，按需输入当前管理员密码）。上传暂存在数据目录私有目录，30分钟未确认或取消即删除，确认时不必重新上传。

确认后先在暂存区恢复并升级、校验，再生成一份“恢复前”备份（此份不做完整性校验，损坏的当前数据也不会阻止恢复；只有写入失败如磁盘满才中止），然后拒绝新请求（503）、等待在途请求（最长15秒，否则409不恢复）、关闭服务、整份换入并重开；重开失败则换回原文件并提示“已回到原数据”。成功后换下的文件删除，旧会话全部失效，管理员保持当前账号，发起恢复的浏览器直接获得新会话。撤销恢复：在列表中恢复那份“恢复前”备份。

新安装尚无管理员时，初始化页“已有备份？从备份恢复”走同一向导，最后一步设置管理员用户名和密码（创建管理员后该入口关闭，返回409），不生成恢复前备份。旧实例若仍在运行且未勾选暂停，会重复采集和通知。

## 停服命令

首次为容器准备**新的空** Linux 备份/恢复父目录：

~~~bash
export SEEKBELL_BACKUP_DIR="$HOME/.local/share/seekbell-backups"
export SEEKBELL_RESTORE_DIR="$HOME/.local/share/seekbell-restores"
mkdir -p "$SEEKBELL_BACKUP_DIR" "$SEEKBELL_RESTORE_DIR"
chmod 700 "$SEEKBELL_BACKUP_DIR" "$SEEKBELL_RESTORE_DIR"
docker compose -p seekbell-test stop
~~~

`compose.maintenance.yaml`叠加后禁用网络/端口，将上述两个已存在目录挂载至/backup、/restore，不会自动创建错误的宿主路径（Compose需支持!reset）。

~~~bash
docker compose -p seekbell-test -f compose.yaml -f compose.maintenance.yaml \
  run --rm --no-deps -T --user 0 --cap-add CHOWN --entrypoint python seekbell -c \
  "import os; [(os.chmod(p,0o700),os.chown(p,10001,10001)) for p in ('/backup','/restore')]"

docker compose -p seekbell-test -f compose.yaml -f compose.maintenance.yaml \
  run --rm --no-deps -T seekbell python -m seekbell.backup create \
  --output /backup/before-update.tar.gz
~~~

create与服务使用同一实例锁，必须先停服；输出文件必须不存在，生成0600并原子发布。恢复到**尚不存在的新目录**（不能等于当前数据目录），在交互终端设置恢复后的管理员：

~~~bash
docker compose -p seekbell-test -f compose.yaml -f compose.maintenance.yaml \
  run --rm --no-deps seekbell python -m seekbell.backup restore \
  --archive /backup/before-update.tar.gz \
  --destination /restore/recovered-before-update

docker compose -p seekbell-test -f compose.yaml -f compose.maintenance.yaml \
  run --rm --no-deps -T -e SEEKBELL_DATA_DIR=/restore/recovered-before-update \
  seekbell python -m seekbell.db check
~~~

管理员密码只在交互终端输入，不接受参数、环境变量或管道。恢复保留网站/目标原启停、队列与租约/退避。**启动恢复实例前停止原实例，不能让两份数据同时真实发送。**这是时间点恢复，不包含备份后产生的记录与回执。

## 验证

~~~bash
uv run --frozen pytest -q tests/test_backup.py tests/test_web_backups.py
uv run --frozen python -m seekbell.services.backup_demo
pnpm --dir frontend build && pnpm --dir frontend test:backup
python3 scripts/check_backup_container.py "$SEEKBELL_IMAGE" --revision "$SEEKBELL_REVISION"
~~~

backup_demo只用临时库、合成账号/目标和模拟通知：备份不含管理员和会话，恢复后除管理员与会话外所有表一致、原钥可用、待发送/告警队列保留并继续投递。容器脚本在禁外网的一次性项目中验证运行中网页备份、流式下载、检查、就地恢复与恢复前备份，运行中停服命令被拒，停服create/restore及恢复实例登录。浏览器套件（8018–8021一次性服务）覆盖立即备份、下载文件结构、上传检查、恢复、回退、删除和初始化页恢复。
