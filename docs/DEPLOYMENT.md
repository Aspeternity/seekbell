# M4 部署、备份与恢复

本地自动证据见 PROJECT_STATE。以下是交付命令，不代表已部署、已发布或用户验收。只支持 Linux 本地文件系统，一个实例/worker；不挂载 docker socket。PVE、原生 arm64、真实反代及四渠道仍在统一验收中。

## Compose 与反向代理

仓库根目录执行：

```bash
cp deploy/.env.example deploy/.env
# 编辑 deploy/.env：填写已验证的完整提交 SHA 镜像标签，发布后优先使用 image@sha256:digest。
docker compose --env-file deploy/.env -f deploy/compose.yaml config --quiet
docker compose --env-file deploy/.env -f deploy/compose.yaml up -d --wait
docker compose --env-file deploy/.env -f deploy/compose.yaml logs --tail=100 seekbell
```

首次在本机使用时，可先构建本地镜像 `docker build --build-arg VCS_REF="$(git rev-parse HEAD)" -t "seekbell:$(git rev-parse HEAD)" .`，将该精确标签填入 SEEKBELL_IMAGE。不能把有未提交代码的镜像标为某个提交的可复现证据。不要使用 latest 或自动升级。

默认项目 seekbell-test、127.0.0.1:8000、后台关闭；后台关闭仍允许管理员显式连接/发送，离线演练须另外禁外网。日常与测试使用不同项目名、端口和命名卷。正式开放地址、启用后台与真实来源由用户确认；不要用 `down -v` 或全局 prune 更新服务。卷中 UID/GID 为10001；首次命名卷继承镜像 /data 权限，宿主绑定目录需预先配置。

根文件系统只读，/data 可写，/tmp 为64MiB tmpfs；备份明文临时文件在 /data 私有临时目录中，不占用 /tmp。日志采用 local 驱动轮换（10MiB × 3），不把密码、请求正文或通知凭据写入命令行/日志。停止宽限60秒，后台本身给予15秒网络排空宽限；仍可能有结果未知的外部投递。

外部 HTTPS 代理参考 deploy/nginx.conf.example。代理保留 Host，覆盖 X-Forwarded-Proto/For，应用 SEEKBELL_TRUSTED_PROXIES 仅填实际看到的代理地址/CIDR，保持 Uvicorn --no-proxy-headers。Rootless/桥接可能改变对端地址，不能照抄示例 IP。确认 HTTPS Cookie 为 Secure、直接 HTTP 不接受该 Cookie、CSRF 正常；仅回环端口不保证另一台代理能访问。

`/health/live` 是容器存活探针，不因论坛故障重启；`/health/ready` 包含数据库迁移和后台循环状态。unhealthy 不会让 Compose 自动重启；restart: unless-stopped 处理进程退出。就绪故障须查脱敏日志及管理页面。

## 停服全量加密备份

完整备份含管理员密码哈希、通知配置/密钥、规则版本、帖子历史、已见/已发账本和待投递队列。没有“普通配置导出”接口。完整备份不是脱敏样本，禁止提交 Git；口令遗失无法解密。使用独立强口令，和归档分开保管。

```bash
docker compose --env-file deploy/.env -f deploy/compose.yaml stop seekbell
docker compose --env-file deploy/.env -f deploy/compose.yaml run --rm --no-deps seekbell \
  python -m seekbell.backup create /data/pre-upgrade.sbb
mkdir -p backups
chmod 700 backups
docker compose --env-file deploy/.env -f deploy/compose.yaml cp \
  seekbell:/data/pre-upgrade.sbb ./backups/pre-upgrade.sbb
chmod 600 backups/pre-upgrade.sbb
```

在交互终端输入当前管理员密码、备份口令并重复口令；不通过参数、环境变量或管道传密码。未创建管理员时不允许全量备份。使用新文件名，命令拒绝覆盖已有归档。备份成功后按需重新 `up -d --wait`，并将归档另存到受控离线位置；仅放在原卷不防宿主/磁盘损坏。

命令获取整个数据目录实例锁，拒绝正在运行的服务；SQLite backup API 包含已提交 WAL，检查完整性、外键、已知版本及所有目标/待投递/测试/重发的密文快照。原密钥权限必须正确，不能缺钥后生成替代密钥。只在当前 schema 创建备份，不偷偷迁移源库。

封装格式 v1：随机盐的 scrypt（N=32768,r=8,p=1）派生 AES-256-GCM 密钥，随机12字节 nonce；头部作为附加认证数据，归档整体认证，按1MiB流式加解密。归档仅有固定清单、SQLite 和原密钥，包含创建版本与时间；最终认证成功后才解析。文件0600，临时目录0700，成功发布前 fsync，不覆盖旧文件。数据库上限64GiB，部署需预留数据库与归档数倍空间。临时明文不承诺取证级擦除，宿主磁盘保护由运维负责。

## 恢复与升级回退

恢复只写入空目录/新命名卷，永不覆盖现用卷。目标只允许已有 .instance.lock；中断遗留文件也会拒绝，保留现场后换新卷重试。恢复验证备份中的管理员密码（可能不同于当前实例密码）及独立备份口令。旧数据库和旧密钥无需移动或删除。

复制 deploy/.env 为 deploy/.env.restore，设独立项目名 seekbell-restore、端口18000、匹配或兼容的精确镜像、后台 false。先恢复，后启动：

```bash
docker compose --env-file deploy/.env.restore -f deploy/compose.yaml run --rm --no-deps \
  -v "$PWD/backups:/backups:ro" seekbell \
  python -m seekbell.backup restore /backups/pre-upgrade.sbb
docker compose --env-file deploy/.env.restore -f deploy/compose.yaml up -d --wait
```

先验证归档认证、固定成员、SQLite 完整性/外键及版本，再在私有暂存目录验证管理员、迁移、所有密文配置，并撤销全部浏览器会话。未知/较新数据库版本拒绝恢复；迁移或密钥校验失败不安装文件。安装前写入并fsync中断标记，完整数据库/密钥落盘后移除标记，才释放锁；残留标记会阻止服务和维护进程启动。异常中断若留下半安装目标不会继续在线使用，应保留检查并恢复至另一空卷。

在隔离环境检查：重新登录、账号/规则/设置、四渠道秘密可解密、已见/已发账本不变、相同帖子不重新入队、就绪状态。恢复会回到备份时间，之后的已发回执不在备份中，待发/租约可能再次发送；不能承诺无重复。恢复验证期间禁外网，启用后台前检查待投递和结果未知记录。

升级顺序：停止旧服务 → 用支持备份的匹配工具创建并另存备份 → 记录旧镜像完整 SHA/digest、数据库版本与卷名 → 在独立卷恢复并用候选镜像迁移/检查 → 检查通过后才安排切换。不要双实例读写同一卷。首次从M3迁入M4时 schema 同为0007，可用M4工具在停服后备份；未来旧schema应使用对应版本工具。

失败回退使用**旧镜像 + 升级前数据及原密钥**；切回保留未修改的旧卷，或使用兼容工具从备份恢复到新卷。不要让旧镜像打开迁移后的新卷，也不自动 downgrade。候选启动失败不能通过 health/live 视作升级成功；需检查进程退出及 ready。演练用临时数据/隔离卷，正式切换另行授权。

## GHCR 手动流程

.github/workflows/image.yml 仅 workflow_dispatch/main，默认 publish=false，仅构建 amd64/arm64，不登录或推送；普通 push/PR 仍只有现有 CI。发布前须确认命名空间、包可见性与授权，并为 ghcr-release 环境配置所需审核人/分支保护（仅写 environment 名称不自动产生人工门禁）。未获授权不派发 publish=true。

获准后由受信任操作员手动触发，workflow 使用短期 GITHUB_TOKEN，仅该作业 packages:write，完整 SHA 标签、OCI来源/修订、摘要写入结果；不创建 latest，不自动部署。首次创建的GHCR包默认私有，仍须实际核对可见性和拉取权限。多架构构建成功不代表原生 arm64 已运行验证。

依据：[Compose服务配置](https://docs.docker.com/reference/compose-file/services/)、[Docker日志轮换](https://docs.docker.com/engine/logging/drivers/local/)、[GitHub镜像发布](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)、[GHCR权限与可见性](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)。本阶段未派发发布流程。
