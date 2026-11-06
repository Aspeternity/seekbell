# 当前状态

更新：2026-11-07（Asia/Shanghai）。main fd310e5（PR #28），产品版本v0.6.0；工作区含未提交的热榜错峰实现、文档与新图标资产。

## 开局

先运行`python3 scripts/dev_status.py`取得分支、工作区、版本一致性和最新CI，不再逐条手工核对。与本文不符时以实际为准并先更新本文。

## 计划位置

M0–M4已完成。最新公开版本v0.6.0（热榜即时切换与退避拆分）：ghcr.io/aspeternity/seekbell:0.6.0@sha256:efc898cf25f36273178f852894d560a250ee55055549d84e5fa98f2ab11fc705，改动与证据见[v0.6.0记录](history/2026-10-30-v0.6.0热榜即时切换.md)。v0.5.0见[记录](history/2026-10-30-v0.5.0备份恢复简化.md)，v0.4.0见[记录](history/2026-10-29-v0.4.0设置纠正与网页直接恢复.md)。现用实例已运行0.6.0（用户截图代码版本1b9af88，11/04只读证据一致）；M5实机验收（ROADMAP“当前阶段”表）未完成，需另行授权。

## 已完成：发版提速（PR #28 → main fd310e5）

CI拆为checks/pytest(-n auto)/browser×4并行，汇总job仍名baseline：PR检查由14分钟降为3分45秒（运行于PR #28最终提交）。版本号PR合并后由images.yml的workflow_run自动发版：只检出main当前head且须等于通过基线的提交（CodeQL指出检出事件SHA有缓存投毒风险，已改）；合并后实测main CI复用9秒、自动发版preflight判定0.6.0已有标签而跳过（运行40929329810）。真正发布新版本的路径尚待下一次版本号合并验证。Dependabot改为按月分组；13个旧PR已关闭（5个大版本由Dependabot自行关闭）。流程见IMAGE_RELEASE“正式发布”。

仓库设置：用户2026-10-30手动关闭ruleset“Protect main”的strict并开启allow_auto_merge，已经API核实（必需检查仍为baseline与native amd64/arm64）。

## 本次：项目图标方案

按用户要求生成暖橙底“铃铛＋RSS信号”图标，保存于assets/brand/seekbell-icon-v1.png（1254×1254 RGBA）；完整提示词、SHA-256与检查见[资产说明](../assets/brand/README.md)。基于fd310e5，在SeekBell-Dev验证PNG/透明通道及复制一致性；未改产品代码，未重跑构建，未接入页面，待用户审阅。

未提交：assets/brand/为本次新资产；docs/history/2026-11-07-LinuxDO热榜错峰方案.md为新方案记录；PROJECT_STATE合并本次交接。原有IMAGE_RELEASE、PUBLIC_REPOSITORY及PROJECT_STATE的发版提速收尾改动已保留。

## 发布中：Linux DO热榜错峰（v0.6.1）

根因是热榜预热2秒连发（周榜常排最后）。已按用户2026-11-07确认实现：后台榜≥30秒一个、在看榜15秒内最多占第2个请求（采集只计数）、等待不改榜单状态、切榜唤醒；有快照且未超2倍刷新间隔时不显示失败或等待提示。详情与证据见[方案记录](history/2026-11-07-LinuxDO热榜错峰方案.md)。

随v0.6.1发布（分支release/0.6.1）。发布前本机相关pytest 125、hotlist 50、linuxdo 26通过（模拟来源），全量由CI执行；未验证真实来源。

## 暂缓：关于与诊断改版

用户对四块式方案和[精简设计稿](https://claude.ai/artifact/DteK3nhDHqnMArr5t2DzJh)均不满意，要求修完热榜后再讨论，要简洁实用且美观。已确认倾向：诊断摘要对单管理员基本无用。查证事实（fd310e5）：故障只来自RSS采集失败和通知失败；热榜挑战使采集退避时run_once返回backoff不写故障，页面仍显示“无”。可用数据：SourceState、SourceRun、Outbox、DeliveryAttempt、BackupRecord、SystemEvent。代码未动。

## 下一步

1. 用户已授权发布v0.6.1：等待自动发版完成并核对；部署到现用实例需另行授权，部署后观察Linux DO采集和热榜日志（不主动制造挑战）。
2. 重新讨论关于与诊断页。
3. 图标待审阅，采用后再制作使用尺寸并接入；资产说明为本任务读取入口。
4. M5实机验收：在现用实例核验v0.6.0网页恢复与热榜真实来源，验证真实RSS与四渠道收信，见ROADMAP“当前阶段”和ACCEPTANCE。

## 授权

用户2026-11-07授权提交并发布v0.6.1（含推送、PR、合并）。无部署或真实发送授权。

## 按需读取（只读与任务相关的项）

- 社区热榜：错峰方案记录、SPEC 6.1/6.4/6.6、ARCHITECTURE末节、services/hotlists.py、request_budget.py、CommunityHotlist.vue
- 设置界面：UI_DESIGN末节、SPEC第175/181行、frontend/src/pages/*Settings.vue（关于页AboutSettings.vue、services/overview.py）
- 发布/CI：IMAGE_RELEASE“正式发布”、.github/workflows/*.yml、scripts/{bump_version,ci_reuse,verify_release}.py
- 实机验收：ROADMAP“当前阶段”、ACCEPTANCE、RELEASES
- 其他历史只在本文链接指向时阅读。
