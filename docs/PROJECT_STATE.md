# 当前状态

更新：2026-11-08（Asia/Shanghai）。main 24a05e8（PR #31，v0.6.1）；分支hotlist-weekly-stagger准备v0.6.2；图标资产仍未提交。

## 开局

先运行`python3 scripts/dev_status.py`取得分支、工作区、版本一致性和最新CI，不再逐条手工核对。与本文不符时以实际为准并先更新本文。

## 计划位置

M0–M4已完成。最新公开版本v0.6.1（Linux DO热榜错峰）：ghcr.io/aspeternity/seekbell:0.6.1@sha256:f083cd811bd91dda2cc24d032d1c76598e4b0eb5388319af9d6e94571177b046，改动与证据见[方案记录](history/2026-11-07-LinuxDO热榜错峰方案.md)。[v0.6.0记录](history/2026-10-30-v0.6.0热榜即时切换.md)，v0.5.0见[记录](history/2026-10-30-v0.5.0备份恢复简化.md)，v0.4.0见[记录](history/2026-10-29-v0.4.0设置纠正与网页直接恢复.md)。现用实例已运行0.6.1（latest标签，revision 24a05e8，11/08只读核实）；M5实机验收（ROADMAP“当前阶段”表）未完成，需另行授权。

## 已完成：发版提速（PR #28 → main fd310e5）

CI拆为checks/pytest(-n auto)/browser×4并行，汇总job仍名baseline：PR检查由14分钟降为3分45秒（运行于PR #28最终提交）。版本号PR合并后由images.yml的workflow_run自动发版：只检出main当前head且须等于通过基线的提交（CodeQL指出检出事件SHA有缓存投毒风险，已改）；合并后实测main CI复用9秒、自动发版preflight判定0.6.0已有标签而跳过（运行40929329810）。v0.6.1已实测完整路径：版本号合并后自动发版成功（运行42254858356）。Dependabot改为按月分组；13个旧PR已关闭（5个大版本由Dependabot自行关闭）。流程见IMAGE_RELEASE“正式发布”。

仓库设置：用户2026-10-30手动关闭ruleset“Protect main”的strict并开启allow_auto_merge，已经API核实（必需检查仍为baseline与native amd64/arm64）。

## 本次：项目图标方案

按用户要求生成暖橙底“铃铛＋RSS信号”图标，保存于assets/brand/seekbell-icon-v1.png（1254×1254 RGBA）；完整提示词、SHA-256与检查见[资产说明](../assets/brand/README.md)。基于fd310e5，在SeekBell-Dev验证PNG/透明通道及复制一致性；未改产品代码，未重跑构建，未接入页面，待用户审阅。

未提交：assets/brand/新资产（不随v0.6.2提交）。

## 进行中：Linux DO每周榜错开（v0.6.2）

用户否定v0.6.1错峰（热门/每日要等几十秒，采集仍被挑战），按用户方向重做：热门、每日到期即刷新（2秒间隔），只把每周错开到热门/每日请求1分钟后。实机证据、方案与验证见[记录](history/2026-11-08-LinuxDO每周榜错开.md)；v0.6.1方案见[旧记录](history/2026-11-07-LinuxDO热榜错峰方案.md)。

分支hotlist-weekly-stagger（基于24a05e8）：改services/hotlists.py、request_budget.py（恢复0.6.0形态）、sites/hotlists.py、tests/test_linuxdo_runtime.py、frontend/tests/linuxdo/linuxdo.spec.ts，SPEC 6.6、ARCHITECTURE末节、CHANGELOG，版本号已改0.6.2。本机相关测试通过，未推送。

## 暂缓：关于与诊断改版

用户对四块式方案和[精简设计稿](https://claude.ai/artifact/DteK3nhDHqnMArr5t2DzJh)均不满意，要求修完热榜后再讨论，要简洁实用且美观。已确认倾向：诊断摘要对单管理员基本无用。查证事实（fd310e5）：故障只来自RSS采集失败和通知失败；热榜挑战使采集退避时run_once返回backoff不写故障，页面仍显示“无”。可用数据：SourceState、SourceRun、Outbox、DeliveryAttempt、BackupRecord、SystemEvent。代码未动。

## 下一步

1. 经用户授权后推送分支、开PR并`gh pr merge --auto --squash`，合并后自动发版v0.6.2；之后用户升级现用实例，再用只读查询核对Linux DO采集失败（source_runs）和热榜日志。
2. 重新讨论关于与诊断页。
3. 图标待审阅，采用后再制作使用尺寸并接入；资产说明为本任务读取入口。
4. M5实机验收：在现用实例核验v0.6.0网页恢复与热榜真实来源，验证真实RSS与四渠道收信，见ROADMAP“当前阶段”和ACCEPTANCE。

## 授权

v0.6.1发布授权已用完；当前无推送、合并、发布、部署或真实发送授权。用户11/08授权过在docker-vm由用户本人执行只读诊断命令。

## 按需读取（只读与任务相关的项）

- 社区热榜：每周榜错开记录、SPEC 6.1/6.4/6.6、ARCHITECTURE末节、services/hotlists.py、request_budget.py、CommunityHotlist.vue
- 设置界面：UI_DESIGN末节、SPEC第175/181行、frontend/src/pages/*Settings.vue（关于页AboutSettings.vue、services/overview.py）
- 发布/CI：IMAGE_RELEASE“正式发布”、.github/workflows/*.yml、scripts/{bump_version,ci_reuse,verify_release}.py
- 实机验收：ROADMAP“当前阶段”、ACCEPTANCE、RELEASES
- 其他历史只在本文链接指向时阅读。
