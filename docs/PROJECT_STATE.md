# 当前状态

更新：2026-11-11（Asia/Shanghai）。

## 开局

正式环境为SeekBell-Dev的`/home/dev/projects/seekbell`，先运行`python3 scripts/dev_status.py`。main `85618ba`（PR #37），已发布版本0.8.0。当前在本地分支`backup-rework`（未推送）。

## 计划位置

M0–M4完成；v0.8.0（运行中心）已发布，见[v0.8.0记录](history/2026-11-09-v0.8.0运行中心.md)。本地未推送：系统设置重组`01562f0`（[归档](history/2026-11-10-系统设置重组.md)，SPEC 6.5.2）；备份重构第一期`9fd28ba`（[归档](history/2026-11-10-备份重构第一期.md)，SPEC 6.5.3）；第二期本机自动备份`9ffb6f3`（SPEC 6.5.4）；备份页布局与导入（本地提交，SPEC 6.5.5）。WebDAV远程副本暂缓（用户11-11），第三期为升级前备份，见[方案](plans/2026-11-10-备份重构方案.md)顶部调整说明。运行中心阶段三未开始；M5真实RSS、四渠道和恢复验收未完成。

## 进行中

备份第二期本机自动备份已提交`9ffb6f3`（[归档](history/2026-11-11-备份第二期自动备份.md)）。WebDAV按用户11-11要求暂缓。

备份页布局与导入（SPEC 6.5.5，用户11-11选方案A；随后去掉说明性文字，自动备份卡改为卡头开关+三个带标签字段，时间改小时/分钟下拉），已实现并本地提交（本次提交）：
- 后端：`services/backups.py`新增`IMPORTED`/`kind_of`/`new_name`/`staging`/`ensure_room`/`same_archive`/`import_archive`；`api/backups.py`新增`POST /import`，删除管理员`POST /inspect`上传检查，初始化页上传检查内联到`setup_inspect`。
- 前端：`BackupSettings.vue`（顺序状态→自动备份→列表，列表卡头导入+立即备份，状态卡去按钮与运行时间行）、`BackupScheduleSettings.vue`（单区块一行，卡头下次时间）、`BackupRestoreWizard.vue`（上传仅初始化页）、`backups.ts`（imported类型）、`workspace.css`。
- 测试：`tests/test_web_backups.py`（导入新增/查重/空间/失败，原上传检查改走库条目）；e2e `backup`、`approved-ui`、`live/about`。
- 文档：SPEC 6.5.5及6.5.3/6.5.4注、UI_DESIGN新节、BACKUP_RESTORE、ARCHITECTURE“备份导入”、DECISIONS、方案顶部。

证据（本机，提交前）：pytest web_backups/backup/backup_schedule/settings_reorganization 119 passed；ruff、prettier、前端build通过；Playwright backup 2、approved-ui 8、system 26、live 6通过；桌面/390px截图人工检查。全量pytest与容器检查未跑（交CI）。

未提交：`assets/brand/`图标（待审）。

## 下一步

1. 用户继续复审备份页（预览：`pnpm --dir frontend build`后`uv run --frozen python scripts/run_web_smoke.py --system --port 8099`，浏览器Ctrl+Shift+R）。
2. WebDAV远程副本（11-11用户：先不做，暂缓）：以后先出简短方案请用户确认细则（上传是否加密、配置位置与字段、NAS保留份数、哪些类型上传、失败故障、从NAS恢复、测试连接），再实现；CI用模拟WebDAV服务，不连真实NAS。
3. 之后第三期升级前备份；运行中心阶段三；程序日志待议；图标采用。
4. **暂不发版**（用户11-10明确）。发版时机由用户提出；届时本地分支合成一个PR，`bump_version.py`一次，CHANGELOG汇总六类重组、迁移0019–0021（回退需0018备份）与备份格式不兼容旧版。

## 授权

用户确认重组方案、备份重构方案，要求实施第一期与第二期（本机自动备份→WebDAV）。不推送、不开PR、不发版、不部署、不真实发送，也不主动提议；本地分支与提交为实施所需。实例只读命令的既有授权为用户本人执行。

## 按需读取

- 备份：SPEC 6.5.3–6.5.5、BACKUP_RESTORE、ARCHITECTURE“备份重构第一期/第二期”“备份导入”、`backend/seekbell/{backup.py,services/backups.py,services/backup_schedule.py,api/backups.py}`、`frontend/src/{pages/BackupSettings.vue,components/BackupScheduleSettings.vue,components/BackupRestoreWizard.vue,backups.ts}`。
- 设置：SPEC 6.5.2、UI_DESIGN“系统设置六类”、`frontend/src/settings.ts`、`api/settings.py`。
- 运行中心：docs/plans/2026-11-09方案、pages/{Operations,OperationsStatus}.vue、services/{operations,fault_guide,alerts,runtime}.py。
- 发布/实机：IMAGE_RELEASE正式发布段、ROADMAP当前阶段、ACCEPTANCE；图标见assets/brand/README.md。
