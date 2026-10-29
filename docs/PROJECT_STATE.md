# 当前状态

更新：2026-10-29（Asia/Shanghai）。main 43c6baf（PR #25）= v0.4.0；备份调整在分支release-0.5.0（见“进行中”）。

## 开局

先运行`python3 scripts/dev_status.py`取得分支、工作区、版本一致性和最新CI，不再逐条手工核对。与本文不符时以实际为准并先更新本文。

## 计划位置

M0–M4已完成。最新公开版本v0.4.0（见下）；v0.3.0为ghcr.io/aspeternity/seekbell:0.3.0@sha256:fe1d8182a8fc3db29f369813dbbff12740a958b2bca9d0c38dde51a334a0cab3。v0.2.0见[发布归档](history/2026-10-29-v0.2.0发布进度.md)。现用实例尚未部署0.2.0/0.3.0/0.4.0。下一阶段为M5实机验收（ROADMAP“当前阶段”表），需另行授权。

## 已完成：v0.4.0（网页直接恢复与设置纠正）

PR #25（CI 40893571630全绿）squash合并为main 43c6baf；Release运行40896504548成功：https://github.com/Aspeternity/seekbell/releases/tag/v0.4.0 ，ghcr.io/aspeternity/seekbell:0.4.0@sha256:349aab85cf75cf0f0365c264a400bc494ef6eaa297e777b0d9624fbdd3a2fb48（amd64/arm64），6附件经工作流匿名核对。改动、证据与用户选择见[v0.4.0记录](history/2026-10-29-v0.4.0设置纠正与网页直接恢复.md)。网页直接恢复仅在本机/CI临时环境验证，未做真实部署验证。

## 进行中：v0.5.0备份表单三项调整（分支release-0.5.0，基于43c6baf）

用户确认（DECISIONS 2026-10-29 v0.4.0后）：①统一“备份口令”；②恢复不用备份中的管理员——设置页保留当前管理员并保持登录，新安装恢复时设置管理员，CLI回车沿用/填写则替换；③备份下载/恢复/删除副本的当前密码15分钟免确认（进程内Confirmations，无迁移）。改动：backend/seekbell/{backup.py,api/backups.py,api/auth.py,services/authentication.py,main.py}、前端BackupRestoreForm/BackupSettings/Auth/store、相关测试与check_*脚本；SPEC/BACKUP_RESTORE/ARCHITECTURE末节/UI_DESIGN末段/README/CHANGELOG“未发布”已回写。证据（本机，未提交工作区）：pytest test_backup/test_release/test_web_backups/test_administrator/test_proxy/test_privacy/test_baseline共135通过；ruff、prettier、vue-tsc构建通过；Playwright test:backup与test:approved-ui桌面/移动全过。未跑全量pytest与容器演练（check_backup_container/check_proxy_container仅语法检查，CI会跑）。

## 下一步

1. 已bump 0.5.0：PR CI通过→squash合并→`gh release create v0.5.0`→一次`gh run watch`；完成后把本段移入history并记录digest。
2. 下一阶段M5实机验收：在授权环境部署v0.4.0（含网页恢复实测），验证真实RSS与四渠道收信，见ROADMAP“当前阶段”和ACCEPTANCE。
3. 以后发布按IMAGE_RELEASE“正式发布（三步）”；连续步骤可写成一个后台脚本一次等待。

## 授权

2026-10-29用户授权：提交、开PR，CI通过后合并并发布v0.5.0（Release+GHCR）。不含部署或真实发送。

## 按需读取（只读与任务相关的项）

- 设置界面：UI_DESIGN末节、SPEC第175行、frontend/src/pages/*Settings.vue
- 发布/CI：IMAGE_RELEASE“正式发布”、.github/workflows/*.yml、scripts/{bump_version,ci_reuse,verify_release}.py
- 实机验收：ROADMAP“当前阶段”、ACCEPTANCE、RELEASES
- 其他历史只在本文链接指向时阅读。
