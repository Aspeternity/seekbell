# 当前状态

更新时间：2026-10-28（Asia/Shanghai）。阶段：hotlist-20261028已公开发布，Compose固定digest交付；Portainer实机测试由用户进行，尚未用户验收。

## 发布版本与证据

[PR #3](https://github.com/Aspeternity/seekbell/pull/3)已合并main，发布代码9c925eeb6e50f1c60ce0e3298b8d6bba5f4ac0ae，后续仅发布文档/Compose元数据。镜像ghcr.io/aspeternity/seekbell:hotlist-20261028，索引sha256:abb0a56e6c2b648b49348cb697207d8afd7a53b4517020b14c0a6cddfad8aeb5，linux/amd64和linux/arm64。

[最终发布运行40717692197](https://github.com/Aspeternity/seekbell/actions/runs/40717692197)完整基线、原生双架构与发布后固定digest禁外网容器检查全过。源码public、包public，回执及两平台manifest/配置digest见[发布记录](history/2026-10-28-hotlist镜像发布.md)及[JSON回执](history/2026-10-28-hotlist发布回执.json)。本机空Docker配置实际匿名拉取amd64，核对短标签/索引/两平台/版本/UID与配置和层指纹通过。私有原始产物位于/home/dev/.local/state/seekbell/releases/hotlist-20261028。临时发布变量已删除恢复原先缺失。

## 改动与限制

热榜独立刷新设置/0017迁移、采集优先与共享退避、Cloudflare挑战处理、选择框及连接测试历史/本次结果隔离已发布。V2EX仅方案文档，未开发。历史UI和Linux DO两处测试等待竞态修正，最终main全流程通过；过程失败及排除路线见[准备归档](history/2026-10-28-镜像发布准备.md)。首次本机image ID误当配置digest的断言已纠正，平台配置/层独立核对通过。

此前Linux DO日榜429/Cloudflare限制未证明恢复，自动检查不等于实源持续可用或真实通知验收。本轮未部署任何本机/远端实例，未主动真实试发。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe执行。本地main。用户本轮明确授权推送/PR合并/GHCR发布/Compose交付，均已执行；不产生持续发布或代实机部署授权。无多代理，不改变旧Ubuntu/D盘、全局WSL或原容器。8001本机仍记录a0e2b6f/schema0017，本轮未动；镜像/原卷/完整17备份细节见准备归档及2026-10-25连接测试状态修正/热榜本机更新，私有runtime保留。

## 下一步与读取

用户在原Portainer Stack更新deploy/compose.portainer.compare.yaml（8001）或compose.portainer.yaml（8000），保留名称、端口和实际数据卷；自定义配置仅替换image更稳妥。模板固定digest并通过Compose配置检查。升级前完整备份原卷及credentials.key；ui-restore-6的0016升级0017后不能直接用旧镜像读新库，回退须旧镜像配匹配schema备份。

读取清单：本轮发布记录/JSON、IMAGE_RELEASE、RELEASES及deploy两份模板。最终提交仅发布资料，不改变镜像已验证的应用代码；用户实机结果待反馈。
