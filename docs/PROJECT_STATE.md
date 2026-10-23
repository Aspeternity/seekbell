# 当前状态

更新时间：2026-10-24（Asia/Shanghai）。Linux DO HTTP/2修复已实现、验证并保留数据更新本机8001；四个RSS真实读取通过，用户反馈概览警示条贴住统计卡片，页内22px间距已修正，桌面/手机检查及8项UI回归通过，准备更新8001。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发。分支codex/linuxdo-integration，最后实现54bee56f750dfb502a8439ea1ee6acdba20d1a45；后续仅交付文档提交，均未推送/合并。用户“可以 采用这个方案”批准正式接入，沿用保留数据更新同一本机8001授权；公开发布、远程部署、主动真实发送另计。无多代理，不改D盘/旧Ubuntu/全局WSL/8000/4175。

## 读取入口与实现

先读[概览警示间距](history/2026-10-24-概览警示间距.md)及[HTTP/2接入与交付](history/2026-10-24-LinuxDO-HTTP2接入.md)，按需读同日HTTP2验证/匿名客户端实验、前日访问诊断及LinuxDO接入记录。权威需求SPEC 6.2、架构ARCHITECTURE/DECISIONS；代码backend/seekbell/collectors/http及rss、services/runtime/request_budget/hotlists。

public_client仅为https://linux.do挂载HTTP/2池，Runtime采集/连接测试和HotlistService共用，默认其他来源仍HTTP/1.1；测试注入transport覆盖全部请求、统一关闭资源。httpx仍0.28.1，新增锁定h2/hpack/hyperframe，无curl_cffi/浏览器/Cookie。去Cookie、TLS、禁代理/跳转、1MiB限制与原持久退避保持；HTTPX可正常协商回退，挑战不换客户端绕过。无迁移/前端/规则通知改动。

## 证据与限制

实现工作区后端720通过（新增4），Ruff/格式/锁/隐私/wheel通过。镜像构建及离线容器检查通过；未改前端，复用原相关84项浏览器结果。07:35候选镜像内由生产collector/热榜服务有界读取四个RSS，各30条、均200/HTTP/2/无Cookie，未打开数据库/启动Runtime/发通知；不代表长期、PVE/arm64或用户验收。

证据均在/home/dev/.local/state/seekbell/acceptance/2026-10-24-linuxdo-http2-integration，详见backend.log、container.log、container-rss.json、image-size.json、backup-verification.json、private-data-preflight.json、deployment-result.json、windows-after-update.json。此前H2成功/H1仍403对照及curl备选详见历史；不认定Cloudflare具体规则。

## 本机运行与回退

8001同一seekbell-local/seekbell-local-seekbell-1、原卷seekbell-local_data；镜像seekbell:linuxdo-http2-54bee56f750d，ID sha256:631f2a65080c75e8de8f91bc2e3d4830c36e97d7744fc33d07c8ab609aff199a，增加约1.41MiB（0.53%）。schema0011、healthy/read-only/unless-stopped；原账号/配置/密钥保留，未自动新增启用网站。

整卷备份local-runtime/backups/before-http2-54bee56-20261024-073950.tar.gz；SHA及逐文件/解包SQLite校验见交付记录。隔离副本全表/12类配置/凭据通过，正式切换后配置一致；临时卷已清理。旧e1d2f21同schema镜像与备份保留，失败归档/恢复流程已备；更早312d657回退须匹配0010整卷。

原Windows保活PID14716消失导致发行版/Docker反复冷启动，切换前已核实并恢复既有运行方式。新PID32480、创建2026-10-23T23:39:27.9859010Z，身份核对通过；无全局配置变更。runtime.json已更新。Windows两地址/版本/资源通过。

最新只读核对Linux DO仍保留07:37的access_challenge，预算阻塞至08:07:03（北京时间），未清理退避或发额外RSS。本轮Overview.vue/UI_DESIGN/交付记录本地提交，构建新镜像并按已有授权更新8001；持续运行和PVE另验，推送/合并待授权。本轮实现与交付记录均本地保存；恢复时核对实际HEAD，产品实现SHA如上。
