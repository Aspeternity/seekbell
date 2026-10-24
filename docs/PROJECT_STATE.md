# 当前状态

更新时间：2026-10-24（Asia/Shanghai）。Linux DO退避与受限人工重试已实现、验证并保留数据更新本机8001；正式自动采集08:13成功，无来源错误。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发。分支codex/linuxdo-integration，最后产品30252cea8e88df76fe8b807a3721562289e84ba5；后续仅交付文档提交，均未推送/合并。用户要求优化退避，沿用修复与本机8001保留数据更新授权；公开发布、远程部署、主动真实发送另计。无多代理，不改D盘/旧Ubuntu/全局WSL/8000/4175。

## 读取入口与实现

先读[退避与人工重试](history/2026-10-24-退避与人工重试.md)，按需读同日概览警示间距、HTTP2接入/验证及前日诊断。SPEC 6.2、ARCHITECTURE/DECISIONS、UI_DESIGN已同步；相关代码services/request_budget/source_probe/collection/hotlists、collectors/rss、0012迁移与前端Websites。
Linux DO自动403/挑战5→10分钟封顶；429无指令时1→2→4→8→10分钟，传输/服务端错误30秒→1→2→4→5分钟。服务器Retry-After独立保护，最多24小时；0012仅加retry_after_until/next_manual_at，旧预算及失败采集/测试的截止取最大值继承。
人工测试每60秒一次，可提前验证程序退避，但仍受服务器等待、同站2秒/互斥与持久配额约束；成功仅推动失败采集真实重试，不改正常计划/启停/周期/历史/基线或直接写内容/通知。NodeSeek原语义保持。热榜内层失败等待已同步缩短，取消/并发延期不伪造失败。

## 证据与限制

后端739通过（新增19）、Linux DO/原操作桌面手机共18项浏览器通过；格式/类型/构建/锁/隐私/wheel通过。候选容器、加密备份恢复及升级/回退演练通过，全为合成服务/禁外网，不发真实消息。
正式旧实例08:07已自然恢复；新实例08:13只读检查自动采集成功、failures=0、错误空、站点等待0、正常下一次60秒。没有额外人工RSS/通知请求；长期/PVE/arm64及用户验收仍待。
证据/home/dev/.local/state/seekbell/acceptance/2026-10-24-retry-controls：backend.log、linuxdo-browser.log、operations-browser.log、container/backup-container/release-container.log、backup-verification.json、private-data-preflight.json、deployment-result.json、windows-after-update.json、source-before/after.json。

## 本机运行与交接

8001同一seekbell-local/seekbell-local-seekbell-1、原卷seekbell-local_data；镜像seekbell:retry-controls-30252cea8e88，ID sha256:28bb4103cd3a8c2c65e6670d6040facb5ae3d8ed0156f8e2b79bf3d699d61e73。schema0012、healthy/read-only/unless-stopped，原账号/配置/密钥保留，HTTP/2与概览22px修复保留。Windows两地址/版本/资源通过，保活PID32480及创建时间不变，runtime.json已更新。
整卷备份local-runtime/backups/before-retry-30252ce-20261024-081237.tar.gz，SHA/逐文件/解包SQLite验证见新交付记录。副本迁移原表原列/行、12类配置、密钥/凭据一致，新增字段单独核对；正式配置比对通过，临时卷已清理。旧1374da8/0011镜像保留，回退必须恢复匹配0011整卷，禁止旧镜像读0012。

下一步用户刷新8001验收网站配置里的测试说明、连接结果及概览状态；持续运行另验。实现与交付记录本地保存，推送/合并待授权。
