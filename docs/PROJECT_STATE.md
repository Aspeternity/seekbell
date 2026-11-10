# 当前状态

更新：2026-11-10（Asia/Shanghai）。

## 开局

正式环境为SeekBell-Dev的`/home/dev/projects/seekbell`，先运行`python3 scripts/dev_status.py`。main `85618ba`（PR #37），已发布版本0.8.0。当前在本地分支`backup-rework`。

## 计划位置

M0–M4完成；v0.8.0（运行中心）已发布，证据见[v0.8.0记录](history/2026-11-09-v0.8.0运行中心.md)。系统设置重组已在本地分支`settings-reorganization`提交`01562f0`（未推送），记录见[重组归档](history/2026-11-10-系统设置重组.md)，契约SPEC 6.5.2。备份重构按[方案](plans/2026-11-10-备份重构方案.md)分三期，第一期已在本地分支`backup-rework`提交（未推送），契约SPEC 6.5.3。运行中心阶段三未开始；M5真实RSS、四渠道和恢复验收未完成。

## 进行中

备份重构第一期，分支`backup-rework`（基于`01562f0`），已提交、未推送：
- 后端：`backup.py`改为标准tar.gz（不加密、不含管理员与会话、最小USTAR读取器、`inspect_backup`、`restore_backup`必须给管理员）；新`services/backups.py`（备份库、保留、启动清理遗留）；`api/backups.py`重写（立即备份、票据下载、检查/暂存/恢复、初始化页inspect/restore）；`config.backup_dir`；maintenance存储改backup_count/bytes；fault_guide文案；release/manage_release删`--restored`；backup_demo、check_backup_container、check_crypto_compatibility、check_release_container同步。无迁移。
- 前端：`BackupSettings.vue`重写、新`BackupRestoreWizard.vue`、`backups.ts`、`store.ts`（uploadBackup/restoreBackup）、Auth初始化页向导、StorageSummary、`byteSize`加KiB、workspace.css；删`BackupRestoreForm.vue`、`RestoreLeftovers.vue`。
- 测试：重写`tests/test_backup.py`、`tests/test_web_backups.py`、`frontend/tests/backup/backup.spec.ts`；调整test_release、test_settings_reorganization、approved-ui、live/about、system/settings。
- 文档：SPEC 6.5.3、ARCHITECTURE末节、DECISIONS、UI_DESIGN末节、BACKUP_RESTORE重写、RELEASES、README、方案状态已回写。
- 验收修正（11-10，同一提交）：①下载/删除不要密码（恢复保留）；删除用全局`confirmAction`弹窗，恢复向导居中弹窗。②删除操作记录（前后端、BackupRecord，新迁移`0020_drop_backup_records`，部署注释/README/测试修订号同步）。③备份名称：`services/backups.py` labels.json（POST可带name、PATCH改名）、新`BackupNameDialog.vue`。④状态卡三格信息块+存放位置复制+列表名称标题/空状态。⑤修复：文件选择框取消的冒泡cancel关闭恢复弹窗（`dialogCancel`只认自身，e2e用旧处理验证会失败）。⑥去掉备份页凭据提示条；名称弹窗点外部关闭（按坐标判断，内边距不误关）。⑦存放位置移入“已存备份”块第三行（文件夹图标、省略、复制图标），`byteSize(0)`为“0 KiB”，无备份不显示大小行。证据（未提交工作区）：pytest全量1013 passed；ruff、typecheck、prettier、build；Playwright backup 2、approved-ui 8、live 6、system 26通过（⑥后backup 2、approved-ui 8复跑通过）。
- 仍未提交：`assets/brand/`图标（待审，未纳入本提交）；v0.8.0发布记录已随`01562f0`提交。

证据（本机，提交前工作区）：`uv run --frozen pytest tests -q -n auto` 1017 passed；ruff check/format、prettier、前端build通过；Playwright backup 2、approved-ui 8、system 26、live 6、ui 8、retention 2通过；backup_demo通过。`check_backup_container.py`用工作区本地镜像`seekbell:backup-rework-local`（禁外网）全部通过（网页备份/票据下载/检查/就地恢复/恢复前备份、运行中拒绝停服命令、停服create/restore与恢复实例登录、backup_demo）；其网页探针改为只比较配置表（运行时持续写采集记录，整库比较会偶发不等）。`check_release_container.py`与proxy套件未跑，交CI。

## 下一步

1. 用户复审备份页第二轮（名称、三格状态卡、无操作记录、文件选择框修复）（一次性预览：`pnpm --dir frontend build`后`uv run --frozen python scripts/run_web_smoke.py --system --port 8099`，浏览器Ctrl+Shift+R）；按反馈修改。
2. 继续在本地累积：备份第二期（自动备份、独立备份目录，注意`SEEKBELL_BACKUP_DIR`命名冲突）与第三期（升级前备份）；运行中心阶段三；程序日志待议；图标采用。
3. **暂不发版**（用户11-10明确，不按单项改动发版）。发版时机由用户提出；届时`backup-rework`等本地分支合成一个PR，`bump_version.py`一次，CHANGELOG汇总六类重组、迁移0019（回退需0018备份）与备份格式不兼容旧版。

## 授权

用户确认重组方案与备份重构方案并要求实施第一期。不推送、不开PR、不发版、不部署、不真实发送，也不主动提议；本地分支与提交为实施所需。实例只读命令的既有授权为用户本人执行。

## 按需读取

- 备份：SPEC 6.5.3、BACKUP_RESTORE、ARCHITECTURE“备份重构第一期”、`backend/seekbell/{backup.py,services/backups.py,api/backups.py}`、`frontend/src/{pages/BackupSettings.vue,components/BackupRestoreWizard.vue,backups.ts}`。
- 设置：SPEC 6.5.2、UI_DESIGN“系统设置六类”、`frontend/src/settings.ts`、`api/settings.py`。
- 运行中心：docs/plans/2026-11-09方案、pages/{Operations,OperationsStatus}.vue、services/{operations,fault_guide,alerts,runtime}.py。
- 发布/实机：IMAGE_RELEASE正式发布段、ROADMAP当前阶段、ACCEPTANCE；图标见assets/brand/README.md。
