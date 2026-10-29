# 当前状态

更新：2026-10-29（Asia/Shanghai）。main d3eef8b（PR #24 squash合并）= v0.3.0。本段为发布后更新，尚未提交，随下一个PR带上。

## 开局

先运行`python3 scripts/dev_status.py`取得分支、工作区、版本一致性和最新CI，不再逐条手工核对。与本文不符时以实际为准并先更新本文。

## 计划位置

M0–M4已完成。v0.3.0已公开发布：https://github.com/Aspeternity/seekbell/releases/tag/v0.3.0 ，ghcr.io/aspeternity/seekbell:0.3.0@sha256:fe1d8182a8fc3db29f369813dbbff12740a958b2bca9d0c38dde51a334a0cab3（amd64/arm64），0.3.0与latest一致，6附件经工作流匿名核对。v0.2.0见[发布归档](history/2026-10-29-v0.2.0发布进度.md)。现用实例尚未部署0.2.0/0.3.0。下一阶段为M5实机验收（ROADMAP“当前阶段”表），需另行授权。

## 已完成：v0.3.0（三步发布首次实跑）

用户验收通过设置页面。PR #24 CI 40873763420全绿后合并；Release运行40876108078共4分24秒（v0.2.0为23分）：baseline经tree复用跳过，native双架构并行约2.5分，publish与匿名核对通过。

## 进行中：发布v0.4.0（分支release-0.4.0，基于main d3eef8b）

用户2026-10-29指出：关于与诊断杂乱、预览清理影响无法收起、概览拖动无过渡、说明文字过多、备份页混乱。已改（细节见UI_DESIGN末段）：
- 关于页重做为版本卡+服务状态三格卡：`frontend/src/pages/AboutSettings.vue`、`components/CurrentFaults.vue`、`SystemEventLog.vue`
- 清理预览改为开关并重读：`components/RetentionPreview.vue`；保留/存储文字精简：`pages/RetentionSettings.vue`、`components/StorageSummary.vue`
- 概览排序FLIP过渡、拖动跟随与按槽位定位：`components/OverviewModuleSettings.vue`、`pages/OverviewSettings.vue`
- 备份页单卡切换、失败只清管理员密码、副本提示两页可见、紧凑记录：`pages/BackupSettings.vue`
- 用户要求新增删除恢复副本：后端`DELETE /api/manage/backups/candidate`（再验证密码、操作门禁、不跟随链接、实例锁占用拒绝、移出后删除、记录discard/deleted）`backend/seekbell/api/backups.py`，测试`tests/test_web_backups.py`；前端在副本提示内就地确认；ARCHITECTURE/BACKUP_RESTORE已同步。
- 用户要求网页直接恢复（不重启容器）：`backend/seekbell/main.py`启动拆为open/close_workspace并加恢复期503中间件；`api/backups.py`新增`/apply`与`/api/auth/setup/restore`热切换（原数据移入before-restore-*，失败回滚重开）；`backup.py`旧版本备份暂存迁移、`pause`选项。前端`components/BackupRestoreForm.vue`共用于设置页与初始化页`pages/Auth.vue`，`store.ts`新增restoreBackup。用户选择：恢复表单“恢复后暂停采集和通知”默认勾选；初始化页也可恢复。SPEC/ARCHITECTURE/BACKUP_RESTORE/UI_DESIGN已同步。
- 通用/告警/账户/会话说明精简：`pages/{Preferences,AlertsSettings,SessionSettings,Settings}.vue`；样式`styles/workspace.css`；对应Playwright用例已更新。

证据（本机SeekBell-Dev，未提交工作区）：typecheck/format通过；Playwright system 20、backup 2、hotlist 50、retention 2、approved-ui 8、live 6全部通过；后端全量904项通过（含新增热恢复/旧版本/暂停/首次恢复测试），ruff通过；浏览器backup 2（含设置页恢复与初始化页恢复）、approved-ui 8、live 6、system 20、first-entry 8、ui 8通过。未经用户视觉验收。

## 下一步

1. 发布v0.4.0：PR CI通过→合并→`gh release create v0.4.0 --target <main SHA>`→一次`gh run watch`；完成后把本段移入history并记录digest。
2. 下一阶段M5实机验收：在授权环境部署v0.3.0，验证真实RSS与四渠道收信，见ROADMAP“当前阶段”和ACCEPTANCE。
3. 以后发布按IMAGE_RELEASE“正式发布（三步）”；连续步骤可写成一个后台脚本一次等待。

## 授权

用户2026-10-29授权v0.4.0全流程：提交、推送、PR合并、创建Release、GHCR双架构镜像及latest与Release附件。无部署或真实发送授权。

## 按需读取（只读与任务相关的项）

- 设置界面：UI_DESIGN末节、SPEC第175行、frontend/src/pages/*Settings.vue
- 发布/CI：IMAGE_RELEASE“正式发布”、.github/workflows/*.yml、scripts/{bump_version,ci_reuse,verify_release}.py
- 实机验收：ROADMAP“当前阶段”、ACCEPTANCE、RELEASES
- 其他历史只在本文链接指向时阅读。
