# 更新记录

## 0.1.0 — 2026-10-29

首个正式版本，提供 linux/amd64 和 linux/arm64 容器镜像。

- 支持 NodeSeek、Linux DO 官方 RSS，新帖规则监控及 Telegram Bot、Bark、SMTP、Webhook 通知。
- 提供 Web 管理、历史与匹配诊断、社区热榜独立刷新、后台采集/投递及错误退避。
- 支持加密通知配置、整库加密备份、独立恢复、保留原卷的升级和显式回退；数据库 schema 为 0017。
- cryptography 升级到 50.0.2、certifi 升级到 2026.10.18，修复已发现的依赖安全告警。
- 应用及前端版本统一为 0.1.0；正式镜像提供 0.1.0 与 latest，Release 附带固定 digest 的 Portainer Compose 和发布回执。

升级前完整备份原卷及 credentials.key，并保留原 Stack 名、端口与实际数据卷。
回退旧镜像须匹配旧 schema 的备份；本版本没有新增迁移。
自动检查和跨库加密兼容验证使用合成数据；实际来源、通知渠道与部署环境仍需实测。
Linux DO 可能受到 Cloudflare/429 限制，出现异常时保留错误状态并退避。

许可证继续待维护者确定。发布和升级说明见 [镜像流程](docs/IMAGE_RELEASE.md)。
