# 当前状态

更新时间：2026-10-29（Asia/Shanghai）。阶段：用户已明确要求发布正式版本及镜像，正在准备v0.1.0。

## 环境与基准

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe执行。当前codex/release-v0-1-0，从本地交接b31e9e0创建；代码基准origin/main 88374a2。前轮PR #6完整852后端/174浏览器/原生双架构/CodeQL通过，main复跑40728299636热榜收尾竞态失败，根因及修复见本轮准备记录。前轮交接文档随本次发布PR同步，不改D盘/旧Ubuntu/全局WSL。

## 发布准备

版本确定v0.1.0：pyproject与前端改0.1.0；安全依赖cryptography约束>=50.0.2,<51并锁50.0.2，certifi锁2026.10.18；uv锁校验/同步已通过，其余依赖保持原锁。原9条告警对应5个GHSA，Bot安全PR #4是cryptography、#5是certifi（前轮末状态编号说明有误，以此核对为准）。普通版本更新PR不纳入本次发布。

新建scripts/check_crypto_compatibility.py，以合成库和禁网络子进程检查46.0.7与50.0.2互读加密配置/完整备份。旧依赖环境在/home/dev/.local/state/seekbell/releases/v0.1.0/compat-old，由旧锁创建；该目录0700，仅用于离线兼容验证，不是服务实例。准备材料和回执也保存在该私有目录。

## 工作区与验证

本次改动：版本/锁文件、两份deploy模板、发布workflow/脚本/测试、兼容脚本、CHANGELOG及相关发布/决策/状态文档和合成验证JSON；意图为安全修复、版本准备及可复现验证。跨库双向完整备份/凭据兼容通过，189项备份/通知/发布/隐私专项通过（1条已知测试客户端弃用警告）；新增部署附件的79项发布检查、Ruff、actionlint、源码与生成Compose配置均过。热榜两项异步回调补等待，12项重复检查及完整40项通过；未改业务行为或限流。未建Release/标签、未写GHCR。现有hotlist镜像和运行实例未动；源码Compose准备切到0.1.0，Release附件将在实际发布后追加已验证digest，端口与卷名不变。

## 下一步与授权

兼容和针对性检查已完成，推送版本PR，按保护规则通过完整CI/原生双架构并合并；然后发布Git标签v0.1.0与正式Release，等待版本镜像流程全过，匿名核对0.1.0/latest/digest和两平台，并交付固定digest Compose。当前发布指令覆盖本次必要修复、版本提交、PR合并、Release与GHCR发布，不重复索要确认；不含实机部署、真实论坛/通知或旧环境清理。许可证继续暂不决定，不组织多代理。

读取：IMAGE_RELEASE、当前发布workflow/脚本、凭据与备份代码及测试；上一状态与实例/备份/429限制见history/2026-10-29-正式发布前状态.md及其引用。
