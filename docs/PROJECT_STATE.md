# 当前状态

更新：2026-11-11（Asia/Shanghai）。

## 开局

正式环境为SeekBell-Dev的`/home/dev/projects/seekbell`，先运行`python3 scripts/dev_status.py`。main `85618ba`（PR #37），已发布版本0.8.0。当前在本地分支`backup-rework`（未推送）。

## 计划位置

M0–M4完成；v0.8.0（运行中心）已发布，见[v0.8.0记录](history/2026-11-09-v0.8.0运行中心.md)。本地未推送：系统设置重组`01562f0`（[归档](history/2026-11-10-系统设置重组.md)，SPEC 6.5.2）；备份重构第一期`9fd28ba`（[归档](history/2026-11-10-备份重构第一期.md)，SPEC 6.5.3）；第二期本机自动备份`9ffb6f3`（[归档](history/2026-11-11-备份第二期自动备份.md)，SPEC 6.5.4）；备份页布局与导入`6f6e3cf`（[归档](history/2026-11-11-备份页布局与导入.md)，SPEC 6.5.5）；数据页内容上限与自动回收（本地提交，[归档](history/2026-11-11-数据页内容上限.md)，SPEC 6.5.6）。WebDAV远程副本暂缓（用户11-11），第三期为升级前备份，见[方案](plans/2026-11-10-备份重构方案.md)顶部调整说明。运行中心阶段三未开始；M5真实RSS、四渠道和恢复验收未完成。

## 进行中

无进行中的改动。最近完成：数据页重构（11-11用户确认，已本地提交）——数据页只留“历史保留”一卡：现有数据五格、保留天数、内容上限（只限未命中内容，默认不限）、收紧时确认框给预估；删除数据页存储占用、预览按钮和“最近一次清理”；数据库启动时一次性切换自动增量回收，清理后文件变小。迁移`0022_content_limit`。细节与证据见[归档](history/2026-11-11-数据页内容上限.md)。

未提交：`assets/brand/`图标（待审）。

## 下一步

1. 用户复审数据页与备份页（预览：`pnpm --dir frontend build`后`uv run --frozen python scripts/run_web_smoke.py --system --port 8099`，浏览器Ctrl+Shift+R；8099上旧进程需先停掉才能加载新后端）。
2. WebDAV远程副本（11-11用户：先不做，暂缓）：以后先出简短方案请用户确认细则（上传是否加密、配置位置与字段、NAS保留份数、哪些类型上传、失败故障、从NAS恢复、测试连接），再实现；CI用模拟WebDAV服务，不连真实NAS。
3. 之后第三期升级前备份；运行中心阶段三；程序日志待议；图标采用。
4. **暂不发版**（用户11-10明确）。发版时机由用户提出；届时本地分支合成一个PR，`bump_version.py`一次，CHANGELOG汇总六类重组、数据页内容上限与自动回收、迁移0019–0022（回退需0018备份）与备份格式不兼容旧版。

## 授权

用户确认重组方案、备份重构方案，要求实施第一期与第二期（本机自动备份→WebDAV）；11-11确认并要求实施数据页重构。不推送、不开PR、不发版、不部署、不真实发送，也不主动提议；本地分支与提交为实施所需。实例只读命令的既有授权为用户本人执行。

## 按需读取

- 备份：SPEC 6.5.3–6.5.5、BACKUP_RESTORE、ARCHITECTURE“备份重构第一期/第二期”“备份导入”、`backend/seekbell/{backup.py,services/backups.py,services/backup_schedule.py,api/backups.py}`、`frontend/src/{pages/BackupSettings.vue,components/BackupScheduleSettings.vue,components/BackupRestoreWizard.vue,backups.ts}`。
- 设置：SPEC 6.5.2、UI_DESIGN“系统设置六类”、`frontend/src/settings.ts`、`api/settings.py`。
- 数据页：SPEC 6.5.6、UI_DESIGN“数据页”、ARCHITECTURE“内容上限与自动回收”、`services/{retention,maintenance}.py`、`db/runtime.py`、`pages/RetentionSettings.vue`。
- 运行中心：docs/plans/2026-11-09方案、pages/{Operations,OperationsStatus}.vue、services/{operations,fault_guide,alerts,runtime}.py。
- 发布/实机：IMAGE_RELEASE正式发布段、ROADMAP当前阶段、ACCEPTANCE；图标见assets/brand/README.md。
