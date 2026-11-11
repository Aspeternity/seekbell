# 当前状态

更新：2026-11-11（Asia/Shanghai）。

## 开局

正式环境为SeekBell-Dev的`/home/dev/projects/seekbell`，先运行`python3 scripts/dev_status.py`。main `85618ba`（PR #37），已发布版本0.8.0。当前在本地分支`backup-rework`（未推送）。

## 计划位置

M0–M4完成；v0.8.0（运行中心）已发布，见[v0.8.0记录](history/2026-11-09-v0.8.0运行中心.md)。本地未推送：系统设置重组`01562f0`（[归档](history/2026-11-10-系统设置重组.md)，SPEC 6.5.2）；备份重构第一期`9fd28ba`（[归档](history/2026-11-10-备份重构第一期.md)，SPEC 6.5.3）；第二期本机自动备份`9ffb6f3`（[归档](history/2026-11-11-备份第二期自动备份.md)，SPEC 6.5.4）；备份页布局与导入`6f6e3cf`（[归档](history/2026-11-11-备份页布局与导入.md)，SPEC 6.5.5）；数据页内容上限与自动回收（本地提交，[归档](history/2026-11-11-数据页内容上限.md)，SPEC 6.5.6）；告警审查（本地提交，[归档](history/2026-11-11-告警审查.md)，SPEC 6.5.7）。WebDAV远程副本暂缓（用户11-11），第三期为升级前备份，见[方案](plans/2026-11-10-备份重构方案.md)顶部调整说明。运行中心阶段三未开始；M5真实RSS、四渠道和恢复验收未完成。

## 进行中

无进行中的改动。最近完成：数据页重构（11-11用户确认，已本地提交）——数据页为“现有数据”三格状态卡（内容/命中、通知、最早内容；复审后去掉“问题”格）+“保留策略”卡：保留天数、内容上限（只限未命中内容，默认不限）、收紧时确认框给预估；删除数据页存储占用、预览按钮和“最近一次清理”；数据库启动时一次性切换自动增量回收，清理后文件变小。迁移`0022_content_limit`。细节与证据见[归档](history/2026-11-11-数据页内容上限.md)。

已本地提交`d77ce1d`（11-11用户要求，待复审）：①数据页去掉“命中的内容不计入”提示；②换页不闪：根因是各页挂载后先画空卡片、首读返回后再填充跳动（模拟120ms延迟实测设置六类、运行状态、内容与命中、概览均有空帧）。App主区/设置分类/运行中心分区加`<Suspense>`，读数据页面setup末尾`await untilShown(...)`（新`frontend/src/viewReady.ts`），旧页最多保留400ms；父子卡并行首读；会话卡改generation重读；页脚、滚顶、聚焦跟随实际显示的页。新增`tests/system/settings.spec.ts`“never paints an empty card”逐帧检测；`tests/loading`与`history-ui-fixes`首读提示时间改为400ms。证据（本机，`d77ce1d`）：system/loading/operations/retention/backup/first-entry/workspace-stability/content-stability/ui/approved-ui/history/history-ui-fixes/hotlist全部通过；把保留时间临时改0时新测试捕获96个空帧失败，已还原。说明见ARCHITECTURE“换页不闪”、UI_DESIGN加载规则。

告警审查（11-11用户“全都做吧”，已本地提交，待复审）：告警设置留在设置页；服务卡住（循环超120秒）记录并告警；恢复/提醒只发给收到过该故障的目标；可选“仍未恢复提醒”6/24小时；消息附中文原因与持续时长；新装默认延迟1分钟；页面两区+最近一次告警+单渠道提示；迁移`0023_alert_reminders`。证据（本机）：后端全量1038项、浏览器system/operations/approved-ui/ui/runtime全部通过，见[归档](history/2026-11-11-告警审查.md)。

告警页美化重构（11-11用户要求，三轮复审后已本地提交，待再审）：只留一张“系统告警”卡，卡头只有大号开关（设置卡卡头开关统一44×24，自动备份卡同）；目标选择卡、测试同行；延迟改为0–1440整数分钟自填（后端`MAX_DELAY_SECONDS`，API `multiple_of=60`），提醒仍三档；删除状态卡、后端只读`recent`、“查看问题历史”链接与规则提示块；修复校验提示残留（`settings.ts`草稿变化即清除校验错误）。见UI_DESIGN“告警页（…定稿）”。证据（本机）：后端告警相关43项、浏览器system 28项（含卡片间距、校验提示随草稿消失回归测试）、approved-ui 8项、ui 8项、backup 2项通过；桌面/手机截图检查。

未提交：`assets/brand/`图标（待审）。

## 下一步

1. 用户复审告警页（新两卡布局）、换页不闪与数据页、备份页（预览：`pnpm --dir frontend build`后`uv run --frozen python scripts/run_web_smoke.py --system --port 8099`，浏览器Ctrl+Shift+R；8099上旧进程需先停掉才能加载新后端）。
2. WebDAV远程副本（11-11用户：先不做，暂缓）：以后先出简短方案请用户确认细则（上传是否加密、配置位置与字段、NAS保留份数、哪些类型上传、失败故障、从NAS恢复、测试连接），再实现；CI用模拟WebDAV服务，不连真实NAS。
3. 之后第三期升级前备份；运行中心阶段三；程序日志待议；图标采用。
4. **暂不发版**（用户11-10明确）。发版时机由用户提出；届时本地分支合成一个PR，`bump_version.py`一次，CHANGELOG汇总六类重组、数据页内容上限与自动回收、迁移0019–0023（回退需0018备份）、告警审查（新装默认延迟1分钟且可自填0–1440分钟、仍未恢复提醒、Webhook alert新增字段）与备份格式不兼容旧版。

## 授权

用户确认重组方案、备份重构方案，要求实施第一期与第二期（本机自动备份→WebDAV）；11-11确认并要求实施数据页重构。不推送、不开PR、不发版、不部署、不真实发送，也不主动提议；本地分支与提交为实施所需。实例只读命令的既有授权为用户本人执行。

## 按需读取

- 备份：SPEC 6.5.3–6.5.5、BACKUP_RESTORE、ARCHITECTURE“备份重构第一期/第二期”“备份导入”、`backend/seekbell/{backup.py,services/backups.py,services/backup_schedule.py,api/backups.py}`、`frontend/src/{pages/BackupSettings.vue,components/BackupScheduleSettings.vue,components/BackupRestoreWizard.vue,backups.ts}`。
- 设置：SPEC 6.5.2、UI_DESIGN“系统设置六类”、`frontend/src/settings.ts`、`api/settings.py`。
- 数据页：SPEC 6.5.6、UI_DESIGN“数据页”、ARCHITECTURE“内容上限与自动回收”、`services/{retention,maintenance}.py`、`db/runtime.py`、`pages/RetentionSettings.vue`。
- 告警：SPEC 6.5.7、ARCHITECTURE“告警审查”、UI_DESIGN“告警页（2026-11-11美化重构）”、`services/{alerts,stalls}.py`、`pages/AlertsSettings.vue`。
- 运行中心：docs/plans/2026-11-09方案、pages/{Operations,OperationsStatus}.vue、services/{operations,fault_guide,alerts,runtime}.py。
- 发布/实机：IMAGE_RELEASE正式发布段、ROADMAP当前阶段、ACCEPTANCE；图标见assets/brand/README.md。
