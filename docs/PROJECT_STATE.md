# 当前状态

更新：2026-10-30（Asia/Shanghai）。main 80a5209（PR #26）= v0.5.0。本段为发布后更新，尚未提交，随下一个PR带上。

## 开局

先运行`python3 scripts/dev_status.py`取得分支、工作区、版本一致性和最新CI，不再逐条手工核对。与本文不符时以实际为准并先更新本文。

## 计划位置

M0–M4已完成。最新公开版本v0.5.0（见下）；v0.4.0为ghcr.io/aspeternity/seekbell:0.4.0@sha256:349aab85cf75cf0f0365c264a400bc494ef6eaa297e777b0d9624fbdd3a2fb48，见[v0.4.0记录](history/2026-10-29-v0.4.0设置纠正与网页直接恢复.md)。v0.2.0见[发布归档](history/2026-10-29-v0.2.0发布进度.md)。现用实例尚未部署0.2.0～0.5.0。下一阶段为M5实机验收（ROADMAP“当前阶段”表），需另行授权。

## 已完成：v0.5.0（备份恢复简化）

PR #26 squash合并为main 80a5209；Release运行40911054432成功：https://github.com/Aspeternity/seekbell/releases/tag/v0.5.0 ，ghcr.io/aspeternity/seekbell:0.5.0@sha256:bb1473f497e59418f8da8b622bdac8459b07eb986e7cf97130d0fb69df8dd53d 。改动、证据与CI偶发失败见[v0.5.0记录](history/2026-10-30-v0.5.0备份恢复简化.md)。仅本机/CI验证，未真实部署。

## 进行中：v0.6.0 热榜即时切换（分支codex/hotlist-instant）

用户2026-10-30确认“1+2+3加15分钟宽限和退避拆分”并授权测完提交、推送、发版。契约SPEC 6.6，设计ARCHITECTURE末节，决定DECISIONS首条（含更正：“取消其他周期预取”非用户单独要求）。版本0.6.0，无迁移（schema 0018）。
- 后端：services/hotlists.py（预热、15分钟宽限、GET /api/manage/hotlists看板与25秒长轮询、恢复时wake）、request_budget.py（auxiliary：热榜只共享429/访问验证/Retry-After）、overview_preferences.hotlist_catalog、api/hotlists.py、api/backups.py、main.py。
- 前端：CommunityHotlist.vue看板长轮询、本地切换；store.ts支持AbortSignal。
- 本机验证（SeekBell-Dev，提交前工作区）：全量pytest 912通过；CI全部19组Playwright套件通过（hotlist 50、linuxdo 26等）。未做真实来源/实机验证。

## 下一步

1. v0.6.0：PR通过CI后squash合并，按IMAGE_RELEASE三步发布；完成后把本节移入docs/history并更新计划位置。
2. 下一阶段M5实机验收：在授权环境部署v0.5.0（含网页恢复实测），验证真实RSS与四渠道收信，见ROADMAP“当前阶段”和ACCEPTANCE。
3. 以后发布按IMAGE_RELEASE“正式发布（三步）”；连续步骤可写成一个后台脚本一次等待。

## 授权

2026-10-30用户授权v0.6.0热榜改动的提交、推送、合并与发版（仅此一次）；无部署或真实发送授权。

## 按需读取（只读与任务相关的项）

- 设置界面：UI_DESIGN末节、SPEC第175行、frontend/src/pages/*Settings.vue
- 发布/CI：IMAGE_RELEASE“正式发布”、.github/workflows/*.yml、scripts/{bump_version,ci_reuse,verify_release}.py
- 实机验收：ROADMAP“当前阶段”、ACCEPTANCE、RELEASES
- 其他历史只在本文链接指向时阅读。
