# 当前状态

更新时间：2026-10-24（Asia/Shanghai）。httpx启用HTTP/2隔离验证成功，四个Linux DO RSS各30条；建议采用此轻量修复，正式实现已完成、后端720通过；镜像/本地更新正在进行。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发。分支codex/linuxdo-integration，HEAD 4ce2dd94b7e3cce0d5cc81c26f28514a7bfb56c0，产品e1d2f21，未推送/合并。无多代理，不改D盘/旧Ubuntu/全局WSL/8000/4175。沿用保留数据更新同一本机8001授权；公开发布、远程部署、主动真实发送另计。

用户已分别批准curl_cffi与httpx HTTP/2隔离实验，6次及5次请求均完成。未改产品/正式依赖/容器/正式库，未登录或发通知。用户随后“可以 采用这个方案”批准正式HTTP/2接入；沿用本机8001保留数据更新授权。未提交含原有诊断记录，以及HTTP/2客户端工厂、Runtime/HotlistService接入、httpx[http2]/锁、针对性测试和权威文档。

## 读取入口

先读[正式接入](history/2026-10-24-LinuxDO-HTTP2接入.md)及[HTTP/2验证](history/2026-10-24-LinuxDO-HTTP2验证.md)，按需读[匿名curl实验](history/2026-10-24-LinuxDO匿名客户端实验.md)、[查因/资料/体积](history/2026-10-23-LinuxDO访问诊断与审批方案.md)、[接入部署](history/2026-10-23-LinuxDO接入.md)。SPEC 6.2、ARCHITECTURE/DECISIONS及backend/seekbell/collectors/http及rss、services/runtime/request_budget/hotlists为相关入口。

## 最新证据与结论

07:16在同一httpx 0.28.1及请求参数下，http2=True对hot/latest?order=created/daily/weekly全部200，实际HTTP/2，各30条解析/适配无诊断，三榜单解析通过；紧接http2=False对hot仍403、cf-mitigated=challenge，实际HTTP/1.1。复用public_response，无Cookie/登录、TLS校验、禁代理/跳转、1MiB限制、至少2秒间隔；沿用上轮挑战冷却，最后403后停止。

证据均在/home/dev/.local/state/seekbell：acceptance/2026-10-24-linuxdo-httpx-http2/{results,summary}.json，脚本及独立deps在experiments/linuxdo-httpx-http2-20261024。h2 4.4.1/hpack 4.2.0/hyperframe 6.1.0文件约0.48MiB，不是实际镜像增量。原curl证据在acceptance/2026-10-24-linuxdo-curl-cffi，四源可读但需约37.14MiB库；现不推荐纳入生产。

已证实本机开启HTTP/2足以解决当前读取；不能断定站方具体规则或TLS单独原因。尚未验证长期、目标容器、PVE/arm64或用户验收。无RSS正文/用户会话落盘。正式配置仍HTTP/1.1。

## 运行基线与下一步

e1d2f21后端716、相关浏览器84通过，构建/隐私/锁及离线容器/恢复/升级回退证据详见接入记录。本轮后端720通过（新增4），Ruff/格式/锁/隐私/wheel通过；前端未改，复用原浏览器结果。0011按站调度/共享预算/持久退避，作者显示名不作用户名，榜单600秒按需更新、旧快照24小时，边界沿用。

8001仍seekbell-local/seekbell-local-seekbell-1、原卷seekbell-local_data；镜像seekbell:linuxdo-e1d2f21b5cd5，ID sha256:efae316460c5f0b66b3fb7a5d763d843a78aa59a916bbc4ee7e0c4c39d443b81，本轮未改。备份local-runtime/backups/before-linuxdo-e1d2f21-20261023-232943.tar.gz、SHA及原配置迁移验证见接入记录；旧312d657回退须恢复匹配0010整卷，不能读0011。

已获批准，正在正式HTTP/2接入：仅Linux DO三入口启用，锁定可选依赖、同步权威文档、针对性回归与容器实测后按已有授权更新8001。持续运行、用户验收和推送/合并仍待办。
