# 当前状态

更新时间：2026-10-29（Asia/Shanghai）。阶段：公开仓库治理与版本镜像流程调整中；Portainer实机验收仍待用户反馈。

## 工作目录与基准

唯一开发环境SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe执行。起点main 6a9f595，工作区原干净；当前分支codex/public-repository-release。应用发布代码9c925ee未改，本轮仅调整GitHub治理、CI/发布脚本、测试及文档。D盘交接副本过时，不在该处开发。

## 已生效的公开设置

仓库public。main ruleset 26056251：必须PR、baseline检查且同步main、讨论解决、禁止删除/强推；单维护者暂不要求第二人批准，无绕过名单。只允许squash，合并后删分支、允许更新分支；已设置简介与topics。开启secret scanning/推送保护、Dependabot告警/安全修复和私密漏洞报告。Actions默认只读、不允许批准PR，外部贡献者运行均需审核。配置证据将归档到2026-10-29公开仓库治理记录。

## 镜像与限制

现有公开hotlist-20261028双架构索引sha256:abb0a56e6c2b648b49348cb697207d8afd7a53b4517020b14c0a6cddfad8aeb5；现有Compose继续固定它。历史SHA/run/架构标签来自候选流程，旧流程明确禁止latest；远端尚无Git版本标签或Release。新流程正在加入发布Release后校验版本/主分支归属、完整CI/原生双架构/发布后检查，再给同一索引添加版本号及受控latest。预发布不移动latest，同版本不同digest拒绝覆盖。尚未真实执行新版发布。

## 未提交与验证

未提交路径：.github/workflows/ci.yml、images.yml、dependabot/PR/Issue模板、scripts/release_images.py、tests/test_release_images.py、CONTRIBUTING.md、SECURITY.md和相关发布/决策/状态文档；用途是公开治理与标准版本发布。新增71项发布脚本/版本门禁测试、Ruff及actionlint通过；新版脚本实际匿名读取现有索引一致，尚未推送或合并。许可证按用户2026-10-29回复暂不决定。

## 下一步与读取

完成脚本安全测试与工作流静态检查，记录设置回读，再推送PR执行完整CI；合并与首个版本实际发布按本次具体授权处理。当前pyproject仍0.1.0.dev0，创建正式v0.1.0前须有明确版本提交并更新锁文件。只读本轮CI/镜像脚本、IMAGE_RELEASE及PUBLIC_REPOSITORY；部署维护查RELEASES。

## 授权与保留事项

用户本轮要求按公开GitHub标准调整设置并解决镜像命名，授权仓库设置和相关实现。无代用户实机部署、真实论坛/通知发送或旧Ubuntu清理授权，不组织多代理。历史发布、8001实例/原卷/完整备份及来源429限制见[上一状态归档](history/2026-10-28-公开配置前状态.md)及其链接；本轮不改变运行实例。
