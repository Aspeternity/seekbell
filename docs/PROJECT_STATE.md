# 当前状态

更新：2026-11-08（Asia/Shanghai）。main 5637e6b（PR #34），产品版本v0.6.4；本文与发布回执、图标资产未提交。

## 开局

先运行`python3 scripts/dev_status.py`取得分支、工作区、版本一致性和最新CI，不再逐条手工核对。与本文不符时以实际为准并先更新本文。

## 计划位置

M0–M4已完成。最新公开版本v0.6.4（数据目录自动权限）：ghcr.io/aspeternity/seekbell:0.6.4@sha256:952df139539cac59170a916e9b35e260d259bd6c8c631ba959879d730e8f4c9f，见[记录](history/2026-11-08-v0.6.4数据目录自动权限.md)；v0.6.3见[快速停止记录](history/2026-11-08-v0.6.3快速停止与模板精简.md)；v0.6.2见[每周榜错开记录](history/2026-11-08-LinuxDO每周榜错开.md)；v0.6.1见[错峰记录](history/2026-11-07-LinuxDO热榜错峰方案.md)。[v0.6.0记录](history/2026-10-30-v0.6.0热榜即时切换.md)，v0.5.0见[记录](history/2026-10-30-v0.5.0备份恢复简化.md)，v0.4.0见[记录](history/2026-10-29-v0.4.0设置纠正与网页直接恢复.md)。现用实例已运行0.6.4（11/08用户核实：revision 5637e6b、入口脚本生效、healthy，数据为全新的`/opt/docker/SeekBell/data`绑定目录，无需chown；首次建管理员并添加Linux DO后，热门、每日几乎立即出现，每周约晚1分钟出现，符合设计）；M5实机验收（ROADMAP“当前阶段”表）未完成，需另行授权。

## 已完成：发版提速（PR #28 → main fd310e5）

CI拆为checks/pytest(-n auto)/browser×4并行，汇总job仍名baseline：PR检查由14分钟降为3分45秒（运行于PR #28最终提交）。版本号PR合并后由images.yml的workflow_run自动发版：只检出main当前head且须等于通过基线的提交（CodeQL指出检出事件SHA有缓存投毒风险，已改）；合并后实测main CI复用9秒、自动发版preflight判定0.6.0已有标签而跳过（运行40929329810）。v0.6.1已实测完整路径：版本号合并后自动发版成功（运行42254858356）。Dependabot改为按月分组；13个旧PR已关闭（5个大版本由Dependabot自行关闭）。流程见IMAGE_RELEASE“正式发布”。

仓库设置：用户2026-10-30手动关闭ruleset“Protect main”的strict并开启allow_auto_merge，已经API核实（必需检查仍为baseline与native amd64/arm64）。

## 本次：项目图标方案

按用户要求生成暖橙底“铃铛＋RSS信号”图标，保存于assets/brand/seekbell-icon-v1.png（1254×1254 RGBA）；完整提示词、SHA-256与检查见[资产说明](../assets/brand/README.md)。基于fd310e5，在SeekBell-Dev验证PNG/透明通道及复制一致性；未改产品代码，未重跑构建，未接入页面，待用户审阅。

未提交：assets/brand/新资产（不随v0.6.2提交）。

## 已发布：Linux DO每周榜错开（v0.6.2）

用户否定v0.6.1错峰后按用户方向重做：热门、每日到期即刷新（2秒间隔），只把每周错开到热门/每日请求1分钟后。PR #32全部CI通过，合并为98b5fcb，自动发版运行42425292442成功。证据、方案、验证与回执见[记录](history/2026-11-08-LinuxDO每周榜错开.md)。仅模拟来源验证。

## 已发布：v0.6.3快速停止与模板精简

PR #33合并为c449755，自动发版运行42428086149成功。收到停止信号时长轮询立即返回，uvicorn兜底超时3秒，后台宽限5秒，在Docker默认10秒内停完；镜像去除setuid；模板精简并删除8001对比模板。查证、改动和验证见[记录](history/2026-11-08-v0.6.3快速停止与模板精简.md)。

## 已发布：v0.6.4数据目录自动权限

用户部署0.6.3时宿主目录属于root，容器一直重启（PermissionError /data/.instance.lock）。用户确认改为root启动、入口脚本接管/data后降为10001运行（可选PUID/PGID），并授权发布。PR #34合并为5637e6b，自动发版运行42433083768成功；CI linuxdo浏览器套件有未查明的偶发失败，见[v0.6.4记录](history/2026-11-08-v0.6.4数据目录自动权限.md)。

## 进行中：v0.6.5每周旧榜保留7天

用户确认Linux DO每周旧榜保留7天、否决加载提示，并授权发布。分支weekly-retention（基于5637e6b），见[v0.6.5记录](history/2026-11-08-v0.6.5每周旧榜保留7天.md)。

## 暂缓：关于与诊断改版

用户对四块式方案和[精简设计稿](https://claude.ai/artifact/DteK3nhDHqnMArr5t2DzJh)均不满意，要求修完热榜后再讨论，要简洁实用且美观。已确认倾向：诊断摘要对单管理员基本无用。查证事实（fd310e5）：故障只来自RSS采集失败和通知失败；热榜挑战使采集退避时run_once返回backoff不写故障，页面仍显示“无”。可用数据：SourceState、SourceRun、Outbox、DeliveryAttempt、BackupRecord、SystemEvent。代码未动。

## 下一步

1. 现用实例已是0.6.4；运行一段时间后用记录中的只读查询核对Linux DO采集失败（source_runs）、热榜日志，以及热门/每日打开即刷新、每周晚约1分钟。
2. 旧命名卷残留由用户自行删除（`docker volume ls | grep -i seekbell`后`docker volume rm`），尚未确认是否已删。
3. CI linuxdo浏览器套件偶发失败：再次出现时下载browser-traces-*追踪查根因（记录见v0.6.4记录）。
4. 重新讨论关于与诊断页。
5. 图标待审阅，采用后再制作使用尺寸并接入；资产说明为本任务读取入口。
6. M5实机验收：在现用实例核验v0.6.0网页恢复与热榜真实来源，验证真实RSS与四渠道收信，见ROADMAP“当前阶段”和ACCEPTANCE。

## 授权

v0.6.4发布授权已用完；v0.6.5（PR、自动合并、自动发版）已获授权；当前无推送、合并、发布、部署或真实发送授权。用户11/08授权过在docker-vm由用户本人执行只读诊断命令。

## 按需读取（只读与任务相关的项）

- 社区热榜：每周榜错开记录、SPEC 6.1/6.4/6.6、ARCHITECTURE末节、services/hotlists.py、request_budget.py、CommunityHotlist.vue
- 设置界面：UI_DESIGN末节、SPEC第175/181行、frontend/src/pages/*Settings.vue（关于页AboutSettings.vue、services/overview.py）
- 发布/CI：IMAGE_RELEASE“正式发布”、.github/workflows/*.yml、scripts/{bump_version,ci_reuse,verify_release}.py
- 实机验收：ROADMAP“当前阶段”、ACCEPTANCE、RELEASES
- 其他历史只在本文链接指向时阅读。
