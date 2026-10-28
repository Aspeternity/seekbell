# 当前状态

更新时间：2026-10-29（Asia/Shanghai）。阶段：公开治理及版本镜像流程PR #6已授权合并；首个标准版本尚未发布，Portainer实机验收待用户反馈。

## 环境与代码

唯一开发环境SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe执行。main=origin/main 88374a2；其tree与已完整测试的PR HEAD 222cfb7一致，PR合成合并SHA 5867753。本轮只改治理、CI/镜像/隐私脚本、测试和文档，无应用依赖/数据库/Compose变更。

当前分支codex/public-repository-handoff，仅保存最终交接文档，未推送，后续随相关PR同步；路径为PROJECT_STATE、PUBLIC_REPOSITORY、本轮治理记录和配置JSON。D盘交接副本过时，未改动。

## 已生效设置与证据

main规则26056251要求PR、同步main、讨论解决、baseline与原生amd64/arm64三项成功（绑定GitHub Actions），禁止删除/强推，无绕过名单；单维护者批准人数0，仅squash、合并后删分支。v*规则26056497禁止更新/删除。已开启密钥扫描/推送保护、依赖告警/安全更新、私密漏洞报告和CodeQL；Actions只读、外部fork均需审核。配置回读及详情见本轮治理记录/JSON。

[PR #6](https://github.com/Aspeternity/seekbell/pull/6)运行40724613117全部通过：852 pytest、174浏览器测试、容器维护/TLS及原生双架构；CodeQL运行40724604175全过。本机发布/版本/隐私81项、Ruff、actionlint、工作流Python语法及全Git隐私通过。首次CI误判机器人固定官方服务尾注，已作精确例外，个人地址/文件约束仍保留。main自动复跑40728299636记录时仍进行中，不冒称通过；复用的是相同代码树的完整PR证据。

## 发布与限制

旧hotlist-20261028索引sha256:abb0a56e6c2b648b49348cb697207d8afd7a53b4517020b14c0a6cddfad8aeb5，新脚本实际匿名核对一致，Compose仍固定它。新流程在Release发布并完成检查后添加X.Y.Z及受控latest；预发布不移latest，同版本异digest拒绝覆盖。尚未真实执行新版发布，pyproject仍0.1.0.dev0。

依赖告警9条（5个GHSA，1 critical/6 high/2 medium）：certifi修复版2026.10.18；cryptography完整修复涉及50.0.0跨大版本。安全修复PR #4/#5及后续自动版本PR均未合并。许可证按用户回复暂不决定。

## 下一步与授权

用户本轮明确允许PR #6 squash合并，已执行；不产生后续版本发布/部署/真实发送授权。下一步先评估依赖修复，验证加密配置与备份兼容，再明确版本/锁文件及首个Release授权；main自动CI结果可先只读核对。不组织多代理，不改旧Ubuntu、全局WSL或原容器。

读取：PUBLIC_REPOSITORY、IMAGE_RELEASE、本轮治理记录及相关脚本；依赖修复时再读锁文件、vault/备份影响代码。8001实例、原卷/备份、Portainer待验收和来源429限制见history/2026-10-28-公开配置前状态.md及链接，本轮未部署。
