# 当前状态

更新时间：2026-10-21（Asia/Shanghai）。M0～M3实现及本地自动检查已完成；当前M4部署恢复/私有镜像交付，正在修复首次GHCR发布后的元数据误判并完整复验。M5实机与用户验收未执行。

## 环境与代码

仅SeekBell-Dev:/home/dev/projects/seekbell开发，原Ubuntu经wsl.exe派发，[环境入口](DEVELOPMENT_ENVIRONMENT.md)。main已普通合并推送2da8d1d，开发分支cb3de42保留。产品代码仍等同faa991d，本轮仅CI、发布校验、测试及文档，无新业务/依赖/迁移。当前待提交：包校验器及专项、images失败回执保存、删除临时只读workflow、镜像说明和状态/证据；临时workflow已远程禁用。

## 已取得证据

34cf183的[远程CI与原生双架构](history/2026-10-21-远程CI与原生双架构验证.md)通过：后端473项、浏览器64项、amd64/arm64原生构建、容器、备份升级、真实TLS及归档往返。已排除原型误收集与Docker自动池未显式声明子网两条失败路线，不改全局网络。

[首次发布39482339606](https://github.com/Aspeternity/seekbell/actions/runs/39482339606)，代码2da8d1d：完整baseline后端493项/浏览器64项及双架构通过；实际双平台索引已上传并校验，digest为sha256:aabfe5e27d5d942f2f9a91e5986da8b52462561b78c96f387cc438a5867d110b。后置检查确认private后，错误要求API必须返回repository，导致整轮失败，固定digest拉取未执行。不可记成功或删除已发布产物。

只读诊断和GitHub官方schema确认repository可选/可空。现改为缺失记录not-reported，有报告则严格核对；仍验证私有源仓库/包、短期令牌和产物source/config，不改变包权限。专项57项0.33秒、Ruff/Prettier/actionlint通过。首次发布开关已恢复原先缺失；下一轮仍仅临时开启，完成后恢复。[完整记录](history/2026-10-21-主分支合并与GHCR候选发布.md)，[可运行流程](IMAGE_RELEASE.md)。

## 验收实例与下一步

保留seekbell-acceptance-b45fc2c-20261020项目、-seekbell-1容器、_data卷及seekbell:backup-local（b45fc2c），http://localhost:18081/。最近只读running、重启0，未替换/重置/代配置。旧seekbell-acceptance不兼容卷保留，旧4175/18080不动；[故障说明](history/2026-10-20-本机验收启动修复.md)。本机另保留两平台ci-34cf183候选，ID见归档。

下一步提交修复main并以精确SHA完整重跑私有GHCR发布，确认回执及digest拉取/隔离容器检查，再恢复开关。之后M5需目标PVE、真实RSS/四渠道、Safari/真机和运行观察及用户验收；跨版本加密恢复仍未验证。[阶段顺序](ROADMAP.md)。原生CI不等同真实设备验收，恢复回退可能重复发送，保留原卷、不降级新库。

## 恢复与授权

恢复读AGENTS、本状态、IMAGE_RELEASE及本次发布记录，按需读相关workflow/校验器；不全仓重读。文档收尾使用skip ci并复用实际代码证据，不循环写自身SHA。

2026-10-21用户明确授权主分支合并及私有GHCR发布，允许本轮临时启用开关后恢复；沿用独立WSL/noreply。无远程部署、真实发送、仓库/包公开、正式GitHub Release、旧环境清理或全局WSL变更授权。不组织多代理，保留验收实例。
