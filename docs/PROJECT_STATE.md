# 当前状态

更新：2026-10-30（Asia/Shanghai）。main 1b9af88（PR #27）= v0.6.0。之后为发版提速PR（不改产品代码）。

## 开局

先运行`python3 scripts/dev_status.py`取得分支、工作区、版本一致性和最新CI，不再逐条手工核对。与本文不符时以实际为准并先更新本文。

## 计划位置

M0–M4已完成。最新公开版本v0.6.0（热榜即时切换与退避拆分）：ghcr.io/aspeternity/seekbell:0.6.0@sha256:efc898cf25f36273178f852894d560a250ee55055549d84e5fa98f2ab11fc705，改动与证据见[v0.6.0记录](history/2026-10-30-v0.6.0热榜即时切换.md)。v0.5.0见[记录](history/2026-10-30-v0.5.0备份恢复简化.md)，v0.4.0见[记录](history/2026-10-29-v0.4.0设置纠正与网页直接恢复.md)。现用实例尚未部署0.2.0～0.6.0。下一阶段为M5实机验收（ROADMAP“当前阶段”表），需另行授权。

## 进行中：发版提速（分支codex/dependabot-groups）

用户2026-10-30要求发版提速并授权“全部都做、做完汇报”（DECISIONS首条）。改动：.github/dependabot.yml按月分组、不自动rebase、忽略大版本；ci.yml拆为checks/pytest(-n auto)/browser×4，汇总job仍名baseline；native-images.yml与ci.yml接受revision输入；images.yml新增workflow_run自动发版（scripts/release_preflight.py，Release在镜像就绪后创建）；scripts/ci_install_browser.sh；pytest-xdist入dev依赖；IMAGE_RELEASE“正式发布”、AGENTS、PUBLIC_REPOSITORY更新。本机pytest -n auto 921通过（21秒）。
未完成：关闭ruleset strict与开启allow_auto_merge被本机权限拦截，需用户手动；13个旧Dependabot PR待配置合并后关闭。自动发版路径需下一次真实版本号合并时验证。

## 下一步

1. 下一阶段M5实机验收：在授权环境部署v0.6.0（含网页恢复与热榜预热/真实来源实测），验证真实RSS与四渠道收信，见ROADMAP“当前阶段”和ACCEPTANCE。
2. 以后发布按IMAGE_RELEASE“正式发布”：版本PR合并后自动发版，一次等待。

## 授权

v0.6.0发布授权已用完。2026-10-30授权发版提速全部改动（推送、PR合并、关闭旧依赖PR、仓库设置）；无版本发布、部署或真实发送授权。

## 按需读取（只读与任务相关的项）

- 社区热榜：SPEC 6.1/6.4/6.6、ARCHITECTURE末节、services/hotlists.py、CommunityHotlist.vue
- 设置界面：UI_DESIGN末节、SPEC第175行、frontend/src/pages/*Settings.vue
- 发布/CI：IMAGE_RELEASE“正式发布”、.github/workflows/*.yml、scripts/{bump_version,ci_reuse,verify_release}.py
- 实机验收：ROADMAP“当前阶段”、ACCEPTANCE、RELEASES
- 其他历史只在本文链接指向时阅读。
