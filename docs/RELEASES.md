# 保留原卷的切换与升级回退（M4第三子阶段）

适用标准Compose单实例、Linux本地Unix socket Docker、同一宿主机/同一操作用户。维护工具用Python标准库和宿主机Docker CLI，不将Docker socket或发布权限交给Web。当前支持已有命名卷、UID/GID10001、只读根、单个127.0.0.1端口（或禁外网演练）；自定义挂载/静态路径/未知启动参数需另行核对，不能假定本工具保留任意自定义Compose配置。

## 数据与失败边界

prepare只接受已停止的标准服务。新建独立命名卷，目标镜像在禁网络维护容器中读取原卷的只读挂载、持原实例同一锁，SQLite一致快照含已提交WAL。已知旧迁移可在**新卷**升级，随后校验当前结构/完整性/外键/管理员/原钥和全部历史密文，清除副本会话，原子发布候选与私有准备记录。原卷不迁移、不覆盖、不删；未知迁移（包括此前不兼容旧库）拒绝。不要直接换旧镜像启动已升级的新卷，不运行数据库downgrade。

activate重新检查Docker daemon与Compose配置、原实例是否被启动/替换、来源快照/原钥是否变化、候选数据库/原钥/构建版本校验；全部通过才按固定image ID + 已存在volume + data_dir成对启动。compose.release.yaml声明external卷，拼错或丢卷不会静默建空库。正常实例保留原本机端口，演练实例保留禁外网且无端口。启动会按备份/原配置运行后台；有真实来源/目标时将实际采集或发送。

准备/迁移失败时原服务保持停止、新卷保留诊断；不会自动启动原实例。切换启动/就绪失败会停止新实例，原卷和新卷均保留，不自动回退。只有显式rollback --accept-data-loss才停止当前匹配实例，再启动原image ID + 原卷 + 原data_dir；回退放弃切换后的新数据与回执，可能重复发送。该标志表示操作者已确认此影响，不是数据合并。故障中断可能停在preparing/activating等中间状态，status必须同时看记录phase与实际observed/running；不要把旧phase当成功，也不要删除卷或手改迁移号。

本机状态目录0700、状态文件0600、原子更新/fsync；只含image ID、卷、项目、配置指纹和阶段，不含口令或数据库内容。操作按本地daemon/项目加文件锁，防止同一操作用户并发使用本工具；不协调其他用户/宿主机或绕过工具的Docker命令。准备后禁止手工启停/改卷，变化后须重新prepare到新卷。维护CLI永不删除数据卷，失败候选也保留，清理应另行核对且不使用全局prune。文件系统权限是维护信任边界，准备记录不是对恶意宿主机管理员的签名。

## 实际命令

在已确认的SeekBell-Dev正式目录操作。下面seekbell-test仅为示例项目名，必须替换成实际项目；**不能拿旧不兼容卷或当前验收实例做演练**。先核对目标固定提交镜像已构建/加载（不自动拉取）、源/目标磁盘余量、现有项目和加密备份。维护需要原卷体积之外约3倍数据库暂存空间，另预留新候选及后续增长；升级副本含明文数据库/原钥，须存可信本机盘。普通加密备份仍按BACKUP_RESTORE保留并另存口令。

~~~bash
python3 scripts/manage_release.py --help
# 建议每次使用新的私有状态文件；状态文件必须保留以便回退。
mkdir -p "$HOME/.local/share/seekbell-releases"
chmod 700 "$HOME/.local/share/seekbell-releases"
export SEEKBELL_RELEASE_STATE="$HOME/.local/share/seekbell-releases/before-upgrade.json"
export SEEKBELL_IMAGE='seekbell:已验证的固定提交标签'
docker compose -p seekbell-test stop
python3 scripts/manage_release.py --state "$SEEKBELL_RELEASE_STATE" prepare \
  --project seekbell-test --image "$SEEKBELL_IMAGE"
python3 scripts/manage_release.py --state "$SEEKBELL_RELEASE_STATE" status
# 这一步将启用新实例的原启停配置/队列；有真实目标会实际发送。
python3 scripts/manage_release.py --state "$SEEKBELL_RELEASE_STATE" activate
python3 scripts/manage_release.py --state "$SEEKBELL_RELEASE_STATE" status
~~~

若是启用网页已上传验证的web-restore副本，使用**新状态路径**，prepare加--restored。先停当前原服务；工具会将固定web-restore复制到另一个新卷，再迁移/验证/切换，不直接在原卷子目录中启动。副本中的旧会话已撤销，切换后使用备份当时管理员登录。用于回退的原卷保留的是切换前工作空间。

~~~bash
python3 scripts/manage_release.py --state "$SEEKBELL_RELEASE_STATE" prepare \
  --project seekbell-test --image "$SEEKBELL_IMAGE" --restored
~~~

需要回退时，先查看status，再明确接受丢弃新数据：

~~~bash
python3 scripts/manage_release.py --state "$SEEKBELL_RELEASE_STATE" status
python3 scripts/manage_release.py --state "$SEEKBELL_RELEASE_STATE" rollback --accept-data-loss
~~~

每次维护生成不同状态文件和候选卷，保存每个版本对。不要在切换后直接执行只带原compose.yaml的up：它会按项目默认卷重新选数据。日常启停应先根据状态核对实际运行的镜像/卷；本阶段维护工具提供切换/回退，未实现通用Compose配置管理或无人值守升级。status为只读核对；重复activate会拒绝，避免重放切换。

## 自动演练

~~~bash
uv run --frozen pytest -q tests/test_release.py tests/test_backup.py tests/test_web_backups.py
python3 scripts/check_release_container.py "$SEEKBELL_IMAGE" --revision "$SEEKBELL_REVISION"
~~~

只创建唯一临时项目/命名卷，来源和维护/服务全程禁外网、无发布端口；原卷只读快照/迁移，失败和成功切换均保留原卷。演练派生临时镜像加入合成0010迁移（成功/事务失败）和启动失败CMD，验证迁移失败不启原/新、启动失败停止新实例不自动回退、显式回退匹配原image/volume，以及网页恢复候选转入新卷。合成0010不进入产品迁移，不等同未来任意版本均兼容。结束仅清理本轮明确跟踪的资源；实际部署/真实发送/用户验收另记。
