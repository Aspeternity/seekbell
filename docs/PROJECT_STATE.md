# 当前状态

更新时间：2026-10-24（Asia/Shanghai）。Linux DO榜单短等、首次测试伪限频与网站排序修复已保留数据更新本机8001；后端750/浏览器48项及容器检查通过，用户界面验收待。

## 环境与授权

唯一SeekBell-Dev:/home/dev/projects/seekbell，经原Ubuntu的wsl.exe派发。分支codex/linuxdo-integration，最后实现9597083899b834a3406d5a715cf6cee76575d707；后续交付文档提交，均未推送/合并。用户要求继续三项修复，沿用本机8001保留数据更新授权；公开发布/远程部署/主动真实发送另计。无多代理，不改D盘/旧Ubuntu/全局WSL/8000/4175。

## 本任务读取与实现

先读[多站验收修正](history/2026-10-24-LinuxDO验收修正.md)，追溯再读同日退避/HTTP2记录。SPEC6.2、ARCHITECTURE/DECISIONS、UI_DESIGN已同步；相关代码request_budget/source_probe/hotlists/overview_preferences、api/management、WebsiteInstallation/0013、CommunityHotlist。
自动失败曾错误占60秒人工配额；现仅真实人工预算reserve占配额，未发请求的延期短等2秒。0013从实际测试证据修正旧伪配额，服务器等待保持。HTTP/2、退避阶梯/保护、NodeSeek和概览22px间距保持。
Linux DO热榜关闭跨周期预取，忙碌/间隔返回waiting并自动重试、保留旧条目，真实来源异常据实展示。每日已有成功快照，不能将全部历史错误归于同因。网站原按ID排序，现position按添加顺序，移除重加置末；原库rowid确认NodeSeek在先。

## 验证与限制

私有acceptance/2026-10-24-linuxdo-followups：backend-final.log（750）、Linux DO16/热榜26/操作6项浏览器日志；格式/类型/构建/锁/隐私/wheel通过。container/backup-container/release-container.log证明离线启动、加密备份及未来迁移/回退演练通过，全部合成服务。
12:16只读正式核对：0013、NodeSeek1/Linux DO2、人工配额0、无测试记录；每日/热门/每周各30条快照保留。新实例自动采集成功、failures=0、错误空，健康下一次60秒；没有额外人工RSS/测试/通知请求。仅证明当前本机，长期/PVE/arm64与用户验收未完成。

## 本机运行与回退

同一seekbell-local/seekbell-local-seekbell-1、原卷seekbell-local_data、127.0.0.1:8001；镜像seekbell:linuxdo-followups-9597083899b8，ID sha256:e3370a9355fa54d8212b59d94867ca9cfc6e7fa4953ae7d523ee59fa6838579f。healthy/read-only/unless-stopped，原账号/配置/密钥保留；Windows两地址/版本/资源及22px通过，保活PID32480及创建时间未变。local-runtime/runtime.json已更新。
整卷备份before-followups-9597083-20261024-121559.tar.gz，SHA/逐文件/SQLite证据见新交付记录。副本原列/行（排除预期修复next_manual_at）、原配置/密钥/凭据一致，position/配额单独验证；正式配置与顺序复核通过，临时卷清理。
旧30252ce/0012镜像与匹配备份保留；回退必须恢复该整卷再启旧镜像，禁止旧镜像读0013。下一步用户刷新8001验每日榜单与测试结果；遇上游真实异常按code/服务器等待排查，不能清空等待掩盖。推送/合并待授权。
