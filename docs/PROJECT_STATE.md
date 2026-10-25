# 当前状态

更新时间：2026-10-25（Asia/Shanghai）。ui-restore-6已公开发布，等待用户Portainer实机测试；未代部署或真实试发。产品代码987beda5ea38c01e9969fb2fa684c8f970edeec0，后续仅发布元数据。

## 版本与证据

ghcr.io/aspeternity/seekbell:ui-restore-6，固定digest sha256:6fd13c6fc1e722b2477405851536526abb9bab6aed3ee2723b36f26897c96f6d，linux/amd64、linux/arm64。用户明确批准公开GHCR，本轮按已合并main运行[40159916595](https://github.com/Aspeternity/seekbell/actions/runs/40159916595)，完整baseline实际789后端/154浏览器、原生双架构、发布后固定digest容器检查均通过。本机空Docker配置按digest真实匿名拉取amd64并验代码/UID/层，7旧短标签不变。源码仍private、包public，临时发布开关已恢复缺失；无持续发布/远程部署授权。

先读[发布记录](history/2026-10-25-ui-restore-6发布.md)、其JSON回执/匿名核验、IMAGE_RELEASE及RELEASES。代码包含PR #2的Linux DO/多站任务/按站版块/匹配诊断与界面修复；V2EX与后续热榜分周期建议未开发。36提交已合并，main合并5cdf5bd，发布SHA987beda。自动结果不代表真实论坛/渠道可用或用户验收。

## 升级与权限

ui-restore-5到本版含0010–0016，升级前完整备份旧卷和原钥；原Stack/端口/卷不变，更新重新拉取镜像。回退须旧镜像配匹配schema备份，不直接读新卷。deploy/compose.portainer.compare.yaml仅更新镜像，8001及原对比卷保持；8000模板保留旧版本。

唯一开发SeekBell-Dev:/home/dev/projects/seekbell，原Ubuntu经wsl.exe派发；不在D盘开发，不改旧Ubuntu/全局WSL或已运行实例。私有发布记录在/home/dev/.local/state/seekbell/releases/ui-restore-6。现有本机8001仍记录9becf75/schema0016原项目/卷，未由本次发布更新；实际本机runtime元数据在私有local-runtime/runtime.json。

## 下一步

用户更新原Portainer Stack验收，若报错先区分程序/来源限流/通知投递。V2EX方案及候选网站咨询仍在本地codex/v2ex-plan，当前不推送/开发；需要继续时先读该分支PROJECT_STATE，按用户大类范围完成新帖与跨类归属设计后另审。schema0016之后任何新迁移先新备16整卷，旧15快照不能作16回退。发布成功不等于用户实机验收完成。
