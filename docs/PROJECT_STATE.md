# 当前状态

更新：2026-11-11（Asia/Shanghai）。

## 开局

正式环境为SeekBell-Dev的`/home/dev/projects/seekbell`，先运行`python3 scripts/dev_status.py`。main `85618ba`（PR #37），已发布版本0.8.0。当前在本地分支`backup-rework`（未推送）。

## 计划位置

M0–M4完成；v0.8.0（运行中心）已发布，见[v0.8.0记录](history/2026-11-09-v0.8.0运行中心.md)。本地未推送：系统设置重组`01562f0`（[归档](history/2026-11-10-系统设置重组.md)，SPEC 6.5.2）；备份重构第一期`9fd28ba`（[归档](history/2026-11-10-备份重构第一期.md)，SPEC 6.5.3）；第二期本机自动备份（本次提交，SPEC 6.5.4）。第二期后半为WebDAV远程副本，第三期为升级前备份，见[方案](plans/2026-11-10-备份重构方案.md)顶部调整说明。运行中心阶段三未开始；M5真实RSS、四渠道和恢复验收未完成。

## 进行中

备份第二期·本机自动备份已实现（分支`backup-rework`，本地提交）：迁移`0021_backup_schedule`（默认开启每天03:00保留7）；`services/backup_schedule.py`（时刻计算、补做一次、每小时重试、`runtime:backup`故障failed/overdue）；`BackupScheduler`在`main.open_workspace`中启动（不进Runtime）；`backups.create/prune(keep=)`；`backup.restore_backup`重置计划运行状态；`api/backups.py` GET/PUT `/schedule`及状态`health`、`schedule`；operations `_storage_problems`、fault_guide两条；前端`BackupScheduleSettings.vue`、状态卡`.backup-next`、`backups.ts`；`authentication.initialize`创建管理员时重新计时；测试`tests/test_backup_schedule.py`（12项），backup e2e加自动备份段；测试修订号改0021，Portainer注释schema 0021，`check_release_container.py`夹具down_revision改0021。文档：SPEC 6.5.4、方案顶部、DECISIONS、ARCHITECTURE末节、UI_DESIGN末节、BACKUP_RESTORE、README。

证据（本机工作区，提交前）：`uv run --frozen pytest tests -q -n auto` 1025 passed；ruff check/format、prettier、前端build通过；Playwright backup 2、approved-ui 8、system 26、live 6、ui 8、operations 8通过；backup_demo通过。容器检查未跑（无容器相关改动，交CI）。

未提交：`assets/brand/`图标（待审）。

## 下一步

1. 用户复审自动备份卡与状态卡（预览：`pnpm --dir frontend build`后`uv run --frozen python scripts/run_web_smoke.py --system --port 8099`，浏览器Ctrl+Shift+R）。
2. WebDAV远程副本：先出简短方案请用户确认细则（上传是否加密、配置位置与字段、NAS保留份数、哪些类型上传、失败故障、从NAS恢复、测试连接），再实现；CI用模拟WebDAV服务，不连真实NAS。
3. 之后第三期升级前备份；运行中心阶段三；程序日志待议；图标采用。
4. **暂不发版**（用户11-10明确）。发版时机由用户提出；届时本地分支合成一个PR，`bump_version.py`一次，CHANGELOG汇总六类重组、迁移0019–0021（回退需0018备份）与备份格式不兼容旧版。

## 授权

用户确认重组方案、备份重构方案，要求实施第一期与第二期（本机自动备份→WebDAV）。不推送、不开PR、不发版、不部署、不真实发送，也不主动提议；本地分支与提交为实施所需。实例只读命令的既有授权为用户本人执行。

## 按需读取

- 备份：SPEC 6.5.3/6.5.4、BACKUP_RESTORE、ARCHITECTURE“备份重构第一期/第二期”、`backend/seekbell/{backup.py,services/backups.py,services/backup_schedule.py,api/backups.py}`、`frontend/src/{pages/BackupSettings.vue,components/BackupScheduleSettings.vue,components/BackupRestoreWizard.vue,backups.ts}`。
- 设置：SPEC 6.5.2、UI_DESIGN“系统设置六类”、`frontend/src/settings.ts`、`api/settings.py`。
- 运行中心：docs/plans/2026-11-09方案、pages/{Operations,OperationsStatus}.vue、services/{operations,fault_guide,alerts,runtime}.py。
- 发布/实机：IMAGE_RELEASE正式发布段、ROADMAP当前阶段、ACCEPTANCE；图标见assets/brand/README.md。
