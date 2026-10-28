# 参与开发

请先在 Issue 中说明问题或建议，确认范围后从 main 建立分支，通过 PR 提交。
开发环境与检查命令见 [README](README.md)。维护者本机环境限制见 [AGENTS](AGENTS.md)。

PR 必须通过完整 baseline 和两种原生架构的离线镜像检查，解决所有评审讨论后以 squash 合并。
单维护者阶段不强制第二人批准；CI 不联系真实论坛、不发送真实通知。
依赖更新由 Dependabot 创建 PR，经过相同检查，不自动合并。

提交身份使用 GitHub noreply 地址。克隆后启用 .githooks，并运行隐私检查。
提交中不得包含真实通知凭据、数据库、会话、备份或个人邮箱。

发布遵循 [镜像版本流程](docs/IMAGE_RELEASE.md)。发布版本和运行实例验收分别记录。
许可证尚待维护者确定。
