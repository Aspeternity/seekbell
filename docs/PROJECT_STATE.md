# 当前状态

更新：2026-11-12（Asia/Shanghai）。

## 开局

正式环境为SeekBell-Dev的`/home/dev/projects/seekbell`，先运行`python3 scripts/dev_status.py`。main `4977480`（PR #38），已发布版本0.9.0（镜像digest `sha256:206852a9…c02080`），见[v0.9.0记录](history/2026-11-12-v0.9.0发布.md)。当前在本地分支`after-0.9.0`（基于main，仅本次发布记录与文档状态更新，未推送）。

## 计划位置

M0–M4完成；v0.8.0运行中心、v0.9.0（设置六类、备份重构与自动备份、数据页内容上限、告警审查、运行中心美化与内容记录、换页不闪）已发布。WebDAV远程副本暂缓（用户11-11）；备份第三期为升级前备份，见[方案](plans/2026-11-10-备份重构方案.md)顶部调整说明。运行中心阶段三的链接/ID搜索与查不到说明经用户决定不做（11-12，已移入方案“不做”），处理过程小结已随0.9.0发布；M5真实RSS、四渠道和恢复验收未完成。

## 进行中

无进行中的改动。0.9.0的界面（运行中心三卡、内容记录、告警页、数据页、备份页、换页不闪）用户未逐项复审即授权发版，后续反馈按新改动处理。

未提交：`assets/brand/`图标（待审）。

## 下一步

1. 用户实机升级0.9.0时：先完整备份（0.8.x备份是回退唯一依据），升级后检查自动备份已开启、告警延迟保持原值。部署和真实发送需用户另行授权或亲自执行。
2. WebDAV远程副本（暂缓）：先出简短方案请用户确认细则（上传是否加密、配置位置与字段、NAS保留份数、上传哪些类型、失败故障、从NAS恢复、测试连接），CI用模拟WebDAV服务。
3. 备份第三期升级前备份；程序日志待议；图标采用。
4. 本地累积期间CI不运行：大改动后可在本机跑相关容器检查（`docker build -t seekbell:candidate .`后`python3 scripts/check_{container,backup_container,release_container,proxy_container}.py seekbell:candidate --revision $(git rev-parse HEAD)`），避免发版时才暴露脚本未同步。

## 授权

0.9.0的推送、PR、发版授权（11-11）已用完。此后改动先本地累积，不推送、不开PR、不发版、不部署、不真实发送，也不主动提议；发版时机由用户提出。实例只读命令的既有授权为用户本人执行。

## 按需读取

- 备份：SPEC 6.5.3–6.5.5、BACKUP_RESTORE、ARCHITECTURE“备份重构第一期/第二期”“备份导入”、`backend/seekbell/{backup.py,services/backups.py,services/backup_schedule.py,api/backups.py}`、`frontend/src/{pages/BackupSettings.vue,components/BackupScheduleSettings.vue,components/BackupRestoreWizard.vue,backups.ts}`。
- 设置：SPEC 6.5.2、UI_DESIGN“系统设置六类”、`frontend/src/settings.ts`、`api/settings.py`。
- 数据页：SPEC 6.5.6、UI_DESIGN“数据页”、ARCHITECTURE“内容上限与自动回收”、`services/{retention,maintenance}.py`、`db/runtime.py`、`pages/RetentionSettings.vue`。
- 告警：SPEC 6.5.7、ARCHITECTURE“告警审查”、UI_DESIGN“告警页（2026-11-11美化重构）”、`services/{alerts,stalls}.py`、`pages/AlertsSettings.vue`。
- 运行中心与内容记录：UI_DESIGN“运行中心美化”、docs/plans/2026-11-09方案、pages/{Operations,OperationsStatus,Content}.vue、services/{operations,fault_guide,alerts,runtime}.py。
- 发布/实机：IMAGE_RELEASE正式发布段、ROADMAP当前阶段、ACCEPTANCE；图标见assets/brand/README.md。
